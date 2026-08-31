<script setup lang="ts">
/** 疼痛指标编辑器：使用 NRS 0～10，满分由系统规则固定。 */

import { computed } from 'vue'
import type { AssessmentMetricInput, AssessmentSide, AssessmentMetricContext } from '@/types/api'

const metric = defineModel<AssessmentMetricInput>({ required: true })

const sideOptions: Array<{ label: string; value: AssessmentSide }> = [
  { label: '左侧', value: 'left' },
  { label: '右侧', value: 'right' },
  { label: '双侧', value: 'bilateral' },
  { label: '不适用', value: 'not_applicable' },
]

const contextOptions: Array<{ label: string; value: AssessmentMetricContext }> = [
  { label: '静息时', value: 'rest' },
  { label: '活动时', value: 'activity' },
  { label: '训练前', value: 'pre_training' },
  { label: '训练后', value: 'post_training' },
  { label: '夜间', value: 'night' },
  { label: '其他场景', value: 'custom' },
]

const customContext = computed({
  get: () => String(metric.value.details?.context_label ?? ''),
  set: (value: string) => {
    metric.value.details = { ...(metric.value.details ?? {}), context_label: value }
  },
})

function setScore(value: number | number[]): void {
  metric.value.score = Array.isArray(value) ? Number(value[0]) : Number(value)
  metric.value.scale_code = 'NRS_0_10'
  metric.value.unit = 'point'
}
</script>

<template>
  <div class="metric-editor">
    <div class="form-grid">
      <el-form-item label="疼痛部位" required>
        <el-input v-model="metric.body_part" placeholder="例如：右膝前侧" />
      </el-form-item>
      <el-form-item label="侧别">
        <el-select v-model="metric.side" class="full-width" placeholder="选择侧别">
          <el-option v-for="option in sideOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
      </el-form-item>
    </div>

    <el-form-item label="什么时候测到的疼痛" required>
      <el-radio-group v-model="metric.context" class="choice-grid">
        <el-radio v-for="option in contextOptions" :key="option.value" :value="option.value">{{ option.label }}</el-radio>
      </el-radio-group>
      <el-input v-if="metric.context === 'custom'" v-model="customContext" class="custom-context" placeholder="请补充具体场景" />
    </el-form-item>

    <el-form-item label="疼痛程度" required>
      <div class="score-field">
        <div class="score-value"><strong>{{ metric.score ?? 0 }}</strong><span>分</span></div>
        <el-slider :model-value="metric.score ?? 0" :min="0" :max="10" :step="1" :show-tooltip="false" @update:model-value="setScore" />
        <div class="score-endpoints"><span>0 无痛</span><span>10 最剧烈的疼痛</span></div>
      </div>
    </el-form-item>

    <el-form-item label="疼痛性质、诱发动作或补充描述">
      <el-input v-model="metric.description" type="textarea" :rows="2" placeholder="例如：刺痛，下楼时出现；暂不清楚也可以说明" maxlength="1000" show-word-limit />
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

.choice-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
}

.choice-grid :deep(.el-radio) {
  min-height: 44px;
  margin-right: 0;
}

.custom-context {
  width: 100%;
  max-width: 360px;
  margin-top: 8px;
}

.score-field {
  width: 100%;
  padding: 2px 4px 0;
}

.score-value {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-bottom: 4px;
  color: var(--retrue-primary-dark);
}

.score-value strong {
  font-size: 28px;
}

.score-value span {
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.score-endpoints {
  display: flex;
  justify-content: space-between;
  color: var(--retrue-text-muted);
  font-size: 12px;
}

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
}
</style>
