import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { fetchMe, login as loginApi, register as registerApi } from '@/api/auth'
import type { User } from '@/api/auth'
import { TOKEN_KEY } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<User | null>(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value))

  function setToken(value: string | null): void {
    token.value = value
    if (value) {
      localStorage.setItem(TOKEN_KEY, value)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
  }

  async function login(username: string, password: string): Promise<void> {
    loading.value = true
    try {
      const res = await loginApi(username, password)
      setToken(res.access_token)
      user.value = res.user
    } finally {
      loading.value = false
    }
  }

  async function register(username: string, password: string): Promise<void> {
    loading.value = true
    try {
      await registerApi(username, password)
    } finally {
      loading.value = false
    }
  }

  async function loadMe(): Promise<void> {
    if (!token.value) return
    try {
      user.value = await fetchMe()
    } catch {
      // 401 已由 Axios 拦截器统一处理
    }
  }

  function logout(): void {
    setToken(null)
    user.value = null
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    login,
    register,
    loadMe,
    logout,
    setToken,
  }
})
