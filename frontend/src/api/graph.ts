import { http } from './client'

import type { ModelConfig } from '@/types/graph'

export interface GraphValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

/** 调用后端校验拓扑结构（与阶段四训练引擎共用同一套规则） */
export async function validateGraph(
  config: ModelConfig,
): Promise<GraphValidationResult> {
  const { data } = await http.post<GraphValidationResult>(
    '/api/graph/validate',
    config,
  )
  return data
}
