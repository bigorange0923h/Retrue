# 评估接口（assessments）

所有接口返回统一信封结构 `{code, message, data}`。数据强制按当前登录康复师隔离；康复师只填写临床观察或测量结果，量表范围、单位和满分由服务端根据指标类型派生。

## 领域规则

- `assessment_type`：`initial`（首次评估）或 `reassessment`（阶段复评）。
- `status`：`draft`（草稿）或 `completed`（已完成），新建评估默认是 `draft`。
- 草稿允许暂缺完成评估所需字段，可以保存和继续编辑；只有完成接口执行完整校验并将状态改为 `completed`。
- 每位康复师的每位客户只能有一份 `initial` 记录。已有首次评估草稿时必须返回原记录供继续编辑，不得创建第二份。
- `score_max` 是响应中的兼容字段，只能由服务端派生，客户端不得将它当作可编辑字段。新客户端请求不传该字段；兼容旧客户端期间即使传入也不能被直接信任。
- AI 上下文、趋势分析和“是否完成首次评估”的判断只读取 `status=completed` 的记录。草稿不会进入长期记忆或阶段进展依据。

## 指标类型与字段

每个指标先选择 `metric_type`，再按类型提交专用字段。页面可以使用更易懂的中文标签，但 API 字段和校验规则保持一致。

| `metric_type` | 康复师填写 | 服务端保存/派生规则 |
| --- | --- | --- |
| `pain` | `body_part`、`side`、`context`、`score`，可补充 `details` | 固定 `scale_code=NRS_0_10`、`unit=point`、`score_max=10`；`score` 只能是 0～10 的整数，越低通常越好 |
| `strength` | `body_part`、`side`、`movement`、`score`，可补充 `details` | 固定 `scale_code=MRC_0_5`、`unit=grade`、`score_max=5`；`score` 只能是 0～5 的整数，越高通常越好 |
| `rom` | `body_part`、`side`、`movement`、`measurement_mode`、`score` | `unit=degree`；允许合理范围内的小数；`scale_code` 和 `score_max` 必须为 `null` |
| `special_test` | `body_part`、`side`、`result_code`、`details.test_name` | `result_code` 为 `positive/negative/uncertain`；`score` 和 `score_max` 必须为 `null` |
| `functional` | `details.action_name`、`result_code`，可补充 `details.pain_status` | `result_code` 为 `normal/limited/unable`；观察型记录不使用 `score` 和 `score_max` |

通用指标字段还包括：`description`（补充描述）、`sort_order`（展示顺序）、`details`（类型专用扩展对象）、`side`（`left/right/bilateral/not_applicable`）、`context`（`rest/activity/pre_training/post_training/night/custom`）、`measurement_mode`（ROM 使用 `active/passive`，其他类型为 `null`）。

## 指标定义

`GET /api/assessments/metric-definitions/`

权限：已登录康复师。

该接口是前端量表控件的单一规则来源，返回五种指标的名称、结果类型、必填字段、可选值、最小值、最大值、步长、单位、计分方向和解释。页面不得另行维护一套会与服务端不一致的满分或选项。MRC 解释文案也由此接口提供。

示例响应（字段可随版本增加）：

```json
{
  "code": 200,
  "message": "查询评估指标定义成功",
  "data": [
    {
      "metric_type": "pain",
      "name": "疼痛",
      "result_kind": "numeric",
      "scale_code": "NRS_0_10",
      "min": 0,
      "max": 10,
      "step": 1,
      "unit": "point",
      "score_direction": "lower_is_better",
      "required_fields": ["body_part", "side", "context", "score"]
    },
    {
      "metric_type": "strength",
      "name": "肌力",
      "result_kind": "scale",
      "scale_code": "MRC_0_5",
      "min": 0,
      "max": 5,
      "step": 1,
      "unit": "grade",
      "score_direction": "higher_is_better",
      "required_fields": ["body_part", "side", "movement", "score"],
      "options": [
        { "value": 0, "label": "未观察到肌肉收缩" },
        { "value": 1, "label": "可观察或触及轻微收缩" },
        { "value": 2, "label": "去除重力后可以完成活动" },
        { "value": 3, "label": "可以克服重力完成活动" },
        { "value": 4, "label": "可以抵抗一定阻力，但较正常弱" },
        { "value": 5, "label": "肌力正常" }
      ]
    },
    {
      "metric_type": "rom",
      "name": "关节活动度",
      "result_kind": "numeric",
      "unit": "degree",
      "score_direction": "neutral",
      "required_fields": ["body_part", "side", "movement", "measurement_mode", "score"]
    },
    {
      "metric_type": "special_test",
      "name": "特殊测试",
      "result_kind": "categorical",
      "score_direction": "neutral",
      "required_fields": ["body_part", "side", "result_code", "details.test_name"],
      "options": ["positive", "negative", "uncertain"]
    },
    {
      "metric_type": "functional",
      "name": "功能动作",
      "result_kind": "categorical",
      "score_direction": "neutral",
      "required_fields": ["details.action_name", "result_code"],
      "options": ["normal", "limited", "unable"]
    }
  ]
}
```

