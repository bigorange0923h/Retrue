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
      "end_date": "2026-10-31",
      "status": "active",
      "status_display": "进行中",
      "goals": "恢复无痛下蹲和基础跑跳能力",
      "note": "",
      "stages": [],
      "course_count": 3,
      "created_at": "2026-08-26T10:00:00+08:00",
      "updated_at": "2026-08-26T10:00:00+08:00"
    }
  ]
}
```

错误：`400` 缺少 customer_id；`401` 未登录。

## 创建康复计划

`POST /api/rehab/plans/`

请求体：`{ "customer": 1, "start_date": "2026-08-01", "end_date": "2026-10-31", "name": "膝关节术后周期", "goals": "恢复无痛下蹲" }`

同一客户只能有一个进行中的康复周期，服务层与数据库均会约束。错误：`400` 已有进行中周期或参数错误；`403` 无权为该客户操作。

## 更新康复周期

`PUT /api/rehab/plans/{id}/`

可更新周期名称、起止日期、总体目标、备注和状态（`active` / `closed`）。结束日期不得早于开始日期或当前阶段进入日期；关闭周期时系统同步关闭当前阶段，之后不能继续添加排课或调整课程次数。

## 周期课程列表

`GET /api/rehab/plan-courses/?plan_id={plan_id}`

也可使用 `customer_id` 和 `status` 查询。每条周期课程返回：课程模板、单次时长、单次课时消耗、计划次数、已完成次数、剩余次数、状态、课时包及次数调整历史。

## 添加周期课程

`POST /api/rehab/plan-courses/`

```json
{
  "rehab_plan": 1,
  "course_type": 2,
  "package": 3,
  "planned_count": 8,
  "duration": 60,
  "session_cost": 1.0,
  "goals": "恢复单腿稳定与下肢力量"
}
```

课程必须属于进行中的康复周期；未传时长、单次课时或目标时，从课程模板复制默认值。

## 更新周期课程

`PUT /api/rehab/plan-courses/{id}/`

可更新课程级目标、单次时长、单次课时、课时包和状态。所属周期与课程模板创建后不可更换；已有扣课记录后不能更换课时包。计划次数必须通过“调整课程次数”接口增减并填写原因。

## 调整课程次数

`POST /api/rehab/plan-courses/{id}/adjust/`

```json
{
  "delta_count": 2,
  "reason": "阶段复评后增加力量训练",
  "assessment": 12
}
```

`delta_count` 正数增加、负数减少；调整后次数不能少于已经完成的次数，且只能调整进行中周期的课程。系统保存调整前后次数、原因、操作人、时间和可选关联复评，并在客户详情展示历史。

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

说明：客户必须先有进行中的康复周期；也可传 `plan` 明确指定该客户的进行中周期。阶段必须位于周期日期内。设置新当前阶段会自动关闭该周期上一条未结束的阶段，确保每个周期同一时间只有一个有效阶段；阶段的客户和康复师归属由周期派生，不重复保存。

错误：`400` 没有进行中周期、日期不在周期内或参数错误；`403/404` 客户无权访问或不存在。
