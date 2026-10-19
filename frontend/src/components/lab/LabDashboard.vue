<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'

import type {
  LabBoundaryEvent,
  LabEpochEvent,
  LabWeightsEvent,
} from '@/composables/useLabSocket'

const props = defineProps<{
  history: LabEpochEvent[]
  latest: LabEpochEvent | null
  weights: LabWeightsEvent | null
  boundary: LabBoundaryEvent | null
}>()

const lineRef = ref<HTMLElement | null>(null)
const histogramRef = ref<HTMLElement | null>(null)
const boundaryRef = ref<HTMLCanvasElement | null>(null)

let lineChart: ECharts | null = null
let histogramChart: ECharts | null = null
let canvasObserver: ResizeObserver | null = null

function format(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

const KPI_ITEMS = [
  { key: 'epoch', label: '轮次' },
  { key: 'train_loss', label: '训练 loss' },
  { key: 'val_loss', label: '验证 loss' },
  { key: 'accuracy', label: '验证准确率' },
  { key: 'grad_norm', label: '梯度范数' },
] as const

function kpiValue(key: (typeof KPI_ITEMS)[number]['key']): string {
  const current = props.latest
  if (!current) return '—'
  if (key === 'epoch') return String(current.epoch)
  if (key === 'accuracy') return format(current.accuracy, 3)
  if (key === 'grad_norm') return format(current.grad_norm, 2)
  return format(current[key], 4)
}

function baseLineOption(): echarts.EChartsOption {
  return {
    backgroundColor: 'transparent',
    grid: { left: 42, right: 42, top: 28, bottom: 26 },
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#94a3b8', fontSize: 10 }, top: 0 },
    xAxis: {
      type: 'category',
      data: [],
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel: { color: '#94a3b8', fontSize: 10 },
    },
    yAxis: [
      {
        type: 'value',
        name: 'loss',
        nameTextStyle: { color: '#94a3b8', fontSize: 10 },
        axisLabel: { color: '#94a3b8', fontSize: 10 },
        splitLine: { lineStyle: { color: 'rgba(148,163,184,0.12)' } },
      },
      {
        type: 'value',
        name: 'acc',
        min: 0,
        max: 1,
        nameTextStyle: { color: '#94a3b8', fontSize: 10 },
        axisLabel: { color: '#94a3b8', fontSize: 10 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '训练 loss',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: [],
        itemStyle: { color: '#f97316' },
      },
      {
        name: '验证 loss',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: [],
        itemStyle: { color: '#22d3ee' },
      },
      {
        name: '验证准确率',
        type: 'line',
        smooth: true,
        showSymbol: false,
        yAxisIndex: 1,
        data: [],
        itemStyle: { color: '#a78bfa' },
      },
    ],
  }
}

function updateLineChart(): void {
  if (!lineChart) return
  lineChart.setOption({
    xAxis: { data: props.history.map((item) => item.epoch) },
    series: [
      { data: props.history.map((item) => item.train_loss) },
      { data: props.history.map((item) => item.val_loss) },
      { data: props.history.map((item) => item.accuracy) },
    ],
  })
}

function updateHistogram(): void {
  if (!histogramChart) return
  const weights = props.weights
  if (!weights) {
    histogramChart.setOption({ xAxis: { data: [] }, series: [{ data: [] }] })
    return
  }

  const labels = weights.counts.map((_, index) => {
    const start = weights.edges[index] ?? 0
    const end = weights.edges[index + 1] ?? 0
    return `${start.toFixed(2)}~${end.toFixed(2)}`
  })

  histogramChart.setOption({
    xAxis: { data: labels },
    series: [{ data: weights.counts }],
  })
}

function drawBoundary(): void {
  const canvas = boundaryRef.value
  const data = props.boundary
  if (!canvas) return

  const parent = canvas.parentElement
  const width = Math.max(parent?.clientWidth ?? 260, 120)
  const height = Math.max(parent?.clientHeight ?? 180, 100)

  if (canvas.width !== width) canvas.width = width
  if (canvas.height !== height) canvas.height = height

  const context = canvas.getContext('2d')
  if (!context) return

  context.clearRect(0, 0, width, height)
  if (!data) return

  const { size, min, max, values, points } = data
  const cellWidth = width / size
  const cellHeight = height / size

  for (let row = 0; row < size; row += 1) {
    for (let column = 0; column < size; column += 1) {
      const probability = values[row * size + column] ?? 0.5
      // 类别 1 用橙色、类别 0 用青色，按概率混合
      const red = Math.round(34 + (249 - 34) * probability)
      const green = Math.round(211 + (115 - 211) * probability)
      const blue = Math.round(238 + (22 - 238) * probability)
      context.fillStyle = `rgba(${red}, ${green}, ${blue}, 0.28)`
      context.fillRect(
        column * cellWidth,
        height - (row + 1) * cellHeight,
        cellWidth + 1,
        cellHeight + 1,
      )
    }
  }

  const span = max - min || 1
  for (const point of points) {
    const px = ((point.x - min) / span) * width
    const py = height - ((point.y - min) / span) * height
    context.beginPath()
    context.arc(px, py, 1.8, 0, Math.PI * 2)
    context.fillStyle = point.label === 0 ? '#67e8f9' : '#fdba74'
    context.fill()
  }
}

function resizeBoundary(): void {
  drawBoundary()
}

onMounted(() => {
  if (lineRef.value) {
    lineChart = echarts.init(lineRef.value)
    lineChart.setOption(baseLineOption())
    updateLineChart()
  }

  if (histogramRef.value) {
    histogramChart = echarts.init(histogramRef.value)
    histogramChart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 34, right: 12, top: 22, bottom: 34 },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: [],
        axisLabel: { color: '#94a3b8', fontSize: 9, rotate: 40 },
        axisLine: { lineStyle: { color: '#334155' } },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#94a3b8', fontSize: 10 },
        splitLine: { lineStyle: { color: 'rgba(148,163,184,0.12)' } },
      },
      series: [
        {
          type: 'bar',
          data: [],
          itemStyle: { color: '#22d3ee' },
          barMaxWidth: 14,
        },
      ],
    })
    updateHistogram()
  }

  drawBoundary()

  if (typeof ResizeObserver !== 'undefined' && boundaryRef.value?.parentElement) {
    canvasObserver = new ResizeObserver(() => resizeBoundary())
    canvasObserver.observe(boundaryRef.value.parentElement)
  }
})

