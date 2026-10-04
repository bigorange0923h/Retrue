<script setup lang="ts">
/** 辅助业务组件：展示与操作家庭训练、课时包、回访。 */

import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { apiAdjustCoursePackage, apiCreateCoursePackage } from '@/api/coursePackages'
import { apiCreateFollowUp, apiListFollowUps, apiUpdateFollowUp } from '@/api/followups'
import { apiCreateHomeTrainingPlan, apiListHomeTrainingPlans, apiUpdateHomeTrainingPlan } from '@/api/training'
import type { CoursePackage, FollowUpTask, FollowUpType, HomeTrainingExercise, HomeTrainingPlan } from '@/types/api'
import { createCustomerScope } from '@/utils/customerScope'
import { formatHomeExercise, homeTrainingText } from '@/utils/homeTraining'
import ExerciseLibraryPicker from '@/components/ExerciseLibraryPicker.vue'

const props = defineProps<{ customerId: number; packages: CoursePackage[] }>()
const emit = defineEmits<{ packagesChanged: [] }>()
const route = useRoute()
const scope = createCustomerScope()

const loading = ref(false)
const plans = ref<HomeTrainingPlan[]>([])
const followUps = ref<FollowUpTask[]>([])
const failed = ref(false)
const saving = ref(false)
const activeTab = ref('plans')
let loadSequence = 0
let dialogCustomerId = 0

// 家庭训练弹窗
const planVisible = ref(false)
const editingPlanId = ref<number | null>(null)
const copyVisible = ref(false)
const copyText = ref('')
const planForm = reactive({
  title: '家庭训练',
  frequency: '',
  note: '',
  exercises: [] as HomeTrainingExercise[],
})

// 课时包弹窗
const packageVisible = ref(false)
const packageForm = reactive({ name: '', total_sessions: 20 as number | null })
const packageAdjustmentVisible = ref(false)
const adjustingPackage = ref<CoursePackage | null>(null)
const packageAdjustmentForm = reactive({ delta: 0.5, reason: '' })

// 回访弹窗
const followUpVisible = ref(false)
const followUpForm = reactive<{ followup_type: FollowUpType; due_date: string; content: string }>({
  followup_type: 'visit',
  due_date: '',
  content: '',
})
const outcomeVisible = ref(false)
const outcomeTask = ref<FollowUpTask | null>(null)
const outcomeForm = reactive({ status: 'done' as 'done' | 'skipped', result: '', arrangeNext: false, followup_type: 'visit' as FollowUpType, due_date: '', content: '' })

