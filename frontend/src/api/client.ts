import axios, { AxiosError } from 'axios'

import { useToastStore } from '@/stores/toast'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 静默请求：不触发全局 Toast 与 401 跳转，由调用方自行处理错误 */
    silent?: boolean
  }
}

export const TOKEN_KEY = 'dv_token'

/** 这些端点自行处理 401（例如登录失败要显示在表单里，而不是跳转） */
const AUTH_ENDPOINTS = ['/auth/login', '/auth/register']

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 15000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

interface ApiErrorBody {
  code?: string
  message?: string
}

function resolveMessage(error: AxiosError<ApiErrorBody>): string {
  if (error.response?.data?.message) {
    return error.response.data.message
  }
  if (error.code === 'ECONNABORTED') {
    return '请求超时，请稍后重试'
  }
  if (!error.response) {
    return '网络异常，请确认后端服务已启动'
  }
  return `请求失败（HTTP ${error.response.status}）`
}

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorBody>) => {
    const config = error.config
    const status = error.response?.status
    const url = config?.url ?? ''
    const isAuthEndpoint = AUTH_ENDPOINTS.some((path) => url.includes(path))
    const silent = config?.silent === true

    // 认证端点的错误由表单内联展示，避免重复提示
    if (!silent && !isAuthEndpoint) {
      useToastStore().error(resolveMessage(error))
    } else if (!silent && isAuthEndpoint && status !== 401) {
      useToastStore().error(resolveMessage(error))
    }

    // 401：清除本地凭证并回到登录页
    if (status === 401 && !isAuthEndpoint && !silent) {
      localStorage.removeItem(TOKEN_KEY)
      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }

    return Promise.reject(error)
  },
)
