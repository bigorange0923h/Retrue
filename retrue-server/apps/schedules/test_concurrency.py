"""PostgreSQL 双连接课程并发验收；SQLite 不替代行锁与事务锁验证。"""

from datetime import date, time, timedelta
from decimal import Decimal
from queue import Queue
from threading import Barrier, Thread
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.ai.models import AiDraft, AiDraftStatus
from apps.ai.services.training_parser import confirm_training_draft
from apps.courses.models import CourseAdjustment, CourseAdjustmentType, CoursePackage
from apps.courses.services import complete_session_for_record
from apps.customers.models import Customer
from apps.rehab.models import RehabPlan
from apps.schedules.locking import CourseWriteBusyError, course_write_transaction
from apps.schedules.models import CourseSession, CourseSessionStatus, CourseType, PlanCourseStatus, RehabPlanCourse
from apps.schedules.services import (
    adjust_plan_course_count,
    confirm_batch_schedule,
    create_course_session,
    update_course_session,
    update_plan_course,
)
from apps.training.models import TrainingRecord


@skipUnless(connection.vendor == "postgresql", "课程并发验收必须使用 PostgreSQL 双连接")
class CourseConcurrencyTests(TransactionTestCase):
    """同一康复师跨计划、单节/批量、取消/确认及计划调整的真实事务竞争。"""

    def setUp(self):
        """准备同一康复师的两个客户计划和可扣课时包。"""
        self.therapist = get_user_model().objects.create_user(username="concurrency_owner")
        self.customer = Customer.objects.create(therapist=self.therapist, name="测试客户甲")
        self.other_customer = Customer.objects.create(therapist=self.therapist, name="测试客户乙")
        self.day = date(2030, 1, 7)
        self.package = CoursePackage.objects.create(
            therapist=self.therapist, customer=self.customer,
            name="测试课时", total_sessions=Decimal("10.0"),
        )
        self.plan_course = self._plan_course(self.customer, self.package)
        self.other_plan_course = self._plan_course(self.other_customer)

    def _plan_course(self, customer, package=None):
        """为独立客户创建进行中计划，模拟跨计划预约同一时段。"""
        plan = RehabPlan.objects.create(
            therapist=self.therapist, customer=customer, start_date=self.day,
        )
        course_type = CourseType.objects.create(therapist=self.therapist, name="测试课程")
        return RehabPlanCourse.objects.create(
            rehab_plan=plan, course_type=course_type, planned_count=2,
            session_cost=Decimal("1.0"), duration=60, package=package,
        )

    def _data(self, course, customer):
        """构造相同日期时间的单节排课请求。"""
        return {
            "customer": customer, "plan_course": course, "date": self.day,
            "start_time": time(10), "end_time": time(11),
        }

    def _session(self, session_date=None):
        """创建一节待确认的计划排课。"""
        data = self._data(self.plan_course, self.customer)
        data["date"] = session_date or self.day
        return create_course_session(self.therapist, data)

    def _confirm_record(self, session):
        """复用手动记录的原子写入顺序，失败时记录和扣课一起回滚。"""
        with course_write_transaction(self.therapist):
            record = TrainingRecord.objects.create(
                therapist=self.therapist, customer=self.customer,
                course_session=session, training_date=session.date,
            )
            complete_session_for_record(self.therapist, record)
            return record.pk

    def _race(self, *actions):
        """每个线程使用独立连接，Barrier 同时放行；收集结果并拒绝悬挂线程。"""
        barrier = Barrier(len(actions))
        results = Queue()

        def worker(action):
            """独立连接执行一个请求；任何未预期异常都交还主线程断言。"""
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET statement_timeout = '15000ms'")
                barrier.wait(timeout=10)
                results.put(("ok", action()))
            except Exception as exc:
                results.put(("error", exc))
            finally:
                connection.close()

        threads = [Thread(target=worker, args=(action,), daemon=True) for action in actions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertFalse(any(thread.is_alive() for thread in threads), "课程并发请求发生悬挂")
        self.assertEqual(results.qsize(), len(actions))
        outcomes = [results.get_nowait() for _ in actions]
        for state, result in outcomes:
            if state == "error":
                self.assertIsInstance(result, (ValueError, CourseWriteBusyError), repr(result))
        return outcomes

    def _assert_one_success(self, outcomes):
        """冲突请求只能有一个成功，另一个以可解释的业务错误终止。"""
        self.assertEqual(sum(state == "ok" for state, _ in outcomes), 1, outcomes)

    def test_cross_plan_simultaneous_booking_only_one_succeeds(self):
        """不同计划行锁不能互相保护空时段，康复师锁必须阻止双排课。"""
        outcomes = self._race(
            lambda: create_course_session(self.therapist, self._data(self.plan_course, self.customer)),
            lambda: create_course_session(self.therapist, self._data(self.other_plan_course, self.other_customer)),
        )
        self._assert_one_success(outcomes)
        self.assertEqual(CourseSession.objects.count(), 1)

    def test_single_and_batch_schedule_compete_across_plans(self):
        """单节和批量确认共用同一康复师锁；批量冲突整体失败。"""
        outcomes = self._race(
            lambda: create_course_session(self.therapist, self._data(self.plan_course, self.customer)),
            lambda: confirm_batch_schedule(self.therapist, {
                "plan_course": self.other_plan_course, "start_date": self.day,
                "start_time": time(10), "weekdays": [1],
            }),
        )
        self._assert_one_success(outcomes)
        self.assertEqual(CourseSession.objects.filter(date=self.day).count(), 1)
        self.assertIn(CourseSession.objects.count(), (1, 2))

    def test_simultaneous_booking_does_not_exceed_plan_capacity(self):
        """不同时间同时占用最后一次计划余量，仍只有一条待上课排期。"""
        self.plan_course.planned_count = 1
        self.plan_course.save(update_fields=["planned_count"])
        second = self._data(self.plan_course, self.customer)
        second.update(start_time=time(12), end_time=time(13))
        outcomes = self._race(
            lambda: create_course_session(self.therapist, self._data(self.plan_course, self.customer)),
            lambda: create_course_session(self.therapist, second),
        )
        self._assert_one_success(outcomes)
        self.assertEqual(CourseSession.objects.count(), 1)

    def test_cancel_and_confirm_cannot_leave_consumed_cancelled_course(self):
        """取消先成功则确认全回滚；确认先成功则旧取消请求被拒。"""
        session = self._session()
        outcomes = self._race(
            lambda: update_course_session(self.therapist, session, {"status": CourseSessionStatus.CANCELLED}),
            lambda: self._confirm_record(session),
        )
        self._assert_one_success(outcomes)
        session.refresh_from_db()
        self.package.refresh_from_db()
        if session.status == CourseSessionStatus.COMPLETED:
            self.assertTrue(session.session_consumed)
            self.assertEqual(TrainingRecord.objects.count(), 1)
            self.assertEqual(self.package.used_sessions, Decimal("1.0"))
            self.assertEqual(CourseAdjustment.objects.count(), 1)
        else:
            self.assertEqual(session.status, CourseSessionStatus.CANCELLED)
            self.assertFalse(session.session_consumed)
            self.assertEqual(TrainingRecord.objects.count(), 0)
            self.assertEqual(self.package.used_sessions, Decimal("0.0"))
            self.assertEqual(CourseAdjustment.objects.count(), 0)

    def test_stale_cancel_waiting_on_confirmation_is_rejected(self):
        """用 Barrier 固定确认先持锁，证明锁外旧快照不能覆盖完成结果。"""
        session = self._session()
        barrier = Barrier(2)
        outcome = Queue()

        def cancel():
            """携带已读取的旧排课等待确认事务提交后再尝试取消。"""
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                update_course_session(self.therapist, session, {"status": CourseSessionStatus.CANCELLED})
                outcome.put(None)
            except Exception as exc:
                outcome.put(exc)
            finally:
                connection.close()

        with course_write_transaction(self.therapist):
            thread = Thread(target=cancel, daemon=True)
            thread.start()
            barrier.wait(timeout=10)
            self._confirm_record(session)
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(outcome.get_nowait(), ValueError)
        session.refresh_from_db()
        self.assertEqual(session.status, CourseSessionStatus.COMPLETED)
        self.assertEqual(TrainingRecord.objects.count(), 1)

    def test_count_adjustment_and_confirmation_preserve_latest_completion(self):
        """调整与确认无论先后，都按最新次数和完成数更新课程状态。"""
        session = self._session()
        outcomes = self._race(
            lambda: adjust_plan_course_count(self.therapist, self.plan_course, -1, "减少未安排次数"),
            lambda: self._confirm_record(session),
        )
        self.assertTrue(all(state == "ok" for state, _ in outcomes), outcomes)
        self.plan_course.refresh_from_db()
        self.assertEqual(self.plan_course.planned_count, 1)
        self.assertEqual(self.plan_course.status, PlanCourseStatus.COMPLETED)
        self.assertEqual(TrainingRecord.objects.count(), 1)

    def test_repeated_draft_confirmation_creates_one_record_and_one_deduction(self):
        """重复确认同一 AI 草稿幂等返回，数据库仅有一条正式记录和消费流水。"""
        session = self._session()
        draft = AiDraft.objects.create(
            therapist=self.therapist, customer=self.customer, input_text="测试确认",
        )

        def confirm():
            """两个客户端重试同一请求，不调用模型。"""
            return confirm_training_draft(
                self.therapist, draft.id, {"training_date": self.day.isoformat()},
                self.customer.id, session.id, idempotency_key="same-request",
            ).training_record_id

        outcomes = self._race(confirm, confirm)
        self.assertTrue(all(state == "ok" for state, _ in outcomes), outcomes)
        self.assertEqual(len({result for _, result in outcomes}), 1)
        self.assertEqual(TrainingRecord.objects.count(), 1)
        self.assertEqual(CourseAdjustment.objects.filter(adjustment_type=CourseAdjustmentType.CONSUMPTION).count(), 1)
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, Decimal("1.0"))

    def test_two_confirmations_compete_for_last_package_credit(self):
        """共享最后一课时：仅一个确认成功，另一记录/课程/流水整体回滚。"""
        self.package.total_sessions = Decimal("1.0")
        self.package.save(update_fields=["total_sessions"])
        first = self._session()
        second = self._session(self.day + timedelta(days=1))
        outcomes = self._race(lambda: self._confirm_record(first), lambda: self._confirm_record(second))
        self._assert_one_success(outcomes)
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, Decimal("1.0"))
        self.assertEqual(TrainingRecord.objects.count(), 1)
        self.assertEqual(CourseAdjustment.objects.count(), 1)
        self.assertEqual(CourseSession.objects.filter(status=CourseSessionStatus.COMPLETED, session_consumed=True).count(), 1)
        self.assertEqual(CourseSession.objects.filter(status=CourseSessionStatus.SCHEDULED, session_consumed=False).count(), 1)

    def test_insufficient_credit_leaves_draft_pending(self):
        """余额不足维持现行整体回滚规则，草稿不被标成确认。"""
        self.package.total_sessions = Decimal("0.0")
        self.package.save(update_fields=["total_sessions"])
        session = self._session()
        draft = AiDraft.objects.create(therapist=self.therapist, customer=self.customer, input_text="测试")
        with self.assertRaisesMessage(ValueError, "课时不足"):
            confirm_training_draft(
                self.therapist, draft.id, {"training_date": self.day.isoformat()},
                self.customer.id, session.id,
            )
        draft.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(draft.status, AiDraftStatus.PENDING)
        self.assertEqual(session.status, CourseSessionStatus.SCHEDULED)
        self.assertFalse(session.session_consumed)
        self.assertEqual(TrainingRecord.objects.count(), 0)
        self.assertEqual(CourseAdjustment.objects.count(), 0)

    def test_completed_history_and_consumed_package_cannot_be_changed(self):
        """服务直接调用及旧页面都不能改已完成日期或已扣课时包。"""
        session = self._session()
        self._confirm_record(session)
        for changes in (
            {"date": self.day + timedelta(days=1)}, {"start_time": time(12)},
            {"session_count": Decimal("0.5")}, {"status": CourseSessionStatus.SCHEDULED},
            {"customer": self.other_customer}, {"plan_course": self.other_plan_course},
            {"arrangement_type": "other"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                update_course_session(self.therapist, session, changes)
        with self.assertRaisesMessage(ValueError, "不能更换课时包"):
            update_plan_course(self.therapist, self.plan_course, {"package": None})
        update_course_session(self.therapist, session, {"note": "补充备注"})
        session.refresh_from_db()
        self.assertEqual(session.date, self.day)
        self.assertEqual(session.note, "补充备注")

    def test_lock_timeout_returns_retryable_business_error(self):
        """另一个连接持有康复师事务锁时，请求有界失败并可整体重试。"""
        barrier = Barrier(2)
        outcome = Queue()

        def writer():
            """等待主连接占锁后尝试新增排课。"""
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                create_course_session(self.therapist, self._data(self.plan_course, self.customer))
                outcome.put(None)
            except Exception as exc:
                outcome.put(exc)
            finally:
                connection.close()

        with course_write_transaction(self.therapist):
            thread = Thread(target=writer, daemon=True)
            thread.start()
            barrier.wait(timeout=10)
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertIsInstance(outcome.get_nowait(), CourseWriteBusyError)
        self.assertEqual(CourseSession.objects.count(), 0)
