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

只有 `status=active` 且 `is_active=true` 的条目会被注入 AI 上下文；删除和停用均保留审计与来源追溯。

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
