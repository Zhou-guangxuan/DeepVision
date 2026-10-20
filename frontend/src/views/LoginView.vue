<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { AxiosError } from 'axios'

import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppInput from '@/components/ui/AppInput.vue'
import { useTopologyCanvas } from '@/composables/useTopologyCanvas'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

const REMEMBER_KEY = 'dv_remembered_username'
const USERNAME_RE = /^[A-Za-z0-9_-]{3,64}$/
const STRENGTH_LABELS = ['', '弱', '一般', '较强', '强']
const STRENGTH_COLORS = [
  '',
  'bg-danger',
  'bg-warning',
  'bg-brand-cyan',
  'bg-success',
]

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()

const canvasRef = ref<HTMLCanvasElement | null>(null)
useTopologyCanvas(canvasRef)

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const confirm = ref('')
const remember = ref(true)
const shaking = ref(false)

const errors = ref<{
  username?: string
  password?: string
  confirm?: string
  form?: string
}>({})

const isRegister = computed(() => mode.value === 'register')

const strength = computed(() => {
  const value = password.value
  if (!value) return 0
  let score = 0
  if (value.length >= 8) score += 1
  if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1
  if (/\d/.test(value)) score += 1
  if (/[^A-Za-z0-9]/.test(value)) score += 1
  return Math.max(1, score)
})

const strengthLabel = computed(() => STRENGTH_LABELS[strength.value] ?? '')
const strengthColor = computed(() => STRENGTH_COLORS[strength.value] ?? '')

const features = [
  '拖拽即得网络拓扑，画布即数据源',
  '训练过程实时可见，前向 / 反向传播可感知',
  'LLM 助教诊断结构，建议可一键应用',
]

onMounted(() => {
  const remembered = localStorage.getItem(REMEMBER_KEY)
  if (remembered) {
    username.value = remembered
    remember.value = true
  }
})

function shake(): void {
  shaking.value = false
  window.requestAnimationFrame(() => {
    shaking.value = true
    window.setTimeout(() => {
      shaking.value = false
    }, 260)
  })
}

function validate(): boolean {
  const next: typeof errors.value = {}

  if (!USERNAME_RE.test(username.value.trim())) {
    next.username = '用户名需 3-64 位，仅支持字母、数字、下划线与连字符'
  }
  if (password.value.length < 6) {
    next.password = '密码至少 6 位'
  }
  if (isRegister.value && confirm.value !== password.value) {
    next.confirm = '两次输入的密码不一致'
  }

  errors.value = next
  return Object.keys(next).length === 0
}

function handleError(error: unknown): void {
  const axiosError = error as AxiosError<{ code?: string; message?: string }>
  const code = axiosError.response?.data?.code
  const message = axiosError.response?.data?.message
  const next: typeof errors.value = {}

  if (code === 'INVALID_CREDENTIALS') {
    next.form = '用户名或密码错误'
  } else if (code === 'USERNAME_TAKEN') {
    next.username = '用户名已被占用'
  } else if (code === 'VALIDATION_ERROR') {
    next.form = '提交内容不符合要求，请检查后重试'
  } else if (message) {
    next.form = message
  } else {
    next.form = '网络异常，请确认后端服务已启动'
  }

  errors.value = next
  shake()
}

async function onSubmit(): Promise<void> {
  if (auth.loading) return
  errors.value = {}

  if (!validate()) {
    shake()
    return
  }

  const account = username.value.trim()

  try {
    if (isRegister.value) {
      await auth.register(account, password.value)
      await auth.login(account, password.value)
      toast.success('账号已创建，已自动登录')
    } else {
      await auth.login(account, password.value)
      toast.success('登录成功')
    }

    if (remember.value) {
      localStorage.setItem(REMEMBER_KEY, account)
    } else {
      localStorage.removeItem(REMEMBER_KEY)
    }

    const redirect =
      typeof route.query.redirect === 'string' &&
      route.query.redirect.startsWith('/')
        ? route.query.redirect
        : '/workspace'
    await router.replace(redirect)
  } catch (error) {
    handleError(error)
  }
}

function toggleMode(): void {
  mode.value = isRegister.value ? 'login' : 'register'
  errors.value = {}
  confirm.value = ''
}

function onForgot(): void {
  toast.info('找回密码功能将在后续版本开放')
}
</script>

