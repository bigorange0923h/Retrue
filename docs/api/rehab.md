# 客户课程计划与康复阶段接口（rehab）

所有接口返回统一信封结构 `{code, message, data}`。数据强制按当前康复师隔离。

## 课程计划模板

### 查询课程计划模板

`GET /api/rehab/plan-templates/?keyword={关键词}&active_only=1`

返回当前康复师维护的模板及其课程组成、默认总次数、计划总课时和已应用客户计划数。

### 创建课程计划模板

`POST /api/rehab/plan-templates/`

```json
{
  "name": "膝关节术后恢复",
  "description": "适用于膝关节术后基础恢复",
  "suggested_duration_weeks": 12,
  "goals": "恢复无痛行走及基础运动能力",
  "is_active": true,
  "courses": [
    {
      "course_type": 2,
      "planned_count": 8,
      "duration": 60,
      "session_cost": 1.0,
      "goals": "恢复关节活动度",
      "sort_order": 0
    }
  ]
}
```

启用的课程计划模板至少包含一门启用的本人课程模板；同一课程不能在一个计划模板中重复添加。

### 更新课程计划模板

`PUT /api/rehab/plan-templates/{id}/`

可以更新基本信息、启用状态和完整课程组成。更新模板只影响以后创建的客户计划，不修改已经复制出的 `RehabPlan` 和 `RehabPlanCourse`。

## 客户课程计划列表

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
      "source_template": 3,
      "source_template_name": "膝关节术后恢复",
      "name": "课程计划",
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

## 创建客户课程计划

`POST /api/rehab/plans/`

可以创建空白计划，也可以选择课程计划模板并提交康复师在预览中调整后的课程快照：

```json
{
  "customer": 1,
  "source_template": 3,
  "start_date": "2026-08-01",
  "end_date": "2026-10-31",
  "name": "张三膝关节术后恢复计划",
  "goals": "恢复无痛下蹲",
  "courses": [
    {
      "course_type": 2,
      "package": 6,
      "planned_count": 6,
      "duration": 60,
      "session_cost": 1.0,
      "goals": "按首次评估调整后的活动度目标"
    }
  ]
}
```

传 `source_template` 但不传 `courses` 时，后端按模板当前课程组成复制；传 `courses` 时，以预览调整后的课程为准。模板只记录来源，创建后的客户计划与模板独立。

同一客户只能有一个进行中的课程计划，服务层与数据库均会约束。错误：`400` 已有进行中计划或参数错误；`403` 无权为该客户操作。

计划创建成功后，PC 和移动端会向康复师提示“课程计划已保存，是否现在安排上课时间？”，可选择“现在安排”进入课表安排向导，也可选择“稍后再说”留在客户详情。该提示是页面流程，不会在创建计划接口中静默生成排课。

## 更新客户课程计划

`PUT /api/rehab/plans/{id}/`

可更新计划名称、起止日期、总体目标、备注和状态（`active` / `closed`）。结束日期不得早于开始日期或当前阶段进入日期；关闭计划时系统同步关闭当前康复阶段，之后不能继续添加排课或调整课程次数。

## 计划内课程列表

`GET /api/rehab/plan-courses/?plan_id={plan_id}`

也可使用 `customer_id` 和 `status` 查询。每条计划内课程返回：课程模板、单次时长、单次课时消耗、计划次数、已完成次数、剩余次数、状态、课时包及次数调整历史。

与课表联动时，还会返回以下进度字段：

- `completed_count`：已有正式训练记录且排课为“已完成”的次数。
- `scheduled_count`：状态为“待上课”的有效排课次数；日期已过但尚未处理的课程仍计入此项。
- `unscheduled_count`：`max(planned_count - completed_count - scheduled_count, 0)`，即还没有放入课表的次数。
- `overdue_count`：日期已过但仍为“待上课”的次数。
- `next_session`：今天起最近一节待上课课程；没有则为 `null`。
- `remaining_count`：为兼容旧客户端保留，当前含义与 `unscheduled_count` 相同。

已取消和请假课程不计入 `scheduled_count` 或 `completed_count`。这些统计由关联的课程排期实时计算，不在计划内课程表中另存重复数字。

### 计划内课程进度示例

```json
{
  "id": 3,
  "course_type_name": "力量重建训练",
  "planned_count": 10,
  "completed_count": 2,
  "scheduled_count": 5,
  "unscheduled_count": 3,
  "overdue_count": 1,
  "next_session": {
    "id": 18,
    "date": "2026-09-03",
    "start_time": "14:00:00",
    "end_time": "15:00:00",
    "status": "scheduled"
  },
  "remaining_count": 3
}
```

从客户计划内课程点击“安排课程”时，前端会自动带入客户和这门课程；批量预览与确认接口及数量/冲突规则详见 [`docs/api/courses.md`](courses.md) 的“批量安排课程”章节。

## 添加计划内课程

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

课程必须属于进行中的客户课程计划；未传时长、单次课时或目标时，从课程模板复制默认值。

新添加的课程状态为“进行中”，不能直接设为“已完成”。计划关闭后不能添加课程。暂停或取消一门计划内课程前，如仍有待上课排课，接口会要求先取消或改期这些课程。

## 更新计划内课程

`PUT /api/rehab/plan-courses/{id}/`

可更新课程级目标、单次时长、单次课时、课时包和状态。所属计划与课程模板创建后不可更换；已有扣课记录后不能更换课时包。计划次数必须通过“调整课程次数”接口增减并填写原因。将课程改为“已完成”前，已完成次数必须达到计划次数；有待上课排课时暂停或取消会被阻止，需先处理未来课程。

## 调整课程次数

`POST /api/rehab/plan-courses/{id}/adjust/`

```json
{
  "delta_count": 2,
  "reason": "阶段复评后增加力量训练",
  "assessment": 12
}
```

`delta_count` 正数增加、负数减少；调整后次数不能少于“已完成次数 + 已安排次数”。逾期但仍待上课的课程也属于已安排，需先取消或改期后再减少计划次数。只能调整进行中计划且不能调整已取消的计划内课程。系统保存调整前后次数、原因、操作人、时间和可选关联复评，并在客户详情展示历史。

单节排课和批量确认都会在服务端重新检查计划余量；`已完成 + 待上课` 达到计划次数后不能继续新增有效排课。课程计划关闭时，如仍有待上课课程，接口会拒绝关闭；修改结束日期时也不能把待上课课程排到计划结束日期之后。

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

说明：客户必须先有进行中的课程计划；也可传 `plan` 明确指定该客户的进行中计划。康复阶段必须位于计划日期范围内。设置新当前阶段会自动关闭该计划上一条未结束的阶段，确保每个计划同一时间只有一个有效阶段；阶段的客户和康复师归属由计划派生，不重复保存。

错误：`400` 没有进行中周期、日期不在周期内或参数错误；`403/404` 客户无权访问或不存在。
