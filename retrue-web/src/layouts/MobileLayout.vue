<script setup lang="ts">
/** 小程序式移动端外壳：顶部状态栏、任务导航与快速记录入口。 */

import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
const route = useRoute()
const router = useRouter()
const quickVisible = ref(false)

const currentTitle = computed(() => (route.meta.title as string) || 'Retrue')

/** 前往目标页面并关闭快速入口面板。 */
function goTo(name: string): void {
  quickVisible.value = false
  router.push({ name })
}

/** 判断底部导航项是否与当前路由匹配。 */
function isActive(path: string): boolean {
  return path === '/' ? route.path === path : route.path.startsWith(path)
}

</script>

<template>
  <div class="mobile-layout">
    <header class="mobile-header">
      <div class="mobile-brand">
        <span class="mobile-brand-mark">R</span>
        <span>Retrue</span>
      </div>
      <span class="mobile-title">{{ currentTitle }}</span>
      <el-button circle text class="mobile-profile-button" aria-label="我的" @click="router.push({ name: 'profile' })">
        <el-icon><UserFilled /></el-icon>
      </el-button>
    </header>

    <main class="mobile-main">
      <router-view />
    </main>

    <nav class="mobile-tabbar" aria-label="主导航">
      <el-button text class="mobile-tab" :class="{ 'is-active': isActive('/') }" @click="router.push('/')"><span class="mobile-tab-content"><el-icon><HomeFilled /></el-icon><span>首页</span></span></el-button>
      <el-button text class="mobile-tab" :class="{ 'is-active': isActive('/customers') }" @click="router.push('/customers')"><span class="mobile-tab-content"><el-icon><User /></el-icon><span>客户</span></span></el-button>
      <el-button circle type="primary" class="mobile-add-button" aria-label="快速记录" @click="quickVisible = true"><el-icon><Plus /></el-icon></el-button>
      <el-button text class="mobile-tab" :class="{ 'is-active': isActive('/schedule') }" @click="router.push('/schedule')"><span class="mobile-tab-content"><el-icon><Calendar /></el-icon><span>课表</span></span></el-button>
      <el-button text class="mobile-tab" :class="{ 'is-active': isActive('/profile') }" aria-label="我的" @click="router.push({ name: 'profile' })"><span class="mobile-tab-content"><el-icon><UserFilled /></el-icon><span>我的</span></span></el-button>
    </nav>

    <el-drawer v-model="quickVisible" direction="btt" size="auto" :with-header="false">
      <div class="quick-sheet">
        <h3>快速开始</h3><p>选择本次要完成的工作。</p>
        <el-button type="primary" @click="goTo('ai-draft')">AI 统一补记</el-button>
        <el-button @click="goTo('customer-list')">单客户记录</el-button>
        <el-button @click="goTo('customer-list')">首次评估</el-button>
      </div>
    </el-drawer>

  </div>
</template>

<style scoped>
.mobile-layout { min-height: 100dvh; background: var(--retrue-bg); }
.mobile-header { position: sticky; z-index: 10; top: 0; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; height: 52px; padding: 0 12px; border-bottom: 1px solid var(--retrue-border); background: var(--retrue-surface-overlay); backdrop-filter: blur(12px); }
.mobile-brand { display: flex; align-items: center; gap: 6px; color: var(--retrue-text); font-size: 15px; font-weight: 700; }.mobile-brand-mark { display: grid; width: 22px; height: 22px; place-items: center; border-radius: var(--retrue-radius-sm); background: var(--retrue-primary); color: var(--retrue-on-primary); font-size: 12px; }.mobile-title { color: var(--retrue-text); font-size: 15px; font-weight: 600; }.mobile-profile-button { justify-self: end; }.mobile-main { padding: 16px 12px calc(88px + env(safe-area-inset-bottom)); }
.mobile-tabbar { position: fixed; z-index: 1000; right: 0; bottom: 0; left: 0; display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); align-items: stretch; height: calc(72px + env(safe-area-inset-bottom)); padding: 0 0 env(safe-area-inset-bottom); border-top: 1px solid var(--retrue-border); background: var(--retrue-surface); box-shadow: var(--retrue-shadow-top); }.mobile-tabbar > .el-button + .el-button { margin-left: 0; }.mobile-tab { display: block; align-self: stretch; justify-self: stretch; width: 100%; min-width: 0; height: 100%; margin: 0; padding: 0; border: 0; border-radius: 0; color: var(--retrue-text-muted); background: transparent; font-size: 12px; text-align: center; }.mobile-tab.is-text:not(.is-disabled):hover, .mobile-tab.is-text:not(.is-disabled):focus, .mobile-tab.is-text:not(.is-disabled):active { background: transparent; }.mobile-tab :deep(.mobile-tab-content) { display: flex; width: 100%; height: 100%; flex-direction: column; align-items: center; justify-content: center; line-height: 1.2; text-align: center; }.mobile-tab :deep(.mobile-tab-content .el-icon) { margin: 0 0 5px; font-size: 22px; }.mobile-tab :deep(.mobile-tab-content .el-icon + span) { margin-left: 0; }.mobile-tab.is-active { color: var(--retrue-primary); background: transparent; }.mobile-add-button { align-self: center; justify-self: center; width: 54px; height: 54px; margin: 0; transform: translateY(-2px); border: 4px solid var(--retrue-bg); box-shadow: var(--retrue-shadow-brand); }
.quick-sheet { display: flex; flex-direction: column; gap: 10px; padding: 8px 4px 20px; }.quick-sheet h3 { margin: 0; color: var(--retrue-text); font-size: 18px; }.quick-sheet p { margin: -4px 0 8px; color: var(--retrue-text-secondary); font-size: 13px; }.quick-sheet :deep(.el-button) { width: 100%; height: 44px; margin: 0; }
</style>
