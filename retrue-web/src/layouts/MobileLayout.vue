<script setup lang="ts">
/** 小程序式移动端外壳：顶部状态栏、任务导航与快速记录入口。 */

import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import QuickRecordDrawer from '@/components/QuickRecordDrawer.vue'
import { isMainNavigationActive, mainNavigationItems, managementNavigationItems } from '@/config/navigation'
const route = useRoute()
const router = useRouter()
const quickVisible = ref(false)

const currentTitle = computed(() => (route.meta.title as string) || 'Retrue')

/** 从"我的"页进入的子功能页：顶部显示返回箭头，回到"我的"。 */
const profileSubPages = new Set<string>(managementNavigationItems.map((item) => item.name))
const isProfileSubPage = computed(() => route.name !== undefined && profileSubPages.has(route.name as string))

/** 返回"我的"页面。 */
function goBackToProfile(): void {
  router.push({ name: 'profile' })
}

/** 判断底部导航项是否与当前路由匹配。 */
function isActive(item: (typeof mainNavigationItems)[number]): boolean {
  return isMainNavigationActive(item, route.name, route.path)
}

</script>

<template>
  <div class="mobile-layout">
    <header class="mobile-header">
      <el-button v-if="isProfileSubPage" circle text class="mobile-back-button" aria-label="返回" @click="goBackToProfile">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <div v-else class="mobile-brand">
        <span class="mobile-brand-mark">R</span>
        <span>Retrue</span>
      </div>
      <span class="mobile-title">{{ currentTitle }}</span>
      <span class="mobile-header-spacer" aria-hidden="true" />
    </header>

    <main class="mobile-main">
      <router-view />
    </main>

    <nav class="mobile-tabbar" aria-label="主导航">
      <el-button
        v-for="item in mainNavigationItems.slice(0, 2)"
        :key="item.name"
        text
        class="mobile-tab"
        :class="{ 'is-active': isActive(item) }"
        @click="router.push(item.path)"
      ><span class="mobile-tab-content"><el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span></span></el-button>
      <el-button circle type="primary" class="mobile-add-button" aria-label="快速记录" @click="quickVisible = true"><el-icon><Plus /></el-icon></el-button>
      <el-button
        v-for="item in mainNavigationItems.slice(2)"
        :key="item.name"
        text
        class="mobile-tab"
        :class="{ 'is-active': isActive(item) }"
        @click="router.push(item.path)"
      ><span class="mobile-tab-content"><el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span></span></el-button>
    </nav>

    <QuickRecordDrawer v-model="quickVisible" mode="mobile" />

  </div>
</template>

<style scoped>
.mobile-layout { min-height: 100dvh; background: var(--retrue-bg); }
.mobile-header { position: sticky; z-index: 10; top: 0; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; height: 52px; padding: 0 12px; border-bottom: 1px solid var(--retrue-border); background: var(--retrue-surface-overlay); backdrop-filter: blur(12px); }
.mobile-brand { display: flex; align-items: center; gap: 6px; color: var(--retrue-text); font-size: 15px; font-weight: 700; }.mobile-brand-mark { display: grid; width: 22px; height: 22px; place-items: center; border-radius: var(--retrue-radius-sm); background: var(--retrue-primary); color: var(--retrue-on-primary); font-size: 12px; }.mobile-title { color: var(--retrue-text); font-size: 15px; font-weight: 600; }.mobile-header-spacer { justify-self: end; width: 32px; }.mobile-back-button { justify-self: start; color: var(--retrue-text); }.mobile-main { padding: 16px 12px calc(88px + env(safe-area-inset-bottom)); }
.mobile-tabbar { position: fixed; z-index: 1000; right: 0; bottom: 0; left: 0; display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); align-items: stretch; height: calc(72px + env(safe-area-inset-bottom)); padding: 0 0 env(safe-area-inset-bottom); border-top: 1px solid var(--retrue-border); background: var(--retrue-surface); box-shadow: var(--retrue-shadow-top); }.mobile-tabbar > .el-button + .el-button { margin-left: 0; }.mobile-tab { display: block; align-self: stretch; justify-self: stretch; width: 100%; min-width: 0; height: 100%; margin: 0; padding: 0; border: 0; border-radius: 0; color: var(--retrue-text-muted); background: transparent; font-size: 12px; text-align: center; }.mobile-tab.is-text:not(.is-disabled):hover, .mobile-tab.is-text:not(.is-disabled):focus, .mobile-tab.is-text:not(.is-disabled):active { background: transparent; }.mobile-tab :deep(.mobile-tab-content) { display: flex; width: 100%; height: 100%; flex-direction: column; align-items: center; justify-content: center; line-height: 1.2; text-align: center; }.mobile-tab :deep(.mobile-tab-content .el-icon) { margin: 0 0 5px; font-size: 22px; }.mobile-tab :deep(.mobile-tab-content .el-icon + span) { margin-left: 0; }.mobile-tab.is-active { color: var(--retrue-primary); background: transparent; }.mobile-add-button { align-self: center; justify-self: center; width: 54px; height: 54px; margin: 0; transform: translateY(-2px); border: 4px solid var(--retrue-bg); box-shadow: var(--retrue-shadow-brand); }
</style>
