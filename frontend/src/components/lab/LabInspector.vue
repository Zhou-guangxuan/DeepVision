<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'

import {
  attributionLab,
  attentionLab,
  inspectLab,
  projectLab,
  type AttributionResult,
  type LabAttentionHistory,
  type LabInspect,
  type LabProjection,
} from '@/api/lab'
import AppButton from '@/components/ui/AppButton.vue'

/**
 * 教学实验室的「观察」弹窗：
 * - 传播：逐层单步查看前向激活 / 反向梯度；
 * - 注意力：输入特征的贡献（|梯度 × 输入|）；
 * - 注意力曲线：逐 epoch 观察关注点如何变化；
 * - 投影：指定层激活的 PCA / t-SNE 二维散点。
 */

const props = defineProps<{
  open: boolean
  taskId: string | null
  layers: number[]
  initialTab?:
    'propagation' | 'attention' | 'trend' | 'projection' | 'attribution'
}>()

const emit = defineEmits<{ close: []; saliency: [number[]] }>()

type Tab = 'propagation' | 'attention' | 'trend' | 'projection' | 'attribution'

const tab = ref<Tab>('propagation')
const sampleIndex = ref(0)
const inspect = ref<LabInspect | null>(null)
const projection = ref<LabProjection | null>(null)
const projectionLayer = ref(0)
const projectionMethod = ref<'pca' | 'tsne'>('pca')
const trend = ref<LabAttentionHistory | null>(null)
const attribution = ref<AttributionResult | null>(null)
const attributionIndex = ref(0)
const loading = ref(false)
const exporting = ref(false)
const errorMessage = ref('')
const step = ref(0)
const direction = ref<'forward' | 'backward'>('forward')
const canvasRef = ref<HTMLCanvasElement | null>(null)
const trendRef = ref<HTMLElement | null>(null)
const attributionRef = ref<HTMLElement | null>(null)
const modalRef = ref<HTMLElement | null>(null)
let trendChart: ECharts | null = null
let attributionChart: ECharts | null = null
let canvasObserver: ResizeObserver | null = null

const layerCount = computed(() => inspect.value?.layers.length ?? 0)

const currentLayer = computed(() => {
  const data = inspect.value
  if (!data) return null
  return data.layers[Math.min(step.value, data.layers.length - 1)] ?? null
})

const maxActivation = computed(() => {
  const layer = currentLayer.value
  if (!layer) return 1e-9
  return Math.max(...layer.activation.map((value) => Math.abs(value)), 1e-9)
})

const maxGradient = computed(() => {
  const layer = currentLayer.value
  if (!layer) return 1e-9
  return Math.max(...layer.gradient.map((value) => Math.abs(value)), 1e-9)
})

const maxSaliency = computed(() => {
  const data = inspect.value
  if (!data) return 1e-9
  return Math.max(...data.saliency.map((value) => Math.abs(value)), 1e-9)
})

async function runInspect(): Promise<void> {
  if (!props.taskId) {
    errorMessage.value = '请先开始一次训练，训练完成后才能观察传播过程'
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    inspect.value = await inspectLab(props.taskId, sampleIndex.value)
    step.value = 0
    direction.value = 'forward'
    emit('saliency', inspect.value.saliency)
  } catch (error) {
    errorMessage.value =
      error instanceof Error ? error.message : '读取传播过程失败'
  } finally {
    loading.value = false
  }
}

async function loadProjection(): Promise<void> {
  if (!props.taskId) {
    errorMessage.value = '请先开始一次训练'
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    projection.value = await projectLab(
      props.taskId,
      projectionLayer.value,
      projectionMethod.value,
    )
    await nextTick()
    drawProjection()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '降维投影失败'
  } finally {
    loading.value = false
  }
}

