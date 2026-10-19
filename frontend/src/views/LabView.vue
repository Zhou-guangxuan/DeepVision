<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { streamChat } from '@/api/ai'
import {
  pauseLab,
  resumeLab,
  startLab,
  stopLab,
  type LabActivation,
  type LabConfig,
  type LabInit,
  type LabOptimizer,
} from '@/api/lab'
import LabDashboard from '@/components/lab/LabDashboard.vue'
import LabNetwork3D from '@/components/lab/LabNetwork3D.vue'
import AppButton from '@/components/ui/AppButton.vue'
import {
  useLabSocket,
  type LabBoundaryEvent,
  type LabEpochEvent,
  type LabEvent,
  type LabWeightsEvent,
} from '@/composables/useLabSocket'
import { useToastStore } from '@/stores/toast'

type LabStatus =
  | 'idle'
  | 'running'
  | 'paused'
  | 'completed'
  | 'stopped'
  | 'failed'

const STATUS_TEXT: Record<LabStatus, string> = {
  idle: 'idle',
  running: 'running',
  paused: 'paused',
  completed: 'completed',
  stopped: 'stopped',
  failed: 'failed',
}

const NAV_ITEMS = ['训练/求解器', '前向/反向传播', '注意力 3D', '降维投影']

const router = useRouter()
const toast = useToastStore()

const hiddenLayers = ref<number[]>([8, 8])
const activation = ref<LabActivation>('relu')
const init = ref<LabInit>('he')
const optimizer = ref<LabOptimizer>('adam')
const learningRate = ref(0.05)
const batchSize = ref(32)
const epochs = ref(60)
const l2 = ref(0)
const dropout = ref(0)

const resetToken = ref(0)
const status = ref<LabStatus>('idle')
const socketState = ref<'connecting' | 'open' | 'closed'>('closed')
const taskId = ref<string | null>(null)
const serverParamCount = ref<number | null>(null)

const history = ref<LabEpochEvent[]>([])
const latest = ref<LabEpochEvent | null>(null)
const weights = ref<LabWeightsEvent | null>(null)
const boundary = ref<LabBoundaryEvent | null>(null)

const question = ref('')
const answer = ref('')
const sources = ref<string[]>([])
const asking = ref(false)
const answerMs = ref(0)
const engine = ref<'auto' | 'offline'>('auto')

const layers = computed(() => [2, ...hiddenLayers.value, 2])

const structureText = computed(() => layers.value.join(' → '))

const parameterCount = computed(() => {
  let previous = 2
  let total = 0
  for (const units of hiddenLayers.value) {
    total += previous * units + units
    previous = units
  }
  total += previous * 2 + 2
  return total
})

const displayParamCount = computed(
  () => serverParamCount.value ?? parameterCount.value,
)

const config = computed<LabConfig>(() => ({
  hidden_layers: hiddenLayers.value,
  activation: activation.value,
  init: init.value,
  optimizer: optimizer.value,
  learning_rate: learningRate.value,
  batch_size: batchSize.value,
  epochs: epochs.value,
  l2: l2.value,
  dropout: dropout.value,
}))

const socket = useLabSocket(onLabEvent, (state) => {
  socketState.value = state
})

function onLabEvent(event: LabEvent): void {
  switch (event.type) {
    case 'started':
      status.value = 'running'
      serverParamCount.value = event.parameter_count
      break
    case 'epoch':
      history.value = [...history.value, event]
      latest.value = event
      break
    case 'weights':
      weights.value = event
      break
    case 'boundary':
      boundary.value = event
      break
    case 'paused':
      status.value = 'paused'
      break
    case 'resumed':
      status.value = 'running'
      break
    case 'stopping':
      break
    case 'completed':
      status.value = 'completed'
      toast.success('训练完成')
      break
    case 'stopped':
      status.value = 'stopped'
      toast.info('训练已停止')
      break
    case 'failed':
      status.value = 'failed'
      toast.error(event.reason)
      break
  }
}

function addLayer(): void {
  if (hiddenLayers.value.length >= 4) {
    toast.info('最多 4 个隐藏层')
    return
  }
  hiddenLayers.value = [...hiddenLayers.value, 8]
}

function removeLayer(): void {
  if (hiddenLayers.value.length <= 1) {
    toast.info('至少保留 1 个隐藏层')
    return
  }
  hiddenLayers.value = hiddenLayers.value.slice(0, -1)
}

function rebuild(): void {
  history.value = []
  latest.value = null
  weights.value = null
  boundary.value = null
  serverParamCount.value = null
  status.value = 'idle'
  resetToken.value += 1
  toast.info('模型已重建')
}

