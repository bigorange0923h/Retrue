<script setup lang="ts">
/** 客户列表路由适配器：移动端使用卡片列表而非压缩表格。 */
import { useViewport } from '@/composables/useViewport'
import DesktopCustomerListView from '@/views/customers/CustomerListView.vue'
import MobileCustomerListView from '@/views/mobile/MobileCustomerListView.vue'
const { isMobile } = useViewport()
</script>
<template><MobileCustomerListView v-if="isMobile" /><DesktopCustomerListView v-else /></template>
