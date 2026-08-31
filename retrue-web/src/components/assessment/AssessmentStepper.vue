<script setup lang="ts">
/** 评估步骤导航：允许回看已完成的步骤，当前步骤由页面统一管理。 */

const props = withDefaults(
  defineProps<{
    modelValue: number
    steps?: string[]
  }>(),
  {
    steps: () => ['本次问题', '主观情况', '客观评估', '目标与备注', '检查并完成'],
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: number]
}>()

function selectStep(index: number): void {
  // 不允许跳过尚未填写的步骤；返回修改时可点击已走过的步骤。
  if (index <= props.modelValue) emit('update:modelValue', index)
}
</script>

<template>
  <nav class="assessment-stepper" aria-label="评估填写步骤">
    <button
      v-for="(step, index) in props.steps"
      :key="step"
      type="button"
      class="step-item"
      :class="{ active: index === props.modelValue, completed: index < props.modelValue }"
      :aria-current="index === props.modelValue ? 'step' : undefined"
      :aria-label="`${index + 1}. ${step}`"
      @click="selectStep(index)"
    >
      <span class="step-index">
        <el-icon v-if="index < props.modelValue"><Check /></el-icon>
        <span v-else>{{ index + 1 }}</span>
      </span>
      <span class="step-label">{{ step }}</span>
      <span v-if="index < props.steps.length - 1" class="step-line" aria-hidden="true" />
    </button>
  </nav>
</template>

<style scoped>
.assessment-stepper {
  display: flex;
  width: 100%;
  margin-bottom: 22px;
}

.step-item {
  position: relative;
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  border: 0;
  background: transparent;
  color: var(--retrue-text-muted);
  cursor: pointer;
  font: inherit;
  padding: 0 4px;
}

.step-item:focus-visible {
  outline: 2px solid var(--retrue-primary);
  outline-offset: 3px;
  border-radius: var(--retrue-radius-sm);
}

.step-index {
  z-index: 1;
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid var(--retrue-border);
  border-radius: 50%;
  background: var(--retrue-surface);
  color: var(--retrue-text-muted);
  font-size: 13px;
  font-weight: 600;
}

.step-label {
  overflow: hidden;
  max-width: 100%;
  color: inherit;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-line {
  position: absolute;
  top: 16px;
  right: calc(-50% + 16px);
  left: calc(50% + 16px);
  height: 1px;
  background: var(--retrue-border);
}

.step-item.active {
  color: var(--retrue-primary);
}

.step-item.active .step-index {
  border-color: var(--retrue-primary);
  background: var(--retrue-primary);
  color: var(--retrue-on-primary);
  box-shadow: 0 0 0 4px var(--retrue-primary-light);
}

.step-item.completed {
  color: var(--retrue-primary-dark);
}

.step-item.completed .step-index {
  border-color: var(--retrue-primary);
  background: var(--retrue-primary-light);
  color: var(--retrue-primary);
}

.step-item.completed .step-line {
  background: var(--retrue-primary);
}

@media (max-width: 520px) {
  .assessment-stepper {
    margin-right: -4px;
    margin-left: -4px;
  }

  .step-index {
    width: 28px;
    height: 28px;
  }

  .step-line {
    top: 14px;
    right: calc(-50% + 14px);
    left: calc(50% + 14px);
  }

  .step-label {
    font-size: 11px;
  }
}
</style>
