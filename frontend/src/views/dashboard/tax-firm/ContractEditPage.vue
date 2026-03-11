<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuth } from '@/composables/useAuth';
import { contractSchema, type ContractFormValues } from '@/lib/utils/validations';
import ContractInfoForm from '@/components/registration/ContractInfoForm.vue';
import UserPermissionList from '@/components/registration/UserPermissionList.vue';
import type { UserData } from '@/components/registration/UserPermissionList.vue';

// Firebase imports for secondary app creation
import { initializeApp } from 'firebase/app';
import { getAuth, createUserWithEmailAndPassword } from 'firebase/auth';
import { doc, setDoc } from 'firebase/firestore';
import { firebaseConfig, db } from '@/lib/firebase/config';

const route = useRoute();
const router = useRouter();
const { currentUser, getToken } = useAuth();

const isSubmitting = ref(false);
const users = ref<UserData[]>([]);
const editModeClientId = ref<string | null>(null);
const isLoadingEdit = ref(false);

const formState = ref<Partial<ContractFormValues>>({
  companyName: '',
  companyUrl: '',
  address: '',
  loginEmail: '',
  loginPassword: '',
  maIntent: 'none'
});

const formErrors = ref<Record<string, string>>({});

onMounted(async () => {
  const clientId = (route.query.id || route.params.id) as string | undefined;
  if (clientId && currentUser.value) {
    editModeClientId.value = clientId;
    isLoadingEdit.value = true;
    try {
      const token = await getToken();
      const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${apiUrl}/users/clients/${clientId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        const clientData = data.data.client;
        
        formState.value.companyName = clientData.companyName || '';
        formState.value.companyUrl = clientData.companyUrl || '';
        formState.value.address = clientData.address || '';
        formState.value.maIntent = clientData.maIntent || 'none';
        formState.value.loginEmail = clientData.loginEmail || '';
        formState.value.loginPassword = 'DummyPassword123!';

        const empData = data.data.employees || [];
        users.value = empData.map((e: any) => ({
          id: e.id || `user-${Date.now()}-${Math.random()}`,
          name: e.name || '',
          email: e.email || '',
          role: e.role || 'staff',
          usageFee: e.usageFee || 0,
          status: 'draft',
          permissions: e.permissions || { dataProcessing: true, reportExtraction: true }
        }));
      }
    } catch (err) {
      console.error("Failed to fetch client for editing", err);
    } finally {
      isLoadingEdit.value = false;
    }
  }
});

