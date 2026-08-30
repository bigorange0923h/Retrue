<script setup lang="ts">
/** 移动端课程模板页：卡片列表替代桌面数据表，支持新建/编辑/启停。 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { apiCreateCourseType, apiListCourseTypes, apiUpdateCourseType } from '@/api/courses'
import type { CourseType } from '@/types/api'

const loading = ref(false)
const items = ref<CourseType[]>([])
const keyword = ref('')

async function loadTypes(): Promise<void> {
  loading.value = true
  try {
    items.value = await apiListCourseTypes(keyword.value)
  } finally {
    loading.value = false
  }
}

// 新建/编辑弹窗
const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  description: '',
  default_duration: null as number | null,
  default_session_cost: 1.0,
  default_goals: '',
  is_active: true,
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入课程模板名称', trigger: 'blur' }],
  default_session_cost: [{ required: true, message: '请输入单节课时消耗', trigger: 'blur' }],
}

function openCreate(): void {
  editingId.value = null
  form.name = ''
  form.description = ''
  form.default_duration = null
  form.default_session_cost = 1.0
  form.default_goals = ''
  form.is_active = true
  dialogVisible.value = true
}

function openEdit(row: CourseType): void {
  editingId.value = row.id
  form.name = row.name
  form.description = row.description
  form.default_duration = row.default_duration
  form.default_session_cost = row.default_session_cost
  form.default_goals = row.default_goals
  form.is_active = row.is_active
  dialogVisible.value = true
}

async function handleSave(): Promise<void> {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const payload = { ...form }
    if (editingId.value) {
      await apiUpdateCourseType(editingId.value, payload)
      ElMessage.success('课程模板已更新')
    } else {
      await apiCreateCourseType(payload)
      ElMessage.success('课程模板创建成功')
    }
    dialogVisible.value = false
    await loadTypes()
  } finally {
    saving.value = false
  }
}

async function toggleActive(row: CourseType): Promise<void> {
  try {
    await apiUpdateCourseType(row.id, { is_active: !row.is_active })
    ElMessage.success(row.is_active ? '已停用' : '已启用')
    await loadTypes()
  } catch {
    // 错误提示由请求拦截器统一处理。
  }
}

onMounted(loadTypes)
</script>

<template>
  <div class="mobile-course-types">
    <div class="type-search">
      <el-input v-model="keyword" clearable placeholder="搜索课程模板名称" @keyup.enter="loadTypes">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="loadTypes">搜索</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="5" animated />
    <el-empty v-else-if="items.length === 0" description="暂无课程模板" />

    <div v-else class="type-cards">
      <el-card v-for="row in items" :key="row.id" shadow="never" class="type-card">
        <div class="type-card-header">
          <strong>{{ row.name }}</strong>
          <el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.status_display }}</el-tag>
        </div>
        <p class="type-desc">{{ row.description || '暂无简介' }}</p>
        <div class="type-meta">
          <span>{{ row.default_session_cost }} 课时/节</span>
          <span>{{ row.default_duration ? `${row.default_duration} 分钟` : '时长未设' }}</span>
          <span>{{ row.course_count }} 个计划内课程</span>
        </div>
        <div class="type-actions">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button v-if="row.is_active" size="small" type="warning" @click="toggleActive(row)">停用</el-button>
          <el-button v-else size="small" type="success" @click="toggleActive(row)">启用</el-button>
        </div>
      </el-card>
    </div>

    <el-button type="primary" class="create-button" @click="openCreate">新建课程模板</el-button>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑课程模板' : '新建课程模板'">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：膝关节术后力量重建" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.description" placeholder="简要说明该课程模板" />
        </el-form-item>
        <el-form-item label="默认课时消耗" prop="default_session_cost">
          <el-input-number v-model="form.default_session_cost" :min="0.5" :step="0.5" :precision="1" />
          <span class="field-hint">半课 0.5 / 全课 1.0</span>
        </el-form-item>
        <el-form-item label="默认时长（分钟）">
          <el-input-number v-model="form.default_duration" :min="0" :step="15" placeholder="可空" />
        </el-form-item>
        <el-form-item label="课程目标">
          <el-input v-model="form.default_goals" type="textarea" :rows="2" placeholder="默认课程目标" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" active-text="启用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mobile-course-types { display: flex; flex-direction: column; gap: 12px; padding-bottom: 24px; }
.type-search { display: flex; gap: 8px; }
.type-search :deep(.el-input) { flex: 1; }
.type-search :deep(.el-button) { flex: none; }
.type-cards { display: flex; flex-direction: column; gap: 10px; }
.type-card { border-color: var(--retrue-border); border-radius: var(--retrue-radius-md); }
.type-card-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.type-card-header strong { color: var(--retrue-text); font-size: 15px; }
.type-desc { margin: 6px 0; color: var(--retrue-text-secondary); font-size: 13px; }
.type-meta { display: flex; flex-wrap: wrap; gap: 8px 14px; color: var(--retrue-text-muted); font-size: 12px; }
.type-actions { display: flex; gap: 8px; margin-top: 10px; }
.create-button { width: 100%; height: 44px; margin: 0; }
.field-hint { margin-left: 8px; color: var(--retrue-text-muted); font-size: 12px; }
</style>
