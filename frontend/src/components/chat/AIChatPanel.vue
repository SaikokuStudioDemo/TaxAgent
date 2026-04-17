<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue';
import { MessageSquare, X, Send, Bot, Loader2, Paperclip } from 'lucide-vue-next';
import { api } from '@/lib/api';
import { userProfile, corporateId } from '@/composables/useAuth';
import { useFileUpload } from '@/composables/useFileUpload';

const props = defineProps<{
  isOverlay: boolean;
  sidebarCollapsed?: boolean;
}>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'open-overlay'): void;
}>();

// ── 型定義 ─────────────────────────────────────────────────────────────
interface ChatMessage {
  role: 'ai' | 'user';
  text: string;
  isLoading?: boolean;  // ファイル処理中のローディングバブル用
  // Task#17-C: 確認フロー用（③ チャット送信とは別コードパス）
  confirmationRequired?: boolean;
  confirmPayload?: {
    tool_name: string;
    payload: Record<string, unknown>;
  };
}

interface OcrResult {
  ocr_result: {
    vendor_name?: string;
    payee?: string;
    total_amount?: number;
    date?: string;
    issue_date?: string;
    category?: string;
    description?: string;
  };
  journal_suggestion: {
    suggested_debit: string;
    suggested_credit: string;
    suggested_tax_category: string;
    confidence: string;
  };
  confirmation_required: boolean;
}

// ── State ──────────────────────────────────────────────────────────────
const query = ref('');
const isLoading = ref(false);          // テキスト送信中
const isFileProcessing = ref(false);   // ファイル処理中（⑤ isLoading と分離）
const isExecuting = ref(false);        // ④ 確認フロー実行中（二重実行防止）
const messages = ref<ChatMessage[]>([]);
const chatContainer = ref<HTMLElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);

// ── ① corporateId 型変換（ComputedRef<string|null> → Ref<string|undefined>）──
// useFileUpload は Ref<string | undefined> を期待するため変換が必要
const corpIdRef = computed<string | undefined>(() => corporateId.value ?? undefined);

// ② useFileUpload を setup 直下でインスタンス化（handleFileAttach 内ではなく）
const { uploadSingleFile } = useFileUpload({
  storagePath: 'chat_attachments/',
  corporateId: corpIdRef,
});

// ── スクロール ────────────────────────────────────────────────────────
// ① watch より前に定義することで TDZ エラーを防ぐ
const scrollToBottom = async () => {
  await nextTick();
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
  }
};

// ── ウェルカムメッセージ + 履歴取得 ──────────────────────────────────
// 処理順：ローディング表示 → 履歴取得 → 挨拶追加
const initMessage = async () => {
  if (messages.value.length > 0) return;

  messages.value.push({ role: 'ai', text: '読み込み中...', isLoading: true });

  const fallback = 'こんにちは！何かお手伝いできることはありますか？';

  try {
    await scrollToBottom();

    // ① 履歴取得（失敗しても続行）
    const history = await Promise.race([
      api.get<{ messages: Array<{ role: string; content: string }> }>('/advisor/history'),
      new Promise<never>((_, reject) => setTimeout(() => reject(new Error('timeout')), 5000)),
    ]).catch(() => ({ messages: [] }));

    // ② content → text マッピングしてローディングを除去・履歴を展開
    messages.value = (history.messages ?? []).map(m => ({
      role: m.role as 'ai' | 'user',
      text: m.content ?? '',
    }));

    // 挨拶取得（失敗時はフォールバック）
    const greeted = await Promise.race([
      api.get<{ greeting: string }>('/advisor/greeting'),
      new Promise<never>((_, reject) => setTimeout(() => reject(new Error('timeout')), 5000)),
    ]).catch(() => ({ greeting: fallback }));

    messages.value.push({
      role: 'ai',
      text: greeted.greeting ?? fallback,
    });

    await scrollToBottom();
  } catch {
    // 予期しないエラー時はフォールバックのみ表示
    messages.value = [{ role: 'ai', text: fallback }];
  }
};

// userProfile が確定したら initMessage（即時 + 変化時）
// ③ scrollToBottom → initMessage → watch の順で定義
watch(userProfile, (val) => {
  if (val) initMessage();
}, { immediate: true });

// ── Body スクロールロック + 開いた時に最下部へスクロール ─────────────
watch(() => props.isOverlay, (val) => {
  document.body.style.overflow = val ? 'hidden' : '';
  if (val) scrollToBottom();
}, { immediate: true });

onUnmounted(() => {
  document.body.style.overflow = '';
});

