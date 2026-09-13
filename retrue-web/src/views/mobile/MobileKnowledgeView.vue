<script setup lang="ts">
/** 移动端客户知识库页：选择客户后管理知识条目、确认 AI 候选并进行 RAG 问答。 */

import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import {
  apiBuildKnowledgeIndex,
  apiCreateKnowledgeItem,
  apiDecideMemoryEpisode,
  apiDecideKnowledgeCandidate,
  apiDeleteMemoryEpisode,
  apiDeleteKnowledgeItem,
  apiListKnowledgeCandidates,
  apiListKnowledgeItems,
  apiListMemoryEpisodes,
  apiRagAnswer,
  apiUpdateKnowledgeItem,
} from '@/api/knowledge'
import { apiListCustomers } from '@/api/customers'
import type { CustomerListItem, KnowledgeCategory, KnowledgeCandidate, KnowledgeItem, MemoryEpisode } from '@/types/api'

const customerId = ref<number | null>(null)
const customers = ref<CustomerListItem[]>([])

const items = ref<KnowledgeItem[]>([])
const candidates = ref<KnowledgeCandidate[]>([])
const episodes = ref<MemoryEpisode[]>([])
const itemsLoading = ref(false)
const candidatesLoading = ref(false)
const episodesLoading = ref(false)
const activeTab = ref<'knowledge' | 'candidates' | 'episodes' | 'qa'>('knowledge')

const categoryOptions: Array<{ value: KnowledgeCategory; label: string }> = [
  { value: 'medical', label: '医疗与康复背景' },
  { value: 'safety', label: '安全限制' },
  { value: 'recovery', label: '康复过程' },
  { value: 'preference', label: '个体化偏好' },
  { value: 'other', label: '其他' },
]

const hasSelected = computed(() => customerId.value !== null)

function categoryTag(category: KnowledgeCategory) {
  const map: Record<string, string> = {
    safety: 'danger',
    medical: 'warning',
    recovery: 'success',
    preference: 'info',
    other: 'info',
  }
  return map[category] || 'info'
}

async function loadCustomers(): Promise<void> {
  customers.value = (await apiListCustomers({ page: 1, page_size: 200 })).items
}

async function handleCustomerChange(): Promise<void> {
  if (customerId.value === null) {
    items.value = []
    candidates.value = []
    episodes.value = []
    return
  }
  await Promise.all([loadItems(), loadCandidates(), loadEpisodes()])
}

async function loadItems(): Promise<void> {
  if (customerId.value === null) return
  itemsLoading.value = true
  try {
    items.value = await apiListKnowledgeItems(customerId.value)
  } finally {
    itemsLoading.value = false
  }
}

async function loadCandidates(): Promise<void> {
  if (customerId.value === null) return
  candidatesLoading.value = true
  try {
    candidates.value = await apiListKnowledgeCandidates(customerId.value, 'open')
  } finally {
    candidatesLoading.value = false
  }
}

async function loadEpisodes(): Promise<void> {
  if (customerId.value === null) return
  episodesLoading.value = true
  try {
    episodes.value = await apiListMemoryEpisodes(customerId.value)
  } finally {
    episodesLoading.value = false
  }
}

// 新增/编辑知识条目
const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  content: '',
  category: 'other' as KnowledgeCategory,
  importance: 'normal' as 'high' | 'normal',
})

const rules: FormRules = {
  content: [{ required: true, message: '请输入知识内容', trigger: 'blur' }],
}

function openCreate(): void {
  editingId.value = null
  form.content = ''
  form.category = 'other'
  form.importance = 'normal'
  dialogVisible.value = true
}

function openEdit(item: KnowledgeItem): void {
  editingId.value = item.id
  form.content = item.content
  form.category = item.category
  form.importance = item.importance
  dialogVisible.value = true
}

async function handleSaveItem(): Promise<void> {
  if (!formRef.value || customerId.value === null) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const payload = { customer: customerId.value, ...form }
    if (editingId.value) {
      await apiUpdateKnowledgeItem(editingId.value, payload)
      ElMessage.success('知识条目已更新')
    } else {
      await apiCreateKnowledgeItem(payload)
      ElMessage.success('知识条目已添加')
    }
    dialogVisible.value = false
    await loadItems()
  } finally {
    saving.value = false
  }
}

