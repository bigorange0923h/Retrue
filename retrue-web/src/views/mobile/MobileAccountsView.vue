<script setup lang="ts">
/** 移动端账号管理页：卡片列表替代桌面数据表，支持新建/编辑/启停（仅超管）。 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import { apiCreateUser, apiListUsers, apiUpdateUser } from '@/api/accounts'
import type { UserAccountItem, UserCreateForm, UserUpdateForm } from '@/types/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const loading = ref(false)
const items = ref<UserAccountItem[]>([])
const keyword = ref('')

async function loadUsers(): Promise<void> {
  loading.value = true
  try {
    const data = await apiListUsers({ keyword: keyword.value, page: 1, page_size: 50 })
    items.value = data.items
  } finally {
    loading.value = false
  }
}

// 新建账号弹窗
const createVisible = ref(false)
const createFormRef = ref<FormInstance>()
const creating = ref(false)
const createForm = reactive<UserCreateForm>({
  username: '',
  password: '',
  is_active: true,
  is_staff: false,
  is_superuser: false,
})

const createRules: FormRules = {
  username: [
    { required: true, message: '请输入登录名', trigger: 'blur' },
    { min: 2, max: 150, message: '登录名长度 2-150 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入初始密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
}

function openCreate(): void {
  createForm.username = ''
  createForm.password = ''
  createForm.is_active = true
  createForm.is_staff = false
  createForm.is_superuser = false
  createVisible.value = true
}

async function handleCreate(): Promise<void> {
  if (!createFormRef.value) return
  const valid = await createFormRef.value.validate().catch(() => false)
  if (!valid) return

  creating.value = true
  try {
    await apiCreateUser({ ...createForm })
    ElMessage.success('账号创建成功')
    createVisible.value = false
    await loadUsers()
  } finally {
    creating.value = false
  }
}

// 编辑账号弹窗
const editVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editing = ref(false)
const editingId = ref(0)
const editingSelf = ref(false)
const editForm = reactive<UserUpdateForm>({
  is_active: true,
  is_staff: false,
  is_superuser: false,
  password: '',
})

function openEdit(row: UserAccountItem): void {
  editingId.value = row.id
  editingSelf.value = row.id === userStore.currentUser?.id
  editForm.is_active = row.is_active
  editForm.is_staff = row.is_staff
  editForm.is_superuser = row.is_superuser
  editForm.password = ''
  editVisible.value = true
}

const editRules: FormRules = {
  password: [{ min: 8, message: '密码至少 8 位', trigger: 'blur' }],
}

async function handleEdit(): Promise<void> {
  if (!editFormRef.value) return
  const valid = await editFormRef.value.validate().catch(() => false)
  if (!valid) return

  editing.value = true
  try {
    const payload: UserUpdateForm = {
      is_active: editForm.is_active,
      is_staff: editForm.is_staff,
      is_superuser: editForm.is_superuser,
    }
    if (editForm.password) payload.password = editForm.password
    await apiUpdateUser(editingId.value, payload)
    ElMessage.success('账号已更新')
    editVisible.value = false
    await loadUsers()
  } finally {
    editing.value = false
  }
}

// 快捷停用/启用
async function toggleActive(row: UserAccountItem): Promise<void> {
  const next = !row.is_active
  const label = next ? '启用' : '停用'
  if (!next) {
    try {
      await ElMessageBox.confirm(`确定停用账号「${row.display_name || row.username}」吗？停用后该账号将无法登录。`, '停用确认', {
        type: 'warning',
      })
    } catch {
      return
    }
  }
  try {
    await apiUpdateUser(row.id, { is_active: next })
    ElMessage.success(`账号已${label}`)
    await loadUsers()
  } catch {
    // 错误提示已由拦截器统一处理（如不能停用最后一个超管）
  }
}

function roleTag(row: UserAccountItem): { type: 'danger' | 'warning' | 'info'; label: string } {
  if (row.is_superuser) return { type: 'danger', label: '超级管理员' }
  if (row.is_staff) return { type: 'warning', label: '后台管理' }
  return { type: 'info', label: '康复师' }
}

// 重置密码弹窗
const resetVisible = ref(false)
const resetFormRef = ref<FormInstance>()
const resetting = ref(false)
const resetTarget = ref<UserAccountItem | null>(null)
const resetForm = reactive({ password: '', confirm: '' })

const resetRules: FormRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== resetForm.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

function openReset(row: UserAccountItem): void {
  resetTarget.value = row
  resetForm.password = ''
  resetForm.confirm = ''
  resetVisible.value = true
}

async function handleReset(): Promise<void> {
  if (!resetFormRef.value || !resetTarget.value) return
  const valid = await resetFormRef.value.validate().catch(() => false)
  if (!valid) return

  resetting.value = true
  try {
    await apiUpdateUser(resetTarget.value.id, { password: resetForm.password })
    ElMessage.success(`已重置账号「${resetTarget.value.display_name || resetTarget.value.username}」的密码`)
    resetVisible.value = false
  } catch {
    // 错误提示已由拦截器统一处理
  } finally {
    resetting.value = false
  }
}

onMounted(loadUsers)
</script>

<template>
  <div class="mobile-accounts">
    <div class="account-search">
      <el-input v-model="keyword" clearable placeholder="搜索登录名或姓名" @keyup.enter="loadUsers">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="loadUsers">搜索</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="5" animated />
    <el-empty v-else-if="items.length === 0" description="暂无账号" />

    <div v-else class="account-cards">
      <el-card v-for="row in items" :key="row.id" shadow="never" class="account-card">
        <div class="account-card-header">
          <div class="account-identity">
            <strong>{{ row.display_name }}</strong>
            <span>{{ row.username }}</span>
          </div>
          <div class="account-badges">
            <el-tag :type="roleTag(row).type" size="small">{{ roleTag(row).label }}</el-tag>
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
          </div>
        </div>
        <p class="account-login">最近登录：{{ row.last_login || '从未登录' }}</p>
        <div class="account-actions">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" @click="openReset(row)">重置密码</el-button>
          <el-button v-if="row.is_active" size="small" type="warning" @click="toggleActive(row)">停用</el-button>
          <el-button v-else size="small" type="success" @click="toggleActive(row)">启用</el-button>
        </div>
      </el-card>
    </div>

    <el-button type="primary" class="create-button" @click="openCreate">新建账号</el-button>

    <el-dialog v-model="createVisible" title="新建账号">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-position="top">
        <el-form-item label="登录名" prop="username">
          <el-input v-model="createForm.username" placeholder="用于登录的用户名" />
        </el-form-item>
        <el-form-item label="初始密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item label="权限">
          <div class="perm-options">
            <el-switch v-model="createForm.is_superuser" active-text="超级管理员" />
            <el-switch v-model="createForm.is_staff" active-text="后台管理" />
            <el-switch v-model="createForm.is_active" active-text="启用" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑账号">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-position="top">
        <el-form-item label="重置密码">
          <el-input
            v-model="editForm.password"
            type="password"
            show-password
            placeholder="留空则不修改密码（至少 8 位）"
          />
        </el-form-item>
        <el-form-item label="权限">
          <div class="perm-options">
            <el-switch v-model="editForm.is_superuser" active-text="超级管理员" :disabled="editingSelf" />
            <el-switch v-model="editForm.is_staff" active-text="后台管理" :disabled="editingSelf" />
            <el-switch v-model="editForm.is_active" active-text="启用" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="handleEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码">
      <p class="reset-tip">即将为账号「{{ resetTarget?.display_name || resetTarget?.username }}」重置密码。</p>
      <el-form ref="resetFormRef" :model="resetForm" :rules="resetRules" label-position="top">
        <el-form-item label="新密码" prop="password">
          <el-input v-model="resetForm.password" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input v-model="resetForm.confirm" type="password" show-password placeholder="再次输入新密码" @keyup.enter="handleReset" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="handleReset">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mobile-accounts { display: flex; flex-direction: column; gap: 12px; padding-bottom: 24px; }
.account-search { display: flex; gap: 8px; }
.account-search :deep(.el-input) { flex: 1; }
.account-search :deep(.el-button) { flex: none; }
.account-cards { display: flex; flex-direction: column; gap: 10px; }
.account-card { border-color: var(--retrue-border); border-radius: var(--retrue-radius-md); }
.account-card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.account-identity { display: flex; min-width: 0; flex-direction: column; gap: 2px; }
.account-identity strong { color: var(--retrue-text); font-size: 15px; }
.account-identity span { color: var(--retrue-text-muted); font-size: 12px; }
.account-badges { display: flex; flex: 0 0 auto; gap: 6px; }
.account-login { margin: 8px 0 0; color: var(--retrue-text-secondary); font-size: 12px; }
.account-actions { display: flex; gap: 8px; margin-top: 10px; }
.create-button { width: 100%; height: 44px; margin: 0; }
.perm-options { display: flex; flex-wrap: wrap; gap: 16px; }
.reset-tip { margin: 0 0 12px; color: var(--retrue-text-secondary); font-size: 14px; }
</style>
