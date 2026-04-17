# Vue Composable 実装パターン

既存の composable: `frontend/src/composables/use*.ts`
参考実装: `useReceipts.ts`, `useInvoices.ts`, `useFileUpload.ts`

---

## 基本テンプレート（loading / error / data の3点セット）

```typescript
// frontend/src/composables/useXxx.ts
import { ref } from 'vue';
import { api, buildQueryString } from '@/lib/api';

export interface Xxx {
  id: string;
  corporate_id: string;
  // ... フィールド定義
}

export function useXxx() {
  const items = ref<Xxx[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  const fetchItems = async (params?: {
    status?: string;
    fiscal_period?: string;
  }) => {
    isLoading.value = true;
    error.value = null;
    try {
      items.value = await api.get<Xxx[]>(`/xxx${buildQueryString(params)}`);
    } catch (e: any) {
      error.value = e.message ?? '取得に失敗しました';
    } finally {
      isLoading.value = false;
    }
  };

  const getItem = async (id: string): Promise<Xxx | null> => {
    try {
      return await api.get<Xxx>(`/xxx/${id}`);
    } catch (e: any) {
      error.value = e.message;
      return null;
    }
  };

  return {
    items,
    isLoading,
    error,
    fetchItems,
    getItem,
  };
}
```

---

## api.get / api.post のパターン

```typescript
import { api } from '@/lib/api';

// GET（クエリパラメータあり）
const receipts = await api.get<Receipt[]>(`/receipts${buildQueryString({
  approval_status: 'pending_approval',
  fiscal_period: '2025-04',
})}`);

// POST（ボディあり）
const created = await api.post<Receipt>('/receipts', {
  amount: 5000,
  payee: 'タクシー',
  date: '2025-04-01',
});

// PATCH（部分更新）
const updated = await api.patch<Receipt>(`/receipts/${id}`, {
  approval_status: 'approved',
});

// DELETE
await api.delete(`/receipts/${id}`);

// buildQueryString は undefined / null を自動で除外する
// buildQueryString({ a: 'foo', b: undefined }) → '?a=foo'
```

---

## onMounted での初期取得

```vue
<script setup lang="ts">
import { onMounted } from 'vue';
import { useReceipts } from '@/composables/useReceipts';

const { receipts, isLoading, error, fetchReceipts } = useReceipts();

onMounted(() => {
  fetchReceipts({ approval_status: 'pending_approval' });
});
</script>

<template>
  <div v-if="isLoading">読み込み中...</div>
  <div v-else-if="error" class="text-red-500">{{ error }}</div>
  <ul v-else>
    <li v-for="r in receipts" :key="r.id">{{ r.payee }}</li>
  </ul>
</template>
```

---

## watch で corporate_id が変わったら再取得するパターン

```typescript
import { watch } from 'vue';
import { corporateId } from '@/composables/useAuth';

// corporateId が確定したら（または変化したら）データを取得する
watch(corporateId, (newId) => {
  if (newId) fetchItems();
}, { immediate: true });

// immediate: true → マウント時に corporateId がすでにセットされていれば即実行
// immediate: false → 変化時だけ（ページ内でログイン状態が変わる場合）
```

**注意**: `corporateId` は `ComputedRef<string | null>` 型。`null` チェックを忘れずに。

---

## ComputedRef vs Ref の使い分け

```typescript
import { ref, computed, type Ref, type ComputedRef } from 'vue';

// Ref<T>      → 直接書き換えできる（.value = xxx）
const isOpen = ref(false);
isOpen.value = true;  // OK

// ComputedRef<T> → 読み取り専用（他の reactive 値から導出）
const displayName = computed(() => userProfile.value?.name ?? '未ログイン');
// displayName.value = 'xxx'  // ❌ エラー

// useAuth から来る corporateId は ComputedRef<string | null>
import { corporateId } from '@/composables/useAuth';
// corporateId.value で読み取り、直接代入は不可
```

### useFileUpload に渡す際の型変換

