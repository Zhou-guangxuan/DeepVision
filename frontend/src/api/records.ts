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
  'pending' | 'running' | 'success' | 'failed' | 'interrupted'

export interface TrainingRecord {
  id: number
  dataset_id: number | null
  task_id: string
  model_config: ModelConfig
  hyperparameters: Record<string, unknown>
  result_metrics: Record<string, unknown>
  model_file_url: string | null
  status: RecordStatus
  source: string
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

export async function getRecord(id: number): Promise<TrainingRecord> {
  const { data } = await http.get<TrainingRecord>(`/api/records/${id}`)
  return data
}

/** 下载该记录保存的模型权重（.pt） */
export async function downloadModel(recordId: number): Promise<Blob> {
  const { data } = await http.get<Blob>(`/api/records/${recordId}/model`, {
    responseType: 'blob',
  })
  return data
}

export interface CurvePoint {
  epoch: number | null
  train_loss: number | null
  val_loss: number | null
  accuracy: number | null
  /** 该 epoch 结束时的累计耗时（毫秒）；旧记录可能为空 */
  elapsed_ms?: number | null
}

export interface CompareRun {
  id: number
  task_id: string
  source: string
  status: RecordStatus
  created_at: string
  epochs: number
  final_accuracy: number | null
  history: CurvePoint[]
}

export type IssueSeverity = 'error' | 'warning' | 'info'

export interface DiagnosisIssue {
  code: string
  severity: IssueSeverity
  title: string
  detail: string
  suggestion: string
  evidence: Record<string, unknown>
}

export interface DiagnosisResult {
  healthy: boolean | null
  summary: string
  issues: DiagnosisIssue[]
  stats: Record<string, number>
}

export async function compareRecords(
  ids: number[],
): Promise<{ runs: CompareRun[] }> {
  const { data } = await http.get<{ runs: CompareRun[] }>(
    '/api/records/compare',
    { params: { ids: ids.join(',') } },
  )
  return data
}

export async function diagnoseRecord(id: number): Promise<DiagnosisResult> {
  const { data } = await http.get<DiagnosisResult>(
    `/api/records/${id}/diagnosis`,
  )
  return data
}

export async function rerunRecord(
  id: number,
): Promise<{ task_id: string; total_epochs: number }> {
  const { data } = await http.post<{ task_id: string; total_epochs: number }>(
    `/api/records/${id}/rerun`,
  )
  return data
}

export interface ImageEvalSample {
  label: number
  prediction: number
  probability: number
  pixels: number[][]
}

export interface ImageEvalData {
  classes: string[]
  size: number
  confusion: number[][]
  samples: ImageEvalSample[]
}

/** 图像训练的混淆矩阵与样本预测 */
export async function getImageEval(recordId: number): Promise<ImageEvalData> {
  const { data } = await http.get<ImageEvalData>(
    `/api/records/${recordId}/image-eval`,
  )
  return data
}
