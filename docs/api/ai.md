# AI 草稿接口（ai）

所有接口返回统一信封结构 `{code, message, data}`。AI 只生成待确认草稿，**确认后才创建正式训练记录**。

## 解析训练文本生成草稿

`POST /api/ai/parse/`

权限：已登录康复师

请求体：

```json
{
  "input_text": "今天做了臀桥 3 组 12 次，靠墙静蹲 3 组 30 秒。左膝下蹲还有一点疼，大概 2 分。下次可以开始加单腿稳定训练。",
  "customer_id": 1
}
```

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

## 确认草稿（创建正式训练记录）

`POST /api/ai/confirm/{draft_id}/`

权限：已登录康复师（仅限本人草稿）

请求体（`confirmed` 为人工编辑后的最终结果，`customer_id` 为确认客户）：

```json
{
  "customer_id": 1,
  "confirmed": {
    "training_date": "2026-08-26",
    "customer_feedback": "左膝下蹲疼痛 NRS 2",
    "therapist_observation": "稳定性改善",
    "next_plan": "增加单腿稳定训练",
    "exercises": [
      { "exercise_name": "臀桥", "sets": 3, "reps": 12 }
    ]
  }
}
```

成功响应：草稿状态变为 `confirmed`，并创建正式训练记录。

错误：`400` 草稿不存在/无权访问/状态不允许确认/客户无效；`401` 未登录。

## 取消草稿

`POST /api/ai/cancel/{draft_id}/`

权限：已登录康复师（仅限本人草稿）

说明：取消后不创建任何正式记录。

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
