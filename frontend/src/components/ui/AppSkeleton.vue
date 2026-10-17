<script setup lang="ts">
withDefaults(
  defineProps<{
    width?: string
    height?: string
    rounded?: string
  }>(),
  {
    width: '100%',
    height: '16px',
    rounded: '8px',
  },
)
</script>

<template>
  <div
    class="dv-skeleton"
    :style="{ width, height, borderRadius: rounded }"
    aria-hidden="true"
  />
</template>
