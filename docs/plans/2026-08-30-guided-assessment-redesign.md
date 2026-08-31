# Retrue 引导式评估模块改造执行方案

> 状态：已实施（代码与自动化验证完成；开发 PostgreSQL 迁移待 Docker Desktop 启动后执行）  
> 编写日期：2026-08-30  
> 适用范围：`retrue-server/apps/assessments`、`retrue-web/src/views/assessment` 及其关联服务  
> 执行对象：后续负责修改代码与业务逻辑的 AI / 开发人员

## 1. 改造结论

当前评估页将底层通用字段 `score`、`score_max` 直接展示为“评分、满分”，并让疼痛、肌力、活动度、特殊测试和功能动作共用一套输入方式。这会让康复师先理解系统结构，才能完成临床记录。

本次改造应采用以下原则：

1. 康复师只填写实际询问、观察和测量的结果。
2. 量表范围、满分、单位、结果方向和解释由系统管理，禁止康复师手工填写“满分”。
3. 不同指标类型使用不同输入控件和校验规则。
4. 首次评估采用引导式步骤；移动端一屏一阶段、一个主要输入项占满一行。
5. 草稿和已完成评估分开管理；AI、趋势分析和首次评估完成判断只使用已完成数据。
6. AI 可以整理和建议，但不能代替康复师确认临床评估结果。
7. 改造必须兼容现有评估数据，不能直接删除 `score`、`score_max` 或覆盖历史评估。

## 2. 当前实现基线

### 2.1 后端

- `Assessment` 保存评估类型、日期、主诉、病史、目标、当前状态和备注。
- `AssessmentMetric` 只有通用字段：`metric_type`、`body_part`、`score`、`score_max`、`description`。
- 创建和更新接口接受前端传入的 `score_max`，服务端没有按指标类型校验范围。
- 更新评估时会删除原指标并整体重建。
- 没有限制同一客户重复创建“首次评估”。
- 没有“草稿 / 已完成”状态。
- `apps/ai/services/progress.py` 会取某一类型的第一条指标做趋势比较，尚未按部位、侧别、动作和场景匹配。

### 2.2 前端

- `AssessmentEditView.vue` 是单页长表单。
- 五类指标共用：类型、部位、评分、满分、描述。
- 首次评估引导入口已可通过 `mode=initial` 锁定评估类型。
- 客户详情在没有首次评估时会提示“去评估 / 以后再说”，但目前判断的是是否存在任意 `initial` 记录，尚未区分草稿和已完成。
- 移动端指标已临时调整为单列，但仍缺少分步骤、字段解释和类型专用控件。
- 评估列表的编辑跳转当前使用了新建路由名并附加 `id` 参数，实施时应改为 `assessment-revise`；编辑保存后的返回客户 ID 应使用已加载的 `form.customer`，不能依赖新建页查询参数。

### 2.3 必须同步维护的文件

- Django 模型与 migration。
- Serializer、Service、View、URL 和 API 测试。
- 前端 API 类型、页面、组件和构建。
- `docs/api/assessments.md`。
- `docs/database/assessments.sql`。
- `docs/Retrue_项目设计文档_V1.0.md`。
- 使用评估指标的 AI 趋势服务及其测试。

## 3. 目标业务流程

### 3.1 未完成首次评估的客户

```text
进入客户详情
  └─ 查询是否存在“已完成”的首次评估
       ├─ 已完成：不提示
       ├─ 存在首次评估草稿：提示“继续评估 / 以后再说”
       └─ 不存在：提示“去评估 / 以后再说”
```

- “去评估”进入绑定当前客户的首次评估页。
- 首次评估类型不可切换。
- “继续评估”打开已有草稿，不能再创建第二份首次评估。
- “以后再说”仅关闭本次提示，不应伪造已评估状态。
- 首次评估完成后不再提示。

### 3.2 首次评估步骤

```text
步骤 1：本次问题
步骤 2：主观情况
步骤 3：客观评估
步骤 4：康复目标与备注
步骤 5：检查并完成
```