/** 使用本地日历日期，避免 UTC 转换在清晨把日期移到昨天。 */
function today(): string {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

async function load(): Promise<void> {
  const snapshot = scope.capture()
  const sequence = ++loadSequence
  loading.value = true
  failed.value = false
  try {
    const [planRes, fuRes] = await Promise.all([
      apiListHomeTrainingPlans(snapshot.customerId),
      apiListFollowUps({ customer_id: snapshot.customerId }),
    ])
    if (!scope.isCurrent(snapshot) || sequence !== loadSequence) return
    plans.value = planRes
    followUps.value = fuRes
    const focused = fuRes.find((item) => item.id === Number(route.query.followupId) && item.status === 'pending')
    if (focused && route.query.focus === 'followup' && !outcomeVisible.value) openOutcome(focused, 'done')
  } catch {
    if (scope.isCurrent(snapshot) && sequence === loadSequence) failed.value = true
  } finally {
    if (scope.isCurrent(snapshot) && sequence === loadSequence) loading.value = false
  }
}

function openPlanDialog(plan?: HomeTrainingPlan): void {
  dialogCustomerId = props.customerId
  editingPlanId.value = plan?.id ?? null
  planForm.title = plan?.title || '家庭训练'
  planForm.frequency = plan?.frequency || ''
  planForm.note = plan?.note || ''
  planForm.exercises = plan?.exercises.map((item) => ({ ...item })) || []
  planVisible.value = true
}

function addPlanExercise(): void {
  planForm.exercises.push({ exercise_name: '', sets: null, reps: null, duration_seconds: null, frequency: '', note: '', sort_order: planForm.exercises.length })
}

async function savePlan(): Promise<void> {
  if (!planForm.title.trim()) { ElMessage.warning('请填写计划标题'); return }
  if (planForm.exercises.some((item) => !item.exercise_name.trim())) { ElMessage.warning('请填写每项动作名称或移除空动作'); return }
  const id = editingPlanId.value
  const payload = { title: planForm.title, frequency: planForm.frequency, note: planForm.note,
    exercises: planForm.exercises.map((item, index) => ({ ...item, sort_order: index })) }
  await saveForCustomer(async () => {
    if (id) await apiUpdateHomeTrainingPlan(id, payload)
    else await apiCreateHomeTrainingPlan({ customer: dialogCustomerId, ...payload })
  }, '家庭训练已保存', () => { planVisible.value = false })
}

/** 先展示完整文案供核对，复制只在用户点击后发生。 */
function previewCopy(plan: HomeTrainingPlan): void { copyText.value = homeTrainingText(plan); copyVisible.value = true }
async function copyPlan(): Promise<void> {
  try { await navigator.clipboard.writeText(copyText.value); ElMessage.success('已复制完整训练文案') }
  catch { ElMessage.warning('无法自动复制，请在文案框中选择并复制') }
}

/** 请求使用打开弹窗时的稳定目标；失败保留输入，旧客户完成不影响当前页面。 */
async function saveForCustomer(action: () => Promise<void>, message: string, close: () => void): Promise<void> {
  if (saving.value || dialogCustomerId !== props.customerId) return
  const snapshot = scope.capture()
  saving.value = true
  try {
    await action()
    if (!scope.isCurrent(snapshot)) return
    close()
    ElMessage.success(message)
    await load()
  } catch { /* API 层已提示；弹窗与输入保留以便重试。 */ }
  finally { if (scope.isCurrent(snapshot)) saving.value = false }
}

function openPackageDialog(): void {
  dialogCustomerId = props.customerId
  packageForm.name = ''
  packageForm.total_sessions = 20
  packageVisible.value = true
}

async function savePackage(): Promise<void> {
  if (!packageForm.total_sessions) {
    ElMessage.warning('请输入总课时')
    return
  }
  const payload = { customer: dialogCustomerId, name: packageForm.name, total_sessions: packageForm.total_sessions }
  await saveForCustomer(async () => { await apiCreateCoursePackage(payload) }, '课时包已创建', () => { packageVisible.value = false; emit('packagesChanged') })
}

function openPackageAdjustment(pkg: CoursePackage): void {
  dialogCustomerId = props.customerId
  adjustingPackage.value = pkg
  packageAdjustmentForm.delta = 0.5
  packageAdjustmentForm.reason = ''
  packageAdjustmentVisible.value = true
}

async function savePackageAdjustment(): Promise<void> {
  if (!adjustingPackage.value) return
  if (!packageAdjustmentForm.delta || !packageAdjustmentForm.reason.trim()) {
    ElMessage.warning('请填写调整量和原因')
    return
  }
  const id = adjustingPackage.value.id
  const { delta, reason } = packageAdjustmentForm
  await saveForCustomer(async () => { await apiAdjustCoursePackage(id, delta, reason) }, '课时已调整', () => { packageAdjustmentVisible.value = false; emit('packagesChanged') })
}

function openFollowUpDialog(): void {
  dialogCustomerId = props.customerId
  followUpForm.followup_type = 'visit'
  followUpForm.due_date = today()
  followUpForm.content = ''
  followUpVisible.value = true
}

async function saveFollowUp(): Promise<void> {
  if (!followUpForm.due_date) {
    ElMessage.warning('请选择日期')
    return
  }
  const payload = { customer: dialogCustomerId, ...followUpForm }
  await saveForCustomer(async () => { await apiCreateFollowUp(payload) }, '回访已创建', () => { followUpVisible.value = false })
}

function openOutcome(task: FollowUpTask, status: 'done' | 'skipped'): void {
  dialogCustomerId = props.customerId
  outcomeTask.value = task
  Object.assign(outcomeForm, { status, result: '', arrangeNext: false, followup_type: task.followup_type, due_date: '', content: '' })
  outcomeVisible.value = true
}
async function saveOutcome(): Promise<void> {
  const task = outcomeTask.value
  if (!task || !outcomeForm.result.trim()) { ElMessage.warning(outcomeForm.status === 'done' ? '请记录实际回访结果' : '请说明跳过原因'); return }
  if (outcomeForm.arrangeNext && !outcomeForm.due_date) { ElMessage.warning('请明确下一项日期'); return }
  const payload = { due_date: task.due_date, status: outcomeForm.status, result: outcomeForm.result,
    ...(outcomeForm.status === 'done' && outcomeForm.arrangeNext ? { next_task: { followup_type: outcomeForm.followup_type, due_date: outcomeForm.due_date, content: outcomeForm.content } } : {}) }
  await saveForCustomer(async () => { await apiUpdateFollowUp(task.id, payload) }, outcomeForm.status === 'done' ? '回访结果已保存' : '已记录跳过原因', () => { outcomeVisible.value = false })
}

async function confirmNavigation(): Promise<boolean> {
  if (![planVisible.value, packageVisible.value, packageAdjustmentVisible.value, followUpVisible.value, outcomeVisible.value].some(Boolean)) return true
  try { await ElMessageBox.confirm('还有尚未提交的操作，离开将丢弃弹窗中的内容。', '离开客户', { confirmButtonText: '丢弃并离开', cancelButtonText: '继续填写', type: 'warning' }); return true }
  catch { return false }
}
onBeforeRouteLeave(confirmNavigation)
onBeforeRouteUpdate((to, from) => to.params.id === from.params.id ? true : confirmNavigation())
watch(() => props.customerId, (id) => {
  scope.reset(id)
  plans.value = []; followUps.value = []; saving.value = false
  planVisible.value = false; packageVisible.value = false; packageAdjustmentVisible.value = false; followUpVisible.value = false; outcomeVisible.value = false; copyVisible.value = false
  activeTab.value = route.query.focus === 'followup' ? 'followups' : 'plans'
  void load()
}, { immediate: true })
onBeforeUnmount(() => scope.reset(0))
</script>

<template>
  <div v-loading="loading" class="aux-services">
    <el-alert v-if="failed" title="辅助业务加载失败" type="error" :closable="false"><el-button link @click="load">重新加载</el-button></el-alert>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="家庭训练" name="plans">
        <div class="pane-header">
          <span>家庭训练计划</span>
          <el-button type="primary" size="small" @click="openPlanDialog()">新增</el-button>
        </div>
        <el-empty v-if="plans.length === 0" description="暂无家庭训练计划" :image-size="60" />
        <div v-for="plan in plans" :key="plan.id" class="aux-item">
          <div class="aux-title">{{ plan.title }}<el-button link type="primary" @click="openPlanDialog(plan)">编辑</el-button><el-button link type="primary" @click="previewCopy(plan)">核对并复制</el-button></div>
          <div v-if="plan.frequency" class="aux-sub">整体频率：{{ plan.frequency }}</div>
          <div v-for="(exercise, index) in plan.exercises" :key="exercise.id || index" class="aux-sub">{{ index + 1 }}. {{ formatHomeExercise(exercise) }}</div>
          <div v-if="plan.note" class="aux-sub">注意：{{ plan.note }}</div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="课时包" name="packages">
        <div class="pane-header">
          <span>课时包</span>
          <el-button type="primary" size="small" @click="openPackageDialog">新增</el-button>
        </div>
        <el-empty v-if="props.packages.length === 0" description="暂无课时包" :image-size="60" />
        <div v-for="pkg in props.packages" :key="pkg.id" class="aux-item">
          <div class="aux-title">
            {{ pkg.name }}
            <el-button link type="primary" size="small" @click="openPackageAdjustment(pkg)">人工调整</el-button>
          </div>
          <div class="aux-sub">
            已用 {{ pkg.used_sessions }} / 共 {{ pkg.total_sessions }}，剩余
            <el-tag type="success">{{ pkg.remaining_sessions }}</el-tag>
          </div>
          <el-collapse v-if="pkg.adjustments.length" class="package-history">
            <el-collapse-item :title="`课时流水（${pkg.adjustments.length}）`" :name="pkg.id">
              <div v-for="item in pkg.adjustments" :key="item.id" class="package-history-item">
                <el-tag :type="item.adjustment_type === 'consumption' ? 'warning' : 'info'" size="small">
                  {{ item.adjustment_type_display }}
                </el-tag>
                <strong>{{ item.delta > 0 ? '+' : '' }}{{ item.delta }}</strong>
                <span>{{ item.reason }}</span>
                <span class="history-meta">
                  {{ item.course_session_topic || item.therapist_name }} · {{ item.created_at.slice(0, 16).replace('T', ' ') }}
                </span>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-tab-pane>

      <el-tab-pane label="回访" name="followups">
        <div class="pane-header">
          <span>回访/复查</span>
          <el-button type="primary" size="small" @click="openFollowUpDialog">新增</el-button>
        </div>
        <el-empty v-if="followUps.length === 0" description="暂无回访待办" :image-size="60" />
        <div v-for="task in followUps" :key="task.id" class="aux-item">
          <div class="aux-title">
            {{ task.followup_type_display }} · {{ task.due_date }}
            <el-tag v-if="task.status === 'done'" type="success" size="small">{{ task.status_display }}</el-tag>
            <el-tag v-else type="warning" size="small">{{ task.status_display }}</el-tag>
          </div>
          <div v-if="task.content" class="aux-sub">{{ task.content }}</div>
          <div v-if="task.result" class="aux-sub">{{ task.status === 'skipped' ? '跳过原因' : '回访结果' }}：{{ task.result }}</div>
          <div v-if="task.status === 'pending'"><el-button link type="primary" @click="openOutcome(task, 'done')">记录结果</el-button><el-button link @click="openOutcome(task, 'skipped')">跳过并说明原因</el-button></div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 家庭训练弹窗 -->
    <el-dialog v-model="planVisible" :title="editingPlanId ? '编辑家庭训练' : '新增家庭训练'" width="560px" :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving">
      <el-form :model="planForm" label-width="70px" :disabled="saving">
        <el-form-item label="标题"><el-input v-model="planForm.title" /></el-form-item>
        <el-form-item label="频率"><el-input v-model="planForm.frequency" placeholder="如：每天 2 次" /></el-form-item>
        <div v-for="(ex, i) in planForm.exercises" :key="i" class="exercise-editor">
          <el-form-item :label="`动作 ${i + 1}`"><el-input v-model="ex.exercise_name" placeholder="动作名称" /><ExerciseLibraryPicker @select="(item) => ex.exercise_name = item.name" /></el-form-item>
          <div class="dose-grid"><el-form-item label="组数"><el-input-number v-model="ex.sets" :min="0" /></el-form-item><el-form-item label="每组次数"><el-input-number v-model="ex.reps" :min="0" /></el-form-item><el-form-item label="秒/次"><el-input-number v-model="ex.duration_seconds" :min="0" /></el-form-item></div>
          <el-form-item label="动作频率"><el-input v-model="ex.frequency" placeholder="如：每天早晚" /></el-form-item>
          <el-form-item label="动作注意"><el-input v-model="ex.note" type="textarea" :rows="2" /></el-form-item>
          <el-button link type="danger" @click="planForm.exercises.splice(i, 1)">移除该动作</el-button>
        </div>
        <el-button link type="primary" @click="addPlanExercise">+ 添加动作</el-button>
        <el-form-item label="注意">
          <el-input v-model="planForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="planVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePlan">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="packageAdjustmentVisible" title="人工调整课时" width="430px">
      <p v-if="adjustingPackage" class="adjust-summary">
        {{ adjustingPackage.name }}：已用 {{ adjustingPackage.used_sessions }} / 共 {{ adjustingPackage.total_sessions }}
      </p>
      <el-form :model="packageAdjustmentForm" label-width="80px" :disabled="saving">
        <el-form-item label="调整量">
          <el-input-number v-model="packageAdjustmentForm.delta" :step="0.5" :precision="1" />
          <span class="field-hint">正数补扣，负数退还</span>
        </el-form-item>
        <el-form-item label="调整原因">
          <el-input v-model="packageAdjustmentForm.reason" type="textarea" :rows="3" placeholder="请说明补扣或退还原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="packageAdjustmentVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePackageAdjustment">确认调整</el-button>
      </template>
    </el-dialog>

    <!-- 课时包弹窗 -->
    <el-dialog v-model="packageVisible" title="新增课时包" width="400px">
      <el-form :model="packageForm" label-width="70px" :disabled="saving">
        <el-form-item label="名称"><el-input v-model="packageForm.name" placeholder="如：20课时包" /></el-form-item>
        <el-form-item label="总课时"><el-input-number v-model="packageForm.total_sessions" :min="1" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="packageVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePackage">保存</el-button>
      </template>
    </el-dialog>

    <!-- 回访弹窗 -->
    <el-dialog v-model="followUpVisible" title="新增回访" width="400px">
      <el-form :model="followUpForm" label-width="70px" :disabled="saving">
        <el-form-item label="类型">
          <el-select v-model="followUpForm.followup_type">
            <el-option label="回访" value="visit" />
            <el-option label="复查" value="review" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="followUpForm.due_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="内容"><el-input v-model="followUpForm.content" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="followUpVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveFollowUp">保存</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="outcomeVisible" :title="outcomeForm.status === 'done' ? '记录实际回访结果' : '记录跳过原因'" width="480px" :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving">
      <el-form :model="outcomeForm" label-position="top" :disabled="saving">
        <el-form-item :label="outcomeForm.status === 'done' ? '实际结果（必填）' : '跳过原因（必填）'"><el-input v-model="outcomeForm.result" type="textarea" :rows="4" /></el-form-item>
        <template v-if="outcomeForm.status === 'done'">
          <el-checkbox v-model="outcomeForm.arrangeNext">需要继续处理，明确安排下一项</el-checkbox>
          <template v-if="outcomeForm.arrangeNext">
            <el-form-item label="下一项类型"><el-select v-model="outcomeForm.followup_type"><el-option label="回访" value="visit" /><el-option label="复查" value="review" /><el-option label="其他" value="other" /></el-select></el-form-item>
            <el-form-item label="下一项日期"><el-date-picker v-model="outcomeForm.due_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
            <el-form-item label="下一项内容"><el-input v-model="outcomeForm.content" type="textarea" :rows="2" /></el-form-item>
          </template>
        </template>
      </el-form>
      <template #footer><el-button :disabled="saving" @click="outcomeVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveOutcome">保存结果</el-button></template>
    </el-dialog>
    <el-dialog v-model="copyVisible" title="核对客户版训练文案" width="560px">
      <el-input v-model="copyText" type="textarea" :rows="12" readonly />
      <template #footer><el-button @click="copyVisible = false">关闭</el-button><el-button type="primary" @click="copyPlan">复制完整文案</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.pane-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.aux-item {
  padding: 10px 6px;
  border-bottom: 1px solid var(--retrue-border);
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-radius: var(--retrue-radius-sm);
}

.aux-title {
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.aux-sub {
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.exercise-editor { border-top: 1px solid var(--retrue-border); padding: 12px 0; }
.dose-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.aux-title { flex-wrap: wrap; }
@media (max-width: 767px) {
  .dose-grid { grid-template-columns: 1fr; }
  .package-history-item { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  :deep(.el-dialog) { max-width: calc(100vw - 32px); }
  :deep(.el-date-editor), :deep(.el-input-number) { max-width: 100%; }
}

.package-history {
  margin-top: 4px;
}

.package-history-item {
  display: grid;
  grid-template-columns: 76px 48px minmax(160px, 1fr) minmax(180px, auto);
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
}

.history-meta,
.field-hint,
.adjust-summary {
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.field-hint {
  margin-left: 8px;
}
</style>