// ── テキスト送信 ──────────────────────────────────────────────────────
const handleSend = async () => {
  if (!query.value.trim() || isLoading.value) return;

  const userMsg = query.value;
  messages.value.push({ role: 'user', text: userMsg });
  query.value = '';
  isLoading.value = true;
  scrollToBottom();

  try {
    const res = await api.post<{ response: string }>('/advisor/chat', { query: userMsg });
    const responseText = res.response || '';

    const toolMatch = responseText.match(/\[\[TOOL:(\w+)\]\]([\s\S]*?)\[\[\/TOOL\]\]/);
    const payloadMatch = responseText.match(/\[\[TOOL_PAYLOAD:([\s\S]*?)\]\]/);

    if (toolMatch && payloadMatch) {
      try {
        const toolName = toolMatch[1];
        const confirmMessage = toolMatch[2].trim();
        const payload = JSON.parse(payloadMatch[1]);
        messages.value.push({
          role: 'ai',
          text: confirmMessage,
          confirmationRequired: true,
          confirmPayload: { tool_name: toolName, payload },
        });
      } catch {
        messages.value.push({ role: 'ai', text: responseText });
      }
    } else {
      messages.value.push({ role: 'ai', text: responseText });
    }
  } catch (err) {
    console.error('AIChat Error:', err);
    messages.value.push({
      role: 'ai',
      text: '申し訳ありません。アドバイザーとの接続に問題が発生しました。'
    });
  } finally {
    isLoading.value = false;
    scrollToBottom();
  }
};

// ── OCR 結果フォーマット ──────────────────────────────────────────────
const formatOcrResult = (result: OcrResult): string => {
  const ocr = result.ocr_result;
  const journal = result.journal_suggestion;
  const amount = ocr.total_amount != null
    ? ocr.total_amount.toLocaleString()
    : '不明';
  const dateStr = ocr.date ?? ocr.issue_date ?? '不明';
  const payee = ocr.payee ?? ocr.vendor_name ?? '不明';

  return (
    `以下の内容で読み取りました。確認してください。\n\n` +
    `取引先：${payee}\n` +
    `金額：${amount}円\n` +
    `日付：${dateStr}\n` +
    `推奨科目：${journal.suggested_debit}（${journal.suggested_tax_category}）\n\n` +
    `この内容で申請しますか？\n` +
    `1. はい、申請する\n` +
    `2. 内容を修正する\n` +
    `3. キャンセル`
  );
};

// ── ファイル添付処理 ──────────────────────────────────────────────────
const handleFileAttach = async (file: File) => {
  if (isFileProcessing.value) return;
  isFileProcessing.value = true;

  // ローディングバブルをチャットに追加
  messages.value.push({ role: 'ai', text: '読み取り中...', isLoading: true });
  scrollToBottom();

  try {
    // ② Firebase Storage にアップロード（setup 直下でインスタンス化済みの uploadSingleFile を使う）
    const fileUrl = await uploadSingleFile(file);
    if (!fileUrl) throw new Error('ファイルのアップロードに失敗しました。');

    // OCR 実行
    const result = await api.post<OcrResult>('/ocr/extract', {
      file_url: fileUrl,
      doc_type: 'receipt',
    });

    // ローディングバブルを OCR 結果に差し替え
    const lastMsg = messages.value[messages.value.length - 1];
    if (lastMsg?.isLoading) {
      lastMsg.text = formatOcrResult(result);
      lastMsg.isLoading = false;
    }
  } catch (err) {
    console.error('OCR Error:', err);
    const lastMsg = messages.value[messages.value.length - 1];
    if (lastMsg?.isLoading) {
      lastMsg.text = '読み取りに失敗しました。もう一度お試しください。';
      lastMsg.isLoading = false;
    }
  } finally {
    isFileProcessing.value = false;
    scrollToBottom();
  }
};

const onFileInputChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) {
    handleFileAttach(file);
    input.value = ''; // 同じファイルを再選択できるようリセット
  }
};

const triggerFileInput = () => {
  fileInputRef.value?.click();
};

// ── Task#17-C: 確認フロー（③ チャット送信と別コードパス） ─────────────

/**
 * ④ 確認ボタン「はい、実行する」を押した時の処理。
 * isExecuting で二重実行を防止する。
 */
