import { onBeforeUnmount, ref } from 'vue'

import { TOKEN_KEY } from '@/api/client'

export type TrainingSocketState =
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'

export interface TrainingEvent {
  type: 'started' | 'epoch' | 'completed' | 'failed' | 'stopped' | 'pong'
  [key: string]: unknown
}

const TERMINAL_TYPES = new Set(['completed', 'failed', 'stopped'])
const MAX_ATTEMPTS = 5

/**
 * 训练 WebSocket 客户端。
 *
 * - 断线后按 1s → 2s → 4s → 8s → 16s 指数退避重连，最多 5 次；
 * - 服务端在重连后会回放历史事件，调用方需按 epoch 去重。
 */
export function useTrainingSocket(
  taskId: string,
  onEvent: (event: TrainingEvent) => void,
  onStateChange?: (state: TrainingSocketState) => void,
) {
  let socket: WebSocket | null = null
  let timer: number | undefined
  let attempts = 0
  let manualClose = false

  const finished = ref(false)

  function buildUrl(): string {
    const token = localStorage.getItem(TOKEN_KEY) ?? ''
    const base = import.meta.env.VITE_API_BASE_URL
    const path = `/ws/train/${taskId}?token=${encodeURIComponent(token)}`

    if (base) {
      return `${base.replace(/^http/, 'ws')}${path}`
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}${path}`
  }

  function connect(): void {
    onStateChange?.(attempts === 0 ? 'connecting' : 'reconnecting')

    socket = new WebSocket(buildUrl())

    socket.onopen = () => {
      attempts = 0
      onStateChange?.('open')
    }

    socket.onmessage = (event: MessageEvent<string>) => {
      let data: TrainingEvent
      try {
        data = JSON.parse(event.data) as TrainingEvent
      } catch {
        return
      }

      if (data.type === 'pong') return

      onEvent(data)

      if (TERMINAL_TYPES.has(data.type)) {
        finished.value = true
        manualClose = true
        window.clearTimeout(timer)
        socket?.close()
      }
    }

    socket.onclose = () => {
      if (manualClose || finished.value) {
        onStateChange?.('closed')
        return
      }

      attempts += 1
      if (attempts > MAX_ATTEMPTS) {
        onStateChange?.('closed')
        return
      }

      const delay = Math.min(1000 * 2 ** (attempts - 1), 16000)
      onStateChange?.('reconnecting')
      timer = window.setTimeout(connect, delay)
    }

    socket.onerror = () => {
      // 具体错误交给 onclose 统一处理重连
    }
  }

  function close(): void {
    manualClose = true
    window.clearTimeout(timer)
    if (socket) {
      socket.onclose = null
      socket.close()
      socket = null
    }
  }

  connect()

  onBeforeUnmount(close)

  return { finished, close }
}
