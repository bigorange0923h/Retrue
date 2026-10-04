<script setup lang="ts">
/** 可复用的动作目录选择入口，保留自由输入，不覆盖剂量或已有备注。 */
import { onBeforeUnmount, ref } from 'vue'
import { apiListExercises, type ExerciseDefinition } from '@/api/exercises'
const emit = defineEmits<{ select: [exercise: ExerciseDefinition] }>()
const visible = ref(false)
const keyword = ref('')
const items = ref<ExerciseDefinition[]>([])
const loading = ref(false)
const failed = ref(false)
let generation = 0
async function search(): Promise<void> {
  const current = ++generation; loading.value = true; failed.value = false
  try { const result = await apiListExercises(keyword.value); if (current === generation) items.value = result }
  catch { if (current === generation) failed.value = true }
  finally { if (current === generation) loading.value = false }
}
function open(): void { visible.value = true; void search() }
function select(item: ExerciseDefinition): void { emit('select', item); visible.value = false }
onBeforeUnmount(() => { generation += 1 })
</script>
<template>
  <el-button link type="primary" @click="open">从动作库选择</el-button>
  <el-dialog v-model="visible" title="选择正式动作名称" width="560px">
    <div class="search-row"><el-input v-model="keyword" placeholder="名称或别名" clearable @keyup.enter="search" /><el-button :loading="loading" @click="search">查询</el-button></div>
    <el-alert v-if="failed" title="动作库加载失败，请重试。" type="error" :closable="false" />
    <div v-loading="loading" class="exercise-list">
      <el-empty v-if="!loading && !failed && !items.length" description="没有匹配动作，可在表单中直接填写" :image-size="50" />
      <div v-for="item in items" :key="item.id" class="exercise-item"><div><strong>{{ item.name }}</strong><el-tag size="small" :type="item.is_official ? 'info' : 'success'">{{ item.is_official ? '官方' : '个人' }}</el-tag><p v-if="item.precautions">注意：{{ item.precautions }}</p><p v-if="item.contraindications">禁忌：{{ item.contraindications }}</p></div><el-button size="small" @click="select(item)">采用名称</el-button></div>
    </div>
  </el-dialog>
</template>
<style scoped>
.search-row, .exercise-item { display: flex; align-items: center; gap: 10px; }
.exercise-item { justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--retrue-border); }
.exercise-item > div { min-width: 0; overflow-wrap: anywhere; }
.exercise-item .el-tag { margin-left: 8px; }
.exercise-item p { margin: 4px 0; color: var(--retrue-text-secondary); font-size: 13px; }
.exercise-list { min-height: 80px; max-height: 50vh; overflow: auto; }
@media (max-width: 767px) { :deep(.el-dialog) { max-width: calc(100vw - 32px); } .exercise-item { flex-wrap: wrap; } }
</style>
