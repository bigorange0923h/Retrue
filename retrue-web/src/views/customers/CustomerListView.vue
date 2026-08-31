<script setup lang="ts">
/** 客户列表页：展示当前康复师的客户，支持搜索、状态筛选与新增。 */

import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance } from 'element-plus'

import {
  apiCreateCustomer,
  apiListCustomers,
  type CustomerForm,
} from '@/api/customers'
import { apiGetInitialAssessment } from '@/api/assessments'
import type { CustomerListItem } from '@/types/api'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const items = ref<CustomerListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const statusFilter = ref('')

// 新增客户弹窗
const createVisible = ref(false)
const createFormRef = ref<FormInstance>()
const creating = ref(false)
const createForm = reactive<CustomerForm>({
  name: '',
  phone: '',
  gender: '',
  main_issue: '',
})

async function loadCustomers(): Promise<void> {
  loading.value = true
  try {
    const data = await apiListCustomers({
      keyword: keyword.value,
      status: statusFilter.value,
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
  loadCustomers()
}

function handleReset(): void {
  keyword.value = ''
  statusFilter.value = ''
  page.value = 1
  loadCustomers()
}

function openCreate(): void {
  createForm.name = ''
  createForm.phone = ''
  createForm.gender = ''
  createForm.main_issue = ''
  createVisible.value = true
}

async function handleCreate(): Promise<void> {
  if (!createFormRef.value) return
  const valid = await createFormRef.value.validate().catch(() => false)
  if (!valid) return

  creating.value = true
  try {
    const customer = await apiCreateCustomer({ ...createForm })
    ElMessage.success('客户创建成功')
    createVisible.value = false
    await loadCustomers()
    if (route.query.mode === 'initial' || route.query.action === 'initial-assessment') {
      router.push({ name: 'assessment-edit', query: { customerId: customer.id, mode: 'initial' } })
    } else {
      router.push({ name: 'customer-detail', params: { id: customer.id } })
    }
  } finally {
    creating.value = false
  }
}

async function goDetail(row: CustomerListItem): Promise<void> {
  const initialFlow = route.query.mode === 'initial' || route.query.action === 'initial-assessment'
  if (initialFlow) {
    try {
      const initial = await apiGetInitialAssessment(row.id)
      if (initial.exists) {
        ElMessage.info(initial.status === 'draft' ? '已打开尚未完成的首次评估' : '该客户已完成首次评估，已打开原评估记录')
        await router.push({ name: 'assessment-revise', params: { id: initial.assessment_id } })
      } else {
        await router.push({ name: 'assessment-edit', query: { customerId: row.id, mode: 'initial' } })
      }
    } catch {
      // API 拦截器已提示错误，停留在客户列表供康复师重试。
    }
    return
  }
  router.push({ name: 'customer-detail', params: { id: row.id } })
}

/** 操作列始终进入客户档案，不受“选择客户去首次评估”模式影响。 */
function openCustomerDetail(row: CustomerListItem): void {
  router.push({ name: 'customer-detail', params: { id: row.id } })
}

onMounted(loadCustomers)
</script>

<template>
  <div class="customer-list-page">
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索客户姓名"
        clearable
        class="search-input"
        @keyup.enter="handleSearch"
      />
      <el-select v-model="statusFilter" placeholder="全部状态" clearable class="status-select" @change="handleSearch">
        <el-option label="正常" value="active" />
        <el-option label="暂停" value="paused" />
        <el-option label="结案" value="closed" />
      </el-select>
      <el-button type="primary" @click="handleSearch">查询</el-button>
      <el-button @click="handleReset">重置</el-button>
      <div class="spacer" />
      <el-button type="primary" @click="openCreate">新增客户</el-button>
    </div>

    <el-card class="table-card">
      <el-table
        v-loading="loading"
        :data="items"
        empty-text="暂无客户，点击右上角新增"
        row-class-name="clickable-customer-row"
        @row-click="goDetail"
      >
        <el-table-column prop="name" label="姓名" min-width="120">
          <template #default="{ row }">
            <el-link type="primary" @click.stop="goDetail(row)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="phone_masked" label="手机号" width="140" />
        <el-table-column prop="gender_display" label="性别" width="80" />
        <el-table-column prop="main_issue" label="主要问题" min-width="160" show-overflow-tooltip />
        <el-table-column prop="status_display" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : row.status === 'paused' ? 'warning' : 'info'">
              {{ row.status_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="first_visit_date" label="首次到店" width="120" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openCustomerDetail(row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadCustomers"
        />
      </div>
    </el-card>

    <el-dialog v-model="createVisible" title="新增客户" width="480px">
      <el-form ref="createFormRef" :model="createForm" label-width="80px">
        <el-form-item label="姓名" prop="name" :rules="[{ required: true, message: '请输入客户姓名' }]">
          <el-input v-model="createForm.name" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="createForm.phone" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="性别" prop="gender">
          <el-select v-model="createForm.gender" placeholder="选择性别" class="full-width">
            <el-option label="男" value="male" />
            <el-option label="女" value="female" />
          </el-select>
        </el-form-item>
        <el-form-item label="主要问题" prop="main_issue">
          <el-input v-model="createForm.main_issue" placeholder="请输入当前主要康复问题" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
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
  width: 240px;
}

.status-select {
  width: 140px;
}

.spacer {
  flex: 1;
}

.table-card {
  border-radius: var(--retrue-radius-lg);
  border: 1px solid var(--retrue-border);
  box-shadow: var(--retrue-shadow);
}

.table-card :deep(.clickable-customer-row) {
  cursor: pointer;
}

.table-card :deep(.clickable-customer-row:hover > td.el-table__cell) {
  background: var(--retrue-primary-light);
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.full-width {
  width: 100%;
}
</style>
