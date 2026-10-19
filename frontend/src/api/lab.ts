import { http } from './client'

export type LabActivation = 'relu' | 'tanh' | 'sigmoid'
export type LabInit = 'he' | 'xavier' | 'uniform'
export type LabOptimizer = 'adam' | 'sgd'

export interface LabConfig {
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