## 评估列表

`GET /api/assessments/?customer_id={id}`

可选参数：`status=draft` 或 `status=completed`。不传时返回该康复师对该客户有权限访问的全部评估。

权限：已登录康复师

成功响应：

```json
{
  "code": 200,
  "message": "查询评估成功",
  "data": [
    {
      "id": 1,
      "customer": 1,
      "customer_name": "张三",
      "plan": null,
      "assessment_type": "initial",
      "assessment_type_display": "首次评估",
      "status": "completed",
      "status_display": "已完成",
      "completed_at": "2026-08-01T11:00:00+08:00",
      "assessment_date": "2026-08-01",
      "chief_complaint": "左膝前侧疼痛",
      "medical_history": "",
      "onset_date": "2026-07-20",
      "onset_description": "",
      "onset_mode": "gradual",
      "aggravating_factors": "下蹲至90度时加重",
      "relieving_factors": "休息后减轻",
      "prior_care": "",
      "surgery_history": "",
      "medication": "",
      "exercise_habits": "每周跑步2次",
      "work_demands": "久坐",
      "sleep_impact": "无明显影响",
      "rehab_goal": "恢复下蹲功能",
      "current_status": "",
      "note": "",
      "metrics": [
        {
          "id": 1,
          "metric_type": "pain",
          "metric_type_display": "疼痛",
          "body_part": "左膝前侧",
          "side": "left",
          "context": "activity",
          "movement": "",
          "measurement_mode": null,
          "score": 6,
          "score_max": 10,
          "scale_code": "NRS_0_10",
          "unit": "point",
          "result_code": null,
          "details": { "pain_type": "刺痛", "aggravating_action": "下蹲至90度" },
          "description": "活动时加重",
          "sort_order": 0
        }
      ],
      "created_at": "2026-08-26T10:00:00+08:00",
      "updated_at": "2026-08-26T10:00:00+08:00"
    }
  ]
}
```

草稿响应同样返回完整结构，但 `status=draft`、`completed_at=null`。客户详情判断是否已完成首次评估时必须过滤 `status=completed`；如果存在 `initial` 草稿，前端应提供“继续评估”。

错误：`400` 缺少或无效的 `customer_id`；`401` 未登录；`404` 客户不存在或无权访问。

## 创建评估

`POST /api/assessments/`

权限：已登录康复师，且只能为本人客户创建。

新建请求默认保存为草稿。草稿阶段允许暂缺完成评估字段；客户端不传 `score_max`、`scale_code`、`unit` 等派生字段，服务端根据 `metric_type` 生成它们。

请求体示例：

```json
{
  "customer": 1,
  "assessment_type": "initial",
  "assessment_date": "2026-08-01",
  "chief_complaint": "左膝前侧疼痛",
  "onset_mode": "gradual",
  "aggravating_factors": "下蹲至90度时加重",
  "rehab_goal": "恢复下蹲功能",
  "metrics": [
    {
      "metric_type": "pain",
      "body_part": "左膝前侧",
      "side": "left",
      "context": "activity",
      "score": 6,
      "details": { "pain_type": "刺痛", "aggravating_action": "下蹲至90度" },
      "description": "活动时加重"
    },
    {
      "metric_type": "strength",
      "body_part": "左膝",
      "side": "left",
      "movement": "膝关节伸展",
      "score": 4,
      "details": { "muscle_group": "股四头肌" }
    },
    {
      "metric_type": "rom",
      "body_part": "膝关节",
      "side": "left",
      "movement": "屈曲",
      "measurement_mode": "active",
      "score": 90
    },
    {
      "metric_type": "special_test",
      "body_part": "膝关节",
      "side": "left",
      "result_code": "negative",
      "details": { "test_name": "Lachman测试" }
    },
    {
      "metric_type": "functional",
      "body_part": "下肢",
      "side": "left",
      "result_code": "limited",
      "details": { "action_name": "单腿蹲", "pain_status": "有", "observation": "膝内扣" }
    }
  ]
}
```

响应返回创建后的完整评估（含 `id`、`status=draft`、派生字段和指标 ID）。更新接口使用同一数据结构。

错误：

- `400` 指标字段格式不正确，返回 `metric_value_out_of_range` 或 `metric_required_field_missing`。
- `401` 未登录。
- `403` 无权为该客户创建。
- `409` `initial_assessment_exists`：该康复师和客户已有首次评估，`data.assessment_id` 返回已有记录 ID；前端应打开该草稿或展示已完成记录。

## 首次评估直达接口

`GET /api/assessments/initial/?customer_id={id}`

