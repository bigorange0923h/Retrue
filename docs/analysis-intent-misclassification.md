# 意图识别误判分析报告：咨询被识别成“训练补记”

> 现象：用户输入 `黄伟成做了几次训练了`，意图识别为 `training_record`（训练补记），
> 而不是咨询/历史查询（如 customer_question）。由于是补记意图，编排把“问句”当
> “补记陈述”去调模型生成训练草稿，最终接口 500。
>
> 本文档为纯分析报告，未改代码，供进一步讨论修复方案。

## 1. 判定的输入

```
黄伟成做了几次训练了
```

- 未绑定客户（新一轮，customer_id 为空，即 `customer_bound=False`）
- 语义：询问“黄伟成总共做过几次训练”（咨询 / 历史统计）
- 非语义：并非在陈述“今天补记：黄伟成做了 3 组 12 次深蹲”

## 2. 分类入口与关键常量（`retrue-server/apps/ai/orchestration/intent.py`）

### 2.1 训练补记触发词 `_TRAINING_KEYWORDS`（约 42-53 行）
```python
_TRAINING_KEYWORDS = (
    "补记", "训练记录", "今天训练", "昨天训练",
    "做了",   # ← “黄伟成做了几次训练了”命中
    "组",
    "次",     # ← 单字，任何含“次”的句子都会命中
    "训练量", "练了", "康复训练",
)
```

### 2.2 客户咨询/历史触发词 `_CUSTOMER_QUESTION_KEYWORDS`（约 56-66 行）
```python
_CUSTOMER_QUESTION_KEYWORDS = (
    "最近", "历史", "进展", "上次", "进度",
    "恢复情况", "评估", "课程", "计划",
)
```
注意：其中**没有**“几次/多少次/次数”这类“询问频次”的词，也没有疑问语气词。

### 2.3 分类主流程 `classify_intent` 的分支顺序（约 176-237 行，已精简）
```python
1  if 含 _RISK_KEYWORDS:                     → risk_review
2  elif _is_multi_customer(...):              → multi_customer_training_record
3  elif 未绑定 且 (customer_name 或 称谓词):   → customer_lookup
4  elif 含 _ASSESSMENT_KEYWORDS:              → assessment
5  elif 含 _TRAINING_REVISION_KEYWORDS:        → training_revision
6  elif 含 _FOLLOWUP_KEYWORDS:                 → followup
7  elif 含 _TRAINING_KEYWORDS:                 → training_record   # ← 本例落这里
8  elif 已绑定 且 含 _CUSTOMER_QUESTION_KEYWORDS: → customer_question
9  else:                                       → general_knowledge / 模型补充
```

## 3. 为什么落到了 training_record

对输入 `黄伟成做了几次训练了`，逐条匹配：

1. `_RISK_KEYWORDS`：不命中（无风险/禁忌词）→ 跳过
2. `_is_multi_customer`：只有一位客户，返回 False → 跳过
3. `customer_lookup` 分支：要求 `customer_bound=False` 且含“客户/病人/患者”称谓
   （`_NAME_LOOKUP_KEYWORDS`）或显式 `customer_name`。本例既无称谓词、
   也没传 customer_name → 不进入 → 跳过
4. `_ASSESSMENT_KEYWORDS`：无“评估/首评/复评”→ 跳过
5. `_TRAINING_REVISION_KEYWORDS`：无“修改/修订训练”→ 跳过
6. `_FOLLOWUP_KEYWORDS`：无“随访/回访”→ 跳过
7. `_TRAINING_KEYWORDS`：
   - “做了” → 命中
   - “次”   → 命中（“做了几次训练了”里含“次”）
   → 进入分支 7，意图 = `training_record`  ❌
8. `customer_question` 分支：在分支 7 之后，永远轮不到；
   且它还要求 `customer_bound=True`，本例未绑定也不满足。

## 4. 根因归纳

1. **触发词过宽 / 有“次”这种单字**
   `_TRAINING_KEYWORDS` 含“次”“做了”，这些词在**问句**（做了几次 / 多少次）
   和**补记陈述**（做了 3 组 12 次）里都会出现，无法仅靠它们区分“补记”与“咨询”。

2. **没有疑问语气 / 咨询语义识别**
   分类器没有识别“几次 / 多少次 / 怎么样 / 如何 / 多少 / ？ / 吗”等疑问信号的逻辑。
   “做了几次训练了”是问句，却被当作陈述“做了训练”处理。

3. **分支顺序：补记优先于咨询**
   `training_record` 在 `customer_question` 之前判定；且 `customer_question`
   又要求 `customer_bound=True`。未绑定客户的问句，在无称谓词时既进不了
   `customer_lookup`，又会被 `training_record` 提前截走。

4. **customer_lookup 分支的进入条件偏窄**
   只认“客户/病人/患者”称谓或显式姓名参数，不认“裸姓名 + 询问训练频次”这类
   自然问句（这里“黄伟成做了几次训练了”实际应触发“先定位黄伟成，再查其训练次数”）。

## 5. 影响

- 问句进了补记流程 → 调模型按“补记”解析文本 → 模型对非补记文本返回的
  `TrainingDraft` 缺字段（training_date / customer_feedback 等为 None）→
  Pydantic 校验失败 → 编排层抛异常 → 接口 500。

## 6. 可能的修复方向（供讨论，未实施）

- A. 新增“咨询/问句优先拦截”：判定 `training_record` 前，先识别疑问语气
  （`几次 / 多少次 / 多少次 / 怎么样 / 如何 / 多少 / ？ / 吗`），命中则归到
  咨询类意图（customer_question / customer_lookup / general_knowledge），
  而不进入补记。
- B. 收窄 `_TRAINING_KEYWORDS`：移除会被问句误伤的短词（`次`、`做了`），
  改依赖更强的“补记”信号（补记 / 记录一下 / 训练记录 + 明确“动作+组×次”陈述）。
- C. 调整分支顺序与咨询分支前提：把“客户相关咨询”的判定提前，并放开其
  `customer_bound` 前提（未绑定也应允许“先定位客户再回答”）。
- D. 在分类后增加“写类意图才生成草稿”的兜底校验：若 training_record 解析出的
  训练内容为空（无动作），回落为咨询而不是继续生成补记。

> 备注：本报告仅陈述当前代码行为，未做任何代码改动。
