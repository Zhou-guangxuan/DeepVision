<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

import { streamChat } from '@/api/ai'
import {
  diagnoseLab,
  pauseLab,
  resumeLab,
  startLab,
  stopLab,
  type LabActivation,
  type LabConfig,
  type LabDiagnosis,
  type LabInit,
  type LabOptimizer,
} from '@/api/lab'
import LabDashboard from '@/components/lab/LabDashboard.vue'
import LabInspector from '@/components/lab/LabInspector.vue'
import LabNetwork3D from '@/components/lab/LabNetwork3D.vue'
import AppButton from '@/components/ui/AppButton.vue'
import {
  useLabSocket,
  type LabBoundaryEvent,
  type LabEpochEvent,
  type LabEvent,
  type LabWeightsEvent,
} from '@/composables/useLabSocket'
import { TEACHING_TASKS, type TeachingTask } from '@/data/teachingTasks'
import { useToastStore } from '@/stores/toast'

type LabStatus =
  'idle' | 'running' | 'paused' | 'completed' | 'stopped' | 'failed'

const STATUS_TEXT: Record<LabStatus, string> = {
  idle: 'idle',
  running: 'running',
  paused: 'paused',
  completed: 'completed',
  stopped: 'stopped',
  failed: 'failed',
}

type InspectorTab = 'propagation' | 'attention' | 'trend' | 'projection'

const NAV_ITEMS: {
  label: string
  tab: InspectorTab
}[] = [
  { label: '前向/反向传播', tab: 'propagation' },
  { label: '注意力 3D', tab: 'attention' },
  { label: '注意力曲线', tab: 'trend' },
  { label: '降维投影', tab: 'projection' },
]

const router = useRouter()
const toast = useToastStore()

const hiddenLayers = ref<number[]>([8, 8])
/** 输入神经元数（= 特征维度） */
const inputUnits = ref(2)
/** 输出类别数 */
const outputUnits = ref(2)
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
const answerMode = ref<'llm' | 'fallback' | ''>('')
const answerNote = ref('')
const engine = ref<'auto' | 'llm' | 'offline'>('auto')
const inspectorOpen = ref(false)
const inspectorTab = ref<InspectorTab>('propagation')
/** 输入特征注意力，用于在 3D 中高亮输入层 */
const saliency = ref<number[]>([])

// ---- 教学任务（P1）----
const taskPanelOpen = ref(false)
const currentTask = ref<TeachingTask | null>(null)
const taskResult = ref<{
  passed: boolean
  reason: string
  diagnosis: LabDiagnosis | null
} | null>(null)
const checkpointAnswers = ref<Record<number, number>>({})
const evaluating = ref(false)
const previousSummary = ref<{
  label: string
  accuracy: number
  loss: number
  epochs: number
} | null>(null)

const renderedAnswer = computed(() => {
  if (!answer.value) return ''
  const html = marked.parse(answer.value, { async: false }) as string
  return DOMPurify.sanitize(html)
})

function openInspector(tab: InspectorTab): void {
  inspectorTab.value = tab
  inspectorOpen.value = true
}

/** 应用教学任务预设 */
function applyTask(task: TeachingTask): void {
  const preset = task.preset
  inputUnits.value = preset.inputUnits
  outputUnits.value = preset.outputUnits
  hiddenLayers.value = [...preset.hiddenLayers]
  activation.value = preset.activation
  init.value = preset.init
  optimizer.value = preset.optimizer
  learningRate.value = preset.learningRate
  batchSize.value = preset.batchSize
  epochs.value = preset.epochs
  l2.value = preset.l2
  dropout.value = preset.dropout

  currentTask.value = task
  taskResult.value = null
  checkpointAnswers.value = {}
  previousSummary.value = null
  taskPanelOpen.value = false
  resetToken.value += 1
  toast.info(`已应用：${task.title}`)
}

