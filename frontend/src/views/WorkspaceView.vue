<script setup lang="ts">
import {
  defineAsyncComponent,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import { useRouter } from 'vue-router'

import { validateGraph } from '@/api/graph'
import { listRecords } from '@/api/records'
import NetworkCanvas from '@/components/canvas/NetworkCanvas.vue'
import NodeLibrary from '@/components/canvas/NodeLibrary.vue'
import PropertyPanel from '@/components/canvas/PropertyPanel.vue'
import StartTrainingDialog from '@/components/train/StartTrainingDialog.vue'
import AppButton from '@/components/ui/AppButton.vue'
import { useAuthStore } from '@/stores/auth'
import { useGraphStore } from '@/stores/graph'
import type { LayerStat, ViewMode } from '@/stores/graph'
import { useToastStore } from '@/stores/toast'
import type { NodeParamValue, NodeType } from '@/types/graph'

const VIEW_MODES: { value: ViewMode; label: string }[] = [
  { value: 'weight', label: '权重' },
  { value: 'gradient', label: '梯度' },
  { value: 'activation', label: '激活' },
]

// three.js 体积较大，只有切到 3D 视图时才加载
const Network3DView = defineAsyncComponent(
  () => import('@/components/threed/Network3DView.vue'),
)

const auth = useAuthStore()
const graph = useGraphStore()
const toast = useToastStore()
const router = useRouter()

const canvasRef = ref<{ addNodeAtCenter: (type: NodeType) => void } | null>(null)
const showTrainingDialog = ref(false)
/** 中央区在 2D 编辑与 3D 只读视图之间切换 */
const is3D = ref(false)
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
  await loadLayerStats()
})

/** 读取最近一次训练记录的逐层统计，供顶栏的权重/梯度/激活视图使用 */
async function loadLayerStats(): Promise<void> {
  try {
    const page = await listRecords(1, 1)
    const latest = page.items[0]
    const metrics = latest?.result_metrics as
      | { layer_stats?: LayerStat[] }
      | undefined
    const stats = metrics?.layer_stats
    if (Array.isArray(stats) && stats.length > 0) {
      graph.setLayerStats(stats)
    }
  } catch {
    // 没有历史训练记录时保持未加载状态，界面会退化为中性样式
  }
}

onBeforeUnmount(() => {
  window.clearTimeout(saveTimer)
})

async function onAddNode(type: NodeType): Promise<void> {
  // 3D 视图下 2D 画布未挂载，先切回再添加
  if (!canvasRef.value && is3D.value) {
    is3D.value = false
    await nextTick()
  }
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

function onTrainingStarted(taskId: string): void {
  showTrainingDialog.value = false
  void router.push(`/train/${taskId}`)
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

      <!-- 视图模式切换（设计文档第二版 · 模块一） -->
      <div class="flex flex-1 justify-center px-2">
        <div
          class="flex items-center gap-0.5 rounded-md border p-0.5"
          :style="{
            borderColor: 'var(--border-default)',
            background: 'var(--bg-base)',
          }"
          role="group"
          aria-label="视图模式"
        >
          <span class="px-2 text-[11px] text-muted">视图</span>
          <button
            v-for="mode in VIEW_MODES"
            :key="mode.value"
            type="button"
            class="rounded-sm px-2.5 py-1 text-xs transition-colors duration-fast"
            :class="
              graph.viewMode === mode.value
                ? 'text-primary'
                : 'text-muted hover:text-secondary'
            "
            :style="
              graph.viewMode === mode.value
                ? { background: 'var(--bg-elevated)' }
                : {}
            "
            :title="
              graph.layerStatsLoaded
                ? '按最近一次训练的逐层数据渲染'
                : '完成一次训练后可查看逐层数据'
            "
            @click="graph.setViewMode(mode.value)"
          >
            {{ mode.label }}
          </button>
        </div>

        <button
          type="button"
          class="ml-1 rounded-sm border px-2.5 py-1 text-xs transition-colors duration-fast"
          :style="
            is3D
              ? {
                  borderColor: 'var(--brand-cyan)',
                  color: 'var(--brand-cyan)',
                  background: 'rgba(34, 211, 238, 0.12)',
                }
              : {
                  borderColor: 'var(--border-default)',
                  color: 'var(--text-muted)',
                }
          "
          :title="is3D ? '切换回 2D 编辑画布' : '切换为 3D 只读视图'"
          @click="is3D = !is3D"
        >
          {{ is3D ? '2D 编辑' : '3D 视图' }}
        </button>
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
        <AppButton variant="secondary" size="sm" @click="router.push('/data')">
          数据集
        </AppButton>
        <AppButton size="sm" @click="showTrainingDialog = true">
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
        <Network3DView v-if="is3D" />
        <NetworkCanvas
          v-else
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

    <StartTrainingDialog
      :open="showTrainingDialog"
      @close="showTrainingDialog = false"
      @started="onTrainingStarted"
    />
  </div>
</template>
