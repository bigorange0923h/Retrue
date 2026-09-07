<script setup lang="ts">
/**
 * 训练记录关联排课选择器。
 * 已回填或非待上课的排课仍展示但不可选择，最终唯一性仍由服务端校验。
 */

import { computed, ref, watch } from 'vue'

import { apiGetCourse, apiGetTodayCourses } from '@/api/courses'
import type { CourseSessionItem } from '@/types/api'

interface Props {
  modelValue: number | null
  customerId: number | null
  trainingDate: string
  locked?: boolean
  disabled?: boolean
  allowUnavailableSelection?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  locked: false,
  disabled: false,
  allowUnavailableSelection: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
}>()

const sessions = ref<CourseSessionItem[]>([])
const loading = ref(false)
let loadVersion = 0

const selectedSession = computed(() => sessions.value.find((item) => item.id === props.modelValue) || null)
const selectionError = computed(() => {
  const session = selectedSession.value
  if (!props.modelValue) return ''
  if (!session) return loading.value ? '正在核对所选排课' : '所选排课不存在或不属于当前客户'
  if (props.allowUnavailableSelection) return ''
  if (session.date !== props.trainingDate) return `所选排课日期为 ${session.date}，与训练日期不一致`
  if (session.training_record_id !== null) return '该排课已经关联正式训练记录，不能重复选择'
  if (session.status !== 'scheduled') return `该排课当前为${session.status_display}，不能关联新的训练记录`
  return ''
})

function unavailableReason(session: CourseSessionItem): string {
  if (session.date !== props.trainingDate) return '日期不一致'
  if (session.training_record_id !== null) return '已回填'
  if (session.status !== 'scheduled') return session.status_display
  return ''
}

function isOptionDisabled(session: CourseSessionItem): boolean {
  return session.date !== props.trainingDate || session.training_record_id !== null || session.status !== 'scheduled'
}

function formatTime(session: CourseSessionItem): string {
  if (!session.start_time) return '时间待定'
  const start = session.start_time.slice(0, 5)
  const end = session.end_time?.slice(0, 5)
  return end ? `${start}–${end}` : start
}

function optionLabel(session: CourseSessionItem, index: number): string {
  const courseName = session.plan_course_name || session.session_topic || session.arrangement_type_display || '康复训练'
  const duplicateCount = sessions.value.filter((item) => (
    item.plan_course_name === session.plan_course_name
    && item.session_topic === session.session_topic
    && item.start_time === session.start_time
    && item.end_time === session.end_time
  )).length
  const duplicateIndex = sessions.value.slice(0, index + 1).filter((item) => (
    item.plan_course_name === session.plan_course_name
    && item.session_topic === session.session_topic
    && item.start_time === session.start_time
    && item.end_time === session.end_time
  )).length
  const sequence = duplicateCount > 1 ? ` · 同时段第 ${duplicateIndex} 节` : ''
  const reason = unavailableReason(session)
  return `${formatTime(session)} · ${courseName}${sequence}${reason ? `（${reason}）` : ''}`
}

async function loadSessions(): Promise<void> {
  const version = ++loadVersion
  if (!props.customerId || !props.trainingDate) {
    sessions.value = []
    return
  }
  loading.value = true
  try {
    const values = (await apiGetTodayCourses(props.trainingDate))
      .filter((item) => item.customer === props.customerId)
      .sort((a, b) => `${a.start_time || ''}-${a.id}`.localeCompare(`${b.start_time || ''}-${b.id}`))

    if (props.modelValue && !values.some((item) => item.id === props.modelValue)) {
      try {
        const selected = await apiGetCourse(props.modelValue)
        if (selected.customer === props.customerId) values.push(selected)
      } catch {
        // 统一由 selectionError 给出不可关联提示，不暴露资源是否存在。
      }
    }
    if (version === loadVersion) sessions.value = values
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

function validateSelection(): boolean {
  return !selectionError.value
}

watch(
  () => [props.customerId, props.trainingDate, props.modelValue] as const,
  () => { void loadSessions() },
  { immediate: true },
)

defineExpose({ validateSelection, selectionError })
</script>

<template>
  <div class="course-session-picker">
    <el-select
      :model-value="modelValue"
      class="full-width"
      clearable
      :loading="loading"
      :disabled="disabled || locked"
      placeholder="不关联排课（计划外训练）"
      @update:model-value="emit('update:modelValue', $event ?? null)"
    >
      <el-option
        v-for="(session, index) in sessions"
        :key="session.id"
        :label="optionLabel(session, index)"
        :value="session.id"
        :disabled="isOptionDisabled(session)"
      />
    </el-select>
    <p v-if="selectionError" class="picker-error">{{ selectionError }}</p>
    <p v-else-if="locked && modelValue" class="picker-hint">
      {{ allowUnavailableSelection ? '正式训练记录的关联排课不可更换。' : '已锁定从工作台进入的本次排课。' }}
    </p>
    <p v-else class="picker-hint">不选择排课时，将作为计划外训练保存，不会完成课程或扣减课时。</p>
  </div>
</template>

<style scoped>
.full-width { width: 100%; }
.picker-hint, .picker-error { margin: 5px 0 0; font-size: 12px; line-height: 1.5; }
.picker-hint { color: var(--retrue-text-muted); }
.picker-error { color: var(--el-color-danger); }
</style>
