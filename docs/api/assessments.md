# 评估接口（assessments）

所有接口返回统一信封结构 `{code, message, data}`。数据强制按当前康复师隔离。

## 评估列表

`GET /api/assessments/?customer_id={id}`

权限：已登录康复师

成功响应：

```json
{
  "code": 200,
  "message": "查询评估成功",
  "data": [
    {
      "id": 1,
      "customer": 1,
      "customer_name": "张三",
      "plan": null,
      "assessment_type": "initial",
      "assessment_type_display": "首次评估",
      "assessment_date": "2026-08-01",
      "chief_complaint": "左膝前侧疼痛",
      "medical_history": "",
      "rehab_goal": "恢复下蹲功能",
      "current_status": "",
      "note": "",
      "metrics": [
        { "id": 1, "metric_type": "pain", "metric_type_display": "疼痛", "body_part": "左膝前侧", "score": 6, "score_max": 10, "description": "下蹲至90度时加重", "sort_order": 0 }
      ],
      "created_at": "2026-08-26T10:00:00+08:00",
      "updated_at": "2026-08-26T10:00:00+08:00"
    }
  ]
}
```

错误：`400` 缺少 customer_id；`401` 未登录。

## 创建评估

`POST /api/assessments/`

请求体：

```json
{
  "customer": 1,
  "assessment_type": "initial",
  "assessment_date": "2026-08-01",
  "chief_complaint": "左膝前侧疼痛",
  "rehab_goal": "恢复下蹲功能",
  "metrics": [
    { "metric_type": "pain", "body_part": "左膝前侧", "score": 6, "score_max": 10, "description": "下蹲至90度时加重" },
    { "metric_type": "strength", "body_part": "左膝", "score": 4, "score_max": 5, "description": "股四头肌肌力" }
  ]
}
```

指标 `metric_type`：`pain`（疼痛 NRS 0-10）、`strength`（肌力 0-5 级）、`rom`（活动度）、`special_test`（特殊测试）、`functional`（功能动作）。

错误：`403` 无权为该客户创建。

## 评估详情

`GET /api/assessments/{id}/`

错误：`404` 评估不存在或无权访问。

## 更新评估

`PUT /api/assessments/{id}/`

说明：更新评估及其指标（指标整体替换），并记录审计。
