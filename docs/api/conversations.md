# AI 统一会话接口

会话始终归属当前登录康复师；`customer` 可为空。绑定客户时，后端校验客户必须属于当前康复师。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/conversations/?customer={id}` | 查询当前康复师最近会话 |
| POST | `/api/conversations/` | 创建会话并记录入口、类型和关联资源 |
| GET | `/api/conversations/{id}/` | 获取会话及完整消息 |
| POST | `/api/conversations/{id}/messages/` | 保存用户消息、生成并保存回复、执行记忆评估 |
| POST | `/api/conversations/{id}/episodes/extract/` | 主动提取待确认 Episode |

创建示例：

```json
{
  "customer": 35,
  "origin": "customer_detail",
  "conversation_type": "customer_discussion",
  "context_resource_type": "customer",
  "context_resource_id": "35"
}
```

发送消息返回本轮的 `user_message`、`assistant_message` 与 `memory_candidates`。记忆评估失败不会影响正常对话归档和回答。

每段会话的模型上下文最多携带最近 10 条原始消息。第 11 条开始，退出窗口的消息会增量合并到 `summary`；后续上下文使用 `summary + 最近 10 条消息`。完整原始消息仍保存在 `tb_ai_messages`，摘要不会删除或覆盖原文。

每累计 10 条新压缩消息，系统自动评估一次 Episode；也可调用提取接口主动评估。提取结果始终为候选，不能直接进入 AI 上下文。
