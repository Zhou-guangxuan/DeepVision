import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发期把 /api 代理到后端，避免跨域
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // WebSocket 实时通道：路径不带 /api 前缀，需要单独代理并开启 ws
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
})
