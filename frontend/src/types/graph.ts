/** 网络拓扑的类型定义与常量，对应设计文档 §6.3 的 model_config 契约。 */

export type NodeType = 'input' | 'hidden' | 'output'
export type Activation = 'relu' | 'sigmoid' | 'tanh'
export type TaskType = 'classification' | 'regression'
export type NodeParamValue = number | string

/** 画布中的节点：比 model_config 多出 x / y，导出时会被剔除 */
export interface GraphNode {
  id: string
  type: NodeType
  params: Record<string, NodeParamValue>
  x: number
  y: number
}

export interface GraphEdge {
  id: string
  source: string
  target: string
}

export interface ModelConfigNode {
  id: string
  type: NodeType
  params: Record<string, NodeParamValue>
}

export interface ModelConfigEdge {
  source: string
  target: string
}

export interface ModelConfig {
  version: number
  nodes: ModelConfigNode[]
  edges: ModelConfigEdge[]
}

/** 节点视觉尺寸（px，世界坐标） */
export const NODE_WIDTH = 152
export const NODE_HEIGHT = 76
export const GRID_SIZE = 24
export const WORLD_WIDTH = 4000
export const WORLD_HEIGHT = 3000

export const NODE_TYPE_LABEL: Record<NodeType, string> = {
  input: '输入层',
  hidden: '隐藏层',
  output: '输出层',
}

export const NODE_TYPE_ACCENT: Record<NodeType, string> = {
  input: 'var(--brand-cyan)',
  hidden: 'var(--brand-violet)',
  output: 'var(--success)',
}

export const NODE_DEFAULTS: Record<NodeType, Record<string, NodeParamValue>> = {
  input: { features: 8 },
  hidden: { units: 128, activation: 'relu' },
  output: { units: 2, task: 'classification' },
}

export const ACTIVATIONS: Activation[] = ['relu', 'sigmoid', 'tanh']
export const TASKS: TaskType[] = ['classification', 'regression']

export const ACTIVATION_LABEL: Record<Activation, string> = {
  relu: 'ReLU',
  sigmoid: 'Sigmoid',
  tanh: 'Tanh',
}

/** 节点上显示的一行摘要，例如 `128 · ReLU` */
export function nodeSummary(node: GraphNode): string {
  if (node.type === 'input') {
    return `${node.params.features ?? '—'} 个特征`
  }
  if (node.type === 'hidden') {
    const activation =
      typeof node.params.activation === 'string'
        ? (ACTIVATION_LABEL[node.params.activation as Activation] ??
          node.params.activation)
        : '—'
    return `${node.params.units ?? '—'} · ${activation}`
  }
  const task = node.params.task === 'regression' ? '回归' : '分类'
  return `${node.params.units ?? '—'} · ${task}`
}
