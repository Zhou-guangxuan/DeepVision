import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  type: ToastType
  message: string
}

let seed = 0

export const useToastStore = defineStore('toast', () => {
  const items = ref<ToastItem[]>([])

  function push(type: ToastType, message: string, duration = 4000): number {
    const id = ++seed
    items.value.push({ id, type, message })
    if (duration > 0) {
      window.setTimeout(() => remove(id), duration)
    }
    return id
  }

  function remove(id: number): void {
    items.value = items.value.filter((item) => item.id !== id)
  }

  const success = (message: string) => push('success', message)
  const error = (message: string) => push('error', message)
  const info = (message: string) => push('info', message)

  return { items, push, remove, success, error, info }
})
