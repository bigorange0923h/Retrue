/** 认证相关 API 模块。
 *
 * 所有请求通过统一的 request 封装，返回后端信封中的 data 字段。
 */

import { request } from './http'
import type { CurrentUser } from '@/types/api'

/** 登录请求体。 */
export interface LoginParams {
  username: string
  password: string
}

/** 登录接口。 */
export function apiLogin(params: LoginParams): Promise<CurrentUser> {
  return request<CurrentUser>({
    method: 'POST',
    url: '/auth/login/',
    data: params,
  })
}

/** 登出接口。 */
export function apiLogout(): Promise<null> {
  return request<null>({
    method: 'POST',
    url: '/auth/logout/',
  })
}

/** 获取当前登录用户信息。 */
export function apiGetCurrentUser(): Promise<CurrentUser> {
  return request<CurrentUser>({
    method: 'GET',
    url: '/auth/me/',
  })
}
