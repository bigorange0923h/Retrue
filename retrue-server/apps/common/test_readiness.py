"""就绪/存活探针边界回归：短超时、只读、无真实模型调用和脱敏。"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.common.readiness import _database_readiness


class ReadinessTests(SimpleTestCase):
    """探针不依赖现有业务连接，不把 mock 或配置检查描述成真实模型通过。"""

    def test_ready_keeps_real_model_unverified(self):
        """所有数据库检查通过也明确返回 live_model_checked=false。"""
        with patch("apps.common.readiness._database_readiness", return_value={
            "database": "ok", "migrations": "ok", "cache": "ok", "vector": "ok",
        }), patch("apps.ai.providers.factory.get_provider") as factory:
            response = self.client.get(reverse("readiness-check"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["live_model_checked"])
        self.assertEqual(response.json()["data"]["checks"]["model_runtime"], "not_checked")
        factory.return_value.chat.assert_not_called()
        factory.return_value.parse_training_text.assert_not_called()
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_database_down_returns_503_but_liveness_stays_200(self):
        """依赖故障不能把 liveness 当业务可用，也不暴露异常里的密码。"""
        with patch("apps.common.readiness._expected_migrations", return_value=set()), \
             patch("apps.common.readiness.psycopg.connect", side_effect=RuntimeError("private-db-password")), \
             patch("apps.ai.providers.factory.get_provider"):
            response = self.client.get(reverse("readiness-check"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-db-password", response.content.decode())
        self.assertEqual(self.client.get(reverse("health-check")).status_code, 200)

    def test_invalid_model_configuration_is_distinct_from_runtime_unknown(self):
        """缺密钥/配置错误返回 invalid，不能声称已测出模型远端不可用。"""
        with patch("apps.common.readiness._database_readiness", return_value={
            "database": "ok", "migrations": "ok", "cache": "ok", "vector": "ok",
        }), patch("apps.ai.providers.factory.get_provider", side_effect=ValueError("private-key")):
            response = self.client.get(reverse("readiness-check"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["data"]["checks"]["model_configuration"], "invalid")
        self.assertEqual(response.json()["data"]["checks"]["model_runtime"], "not_checked")
        self.assertNotIn("private-key", response.content.decode())

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "retrue_cache"}})
    def test_database_probe_uses_independent_read_only_bounded_connection(self):
        """连接最多两秒，单条查询/锁等待一秒，迁移缺失明确为 pending。"""
        connect = MagicMock()
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [("accounts", "0001_initial")]
        cursor.fetchone.return_value = [True]
        with patch("apps.common.readiness.psycopg.connect", connect), patch(
            "apps.common.readiness._expected_migrations",
            return_value={("accounts", "0001_initial"), ("accounts", "0002_more")},
        ):
            checks = _database_readiness()
        self.assertEqual(checks, {"database": "ok", "migrations": "pending", "cache": "ok", "vector": "ok"})
        kwargs = connect.call_args.kwargs
        self.assertEqual(kwargs["connect_timeout"], 2)
        self.assertTrue(kwargs["autocommit"])
        self.assertIn("statement_timeout=1000", kwargs["options"])
        self.assertIn("default_transaction_read_only=on", kwargs["options"])

    def test_post_is_rejected(self):
        """健康探针只提供读取入口。"""
        self.assertEqual(self.client.post(reverse("readiness-check")).status_code, 405)
