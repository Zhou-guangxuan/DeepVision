<script setup lang="ts">
import { storeToRefs } from 'pinia'

import { useToastStore } from '@/stores/toast'
import type { ToastType } from '@/stores/toast'

const toast = useToastStore()
const { items } = storeToRefs(toast)

const DOT_CLASS: Record<ToastType, string> = {
  success: 'bg-success',
  error: 'bg-danger',
  info: 'bg-info',
}
</script>

<template>
  <Teleport to="body">
    <div
      class="pointer-events-none fixed right-4 top-4 z-[100] flex w-full max-w-[380px] flex-col gap-2"
      aria-live="polite"
      aria-atomic="false"
    >
      <TransitionGroup name="toast">
        <div
          v-for="item in items"
          :key="item.id"
          class="dv-toast pointer-events-auto"
          :class="`dv-toast--${item.type}`"
        >
          <span
            class="mt-1.5 h-2 w-2 shrink-0 rounded-full"
            :class="DOT_CLASS[item.type]"
            aria-hidden="true"
          />
          <p class="flex-1">{{ item.message }}</p>
          <button
            class="shrink-0 px-1 text-lg leading-none text-muted transition-colors duration-fast hover:text-primary"
            aria-label="关闭提示"
            @click="toast.remove(item.id)"
          >
            ×
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity var(--dur-base) var(--ease-standard),
    transform var(--dur-base) var(--ease-standard);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
</style>
