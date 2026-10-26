import { http } from './client'

import type { ModelConfig } from '@/types/graph'

export interface Hyperparameters {
  epochs: number
  batch_size: number
  learning_rate: number
}

export interface StartTrainingPayload {
  dataset_id: number
  model_config: ModelConfig
  hyperparameters: Hyperparameters
}

export interface StartTrainingResponse {
  task_id: string
  total_epochs: number
}

export async function startTraining(
  payload: StartTrainingPayload,
): Promise<StartTrainingResponse> {
  const { data } = await http.post<StartTrainingResponse>('/api/train', payload)
  return data
}

export async function stopTraining(taskId: string): Promise<void> {
  await http.post(`/api/train/${taskId}/stop`)
}

/** 图像实验线：固定小 CNN 训练 */
export async function startImageTraining(
  datasetId: number,
  hyperparameters: Hyperparameters,
): Promise<StartTrainingResponse> {
  const { data } = await http.post<StartTrainingResponse>('/api/train/image', {
    dataset_id: datasetId,
    hyperparameters,
  })
  return data
}

/** 多模态实验线：图像 + 表格特征融合 */
export async function startMultimodalTraining(
  datasetId: number,
  hyperparameters: Hyperparameters,
): Promise<StartTrainingResponse> {
  const { data } = await http.post<StartTrainingResponse>(
    '/api/train/multimodal',
    { dataset_id: datasetId, hyperparameters },
  )
  return data
}

export interface CodeLineRange {
  definition: number[]
  forward: number[]
}

export interface GeneratedCode {
  code: string
  lines: Record<string, CodeLineRange>
  total_lines: number
}

/** 生成等效 PyTorch 代码与节点到行号的映射 */
export async function getTrainCode(taskId: string): Promise<GeneratedCode> {
  const { data } = await http.get<GeneratedCode>(`/api/train/${taskId}/code`)
  return data
}
