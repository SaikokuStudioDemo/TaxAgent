<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { signInWithEmailAndPassword, signOut as firebaseSignOut, sendEmailVerification, getAuth } from 'firebase/auth';
import { initializeApp } from 'firebase/app';
import { auth, firebaseConfig } from '@/lib/firebase/config';
import { useAuth } from '@/composables/useAuth';
import { Building2, Landmark, LogIn, Loader2, Eye, EyeOff } from 'lucide-vue-next';

const router = useRouter();
const { userProfile, isLoading, initAuth, devLogin } = useAuth();
const isDevMode = import.meta.env.DEV;

const email = ref('');
const password = ref('');
const errorMsg = ref('');
const isSubmitting = ref(false);
const showPassword = ref(false);

const handleLogin = async () => {
  errorMsg.value = '';
  isSubmitting.value = true;
  try {
    const userCredential = await signInWithEmailAndPassword(auth, email.value, password.value);
    if (!userCredential.user.emailVerified) {
      await firebaseSignOut(auth);
      throw new Error(
        'メールアドレスの確認が完了していません。\n' +
        '登録時に送信した確認メールのリンクをクリックしてください。\n' +
        '※確認メールが届いていない場合は下のリンクから再送信できます。'
      );
    }
    // onAuthStateChanged in useAuth will pick this up and fetch the profile.
  } catch (err: any) {
    console.error("Login failed:", err);
    errorMsg.value = err.message?.includes('メールアドレスの確認')
      ? err.message
      : 'メールアドレスまたはパスワードが間違っています。';
    isSubmitting.value = false;
  }
};

const resendVerificationEmail = async () => {
  if (!email.value || !password.value) {
    alert('メールアドレスとパスワードを入力してください。');
    return;
  }
  try {
    // セカンダリアプリ経由でログインし、メインのonAuthStateChangedを汚染しない
    const tempApp = initializeApp(firebaseConfig, `ResendApp-${Date.now()}`);
    const tempAuth = getAuth(tempApp);
    const credential = await signInWithEmailAndPassword(tempAuth, email.value, password.value);
    await sendEmailVerification(credential.user);
    await tempAuth.signOut();
    alert('確認メールを再送信しました。');
  } catch (err) {
    alert('再送信に失敗しました。メールアドレスとパスワードを確認してください。');
  }
};

// ログイン操作後にプロフィールが確定したらダッシュボードへリダイレクト
// immediate: true は不要（ログイン済みの場合は router guard の guestOnly で処理される）
watch(userProfile, (newVal) => {
  if (newVal) {
    const isTaxFirm = newVal.type === 'tax_firm' || newVal.parent_type === 'tax_firm';
    const isAdmin = newVal.type === 'admin';

    if (isAdmin) {
      router.push('/dashboard/admin');
    } else if (isTaxFirm) {
      router.push('/dashboard/tax-firm');
    } else {
      router.push('/dashboard/corporate');
    }
  }
});

onMounted(() => {
  // main.ts で initAuth() 済みだが、_authListenerInitialized フラグで二重登録を防止しているため安全
  initAuth();
});
</script>

