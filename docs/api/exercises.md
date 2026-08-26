# 动作库接口（exercises）

所有接口返回统一信封结构 `{code, message, data}`。

## 动作库列表

`GET /api/exercises/?keyword={名称}`

权限：已登录康复师

说明：返回官方动作 + 本人个人动作（不含他人个人动作）。

成功响应：

```json
{
  "code": 200,
  "message": "查询动作库成功",
  "data": [
    {
      "id": 1,
      "name": "臀桥",
      "body_part": "髋",
      "description": "",
      "precautions": "",
      "contraindications": "",
      "is_official": true,
      "aliases": [],
      "created_at": "2026-08-26T10:00:00+08:00",
      "updated_at": "2026-08-26T10:00:00+08:00"
    }
  ]
}
```

错误：`401` 未登录。

## 创建个人动作

`POST /api/exercises/`

请求体：`{ "name": "靠墙静蹲", "body_part": "膝", "description": "..." }`

错误：`400` 参数错误。

## 动作详情

`GET /api/exercises/{id}/`

错误：`404` 动作不存在或无权访问（他人个人动作）。

## 更新动作

`PUT /api/exercises/{id}/`

说明：仅个人动作可修改。

错误：`403` 官方动作不可修改；`404` 无权访问。
