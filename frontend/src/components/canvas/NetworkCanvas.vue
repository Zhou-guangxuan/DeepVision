<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import CanvasMinimap from '@/components/canvas/CanvasMinimap.vue'
import CanvasToolbar from '@/components/canvas/CanvasToolbar.vue'
import GraphNodeView from '@/components/canvas/GraphNode.vue'
import { useCanvasViewport } from '@/composables/useCanvasViewport'
import { useGraphStore } from '@/stores/graph'
import {
  GRID_SIZE,
  NODE_HEIGHT,
  NODE_WIDTH,
  WORLD_HEIGHT,
  WORLD_WIDTH,
  type NodeType,
} from '@/types/graph'

const emit = defineEmits<{
  (event: 'notify', message: string): void
  (event: 'validate'): void
}>()

const store = useGraphStore()
const viewportRef = ref<HTMLElement | null>(null)
const viewport = useCanvasViewport(viewportRef)
const viewportSize = ref({ width: 0, height: 0 })

const spacePressed = ref(false)
const isPanning = ref(false)
const dragState = ref<{
  nodeId: string
  pointerX: number
  pointerY: number
  nodeX: number
  nodeY: number
} | null>(null)
const connecting = ref<{ sourceId: string; x: number; y: number } | null>(null)

let dragMoved = false
let panLast = { x: 0, y: 0 }
let resizeObserver: ResizeObserver | null = null

const NODE_TYPES: NodeType[] = ['input', 'hidden', 'output']

const nodeMap = computed(
  () => new Map(store.nodes.map((node) => [node.id, node])),
)

const edgePaths = computed(() =>
  store.edges
    .map((edge) => {
      const source = nodeMap.value.get(edge.source)
      const target = nodeMap.value.get(edge.target)
      if (!source || !target) return null
      const x1 = source.x + NODE_WIDTH / 2
      const y1 = source.y + NODE_HEIGHT
      const x2 = target.x + NODE_WIDTH / 2
      const y2 = target.y
      const delta = Math.max(48, Math.abs(y2 - y1) * 0.5)
      return {
        id: edge.id,
        d: `M ${x1} ${y1} C ${x1} ${y1 + delta}, ${x2} ${y2 - delta}, ${x2} ${y2}`,
        selected: edge.id === store.selectedEdgeId,
      }
    })
    .filter((item): item is { id: string; d: string; selected: boolean } => item !== null),
)

const tempPath = computed(() => {
  if (!connecting.value) return null
  const source = nodeMap.value.get(connecting.value.sourceId)
  if (!source) return null
  const x1 = source.x + NODE_WIDTH / 2
  const y1 = source.y + NODE_HEIGHT
  const x2 = connecting.value.x
  const y2 = connecting.value.y
  const delta = Math.max(40, Math.abs(y2 - y1) * 0.5)
  return `M ${x1} ${y1} C ${x1} ${y1 + delta}, ${x2} ${y2 - delta}, ${x2} ${y2}`
})

const gridStyle = computed(() => ({
  backgroundImage:
    'radial-gradient(circle, rgba(148, 163, 184, 0.16) 1px, transparent 1px)',
  backgroundSize: `${GRID_SIZE * viewport.scale.value}px ${GRID_SIZE * viewport.scale.value}px`,
  backgroundPosition: `${viewport.tx.value}px ${viewport.ty.value}px`,
}))

const cursorStyle = computed(() => {
  if (isPanning.value) return 'grabbing'
  if (spacePressed.value) return 'grab'
  if (connecting.value) return 'crosshair'
  return 'default'
})

function updateSize(): void {
  const element = viewportRef.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  viewportSize.value = { width: rect.width, height: rect.height }
}

function attachWindowListeners(): void {
  window.addEventListener('pointermove', onWindowPointerMove)
  window.addEventListener('pointerup', onWindowPointerUp)
}

function detachWindowListeners(): void {
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointerup', onWindowPointerUp)
}

function onCanvasPointerDown(event: PointerEvent): void {
  // 中键或按住空格：平移
  if (event.button === 1 || spacePressed.value) {
    isPanning.value = true
    panLast = { x: event.clientX, y: event.clientY }
    attachWindowListeners()
    event.preventDefault()
    return
  }

  if (event.button === 0) {
    store.selectNode(null)
    store.selectEdge(null)
  }
}

function onNodePointerDown(nodeId: string, event: PointerEvent): void {
  if (event.button !== 0) return

  store.selectNode(nodeId)
  const node = nodeMap.value.get(nodeId)
  if (!node) return

  dragMoved = false
  dragState.value = {
    nodeId,
    pointerX: event.clientX,
    pointerY: event.clientY,
    nodeX: node.x,
    nodeY: node.y,
  }
  attachWindowListeners()
}

