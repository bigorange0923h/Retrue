<script setup lang="ts">
/** 今日工作台：展示今日课程（今日客户），可进入客户详情。 */

import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { apiGetTodayCourses } from '@/api/courses'
import { useUserStore } from '@/stores/user'
import type { CourseSessionItem } from '@/types/api'

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const courses = ref<CourseSessionItem[]>([])

async function loadToday(): Promise<void> {
  loading.value = true
  try {
    courses.value = await apiGetTodayCourses()
  } finally {
    loading.value = false
  }
}

function goCustomer(session: CourseSessionItem): void {
  router.push({ name: 'customer-detail', params: { id: session.customer } })
}

function formatTime(time: string | null): string {
  return time ? time.slice(0, 5) : '待定'
}

onMounted(loadToday)
</script>

<template>
  <div class="dashboard">
    <div class="welcome-row">
      <div>
        <h2>今日工作台</h2>
        <p class="date-text">欢迎回来，{{ userStore.currentUser?.display_name }}</p>
      </div>
    </div>

    <el-card v-loading="loading" class="today-card">
      <template #header>
        <div class="card-header">
          <span>今日课程</span>
          <el-tag type="success">{{ courses.length }} 节</el-tag>
        </div>
      </template>

      <el-empty v-if="!loading && courses.length === 0" description="今天暂无课程安排" />

      <div v-else class="course-list">
        <div v-for="course in courses" :key="course.id" class="course-item" @click="goCustomer(course)">
          <div class="course-time">{{ formatTime(course.start_time) }}</div>
          <div class="course-body">
            <span class="course-name">{{ course.customer_name }}</span>
            <span class="course-phone">{{ course.customer_phone_masked }}</span>
          </div>
          <el-tag :type="course.status === 'scheduled' ? 'primary' : 'info'" size="small">
            {{ course.status_display }}
          </el-tag>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.welcome-row {
  margin-bottom: 16px;
}

.welcome-row h2 {
  margin: 0 0 4px;
}

.date-text {
  color: #888;
  margin: 0;
}

.today-card {
  border-radius: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.course-list {
  display: flex;
  flex-direction: column;
}

.course-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 8px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.2s;
}

.course-item:hover {
  background: #f8f9fa;
}

.course-item:last-child {
  border-bottom: none;
}

.course-time {
  font-weight: 600;
  width: 52px;
  color: #07a358;
}

.course-body {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.course-name {
  font-weight: 500;
}

.course-phone {
  color: #999;
  font-size: 12px;
}
</style>
