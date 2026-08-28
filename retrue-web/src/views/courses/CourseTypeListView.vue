<script setup lang="ts">
/** 课程类型管理页：康复师维护的可复用课程目录。 */

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

function handleSearch(): void {
  loadTypes()
}

function handleReset(): void {
  keyword.value = ''
  loadTypes()
}

// 新建弹窗
const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  description: '',
  default_duration: null as number | null,
  default_session_cost: 1.0,
  default_stage: '',
  default_goals: '',
  default_notes: '',
  is_active: true,
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入课程类型名称', trigger: 'blur' }],
  default_session_cost: [{ required: true, message: '请输入单节课时消耗', trigger: 'blur' }],
}

function openCreate(): void {
  editingId.value = null
  form.name = ''
  form.description = ''
  form.default_duration = null
  form.default_session_cost = 1.0
  form.default_stage = ''
  form.default_goals = ''
  form.default_notes = ''
  form.is_active = true
  dialogVisible.value = true
}

function openEdit(row: CourseType): void {
  editingId.value = row.id
  form.name = row.name
  form.description = row.description
  form.default_duration = row.default_duration
  form.default_session_cost = row.default_session_cost
  form.default_stage = row.default_stage
  form.default_goals = row.default_goals
  form.default_notes = row.default_notes
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
      ElMessage.success('课程类型已更新')
    } else {
      await apiCreateCourseType(payload)
      ElMessage.success('课程类型创建成功')
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
    // 错误提示由拦截器处理（如被疗程引用不能停用）
  }
}

onMounted(loadTypes)
</script>

<template>
  <div class="course-type-page">
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索课程类型名称"
        clearable
        class="search-input"
        @keyup.enter="handleSearch"
      />
      <el-button type="primary" @click="handleSearch">查询</el-button>
      <el-button @click="handleReset">重置</el-button>
      <div class="spacer" />
      <el-button type="primary" @click="openCreate">新建课程类型</el-button>
    </div>

    <el-card class="table-card">
      <el-table v-loading="loading" :data="items" empty-text="暂无课程类型">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="description" label="简介" min-width="200" show-overflow-tooltip />
        <el-table-column prop="default_session_cost" label="课时消耗" width="100">
          <template #default="{ row }">{{ row.default_session_cost }} 课时</template>
        </el-table-column>
        <el-table-column label="时长" width="90">
          <template #default="{ row }">{{ row.default_duration ? `${row.default_duration} 分钟` : '—' }}</template>
        </el-table-column>
        <el-table-column prop="default_stage" label="适用阶段" width="120" />
        <el-table-column prop="course_count" label="疗程数" width="80" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.is_active" link type="warning" @click="toggleActive(row)">停用</el-button>
            <el-button v-else link type="success" @click="toggleActive(row)">启用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑课程类型' : '新建课程类型'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：膝关节术后力量重建" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.description" placeholder="简要说明该课程类型" />
        </el-form-item>
        <el-form-item label="默认课时消耗" prop="default_session_cost">
          <el-input-number v-model="form.default_session_cost" :min="0.5" :step="0.5" :precision="1" />
          <span class="field-hint">半课 0.5 / 全课 1.0</span>
        </el-form-item>
        <el-form-item label="默认时长（分钟）">
          <el-input-number v-model="form.default_duration" :min="0" :step="15" placeholder="可空" />
        </el-form-item>
        <el-form-item label="适用阶段">
          <el-input v-model="form.default_stage" placeholder="如：力量重建期" />
        </el-form-item>
        <el-form-item label="课程目标">
          <el-input v-model="form.default_goals" type="textarea" :rows="2" placeholder="默认课程目标" />
        </el-form-item>
        <el-form-item label="注意事项">
          <el-input v-model="form.default_notes" type="textarea" :rows="2" placeholder="默认注意事项" />
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

.search-input {
  width: 260px;
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
