<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { AxiosError } from 'axios'

import { listDatasets } from '@/api/datasets'
import type { DatasetSummary } from '@/api/datasets'
import { startTraining } from '@/api/train'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import { useGraphStore } from '@/stores/graph'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ open: boolean }>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'started', taskId: string): void
}>()

const graph = useGraphStore()
const toast = useToastStore()

const datasets = ref<DatasetSummary[]>([])
const loadingDatasets = ref(false)
const datasetId = ref<number | null>(null)
const epochs = ref(20)
const batchSize = ref(32)
const learningRate = ref(0.001)
const submitting = ref(false)
const errorMessage = ref('')

async function loadDatasets(): Promise<void> {
  loadingDatasets.value = true
  try {
    const page = await listDatasets(1, 50)
    datasets.value = page.items
    if (page.items.length > 0 && datasetId.value === null) {
      datasetId.value = page.items[0].id
    }
  } catch {
    // 拦截器已提示
  } finally {
    loadingDatasets.value = false
  }
}

onMounted(() => {
  void loadDatasets()
})

watch(
  () => props.open,
  (open) => {
    if (open) {
      errorMessage.value = ''
      void loadDatasets()
    }
  },
)

async function onSubmit(): Promise<void> {
  if (submitting.value) return

  if (datasetId.value === null) {
    errorMessage.value = '请选择数据集'
    return
  }
  if (graph.nodes.length === 0) {
    errorMessage.value = '画布为空，请先搭建网络'
    return
  }

  submitting.value = true
  errorMessage.value = ''
  try {
    const result = await startTraining({
      dataset_id: datasetId.value,
      model_config: graph.toModelConfig(),
      hyperparameters: {
        epochs: epochs.value,
        batch_size: batchSize.value,
        learning_rate: learningRate.value,
      },
    })
    toast.success('训练任务已创建')
    emit('started', result.task_id)
  } catch (error) {
    const axiosError = error as AxiosError<{ message?: string }>
    errorMessage.value =
      axiosError.response?.data?.message ?? '创建训练任务失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 grid place-items-center px-4"
      style="background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(4px)"
      @click.self="emit('close')"
    >
      <AppCard class="w-full max-w-md" padding="lg">
        <h2 class="text-lg font-semibold text-primary">开始训练</h2>
        <p class="mt-1 text-xs text-muted">
          使用当前画布的网络结构与所选数据集
        </p>

        <div class="mt-5 space-y-4">
          <div>
            <label class="mb-1.5 block text-xs text-secondary" for="ds-select">
              数据集
            </label>
            <select
              id="ds-select"
              v-model.number="datasetId"
              class="dv-select"
              :disabled="loadingDatasets"
            >
              <option v-if="datasets.length === 0" :value="null" disabled>
                暂无数据集，请先到「数据集」页上传
              </option>
              <option
                v-for="item in datasets"
                :key="item.id"
                :value="item.id"
              >
                {{ item.name }}（{{ item.sample_count }} 行 · {{ item.feature_count }} 特征）
              </option>
            </select>
          </div>

          <div class="grid grid-cols-3 gap-3">
            <div>
              <label class="mb-1.5 block text-xs text-secondary" for="hp-epochs">
                Epochs
              </label>
              <input
                id="hp-epochs"
                v-model.number="epochs"
                class="dv-input-plain"
                type="number"
                min="1"
                max="500"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs text-secondary" for="hp-batch">
                Batch
              </label>
              <input
                id="hp-batch"
                v-model.number="batchSize"
                class="dv-input-plain"
                type="number"
                min="1"
                max="1024"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs text-secondary" for="hp-lr">
                学习率
              </label>
              <input
                id="hp-lr"
                v-model.number="learningRate"
                class="dv-input-plain"
                type="number"
                step="0.0001"
                min="0.000001"
                max="1"
              />
            </div>
          </div>

          <p v-if="errorMessage" class="text-xs text-danger" role="alert">
            {{ errorMessage }}
          </p>
        </div>

        <div class="mt-6 flex justify-end gap-3">
          <AppButton variant="secondary" @click="emit('close')">取消</AppButton>
          <AppButton
            :loading="submitting"
            :disabled="datasets.length === 0"
            @click="onSubmit"
          >
            开始训练
          </AppButton>
        </div>
      </AppCard>
    </div>
  </Teleport>
</template>
