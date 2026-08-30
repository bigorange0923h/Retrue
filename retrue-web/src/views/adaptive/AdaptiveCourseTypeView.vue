<script setup lang="ts">
/** 课程模板与计划模板管理：两端共用标签结构，内部使用各自适配视图。 */
import { ref } from 'vue'
import { useViewport } from '@/composables/useViewport'
import RehabPlanTemplateManager from '@/components/RehabPlanTemplateManager.vue'
import DesktopCourseTypeView from '@/views/courses/CourseTypeListView.vue'
import MobileCourseTypeView from '@/views/mobile/MobileCourseTypeView.vue'
const { isMobile } = useViewport()
const activeTab = ref('course-types')
</script>
<template>
  <div class="template-management-page">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="课程模板" name="course-types">
        <MobileCourseTypeView v-if="isMobile" />
        <DesktopCourseTypeView v-else />
      </el-tab-pane>
      <el-tab-pane label="课程计划模板" name="plan-templates">
        <RehabPlanTemplateManager />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.template-management-page { min-width: 0; }
</style>
