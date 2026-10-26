<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'

import { getTrainCode, stopTraining, type GeneratedCode } from '@/api/train'
import type { ImageEvalData } from '@/api/records'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import ImageEvalPanel from '@/components/train/ImageEvalPanel.vue'
import TrainingTopology from '@/components/train/TrainingTopology.vue'
import {
  useTrainingSocket,
  type TrainingEvent,
  type TrainingSocketState,
} from '@/composables/useTrainingSocket'
import { useGraphStore } from '@/stores/graph'
import { useToastStore } from '@/stores/toast'
import { NODE_TYPE_LABEL } from '@/types/graph'

type TrainStatus = 'connecting' | 'running' | 'completed' | 'failed' | 'stopped'

interface LogLine {
  id: number
  text: string
}

const route = useRoute()
const router = useRouter()
const graph = useGraphStore()
const toast = useToastStore()

const taskId = String(route.params.taskId ?? '')

const chartRef = ref<HTMLElement | null>(null)
const layerChartRef = ref<HTMLElement | null>(null)
const logRef = ref<HTMLElement | null>(null)
let chart: ECharts | null = null
let layerChart: ECharts | null = null

const status = ref<TrainStatus>('connecting')
const socketState = ref<TrainingSocketState>('connecting')
const totalEpochs = ref(0)
const currentEpoch = ref(0)
const logs = ref<LogLine[]>([])
const stopping = ref(false)
const failureReason = ref('')
const finalLoss = ref<number | null>(null)
const finalAccuracy = ref<number | null>(null)

const epochSeries = ref<number[]>([])
const trainLossSeries = ref<(number | null)[]>([])
const valLossSeries = ref<(number | null)[]>([])
const accuracySeries = ref<(number | null)[]>([])

/** 逐层权重范数 / 标准差 / 激活分位数：node_id → 每个 epoch 的统计量 */
const layerHistory = ref<
  Record<string, { norm: number; std: number; p95: number }[]>
>({})
const layerOrder = ref<string[]>([])
const layerMetric = ref<'weight_norm' | 'weight_std' | 'activation_p95'>(
  'weight_norm',
)

interface GraphProfileNode {
  node_id: string
  kind: string
  in_dim: number
  out_dim: number
  dtype: string
  param_count: number
  weight_bytes: number
  activation_bytes: number
  time_ms: number
}

/** 计算图剖析：训练开始时由后端推送一次 */
const graphProfile = ref<GraphProfileNode[]>([])

/** 图像训练评估：训练结束时推送 */
const imageEval = ref<ImageEvalData | null>(null)