async function toggleActive(item: KnowledgeItem): Promise<void> {
  await apiUpdateKnowledgeItem(item.id, { is_active: !item.is_active })
  ElMessage.success(item.is_active ? '已停用' : '已启用')
  await loadItems()
}

async function removeItem(item: KnowledgeItem): Promise<void> {
  await apiDeleteKnowledgeItem(item.id)
  ElMessage.success('知识条目已删除')
  await loadItems()
}

// 候选确认/拒绝
async function confirmCandidate(c: KnowledgeCandidate): Promise<void> {
  await apiDecideKnowledgeCandidate(c.id, 'confirm', { category: c.category, importance: 'normal' })
  ElMessage.success('已确认并转为正式知识')
  await Promise.all([loadCandidates(), loadItems()])
}

async function rejectCandidate(c: KnowledgeCandidate): Promise<void> {
  await apiDecideKnowledgeCandidate(c.id, 'reject')
  ElMessage.success('候选已拒绝')
  await loadCandidates()
}

async function resolveConflict(
  c: KnowledgeCandidate,
  action: 'replace' | 'keep_existing' | 'coexist' | 'defer',
): Promise<void> {
  await apiDecideKnowledgeCandidate(c.id, action)
  const messages = {
    replace: '已用新记忆替代旧记忆',
    keep_existing: '已保留旧记忆',
    coexist: '已按不同条件保留',
    defer: '已暂缓处理',
  }
  ElMessage.success(messages[action])
  await Promise.all([loadCandidates(), loadItems()])
}

async function decideEpisode(episode: MemoryEpisode, action: 'confirm' | 'reject'): Promise<void> {
  await apiDecideMemoryEpisode(episode.id, action)
  ElMessage.success(action === 'confirm' ? '历史事件已确认' : '历史事件已拒绝')
  await loadEpisodes()
}

async function removeEpisode(episode: MemoryEpisode): Promise<void> {
  await apiDeleteMemoryEpisode(episode.id)
  ElMessage.success('历史事件已删除')
  await loadEpisodes()
}

// 索引重建
const indexing = ref(false)
async function rebuildIndex(): Promise<void> {
  if (customerId.value === null) return
  indexing.value = true
  try {
    const res = await apiBuildKnowledgeIndex(customerId.value)
    if (res.embedding_available) {
      ElMessage.success(`知识向量索引已更新（成功 ${res.indexed} 条${res.pending ? `，待处理 ${res.pending} 条` : ''}）`)
    } else {
      ElMessage.warning('embedding 服务不可用，索引未生成，问答将按有限关键词匹配')
    }
  } finally {
    indexing.value = false
  }
}

// RAG 问答
const question = ref('')
const answering = ref(false)
const answer = ref('')
const usedKnowledge = ref<KnowledgeItem[]>([])
const retrievalMode = ref<'safety' | 'vector' | 'keyword' | 'no_result'>('no_result')
async function askRag(): Promise<void> {
  if (customerId.value === null || !question.value.trim()) {
    ElMessage.warning('请输入问题')
    return
  }
  answering.value = true
  answer.value = ''
  usedKnowledge.value = []
  retrievalMode.value = 'no_result'
  try {
    const res = await apiRagAnswer(customerId.value, question.value.trim())
    answer.value = res.answer
    usedKnowledge.value = res.used_knowledge
    retrievalMode.value = res.retrieval_mode
  } finally {
    answering.value = false
  }
}

onMounted(loadCustomers)
</script>

