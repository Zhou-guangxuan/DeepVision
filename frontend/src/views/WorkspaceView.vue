<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { listRecords } from '@/api/records'
import type { RecordStatus, TrainingRecord } from '@/api/records'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppSkeleton from '@/components/ui/AppSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

const auth = useAuthStore()
const toast = useToastStore()
const router = useRouter()

const records = ref<TrainingRecord[]>([])
const loading = ref(true)
const loadError = ref(false)

const STATUS_TEXT: Record<RecordStatus, string> = {
  pending: '等待中',
  running: '训练中',
  success: '成功',
  failed: '失败',
  interrupted: '已中断',
}

const STATUS_BADGE: Record<RecordStatus, string> = {
  pending: 'dv-badge--neutral',
  running: 'dv-badge--warning',
  success: 'dv-badge--success',
  failed: 'dv-badge--danger',
  interrupted: 'dv-badge--neutral',
}

onMounted(async () => {
  await auth.loadMe()
  await load()
})

async function load(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    const page = await listRecords(1, 20)
    records.value = page.items
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function logout(): void {
  auth.logout()
  toast.info('已退出登录')
  void router.replace('/login')
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <div class="min-h-screen bg-base">
    <!-- 顶栏 -->
    <header
      class="sticky top-0 z-30 flex h-16 items-center justify-between border-b px-6 backdrop-blur"
      style="
        border-color: var(--border-subtle);
        background: rgba(10, 14, 26, 0.8);
      "
    >
      <div class="flex items-center gap-2.5">
        <span
          class="grid h-8 w-8 place-items-center rounded-md text-sm font-bold text-[#04070f]"
          style="background-image: var(--brand-gradient)"
        >
          D
        </span>
        <span class="text-lg font-semibold tracking-tight">DeepVision</span>
        <span class="dv-badge dv-badge--neutral ml-1">阶段一</span>
      </div>

      <div class="flex items-center gap-3">
        <span class="hidden text-sm text-secondary sm:inline">
          {{ auth.user?.username ?? '已登录用户' }}
        </span>
        <AppButton variant="secondary" size="sm" @click="logout">
          退出登录
        </AppButton>
      </div>
    </header>

    <main class="mx-auto w-full max-w-5xl px-6 py-10">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="text-2xl font-semibold tracking-tight">训练记录</h1>
          <p class="mt-1.5 text-sm text-secondary">
            阶段一已打通「注册 → 登录 → 鉴权 → 记录读写」链路。
          </p>
        </div>
        <AppButton size="sm" @click="load">刷新</AppButton>
      </div>

      <div class="mt-8 space-y-3">
        <!-- 加载态 -->
        <template v-if="loading">
          <AppCard v-for="index in 3" :key="index" padding="md">
            <div class="flex items-center gap-4">
              <AppSkeleton width="40px" height="40px" rounded="12px" />
              <div class="flex-1 space-y-2">
                <AppSkeleton width="160px" height="14px" />
                <AppSkeleton width="96px" height="12px" />
              </div>
            </div>
          </AppCard>
        </template>

        <!-- 错误态 -->
        <AppCard v-else-if="loadError" padding="lg">
          <div class="flex flex-col items-center gap-3 py-6 text-center">
            <p class="text-sm text-danger">训练记录加载失败</p>
            <p class="text-xs text-muted">请确认后端服务已启动，或稍后重试</p>
            <AppButton variant="secondary" size="sm" @click="load">
              重试
            </AppButton>
          </div>
        </AppCard>

        <!-- 空态 -->
        <AppCard v-else-if="records.length === 0" padding="lg">
          <div class="flex flex-col items-center gap-3 py-10 text-center">
            <div
              class="grid h-14 w-14 place-items-center rounded-full border"
              style="border-color: var(--border-default)"
            >
              <span class="h-2 w-2 rounded-full bg-brand-cyan dv-pulse" />
            </div>
            <p class="text-sm text-primary">还没有训练记录</p>
            <p class="max-w-sm text-xs leading-relaxed text-muted">
              认证与记录读写链路已就绪。画布、数据集与训练模块将在后续阶段接入。
            </p>
          </div>
        </AppCard>

        <!-- 列表 -->
        <template v-else>
          <AppCard
            v-for="record in records"
            :key="record.id"
            padding="md"
            class="transition-colors duration-base"
          >
            <div class="flex items-center justify-between gap-4">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="truncate font-mono text-sm text-primary">
                    {{ record.task_id }}
                  </span>
                  <span
                    class="dv-badge"
                    :class="STATUS_BADGE[record.status]"
                  >
                    {{ STATUS_TEXT[record.status] }}
                  </span>
                </div>
                <p class="mt-1 text-xs text-muted">
                  {{ formatTime(record.created_at) }}
                </p>
              </div>
              <span class="shrink-0 text-xs text-muted">
                {{ record.model_config?.nodes?.length ?? 0 }} 层
              </span>
            </div>
          </AppCard>
        </template>
      </div>
    </main>
  </div>
</template>
