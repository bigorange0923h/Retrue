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
)
from apps.knowledge.serializers import (
    CandidateConfirmSerializer,
    KnowledgeCandidateSerializer,
    KnowledgeItemSerializer,
)
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
        if customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户添加知识", 403)

        item = CustomerKnowledgeItem.objects.create(
            therapist=request.user,
            customer=customer,
            created_by=request.user,
            updated_by=request.user,
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
        for field, value in serializer.validated_data.items():
            setattr(item, field, value)
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
        """删除知识条目（保留审计，避免误删历史）。"""
        item = self._get_item(request, item_id)
        if item is None:
            return ApiResponse.error("知识条目不存在或无权访问", 404)
        before = KnowledgeItemSerializer(item).data
        item.delete()
        write_audit_log(
            actor=request.user,
            action=AuditAction.DELETE,
            obj=item,
            before=before,
            reason="知识条目删除",
        )
        return ApiResponse.ok(message="知识条目已删除")


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
        if status:
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
        if candidate.status != CandidateStatus.PENDING:
            return ApiResponse.error("该候选已处理", 400)

        serializer = CandidateConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]

        candidate.status = (
            CandidateStatus.CONFIRMED if action == "confirm" else CandidateStatus.REJECTED
        )
        candidate.decided_by = request.user
        candidate.decided_at = timezone.now()

        if action == "confirm":
            item = CustomerKnowledgeItem.objects.create(
                therapist=request.user,
                customer=candidate.customer,
                category=serializer.validated_data.get("category", candidate.category),
                content=candidate.content,
                source=KnowledgeSource.AI_CONFIRMED,
                importance=serializer.validated_data.get("importance"),
                created_by=request.user,
                updated_by=request.user,
            )
            candidate.knowledge_item = item
            write_audit_log(
                actor=request.user,
                action=AuditAction.CREATE,
                obj=item,
                after=KnowledgeItemSerializer(item).data,
                reason=f"候选确认：{candidate.source_ref or 'AI 建议'}",
            )
        candidate.save()
        return ApiResponse.ok(KnowledgeCandidateSerializer(candidate).data, message="候选已处理")
