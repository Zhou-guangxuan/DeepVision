<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { uploadDataset } from '@/api/datasets'
import type { DatasetDetail } from '@/api/datasets'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import {
  countProcessedRows,
  parseCsv,
  profileColumns,
  type ColumnProfile,
  type MissingStrategy,
} from '@/utils/csv'

const MAX_BYTES = 50 * 1024 * 1024
const PREVIEW_ROWS = 10

const STRATEGIES: { value: MissingStrategy; label: string }[] = [
  { value: 'mean', label: '均值填充' },
  { value: 'median', label: '中位数填充' },
  { value: 'mode', label: '众数填充' },
  { value: 'drop', label: '删除含缺失的行' },
]

const dtypeLabel: Record<ColumnProfile['dtype'], string> = {
  number: '数值',
  category: '类别',
  date: '日期',
}

const dtypeBadge: Record<ColumnProfile['dtype'], string> = {
  number: 'dv-badge--success',
  category: 'dv-badge--neutral',
  date: 'dv-badge--warning',
}

const auth = useAuthStore()
const toast = useToastStore()
const router = useRouter()

const fileInput = ref<HTMLInputElement | null>(null)
const dragActive = ref(false)
const file = ref<File | null>(null)
const parsing = ref(false)
const parseError = ref('')

const headers = ref<string[]>([])
const rows = ref<string[][]>([])
const profiles = ref<ColumnProfile[]>([])

const featureColumns = ref<string[]>([])
const targetColumn = ref('')
const strategy = ref<MissingStrategy>('mean')

const submitting = ref(false)
const result = ref<DatasetDetail | null>(null)

const previewRows = computed(() => rows.value.slice(0, PREVIEW_ROWS))

const processedCount = computed(() => {
  if (rows.value.length === 0) return 0
  const selected = [...featureColumns.value, targetColumn.value].filter(Boolean)
  return countProcessedRows(rows.value, headers.value, selected, strategy.value)
})

const nonNumericWithMissing = computed(() => {
  const selected = [...featureColumns.value, targetColumn.value].filter(Boolean)
  return profiles.value.filter(
    (profile) =>
      selected.includes(profile.name) &&
      profile.dtype !== 'number' &&
      profile.missing > 0,
  )
})

const selectionError = computed(() => {
  if (headers.value.length === 0) return '请先选择 CSV 文件'
  if (featureColumns.value.length === 0) return '请至少选择一个特征列'
  if (!targetColumn.value) return '请选择目标列'
  if (featureColumns.value.includes(targetColumn.value)) {
    return '目标列不能同时作为特征列'
  }
  if (
    (strategy.value === 'mean' || strategy.value === 'median') &&
    nonNumericWithMissing.value.length > 0
  ) {
    return `列「${nonNumericWithMissing.value[0].name}」不是数值类型，无法用${
      strategy.value === 'mean' ? '均值' : '中位数'
    }填充`
  }
  return ''
})

function resetSelection(): void {
  file.value = null
  parseError.value = ''
  headers.value = []
  rows.value = []
  profiles.value = []
  featureColumns.value = []
  targetColumn.value = ''
  result.value = null
}

function pickFile(): void {
  fileInput.value?.click()
}

async function handleFile(picked: File | null | undefined): Promise<void> {
  if (!picked) return

  resetSelection()

  if (!picked.name.toLowerCase().endsWith('.csv')) {
    parseError.value = '仅支持 .csv 文件'
    return
  }
  if (picked.size > MAX_BYTES) {
    parseError.value = '文件超过 50MB 限制'
    return
  }
  if (picked.size === 0) {
    parseError.value = '文件内容为空'
    return
  }

  file.value = picked
  parsing.value = true
  try {
    const text = await picked.text()
    const parsed = parseCsv(text)
    if (parsed.headers.length === 0 || parsed.rows.length === 0) {
      parseError.value = '文件没有数据行'
      file.value = null
      return
    }

    headers.value = parsed.headers
    rows.value = parsed.rows
    profiles.value = profileColumns(parsed.headers, parsed.rows)

    // 默认：最后一列作为目标列，其余作为特征列
    targetColumn.value = parsed.headers[parsed.headers.length - 1] ?? ''
    featureColumns.value = parsed.headers.slice(0, -1)
  } catch {
    parseError.value = '文件读取失败，请确认是合法的 CSV'
    file.value = null
  } finally {
    parsing.value = false
  }
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  void handleFile(input.files?.[0])
  input.value = ''
}

function onDrop(event: DragEvent): void {
  dragActive.value = false
  void handleFile(event.dataTransfer?.files?.[0])
}

function toggleFeature(name: string): void {
  if (featureColumns.value.includes(name)) {
    featureColumns.value = featureColumns.value.filter((item) => item !== name)
  } else {
    featureColumns.value = [...featureColumns.value, name]
  }
}

function formatNumber(value: number | null): string {
  if (value === null) return '—'
  return Math.abs(value) >= 1000 ? value.toFixed(2) : value.toFixed(4)
}

