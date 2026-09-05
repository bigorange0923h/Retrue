/** Axios 实例与统一拦截器。
 *
 * 职责：
 * - 统一配置 baseURL 与 withCredentials（Session Cookie 认证）。
 * - 响应拦截器解析后端统一信封 {code, message, data}。
 * - 集中处理 401 未登录跳转登录页。
 */

import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

import { ApiCode, type ApiResponse } from '@/types/api'

/** 创建 Axios 实例，携带 Cookie，便于 Session 认证。 */
const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
  withCredentials: true,
})

/** 请求拦截器：为写操作附加 CSRF token（Django Session 认证要求）。 */
http.interceptors.request.use((config) => {
  const method = (config.method || 'get').toUpperCase()
  if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
    const token = getCsrfToken()
    if (token) {
      config.headers['X-CSRFToken'] = token
    }
  }
  return config
})

/** 从 Cookie 读取 Django 的 csrftoken。 */
export function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

/** 响应拦截器：解析统一信封，集中处理错误。 */
http.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse<unknown>
    // 业务成功码才视为成功；其它业务码统一抛出携带 message 的错误
    if (body && typeof body.code === 'number') {
      if (body.code === ApiCode.SUCCESS) {
        return body as unknown as AxiosResponse
      }
      // 未登录：跳转登录页
      if (body.code === ApiCode.UNAUTHORIZED) {
        redirectToLogin()
      }
      return Promise.reject(new ApiBusinessError(body.code, body.message))
    }
    return response.data
  },
  (error: AxiosError<ApiResponse<unknown>>) => {
    const code = error.response?.data?.code ?? ApiCode.SERVER_ERROR
    const message = error.response?.data?.message ?? '网络异常，请稍后重试'
    if (code === ApiCode.UNAUTHORIZED) {
      redirectToLogin()
    }
    ElMessage.error(message)
    return Promise.reject(new ApiBusinessError(code, message))
  },
)

/** 业务错误类，携带后端返回的业务码与消息。 */
export class ApiBusinessError extends Error {
  code: number

  constructor(code: number, message: string) {
    super(message)
    this.name = 'ApiBusinessError'
    this.code = code
  }
}

/** 跳转到登录页，避免模块循环依赖，通过地址栏跳转。 */
export function redirectToLogin(): void {
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

/** 统一请求封装：返回后端 data 字段。 */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await http.request<ApiResponse<T>>(config)
  return (response as unknown as ApiResponse<T>).data
}

// Axios 响应对象类型别名，供拦截器内部使用
type AxiosResponse = ApiResponse<unknown>
