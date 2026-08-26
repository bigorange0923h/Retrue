<script setup lang="ts">
/** 桌面端主布局：左侧导航 + 右侧工作区。
 *
 * 顶部展示当前用户与登出入口，左侧为业务导航，右侧渲染路由页面。
 */

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useUserStore } from '@/stores/user'

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
          <span>课表</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="layout-body">
      <el-header class="layout-header">
        <h2 class="page-title">{{ currentTitle }}</h2>
        <div class="header-user">
          <span v-if="userStore.currentUser" class="user-name">
            {{ userStore.currentUser.display_name }}
          </span>
          <el-button link type="primary" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.desktop-layout {
  height: 100vh;
}

.layout-aside {
  background: #ffffff;
  border-right: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px;
}

.brand-dot {
  width: 12px;
  height: 12px;
  border-radius: 4px;
  background: #07a358;
}

.brand-name {
  font-size: 18px;
  font-weight: 600;
}

.layout-menu {
  border-right: none;
  flex: 1;
}

.layout-body {
  flex-direction: column;
}

.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  border-bottom: 1px solid #e8e8e8;
  height: 60px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}

.header-user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-name {
  color: #333;
}

.layout-main {
  background: #f5f6f7;
  padding: 24px;
}
</style>
