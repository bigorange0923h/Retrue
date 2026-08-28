<script setup lang="ts">
/** AI 草稿工作台：自然语言记录训练，生成草稿、编辑并确认/取消。 */

import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { apiCancelDraft, apiConfirmDraft, apiCustomerCandidates, apiParseDraft } from '@/api/ai'
import type { AiDraft, AiDraftResult, CustomerCandidate } from '@/types/api'

const route = useRoute()
const router = useRouter()
const customerId = Number(route.query.customerId || 0)

const inputText = ref('')
const parsing = ref(false)
const confirming = ref(false)
const draft = ref<AiDraft | null>(null)

// 编辑后的草稿结果
const editForm = reactive<AiDraftResult>({
  training_date: '',
  customer_hint: null,
  exercises: [],
  customer_feedback: '',
  therapist_observation: '',
  next_plan: '',
})

// 客户选择
const customerPickerVisible = ref(false)
const candidates = ref<CustomerCandidate[]>([])
const selectedCustomer = ref<CustomerCandidate | null>(null)
const customerKeyword = ref('')

function resetDraft(): void {
  draft.value = null
  editForm.training_date = ''
  editForm.customer_hint = null
  editForm.exercises = []
  editForm.customer_feedback = ''
  editForm.therapist_observation = ''
  editForm.next_plan = ''
}

async function handleParse(): Promise<void> {
  if (!inputText.value.trim()) {
    ElMessage.warning('请输入训练描述')
    return
  }
  parsing.value = true
  try {
    const result = await apiParseDraft(inputText.value, customerId || null)
    draft.value = result
    if (result.status === 'failed') {
      ElMessage.error(result.error_message || 'AI 解析失败')
      return
    }
    // 填充编辑表单
    editForm.training_date = result.ai_result.training_date
    editForm.customer_hint = result.ai_result.customer_hint
    editForm.exercises = result.ai_result.exercises.map((e, i) => ({ ...e, sort_order: i }))
    editForm.customer_feedback = result.ai_result.customer_feedback
    editForm.therapist_observation = result.ai_result.therapist_observation
    editForm.next_plan = result.ai_result.next_plan

    // 有明确客户则选中
    if (customerId) {
      selectedCustomer.value = { id: customerId, name: '', phone_masked: '' }
    } else {
      // 无明确客户，弹出候选选择
      await openCustomerPicker()
    }
  } finally {
    parsing.value = false
  }
}

async function openCustomerPicker(): Promise<void> {
  customerPickerVisible.value = true
  await loadCandidates()
}

async function loadCandidates(): Promise<void> {
  candidates.value = await apiCustomerCandidates(customerKeyword.value || '')
}

async function handleConfirm(): Promise<void> {
  if (!draft.value) return
  if (!selectedCustomer.value?.id) {
    ElMessage.warning('请选择客户')
    return
  }
  confirming.value = true
  try {
    const payload: AiDraftResult = { ...editForm }
    const result = await apiConfirmDraft(draft.value.id, selectedCustomer.value.id, payload)
    ElMessage.success('已确认并创建训练记录')
    draft.value = result
    customerPickerVisible.value = false
    // 跳转到客户详情查看时间线
    router.push({ name: 'customer-detail', params: { id: selectedCustomer.value.id } })
  } finally {
    confirming.value = false
  }
}

async function handleCancel(): Promise<void> {
  if (!draft.value) return
  await apiCancelDraft(draft.value.id)
  ElMessage.info('草稿已取消')
  resetDraft()
  inputText.value = ''
}

function pickCustomer(candidate: CustomerCandidate): void {
  selectedCustomer.value = candidate
  customerPickerVisible.value = false
}

onMounted(() => {
  if (customerId) {
    selectedCustomer.value = { id: customerId, name: '', phone_masked: '' }
  }
})
</script>

