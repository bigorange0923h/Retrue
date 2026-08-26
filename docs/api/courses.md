# 课时管理接口（courses）

所有接口返回统一信封结构 `{code, message, data}`。数据强制按当前康复师隔离。

## 课时包列表

`GET /api/courses/packages/?customer_id={id}`

权限：已登录康复师

成功响应：

```json
{
  "code": 200,
  "message": "查询课时包成功",
  "data": [
    {
      "id": 1,
      "customer": 1,
      "customer_name": "张三",
      "name": "20课时包",
      "total_sessions": 20,
      "used_sessions": 2,
      "remaining_sessions": 18,
      "note": "",
      "created_at": "2026-08-26T10:00:00+08:00",
      "updated_at": "2026-08-26T10:00:00+08:00"
    }
  ]
}
```

错误：`400` 缺少 customer_id；`401` 未登录。

## 创建课时包

`POST /api/courses/packages/`

请求体：`{ "customer": 1, "name": "20课时包", "total_sessions": 20 }`

错误：`403` 无权为该客户创建。

## 人工调整课时

`POST /api/courses/packages/{id}/adjust/`

请求体：

```json
{ "delta": -1, "reason": "误扣退还1课时" }
```

说明：
- `delta`：调整量，正值扣减已用课时、负值退还已用课时。
- `reason`：调整原因，**必填**。

错误：`400` 缺少原因或参数错误；`404` 课时包不存在或无权访问。

## 课时消耗规则

课时消耗需同时满足：
1. 课程已完成。
2. 训练记录已确认保存。

请假、取消不扣课时；补课不重复扣。
