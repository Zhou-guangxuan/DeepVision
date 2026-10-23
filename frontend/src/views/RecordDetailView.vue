<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'

import {
  diagnoseRecord,
  getImageEval,
  getRecord,
  rerunRecord,
  type DiagnosisResult,
  type ImageEvalData,
  type TrainingRecord,
} from '@/api/records'
import ImageEvalPanel from '@/components/train/ImageEvalPanel.vue'
import TrainingTopology from '@/components/train/TrainingTopology.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import { NODE_HEIGHT } from '@/types/graph'
import type { GraphEdge, GraphNode } from '@/types/graph'
import { useToastStore } from '@/stores/toast'

/**
 * 记录详情页（只读）：拓扑、超参、指标曲线、诊断结果。
 * 图像训练额外展示混淆矩阵与样本预测。
 */

const route = useRoute()
const router = useRouter()
const toast = useToastStore()

const recordId = Number(route.params.id)
const record = ref<TrainingRecord | null>(null)
const diagnosis = ref<DiagnosisResult | null>(null)
const imageEval = ref<ImageEvalData | null>(null)
const loading = ref(false)
const rerunning = ref(false)

const chartRef = ref<HTMLElement | null>(null)
let chart: ECharts | null = null

interface CurvePoint {
  epoch?: number
  train_loss?: number
  val_loss?: number
  accuracy?: number
}

const history = computed<CurvePoint[]>(() => {
  const metrics = record.value?.result_metrics as
    { history?: CurvePoint[] } | undefined
  return metrics?.history ?? []
})

/** 记录里的 nodes 没有坐标，按纵向堆叠生成只读布局 */
const topologyNodes = computed<GraphNode[]>(() => {
  const nodes = record.value?.model_config?.nodes ?? []
  return nodes.map((node, index) => ({
    id: node.id,
    type: node.type,
    params: node.params as GraphNode['params'],
    x: 340,
    y: 40 + index * (NODE_HEIGHT + 40),
  }))
})

const topologyEdges = computed<GraphEdge[]>(() => {
  const edges = record.value?.model_config?.edges ?? []
  return edges.map((edge, index) => ({ ...edge, id: `e${index}` }))
})

const finalAccuracy = computed(() => {
  const value = record.value?.result_metrics?.final_accuracy
  return typeof value === 'number' ? value.toFixed(4) : '—'
})

const finalLoss = computed(() => {
  const value = record.value?.result_metrics?.final_loss
  return typeof value === 'number' ? value.toFixed(4) : '—'
})

const epochs = computed(() => {
  const value = record.value?.result_metrics?.epochs
  return typeof value === 'number' ? value : history.value.length
})

function renderChart(): void {
  if (!chartRef.value || history.value.length === 0) return
  if (!chart) chart = echarts.init(chartRef.value)

  const points = history.value
  chart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 48, right: 46, top: 40, bottom: 30 },
      tooltip: { trigger: 'axis', confine: true },
      legend: {
        top: 4,
        left: 6,
        icon: 'roundRect',
        itemWidth: 10,
        itemHeight: 8,
        textStyle: { color: '#94a3b8', fontSize: 10 },
      },
      xAxis: {
        type: 'category',
        data: points.map((point, index) => point.epoch ?? index + 1),
        boundaryGap: false,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#94a3b8', fontSize: 9 },
      },
      yAxis: [
        {
          type: 'value',
          min: 0,
          axisTick: { show: false },
          axisLine: { show: false },
          axisLabel: { color: '#94a3b8', fontSize: 9 },
          splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.1)' } },
        },
        {
          type: 'value',
          min: 0,
          max: 1,
          axisTick: { show: false },
          axisLine: { show: false },
          axisLabel: { color: '#94a3b8', fontSize: 9 },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: '训练 loss',
          type: 'line',
          smooth: true,
          showSymbol: false,
          data: points.map((point) => point.train_loss ?? null),
          itemStyle: { color: '#f97316' },
        },
        {
          name: '验证 loss',
          type: 'line',
          smooth: true,
          showSymbol: false,
          data: points.map((point) => point.val_loss ?? null),
          itemStyle: { color: '#22d3ee' },
        },
        {
          name: '验证准确率',
          type: 'line',
          smooth: true,
          showSymbol: false,
          yAxisIndex: 1,
          lineStyle: { type: 'dashed', width: 1.6 },
          data: points.map((point) => point.accuracy ?? null),
          itemStyle: { color: '#a78bfa' },
        },
      ],
    },
    true,
  )
}

