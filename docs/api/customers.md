# 客户接口（customers）

所有接口返回统一信封结构 `{code, message, data}`。客户数据强制按当前康复师隔离。

## 客户别称维护

`GET /api/customers/{id}/aliases/` 返回全部别称（包括停用项）：`[{id, alias, normalized_alias, is_active, created_at}]`。

`POST /api/customers/{id}/aliases/` 接收 `{ "alias": "测试小成", "is_active": true }`。

`PUT /api/customers/{id}/aliases/{alias_id}/` 接收 `alias`、`is_active` 的部分更新；停用使用 `{ "is_active": false }`。不提供物理删除。

匹配键由服务器复用目录规则归一化。空白/纯称谓、同账号归一化重复、与其他客户正式名冲突返回 `400`。停用项保留唯一键以便重新启用和追溯，并从目录匹配排除。客户端不能改绑客户或康复师；其他账号客户或不属于该客户的别称返回 `404`。增改、停用与审计同事务。

## 客户资料导出

`GET /api/customers/{id}/export/?output=json`（默认）或 `output=report`。

`data` 返回 `{filename, content_type, content, audit_id}`；`content` 为结构化 JSON 对象或中文纯文本报告，前端下载时按 `content_type` 创建文件。仍使用统一信封。响应禁止缓存。

包含客户档案、评估/指标、康复计划/阶段/计划课程/调整、排课、课时包/流水、训练/明细、家庭训练/动作、回访、风险提示和客户长期记忆。JSON 中业务关联 ID 用于核对；日期为 ISO 格式，课时和评分等小数以字符串保留精度。

默认删除完整 `phone` 字段，并脱敏自由文本中的手机号。第一批不导出 AI 原始输入、未确认草稿、会话原文/摘要、执行状态、向量或密钥，避免多客户会话污染交付资料。`include_sensitive=true` 返回 `400`，完整信息导出权限尚未开放。超过一万条业务记录返回 `400`，不生成静默截断文件。

导出访问用 `export` 审计动作记录格式、脱敏标记和记录数；不会在审计日志复制健康资料。其他账号或不存在客户统一 `404`。

## 只读删除影响预览

`GET /api/customers/{id}/deletion-preview/` 返回：

```json
{
  "customer_id": 1,
  "resources": [{"key": "training_records", "label": "训练记录", "count": 3}],
  "can_delete": false,
  "execution_enabled": false,
  "policy_status": "待确认授权角色、保留期限、恢复期、审计与备份处理策略",
  "external_boundaries": ["备份、已下载导出文件与第三方模型记录无法由本预览统计或清除"],
  "derived_content": ["长期记忆向量", "讨论事件摘要", "会话滚动摘要", "助手状态与外部持久化检查点"]
}
```

资源清单另包含客户别称、记忆候选/事件、绑定会话/消息、AI 草稿、助手任务/运行/工具/事件、训练批量子项及本账号客户资源审计。计数基于明确归属链，未绑定/多客户共享会话不会按姓名猜测归属。

接口没有写入或审计副作用，且无 DELETE 执行入口。恢复期、软删、清除与备份处理须待 D3 决策确认；见 [生命周期交付设计](../plans/2026-10-03-customer-data-lifecycle.md)。

## 客户列表

`GET /api/customers/`

权限：已登录康复师

查询参数：
- `keyword`（可选）：按姓名模糊搜索。
- `status`（可选）：`active`/`paused`/`closed`。
- `page`（可选）：页码，默认 1。
- `page_size`（可选）：每页条数，默认 20，最大 100。

成功响应（**手机号已脱敏，返回 `phone_masked`**）：

```json
{
  "code": 200,
  "message": "查询成功",
  "data": {
    "items": [
      {
        "id": 1,
        "name": "张三",
        "phone_masked": "138****1234",
        "gender": "male",
        "gender_display": "男",
        "main_issue": "左膝疼痛",
        "status": "active",
        "status_display": "正常",
        "first_visit_date": "2026-08-01",
        "created_at": "2026-08-26T10:00:00+08:00",
        "updated_at": "2026-08-26T10:00:00+08:00"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
}
```

错误：`401` 未登录。

## 创建客户

`POST /api/customers/`

权限：已登录康复师

请求体：

```json
{
  "name": "张三",
  "phone": "13800138000",
  "gender": "male",
  "main_issue": "左膝疼痛"
}
```

成功响应：返回客户详情（含完整 `phone`）。

错误：`400` 参数错误；`401` 未登录。

## 客户详情

`GET /api/customers/{id}/`

权限：已登录康复师（仅限本人客户）

成功响应：返回客户详情，**含完整手机号 `phone`（受控编辑场景）**。

错误：`401` 未登录；`404` 客户不存在或无权访问。

## 更新客户

`PUT /api/customers/{id}/`

权限：已登录康复师（仅限本人客户）

请求体：可部分更新，字段同创建。

成功响应：返回更新后的客户详情。

错误：`400` 参数错误；`401` 未登录；`404` 客户不存在或无权访问。
