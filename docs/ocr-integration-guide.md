# OCR機能 統合ガイド

Tax AgentにOCR機能を導入する開発者向けのドキュメントです。

---

## 目次

1. [概要](#概要)
2. [現在の実装状況](#現在の実装状況)
3. [OCRが返すべきJSONの仕様](#ocrが返すべきjsonの仕様)
4. [Tax Agentがデータを受け取る流れ](#tax-agentがデータを受け取る流れ)
5. [統合ポイント（実装が必要な箇所）](#統合ポイント実装が必要な箇所)
6. [関連ファイル一覧](#関連ファイル一覧)
7. [認証・セキュリティ](#認証セキュリティ)

---

## 概要

Tax AgentのOCRフローは以下の流れになっています。

```
写真/PDF
  ↓
OCR機能（画像を読み取りJSON化）  ← 今回の開発対象
  ↓
Tax Agent（JSONを受け取り、フォームに自動入力）
  ↓
ユーザーが内容を確認・修正
  ↓
承認ワークフロー → MongoDB保存
```

OCR機能は**画像ファイルを受け取ってJSONを返すだけ**でOKです。Tax Agent側のフォームへの反映・保存・承認は既存の仕組みが処理します。

---

## 現在の実装状況

既にGemini Vision APIを使った暫定実装が存在します。

**ファイル**: `backend/app/services/temp_ocr/invoice_ocr.py`

| 機能 | 状態 |
|------|------|
| Gemini Vision APIによる請求書OCR | 実装済み（スクリプト実行のみ） |
| PDF → JPEG変換 | 実装済み |
| iOSスキャン形式（Zip）対応 | 実装済み |
| HTTPエンドポイント経由での呼び出し | **未実装（要作成）** |
| フロントエンドからの自動呼び出し | **未実装（要作成）** |

---

## OCRが返すべきJSONの仕様

### 請求書（Invoice）

```json
{
  "invoice_number": "INV-2024-001",
  "client_name": "株式会社山田商事",
  "vendor_name": "株式会社田中サービス",
  "issue_date": "2024-01-15",
  "due_date": "2024-02-15",
  "subtotal": 100000,
  "tax_amount": 10000,
  "total_amount": 110000,
  "line_items": [
    {
      "description": "システム開発費",
      "category": "外注費",
      "amount": 100000,
      "tax_rate": 10
    }
  ]
}
```

### レシート（Receipt）

```json
{
  "date": "2024-01-15",
  "amount": 5500,
  "tax_rate": 10,
  "payee": "コンビニA 渋谷店",
  "category": "消耗品費",
  "line_items": [
    {
      "description": "文房具",
      "category": "消耗品費",
      "amount": 5000,
      "tax_rate": 10
    }
  ]
}
```

### フィールド定義

#### 共通

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `date` / `issue_date` | `string` | 必須 | `YYYY-MM-DD` 形式 |
| `total_amount` | `integer` | 必須 | 税込合計金額（円） |
| `tax_amount` | `integer` | 必須 | 消費税額（円） |
| `subtotal` | `integer` | 必須 | 税抜合計金額（円） |
| `line_items` | `array` | 任意 | 明細行のリスト |

#### line_items の各要素

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `description` | `string` | 必須 | 品目名 |
| `category` | `string` | 必須 | 勘定科目（日本語） |
| `amount` | `integer` | 必須 | 金額（税抜、円） |
| `tax_rate` | `integer` | 必須 | 税率 `10` / `8` / `0` |

#### 勘定科目の例（`category`フィールド）

OCR側で判断して入力してください。Tax Agentはこの値をそのまま使います。

```
消耗品費 / 交通費 / 接待交際費 / 外注費 / 広告宣伝費
通信費 / 水道光熱費 / 賃借料 / 保険料 / 修繕費
```

---

## Tax Agentがデータを受け取る流れ

### ステップ1: ファイルのアップロード

フロントエンドはまずFirebase Storageにファイルをアップロードし、**ファイルURL**を取得します。

```
frontend/src/composables/useFileUpload.ts
frontend/src/lib/firebase/storage.ts
```

### ステップ2: OCRの呼び出し（統合ポイント）

アップロード完了後、フロントエンドがバックエンドのOCRエンドポイントを呼び出します。

```
POST /api/v1/ocr/extract
```

**リクエスト**:
```json
{
  "file_url": "https://storage.googleapis.com/...",
  "doc_type": "invoice"
}
```

**レスポンス**: 上記のJSON仕様に従った抽出結果

### ステップ3: フォームへの自動入力

OCRの結果をフォームに自動入力し、ユーザーが確認・修正できる状態にします。

```
frontend/src/views/dashboard/corporate/receipts/ReceiptUploadPage.vue
frontend/src/views/dashboard/corporate/invoices/ReceivedInvoiceUploadPage.vue
```

### ステップ4: 保存・承認

ユーザーが「提出」ボタンを押すと、以下のエンドポイントにPOSTされます。

- レシート: `POST /api/v1/receipts/batch`
- 請求書: `POST /api/v1/invoices`

このとき `ai_extracted: true` フラグが付いて保存されます。

---

## 統合ポイント（実装が必要な箇所）

### A. バックエンド: OCRエンドポイントの作成

**新規作成するファイル**: `backend/app/api/routes/ocr.py`

```python
from fastapi import APIRouter, HTTPException, Depends
from app.services.temp_ocr.invoice_ocr import extract_invoice_data_with_gemini
from app.api.deps import get_current_user
import httpx
import tempfile
import os

router = APIRouter()

@router.post("/extract")
async def extract_document(
    payload: dict,  # { file_url: str, doc_type: "invoice" | "receipt" }
    current_user: dict = Depends(get_current_user),
):
    """
    Firebase StorageのURLからファイルを取得し、OCRで情報を抽出する。
    
    リクエスト:
      file_url: str  - Firebase StorageのダウンロードURL
      doc_type: str  - "invoice" または "receipt"
    
    レスポンス:
      抽出されたデータのJSON（上記仕様参照）
    """
    file_url = payload.get("file_url")
    doc_type = payload.get("doc_type", "invoice")

    if not file_url:
        raise HTTPException(status_code=400, detail="file_url is required")

    # 1. ファイルをダウンロード
    tmp_path = None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(file_url)
            response.raise_for_status()

        suffix = ".pdf" if "pdf" in file_url.lower() else ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        # 2. OCRを実行
        extracted = extract_invoice_data_with_gemini(tmp_path)
        return extracted

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
```

**`backend/app/main.py` に追加**:

```python
from app.api.routes import ocr

app.include_router(
    ocr.router,
    prefix=f"{settings.API_V1_STR}/ocr",
    tags=["ocr"],
)
```

---

### B. フロントエンド: アップロード後にOCRを呼び出す

**ファイル**: `frontend/src/views/dashboard/corporate/receipts/ReceiptUploadPage.vue`

現在は以下のように固定値が入っています（TODO コメントあり）:

```typescript
// TODO: OCR/AI extraction will populate these fields
newReceipts.push({
  id: crypto.randomUUID(),
  date: new Date().toISOString().split('T')[0],  // ← 本日日付
  amount: 0,                                      // ← 0固定
  payee: file.name.split('.')[0],                 // ← ファイル名
  category: '消耗品費',                           // ← 固定値
  ...
});
```

ここをOCR呼び出しに差し替えます:

```typescript
// アップロード後にOCRを呼び出す
const ocrResult = await api.post('/ocr/extract', {
  file_url: uploadedUrl,
  doc_type: 'receipt',
});

newReceipts.push({
  id: crypto.randomUUID(),
  date: ocrResult.date ?? new Date().toISOString().split('T')[0],
  amount: ocrResult.total_amount ?? 0,
  tax_rate: ocrResult.tax_rate ?? 10,
  payee: ocrResult.payee ?? '',
  category: ocrResult.category ?? '消耗品費',
  line_items: ocrResult.line_items ?? [],
  status: 'new',
  fileUrl: uploadedUrl,
  fileName: file.name,
});
```

受取請求書も同様に `ReceivedInvoiceUploadPage.vue` の `handleFileSelect` 内で処理します。

---

### C. （任意）信頼度スコアの追加

OCR結果の信頼度を返すと、フロントエンド側でユーザーに「要確認」を表示できます。

```json
{
  "total_amount": 110000,
  "confidence": 0.85,
  ...
}
```

`confidence` が低い場合（例: 0.7未満）はUIで警告を表示する想定です。

---

## 関連ファイル一覧

### バックエンド

| ファイル | 内容 |
|---------|------|
| `backend/app/services/temp_ocr/invoice_ocr.py` | 既存のGemini VisionベースOCR実装 |
| `backend/app/services/ai_service.py` | Gemini API連携の共通サービス |
| `backend/app/models/invoice.py` | 請求書のPydanticモデル（`ai_extracted`フィールドあり） |
| `backend/app/models/transaction.py` | レシートのPydanticモデル |
| `backend/app/api/routes/invoices.py` | 請求書APIルーター |
| `backend/app/api/routes/receipts.py` | レシートAPIルーター |
| `backend/app/api/deps.py` | 認証依存関係（`get_current_user`） |
| `backend/app/main.py` | FastAPIアプリ定義（ルーター登録場所） |

### フロントエンド

| ファイル | 内容 |
|---------|------|
| `frontend/src/views/dashboard/corporate/receipts/ReceiptUploadPage.vue` | レシートアップロード画面（OCR呼び出し箇所あり） |
| `frontend/src/views/dashboard/corporate/invoices/ReceivedInvoiceUploadPage.vue` | 受取請求書アップロード画面（OCR呼び出し箇所あり） |
| `frontend/src/composables/useFileUpload.ts` | Firebase Storageへのアップロードロジック |
| `frontend/src/lib/api.ts` | APIクライアント（`api.post()`, `api.get()` など） |

### テストデータ

| ファイル | 内容 |
|---------|------|
| `backend/scripts/test_data/invoices_data.json` | OCRテスト用の請求書JSONサンプル |
| `backend/scripts/test_data/receipts_data.json` | OCRテスト用のレシートJSONサンプル |

---

## 認証・セキュリティ

### APIリクエストの認証

全てのAPIリクエストはFirebase認証のBearerトークンが必要です。

```
Authorization: Bearer <Firebase ID Token>
```

フロントエンドの `frontend/src/lib/api.ts` がトークンを自動付与するので、フロントエンドからの呼び出しは特別な対応不要です。

### ファイルへのアクセス

Firebase StorageのURLはFirebase認証ユーザーのみアクセス可能に設定されています。バックエンドからURLにアクセスする場合は、Firebase Admin SDKまたは認証付きダウンロードURLを使用してください。

### 環境変数

```
# backend/.env
GOOGLE_API_KEY=<Gemini API Key>  # OCR処理に必要
```

---

## 開発環境のセットアップ

```bash
# バックエンド起動
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# フロントエンド起動
cd frontend
npm install
npm run dev
```

既存のOCR実装を単体テストする場合:

```bash
cd backend
python -m app.services.temp_ocr.invoice_ocr
# → scripts/test_data/invoices_data.json に結果が保存される
```
