<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'

import {
  compareRecords,
  diagnoseRecord,
  listRecords,
  rerunRecord,
  type CompareRun,
  type DiagnosisResult,
  type TrainingRecord,
} from '@/api/records'
import AppButton from '@/components/ui/AppButton.vue'
import { useToastStore } from '@/stores/toast'

/**
 * 历史记录页：
 * - 多选 2–4 条记录做曲线对比（按 epoch 或按训练进度对齐）
 * - 单条记录做曲线诊断（过拟合 / 欠拟合 / 学习率）
 * - 一键重跑（沿用原配置与超参）
 */

const RUN_COLORS = ['#22d3ee', '#a78bfa', '#f97316', '#34d399']
const MAX_SELECT = 4
const ALIGN_ITEMS = [
  { key: 'epoch' as const, label: '按 Epoch' },
  { key: 'progress' as const, label: '按进度' },
]

const router = useRouter()
const toast = useToastStore()

const records = ref<TrainingRecord[]>([])
const loading = ref(false)
const selected = ref<number[]>([])
const runs = ref<CompareRun[]>([])
const align = ref<'epoch' | 'progress'>('epoch')
const comparing = ref(false)

const diagnosis = ref<DiagnosisResult | null>(null)
const diagnosisFor = ref<TrainingRecord | null>(null)
const diagnosing = ref(false)
const rerunning = ref<number | null>(null)

const lossRef = ref<HTMLElement | null>(null)
const accRef = ref<HTMLElement | null>(null)
let lossChart: ECharts | null = null
let accChart: ECharts | null = null

const canCompare = computed(() => selected.value.length >= 2)

function runLabel(run: CompareRun): string {
  const source = run.source === 'lab' ? '实验室' : '平台'
  return `#${run.id} ${source}`
}

function accuracyOf(record: TrainingRecord): string {
  const value = record.result_metrics?.final_accuracy
  return typeof value === 'number' ? value.toFixed(3) : '—'
}

function epochsOf(record: TrainingRecord): string {
  const value = record.result_metrics?.epochs
  return typeof value === 'number' ? String(value) : '—'
}

function sourceLabel(record: TrainingRecord): string {
  return record.source === 'lab' ? '实验室' : '平台'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const page = await listRecords(1, 50)
    records.value = page.items
    selected.value = selected.value.filter((id) =>
      page.items.some((item) => item.id === id),
    )
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function toggle(id: number): void {
  if (selected.value.includes(id)) {
    selected.value = selected.value.filter((item) => item !== id)
    return
  }
  if (selected.value.length >= MAX_SELECT) {
    toast.info(`最多同时对比 ${MAX_SELECT} 条记录`)
    return
  }
  selected.value = [...selected.value, id]
}

async function runCompare(): Promise<void> {
  if (!canCompare.value) return
  comparing.value = true
  try {
    const result = await compareRecords(selected.value)
    runs.value = result.runs
    await nextTick()
    renderCharts()
  } catch {
    // 拦截器已提示
  } finally {
    comparing.value = false
  }
}

function xOf(run: CompareRun, index: number, epoch: number | null): number {
  if (align.value === 'progress') {
    return ((index + 1) / Math.max(run.history.length, 1)) * 100
  }
  return epoch ?? index + 1
}

function renderCharts(): void {
  if (!lossRef.value || !accRef.value) return
  if (!lossChart) lossChart = echarts.init(lossRef.value)
  if (!accChart) accChart = echarts.init(accRef.value)

  const axisName = align.value === 'progress' ? '训练进度 (%)' : 'Epoch'

  const lossSeries = runs.value.flatMap((run, runIndex) => {
    const color = RUN_COLORS[runIndex % RUN_COLORS.length]
    const train = run.history
      .map((point, index) =>
        point.train_loss === null
          ? null
          : [xOf(run, index, point.epoch), point.train_loss],
      )
      .filter((item): item is [number, number] => item !== null)
    const val = run.history
      .map((point, index) =>
        point.val_loss === null
          ? null
          : [xOf(run, index, point.epoch), point.val_loss],
      )
      .filter((item): item is [number, number] => item !== null)

    return [
      {
        name: `${runLabel(run)} 训练`,
        type: 'line' as const,
        smooth: true,
        showSymbol: false,
        data: train,
        itemStyle: { color },
        lineStyle: { width: 1.6 },
      },
      {
        name: `${runLabel(run)} 验证`,
        type: 'line' as const,
        smooth: true,
        showSymbol: false,
        data: val,
        itemStyle: { color },
        lineStyle: { width: 1.6, type: 'dashed' as const },
      },
    ]
  })

  const accSeries = runs.value.map((run, runIndex) => ({
    name: runLabel(run),
    type: 'line' as const,
    smooth: true,
    showSymbol: false,
    data: run.history
      .map((point, index) =>
        point.accuracy === null
          ? null
          : [xOf(run, index, point.epoch), point.accuracy],
      )
      .filter((item): item is [number, number] => item !== null),
    itemStyle: { color: RUN_COLORS[runIndex % RUN_COLORS.length] },
    lineStyle: { width: 1.6 },
  }))

  const base = {
    backgroundColor: 'transparent',
    grid: { left: 48, right: 20, top: 46, bottom: 36 },
    tooltip: { trigger: 'axis' as const, confine: true },
    legend: {
      top: 4,
      left: 6,
      type: 'scroll' as const,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 8,
      textStyle: { color: '#94a3b8', fontSize: 10 },
    },
    xAxis: {
      type: 'value' as const,
      name: axisName,
      nameTextStyle: { color: '#94a3b8', fontSize: 10 },
      min: 0,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel: { color: '#94a3b8', fontSize: 9 },
    },
    yAxis: {
      type: 'value' as const,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: '#94a3b8', fontSize: 9 },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.1)' } },
    },
  }

  lossChart.setOption({ ...base, series: lossSeries }, true)
  accChart.setOption(
    {
      ...base,
      yAxis: { ...base.yAxis, min: 0, max: 1 },
      series: accSeries,
    },
    true,
  )
}

