<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { api } from '@/lib/api';
import { auth, db } from '@/lib/firebase/config';
import { createUserWithEmailAndPassword, sendEmailVerification } from 'firebase/auth';
import { doc, setDoc } from 'firebase/firestore';
import ContractInfoForm from '@/components/registration/ContractInfoForm.vue';
import PlanSelectionCard from '@/components/registration/PlanSelectionCard.vue';
import UserPermissionList from '@/components/registration/UserPermissionList.vue';
import PricingSummary from '@/components/registration/PricingSummary.vue';
import { contractSchema, type ContractFormValues } from '@/lib/utils/validations';
import type { UserData } from '@/components/registration/UserPermissionList.vue';
import { calculateMonthlyFee } from '@/lib/utils/pricing';

const router = useRouter();
const route = useRoute();

// 招待トークン関連（Task#5 の onMounted で設定される）
const invitationToken = ref<string | null>(null);
const invitationTaxFirmId = ref<string | null>(null);

const selectedPlanId = ref<string>('plan_standard');
const selectedOptions = ref<string[]>([]);
const isSubmitting = ref(false);
const users = ref<UserData[]>([]);
const departments = ref<any[]>([]);

const fetchDepartments = async () => {
  try {
    const data = await api.get<any[]>('/departments');
    departments.value = data.map((d: any) => ({
      id: d.id,
      label: d.name,
      groups: (d.groups || []).map((g: any) => ({ id: g.id, label: g.name }))
    }));
  } catch (e) {
    // During registration the corporate doesn't exist yet, empty is fine
    console.warn('Could not fetch departments (expected during registration):', e);
  }
};

onMounted(async () => {
  fetchDepartments();

  // 招待トークンの処理
  const token = route.query.token as string | undefined;
  if (token) {
    invitationToken.value = token;
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
    try {
      const res = await fetch(`${apiUrl}/invitations/verify?token=${token}`);
      const data = await res.json();
      if (data.valid) {
        invitationTaxFirmId.value = data.tax_firm_id;
        if (data.invited_email) {
          formState.value.loginEmail = data.invited_email;
        }
      } else {
        invitationToken.value = null;
        alert('この招待リンクは無効または期限切れです。税理士法人に再発行を依頼してください。');
      }
    } catch (e) {
      console.error('招待トークン検証エラー:', e);
    }
  }
});

const formState = ref<Partial<ContractFormValues>>({
  companyName: '',
  companyUrl: '',
  address: '',
  loginEmail: '',
  loginPassword: '',
  phone: '',
  registrationNumber: ''
});

const formErrors = ref<Record<string, string>>({});

