<script setup lang="ts">
import {
  NODE_DEFAULTS,
  NODE_TYPE_ACCENT,
  NODE_TYPE_LABEL,
  nodeSummary,
  type GraphNode,
  type NodeType,
} from '@/types/graph'

const emit = defineEmits<{
  (event: 'add', type: NodeType): void
}>()

interface LibraryItem {
  type: NodeType
  description: string
}

const items: LibraryItem[] = [
  { type: 'input', description: '网络入口，指定特征维度' },
  { type: 'hidden', description: '全连接层，可设神经元与激活函数' },
  { type: 'output', description: '网络出口，指定类别数或回归' },
]

/** 用默认参数生成一行摘要，作为节点库的预览文案 */
function preview(type: NodeType): string {
  const node: GraphNode = {
    id: 'preview',
    type,
    params: { ...NODE_DEFAULTS[type] },
    x: 0,
    y: 0,
  }
  return nodeSummary(node)
}

function onDragStart(event: DragEvent, type: NodeType): void {
  if (!event.dataTransfer) return
  event.dataTransfer.setData('application/x-deepvision-node', type)
  event.dataTransfer.effectAllowed = 'copy'
}
</script>

<template>
  <aside
    class="flex h-full w-60 shrink-0 flex-col border-r"
    :style="{
      borderColor: 'var(--border-subtle)',
      background: 'var(--bg-surface)',
    }"
  >
    <div class="px-4 pb-3 pt-4">
      <h2 class="text-sm font-semibold text-primary">节点库</h2>
      <p class="mt-1 text-xs leading-relaxed text-muted">
        拖到画布，或点击直接添加到中央
      </p>
    </div>

    <div class="flex-1 space-y-2 overflow-y-auto px-3 pb-4">
      <button
        v-for="item in items"
        :key="item.type"
        type="button"
        draggable="true"
        class="w-full cursor-grab rounded-md border p-3 text-left transition-colors duration-fast"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'var(--bg-elevated)',
        }"
        @dragstart="onDragStart($event, item.type)"
        @click="emit('add', item.type)"
      >
        <div class="flex items-center gap-1.5">
          <span
            class="h-1.5 w-1.5 rounded-full"
            :style="{ background: NODE_TYPE_ACCENT[item.type] }"
          />
          <span class="text-xs font-medium text-primary">
            {{ NODE_TYPE_LABEL[item.type] }}
          </span>
        </div>
        <p class="mt-1.5 font-mono text-xs text-secondary">
          {{ preview(item.type) }}
        </p>
        <p class="mt-1 text-[11px] leading-relaxed text-muted">
          {{ item.description }}
        </p>
      </button>
    </div>

    <div
      class="border-t px-4 py-3"
      :style="{ borderColor: 'var(--border-subtle)' }"
    >
      <p class="text-[11px] leading-relaxed text-muted">
        支持分支与汇合：多个前驱的节点会按
        <b class="font-medium text-secondary">特征维 concat</b> 合并。
      </p>
    </div>
  </aside>
</template>
