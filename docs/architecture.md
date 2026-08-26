# Retrue 系统架构

## V1 边界

V1 采用单体架构，优先跑通「今日客户 → 训练记录 → AI 草稿确认 → 正式保存 → 客户时间线 → 下次备课」闭环。

```text
Vue 3 Web
    │ REST API
    ▼
Django + DRF
    ├── 业务 Apps
    ├── AI Service（仅生成草稿）
    └── Django Admin
    │
    ▼
PostgreSQL
```

## 业务模块边界

| 模块 | 职责 |
| --- | --- |
| accounts / therapists | 登录、账号与康复师身份 |
| customers | 客户档案、隐私字段脱敏与数据隔离 |
| schedules / courses | 课表、课程与课时流水 |
| assessments / rehab | 首次评估、复评、康复计划与阶段 |
| training / exercises | 训练记录、动作库、家庭训练 |
| followups | 回访、复查与轻量待办 |
| ai | AI 草稿解析、备课建议、风险提示 |
| audit | 正式记录变更的审计追踪 |

## AI 数据流

```text
原始输入 → AI 结构化草稿 → 康复师编辑/确认 → 正式业务记录 → 审计日志
```

- AI 草稿与正式记录必须分表或通过明确状态字段隔离。
- AI 不得直接更新训练记录、评估、阶段、课时或风险处理结果。
- 客户识别不确定时必须返回候选项，禁止自动猜测并保存。

## 本地环境

- PostgreSQL 由 `compose.yaml` 提供，宿主机端口为 `5433`。
- 本地运行 Django 使用 `127.0.0.1:5433`；Compose 内运行 Django 使用服务名 `postgres:5432`。
- 环境变量只写入 `.env`，示例变量维护在 `.env.example`。