每个步骤点击“下一步”时自动保存草稿，保存成功后才切换步骤，不提供单独的“保存草稿”按钮。最后一步执行“完成评估”，服务端进行完整校验。

### 3.3 阶段复评

- 复评单独创建，不覆盖首次评估。
- 默认带出上一次已完成评估中可比较的项目，康复师选择是否沿用。
- 对比必须按“指标类型 + 部位 + 侧别 + 动作/测试 + 场景”匹配，不能仅按指标类型取第一条。
- 复评允许增加新的评估项目。

## 4. 页面信息架构

### 4.1 步骤 1：本次问题

展示客户姓名，客户由路由绑定且不可临时更换。

字段：

- 评估日期：必填，默认当天。
- 主要问题或不适部位：必填。
- 侧别：左侧 / 右侧 / 双侧 / 不适用。
- 开始时间：允许精确日期或自由描述，二者至少填写一种。
- 发生方式：受伤 / 突然发作 / 逐渐加重 / 术后 / 其他 / 不清楚。

### 4.2 步骤 2：主观情况

页面使用问题式文案，字段仍保持结构化：

- 现在最困扰的问题是什么？对应 `chief_complaint`。
- 哪些动作或场景会加重？对应 `aggravating_factors`。
- 哪些方式可以缓解？对应 `relieving_factors`。
- 之前是否就医或接受治疗？对应 `prior_care`。
- 既往伤病、手术和用药情况，对应独立文本字段。
- 日常运动、工作负荷、睡眠影响，保存本次评估快照。

每个问题提供示例或提示语；不确定的信息允许选择“暂不清楚”，不能强迫编造。

### 4.3 步骤 3：客观评估

点击“添加评估项目”后先选择指标类型，再渲染类型专用卡片。页面禁止出现可编辑的通用“满分”。

#### 疼痛 NRS

- 部位：必填。
- 侧别：左 / 右 / 双侧 / 不适用。
- 场景：静息、活动时、训练前、训练后、夜间或自定义。
- 结果：0～10 的整数滑杆或单选刻度。
- 端点解释：0 为无痛，10 为可想象的最剧烈疼痛。
- 疼痛性质、诱发动作和描述：可选。
- 系统写入：`scale_code=NRS_0_10`、`score_max=10`、`unit=point`。

#### MRC 肌力

- 部位或肌群：必填。
- 侧别：必填。
- 动作：必填。
- 结果：0～5 单选，每一级显示临床含义，禁止自由输入小数。
- 系统写入：`scale_code=MRC_0_5`、`score_max=5`、`unit=grade`。

MRC 展示文案：

| 等级 | 页面解释 |
| --- | --- |
| 0 | 未观察到肌肉收缩 |
| 1 | 可观察或触及轻微收缩 |
| 2 | 去除重力后可以完成活动 |
| 3 | 可以克服重力完成活动 |
| 4 | 可以抵抗一定阻力，但较正常弱 |
| 5 | 肌力正常 |

#### 关节活动度 ROM

- 关节/部位：必填。
- 侧别：必填。
- 动作：必填，如屈曲、伸展、外旋。
- 测量方式：主动 AROM / 被动 PROM。
- 测量结果：角度数值，单位固定为 `°`。
- 正常参考范围由指标定义展示，只作参考，不作为“满分”。
- 系统写入：`scale_code` 为空、`score_max` 为空、`unit=degree`。

#### 特殊测试

- 测试名称：必填。
- 部位和侧别：按测试要求填写。
- 结果：阴性 / 阳性 / 无法判断。
- 症状、终末感及补充描述：可选。
- 不使用 `score` 和 `score_max`。

#### 功能动作

第一期采用观察型记录：

- 动作名称：必填。
- 完成情况：正常 / 受限 / 无法完成。
- 是否诱发疼痛：无 / 有 / 不确定。
- 观察描述：稳定性、代偿、活动质量等。
- 不使用通用满分。

正式量表作为后续独立能力接入。接入时必须记录量表代码、版本、范围、计分方向和许可信息，不能让康复师自行填写满分。

### 4.4 步骤 4：目标与备注

