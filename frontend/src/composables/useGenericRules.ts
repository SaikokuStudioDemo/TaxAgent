/**
 * useGenericRules.ts
 * ルール系 CRUD composable の共通ファクトリ
 *
 * useMatchingRules / useJournalRules / useApprovalRules はすべてこのファクトリを利用する。
 * エンドポイントパスと型だけが異なり、ロジックは同一のため一本化。
 */
import { ref, type Ref } from 'vue';
import { api } from '@/lib/api';

export function useGenericRules<T extends { id: string; created_at: string }>(
    endpoint: string,
    options?: { filterParam?: string },
) {
    const rules = ref([]) as Ref<T[]>;
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    /** ルール一覧を取得する。filterValue を渡すと `?{filterParam}=value` を付加する */
    const fetchRules = async (filterValue?: string) => {
        isLoading.value = true;
        error.value = null;
        try {
            const qs =
                filterValue && options?.filterParam
                    ? `?${options.filterParam}=${encodeURIComponent(filterValue)}`
                    : '';
            rules.value = await api.get<T[]>(`${endpoint}${qs}`);
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    /** ルールを新規作成する。エラーは呼び出し元に propagate する */
    const createRule = async (data: Omit<T, 'id' | 'created_at'>) => {
        const created = await api.post<T>(endpoint, data);
        rules.value.unshift(created);
        return created;
    };

    /** ルールを更新する。エラーは呼び出し元に propagate する */
    const updateRule = async (id: string, data: Partial<T>) => {
        const updated = await api.patch<T>(`${endpoint}/${id}`, data);
        const idx = rules.value.findIndex(r => r.id === id);
        if (idx !== -1) rules.value[idx] = updated;
        return updated;
    };

    /** ルールを削除する。成功時 true、失敗時 false を返す */
    const deleteRule = async (id: string) => {
        try {
            await api.delete(`${endpoint}/${id}`);
            rules.value = rules.value.filter(r => r.id !== id);
            return true;
        } catch (e: any) {
            error.value = e.message;
            return false;
        }
    };

    return { rules, isLoading, error, fetchRules, createRule, updateRule, deleteRule };
}
