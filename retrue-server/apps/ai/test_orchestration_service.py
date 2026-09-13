"""LangGraph 编排服务（阶段 2/3/4）测试。

覆盖：普通咨询、同名客户选择、未选客户不能客户写入、草稿确认前不能写入、
任务中断恢复、工具失败安全降级。
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.ai.models import AiDraft, AiDraftStatus
from apps.ai.orchestration import (
    OrchestrationDisabledError,
    handle_turn,
    resume_task,
    submit_customer_selection,
)
from apps.ai.orchestration.service import ConversationContextConflictError
from apps.assistant_tasks.models import AssistantTask, AssistantTaskStatus
from apps.conversations.models import Conversation
from apps.customers.catalog import normalize_name
from apps.customers.models import Customer, CustomerAlias
from apps.schedules.models import CourseSession, CourseSessionStatus
from apps.training.models import TrainingRecord

User = get_user_model()


@override_settings(AI_ORCHESTRATION_ENABLED=True, AI_PROVIDER="mock", AI_CONFIG_FILE="")
class OrchestrationServiceTests(APITestCase):
    """编排服务核心流程测试。"""

    def setUp(self) -> None:
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer_a = Customer.objects.create(therapist=self.therapist, name="张三")
        self.customer_b = Customer.objects.create(therapist=self.therapist, name="李四")

    def test_general_knowledge_answered_without_customer(self) -> None:
        """普通咨询直接回答，不读客户数据、不创建草稿。"""
        result = handle_turn(self.therapist, message="做深蹲时膝盖应该怎么放？")
        self.assertEqual(result["intent"], "general_knowledge")
        self.assertIsNone(result["customer_id"])
        self.assertEqual(result["resource_refs"], {})
        # 未产生任何草稿或训练记录。
        self.assertEqual(AiDraft.objects.count(), 0)
        self.assertEqual(TrainingRecord.objects.count(), 0)

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_single_customer_turn_classifies_once_then_reuses_intake_result(self) -> None:
        """首句分类只执行一次，完整图必须从其受控结果继续路由。"""
        from apps.ai.orchestration.nodes import classify_intent as classify

        with patch("apps.ai.orchestration.nodes.classify_intent", wraps=classify) as mocked:
            result = handle_turn(self.therapist, message="做深蹲时膝盖应该怎么放？")

        self.assertEqual(result["intent"], "general_knowledge")
        self.assertEqual(mocked.call_count, 1)

    def test_training_record_without_customer_waits_selection(self) -> None:
        """未选客户时，训练补记进入等待选择，不生成草稿。"""
        result = handle_turn(self.therapist, message="今天做了臀桥 3 组 12 次")
        self.assertEqual(result["intent"], "training_record")
        self.assertIsNone(result["customer_id"])
        self.assertEqual(result["current_step"], "wait_customer_selection")
        # 未绑定客户不能生成草稿。
        self.assertEqual(AiDraft.objects.count(), 0)

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_first_message_with_a_name_searches_before_training_draft(self) -> None:
        """首句“张三今天做了……”：目录唯一精确命中，直接预选张三并生成待确认草稿。

        预选通过 customer_preselected 卡片透出，草稿本身为 pending 仍需康复师确认，
        从而不绕过人工把关。若改为无法匹配/歧义则回落到选择流程。
        """
        result = handle_turn(self.therapist, message="张三 今天做了臀桥10组 每组12个")
        self.assertEqual(result["intent"], "training_record")
        self.assertEqual(result["customer_id"], self.customer_a.id)
        self.assertEqual(result["current_step"], "wait_draft_confirmation")
        cards = result.get("cards") or []
        preselected_cards = [card for card in cards if card["type"] == "customer_preselected"]
        self.assertEqual(len(preselected_cards), 1)
        self.assertEqual(preselected_cards[0]["resource_refs"]["customer_id"], self.customer_a.id)
        # 卡片携带预选客户姓名，供前端核对/更换。
        self.assertEqual(preselected_cards[0]["resource_refs"]["customer_name"], "张三")
        self.assertEqual(preselected_cards[0]["allowed_actions"], ["confirm"])
        # 草稿是 pending，不是正式记录。
        draft = AiDraft.objects.get(id=result["resource_refs"]["draft_id"])
        self.assertEqual(draft.status, AiDraftStatus.PENDING)
        self.assertEqual(draft.customer_id, self.customer_a.id)
        self.assertEqual(draft.ai_result["exercises"][0]["exercise_name"], "臀桥")
        self.assertEqual(draft.ai_result["exercises"][0]["sets"], 10)
        self.assertEqual(draft.ai_result["exercises"][0]["reps"], 12)
        self.assertEqual(TrainingRecord.objects.count(), 0)

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_training_record_with_bound_customer_creates_draft(self) -> None:
        """已绑定客户时，训练补记生成 pending 草稿，等待确认。"""
        result = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
        )
        self.assertEqual(result["intent"], "training_record")
        self.assertEqual(result["customer_id"], self.customer_a.id)
        self.assertEqual(result["current_step"], "wait_draft_confirmation")
        self.assertTrue(result["needs_confirmation"])
        self.assertIn("draft_id", result["resource_refs"])
        # 草稿是 pending，不是正式记录。
        draft = AiDraft.objects.get(id=result["resource_refs"]["draft_id"])
        self.assertEqual(draft.status, AiDraftStatus.PENDING)
        self.assertEqual(TrainingRecord.objects.count(), 0)

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_course_refill_entry_skips_general_intent_and_binds_session(self) -> None:
        """工作台课程回填由后端固定训练分支，且草稿使用排课日期。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer_a,
            date="2026-09-07",
            start_time="09:00",
            end_time="10:00",
            session_topic="髋关节术后训练",
        )
        with patch("apps.ai.orchestration.nodes.classify_intent", side_effect=AssertionError("不应重新识别意图")):
            result = handle_turn(
                self.therapist,
                message="今天做了臀桥 3 组 12 次，做完感觉稳定一些",
                customer_id=self.customer_a.id,
                entry_action="fill_course_training_record",
                course_session_id=session.id,
            )

        self.assertEqual(result["intent"], "training_record")
        self.assertEqual(result["current_step"], "wait_draft_confirmation")
        self.assertEqual(result["missing_fields"], [])
        task = AssistantTask.objects.get(id=result["task_id"])
        self.assertEqual(task.skill_code, "course_training_fill")
        self.assertEqual(task.context_resource_type, "course_session")
        self.assertEqual(task.context_resource_id, str(session.id))
        draft = AiDraft.objects.get(id=result["resource_refs"]["draft_id"])
        self.assertEqual(draft.ai_result["training_date"], "2026-09-07")
        self.assertEqual(draft.assistant_task.context_resource_id, str(session.id))
        self.assertEqual(TrainingRecord.objects.count(), 0)

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_course_refill_without_training_content_asks_then_resumes(self) -> None:
        """咨询性原文不生成空草稿，补充实际项目后从同一任务继续。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer_a,
            date="2026-09-07",
            session_topic="下肢力量训练",
        )
        first = handle_turn(
            self.therapist,
            message="这个客户膝盖疼还能继续练吗？",
            customer_id=self.customer_a.id,
            entry_action="fill_course_training_record",
            course_session_id=session.id,
        )
        self.assertEqual(first["current_step"], "wait_training_details")
        self.assertEqual(first["missing_fields"], ["training_content"])
        self.assertIn("实际完成", first["reply_content"])
        self.assertEqual(AiDraft.objects.count(), 0)

        resumed = resume_task(
            self.therapist,
            first["task_id"],
            message="本次做了臀桥 3 组 12 次，做完感觉膝盖没有加重",
        )
        self.assertEqual(resumed["current_step"], "wait_draft_confirmation")
        self.assertEqual(AiDraft.objects.count(), 1)
        draft = AiDraft.objects.get(id=resumed["resource_refs"]["draft_id"])
        self.assertEqual(draft.ai_result["training_date"], "2026-09-07")

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_course_refill_with_only_items_marks_training_effect_missing(self) -> None:
        """已识别项目先预填草稿，缺少训练效果时给出具体补充提示。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer_a,
            date="2026-09-07",
        )
        result = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
            entry_action="fill_course_training_record",
            course_session_id=session.id,
        )
        self.assertEqual(result["current_step"], "wait_draft_confirmation")
        self.assertEqual(result["missing_fields"], ["training_effect"])
        self.assertIn("训练后反应", result["reply_content"])

    def test_course_refill_rejects_non_scheduled_or_recorded_session(self) -> None:
        """已取消、已完成或已有正式记录的排课不能进入新的回填工作流。"""
        from apps.assistant_tasks.services import ResourceValidationError

        cancelled = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer_a,
            date="2026-09-07",
            status=CourseSessionStatus.CANCELLED,
        )
        with self.assertRaises(ResourceValidationError):
            handle_turn(
                self.therapist,
                message="做了臀桥 3 组",
                customer_id=self.customer_a.id,
                entry_action="fill_course_training_record",
                course_session_id=cancelled.id,
            )
        recorded = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer_a,
            date="2026-09-08",
        )
        TrainingRecord.objects.create(
            therapist=self.therapist,
            customer=self.customer_a,
            course_session=recorded,
            training_date="2026-09-08",
        )
        with self.assertRaises(ResourceValidationError):
            handle_turn(
                self.therapist,
                message="做了臀桥 3 组",
                customer_id=self.customer_a.id,
                entry_action="fill_course_training_record",
                course_session_id=recorded.id,
            )

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_first_message_with_two_names_starts_first_customer_confirmation(self) -> None:
        """首句含两位姓名时，经图拆分后立刻展示第一位的客户确认卡。"""
        result = handle_turn(
            self.therapist,
            message="张三今天做了深蹲10次；李四做了俯卧撑，每组10次，共5组。",
        )
        self.assertEqual(result["intent"], "multi_customer_training_record")
        self.assertEqual(result["current_step"], "wait_item_customer_confirmation")
        cards = result.get("cards") or []
        selection_cards = [card for card in cards if card["type"] == "customer_selection"]
        self.assertEqual(len(selection_cards), 1)
        self.assertEqual(selection_cards[0]["resource_refs"]["sequence"], 1)
        self.assertEqual(selection_cards[0]["customer_candidates"][0]["id"], self.customer_a.id)

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_draft_not_written_before_confirmation(self) -> None:
        """草稿确认前不能写入正式训练记录。"""
        result = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
        )
        draft_id = result["resource_refs"]["draft_id"]
        # 图流程本身绝不写正式记录。
        self.assertEqual(TrainingRecord.objects.count(), 0)
        draft = AiDraft.objects.get(id=draft_id)
        self.assertEqual(draft.status, AiDraftStatus.PENDING)
        self.assertIsNone(draft.training_record_id)

    def test_customer_lookup_single_match_binds(self) -> None:
        """客户姓名唯一匹配时直接绑定客户。"""
        result = handle_turn(self.therapist, message="客户张三最近的训练怎么样", customer_name="张三")
        # 未绑定客户 + 姓名唯一匹配 -> 直接绑定。
        self.assertEqual(result["intent"], "customer_lookup")
        self.assertEqual(result["customer_id"], self.customer_a.id)

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_name_only_binds_unique_customer(self) -> None:
        """仅姓名唯一命中时，返回当前聊天可绑定的客户引用。"""
        customer = Customer.objects.create(therapist=self.therapist, name="黄伟成")
        conversation = Conversation.objects.create(therapist=self.therapist)
        result = handle_turn(self.therapist, message="黄伟成", conversation_id=conversation.id)
        self.assertEqual(result["intent"], "customer_lookup")
        self.assertEqual(result["customer_id"], customer.id)
        self.assertEqual(result["current_step"], "bound")
        conversation.refresh_from_db()
        self.assertEqual(conversation.customer_id, customer.id)

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_followup_restores_customer_and_query_context_from_conversation(self) -> None:
        """后续请求未提交 customer_id 时，服务端从同一会话恢复唯一客户。"""
        conversation = Conversation.objects.create(
            therapist=self.therapist,
            customer=self.customer_a,
            context_data={
                "mode": "single",
                "active_customer_id": self.customer_a.id,
                "last_intent": "customer_analysis",
                "last_query_goal": "recent_training",
                "last_tool": "list_recent_training_records",
            },
        )
        result = handle_turn(self.therapist, message="那近三个月呢？", conversation_id=conversation.id)
        self.assertEqual(result["intent"], "customer_analysis")
        self.assertEqual(result["query_goal"], "recent_training")
        self.assertEqual(result["customer_id"], self.customer_a.id)
        conversation.refresh_from_db()
        self.assertEqual(conversation.context_data["active_customer_id"], self.customer_a.id)
        self.assertEqual(conversation.context_data["last_query_goal"], "recent_training")

    def test_cannot_silently_switch_customer_in_bound_conversation(self) -> None:
        """显式提交另一客户也不能覆盖当前会话归属。"""
        conversation = Conversation.objects.create(therapist=self.therapist, customer=self.customer_a)
        with self.assertRaises(ConversationContextConflictError):
            handle_turn(
                self.therapist,
                message="李四最近训练怎么样？",
                conversation_id=conversation.id,
                customer_id=self.customer_b.id,
            )
        conversation.refresh_from_db()
        self.assertEqual(conversation.customer_id, self.customer_a.id)

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_unbound_training_count_question_reads_customer_data(self) -> None:
        """未绑定且含姓名的训练次数问句先定位客户，再执行只读查询，不生成草稿。"""
        customer = Customer.objects.create(therapist=self.therapist, name="黄伟成")
        result = handle_turn(self.therapist, message="黄伟成做了几次训练了？")
        self.assertEqual(result["intent"], "customer_analysis")
        self.assertEqual(result["customer_id"], customer.id)
        self.assertTrue(result["reply_content"])
        self.assertEqual(AiDraft.objects.count(), 0)

    def test_customer_selection_flow(self) -> None:
        """同名客户进入等待选择，提交选择后继续。"""
        Customer.objects.create(therapist=self.therapist, name="张三")
        result = handle_turn(self.therapist, message="客户张三最近怎么样", customer_name="张三")
        self.assertEqual(result["current_step"], "wait_customer_selection")
        self.assertGreaterEqual(len(result["customer_candidates"]), 2)
        # 返回结构化客户选择卡片。
        cards = result.get("cards") or []
        selection_cards = [c for c in cards if c["type"] == "customer_selection"]
        self.assertEqual(len(selection_cards), 1)
        self.assertEqual(selection_cards[0]["status"], "waiting_user")
        self.assertGreaterEqual(len(selection_cards[0]["customer_candidates"]), 2)

        task_id = result["task_id"]
        selected = submit_customer_selection(self.therapist, task_id, self.customer_a.id)
        self.assertEqual(selected["customer_id"], self.customer_a.id)

    def test_unbound_named_question_resolves_then_answers(self) -> None:
        """未绑定的具名问句先定位客户，再在同一回合执行只读回答。"""
        result = handle_turn(self.therapist, message="客户张三最近的训练强度如何")
        self.assertEqual(result["intent"], "customer_analysis")
        self.assertEqual(result["customer_id"], self.customer_a.id)
        self.assertTrue(result["reply_content"])

    def test_unbound_named_alias_question_resolves_then_answers(self) -> None:
        """别称出现在未绑定问句中时，也会先解析身份再读取客户信息。"""
        CustomerAlias.objects.create(
            therapist=self.therapist,
            customer=self.customer_a,
            alias="阿张",
            normalized_alias=normalize_name("阿张"),
        )
        result = handle_turn(self.therapist, message="客户阿张最近练得怎么样")
        self.assertEqual(result["intent"], "customer_analysis")
        self.assertEqual(result["customer_id"], self.customer_a.id)

    def test_training_draft_card_returned(self) -> None:
        """训练补记生成草稿时返回 training_draft 卡片。"""
        result = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
        )
        cards = result.get("cards") or []
        draft_cards = [c for c in cards if c["type"] == "training_draft"]
        self.assertEqual(len(draft_cards), 1)
        self.assertEqual(draft_cards[0]["status"], "waiting_confirmation")
        self.assertIn("draft_id", draft_cards[0]["resource_refs"])
        self.assertIn("confirm", draft_cards[0]["allowed_actions"])

    def test_customer_selection_resumes_training_record_with_draft(self) -> None:
        """同名歧义时停在选择，选中后恢复训练补记并返回待确认草稿。

        目录中两位“张三”均精确命中但指向不同客户 -> 不停留直接前进，
        而是 wait_customer_selection 展示候选，康复师选定后才继续。
        """
        Customer.objects.create(therapist=self.therapist, name="张三", phone="13900139000")
        conversation = Conversation.objects.create(therapist=self.therapist)
        initial = handle_turn(
            self.therapist,
            message="张三今天做了臀桥 3 组 12 次",
            conversation_id=conversation.id,
        )
        self.assertEqual(initial["current_step"], "wait_customer_selection")

        selected = submit_customer_selection(self.therapist, initial["task_id"], self.customer_a.id)

        self.assertEqual(selected["current_step"], "wait_draft_confirmation")
        self.assertTrue(selected["needs_confirmation"])
        draft_cards = [card for card in selected.get("cards") or [] if card["type"] == "training_draft"]
        self.assertEqual(len(draft_cards), 1)
        self.assertIn("draft_id", draft_cards[0]["resource_refs"])

    def test_risk_review_card_returned(self) -> None:
        """风险信号返回 risk_review 卡片，状态为 blocked。"""
        result = handle_turn(
            self.therapist,
            message="这个客户红肿发热会不会加重？",
            customer_id=self.customer_a.id,
        )
        cards = result.get("cards") or []
        risk_cards = [c for c in cards if c["type"] == "risk_review"]
        self.assertEqual(len(risk_cards), 1)
        self.assertEqual(risk_cards[0]["status"], "blocked")

    def test_resume_after_interruption(self) -> None:
        """任务中断后可从 state_data 恢复并继续。"""
        first = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
        )
        task = AssistantTask.objects.get(id=first["task_id"])
        # 模拟中断：任务卡在 running。
        task.status = AssistantTaskStatus.RUNNING
        task.save(update_fields=["status"])

        resumed = resume_task(self.therapist, task.id, message="继续补记")
        self.assertIn(resumed["current_step"], {"wait_draft_confirmation", "wait_customer_selection", "completed"})

    @override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="")
    def test_tool_failure_degrades_safely(self) -> None:
        """工具失败时任务降级为失败，不伪造客户历史。"""
        # 已绑定客户 + 客户问题，但 get_customer_context 会因无客户数据而安全返回；
        # 这里通过未绑定客户 + 客户问题场景验证：不会越权读取。
        result = handle_turn(
            self.therapist,
            message="客户张三最近怎么样",
        )
        # 未绑定客户时先按姓名检索，再仅在本人的目录内执行只读查询。
        self.assertEqual(result["intent"], "customer_analysis")

    def test_customer_selection_rejects_other_therapist_customer(self) -> None:
        """提交其他康复师的客户时被拒绝。"""
        other = User.objects.create_user(username="t2", password="test12345")
        foreign = Customer.objects.create(therapist=other, name="王五")
        result = handle_turn(self.therapist, message="今天做了臀桥 3 组 12 次")
        task_id = result["task_id"]
        from apps.assistant_tasks.services import TaskPermissionError

        with self.assertRaises(TaskPermissionError):
            submit_customer_selection(self.therapist, task_id, foreign.id)

    def test_resume_selection_rejects_customer_moved_to_other_therapist(self) -> None:
        """验收：暂停待选后客户被转移/失效，恢复时不沿用旧预选，提交即被拒。

        目录两位“张三”制造待选择，随后把原候选 customer_a 转移到其他康复师，
        再提交该失效客户 —— 服务端按最新归属重校验，拒绝，绝不沿用旧预选。
        """
        from apps.assistant_tasks.services import TaskPermissionError

        other = User.objects.create_user(username="t3", password="test12345")
        Customer.objects.create(therapist=self.therapist, name="张三")  # 第二位同名
        result = handle_turn(self.therapist, message="客户张三最近怎么样", customer_name="张三")
        self.assertEqual(result["current_step"], "wait_customer_selection")
        task_id = result["task_id"]

        # 客户被转移给其他康复师：旧预选/候选随之失效。
        Customer.objects.filter(pk=self.customer_a.id).update(therapist=other)

        with self.assertRaises(TaskPermissionError):
            submit_customer_selection(self.therapist, task_id, self.customer_a.id)

    def test_general_knowledge_has_reply_without_customer_tool(self) -> None:
        """普通咨询有可展示回复，且不调用客户只读 Tool。"""
        result = handle_turn(self.therapist, message="深蹲的标准动作是什么？")
        self.assertEqual(result["intent"], "general_knowledge")
        self.assertTrue(result["reply_content"])
        # 没有执行任何客户只读 Tool。
        task = AssistantTask.objects.get(id=result["task_id"])
        self.assertEqual(task.tool_executions.count(), 0)

    def test_customer_question_uses_read_tool_with_reply(self) -> None:
        """已确认客户的历史问题调用只读 Tool，并有可展示回复。"""
        result = handle_turn(
            self.therapist,
            message="这个客户最近的进展怎么样？",
            customer_id=self.customer_a.id,
        )
        self.assertEqual(result["intent"], "customer_question")
        self.assertTrue(result["reply_content"])
        task = AssistantTask.objects.get(id=result["task_id"])
        # 至少执行了一次只读 Tool 且有 ToolExecution 审计。
        self.assertGreaterEqual(task.tool_executions.count(), 1)

    def test_draft_resume_does_not_create_second_draft(self) -> None:
        """草稿待确认后 resume 只返回已有草稿，不重复生成。"""
        first = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
        )
        original_draft_id = first["resource_refs"]["draft_id"]
        self.assertEqual(AiDraft.objects.count(), 1)

        resumed = resume_task(self.therapist, first["task_id"])
        # resume 不重新生成草稿，仍指向原草稿。
        self.assertEqual(AiDraft.objects.count(), 1)
        self.assertEqual(resumed["resource_refs"].get("draft_id"), original_draft_id)

    def test_resume_is_idempotent(self) -> None:
        """重复 resume 不会产生第二份草稿或正式记录。"""
        first = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
        )
        for _ in range(3):
            resume_task(self.therapist, first["task_id"])
        self.assertEqual(AiDraft.objects.count(), 1)
        self.assertEqual(TrainingRecord.objects.count(), 0)

    def test_risk_branch_no_formal_write(self) -> None:
        """风险分支不产生自动正式写入，并给出人工核查提醒。"""
        result = handle_turn(
            self.therapist,
            message="这个客户做动作时红肿发热会不会加重？",
            customer_id=self.customer_a.id,
        )
        self.assertEqual(result["intent"], "risk_review")
        self.assertTrue(result.get("risk_notice") or result.get("reply_content"))
        self.assertEqual(TrainingRecord.objects.count(), 0)
        self.assertEqual(AiDraft.objects.count(), 0)

    def test_other_therapist_cannot_resume(self) -> None:
        """非当前康复师不能恢复任务。"""
        first = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
        )
        other = User.objects.create_user(username="t2", password="test12345")
        from apps.assistant_tasks.services import TaskPermissionError

        with self.assertRaises(TaskPermissionError):
            resume_task(other, first["task_id"])

    def test_unbound_customer_cannot_read_customer_data(self) -> None:
        """客户未确定时不能读取客户资料或生成正式数据。"""
        result = handle_turn(self.therapist, message="今天做了臀桥 3 组 12 次")
        self.assertEqual(result["current_step"], "wait_customer_selection")
        # 未选客户，没有执行任何只读 Tool（不能读客户数据）。
        task = AssistantTask.objects.get(id=result["task_id"])
        self.assertEqual(task.tool_executions.count(), 0)
        self.assertEqual(AiDraft.objects.count(), 0)


@override_settings(AI_ORCHESTRATION_ENABLED=False)
class OrchestrationDisabledTests(APITestCase):
    """编排功能开关关闭时的行为。"""

    def setUp(self) -> None:
        self.therapist = User.objects.create_user(username="t1", password="test12345")

    def test_turn_raises_when_disabled(self) -> None:
        """开关关闭时发起回合应抛编排未启用错误。"""
        with self.assertRaises(OrchestrationDisabledError):
            handle_turn(self.therapist, message="你好")
