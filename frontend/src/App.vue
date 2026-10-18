<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import AssistantDrawer from '@/components/ai/AssistantDrawer.vue'
import AppToastHost from '@/components/ui/AppToastHost.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

// 登录页不显示助教入口
const showAssistant = computed(
  () => auth.isAuthenticated && route.name !== 'login',
)
</script>

<template>
  <RouterView />
  <AssistantDrawer v-if="showAssistant" />
  <AppToastHost />
</template>
