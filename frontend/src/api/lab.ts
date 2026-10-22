import { http } from './client'

export type LabActivation = 'relu' | 'tanh' | 'sigmoid'
export type LabInit = 'he' | 'xavier' | 'uniform'
export type LabOptimizer = 'adam' | 'sgd'

export interface LabConfig {
  input_units: number
  output_units: number
  hidden_layers: number[]
  activation: LabActivation
  init: LabInit
  optimizer: LabOptimizer
  learning_rate: number
  batch_size: number
  epochs: number
  l2: number
  dropout: number
}

export interface LabStartResponse {
  task_id: string
  parameter_count: number
}

export interface LabControlResponse {
  task_id: string
  status: string
}

export async function startLab(config: LabConfig): Promise<LabStartResponse> {
  const { data } = await http.post<LabStartResponse>('/api/lab/train', {
    config,
  })
  return data
}

export async function pauseLab(taskId: string): Promise<LabControlResponse> {
  const { data } = await http.post<LabControlResponse>(
    `/api/lab/${taskId}/pause`,
  )
  return data
}

export async function resumeLab(taskId: string): Promise<LabControlResponse> {
  const { data } = await http.post<LabControlResponse>(
    `/api/lab/${taskId}/resume`,
  )
  return data
}

export async function stopLab(taskId: string): Promise<LabControlResponse> {
  const { data } = await http.post<LabControlResponse>(
    `/api/lab/${taskId}/stop`,
  )
  return data
}

export interface LabLayerInspect {
  index: number
  size: number
  activation: number[]
  gradient: number[]
}

export interface LabInspect {
  sample_index: number
  total_samples: number
  true_label: number
  prediction: number
  probabilities: number[]
  input: number[]
  saliency: number[]
  layers: LabLayerInspect[]
  loss: number
}

export interface LabProjection {
  layer_index: number
  layer_count: number
  method: 'pca' | 'tsne'
  explained: number[]
  points: { x: number; y: number; label: number }[]
}

export interface LabAttentionHistory {
  epochs: number[]
  series: { feature: number; values: number[] }[]
}

/** 单样本前向 + 反向，返回逐层激活 / 梯度与输入注意力 */
export async function inspectLab(
  taskId: string,
  index: number,
): Promise<LabInspect> {
  const { data } = await http.get<LabInspect>(`/api/lab/${taskId}/inspect`, {
    params: { index },
  })
  return data
}

/** 指定层的降维投影：pca（线性）或 tsne（非线性） */
export async function projectLab(
  taskId: string,
  layer: number,
  method: 'pca' | 'tsne' = 'pca',
): Promise<LabProjection> {
  const { data } = await http.get<LabProjection>(
    `/api/lab/${taskId}/projection`,
    { params: { layer, method } },
  )
  return data
}

/** 逐 epoch 的输入注意力，用于观察模型关注点如何变化 */
export async function attentionLab(
  taskId: string,
): Promise<LabAttentionHistory> {
  const { data } = await http.get<LabAttentionHistory>(
    `/api/lab/${taskId}/attention`,
  )
  return data
}

/** 教学任务的曲线诊断（复用记录级规则引擎） */
export async function diagnoseLab(taskId: string): Promise<LabDiagnosis> {
  const { data } = await http.get<LabDiagnosis>(`/api/lab/${taskId}/diagnosis`)
  return data
}

export interface LabDiagnosisIssue {
  code: string
  severity: 'error' | 'warning' | 'info'
  title: string
  detail: string
  suggestion: string
  evidence: Record<string, unknown>
}

export interface LabDiagnosis {
  healthy: boolean | null
  summary: string
  issues: LabDiagnosisIssue[]
  stats: Record<string, number>
}

export interface TuneTrial {
  index: number
  learning_rate: number
  hidden_layers: number[]
  activation: string
  l2: number
  dropout: number
  batch_size: number
  accuracy: number
  loss: number
  epochs_run: number
  best_epoch: number
  early_stopped: boolean
}

export interface TuneState {
  tune_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'stopped'
  total: number
  done: number
  trials: TuneTrial[]
  best: TuneTrial | null
  error: string | null
}

/** 启动自动调参（随机搜索 + 早停） */
export async function startTune(
  config: LabConfig,
  trials = 6,
  epochs = 12,
): Promise<TuneState> {
  const { data } = await http.post<TuneState>('/api/lab/tune', {
    config,
    trials,
    epochs,
  })
  return data
}

/** 查询自动调参进度 */
export async function getTune(tuneId: string): Promise<TuneState> {
  const { data } = await http.get<TuneState>(`/api/lab/tune/${tuneId}`)
  return data
}

export interface BaselineCase {
  params: number
  nonzero: number
  size_bytes: number
  weight_bytes: number
  accuracy: number
}

export interface PrunedCase {
  sparsity: number
  params: number
  nonzero: number
  size_bytes: number
  weight_bytes: number
  sparse_bytes: number
  accuracy: number
}

export interface QuantizedCase {
  dtype: string
  size_bytes: number
  weight_bytes: number
  compression_ratio: number
  accuracy: number
}

export interface CompressionResult {
  baseline: BaselineCase
  pruned: PrunedCase
  quantized: QuantizedCase
  samples: number
}

/** 剪枝 / 量化压缩对比 */
export async function compressLab(
  taskId: string,
  sparsity = 0.3,
): Promise<CompressionResult> {
  const { data } = await http.get<CompressionResult>(
    `/api/lab/${taskId}/compression`,
    { params: { sparsity } },
  )
  return data
}
