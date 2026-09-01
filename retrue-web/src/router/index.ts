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
          component: () => import('@/views/adaptive/AdaptiveDashboardView.vue'),
          meta: { title: '首页' },
        },
        {
          path: 'customers',
          name: 'customer-list',
          component: () => import('@/views/adaptive/AdaptiveCustomerListView.vue'),
          meta: { title: '客户' },
        },
        {
          path: 'schedule',
          name: 'schedule',
          component: () => import('@/views/adaptive/AdaptiveScheduleView.vue'),
          meta: { title: '课表' },
        },
        {
          path: 'course-types',
          name: 'course-types',
          component: () => import('@/views/adaptive/AdaptiveCourseTypeView.vue'),
          meta: { title: '课程模板与计划模板' },
        },
        {
          path: 'knowledge',
          name: 'knowledge',
          component: () => import('@/views/adaptive/AdaptiveKnowledgeView.vue'),
          meta: { title: '客户知识库' },
        },
        {
          path: 'customers/:id',
          name: 'customer-detail',
          component: () => import('@/views/customers/CustomerDetailView.vue'),
          meta: { title: '客户详情' },
        },
        {
          path: 'training/edit',
          name: 'training-edit',
          component: () => import('@/views/training/TrainingRecordEditView.vue'),
          meta: { title: '训练记录' },
        },
        {
          path: 'training/:id/edit',
          name: 'training-revise',
          component: () => import('@/views/training/TrainingRecordEditView.vue'),
          meta: { title: '修订训练记录' },
        },
        {
          path: 'assistant',
          name: 'assistant',
          component: () => import('@/views/assistant/AssistantView.vue'),
          meta: { title: '智能助理' },
        },
        {
          path: 'ai-draft',
          name: 'ai-draft',
          redirect: (to) => ({
            name: 'assistant',
            query: {
              ...to.query,
              mode: 'training',
              theme: to.query.theme || 'smart',
            },
          }),
          meta: { title: '训练补记' },
        },
        {
          path: 'assessment/edit',
          name: 'assessment-edit',
          component: () => import('@/views/assessment/AssessmentEditView.vue'),
          meta: { title: '评估' },
        },
        {
          path: 'assessment/:id/edit',
          name: 'assessment-revise',
          component: () => import('@/views/assessment/AssessmentEditView.vue'),
          meta: { title: '编辑评估' },
        },
        {
          path: 'accounts',
          name: 'accounts',
          component: () => import('@/views/adaptive/AdaptiveAccountsView.vue'),
          meta: { title: '账号管理', adminOnly: true },
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('@/views/ProfileView.vue'),
          meta: { title: '我的' },
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
  // 管理页面：仅超级用户可访问（后端同样强制校验）
  const requiresAdmin = to.matched.some((record) => record.meta.adminOnly)
  if (requiresAdmin && !userStore.currentUser?.is_superuser) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