function onNodeDoubleClick(nodeId: string): void {
  const node = nodeMap.value.get(nodeId)
  if (!node) return
  viewport.centerOn(node.x + NODE_WIDTH / 2, node.y + NODE_HEIGHT / 2)
}

function onPortPointerDown(nodeId: string, event: PointerEvent): void {
  const world = viewport.screenToWorld(event.clientX, event.clientY)
  connecting.value = { sourceId: nodeId, x: world.x, y: world.y }
  attachWindowListeners()
}

function onWindowPointerMove(event: PointerEvent): void {
  if (isPanning.value) {
    viewport.panBy(event.clientX - panLast.x, event.clientY - panLast.y)
    panLast = { x: event.clientX, y: event.clientY }
    return
  }

  if (dragState.value) {
    const dx = (event.clientX - dragState.value.pointerX) / viewport.scale.value
    const dy = (event.clientY - dragState.value.pointerY) / viewport.scale.value

    // 超过阈值才计为拖动，避免单击也产生历史记录
    if (!dragMoved && (Math.abs(dx) > 2 || Math.abs(dy) > 2)) {
      store.pushHistory()
      dragMoved = true
    }
    if (dragMoved) {
      store.moveNode(
        dragState.value.nodeId,
        dragState.value.nodeX + dx,
        dragState.value.nodeY + dy,
      )
    }
    return
  }

  if (connecting.value) {
    const world = viewport.screenToWorld(event.clientX, event.clientY)
    connecting.value = { ...connecting.value, x: world.x, y: world.y }
  }
}

function onWindowPointerUp(event: PointerEvent): void {
  if (connecting.value) {
    const element = document.elementFromPoint(event.clientX, event.clientY)
    const target = element?.closest('[data-node-id]') as HTMLElement | null
    const sourceId = connecting.value.sourceId
    connecting.value = null

    if (target?.dataset.nodeId) {
      const error = store.addEdge(sourceId, target.dataset.nodeId)
      if (error) emit('notify', error)
    }
  }

  dragState.value = null
  dragMoved = false
  isPanning.value = false
  detachWindowListeners()
}

function onDrop(event: DragEvent): void {
  const rawType = event.dataTransfer?.getData('application/x-deepvision-node')
  if (!rawType) return
  const type = rawType as NodeType
  if (!NODE_TYPES.includes(type)) return

  const world = viewport.screenToWorld(event.clientX, event.clientY)
  store.addNode(type, world.x - NODE_WIDTH / 2, world.y - NODE_HEIGHT / 2)
}

function addNodeAtCenter(type: NodeType): void {
  const element = viewportRef.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  const world = viewport.screenToWorld(
    rect.left + rect.width / 2,
    rect.top + rect.height / 2,
  )
  store.addNode(type, world.x - NODE_WIDTH / 2, world.y - NODE_HEIGHT / 2)
}

function onMinimapNavigate(worldX: number, worldY: number): void {
  viewport.centerOn(worldX, worldY)
}

function onKeyDown(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null
  if (
    target &&
    ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName)
  ) {
    return
  }

  if (event.code === 'Space') {
    spacePressed.value = true
    event.preventDefault()
    return
  }

  if (event.key === 'Delete' || event.key === 'Backspace') {
    if (store.selectedNodeId) {
      store.removeNode(store.selectedNodeId)
      event.preventDefault()
    } else if (store.selectedEdgeId) {
      store.removeEdge(store.selectedEdgeId)
      event.preventDefault()
    }
    return
  }

  if (event.ctrlKey || event.metaKey) {
    const key = event.key.toLowerCase()
    if (key === 'z') {
      event.preventDefault()
      if (event.shiftKey) store.redo()
      else store.undo()
    } else if (key === 'y') {
      event.preventDefault()
      store.redo()
    } else if (key === 's') {
      event.preventDefault()
      store.saveDraft()
    }
  }

  if (event.key === 'Escape') {
    connecting.value = null
    dragState.value = null
    isPanning.value = false
    detachWindowListeners()
  }
}

function onKeyUp(event: KeyboardEvent): void {
  if (event.code === 'Space') spacePressed.value = false
}

onMounted(() => {
  updateSize()
  if (typeof ResizeObserver !== 'undefined' && viewportRef.value) {
    resizeObserver = new ResizeObserver(updateSize)
    resizeObserver.observe(viewportRef.value)
  }
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  detachWindowListeners()
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
})

