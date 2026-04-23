/**
 * Admin専用の認証 composable。
 * useAuth とは完全に分離する。Admin画面でのみ使用。
 * Admin UID かどうかはバックエンドの /admin/me で確認する。
 */
import { ref } from 'vue'
import { signInWithEmailAndPassword, signOut as firebaseSignOut } from 'firebase/auth'
import { auth } from '@/lib/firebase/config'
import { api } from '@/lib/api'

export const useAdminAuth = () => {
  const isAdmin = ref(false)
  const isLoading = ref(true)
  const error = ref<string | null>(null)

  const checkAdminAuth = async (): Promise<boolean> => {
    try {
      await api.get('/admin/me')
      isAdmin.value = true
      return true
    } catch {
      isAdmin.value = false
      return false
    } finally {
      isLoading.value = false
    }
  }

  const adminLogin = async (email: string, password: string): Promise<boolean> => {
    error.value = null
    try {
      await signInWithEmailAndPassword(auth, email, password)
      const ok = await checkAdminAuth()
      if (!ok) {
        error.value = '権限がありません。Admin アカウントでログインしてください。'
        await firebaseSignOut(auth)
        return false
      }
      return true
    } catch {
      error.value = 'ログインに失敗しました。メールアドレスとパスワードを確認してください。'
      return false
    }
  }

  const adminSignOut = async () => {
    await firebaseSignOut(auth)
    isAdmin.value = false
  }

  return { isAdmin, isLoading, error, checkAdminAuth, adminLogin, adminSignOut }
}