async function load(): Promise<void> {
  loading.value = true
  try {
    record.value = await getRecord(recordId)
    await nextTick()
    renderChart()

    const hasImage = Boolean(
      (record.value.result_metrics as { image_eval?: unknown } | undefined)
        ?.image_eval,
    )

    const [diag, evalData] = await Promise.allSettled([
      diagnoseRecord(recordId),
      hasImage ? getImageEval(recordId) : Promise.resolve(null),
    ])
    if (diag.status === 'fulfilled') diagnosis.value = diag.value
    if (evalData.status === 'fulfilled' && evalData.value) {
      imageEval.value = evalData.value
    }
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function onRerun(): Promise<void> {
  rerunning.value = true
  try {
    const result = await rerunRecord(recordId)
    toast.success('已按原配置创建训练任务')
    void router.push(`/train/${result.task_id}`)
  } catch {
    // 拦截器已提示
  } finally {
    rerunning.value = false
  }
}

function handleResize(): void {
  chart?.resize()
}

onMounted(() => {
  void load()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
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
        <AppButton variant="ghost" size="sm" @click="router.push('/history')">
          ← 历史记录
        </AppButton>
        <span class="text-sm font-medium text-primary">
          记录 #{{ recordId }}
        </span>
        <span v-if="record" class="text-[11px] text-muted">
          {{ record.status }} ·
          {{ new Date(record.created_at).toLocaleString() }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <AppButton
          variant="secondary"
          size="sm"
          :disabled="record?.dataset_id === null"
          :loading="rerunning"
          @click="onRerun"
        >
          按原配置重跑
        </AppButton>
      </div>
    </header>

    <div class="grid min-h-0 flex-1 gap-4 overflow-auto p-4 lg:grid-cols-3">
      <AppCard class="lg:col-span-1" padding="none">
        <div
          class="border-b px-4 py-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <h2 class="text-sm font-medium text-primary">只读拓扑</h2>
        </div>
        <div class="h-[260px] p-2">
          <TrainingTopology
            :nodes="topologyNodes"
            :edges="topologyEdges"
            :active="false"
          />
        </div>
        <dl
          class="space-y-1.5 border-t px-4 py-3 text-[11px]"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <div class="flex justify-between">
            <dt class="text-muted">数据集</dt>
            <dd class="text-secondary">{{ record?.dataset_id ?? '—' }}</dd>
          </div>
          <div class="flex justify-between">
            <dt class="text-muted">轮数</dt>
            <dd class="font-mono text-secondary">{{ epochs }}</dd>
          </div>
          <div v-if="record" class="flex justify-between">
            <dt class="text-muted">批大小</dt>
            <dd class="font-mono text-secondary">
              {{ record.hyperparameters.batch_size ?? '—' }}
            </dd>
          </div>
          <div v-if="record" class="flex justify-between">
            <dt class="text-muted">学习率</dt>
            <dd class="font-mono text-secondary">
              {{ record.hyperparameters.learning_rate ?? '—' }}
            </dd>
          </div>
        </dl>
      </AppCard>

      <AppCard class="lg:col-span-2" padding="none">
        <div
          class="flex items-center justify-between border-b px-4 py-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <h2 class="text-sm font-medium text-primary">指标曲线</h2>
          <span class="text-[11px] text-muted">
            最终 loss {{ finalLoss }} · 准确率 {{ finalAccuracy }}
          </span>
        </div>
        <div class="h-[320px] p-2">
          <div ref="chartRef" class="h-full w-full" />
        </div>
      </AppCard>

      <AppCard v-if="diagnosis" class="lg:col-span-3" padding="none">
        <div
          class="border-b px-4 py-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <h2 class="text-sm font-medium text-primary">曲线诊断</h2>
        </div>
        <div class="space-y-2 p-4">
          <p class="text-[11px] text-secondary">{{ diagnosis.summary }}</p>
          <ul class="space-y-1">
            <li
              v-for="issue in diagnosis.issues"
              :key="issue.code"
              class="text-[11px] text-muted"
            >
              · {{ issue.title }}：{{ issue.suggestion }}
            </li>
          </ul>
        </div>
      </AppCard>

      <AppCard v-if="imageEval" class="lg:col-span-3" padding="none">
        <div
          class="border-b px-4 py-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <h2 class="text-sm font-medium text-primary">图像评估</h2>
        </div>
        <ImageEvalPanel v-bind="imageEval" />
      </AppCard>
    </div>
  </div>
</template>
