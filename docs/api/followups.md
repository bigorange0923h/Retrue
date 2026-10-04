# 回访/复查接口（followups）

所有接口返回统一信封结构 `{code, message, data}`。数据强制按当前康复师隔离。

## 回访列表

`GET /api/followups/?customer_id={id}&status={status}`

权限：已登录康复师

查询参数：
- `customer_id`（可选）：按客户筛选。
- `status`（可选）：`pending`/`done`/`skipped`。

成功响应：

```json
{
  "code": 200,
  "message": "查询回访成功",
  "data": [
    {
      "id": 1,
      "customer": 1,
      "customer_name": "张三",
      "followup_type": "visit",
      "followup_type_display": "回访",
      "due_date": "2026-08-27",
      "content": "电话回访膝盖情况",
      "status": "pending",
      "status_display": "待处理",
      "result": "",
      "created_at": "2026-08-26T10:00:00+08:00",
      "updated_at": "2026-08-26T10:00:00+08:00"
    }
  ]
}
```

错误：`401` 未登录。

## 创建回访

`POST /api/followups/`

请求体：

```json
{
  "customer": 1,
  "followup_type": "review",
  "due_date": "2026-08-28",
  "content": "复评膝盖"
}
```

错误：`403` 无权为该客户创建。

## 更新回访

`PUT /api/followups/{id}/`

可更新类型、日期、状态与结果：

```json
{ "status": "done", "result": "电话回访完成" }
```

错误：`404` 回访不存在或无权访问。

### 状态与结果约束

- `done`：`result` 必须填写实际回访结果；空白或“已完成”等占位文案返回 `400`。
- `skipped`：`result` 必须填写跳过原因，不能伪装为完成。
- 已创建回访不能更换客户；同客户值兼容。
- `customer_id` 必须为正整数；非法筛选返回 `400`。
- 回访创建、状态结果修改及审计同步提交，失败全部回滚。

完成时可显式安排同客户的下一项（不自动推测日期）：

```json
{
  "status": "done",
  "result": "测试客户可完成家庭训练，仍需核对一周后的表现",
  "next_task": { "followup_type": "review", "due_date": "2026-10-10", "content": "核对训练表现" }
}
```

`next_task.due_date` 必填。成功 `data` 仍为当前回访对象，并增加 `next_task_id`。
只有当前状态为 `pending` 且本次明确提交 `status=done` 才接受下一项；重复提交不会重复续建，返回 `400`。已处理回访需要新增后续事项时使用创建接口。
