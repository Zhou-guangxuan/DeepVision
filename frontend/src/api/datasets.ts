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
}

export interface DatasetDetail {
  id: number
  name: string
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
