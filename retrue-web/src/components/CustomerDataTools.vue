<script setup lang="ts">
/** 客户数据工具：用户主动导出；删除影响仅供查看，没有清除操作。 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { apiExportCustomer, apiPreviewCustomerDeletion, type CustomerDeletionPreview } from '@/api/customers'
import { createCustomerScope } from '@/utils/customerScope'
const props = defineProps<{ customerId: number }>()
const scope = createCustomerScope()
const loading = ref(false)
const visible = ref(false)
const preview = ref<CustomerDeletionPreview | null>(null)
async function download(output: 'json' | 'report'): Promise<void> {
  if (loading.value) return
  const snapshot = scope.capture(); loading.value = true
  try {
    const result = await apiExportCustomer(snapshot.customerId, output)
    if (!scope.isCurrent(snapshot)) return
    const content = typeof result.content === 'string' ? result.content : JSON.stringify(result.content, null, 2)
    const url = URL.createObjectURL(new Blob([content], { type: result.content_type }))
    const link = document.createElement('a'); link.href = url; link.download = result.filename; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch { /* API 层已提示，不创建不完整导出文件。 */ }
  finally { if (scope.isCurrent(snapshot)) loading.value = false }
}
async function showPreview(): Promise<void> {
  if (loading.value) return
  const snapshot = scope.capture(); loading.value = true
  try { const result = await apiPreviewCustomerDeletion(snapshot.customerId); if (scope.isCurrent(snapshot)) { preview.value = result; visible.value = true } }
  catch { /* 失败不展示旧客户的影响范围。 */ }
  finally { if (scope.isCurrent(snapshot)) loading.value = false }
}
watch(() => props.customerId, (id) => { scope.reset(id); preview.value = null; visible.value = false; loading.value = false }, { immediate: true })
onBeforeUnmount(() => scope.reset(0))
</script>
<template>
  <section><strong>客户数据</strong><p class="hint">导出默认隐藏完整手机号，包含本客户的业务记录；导出操作会留审计。</p><div class="tools-row"><el-button :loading="loading" @click="download('json')">导出结构化资料</el-button><el-button :disabled="loading" @click="download('report')">导出可读报告</el-button><el-button :disabled="loading" @click="showPreview">查看删除影响</el-button></div>
    <el-dialog v-model="visible" title="删除影响预览（只读）" width="560px"><template v-if="preview"><el-alert title="本页只展示范围，不执行删除。保留策略确认前不开放清除。" type="info" :closable="false" /><div v-for="item in preview.resources" :key="item.key" class="resource-row"><span>{{ item.label }}</span><strong>{{ item.count }} 条</strong></div><p v-for="item in preview.derived_content" :key="item" class="hint">{{ item }}</p><p v-for="item in preview.external_boundaries" :key="item" class="hint">{{ item }}</p></template><template #footer><el-button @click="visible = false">关闭预览</el-button></template></el-dialog>
  </section>
</template>
<style scoped>
.hint { font-size: 13px; color: var(--retrue-text-secondary); }
.tools-row { display: flex; gap: 8px; flex-wrap: wrap; }
.tools-row .el-button { margin-left: 0; }
.resource-row { display: flex; justify-content: space-between; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--retrue-border); }
@media (max-width: 767px) { :deep(.el-dialog) { max-width: calc(100vw - 32px); } }
</style>
