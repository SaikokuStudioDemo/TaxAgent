# テストデータスクリプト

領収書データをGemini Visionで抽出し、バックエンドAPIに投入するためのスクリプト群です。

## ⚠️ 注意事項

**`source/` 内のファイルおよび `*.json` はGitに含まれません（個人情報・機密情報のため）。**
`.gitignore` により除外済みです。絶対にコミットしないでください。

---

## ディレクトリ構成

```
scripts/test_data/
├── source/
│   ├── receipts/   # 領収書ファイル群（PDF / JPEG）← Gitignore対象
│   └── banking/    # 通帳・クレカファイル群（PDF / JPEG）← Gitignore対象
├── extract_receipts.py   # Step 1: Gemini APIで領収書情報を抽出
├── import_receipts.py    # Step 2: 抽出データをAPIに投入
├── cleanup_receipts.py   # Step 3: 投入データを全件削除
├── receipts_data.json    # Step 1の出力 ← Gitignore対象
├── imported_ids.json     # Step 2の出力（inserted_ids がある場合）← Gitignore対象
└── README.md
```

---

## 事前準備

### 1. 依存パッケージのインストール

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

### 2. `.env` の設定

`backend/.env` に以下を追加:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
DEV_AUTH_TOKEN=your_dev_token_here   # 省略時は "test-token"
API_BASE_URL=http://localhost:8000   # 省略時はこの値
```

---

## 実行手順

すべて **`backend/` ディレクトリから** 実行してください。

### Step 1: 領収書データの抽出

```bash
python scripts/test_data/extract_receipts.py
```

- `source/receipts/` 内の全ファイルをGemini Visionで解析
- 結果を `receipts_data.json` に出力
- 失敗したファイルはスキップしてログ表示

### Step 2: APIへの投入

```bash
python scripts/test_data/import_receipts.py
```

- `receipts_data.json` を読み込み `POST /api/v1/receipts/batch` に投入
- バックエンドが起動していることを確認してから実行

### Step 3: テストデータの削除（後片付け）

```bash
python scripts/test_data/cleanup_receipts.py
```

- `imported_ids.json` を読み込み `DELETE /api/v1/receipts/{id}` を全件実行
- 完了後に `imported_ids.json` 自体を削除

---

## 対応ファイル形式

| 形式 | 処理方法 |
|------|---------|
| JPEG / JPG | そのままGemini Visionに渡す |
| PDF（標準形式） | PyMuPDFで画像変換してGemini Visionに渡す |
| PDF（ZIP形式） | 展開してJPEGを取得し、Gemini Visionに渡す |

ZIP展開先: `/tmp/receipt_extracted/`
