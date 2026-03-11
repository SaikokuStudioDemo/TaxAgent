import { ref } from 'vue';
import { onAuthStateChanged, User, signOut as firebaseSignOut } from 'firebase/auth';
import { auth } from '@/lib/firebase/config';
import { useRouter } from 'vue-router';

const currentUser = ref<User | null>(null);
const userProfile = ref<any>(null);
const isLoading = ref(true);

export function useAuth() {
    const router = useRouter();

    const enableLocalBypass = (role: 'corporate' | 'tax_firm') => {
        localStorage.setItem('DEV_BYPASS_AUTH', 'true');
        userProfile.value = {
            type: role,
            data: {
                name: 'Test Setup User',
                email: 'test@example.com',
                companyName: 'Bypass Corporation'
            }
        };
        isLoading.value = false;
        router.push(role === 'corporate' ? '/dashboard/corporate' : '/dashboard/tax-firm');
    };

    // Initialize Auth Listener
    const initAuth = () => {
        onAuthStateChanged(auth, async (user) => {
            currentUser.value = user;
            if (user) {
                await fetchProfile(user);
            } else {
                userProfile.value = null;
            }
            isLoading.value = false;
        });
    };

    const fetchProfile = async (user: User) => {
        try {
            const token = await user.getIdToken();
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

    const getToken = async (): Promise<string | null> => {
        if (currentUser.value) {
            return await currentUser.value.getIdToken();
        }
        return null;
    };

    const signOut = async () => {
        localStorage.removeItem('DEV_BYPASS_AUTH');
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
        enableLocalBypass
    };
}
