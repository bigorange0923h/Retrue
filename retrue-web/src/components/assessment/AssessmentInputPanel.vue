<script setup lang="ts">
/** 本次文字整理与逐项复核；候选只在主动采用后合并到父页面的同一草稿。 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiGetAssessmentInput, apiOrganizeAssessment, apiSaveAssessmentSource, type AssessmentForm, type AssessmentInputDraft } from '@/api/assessments'
import { assessmentFieldLabels, metricIdentity, onsetLabels } from '@/utils/assessmentInput'

const props = defineProps<{ form: AssessmentForm; assessmentId: number | null; disabled: boolean; ready: boolean; prepareSave: () => Promise<boolean> }>()
const emit = defineEmits<{
  busy: [value: boolean]
  unsaved: [value: boolean]
  adopt: [draft: AssessmentInputDraft, fields: string[], metrics: number[]]
}>()
const input = ref('')
const draft = ref<AssessmentInputDraft | null>(null)
const selectedFields = ref<string[]>([])
const selectedMetrics = ref<number[]>([])
const busy = ref(false)
const failed = ref(false)
const recoveryFailed = ref(false)
const adopted = ref(false)
const savedSource = ref('')
const savingSource = ref(false)
const savedContext = ref('')
const savedDraftId = ref<number | undefined>()
let controller: AbortController | null = null
let generation = 0
const context = computed(() => ({ customer_id: props.form.customer, assessment_id: props.assessmentId, assessment_type: props.form.assessment_type }))
const metricLabels: Record<string, string> = { pain: '疼痛', strength: '肌力', rom: '活动度', special_test: '特殊测试', functional: '功能动作' }
const resultLabels: Record<string, string> = { positive: '阳性', negative: '阴性', uncertain: '无法判断', normal: '正常', limited: '受限', unable: '无法完成' }

function display(field: string, value: unknown): string {
  if (!value) return '尚未记录'
  return field === 'onset_mode' ? (onsetLabels[String(value)] || String(value)) : String(value)
}
function current(field: string): unknown { return (props.form as unknown as Record<string, unknown>)[field] }
function conflicting(field: string, value: string): boolean {
  const existing = current(field)
  return !!existing && existing !== value && !(field === 'onset_mode' && existing === 'unknown')
}
function duplicate(index: number): boolean {
  const metric = draft.value?.metrics[index]?.value
  return !!metric && props.form.metrics.some((existing) => metricIdentity(existing) === metricIdentity(metric))
}
function hydrate(value: AssessmentInputDraft): void {
  draft.value = value.source_only ? null : value
  savedSource.value = value.input_text
  savedContext.value = JSON.stringify(context.value)
  savedDraftId.value = value.id
  input.value = value.input_text
  selectedFields.value = value.fields.filter((item) => !conflicting(item.field, item.value) && current(item.field) !== item.value).map((item) => item.field)
  selectedMetrics.value = []
  adopted.value = false
  failed.value = false
}
/** 只在用户主动保存/离开时保存尚未整理的文字，失败保留原输入。 */
async function saveSource(): Promise<boolean> {
  if (!input.value.trim()) return true
  if (savingSource.value || busy.value) return false
  savingSource.value = true
  const source = input.value
  try {
    if (!await props.prepareSave()) return false
    await nextTick()
    if (source === savedSource.value && savedContext.value === JSON.stringify(context.value)) return true
    const value = await apiSaveAssessmentSource(context.value, source, source === savedSource.value && !adopted.value ? savedDraftId.value : undefined)
    savedSource.value = source
    savedDraftId.value = value.id
    savedContext.value = JSON.stringify(context.value)
    return input.value === source
  } catch { return false }
  finally { savingSource.value = false }
}
defineExpose({ saveSource })
async function organize(): Promise<void> {
  if (busy.value || props.disabled || !input.value.trim()) return
  busy.value = true
  emit('busy', true)
  failed.value = false
  controller = new AbortController()
  const requestGeneration = ++generation
  try {
    const value = await apiOrganizeAssessment(context.value, input.value, controller.signal)
    if (requestGeneration === generation) hydrate(value)
  } catch {
    if (requestGeneration === generation) failed.value = true
  } finally {
    if (requestGeneration === generation) { busy.value = false; emit('busy', false) }
  }
}
async function recover(): Promise<void> {
  if (!props.ready || !props.form.customer || props.form.status !== 'draft' || draft.value) return
  const key = JSON.stringify(context.value)
  recoveryFailed.value = false
  try {
    const value = await apiGetAssessmentInput(context.value)
    if (value && key === JSON.stringify(context.value) && !draft.value && !input.value) hydrate(value)
  } catch { recoveryFailed.value = true }
}
function adopt(): void {
  if (!draft.value || adopted.value || busy.value || props.disabled) return
  if (!selectedFields.value.length && !selectedMetrics.value.length) {
    ElMessage.info('请先选择要采用的内容，已有值默认保留')
    return
  }
  emit('adopt', draft.value, selectedFields.value, selectedMetrics.value)
  adopted.value = true
  ElMessage.success('已采用选中内容，可修改或补充；评估尚未完成')
}
watch([context, () => props.ready], recover, { immediate: true })
watch(context, async (value, previous) => {
  // 普通字段先保存创建了评估时，将新建页已有候选关联到该草稿，避免刷新找不到。
  if (!previous.assessment_id && value.assessment_id && savedDraftId.value && !adopted.value && input.value === savedSource.value) {
    try {
      const stored = await apiSaveAssessmentSource(value, savedSource.value, savedDraftId.value)
      savedContext.value = JSON.stringify(value)
      savedDraftId.value = stored.id
    } catch { recoveryFailed.value = true }
  }
})
// 整理后若康复师又手填了同一字段，撤销该候选的默认勾选，避免晚采用覆盖人工值。
watch(() => props.form, () => {
  selectedFields.value = selectedFields.value.filter((field) => {
    const item = draft.value?.fields.find((candidate) => candidate.field === field)
    return !!item && !conflicting(field, item.value)
  })
}, { deep: true })
watch([input, savedSource], () => emit('unsaved', !!input.value.trim() && input.value !== savedSource.value), { flush: 'sync' })
onBeforeUnmount(() => { generation++; controller?.abort(); emit('busy', false) })
</script>

