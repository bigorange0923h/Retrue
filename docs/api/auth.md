# 认证接口（auth）

认证方案：Django Session + Cookie。登录成功后通过 Cookie 保持会话，跨域需允许携带凭证。
所有接口返回统一信封结构 `{code, message, data}`。

## CSRF token

`GET /api/auth/csrf/`

权限：允许匿名访问

说明：登录等写请求强制 CSRF 校验。客户端应先调用本接口获取 `csrftoken` Cookie
与 `token`，再在写请求头携带 `X-CSRFToken: {token}`。前端 http 模块已对非 GET
请求自动附加该头；登录页在挂载与提交时均会先获取一次。

成功响应：

```json
{ "code": 200, "message": "获取成功", "data": { "token": "..." } }
```

CSRF 校验失败统一返回：

```json
{ "code": 403, "message": "请求校验失败，请刷新页面后重试", "data": { "error_code": "csrf_failed" } }
```

## 登录

`POST /api/auth/login/`

权限：允许匿名访问（需携带有效 CSRF token）

请求体：

```json
{ "username": "retrue", "password": "secret" }
```

成功响应：

```json
{
  "code": 200,
  "message": "登录成功",
  "data": { "id": 1, "username": "retrue", "display_name": "张康复师", "therapist_id": 1 }
}
```

错误：
- `400` 用户名或密码错误、账号停用。
- `403` CSRF token 缺失/错误或 Origin 不被信任（`error_code=csrf_failed`）。
- `429` 账号或来源 IP 短期失败次数超过阈值（`error_code=login_throttled`），窗口过期后自动恢复，不永久锁号。

登录失败按“用户名 + 来源 IP”双维度计数，写入 PostgreSQL 数据库缓存（`retrue_cache`），
多进程共享；成功登录只清除本人的失败计数，来源 IP 的计数保留至窗口过期，避免共享出口下一个账号重置其他账号的 IP 限流。

## 登出

`POST /api/auth/logout/`

权限：已登录康复师

成功响应：

```json
{ "code": 200, "message": "已退出登录", "data": null }
```

错误：`401` 未登录。

## 当前用户

`GET /api/auth/me/`

权限：已登录康复师

成功响应：

```json
{
  "code": 200,
  "message": "获取当前用户成功",
  "data": { "id": 1, "username": "retrue", "display_name": "张康复师", "therapist_id": 1 }
}
```

错误：`401` 未登录。
