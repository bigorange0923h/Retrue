<script setup lang="ts">
/** 指标类型选择器：先选要记录的临床项目，再进入对应编辑器。 */

import type { MetricType } from '@/types/api'

const props = withDefaults(
  defineProps<{
    modelValue: MetricType
    options?: Array<{ label: string; value: MetricType; hint?: string }>
  }>(),
  {
    options: () => [
      { label: '疼痛', value: 'pain', hint: '0～10 的疼痛程度' },
      { label: '肌力', value: 'strength', hint: '0～5 级肌力表现' },
      { label: '活动度', value: 'rom', hint: '测量关节角度' },
      { label: '特殊测试', value: 'special_test', hint: '阳性、阴性或无法判断' },
      { label: '功能动作', value: 'functional', hint: '正常、受限或无法完成' },
    ],
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: MetricType]
}>()
</script>

<template>
  <div class="metric-type-picker" role="radiogroup" aria-label="评估项目类型">
    <button
      v-for="option in props.options"
      :key="option.value"
      type="button"
      class="metric-type-option"
      :class="{ selected: option.value === props.modelValue }"
      role="radio"
      :aria-checked="option.value === props.modelValue"
      @click="emit('update:modelValue', option.value)"
    >
      <span class="metric-type-name">{{ option.label }}</span>
      <small>{{ option.hint }}</small>
    </button>
  </div>
</template>

<style scoped>
.metric-type-picker {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.metric-type-option {
  display: flex;
  min-height: 82px;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  border: 1px solid var(--retrue-border);
  border-radius: var(--retrue-radius-md);
  background: var(--retrue-surface);
  color: var(--retrue-text);
  cursor: pointer;
  font: inherit;
  padding: 10px;
  text-align: left;
  transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}

.metric-type-option:hover,
.metric-type-option:focus-visible {
  border-color: var(--retrue-primary);
  outline: none;
}

.metric-type-option.selected {
  border-color: var(--retrue-primary);
  background: var(--retrue-primary-light);
  box-shadow: 0 0 0 2px rgb(7 163 88 / 12%);
}

.metric-type-name {
  font-size: 14px;
  font-weight: 600;
}

.metric-type-option small {
  color: var(--retrue-text-secondary);
  font-size: 11px;
  line-height: 1.4;
}

@media (max-width: 768px) {
  .metric-type-picker {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
