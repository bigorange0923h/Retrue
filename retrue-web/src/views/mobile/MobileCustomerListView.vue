<script setup lang="ts">
/** 小程序式客户页：使用卡片列表替代桌面端数据表。 */

import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { apiGetInitialAssessment } from '@/api/assessments'
import { apiListCustomers } from '@/api/customers'
import type { CustomerListItem } from '@/types/api'

const route = useRoute()
const router = useRouter()
const keyword = ref('')
const loading = ref(false)
const customers = ref<CustomerListItem[]>([])

/** 按姓名查询当前康复师的客户。 */
async function loadCustomers(): Promise<void> {
  loading.value = true
  try { customers.value = (await apiListCustomers({ keyword: keyword.value, page: 1, page_size: 50 })).items } finally { loading.value = false }
}

async function goDetail(customer: CustomerListItem): Promise<void> {
  const initialFlow = route.query.mode === 'initial' || route.query.action === 'initial-assessment'
  if (!initialFlow) {
    await router.push({ name: 'customer-detail', params: { id: customer.id } })
    return
  }

  const initial = await apiGetInitialAssessment(customer.id)
  if (initial.exists) {
    ElMessage.info(initial.status === 'draft' ? '已打开尚未完成的首次评估' : '该客户已完成首次评估，已打开原评估记录')
    await router.push({ name: 'assessment-revise', params: { id: initial.assessment_id } })
  } else {
    await router.push({ name: 'assessment-edit', query: { customerId: customer.id, mode: 'initial' } })
  }
}

onMounted(loadCustomers)
</script>

<template>
  <div class="mobile-customers">
    <div class="customer-search"><el-input v-model="keyword" clearable placeholder="搜索客户姓名" @keyup.enter="loadCustomers"><template #prefix><el-icon><Search /></el-icon></template></el-input><el-button type="primary" @click="loadCustomers">搜索</el-button></div>
    <el-skeleton v-if="loading" :rows="5" animated />
    <el-empty v-else-if="customers.length === 0" description="暂无匹配客户" />
    <div v-else class="customer-cards">
      <el-card v-for="customer in customers" :key="customer.id" shadow="never" class="customer-card" @click="goDetail(customer)">
        <div class="customer-avatar">{{ customer.name.slice(0, 1) }}</div><div class="customer-info"><div><strong>{{ customer.name }}</strong><span>{{ customer.gender_display || '未填写性别' }}</span></div><p>{{ customer.main_issue || '暂未填写主要问题' }}</p><small>{{ customer.phone_masked }}</small></div><el-tag size="small" :type="customer.status === 'active' ? 'success' : customer.status === 'paused' ? 'warning' : 'info'">{{ customer.status_display }}</el-tag>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.customer-search { display: flex; gap: 8px; margin-bottom: 16px; }.customer-search :deep(.el-input) { flex: 1; }.customer-search :deep(.el-button) { flex: none; }.customer-cards { display: flex; flex-direction: column; gap: 10px; }.customer-card { border-color: var(--retrue-border); border-radius: var(--retrue-radius-md); cursor: pointer; }.customer-card :deep(.el-card__body) { display: flex; align-items: center; gap: 12px; padding: 14px; }.customer-avatar { display: grid; flex: 0 0 auto; width: 40px; height: 40px; place-items: center; border-radius: 50%; background: var(--retrue-primary-light); color: var(--retrue-primary); font-weight: 700; }.customer-info { min-width: 0; flex: 1; }.customer-info div { display: flex; align-items: center; gap: 8px; }.customer-info span, .customer-info small { color: var(--retrue-text-muted); font-size: 12px; }.customer-info p { overflow: hidden; margin: 4px 0; color: var(--retrue-text-secondary); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
</style>
