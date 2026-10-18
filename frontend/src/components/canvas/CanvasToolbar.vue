<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  scalePercent: number
  canUndo: boolean
  canRedo: boolean
  savedAt: string | null
  nodeCount: number
}>()

const emit = defineEmits<{
  (event: 'zoom-in'): void
  (event: 'zoom-out'): void
  (event: 'reset'): void
  (event: 'undo'): void
  (event: 'redo'): void
  (event: 'template'): void
  (event: 'clear'): void
  (event: 'validate'): void
}>()

const savedLabel = computed(() => {
  if (!props.savedAt) return '尚未保存'
  const date = new Date(props.savedAt)
  if (Number.isNaN(date.getTime())) return '尚未保存'
  return `已保存 ${date.toLocaleTimeString('zh-CN', { hour12: false })}`
})

const buttonClass =
  'grid h-8 w-8 place-items-center rounded-sm text-sm text-secondary transition-colors duration-fast hover:text-primary disabled:cursor-not-allowed disabled:opacity-40'
</script>

<template>
  <div
    class="pointer-events-auto flex items-center gap-1 rounded-md border px-2 py-1.5"
    :style="{
      background: 'rgba(17, 24, 39, 0.9)',
      borderColor: 'var(--border-default)',
      backdropFilter: 'blur(8px)',
    }"
  >
    <button
      type="button"
      :class="buttonClass"
      title="撤销 (Ctrl+Z)"
      :disabled="!canUndo"
      @click="emit('undo')"
    >
      ↶
    </button>
    <button
      type="button"
      :class="buttonClass"
      title="重做 (Ctrl+Y)"
      :disabled="!canRedo"
      @click="emit('redo')"
    >
      ↷
    </button>

    <span class="mx-1 h-5 w-px" :style="{ background: 'var(--border-subtle)' }" />

    <button
      type="button"
      :class="buttonClass"
      title="缩小"
      @click="emit('zoom-out')"
    >
      −
    </button>
    <button
      type="button"
      class="h-8 min-w-[52px] rounded-sm px-1 text-xs text-secondary transition-colors duration-fast hover:text-primary"
      title="重置为 100%"
      @click="emit('reset')"
    >
      {{ scalePercent }}%
    </button>
    <button
      type="button"
      :class="buttonClass"
      title="放大"
      @click="emit('zoom-in')"
    >
      +
    </button>

    <span class="mx-1 h-5 w-px" :style="{ background: 'var(--border-subtle)' }" />

    <button
      type="button"
      class="h-8 rounded-sm px-2 text-xs text-secondary transition-colors duration-fast hover:text-primary disabled:cursor-not-allowed disabled:opacity-40"
      title="插入三层 MLP 模板"
      :disabled="nodeCount > 0"
      @click="emit('template')"
    >
      模板
    </button>
    <button
      type="button"
      class="h-8 rounded-sm px-2 text-xs text-secondary transition-colors duration-fast hover:text-danger disabled:cursor-not-allowed disabled:opacity-40"
      title="清空画布"
      :disabled="nodeCount === 0"
      @click="emit('clear')"
    >
      清空
    </button>
    <button
      type="button"
      class="h-8 rounded-sm px-2 text-xs text-brand-cyan transition-colors duration-fast hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
      title="调用后端校验拓扑"
      :disabled="nodeCount === 0"
      @click="emit('validate')"
    >
      校验
    </button>

    <span class="ml-1 text-[11px] text-muted">{{ savedLabel }}</span>
  </div>
</template>
