import { onBeforeUnmount, ref } from 'vue'

import { TOKEN_KEY } from '@/api/client'

export interface LabEpochEvent {
  type: 'epoch'
  epoch: number
  total_epochs: number
  train_loss: number
  val_loss: number
  accuracy: number
  grad_norm: number
  elapsed_ms: number
}

export interface LabWeightsEvent {
  type: 'weights'
  counts: number[]
  edges: number[]
  min: number
  max: number
  total: number
}

export interface LabPoint {
  x: number
  y: number
  label: number
}

export interface LabBoundaryEvent {
  type: 'boundary'
  size: number
  min: number
  max: number
  values: number[]
  points: LabPoint[]
}

export interface LabStartedEvent {
  type: 'started'
  task_id: string
  total_epochs: number
  parameter_count: number
  train_size: number
  val_size: number
}

export type LabEvent =
  | LabEpochEvent
  | LabWeightsEvent
  | LabBoundaryEvent
  | LabStartedEvent
  | { type: 'completed'; epochs: number }
  | { type: 'failed'; reason: string }
  | { type: 'stopped'; epoch: number }
  | { type: 'paused' }
  | { type: 'resumed' }
  | { type: 'stopping' }
  | { type: 'pong' }

export type LabSocketState = 'connecting' | 'open' | 'closed'

const TERMINAL = new Set(['completed', 'failed', 'stopped'])

/** 实验实 WebSocket：只负责接收，不自动重连（训练任务有暂停/停止语义） */
export function useLabSocket(
  onEvent: (event: LabEvent) => void,
  onStateChange?: (state: LabSocketState) => void,
) {
  let socket: WebSocket | null = null
  const active = ref(false)

  function buildUrl(taskId: string): string {
    const token = localStorage.getItem(TOKEN_KEY) ?? ''
    const base = import.meta.env.VITE_API_BASE_URL
    const path = `/ws/lab/${taskId}?token=${encodeURIComponent(token)}`
    if (base) return `${base.replace(/^http/, 'ws')}${path}`
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}${path}`
  }

  function connect(taskId: string): void {
    close()
    onStateChange?.('connecting')
    active.value = true

    socket = new WebSocket(buildUrl(taskId))

    socket.onopen = () => onStateChange?.('open')

    socket.onmessage = (event: MessageEvent<string>) => {
      let data: LabEvent
      try {
        data = JSON.parse(event.data) as LabEvent
      } catch {
        return
      }
      if (data.type === 'pong') return
      onEvent(data)
      if (TERMINAL.has(data.type)) {
        active.value = false
        onStateChange?.('closed')
        socket?.close()
      }
    }

    socket.onclose = () => {
      active.value = false
      onStateChange?.('closed')
    }
  }

  function close(): void {
    if (socket) {
      socket.onclose = null
      socket.close()
      socket = null
    }
    active.value = false
  }

  onBeforeUnmount(close)

  return { connect, close, active }
}