- 康复目标：必填，使用“希望恢复什么活动”的引导文案。
- 康复师观察与补充备注：可选。
- 首次评估不在此步骤自动创建康复计划。
- 完成评估后提供“下一步创建康复计划”入口，由康复师确认后进入计划页。

### 4.5 步骤 5：检查并完成

按中文摘要展示：

- 客户、本次问题和日期。
- 主观信息摘要。
- 客观评估卡片。
- 康复目标。
- 未完成或存在异常的字段提示。

操作：

- 返回修改。
- 点击“下一步”自动保存当前草稿。
- 完成评估。

只有“完成评估”触发完整校验，并使数据进入 AI、趋势和首次评估完成判断。

## 5. 移动端交互规则

以下规则应作为评估模块的前端硬性验收项：

1. 宽度小于或等于 768px 时，表单使用顶部标签 `label-position=top`。
2. 一个主要输入控件占满一行，不把“类型 + 部位”“评分 + 满分”等多个输入挤在同一行。
3. 输入、选择、日期、数字和操作按钮宽度为 100%。
4. 选项较多时允许按钮或单选卡片自然换行，不允许横向滚动填写核心内容。
5. 点击区域最小高度 44px。
6. 每一步只展示当前阶段所需字段；底部使用固定的“上一步 / 下一步”操作区。
7. 长列表中的每个评估项目使用独立卡片，卡片内部纵向排列。
8. 删除操作放在卡片底部，提供确认或撤销能力。
9. 弹窗宽度应适配小屏，不能使用固定 420px/480px 导致溢出。
10. 键盘弹起后，当前字段和底部主要操作仍应可访问。

## 6. 后端数据模型调整

### 6.1 `Assessment` 建议新增字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | CharField | `draft/completed`，默认 `draft` |
| `completed_at` | DateTimeField，可空 | 完成时间 |
| `onset_date` | DateField，可空 | 可确认的开始日期 |
| `onset_description` | CharField/TextField | 无法确认日期时的描述 |
| `onset_mode` | CharField | injury/sudden/gradual/postoperative/other/unknown |
| `aggravating_factors` | TextField | 加重因素 |
| `relieving_factors` | TextField | 缓解因素 |
| `prior_care` | TextField | 既往就医与治疗 |
| `surgery_history` | TextField | 手术史快照 |
| `medication` | TextField | 用药情况 |
| `exercise_habits` | TextField | 运动习惯快照 |
| `work_demands` | TextField | 工作负荷快照 |
| `sleep_impact` | TextField | 睡眠影响 |

保留现有 `chief_complaint`、`medical_history`、`rehab_goal`、`current_status` 和 `note`，避免破坏历史数据。

### 6.2 `AssessmentMetric` 建议新增字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `side` | CharField | left/right/bilateral/not_applicable |
| `scale_code` | CharField | NRS_0_10、MRC_0_5 或后续正式量表代码 |
| `unit` | CharField | point/grade/degree 等，由服务端决定 |
| `context` | CharField | rest/activity/pre_training/post_training/night/custom |
| `movement` | CharField | 动作、关节方向或肌群动作 |
| `measurement_mode` | CharField | active/passive，主要供 ROM 使用 |
| `result_code` | CharField | positive/negative/uncertain、normal/limited/unable 等分类结果 |
| `details` | JSONField | 疼痛性质、诱发动作、测试名称等扩展信息 |

兼容策略：

- 第一阶段保留 `score` 和 `score_max`。
- `score` 作为数值结果继续供疼痛、肌力和 ROM 使用，但 API 与前端统一称为“测量结果”或类型专用名称。
- `score_max` 改为服务端派生、客户端只读；ROM、特殊测试和观察型功能动作必须为空。
- 新接口若收到客户端提交的 `score_max`，不得直接信任。兼容旧客户端时可忽略，并根据类型重算；完成兼容窗口后改为拒绝该字段。

### 6.3 首次评估唯一性