async function showDiagnosis(record: TrainingRecord): Promise<void> {
  diagnosing.value = true
  diagnosisFor.value = record
  try {
    diagnosis.value = await diagnoseRecord(record.id)
  } catch {
    diagnosis.value = null
  } finally {
    diagnosing.value = false
  }
}

function closeDiagnosis(): void {
  diagnosis.value = null
  diagnosisFor.value = null
}

async function onRerun(record: TrainingRecord): Promise<void> {
  rerunning.value = record.id
  try {
    const result = await rerunRecord(record.id)
    toast.success('已按原配置创建训练任务')
    void router.push(`/train/${result.task_id}`)
  } catch {
    // 拦截器已提示
  } finally {
    rerunning.value = null
  }
}

function severityColor(severity: string): string {
  if (severity === 'error') return 'var(--danger)'
  if (severity === 'warning') return 'var(--warning)'
  return 'var(--info)'
}

function setAlign(next: 'epoch' | 'progress'): void {
  align.value = next
  if (runs.value.length > 0) renderCharts()
}

function handleResize(): void {
  lossChart?.resize()
  accChart?.resize()
}

onMounted(() => {
  void load()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  lossChart?.dispose()
  accChart?.dispose()
  lossChart = null
  accChart = null
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
      <div class="flex items-center gap-3">
        <AppButton variant="ghost" size="sm" @click="router.push('/workspace')">
          ← 工作台
        </AppButton>
        <span class="text-sm font-medium text-primary">历史记录</span>
        <span class="text-[11px] text-muted">共 {{ records.length }} 条</span>
      </div>

      <div class="flex items-center gap-2">
        <div
          class="flex items-center gap-0.5 rounded-md border p-0.5"
          :style="{ borderColor: 'var(--border-default)' }"
        >
          <button
            v-for="item in ALIGN_ITEMS"
            :key="item.key"
            type="button"
            class="rounded-sm px-2.5 py-1 text-xs"
            :class="
              align === item.key
                ? 'text-primary'
                : 'text-muted hover:text-secondary'
            "
            :style="
              align === item.key ? { background: 'var(--bg-elevated)' } : {}
            "
            @click="setAlign(item.key)"
          >
            {{ item.label }}
          </button>
        </div>
        <AppButton variant="secondary" size="sm" @click="load">刷新</AppButton>
        <AppButton
          size="sm"
          :disabled="!canCompare"
          :loading="comparing"
          @click="runCompare"
        >
          对比选中（{{ selected.length }}）
        </AppButton>
      </div>
    </header>

    <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-4">
      <!-- 记录列表 -->
      <div
        class="min-h-0 flex-1 overflow-auto rounded-md border"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'var(--bg-surface)',
        }"
      >
        <table class="w-full text-left text-xs">
          <thead
            class="sticky top-0"
            :style="{ background: 'var(--bg-elevated)' }"
          >
            <tr class="text-muted">
              <th class="w-10 px-3 py-2">选</th>
              <th class="px-3 py-2">记录</th>
              <th class="px-3 py-2">来源</th>
              <th class="px-3 py-2">状态</th>
              <th class="px-3 py-2">轮次</th>
              <th class="px-3 py-2">准确率</th>
              <th class="px-3 py-2">时间</th>
              <th class="px-3 py-2 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="record in records"
              :key="record.id"
              class="border-t"
              :style="{ borderColor: 'var(--border-subtle)' }"
            >
              <td class="px-3 py-2">
                <input
                  type="checkbox"
                  :checked="selected.includes(record.id)"
                  class="accent-[var(--brand-cyan)]"
                  @change="toggle(record.id)"
                />
              </td>
              <td class="px-3 py-2 font-mono text-secondary">
                #{{ record.id }} · {{ record.task_id.slice(0, 8) }}
              </td>
              <td class="px-3 py-2 text-secondary">
                {{ sourceLabel(record) }}
              </td>
              <td class="px-3 py-2 text-secondary">{{ record.status }}</td>
              <td class="px-3 py-2 font-mono text-secondary">
                {{ epochsOf(record) }}
              </td>
              <td class="px-3 py-2 font-mono text-primary">
                {{ accuracyOf(record) }}
              </td>
              <td class="px-3 py-2 text-muted">
                {{ new Date(record.created_at).toLocaleString() }}
              </td>
              <td class="px-3 py-2 text-right">
                <div class="flex justify-end gap-1.5">
                  <AppButton
                    variant="secondary"
                    size="sm"
                    @click="router.push(`/history/${record.id}`)"
                  >
                    详情
                  </AppButton>
                  <AppButton
                    variant="secondary"
                    size="sm"
                    @click="showDiagnosis(record)"
                  >
                    诊断
                  </AppButton>
                  <AppButton
                    variant="secondary"
                    size="sm"
                    :loading="rerunning === record.id"
                    :disabled="record.dataset_id === null"
                    @click="onRerun(record)"
                  >
                    重跑
                  </AppButton>
                </div>
              </td>
            </tr>
            <tr v-if="records.length === 0">
              <td colspan="8" class="px-3 py-6 text-center text-muted">
                {{ loading ? '加载中…' : '还没有训练记录' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 对比图 -->
      <div
        v-if="runs.length > 0"
        class="grid h-[300px] shrink-0 grid-cols-2 gap-3"
      >
        <div
          class="rounded-md border p-2"
          :style="{
            borderColor: 'var(--border-subtle)',
            background: 'var(--bg-surface)',
          }"
        >
          <div ref="lossRef" class="h-full w-full" />
        </div>
        <div
          class="rounded-md border p-2"
          :style="{
            borderColor: 'var(--border-subtle)',
            background: 'var(--bg-surface)',
          }"
        >
          <div ref="accRef" class="h-full w-full" />
        </div>
      </div>
    </div>

    <!-- 诊断结果 -->
    <div
      v-if="diagnosisFor"
      class="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
      @click.self="closeDiagnosis"
    >
      <div
        class="w-full max-w-lg rounded-lg border p-4"
        :style="{
          borderColor: 'var(--border-default)',
          background: 'var(--bg-surface)',
        }"
      >
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-medium text-primary">
            记录 #{{ diagnosisFor.id }} 的曲线诊断
          </h3>
          <AppButton variant="ghost" size="sm" @click="closeDiagnosis">
            关闭
          </AppButton>
        </div>

        <p v-if="diagnosing" class="mt-4 text-xs text-muted">诊断中…</p>

        <template v-else-if="diagnosis">
          <p class="mt-3 text-xs text-secondary">{{ diagnosis.summary }}</p>

          <ul v-if="diagnosis.issues.length > 0" class="mt-3 space-y-2">
            <li
              v-for="issue in diagnosis.issues"
              :key="issue.code"
              class="rounded-md border p-2.5"
              :style="{ borderColor: 'var(--border-subtle)' }"
            >
              <p
                class="text-xs font-medium"
                :style="{ color: severityColor(issue.severity) }"
              >
                {{ issue.title }}
              </p>
              <p class="mt-1 text-[11px] leading-relaxed text-secondary">
                {{ issue.detail }}
              </p>
              <p class="mt-1 text-[11px] leading-relaxed text-muted">
                建议：{{ issue.suggestion }}
              </p>
            </li>
          </ul>

          <dl class="mt-3 grid grid-cols-2 gap-1 text-[11px]">
            <div class="flex justify-between">
              <dt class="text-muted">轮次</dt>
              <dd class="font-mono text-secondary">
                {{ diagnosis.stats.epochs }}
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-muted">末次训练 loss</dt>
              <dd class="font-mono text-secondary">
                {{ diagnosis.stats.last_train_loss?.toFixed(4) }}
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-muted">末次验证 loss</dt>
              <dd class="font-mono text-secondary">
                {{ diagnosis.stats.last_val_loss?.toFixed(4) }}
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-muted">train/val 差距</dt>
              <dd class="font-mono text-secondary">
                {{ diagnosis.stats.gap?.toFixed(4) }}
              </dd>
            </div>
          </dl>
        </template>
      </div>
    </div>
  </div>
</template>
