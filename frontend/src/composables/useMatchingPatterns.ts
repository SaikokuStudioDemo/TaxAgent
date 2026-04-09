/**
 * useMatchingPatterns.ts - マッチングパターン管理 composable
 */
import { ref } from 'vue';
import { api } from '@/lib/api';

export interface MatchingPattern {
    id: string;
    corporate_id: string;
    client_id: string;
    pattern: string;
    source: 'manual_match' | 'ai_suggest' | 'manual';
    confidence: number;
    created_at: string;
    used_count: number;
}

const SOURCE_LABEL: Record<MatchingPattern['source'], string> = {
    manual_match: '手動消込',
    ai_suggest: 'AI提案',
    manual: '手動',
};

export function sourceLabel(source: MatchingPattern['source']): string {
    return SOURCE_LABEL[source] ?? source;
}

export function useMatchingPatterns() {
    const patterns = ref<MatchingPattern[]>([]);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    const fetchPatterns = async (clientId?: string) => {
        isLoading.value = true;
        error.value = null;
        try {
            const params = clientId ? `?client_id=${clientId}` : '';
            patterns.value = await api.get<MatchingPattern[]>(`/matching-patterns${params}`);
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    const addPattern = async (clientId: string, pattern: string, source: MatchingPattern['source'] = 'manual') => {
        try {
            const created = await api.post<MatchingPattern>('/matching-patterns', {
                client_id: clientId,
                pattern,
                source,
                confidence: 1.0,
            });
            patterns.value.unshift(created);
            return created;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const removePattern = async (patternId: string) => {
        try {
            await api.delete(`/matching-patterns/${patternId}`);
            patterns.value = patterns.value.filter(p => p.id !== patternId);
            return true;
        } catch (e: any) {
            error.value = e.message;
            return false;
        }
    };

    return {
        patterns,
        isLoading,
        error,
        fetchPatterns,
        addPattern,
        removePattern,
    };
}