async function onStart(): Promise<void> {
  if (status.value === 'running' || status.value === 'paused') {
    toast.info('当前已有训练在进行')
    return
  }

  history.value = []
  latest.value = null
  weights.value = null
  boundary.value = null

  try {
    const result = await startLab(config.value)
    taskId.value = result.task_id
    serverParamCount.value = result.parameter_count
    socket.connect(result.task_id)
  } catch {
    // 拦截器已提示
  }
}

async function onPause(): Promise<void> {
  if (!taskId.value || status.value !== 'running') return
  await pauseLab(taskId.value)
}

async function onResume(): Promise<void> {
  if (!taskId.value || status.value !== 'paused') return
  await resumeLab(taskId.value)
}

async function onStop(): Promise<void> {
  if (!taskId.value) return
  await stopLab(taskId.value)
}

async function ask(text?: string): Promise<void> {
  const content = (text ?? question.value).trim()
  if (!content || asking.value) return

  question.value = content
  answer.value = ''
  sources.value = []
  asking.value = true
  const started = performance.now()

  try {
    await streamChat(content, (event) => {
      if (event.type === 'delta' && event.text) answer.value += event.text
      if (event.type === 'done') sources.value = event.sources ?? []
    })
  } catch (error) {
    answer.value =
      answer.value ||
      (error instanceof Error ? error.message : '助教暂时不可用')
  } finally {
    answerMs.value = Math.round(performance.now() - started)
    asking.value = false
  }
}

function diagnoseTraining(): void {
  const current = latest.value
  const context = current
    ? `当前 ${structureText.value}，epoch ${current.epoch}/${current.total_epochs}，` +
      `训练 loss ${current.train_loss.toFixed(4)}，验证 loss ${current.val_loss.toFixed(4)}，` +
      `验证准确率 ${current.accuracy.toFixed(3)}。`
    : `当前 ${structureText.value}，尚未开始训练。`
  void ask(`${context}请诊断当前训练状态并给出调参建议。`)
}
</script>

