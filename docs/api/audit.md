# 审计日志接口（audit）

所有接口返回统一信封结构 `{code, message, data}`。

所有列表与按对象查询仅返回 `actor=当前登录康复师` 的日志。当前无跨康复师审计查看业务角色，`is_staff`/`is_superuser` 不隐式扩大接口读取权限；其他账号和系统日志不会通过这些接口返回。`export` 表示客户资料导出访问，仅保存导出类型、脱敏标记和记录数，不在审计中复制整份健康资料。

## 审计日志分页列表

`GET /api/audit/`

权限：已登录康复师

查询参数：
- `content_type`（可选）：ContentType id。
- `object_id`（可选）：业务对象 id，需配合 `content_type`。
- `page`（可选）：页码，默认 1。
- `page_size`（可选）：每页条数，默认 20，最大 100。

成功响应：

```json
{
  "code": 200,
  "message": "查询审计日志成功",
  "data": {
    "items": [
      {
        "id": 1,
        "action": "login",
        "action_display": "登录",
        "actor_name": "retrue",
        "before_data": {},
        "after_data": {},
        "reason": "",
        "created_at": "2026-08-26T10:00:00+08:00"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
}
```

错误：`401` 未登录。

## 对象审计历史

`GET /api/audit/object/?model=customer&object_id=1`

权限：已登录康复师

查询参数：
- `model`：模型名（小写，如 `customer`、`trainingrecord`）。
- `object_id`：对象主键。

成功响应：返回该对象的审计日志列表（无分页）。

```json
{
  "code": 200,
  "message": "查询审计历史成功",
  "data": []
}
```

错误：`400` 缺少参数或未知对象类型；`401` 未登录。
