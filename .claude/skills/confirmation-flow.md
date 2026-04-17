# 確認フロー実装パターン（提案 → 確認 → 実行）

AIエージェントツールやフォーム操作で「内容を確認してから DB に書き込む」パターン。
**AIが確認なしに DB を変更・削除してはいけない**（CLAUDE.md 最重要ルール）。

---

## パターン A（推奨）: フロントが `confirmed` フラグを管理

**特徴**: 提案エンドポイントと実行エンドポイントを分ける。一番シンプル。

### バックエンド：提案エンドポイント（DB 書き込みなし）

```python
@router.post("/tools/draft_expense_claim")
async def tool_draft_expense_claim(
    payload: DraftExpenseClaimRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    経費申請の下書きを返す。DB への保存は行わない。
    confirmation_required=True を返してフロントに確認を促す。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)

    draft = {
        "corporate_id": corporate_id,
        "submitted_by": user_id,
        "amount": payload.amount,
        "description": payload.description,
        "date": payload.date,
        "approval_status": "pending_approval",
    }

    return {
        "draft": draft,
        "confirmation_required": True,   # ← 必須フラグ
        "message": "以下の内容で申請します。よろしいですか？",
    }
```

### バックエンド：実行エンドポイント（DB に書き込む）

```python
class SubmitExpenseClaimRequest(BaseModel):
    amount: int
    description: str
    date: str
    category: Optional[str] = None

@router.post("/receipts")
async def create_receipt(
    payload: SubmitExpenseClaimRequest,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """確認済みの内容を DB に保存する実行エンドポイント。"""
    doc = {
        **payload.model_dump(),
        "corporate_id": ctx.corporate_id,
        "submitted_by": ctx.user_id,
        "approval_status": "pending_approval",
        "created_at": datetime.utcnow(),
    }
    result = await ctx.db["receipts"].insert_one(doc)
    created = await ctx.db["receipts"].find_one({"_id": result.inserted_id})
    return serialize_doc(created)
```

---

## パターン B: 同一エンドポイントで `confirmed` フラグを受け取る

**特徴**: エンドポイントが1つで済む。`confirmed=False` → 下書き返却、`confirmed=True` → 保存。

```python
class CreateInvoiceRequest(BaseModel):
    client_id: str
    amount: int
    description: str
    due_date: Optional[str] = None
    confirmed: bool = False   # ← フロントが True を送るまで保存しない

@router.post("/invoices")
async def create_invoice(
    payload: CreateInvoiceRequest,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    # 下書き生成（常に実行）
    client = await get_doc_or_404(ctx.db, "clients", payload.client_id, ctx.corporate_id, "client")

    draft = {
        "corporate_id": ctx.corporate_id,
        "client_name": client.get("name", ""),
        "amount": payload.amount,
        "description": payload.description,
        "due_date": payload.due_date or ...,
        "approval_status": "pending_approval",
    }

    if not payload.confirmed:
        # 確認前 → 下書きを返すだけ（DB 書き込みなし）
        return {
            "draft": draft,
            "confirmation_required": True,
        }

    # 確認済み → DB に保存
    doc = {**draft, "created_at": datetime.utcnow()}
    result = await ctx.db["invoices"].insert_one(doc)
    created = await ctx.db["invoices"].find_one({"_id": result.inserted_id})
    return serialize_doc(created)
```

---

## フロントエンド側の実装

### 確認ダイアログ → 実行 API の繋ぎ方

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { api } from '@/lib/api';

const draft = ref<any>(null);
const showConfirmDialog = ref(false);
const isSubmitting = ref(false);
const error = ref<string | null>(null);

// Step 1: 提案APIを呼んで下書きを取得
const handlePreview = async () => {
  const result = await api.post('/advisor/tools/draft_expense_claim', {
    amount: form.amount,
    description: form.description,
    date: form.date,
  });

  if (result.confirmation_required) {
    draft.value = result.draft;
    showConfirmDialog.value = true;  // 確認ダイアログを表示
  }
};

// Step 2: ユーザーが「確認」を押したら実行APIを呼ぶ
const handleConfirm = async () => {
  if (!draft.value) return;
  isSubmitting.value = true;
  error.value = null;

  try {
    await api.post('/receipts', {
      amount: draft.value.amount,
      description: draft.value.description,
      date: draft.value.date,
    });
    showConfirmDialog.value = false;
    draft.value = null;
    // 成功後の処理（リスト更新、通知表示など）
  } catch (e: any) {
    error.value = e.message;
  } finally {
    isSubmitting.value = false;
  }
};

// キャンセル
const handleCancel = () => {
  showConfirmDialog.value = false;
  draft.value = null;
};
</script>

<template>
  <!-- 確認ダイアログ -->
  <div v-if="showConfirmDialog" class="modal">
    <h3>以下の内容で申請しますか？</h3>
    <dl>
      <dt>金額</dt><dd>{{ draft?.amount?.toLocaleString() }}円</dd>
      <dt>説明</dt><dd>{{ draft?.description }}</dd>
      <dt>日付</dt><dd>{{ draft?.date }}</dd>
    </dl>
    <div class="flex gap-2">
      <button @click="handleCancel">キャンセル</button>
      <button @click="handleConfirm" :disabled="isSubmitting">
        {{ isSubmitting ? '送信中...' : '申請する' }}
      </button>
    </div>
  </div>
</template>
```

---

## チャット UI での確認フロー

チャットの OCR 読み取り後に「申請しますか？」と聞くパターン。

```typescript
// AIChatPanel.vue 内
const formatOcrResult = (result: OcrResult): string => {
  const ocr = result.ocr_result;
  return (
    `以下の内容で読み取りました。確認してください。\n\n` +
    `取引先：${ocr.payee ?? ocr.vendor_name ?? '不明'}\n` +
    `金額：${ocr.total_amount?.toLocaleString() ?? '不明'}円\n` +
    `日付：${ocr.date ?? ocr.issue_date ?? '不明'}\n\n` +
    `この内容で申請しますか？\n` +
    `1. はい、申請する\n` +
    `2. 内容を修正する\n` +
    `3. キャンセル`
  );
};
```

---

## 実装チェックリスト

- [ ] 提案系エンドポイントに `confirmation_required: True` が含まれること
- [ ] 提案系エンドポイントで `insert_one` / `update_one` / `delete_one` を呼ばないこと
- [ ] 実行系エンドポイントは別エンドポイント（またはパターンBなら `confirmed=True` 必須）
- [ ] フロントで確認ダイアログを挟んでから実行APIを呼ぶこと
- [ ] キャンセル時に draft を破棄してダイアログを閉じること
- [ ] 実行中は `isSubmitting` フラグでボタンを無効化すること
