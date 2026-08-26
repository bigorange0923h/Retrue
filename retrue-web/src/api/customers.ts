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
