<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Lock } from 'lucide-vue-next';
import { useAuth } from '@/composables/useAuth';
import { getRoleLabel } from '@/lib/i18n/roles';
import { api } from '@/lib/api';

const { isAdmin } = useAuth();

// ─── 固定権限（変更不可・グレーアウト表示） ───────────────────────
const FIXED_PERMISSIONS = [
  { label: '自社情報管理',           note: '管理者のみ' },
  { label: 'ユーザー管理',           note: '管理者のみ' },
  { label: '部門・プロジェクト管理', note: '管理者のみ' },
  { label: '承認ルール設定',         note: '管理者のみ' },
  { label: '銀行明細アップロード',   note: '経理以上' },
  { label: '現金出納帳',             note: '経理以上' },
  { label: '消込',                   note: '経理以上' },
  { label: 'CSV出力',               note: '経理以上' },
  { label: '全銀データ出力',         note: '経理以上' },
  { label: '予算登録・編集',         note: '管理者のみ' },
  { label: 'AIチャット（設定・管理）', note: '管理者のみ' },
] as const;

// ─── 柔軟権限ラベルマップ ───────────────────────────────────────
const FLEXIBLE_LABELS: Record<string, string> = {
  client_management:       '取引先管理',
  journal_rule_settings:   '自動仕訳ルール設定',
  matching_rule_settings:  '消込条件ルール設定',
  report_view:             'レポート確認',
  budget_comparison_view:  '予算対比レポート確認',
  ai_chat_basic:           'AIチャット（申請・税務知識）',
  ai_chat_accounting:      'AIチャット（経理・仕訳）',
};

// 承認プロセストグルを表示する機能キー
const APPROVAL_TOGGLE_KEYS = new Set(['client_management']);

// ロール選択肢（昇順）
const ROLE_OPTIONS = ['staff', 'approver', 'accounting', 'manager', 'admin'];

// ─── State ──────────────────────────────────────────────────
const settings = ref<any[]>([]);
const isLoading = ref(true);
const isSaving = ref(false);

const fetchSettings = async () => {
  try {
    const data = await api.get<any[]>('/permission-settings');
    settings.value = data;
  } catch (err) {
    console.error('Failed to load permission settings:', err);
  } finally {
    isLoading.value = false;
  }
};

onMounted(fetchSettings);

const onSave = async () => {
  if (!isAdmin.value) return;
  isSaving.value = true;
  try {
    await api.put('/permission-settings', settings.value.map(s => ({
      feature_key: s.feature_key,
      min_role: s.min_role,
      require_approval: s.require_approval ?? false,
    })));
    alert('権限設定を保存しました。');
  } catch (err: any) {
    console.error('Failed to save permission settings:', err);
    alert(`保存に失敗しました。\n${err?.message ?? ''}`);
  } finally {
    isSaving.value = false;
  }
};
</script>

<template>
  <div class="p-8">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-gray-900 mb-2">権限設定</h1>
      <p class="text-gray-500">
        機能ごとの最低必要ロールを設定します。
        <Lock :size="13" class="inline-block text-gray-400 mb-0.5" /> の項目は変更できません。
      </p>
    </div>

    <div v-if="isLoading" class="flex justify-center py-16 text-gray-400">
      読み込み中...
    </div>

    <div v-else class="max-w-3xl space-y-8">

      <!-- ── 固定権限 ── -->
      <div class="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div class="px-6 py-3 border-b border-gray-100 bg-gray-50">
          <h2 class="text-xs font-bold text-gray-500 uppercase tracking-wider">固定権限（変更不可）</h2>
        </div>
        <div class="divide-y divide-gray-50">
          <div
            v-for="perm in FIXED_PERMISSIONS"
            :key="perm.label"
            class="flex items-center justify-between px-6 py-3 opacity-55"
          >
            <div class="flex items-center gap-2">
              <Lock :size="13" class="text-gray-400 shrink-0" />
              <span class="text-sm text-gray-600">{{ perm.label }}</span>
            </div>
            <span class="text-xs text-gray-500 bg-gray-100 px-3 py-1 rounded-full font-medium">
              {{ perm.note }}
            </span>
          </div>
        </div>
      </div>

      <!-- ── 柔軟権限 ── -->
      <div class="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div class="px-6 py-3 border-b border-gray-100 bg-gray-50">
          <h2 class="text-xs font-bold text-gray-500 uppercase tracking-wider">変更可能な権限</h2>
        </div>
        <div class="divide-y divide-gray-50">
          <div
            v-for="setting in settings"
            :key="setting.feature_key"
            class="flex items-center justify-between px-6 py-4 transition-colors"
            :class="isAdmin ? 'hover:bg-gray-50/60' : 'opacity-60'"
          >
            <span class="text-sm font-medium text-gray-700">
              {{ FLEXIBLE_LABELS[setting.feature_key] ?? setting.feature_key }}
            </span>
            <div class="flex items-center gap-4">
              <!-- 承認プロセストグル（一部機能のみ） -->
              <label
                v-if="APPROVAL_TOGGLE_KEYS.has(setting.feature_key)"
                class="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none"
              >
                <input
                  type="checkbox"
                  v-model="setting.require_approval"
                  :disabled="!isAdmin"
                  class="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-400 disabled:cursor-not-allowed"
                />
                承認プロセス
              </label>

              <!-- ロール選択 -->
              <select
                v-model="setting.min_role"
                :disabled="!isAdmin"
                class="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 disabled:bg-gray-50 disabled:cursor-not-allowed"
              >
                <option v-for="role in ROLE_OPTIONS" :key="role" :value="role">
                  {{ getRoleLabel(role) }} 以上
                </option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- ── 保存ボタン / 非管理者メッセージ ── -->
      <div v-if="isAdmin" class="flex justify-end">
        <button
          @click="onSave"
          :disabled="isSaving"
          class="bg-indigo-600 text-white font-bold py-2.5 px-8 rounded-xl hover:bg-indigo-700 shadow-md transition-colors disabled:opacity-50"
        >
          {{ isSaving ? '保存中...' : '変更を保存する' }}
        </button>
      </div>
      <div v-else class="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
        ※ 権限設定の変更は管理者のみ行えます。
      </div>

    </div>
  </div>
</template>
