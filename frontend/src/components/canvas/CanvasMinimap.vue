<script setup lang="ts">
import { computed } from 'vue'

import {
  NODE_HEIGHT,
  NODE_TYPE_ACCENT,
  NODE_WIDTH,
  type GraphNode,
} from '@/types/graph'

const MINIMAP_WIDTH = 168
const MINIMAP_HEIGHT = 118

const props = defineProps<{
  nodes: GraphNode[]
  tx: number
  ty: number
  scale: number
  viewportWidth: number
  viewportHeight: number
}>()

const emit = defineEmits<{
  (event: 'navigate', worldX: number, worldY: number): void
}>()

const bounds = computed(() => {
  if (props.nodes.length === 0) {
    return { minX: 0, minY: 0, width: 1200, height: 800 }
  }
  let minX = Number.POSITIVE_INFINITY
  let minY = Number.POSITIVE_INFINITY
  let maxX = Number.NEGATIVE_INFINITY
  let maxY = Number.NEGATIVE_INFINITY
  for (const node of props.nodes) {
    minX = Math.min(minX, node.x)
    minY = Math.min(minY, node.y)
    maxX = Math.max(maxX, node.x + NODE_WIDTH)
    maxY = Math.max(maxY, node.y + NODE_HEIGHT)
  }
  const padding = 140
  return {
    minX: minX - padding,
    minY: minY - padding,
    width: maxX - minX + padding * 2,
    height: maxY - minY + padding * 2,
  }
})

const ratio = computed(() =>
  Math.min(
    MINIMAP_WIDTH / Math.max(bounds.value.width, 1),
    MINIMAP_HEIGHT / Math.max(bounds.value.height, 1),
  ),
)

/** 世界坐标 → 小地图坐标 */
function project(x: number, y: number) {
  return {
    x: (x - bounds.value.minX) * ratio.value,
    y: (y - bounds.value.minY) * ratio.value,
  }
}

const nodeRects = computed(() =>
  props.nodes.map((node) => {
    const point = project(node.x, node.y)
    return {
      id: node.id,
      x: point.x,
      y: point.y,
      width: Math.max(NODE_WIDTH * ratio.value, 3),
      height: Math.max(NODE_HEIGHT * ratio.value, 3),
      color: NODE_TYPE_ACCENT[node.type],
    }
  }),
)

/** 当前视口在世界坐标中的矩形 */
const viewportRect = computed(() => {
  const left = -props.tx / props.scale
  const top = -props.ty / props.scale
  const point = project(left, top)
  return {
    x: point.x,
    y: point.y,
    width: (props.viewportWidth / props.scale) * ratio.value,
    height: (props.viewportHeight / props.scale) * ratio.value,
  }
})

function onClick(event: MouseEvent): void {
  const target = event.currentTarget as HTMLElement | null
  if (!target) return
  const rect = target.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  emit(
    'navigate',
    bounds.value.minX + x / ratio.value,
    bounds.value.minY + y / ratio.value,
  )
}
</script>

<template>
  <div
    class="pointer-events-auto cursor-pointer overflow-hidden rounded-md border"
    :style="{
      width: `${MINIMAP_WIDTH}px`,
      height: `${MINIMAP_HEIGHT}px`,
      background: 'rgba(10, 14, 26, 0.85)',
      borderColor: 'var(--border-default)',
      backdropFilter: 'blur(8px)',
    }"
    aria-hidden="true"
    @click="onClick"
  >
    <svg :width="MINIMAP_WIDTH" :height="MINIMAP_HEIGHT">
      <rect
        v-for="item in nodeRects"
        :key="item.id"
        :x="item.x"
        :y="item.y"
        :width="item.width"
        :height="item.height"
        :fill="item.color"
        fill-opacity="0.55"
        rx="2"
      />
      <rect
        :x="viewportRect.x"
        :y="viewportRect.y"
        :width="viewportRect.width"
        :height="viewportRect.height"
        fill="none"
        stroke="var(--brand-cyan)"
        stroke-width="1"
        stroke-opacity="0.8"
      />
    </svg>
  </div>
</template>