/** 训练结束后判定是否达成教学目标 */
async function evaluateTask(): Promise<void> {
  const task = currentTask.value
  if (!task) return

  evaluating.value = true
  try {
    const diagnosis = taskId.value ? await diagnoseLab(taskId.value) : null
    const rule = task.success

    let passed = false
    let reason = ''
    if (rule.metric === 'accuracy') {
      const accuracy = latest.value?.accuracy ?? 0
      passed = accuracy >= rule.threshold
      reason = `最终验证准确率 ${accuracy.toFixed(3)}，目标 ≥ ${rule.threshold}`
    } else {
      const hit = diagnosis?.issues.find((issue) =>
        rule.codes.includes(issue.code),
      )
      passed = Boolean(hit)
      reason = hit
        ? `出现了预期现象：${hit.title}`
        : '没有出现预期的异常现象，可以按提示调整后再试一次'
    }

    taskResult.value = { passed, reason, diagnosis }
  } finally {
    evaluating.value = false
  }
}

function answerCheckpoint(index: number, option: number): void {
  checkpointAnswers.value = { ...checkpointAnswers.value, [index]: option }
}

/** 保存本组结果，清空曲线，准备跑第二组做对比 */
function prepareComparison(): void {
  const current = latest.value
  if (!current || !currentTask.value) return

  previousSummary.value = {
    label: currentTask.value.title,
    accuracy: current.accuracy,
    loss: current.val_loss,
    epochs: current.epoch,
  }
  history.value = []
  latest.value = null
  weights.value = null
  boundary.value = null
  status.value = 'idle'
  taskResult.value = null
  checkpointAnswers.value = {}
  toast.info('已记录本组结果，调整参数后可再跑一组')
}

function closeTaskResult(): void {
  taskResult.value = null
}

/** 任务预设的结构摘要，例如 2 → 8 → 8 → 2 */
function presetSummary(task: TeachingTask): string {
  return [
    task.preset.inputUnits,
    ...task.preset.hiddenLayers,
    task.preset.outputUnits,
  ].join(' → ')
}

function successText(task: TeachingTask): string {
  const rule = task.success
  if (rule.metric === 'accuracy') {
    return `验证准确率 ≥ ${rule.threshold}`
  }
  return '训练曲线出现预期异常（由诊断规则自动判定）'
}

const layers = computed(() => [
  inputUnits.value,
  ...hiddenLayers.value,
  outputUnits.value,
])

const structureText = computed(() => layers.value.join(' → '))

const parameterCount = computed(() => {
  let previous = inputUnits.value
  let total = 0
  for (const units of hiddenLayers.value) {
    total += previous * units + units
    previous = units
  }
  total += previous * outputUnits.value + outputUnits.value
  return total
})

const displayParamCount = computed(
  () => serverParamCount.value ?? parameterCount.value,
)

