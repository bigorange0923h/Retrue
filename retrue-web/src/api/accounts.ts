/** 账号管理 API 模块（仅超级用户可调用）。 */

import { request } from './http'
import type { PageData, UserAccountItem, UserCreateForm, UserUpdateForm } from '@/types/api'

/** 账号查询参数。 */
export interface UserQuery {
  keyword?: string
  page?: number
  page_size?: number
}

/** 分页查询用户列表。 */
export function apiListUsers(params: UserQuery): Promise<PageData<UserAccountItem>> {
  return request<PageData<UserAccountItem>>({ method: 'GET', url: '/auth/users/', params })
}

/** 创建账号。 */
export function apiCreateUser(data: UserCreateForm): Promise<UserAccountItem> {
  return request<UserAccountItem>({ method: 'POST', url: '/auth/users/', data })
}

/** 更新账号（启停/后台权限/超管权限/重置密码）。 */
export function apiUpdateUser(id: number, data: UserUpdateForm): Promise<UserAccountItem> {
  return request<UserAccountItem>({ method: 'PUT', url: `/auth/users/${id}/`, data })
}
