<script setup lang="ts">
/** 客户疗程管理页：将课程类型分配给客户形成个体化执行单元。 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import {
  apiCreateCustomerCourse,
  apiListCourseTypes,
  apiListCustomerCourses,
  apiUpdateCustomerCourse,
} from '@/api/courses'
import { apiListCoursePackages } from '@/api/coursePackages'
import { apiListCustomers } from '@/api/customers'
import type { CoursePackage, CourseType, CustomerCourse, CustomerCourseStatus, CustomerListItem } from '@/types/api'

const loading = ref(false)
const items = ref<CustomerCourse[]>([])
const statusFilter = ref('')

async function loadCourses(): Promise<void> {
  loading.value = true
  try {
    items.value = await apiListCustomerCourses({ status: statusFilter.value || undefined })
  } finally {
    loading.value = false
  }
}

// 弹窗
const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)

const customers = ref<CustomerListItem[]>([])
const courseTypes = ref<CourseType[]>([])
const packages = ref<CoursePackage[]>([])

const form = reactive({
  customer: null as number | null,
  course_type: null as number | null,
  package: null as number | null,
  start_date: '' as string,
  end_date: '' as string,
  status: 'pending' as CustomerCourseStatus,
  individual_goals: '',
  planned_sessions: null as number | null,
  session_cost: 1.0,
  duration: null as number | null,
})

const rules: FormRules = {
  customer: [{ required: true, message: '请选择客户', trigger: 'change' }],
  course_type: [{ required: true, message: '请选择课程类型', trigger: 'change' }],
}

const statusOptions: Array<{ value: CustomerCourseStatus; label: string }> = [
  { value: 'pending', label: '待开始' },
  { value: 'active', label: '进行中' },
  { value: 'paused', label: '暂停' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
]

async function prepareOptions(): Promise<void> {
  const [c, t] = await Promise.all([apiListCustomers({ page: 1, page_size: 200 }), apiListCourseTypes()])
  customers.value = c.items
  courseTypes.value = t
}

async function handleCustomerChange(): Promise<void> {
  form.package = null
  if (form.customer) {
    packages.value = await apiListCoursePackages(form.customer)
  } else {
    packages.value = []
  }
}

function openCreate(): void {
  editingId.value = null
  form.customer = null
  form.course_type = null
  form.package = null
  form.start_date = ''
  form.end_date = ''
  form.status = 'pending'
  form.individual_goals = ''
  form.planned_sessions = null
  form.session_cost = 1.0
  form.duration = null
  dialogVisible.value = true
}

async function openEdit(row: CustomerCourse): Promise<void> {
  editingId.value = row.id
  form.customer = row.customer
  form.course_type = row.course_type
  form.package = row.package
  form.start_date = row.start_date ?? ''
  form.end_date = row.end_date ?? ''
  form.status = row.status
  form.individual_goals = row.individual_goals
  form.planned_sessions = row.planned_sessions
  form.session_cost = row.session_cost
  form.duration = row.duration
  if (row.customer) {
    packages.value = await apiListCoursePackages(row.customer)
  }
  dialogVisible.value = true
}

async function handleSave(): Promise<void> {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const payload = {
      customer: form.customer as number,
      course_type: form.course_type as number,
      package: form.package,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      status: form.status,
      individual_goals: form.individual_goals,
      planned_sessions: form.planned_sessions,
      session_cost: form.session_cost,
      duration: form.duration,
    }
    if (editingId.value) {
      await apiUpdateCustomerCourse(editingId.value, payload)
      ElMessage.success('客户疗程已更新')
    } else {
      await apiCreateCustomerCourse(payload)
      ElMessage.success('客户疗程创建成功')
    }
    dialogVisible.value = false
    await loadCourses()
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadCourses()
  prepareOptions()
})
</script>

<template>
  <div class="customer-course-page">
    <div class="toolbar">
      <el-select v-model="statusFilter" placeholder="全部状态" clearable class="status-select" @change="loadCourses">
        <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <div class="spacer" />
      <el-button type="primary" @click="openCreate">新建客户疗程</el-button>
    </div>

    <el-card class="table-card">
      <el-table v-loading="loading" :data="items" empty-text="暂无客户疗程">
        <el-table-column prop="customer_name" label="客户" min-width="110" />
        <el-table-column prop="course_type_name" label="课程类型" min-width="160" />
        <el-table-column prop="package_name" label="课时包" min-width="120">
          <template #default="{ row }">{{ row.package_name || '—' }}</template>
        </el-table-column>
        <el-table-column prop="session_cost" label="课时消耗" width="100">
          <template #default="{ row }">{{ row.session_cost }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="start_date" label="开始日期" width="110" />
        <el-table-column prop="end_date" label="结束日期" width="110" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑客户疗程' : '新建客户疗程'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="客户" prop="customer">
          <el-select v-model="form.customer" placeholder="选择客户" filterable @change="handleCustomerChange">
            <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="课程类型" prop="course_type">
          <el-select v-model="form.course_type" placeholder="选择课程类型">
            <el-option
              v-for="t in courseTypes"
              :key="t.id"
              :label="t.name"
              :value="t.id"
              :disabled="!t.is_active"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="课时包">
          <el-select v-model="form.package" placeholder="选择该客户课时包（可空）" clearable>
            <el-option
              v-for="p in packages"
              :key="p.id"
              :label="`${p.name}（余 ${p.remaining_sessions}）`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status">
            <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" placeholder="可空" />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker v-model="form.end_date" type="date" value-format="YYYY-MM-DD" placeholder="可空" />
        </el-form-item>
        <el-form-item label="单节课时消耗">
          <el-input-number v-model="form.session_cost" :min="0.5" :step="0.5" :precision="1" />
        </el-form-item>
        <el-form-item label="计划课次/课时">
          <el-input-number v-model="form.planned_sessions" :min="0" :step="0.5" :precision="1" placeholder="可空" />
        </el-form-item>
        <el-form-item label="单节时长（分钟）">
          <el-input-number v-model="form.duration" :min="0" :step="15" placeholder="可空" />
        </el-form-item>
        <el-form-item label="个体化目标">
          <el-input v-model="form.individual_goals" type="textarea" :rows="2" placeholder="个体化康复目标" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts">
export default {
  methods: {
    statusTag(status: string) {
      switch (status) {
        case 'active':
          return 'success'
        case 'pending':
          return 'warning'
        case 'paused':
          return 'info'
        case 'completed':
          return 'primary'
        default:
          return 'danger'
      }
    },
  },
}
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  background: var(--retrue-surface);
  border: 1px solid var(--retrue-border);
  border-radius: var(--retrue-radius-md);
  padding: 12px 16px;
  box-shadow: var(--retrue-shadow);
}

.status-select {
  width: 160px;
}

.spacer {
  flex: 1;
}

.table-card {
  border-radius: var(--retrue-radius-lg);
  border: 1px solid var(--retrue-border);
  box-shadow: var(--retrue-shadow);
}

.field-hint {
  margin-left: 8px;
  color: var(--retrue-text-muted);
  font-size: 12px;
}
</style>
