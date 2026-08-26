<script setup lang="ts">
/** 今日工作台（阶段 1 占位页）。 */

import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
</script>

<template>
  <div class="dashboard">
    <el-empty description="今日工作台建设中，阶段 2 将在此展示今日客户与待办" />
    <p v-if="userStore.currentUser" class="welcome">
      欢迎，{{ userStore.currentUser.display_name }}
    </p>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding-top: 60px;
}

.welcome {
  color: #888;
}
</style>
