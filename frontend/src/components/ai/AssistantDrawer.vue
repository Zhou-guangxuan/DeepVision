<script setup lang="ts">
import { nextTick, ref } from 'vue'

import {
  diagnoseGraph,
  streamChat,
  type ChatEvent,
  type DiagnoseResult,
  type DiagnoseSuggestion,
  type SuggestionField,
} from '@/api/ai'
import AppButton from '@/components/ui/AppButton.vue'
import { useGraphStore } from '@/stores/graph'
import { useToastStore } from '@/stores/toast'

interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  sources: string[]
  streaming: boolean
}

const QUICK_QUESTIONS = [
  '什么是梯度消失？',
  '学习率该设多少？',
  '过拟合了怎么办？',
  '为什么需要标准化？',
]

const FIELD_LABEL: Record<SuggestionField, string> = {
  features: '输入特征数',
  units: '神经元数',
  activation: '激活函数',
  task: '任务类型',
}

const graph = useGraphStore()
const toast = useToastStore()

const open = ref(false)
const tab = ref<'chat' | 'diagnose'>('chat')

const messages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const messageListRef = ref<HTMLElement | null>(null)
let messageSeed = 0

const diagnosing = ref(false)
const diagnosis = ref<DiagnoseResult | null>(null)
const appliedKeys = ref<Set<string>>(new Set())

function scrollToBottom(): void {
  void nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

async function send(text: string): Promise<void> {
  const content = text.trim()
  if (!content || sending.value) return

  messageSeed += 1
  messages.value.push({
    id: messageSeed,
    role: 'user',
    content,
    sources: [],
    streaming: false,
  })

  messageSeed += 1
  const assistant: ChatMessage = {
    id: messageSeed,
    role: 'assistant',
    content: '',
    sources: [],
    streaming: true,
  }
  messages.value.push(assistant)

  input.value = ''
  sending.value = true
  scrollToBottom()

  try {
    await streamChat(content, (event: ChatEvent) => {
      if (event.type === 'delta' && event.text) {
        assistant.content += event.text
        scrollToBottom()
      } else if (event.type === 'done') {
        assistant.sources = event.sources ?? []
        assistant.streaming = false
      }
    })
  } catch (error) {
    assistant.streaming = false
    assistant.content =
      assistant.content ||
      (error instanceof Error ? error.message : 'AI 助教暂时不可用')
  } finally {
    assistant.streaming = false
    sending.value = false
    scrollToBottom()
  }
}

async function runDiagnosis(): Promise<void> {
  if (diagnosing.value) return
  if (graph.nodes.length === 0) {
    toast.info('画布为空，先搭建网络')
    return
  }

  diagnosing.value = true
  try {
    diagnosis.value = await diagnoseGraph({
      model_config: graph.toModelConfig(),
    })
    appliedKeys.value = new Set()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '诊断失败')
  } finally {
    diagnosing.value = false
  }
}

function suggestionKey(suggestion: DiagnoseSuggestion): string {
  return `${suggestion.node_id}:${suggestion.field}:${String(suggestion.to)}`
}

function applySuggestion(suggestion: DiagnoseSuggestion): void {
  const node = graph.nodes.find((item) => item.id === suggestion.node_id)
  if (!node) {
    toast.error('节点已不存在，请重新诊断')
    return
  }

  graph.updateParams(suggestion.node_id, {
    [suggestion.field]: suggestion.to as string | number,
  })
  appliedKeys.value = new Set([...appliedKeys.value, suggestionKey(suggestion)])
  toast.success(
    `已应用：${FIELD_LABEL[suggestion.field]} → ${String(suggestion.to)}`,
  )
}

const SEVERITY_CLASS: Record<string, string> = {
  error: 'text-danger',
  warning: 'text-warning',
  info: 'text-secondary',
}
</script>

