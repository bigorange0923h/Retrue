<script setup lang="ts">
/**
 * 旧 AI 草稿地址的兼容组件。
 *
 * 新入口统一使用 /assistant；保留该组件是为了兼容仍直接引用旧页面的外部
 * 链接，并复用统一训练草稿工作区，避免两套表单和确认逻辑继续分叉。
 */

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import TrainingDraftPanel from '@/components/assistant/TrainingDraftPanel.vue'

const route = useRoute()
const router = useRouter()

function readNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const item = Array.isArray(value) ? value[0] : value
    const parsed = Number(item)
    if (Number.isFinite(parsed) && parsed > 0) return parsed
  }
  return null
}

const customerId = computed(() => readNumber(route.query.customerId, route.query.customer_id))
const courseSessionId = computed(() => readNumber(route.query.courseSessionId, route.query.course_session_id))

function goCustomer(_draft: unknown, id: number): void {
  void router.push({ name: 'customer-detail', params: { id } })
}
</script>

<template>
  <div class="legacy-ai-draft-page">
    <TrainingDraftPanel
      :customer-id="customerId"
      :course-session-id="courseSessionId"
      topic="智能补记"
      @confirmed="goCustomer"
    />
  </div>
</template>

<style scoped>
.legacy-ai-draft-page { width: 100%; max-width: 860px; margin: 0 auto; }
</style>
