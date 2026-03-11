<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { FileText, Cpu, CheckCircle2, AlertCircle, Loader2, Play } from 'lucide-vue-next';
import { api } from '@/lib/api';

const samples = ref<any[]>([]);
const isLoading = ref(false);
const processingFile = ref<string | null>(null);
const results = ref<any>(null);

const fetchSamples = async () => {
    isLoading.value = true;
    try {
        const res = await api.get<{ samples: any[] }>('/ai-training/samples');
        samples.value = res.samples;
    } catch (err) {
        console.error("Failed to fetch samples", err);
    } finally {
        isLoading.value = false;
    }
};

const handleTrain = async (filename: string) => {
    processingFile.value = filename;
    results.value = null;
    try {
        const res = await api.post<any>('/ai-training/train', { 
            filename,
            vendor_name: "サンプル株式会社"
        });
        results.value = res;
    } catch (err) {
        console.error("Training failed", err);
    } finally {
        processingFile.value = null;
    }
};

onMounted(fetchSamples);
</script>

<template>
    <div class="space-y-6">
        <header>
            <h1 class="text-2xl font-bold text-slate-800 flex items-center gap-2">
                <Cpu class="w-6 h-6 text-indigo-600" />
                AI 請求書トレーニング (Gemini 3.1)
            </h1>
            <p class="text-slate-500 mt-1">提供された請求書サンプルを使用して、AIの抽出能力をテストおよび学習させます。</p>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Samples List -->
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="p-4 border-b border-slate-100 flex justify-between items-center">
                    <h2 class="font-bold text-slate-700">利用可能なサンプル (InvoiceSample/)</h2>
                    <button @click="fetchSamples" class="text-xs text-indigo-600 hover:underline">再読込</button>
                </div>
                <div class="divide-y divide-slate-100">
                    <div v-if="isLoading" class="p-12 flex justify-center">
                        <Loader2 class="w-8 h-8 animate-spin text-slate-300" />
                    </div>
                    <div v-else-if="samples.length === 0" class="p-12 text-center text-slate-400">
                        サンプルが見つかりません。
                    </div>
                    <div v-for="file in samples" :key="file.filename" class="p-4 flex items-center justify-between hover:bg-slate-50 transition-colors">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 rounded-lg bg-indigo-50 flex items-center justify-center text-indigo-600">
                                <FileText class="w-5 h-5" />
                            </div>
                            <div>
                                <p class="text-sm font-medium text-slate-700">{{ file.filename }}</p>
                                <p class="text-xs text-slate-400">{{ (file.size / 1024).toFixed(1) }} KB</p>
                            </div>
                        </div>
                        <button 
                            @click="handleTrain(file.filename)"
                            :disabled="processingFile === file.filename"
                            class="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50"
                        >
                            <Loader2 v-if="processingFile === file.filename" class="w-4 h-4 animate-spin" />
                            <Play v-else class="w-4 h-4 fill-current" />
                            AIで解析テスト
                        </button>
                    </div>
                </div>
            </div>

            <!-- Results Panel -->
            <div class="bg-slate-900 rounded-xl shadow-lg p-6 text-slate-300 font-mono text-sm overflow-auto max-h-[600px]">
                <div class="flex items-center justify-between mb-4 border-b border-slate-800 pb-2">
                    <span class="text-slate-500 uppercase text-xs tracking-widest">AI Extraction Output</span>
                    <div v-if="results" class="flex items-center gap-2 text-emerald-400 text-xs">
                        <CheckCircle2 class="w-3 h-3" />
                        Analysis Complete
                    </div>
                </div>
                
                <div v-if="processingFile" class="flex flex-col items-center justify-center h-64 space-y-4">
                    <Loader2 class="w-8 h-8 animate-spin text-indigo-500" />
                    <p class="text-slate-400 animate-pulse">Gemini 3.1 FlashがPDFを解析中...</p>
                </div>
                
                <div v-else-if="results">
                    <pre>{{ JSON.stringify(results, null, 2) }}</pre>
                </div>
                
                <div v-else class="flex flex-col items-center justify-center h-64 text-slate-600">
                    <Cpu class="w-12 h-12 mb-4 opacity-10" />
                    <p>左側のサンプルを選択して解析を開始してください。</p>
                </div>
            </div>
        </div>

        <!-- Explanation Section -->
        <div class="bg-indigo-50 border border-indigo-100 rounded-xl p-6">
            <h3 class="font-bold text-indigo-900 flex items-center gap-2 mb-2">
                <AlertCircle class="w-5 h-5" />
                この機能の仕組み
            </h3>
            <ul class="text-sm text-indigo-800 space-y-2 list-disc ml-5">
                <li>Gemini 3.1 Flash のマルチモーダル機能を活用し、PDFファイルを直接読み取って構造を分析します。</li>
                <li>一度解析されたベンダーのレイアウトは、テンプレート（抽出ルール）として保存されます。</li>
                <li>次回以降、同じベンダーの請求書がアップロードされると、AIはそのルールに基づいて瞬時にデータを抽出します。</li>
            </ul>
        </div>
    </div>
</template>
