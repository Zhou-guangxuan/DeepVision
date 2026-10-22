import { http } from './client'
import type { GraphEdge, GraphNode } from '@/types/graph'

/** 工作台草稿：同一账号在多设备间恢复画布 */

export interface DraftGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  savedAt?: string
}

export interface DraftResponse {
  graph: DraftGraph | null
  updated_at: string | null
}

export async function getWorkspaceDraft(): Promise<DraftResponse> {
  const { data } = await http.get<DraftResponse>('/api/workspace/draft')
  return data
}

export async function saveWorkspaceDraft(
  nodes: GraphNode[],
  edges: GraphEdge[],
): Promise<DraftResponse> {
  const { data } = await http.put<DraftResponse>('/api/workspace/draft', {
    nodes,
    edges,
    saved_at: new Date().toISOString(),
  })
  return data
}