/** 拓扑流光方向：仅作视觉示意，前向青色 / 反向紫红 */
const flowDirection = ref<'forward' | 'backward'>('forward')

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(2)} MB`
}

/** 归一化耗时，用于拓扑图热力叠加 */
const heatByNode = computed(() => {
  const max = Math.max(
    ...graphProfile.value.map((node) => node.time_ms),
    0.0001,
  )
  const map: Record<string, number> = {}
  for (const node of graphProfile.value) {
    map[node.node_id] = node.time_ms / max
  }
  return map
})

const profileTitles = computed(() => {
  const map: Record<string, string> = {}
  for (const node of graphProfile.value) {
    map[node.node_id] =
      `${node.node_id} · ${node.in_dim}→${node.out_dim} · ` +
      `${node.time_ms.toFixed(3)} ms · 权重 ${formatBytes(node.weight_bytes)} · ` +
      `激活 ${formatBytes(node.activation_bytes)}`
  }
  return map
})

const totalWeightBytes = computed(() =>
  graphProfile.value.reduce((sum, node) => sum + node.weight_bytes, 0),
)
const totalActivationBytes = computed(() =>
  graphProfile.value.reduce((sum, node) => sum + node.activation_bytes, 0),
)

// 代码查看器
const codeOpen = ref(false)
const codeLoading = ref(false)
const codeData = ref<GeneratedCode | null>(null)
const codeNodeId = ref('')

const codeLines = computed(() => codeData.value?.code.split('\n') ?? [])

const highlightedLines = computed(() => {
  const active = new Set<number>()
  const entry = codeData.value?.lines[codeNodeId.value]
  if (!entry) return active
  for (const range of [entry.definition, entry.forward]) {
    if (range && range.length === 2) {
      for (let line = range[0]; line <= range[1]; line += 1) active.add(line)
    }
  }
  return active
})

async function openCode(nodeId: string): Promise<void> {
  if (!taskId) return
  codeNodeId.value = nodeId
  codeOpen.value = true
  if (codeData.value) return

  codeLoading.value = true
  try {
    codeData.value = await getTrainCode(taskId)
  } catch {
    codeOpen.value = false
  } finally {
    codeLoading.value = false
  }
}

const LAYER_COLORS = [
  '#22d3ee',
  '#a78bfa',
  '#34d399',
  '#f97316',
  '#f472b6',
  '#facc15',
]

function nodeLabel(nodeId: string): string {
  const node = graph.nodes.find((item) => item.id === nodeId)
  if (!node) return nodeId
  const units = node.type === 'input' ? node.params.features : node.params.units
  return `${NODE_TYPE_LABEL[node.type]} ${units ?? ''}`.trim()
}

const seenEpochs = new Set<number>()
let logSeed = 0

const progress = computed(() => {
  if (totalEpochs.value === 0) return 0
  return Math.min(
    100,
    Math.round((currentEpoch.value / totalEpochs.value) * 100),
  )
})

const statusText: Record<TrainStatus, string> = {
  connecting: '连接中',
  running: '训练中',
  completed: '已完成',
  failed: '失败',
  stopped: '已中止',
}

const statusBadge: Record<TrainStatus, string> = {
  connecting: 'dv-badge--neutral',
  running: 'dv-badge--warning',
  completed: 'dv-badge--success',
  failed: 'dv-badge--danger',
  stopped: 'dv-badge--neutral',
}

function format(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return Number(value).toFixed(4)
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

async function pushLog(text: string): Promise<void> {
  logSeed += 1
  logs.value.push({ id: logSeed, text })
  await nextTick()
  if (logRef.value) {
    logRef.value.scrollTop = logRef.value.scrollHeight
  }
}

function baseOption(): echarts.EChartsOption {
  return {
    backgroundColor: 'transparent',
    grid: { left: 56, right: 56, top: 40, bottom: 36 },
    tooltip: { trigger: 'axis' },
    legend: {
      textStyle: { color: '#94a3b8' },
      icon: 'roundRect',
      top: 4,
    },
    xAxis: {
      type: 'category',
      data: [],
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel: { color: '#94a3b8' },
    },
    yAxis: [
      {
        type: 'value',
        name: 'Loss',
        nameTextStyle: { color: '#94a3b8' },
        axisLabel: { color: '#94a3b8' },
        splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } },
      },
      {
        type: 'value',
        name: 'Accuracy',
        min: 0,
        max: 1,
        nameTextStyle: { color: '#94a3b8' },
        axisLabel: { color: '#94a3b8' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '训练损失',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: [],
        itemStyle: { color: '#22d3ee' },
        animationDuration: 300,
      },
      {
        name: '验证损失',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: [],
        itemStyle: { color: '#8b5cf6' },
        animationDuration: 300,
      },
      {
        name: '准确率',
        type: 'line',
        smooth: true,
        showSymbol: false,
        yAxisIndex: 1,
        data: [],
        itemStyle: { color: '#34d399' },
        animationDuration: 300,
      },
    ],
  }
}

function updateChart(): void {
  if (!chart) return
  chart.setOption({
    xAxis: { data: epochSeries.value },
    series: [
      { data: trainLossSeries.value },
      { data: valLossSeries.value },
      { data: accuracySeries.value },
    ],
  })
}

function resizeChart(): void {
  chart?.resize()
  layerChart?.resize()
}

function layerOption(): echarts.EChartsOption {
  return {
    backgroundColor: 'transparent',
    grid: { left: 48, right: 16, top: 26, bottom: 22 },
    tooltip: { trigger: 'axis' },
    legend: {
      textStyle: { color: '#94a3b8', fontSize: 10 },
      icon: 'roundRect',
      top: 0,
      type: 'scroll',
    },
    xAxis: {
      type: 'category',
      data: epochSeries.value,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel: { color: '#94a3b8', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      name:
        layerMetric.value === 'weight_norm'
          ? '‖W‖₁'
          : layerMetric.value === 'weight_std'
            ? 'σ(W)'
            : '|激活| P95',
      nameTextStyle: { color: '#94a3b8', fontSize: 10 },
      axisLabel: { color: '#94a3b8', fontSize: 10 },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } },
    },
    series: layerOrder.value.map((nodeId, index) => ({
      name: nodeLabel(nodeId),
      type: 'line' as const,
      smooth: true,
      showSymbol: false,
      data: (layerHistory.value[nodeId] ?? []).map((point) =>
        layerMetric.value === 'weight_norm'
          ? point.norm
          : layerMetric.value === 'weight_std'
            ? point.std
            : point.p95,
      ),
      itemStyle: { color: LAYER_COLORS[index % LAYER_COLORS.length] },
      animationDuration: 300,
    })),
  }
}

function updateLayerChart(): void {
  if (!layerChart) return
  // 层数变化会改变 series 数量，整体替换避免残留旧序列
  layerChart.setOption(layerOption(), true)
}

function setLayerMetric(
  metric: 'weight_norm' | 'weight_std' | 'activation_p95',
): void {
  layerMetric.value = metric
  updateLayerChart()
}

/** 计算图剖析里耗时最长的一层，用于归一化热力条 */
const maxProfileTime = computed(() =>
  Math.max(...graphProfile.value.map((node) => node.time_ms), 0.0001),
)

function onEvent(event: TrainingEvent): void {
  switch (event.type) {
    case 'started':
      status.value = 'running'
      totalEpochs.value = toNumber(event.total_epochs) ?? 0
      void pushLog(
        `训练开始：共 ${event.total_epochs} 个 epoch，输入维度 ${event.input_dim}`,
      )
      break

    case 'graph_profile': {
      const nodes = event.nodes
      if (Array.isArray(nodes)) {
        graphProfile.value = nodes as GraphProfileNode[]
      }
      break
    }

    case 'image_eval': {
      imageEval.value = event as unknown as ImageEvalData
      break
    }

    case 'epoch': {
      const epoch = toNumber(event.epoch)
      if (epoch === null || seenEpochs.has(epoch)) return
      seenEpochs.add(epoch)

      currentEpoch.value = epoch
      epochSeries.value.push(epoch)
      trainLossSeries.value.push(toNumber(event.train_loss))
      valLossSeries.value.push(toNumber(event.val_loss))
      accuracySeries.value.push(toNumber(event.accuracy))
      updateChart()

      const accuracyText =
        event.accuracy === null
          ? ''
          : ` acc=${format(toNumber(event.accuracy))}`

      const stats = event.layer_stats
      if (Array.isArray(stats)) {
        for (const raw of stats) {
          const item = raw as {
            node_id?: string
            weight_norm?: number
            weight_std?: number
            activation_p95?: number
          }
          const nodeId = String(item.node_id ?? '')
          if (!nodeId) continue
          if (!layerOrder.value.includes(nodeId)) {
            layerOrder.value = [...layerOrder.value, nodeId]
          }
          const values = layerHistory.value[nodeId] ?? []
          layerHistory.value[nodeId] = [
            ...values,
            {
              norm: Number(item.weight_norm ?? 0),
              std: Number(item.weight_std ?? 0),
              p95: Number(item.activation_p95 ?? 0),
            },
          ]
        }
        updateLayerChart()
      }

      void pushLog(
        `Epoch ${epoch}: train_loss=${format(toNumber(event.train_loss))} val_loss=${format(toNumber(event.val_loss))}${accuracyText}`,
      )
      break
    }

    case 'completed':
      status.value = 'completed'
      finalLoss.value = toNumber(event.final_loss)
      finalAccuracy.value = toNumber(event.final_accuracy)
      void pushLog('训练完成，训练记录已保存')
      toast.success('训练完成')
      break

    case 'failed':
      status.value = 'failed'
      failureReason.value = String(event.reason ?? '训练失败')
      void pushLog(`训练失败：${failureReason.value}`)
      toast.error('训练失败')
      break

    case 'stopped':
      status.value = 'stopped'
      void pushLog(`训练已中止于第 ${event.epoch} 个 epoch`)
      toast.info('训练已中止')
      break
  }
}

useTrainingSocket(taskId, onEvent, (state) => {
  socketState.value = state
  if (state === 'closed' && status.value === 'connecting') {
    status.value = 'failed'
    failureReason.value = '无法连接到训练通道'
  }
})

async function onStop(): Promise<void> {
  stopping.value = true
  try {
    await stopTraining(taskId)
  } catch {
    // 拦截器已提示
  } finally {
    stopping.value = false
  }
}

onMounted(() => {
  graph.loadDraft()
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    chart.setOption(baseOption())
  }
  if (layerChartRef.value) {
    layerChart = echarts.init(layerChartRef.value)
    layerChart.setOption(layerOption())
  }
  window.addEventListener('resize', resizeChart)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
  layerChart?.dispose()
  chart = null
  layerChart = null
})
</script>

<template>
  <div class="flex h-screen flex-col overflow-hidden bg-base">
    <header
      class="flex h-16 shrink-0 items-center justify-between gap-4 border-b px-5"
      :style="{
        borderColor: 'var(--border-subtle)',
        background: 'var(--bg-surface)',
      }"
    >
      <div class="flex min-w-0 items-center gap-3">
        <AppButton variant="ghost" size="sm" @click="router.push('/workspace')">
          ← 工作台
        </AppButton>
        <span class="text-sm font-medium text-primary">训练监控</span>
        <span class="dv-badge" :class="statusBadge[status]">
          {{ statusText[status] }}
        </span>
        <span
          v-if="socketState === 'reconnecting'"
          class="text-[11px] text-warning"
        >
          连接中断，正在重连…
        </span>
      </div>

      <div class="flex items-center gap-3">
        <span class="font-mono text-xs text-muted">
          epoch {{ currentEpoch }} / {{ totalEpochs || '—' }}
        </span>
        <AppButton
          variant="danger"
          size="sm"
          :loading="stopping"
          :disabled="status !== 'running'"
          @click="onStop"
        >
          停止训练
        </AppButton>
      </div>
    </header>

    <div
      class="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-hidden p-4 lg:grid-cols-3"
    >
      <!-- 指标曲线 -->
      <AppCard class="flex min-h-0 flex-col lg:col-span-2" padding="none">
        <div
          class="flex items-center justify-between border-b px-4 py-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <h2 class="text-sm font-medium text-primary">训练指标</h2>
          <span class="font-mono text-xs text-muted">{{ progress }}%</span>
        </div>
        <div class="h-1 w-full" :style="{ background: 'var(--border-subtle)' }">
          <div
            class="h-1 transition-all duration-emphasis"
            :style="{
              width: `${progress}%`,
              backgroundImage: 'var(--brand-gradient)',
            }"
          />
        </div>
        <div ref="chartRef" class="min-h-0 flex-1" />
        <div
          class="flex shrink-0 items-center justify-between border-t px-4 py-1.5"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <span class="text-[11px] text-muted">
            {{
              layerMetric === 'weight_norm'
                ? '逐层权重范数（‖W‖₁ 随 epoch）'
                : '逐层权重标准差（σ(W) 随 epoch）'
            }}
          </span>
          <div class="flex items-center gap-0.5">
            <button
              v-for="item in [
                { key: 'weight_norm', label: '范数' },
                { key: 'weight_std', label: '标准差' },
                { key: 'activation_p95', label: '激活 P95' },
              ]"
              :key="item.key"
              type="button"
              class="rounded-sm px-2 py-0.5 text-[10px]"
              :class="
                layerMetric === item.key
                  ? 'text-primary'
                  : 'text-muted hover:text-secondary'
              "
              :style="
                layerMetric === item.key
                  ? { background: 'var(--bg-elevated)' }
                  : {}
              "
              @click="
                setLayerMetric(
                  item.key as 'weight_norm' | 'weight_std' | 'activation_p95',
                )
              "
            >
              {{ item.label }}
            </button>
          </div>
        </div>
        <div ref="layerChartRef" class="h-[150px] w-full shrink-0" />
      </AppCard>

      <!-- 拓扑与结果 -->
      <div class="flex min-h-0 flex-col gap-4">
        <AppCard class="shrink-0" padding="none">
          <div
            class="flex items-center justify-between border-b px-4 py-3"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <h2 class="text-sm font-medium text-primary">网络拓扑</h2>
            <div class="flex items-center gap-0.5">
              <button
                v-for="item in [
                  { key: 'forward', label: '前向' },
                  { key: 'backward', label: '反向' },
                ]"
                :key="item.key"
                type="button"
                class="rounded-sm px-2 py-0.5 text-[10px]"
                :class="
                  flowDirection === item.key
                    ? 'text-primary'
                    : 'text-muted hover:text-secondary'
                "
                :style="
                  flowDirection === item.key
                    ? { background: 'var(--bg-elevated)' }
                    : {}
                "
                @click="flowDirection = item.key as 'forward' | 'backward'"
              >
                {{ item.label }}
              </button>
            </div>
          </div>
          <div class="h-[200px] p-2">
            <TrainingTopology
              :nodes="graph.nodes"
              :edges="graph.edges"
              :active="status === 'running'"
              :direction="flowDirection"
              :heat="heatByNode"
              :titles="profileTitles"
            />
          </div>
        </AppCard>

        <AppCard class="shrink-0">
          <h2 class="text-sm font-medium text-primary">最终结果</h2>
          <dl class="mt-3 space-y-2 text-xs">
            <div class="flex justify-between">
              <dt class="text-muted">最终验证损失</dt>
              <dd class="font-mono text-primary">{{ format(finalLoss) }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-muted">最终准确率</dt>
              <dd class="font-mono text-primary">
                {{ format(finalAccuracy) }}
              </dd>
            </div>
          </dl>
          <p
            v-if="failureReason"
            class="mt-3 text-xs leading-relaxed text-danger"
          >
            {{ failureReason }}
          </p>
        </AppCard>
      </div>

      <!-- 计算图剖析 -->
      <AppCard
        v-if="graphProfile.length > 0"
        class="lg:col-span-3"
        padding="none"
      >
        <div
          class="flex items-center justify-between border-b px-4 py-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <h2 class="text-sm font-medium text-primary">计算图剖析</h2>
          <span class="text-[10px] text-muted">
            单次前向的粗略耗时（毫秒）· 点击行查看等效代码
          </span>
        </div>
        <div class="max-h-64 overflow-auto">
          <table class="w-full text-left text-[11px]">
            <thead
              class="sticky top-0"
              :style="{ background: 'var(--bg-elevated)' }"
            >
              <tr class="text-muted">
                <th class="px-4 py-2">节点</th>
                <th class="px-3 py-2">类型</th>
                <th class="px-3 py-2">输入 → 输出</th>
                <th class="px-3 py-2">dtype</th>
                <th class="px-3 py-2">参数</th>
                <th class="px-3 py-2">内存</th>
                <th class="px-3 py-2">耗时</th>
                <th class="px-4 py-2">占比</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="node in graphProfile"
                :key="node.node_id"
                class="cursor-pointer border-t transition-colors duration-fast hover:bg-hover"
                :style="{ borderColor: 'var(--border-subtle)' }"
                @click="openCode(node.node_id)"
              >
                <td class="px-4 py-1.5 font-mono text-secondary">
                  {{ node.node_id }}
                </td>
                <td class="px-3 py-1.5 text-secondary">
                  {{ node.kind === 'input' ? '输入' : '全连接' }}
                </td>
                <td class="px-3 py-1.5 font-mono text-secondary">
                  {{ node.in_dim }} → {{ node.out_dim }}
                </td>
                <td class="px-3 py-1.5 font-mono text-muted">
                  {{ node.dtype }}
                </td>
                <td class="px-3 py-1.5 font-mono text-secondary">
                  {{ node.param_count }}
                </td>
                <td
                  class="px-3 py-1.5 font-mono text-secondary"
                  :title="`权重 ${formatBytes(node.weight_bytes)} + 激活 ${formatBytes(node.activation_bytes)}`"
                >
                  {{ formatBytes(node.weight_bytes + node.activation_bytes) }}
                </td>
                <td class="px-3 py-1.5 font-mono text-primary">
                  {{ node.time_ms.toFixed(3) }} ms
                </td>
                <td class="px-4 py-1.5">
                  <div
                    class="h-1.5 w-full overflow-hidden rounded-sm"
                    :style="{ background: 'var(--bg-elevated)' }"
                  >
                    <div
                      class="h-1.5"
                      :style="{
                        width: `${(node.time_ms / maxProfileTime) * 100}%`,
                        backgroundImage: 'var(--brand-gradient)',
                      }"
                    />
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div
          class="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-2 text-[10px] text-muted"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <span>
            合计：权重 {{ formatBytes(totalWeightBytes) }} · 单批激活
            {{ formatBytes(totalActivationBytes) }}
          </span>
          <span
            >激活按单批输入估算，不含优化器状态；拓扑节点颜色深浅 =
            耗时占比</span
          >
        </div>
      </AppCard>

      <!-- 图像评估 -->
      <AppCard v-if="imageEval" class="lg:col-span-3" padding="none">
        <div
          class="flex items-center justify-between border-b px-4 py-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <h2 class="text-sm font-medium text-primary">图像评估</h2>
          <span class="text-[10px] text-muted"> 验证集混淆矩阵与样本预测 </span>
        </div>
        <ImageEvalPanel v-bind="imageEval" />
      </AppCard>

      <!-- 等效代码 -->
      <div
        v-if="codeOpen"
        class="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
        @click.self="codeOpen = false"
      >
        <div
          class="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg border"
          :style="{
            borderColor: 'var(--border-default)',
            background: 'var(--bg-surface)',
          }"
        >
          <header
            class="flex shrink-0 items-center justify-between border-b px-4 py-3"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <div>
              <h3 class="text-sm font-medium text-primary">
                等效代码 · 节点 {{ codeNodeId }}
              </h3>
              <p class="mt-0.5 text-[10px] text-muted">
                由拓扑自动生成，用于对照阅读；实际训练由 DagNet 执行
              </p>
            </div>
            <AppButton variant="ghost" size="sm" @click="codeOpen = false">
              关闭
            </AppButton>
          </header>

          <div class="min-h-0 flex-1 overflow-auto py-2">
            <p v-if="codeLoading" class="px-4 text-xs text-muted">生成中…</p>
            <div
              v-for="(line, index) in codeLines"
              :key="index"
              class="flex gap-3 px-3 font-mono text-[11px] leading-5"
              :style="
                highlightedLines.has(index + 1)
                  ? { background: 'rgba(34, 211, 238, 0.12)' }
                  : {}
              "
            >
              <span class="w-8 shrink-0 select-none text-right text-muted">
                {{ index + 1 }}
              </span>
              <span class="whitespace-pre text-secondary">{{
                line || ' '
              }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 日志 -->
      <AppCard class="min-h-0 lg:col-span-3" padding="none">
        <div
          class="border-b px-4 py-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <h2 class="text-sm font-medium text-primary">训练日志</h2>
        </div>
        <div
          ref="logRef"
          class="max-h-40 overflow-y-auto px-4 py-2 font-mono text-[11px] leading-relaxed text-secondary"
        >
          <p v-for="line in logs" :key="line.id">{{ line.text }}</p>
          <p v-if="logs.length === 0" class="text-muted">等待训练开始…</p>
        </div>
      </AppCard>
    </div>
  </div>
</template>