- 业务目标：每位康复师的每位客户只能有一份首次评估记录，草稿应被继续编辑。
- 新建首次评估前由服务层查询现有记录；存在时返回现有评估 ID 和明确错误码，例如 `initial_assessment_exists`。
- 数据库最终增加条件唯一约束：`therapist + customer` 在 `assessment_type=initial` 时唯一。
- 增加约束前先编写数据迁移检查重复数据。
- 对历史重复数据：保留按 `assessment_date、created_at、id` 最早的一份为首次评估，其余转换为复评，并在迁移说明中记录规则。执行前在开发数据库输出重复数据清单。

## 7. 指标定义与服务端校验

### 7.1 单一规则来源

第一期在后端新增 `apps/assessments/metric_definitions.py`，集中定义：

- 指标代码和展示名称。
- 结果类型：numeric / scale / categorical。
- 最小值、最大值和步长。
- 单位。
- 计分方向：lower_is_better / higher_is_better / neutral。
- 必填字段。
- 分类选项及解释。

禁止前端和 Serializer 分别硬编码两套相互独立的规则。

建议新增接口：

```text
GET /api/assessments/metric-definitions/
```

前端使用该接口渲染范围、单位和选项。MRC 的长解释等稳定文案也可由定义接口返回。

### 7.2 校验规则

- 疼痛：整数 0～10，服务端强制 `scale_code=NRS_0_10`、`score_max=10`。
- 肌力：整数 0～5，服务端强制 `scale_code=MRC_0_5`、`score_max=5`。
- ROM：允许合理范围内的小数，必须有动作、侧别、主动/被动；`unit=degree`、`score_max=null`。
- 特殊测试：必须有测试名称和 `result_code`；`score=null`、`score_max=null`。
- 功能动作：必须有动作名称和完成情况；第一期 `score_max=null`。
- `plan` 若传入，必须属于同一康复师和同一客户。
- 更新时不能把其他客户的评估改绑到当前客户。
- 草稿采用宽松校验；完成评估采用完整校验。

## 8. API 调整

### 8.1 保留接口

- `GET /api/assessments/?customer_id={id}`。
- `POST /api/assessments/`。
- `GET /api/assessments/{id}/`。
- `PUT /api/assessments/{id}/`。

响应增加 `status`、`completed_at`、新增主观字段和新增指标字段。

### 8.2 新增接口

```text
GET  /api/assessments/metric-definitions/
POST /api/assessments/{id}/complete/
```

`complete` 接口职责：

1. 检查权限和客户归属。
2. 运行首次评估或复评的完整校验。
3. 将 `status` 更新为 `completed` 并写入 `completed_at`。
4. 写入审计日志。
5. 返回完整评估。

### 8.3 错误返回

除现有统一信封外，业务错误应提供稳定错误码，至少包括：

- `initial_assessment_exists`。
- `assessment_incomplete`。
- `metric_value_out_of_range`。
- `metric_required_field_missing`。
- `plan_customer_mismatch`。

前端不能靠解析中文错误文本决定跳转逻辑。

## 9. 前端组件拆分

避免继续扩大 `AssessmentEditView.vue`，建议拆分为：

```text
src/views/assessment/AssessmentEditView.vue
src/components/assessment/AssessmentStepper.vue
src/components/assessment/AssessmentProblemStep.vue
src/components/assessment/AssessmentSubjectiveStep.vue
src/components/assessment/AssessmentMetricsStep.vue
src/components/assessment/AssessmentGoalStep.vue
src/components/assessment/AssessmentReviewStep.vue
src/components/assessment/MetricTypePicker.vue
src/components/assessment/metrics/PainMetricEditor.vue
src/components/assessment/metrics/StrengthMetricEditor.vue
src/components/assessment/metrics/RomMetricEditor.vue
src/components/assessment/metrics/SpecialTestMetricEditor.vue
src/components/assessment/metrics/FunctionalMetricEditor.vue
```

状态管理建议：

- 页面级 `reactive` 表单作为唯一编辑状态。
- 子组件通过 `v-model` 或明确事件更新对应分区。
- 不在每个子组件重复请求评估定义。
- 切换步骤前只校验当前步骤；完成时由前后端再次进行全量校验。
- 离开存在未保存修改的页面前给予提醒。

