import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  NODE_DEFAULTS,
  NODE_HEIGHT,
  NODE_WIDTH,
  WORLD_HEIGHT,
  WORLD_WIDTH,
  type GraphEdge,
  type GraphNode,
  type ModelConfig,
  type NodeParamValue,
  type NodeType,
} from '@/types/graph'

const HISTORY_LIMIT = 50
const DRAFT_KEY = 'dv_graph_draft'

interface Snapshot {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

let idSeed = 0

function nextId(prefix: string): string {
  idSeed += 1
  return `${prefix}_${Date.now().toString(36)}${idSeed.toString(36)}`
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

export const useGraphStore = defineStore('graph', () => {
  const nodes = ref<GraphNode[]>([])
  const edges = ref<GraphEdge[]>([])
  const selectedNodeId = ref<string | null>(null)
  const selectedEdgeId = ref<string | null>(null)
  const savedAt = ref<string | null>(null)

  const past = ref<Snapshot[]>([])
  const future = ref<Snapshot[]>([])

  const canUndo = computed(() => past.value.length > 0)
  const canRedo = computed(() => future.value.length > 0)

  const selectedNode = computed(
    () => nodes.value.find((node) => node.id === selectedNodeId.value) ?? null,
  )

  function snapshot(): Snapshot {
    return {
      nodes: nodes.value.map((node) => ({ ...node, params: { ...node.params } })),
      edges: edges.value.map((edge) => ({ ...edge })),
    }
  }

  function restore(state: Snapshot): void {
    nodes.value = state.nodes.map((node) => ({
      ...node,
      params: { ...node.params },
    }))
    edges.value = state.edges.map((edge) => ({ ...edge }))
    selectedNodeId.value = null
    selectedEdgeId.value = null
  }

  /** 在任何会改变拓扑的操作前调用 */
  function pushHistory(): void {
    past.value.push(snapshot())
    if (past.value.length > HISTORY_LIMIT) past.value.shift()
    future.value = []
  }

  function undo(): void {
    const previous = past.value.pop()
    if (!previous) return
    future.value.push(snapshot())
    restore(previous)
  }

  function redo(): void {
    const next = future.value.pop()
    if (!next) return
    past.value.push(snapshot())
    restore(next)
  }

  function addNode(type: NodeType, x: number, y: number): GraphNode {
    pushHistory()
    const node: GraphNode = {
      id: nextId(type),
      type,
      params: { ...NODE_DEFAULTS[type] },
      x: clamp(x, 0, WORLD_WIDTH - NODE_WIDTH),
      y: clamp(y, 0, WORLD_HEIGHT - NODE_HEIGHT),
    }
    nodes.value.push(node)
    selectedNodeId.value = node.id
    selectedEdgeId.value = null
    return node
  }

  function removeNode(id: string): void {
    if (!nodes.value.some((node) => node.id === id)) return
    pushHistory()
    nodes.value = nodes.value.filter((node) => node.id !== id)
    edges.value = edges.value.filter(
      (edge) => edge.source !== id && edge.target !== id,
    )
    selectedNodeId.value = null
    selectedEdgeId.value = null
  }

  function moveNode(id: string, x: number, y: number): void {
    const node = nodes.value.find((item) => item.id === id)
    if (!node) return
    node.x = clamp(x, 0, WORLD_WIDTH - NODE_WIDTH)
    node.y = clamp(y, 0, WORLD_HEIGHT - NODE_HEIGHT)
  }

  function updateParams(
    id: string,
    patch: Record<string, NodeParamValue>,
  ): void {
    const node = nodes.value.find((item) => item.id === id)
    if (!node) return
    pushHistory()
    node.params = { ...node.params, ...patch }
  }

  function hasEdge(source: string, target: string): boolean {
    return edges.value.some(
      (edge) => edge.source === source && edge.target === target,
    )
  }

  /** 从 target 出发能否回到 source —— 能则说明新连线会成环 */
  function wouldCreateCycle(source: string, target: string): boolean {
    const adjacency = new Map<string, string[]>()
    for (const edge of edges.value) {
      const list = adjacency.get(edge.source) ?? []
      list.push(edge.target)
      adjacency.set(edge.source, list)
    }
    const stack = [target]
    const visited = new Set<string>()
    while (stack.length > 0) {
      const current = stack.pop() as string
      if (current === source) return true
      if (visited.has(current)) continue
      visited.add(current)
      for (const next of adjacency.get(current) ?? []) stack.push(next)
    }
    return false
  }

  /** 连线前置校验，返回错误文案；null 表示允许 */
  function connectError(source: string, target: string): string | null {
    if (source === target) return '节点不能连接到自身'
    const sourceNode = nodes.value.find((node) => node.id === source)
    const targetNode = nodes.value.find((node) => node.id === target)
    if (!sourceNode || !targetNode) return '节点不存在'
    if (sourceNode.type === 'output') return '输出层之后不能再连接其他层'
    if (targetNode.type === 'input') return '输入层不能作为连线终点'
    if (hasEdge(source, target)) return '这两个节点之间已存在连线'
    if (wouldCreateCycle(source, target)) {
      return '该连线会形成环，神经网络必须是有向无环图'
    }
    return null
  }

  function addEdge(source: string, target: string): string | null {
    const error = connectError(source, target)
    if (error) return error
    pushHistory()
    edges.value.push({ id: nextId('edge'), source, target })
    return null
  }

  function removeEdge(id: string): void {
    if (!edges.value.some((edge) => edge.id === id)) return
    pushHistory()
    edges.value = edges.value.filter((edge) => edge.id !== id)
    selectedEdgeId.value = null
  }

  function selectNode(id: string | null): void {
    selectedNodeId.value = id
    selectedEdgeId.value = null
  }

  function selectEdge(id: string | null): void {
    selectedEdgeId.value = id
    selectedNodeId.value = null
  }

  function clear(): void {
    if (nodes.value.length === 0) return
    pushHistory()
    nodes.value = []
    edges.value = []
    selectedNodeId.value = null
    selectedEdgeId.value = null
  }

  /** 三层 MLP 快速模板 */
  function loadTemplate(): void {
    pushHistory()
    const input: GraphNode = {
      id: nextId('input'),
      type: 'input',
      params: { ...NODE_DEFAULTS.input },
      x: 340,
      y: 160,
    }
    const hidden: GraphNode = {
      id: nextId('hidden'),
      type: 'hidden',
      params: { ...NODE_DEFAULTS.hidden },
      x: 340,
      y: 320,
    }
    const output: GraphNode = {
      id: nextId('output'),
      type: 'output',
      params: { ...NODE_DEFAULTS.output },
      x: 340,
      y: 480,
    }
    nodes.value = [input, hidden, output]
    edges.value = [
      { id: nextId('edge'), source: input.id, target: hidden.id },
      { id: nextId('edge'), source: hidden.id, target: output.id },
    ]
    selectedNodeId.value = null
    selectedEdgeId.value = null
  }

  /** 导出为后端契约（剔除画布坐标） */
  function toModelConfig(): ModelConfig {
    return {
      version: 1,
      nodes: nodes.value.map((node) => ({
        id: node.id,
        type: node.type,
        params: { ...node.params },
      })),
      edges: edges.value.map((edge) => ({
        source: edge.source,
        target: edge.target,
      })),
    }
  }

  function saveDraft(): void {
    const payload = {
      nodes: nodes.value,
      edges: edges.value,
      savedAt: new Date().toISOString(),
    }
    localStorage.setItem(DRAFT_KEY, JSON.stringify(payload))
    savedAt.value = payload.savedAt
  }

  function loadDraft(): boolean {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return false
    try {
      const data = JSON.parse(raw) as {
        nodes?: GraphNode[]
        edges?: GraphEdge[]
        savedAt?: string
      }
      if (!Array.isArray(data.nodes) || !Array.isArray(data.edges)) return false
      nodes.value = data.nodes
      edges.value = data.edges
      savedAt.value = data.savedAt ?? null
      return true
    } catch {
      return false
    }
  }

  function clearDraft(): void {
    localStorage.removeItem(DRAFT_KEY)
    savedAt.value = null
  }

  return {
    nodes,
    edges,
    selectedNodeId,
    selectedEdgeId,
    selectedNode,
    savedAt,
    canUndo,
    canRedo,
    pushHistory,
    undo,
    redo,
    addNode,
    removeNode,
    moveNode,
    updateParams,
    connectError,
    addEdge,
    removeEdge,
    selectNode,
    selectEdge,
    clear,
    loadTemplate,
    toModelConfig,
    saveDraft,
    loadDraft,
    clearDraft,
  }
})