<template>
  <div class="min-h-screen bg-gray-50 flex items-center justify-center p-4">
    
    <div v-if="isLoading" class="flex flex-col items-center justify-center gap-4 text-indigo-500">
       <Loader2 class="w-12 h-12 animate-spin" />
       <p class="font-medium">認証情報を確認中...</p>
    </div>

    <div v-else class="max-w-6xl w-full grid md:grid-cols-2 gap-8 items-center">
      
      <!-- Call to Action / Branding -->
      <div class="space-y-8 pr-8 hidden md:block">
        <div>
          <img src="/logo.png" alt="Tax Agent" class="h-12 w-auto object-contain mb-6" />
          <h1 class="text-4xl font-extrabold text-gray-900 tracking-tight mb-4">
            AIバックオフィス業務代行システム<br/>
            <span class="text-indigo-600">Tax-Agent</span>
          </h1>
          <p class="text-xl text-gray-500">
            税理士法人と一般企業をつなぐ、次世代のバックオフィスシステム。AIが日々の入力作業からレポート作成まで自動化します。
          </p>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <RouterLink to="/register/tax-firm" class="bg-indigo-50 border border-indigo-100 p-6 rounded-2xl hover:bg-indigo-100 transition-colors group cursor-pointer text-left block">
            <div class="w-12 h-12 bg-indigo-600 text-white rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <Landmark :size="24" />
            </div>
            <h3 class="font-bold text-gray-900 text-lg mb-2">税理士法人として利用</h3>
            <p class="text-gray-500 text-sm">顧客管理、AIレポート抽出、ダッシュボード機能等</p>
          </RouterLink>

          <RouterLink to="/register/corporate" class="bg-emerald-50 border border-emerald-100 p-6 rounded-2xl hover:bg-emerald-100 transition-colors group cursor-pointer text-left block">
            <div class="w-12 h-12 bg-emerald-600 text-white rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <Building2 :size="24" />
            </div>
            <h3 class="font-bold text-gray-900 text-lg mb-2">一般法人として利用</h3>
            <p class="text-gray-500 text-sm">チャットUIでのデータ連携、仕訳代行、日次レポート等</p>
          </RouterLink>
        </div>
      </div>

      <!-- Login Form Card -->
      <div class="bg-white p-8 sm:p-12 rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-100">
        <div class="text-center mb-8">
          <img src="/logo.png" alt="Tax Agent" class="h-10 w-auto object-contain mx-auto mb-4" />
          <h2 class="text-2xl font-bold text-gray-900">ログイン</h2>
          <p class="text-gray-500 mt-2">Tax-Agentのアカウントにログインしてください</p>
        </div>

        <form @submit.prevent="handleLogin" class="space-y-6">
          <div v-if="errorMsg" class="p-4 bg-red-50 text-red-600 rounded-xl text-sm font-medium border border-red-100 text-center space-y-2">
            <p class="whitespace-pre-line">{{ errorMsg }}</p>
            <button
              v-if="errorMsg.includes('メールアドレスの確認')"
              type="button"
              @click="resendVerificationEmail"
              class="text-indigo-600 underline hover:text-indigo-500 font-semibold text-sm"
            >
              確認メールを再送信する
            </button>
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 mb-2">メールアドレス</label>
            <input 
              v-model="email"
              type="email" 
              required
              class="w-full px-5 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-indigo-600 focus:border-transparent transition-all outline-none"
              placeholder="example@tax-agent.com"
            />
          </div>

          <div>
            <div class="flex items-center justify-between mb-2">
              <label class="block text-sm font-semibold text-gray-700">パスワード</label>
              <a href="#" class="text-sm font-medium text-indigo-600 hover:text-indigo-500 transition-colors">パスワードをお忘れですか？</a>
            </div>
            <div class="relative">
              <input 
                v-model="password"
                :type="showPassword ? 'text' : 'password'" 
                required
                class="w-full pl-5 pr-12 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-indigo-600 focus:border-transparent transition-all outline-none"
                placeholder="••••••••"
              />
              <button 
                type="button" 
                @click="showPassword = !showPassword"
                class="absolute inset-y-0 right-0 pr-4 flex items-center text-gray-400 hover:text-gray-600 focus:outline-none"
              >
                <component :is="showPassword ? EyeOff : Eye" :size="20" />
              </button>
            </div>
          </div>

          <button 
            type="submit" 
            :disabled="isSubmitting"
            class="w-full bg-gray-900 text-white font-bold py-4 rounded-xl hover:bg-gray-800 transition-colors flex items-center justify-center gap-2 group disabled:opacity-50"
          >
            <LogIn class="group-hover:-translate-x-1 transition-transform" />
            {{ isSubmitting ? 'ログイン中...' : 'ログイン' }}
          </button>
        </form>

        <!-- Developer Mode Fast Login Bypass -->
        <div v-if="isDevMode" class="mt-8 pt-8 border-t border-gray-200">
           <div class="px-3 py-2 bg-yellow-50 border border-yellow-200 rounded-xl">
             <p class="text-xs font-bold text-yellow-800 mb-3 flex items-center gap-1">
               <span class="w-2 h-2 rounded-full bg-yellow-500 inline-block animate-pulse"></span>
               開発・テスト用ワンクリックログイン
             </p>
             <div class="flex flex-col gap-2">
                 <button 
                  @click="devLogin('corporate')"
                  class="w-full text-xs bg-white text-emerald-700 font-semibold border border-emerald-200 hover:bg-emerald-50 py-2 rounded-lg transition-colors"
                 >
                   一般法人として入る
                 </button>
                 <button 
                  @click="devLogin('tax_firm')"
                  class="w-full text-xs bg-white text-indigo-700 font-semibold border border-indigo-200 hover:bg-indigo-50 py-2 rounded-lg transition-colors"
                 >
                   税理士法人として入る
                 </button>
             </div>
           </div>
        </div>

        <div class="mt-8 pt-8 border-t border-gray-100 text-center md:hidden">
          <p class="text-sm text-gray-500 mb-4">アカウントをお持ちでない場合はこちら</p>
          <div class="flex flex-col gap-3">
             <RouterLink to="/register/tax-firm" class="text-indigo-600 font-semibold hover:underline">税理士法人として登録</RouterLink>
             <RouterLink to="/register/corporate" class="text-emerald-600 font-semibold hover:underline">一般法人として登録</RouterLink>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>
