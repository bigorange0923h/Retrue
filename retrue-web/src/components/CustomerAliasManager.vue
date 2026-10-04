<script setup lang="ts">
/** 别称维护保留正式姓名，冲突由服务端拒绝，绝不自动改绑客户。 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ElMessageBox } from 'element-plus'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { apiCreateCustomerAlias, apiListCustomerAliases, apiUpdateCustomerAlias, type CustomerAlias } from '@/api/customers'
import { createCustomerScope } from '@/utils/customerScope'
const props = defineProps<{ customerId: number }>()
const scope = createCustomerScope()
const items = ref<CustomerAlias[]>([])
const loading = ref(false)
const failed = ref(false)
const saving = ref(false)
const visible = ref(false)
const editingId = ref<number | null>(null)
const text = ref('')
async function load(): Promise<void> {
  const snapshot = scope.capture(); loading.value = true; failed.value = false
  try { const result = await apiListCustomerAliases(snapshot.customerId); if (scope.isCurrent(snapshot)) items.value = result }
  catch { if (scope.isCurrent(snapshot)) failed.value = true }
  finally { if (scope.isCurrent(snapshot)) loading.value = false }
}
function open(item?: CustomerAlias): void { editingId.value = item?.id ?? null; text.value = item?.alias || ''; visible.value = true }
async function save(): Promise<void> {
  if (saving.value || !text.value.trim()) return
  const snapshot = scope.capture(); const id = editingId.value; const alias = text.value; saving.value = true
  try {
    if (id) await apiUpdateCustomerAlias(snapshot.customerId, id, { alias })
    else await apiCreateCustomerAlias(snapshot.customerId, alias)
    if (!scope.isCurrent(snapshot)) return
    visible.value = false; ElMessage.success('客户别称已保存'); await load()
  } catch { /* 冲突时保留输入，不自动解决身份归属。 */ }
  finally { if (scope.isCurrent(snapshot)) saving.value = false }
}
async function toggle(item: CustomerAlias): Promise<void> {
  if (saving.value) return
  const snapshot = scope.capture(); saving.value = true
  try { await apiUpdateCustomerAlias(snapshot.customerId, item.id, { is_active: !item.is_active }); if (scope.isCurrent(snapshot)) await load() }
  catch { /* 服务端错误已提示。 */ }
  finally { if (scope.isCurrent(snapshot)) saving.value = false }
}
watch(() => props.customerId, (id) => { scope.reset(id); items.value = []; visible.value = false; saving.value = false; void load() }, { immediate: true })
onBeforeUnmount(() => scope.reset(0))
async function confirmNavigation(): Promise<boolean> {
  if (!visible.value) return true
  try { await ElMessageBox.confirm('别称尚未提交，离开将丢弃编辑。', '离开客户', { confirmButtonText: '丢弃并离开', cancelButtonText: '继续编辑' }); return true }
  catch { return false }
}
onBeforeRouteLeave(confirmNavigation)
onBeforeRouteUpdate((to, from) => to.params.id === from.params.id ? true : confirmNavigation())
</script>
<template>
  <section v-loading="loading">
    <div class="alias-header"><strong>客户别称</strong><el-button link type="primary" @click="open()">新增别称</el-button></div>
    <p class="hint">用于识别常用称呼，正式姓名保持不变。同名或冲突仍需人工选择。</p>
    <el-alert v-if="failed" title="别称加载失败" type="error" :closable="false"><el-button link @click="load">重试</el-button></el-alert>
    <el-empty v-else-if="!loading && !items.length" description="暂无别称" :image-size="40" />
    <div v-for="item in items" :key="item.id" class="alias-row"><span>{{ item.alias }}</span><el-tag size="small" :type="item.is_active ? 'success' : 'info'">{{ item.is_active ? '启用' : '停用' }}</el-tag><el-button link :disabled="saving" @click="open(item)">编辑</el-button><el-button link :disabled="saving" @click="toggle(item)">{{ item.is_active ? '停用' : '启用' }}</el-button></div>
    <el-dialog v-model="visible" title="客户别称" width="400px" :close-on-click-modal="false" :show-close="!saving"><el-form :disabled="saving" label-position="top"><el-form-item label="常用称呼"><el-input v-model="text" maxlength="100" /></el-form-item></el-form><template #footer><el-button :disabled="saving" @click="visible = false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!text.trim()" @click="save">保存</el-button></template></el-dialog>
  </section>
</template>
<style scoped>
.alias-header, .alias-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.alias-header { justify-content: space-between; }
.alias-row { padding: 8px 0; }
.hint { color: var(--retrue-text-secondary); font-size: 13px; }
@media (max-width: 767px) { :deep(.el-dialog) { max-width: calc(100vw - 32px); } }
</style>