async function loadAttentionTrend(): Promise<void> {
  if (!props.taskId) {
    errorMessage.value = '请先开始一次训练'
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    trend.value = await attentionLab(props.taskId)
    await nextTick()
    renderTrend()
  } catch (error) {
    errorMessage.value =
      error instanceof Error ? error.message : '读取注意力曲线失败'
  } finally {
    loading.value = false
  }
}

function renderTrend(): void {
  if (!trendRef.value || !trend.value) return
  if (!trendChart) trendChart = echarts.init(trendRef.value)

  const colors = [
    '#22d3ee',
    '#a78bfa',
    '#34d399',
    '#f97316',
    '#f472b6',
    '#facc15',
    '#60a5fa',
    '#fb7185',
  ]

  trendChart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 44, right: 12, top: 28, bottom: 26 },
      tooltip: { trigger: 'axis' },
      legend: {
        textStyle: { color: '#94a3b8', fontSize: 10 },
        top: 0,
        type: 'scroll',
      },
      xAxis: {
        type: 'category',
        data: trend.value.epochs,
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#94a3b8', fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#94a3b8', fontSize: 10 },
        splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } },
      },
      series: trend.value.series.map((item, index) => ({
        name: `f${item.feature}`,
        type: 'line' as const,
        smooth: true,
        showSymbol: false,
        data: item.values,
        itemStyle: { color: colors[index % colors.length] },
      })),
    },
    true,
  )
}

function onProjectionMethodChange(): void {
  void loadProjection()
}

async function loadAttribution(): Promise<void> {
  if (!props.taskId) return
  loading.value = true
  errorMessage.value = ''
  try {
    attribution.value = await attributionLab(
      props.taskId,
      attributionIndex.value,
    )
    await nextTick()
    renderAttribution()
  } catch {
    attribution.value = null
    errorMessage.value = '归因计算失败，请重试'
  } finally {
    loading.value = false
  }
}

function renderAttribution(): void {
  if (!attributionRef.value || !attribution.value) return
  if (!attributionChart) attributionChart = echarts.init(attributionRef.value)

  const data = attribution.value
  const bars = data.attributions.map((value) => ({
    value,
    itemStyle: { color: value >= 0 ? '#22d3ee' : '#fb7185' },
    label: {
      show: true,
      position: 'right' as const,
      color: '#94a3b8',
      fontSize: 9,
    },
  }))

  attributionChart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 44, right: 60, top: 16, bottom: 26 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: {
        type: 'value',
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#94a3b8', fontSize: 9 },
        splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.1)' } },
      },
      yAxis: {
        type: 'category',
        data: data.attributions.map((_, index) => `f${index}`),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: '#94a3b8', fontSize: 10 },
      },
      series: [{ type: 'bar', data: bars, barMaxWidth: 16 }],
    },
    true,
  )
}

/** 把当前弹窗内容导出为 PNG */
async function exportImage(): Promise<void> {
  if (!modalRef.value || exporting.value) return
  exporting.value = true
  try {
    // html2canvas 只在导出时用，按需加载避免拖慢实验室首屏
    const { default: html2canvas } = await import('html2canvas')
    const canvas = await html2canvas(modalRef.value, {
      backgroundColor: '#0b1220',
      scale: 2,
    })
    const link = document.createElement('a')
    link.href = canvas.toDataURL('image/png')
    link.download = `deepvision-inspector-${tab.value}-${Date.now()}.png`
    link.click()
  } catch {
    errorMessage.value = '导出图片失败，请重试'
  } finally {
    exporting.value = false
  }
}

