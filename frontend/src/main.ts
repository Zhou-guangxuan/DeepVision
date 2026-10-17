import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp(App)

// Pinia 必须先于 router 安装：路由守卫内部会使用 auth store
app.use(createPinia())
app.use(router)

app.mount('#app')
