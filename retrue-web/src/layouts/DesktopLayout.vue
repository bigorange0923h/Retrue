<script setup lang="ts">
/** 桌面端主布局：左侧高频导航 + 右上角用户与管理菜单。 */

import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import QuickRecordDrawer from '@/components/QuickRecordDrawer.vue'
import { useViewport } from '@/composables/useViewport'
import {
  getVisibleManagementItems,
  isMainNavigationActive,
  mainNavigationItems,
} from '@/config/navigation'
import { useUserStore } from '@/stores/user'
import FloatingAiAssistant from '@/components/FloatingAiAssistant.vue'
import MobileLayout from '@/layouts/MobileLayout.vue'

const userStore = useUserStore()
const route = useRoute()
const router = useRouter()
const { isMobile } = useViewport()
const quickVisible = ref(false)

const currentTitle = computed(() => (route.meta.title as string) || '')
const desktopNavigationItems = mainNavigationItems.filter((item) => item.name !== 'profile')
const activeNavigationPath = computed(
  () => desktopNavigationItems.find((item) => isMainNavigationActive(item, route.name, route.path))?.path || '',
)
const visibleManagementItems = computed(() =>
  getVisibleManagementItems(!!userStore.currentUser?.is_superuser),
)

async function handleLogout(): Promise<void> {
  await userStore.logout()
  ElMessage.success('已退出登录')
  router.push({ name: 'login' })
}

/** 处理用户下拉菜单命令。 */
async function handleUserCommand(command: string): Promise<void> {
  if (command === 'logout') {
    await handleLogout()
    return
  }
  await router.push({ name: command })
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
      <el-menu router :default-active="activeNavigationPath" class="layout-menu">
        <el-menu-item v-for="item in desktopNavigationItems" :key="item.name" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
      <div class="aside-quick-action">
        <el-button type="primary" class="quick-record-button" @click="quickVisible = true">
          <el-icon><Plus /></el-icon>
          <span>补充记录</span>
        </el-button>
      </div>
    </el-aside>

    <el-container class="layout-body">
      <el-header class="layout-header">
        <h2 class="page-title">{{ currentTitle }}</h2>
        <el-dropdown v-if="userStore.currentUser" trigger="click" @command="handleUserCommand">
          <span class="header-user" tabindex="0">
            <span class="user-avatar">{{ userStore.currentUser.display_name.slice(0, 1) }}</span>
            <span class="user-name">{{ userStore.currentUser.display_name }}</span>
            <el-icon class="user-arrow"><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">
                <el-icon><User /></el-icon>
                个人信息
              </el-dropdown-item>
              <el-dropdown-item
                v-for="(item, index) in visibleManagementItems"
                :key="item.name"
                :command="item.name"
                :divided="index === 0"
              >
                <el-icon><component :is="item.icon" /></el-icon>
                {{ item.label }}
              </el-dropdown-item>
              <el-dropdown-item command="logout" divided class="logout-menu-item">
                <el-icon><SwitchButton /></el-icon>
                退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="layout-main">
        <router-view />
      </el-main>
      <FloatingAiAssistant />
      <QuickRecordDrawer v-model="quickVisible" mode="desktop" />
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

.aside-quick-action {
  padding: 0 16px 18px;
}

.quick-record-button {
  width: 100%;
  height: 42px;
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
  padding: 6px 8px;
  border-radius: var(--retrue-radius-sm);
  cursor: pointer;
  outline: none;
  transition: background-color 0.2s ease;
}

.header-user:hover,
.header-user:focus-visible {
  background: var(--retrue-primary-light);
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

.user-arrow {
  color: var(--retrue-text-muted);
  font-size: 13px;
}

.layout-main {
  background: var(--retrue-bg);
  padding: 24px 28px;
  overflow-y: auto;
}

</style>
