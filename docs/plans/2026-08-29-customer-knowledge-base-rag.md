# 阶段 B：客户私有康复知识库 + RAG（pgvector + Qwen embedding）实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现客户私有知识库（知识条目 + AI 候选确认 + 向量检索 RAG），按客户严格隔离。

**Architecture:** 新增 `CustomerKnowledgeItem`（正式知识，含 pgvector 向量字段）与 `KnowledgeCandidate`（AI 建议候选，确认后转正）。知识向量化用 Qwen embedding，检索用 pgvector 余弦相似度；RAG 回答拼入知识片段并调用聊天模型。所有知识按 therapist_id + customer_id 隔离。

---

## Task 1: 模型层（知识条目 + 候选 + 向量）

**Files:**
- Create: `retrue-server/apps/knowledge/models.py`
- Create: `retrue-server/apps/knowledge/apps.py`
- Modify: `retrue-server/config/settings.py`（注册 knowledge app）

**Step 1:** 创建 knowledge app 骨架（apps.py、__init__.py、models.py）。

**Step 2:** `CustomerKnowledgeItem` 模型：
- therapist(FK User), customer(FK Customer)
- category（诊断/安全限制/康复过程/个体化偏好）
- content(Text)
- source（manual/ai_confirmed/training/assessment/conversation）
- importance（high/normal；风险置顶）
- is_active
- embedding(VectorField(1024), null=True)
- created_by/updated_by, created_at/updated_at

**Step 3:** `KnowledgeCandidate` 模型：
- therapist, customer, content, source_ref, suggested_at, status(pending/confirmed/rejected)
- 关联知识条目（确认后）

**Step 4:** settings INSTALLED_APPS 注册 knowledge。

**Step 5:** makemigrations（含 VectorExtension）+ migrate + check。

**Step 6:** Commit

---

## Task 2: 知识条目接口（CRUD + 候选确认）

**Files:**
- Create: `retrue-server/apps/knowledge/serializers.py`
- Create: `retrue-server/apps/knowledge/views.py`
- Create: `retrue-server/apps/knowledge/urls.py`

**Step 1:** 知识条目序列化器（含分类/来源/重要级别）。

**Step 2:** 视图：KnowledgeListView/DetailView（CRUD，数据隔离，停用保留），候选列表/确认/拒绝。

**Step 3:** 写审计日志（正式知识的增删改必须记录）。

**Step 4:** urls 挂载（/api/knowledge/...）。

**Step 5:** 测试 + check + commit

---

## Task 3: 向量化 + RAG 检索服务

**Files:**
- Create: `retrue-server/apps/knowledge/services.py`

**Step 1:** `embed_texts(texts)` — 调 Qwen embedding，缓存维度。

**Step 2:** `build_knowledge_index(customer_id)` — 将激活知识条目向量化并存入 embedding 字段。

**Step 3:** `search_knowledge(customer_id, query, top_k)` — 余弦相似度检索，风险条目优先。

**Step 4:** 单测（mock embedding 层，避免真实 API 调用）。

**Step 5:** check + commit

---

## Task 4: RAG 回答接口

**Files:**
- Modify: `retrue-server/apps/knowledge/views.py` / `services.py`
- Modify: `retrue-server/apps/ai/providers/factory.py`（复用聊天 provider）

**Step 1:** `rag_answer(customer, question)` — 检索知识 → 渲染 `rag_system` prompt → 调聊天模型返回。

**Step 2:** 接口 `/api/knowledge/rag/`（客户模式）。

**Step 3:** 测试（mock chat provider）。

**Step 4:** check + commit

---

### 验证检查表
- [ ] migration 含 VectorExtension + 向量字段成功
- [ ] 知识条目 CRUD + 候选确认测试通过
- [ ] 向量化 + 检索测试通过（mock embedding）
- [ ] RAG 回答测试通过（mock chat）
- [ ] 全量测试通过