## 10. AI 与趋势服务调整

### 10.1 AI 数据使用边界

- AI 上下文和趋势分析只读取 `status=completed` 的评估。
- 草稿不进入长期记忆，不作为阶段进展依据。
- AI 生成的评估内容必须以“建议填入”的形式呈现，康复师确认后才能保存。
- AI 不自动完成评估、不自动修改康复阶段、不自动创建康复计划。

### 10.2 趋势匹配

修改 `apps/ai/services/progress.py`：

- 不再只取同类型第一条指标。
- 构造稳定匹配键：`metric_type + body_part + side + movement + context + measurement_mode + scale_code`。
- 只比较匹配键一致、单位一致、量表一致的数值。
- 疼痛按 `lower_is_better` 解释。
- 肌力按 `higher_is_better` 解释。
- ROM 只描述角度增减；是否代表改善需结合目标和动作，不能仅凭数值增大断言。
- 分类结果展示变化，不做未经确认的医学结论。

## 11. 分阶段执行任务

### 阶段 A：模型和规则基础

- [x] 新增评估状态及主观结构化字段。
- [x] 新增指标侧别、单位、场景、动作、测量方式、分类结果和扩展字段。
- [x] 建立 `metric_definitions.py`。
- [x] 编写数据迁移和数据库参考 SQL。
- [x] 增加服务端类型专用校验。
- [x] 增加首次评估重复保护及迁移策略。

完成条件：后端可以安全保存草稿与五种类型指标，客户端无法自行决定满分。

### 阶段 B：API 与测试

- [x] 更新 Serializer，`score_max` 只读或服务端派生。
- [x] 增加指标定义接口。
- [x] 增加完成评估接口。
- [x] 增加稳定业务错误码。
- [x] 补充权限、范围、必填、重复首评、草稿完成和计划归属测试。
- [x] 更新 API 文档。

完成条件：API 测试覆盖各指标的合法和非法输入。

### 阶段 C：引导式前端

- [x] 将评估页拆为五个步骤。
- [x] 建立五种指标专用编辑器。
- [x] 页面移除可编辑的“满分”。
- [x] 增加字段示例、“暂不清楚”和完成状态。
- [x] 增加“下一步”自动保存草稿、检查摘要和完成评估。
- [x] 增加离开未保存页面提醒。
- [x] 落实移动端单列、全宽、44px 点击区域和固定步骤操作栏。
- [x] 修正评估编辑路由与编辑保存后的客户详情返回逻辑。
- [x] 新建页缺少或包含非法 `customerId` 时阻止提交并给出明确提示。

完成条件：不了解评分模型的康复师能够只按页面提示完成首次评估。

### 阶段 D：入口与复评

- [x] 客户详情按“已完成首次评估”判断是否提示。
- [x] 存在草稿时改为“继续评估”。
- [x] 快捷入口携带首次评估意图，并在选中客户后直接进入或继续首评。
- [x] 复评支持从最近已完成评估选择可比项目。
- [x] 客户详情明确区分草稿、已完成首次评估和复评。

完成条件：不会重复创建首次评估，草稿可以可靠恢复。

### 阶段 E：趋势、AI 和文档收尾

- [x] 重写指标趋势匹配逻辑。
- [x] 排除草稿评估。
- [x] 更新 AI 输入与趋势规则；当前采用确定性比较逻辑，无需新增生成式提示词，并保持康复师确认机制。
- [x] 更新项目设计文档、数据库文档和架构说明。
- [x] 执行全量后端测试与前端生产构建。

完成条件：历史趋势不再比较不同部位、不同侧别或不同量表的数据。

## 12. 数据迁移与兼容顺序

必须采用先扩展、后切换、再清理的顺序：

1. 新增可空字段，不删除旧字段。
2. 为旧数据补齐可确定的规则：疼痛 `NRS_0_10`、肌力 `MRC_0_5`；无法可靠推断的字段保持空值。
3. 后端同时兼容旧请求和新请求，但所有新写入由服务端重算 `score_max`。
4. 发布新前端，停止提交手工满分。
5. 确认没有旧客户端后，将 `score_max` 输入改为严格只读。
6. 在后续独立迁移中评估是否重命名 `score` 为更通用的 `numeric_value`；本轮不做破坏性删除。