onBeforeUnmount(() => {
  canvasObserver?.disconnect()
  lineChart?.dispose()
  histogramChart?.dispose()
  lineChart = null
  histogramChart = null
})

watch(() => props.history, updateLineChart, { deep: true })
watch(() => props.weights, updateHistogram, { deep: true })
watch(() => props.boundary, drawBoundary, { deep: true })
</script>

<template>
  <div class="flex h-full flex-col gap-2">
    <div class="grid shrink-0 grid-cols-5 gap-2">
      <div
        v-for="item in KPI_ITEMS"
        :key="item.key"
        class="rounded-md border px-3 py-1.5"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'var(--bg-surface)',
        }"
      >
        <p class="text-[10px] text-muted">{{ item.label }}</p>
        <p class="mt-0.5 font-mono text-sm text-primary">
          {{ kpiValue(item.key) }}
        </p>
      </div>
    </div>

    <div class="grid min-h-0 flex-1 grid-cols-3 gap-2">
      <div
        class="min-h-0 rounded-md border p-2"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'var(--bg-surface)',
        }"
      >
        <div ref="lineRef" class="h-full w-full" />
      </div>

      <div
        class="min-h-0 rounded-md border p-2"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'var(--bg-surface)',
        }"
      >
        <div ref="histogramRef" class="h-full w-full" />
      </div>

      <div
        class="relative min-h-0 rounded-md border p-2"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'var(--bg-surface)',
        }"
      >
        <canvas ref="boundaryRef" class="h-full w-full" />
        <p class="pointer-events-none absolute right-3 top-2 text-[10px] text-muted">
          决策边界 + 数据分布
        </p>
      </div>
    </div>
  </div>
</template>
