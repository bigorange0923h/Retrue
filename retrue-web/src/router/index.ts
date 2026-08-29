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
        {
          path: 'customers',
          name: 'customer-list',
          component: () => import('@/views/customers/CustomerListView.vue'),
          meta: { title: '客户管理' },
        },
        {
          path: 'schedule',
          name: 'schedule',
          component: () => import('@/views/ScheduleView.vue'),
          meta: { title: '课程管理' },
        },
        {
          path: 'course-types',
          name: 'course-types',
          component: () => import('@/views/courses/CourseTypeListView.vue'),
          meta: { title: '课程类型' },
        },
        {
          path: 'customer-courses',
          name: 'customer-courses',
          component: () => import('@/views/courses/CustomerCourseView.vue'),
          meta: { title: '客户疗程' },
        },
        {
          path: 'knowledge',
          name: 'knowledge',
          component: () => import('@/views/knowledge/KnowledgeView.vue'),
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
          path: 'ai-draft',
          name: 'ai-draft',
          component: () => import('@/views/ai/AiDraftView.vue'),
          meta: { title: 'AI 训练记录' },
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
          component: () => import('@/views/accounts/AccountsView.vue'),
          meta: { title: '账号管理', adminOnly: true },
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
