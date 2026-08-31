<script setup lang="ts">
/** 功能动作编辑器：观察完成质量，不使用通用数字满分。 */

import { computed } from 'vue'
import type { AssessmentMetricInput } from '@/types/api'

const metric = defineModel<AssessmentMetricInput>({ required: true })

const painStatus = computed({
  get: () => String(metric.value.details?.pain_status ?? ''),
  set: (value: string) => {
    metric.value.details = { ...(metric.value.details ?? {}), pain_status: value }
  },
})
</script>

<template>
  <div class="metric-editor">
    <el-form-item label="动作名称" required>
      <el-input v-model="metric.movement" placeholder="例如：单腿蹲、起立、步行" />
    </el-form-item>

    <el-form-item label="完成情况" required>
      <el-radio-group v-model="metric.result_code" class="result-grid">
        <el-radio-button value="normal">正常完成</el-radio-button>
        <el-radio-button value="limited">受限完成</el-radio-button>
        <el-radio-button value="unable">无法完成</el-radio-button>
      </el-radio-group>
    </el-form-item>

    <el-form-item label="是否诱发疼痛">
      <el-radio-group v-model="painStatus" class="choice-grid">
        <el-radio value="none">无</el-radio>
        <el-radio value="present">有</el-radio>
        <el-radio value="uncertain">不确定</el-radio>
      </el-radio-group>
    </el-form-item>

    <el-form-item label="动作表现与观察描述">
      <el-input v-model="metric.description" type="textarea" :rows="3" placeholder="记录稳定性、代偿、活动质量等，例如：膝内扣、躯干代偿" maxlength="1200" show-word-limit />
    </el-form-item>
  </div>
</template>

<style scoped>
.metric-editor {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.result-grid {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
}

.result-grid :deep(.el-radio-button) {
  flex: 1;
  min-width: 110px;
}

.result-grid :deep(.el-radio-button__inner) {
  width: 100%;
  min-height: 44px;
  padding: 12px 16px;
}

.choice-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
}

.choice-grid :deep(.el-radio) {
  min-height: 44px;
  margin-right: 0;
}

@media (max-width: 768px) {
  .result-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
  }

  .result-grid :deep(.el-radio-button) {
    min-width: 0;
  }
}
</style>
