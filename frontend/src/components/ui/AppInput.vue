<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    label: string
    id?: string
    type?: string
    error?: string
    hint?: string
    autocomplete?: string
    disabled?: boolean
  }>(),
  {
    id: undefined,
    type: 'text',
    error: '',
    hint: '',
    autocomplete: 'off',
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  blur: []
  enter: []
}>()

const focused = ref(false)
const inputId = computed(
  () => props.id ?? `dv-input-${Math.random().toString(36).slice(2, 9)}`,
)
// 聚焦或有内容时，标签上浮
const floating = computed(() => focused.value || (props.modelValue ?? '').length > 0)

function onInput(event: Event): void {
  emit('update:modelValue', (event.target as HTMLInputElement).value)
}

function onBlur(): void {
  focused.value = false
  emit('blur')
}
</script>

<template>
  <div>
    <div class="dv-field">
      <input
        :id="inputId"
        class="dv-input"
        :class="{ 'dv-input--error': Boolean(error) }"
        :type="type"
        :value="modelValue"
        :disabled="disabled"
        :autocomplete="autocomplete"
        :aria-invalid="Boolean(error) || undefined"
        :aria-describedby="error ? `${inputId}-error` : undefined"
        placeholder=" "
        @input="onInput"
        @focus="focused = true"
        @blur="onBlur"
        @keyup.enter="emit('enter')"
      />
      <label
        :for="inputId"
        class="dv-float-label"
        :class="{
          'dv-float-label--active': floating,
          'dv-float-label--focus': focused,
        }"
      >
        {{ label }}
      </label>
    </div>

    <p
      v-if="error"
      :id="`${inputId}-error`"
      class="mt-1.5 text-xs leading-relaxed text-danger"
      role="alert"
    >
      {{ error }}
    </p>
    <p v-else-if="hint" class="mt-1.5 text-xs leading-relaxed text-muted">
      {{ hint }}
    </p>
  </div>
</template>
