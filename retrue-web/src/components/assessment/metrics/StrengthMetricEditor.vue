<script setup lang="ts">
/** 肌力指标编辑器：使用 MRC 0～5 级，康复师选择临床表现。 */

import type { AssessmentMetricInput, AssessmentSide } from '@/types/api'

const metric = defineModel<AssessmentMetricInput>({ required: true })

const sideOptions: Array<{ label: string; value: AssessmentSide }> = [
  { label: '左侧', value: 'left' },
  { label: '右侧', value: 'right' },
  { label: '双侧', value: 'bilateral' },
]

const grades = [
  { value: 0, label: '无收缩', description: '未观察到肌肉收缩' },
  { value: 1, label: '轻微收缩', description: '可观察或触及轻微收缩' },
  { value: 2, label: '去重力活动', description: '去除重力后可以完成活动' },
  { value: 3, label: '克服重力', description: '可以克服重力完成活动' },
  { value: 4, label: '部分抗阻', description: '可以抵抗一定阻力，但较正常弱' },
  { value: 5, label: '肌力正常', description: '肌力正常' },
]

function selectGrade(value: number): void {
  metric.value.score = value
  metric.value.scale_code = 'MRC_0_5'
  metric.value.unit = 'grade'
}
</script>

<template>
  <div class="metric-editor">
    <div class="form-grid">
      <el-form-item label="部位或肌群" required>
        <el-input v-model="metric.body_part" placeholder="例如：右侧股四头肌" />
      </el-form-item>
      <el-form-item label="侧别" required>
        <el-select v-model="metric.side" class="full-width" placeholder="选择侧别">
          <el-option v-for="option in sideOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
      </el-form-item>
    </div>

    <el-form-item label="动作" required>
      <el-input v-model="metric.movement" placeholder="例如：膝关节伸展" />
    </el-form-item>

    <el-form-item label="肌力等级" required>
      <div class="grade-grid" role="radiogroup" aria-label="MRC 肌力等级">
        <button
          v-for="grade in grades"
          :key="grade.value"
          type="button"
          class="grade-option"
          :class="{ selected: metric.score === grade.value }"
          role="radio"
          :aria-checked="metric.score === grade.value"
          @click="selectGrade(grade.value)"
        >
          <span class="grade-number">{{ grade.value }}</span>
          <span class="grade-label">{{ grade.label }}</span>
          <small>{{ grade.description }}</small>
        </button>
      </div>
    </el-form-item>

    <el-form-item label="补充描述">
      <el-input v-model="metric.description" type="textarea" :rows="2" placeholder="记录测试姿势、疼痛或其他观察" maxlength="1000" show-word-limit />
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

.grade-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  width: 100%;
  gap: 8px;
}

.grade-option {
  display: flex;
  min-height: 108px;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  border: 1px solid var(--retrue-border);
  border-radius: var(--retrue-radius-sm);
  background: var(--retrue-surface);
  color: var(--retrue-text);
  cursor: pointer;
  font: inherit;
  padding: 8px;
  text-align: left;
}

.grade-option:hover,
.grade-option:focus-visible {
  border-color: var(--retrue-primary);
  outline: none;
}

.grade-option.selected {
  border-color: var(--retrue-primary);
  background: var(--retrue-primary-light);
  box-shadow: 0 0 0 2px rgb(7 163 88 / 12%);
}

.grade-number {
  color: var(--retrue-primary-dark);
  font-size: 20px;
  font-weight: 700;
}

.grade-label {
  font-size: 12px;
  font-weight: 600;
}

.grade-option small {
  color: var(--retrue-text-secondary);
  font-size: 11px;
  line-height: 1.4;
}

@media (max-width: 900px) {
  .grade-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }

  .grade-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .grade-option {
    min-height: 92px;
  }
}
</style>