`useFileUpload` は `corporateId: Ref<string | undefined>` を期待するが、
`useAuth` の `corporateId` は `ComputedRef<string | null>` なので変換が必要。

```typescript
import { computed } from 'vue';
import { corporateId } from '@/composables/useAuth';
import { useFileUpload } from '@/composables/useFileUpload';

// ✅ setup() の直下でインスタンス化する（関数内ではなく）
const corpIdRef = computed<string | undefined>(() => corporateId.value ?? undefined);

const { uploadSingleFile, isUploading, uploadError } = useFileUpload({
  storagePath: 'receipts/',
  corporateId: corpIdRef,
});
```

**重要**: `useFileUpload` は `setup()` 直下でインスタンス化すること。
ボタンクリックハンドラ等の関数内で呼ぶと Vue の composition API ルール違反になる。

---

## useFileUpload の使い方（完全例）

```vue
<script setup lang="ts">
import { computed, ref } from 'vue';
import { corporateId } from '@/composables/useAuth';
import { useFileUpload } from '@/composables/useFileUpload';
import { api } from '@/lib/api';

// ① setup 直下でインスタンス化（ここが重要）
const corpIdRef = computed<string | undefined>(() => corporateId.value ?? undefined);
const { uploadSingleFile, isUploading } = useFileUpload({
  storagePath: 'receipts/',
  corporateId: corpIdRef,
});

const fileInputRef = ref<HTMLInputElement | null>(null);
const ocrResult = ref<any>(null);

// ② ファイル選択時の処理
const onFileChange = async (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;

  // Firebase Storage にアップロード
  const fileUrl = await uploadSingleFile(file);
  if (!fileUrl) return;  // バリデーションエラー or アップロード失敗

  // OCR 実行
  ocrResult.value = await api.post('/ocr/extract', {
    file_url: fileUrl,
    doc_type: 'receipt',
  });

  // 同じファイルを再選択できるようリセット
  if (fileInputRef.value) fileInputRef.value.value = '';
};
</script>

<template>
  <input ref="fileInputRef" type="file" accept=".jpg,.jpeg,.png,.pdf" @change="onFileChange" class="hidden" />
  <button @click="fileInputRef?.click()" :disabled="isUploading">
    {{ isUploading ? 'アップロード中...' : 'ファイルを選択' }}
  </button>
</template>
```

---

## よくあるパターン：複数のフィルタ条件を持つ composable

```typescript
export function useInvoices() {
  const invoices = ref<Invoice[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  const fetchInvoices = async (params?: {
    document_type?: 'issued' | 'received';
    approval_status?: string;
    fiscal_period?: string;
    reconciliation_status?: string;
  }) => {
    isLoading.value = true;
    error.value = null;
    try {
      invoices.value = await api.get<Invoice[]>(`/invoices${buildQueryString(params)}`);
    } catch (e: any) {
      error.value = e.message;
    } finally {
      isLoading.value = false;
    }
  };

  // 承認・差戻し操作
  const approveInvoice = async (id: string, comment?: string) => {
    return api.post(`/approvals/events`, {
      document_id: id,
      document_type: 'invoice',
      action: 'approved',
      comment,
    });
  };

  const rejectInvoice = async (id: string, comment: string) => {
    return api.post(`/approvals/events`, {
      document_id: id,
      document_type: 'invoice',
      action: 'rejected',
      comment,  // rejection は comment 必須
    });
  };

  return { invoices, isLoading, error, fetchInvoices, approveInvoice, rejectInvoice };
}
```

---

## よくあるミス

- `isLoading.value = false` を `finally` ブロックに置かない → エラー時にローディングが消えない
- `useFileUpload` をクリックハンドラ内でインスタンス化 → composition API ルール違反
- `corporateId`（ComputedRef）を `Ref<string | undefined>` が必要な場所に直接渡す → 型エラー
- `buildQueryString` に `null` を渡す → `?key=null` という文字列になることがある（`undefined` を使う）
- `error.value = null` のリセットを fetch 前に行わないと古いエラーが残る
