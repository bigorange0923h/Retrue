<script setup lang="ts">
/** 特殊测试编辑器：记录测试名称和分类结果，不要求数字评分。 */

import { computed } from 'vue'
import type { AssessmentMetricInput, AssessmentSide } from '@/types/api'

const metric = defineModel<AssessmentMetricInput>({ required: true })

const sideOptions: Array<{ label: string; value: AssessmentSide }> = [
  { label: '左侧', value: 'left' },
  { label: '右侧', value: 'right' },
  { label: '双侧', value: 'bilateral' },
  { label: '不适用', value: 'not_applicable' },
]

const testName = computed({
  get: () => String(metric.value.details?.test_name ?? ''),
  set: (value: string) => {
    metric.value.details = { ...(metric.value.details ?? {}), test_name: value }
  },
})
</script>

<template>
  <div class="metric-editor">
    <el-form-item label="测试名称" required>
      <el-input v-model="testName" placeholder="例如：Lachman 测试、抽屉试验" />
    </el-form-item>

    <div class="form-grid">
      <el-form-item label="部位">
        <el-input v-model="metric.body_part" placeholder="例如：右膝" />
      </el-form-item>
      <el-form-item label="侧别">
        <el-select v-model="metric.side" class="full-width" placeholder="选择侧别">
          <el-option v-for="option in sideOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
      </el-form-item>
    </div>

    <el-form-item label="测试结果" required>
      <el-radio-group v-model="metric.result_code" class="result-grid">
        <el-radio-button value="negative">阴性</el-radio-button>
        <el-radio-button value="positive">阳性</el-radio-button>
        <el-radio-button value="uncertain">无法判断</el-radio-button>
      </el-radio-group>
    </el-form-item>

    <el-form-item label="症状、终末感及补充描述">
      <el-input v-model="metric.description" type="textarea" :rows="3" placeholder="记录测试过程中的症状、终末感和观察结果" maxlength="1200" show-word-limit />
    </el-form-item>
  </div>
</template>

<style scoped>
.metric-editor {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.full-width {
  width: 100%;
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

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }

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