function drawProjection(): void {
  const canvas = canvasRef.value
  const data = projection.value
  if (!canvas) return

  const parent = canvas.parentElement
  const width = Math.max(parent?.clientWidth ?? 340, 160)
  const height = Math.max(parent?.clientHeight ?? 300, 120)

  // 按设备像素比放大位图，避免高分屏发虚；绘制坐标仍用 CSS 像素
  const ratio = window.devicePixelRatio || 1
  canvas.width = Math.round(width * ratio)
  canvas.height = Math.round(height * ratio)
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`

  const context = canvas.getContext('2d')
  if (!context) return
  context.setTransform(ratio, 0, 0, ratio, 0, 0)
  context.clearRect(0, 0, width, height)
  if (!data) return

  const pad = 16
  const toX = (value: number) => pad + ((value + 1) / 2) * (width - pad * 2)
  const toY = (value: number) =>
    height - pad - ((value + 1) / 2) * (height - pad * 2)

  context.strokeStyle = 'rgba(148, 163, 184, 0.18)'
  context.lineWidth = 1
  context.beginPath()
  context.moveTo(pad, height / 2)
  context.lineTo(width - pad, height / 2)
  context.moveTo(width / 2, pad)
  context.lineTo(width / 2, height - pad)
  context.stroke()

  for (const point of data.points) {
    context.beginPath()
    context.arc(toX(point.x), toY(point.y), 2.2, 0, Math.PI * 2)
    context.fillStyle = point.label === 0 ? '#67e8f9' : '#fdba74'
    context.fill()
  }
}

function stepTo(delta: number): void {
  const total = layerCount.value
  if (total === 0) return
  step.value = Math.min(Math.max(step.value + delta, 0), total - 1)
  direction.value = delta < 0 ? 'backward' : 'forward'
}

function switchTab(next: Tab): void {
  tab.value = next
  errorMessage.value = ''
  if (next === 'projection') {
    if (projection.value === null) {
      void loadProjection()
    } else {
      // 切走再切回时 canvas 元素被重建，需要重绘
      void nextTick().then(drawProjection)
    }
  }
  if (next === 'trend') {
    if (trend.value === null) {
      void loadAttentionTrend()
    } else {
      void nextTick().then(renderTrend)
    }
  }
  if (next === 'attribution') {
    if (attribution.value === null) {
      void loadAttribution()
    } else {
      void nextTick().then(renderAttribution)
    }
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    if (props.initialTab) tab.value = props.initialTab
    if (inspect.value === null) {
      void runInspect()
    }
    if (tab.value === 'projection') {
      if (projection.value === null) void loadProjection()
      void nextTick().then(() => {
        drawProjection()
        observeCanvas()
      })
    }
    if (tab.value === 'trend') {
      if (trend.value === null) void loadAttentionTrend()
      void nextTick().then(renderTrend)
    }
    if (tab.value === 'attribution') {
      if (attribution.value === null) void loadAttribution()
      void nextTick().then(renderAttribution)
    }
  },
)

function handleWindowResize(): void {
  drawProjection()
  trendChart?.resize()
  attributionChart?.resize()
}

/** 画布尺寸跟随容器；容器显隐或缩放都会触发重绘 */
function observeCanvas(): void {
  canvasObserver?.disconnect()
  canvasObserver = null

  const parent = canvasRef.value?.parentElement
  if (!parent || typeof ResizeObserver === 'undefined') return

  canvasObserver = new ResizeObserver(() => drawProjection())
  canvasObserver.observe(parent)
}

// 切到投影页后，等本次渲染完成再重绘（canvas 元素是新建的）
watch(tab, (value) => {
  if (value === 'projection') {
    void nextTick().then(() => {
      drawProjection()
      observeCanvas()
    })
  }
  if (value === 'trend') {
    void nextTick().then(renderTrend)
  }
})

// 数据回来后重绘，避免「先画空、后到数据」
watch(projection, () => {
  void nextTick().then(drawProjection)
})

onMounted(() => {
  window.addEventListener('resize', handleWindowResize)
  if (tab.value === 'projection') {
    void nextTick().then(() => {
      drawProjection()
      observeCanvas()
    })
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleWindowResize)
  canvasObserver?.disconnect()
  canvasObserver = null
  trendChart?.dispose()
  trendChart = null
  attributionChart?.dispose()
  attributionChart = null
})
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
    @click.self="emit('close')"
  >
    <div
      ref="modalRef"
      class="flex max-h-[86vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border"
      :style="{
        borderColor: 'var(--border-default)',
        background: 'var(--bg-surface)',
      }"
    >
      <header
        class="flex shrink-0 items-center justify-between border-b px-4 py-3"
        :style="{ borderColor: 'var(--border-subtle)' }"
      >
        <div class="flex items-center gap-1">
          <button
            v-for="item in [
              { key: 'propagation', label: '前向 / 反向传播' },
              { key: 'attention', label: '注意力' },
              { key: 'trend', label: '注意力曲线' },
              { key: 'attribution', label: '归因' },
              { key: 'projection', label: '降维投影' },
            ]"
            :key="item.key"
            type="button"
            class="rounded-sm px-2.5 py-1 text-xs transition-colors duration-fast"
            :class="
              tab === item.key
                ? 'text-primary'
                : 'text-muted hover:text-secondary'
            "
            :style="
              tab === item.key ? { background: 'var(--bg-elevated)' } : {}
            "
            @click="switchTab(item.key as Tab)"
          >
            {{ item.label }}
          </button>
        </div>
        <div class="flex items-center gap-2">
          <AppButton
            variant="secondary"
            size="sm"
            :loading="exporting"
            @click="exportImage"
          >
            导出图片
          </AppButton>
          <AppButton variant="ghost" size="sm" @click="emit('close')"
            >关闭</AppButton
          >
        </div>
      </header>

      <div class="min-h-0 flex-1 overflow-y-auto p-4">
        <p v-if="errorMessage" class="mb-3 text-xs text-danger">
          {{ errorMessage }}
        </p>

        <!-- 传播 -->
        <template v-if="tab === 'propagation'">
          <div class="flex flex-wrap items-end gap-2">
            <label class="text-[11px] text-secondary">
              样本序号
              <input
                v-model.number="sampleIndex"
                type="number"
                min="0"
                class="dv-input-plain ml-1 h-8 w-24 text-xs"
              />
            </label>
            <AppButton size="sm" :loading="loading" @click="runInspect">
              运行前向 / 反向
            </AppButton>
            <template v-if="inspect">
              <span class="text-[11px] text-muted">
                共 {{ inspect.total_samples }} 条 · 真实
                {{ inspect.true_label }} · 预测 {{ inspect.prediction }} · loss
                {{ inspect.loss.toFixed(4) }}
              </span>
            </template>
          </div>

          <div v-if="inspect" class="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <p class="mb-1 text-[11px] text-secondary">输入向量</p>
              <div class="flex gap-2">
                <span
                  v-for="(value, index) in inspect.input"
                  :key="index"
                  class="rounded-sm px-2 py-1 font-mono text-[11px] text-primary"
                  :style="{ background: 'var(--bg-elevated)' }"
                >
                  f{{ index }} = {{ value }}
                </span>
              </div>

              <p class="mb-1 mt-3 text-[11px] text-secondary">输出概率</p>
              <div class="flex gap-2">
                <span
                  v-for="(value, index) in inspect.probabilities"
                  :key="index"
                  class="rounded-sm px-2 py-1 font-mono text-[11px]"
                  :style="{ background: 'var(--bg-elevated)' }"
                  :class="
                    index === inspect.prediction ? 'text-primary' : 'text-muted'
                  "
                >
                  p{{ index }} = {{ value }}
                </span>
              </div>

              <div class="mt-3 flex gap-2">
                <AppButton variant="secondary" size="sm" @click="stepTo(-1)">
                  上一步
                </AppButton>
                <AppButton variant="secondary" size="sm" @click="stepTo(1)">
                  下一步
                </AppButton>
                <span class="self-center text-[11px] text-muted">
                  第 {{ step + 1 }} / {{ layerCount }} 层 ·
                  {{ direction === 'forward' ? '前向激活' : '反向梯度' }}
                </span>
              </div>
            </div>

            <div v-if="currentLayer">
              <p class="mb-1 text-[11px] text-secondary">
                第 {{ currentLayer.index + 1 }} 层（{{ currentLayer.size }}
                个单元）
              </p>
              <div class="space-y-1">
                <div
                  v-for="(value, index) in currentLayer.activation"
                  :key="`a-${index}`"
                  class="flex items-center gap-2"
                >
                  <span
                    class="w-8 shrink-0 text-right font-mono text-[10px] text-muted"
                  >
                    {{ index }}
                  </span>
                  <div
                    class="h-2 flex-1 overflow-hidden rounded-sm"
                    :style="{ background: 'var(--bg-elevated)' }"
                  >
                    <div
                      class="h-2"
                      :style="{
                        width: `${(Math.abs(value) / maxActivation) * 100}%`,
                        background: '#22d3ee',
                      }"
                    />
                  </div>
                  <span
                    class="w-14 shrink-0 font-mono text-[10px] text-secondary"
                  >
                    {{ value.toFixed(3) }}
                  </span>
                </div>
              </div>

              <template v-if="direction === 'backward'">
                <p class="mb-1 mt-3 text-[11px] text-secondary">梯度</p>
                <div class="space-y-1">
                  <div
                    v-for="(value, index) in currentLayer.gradient"
                    :key="`g-${index}`"
                    class="flex items-center gap-2"
                  >
                    <span
                      class="w-8 shrink-0 text-right font-mono text-[10px] text-muted"
                    >
                      {{ index }}
                    </span>
                    <div
                      class="h-2 flex-1 overflow-hidden rounded-sm"
                      :style="{ background: 'var(--bg-elevated)' }"
                    >
                      <div
                        class="h-2"
                        :style="{
                          width: `${(Math.abs(value) / maxGradient) * 100}%`,
                          background: '#f97316',
                        }"
                      />
                    </div>
                    <span
                      class="w-14 shrink-0 font-mono text-[10px] text-secondary"
                    >
                      {{ value.toFixed(3) }}
                    </span>
                  </div>
                </div>
              </template>
            </div>
          </div>

          <p v-else class="mt-6 text-xs text-muted">
            点击「运行前向 / 反向」后，可逐层查看激活与梯度。
          </p>
        </template>

        <!-- 注意力 -->
        <template v-else-if="tab === 'attention'">
          <div class="flex items-end gap-2">
            <label class="text-[11px] text-secondary">
              样本序号
              <input
                v-model.number="sampleIndex"
                type="number"
                min="0"
                class="dv-input-plain ml-1 h-8 w-24 text-xs"
              />
            </label>
            <AppButton size="sm" :loading="loading" @click="runInspect">
              计算特征注意力
            </AppButton>
          </div>

          <div v-if="inspect" class="mt-4">
            <p class="mb-2 text-[11px] text-muted">
              注意力 = |∂loss/∂x ×
              x|，数值越大表示该输入特征对本次预测影响越大。
            </p>
            <div class="space-y-1.5">
              <div
                v-for="(value, index) in inspect.saliency"
                :key="index"
                class="flex items-center gap-2"
              >
                <span
                  class="w-10 shrink-0 text-right font-mono text-[10px] text-muted"
                >
                  f{{ index }}
                </span>
                <div
                  class="h-2.5 flex-1 overflow-hidden rounded-sm"
                  :style="{ background: 'var(--bg-elevated)' }"
                >
                  <div
                    class="h-2.5"
                    :style="{
                      width: `${(value / maxSaliency) * 100}%`,
                      backgroundImage: 'var(--brand-gradient)',
                    }"
                  />
                </div>
                <span
                  class="w-16 shrink-0 font-mono text-[10px] text-secondary"
                >
                  {{ value.toFixed(4) }}
                </span>
              </div>
            </div>
          </div>
          <p v-else class="mt-6 text-xs text-muted">
            点击「计算特征注意力」查看各输入特征的贡献。
          </p>
        </template>

        <!-- 注意力曲线 -->
        <template v-else-if="tab === 'trend'">
          <div class="flex flex-wrap items-end gap-2">
            <AppButton size="sm" :loading="loading" @click="loadAttentionTrend">
              刷新曲线
            </AppButton>
            <span v-if="trend" class="text-[11px] text-muted">
              共 {{ trend.epochs.length }} 个 epoch · {{ trend.series.length }}
              个输入特征
            </span>
          </div>
          <div
            class="relative mt-3 h-[300px] w-full overflow-hidden rounded-md border"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <div ref="trendRef" class="h-full w-full" />
          </div>
          <p class="mt-2 text-[10px] text-muted">
            每条线代表一个输入特征的 |∂loss/∂x × x| 随 epoch
            的均值；曲线走高说明模型越来越依赖该特征。
          </p>
        </template>

        <!-- 归因 -->
        <template v-else-if="tab === 'attribution'">
          <div class="flex flex-wrap items-end gap-2">
            <label class="text-[11px] text-secondary">
              样本
              <input
                v-model.number="attributionIndex"
                type="number"
                min="0"
                class="ml-1 w-20 rounded-sm border bg-transparent px-2 py-1 text-xs text-secondary"
                :style="{ borderColor: 'var(--border-default)' }"
              />
            </label>
            <AppButton size="sm" :loading="loading" @click="loadAttribution">
              计算归因
            </AppButton>
            <span v-if="attribution" class="text-[11px] text-muted">
              预测类别 {{ attribution.prediction }} · 置信度
              {{ (attribution.probability * 100).toFixed(1) }}% · 真实标签
              {{ attribution.label }}
            </span>
          </div>
          <div
            class="relative mt-3 h-[240px] w-full overflow-hidden rounded-md border"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <div ref="attributionRef" class="h-full w-full" />
          </div>
          <p class="mt-2 text-[10px] leading-relaxed text-muted">
            Integrated Gradients：基线取全零、积分
            {{ attribution?.steps ?? 32 }}
            步。正值表示该特征把预测推向当前类别，负值表示拉回。
          </p>
        </template>

        <!-- 投影 -->
        <template v-else>
          <div class="flex flex-wrap items-end gap-2">
            <label class="text-[11px] text-secondary">
              层
              <select
                v-model.number="projectionLayer"
                class="dv-select ml-1 h-8 text-xs"
              >
                <option
                  v-for="index in projection?.layer_count ?? 3"
                  :key="index"
                  :value="index - 1"
                >
                  第 {{ index }} 层
                </option>
              </select>
            </label>
            <label class="text-[11px] text-secondary">
              方法
              <select
                v-model="projectionMethod"
                class="dv-select ml-1 h-8 text-xs"
                @change="onProjectionMethodChange"
              >
                <option value="pca">PCA</option>
                <option value="tsne">t-SNE</option>
              </select>
            </label>
            <AppButton size="sm" :loading="loading" @click="loadProjection">
              重新投影
            </AppButton>
            <span
              v-if="projection && projection.method === 'pca'"
              class="text-[11px] text-muted"
            >
              主成分解释度 {{ (projection.explained[0] * 100).toFixed(1) }}% /
              {{ (projection.explained[1] * 100).toFixed(1) }}%
            </span>
            <span v-else-if="projection" class="text-[11px] text-muted">
              t-SNE 为非线性投影，无解释度指标
            </span>
          </div>

          <div
            class="relative mt-3 w-full overflow-hidden rounded-md border"
            :style="{ borderColor: 'var(--border-subtle)', height: '300px' }"
          >
            <canvas ref="canvasRef" class="block h-full w-full" />
          </div>
          <p class="mt-2 text-[10px] text-muted">
            每个颜色代表一个类别；坐标是该层激活经
            {{ projection?.method === 'tsne' ? 't-SNE' : 'PCA' }}
            降到二维后的位置。
          </p>
        </template>
      </div>
    </div>
  </div>
</template>
