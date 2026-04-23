/**
 * usePlans.ts
 * プラン・オプション情報を system_settings API から取得する composable。
 * Task#32: mockData.ts のハードコードから system_settings コレクションへの移行。
 */
import { ref, onMounted } from 'vue';

export function usePlans() {
  const plans = ref<any[]>([]);
  const options = ref<any[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  const fetchPlans = async () => {
    isLoading.value = true;
    error.value = null;
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

      // ⑤ plans と options を Promise.all で並列取得
      const [plansRes, optionsRes] = await Promise.all([
        fetch(`${apiUrl}/system-settings/plans`),
        fetch(`${apiUrl}/system-settings/options`),
      ]);

      if (plansRes.ok) {
        plans.value = await plansRes.json();
      } else {
        throw new Error('plans fetch failed');
      }

      if (optionsRes.ok) {
        options.value = await optionsRes.json();
      }
    } catch (e) {
      error.value = 'プラン情報の取得に失敗しました';
    } finally {
      isLoading.value = false;
    }
  };

  onMounted(fetchPlans);

  return { plans, options, isLoading, error, fetchPlans };
}