const onSubmit = async () => {
    if (!currentUser.value) {
        alert('税理士法人アカウントでログインしてください');
        return;
    }

    formErrors.value = {};
    const validationResult = contractSchema.safeParse(formState.value);
    if (!validationResult.success) {
      const fieldErrors: Record<string, string> = {};
      validationResult.error.issues.forEach(issue => {
        fieldErrors[String(issue.path[0])] = issue.message;
      });
      formErrors.value = fieldErrors;
      alert('入力内容にエラーがあります。赤字の項目をご確認ください。');
      return;
    }

    const data = validationResult.data;
    isSubmitting.value = true;

    try {
        const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

        if (editModeClientId.value) {
            // EDIT MODE -> PUT request
            const token = await getToken();
            const payload = {
                companyName: data.companyName,
                companyUrl: data.companyUrl || null,
                address: data.address,
                maIntent: data.maIntent || null,
            };

            const response = await fetch(`${apiUrl}/users/clients/${editModeClientId.value}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error('Failed to update client');

            // Sync Employees
            const validUsers = users.value.filter(u => u.name.trim() !== '' && u.email.trim() !== '' && u.email.includes('@'));
            if (validUsers.length > 0) {
                const empRes = await fetch(`${apiUrl}/users/clients/${editModeClientId.value}/employees`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(validUsers.map(u => ({
                        name: u.name,
                        email: u.email,
                        role: u.role,
                        usageFee: u.usageFee,
                        permissions: u.permissions
                    })))
                });

                if (!empRes.ok) {
                    try {
                        const errData = await empRes.json();
                        alert(`ユーザー情報の同期に一部失敗しました:\n${errData.detail || JSON.stringify(errData)}`);
                    } catch (e) {
                        alert('ユーザー情報の同期に一部失敗しました。');
                    }
                }
            }

            alert('顧客情報の更新とユーザーの同期が完了しました！');
            router.push('/dashboard/tax-firm/customers');
            return;
        }

        // --- CREATE MODE BELOW ---
        // 1. Create a "Secondary" Firebase app instance to register the client setup
        const secondaryApp = initializeApp(firebaseConfig, `SecondaryApp-${Date.now()}`);
        const secondaryAuth = getAuth(secondaryApp);

        let userCredential;
        try {
            userCredential = await createUserWithEmailAndPassword(
                secondaryAuth,
                data.loginEmail,
                data.loginPassword
            );
        } catch (err: any) {
            if (err.code === 'auth/email-already-in-use') {
                throw new Error('入力されたログイン用メールアドレスは既に登録されています。別のメールアドレスをご確認ください。');
            }
            throw err;
        }

        // 2. Save PII to Firestore immediately
        const uid = userCredential.user.uid;
        await setDoc(doc(db, 'corporates', uid), {
            companyName: data.companyName,
            companyUrl: data.companyUrl || null,
            address: data.address,
            maIntent: data.maIntent || null,
            loginEmail: data.loginEmail,
            corporateType: "corporate",
            createdAt: new Date().toISOString()
        });

        // 3. Get the JWT Token for the NEW user
        const idToken = await userCredential.user.getIdToken();

        // 4. Prepare payload for FastAPI (NO PII allowed)
        const payload = {
            corporateType: 'corporate',
            companyUrl: data.companyUrl || null,
            maIntent: data.maIntent || null,
            planId: 'plan-tax-firm-managed',
            monthlyFee: 0,
            advising_tax_firm_id: currentUser.value.uid,
            selectedOptions: [],
            sales_agent_id: null,
            referrer_id: null
        };

        const response = await fetch(`${apiUrl}/users/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${idToken}`
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'バックエンドへの顧客データ保存に失敗しました');
        }

        // 5. Submit Employees to Backend using the newly created secondary user's ID Token!
        const validUsers = users.value.filter(u => u.name.trim() !== '' && u.email.trim() !== '' && u.email.includes('@'));

        if (validUsers.length > 0) {
            try {
                const employeesResponse = await fetch(`${apiUrl}/users/employees`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${idToken}`
                    },
                    body: JSON.stringify(validUsers.map(u => ({
                        email: u.email,
                        name: u.name,
                        role: u.role,
                        usageFee: u.usageFee,
                        permissions: u.permissions
                    })))
                });

                if (!employeesResponse.ok) {
                    console.error("Failed to post employees to backend.");
                } else {
                    const empData = await employeesResponse.json().catch(() => ({}));
                    const failedEmps = empData.data?.filter((e: any) => e.status === 'failed') || [];
                    if (failedEmps.length > 0) {
                        const failedEmails = failedEmps.map((e: any) => e.email).join('\n');
                        alert(`顧客の登録は完了しましたが、以下のメールアドレスのアカウント作成に失敗しました（既に登録されている可能性があります）：\n${failedEmails}`);
                    }
                }
            } catch (err) {
                console.error("Employee sync error:", err);
            }
        }

        // Clean up: sign out the secondary app so nothing leaks
        await secondaryAuth.signOut();

        alert('顧客の登録が完了しました！顧客一覧に戻ります。');
        router.push('/dashboard/tax-firm/customers');

    } catch (error) {
        console.error('Client Registration Error:', error);
        const errMessage = error instanceof Error ? error.message : 'Unknown error occurred';
        alert(`登録エラー: ${errMessage}`);
    } finally {
        isSubmitting.value = false;
    }
};
</script>

<template>
  <div class="p-8">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-gray-900 mb-2">
        {{ editModeClientId ? '顧客情報を編集' : '契約情報編集/追加' }}
      </h1>
      <p class="text-gray-500">
        {{ editModeClientId ? '既存顧客の契約内容を編集します。メールアドレスの変更はセキュリティ上、サポートにお問い合わせください。' : '新規の顧客（一般法人）を登録します。' }}
      </p>
    </div>

    <div class="max-w-5xl">
      <div v-if="isLoadingEdit" class="py-12 flex justify-center text-gray-400">
        顧客データを読み込んでいます...
      </div>
      
      <form v-else @submit.prevent="onSubmit" class="space-y-8">
        <ContractInfoForm
          :isEditMode="!!editModeClientId"
          v-model:formState="formState"
          :errors="formErrors"
        />

        <UserPermissionList v-model:users="users" :showUsageFee="true" />

        <div class="flex justify-end pt-4">
          <button
            type="submit"
            :disabled="isSubmitting"
            class="bg-indigo-600 text-white font-bold py-3 px-8 rounded-xl hover:bg-indigo-700 shadow-md transition-colors disabled:opacity-50"
          >
            {{ isSubmitting ? '保存中...' : 'この内容で保存する' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
