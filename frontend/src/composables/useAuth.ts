import { ref } from 'vue';
import { onAuthStateChanged, User, signOut as firebaseSignOut } from 'firebase/auth';
import { auth } from '@/lib/firebase/config';
import { useRouter } from 'vue-router';

const currentUser = ref<User | null>(null);
const userProfile = ref<any>(null);
const isLoading = ref(true);

// Key used to store the dev auth token in localStorage
const DEV_AUTH_TOKEN_KEY = 'DEV_AUTH_TOKEN';

// ページリフレッシュ時もuserProfileを復元するため、
// モジュールロード時にDEVトークンがあれば自動でプロファイル取得する
const _devToken = localStorage.getItem(DEV_AUTH_TOKEN_KEY);
if (_devToken && !userProfile.value) {
  const _apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
  fetch(`${_apiUrl}/users/me`, { headers: { Authorization: `Bearer ${_devToken}` } })
    .then(res => (res.ok ? res.json() : null))
    .then(data => { if (data) { userProfile.value = data; isLoading.value = false; } })
    .catch(() => { isLoading.value = false; });
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

    // Initialize Auth Listener
    const initAuth = () => {
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
        currentUser,
        userProfile,
        isLoading,
        initAuth,
        getToken,
        signOut,
        devLogin,
    };
}
