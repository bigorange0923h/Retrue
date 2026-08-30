<script setup lang="ts">
/** 客户知识库路由适配器：移动端使用卡片列表与标签页替代桌面三栏布局。 */
import { useViewport } from '@/composables/useViewport'
import DesktopKnowledgeView from '@/views/knowledge/KnowledgeView.vue'
import MobileKnowledgeView from '@/views/mobile/MobileKnowledgeView.vue'
const { isMobile } = useViewport()
</script>
<template><MobileKnowledgeView v-if="isMobile" /><DesktopKnowledgeView v-else /></template>
