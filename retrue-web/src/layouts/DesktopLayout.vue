<script setup lang="ts">
/** 桌面端主布局：左侧导航 + 右侧工作区。
 *
 * 顶部展示当前用户与登出入口，左侧为业务导航，右侧渲染路由页面。
 */

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useViewport } from '@/composables/useViewport'
import { useUserStore } from '@/stores/user'
import FloatingAiAssistant from '@/components/FloatingAiAssistant.vue'
import MobileLayout from '@/layouts/MobileLayout.vue'

const userStore = useUserStore()
const route = useRoute()
const router = useRouter()
const { isMobile } = useViewport()

const currentTitle = computed(() => (route.meta.title as string) || '')

async function handleLogout(): Promise<void> {
  await userStore.logout()
  ElMessage.success('已退出登录')
  router.push({ name: 'login' })
}
</script>

<template>
  <MobileLayout v-if="isMobile" />
  <el-container v-else class="desktop-layout">
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
        <el-menu-item index="/ai-draft" class="mobile-only">
          <el-icon><EditPen /></el-icon>
          <span>快速记录</span>
        </el-menu-item>
        <el-menu-item index="/course-types" class="desktop-only">
          <el-icon><Notebook /></el-icon>
          <span>课程模板</span>
        </el-menu-item>
        <el-menu-item index="/knowledge" class="desktop-only">
          <el-icon><Reading /></el-icon>
          <span>客户知识库</span>
        </el-menu-item>
        <el-menu-item v-if="userStore.currentUser?.is_superuser" index="/accounts" class="desktop-only">
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

.mobile-only {
  display: none;
}

@media (max-width: 768px) {
  .desktop-layout {
    height: 100dvh;
  }

  .layout-aside {
    position: fixed;
    z-index: 1000;
    right: 0;
    bottom: 0;
    left: 0;
    width: 100% !important;
    height: 68px;
    border-top: 1px solid var(--retrue-border);
    border-right: 0;
    box-shadow: 0 -4px 16px rgb(0 0 0 / 6%);
  }

  .brand,
  .desktop-only {
    display: none;
  }

  .mobile-only {
    display: flex;
  }

  .layout-menu {
    display: flex;
    flex: 1;
    width: 100%;
    padding: 0;
  }

  .layout-menu :deep(.el-menu-item) {
    display: flex;
    flex: 1;
    flex-direction: column;
    justify-content: center;
    min-width: 0;
    height: 67px;
    padding: 6px 2px !important;
    line-height: 1.25;
    font-size: 11px;
  }

  .layout-menu :deep(.el-menu-item .el-icon) {
    margin: 0 0 3px;
    font-size: 18px;
  }

  .layout-header {
    height: 52px;
    padding: 0 16px;
  }

  .page-title {
    font-size: 16px;
  }

  .header-user {
    gap: 8px;
  }

  .user-name {
    display: none;
  }

  .layout-main {
    padding: 16px 12px 84px;
  }
}
</style>