defineExpose({ addNodeAtCenter })
</script>

<template>
  <div
    ref="viewportRef"
    class="relative h-full min-h-0 w-full overflow-hidden"
    :style="{ background: 'var(--bg-base)', cursor: cursorStyle }"
    @wheel.prevent="viewport.onWheel($event)"
    @pointerdown="onCanvasPointerDown"
    @dragover.prevent
    @drop.prevent="onDrop"
  >
    <!-- 点阵网格 -->
    <div class="pointer-events-none absolute inset-0" :style="gridStyle" />

    <!-- 世界坐标层 -->
    <div
      class="absolute left-0 top-0 origin-top-left"
      :style="{ transform: viewport.transform.value }"
    >
      <svg
        class="pointer-events-none absolute left-0 top-0 overflow-visible"
        :width="WORLD_WIDTH"
        :height="WORLD_HEIGHT"
        aria-hidden="true"
      >
        <g v-for="edge in edgePaths" :key="edge.id">
          <path
            :d="edge.d"
            fill="none"
            stroke="transparent"
            stroke-width="14"
            style="pointer-events: stroke; cursor: pointer"
            @pointerdown.stop="store.selectEdge(edge.id)"
          />
          <path
            :d="edge.d"
            fill="none"
            :stroke="edge.selected ? 'var(--brand-cyan)' : 'var(--border-default)'"
            :stroke-width="edge.selected ? 2.5 : 1.5"
          />
        </g>

        <path
          v-if="tempPath"
          :d="tempPath"
          fill="none"
          stroke="var(--brand-cyan)"
          stroke-width="1.5"
          stroke-dasharray="6 6"
        />
      </svg>

      <GraphNodeView
        v-for="node in store.nodes"
        :key="node.id"
        :node="node"
        :selected="node.id === store.selectedNodeId"
        @node-pointerdown="onNodePointerDown(node.id, $event)"
        @port-pointerdown="onPortPointerDown(node.id, $event)"
        @dblclick="onNodeDoubleClick(node.id)"
      />
    </div>

    <!-- 顶部浮动工具栏 -->
    <div class="absolute right-3 top-3 flex items-start gap-2" @pointerdown.stop>
      <CanvasToolbar
        :scale-percent="viewport.scalePercent.value"
        :can-undo="store.canUndo"
        :can-redo="store.canRedo"
        :saved-at="store.savedAt"
        :node-count="store.nodes.length"
        @zoom-in="viewport.zoomAtCenter(1.1)"
        @zoom-out="viewport.zoomAtCenter(1 / 1.1)"
        @reset="viewport.reset()"
        @undo="store.undo()"
        @redo="store.redo()"
        @template="store.loadTemplate()"
        @clear="store.clear()"
        @validate="emit('validate')"
      />
    </div>

    <!-- 空状态 -->
    <div
      v-if="store.nodes.length === 0"
      class="pointer-events-none absolute inset-0 grid place-items-center"
    >
      <div class="pointer-events-auto flex max-w-sm flex-col items-center gap-4 text-center">
        <div
          class="grid h-16 w-16 place-items-center rounded-full border"
          :style="{ borderColor: 'var(--border-default)' }"
        >
          <span class="h-2.5 w-2.5 rounded-full bg-brand-cyan dv-pulse" />
        </div>
        <div>
          <p class="text-sm text-primary">从左侧拖入节点开始搭建</p>
          <p class="mt-1.5 text-xs leading-relaxed text-muted">
            拖入输入层、隐藏层与输出层，再用节点下方的圆点拖出连线。
          </p>
        </div>
        <button
          type="button"
          class="dv-btn dv-btn--secondary dv-btn--sm"
          @click="store.loadTemplate()"
        >
          三层 MLP 快速模板
        </button>
      </div>
    </div>

    <!-- 小地图 -->
    <div class="pointer-events-none absolute bottom-3 right-3" @pointerdown.stop>
      <CanvasMinimap
        :nodes="store.nodes"
        :tx="viewport.tx.value"
        :ty="viewport.ty.value"
        :scale="viewport.scale.value"
        :viewport-width="viewportSize.width"
        :viewport-height="viewportSize.height"
        @navigate="onMinimapNavigate"
      />
    </div>

    <!-- 操作提示 -->
    <p
      class="pointer-events-none absolute bottom-3 left-3 text-[11px] leading-relaxed text-muted"
    >
      滚轮缩放 · 空格/中键拖拽平移 · Delete 删除 · Ctrl+Z 撤销
    </p>
  </div>
</template>
