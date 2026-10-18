<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { validateGraph } from '@/api/graph'
import NetworkCanvas from '@/components/canvas/NetworkCanvas.vue'
import NodeLibrary from '@/components/canvas/NodeLibrary.vue'
import PropertyPanel from '@/components/canvas/PropertyPanel.vue'
import AppButton from '@/components/ui/AppButton.vue'
import { useAuthStore } from '@/stores/auth'
import { useGraphStore } from '@/stores/graph'
import { useToastStore } from '@/stores/toast'
import type { NodeParamValue, NodeType } from '@/types/graph'

const auth = useAuthStore()
const graph = useGraphStore()
const toast = useToastStore()
const router = useRouter()

const canvasRef = ref<{ addNodeAtCenter: (type: NodeType) => void } | null>(null)
const projectName = ref('未命名项目')
const validating = ref(false)

let saveTimer: number | undefined

// 拓扑变更后 2s 防抖写入本地草稿（对应设计文档 §5.3「自动保存」）
watch(
  [() => graph.nodes, () => graph.edges],
  () => {
    window.clearTimeout(saveTimer)
    saveTimer = window.setTimeout(() => graph.saveDraft(), 2000)
  },
  { deep: true },
)

onMounted(async () => {
  await auth.loadMe()
  if (graph.loadDraft() && graph.nodes.length > 0) {
    toast.info('已恢复上次的拓扑草稿')
  }
})

onBeforeUnmount(() => {
  window.clearTimeout(saveTimer)
})

function onAddNode(type: NodeType): void {
  canvasRef.value?.addNodeAtCenter(type)
}

function onUpdateParams(patch: Record<string, NodeParamValue>): void {
  if (graph.selectedNodeId) graph.updateParams(graph.selectedNodeId, patch)
}

function onRemoveNode(): void {
  if (graph.selectedNodeId) graph.removeNode(graph.selectedNodeId)
}

function onNotify(message: string): void {
  toast.error(message)
}

async function onValidate(): Promise<void> {
  if (graph.nodes.length === 0) {
    toast.info('画布为空，先拖入节点')
    return
  }

  validating.value = true
  try {
    const result = await validateGraph(graph.toModelConfig())
    if (!result.valid) {
      toast.error(`校验未通过：${result.errors[0]}`)
    } else if (result.warnings.length > 0) {
      toast.info(`结构合法，但：${result.warnings[0]}`)
    } else {
      toast.success('拓扑校验通过')
    }
  } catch {
    // 错误已由 Axios 拦截器统一提示
  } finally {
    validating.value = false
  }
}

function logout(): void {
  auth.logout()
  toast.info('已退出登录')
  void router.replace('/login')
}
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
        <span
          class="grid h-8 w-8 shrink-0 place-items-center rounded-md text-sm font-bold text-[#04070f]"
          style="background-image: var(--brand-gradient)"
        >
          D
        </span>
        <input
          v-model="projectName"
          class="w-40 bg-transparent text-sm text-secondary outline-none transition-colors duration-fast hover:text-primary focus:text-primary"
          aria-label="项目名称"
        />
        <span class="dv-badge dv-badge--neutral shrink-0">阶段二</span>
        <span class="hidden text-[11px] text-muted md:inline">
          {{ graph.savedAt ? '草稿已保存' : '草稿未保存' }}
        </span>
      </div>

      <div class="flex items-center gap-2">
        <AppButton
          variant="secondary"
          size="sm"
          :loading="validating"
          @click="onValidate"
        >
          校验拓扑
        </AppButton>
        <AppButton variant="ghost" size="sm" disabled title="阶段三开放">
          数据集
        </AppButton>
        <AppButton variant="ghost" size="sm" disabled title="阶段四开放">
          开始训练
        </AppButton>
        <span
          class="mx-1 h-5 w-px"
          :style="{ background: 'var(--border-subtle)' }"
        />
        <span class="hidden text-sm text-secondary sm:inline">
          {{ auth.user?.username ?? '已登录' }}
        </span>
        <AppButton variant="secondary" size="sm" @click="logout">
          退出
        </AppButton>
      </div>
    </header>

    <div class="flex min-h-0 flex-1">
      <NodeLibrary @add="onAddNode" />

      <main class="relative flex min-w-0 flex-1">
        <NetworkCanvas
          ref="canvasRef"
          @notify="onNotify"
          @validate="onValidate"
        />
      </main>

      <PropertyPanel
        :node="graph.selectedNode"
        @update="onUpdateParams"
        @remove="onRemoveNode"
      />
    </div>
  </div>
</template>
