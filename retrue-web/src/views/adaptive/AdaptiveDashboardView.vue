<script setup lang="ts">
/** 工作台路由适配器：同一路由按视口渲染独立页面。 */
import { useViewport } from '@/composables/useViewport'
import DesktopDashboardView from '@/views/DashboardView.vue'
import MobileDashboardView from '@/views/mobile/MobileDashboardView.vue'
const { isMobile } = useViewport()
</script>
<template><MobileDashboardView v-if="isMobile" /><DesktopDashboardView v-else /></template>
