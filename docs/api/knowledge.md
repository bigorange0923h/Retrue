# 客户长期记忆接口

所有接口均要求登录，并按当前康复师与客户隔离。响应统一为 `{ code, message, data }`。

## 记忆条目

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/knowledge/items/?customer={id}` | 查询客户记忆（含历史状态） |
| POST | `/api/knowledge/items/` | 手动新增已确认的 active 记忆 |
| PUT | `/api/knowledge/items/{id}/` | 修改内容、分类、重要度或启用状态 |
| POST | `/api/knowledge/items/{id}/expire/` | 停用，状态改为 `expired` |
| DELETE | `/api/knowledge/items/{id}/` | 软删除，状态改为 `deleted` |

记忆条目新增字段：`memory_type`、`memory_key`、`normalized_value`、`confidence`、`importance_score`、`status`、`effective_from`、`effective_to`、`last_confirmed_at`、`source_type`、`source_id`、`source_message_id` 与 `supersedes_memory`。

只有 `status=active`、`is_active=true` 且处于 `effective_from`/`effective_to` 有效期内的条目会被注入 AI 上下文（知识检索、备课与长期记忆评估使用同一生命周期语义）；删除和停用均保留审计与来源追溯。

## 候选确认

`POST /api/knowledge/candidates/{id}/decide/` 支持 `confirm`、`reject`、`replace`、`keep_existing`、`coexist` 和 `defer`：

```json
{
  "action": "replace",
  "memory_type": "preference",
  "importance_score": 3,
  "supersede_existing": true
}
```

确认时服务端按 `therapist_id + customer_id + memory_key + normalized_value` 去重。`replace` 会将同键旧 active 记忆置为 `superseded`；`keep_existing` 忽略新候选；`coexist` 为不同适用条件保留独立 key；`defer` 保留在 open 列表供稍后处理。AI 不能自行覆盖有效记忆。

候选返回 `source_conversation`、`source_message`、`conflict_memory`、`conflict_memory_content` 和 `conflict_type`，界面应同时展示旧信息、新信息及来源。

## Memory Episode

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/knowledge/episodes/?customer={id}` | 查询客户历史讨论事件 |
| POST | `/api/knowledge/episodes/{id}/decide/` | `confirm` 或 `reject` 候选 |
| DELETE | `/api/knowledge/episodes/{id}/` | 将事件标记为 deleted |

Episode 保存主题、摘要、关键点、讨论决定、下一步行动和来源消息范围。只有康复师确认后的 `active` Episode 会进入客户 AI 上下文，默认最多 3 条。

## RAG 问答

`POST /api/knowledge/rag/`，请求体 `{ "customer": 1, "question": "这个客户能深蹲吗？" }`。

检索只返回有效生命周期内的条目：`safety` 分类或 `high` 重要度的安全限制会先独立召回（最多 8 条），再按语义相似度（有 embedding）或最近条目（无 embedding）补充普通知识，最终返回不超过 `top_k`（默认 5）条。安全限制不会被相似度 top-k 或最近 top-k 排除。

响应：

```json
{
  "code": 200,
  "message": "RAG 回答生成成功",
  "data": {
    "answer": "……",
    "used_knowledge": [
      { "content": "左膝 ACL 重建术后禁止深蹲", "category": "safety", "importance": "high", "similarity": null, "matched": "keyword" }
    ],
    "using_customer_context": true,
    "retrieval_mode": "keyword"
  }
}
```

- `retrieval_mode`：`vector`=语义检索；`keyword`=embedding 不可用时的有限关键词/最近条目匹配（界面应如实提示，不伪装成语义检索）；`no_result`=无片段。
- `used_knowledge[]` 每项的 `matched` 标注该项检索方式。
- 提示词把知识片段声明为「受控康复知识库」的不可信数据，禁止把片段中的指令当作系统指令。

错误：`400` 缺少 customer/question；`404` 客户不存在或无权访问。

## 知识索引重建

`POST /api/knowledge/index/`，请求体 `{ "customer": 1 }`。

为当前客户的 `memory_type=other`（自由文本/历史资料）且尚未向量化的生效条目生成向量。内容被编辑、停用或删除时服务端会清空该条目的 embedding，重建后才按新内容向量化，避免命中旧向量。

响应：`{ "indexed": 3, "pending": 2, "embedding_available": true }`。`embedding_available=false` 时检索将退化为 `keyword` 模式，应提示用户先配置 embedding 或接受有限检索。

错误：`400` 缺少 customer；`404` 客户不存在或无权访问。
