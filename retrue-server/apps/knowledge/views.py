"""knowledge：客户知识库接口视图。

提供知识条目 CRUD 与 AI 候选确认接口。
数据隔离：所有查询限定当前康复师本人，且知识严格按客户归属。
正式知识的增删改必须写入审计日志。
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.audit.models import AuditAction, write_audit_log
from apps.common.response import ApiResponse
from apps.customers.models import Customer
from apps.knowledge.models import (
    CandidateStatus,
    CustomerKnowledgeItem,
    KnowledgeCandidate,
    KnowledgeSource,
    MemoryConflictType,
    MemoryEpisode,
    EpisodeStatus,
    MemoryStatus,
)
from apps.knowledge.memory_service import confirm_candidate, normalize_memory_value
from apps.knowledge.serializers import (
    CandidateConfirmSerializer,
    KnowledgeCandidateSerializer,
    KnowledgeItemSerializer,
    MemoryEpisodeSerializer,
    EpisodeDecisionSerializer,
)
from apps.knowledge.episode_service import decide_episode
from apps.knowledge.services import build_knowledge_index, rag_answer


class RagAnswerView(APIView):
    """RAG 回答接口（客户模式）。

    接收客户 ID 与问题，检索该客户的私有知识库，结合聊天模型生成回答。
    必须显式指定客户（customer），回答基于该客户的确认知识，不携带无关客户信息。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """基于客户私有知识库回答。"""
        customer_id = request.data.get("customer")
        question = (request.data.get("question") or "").strip()
        if not customer_id:
            return ApiResponse.error("缺少 customer 参数", 400)
        if not question:
            return ApiResponse.error("缺少 question 参数", 400)

        customer = Customer.objects.filter(id=customer_id, therapist=request.user).first()
        if customer is None:
            return ApiResponse.error("客户不存在或无权访问", 404)

        answer, chunks = rag_answer(
            customer_id,
            question,
            therapist_name=getattr(request.user, "therapist_profile", None)
            and request.user.therapist_profile.name
            or request.user.username,
            customer_name=customer.name,
        )
        return ApiResponse.ok(
            {
                "answer": answer,
                "used_knowledge": chunks,
                "using_customer_context": True,
            },
            message="RAG 回答生成成功",
        )


