<script setup lang="ts">
import { computed } from 'vue'

import {
  NODE_HEIGHT,
  NODE_TYPE_ACCENT,
  NODE_TYPE_LABEL,
  NODE_WIDTH,
  nodeSummary,
  type GraphNode,
} from '@/types/graph'

const props = defineProps<{
  node: GraphNode
  selected: boolean
  /** 0~1，用于「权重 / 梯度 / 激活」视图下的发光强度 */
  intensity?: number
}>()

const emit = defineEmits<{
  (event: 'node-pointerdown', payload: PointerEvent): void
  (event: 'port-pointerdown', payload: PointerEvent): void
}>()

const accent = computed(() => NODE_TYPE_ACCENT[props.node.type])
const summary = computed(() => nodeSummary(props.node))
const intensity = computed(() => props.intensity ?? 0)
const showInputPort = computed(() => props.node.type !== 'input')
const showOutputPort = computed(() => props.node.type !== 'output')
</script>

<template>
  <div
    :data-node-id="node.id"
    class="absolute cursor-grab select-none rounded-lg border p-3"
    :style="{
      left: `${node.x}px`,
      top: `${node.y}px`,
      width: `${NODE_WIDTH}px`,
      height: `${NODE_HEIGHT}px`,
      background: 'var(--bg-surface)',
      borderColor: selected ? accent : 'var(--border-default)',
      borderWidth: selected ? '2px' : '1px',
      boxShadow: selected
        ? '0 0 20px rgba(34, 211, 238, 0.22)'
        : intensity > 0.02
          ? `0 0 ${Math.round(8 + intensity * 18)}px rgba(34, 211, 238, ${(0.12 + intensity * 0.3).toFixed(2)})`
          : 'none',
    }"
    @pointerdown.stop="emit('node-pointerdown', $event)"
  >
    <!-- 输入端口（仅视觉，落点由画布命中检测） -->
    <span
      v-if="showInputPort"
      class="absolute left-1/2 h-2.5 w-2.5 -translate-x-1/2 rounded-full border"
      :style="{
        top: '-6px',
        background: 'var(--bg-base)',
        borderColor: accent,
      }"
      aria-hidden="true"
    />

    <div class="flex items-center gap-1.5">
      <span class="h-1.5 w-1.5 rounded-full" :style="{ background: accent }" />
      <span class="text-xs text-secondary">{{ NODE_TYPE_LABEL[node.type] }}</span>
    </div>

    <p class="mt-2 truncate font-mono text-sm text-primary">{{ summary }}</p>

    <!-- 输出端口：从这里拖出连线 -->
    <button
      v-if="showOutputPort"
      type="button"
      class="absolute left-1/2 h-3 w-3 -translate-x-1/2 cursor-crosshair rounded-full border-2"
      :style="{
        bottom: '-7px',
        background: 'var(--bg-base)',
        borderColor: accent,
      }"
      :aria-label="`从 ${NODE_TYPE_LABEL[node.type]} 拖出连线`"
      @pointerdown.stop.prevent="emit('port-pointerdown', $event)"
    />
  </div>
</template>
