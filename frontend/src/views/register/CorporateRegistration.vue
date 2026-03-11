<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { auth, db } from '@/lib/firebase/config';
import { createUserWithEmailAndPassword } from 'firebase/auth';
import { doc, setDoc } from 'firebase/firestore';
import ContractInfoForm from '@/components/registration/ContractInfoForm.vue';
import PlanSelectionCard from '@/components/registration/PlanSelectionCard.vue';
import UserPermissionList from '@/components/registration/UserPermissionList.vue';
import PricingSummary from '@/components/registration/PricingSummary.vue';
import { contractSchema, type ContractFormValues } from '@/lib/utils/validations';
import type { UserData } from '@/components/registration/UserPermissionList.vue';
import { calculateMonthlyFee } from '@/lib/utils/pricing';

const router = useRouter();

const selectedPlanId = ref<string>('plan-standard');
const selectedOptions = ref<string[]>([]);
const isSubmitting = ref(false);
const users = ref<UserData[]>([]);

const formState = ref<Partial<ContractFormValues>>({
  companyName: '',
  companyUrl: '',
  address: '',
  loginEmail: '',
  loginPassword: '',
  maIntent: 'none'
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
      maIntent: data.maIntent || null,
      loginEmail: data.loginEmail,
      corporateType: "corporate",
      createdAt: new Date().toISOString()
    });

    // 3. Get the JWT Token
    const idToken = await userCredential.user.getIdToken();

    // 4. Prepare payload for FastAPI (NO PII allowed)
    const payload = {
      corporateType: "corporate",
      companyUrl: data.companyUrl || null,
      maIntent: data.maIntent || null,
      planId: selectedPlanId.value,
      selectedOptions: selectedOptions.value,
      monthlyFee: calculateMonthlyFee(selectedPlanId.value, selectedOptions.value),
      sales_agent_id: null,
      referrer_id: null,
      advising_tax_firm_id: null
    };

    // 4. Send to FastAPI Backend
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

    // 5. Submit Employees to Backend
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

    // 6. Success! Redirect to dashboard
    alert('登録が完了しました！ダッシュボードへ移動します。');
    router.push('/dashboard/corporate');

  } catch (error) {
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
        <UserPermissionList v-model:users="users" />

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
