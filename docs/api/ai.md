# AI 草稿接口（ai）

所有接口返回统一信封结构 `{code, message, data}`。AI 只生成待确认草稿，**确认后才创建正式训练记录**。

## 解析训练文本生成草稿

`POST /api/ai/parse/`

权限：已登录康复师

请求体：

```json
{
  "input_text": "今天做了臀桥 3 组 12 次，靠墙静蹲 3 组 30 秒。左膝下蹲还有一点疼，大概 2 分。下次可以开始加单腿稳定训练。",
  "customer_id": 1,
  "assistant_task_id": 12,
  "course_session_id": 10,
  "client_request_id": "training-parse-20260901-001"
}
```

`assistant_task_id` 可选。提供后，服务端只接受当前康复师名下且
`task_type=training_record` 的统一任务，并复核任务中的客户与课程上下文；
任务状态会依次更新为 `running`、`waiting_confirmation`，解析失败则为
`failed`（任务保留，可重试）。`course_session_id` 仅在从排课入口补记时传入，
且必须与任务上下文一致。

同一任务内相同 `client_request_id` 的网络重试会返回第一次生成的草稿，不会再次调用模型或生成第二份草稿。任务仍在整理时，页面应查询任务状态后继续等待，而不是重复提交。

成功响应：

```json
{
  "code": 200,
  "message": "草稿生成成功",
  "data": {
    "id": 1,
    "status": "pending",
    "status_display": "待确认",
    "customer": 1,
    "customer_name": "张三",
    "assistant_task": 12,
    "training_record": null,
    "input_text": "...",
    "ai_result": {
      "training_date": "2026-08-26",
      "exercises": [
        { "exercise_name": "臀桥", "sets": 3, "reps": 12, "weight": "", "duration_seconds": null, "note": "" },
        { "exercise_name": "靠墙静蹲", "sets": 3, "reps": null, "weight": "", "duration_seconds": 30, "note": "" }
      ],
      "customer_feedback": "左膝下蹲疼痛 2 分",
      "therapist_observation": "",
      "next_plan": "开始加单腿稳定训练"
    },
    "confirmed_result": {},
    "error_message": "",
    "created_at": "2026-08-26T10:00:00+08:00"
  }
}
```

解析失败时 `status` 为 `failed`，`error_message` 给出原因。

错误：`400` 参数错误；`401` 未登录。

## 确认草稿（创建正式记录）

`POST /api/ai/confirm/{draft_id}/`

权限：已登录康复师（仅限本人草稿）

按草稿 `draft_type` 分派到对应确认服务：

- `training_record`（训练补记，默认）：创建正式训练记录。
- `assessment`（评估）：创建正式评估记录（`status=draft`，由评估工作台继续完成）。
- `training_revision`（训练记录修订）：更新目标训练记录的修订字段。
- `followup`（随访）：创建正式随访待办。

请求体（`confirmed` 为人工编辑后的最终结果，`customer_id` 为确认客户；从排课进入时可传 `course_session_id`；重复提交应复用同一个 `idempotency_key`）：

```json
{
  "customer_id": 1,
  "course_session_id": 10,
  "idempotency_key": "confirm-20260826-001",
  "confirmed": {
    "training_date": "2026-08-26",
    "customer_feedback": "左膝下蹲疼痛 NRS 2",
    "therapist_observation": "稳定性改善",
    "next_plan": "增加单腿稳定训练",
    "exercises": [
      { "exercise_name": "臀桥", "activity_type": "exercise", "sets": 3, "reps": 12, "quantity": null, "unit": "" },
      { "exercise_name": "康复按摩", "activity_type": "massage", "sets": null, "reps": null, "quantity": 1, "unit": "次" }
    ]
  }
}
```

`exercises` 中每项支持 `activity_type`（exercise=训练动作 / therapy=康复治疗 / massage=按摩）、`quantity` 与 `unit`，用于表达"康复按摩 1 次"这类无法用组数/次数描述的项目；按摩/治疗的数量必须用 `quantity+unit`，不要用 `sets/reps` 替代。这些字段会无损写入正式训练记录并可在 GET 与时间线中读回。

成功响应：草稿状态变为 `confirmed`，并创建正式训练记录；响应中的 `training_record` 为正式记录 ID。传入 `course_session_id` 时，会在同一事务内完成排课、扣减关联课时并判断计划内课程是否达到计划次数。服务端会在事务中锁定草稿并重新校验客户、课程资源；相同 `idempotency_key` 的重复确认直接返回同一正式记录，不会重复创建或扣课时。即使页面刷新丢失了首次幂等键，已确认草稿在客户和课程一致时也会安全返回原结果。确认内容会校验日期、动作名称、项目类型枚举、组数/次数/数量/时长和文本长度；若草稿关联统一任务，成功后任务变为 `completed`，并写入 `result_resource_type=training_record` 与 `result_resource_id`。

错误：`400` 草稿不存在/无权访问/状态不允许确认/客户无效、确认结构不合法、任务或课程上下文不匹配或课时不足；`401` 未登录。

## 取消草稿

`POST /api/ai/cancel/{draft_id}/`

权限：已登录康复师（仅限本人草稿）

说明：取消后不创建任何正式记录；若草稿关联统一任务，任务同步变为 `cancelled`。解析失败的草稿也可以取消，任务仍保留可追踪的取消事件。

