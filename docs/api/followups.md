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
