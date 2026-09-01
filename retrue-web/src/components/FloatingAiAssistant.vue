<script setup lang="ts">
/** 桌面端统一助理入口：不再维护独立聊天状态，始终进入 /assistant。 */

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const isAssistantPage = computed(() => route.name === 'assistant')
const customerId = computed(() => {
  const value = route.name === 'customer-detail' ? route.params.id : route.query.customerId || route.query.customer_id
  const parsed = Number(Array.isArray(value) ? value[0] : value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
})

/** 打开统一助理，并沿用当前页面的客户上下文。 */
function openAssistant(): void {
  const query: Record<string, string> = { mode: 'chat', theme: 'smart' }
  if (customerId.value) query.customerId = String(customerId.value)
  void router.push({ name: 'assistant', query })
}
</script>

<template>
  <el-button
    v-if="!isAssistantPage"
    class="assistant-fab"
    type="primary"
    circle
    size="large"
    aria-label="打开智能助理"
    @click="openAssistant"
  >
    <el-icon :size="22"><ChatDotRound /></el-icon>
  </el-button>
</template>

<style scoped>
.assistant-fab { position: fixed; right: 30px; bottom: 28px; z-index: 1000; width: 52px; height: 52px; box-shadow: var(--retrue-shadow-brand); }

@media (max-width: 768px) {
  .assistant-fab { display: none; }
}
</style>
