<script setup lang="ts">
/** 辅助业务组件：展示与操作家庭训练、课时包、回访。 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { apiCreateCoursePackage, apiListCoursePackages } from '@/api/coursePackages'
import { apiCreateFollowUp, apiListFollowUps, apiUpdateFollowUp } from '@/api/followups'
import { apiCreateHomeTrainingPlan, apiListHomeTrainingPlans } from '@/api/training'
import type { CoursePackage, FollowUpTask, FollowUpType, HomeTrainingExercise, HomeTrainingPlan } from '@/types/api'

const props = defineProps<{ customerId: number }>()

const loading = ref(false)
const plans = ref<HomeTrainingPlan[]>([])
const packages = ref<CoursePackage[]>([])
const followUps = ref<FollowUpTask[]>([])

// 家庭训练弹窗
const planVisible = ref(false)
const planForm = reactive({
  title: '家庭训练',
  frequency: '',
  note: '',
  exercises: [] as HomeTrainingExercise[],
})

// 课时包弹窗
const packageVisible = ref(false)
const packageForm = reactive({ name: '', total_sessions: 20 as number | null })

// 回访弹窗
const followUpVisible = ref(false)
const followUpForm = reactive<{ followup_type: FollowUpType; due_date: string; content: string }>({
  followup_type: 'visit',
  due_date: '',
  content: '',
})

async function load(): Promise<void> {
  loading.value = true
  try {
    const [planRes, pkgRes, fuRes] = await Promise.all([
      apiListHomeTrainingPlans(props.customerId),
      apiListCoursePackages(props.customerId),
      apiListFollowUps({ customer_id: props.customerId }),
    ])
    plans.value = planRes
    packages.value = pkgRes
    followUps.value = fuRes
  } finally {
    loading.value = false
  }
}

function openPlanDialog(): void {
  planForm.title = '家庭训练'
  planForm.frequency = ''
  planForm.note = ''
  planForm.exercises = []
  planVisible.value = true
}

function addPlanExercise(): void {
  planForm.exercises.push({ exercise_name: '', sets: null, reps: null, duration_seconds: null, frequency: '', note: '', sort_order: planForm.exercises.length })
}

async function savePlan(): Promise<void> {
  const exercises = planForm.exercises.filter((e) => e.exercise_name.trim())
  await apiCreateHomeTrainingPlan({ customer: props.customerId, ...planForm, exercises })
  ElMessage.success('家庭训练已创建')
  planVisible.value = false
  await load()
}

function openPackageDialog(): void {
  packageForm.name = ''
  packageForm.total_sessions = 20
  packageVisible.value = true
}

async function savePackage(): Promise<void> {
  if (!packageForm.total_sessions) {
    ElMessage.warning('请输入总课时')
    return
  }
  await apiCreateCoursePackage({ customer: props.customerId, name: packageForm.name, total_sessions: packageForm.total_sessions })
  ElMessage.success('课时包已创建')
  packageVisible.value = false
  await load()
}

function openFollowUpDialog(): void {
  followUpForm.followup_type = 'visit'
  followUpForm.due_date = new Date().toISOString().slice(0, 10)
  followUpForm.content = ''
  followUpVisible.value = true
}

async function saveFollowUp(): Promise<void> {
  if (!followUpForm.due_date) {
    ElMessage.warning('请选择日期')
    return
  }
  await apiCreateFollowUp({ customer: props.customerId, ...followUpForm })
  ElMessage.success('回访已创建')
  followUpVisible.value = false
  await load()
}

async function markFollowUpDone(task: FollowUpTask): Promise<void> {
  await apiUpdateFollowUp(task.id, { due_date: task.due_date, status: 'done', result: '已完成' })
  ElMessage.success('回访已完成')
  await load()
}

function formatPlanExercises(plan: HomeTrainingPlan): string {
  return plan.exercises.map((e) => e.exercise_name).join('、') || '无动作'
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="aux-services">
    <el-tabs>
      <el-tab-pane label="家庭训练">
        <div class="pane-header">
          <span>家庭训练计划</span>
          <el-button type="primary" size="small" @click="openPlanDialog">新增</el-button>
        </div>
        <el-empty v-if="plans.length === 0" description="暂无家庭训练计划" :image-size="60" />
        <div v-for="plan in plans" :key="plan.id" class="aux-item">
          <div class="aux-title">{{ plan.title }}</div>
          <div class="aux-sub">{{ formatPlanExercises(plan) }}</div>
          <div v-if="plan.note" class="aux-sub">注意：{{ plan.note }}</div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="课时包">
        <div class="pane-header">
          <span>课时包</span>
          <el-button type="primary" size="small" @click="openPackageDialog">新增</el-button>
        </div>
        <el-empty v-if="packages.length === 0" description="暂无课时包" :image-size="60" />
        <div v-for="pkg in packages" :key="pkg.id" class="aux-item">
          <div class="aux-title">{{ pkg.name }}</div>
          <div class="aux-sub">
            已用 {{ pkg.used_sessions }} / 共 {{ pkg.total_sessions }}，剩余
            <el-tag type="success">{{ pkg.remaining_sessions }}</el-tag>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="回访">
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
          <el-button v-if="task.status === 'pending'" link type="primary" size="small" @click="markFollowUpDone(task)">
            标记完成
          </el-button>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 家庭训练弹窗 -->
    <el-dialog v-model="planVisible" title="新增家庭训练" width="480px">
      <el-form :model="planForm" label-width="70px">
        <el-form-item label="标题"><el-input v-model="planForm.title" /></el-form-item>
        <el-form-item label="频率"><el-input v-model="planForm.frequency" placeholder="如：每天 2 次" /></el-form-item>
        <div v-for="(ex, i) in planForm.exercises" :key="i" class="ex-row">
          <el-input v-model="ex.exercise_name" placeholder="动作" class="ex-name" />
          <el-input-number v-model="ex.sets" :min="0" placeholder="组" class="ex-num" />
          <el-input-number v-model="ex.reps" :min="0" placeholder="次" class="ex-num" />
        </div>
        <el-button link type="primary" @click="addPlanExercise">+ 添加动作</el-button>
        <el-form-item label="注意">
          <el-input v-model="planForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="planVisible = false">取消</el-button>
        <el-button type="primary" @click="savePlan">保存</el-button>
      </template>
    </el-dialog>

    <!-- 课时包弹窗 -->
    <el-dialog v-model="packageVisible" title="新增课时包" width="400px">
      <el-form :model="packageForm" label-width="70px">
        <el-form-item label="名称"><el-input v-model="packageForm.name" placeholder="如：20课时包" /></el-form-item>
        <el-form-item label="总课时"><el-input-number v-model="packageForm.total_sessions" :min="1" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="packageVisible = false">取消</el-button>
        <el-button type="primary" @click="savePackage">保存</el-button>
      </template>
    </el-dialog>

    <!-- 回访弹窗 -->
    <el-dialog v-model="followUpVisible" title="新增回访" width="400px">
      <el-form :model="followUpForm" label-width="70px">
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
        <el-button @click="followUpVisible = false">取消</el-button>
        <el-button type="primary" @click="saveFollowUp">保存</el-button>
      </template>
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

.ex-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.ex-name {
  flex: 1;
}

.ex-num {
  width: 100px;
}
</style>
