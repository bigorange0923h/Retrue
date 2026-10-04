/** 客户相关 API 模块。 */

import { request } from './http'
import type { CustomerDetail, CustomerListItem, PageData } from '@/types/api'

/** 客户查询参数。 */
export interface CustomerQuery {
  keyword?: string
  status?: string
  page?: number
  page_size?: number
}

/** 客户创建/更新表单。 */
export interface CustomerForm {
  name: string
  phone?: string
  gender?: string
  birth_date?: string | null
  occupation?: string
  sport?: string
  main_issue?: string
  injury_date?: string | null
  surgery_date?: string | null
  status?: string
  first_visit_date?: string | null
  note?: string
}

/** 分页查询客户列表（脱敏手机号）。 */
export function apiListCustomers(params: CustomerQuery): Promise<PageData<CustomerListItem>> {
  return request<PageData<CustomerListItem>>({ method: 'GET', url: '/customers/', params })
}

/** 获取客户详情（含完整手机号）。 */
export function apiGetCustomer(id: number): Promise<CustomerDetail> {
  return request<CustomerDetail>({ method: 'GET', url: `/customers/${id}/` })
}

/** 创建客户。 */
export function apiCreateCustomer(data: CustomerForm): Promise<CustomerDetail> {
  return request<CustomerDetail>({ method: 'POST', url: '/customers/', data })
}

/** 更新客户。 */
export function apiUpdateCustomer(id: number, data: CustomerForm): Promise<CustomerDetail> {
  return request<CustomerDetail>({ method: 'PUT', url: `/customers/${id}/`, data })
}

/** 客户别称仅在本人客户目录内使用，停用后不再参与匹配。 */
export interface CustomerAlias { id: number; alias: string; is_active: boolean; normalized_alias?: string }
export function apiListCustomerAliases(customerId: number): Promise<CustomerAlias[]> {
  return request({ method: 'GET', url: `/customers/${customerId}/aliases/` })
}
export function apiCreateCustomerAlias(customerId: number, alias: string): Promise<CustomerAlias> {
  return request({ method: 'POST', url: `/customers/${customerId}/aliases/`, data: { alias } })
}
export function apiUpdateCustomerAlias(customerId: number, aliasId: number, data: { alias?: string; is_active?: boolean }): Promise<CustomerAlias> {
  return request({ method: 'PUT', url: `/customers/${customerId}/aliases/${aliasId}/`, data })
}

/** 客户授权导出；健康记录仅在用户主动点击后生成本地文件。 */
export interface CustomerExport { filename: string; content_type: string; content: unknown; audit_id: number }
export function apiExportCustomer(customerId: number, output: 'json' | 'report'): Promise<CustomerExport> {
  return request({ method: 'GET', url: `/customers/${customerId}/export/`, params: { output } })
}
/** 只读影响范围，服务端不提供执行删除能力。 */
export interface CustomerDeletionPreview {
  customer_id: number; resources: { key: string; label: string; count: number }[]
  can_delete: false; execution_enabled: false; policy_status: string
  external_boundaries: string[]; derived_content: string[]
}
export function apiPreviewCustomerDeletion(customerId: number): Promise<CustomerDeletionPreview> {
  return request({ method: 'GET', url: `/customers/${customerId}/deletion-preview/` })
}
