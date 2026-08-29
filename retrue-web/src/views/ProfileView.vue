<script setup lang="ts">
/** “我的”页面：展示当前账号并提供会话退出入口。 */

import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

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
    <el-button class="logout-button" @click="handleLogout">退出登录</el-button>
  </div>
</template>

<style scoped>
.profile-page { max-width: 560px; margin: 0 auto; }.profile-summary { display: flex; align-items: center; gap: 14px; padding: 12px 4px 24px; }.profile-avatar { display: grid; width: 58px; height: 58px; place-items: center; border-radius: 50%; background: var(--retrue-primary-light); color: var(--retrue-primary); font-size: 24px; font-weight: 700; }.profile-summary h2 { margin: 0 0 4px; color: var(--retrue-text); font-size: 20px; }.profile-summary p { margin: 0; color: var(--retrue-text-secondary); font-size: 13px; }.profile-card { border-color: var(--retrue-border); border-radius: var(--retrue-radius-md); }.profile-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; color: var(--retrue-text-secondary); font-size: 14px; }.profile-row + .profile-row { border-top: 1px solid var(--retrue-border); }.logout-button { width: 100%; height: 44px; margin-top: 18px; color: var(--retrue-risk); border-color: var(--retrue-border); }
</style>
