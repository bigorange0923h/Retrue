<script setup lang="ts">
/** PC 与移动端共用的补充记录入口面板。 */

import { useRouter } from 'vue-router'

const props = withDefaults(defineProps<{ mode?: 'desktop' | 'mobile' }>(), {
  mode: 'mobile',
})
const visible = defineModel<boolean>({ default: false })
const router = useRouter()

/** 进入记录任务，并关闭入口面板。 */
function goTo(name: string, query?: Record<string, string>): void {
  visible.value = false
  router.push({ name, query })
}
</script>

<template>
  <el-drawer
    v-model="visible"
    :direction="props.mode === 'mobile' ? 'btt' : 'rtl'"
    :size="props.mode === 'mobile' ? 'auto' : '380px'"
    :with-header="false"
    class="quick-record-drawer"
  >
    <div class="quick-record-panel">
      <div class="quick-record-heading">
        <h3>补充记录</h3>
        <p>选择本次要完成的记录任务。</p>
      </div>

      <el-button type="primary" class="quick-record-action" @click="goTo('ai-draft')">
        <span class="quick-record-action-content">
          <el-icon><EditPen /></el-icon>
          <span class="quick-record-action-text"><strong>AI 统一补记</strong><small>使用自然语言快速整理训练记录</small></span>
        </span>
      </el-button>
      <el-button class="quick-record-action" @click="goTo('customer-list')">
        <span class="quick-record-action-content">
          <el-icon><User /></el-icon>
          <span class="quick-record-action-text"><strong>单客户记录</strong><small>选择客户后补充训练记录</small></span>
        </span>
      </el-button>
      <el-button class="quick-record-action" @click="goTo('customer-list', { mode: 'initial' })">
        <span class="quick-record-action-content">
          <el-icon><DocumentChecked /></el-icon>
          <span class="quick-record-action-text"><strong>首次评估</strong><small>选择客户后创建首次评估</small></span>
        </span>
      </el-button>
    </div>
  </el-drawer>
</template>

<style scoped>
.quick-record-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 4px 20px;
}

.quick-record-heading h3 {
  margin: 0;
  color: var(--retrue-text);
  font-size: 18px;
}

.quick-record-heading p {
  margin: 4px 0 10px;
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.quick-record-action {
  width: 100%;
  height: auto;
  min-height: 58px;
  justify-content: flex-start;
  margin: 0;
  padding: 10px 14px;
}

.quick-record-action-content {
  display: flex;
  width: 100%;
  align-items: center;
}

.quick-record-action-content .el-icon {
  flex: 0 0 auto;
  font-size: 20px;
}

.quick-record-action-text {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
  margin-left: 8px;
  text-align: left;
}

.quick-record-action-text strong {
  font-size: 14px;
  font-weight: 600;
}

.quick-record-action-text small {
  color: inherit;
  font-size: 12px;
  font-weight: 400;
  opacity: 0.72;
}
</style>