<template>
  <div class="flex min-h-screen w-full overflow-hidden bg-base">
    <!-- 品牌区：宽屏显示 -->
    <section class="relative hidden w-3/5 flex-col justify-center p-12 lg:flex">
      <div class="pointer-events-none absolute inset-0">
        <div
          class="absolute -left-32 -top-32 h-[440px] w-[440px] rounded-full blur-[130px]"
          style="background: rgba(34, 211, 238, 0.1)"
        />
        <div
          class="absolute -bottom-40 -right-20 h-[480px] w-[480px] rounded-full blur-[140px]"
          style="background: rgba(139, 92, 246, 0.1)"
        />
      </div>

      <canvas
        ref="canvasRef"
        class="pointer-events-none absolute inset-0 h-full w-full opacity-60"
        aria-hidden="true"
      />

      <div class="relative z-10 max-w-xl">
        <h1 class="text-3xl font-semibold leading-tight tracking-tight">
          把「搭网络 + 看训练」<br />
          从代码里搬到画布上
        </h1>
        <p class="mt-4 text-base leading-relaxed text-secondary">
          拖拽搭建神经网络结构，上传 CSV
          数据，实时观察训练过程中损失与准确率的变化，并由 AI
          助教给出结构与超参建议。
        </p>
        <ul class="mt-8 space-y-3">
          <li
            v-for="item in features"
            :key="item"
            class="flex items-center gap-2.5 text-sm text-secondary"
          >
            <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-cyan" />
            {{ item }}
          </li>
        </ul>
      </div>
    </section>

    <!-- 表单区 -->
    <section
      class="flex w-full flex-1 items-center justify-center px-6 py-10 lg:w-2/5"
    >
      <div class="dv-fade-up w-full max-w-[360px]">
        <div class="mb-6 flex items-center gap-2.5 lg:hidden">
          <span
            class="grid h-8 w-8 place-items-center rounded-md text-sm font-bold text-[#04070f]"
            style="background-image: var(--brand-gradient)"
          >
            D
          </span>
          <span class="text-lg font-semibold tracking-tight">DeepVision</span>
        </div>

        <AppCard variant="glass" :class="{ 'dv-shake': shaking }">
          <h2 class="text-xl font-semibold tracking-tight">
            {{ isRegister ? '创建账号' : '登录' }}
          </h2>
          <p class="mt-1.5 text-sm text-secondary">
            {{
              isRegister ? '注册后即可搭建第一个网络' : '使用你的账号进入工作台'
            }}
          </p>

          <form class="mt-6 space-y-4" novalidate @submit.prevent="onSubmit">
            <AppInput
              v-model="username"
              label="用户名"
              :error="errors.username"
              autocomplete="username"
            />

            <AppInput
              v-model="password"
              label="密码"
              type="password"
              :error="errors.password"
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
              @enter="onSubmit"
            />

            <template v-if="isRegister">
              <AppInput
                v-model="confirm"
                label="确认密码"
                type="password"
                :error="errors.confirm"
                autocomplete="new-password"
                @enter="onSubmit"
              />

              <div>
                <div class="flex gap-1.5">
                  <span
                    v-for="segment in 4"
                    :key="segment"
                    class="h-1 flex-1 rounded-full transition-colors duration-base"
                    :class="segment <= strength ? strengthColor : 'bg-hover'"
                  />
                </div>
                <p class="mt-1.5 text-xs text-muted">
                  密码强度：<span class="text-secondary">{{
                    strengthLabel || '—'
                  }}</span>
                </p>
              </div>
            </template>

            <div
              v-if="!isRegister"
              class="flex items-center justify-between text-sm"
            >
              <label
                class="flex cursor-pointer items-center gap-2 text-secondary"
              >
                <input
                  v-model="remember"
                  type="checkbox"
                  class="h-3.5 w-3.5 accent-brand-cyan"
                />
                记住我
              </label>
              <button
                type="button"
                class="text-muted transition-colors duration-fast hover:text-brand-cyan"
                @click="onForgot"
              >
                忘记密码
              </button>
            </div>

            <p v-if="errors.form" class="text-xs text-danger" role="alert">
              {{ errors.form }}
            </p>

            <AppButton type="submit" block size="lg" :loading="auth.loading">
              {{ isRegister ? '注册并登录' : '登录' }}
            </AppButton>
          </form>

          <div class="dv-divider my-6" />

          <p class="text-center text-sm text-secondary">
            {{ isRegister ? '已有账号？' : '还没有账号？' }}
            <button
              type="button"
              class="ml-1 text-brand-cyan transition-opacity duration-fast hover:opacity-80"
              @click="toggleMode"
            >
              {{ isRegister ? '去登录' : '立即注册' }}
            </button>
          </p>
        </AppCard>
      </div>
    </section>
  </div>
</template>