const executeConfirmed = async (confirmPayload: {
  tool_name: string;
  payload: Record<string, unknown>;
}) => {
  if (isExecuting.value) return;
  isExecuting.value = true;

  try {
    const result = await api.post<any>(
      `/advisor/tools/${confirmPayload.tool_name}`,
      { ...confirmPayload.payload, confirmed: true },
    );

    // 確認ボタンを非表示に（最後の confirmationRequired メッセージ）
    const lastConfirmIdx = [...messages.value].reverse().findIndex(m => m.confirmationRequired);
    if (lastConfirmIdx !== -1) {
      const idx = messages.value.length - 1 - lastConfirmIdx;
      messages.value.splice(idx, 1, {
        ...messages.value[idx],
        confirmationRequired: false,
      });
    }

    if (result.error) {
      const errorMsg = result.error as string;
      const userMessage = (
        errorMsg.includes('見つかりません') || errorMsg.includes('not found')
          ? '対象のデータが見つかりませんでした。画面から直接操作してください。'
          : '一時的なエラーが発生しました。しばらく時間を置いてから再試行してください。'
      );
      messages.value.push({ role: 'ai', text: userMessage });
    } else {
      messages.value.push({
        role: 'ai',
        text: result.message || '処理が完了しました。',
      });
    }

    // download_url がある場合はリンクを表示
    if (result.download_url) {
      messages.value.push({
        role: 'ai',
        text: `📥 ダウンロード準備ができました。以下のリンクからダウンロードしてください。\n${result.download_url}`,
      });
    }
  } catch (err: any) {
    messages.value.push({
      role: 'ai',
      text: `エラーが発生しました。${err.message ?? ''}`,
    });
  } finally {
    isExecuting.value = false;
    scrollToBottom();
  }
};

/** 確認をキャンセルする。 */
const cancelConfirmation = (msg: ChatMessage) => {
  const idx = messages.value.findIndex(m => m === msg);
  if (idx !== -1) {
    messages.value.splice(idx, 1, { ...msg, confirmationRequired: false });
  }
  messages.value.push({ role: 'ai', text: 'キャンセルしました。' });
  scrollToBottom();
};

// ── オーバーレイを閉じる ──────────────────────────────────────────────
const handleClose = () => {
  emit('close');
};
</script>