<template>
  <div class="mobile-knowledge">
    <div class="customer-select">
      <el-select v-model="customerId" placeholder="选择客户" filterable class="customer-picker" @change="handleCustomerChange">
        <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-button :disabled="!hasSelected" :loading="indexing" @click="rebuildIndex">重建索引</el-button>
    </div>

    <template v-if="hasSelected">
      <el-tabs v-model="activeTab" class="know-tabs">
        <el-tab-pane label="知识条目" name="knowledge" />
        <el-tab-pane label="AI 候选" name="candidates" />
        <el-tab-pane label="历史事件" name="episodes" />
        <el-tab-pane label="AI 问答" name="qa" />
      </el-tabs>

      <!-- 知识条目 -->
      <div v-show="activeTab === 'knowledge'" class="tab-panel">
        <div class="panel-head">
          <span>知识条目（{{ items.length }}）</span>
          <el-button type="primary" size="small" @click="openCreate">新增</el-button>
        </div>
        <div v-loading="itemsLoading" class="item-list">
          <el-empty v-if="items.length === 0 && !itemsLoading" description="暂无知识条目" />
          <el-card v-for="item in items" :key="item.id" shadow="never" class="knowledge-card">
            <div class="knowledge-card-head">
              <el-tag :type="categoryTag(item.category)" size="small">{{ item.category_display }}</el-tag>
              <el-tag v-if="item.importance === 'high'" type="danger" size="small">高</el-tag>
              <el-tag :type="item.is_active ? 'success' : 'info'" size="small">{{ item.is_active ? '生效' : '停用' }}</el-tag>
            </div>
            <p class="knowledge-content">{{ item.content }}</p>
            <div class="knowledge-actions">
              <el-button size="small" @click="openEdit(item)">编辑</el-button>
              <el-button size="small" :type="item.is_active ? 'warning' : 'success'" @click="toggleActive(item)">
                {{ item.is_active ? '停用' : '启用' }}
              </el-button>
              <el-button size="small" type="danger" @click="removeItem(item)">删除</el-button>
            </div>
          </el-card>
        </div>
      </div>

      <!-- Memory Episode -->
      <div v-show="activeTab === 'episodes'" class="tab-panel">
        <div v-loading="episodesLoading" class="item-list">
          <el-empty v-if="episodes.length === 0 && !episodesLoading" description="暂无历史讨论事件" />
          <el-card v-for="episode in episodes" :key="episode.id" shadow="never" class="knowledge-card">
            <div class="knowledge-card-head">
              <strong>{{ episode.title }}</strong>
              <el-tag :type="episode.status === 'active' ? 'success' : episode.status === 'candidate' ? 'warning' : 'info'" size="small">
                {{ episode.status_display }}
              </el-tag>
            </div>
            <p class="knowledge-content">{{ episode.summary }}</p>
            <div v-if="episode.decisions.length" class="episode-section">决定：{{ episode.decisions.join('；') }}</div>
            <div v-if="episode.next_actions.length" class="episode-section">下一步：{{ episode.next_actions.join('；') }}</div>
            <div class="knowledge-actions">
              <template v-if="episode.status === 'candidate'">
                <el-button size="small" type="primary" @click="decideEpisode(episode, 'confirm')">确认</el-button>
                <el-button size="small" @click="decideEpisode(episode, 'reject')">拒绝</el-button>
              </template>
              <el-button v-if="episode.status === 'active'" size="small" type="danger" @click="removeEpisode(episode)">删除</el-button>
            </div>
          </el-card>
        </div>
      </div>

      <!-- AI 候选 -->
      <div v-show="activeTab === 'candidates'" class="tab-panel">
        <div v-loading="candidatesLoading" class="item-list">
          <el-empty v-if="candidates.length === 0 && !candidatesLoading" description="暂无待确认的 AI 候选" />
          <el-card v-for="c in candidates" :key="c.id" shadow="never" class="knowledge-card">
            <div class="knowledge-card-head">
              <el-tag :type="categoryTag(c.category)" size="small">{{ c.category_display }}</el-tag>
              <span class="candidate-source">{{ c.source_ref || 'AI 建议' }}</span>
            </div>
            <p class="knowledge-content">{{ c.content }}</p>
            <div v-if="c.conflict_memory" class="candidate-conflict">
              <el-tag type="warning" size="small">{{ c.conflict_type_display }}</el-tag>
              <span>当前有效记忆：{{ c.conflict_memory_content }}</span>
            </div>
            <div class="knowledge-actions">
              <template v-if="c.conflict_memory">
                <el-button size="small" type="primary" @click="resolveConflict(c, 'replace')">替代旧项</el-button>
                <el-button size="small" @click="resolveConflict(c, 'keep_existing')">保留旧项</el-button>
                <el-button size="small" @click="resolveConflict(c, 'coexist')">条件并存</el-button>
                <el-button size="small" @click="resolveConflict(c, 'defer')">暂缓</el-button>
              </template>
              <template v-else>
                <el-button size="small" type="primary" @click="confirmCandidate(c)">确认</el-button>
                <el-button size="small" @click="rejectCandidate(c)">拒绝</el-button>
              </template>
            </div>
          </el-card>
        </div>
      </div>

      <!-- RAG 问答 -->
      <div v-show="activeTab === 'qa'" class="tab-panel">
        <div class="rag-input">
          <el-input v-model="question" placeholder="输入问题，例如：这个客户能深蹲吗？" @keyup.enter="askRag" />
          <el-button type="primary" :loading="answering" @click="askRag">提问</el-button>
        </div>
        <div v-if="answer" class="rag-answer">
          <p class="answer-text">{{ answer }}</p>
          <p v-if="retrievalMode === 'keyword'" class="rag-degraded">
            当前未启用语义检索（embedding 不可用），本次按关键词/最近知识条目匹配，仅供参考。
          </p>
          <p v-else-if="retrievalMode === 'safety'" class="rag-degraded">
            本次仅使用客户的有效安全限制；未检索到其他相关知识条目。
          </p>
          <div v-if="usedKnowledge.length" class="rag-refs">
            <span class="ref-title">参考知识：</span>
            <el-tag
              v-for="(k, i) in usedKnowledge"
              :key="i"
              size="small"
              :type="categoryTag(k.category)"
              class="ref-tag"
            >{{ k.content.slice(0, 30) }}</el-tag>
          </div>
        </div>
      </div>
    </template>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑知识' : '新增知识'">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="内容" prop="content">
          <el-input v-model="form.content" type="textarea" :rows="4" placeholder="输入知识内容，如：左膝 ACL 重建术后 6 周，禁止深蹲" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" class="full-width">
            <el-option v-for="o in categoryOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="重要级别">
          <el-radio-group v-model="form.importance">
            <el-radio-button value="high">高（安全限制置顶）</el-radio-button>
            <el-radio-button value="normal">普通</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSaveItem">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mobile-knowledge { display: flex; flex-direction: column; gap: 12px; }
