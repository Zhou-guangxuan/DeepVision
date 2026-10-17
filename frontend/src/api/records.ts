import { http } from './client'

export interface NetworkNode {
  id: string
  type: 'input' | 'hidden' | 'output'
  params: Record<string, unknown>
}

export interface NetworkEdge {
  source: string
  target: string
}

export interface ModelConfig {
  version: number
  nodes: NetworkNode[]
  edges: NetworkEdge[]
}

export type RecordStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'interrupted'

export interface TrainingRecord {
  id: number
  dataset_id: number | null
  task_id: string
  model_config: ModelConfig
  hyperparameters: Record<string, unknown>
  result_metrics: Record<string, unknown>
  model_file_url: string | null
  status: RecordStatus
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export async function listRecords(
  page = 1,
  pageSize = 20,
): Promise<Page<TrainingRecord>> {
  const { data } = await http.get<Page<TrainingRecord>>('/api/records', {
    params: { page, page_size: pageSize },
  })
  return data
}

export async function createRecord(
  payload: Omit<TrainingRecord, 'id' | 'created_at'>,
): Promise<TrainingRecord> {
  const { data } = await http.post<TrainingRecord>('/api/records', payload)
  return data
}

export async function deleteRecord(id: number): Promise<void> {
  await http.delete(`/api/records/${id}`)
}
