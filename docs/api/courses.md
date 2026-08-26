# 课程/日程接口（courses）

所有接口返回统一信封结构 `{code, message, data}`。课程数据强制按当前康复师隔离。

## 今日课程

`GET /api/courses/today/`

权限：已登录康复师

查询参数：
- `date`（可选）：日期 `YYYY-MM-DD`，缺省为今天。

成功响应：

```json
{
  "code": 200,
  "message": "查询今日课程成功",
  "data": [
    {
      "id": 1,
      "customer": 1,
      "customer_name": "张三",
      "customer_phone_masked": "138****1234",
      "date": "2026-08-26",
      "start_time": "10:00:00",
      "end_time": "11:00:00",
      "status": "scheduled",
      "status_display": "待上课",
      "note": ""
    }
  ]
}
```

错误：`400` 日期格式错误；`401` 未登录。

## 创建课程

`POST /api/courses/`

权限：已登录康复师

请求体：

```json
{
  "customer": 1,
  "date": "2026-08-26",
  "start_time": "10:00:00",
  "end_time": "11:00:00",
  "status": "scheduled",
  "note": ""
}
```

成功响应：返回创建的课程。

错误：`400` 参数错误；`401` 未登录；`403` 无权为该客户排课。