错误：`400` 草稿不存在或已确认；`401` 未登录。

## 待确认草稿列表

`GET /api/ai/drafts/`

权限：已登录康复师

成功响应：返回当前康复师所有 `pending` 状态的草稿。

## 客户候选查询

`GET /api/ai/customer-candidates/?name={姓名提示}`

权限：已登录康复师

说明：按姓名提示返回客户候选（含脱敏手机号），用于草稿客户识别不确定时选择。

```json
{
  "code": 200,
  "message": "查询客户候选成功",
  "data": [
    { "id": 1, "name": "张三", "phone_masked": "138****8000" }
  ]
}
```

## 备课助手

`GET /api/ai/prepare-lesson/?customer_id={id}`

权限：已登录康复师

说明：系统自动汇总客户历史（上次训练、当前疼痛、康复阶段、下次计划），AI 生成备课建议。

成功响应：

```json
{
  "code": 200,
  "message": "备课建议生成成功",
  "data": {
    "customer_summary": {
      "last_record_date": "2026-08-26",
      "last_exercises": ["臀桥", "靠墙静蹲"],
      "customer_feedback": "左膝疼痛 NRS 6",
      "therapist_observation": "稳定性改善",
      "next_plan": "增加单腿稳定训练",
      "current_stage": "力量重建期",
      "note": ""
    },
    "ai_suggestions": {
      "suggested_checks": ["重点检查疼痛部位，评估当前疼痛等级变化", "逐步增加力量训练强度"],
      "recommended_tests": [],
      "recommended_parts": [],
      "training_approach": "重点检查疼痛部位，评估当前疼痛等级变化",
      "risk_reminders": ["⚠️ 当前疼痛 NRS 6 较高，建议谨慎增加负荷"]
    }
  }
}
```

说明：`customer_summary` 为系统真实数据汇总，`ai_suggestions` 由 AI provider 生成（当前为 mock 规则）。

错误：`400` 缺少 customer_id；`401` 未登录。

## 风险提醒列表

`GET /api/ai/risks/?customer_id={id}`

权限：已登录康复师

成功响应：

```json
{
  "code": 200,
  "message": "查询风险提醒成功",
  "data": [
    {
      "id": 1,
      "customer": 1,
      "customer_name": "张三",
      "training_record": null,
      "risk_level": "high",
      "risk_level_display": "高",
      "rule_code": "nrs_high_v1",
      "evidence": "最近 2 条含评分记录 NRS（新→旧）为 [6, 7]，最高 7，最近一次 6 仍不低于 6，是否构成持续未改善/需调整请结合临床人工判断",
      "suggested_action": "pause",
      "suggested_action_display": "暂停",
      "is_confirmed": false,
      "outcome": "",
      "created_at": "2026-08-27T10:00:00+08:00"
    }
  ]
}
```

错误：`401` 未登录。

## 风险检测

`POST /api/ai/risks/detect/`

请求体：`{ "customer_id": 1, "training_record_id": null }`

说明：从客户最近训练记录检测风险。规则 `nrs_high_v1`：最近 3 条记录中至少 2 条含合法 NRS（0-10）且最高值 ≥6 时创建提醒；最近一次已低于 6（较历史高位下降）时降为 `medium` + `review`，不再输出“连续未明显改善”等无证据结论，是否构成持续未改善由康复师结合临床判断。同客户同规则存在未确认提醒时不重复创建，而是更新该提醒。未触发风险时 `data` 为 `null`。

错误：`400` 缺少 customer_id。

## 更新风险提醒

`PUT /api/ai/risks/{id}/`

请求体：

```json
{ "is_confirmed": true, "outcome": "已安排复查" }
```

错误：`404` 风险提醒不存在或无权访问。

## 阶段进展参考

`GET /api/ai/progress/?customer_id={id}`

权限：已登录康复师

说明：AI 从客户历史记录中提取疼痛、活动度等变化趋势，生成阶段进展参考。**AI 不自动修改康复阶段**，仅供参考供康复师判断。

成功响应：

```json
{
  "code": 200,
  "message": "阶段进展分析成功",
  "data": {
    "pain_trend": "改善",
    "observations": [
      "疼痛由 NRS 6 降至 NRS 2，明显改善",
      "活动度评分由 80 提升至 95，活动度改善"
    ],
    "summary": "疼痛由 NRS 6 降至 NRS 2，明显改善；活动度评分由 80 提升至 95，活动度改善",
    "recommendation": "系统判断：当前存在进入下一阶段的迹象。（康复师可手动调整阶段，AI 不会自动修改）"
  }
}
```

错误：`400` 缺少 customer_id；`401` 未登录。

## 专业问答

`POST /api/ai/qa/`

权限：已登录康复师

请求体：`{ "question": "臀桥怎么做" }`

说明：基于内部知识库（动作库）回答康复专业问题，不替代医学诊断。

成功响应：

```json
{
  "code": 200,
  "message": "回答成功",
  "data": {
    "question": "臀桥怎么做",
    "answer": "关于「臀桥」：该动作用于康复训练。训练部位：髋。",
    "sources": [
      { "name": "臀桥", "body_part": "髋", "description": "", "precautions": "" }
    ]
  }
}
```

错误：`400` 缺少问题内容；`401` 未登录。
