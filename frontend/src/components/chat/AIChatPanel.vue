<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue';
import { MessageSquare, X, Send, Bot, User, Loader2 } from 'lucide-vue-next';
import { api } from '@/lib/api';

const isOpen = ref(false);
const query = ref('');
const isLoading = ref(false);
const messages = ref<{ role: 'ai' | 'user'; text: string }[]>([]);
const chatContainer = ref<HTMLElement | null>(null);

const toggleChat = () => {
    isOpen.value = !isOpen.value;
    if (isOpen.value && messages.value.length === 0) {
        messages.value.push({
            role: 'ai',
            text: 'こんにちは！Tax-Agent AIアドバイザーです。現在の経理状況の確認や、税務に関する一般的なご質問など、何でもお手伝いします。'
        });
    }
};

const scrollToBottom = async () => {
    await nextTick();
    if (chatContainer.value) {
        chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
    }
};

const handleSend = async () => {
    if (!query.value.trim() || isLoading.value) return;

    const userMsg = query.value;
    messages.value.push({ role: 'user', text: userMsg });
    query.value = '';
    isLoading.value = true;
    scrollToBottom();

    try {
        const res = await api.post<{ response: string }>('/advisor/chat', { query: userMsg });
        messages.value.push({ role: 'ai', text: res.response });
    } catch (err) {
        messages.value.push({ 
            role: 'ai', 
            text: '申し訳ありません。アドバイザーとの接続に問題が発生しました。' 
        });
    } finally {
        isLoading.value = false;
        scrollToBottom();
    }
};
</script>

<template>
    <div class="fixed bottom-6 right-6 z-50 flex flex-col items-end">
        <!-- Chat Window -->
        <div v-if="isOpen" 
             class="mb-4 w-80 sm:w-96 h-[500px] bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden animate-in slide-in-from-bottom-4 duration-300">
            <!-- Header -->
            <div class="bg-indigo-600 p-4 flex items-center justify-between text-white">
                <div class="flex items-center gap-2">
                    <div class="w-8 h-8 rounded-lg bg-white/20 flex items-center justify-center">
                        <Bot class="w-5 h-5" />
                    </div>
                    <div>
                        <h3 class="font-bold text-sm">Tax-Agent AI Advisor</h3>
                        <p class="text-[10px] text-indigo-100 italic">Powered by Gemini 3.1 Pro</p>
                    </div>
                </div>
                <button @click="toggleChat" class="p-1 hover:bg-white/10 rounded-full transition-colors">
                    <X class="w-5 h-5" />
                </button>
            </div>

            <!-- Messages Area -->
            <div ref="chatContainer" class="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50">
                <div v-for="(msg, i) in messages" :key="i" 
                     :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']">
                    <div :class="[
                        'max-w-[85%] p-3 rounded-2xl text-sm shadow-sm',
                        msg.role === 'user' 
                            ? 'bg-indigo-600 text-white rounded-tr-none' 
                            : 'bg-white text-slate-700 border border-slate-200 rounded-tl-none'
                    ]">
                        {{ msg.text }}
                    </div>
                </div>
                <div v-if="isLoading" class="flex justify-start">
                    <div class="bg-white p-3 rounded-2xl rounded-tl-none border border-slate-200 shadow-sm flex items-center gap-2">
                        <Loader2 class="w-4 h-4 animate-spin text-indigo-600" />
                        <span class="text-xs text-slate-500 italic">Thinking...</span>
                    </div>
                </div>
            </div>

            <!-- Input Area -->
            <div class="p-4 bg-white border-t border-slate-100">
                <form @submit.prevent="handleSend" class="flex gap-2">
                    <input 
                        v-model="query"
                        type="text" 
                        placeholder="質問を入力してください..." 
                        class="flex-1 bg-slate-100 border-none rounded-xl px-4 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                    />
                    <button 
                        type="submit"
                        :disabled="!query.trim() || isLoading"
                        class="w-10 h-10 bg-indigo-600 text-white rounded-xl flex items-center justify-center hover:bg-indigo-700 disabled:opacity-50 disabled:hover:bg-indigo-600 transition-colors shadow-lg shadow-indigo-200"
                    >
                        <Send class="w-4 h-4" />
                    </button>
                </form>
            </div>
        </div>

        <!-- Float Toggle Button -->
        <button 
            @click="toggleChat"
            class="w-14 h-14 bg-indigo-600 text-white rounded-full flex items-center justify-center shadow-xl hover:bg-indigo-700 hover:scale-110 transition-all active:scale-95 group"
        >
            <MessageSquare v-if="!isOpen" class="w-6 h-6" />
            <X v-else class="w-6 h-6" />
            <span class="absolute right-full mr-4 bg-slate-800 text-white text-[10px] px-2 py-1 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap hidden sm:block">
                AIアドバイザーに相談
            </span>
        </button>
    </div>
</template>

<style scoped>
.animate-in {
    animation: slide-up 0.3s ease-out;
}
@keyframes slide-up {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}
</style>
