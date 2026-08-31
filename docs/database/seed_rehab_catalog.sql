-- ============================================================
-- Retrue 康复课程目录与课程计划模板 —— 初始化种子数据
-- 作用：为指定康复师初始化一批课程类型（tb_course_types）与
--       可复用的课程计划模板（tb_rehab_plan_templates /
--       tb_rehab_plan_template_courses）。
-- 说明：本文件是康复课程目录与计划模板初始化的唯一来源，幂等可重复执行；
--       需要初始化数据时直接执行本 SQL 即可。表结构参考见同目录：
--       course_types.sql / rehab_plan_templates.sql。
-- 使用：
--   * 默认初始化给用户名为 bigorange 的康复师。
--   * 如需为其他康复师初始化，请全文替换下面所有 username = 'bigorange'
--     为该康复师的用户名后执行。
-- ============================================================

BEGIN;

-- ------------------------------------------------------------------
-- 1. 课程类型目录（幂等：同康复师+同名课程不存在时才插入）
-- ------------------------------------------------------------------
INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '运动疗法', '以主动运动训练为核心的系统性训练方法', TRUE, 60,
       1.0, '通过主动运动恢复关节活动度与运动控制', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '运动疗法');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '关节松动术', '通过分级被动活动改善关节活动度', TRUE, 30,
       1.0, '改善关节活动度并缓解疼痛', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '关节松动术');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '手法治疗', '软组织松解与筋膜手法治疗', TRUE, 30,
       1.0, '松解软组织粘连、缓解肌肉紧张', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '手法治疗');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '物理因子治疗', '运用超声、电疗、激光等物理手段消炎镇痛', TRUE, 20,
       0.5, '消炎镇痛、促进组织修复', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '物理因子治疗');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '肌力训练', '抗阻训练增强目标肌群力量', TRUE, 45,
       1.0, '增强目标肌群肌力与耐力', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '肌力训练');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '平衡与本体感觉训练', '利用不稳定界面与闭眼等情境训练平衡', TRUE, 30,
       0.5, '改善静态与动态平衡能力', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '平衡与本体感觉训练');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '核心稳定训练', '强化躯干深层稳定肌群', TRUE, 45,
       1.0, '提升躯干核心稳定性', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '核心稳定训练');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '步态训练', '针对异常步态进行分解与重建训练', TRUE, 30,
       1.0, '重建协调、稳定的步态', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '步态训练');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '神经肌肉促进技术', '基于神经生理学原理的易化技术', TRUE, 30,
       1.0, '促进神经肌肉控制与协调', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '神经肌肉促进技术');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '牵伸与柔韧训练', '静态与动态牵伸改善柔韧性', TRUE, 20,
       0.5, '改善柔韧性、缓解肌肉紧张', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '牵伸与柔韧训练');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '心肺耐力训练', '有氧训练提升心肺功能', TRUE, 45,
       1.0, '提升心肺耐力与整体体能', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '心肺耐力训练');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '呼吸训练', '腹式与胸式呼吸再训练', TRUE, 20,
       0.5, '改善呼吸模式与膈肌功能', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '呼吸训练');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '水疗康复', '利用水的浮力与阻力进行康复训练', TRUE, 45,
       1.0, '低负重下进行运动训练', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '水疗康复');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '冲击波治疗', '高能量声波刺激组织修复', TRUE, 20,
       0.5, '缓解慢性肌腱炎、促进修复', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '冲击波治疗');

INSERT INTO tb_course_types
    (therapist_id, name, description, is_active, default_duration,
     default_session_cost, default_goals, created_at, updated_at)
SELECT u.id, '牵引治疗', '脊柱或关节牵引减轻压迫', TRUE, 20,
       0.5, '减轻椎间盘压力、缓解神经压迫', now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_course_types c
                  WHERE c.therapist_id = u.id AND c.name = '牵引治疗');

-- ------------------------------------------------------------------
-- 2. 课程计划模板（幂等：同康复师+同名模板不存在时才插入）
-- ------------------------------------------------------------------
INSERT INTO tb_rehab_plan_templates
    (therapist_id, name, description, suggested_duration_weeks, goals,
     is_active, created_at, updated_at)
SELECT u.id, '膝关节置换术后康复', '适用于全膝关节置换术后的系统康复', 8,
       '恢复膝关节活动度与肌力，重建步行功能，实现无痛上下楼与日常生活自理',
       TRUE, now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_templates t
                  WHERE t.therapist_id = u.id AND t.name = '膝关节置换术后康复');

INSERT INTO tb_rehab_plan_templates
    (therapist_id, name, description, suggested_duration_weeks, goals,
     is_active, created_at, updated_at)
SELECT u.id, '肩袖损伤术后康复', '适用于肩袖修补术后的渐进式康复', 12,
       '恢复肩关节活动度与三角肌肌力，重建肩胛骨稳定性，恢复过顶活动能力',
       TRUE, now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_templates t
                  WHERE t.therapist_id = u.id AND t.name = '肩袖损伤术后康复');

INSERT INTO tb_rehab_plan_templates
    (therapist_id, name, description, suggested_duration_weeks, goals,
     is_active, created_at, updated_at)
SELECT u.id, '腰椎间盘突出症保守康复', '适用于腰椎间盘突出症的保守治疗期康复', 8,
       '缓解腰痛与下肢放射痛，强化核心与腰背肌群，改善姿势管理能力',
       TRUE, now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_templates t
                  WHERE t.therapist_id = u.id AND t.name = '腰椎间盘突出症保守康复');

INSERT INTO tb_rehab_plan_templates
    (therapist_id, name, description, suggested_duration_weeks, goals,
     is_active, created_at, updated_at)
