<script setup lang="ts">
/** 桌面端主布局：左侧导航 + 右侧工作区。
 *
 * 顶部展示当前用户与登出入口，左侧为业务导航，右侧渲染路由页面。
 */

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useUserStore } from '@/stores/user'
import FloatingAiAssistant from '@/components/FloatingAiAssistant.vue'

const userStore = useUserStore()
const route = useRoute()
const router = useRouter()

const currentTitle = computed(() => (route.meta.title as string) || '')

async function handleLogout(): Promise<void> {
  await userStore.logout()
  ElMessage.success('已退出登录')
  router.push({ name: 'login' })
}
</script>

<template>
  <el-container class="desktop-layout">
    <el-aside width="220px" class="layout-aside">
      <div class="brand">
        <span class="brand-dot" />
        <span class="brand-name">Retrue</span>
      </div>
      <el-menu router :default-active="route.path" class="layout-menu">
        <el-menu-item index="/">
          <el-icon><DataBoard /></el-icon>
          <span>今日工作台</span>
        </el-menu-item>
        <el-menu-item index="/customers">
          <el-icon><User /></el-icon>
          <span>客户管理</span>
        </el-menu-item>
        <el-menu-item index="/schedule">
          <el-icon><Calendar /></el-icon>
          <span>课程管理</span>
        </el-menu-item>
        <el-menu-item index="/course-types">
          <el-icon><Notebook /></el-icon>
          <span>课程类型</span>
        </el-menu-item>
        <el-menu-item index="/customer-courses">
          <el-icon><Collection /></el-icon>
          <span>客户疗程</span>
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon><Reading /></el-icon>
          <span>客户知识库</span>
        </el-menu-item>
        <el-menu-item v-if="userStore.currentUser?.is_superuser" index="/accounts">
          <el-icon><Setting /></el-icon>
          <span>账号管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="layout-body">
      <el-header class="layout-header">
        <h2 class="page-title">{{ currentTitle }}</h2>
        <div class="header-user">
          <template v-if="userStore.currentUser">
            <span class="user-avatar">{{ userStore.currentUser.display_name.slice(0, 1) }}</span>
            <span class="user-name">{{ userStore.currentUser.display_name }}</span>
          </template>
          <el-button link type="primary" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main class="layout-main">
        <router-view />
      </el-main>
      <FloatingAiAssistant />
    </el-container>
  </el-container>
</template>

<style scoped>
.desktop-layout {
  height: 100vh;
}

.layout-aside {
  background: var(--retrue-surface);
  border-right: 1px solid var(--retrue-border);
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 22px 20px 18px;
}

.brand-dot {
  width: 14px;
  height: 14px;
  border-radius: 5px;
  background: linear-gradient(135deg, var(--retrue-primary), var(--retrue-primary-dark));
}

.brand-name {
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.layout-menu {
  border-right: none;
  flex: 1;
  padding: 0 10px;
}

.layout-body {
  flex-direction: column;
}

.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--retrue-surface);
  border-bottom: 1px solid var(--retrue-border);
  height: 60px;
  padding: 0 28px;
}

.page-title {
  font-size: 17px;
  font-weight: 600;
  margin: 0;
}

.header-user {
  display: flex;
  align-items: center;
  gap: 14px;
}

.user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--retrue-primary-light);
  color: var(--retrue-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 13px;
}

.user-name {
  color: var(--retrue-text);
  font-weight: 500;
}

.layout-main {
  background: var(--retrue-bg);
  padding: 24px 28px;
  overflow-y: auto;
}
</style>