<template>
  <div class="ai-draft-page">
    <div class="page-header">
      <h2>AI 训练记录</h2>
      <el-button @click="router.back()">返回</el-button>
    </div>

    <!-- 输入区 -->
    <el-card class="input-card">
      <template #header>用一句话记录训练</template>
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="4"
        placeholder="例如：今天做了臀桥 3 组 12 次，靠墙静蹲 3 组 30 秒。左膝下蹲还有一点疼，大概 2 分，比上次稳定。下次可以加单腿稳定训练。"
      />
      <div class="input-actions">
        <span v-if="draft && draft.status === 'failed'" class="error-hint">
          AI 解析失败，请调整描述后重试
        </span>
        <el-button type="primary" :loading="parsing" @click="handleParse">
          {{ draft ? '重新解析' : 'AI 生成草稿' }}
        </el-button>
      </div>
    </el-card>

    <!-- 草稿预览/编辑区 -->
    <el-card v-if="draft && draft.status !== 'failed'" class="draft-card">
      <template #header>
        <div class="draft-header">
          <span>AI 草稿（待确认）</span>
          <el-tag type="warning">草稿</el-tag>
        </div>
      </template>

      <!-- 客户选择 -->
      <div class="customer-row">
        <span class="label">客户：</span>
        <template v-if="selectedCustomer">
          <span class="customer-name">{{ selectedCustomer.name || '已选择' }}</span>
          <el-button link type="primary" @click="openCustomerPicker">更换</el-button>
        </template>
        <el-button v-else link type="primary" @click="openCustomerPicker">选择客户</el-button>
      </div>

      <el-form label-width="80px">
        <el-form-item label="训练日期">
          <el-date-picker v-model="editForm.training_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>

        <el-divider content-position="left">训练动作</el-divider>
        <div v-for="(ex, index) in editForm.exercises" :key="index" class="exercise-row">
          <el-input v-model="ex.exercise_name" placeholder="动作" class="ex-name" />
          <el-input-number v-model="ex.sets" :min="0" placeholder="组" class="ex-num" />
          <el-input-number v-model="ex.reps" :min="0" placeholder="次" class="ex-num" />
          <el-input v-model="ex.weight" placeholder="重量" class="ex-weight" />
        </div>

        <el-divider content-position="left">记录内容</el-divider>
        <el-form-item label="客户感受">
          <el-input v-model="editForm.customer_feedback" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="康复师观察">
          <el-input v-model="editForm.therapist_observation" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="下次计划">
          <el-input v-model="editForm.next_plan" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>

      <div class="draft-actions">
        <el-button @click="handleCancel">取消草稿</el-button>
        <el-button type="primary" :loading="confirming" @click="handleConfirm">确认并保存</el-button>
      </div>
    </el-card>

    <!-- 客户候选选择弹窗 -->
    <el-dialog v-model="customerPickerVisible" title="选择客户" width="420px">
      <el-input v-model="customerKeyword" placeholder="输入姓名搜索" @keyup.enter="loadCandidates" />
      <div class="candidate-list">
        <div
          v-for="c in candidates"
          :key="c.id"
          class="candidate-item"
          @click="pickCustomer(c)"
        >
          <span>{{ c.name }}</span>
          <span class="candidate-phone">{{ c.phone_masked }}</span>
        </div>
        <el-empty v-if="candidates.length === 0" description="没有匹配的客户" :image-size="60" />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.input-card,
.draft-card {
  border-radius: var(--retrue-radius-lg);
  border: 1px solid var(--retrue-border);
  box-shadow: var(--retrue-shadow);
  margin-bottom: 16px;
  max-width: 760px;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.error-hint {
  color: var(--retrue-risk);
  font-size: 13px;
}

.draft-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.customer-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.customer-row .label {
  color: var(--retrue-text-secondary);
}

.customer-name {
  font-weight: 500;
}

.exercise-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.ex-name {
  flex: 1;
}

.ex-num {
  width: 110px;
}

.ex-weight {
  width: 90px;
}

.draft-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.candidate-list {
  margin-top: 12px;
  max-height: 320px;
  overflow-y: auto;
}

.candidate-item {
  display: flex;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: var(--retrue-radius-sm);
  cursor: pointer;
}

.candidate-item:hover {
  background: var(--retrue-bg);
}

.candidate-phone {
  color: var(--retrue-text-muted);
}
</style>
