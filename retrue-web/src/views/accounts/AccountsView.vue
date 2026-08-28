<script setup lang="ts">
/** 账号管理页：系统用户的列表与维护（仅超级用户可见）。
 *
 * 提供用户列表、新建账号、编辑账号（启停/后台权限/超管权限）、重置密码。
 * 该页面的菜单入口与路由均受 is_superuser 控制，后端接口也会强校验超管权限。
 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import { apiCreateUser, apiListUsers, apiUpdateUser } from '@/api/accounts'
import type { UserAccountItem, UserCreateForm, UserUpdateForm } from '@/types/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const loading = ref(false)
const items = ref<UserAccountItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')

async function loadUsers(): Promise<void> {
  loading.value = true
  try {
    const data = await apiListUsers({
      keyword: keyword.value,
      page: page.value,
      page_size: pageSize.value,
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function handleSearch(): void {
  page.value = 1
  loadUsers()
}

function handleReset(): void {
  keyword.value = ''
  page.value = 1
  loadUsers()
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
  password: [
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
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

onMounted(loadUsers)
</script>

<template>
  <div class="accounts-page">
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索登录名或康复师姓名"
        clearable
        class="search-input"
        @keyup.enter="handleSearch"
      />
      <el-button type="primary" @click="handleSearch">查询</el-button>
      <el-button @click="handleReset">重置</el-button>
      <div class="spacer" />
      <el-button type="primary" @click="openCreate">新建账号</el-button>
    </div>

    <el-card class="table-card">
      <el-table v-loading="loading" :data="items" empty-text="暂无账号">
        <el-table-column prop="display_name" label="姓名" min-width="140" />
        <el-table-column prop="username" label="登录名" min-width="120" />
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.is_superuser" type="danger" effect="dark">超级管理员</el-tag>
            <el-tag v-else-if="row.is_staff" type="warning">后台管理</el-tag>
            <el-tag v-else type="info">康复师</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login" label="最近登录" width="160">
          <template #default="{ row }">{{ row.last_login || '从未登录' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.is_active" link type="warning" @click="toggleActive(row)">停用</el-button>
            <el-button v-else link type="success" @click="toggleActive(row)">启用</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadUsers"
        />
      </div>
    </el-card>

    <el-dialog v-model="createVisible" title="新建账号" width="520px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="90px">
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

    <el-dialog v-model="editVisible" title="编辑账号" width="520px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="90px">
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

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.perm-options {
  display: flex;
  gap: 20px;
}
</style>
