<script setup lang="ts">
/** 小程序式首页：只展示今日课程、待办入口和高频操作。 */

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { apiGetTodayCourses } from '@/api/courses'
import { useUserStore } from '@/stores/user'
import type { CourseSessionItem } from '@/types/api'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const courses = ref<CourseSessionItem[]>([])

const todayLabel = computed(() => new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }).format(new Date()))

/** 加载今天的课程。 */
async function loadToday(): Promise<void> {
  loading.value = true
  try { courses.value = await apiGetTodayCourses() } finally { loading.value = false }
}

/** 打开所选客户的档案。 */
function goCustomer(course: CourseSessionItem): void {
  router.push({ name: 'customer-detail', params: { id: course.customer } })
}

function formatTime(value: string | null): string { return value ? value.slice(0, 5) : '待定' }

onMounted(loadToday)
</script>

<template>
  <div class="mobile-dashboard">
    <section class="mobile-greeting"><p>{{ todayLabel }}</p><h2>你好，{{ userStore.currentUser?.display_name }}</h2><span>今天有 {{ courses.length }} 节康复课程</span></section>

    <section class="quick-actions" aria-label="快捷操作">
      <el-button class="quick-action" @click="router.push({ name: 'customer-list' })"><el-icon><User /></el-icon><span>客户</span></el-button>
      <el-button class="quick-action" @click="router.push({ name: 'assistant', query: { mode: 'training', theme: 'smart' } })"><el-icon><EditPen /></el-icon><span>补记</span></el-button>
      <el-button class="quick-action" @click="router.push({ name: 'schedule' })"><el-icon><Calendar /></el-icon><span>课表</span></el-button>
      <el-button class="quick-action" @click="router.push({ name: 'customer-list' })"><el-icon><Plus /></el-icon><span>新客户</span></el-button>
    </section>

    <section class="section-heading"><h3>今日课程</h3><el-button link type="primary" @click="router.push({ name: 'schedule' })">查看课表</el-button></section>
    <el-skeleton v-if="loading" :rows="3" animated />
    <el-empty v-else-if="courses.length === 0" description="今天暂无课程安排" />
    <div v-else class="mobile-course-list">
      <el-card v-for="course in courses.slice(0, 5)" :key="course.id" shadow="never" class="mobile-course-card" @click="goCustomer(course)">
        <div class="course-time">{{ formatTime(course.start_time) }}</div><div class="course-info"><strong>{{ course.customer_name }}</strong><span>{{ course.session_topic || '康复训练' }}</span></div><el-tag size="small" :type="course.status === 'scheduled' ? 'success' : 'info'">{{ course.status_display }}</el-tag>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.mobile-greeting { padding: 8px 4px 18px; }.mobile-greeting p { margin: 0 0 6px; color: var(--retrue-text-secondary); font-size: 13px; }.mobile-greeting h2 { margin: 0 0 4px; color: var(--retrue-text); font-size: 24px; }.mobile-greeting span { color: var(--retrue-text-secondary); font-size: 14px; }
.quick-actions { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 24px; }.quick-action { display: flex; flex-direction: column; height: 74px; margin: 0; border-color: var(--retrue-border); border-radius: var(--retrue-radius-md); color: var(--retrue-text); }.quick-action :deep(.el-icon) { margin-bottom: 7px; color: var(--retrue-primary); font-size: 21px; }.quick-action span { font-size: 12px; }
.section-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }.section-heading h3 { margin: 0; font-size: 17px; }.mobile-course-list { display: flex; flex-direction: column; gap: 10px; }.mobile-course-card { border-color: var(--retrue-border); border-radius: var(--retrue-radius-md); cursor: pointer; }.mobile-course-card :deep(.el-card__body) { display: flex; align-items: center; gap: 12px; padding: 14px; }.course-time { width: 42px; color: var(--retrue-primary); font-size: 14px; font-weight: 700; }.course-info { display: flex; flex: 1; flex-direction: column; gap: 3px; }.course-info strong { color: var(--retrue-text); }.course-info span { overflow: hidden; color: var(--retrue-text-secondary); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
</style>