<template>
  <div class="flex h-screen flex-col overflow-hidden bg-base">
    <!-- 顶栏 -->
    <header
      class="flex h-14 shrink-0 items-center justify-between border-b px-4"
      :style="{
        borderColor: 'var(--border-subtle)',
        background: 'var(--bg-surface)',
      }"
    >
      <div class="flex items-center gap-3">
        <span
          class="grid h-7 w-7 place-items-center rounded-md text-xs font-bold text-[#04070f]"
          style="background-image: var(--brand-gradient)"
        >
          L
        </span>
        <span class="text-sm font-semibold text-primary">教学实验室</span>
        <span class="dv-badge dv-badge--neutral">第二大阶段</span>

        <nav class="ml-4 hidden items-center gap-1 lg:flex">
          <span
            v-for="item in NAV_ITEMS"
            :key="item"
            class="cursor-not-allowed rounded-sm px-2 py-1 text-[11px] text-muted"
            :title="`${item}（后续批次实现）`"
          >
            {{ item }}
          </span>
        </nav>
      </div>

      <div class="flex items-center gap-3 text-[11px] text-muted">
        <span>引擎 PyTorch · CPU</span>
        <span
          class="dv-badge"
          :class="
            status === 'running'
              ? 'dv-badge--warning'
              : status === 'completed'
                ? 'dv-badge--success'
                : status === 'failed'
                  ? 'dv-badge--danger'
                  : 'dv-badge--neutral'
          "
        >
          {{ STATUS_TEXT[status] }}
        </span>
        <AppButton variant="ghost" size="sm" @click="router.push('/workspace')">
          返回工作台
        </AppButton>
      </div>
    </header>

    <div class="flex min-h-0 flex-1">
      <!-- 左：参数控制 -->
      <aside
        class="flex w-[300px] shrink-0 flex-col overflow-y-auto border-r p-3"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'var(--bg-surface)',
        }"
      >
        <section class="space-y-2">
          <div
            v-for="(units, index) in hiddenLayers"
            :key="index"
            class="rounded-md border p-2"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <div class="flex items-center justify-between">
              <span class="text-[11px] text-secondary">
                第 {{ index + 1 }} 层神经元
              </span>
              <span class="font-mono text-xs text-primary">{{ units }}</span>
            </div>
            <input
              v-model.number="hiddenLayers[index]"
              type="range"
              min="1"
              max="64"
              step="1"
              class="mt-1.5 w-full accent-[var(--brand-cyan)]"
            />
          </div>

          <div class="flex gap-2">
            <AppButton variant="secondary" size="sm" class="flex-1" @click="addLayer">
              + 隐藏层
            </AppButton>
            <AppButton variant="secondary" size="sm" class="flex-1" @click="removeLayer">
              − 隐藏层
            </AppButton>
          </div>

          <div>
            <label class="mb-1 block text-[11px] text-secondary">激活函数</label>
            <select v-model="activation" class="dv-select h-9 text-xs">
              <option value="relu">ReLU</option>
              <option value="tanh">Tanh</option>
              <option value="sigmoid">Sigmoid</option>
            </select>
          </div>

          <div>
            <label class="mb-1 block text-[11px] text-secondary">初始化</label>
            <select v-model="init" class="dv-select h-9 text-xs">
              <option value="he">He 正态</option>
              <option value="xavier">Xavier</option>
              <option value="uniform">均匀分布</option>
            </select>
          </div>

          <p class="rounded-md px-2 py-1.5 text-center font-mono text-[11px] text-secondary"
             :style="{ background: 'var(--bg-elevated)' }">
            {{ structureText }}
          </p>
        </section>

        <div class="my-3 h-px" :style="{ background: 'var(--border-subtle)' }" />

        <section class="space-y-2.5">
          <p class="text-[11px] font-medium text-secondary">训练超参</p>

          <div>
            <label class="mb-1 block text-[11px] text-secondary">优化器</label>
            <select v-model="optimizer" class="dv-select h-9 text-xs">
              <option value="adam">Adam</option>
              <option value="sgd">SGD</option>
            </select>
          </div>

          <div>
            <div class="flex justify-between text-[11px] text-secondary">
              <span>学习率</span>
              <span class="font-mono text-primary">{{ learningRate.toFixed(3) }}</span>
            </div>
            <input
              v-model.number="learningRate"
              type="range"
              min="0.001"
              max="0.2"
              step="0.001"
              class="mt-1 w-full accent-[var(--brand-cyan)]"
            />
          </div>

          <div>
            <div class="flex justify-between text-[11px] text-secondary">
              <span>批大小</span>
              <span class="font-mono text-primary">{{ batchSize }}</span>
            </div>
            <input
              v-model.number="batchSize"
              type="range"
              min="8"
              max="256"
              step="8"
              class="mt-1 w-full accent-[var(--brand-cyan)]"
            />
          </div>

          <div>
            <div class="flex justify-between text-[11px] text-secondary">
              <span>训练轮数</span>
              <span class="font-mono text-primary">{{ epochs }}</span>
            </div>
            <input
              v-model.number="epochs"
              type="range"
              min="1"
              max="200"
              step="1"
              class="mt-1 w-full accent-[var(--brand-cyan)]"
            />
          </div>

          <div>
            <div class="flex justify-between text-[11px] text-secondary">
              <span>L2 正则</span>
              <span class="font-mono text-primary">{{ l2.toFixed(3) }}</span>
            </div>
            <input
              v-model.number="l2"
              type="range"
              min="0"
              max="0.1"
              step="0.001"
              class="mt-1 w-full accent-[var(--brand-cyan)]"
            />
          </div>

          <div>
            <div class="flex justify-between text-[11px] text-secondary">
              <span>Dropout</span>
              <span class="font-mono text-primary">{{ dropout.toFixed(2) }}</span>
            </div>
            <input
              v-model.number="dropout"
              type="range"
              min="0"
              max="0.5"
              step="0.01"
              class="mt-1 w-full accent-[var(--brand-cyan)]"
            />
          </div>
        </section>

        <div class="my-3 h-px" :style="{ background: 'var(--border-subtle)' }" />

        <section class="space-y-2">
          <AppButton block size="sm" @click="rebuild">构建 / 重建模型</AppButton>
          <div class="flex gap-2">
            <AppButton
              class="flex-1"
              size="sm"
              :disabled="status === 'running' || status === 'paused'"
              @click="onStart"
            >
              开始训练
            </AppButton>
            <AppButton
              variant="secondary"
              class="flex-1"
              size="sm"
              :disabled="status !== 'running'"
              @click="onPause"
            >
              暂停
            </AppButton>
          </div>
          <div class="flex gap-2">
            <AppButton
              variant="secondary"
              class="flex-1"
              size="sm"
              :disabled="status !== 'paused'"
              @click="onResume"
            >
              恢复
            </AppButton>
            <AppButton
              variant="danger"
              class="flex-1"
              size="sm"
              :disabled="status !== 'running' && status !== 'paused'"
              @click="onStop"
            >
              停止
            </AppButton>
          </div>
          <AppButton variant="ghost" size="sm" block @click="resetToken += 1">
            重置视角
          </AppButton>
          <p class="text-[10px] leading-relaxed text-muted">
            绿灯表示模型已就绪，可直接「开始训练」；训练数据为内置双螺旋（1400 / 600）。
          </p>
        </section>
      </aside>

      <!-- 中：3D + 仪表盘 -->
      <main class="flex min-w-0 flex-1 flex-col">
        <div class="relative min-h-0 flex-1">
          <LabNetwork3D
            :layers="layers"
            :activation="activation"
            :reset-token="resetToken"
          />
          <p
            class="pointer-events-none absolute right-3 top-3 text-[10px] text-muted"
          >
            socket: {{ socketState }} · 参数量 {{ displayParamCount }}
          </p>
        </div>

        <div
          class="h-[268px] shrink-0 border-t p-2"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <LabDashboard
            :history="history"
            :latest="latest"
            :weights="weights"
            :boundary="boundary"
          />
        </div>
      </main>

      <!-- 右：解析 / 助教 -->
      <aside
        class="flex w-[360px] shrink-0 flex-col border-l"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'var(--bg-surface)',
        }"
      >
        <div
          class="flex h-10 shrink-0 items-center border-b px-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <span class="text-xs font-medium text-primary">解析 / 助教</span>
        </div>

        <div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
          <div>
            <label class="mb-1 block text-[11px] text-secondary">模型引擎</label>
            <select v-model="engine" class="dv-select h-9 text-xs">
              <option value="auto">自动（有 Key 走大模型）</option>
              <option value="offline">离线规则</option>
            </select>
            <p class="mt-1 text-[10px] text-muted">
              当前由后端配置决定；未配置 Key 时自动使用内置知识库。
            </p>
          </div>

          <div class="grid grid-cols-2 gap-2">
            <AppButton variant="secondary" size="sm" @click="diagnoseTraining">
              诊断训练状态
            </AppButton>
            <AppButton
              variant="secondary"
              size="sm"
              @click="ask('我该怎么调参？请结合当前网络结构和训练指标说明。')"
            >
              我该怎么调参
            </AppButton>
            <AppButton
              variant="secondary"
              size="sm"
              @click="ask('请解释注意力机制的作用。')"
            >
              解释注意力
            </AppButton>
            <AppButton
              variant="secondary"
              size="sm"
              @click="ask('为什么加深网络有用？')"
            >
              为什么加深有用
            </AppButton>
          </div>

          <textarea
            v-model="question"
            rows="2"
            class="w-full resize-none rounded-sm border bg-transparent px-2 py-1.5 text-xs text-primary outline-none"
            :style="{
              borderColor: 'var(--border-default)',
              background: 'var(--bg-base)',
            }"
            placeholder="问点什么，例如：请解释当前训练状态"
          />

          <AppButton block size="sm" :loading="asking" @click="ask()">
            生成解析
          </AppButton>

          <div
            v-if="answer || asking"
            class="rounded-md border p-2"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <p class="text-[10px] text-muted">
              来源：offline（未配置大模型 Key） · {{ answerMs }} ms
            </p>
            <p class="mt-1.5 whitespace-pre-wrap text-[11px] leading-relaxed text-secondary">
              {{ answer }}<span v-if="asking">▌</span>
            </p>
            <div v-if="sources.length > 0" class="mt-2 border-t pt-1.5"
                 :style="{ borderColor: 'var(--border-subtle)' }">
              <p class="text-[10px] text-muted">参考来源</p>
              <p v-for="source in sources" :key="source" class="text-[10px] text-muted">
                · {{ source }}
              </p>
            </div>
          </div>

          <div class="rounded-md border p-2" :style="{ borderColor: 'var(--border-subtle)' }">
            <p class="text-[11px] font-medium text-secondary">实时指标</p>
            <dl class="mt-1.5 space-y-1 text-[11px]">
              <div class="flex justify-between">
                <dt class="text-muted">数据集</dt>
                <dd class="text-secondary">双螺旋 · 1400 / 600</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">网络结构</dt>
                <dd class="font-mono text-secondary">{{ structureText }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">激活函数</dt>
                <dd class="text-secondary">{{ activation }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">参数量</dt>
                <dd class="font-mono text-secondary">{{ displayParamCount }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">优化器</dt>
                <dd class="text-secondary">{{ optimizer }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">当前学习率</dt>
                <dd class="font-mono text-secondary">{{ learningRate.toFixed(4) }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">会话状态</dt>
                <dd class="text-secondary">{{ STATUS_TEXT[status] }}</dd>
              </div>
            </dl>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
