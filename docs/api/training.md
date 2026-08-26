# 训练记录接口（training）

所有接口返回统一信封结构 `{code, message, data}`。训练记录强制按当前康复师隔离。

## 训练记录列表

`GET /api/training/?customer_id={id}`

权限：已登录康复师

查询参数：
- `customer_id`（必填）：客户 ID。
- `page`（可选）：页码，默认 1。
- `page_size`（可选）：每页条数，默认 20，最大 100。

成功响应：

```json
{
  "code": 200,
  "message": "查询成功",
  "data": {
    "items": [
      {
        "id": 1,
        "customer": 1,
        "customer_name": "张三",
        "course_session": null,
        "training_date": "2026-08-26",
        "customer_feedback": "左膝下蹲疼痛 NRS 2",
        "therapist_observation": "稳定性较上次改善",
        "next_plan": "增加单腿稳定训练",
        "note": "",
        "exercises": [
          { "id": 1, "exercise_name": "臀桥", "sets": 3, "reps": 12, "weight": "", "duration_seconds": null, "note": "", "sort_order": 0 }
        ],
        "created_at": "2026-08-26T10:00:00+08:00",
        "updated_at": "2026-08-26T10:00:00+08:00"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
}
```

错误：`400` 缺少 customer_id；`401` 未登录。

## 创建训练记录

`POST /api/training/`

权限：已登录康复师

请求体：

```json
{
  "customer": 1,
  "training_date": "2026-08-26",
  "customer_feedback": "左膝下蹲疼痛 NRS 2",
  "therapist_observation": "稳定性改善",
  "next_plan": "增加单腿稳定训练",
  "exercises": [
    { "exercise_name": "臀桥", "sets": 3, "reps": 12 },
    { "exercise_name": "靠墙静蹲", "duration_seconds": 30 }
  ]
}
```

成功响应：返回创建的训练记录。

错误：`400` 参数错误；`401` 未登录；`403` 无权为该客户创建。

## 训练记录详情

`GET /api/training/{id}/`

权限：已登录康复师（仅限本人记录）

错误：`401` 未登录；`404` 记录不存在或无权访问。

## 人工修订训练记录

`PUT /api/training/{id}/`

权限：已登录康复师（仅限本人记录）

**修订正式记录必须提供 `reason`（修改原因）**，系统保存前后快照、操作人与时间到审计日志。

请求体：

```json
{
  "reason": "修正客户感受描述",
  "customer_feedback": "左膝下蹲疼痛 NRS 1（修正）",
  "exercises": [ { "exercise_name": "臀桥", "sets": 3, "reps": 12 } ]
}
```

成功响应：返回修订后的训练记录。

错误：`400` 缺少修改原因或参数错误；`401` 未登录；`404` 记录不存在或无权访问。

## 客户时间线

`GET /api/training/timeline/?customer_id={id}`

权限：已登录康复师

说明：返回某客户按训练日期倒序的训练记录（含动作），用于时间线展示。

```json
{
  "code": 200,
  "message": "查询时间线成功",
  "data": []
}
```

错误：`400` 缺少 customer_id；`401` 未登录。
