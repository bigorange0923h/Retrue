<script setup lang="ts">
/** 课表路由适配器：移动端使用按日任务列表而非月历。 */
import { useViewport } from '@/composables/useViewport'
import DesktopScheduleView from '@/views/ScheduleView.vue'
import MobileScheduleView from '@/views/mobile/MobileScheduleView.vue'
const { isMobile } = useViewport()
</script>
<template><MobileScheduleView v-if="isMobile" /><DesktopScheduleView v-else /></template>
