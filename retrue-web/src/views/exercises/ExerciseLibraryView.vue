<script setup lang="ts">
/** 动作库维护：官方只读，个人动作可维护名称、别名及安全提示。 */
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiCreateExercise, apiListExercises, apiUpdateExercise, type ExerciseDefinition, type ExerciseForm } from '@/api/exercises'
const items = ref<ExerciseDefinition[]>([])
const keyword = ref('')
const loading = ref(false)
const failed = ref(false)
const saving = ref(false)
const visible = ref(false)
const editing = ref<ExerciseDefinition | null>(null)
const aliases = ref('')
const form = reactive<ExerciseForm>({ name: '', body_part: '', description: '', precautions: '', contraindications: '', aliases: [] })
let generation = 0
async function load(): Promise<void> { const current = ++generation; loading.value = true; failed.value = false; try { const result = await apiListExercises(keyword.value); if (current === generation) items.value = result } catch { if (current === generation) failed.value = true } finally { if (current === generation) loading.value = false } }
function open(item?: ExerciseDefinition): void { editing.value = item || null; Object.assign(form, { name: item?.name || '', body_part: item?.body_part || '', description: item?.description || '', precautions: item?.precautions || '', contraindications: item?.contraindications || '', aliases: [] }); aliases.value = item?.aliases.map((entry) => entry.alias).join('\n') || ''; visible.value = true }
async function save(): Promise<void> {
  if (saving.value || editing.value?.is_official) return
  if (!form.name.trim()) { ElMessage.warning('请填写正式动作名称'); return }
  const id = editing.value?.id
  const payload = { ...form, aliases: [...new Set(aliases.value.split(/\r?\n/).map((value) => value.trim()).filter(Boolean))].map((alias) => ({ alias })) }
  saving.value = true
  try { if (id) await apiUpdateExercise(id, payload); else await apiCreateExercise(payload); visible.value = false; ElMessage.success('个人动作已保存'); await load() }
  catch { /* 保留编辑内容，失败时不显示保存成功。 */ }
  finally { saving.value = false }
}
onBeforeRouteLeave(async () => { if (!visible.value || editing.value?.is_official) return true; try { await ElMessageBox.confirm('动作内容尚未提交，离开将丢弃编辑。', '离开动作库', { confirmButtonText: '丢弃并离开', cancelButtonText: '继续编辑' }); return true } catch { return false } })
onMounted(load)
onBeforeUnmount(() => { generation += 1 })
</script>
<template>
  <div class="retrue-page"><div class="library-header"><h2>动作库</h2><el-button type="primary" @click="open()">新增个人动作</el-button></div><p class="hint">官方动作只读。动作库提供名称和安全提示，训练剂量由康复师填写。</p>
    <div class="search-row"><el-input v-model="keyword" placeholder="查询名称或别名" clearable @keyup.enter="load" /><el-button :loading="loading" @click="load">查询</el-button></div>
    <el-alert v-if="failed" title="动作库加载失败，请重试。" type="error" :closable="false" />
    <div v-loading="loading"><el-empty v-if="!loading && !failed && !items.length" description="暂无匹配动作" />
      <el-card v-for="item in items" :key="item.id" class="exercise-card" shadow="never"><div class="library-header"><strong>{{ item.name }}</strong><el-tag :type="item.is_official ? 'info' : 'success'">{{ item.is_official ? '官方只读' : '个人' }}</el-tag><el-button link type="primary" @click="open(item)">{{ item.is_official ? '查看' : '编辑' }}</el-button></div><p v-if="item.body_part">部位：{{ item.body_part }}</p><p v-if="item.aliases.length">别名：{{ item.aliases.map((entry) => entry.alias).join('、') }}</p><p v-if="item.precautions">注意：{{ item.precautions }}</p><p v-if="item.contraindications">禁忌：{{ item.contraindications }}</p></el-card>
    </div>
    <el-dialog v-model="visible" :title="editing?.is_official ? '查看官方动作' : editing ? '编辑个人动作' : '新增个人动作'" width="560px" :close-on-click-modal="false" :show-close="!saving"><el-form :model="form" label-position="top" :disabled="saving || !!editing?.is_official"><el-form-item label="正式名称"><el-input v-model="form.name" /></el-form-item><el-form-item label="部位"><el-input v-model="form.body_part" /></el-form-item><el-form-item label="别名（每行一个）"><el-input v-model="aliases" type="textarea" :rows="3" /></el-form-item><el-form-item label="动作说明"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item><el-form-item label="注意事项"><el-input v-model="form.precautions" type="textarea" :rows="2" /></el-form-item><el-form-item label="禁忌"><el-input v-model="form.contraindications" type="textarea" :rows="2" /></el-form-item></el-form><template #footer><el-button :disabled="saving" @click="visible = false">关闭</el-button><el-button v-if="!editing?.is_official" type="primary" :loading="saving" @click="save">保存</el-button></template></el-dialog>
  </div>
</template>
<style scoped>
.library-header, .search-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.library-header h2 { flex: 1; }
.search-row .el-input { flex: 1; min-width: 180px; }
.exercise-card { margin-top: 12px; border-radius: var(--retrue-radius-md); border-color: var(--retrue-border); }
.exercise-card p, .hint { font-size: 13px; color: var(--retrue-text-secondary); overflow-wrap: anywhere; }
@media (max-width: 767px) { :deep(.el-dialog) { max-width: calc(100vw - 32px); } }
</style>