<template>
  <!-- ══════════════════════════════════════════════════════ -->
  <!-- ① オーバーレイモード（isOverlay=true）                  -->
  <!-- ══════════════════════════════════════════════════════ -->
  <Teleport to="body">
    <Transition name="overlay">
      <div
        v-if="isOverlay"
        class="overlay-root fixed inset-0 z-[100]"
      >
        <!-- 背景（全画面・サイドバーも含めてブロック） -->
        <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" />

        <!-- チャット配置エリア（サイドバー幅だけ左をずらす） -->
        <div
          class="absolute top-0 bottom-0 right-0 flex items-center justify-center p-6"
          :class="sidebarCollapsed ? 'left-20' : 'left-64'"
          @click.self="handleClose"
        >

        <!-- チャットウィンドウ -->
        <div class="chat-box relative w-[80%] h-[85vh] bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden">
          <!-- ヘッダー -->
          <div class="bg-indigo-600 px-5 py-4 flex items-center justify-between text-white shrink-0">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center">
                <Bot class="w-5 h-5" />
              </div>
              <h3 class="font-bold text-sm leading-tight">Tax-Agent AI Advisor</h3>
            </div>
            <button
              @click="handleClose"
              class="p-1.5 hover:bg-white/20 rounded-full transition-colors"
              aria-label="閉じる"
            >
              <X class="w-5 h-5" />
            </button>
          </div>

          <!-- メッセージエリア -->
          <div ref="chatContainer" class="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50 chat-messages">
            <div
              v-for="(msg, i) in messages"
              :key="i"
              :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']"
            >
              <!-- ローディングバブル（ファイル処理中） -->
              <div
                v-if="msg.isLoading"
                class="bg-white p-3 rounded-2xl rounded-tl-none border border-slate-200 shadow-sm flex items-center gap-2"
              >
                <Loader2 class="w-4 h-4 animate-spin text-indigo-600 shrink-0" />
                <span class="text-xs text-slate-500 italic">{{ msg.text }}</span>
              </div>
              <!-- 通常メッセージ -->
              <div
                v-else
                :class="[
                  'max-w-[85%] p-3 rounded-2xl text-sm shadow-sm whitespace-pre-wrap leading-relaxed',
                  msg.role === 'user'
                    ? 'bg-indigo-600 text-white rounded-tr-none'
                    : 'bg-white text-slate-700 border border-slate-200 rounded-tl-none'
                ]"
              >
                {{ msg.text }}
                <!-- Task#17-C: 確認ボタン（③ チャット送信とは別コードパス） -->
                <div v-if="msg.confirmationRequired && msg.confirmPayload" class="mt-3 flex gap-2">
                  <button
                    @click="executeConfirmed(msg.confirmPayload!)"
                    :disabled="isExecuting"
                    class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 transition-colors"
                  >
                    {{ isExecuting ? '実行中...' : '✅ はい、実行する' }}
                  </button>
                  <button
                    @click="cancelConfirmation(msg)"
                    :disabled="isExecuting"
                    class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-300 disabled:opacity-40 transition-colors"
                  >
                    ❌ キャンセル
                  </button>
                </div>
              </div>
            </div>
            <!-- テキスト送信中ローディング -->
            <div v-if="isLoading" class="flex justify-start">
              <div class="bg-white p-3 rounded-2xl rounded-tl-none border border-slate-200 shadow-sm flex items-center gap-2">
                <Loader2 class="w-4 h-4 animate-spin text-indigo-600" />
                <span class="text-xs text-slate-500 italic">考えています...</span>
              </div>
            </div>
          </div>

          <!-- 入力エリア -->
          <div class="px-4 py-3 bg-white border-t border-slate-100 shrink-0">
            <!-- 非表示ファイル入力 -->
            <input
              ref="fileInputRef"
              type="file"
              accept=".jpg,.jpeg,.png,.pdf"
              class="hidden"
              @change="onFileInputChange"
            />
            <form @submit.prevent="handleSend" class="flex gap-2 items-center">
              <!-- クリップアイコン（ファイル添付） -->
              <button
                type="button"
                @click="triggerFileInput"
                :disabled="isFileProcessing"
                class="w-9 h-9 flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-slate-100 rounded-lg transition-colors shrink-0 disabled:opacity-40"
                aria-label="ファイルを添付"
                title="領収書・請求書を添付（JPG / PNG / PDF）"
              >
                <Paperclip class="w-4 h-4" />
              </button>
              <input
                v-model="query"
                type="text"
                placeholder="質問を入力してください..."
                class="flex-1 bg-slate-100 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none placeholder-slate-400"
              />
              <button
                type="submit"
                :disabled="!query.trim() || isLoading"
                class="w-10 h-10 bg-indigo-600 text-white rounded-xl flex items-center justify-center hover:bg-indigo-700 disabled:opacity-40 disabled:hover:bg-indigo-600 transition-colors shadow-md shadow-indigo-200 shrink-0"
              >
                <Send class="w-4 h-4" />
              </button>
            </form>
          </div>
        </div>
        </div><!-- /チャット配置エリア -->
      </div>
    </Transition>
  </Teleport>

  <!-- ══════════════════════════════════════════════════════ -->
  <!-- ② フローティングボタン（isOverlay=false 時）             -->
  <!-- ══════════════════════════════════════════════════════ -->
  <div v-if="!isOverlay" class="fixed bottom-6 right-6 z-50">
    <button
      @click="emit('open-overlay')"
      class="w-14 h-14 bg-indigo-600 text-white rounded-full flex items-center justify-center shadow-xl hover:bg-indigo-700 hover:scale-110 transition-all active:scale-95 group"
    >
      <MessageSquare class="w-6 h-6" />
      <span class="absolute right-full mr-4 bg-slate-800 text-white text-[10px] px-2 py-1 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap hidden sm:block">
        AIアドバイザーに相談
      </span>
    </button>
  </div>
</template>

<style scoped>
/* ── オーバーレイ Transition ──────────────────────────────────────── */
/* 背景フェード */
.overlay-enter-active {
  transition: opacity 0.3s ease-out;
}
.overlay-leave-active {
  transition: opacity 0.25s ease-in;
}
.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}

/* チャットボックス：表示時は中央からスケールイン */
.overlay-enter-active .chat-box {
  transition: transform 0.3s ease-out, opacity 0.3s ease-out;
  transform-origin: center;
}
.overlay-enter-from .chat-box {
  transform: scale(0.85);
  opacity: 0;
}

/* チャットボックス：非表示時は右下に向かって収束 */
.overlay-leave-active .chat-box {
  transition: transform 0.25s ease-in, opacity 0.25s ease-in;
  transform-origin: bottom right;
}
.overlay-leave-to .chat-box {
  transform: scale(0);
  opacity: 0;
}

/* ── スクロールバー ───────────────────────────────────────────────── */
.chat-messages::-webkit-scrollbar { width: 4px; }
.chat-messages::-webkit-scrollbar-track { background: transparent; }
.chat-messages::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 2px; }
</style>
