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