.customer-select { display: flex; gap: 8px; }
.customer-select :deep(.customer-picker) { flex: 1; }
.customer-select :deep(.el-button) { flex: none; }
.know-tabs { --el-tabs-header-height: 40px; }
.know-tabs :deep(.el-tabs__header) { margin-bottom: 12px; }
.tab-panel { display: flex; flex-direction: column; gap: 12px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; color: var(--retrue-text); font-size: 14px; font-weight: 600; }
.item-list { display: flex; min-height: 80px; flex-direction: column; gap: 10px; }
.knowledge-card { border-color: var(--retrue-border); border-radius: var(--retrue-radius-md); }
.knowledge-card-head { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.candidate-source { color: var(--retrue-text-muted); font-size: 12px; }
.candidate-conflict { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; color: var(--retrue-text-secondary); font-size: 12px; }
.episode-section { margin-bottom: 6px; color: var(--retrue-text-secondary); font-size: 13px; line-height: 1.5; }
.knowledge-content { margin: 8px 0; color: var(--retrue-text); font-size: 14px; line-height: 1.6; }
.knowledge-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.rag-input { display: flex; gap: 8px; }
.rag-input :deep(.el-input) { flex: 1; }
.rag-input :deep(.el-button) { flex: none; }
.rag-answer { background: var(--retrue-surface); border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-sm); padding: 12px 14px; }
.answer-text { margin: 0 0 8px; white-space: pre-wrap; line-height: 1.7; color: var(--retrue-text); }
.rag-degraded { margin: 0 0 8px; font-size: 12px; color: var(--retrue-text-muted); }
.ref-title { color: var(--retrue-text-muted); font-size: 12px; margin-right: 6px; }
.ref-tag { margin: 0 4px 4px 0; }
.full-width { width: 100%; }
</style>