const config = computed<LabConfig>(() => ({
  input_units: inputUnits.value,
  output_units: outputUnits.value,
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
      if (currentTask.value) void evaluateTask()
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
  answerMode.value = ''
  answerNote.value = ''
  asking.value = true
  const started = performance.now()

  try {
    await streamChat(
      content,
      (event) => {
        if (event.type === 'meta') {
          answerMode.value = event.mode === 'llm' ? 'llm' : 'fallback'
          if (event.reason) answerNote.value = String(event.reason)
        }
        if (event.type === 'delta' && event.text) answer.value += event.text
        if (event.type === 'done') sources.value = event.sources ?? []
      },
      undefined,
      engine.value,
    )
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
        <span v-if="currentTask" class="text-[11px] text-muted">
          任务：{{ currentTask.title }}
        </span>

        <nav class="ml-4 hidden items-center gap-1 lg:flex">
          <button
            v-for="item in NAV_ITEMS"
            :key="item.label"
            type="button"
            class="rounded-sm px-2 py-1 text-[11px] text-muted transition-colors duration-fast hover:text-primary"
            :title="`打开「${item.label}」`"
            @click="openInspector(item.tab)"
          >
            {{ item.label }}
          </button>
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
        <AppButton variant="secondary" size="sm" @click="taskPanelOpen = true">
          实验任务
        </AppButton>
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
            class="rounded-md border p-2"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <div class="flex items-center justify-between">
              <span class="text-[11px] text-secondary">输入神经元</span>
              <span class="font-mono text-xs text-primary">
                {{ inputUnits }}
              </span>
            </div>
            <input
              v-model.number="inputUnits"
              type="range"
              min="1"
              max="8"
              step="1"
              class="mt-1.5 w-full accent-[var(--brand-cyan)]"
            />
            <p class="mt-1 text-[10px] text-muted">
              即特征维度，超出 2 维的部分为噪声
            </p>
          </div>

          <div
            class="rounded-md border p-2"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <div class="flex items-center justify-between">
              <span class="text-[11px] text-secondary">输出类别数</span>
              <span class="font-mono text-xs text-primary">
                {{ outputUnits }}
              </span>
            </div>
            <input
              v-model.number="outputUnits"
              type="range"
              min="2"
              max="6"
              step="1"
              class="mt-1.5 w-full accent-[var(--brand-cyan)]"
            />
            <p class="mt-1 text-[10px] text-muted">
              2 类为螺旋，3 类以上为环形分布
            </p>
          </div>

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
            <AppButton
              variant="secondary"
              size="sm"
              class="flex-1"
              @click="addLayer"
            >
              + 隐藏层
            </AppButton>
            <AppButton
              variant="secondary"
              size="sm"
              class="flex-1"
              @click="removeLayer"
            >
              − 隐藏层
            </AppButton>
          </div>

          <div>
            <label class="mb-1 block text-[11px] text-secondary"
              >激活函数</label
            >
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

          <p
            class="rounded-md px-2 py-1.5 text-center font-mono text-[11px] text-secondary"
            :style="{ background: 'var(--bg-elevated)' }"
          >
            {{ structureText }}
          </p>
        </section>

        <div
          class="my-3 h-px"
          :style="{ background: 'var(--border-subtle)' }"
        />

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
              <span class="font-mono text-primary">{{
                learningRate.toFixed(3)
              }}</span>
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
              <span class="font-mono text-primary">{{
                dropout.toFixed(2)
              }}</span>
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

        <div
          class="my-3 h-px"
          :style="{ background: 'var(--border-subtle)' }"
        />

        <section class="space-y-2">
          <AppButton block size="sm" @click="rebuild"
            >构建 / 重建模型</AppButton
          >
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
            绿灯表示模型已就绪，可直接「开始训练」；训练数据按输入维度与类别数自动生成（1400
            / 600）。
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
            :highlight="saliency"
            :active="status === 'running'"
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
            <label class="mb-1 block text-[11px] text-secondary"
              >模型引擎</label
            >
            <select v-model="engine" class="dv-select h-9 text-xs">
              <option value="auto">自动（有 Key 走大模型）</option>
              <option value="llm">强制大模型</option>
              <option value="offline">离线规则</option>
            </select>
            <p class="mt-1 text-[10px] text-muted">
              「强制大模型」在未配置 Key 时会提示并降级为内置知识库。
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
              来源：{{ answerMode === 'llm' ? '大模型' : '内置知识库' }} ·
              {{ answerMs }} ms
              <span v-if="answerNote"> · {{ answerNote }}</span>
            </p>
            <div
              class="markdown mt-1.5 text-[11px] leading-relaxed text-secondary"
              v-html="renderedAnswer"
            />
            <span v-if="asking" class="text-[11px] text-secondary">▌</span>
            <div
              v-if="sources.length > 0"
              class="mt-2 border-t pt-1.5"
              :style="{ borderColor: 'var(--border-subtle)' }"
            >
              <p class="text-[10px] text-muted">参考来源</p>
              <p
                v-for="source in sources"
                :key="source"
                class="text-[10px] text-muted"
              >
                · {{ source }}
              </p>
            </div>
          </div>

          <div
            class="rounded-md border p-2"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <p class="text-[11px] font-medium text-secondary">实时指标</p>
            <dl class="mt-1.5 space-y-1 text-[11px]">
              <div class="flex justify-between">
                <dt class="text-muted">数据集</dt>
                <dd class="text-secondary">
                  {{ outputUnits === 2 ? '双螺旋' : '多类环形' }} ·
                  {{ inputUnits }} 维 · 1400 / 600
                </dd>
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
                <dd class="font-mono text-secondary">
                  {{ displayParamCount }}
                </dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">优化器</dt>
                <dd class="text-secondary">{{ optimizer }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">当前学习率</dt>
                <dd class="font-mono text-secondary">
                  {{ learningRate.toFixed(4) }}
                </dd>
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

    <LabInspector
      :open="inspectorOpen"
      :task-id="taskId"
      :layers="layers"
      :initial-tab="inspectorTab"
      @saliency="saliency = $event"
      @close="inspectorOpen = false"
    />

    <!-- 实验任务 -->
    <div
      v-if="taskPanelOpen"
      class="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
      @click.self="taskPanelOpen = false"
    >
      <div
        class="flex max-h-[86vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg border"
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
            <h3 class="text-sm font-medium text-primary">实验任务</h3>
            <p class="mt-0.5 text-[11px] text-muted">
              选择任务会自动填好参数，训练结束后检查是否达成目标
            </p>
          </div>
          <AppButton variant="ghost" size="sm" @click="taskPanelOpen = false">
            关闭
          </AppButton>
        </header>

        <div class="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
          <div
            v-for="task in TEACHING_TASKS"
            :key="task.id"
            class="rounded-md border p-3"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium text-primary">
                    {{ task.title }}
                  </span>
                  <span
                    class="rounded-sm px-1.5 py-0.5 text-[10px]"
                    :style="{
                      color:
                        task.kind === 'goal'
                          ? 'var(--success)'
                          : 'var(--warning)',
                      background:
                        task.kind === 'goal'
                          ? 'rgba(52, 211, 153, 0.12)'
                          : 'rgba(251, 191, 36, 0.12)',
                    }"
                  >
                    {{ task.kind === 'goal' ? '目标' : '错误示范' }}
                  </span>
                </div>
                <p class="mt-1 text-[11px] leading-relaxed text-secondary">
                  {{ task.goal }}
                </p>
                <p class="mt-1 text-[11px] leading-relaxed text-muted">
                  {{ task.hint }}
                </p>
                <p class="mt-1.5 font-mono text-[10px] text-muted">
                  预设 {{ presetSummary(task) }} · lr
                  {{ task.preset.learningRate }} · {{ task.preset.epochs }} 轮 ·
                  达标条件：{{ successText(task) }}
                </p>
              </div>
              <AppButton
                size="sm"
                :disabled="status === 'running' || status === 'paused'"
                @click="applyTask(task)"
              >
                应用
              </AppButton>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 任务结果与检查点 -->
    <div
      v-if="taskResult && currentTask"
      class="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
      @click.self="closeTaskResult"
    >
      <div
        class="flex max-h-[86vh] w-full max-w-xl flex-col overflow-hidden rounded-lg border"
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
              {{ currentTask.title }}
            </h3>
            <p class="mt-0.5 text-[11px] text-muted">{{ currentTask.goal }}</p>
          </div>
          <span
            class="rounded-sm px-2 py-1 text-[11px]"
            :style="{
              color: taskResult.passed ? 'var(--success)' : 'var(--warning)',
              background: taskResult.passed
                ? 'rgba(52, 211, 153, 0.12)'
                : 'rgba(251, 191, 36, 0.12)',
            }"
          >
            {{ taskResult.passed ? '已达成目标' : '未达成，可再试' }}
          </span>
        </header>

        <div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          <p class="text-[11px] text-secondary">{{ taskResult.reason }}</p>

          <p v-if="evaluating" class="text-[11px] text-muted">
            正在诊断训练曲线…
          </p>

          <div
            v-if="taskResult.diagnosis"
            class="rounded-md border p-2.5"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <p class="text-[11px] text-secondary">
              {{ taskResult.diagnosis.summary }}
            </p>
            <ul class="mt-1.5 space-y-1">
              <li
                v-for="issue in taskResult.diagnosis.issues"
                :key="issue.code"
                class="text-[11px] text-muted"
              >
                · {{ issue.title }}：{{ issue.suggestion }}
              </li>
            </ul>
          </div>

          <div
            v-if="previousSummary"
            class="rounded-md border p-2.5 text-[11px]"
            :style="{ borderColor: 'var(--border-subtle)' }"
          >
            <p class="text-secondary">对比实验</p>
            <div class="mt-1 flex justify-between text-muted">
              <span>{{ previousSummary.label }}</span>
              <span class="font-mono">
                准确率 {{ previousSummary.accuracy.toFixed(3) }} · loss
                {{ previousSummary.loss.toFixed(4) }}
              </span>
            </div>
            <div class="mt-1 flex justify-between text-muted">
              <span>本组</span>
              <span class="font-mono">
                准确率 {{ (latest?.accuracy ?? 0).toFixed(3) }} · loss
                {{ (latest?.val_loss ?? 0).toFixed(4) }}
              </span>
            </div>
          </div>

          <div class="space-y-2">
            <p class="text-[11px] font-medium text-secondary">检查点</p>
            <div
              v-for="(checkpoint, index) in currentTask.checkpoints"
              :key="index"
              class="rounded-md border p-2.5"
              :style="{ borderColor: 'var(--border-subtle)' }"
            >
              <p class="text-[11px] text-secondary">
                {{ index + 1 }}. {{ checkpoint.question }}
              </p>
              <label
                v-for="(option, optionIndex) in checkpoint.options"
                :key="optionIndex"
                class="mt-1 flex cursor-pointer items-start gap-1.5 text-[11px] text-muted"
              >
                <input
                  type="radio"
                  :name="`checkpoint-${index}`"
                  class="mt-0.5 accent-[var(--brand-cyan)]"
                  :checked="checkpointAnswers[index] === optionIndex"
                  @change="answerCheckpoint(index, optionIndex)"
                />
                <span>{{ option }}</span>
              </label>
              <p
                v-if="checkpointAnswers[index] !== undefined"
                class="mt-1.5 text-[11px] leading-relaxed"
                :style="{
                  color:
                    checkpointAnswers[index] === checkpoint.answer
                      ? 'var(--success)'
                      : 'var(--danger)',
                }"
              >
                {{
                  checkpointAnswers[index] === checkpoint.answer
                    ? '正确：'
                    : '再想想：'
                }}{{ checkpoint.explain }}
              </p>
            </div>
          </div>
        </div>

        <footer
          class="flex shrink-0 justify-end gap-2 border-t px-4 py-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <AppButton
            variant="secondary"
            size="sm"
            :disabled="status !== 'completed'"
            @click="prepareComparison"
          >
            再跑一组对比
          </AppButton>
          <AppButton size="sm" @click="closeTaskResult">关闭</AppButton>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3) {
  margin: 0.6em 0 0.3em;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.markdown :deep(p) {
  margin: 0.4em 0;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0.4em 0;
  padding-left: 1.2em;
  list-style: disc;
}

.markdown :deep(code) {
  border-radius: 3px;
  background: var(--bg-elevated);
  padding: 0 0.3em;
  font-family: ui-monospace, monospace;
}

.markdown :deep(pre) {
  margin: 0.5em 0;
  overflow-x: auto;
  border-radius: 4px;
  background: var(--bg-elevated);
  padding: 0.5em 0.6em;
}

.markdown :deep(pre code) {
  background: transparent;
  padding: 0;
}

.markdown :deep(strong) {
  color: var(--text-primary);
}
</style>
