<script setup lang="ts">
/** "我的"页面：展示当前账号、常用功能入口，并提供会话退出入口。 */

import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { getVisibleManagementItems } from '@/config/navigation'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

/** 与 PC 用户下拉共用同一组管理工具入口。 */
const featureEntries = getVisibleManagementItems(!!userStore.currentUser?.is_superuser)

/** 退出当前会话并回到登录页。 */
async function handleLogout(): Promise<void> {
  await userStore.logout()
  ElMessage.success('已退出登录')
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="profile-page">
    <section class="profile-summary">
      <span class="profile-avatar">{{ userStore.currentUser?.display_name.slice(0, 1) }}</span>
      <div><h2>{{ userStore.currentUser?.display_name }}</h2><p>{{ userStore.currentUser?.username }}</p></div>
    </section>

    <el-card shadow="never" class="profile-card">
      <div class="profile-row"><span>账号状态</span><el-tag type="success" size="small">正常</el-tag></div>
      <div class="profile-row"><span>角色</span><span>{{ userStore.currentUser?.is_superuser ? '超级管理员' : '康复师' }}</span></div>
    </el-card>

    <el-card shadow="never" class="feature-card">
      <template #header>
        <span class="feature-title">管理工具</span>
      </template>
      <el-button
        v-for="entry in featureEntries"
        :key="entry.name"
        text
        class="feature-entry"
        @click="router.push({ name: entry.name })"
      >
        <span class="feature-entry-content">
          <span class="feature-icon"><el-icon><component :is="entry.icon" /></el-icon></span>
          <span class="feature-text">
            <strong>{{ entry.label }}</strong>
            <small>{{ entry.description }}</small>
          </span>
          <el-icon class="feature-arrow"><ArrowRight /></el-icon>
        </span>
      </el-button>
    </el-card>

    <el-button class="logout-button" @click="handleLogout">退出登录</el-button>
  </div>
</template>

<style scoped>
.profile-page { max-width: 560px; margin: 0 auto; }
.profile-summary { display: flex; align-items: center; gap: 14px; padding: 12px 4px 24px; }
.profile-avatar { display: grid; width: 58px; height: 58px; place-items: center; border-radius: 50%; background: var(--retrue-primary-light); color: var(--retrue-primary); font-size: 24px; font-weight: 700; }
.profile-summary h2 { margin: 0 0 4px; color: var(--retrue-text); font-size: 20px; }
.profile-summary p { margin: 0; color: var(--retrue-text-secondary); font-size: 13px; }
.profile-card, .feature-card { border-color: var(--retrue-border); border-radius: var(--retrue-radius-md); }
.profile-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; color: var(--retrue-text-secondary); font-size: 14px; }
.profile-row + .profile-row { border-top: 1px solid var(--retrue-border); }
.feature-card { margin-top: 14px; }
.feature-title { color: var(--retrue-text); font-weight: 600; font-size: 15px; }
.feature-entry { display: block; width: 100%; height: auto; padding: 12px 2px; border: 0; background: transparent; color: var(--retrue-text); cursor: pointer; text-align: left; }
.feature-entry-content { display: flex; width: 100%; align-items: center; gap: 14px; }
.feature-entry + .feature-entry { margin-left: 0; border-top: 1px solid var(--retrue-border); }
.feature-icon { display: grid; flex: 0 0 auto; width: 40px; height: 40px; place-items: center; border-radius: var(--retrue-radius-sm); background: var(--retrue-primary-light); color: var(--retrue-primary); font-size: 20px; }
.feature-text { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 2px; }
.feature-text strong { font-size: 15px; font-weight: 600; }
.feature-text small { color: var(--retrue-text-muted); font-size: 12px; }
.feature-arrow { color: var(--retrue-text-muted); font-size: 16px; }
.logout-button { width: 100%; height: 44px; margin-top: 18px; color: var(--retrue-risk); border-color: var(--retrue-border); }
</style>
