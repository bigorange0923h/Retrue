"""在 PostgreSQL 临时表中验证目录初始化，绝不写入真实业务表。"""

import re
from pathlib import Path
from unittest import skipUnless

from django.db import DatabaseError, connection, transaction
from django.test import TestCase


@skipUnless(connection.vendor == "postgresql", "种子 SQL 验收必须使用 PostgreSQL")
class CatalogSeedTests(TestCase):
    """执行同一份 SQL，验证不存在账号、幂等、歧义回滚及跨账号隔离。"""

    def setUp(self):
        """临时表遮蔽四张真实表；事务回滚后自动清理。"""
        self.docs = Path(__file__).resolve().parents[3] / "docs" / "database"
        self.sql = (self.docs / "seed_rehab_catalog.sql").read_text(encoding="utf-8")
        self.sql = re.sub(r"(?m)^BEGIN;\s*$|^COMMIT;\s*$", "", self.sql)
        with connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TABLE tb_users (id bigint PRIMARY KEY, username text UNIQUE)")
            for name in ("tb_course_types", "tb_rehab_plan_templates", "tb_rehab_plan_template_courses"):
                cursor.execute(f"CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING CONSTRAINTS)")
                # LIKE 的旧序列默认值可能引用 public；为临时表分配独立序列。
                cursor.execute(f"CREATE TEMP SEQUENCE seed_{name}_ids")
                cursor.execute(f"ALTER TABLE {name} ALTER COLUMN id SET DEFAULT nextval('seed_{name}_ids')")
            cursor.execute("ALTER TABLE tb_rehab_plan_template_courses ADD UNIQUE (template_id, course_type_id)")
            cursor.execute("INSERT INTO tb_users VALUES (101, 'bigorange'), (202, 'seed_other')")

    def run_seed(self):
        """完整运行写入主体，使用独立保存点验证 SQL 异常整体回滚。"""
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(self.sql)

    def counts(self):
        """返回三类目录行数，便于断言没有部分初始化。"""
        with connection.cursor() as cursor:
            return tuple(self._count(cursor, name) for name in (
                "tb_course_types", "tb_rehab_plan_templates", "tb_rehab_plan_template_courses",
            ))

    @staticmethod
    def _count(cursor, name):
        """只接受测试固定的表名。"""
        cursor.execute(f"SELECT count(*) FROM {name}")
        return cursor.fetchone()[0]

    def test_clean_and_repeated_execution(self):
        """空目录初始化以及再次执行均保持 15/7/31。"""
        self.run_seed()
        self.assertEqual(self.counts(), (15, 7, 31))
        self.run_seed()
        self.assertEqual(self.counts(), (15, 7, 31))

    def test_missing_account_fails_without_writes(self):
        """目标用户名不存在时明确报错，不以零写入冒充成功。"""
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM tb_users WHERE id = 101")
        with self.assertRaisesMessage(DatabaseError, "目标康复师账号不存在"):
            self.run_seed()
        self.assertEqual(self.counts(), (0, 0, 0))

    def insert_duplicate(self, table, owner):
        """构造目标或其他康复师的重名数据，保留原有记录。"""
        with connection.cursor() as cursor:
            if table == "tb_course_types":
                extra_columns, extra_values = ",default_session_cost,default_goals", ",1.0,''"
            else:
                extra_columns, extra_values = ",goals", ",''"
            for _ in range(2):
                cursor.execute(
                    f"INSERT INTO {table} (therapist_id,name,description,is_active,created_at,updated_at{extra_columns}) "
                    f"VALUES (%s,'模拟重名目录','',true,now(),now(){extra_values})",
                    [owner],
                )

    def test_duplicate_course_rolls_back(self):
        """重名课程拒绝初始化，原数据保持不变。"""
        self.insert_duplicate("tb_course_types", 101)
        with self.assertRaisesMessage(DatabaseError, "存在同名课程"):
            self.run_seed()
        self.assertEqual(self.counts(), (2, 0, 0))

    def test_duplicate_template_rolls_back(self):
        """重名模板拒绝初始化，不留下部分课程。"""
        self.insert_duplicate("tb_rehab_plan_templates", 101)
        with self.assertRaisesMessage(DatabaseError, "存在同名计划模板"):
            self.run_seed()
        self.assertEqual(self.counts(), (0, 2, 0))

    def test_other_owner_duplicates_do_not_receive_links(self):
        """其他账号的重名不阻止当前账号，也不扩散关联。"""
        self.insert_duplicate("tb_course_types", 202)
        self.insert_duplicate("tb_rehab_plan_templates", 202)
        self.run_seed()
        self.assertEqual(self.counts(), (17, 9, 31))
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM tb_rehab_plan_template_courses l "
                "JOIN tb_rehab_plan_templates t ON t.id=l.template_id "
                "JOIN tb_course_types c ON c.id=l.course_type_id "
                "WHERE t.therapist_id <> 101 OR c.therapist_id <> 101"
            )
            self.assertEqual(cursor.fetchone()[0], 0)
