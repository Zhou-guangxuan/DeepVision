<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'solid' | 'glass'
    padding?: 'none' | 'md' | 'lg'
  }>(),
  {
    variant: 'solid',
    padding: 'lg',
  },
)
</script>

<template>
  <div
    class="dv-card"
    :class="[
      variant === 'glass' ? 'dv-card--glass' : '',
      padding === 'lg' ? 'p-6' : padding === 'md' ? 'p-4' : '',
    ]"
  >
    <slot />
  </div>
</template>
