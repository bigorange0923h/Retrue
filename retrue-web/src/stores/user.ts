/** 用户会话 Pinia store。
 *
 * 职责：维护当前登录用户信息、登录/登出动作。
 */

import { defineStore } from 'pinia'

import { apiGetCurrentUser, apiLogin, apiLogout } from '@/api/auth'
import type { CurrentUser } from '@/types/api'

interface UserState {
  currentUser: CurrentUser | null
  /** 是否已初始化（尝试拉取过一次当前用户）。 */
  initialized: boolean
}

export const useUserStore = defineStore('user', {
  state: (): UserState => ({
    currentUser: null,
    initialized: false,
  }),

  getters: {
    /** 是否已登录。 */
    isLoggedIn: (state): boolean => state.currentUser !== null,
  },

  actions: {
    /** 登录：调用后端并保存当前用户。 */
    async login(username: string, password: string): Promise<void> {
      const user = await apiLogin({ username, password })
      this.currentUser = user
      this.initialized = true
    },

    /** 登出：调用后端并清空本地状态。 */
    async logout(): Promise<void> {
      try {
        await apiLogout()
      } finally {
        this.currentUser = null
      }
    },

    /** 应用启动时尝试拉取当前用户，用于恢复会话。 */
    async fetchCurrentUser(): Promise<void> {
      try {
        this.currentUser = await apiGetCurrentUser()
      } catch {
        this.currentUser = null
      } finally {
        this.initialized = true
      }
    },
  },
})
