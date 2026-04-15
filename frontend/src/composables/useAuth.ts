import { ref, computed } from 'vue';
import { onAuthStateChanged, User, signOut as firebaseSignOut } from 'firebase/auth';
import { auth } from '@/lib/firebase/config';
import { useRouter } from 'vue-router';
import { getRoleLabel } from '@/lib/i18n/roles';

export const currentUser = ref<User | null>(null);
export const userProfile = ref<any>(null);
export const isLoading = ref(true);

// Key used to store the dev auth token in localStorage
const DEV_AUTH_TOKEN_KEY = 'DEV_AUTH_TOKEN';

// ─── モジュールレベル computed（userProfile が確定したら自動更新） ───────────

// ユーザーの表示名（法人名 or 従業員名）
// バックエンドは data.name を返す。data.companyName はフォールバック。
export const displayName = computed(() => {
  if (!userProfile.value) return '読込中...';
  return userProfile.value.data?.name || userProfile.value.data?.companyName || '';
});

// ロール（英語キー。法人代表・税理士法人代表は 'admin' 固定）
export const userRole = computed(() => {
  if (!userProfile.value) return null;
  if (userProfile.value.type !== 'employee') return 'admin';
  return userProfile.value.data?.role || 'staff';
});

// ロールの表示名（日本語ラベル。将来 i18n 対応時はここを変更）
export const displayRole = computed(() => {
  if (!userProfile.value) return '';
  const type = userProfile.value.type;
  if (type === 'corporate') return getRoleLabel('corporate');
  if (type === 'tax_firm') return getRoleLabel('tax_firm');
  return getRoleLabel(userProfile.value.data?.role || 'staff');
});

// 法人の ObjectId（_id）
export const corporateId = computed(() => {
  if (!userProfile.value) return null;
  if (userProfile.value.type === 'employee') {
    return userProfile.value.data?.corporate_id || null;
  }
  return userProfile.value.data?._id || null;
});

// 紐付く税理士法人の UID（配下法人のみ。なければ null）
export const advisingTaxFirmId = computed(() => {
  if (!userProfile.value) return null;
  return userProfile.value.data?.advising_tax_firm_id || null;
});

// corporateType（'tax_firm' / 'corporate'）
export const corporateType = computed(() => {
  if (!userProfile.value) return null;
  if (userProfile.value.type === 'employee') {
    return userProfile.value.parent_type || null;
  }
  return userProfile.value.data?.corporateType || null;
});

// 経理以上かどうか（消込・CSV 出力等の権限判定用）
export const isAccountingOrAbove = computed(() => {
  if (!userProfile.value) return false;
  if (userProfile.value.type !== 'employee') return true;
  const role = userProfile.value.data?.role || 'staff';
  return ['admin', 'manager', 'accounting'].includes(role);
});

// 管理者かどうか（設定変更等の権限判定用）
export const isAdmin = computed(() => {
  if (!userProfile.value) return false;
  if (userProfile.value.type !== 'employee') return true;
  return userProfile.value.data?.role === 'admin';
});

// onAuthStateChanged リスナーが設定済みかどうかのフラグ
let _authListenerInitialized = false;

// ページリフレッシュ時もuserProfileを復元するため、
// モジュールロード時にDEVトークンがあれば自動でプロファイル取得する
// ただし isLoading は変更しない（initAuth() に委ねる）
const _devToken = localStorage.getItem(DEV_AUTH_TOKEN_KEY);
if (_devToken && !userProfile.value) {
  const _apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
  fetch(`${_apiUrl}/users/me`, { headers: { Authorization: `Bearer ${_devToken}` } })
    .then(res => (res.ok ? res.json() : null))
    .then(data => { if (data) { userProfile.value = data; } })
    .catch(() => {});
}

export function useAuth() {
    const router = useRouter();

    const fetchProfileWithToken = async (token: string) => {
        try {
            const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
            const res = await fetch(`${apiUrl}/users/me`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (res.ok) {
                userProfile.value = await res.json();
            }
        } catch (err) {
            console.error("Failed to fetch profile", err);
        }
    };

    // Development one-click login: uses test-token against the real backend
    const devLogin = async (role: 'corporate' | 'tax_firm') => {
        const token = role === 'corporate' ? 'test-token' : 'tax-test-token';
        localStorage.setItem(DEV_AUTH_TOKEN_KEY, token);
        isLoading.value = true;
        await fetchProfileWithToken(token);
        isLoading.value = false;
        router.push(role === 'corporate' ? '/dashboard/corporate' : '/dashboard/tax-firm');
    };

    // Initialize Auth Listener（二重登録防止フラグつき）
    const initAuth = () => {
        if (_authListenerInitialized) return;
        _authListenerInitialized = true;

        onAuthStateChanged(auth, async (user) => {
            currentUser.value = user;
            if (user) {
                await fetchProfileWithToken(await user.getIdToken());
            } else if (!localStorage.getItem(DEV_AUTH_TOKEN_KEY)) {
                userProfile.value = null;
            }
            isLoading.value = false;
        });
    };

    const getToken = async (): Promise<string | null> => {
        const devToken = localStorage.getItem(DEV_AUTH_TOKEN_KEY);
        if (devToken) return devToken;
        if (currentUser.value) return await currentUser.value.getIdToken();
        return null;
    };

    const signOut = async () => {
        localStorage.removeItem(DEV_AUTH_TOKEN_KEY);
        await firebaseSignOut(auth);
        userProfile.value = null;
        router.push('/');
    };

    return {
        // 既存
        currentUser,
        userProfile,
        isLoading,
        initAuth,
        getToken,
        signOut,
        devLogin,
        // 新規追加
        displayName,
        displayRole,
        userRole,
        corporateId,
        advisingTaxFirmId,
        corporateType,
        isAccountingOrAbove,
        isAdmin,
    };
}
