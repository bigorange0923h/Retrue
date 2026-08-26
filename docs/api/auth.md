# 认证接口（auth）

认证方案：Django Session + Cookie。登录成功后通过 Cookie 保持会话，跨域需允许携带凭证。

所有接口返回统一信封结构 `{code, message, data}`。

## 登录

`POST /api/auth/login/`

权限：允许匿名访问

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

错误：`400` 用户名或密码错误、账号停用；`401` 未登录。

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