权限：已登录康复师。

前端“去评估 / 继续评估”引导可直接使用本接口判断首评状态，无需自行遍历列表查找 `assessment_type=initial` 的记录。返回该客户是否存在首评及其状态：

```json
{
  "code": 200,
  "message": "查询首次评估成功",
  "data": {
    "exists": true,
    "status": "draft",
    "assessment_id": 1
  }
}
```

- `exists: false`：尚无首评，前端应引导创建新首评。
- `exists: true` 且 `status=draft`：存在未完成首评，前端应引导继续编辑该记录（用 `assessment_id` 打开）。
- `exists: true` 且 `status=completed`：首评已完成，前端不再提示“去评估”。

错误：`400` 缺少或无效的 `customer_id`；`401` 未登录；`404` 客户不存在或无权访问。

## 评估详情

`GET /api/assessments/{id}/`

权限：已登录康复师，仅能读取自己的评估。

返回与列表中的单个评估结构相同，包含草稿/完成状态、主观字段、全部指标专用字段和服务端派生的量表信息。

错误：`401` 未登录；`404` 评估不存在或无权访问。

## 更新评估 / 自动保存草稿

`PUT /api/assessments/{id}/`

说明：更新评估及其指标，并记录审计。指标按 `id` 做差异同步：提交项带 `id` 且属于当前评估时更新原指标（保留原 id），不带 `id` 的新增，本次未提交的已存在指标被删除。更新不能修改客户归属、康复师归属或首次评估唯一性。`score_max` 等派生字段不可写；兼容旧客户端时服务端忽略或重新计算该字段，兼容窗口结束后可返回字段错误。

指标差异更新示例：更新已有指标（带 `id`，保留原 id）、新增指标（不带 `id`）；未出现在本次提交中的旧指标会被删除。

```json
{
  "metrics": [
    { "id": 10, "metric_type": "pain", "body_part": "左膝", "side": "left", "context": "activity", "score": 5 },
    { "metric_type": "rom", "body_part": "左膝", "side": "left", "movement": "屈曲", "measurement_mode": "active", "score": 90 }
  ]
}
```

草稿可继续保存；已完成记录如需修订仍须通过人工编辑并留下审计记录，不能通过普通请求降级为草稿。若修改后需要重新校验完成状态，继续调用完成接口。

错误：`400` 指标校验失败；`403` 无权修改；`404` 评估不存在；`409` `initial_assessment_exists` 或其他唯一性冲突。

## 完成评估

`POST /api/assessments/{id}/complete/`

权限：已登录康复师，仅能完成自己的评估。

请求体：`{}`。

服务端在事务中执行：

1. 校验评估和客户归属、康复计划归属。
2. 对五类指标执行完整的必填、范围、单位、量表和分类值校验。
3. 校验首次评估唯一性。
4. 将 `status` 更新为 `completed`，写入 `completed_at`。
5. 写入评估完成审计日志。
6. 返回完整评估。

成功响应中的 `status` 必须为 `completed`。完成后客户详情不再提示“去评估”，记录才可被 AI、趋势和阶段进展服务消费。

空转重试：已通过正常流程完成（`completed_at` 非空）且完成后未再修改（`updated_at <= completed_at`）的评估，重复调用完成接口会直接返回，不再重复全量校验。若完成后被修订过，服务端会按最新内容重新校验——此时缺少的必填项会导致 `400 assessment_incomplete`，需补齐后再次提交。

错误：

- `400` `assessment_incomplete`：缺少完成必填项，同时返回字段级错误。
- `400` `metric_value_out_of_range`：疼痛不在 0～10 或肌力不在 0～5 等。
- `400` `metric_required_field_missing`：ROM 缺少动作/侧别/主动被动方式，特殊测试缺少测试名称或结果，功能动作缺少动作名称或完成情况。
- `400` `plan_customer_mismatch`：康复计划不属于当前客户。
- `401` 未登录。
- `403` 无权完成。
- `404` 评估不存在。
- `409` 首次评估唯一性冲突。

统一错误示例：

```json
{
  "code": 400,
  "message": "评估尚未完成",
  "data": {
    "error_code": "assessment_incomplete",
    "fields": {
      "rehab_goal": ["请输入康复目标"],
      "metrics[0].context": ["请选择疼痛出现的场景"]
    }
  }
}
```

## 兼容与迁移

- 保留历史 `score` 和 `score_max` 字段，旧评估仍可读取和编辑。
- 新写入由服务端派生 `score_max`：疼痛为 10、肌力为 5，ROM/特殊测试/观察型功能动作为 `null`。
- 历史数据无法可靠推断的侧别、动作、场景和测量方式保持为空，不根据自由文本猜测。
- 数据库增加首次评估条件唯一约束前，应先输出重复数据清单；历史重复记录按迁移方案处理。
