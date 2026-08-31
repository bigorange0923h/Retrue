# 课表与课时管理接口（courses）

所有接口返回统一信封结构 `{code, message, data}`。数据强制按当前康复师隔离。

课程计划与课表的职责不同：课程计划定义“要上哪门课、计划多少次”，课表定义“具体哪天、几点上”。
`CourseSession.plan_course` 用来把一次实际课程归入计划内课程；历史或不消耗计划次数的事项使用空关联和明确的 `arrangement_type`。

## 课表日历

`GET /api/courses/calendar/?start=2026-08-01&end=2026-08-31`

权限：已登录康复师。返回指定日期范围内本人课程，供月历展示；单次最多查询 62 天。

返回的每条课程包含客户、日期时间、状态、课时、本节主题以及安排类型：

- `plan`：计划课程，必须关联一门客户课程计划内课程。
- `initial_assessment`：首次评估，不占用计划次数。
- `reassessment`：阶段复评，不占用计划次数。
- `other`：其他事项，不占用计划次数。

历史数据迁移时，已关联计划内课程的排课归为 `plan`，其余计划外排课归为 `other`。

## 新增单次课程

`POST /api/courses/`

```json
{
  "customer": 1,
  "plan_course": 3,
  "arrangement_type": "plan",
  "session_topic": "力量重建训练",
  "session_count": 1.0,
  "date": "2026-08-27",
  "start_time": "14:00:00",
  "end_time": "15:00:00",
  "status": "scheduled",
  "note": "首次训练"
}
```

只能为当前康复师名下客户排课。`arrangement_type=plan` 时必须提供 `plan_course`，且该课程必须属于该客户当前康复师名下的进行中课程计划；选择计划内课程后，系统会检查计划余量并按课程时长快照自动计算结束时间。`initial_assessment`、`reassessment` 和 `other` 必须不关联 `plan_course`，不会占用计划次数。

客户有进行中的课程计划时，普通康复训练不能省略安排类型和计划内课程；首次评估、阶段复评和其他事项需由康复师明确选择对应安排类型。开始/结束时间必须同时填写或同时留空，且结束时间必须晚于开始时间；新建时不能直接传 `completed`。有完整时间的待上课课程不能与同一康复师已有的待上课或已完成课程重叠；已取消和请假课程不占用时间。

新增一节有效的计划课程前，`已完成次数 + 待上课次数` 不能达到计划次数上限。超出上限时接口会提示“该课程已全部安排，不能继续添加；如需增加请先调整计划次数”。

## 批量安排课程（课程计划 → 课表）

课程计划创建后，康复师可选择“现在安排”，也可以稍后从客户详情或课表点击“安排课程”。批量向导会自动带入客户、计划内课程、单次时长和课时；预览确认后才写入课表。

### 预览

`POST /api/courses/batch/preview/`

从某门计划内课程进入时，也支持：

`POST /api/rehab/plan-courses/{plan_course_id}/schedule/preview/`

请求体：

```json
{
  "customer": 1,
  "plan_course": 3,
  "start_date": "2026-09-01",
  "weekly_count": 2,
  "weekdays": [1, 3],
  "start_time": "14:00:00"
}
```

`weekdays` 使用日历约定：`0` 为周日，`1` 至 `6` 为周一至周六；`weekly_count` 必须与选择的星期数量一致。开始日期必须在课程计划日期范围内。向导会按“待安排次数”生成候选课程，并以计划内课程的 `duration` 计算结束时间；填写开始时间时，如果课程没有单次时长，接口会提示先补充时长（否则无法生成完整时间段）。如果暂不确定具体时段，开始时间和结束时间可以一起留空。

预览只读数据库，不创建排课。成功响应的 `data` 包含：

```json
{
  "plan_course": 3,
  "customer": 1,
  "requested_count": 6,
  "scheduled_count": 1,
  "unscheduled_count": 6,
  "items": [
    {
      "id": null,
      "date": "2026-09-01",
      "start_time": "14:00:00",
      "end_time": "15:00:00",
      "session_topic": "力量重建训练",
      "session_count": 1.0,
      "arrangement_type": "plan",
      "status": "scheduled"
    }
  ],
  "conflicts": [],
  "can_confirm": true
}
```

`items` 是即将加入课表的课程列表；`sessions` 为兼容客户端保留的同内容字段。若与同一康复师已有有效课程发生时间重叠，`conflicts` 会返回日期、时间、已有课程 ID 和自然语言提示，例如“9月8日 14:00 已有其他客户课程，请调整时间”，此时 `can_confirm=false`。

### 确认

`POST /api/courses/batch/confirm/`

从某门计划内课程进入时，也支持：

`POST /api/rehab/plan-courses/{plan_course_id}/schedule/confirm/`

确认接口使用与预览相同的请求体。服务端会重新锁定计划内课程、重算已完成/已安排/待安排次数并再次检查时间冲突；预览后若数据发生变化，确认会失败并返回冲突或余量提示。全部候选课程在同一事务中创建，不能只成功一部分。

成功响应的 `data` 包含 `created_count`、`items`（已写入的课程列表）、兼容字段 `sessions` 和空的 `conflicts`。批量安排只创建“待上课”状态；正式训练记录保存后，原有完成与课时扣减流程继续生效。

## 管理单节课程

`GET /api/courses/{id}/` 查询课程详情；`PUT /api/courses/{id}/` 可更新客户、安排类型、计划内课程、课时、日期、时间、备注及状态。

课程取消请将 `status` 更新为 `cancelled`，以保留排课历史；不提供物理删除接口。“已完成”不能从课程接口直接设置，必须由关联正式训练记录触发。补课应修改原请假/取消排课的日期、时间并改回 `scheduled`，不要为同一次课程重复建单。将取消或请假课程改回待上课时，会重新检查时间冲突和计划余量。

计划内课程只能归入同一客户和当前康复师的进行中计划；更换已存在正式训练记录的课程客户、计划课程、课时或完成状态会被拒绝。

## 课程模板

- `GET /api/courses/course-types/`：查询当前康复师的课程模板。
- `POST /api/courses/course-types/`：创建课程模板及默认时长、单次课时和目标。
- `PUT /api/courses/course-types/{id}/`：更新或停用模板。停用不影响历史计划内课程。

计划内课程的创建、更新和次数调整接口见 `rehab.md`。

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
      "adjustments": [
        {
          "id": 5,
          "adjustment_type": "consumption",
          "adjustment_type_display": "课程扣减",
          "delta": 1.0,
          "reason": "排课 10 保存正式训练记录，自动扣减 1.0 课时",
          "course_session": 10,
          "course_session_topic": "力量重建训练",
          "therapist_name": "therapist1",
          "created_at": "2026-08-26T10:00:00+08:00"
        }
      ],
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
- `delta`：已用课时调整量，正值补扣、负值退还；必须是非零的 `0.5` 倍数。
- `reason`：调整原因，**必填**。
- 调整后的已用课时不得小于 `0` 或超过总课时；成功后会新增 `manual` 类型课时流水。

错误：`400` 缺少原因或参数错误；`404` 课时包不存在或无权访问。

## 课时消耗规则

课时消耗需同时满足：
1. 排课关联正式训练记录。
2. 系统将排课转为已完成。

正式训练记录保存、课程完成、结构化课时流水和课时扣减在同一数据库事务中完成。课时不足时返回明确错误并回滚；请假、取消不扣课时，同一排课不能重复创建正式记录。