<template>
  <Teleport to="body">
    <!-- 悬浮入口 -->
    <button
      v-if="!open"
      type="button"
      class="fixed bottom-5 right-5 z-40 grid h-14 w-14 place-items-center rounded-full text-sm font-semibold text-[#04070f] shadow-lg transition-transform duration-fast hover:scale-105"
      style="background-image: var(--brand-gradient)"
      aria-label="打开 AI 助教"
      @click="open = true"
    >
      AI
    </button>

    <!-- 抽屉 -->
    <aside
      v-if="open"
      class="fixed right-0 top-0 z-50 flex h-full w-full max-w-[384px] flex-col border-l"
      :style="{
        background: 'var(--bg-surface)',
        borderColor: 'var(--border-default)',
      }"
    >
      <header
        class="flex h-14 shrink-0 items-center justify-between border-b px-4"
        :style="{ borderColor: 'var(--border-subtle)' }"
      >
        <div class="flex items-center gap-2">
          <span
            class="grid h-6 w-6 place-items-center rounded-md text-[11px] font-bold text-[#04070f]"
            style="background-image: var(--brand-gradient)"
          >
            AI
          </span>
          <span class="text-sm font-medium text-primary">AI 助教</span>
        </div>
        <button
          type="button"
          class="px-1 text-lg leading-none text-muted transition-colors duration-fast hover:text-primary"
          aria-label="关闭"
          @click="open = false"
        >
          ×
        </button>
      </header>

      <!-- 切换 -->
      <div
        class="flex shrink-0 gap-1 border-b px-2 py-2"
        :style="{ borderColor: 'var(--border-subtle)' }"
      >
        <button
          type="button"
          class="flex-1 rounded-sm px-3 py-1.5 text-xs transition-colors duration-fast"
          :class="
            tab === 'chat' ? 'text-primary' : 'text-muted hover:text-secondary'
          "
          :style="tab === 'chat' ? { background: 'var(--bg-elevated)' } : {}"
          @click="tab = 'chat'"
        >
          问答
        </button>
        <button
          type="button"
          class="flex-1 rounded-sm px-3 py-1.5 text-xs transition-colors duration-fast"
          :class="
            tab === 'diagnose'
              ? 'text-primary'
              : 'text-muted hover:text-secondary'
          "
          :style="
            tab === 'diagnose' ? { background: 'var(--bg-elevated)' } : {}
          "
          @click="tab = 'diagnose'"
        >
          网络诊断
        </button>
      </div>

      <!-- 问答 -->
      <template v-if="tab === 'chat'">
        <div
          ref="messageListRef"
          class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3"
        >
          <div v-if="messages.length === 0" class="space-y-3">
            <p class="text-xs leading-relaxed text-muted">
              可以问我深度学习的基础概念，也可以让我看图之前先给点训练建议。
            </p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="question in QUICK_QUESTIONS"
                :key="question"
                type="button"
                class="rounded-full border px-3 py-1 text-[11px] text-secondary transition-colors duration-fast hover:text-primary"
                :style="{ borderColor: 'var(--border-default)' }"
                @click="send(question)"
              >
                {{ question }}
              </button>
            </div>
          </div>

          <div
            v-for="message in messages"
            :key="message.id"
            class="flex"
            :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
          >
            <div
              class="max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed"
              :style="
                message.role === 'user'
                  ? {
                      backgroundImage: 'var(--brand-gradient)',
                      color: '#04070f',
                    }
                  : {
                      background: 'var(--bg-elevated)',
                      color: 'var(--text-primary)',
                    }
              "
            >
              <p class="whitespace-pre-wrap">
                {{ message.content }}<span v-if="message.streaming">▌</span>
              </p>
              <div
                v-if="message.sources.length > 0"
                class="mt-2 border-t pt-1.5 text-[10px] text-muted"
                :style="{ borderColor: 'var(--border-subtle)' }"
              >
                <p class="mb-0.5 text-secondary">参考来源</p>
                <p v-for="source in message.sources" :key="source">
                  · {{ source }}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div
          class="shrink-0 border-t px-3 py-3"
          :style="{ borderColor: 'var(--border-subtle)' }"
        >
          <div class="flex items-end gap-2">
            <textarea
              v-model="input"
              rows="2"
              class="max-h-24 flex-1 resize-none rounded-sm border bg-transparent px-2 py-1.5 text-xs text-primary outline-none"
              :style="{
                borderColor: 'var(--border-default)',
                background: 'var(--bg-base)',
              }"
              placeholder="问点什么，例如：什么是梯度消失？"
              @keydown.enter.exact.prevent="send(input)"
            />
            <AppButton size="sm" :loading="sending" @click="send(input)">
              发送
            </AppButton>
          </div>
        </div>
      </template>

      <!-- 诊断 -->
      <template v-else>
        <div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <p class="text-xs leading-relaxed text-muted">
            基于当前画布拓扑给出结构建议，可直接应用到节点参数（可撤销）。
          </p>

          <AppButton
            class="mt-3"
            size="sm"
            block
            :loading="diagnosing"
            @click="runDiagnosis"
          >
            诊断当前网络
          </AppButton>

          <template v-if="diagnosis">
            <div class="mt-4 flex items-center justify-between">
              <span class="text-xs text-secondary">健康评分</span>
              <span
                class="font-mono text-lg"
                :class="
                  diagnosis.score >= 80
                    ? 'text-success'
                    : diagnosis.score >= 60
                      ? 'text-warning'
                      : 'text-danger'
                "
              >
                {{ diagnosis.score }}
              </span>
            </div>

            <div v-if="diagnosis.issues.length > 0" class="mt-4 space-y-2">
              <p class="text-xs font-medium text-secondary">问题</p>
              <div
                v-for="(issue, index) in diagnosis.issues"
                :key="index"
                class="flex gap-2 text-[11px] leading-relaxed"
              >
                <span class="shrink-0" :class="SEVERITY_CLASS[issue.severity]">
                  ●
                </span>
                <span class="text-secondary">{{ issue.message }}</span>
              </div>
            </div>
            <p v-else class="mt-4 text-[11px] text-muted">没有发现明显问题。</p>

            <div v-if="diagnosis.suggestions.length > 0" class="mt-5 space-y-2">
              <p class="text-xs font-medium text-secondary">可应用的建议</p>
              <div
                v-for="suggestion in diagnosis.suggestions"
                :key="suggestionKey(suggestion)"
                class="rounded-md border p-2.5"
                :style="{ borderColor: 'var(--border-subtle)' }"
              >
                <p class="text-[11px] text-primary">
                  {{ FIELD_LABEL[suggestion.field] }}：{{ suggestion.from }} →
                  {{ suggestion.to }}
                </p>
                <p class="mt-1 text-[11px] leading-relaxed text-muted">
                  {{ suggestion.reason }}
                </p>
                <div class="mt-2 flex justify-end">
                  <AppButton
                    size="sm"
                    variant="secondary"
                    :disabled="appliedKeys.has(suggestionKey(suggestion))"
                    @click="applySuggestion(suggestion)"
                  >
                    {{
                      appliedKeys.has(suggestionKey(suggestion))
                        ? '已应用'
                        : '一键应用'
                    }}
                  </AppButton>
                </div>
              </div>
            </div>
          </template>
        </div>
      </template>
    </aside>
  </Teleport>
</template>
