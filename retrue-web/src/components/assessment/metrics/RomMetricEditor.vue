<script setup lang="ts">
/** 关节活动度编辑器：记录实际角度和主动/被动测量方式，不设置满分。 */

import type { AssessmentMetricInput, AssessmentSide, AssessmentMeasurementMode } from '@/types/api'

const metric = defineModel<AssessmentMetricInput>({ required: true })

const sideOptions: Array<{ label: string; value: AssessmentSide }> = [
  { label: '左侧', value: 'left' },
  { label: '右侧', value: 'right' },
  { label: '双侧', value: 'bilateral' },
]

const measurementOptions: Array<{ label: string; value: AssessmentMeasurementMode }> = [
  { label: '主动活动（AROM）', value: 'active' },
  { label: '被动活动（PROM）', value: 'passive' },
]

function setScore(value: number | undefined): void {
  metric.value.score = value === undefined ? null : Number(value)
  metric.value.unit = 'degree'
  metric.value.scale_code = ''
}
</script>

<template>
  <div class="metric-editor">
    <div class="form-grid">
      <el-form-item label="关节或部位" required>
        <el-input v-model="metric.body_part" placeholder="例如：右肩" />
      </el-form-item>
      <el-form-item label="侧别" required>
        <el-select v-model="metric.side" class="full-width" placeholder="选择侧别">
          <el-option v-for="option in sideOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
      </el-form-item>
    </div>

    <el-form-item label="动作方向" required>
      <el-input v-model="metric.movement" placeholder="例如：屈曲、伸展、外旋" />
    </el-form-item>

    <el-form-item label="测量方式" required>
      <el-radio-group v-model="metric.measurement_mode" class="choice-grid">
        <el-radio v-for="option in measurementOptions" :key="option.value" :value="option.value">{{ option.label }}</el-radio>
      </el-radio-group>
    </el-form-item>

    <el-form-item label="测量结果" required>
      <div class="degree-input">
        <el-input-number :model-value="metric.score ?? undefined" :min="0" :max="360" :precision="1" :step="1" controls-position="right" placeholder="输入测得角度" @update:model-value="setScore" />
        <span>°</span>
      </div>
      <p class="field-hint">填写实际测量角度；正常参考范围由系统按关节和动作提供，仅作参考。</p>
    </el-form-item>

    <el-form-item label="补充描述">
      <el-input v-model="metric.description" type="textarea" :rows="2" placeholder="记录疼痛、终末感或测量条件" maxlength="1000" show-word-limit />
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

.degree-input {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
}

.degree-input :deep(.el-input-number) {
  width: 100%;
  max-width: 260px;
}

.degree-input > span {
  color: var(--retrue-text-secondary);
  font-size: 18px;
}

.field-hint {
  margin: 6px 0 0;
  color: var(--retrue-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }

  .degree-input :deep(.el-input-number) {
    max-width: none;
  }
}
</style>
