import { ref, computed } from 'vue';
import { onAuthStateChanged, User, signOut as firebaseSignOut } from 'firebase/auth';
import { auth } from '@/lib/firebase/config';
import { useRouter } from 'vue-router';
import { getRoleLabel } from '@/lib/i18n/roles';

export const currentUser = ref<User | null>(null);
export const userProfile = ref<any>(null);
export const isLoading = ref(true);

const DEV_AUTH_TOKEN_KEY = 'DEV_AUTH_TOKEN';

// ─── モジュールレベル computed（userProfile が確定したら自動更新） ───────────

export const displayName = computed(() => {
  if (!userProfile.value) return '読込中...';
  return userProfile.value.data?.name || userProfile.value.data?.companyName || '';
});

export const userRole = computed(() => {
  if (!userProfile.value) return null;
  if (userProfile.value.type !== 'employee') return 'admin';
  return userProfile.value.data?.role || 'staff';
});

export const displayRole = computed(() => {
  if (!userProfile.value) return '';
  const type = userProfile.value.type;
  if (type === 'corporate') return getRoleLabel('corporate');
  if (type === 'tax_firm') return getRoleLabel('tax_firm');
  return getRoleLabel(userProfile.value.data?.role || 'staff');
});

export const corporateId = computed(() => {
  if (!userProfile.value) return null;
  if (userProfile.value.type === 'employee') {
    return userProfile.value.data?.corporate_id || null;
  }
  return userProfile.value.data?._id || null;
});

export const advisingTaxFirmId = computed(() => {
  if (!userProfile.value) return null;
  return userProfile.value.data?.advising_tax_firm_id || null;
});

export const corporateType = computed(() => {
  if (!userProfile.value) return null;
  if (userProfile.value.type === 'employee') {
    return userProfile.value.parent_type || null;
  }
  return userProfile.value.data?.corporateType || null;
});

export const isAccountingOrAbove = computed(() => {
  if (!userProfile.value) return false;
  if (userProfile.value.type !== 'employee') return true;
  const role = userProfile.value.data?.role || 'staff';
  return ['admin', 'manager', 'accounting'].includes(role);
});

export const isAdmin = computed(() => {
  if (!userProfile.value) return false;
  if (userProfile.value.type !== 'employee') return true;
  return userProfile.value.data?.role === 'admin';
});

// ─── モジュールレベルのプロファイル取得（composable 外から呼べる） ───────────

const _fetchProfile = async (token: string) => {
  try {
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
    const res = await fetch(`${apiUrl}/users/me`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (res.ok) {
      userProfile.value = await res.json();
    }
  } catch (err) {
    console.error('Failed to fetch profile', err);
  }
};

// ─── initAuth（モジュールレベルエクスポート。main.ts から呼ぶ） ───────────────
// DEV / Firebase いずれも isLoading = false になる前にプロファイル取得を完了させる。

let _authListenerInitialized = false;

export function initAuth() {
  if (_authListenerInitialized) return;
  _authListenerInitialized = true;

  onAuthStateChanged(auth, async (user) => {
    currentUser.value = user;
    if (user) {
      await _fetchProfile(await user.getIdToken());
    } else {
      const devToken = localStorage.getItem(DEV_AUTH_TOKEN_KEY);
      if (devToken) {
        await _fetchProfile(devToken);
      } else {
        userProfile.value = null;
      }
    }
    isLoading.value = false;
  });
}

export function useAuth() {
  const router = useRouter();

  const devLogin = async (role: 'corporate' | 'tax_firm') => {
    const token = role === 'corporate' ? 'test-token' : 'tax-test-token';
    localStorage.setItem(DEV_AUTH_TOKEN_KEY, token);
    isLoading.value = true;
    await _fetchProfile(token);
    isLoading.value = false;
    router.push(role === 'corporate' ? '/dashboard/corporate' : '/dashboard/tax-firm');
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
    currentUser,
    userProfile,
    isLoading,
    initAuth,
    getToken,
    signOut,
    devLogin,
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