const onSubmit = async () => {
  try {
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

    // 1. Create User in Firebase Auth
    let userCredential;
    try {
      userCredential = await createUserWithEmailAndPassword(auth, data.loginEmail, data.loginPassword);
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
      loginEmail: data.loginEmail,
      phone: data.phone || null,
      registrationNumber: data.registrationNumber || null,
      corporateType: "corporate",
      createdAt: new Date().toISOString()
    });

    // 3. Send email verification (failure is non-fatal)
    try {
      await sendEmailVerification(userCredential.user);
    } catch (err) {
      console.error('Failed to send verification email:', err);
    }

    // 4. Get the JWT Token
    const idToken = await userCredential.user.getIdToken();

    // 5. Prepare payload for FastAPI
    const payload = {
      corporateType: "corporate",
      companyUrl: data.companyUrl || null,
      planId: selectedPlanId.value,
      selectedOptions: selectedOptions.value,
      monthlyFee: calculateMonthlyFee(selectedPlanId.value, selectedOptions.value),
      sales_agent_id: null,
      referrer_id: null,
      advising_tax_firm_id: invitationTaxFirmId.value || null,
      companyName: data.companyName,
      phone: data.phone || null,
      address: data.address,
      registrationNumber: data.registrationNumber || null
    };

    // 6. Send to FastAPI Backend
    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
    const response = await fetch(`${apiUrl}/users/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to register with backend');
    }

    // 7. Submit Employees to Backend
    const validUsers = users.value.filter(u => u.name.trim() !== '' && u.email.trim() !== '' && u.email.includes('@'));

    if (validUsers.length > 0) {
      const employeesResponse = await fetch(`${apiUrl}/users/employees`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${idToken}`
        },
        body: JSON.stringify(validUsers)
      });

      if (!employeesResponse.ok) {
        console.error("Failed to post employees to backend.");
      } else {
        const empData = await employeesResponse.json();
        const failedEmps = empData.data?.filter((e: any) => e.status === 'failed') || [];
        if (failedEmps.length > 0) {
          const failedEmails = failedEmps.map((e: any) => e.email).join('\n');
          alert(`法人の登録は完了しましたが、以下のメールアドレスのアカウント作成に失敗しました（既に登録されている可能性があります）：\n${failedEmails}`);
        }
      }
    }

    // 8. 招待トークンを使用済みにする（失敗しても登録は完了扱い）
    if (invitationToken.value) {
      const acceptUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
      await fetch(`${acceptUrl}/invitations/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: invitationToken.value })
      }).catch(e => console.error('招待トークンのacceptに失敗しました:', e));
    }

    // 9. Success! Redirect to dashboard
    alert('登録が完了しました。\n確認メールを送信しましたので、メール内のリンクをクリックしてメールアドレスの確認を完了してください。');
    router.push('/dashboard/corporate');

  } catch (error) {
    // Firebase Auth ロールバック（APIエラー時にゴミユーザーが残らないよう削除）
    if (userCredential?.user) {
      try {
        await userCredential.user.delete();
        console.log('Firebase Auth user rolled back successfully');
      } catch (deleteError) {
        console.error('Failed to rollback Firebase Auth user:', deleteError);
      }
    }
    console.error('Registration Error:', error);
    const errMessage = error instanceof Error ? error.message : 'Unknown error occurred';
    alert(`登録エラー: ${errMessage}`);
  } finally {
    isSubmitting.value = false;
  }
};

const handleToggleOption = (id: string) => {
  if (selectedOptions.value.includes(id)) {
    selectedOptions.value = selectedOptions.value.filter(o => o !== id);
  } else {
    selectedOptions.value.push(id);
  }
};
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 pb-24">
    <!-- Page Header -->
    <div class="mb-10">
      <img src="/logo.png" alt="Tax Agent" class="h-10 w-auto object-contain mb-6" />
      <h1 class="text-3xl font-extrabold text-gray-900 tracking-tight mb-3">一般法人 新規登録</h1>
      <div class="w-20 h-1 bg-emerald-500 rounded-full mb-4"></div>
      <p class="text-gray-600 max-w-2xl text-lg">
        Tax-Agentの利用を開始するためのアカウント作成と初期設定を行います。法人特化の機能をご利用いただけます。
      </p>
    </div>

    <form @submit.prevent="onSubmit" class="flex flex-col lg:flex-row gap-8 items-start">
      <!-- Main Content Form -->
      <div class="w-full lg:w-2/3">
        <ContractInfoForm
          salesAgentName="佐藤 花子（第二営業部）"
          referrerName="〇〇コンサルティング株式会社"
          v-model:formState="formState"
          :errors="formErrors"
        />
        <PlanSelectionCard
          :selectedPlanId="selectedPlanId"
          :selectedOptions="selectedOptions"
          @selectPlan="selectedPlanId = $event"
          @toggleOption="handleToggleOption"
        />
        <UserPermissionList v-model:users="users" :departments="departments" />

        <!-- Mobile Submit Button -->
        <div class="mt-8 lg:hidden block">
          <button
            type="submit"
            :disabled="isSubmitting"
            class="w-full bg-indigo-600 text-white font-bold py-4 px-6 rounded-xl hover:bg-indigo-700 shadow-md transition-colors disabled:opacity-50"
          >
            {{ isSubmitting ? '登録処理中...' : 'この内容で登録する' }}
          </button>
        </div>
      </div>

      <!-- Sidebar Summary (Sticky) -->
      <div class="w-full lg:w-1/3 hidden lg:block sticky top-24 space-y-6">
        <PricingSummary
          :selectedPlanId="selectedPlanId"
          :selectedOptions="selectedOptions"
        />

        <!-- Desktop Submit Button -->
        <button
          type="submit"
          :disabled="isSubmitting"
          class="w-full bg-indigo-600 text-white font-bold py-4 px-6 rounded-xl hover:bg-indigo-700 shadow-lg shadow-indigo-600/20 transition-all hover:-translate-y-0.5 disabled:opacity-50 disabled:hover:-translate-y-0"
        >
          {{ isSubmitting ? '登録処理中...' : 'この内容で登録する' }}
        </button>
      </div>
    </form>
  </div>
</template>