不得根据 `body_part` 自由文本猜测侧别、动作或 ROM 测量方式。

## 13. 测试清单

### 13.1 后端

- 疼痛只接受 0～10 整数，满分始终由系统设为 10。
- 肌力只接受 0～5 整数，满分始终由系统设为 5。
- ROM 保存角度和单位，不保存满分。
- 特殊测试和功能观察保存分类结果，不要求数字。
- 草稿允许缺少完成必填项。
- 未完成评估不能调用完成接口成功。
- 同一客户不能创建第二份首次评估。
- 其他康复师不能读取、修改或完成评估。
- 不允许关联其他客户或其他康复师的康复计划。
- 评估完成与更新均写入审计。
- 趋势服务只比较匹配键和量表一致的数据。

### 13.2 前端

- 首次评估入口锁定类型和客户。
- 存在草稿时能够继续编辑。
- 五种指标显示各自控件，没有手工满分输入框。
- 切换步骤保留已填数据。
- 通过“下一步”自动保存后刷新可以恢复。
- 完成前显示摘要和缺失项。
- 375px、390px、768px 宽度下无横向溢出。
- 移动端一个主要字段占满一行，软键盘弹起后仍可操作。
- 桌面端保持合理最大宽度，不把表单拉伸到整屏。

### 13.3 建议执行命令

```powershell
cd retrue-server
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test apps.assessments apps.ai --keepdb

cd ..\retrue-web
npm run build
```

模型发生变化时，先生成并检查 migration，再执行实际 `migrate`；同时更新 `docs/database/assessments.sql`。

## 14. 验收标准

改造完成需同时满足：

1. 页面不再要求康复师填写任何指标满分。
2. 疼痛、肌力、ROM、特殊测试和功能动作拥有类型专用输入体验。
3. 新手能够仅依靠页面问题、示例和选项完成首评。
4. 首次评估可保存草稿、继续填写、检查并完成。
5. 同一客户不会生成多份首次评估。
6. 移动端核心字段均采用单列全宽布局，无横向挤压。
7. 服务端独立执行所有范围、单位、量表和权限校验。
8. AI 和趋势服务只消费已完成、可比较的数据。
9. 旧评估可以继续读取和编辑，历史数据没有被静默丢弃。
10. 后端测试、Django 检查和前端生产构建全部通过。

## 15. 本轮明确不做

- 不自动诊断客户病情。
- 不由 AI 自动确认评估结果。
- 不在完成首次评估时自动创建康复计划。
- 不一次性接入所有疾病专用功能量表。
- 不删除历史 `score` / `score_max` 字段。
- 不根据自由文本自动改写历史侧别、动作和测量方式。

后续正式量表、身体部位字典、关节正常参考范围和肩/腰/膝/踝评估模板，应在本方案完成后作为独立迭代实施。

## 16. 实施记录

实施日期：2026-08-31。

- 已完成后端模型、迁移、服务端指标定义与校验、完成评估接口、权限与审计逻辑。
- 已完成五步引导式评估页、五类专用指标编辑器、草稿恢复、复评模板导入及移动端单列全宽适配。
- 已完成首次评估入口、草稿继续、计划关联限制以及仅使用已完成评估的趋势分析。
- 后端全量测试共 179 项通过；评估与 AI 定向测试共 50 项通过；`manage.py check` 与 `makemigrations --check --dry-run` 通过。
- 前端生产构建通过；375px 移动端实测无横向溢出，康复师页面不再出现可编辑“满分”。
- `assessments.0006_guided_assessment` 已在临时 SQLite 验证库完整执行。当前开发 PostgreSQL 由 Docker 提供，但 Docker 服务未启动，因此尚未对开发 PostgreSQL 执行实际 `migrate`；启动 Docker Desktop 后执行第 13.3 节中的迁移命令即可。