class KnowledgeIndexBuildView(APIView):
    """知识向量索引重建接口。

    为指定客户的全部激活知识条目生成向量，供 RAG 检索。
    无有效 embedding 密钥时会优雅降级（向量留空，检索走文本兜底）。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        customer_id = request.data.get("customer")
        if not customer_id:
            return ApiResponse.error("缺少 customer 参数", 400)
        customer = Customer.objects.filter(id=customer_id, therapist=request.user).first()
        if customer is None:
            return ApiResponse.error("客户不存在或无权访问", 404)
        updated = build_knowledge_index(customer_id)
        return ApiResponse.ok({"indexed": updated}, message="知识索引已更新")


class KnowledgeItemListView(APIView):
    """知识条目列表与创建。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回当前康复师指定客户的知识条目，按客户隔离；安全限制优先置顶。"""
        customer_id = request.query_params.get("customer", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer 参数", 400)

        queryset = CustomerKnowledgeItem.objects.filter(
            therapist=request.user, customer_id=customer_id
        )
        # 安全限制高重要性置顶，再按重要级别、分类、时间排序
        queryset = queryset.order_by(
            "-is_active",
            # 安全限制的高重要性知识优先
            "-importance",
            "category",
            "-created_at",
        )
        return ApiResponse.ok(KnowledgeItemSerializer(queryset, many=True).data, message="查询知识条目成功")

    def post(self, request):
        """康复师手动新增知识条目。"""
        serializer = KnowledgeItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        customer = data.pop("customer")
        # 手动新增只能生成已确认的 active 记忆，来源和生命周期由服务端决定。
        for field in (
            "source", "source_type", "source_id", "source_message_id", "status", "is_active",
            "confirmed_by_user", "normalized_value", "confidence", "effective_from", "effective_to",
            "last_confirmed_at", "supersedes_memory",
        ):
            data.pop(field, None)
        if customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户添加知识", 403)

        item = CustomerKnowledgeItem.objects.create(
            therapist=request.user,
            customer=customer,
            created_by=request.user,
            updated_by=request.user,
            normalized_value=normalize_memory_value(data.get("content", "")),
            source=KnowledgeSource.MANUAL,
            source_type="manual",
            status=MemoryStatus.ACTIVE,
            is_active=True,
            confirmed_by_user=True,
            effective_from=timezone.now(),
            last_confirmed_at=timezone.now(),
            **data,
        )
        write_audit_log(
            actor=request.user,
            action=AuditAction.CREATE,
            obj=item,
            after=KnowledgeItemSerializer(item).data,
            reason="知识条目新增",
        )
        return ApiResponse.ok(KnowledgeItemSerializer(item).data, message="知识条目已添加")


class KnowledgeItemDetailView(APIView):
    """知识条目详情：查看、更新、停用。"""

    permission_classes = [IsAuthenticated]

    def _get_item(self, request, item_id: int):
        """获取当前康复师的知识条目。"""
        return CustomerKnowledgeItem.objects.filter(therapist=request.user, id=item_id).first()

    def get(self, request, item_id: int):
        """返回知识条目详情。"""
        item = self._get_item(request, item_id)
        if item is None:
            return ApiResponse.error("知识条目不存在或无权访问", 404)
        return ApiResponse.ok(KnowledgeItemSerializer(item).data, message="查询知识条目成功")

    def put(self, request, item_id: int):
        """更新知识条目内容、分类、重要级别或生效状态。"""
        item = self._get_item(request, item_id)
        if item is None:
            return ApiResponse.error("知识条目不存在或无权访问", 404)
        serializer = KnowledgeItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # 防止越权：忽略请求中的 customer，保持原归属
        if "customer" in serializer.validated_data:
            serializer.validated_data.pop("customer")
        before = KnowledgeItemSerializer(item).data
        # 不允许客户端绕过生命周期规则直接伪造状态或来源。
        protected_fields = {"status", "source", "source_type", "source_id", "source_message_id", "confirmed_by_user"}
        for field, value in serializer.validated_data.items():
            if field in protected_fields:
                continue
            setattr(item, field, value)
        if "content" in serializer.validated_data:
            item.normalized_value = normalize_memory_value(item.content)
        # 兼容旧客户端的 is_active 切换，同时映射到新的生命周期状态。
        if "is_active" in serializer.validated_data:
            item.status = MemoryStatus.ACTIVE if item.is_active else MemoryStatus.EXPIRED
            item.effective_to = None if item.is_active else timezone.now()
        item.updated_by = request.user
        item.save()
        write_audit_log(
            actor=request.user,
            action=AuditAction.UPDATE,
            obj=item,
            before=before,
            after=KnowledgeItemSerializer(item).data,
            reason="知识条目更新",
        )
        return ApiResponse.ok(KnowledgeItemSerializer(item).data, message="知识条目已更新")

    def delete(self, request, item_id: int):
        """软删除记忆，保留审计与来源追溯，AI 不再读取。"""
        item = self._get_item(request, item_id)
        if item is None:
            return ApiResponse.error("知识条目不存在或无权访问", 404)
        before = KnowledgeItemSerializer(item).data
        item.status = MemoryStatus.DELETED
        item.is_active = False
        item.effective_to = timezone.now()
        item.updated_by = request.user
        item.save(update_fields=["status", "is_active", "effective_to", "updated_by", "updated_at"])
        write_audit_log(
            actor=request.user,
            action=AuditAction.DELETE,
            obj=item,
            before=before,
            reason="知识条目删除",
        )
        return ApiResponse.ok(message="记忆已删除")


class KnowledgeItemExpireView(APIView):
    """停用有效记忆，保留其历史和来源。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, item_id: int):
        """将当前康复师的一条记忆标记为 expired。"""
        item = CustomerKnowledgeItem.objects.filter(therapist=request.user, id=item_id).first()
        if item is None:
            return ApiResponse.error("记忆不存在或无权访问", 404)
        before = KnowledgeItemSerializer(item).data
        item.status = MemoryStatus.EXPIRED
        item.is_active = False
        item.effective_to = timezone.now()
        item.updated_by = request.user
        item.save(update_fields=["status", "is_active", "effective_to", "updated_by", "updated_at"])
        write_audit_log(
            actor=request.user,
            action=AuditAction.UPDATE,
            obj=item,
            before=before,
            after=KnowledgeItemSerializer(item).data,
            reason="长期记忆停用",
        )
        return ApiResponse.ok(KnowledgeItemSerializer(item).data, message="记忆已停用")


