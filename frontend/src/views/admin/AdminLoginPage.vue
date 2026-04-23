<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminAuth } from '@/composables/useAdminAuth'

const router = useRouter()
const { adminLogin, error, isLoading } = useAdminAuth()

const email = ref('')
const password = ref('')
const submitting = ref(false)

const handleLogin = async () => {
  if (!email.value || !password.value) return
  submitting.value = true
  const ok = await adminLogin(email.value, password.value)
  submitting.value = false
  if (ok) {
    router.push('/admin')
  }
}
</script>

<template>
  <div class="min-h-screen bg-slate-900 flex items-center justify-center p-4">
    <div class="w-full max-w-md">
      <div class="text-center mb-8">
        <h1 class="text-2xl font-extrabold text-sky-400">Tax-Agent Admin</h1>
        <p class="text-slate-400 text-sm mt-1">運営局 管理ポータル</p>
      </div>

      <form
        @submit.prevent="handleLogin"
        class="bg-slate-800 rounded-2xl shadow-xl p-8 space-y-5 border border-slate-700"
      >
        <div v-if="error" class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
          {{ error }}
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-300 mb-1.5">メールアドレス</label>
          <input
            v-model="email"
            type="email"
            autocomplete="email"
            required
            class="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2.5 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-transparent transition"
            placeholder="admin@example.com"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-300 mb-1.5">パスワード</label>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            class="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2.5 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-transparent transition"
            placeholder="••••••••"
          />
        </div>

        <button
          type="submit"
          :disabled="submitting"
          class="w-full bg-sky-500 hover:bg-sky-400 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-bold rounded-lg py-2.5 transition-colors"
        >
          {{ submitting ? 'ログイン中...' : 'ログイン' }}
        </button>
      </form>
    </div>
  </div>
</template>
