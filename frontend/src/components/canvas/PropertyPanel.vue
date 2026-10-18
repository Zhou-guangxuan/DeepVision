<script setup lang="ts">
import { computed } from 'vue'

import AppButton from '@/components/ui/AppButton.vue'
import {
  ACTIVATIONS,
  ACTIVATION_LABEL,
  NODE_TYPE_ACCENT,
  NODE_TYPE_LABEL,
  TASKS,
  type GraphNode,
  type NodeParamValue,
} from '@/types/graph'

const props = defineProps<{
  node: GraphNode | null
}>()

const emit = defineEmits<{
  (event: 'update', patch: Record<string, NodeParamValue>): void
  (event: 'remove'): void
}>()

const accent = computed(() =>
  props.node ? NODE_TYPE_ACCENT[props.node.type] : 'var(--border-default)',
)

function onNumber(key: string, event: Event, min: number, max: number): void {
  const raw = Number((event.target as HTMLInputElement).value)
  if (!Number.isFinite(raw)) return
  const value = Math.min(Math.max(Math.round(raw), min), max)
  emit('update', { [key]: value })
}

function onSelect(key: string, event: Event): void {
  emit('update', { [key]: (event.target as HTMLSelectElement).value })
}
</script>

<template>
  <aside
    class="flex h-full w-80 shrink-0 flex-col border-l"
    :style="{ borderColor: 'var(--border-subtle)', background: 'var(--bg-surface)' }"
  >
    <div class="border-b px-4 py-4" :style="{ borderColor: 'var(--border-subtle)' }">
      <h2 class="text-sm font-semibold text-primary">属性</h2>
      <p v-if="node" class="mt-1 flex items-center gap-1.5 text-xs text-secondary">
        <span class="h-1.5 w-1.5 rounded-full" :style="{ background: accent }" />
        {{ NODE_TYPE_LABEL[node.type] }}
      </p>
      <p v-else class="mt-1 text-xs text-muted">未选中节点</p>
    </div>

    <div class="flex-1 overflow-y-auto px-4 py-4">
      <template v-if="node">
        <div v-if="node.type === 'input'" class="space-y-4">
          <div>
            <label class="mb-1.5 block text-xs text-secondary" :for="`f-features`">
              输入特征数
            </label>
            <input
              :id="`f-features`"
              class="dv-input-plain"
              type="number"
              min="1"
              max="4096"
              :value="node.params.features"
              @change="onNumber('features', $event, 1, 4096)"
            />
            <p class="mt-1.5 text-[11px] text-muted">
              通常等于 CSV 的特征列数
            </p>
          </div>
        </div>

        <div v-else-if="node.type === 'hidden'" class="space-y-4">
          <div>
            <label class="mb-1.5 block text-xs text-secondary" :for="`f-units`">
              神经元数
            </label>
            <input
              :id="`f-units`"
              class="dv-input-plain"
              type="number"
              min="1"
              max="4096"
              :value="node.params.units"
              @change="onNumber('units', $event, 1, 4096)"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-secondary" :for="`f-activation`">
              激活函数
            </label>
            <select
              :id="`f-activation`"
              class="dv-select"
              :value="node.params.activation"
              @change="onSelect('activation', $event)"
            >
              <option v-for="item in ACTIVATIONS" :key="item" :value="item">
                {{ ACTIVATION_LABEL[item] }}
              </option>
            </select>
          </div>
        </div>

        <div v-else class="space-y-4">
          <div>
            <label class="mb-1.5 block text-xs text-secondary" :for="`f-out-units`">
              输出单元数
            </label>
            <input
              :id="`f-out-units`"
              class="dv-input-plain"
              type="number"
              min="1"
              max="4096"
              :value="node.params.units"
              @change="onNumber('units', $event, 1, 4096)"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-secondary" :for="`f-task`">
              任务类型
            </label>
            <select
              :id="`f-task`"
              class="dv-select"
              :value="node.params.task"
              @change="onSelect('task', $event)"
            >
              <option v-for="item in TASKS" :key="item" :value="item">
                {{ item === 'classification' ? '分类' : '回归' }}
              </option>
            </select>
          </div>
        </div>

        <div class="mt-6 border-t pt-4" :style="{ borderColor: 'var(--border-subtle)' }">
          <p class="font-mono text-[11px] text-muted">id: {{ node.id }}</p>
        </div>
      </template>

      <p v-else class="text-xs leading-relaxed text-muted">
        在画布中单击节点即可编辑参数，双击节点可聚焦到该节点。
      </p>
    </div>

    <div
      v-if="node"
      class="border-t px-4 py-3"
      :style="{ borderColor: 'var(--border-subtle)' }"
    >
      <AppButton variant="danger" size="sm" block @click="emit('remove')">
        删除该节点
      </AppButton>
    </div>
  </aside>
</template>
