<script setup lang="ts">
import { computed } from 'vue'

import {
  NODE_HEIGHT,
  NODE_TYPE_ACCENT,
  NODE_WIDTH,
  type GraphEdge,
  type GraphNode,
} from '@/types/graph'

const props = defineProps<{
  nodes: GraphNode[]
  edges: GraphEdge[]
  active: boolean
}>()

const VIEW_WIDTH = 320
const VIEW_HEIGHT = 200

const bounds = computed(() => {
  if (props.nodes.length === 0) {
    return { minX: 0, minY: 0, width: 800, height: 600 }
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

  const padding = 60
  return {
    minX: minX - padding,
    minY: minY - padding,
    width: maxX - minX + padding * 2,
    height: maxY - minY + padding * 2,
  }
})

const ratio = computed(() =>
  Math.min(
    VIEW_WIDTH / Math.max(bounds.value.width, 1),
    VIEW_HEIGHT / Math.max(bounds.value.height, 1),
  ),
)

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
      width: NODE_WIDTH * ratio.value,
      height: NODE_HEIGHT * ratio.value,
      color: NODE_TYPE_ACCENT[node.type],
    }
  }),
)

const nodeMap = computed(() => new Map(props.nodes.map((n) => [n.id, n])))

const edgePaths = computed(() =>
  props.edges
    .map((edge: GraphEdge) => {
      const source = nodeMap.value.get(edge.source)
      const target = nodeMap.value.get(edge.target)
      if (!source || !target) return null

      const start = project(
        source.x + NODE_WIDTH / 2,
        source.y + NODE_HEIGHT,
      )
      const end = project(target.x + NODE_WIDTH / 2, target.y)
      const delta = Math.max(10, Math.abs(end.y - start.y) * 0.5)

      return {
        id: edge.id,
        d: `M ${start.x} ${start.y} C ${start.x} ${start.y + delta}, ${end.x} ${end.y - delta}, ${end.x} ${end.y}`,
      }
    })
    .filter((item): item is { id: string; d: string } => item !== null),
)
</script>

<template>
  <div class="h-full w-full">
    <svg
      :viewBox="`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`"
      class="h-full w-full"
      aria-hidden="true"
    >
      <g v-for="edge in edgePaths" :key="edge.id">
        <path
          :d="edge.d"
          fill="none"
          stroke="rgba(148, 163, 184, 0.28)"
          stroke-width="1.5"
        />
        <!-- 前向传播流光：dashoffset 逐渐减小，视觉上自输入流向输出 -->
        <path
          v-if="active"
          :d="edge.d"
          fill="none"
          stroke="var(--brand-cyan)"
          stroke-width="1.5"
          stroke-dasharray="3 9"
          class="dv-flow"
        />
      </g>

      <g v-for="node in nodeRects" :key="node.id">
        <rect
          :x="node.x"
          :y="node.y"
          :width="node.width"
          :height="node.height"
          rx="4"
          fill="rgba(17, 24, 39, 0.9)"
          :stroke="node.color"
          stroke-width="1.2"
        />
      </g>
    </svg>
  </div>
</template>

<style scoped>
.dv-flow {
  animation: dv-flow 1.2s linear infinite;
}

@keyframes dv-flow {
  to {
    stroke-dashoffset: -12;
  }
}

@media (prefers-reduced-motion: reduce) {
  .dv-flow {
    animation: none;
  }
}
</style>
