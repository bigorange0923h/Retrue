<script setup lang="ts">
/** 账号管理路由适配器：移动端使用卡片列表而非压缩表格。 */
import { useViewport } from '@/composables/useViewport'
import DesktopAccountsView from '@/views/accounts/AccountsView.vue'
import MobileAccountsView from '@/views/mobile/MobileAccountsView.vue'
const { isMobile } = useViewport()
</script>
<template><MobileAccountsView v-if="isMobile" /><DesktopAccountsView v-else /></template>
