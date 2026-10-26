import { http } from './client'

export interface DatasetColumn {
  name: string
  dtype: string
  missing: number
}

export interface FeatureStats {
  name: string
  mean: number | null
  variance: number | null
}

export interface DatasetStats {
  features: FeatureStats[]
  target: FeatureStats | null
  target_distribution: Record<string, number>
  classes?: string[]
  size?: number | null
  samples?: number | null
  synthetic?: string | null
  tabular_features?: string[]
  tabular_dim?: number | null
}

export interface DatasetDetail {
  id: number
  name: string
  kind: string
  columns_meta: DatasetColumn[]
  target_column: string | null
  missing_strategy: string
  stats: DatasetStats
  sample_count: number
  feature_count: number
  created_at: string
}

export interface DatasetSummary {
  id: number
  name: string
  kind: string
  target_column: string | null
  missing_strategy: string
  sample_count: number
  feature_count: number
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export async function uploadDataset(form: FormData): Promise<DatasetDetail> {
  const { data } = await http.post<DatasetDetail>('/api/datasets', form, {
    timeout: 60000,
  })
  return data
}

export async function listDatasets(
  page = 1,
  pageSize = 20,
): Promise<Page<DatasetSummary>> {
  const { data } = await http.get<Page<DatasetSummary>>('/api/datasets', {
    params: { page, page_size: pageSize },
  })
  return data
}

/** 生成内置合成图像数据集（圆 / 方） */
export async function createImageDataset(
  samples = 1200,
  size = 16,
): Promise<DatasetDetail> {
  const { data } = await http.post<DatasetDetail>('/api/datasets/image', null, {
    params: { samples, size },
  })
  return data
}

export interface ImageSample {
  label: number
  pixels: number[][]
}

export interface ImagePreview {
  size: number
  classes: string[]
  samples: ImageSample[]
}

/** 图像数据集样本预览 */
export async function previewImageDataset(
  id: number,
  count = 8,
): Promise<ImagePreview> {
  const { data } = await http.get<ImagePreview>(`/api/datasets/${id}/preview`, {
    params: { count },
  })
  return data
}

export interface MultimodalSample {
  label: number
  pixels: number[][]
  tabular: number[]
}

export interface MultimodalPreview {
  size: number
  classes: string[]
  feature_names: string[]
  samples: MultimodalSample[]
}

/** 生成内置多模态数据集（图像 + 4 个表格特征） */
export async function createMultimodalDataset(
  samples = 1200,
  size = 16,
): Promise<DatasetDetail> {
  const { data } = await http.post<DatasetDetail>(
    '/api/datasets/multimodal',
    null,
    { params: { samples, size } },
  )
  return data
}

/** 多模态数据集样本预览 */
export async function previewMultimodalDataset(
  id: number,
  count = 8,
): Promise<MultimodalPreview> {
  const { data } = await http.get<MultimodalPreview>(
    `/api/datasets/${id}/preview/multimodal`,
    { params: { count } },
  )
  return data
}
