-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_course_types（课程模板）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 CourseType 模型（apps/schedules/models.py）生成。
-- 课程模板是康复师维护、可复用的课程定义，而非某个客户的周期安排或某次上课记录。
-- ============================================================

CREATE TABLE tb_course_types (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(255) NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    default_duration INT NULL,
    default_session_cost NUMERIC(4,1) NOT NULL DEFAULT 1.0,
    default_goals TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_coursetype_therapist ON tb_course_types (therapist_id, is_active);

COMMENT ON TABLE tb_course_types IS '课程模板表，康复师维护的可复用课程定义';
COMMENT ON COLUMN tb_course_types.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN tb_course_types.name IS '课程类型名称，如膝关节术后力量重建';
COMMENT ON COLUMN tb_course_types.is_active IS '启用状态；被计划内课程引用的模板只能停用不能删除';
COMMENT ON COLUMN tb_course_types.default_duration IS '默认时长（分钟）';
COMMENT ON COLUMN tb_course_types.default_session_cost IS '默认单节课时消耗：半课 0.5 / 全课 1.0';
COMMENT ON COLUMN tb_course_types.default_goals IS '默认课程目标';
