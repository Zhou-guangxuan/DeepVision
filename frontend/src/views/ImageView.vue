<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { useRouter } from 'vue-router'

import {
  createImageDataset,
  listDatasets,
  previewImageDataset,
  type DatasetSummary,
  type ImagePreview,
  type ImageSample,
} from '@/api/datasets'
import { startImageTraining } from '@/api/train'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import { useToastStore } from '@/stores/toast'

/**
 * 图像实验线：内置合成图形分类。
 * 与表格线共用训练页与记录，但使用固定的卷积网络（不可编辑拓扑）。
 */

const router = useRouter()
const toast = useToastStore()

const datasets = ref<DatasetSummary[]>([])
const selected = ref<DatasetSummary | null>(null)
const preview = ref<ImagePreview | null>(null)
const loading = ref(false)
const creating = ref(false)
const training = ref(false)

const samples = ref(1200)
const size = ref(16)
const epochs = ref(20)
const learningRate = ref(0.001)
const batchSize = ref(32)

const canTrain = computed(() => selected.value !== null && !training.value)

async function load(): Promise<void> {
  loading.value = true
  try {
    const page = await listDatasets(1, 50)
    datasets.value = page.items.filter((item) => item.kind === 'image')
    if (datasets.value.length > 0) {
      const current =
        datasets.value.find((item) => item.id === selected.value?.id) ??
        datasets.value[0]
      await select(current)
    } else {
      selected.value = null
      preview.value = null
    }
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function select(dataset: DatasetSummary): Promise<void> {
  selected.value = dataset
  preview.value = await previewImageDataset(dataset.id, 8)
}

async function create(): Promise<void> {
  creating.value = true
  try {
    const dataset = await createImageDataset(samples.value, size.value)
    toast.success('已生成内置图像数据集')
    const page = await listDatasets(1, 50)
    datasets.value = page.items.filter((item) => item.kind === 'image')
    const found = datasets.value.find((item) => item.id === dataset.id)
    if (found) await select(found)
  } catch {
    // 拦截器已提示
  } finally {
    creating.value = false
  }
}

function drawSample(
  element: Element | ComponentPublicInstance | null,
  sample: ImageSample,
): void {
  if (!(element instanceof HTMLCanvasElement)) return
  const side = sample.pixels.length
  element.width = side
  element.height = side
  const context = element.getContext('2d')
  if (!context) return

  const image = context.createImageData(side, side)
  for (let row = 0; row < side; row += 1) {
    for (let column = 0; column < side; column += 1) {
      const value = sample.pixels[row][column]
      const offset = (row * side + column) * 4
      image.data[offset] = value
      image.data[offset + 1] = value
      image.data[offset + 2] = value
      image.data[offset + 3] = 255
    }
  }
  context.putImageData(image, 0, 0)
}

function bindSample(
  element: Element | ComponentPublicInstance | null,
  sample: ImageSample,
): void {
  drawSample(element, sample)
}

async function train(): Promise<void> {
  if (!selected.value) return
  training.value = true
  try {
    const result = await startImageTraining(selected.value.id, {
      epochs: epochs.value,
      batch_size: batchSize.value,
      learning_rate: learningRate.value,
    })
    void router.push(`/train/${result.task_id}`)
  } catch {
    // 拦截器已提示
  } finally {
    training.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="flex h-screen flex-col overflow-hidden bg-base">
    <header
      class="flex h-16 shrink-0 items-center justify-between border-b px-5"
      :style="{
        borderColor: 'var(--border-subtle)',
        background: 'var(--bg-surface)',
      }"
    >
      <div class="flex items-center gap-3">
        <AppButton variant="ghost" size="sm" @click="router.push('/workspace')">
          ← 工作台
        </AppButton>
        <span class="text-sm font-medium text-primary">图像实验</span>
        <span class="text-[11px] text-muted">
          内置合成图形 · 固定小卷积网络 · 与表格线共用训练记录
        </span>
      </div>
      <AppButton variant="secondary" size="sm" @click="load">刷新</AppButton>
    </header>

    <div class="grid min-h-0 flex-1 gap-4 overflow-auto p-4 lg:grid-cols-3">
      <!-- 数据集 -->
      <AppCard class="lg:col-span-1">
        <h2 class="text-sm font-medium text-primary">合成数据集</h2>
        <p class="mt-1 text-[11px] leading-relaxed text-muted">
          随机生成「圆形 / 方形」两类 16×16 灰度图，带位置抖动与噪声，完全离线。
        </p>

        <div class="mt-3 grid grid-cols-2 gap-2">
          <label class="text-[11px] text-muted">
            样本数
            <input
              v-model.number="samples"
              type="number"
              min="200"
              max="4000"
              step="100"
              class="mt-1 w-full rounded-sm border bg-transparent px-2 py-1 text-xs text-secondary"
              :style="{ borderColor: 'var(--border-default)' }"
            />
          </label>
          <label class="text-[11px] text-muted">
            边长
            <select
              v-model.number="size"
              class="dv-select mt-1 h-8 w-full text-xs"
            >
              <option :value="8">8×8</option>
              <option :value="16">16×16</option>
              <option :value="24">24×24</option>
            </select>
          </label>
        </div>

        <AppButton class="mt-3 w-full" :loading="creating" @click="create">
          生成图像数据集
        </AppButton>

        <div class="mt-4 space-y-1.5">
          <button
            v-for="dataset in datasets"
            :key="dataset.id"
            type="button"
            class="w-full rounded-md border px-2.5 py-2 text-left text-[11px]"
            :style="{
              borderColor:
                selected?.id === dataset.id
                  ? 'var(--brand-cyan)'
                  : 'var(--border-subtle)',
              background:
                selected?.id === dataset.id
                  ? 'rgba(34, 211, 238, 0.08)'
                  : 'transparent',
            }"
            @click="select(dataset)"
          >
            <span class="text-secondary">{{ dataset.name }}</span>
            <span class="ml-2 text-muted">
              {{ dataset.sample_count }} 张 · {{ dataset.feature_count }} 像素
            </span>
          </button>
          <p
            v-if="!loading && datasets.length === 0"
            class="text-[11px] text-muted"
          >
            还没有图像数据集，点上面的按钮生成。
          </p>
        </div>
      </AppCard>

      <!-- 预览 -->
      <AppCard class="lg:col-span-2">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-medium text-primary">样本预览</h2>
          <span class="text-[11px] text-muted">
            {{ preview?.classes.join(' / ') ?? '' }}
          </span>
        </div>

        <div v-if="preview" class="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-8">
          <div
            v-for="(sample, index) in preview.samples"
            :key="index"
            class="flex flex-col items-center gap-1"
          >
            <canvas
              :ref="(element) => bindSample(element, sample)"
              class="w-full rounded-sm border"
              :style="{
                borderColor: 'var(--border-subtle)',
                imageRendering: 'pixelated',
              }"
            />
            <span class="text-[10px] text-muted">
              {{ preview.classes[sample.label] ?? sample.label }}
            </span>
          </div>
        </div>
        <p v-else class="mt-3 text-[11px] text-muted">
          生成数据集后可预览样本。
        </p>

        <div
          class="mt-4 border-t pt-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <h3 class="text-xs font-medium text-secondary">训练参数</h3>
          <div class="mt-2 grid grid-cols-3 gap-2">
            <label class="text-[11px] text-muted">
              轮数
              <input
                v-model.number="epochs"
                type="number"
                min="1"
                max="200"
                class="mt-1 w-full rounded-sm border bg-transparent px-2 py-1 text-xs text-secondary"
                :style="{ borderColor: 'var(--border-default)' }"
              />
            </label>
            <label class="text-[11px] text-muted">
              批大小
              <input
                v-model.number="batchSize"
                type="number"
                min="1"
                max="512"
                class="mt-1 w-full rounded-sm border bg-transparent px-2 py-1 text-xs text-secondary"
                :style="{ borderColor: 'var(--border-default)' }"
              />
            </label>
            <label class="text-[11px] text-muted">
              学习率
              <input
                v-model.number="learningRate"
                type="number"
                min="0.00001"
                max="1"
                step="0.0001"
                class="mt-1 w-full rounded-sm border bg-transparent px-2 py-1 text-xs text-secondary"
                :style="{ borderColor: 'var(--border-default)' }"
              />
            </label>
          </div>
          <AppButton
            class="mt-3"
            :disabled="!canTrain"
            :loading="training"
            @click="train"
          >
            开始训练（固定 CNN）
          </AppButton>
          <p class="mt-2 text-[10px] leading-relaxed text-muted">
            图像线使用固定的两层卷积 + 池化 +
            全连接，不支持编辑拓扑；训练曲线与记录和表格线一致。
          </p>
        </div>
      </AppCard>
    </div>
  </div>
</template>
