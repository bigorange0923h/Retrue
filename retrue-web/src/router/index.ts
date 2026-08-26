/** 前端路由配置与守卫。
 *
 * 守卫逻辑：访问受保护页面时若未登录则重定向到登录页；
 * 已登录访问登录页则重定向到首页。
 */

import { createRouter, createWebHistory } from 'vue-router'

import { useUserStore } from '@/stores/user'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: '登录', public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/DesktopLayout.vue'),
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { title: '今日工作台' },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

router.beforeEach(async (to) => {
  const userStore = useUserStore()

  // 首次进入尝试恢复会话
  if (!userStore.initialized) {
    await userStore.fetchCurrentUser()
  }

  const isPublic = to.matched.some((record) => record.meta.public)
  if (!isPublic && !userStore.isLoggedIn) {
    return { name: 'login' }
  }
  if (isPublic && userStore.isLoggedIn) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
