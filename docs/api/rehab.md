# 康复计划与阶段接口（rehab）

所有接口返回统一信封结构 `{code, message, data}`。数据强制按当前康复师隔离。

## 康复计划列表

`GET /api/rehab/plans/?customer_id={id}`

权限：已登录康复师

成功响应：

```json
{
  "code": 200,
  "message": "查询康复计划成功",
  "data": [
    {
      "id": 1,
      "customer": 1,
      "customer_name": "张三",
      "name": "默认康复计划",
      "start_date": "2026-08-01",
      "status": "active",
      "status_display": "进行中",
      "note": "",
      "stages": [],
      "created_at": "2026-08-26T10:00:00+08:00",
      "updated_at": "2026-08-26T10:00:00+08:00"
    }
  ]
}
```

错误：`400` 缺少 customer_id；`401` 未登录。

## 创建康复计划

`POST /api/rehab/plans/`

请求体：`{ "customer": 1, "start_date": "2026-08-01", "name": "默认康复计划" }`

错误：`403` 无权为该客户操作。

## 查询当前康复阶段

`GET /api/rehab/stages/?customer_id={id}`

返回客户当前有效阶段（未结束）：

```json
{
  "code": 200,
  "message": "查询当前阶段成功",
  "data": { "id": 1, "stage_type": "acute", "stage_type_display": "急性期/疼痛控制", "start_date": "2026-08-01", "end_date": null }
}
```

## 设置康复阶段

`POST /api/rehab/stages/`

请求体：

```json
{
  "customer": 1,
  "stage_type": "strength",
  "start_date": "2026-08-26",
  "note": "疼痛控制稳定，进入力量重建期"
}
```

说明：设置新阶段会自动关闭该客户上一条未结束的阶段，确保同一时间只有一个有效阶段。

错误：`403` 无权为该客户操作。
