import { TOKEN_KEY } from './client'

import type { ModelConfig } from '@/types/graph'

export type SuggestionField = 'features' | 'units' | 'activation' | 'task'

export interface DiagnoseIssue {
  node_id: string | null
  severity: 'error' | 'warning' | 'info'
  message: string
}

export interface DiagnoseSuggestion {
  node_id: string
  field: SuggestionField
  from: unknown
  to: unknown
  reason: string
}

export interface DiagnoseResult {
  score: number
  mode: string
  issues: DiagnoseIssue[]
  suggestions: DiagnoseSuggestion[]
}

export interface ChatEvent {
  type: 'meta' | 'delta' | 'done'
  mode?: string
  reason?: string
  text?: string
  sources?: string[]
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY) ?? ''
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }
}

/** 读取 SSE 流，逐个回调事件 */
export async function streamChat(
  message: string,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const base = import.meta.env.VITE_API_BASE_URL ?? ''
  const response = await fetch(`${base}/api/ai/chat`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ message }),
    signal,
  })

  if (!response.ok) {
    let detail = 'AI 助教暂时不可用'
    try {
      const body = (await response.json()) as { message?: string }
      if (body?.message) detail = body.message
    } catch {
      // 保持默认文案
    }
    throw new Error(detail)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('当前环境不支持流式响应')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''

    for (const chunk of chunks) {
      const line = chunk
        .split('\n')
        .find((item) => item.startsWith('data: '))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice(6)) as ChatEvent)
      } catch {
        // 忽略无法解析的分片
      }
    }
  }
}

export async function diagnoseGraph(payload: {
  model_config: ModelConfig
  dataset_id?: number
}): Promise<DiagnoseResult> {
  const base = import.meta.env.VITE_API_BASE_URL ?? ''
  const response = await fetch(`${base}/api/ai/diagnose`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    let detail = '诊断请求失败'
    try {
      const body = (await response.json()) as { message?: string }
      if (body?.message) detail = body.message
    } catch {
      // 保持默认文案
    }
    throw new Error(detail)
  }

  return (await response.json()) as DiagnoseResult
}