async function onSubmit(): Promise<void> {
  if (!file.value || selectionError.value || submitting.value) return

  submitting.value = true
  try {
    const form = new FormData()
    form.append('file', file.value)
    form.append('feature_columns', JSON.stringify(featureColumns.value))
    form.append('target_column', targetColumn.value)
    form.append('missing_strategy', strategy.value)
    form.append('name', file.value.name)

    result.value = await uploadDataset(form)
    toast.success('数据集已解析并保存')
  } catch {
    // 错误已由 Axios 拦截器统一提示
  } finally {
    submitting.value = false
  }
}

function logout(): void {
  auth.logout()
  toast.info('已退出登录')
  void router.replace('/login')
}
</script>

<template>
  <div class="min-h-screen bg-base">
    <header
      class="flex h-16 items-center justify-between border-b px-5"
      :style="{
        borderColor: 'var(--border-subtle)',
        background: 'var(--bg-surface)',
      }"
    >
      <div class="flex items-center gap-3">
        <AppButton variant="ghost" size="sm" @click="router.push('/workspace')">
          ← 工作台
        </AppButton>
        <span class="text-sm font-medium text-primary">数据集上传</span>
        <span class="dv-badge dv-badge--neutral">阶段三</span>
      </div>
      <div class="flex items-center gap-3">
        <span class="hidden text-sm text-secondary sm:inline">
          {{ auth.user?.username ?? '已登录' }}
        </span>
        <AppButton variant="secondary" size="sm" @click="logout"
          >退出</AppButton
        >
      </div>
    </header>

    <main class="mx-auto w-full max-w-6xl px-6 py-8">
      <!-- 上传区 -->
      <div
        v-if="!file && !result"
        class="cursor-pointer rounded-lg border-2 border-dashed p-10 text-center transition-colors duration-base"
        :style="{
          borderColor: dragActive
            ? 'var(--brand-cyan)'
            : 'var(--border-default)',
          background: dragActive ? 'rgba(34, 211, 238, 0.06)' : 'transparent',
        }"
        @click="pickFile"
        @dragover.prevent="dragActive = true"
        @dragleave="dragActive = false"
        @drop.prevent="onDrop"
      >
        <input
          ref="fileInput"
          type="file"
          accept=".csv"
          class="hidden"
          @change="onFileChange"
        />
        <div class="flex flex-col items-center gap-3">
          <div
            class="grid h-12 w-12 place-items-center rounded-full border text-lg text-brand-cyan"
            :style="{ borderColor: 'var(--border-default)' }"
          >
            ↑
          </div>
          <p class="text-sm text-primary">
            拖拽 CSV 文件到这里，或<span class="text-brand-cyan">点击选择</span>
          </p>
          <p class="text-xs text-muted">仅支持 .csv，最大 50MB</p>
        </div>
      </div>

      <p v-if="parseError" class="mt-3 text-xs text-danger" role="alert">
        {{ parseError }}
      </p>

      <p v-if="parsing" class="mt-3 text-xs text-muted">正在解析文件…</p>

      <!-- 解析结果：预览 + 配置 -->
      <template v-if="file && !result">
        <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div class="flex items-center gap-2 text-sm text-secondary">
            <span class="text-primary">{{ file.name }}</span>
            <span class="text-muted">
              {{ rows.length }} 行 · {{ headers.length }} 列
            </span>
          </div>
          <AppButton variant="ghost" size="sm" @click="resetSelection">
            重新选择
          </AppButton>
        </div>

        <!-- 预览 -->
        <AppCard class="mt-4" padding="none">
          <div
            class="border-b px-4 py-3"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <h2 class="text-sm font-medium text-primary">
              数据预览（前 {{ Math.min(PREVIEW_ROWS, rows.length) }} 行）
            </h2>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs">
              <thead>
                <tr>
                  <th
                    v-for="header in headers"
                    :key="header"
                    class="whitespace-nowrap border-b px-3 py-2 font-medium text-secondary"
                    :style="{
                      borderColor: 'var(--border-subtle)',
                      background: 'var(--bg-elevated)',
                    }"
                  >
                    {{ header }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, rowIndex) in previewRows" :key="rowIndex">
                  <td
                    v-for="(header, columnIndex) in headers"
                    :key="`${rowIndex}-${header}`"
                    class="whitespace-nowrap border-b px-3 py-1.5 font-mono"
                    :style="{
                      borderColor: 'var(--border-subtle)',
                      color:
                        (row[columnIndex] ?? '').trim() === ''
                          ? 'var(--warning)'
                          : 'var(--text-secondary)',
                    }"
                  >
                    {{
                      (row[columnIndex] ?? '').trim() === ''
                        ? '（空）'
                        : row[columnIndex]
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </AppCard>

        <!-- 列角色 -->
        <AppCard class="mt-4" padding="none">
          <div
            class="border-b px-4 py-3"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <h2 class="text-sm font-medium text-primary">列角色</h2>
            <p class="mt-1 text-xs text-muted">
              勾选特征列，并选择一列作为目标标签
            </p>
          </div>
          <table class="w-full text-left text-xs">
            <thead>
              <tr>
                <th class="px-4 py-2 font-medium text-secondary">列名</th>
                <th class="px-4 py-2 font-medium text-secondary">类型</th>
                <th class="px-4 py-2 font-medium text-secondary">缺失</th>
                <th class="px-4 py-2 font-medium text-secondary">特征</th>
                <th class="px-4 py-2 font-medium text-secondary">目标</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="profile in profiles"
                :key="profile.name"
                class="border-t"
                :style="{ borderColor: 'var(--border-subtle)' }"
              >
                <td class="px-4 py-2 text-primary">{{ profile.name }}</td>
                <td class="px-4 py-2">
                  <span class="dv-badge" :class="dtypeBadge[profile.dtype]">
                    {{ dtypeLabel[profile.dtype] }}
                  </span>
                </td>
                <td class="px-4 py-2 text-muted">{{ profile.missing }}</td>
                <td class="px-4 py-2">
                  <input
                    type="checkbox"
                    class="h-3.5 w-3.5 accent-brand-cyan"
                    :checked="featureColumns.includes(profile.name)"
                    :aria-label="`把 ${profile.name} 设为特征列`"
                    @change="toggleFeature(profile.name)"
                  />
                </td>
                <td class="px-4 py-2">
                  <input
                    v-model="targetColumn"
                    type="radio"
                    class="h-3.5 w-3.5 accent-brand-cyan"
                    :value="profile.name"
                    :aria-label="`把 ${profile.name} 设为目标列`"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </AppCard>

        <!-- 缺失值处理 -->
        <AppCard class="mt-4">
          <h2 class="text-sm font-medium text-primary">缺失值处理</h2>
          <div class="mt-3 flex flex-wrap items-center gap-3">
            <select v-model="strategy" class="dv-select max-w-[220px]">
              <option
                v-for="item in STRATEGIES"
                :key="item.value"
                :value="item.value"
              >
                {{ item.label }}
              </option>
            </select>
            <span class="text-xs text-secondary">
              处理后样本数：
              <b class="font-mono text-primary">{{ processedCount }}</b>
              / {{ rows.length }}
            </span>
          </div>
          <p
            v-if="selectionError"
            class="mt-3 text-xs text-danger"
            role="alert"
          >
            {{ selectionError }}
          </p>
        </AppCard>

        <div class="mt-6 flex justify-end">
          <AppButton
            size="lg"
            :loading="submitting"
            :disabled="Boolean(selectionError)"
            @click="onSubmit"
          >
            解析并保存数据集
          </AppButton>
        </div>
      </template>

      <!-- 结果 -->
      <template v-if="result">
        <AppCard>
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold text-primary">数据集已保存</h2>
              <p class="mt-1 text-sm text-secondary">
                {{ result.name }} · 目标列
                <span class="font-mono text-primary">{{
                  result.target_column
                }}</span>
              </p>
            </div>
            <span class="dv-badge dv-badge--success">成功</span>
          </div>

          <div class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div
              v-for="item in [
                { label: '样本数', value: result.sample_count },
                { label: '特征数', value: result.feature_count },
                { label: '缺失策略', value: result.missing_strategy },
                { label: '数据集 ID', value: result.id },
              ]"
              :key="item.label"
              class="rounded-md border p-3"
              :style="{ borderColor: 'var(--border-subtle)' }"
            >
              <p class="text-[11px] text-muted">{{ item.label }}</p>
              <p class="mt-1 font-mono text-sm text-primary">
                {{ item.value }}
              </p>
            </div>
          </div>

          <!-- 后端返回的统计 -->
          <div class="mt-6">
            <h3 class="text-sm font-medium text-primary">
              特征统计（后端计算）
            </h3>
            <div class="mt-2 overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead>
                  <tr>
                    <th class="px-3 py-2 font-medium text-secondary">特征</th>
                    <th class="px-3 py-2 font-medium text-secondary">均值</th>
                    <th class="px-3 py-2 font-medium text-secondary">方差</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="feature in result.stats.features"
                    :key="feature.name"
                    class="border-t"
                    :style="{ borderColor: 'var(--border-subtle)' }"
                  >
                    <td class="px-3 py-2 text-primary">{{ feature.name }}</td>
                    <td class="px-3 py-2 font-mono text-secondary">
                      {{ formatNumber(feature.mean) }}
                    </td>
                    <td class="px-3 py-2 font-mono text-secondary">
                      {{ formatNumber(feature.variance) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="mt-6 flex flex-wrap justify-end gap-3">
            <AppButton variant="secondary" @click="resetSelection">
              上传另一个
            </AppButton>
            <AppButton @click="router.push('/workspace')">去搭建网络</AppButton>
          </div>
        </AppCard>
      </template>
    </main>
  </div>
</template>