<template>
  <section class="input-panel">
    <h3>描述本次情况</h3>
    <p>可粘贴文字或使用设备输入法的语音转文字。只描述本次询问和实际测量，未知内容无需猜测。</p>
    <el-input v-model="input" type="textarea" :rows="4" maxlength="8000" show-word-limit :disabled="disabled || busy || savingSource"
      placeholder="例如：右膝下楼疼痛，约两周前开始，休息会缓解，想恢复正常上下楼。刚才测得右膝下蹲疼痛 3 分。" />
    <p class="consent">点击“整理为候选”会把这段文字发送给已配置的 AI；不会自动完成评估。</p>
    <el-button type="primary" :loading="busy" :disabled="disabled || savingSource || !input.trim()" @click="organize">{{ busy ? '正在整理本次描述…' : '整理为候选' }}</el-button>
    <el-button :loading="savingSource" :disabled="disabled || busy || !input.trim()" @click="saveSource">保存描述与草稿</el-button>
    <p v-if="input.trim()">{{ input === savedSource ? '描述已保存在服务端，可稍后继续' : '描述尚未保存' }}</p>
    <p v-if="failed" class="error" role="alert">整理失败，文字仍保留。可重试，也可在下方直接填写。</p>
    <p v-if="recoveryFailed" class="error">暂未恢复上次候选。<el-button link type="primary" @click="recover">重试恢复</el-button></p>
    <div v-if="draft && !adopted" class="candidate">
      <h4>核对本次候选</h4>
      <p>选中后采用；有差异的已有内容默认保留。开始日期与评估日期请分别核对。</p>
      <el-checkbox-group v-model="selectedFields" :disabled="disabled || busy">
        <article v-for="item in draft.fields" :key="item.field" class="candidate-row">
          <el-checkbox :value="item.field">{{ assessmentFieldLabels[item.field] || item.field }}</el-checkbox>
          <p v-if="conflicting(item.field, item.value)">已有：{{ display(item.field, current(item.field)) }}</p>
          <p>候选：{{ display(item.field, item.value) }}</p>
          <details><summary>查看原文依据</summary><p>{{ item.evidence }}</p></details>
        </article>
      </el-checkbox-group>
      <el-checkbox-group v-model="selectedMetrics" :disabled="disabled || busy">
        <article v-for="(item, index) in draft.metrics" :key="index" class="candidate-row">
          <el-checkbox :value="index" :disabled="duplicate(index)">{{ metricLabels[item.value.metric_type] }} · {{ item.value.body_part || item.value.movement || '部位待补充' }}</el-checkbox>
          <p>{{ item.value.score ?? resultLabels[item.value.result_code || ''] ?? '结果待补充' }}{{ item.value.metric_type === 'rom' ? '°' : item.value.metric_type === 'strength' ? ' 级' : item.value.metric_type === 'pain' ? ' 分' : '' }}</p>
          <p v-if="duplicate(index)">已有同类项目，保留人工值；请在客观评估中核对或修改。</p>
          <details><summary>查看原文依据</summary><p>{{ item.evidence.metric_type }}</p></details>
        </article>
      </el-checkbox-group>
      <p v-for="warning in draft.warnings" :key="warning" class="warning">{{ warning }}</p>
      <p v-if="!draft.fields.length && !draft.metrics.length">没有可安全采用的内容，请补充描述或直接填写。</p>
      <el-button type="primary" :disabled="disabled || busy || (!selectedFields.length && !selectedMetrics.length)" @click="adopt">采用选中内容并继续编辑</el-button>
    </div>
    <p v-if="adopted">选中内容已带入下方同一份评估草稿，仍可修改；最终完成需主动提交。</p>
  </section>
</template>

<style scoped>
.input-panel { margin-bottom: 24px; padding: 18px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-md); }
.input-panel h3, .input-panel h4 { margin: 0 0 10px; }
.input-panel p { line-height: 1.7; color: var(--retrue-text-secondary); white-space: pre-wrap; overflow-wrap: anywhere; }
.consent, details { font-size: 12px; }
.candidate { margin-top: 20px; }
.candidate-row { margin: 12px 0; padding: 12px; background: var(--retrue-surface-subtle); border-radius: var(--retrue-radius-sm); }
.candidate-row p { margin: 5px 0; }
.error { color: var(--el-color-danger) !important; }
.warning { color: var(--retrue-visit) !important; }
</style>
