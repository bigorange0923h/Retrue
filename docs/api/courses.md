# 课表与课时管理接口（courses）

所有接口返回统一信封结构 `{code, message, data}`。数据强制按当前康复师隔离。

## 课表日历

`GET /api/courses/calendar/?start=2026-08-01&end=2026-08-31`

权限：已登录康复师。返回指定日期范围内本人课程，供月历展示；单次最多查询 62 天。

## 手动添加课程

`POST /api/courses/`

```json
{
  "customer": 1,
  "plan_course": 3,
  "session_topic": "力量重建训练",
  "session_count": 1.0,
  "date": "2026-08-27",
  "start_time": "14:00:00",
  "end_time": "15:00:00",
  "status": "scheduled",
  "note": "首次训练"
}
```

只能为当前康复师名下客户排课。`plan_course` 可空；选择时必须属于该客户进行中课程计划里的课程，已结束计划不能继续排课。首次评估等计划外课程可以不关联计划内课程。开始/结束时间必须同时填写或同时留空，且结束时间必须晚于开始时间；新建时不能直接传 `completed`。前端选择计划内课程后会按其时长快照自动计算结束时间。

## 管理单节课程

`GET /api/courses/{id}/` 查询课程详情；`PUT /api/courses/{id}/` 可更新客户、计划内课程、课时、日期、时间、备注及状态。

课程取消请将 `status` 更新为 `cancelled`，以保留排课历史；不提供物理删除接口。“已完成”不能从课程接口直接设置，必须由关联正式训练记录触发。补课应修改原请假/取消排课的日期、时间并改回 `scheduled`，不要为同一次课程重复建单。

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
