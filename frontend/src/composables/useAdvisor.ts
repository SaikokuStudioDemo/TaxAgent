import { ref } from 'vue';
import { api } from '@/lib/api';

export function useAdvisor() {
    const messages = ref<{ role: 'ai' | 'user'; text: string }[]>([]);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    const initChat = () => {
        if (messages.value.length === 0) {
            messages.value.push({
                role: 'ai',
                text: 'こんにちは。Tax-Agent AIアドバイザーです。現在の経理状況に基づいたアドバイスが可能です。何かお困りですか？'
            });
        }
    };

    const sendMessage = async (query: string) => {
        if (!query.trim()) return;
        
        messages.value.push({ role: 'user', text: query });
        isLoading.value = true;
        error.value = null;

        try {
            const res = await api.post<{ response: string }>('/advisor/chat', { query });
            messages.value.push({ role: 'ai', text: res.response });
        } catch (err: any) {
            error.value = err.message || 'Error communicating with AI';
            messages.value.push({ 
                role: 'ai', 
                text: '申し訳ありません。現在ご質問にお答えすることができません。' 
            });
        } finally {
            isLoading.value = false;
        }
    };

    return {
        messages,
        isLoading,
        error,
        initChat,
        sendMessage
    };
}
