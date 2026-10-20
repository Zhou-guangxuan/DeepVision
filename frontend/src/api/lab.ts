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
