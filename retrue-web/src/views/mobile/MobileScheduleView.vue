<script setup lang="ts">
/** 小程序式课表：按天展示课程，避免手机端月历信息拥挤。 */

import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { apiGetTodayCourses } from '@/api/courses'
import type { CourseSessionItem } from '@/types/api'

const router = useRouter()
const selectedDate = ref(new Date().toISOString().slice(0, 10))
const loading = ref(false)
const courses = ref<CourseSessionItem[]>([])

/** 查询所选日期的课程。 */
async function loadSchedule(): Promise<void> {
  loading.value = true
  try { courses.value = await apiGetTodayCourses(selectedDate.value) } finally { loading.value = false }
}

function formatTime(value: string | null): string { return value ? value.slice(0, 5) : '待定' }
function goCustomer(course: CourseSessionItem): void { router.push({ name: 'customer-detail', params: { id: course.customer } }) }

watch(selectedDate, loadSchedule)
onMounted(loadSchedule)
</script>

<template>
  <div class="mobile-schedule"><div class="schedule-heading"><div><h2>今日课表</h2><p>按日期查看你的康复课程</p></div><el-date-picker v-model="selectedDate" type="date" value-format="YYYY-MM-DD" /></div>
    <el-skeleton v-if="loading" :rows="4" animated />
    <el-empty v-else-if="courses.length === 0" description="当天暂无课程安排" />
    <div v-else class="schedule-cards"><el-card v-for="course in courses" :key="course.id" shadow="never" class="schedule-card" @click="goCustomer(course)"><div class="schedule-time">{{ formatTime(course.start_time) }}</div><div class="schedule-info"><strong>{{ course.customer_name }}</strong><span>{{ course.session_topic || '康复训练' }}</span><small>{{ course.session_count }} 课时</small></div><el-icon class="schedule-arrow"><ArrowRight /></el-icon></el-card></div>
  </div>
</template>

<style scoped>
.schedule-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 18px; }.schedule-heading h2 { margin: 0 0 4px; font-size: 20px; }.schedule-heading p { margin: 0; color: var(--retrue-text-secondary); font-size: 13px; }.schedule-heading :deep(.el-date-editor) { width: 132px; }.schedule-cards { display: flex; flex-direction: column; gap: 10px; }.schedule-card { border-color: var(--retrue-border); border-radius: var(--retrue-radius-md); cursor: pointer; }.schedule-card :deep(.el-card__body) { display: flex; align-items: center; gap: 12px; padding: 14px; }.schedule-time { width: 42px; color: var(--retrue-primary); font-weight: 700; }.schedule-info { display: flex; flex: 1; flex-direction: column; gap: 3px; }.schedule-info span { color: var(--retrue-text-secondary); font-size: 13px; }.schedule-info small { color: var(--retrue-text-muted); font-size: 12px; }.schedule-arrow { color: var(--retrue-text-muted); }
</style>