class KnowledgeCandidateListView(APIView):
    """AI 知识候选列表与提交。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回当前康复师指定客户的候选记忆，可按状态筛选。"""
        customer_id = request.query_params.get("customer", "")
        status = request.query_params.get("status", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer 参数", 400)
        queryset = KnowledgeCandidate.objects.filter(therapist=request.user, customer_id=customer_id)
        if status == "open":
            queryset = queryset.filter(status__in=[CandidateStatus.PENDING, CandidateStatus.DEFERRED])
        elif status:
            queryset = queryset.filter(status=status)
        return ApiResponse.ok(
            KnowledgeCandidateSerializer(queryset.order_by("-suggested_at"), many=True).data,
            message="查询知识候选成功",
        )

    def post(self, request):
        """提交一条 AI 建议候选记忆（不自动写入正式知识）。"""
        serializer = KnowledgeCandidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        customer = data.pop("customer")
        if customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户提交候选", 403)
        candidate = KnowledgeCandidate.objects.create(
            therapist=request.user, customer=customer, **data
        )
        return ApiResponse.ok(KnowledgeCandidateSerializer(candidate).data, message="候选已提交，待确认")


class KnowledgeCandidateConfirmView(APIView):
    """AI 知识候选确认/拒绝。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, candidate_id: int):
        """确认或拒绝候选记忆；确认时转为正式知识并写入审计。"""
        candidate = KnowledgeCandidate.objects.filter(
            therapist=request.user, id=candidate_id
        ).first()
        if candidate is None:
            return ApiResponse.error("候选不存在或无权访问", 404)
        if candidate.status not in {CandidateStatus.PENDING, CandidateStatus.DEFERRED}:
            return ApiResponse.error("该候选已处理", 400)

        serializer = CandidateConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]

        if action == "confirm" and candidate.conflict_type == MemoryConflictType.CONFLICT:
            return ApiResponse.error("该候选与有效记忆冲突，请选择替代、保留旧记忆、条件并存或暂缓", 400)

        candidate.decided_by = request.user
        candidate.decided_at = timezone.now()
        candidate.resolution_action = action

        if action == "defer":
            candidate.status = CandidateStatus.DEFERRED
        elif action in {"reject", "keep_existing"}:
            candidate.status = CandidateStatus.REJECTED
        else:
            candidate.status = CandidateStatus.CONFIRMED
            if "category" in serializer.validated_data:
                candidate.category = serializer.validated_data["category"]
            if "memory_type" in serializer.validated_data:
                candidate.memory_type = serializer.validated_data["memory_type"]
            if "importance_score" in serializer.validated_data:
                candidate.importance_score = serializer.validated_data["importance_score"]
            if action == "coexist":
                candidate.memory_key = serializer.validated_data.get(
                    "resolved_memory_key", f"{candidate.memory_key}.condition.{candidate.id}"
                )
            candidate.save(update_fields=["category", "memory_type", "importance_score", "memory_key"])
            item, created = confirm_candidate(
                candidate,
                request.user,
                supersede_existing=(
                    action == "replace" or serializer.validated_data["supersede_existing"]
                ),
            )
            # 保持旧接口的 high/normal 语义；新模块使用 importance_score 做精细排序。
            if "importance" in serializer.validated_data:
                item.importance = serializer.validated_data["importance"]
                item.save(update_fields=["importance", "updated_at"])
            candidate.knowledge_item = item
            write_audit_log(
                actor=request.user,
                action=AuditAction.CREATE,
                obj=item,
                after=KnowledgeItemSerializer(item).data,
                reason=("候选确认新增：" if created else "候选确认去重：") + (candidate.source_ref or "AI 建议"),
            )
        candidate.save()
        return ApiResponse.ok(KnowledgeCandidateSerializer(candidate).data, message="候选已处理")


class MemoryEpisodeListView(APIView):
    """查询当前康复师指定客户的历史讨论事件。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """按客户和可选状态返回 Episode。"""
        customer_id = request.query_params.get("customer", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer 参数", 400)
        queryset = MemoryEpisode.objects.filter(
            therapist=request.user,
            customer_id=customer_id,
        ).exclude(status=EpisodeStatus.DELETED).select_related("conversation")
        status = request.query_params.get("status", "")
        if status:
            queryset = queryset.filter(status=status)
        return ApiResponse.ok(
            MemoryEpisodeSerializer(queryset, many=True).data,
            message="查询历史讨论事件成功",
        )


class MemoryEpisodeDecisionView(APIView):
    """确认或拒绝一个 Episode 候选。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, episode_id: int):
        """处理属于当前康复师的 Episode。"""
        episode = MemoryEpisode.objects.filter(therapist=request.user, id=episode_id).first()
        if episode is None:
            return ApiResponse.error("历史讨论事件不存在或无权访问", 404)
        serializer = EpisodeDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        before = MemoryEpisodeSerializer(episode).data
        try:
            decide_episode(episode, request.user, serializer.validated_data["action"])
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        after = MemoryEpisodeSerializer(episode).data
        write_audit_log(
            actor=request.user,
            action=AuditAction.UPDATE,
            obj=episode,
            before=before,
            after=after,
            reason="历史讨论事件确认" if serializer.validated_data["action"] == "confirm" else "历史讨论事件拒绝",
        )
        return ApiResponse.ok(after, message="历史讨论事件已处理")


class MemoryEpisodeDetailView(APIView):
    """删除不再需要的 Episode，保留记录但不进入上下文。"""

    permission_classes = [IsAuthenticated]

    def delete(self, request, episode_id: int):
        """将 Episode 标记为 deleted。"""
        episode = MemoryEpisode.objects.filter(therapist=request.user, id=episode_id).first()
        if episode is None:
            return ApiResponse.error("历史讨论事件不存在或无权访问", 404)
        before = MemoryEpisodeSerializer(episode).data
        episode.status = "deleted"
        episode.decided_by = request.user
        episode.decided_at = timezone.now()
        episode.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
        write_audit_log(
            actor=request.user,
            action=AuditAction.DELETE,
            obj=episode,
            before=before,
            reason="历史讨论事件删除",
        )
        return ApiResponse.ok(message="历史讨论事件已删除")
