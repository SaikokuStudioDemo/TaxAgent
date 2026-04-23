import { createApp } from 'vue'
import './assets/tailwind.css'
import App from './App.vue'
import router from './router'
import { initAuth } from '@/composables/useAuth'

// ルーターガードが判定する前にプロファイルロードを開始する
initAuth()

const app = createApp(App)

app.use(router)
app.mount('#app')
