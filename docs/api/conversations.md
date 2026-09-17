# AI 统一会话接口

会话始终归属当前登录康复师；`customer` 可为空。绑定客户时，后端校验客户必须属于当前康复师。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/conversations/` | 创建会话并记录入口、类型和关联资源 |
| GET | `/api/conversations/{id}/` | 获取会话及完整消息 |

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

会话消息由统一智能助理的受控任务接口写入，详见 [助理任务接口](assistant_tasks.md)。Conversation 只负责保存可追溯的消息与最小会话上下文，不提供另一套直接调用模型的消息接口。