SELECT u.id, '踝关节扭伤康复', '适用于踝关节外侧韧带扭伤的康复', 4,
       '消除肿胀疼痛，恢复踝关节活动度与肌力，重建本体感觉与预防再损伤',
       TRUE, now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_templates t
                  WHERE t.therapist_id = u.id AND t.name = '踝关节扭伤康复');

INSERT INTO tb_rehab_plan_templates
    (therapist_id, name, description, suggested_duration_weeks, goals,
     is_active, created_at, updated_at)
SELECT u.id, '前交叉韧带重建术后康复', '适用于前交叉韧带重建术后的长期康复', 24,
       '分阶段恢复膝关节活动度、肌力与运动控制，安全回归跳跃与变向运动',
       TRUE, now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_templates t
                  WHERE t.therapist_id = u.id AND t.name = '前交叉韧带重建术后康复');

INSERT INTO tb_rehab_plan_templates
    (therapist_id, name, description, suggested_duration_weeks, goals,
     is_active, created_at, updated_at)
SELECT u.id, '髋关节置换术后康复', '适用于全髋关节置换术后的康复', 8,
       '恢复髋关节活动度与肌力，重建安全步行模式，实现术后日常生活自理',
       TRUE, now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_templates t
                  WHERE t.therapist_id = u.id AND t.name = '髋关节置换术后康复');

INSERT INTO tb_rehab_plan_templates
    (therapist_id, name, description, suggested_duration_weeks, goals,
     is_active, created_at, updated_at)
SELECT u.id, '脑卒中早期康复', '适用于脑卒中急性期后稳定期的早期康复', 8,
       '改善偏瘫侧运动功能与姿势控制，重建转移与步行能力，预防继发并发症',
       TRUE, now(), now()
FROM tb_users u
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_templates t
                  WHERE t.therapist_id = u.id AND t.name = '脑卒中早期康复');

-- ------------------------------------------------------------------
-- 3. 模板课程（幂等：同模板+同课程类型不存在时才插入）
--    通过 康复师用户名 -> 模板名 -> 课程名 关联，避免依赖自增 id。
--    排序 sort_order 统一为 0（模板内顺序由 id 决定，与命令初始化保持一致）。
-- ------------------------------------------------------------------

-- 膝关节置换术后康复
INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 16, 1.0, 60, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '膝关节置换术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '运动疗法'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 8, 1.0, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '膝关节置换术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '关节松动术'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 12, 1.0, 45, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '膝关节置换术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '肌力训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 8, 1.0, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '膝关节置换术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '步态训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 6, 0.5, 20, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '膝关节置换术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '物理因子治疗'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

-- 肩袖损伤术后康复
INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 16, 1.0, 60, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '肩袖损伤术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '运动疗法'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 8, 1.0, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '肩袖损伤术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '关节松动术'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 8, 1.0, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '肩袖损伤术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '神经肌肉促进技术'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 10, 1.0, 45, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '肩袖损伤术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '肌力训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

-- 腰椎间盘突出症保守康复
INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 8, 0.5, 20, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '腰椎间盘突出症保守康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '物理因子治疗'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 10, 1.0, 45, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '腰椎间盘突出症保守康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '核心稳定训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 6, 0.5, 20, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '腰椎间盘突出症保守康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '牵伸与柔韧训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 6, 1.0, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '腰椎间盘突出症保守康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '手法治疗'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 4, 0.5, 20, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '腰椎间盘突出症保守康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '呼吸训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

-- 踝关节扭伤康复
INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 4, 0.5, 20, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '踝关节扭伤康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '物理因子治疗'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 3, 1.0, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '踝关节扭伤康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '关节松动术'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 6, 0.5, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '踝关节扭伤康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '平衡与本体感觉训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 4, 1.0, 45, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '踝关节扭伤康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '肌力训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

-- 前交叉韧带重建术后康复
INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 24, 1.0, 60, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '前交叉韧带重建术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '运动疗法'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 20, 1.0, 45, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '前交叉韧带重建术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '肌力训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 12, 0.5, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '前交叉韧带重建术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '平衡与本体感觉训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 8, 1.0, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '前交叉韧带重建术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '步态训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

-- 髋关节置换术后康复
INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 16, 1.0, 60, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '髋关节置换术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '运动疗法'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 12, 1.0, 45, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '髋关节置换术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '肌力训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 8, 1.0, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '髋关节置换术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '步态训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 4, 0.5, 20, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '髋关节置换术后康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '物理因子治疗'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

-- 脑卒中早期康复
INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 16, 1.0, 60, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '脑卒中早期康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '运动疗法'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 12, 1.0, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '脑卒中早期康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '神经肌肉促进技术'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 8, 0.5, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '脑卒中早期康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '平衡与本体感觉训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 8, 1.0, 30, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '脑卒中早期康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '步态训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

INSERT INTO tb_rehab_plan_template_courses
    (template_id, course_type_id, planned_count, session_cost, duration,
     goals, sort_order, created_at, updated_at)
SELECT t.id, ct.id, 4, 0.5, 20, '', 0, now(), now()
FROM tb_users u
JOIN tb_rehab_plan_templates t ON t.therapist_id = u.id AND t.name = '脑卒中早期康复'
JOIN tb_course_types ct ON ct.therapist_id = u.id AND ct.name = '呼吸训练'
WHERE u.username = 'bigorange'
  AND NOT EXISTS (SELECT 1 FROM tb_rehab_plan_template_courses tc
                  WHERE tc.template_id = t.id AND tc.course_type_id = ct.id);

COMMIT;
