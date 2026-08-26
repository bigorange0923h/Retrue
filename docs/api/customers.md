# 客户接口（customers）

所有接口返回统一信封结构 `{code, message, data}`。客户数据强制按当前康复师隔离。

## 客户列表

`GET /api/customers/`

权限：已登录康复师

查询参数：
- `keyword`（可选）：按姓名模糊搜索。
- `status`（可选）：`active`/`paused`/`closed`。
- `page`（可选）：页码，默认 1。
- `page_size`（可选）：每页条数，默认 20，最大 100。

成功响应（**手机号已脱敏，返回 `phone_masked`**）：

```json
{
  "code": 200,
  "message": "查询成功",
  "data": {
    "items": [
      {
        "id": 1,
        "name": "张三",
        "phone_masked": "138****1234",
        "gender": "male",
        "gender_display": "男",
        "main_issue": "左膝疼痛",
        "status": "active",
        "status_display": "正常",
        "first_visit_date": "2026-08-01",
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

错误：`401` 未登录。

## 创建客户

`POST /api/customers/`

权限：已登录康复师

请求体：

```json
{
  "name": "张三",
  "phone": "13800138000",
  "gender": "male",
  "main_issue": "左膝疼痛"
}
```

成功响应：返回客户详情（含完整 `phone`）。

错误：`400` 参数错误；`401` 未登录。

## 客户详情

`GET /api/customers/{id}/`

权限：已登录康复师（仅限本人客户）

成功响应：返回客户详情，**含完整手机号 `phone`（受控编辑场景）**。

错误：`401` 未登录；`404` 客户不存在或无权访问。

## 更新客户

`PUT /api/customers/{id}/`

权限：已登录康复师（仅限本人客户）

请求体：可部分更新，字段同创建。

成功响应：返回更新后的客户详情。

错误：`400` 参数错误；`401` 未登录；`404` 客户不存在或无权访问。
