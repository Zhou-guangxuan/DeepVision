import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/workspace',
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/workspace',
      name: 'workspace',
      component: () => import('@/views/WorkspaceView.vue'),
    },
    {
      path: '/data',
      name: 'data',
      component: () => import('@/views/DataView.vue'),
    },
    {
      path: '/train/:taskId',
      name: 'train',
      component: () => import('@/views/TrainView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/workspace',
    },
  ],
})

// 路由守卫：未登录访问受保护页面 → 重定向到 /login，并记录来源
router.beforeEach((to) => {
  const auth = useAuthStore()

  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'workspace' }
  }

  return true
})

export default router
