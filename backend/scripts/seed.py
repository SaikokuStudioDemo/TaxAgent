"""
Tax-Agent テストデータ投入スクリプト

SeedDataReference フォルダのPDF/画像を読み込み、
匿名化してAPIに投入する。

使い方:
  # キャッシュ生成（初回のみ・OCRが走る）
  cd backend && PYTHONPATH=. venv/bin/python3 scripts/seed.py --generate-cache

  # 特定月をDBに投入（キャッシュあり→即時、なし→OCR）
  cd backend && PYTHONPATH=. venv/bin/python3 scripts/seed.py --month 1

  # 全月一括投入
  cd backend && PYTHONPATH=. venv/bin/python3 scripts/seed.py --all-months

  # リセットして全月投入
  cd backend && PYTHONPATH=. venv/bin/python3 scripts/seed.py --reset --all-months

  # フルリセット（DBクリア、vendorクライアント削除）
  cd backend && PYTHONPATH=. venv/bin/python3 scripts/seed.py --full-reset
"""
import asyncio
import argparse
import base64
import json
import os
import re
import time
from pathlib import Path
from typing import List, Optional

import httpx
import google.generativeai as genai
from app.core.config import settings

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
DEV_TOKEN = os.getenv("DEV_AUTH_TOKEN", "test-token")

SEED_DIR = Path("/Users/yohei/Developer/TaxAgent/SeedDataReference")
CACHE_DIR = SEED_DIR / "cache"

# フォルダ名 → source_type のマッピング（大文字小文字を無視した部分一致）
BANK_FOLDER_NAMES = ["預金", "通帳", "みずほ", "paypay", "みずほ銀行"]
CARD_FOLDER_NAMES = ["クレカ", "カード", "ローン", "smbc", "プレミア", "車のローン"]
RECEIPT_FOLDER_NAMES = ["領収書", "領収証"]
INVOICE_FOLDER_NAMES = ["請求書"]
SALES_FOLDER_NAMES = ["売上"]

# payment_method 正規化マップ
PAYMENT_METHOD_MAP = {
    "クレジットカード": "法人カード",
    "クレカ": "法人カード",
    "カード払い": "法人カード",
    "カード": "法人カード",
    "credit": "法人カード",
    "法人クレジット": "法人カード",
    "現金払い": "現金",
    "cash": "現金",
    "振り込み": "銀行振込",
    "振込": "銀行振込",
    "transfer": "銀行振込",
    "立替払い": "立替",
    "立て替え": "立替",
}

ALLOWED_PAYMENT_METHODS = {"立替", "法人カード", "銀行振込", "現金"}


def normalize_payment_method(raw: str) -> str:
    if not raw:
        return "立替"
    raw_lower = raw.lower()
    for key, val in PAYMENT_METHOD_MAP.items():
        if key.lower() in raw_lower:
            return val
    if raw in ALLOWED_PAYMENT_METHODS:
        return raw
    return "立替"


# 月フォルダ名のパターン
MONTH_PATTERN = re.compile(r'^(\d{1,2})月$')


def get_month_folders() -> list:
    """月フォルダを番号順に返す"""
    months = []
    for folder in SEED_DIR.iterdir():
        if folder.is_dir():
            m = MONTH_PATTERN.match(folder.name)
            if m:
                months.append((int(m.group(1)), folder))
    return sorted(months, key=lambda x: x[0])


def get_pdf_files(folder: Path) -> list:
    """フォルダ内のPDF・画像ファイルを再帰的に取得"""
    extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    files = []
    for f in folder.rglob("*"):
        if f.is_file() and f.suffix.lower() in extensions:
            files.append(f)
    return sorted(files)


def month_str(month_num: int) -> str:
    return f"2025-{str(month_num).zfill(2)}"


def cache_path_for_month(month_num: int) -> Path:
    return CACHE_DIR / month_str(month_num)


# ──────────────────────────────────────────────────────────────────────────────
# Gemini helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _call_gemini_raw(file_path: Path, prompt: str) -> Optional[str]:
    """Geminiにファイルを送りテキストを返す共通処理"""
    genai.configure(api_key=settings.GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        mime_type = "application/pdf"
    elif suffix in {".jpg", ".jpeg"}:
        mime_type = "image/jpeg"
    else:
        mime_type = "image/png"

    b64 = base64.b64encode(file_bytes).decode()

    try:
        response = model.generate_content([{
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": b64}},
                {"text": prompt},
            ]
        }])
        return response.text.strip()
    except Exception as e:
        print(f"    ❌ Gemini エラー: {e}")
    return None


async def call_gemini(file_path: Path, prompt: str) -> Optional[dict]:
    text = await _call_gemini_raw(file_path, prompt)
    if not text:
        return None
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"    ❌ JSON解析エラー: {e}")
    return None


async def call_gemini_list(file_path: Path, prompt: str) -> Optional[list]:
    text = await _call_gemini_raw(file_path, prompt)
    if not text:
        return None
    try:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"    ❌ JSON解析エラー: {e}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Cache generation（OCRを走らせてJSONに保存）
# ──────────────────────────────────────────────────────────────────────────────

async def extract_bank_image_transactions(
    file_path: Path,
    source_type: str,
    account_name: str,
) -> list:
    """JPG/PNG の銀行明細からGemini Visionでトランザクションリストを抽出"""
    prompt = """
この銀行・カード明細の画像から取引データを抽出してください。
JSON配列形式のみで返答（他テキスト不要）：
[
  {
    "transaction_date": "YYYY-MM-DD",
    "description": "摘要",
    "withdrawal_amount": 出金額（整数・なければ0）,
    "deposit_amount": 入金額（整数・なければ0）,
    "amount": 出金額と入金額の大きい方
  }
]
ヘッダー行・合計行・残高行は除外してください。
"""
    data = await call_gemini_list(file_path, prompt)
    if not data or not isinstance(data, list):
        print(f"    ⚠️  {file_path.name}: 画像からデータ抽出失敗")
        return []

    anon_account = account_name
    result = []
    for t in data:
        desc = t.get("description", "")
        w = t.get("withdrawal_amount", 0) or 0
        d = t.get("deposit_amount", 0) or 0
        result.append({
            "transaction_date": t.get("transaction_date", ""),
            "description": desc,
            "withdrawal_amount": w,
            "deposit_amount": d,
            "amount": t.get("amount", 0) or max(w, d),
            "transaction_type": "debit" if w >= d else "credit",
        })
    return result


async def extract_bank_pdf_transactions(
    client: httpx.AsyncClient,
    file_path: Path,
    source_type: str,
    account_name: str,
) -> list:
    """PDFの銀行明細をバックエンドパーサーで抽出（/extract-pdf）"""
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    anon_account = account_name

    res = await client.post(
        "/transactions/extract-pdf",
        files={"file": (file_path.name, file_bytes, "application/pdf")},
    )

    if res.status_code != 200:
        print(f"    ❌ {file_path.name}: extract-pdf 失敗 {res.text[:100]}")
        return []

    transactions = res.json().get("transactions", [])
    result = []
    for t in transactions:
        w = t.get("withdrawal_amount", 0) or 0
        d = t.get("deposit_amount", 0) or 0
        result.append({
            "transaction_date": t.get("date", t.get("transaction_date", "")),
            "description": t.get("description", ""),
            "withdrawal_amount": w,
            "deposit_amount": d,
            "amount": t.get("amount", 0) or max(w, d),
            "transaction_type": t.get("transaction_type", "debit" if w >= d else "credit"),
        })
    return result


async def extract_receipt(file_path: Path, month_num: int) -> Optional[dict]:
    """領収書PDFからGeminiでデータ抽出"""
    prompt = """
この領収書から以下のデータを抽出してください。
JSON形式のみで返答（他のテキスト不要）：
{
  "date": "YYYY-MM-DD",
  "amount": 金額（整数・税込）,
  "tax_rate": 税率（8または10の整数）,
  "payee": "支払先名",
  "category": "勘定科目（消耗品費/交通費/接待交際費/通信費/会議費/その他経費から選択）",
  "payment_method": "支払方法（現金/法人カード/銀行振込/立替から選択）"
}
日付が不明な場合は今月の1日を使用。金額が不明な場合は0。
"""
    data = await call_gemini(file_path, prompt)
    if not data:
        return None

    data["payment_method"] = normalize_payment_method(data.get("payment_method", ""))

    date_str = data.get("date", "")
    if date_str:
        data["fiscal_period"] = date_str[:7]
    else:
        data["fiscal_period"] = month_str(month_num)
        data["date"] = f"{month_str(month_num)}-01"

    return data


async def extract_invoice(file_path: Path, month_num: int, document_type: str) -> Optional[dict]:
    """請求書PDFからGeminiでデータ抽出"""
    prompt = f"""
この請求書から以下のデータを抽出してください。
JSON形式のみで返答（他のテキスト不要）：
{{
  "document_type": "{document_type}",
  "invoice_number": "請求書番号（不明な場合は空文字）",
  "client_name": "取引先名",
  "vendor_name": "請求元会社名（receivedの場合のみ・不明なら空文字）",
  "recipient_email": "送付先メールアドレス（不明な場合は空文字）",
  "issue_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "subtotal": 税抜金額（整数）,
  "tax_amount": 消費税額（整数）,
  "total_amount": 合計金額（整数・税込）,
  "line_items": [
    {{
      "description": "品目名",
      "amount": 金額（整数）,
      "tax_rate": 税率（8または10）,
      "category": "勘定科目"
    }}
  ]
}}
日付が不明な場合は今月の1日を使用。金額が不明な場合は0。
"""
    data = await call_gemini(file_path, prompt)
    if not data:
        return None

    if not data.get("invoice_number"):
        data["invoice_number"] = f"INV-{month_num:02d}-{int(time.time()) % 10000}"
    if not data.get("recipient_email"):
        data["recipient_email"] = "seed@test.example.com"
    if not data.get("subtotal"):
        total = data.get("total_amount", 0)
        tax = data.get("tax_amount", 0)
        data["subtotal"] = total - tax
    if not data.get("due_date"):
        data["due_date"] = data.get("issue_date", f"{month_str(month_num)}-01")

    date_str = data.get("issue_date", "")
    if date_str:
        data["fiscal_period"] = date_str[:7]
    else:
        data["fiscal_period"] = month_str(month_num)
        data["issue_date"] = f"{month_str(month_num)}-01"

    return data


async def generate_cache_for_month(
    client: httpx.AsyncClient,
    month_num: int,
    month_folder: Path,
):
    """1ヶ月分のOCRを実行してキャッシュJSONに保存"""
    mstr = month_str(month_num)
    cache_dir = CACHE_DIR / mstr
    cache_dir.mkdir(parents=True, exist_ok=True)

    tx_groups = []    # [{source_type, account_name, file_name, transactions:[...]}]
    receipts = []
    invoices = []

    for sub_folder in sorted(month_folder.iterdir()):
        if not sub_folder.is_dir():
            continue

        name = sub_folder.name
        name_lower = name.lower()

        if any(n in name_lower for n in BANK_FOLDER_NAMES):
            source_type = "bank"
        elif any(n in name_lower for n in CARD_FOLDER_NAMES):
            source_type = "card"
        else:
            source_type = None

        if source_type:
            print(f"\n  {'🏦' if source_type=='bank' else '💳'} {name}:")
            for f in get_pdf_files(sub_folder):
                suffix = f.suffix.lower()
                if suffix in {".jpg", ".jpeg", ".png"}:
                    txs = await extract_bank_image_transactions(f, source_type, name)
                else:
                    txs = await extract_bank_pdf_transactions(client, f, source_type, name)

                print(f"    ✅ {f.name}: {len(txs)}件")
                if txs:
                    tx_groups.append({
                        "source_type": source_type,
                        "account_name": name,
                        "file_name": f.name,
                        "transactions": txs,
                    })

        elif any(n in name_lower for n in RECEIPT_FOLDER_NAMES):
            print(f"\n  🧾 領収書（{name}）:")
            for f in get_pdf_files(sub_folder):
                data = await extract_receipt(f, month_num)
                if data:
                    receipts.append(data)
                    print(f"    ✅ {f.name}: 抽出完了")
                else:
                    print(f"    ⚠️  {f.name}: スキップ")

        elif any(n in name_lower for n in INVOICE_FOLDER_NAMES):
            print(f"\n  📄 受領請求書（{name}）:")
            for f in get_pdf_files(sub_folder):
                data = await extract_invoice(f, month_num, "received")
                if data:
                    invoices.append(data)
                    print(f"    ✅ {f.name}: 抽出完了")
                else:
                    print(f"    ⚠️  {f.name}: スキップ")

        elif any(n in name_lower for n in SALES_FOLDER_NAMES):
            print(f"\n  📊 発行請求書（{name}）:")
            for f in get_pdf_files(sub_folder):
                data = await extract_invoice(f, month_num, "issued")
                if data:
                    invoices.append(data)
                    print(f"    ✅ {f.name}: 抽出完了")
                else:
                    print(f"    ⚠️  {f.name}: スキップ")

        else:
            print(f"\n  ⚠️  不明なフォルダ: {name}（スキップ）")

    # JSONに保存
    (cache_dir / "transactions.json").write_text(json.dumps(tx_groups, ensure_ascii=False, indent=2))
    (cache_dir / "receipts.json").write_text(json.dumps(receipts, ensure_ascii=False, indent=2))
    (cache_dir / "invoices.json").write_text(json.dumps(invoices, ensure_ascii=False, indent=2))

    print(f"\n  💾 キャッシュ保存: {cache_dir}")
    print(f"     transactions: {sum(len(g['transactions']) for g in tx_groups)}件（{len(tx_groups)}ファイル）")
    print(f"     receipts    : {len(receipts)}件")
    print(f"     invoices    : {len(invoices)}件")


# ──────────────────────────────────────────────────────────────────────────────
# DB投入（キャッシュ優先）
# ──────────────────────────────────────────────────────────────────────────────

async def reset_layer1(token: str):
    """Layer 1データを直接DBから全削除"""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]
    corp = await db["corporates"].find_one({"corporateType": "corporate"})
    cid = str(corp["_id"])

    collections = [
        "matches", "cash_transactions", "transactions",
        "receipts", "invoices", "bank_import_files",
    ]
    for col in collections:
        result = await db[col].delete_many({"corporate_id": cid})
        print(f"  ✅ {col}: {result.deleted_count}件削除")

    client.close()
    print("✅ Layer 1 リセット完了")


async def full_reset():
    """
    フルリセット:
    1. invoices / transactions / receipts / matches / notifications を全件削除
    2. clients から client_type="vendor" を全件削除
    3. 残った clients の bank_display_names を [] にリセット
    """
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]
    corp = await db["corporates"].find_one({"corporateType": "corporate"})
    cid = str(corp["_id"])

    layer1_cols = [
        "invoices", "transactions", "receipts", "matches",
        "notifications", "cash_transactions", "bank_import_files",
    ]
    vendor_count = await db["clients"].count_documents({"corporate_id": cid, "client_type": "vendor"})
    customer_count = await db["clients"].count_documents({
        "corporate_id": cid,
        "client_type": {"$ne": "vendor"},
        "bank_display_names": {"$exists": True, "$ne": []},
    })

    print("\n=== 削除対象件数 ===")
    for col in layer1_cols:
        cnt = await db[col].count_documents({"corporate_id": cid})
        print(f"  {col}: {cnt}件")
    print(f"  clients (client_type=vendor): {vendor_count}件削除")
    print(f"  clients (bank_display_names リセット): {customer_count}件")

    print("\n上記を削除・リセットします。続行しますか？ [y/N]: ", end="", flush=True)
    answer = input().strip().lower()
    if answer != "y":
        print("キャンセルしました。")
        client.close()
        return False

    print("\n🗑️  Layer 1 削除中...")
    for col in layer1_cols:
        result = await db[col].delete_many({"corporate_id": cid})
        print(f"  ✅ {col}: {result.deleted_count}件削除")

    print("\n🗑️  vendor clients 削除中...")
    result = await db["clients"].delete_many({"corporate_id": cid, "client_type": "vendor"})
    print(f"  ✅ clients (vendor): {result.deleted_count}件削除")

    print("\n🔄 bank_display_names リセット中...")
    result = await db["clients"].update_many(
        {"corporate_id": cid},
        {"$set": {"bank_display_names": []}}
    )
    print(f"  ✅ clients (bank_display_names): {result.modified_count}件リセット")

    client.close()
    print("\n✅ フルリセット完了")

    client2 = AsyncIOMotorClient(settings.MONGODB_URI)
    db2 = client2[settings.MONGODB_DB_NAME]
    print("\n=== リセット後の件数 ===")
    for col in layer1_cols:
        cnt = await db2[col].count_documents({"corporate_id": cid})
        print(f"  {col}: {cnt}件")
    remaining_vendors = await db2["clients"].count_documents({"corporate_id": cid, "client_type": "vendor"})
    remaining_clients = await db2["clients"].count_documents({"corporate_id": cid})
    print(f"  clients (vendor残): {remaining_vendors}件")
    print(f"  clients (総数): {remaining_clients}件")
    client2.close()
    return True


async def ensure_alpha_employees() -> List[str]:
    """
    alpha法人の従業員を確認・更新し、employee _id のリストを返す。
    - 山田太郎: role=staff（既存、変更なし）
    - 佐藤花子: role=accounting に変更
    - 鈴木一郎: role=approver で追加（未存在時）
    戻り値: [山田太郎_id, 鈴木一郎_id, 佐藤花子_id]
    """
    from motor.motor_asyncio import AsyncIOMotorClient
    from bson import ObjectId

    mongo = AsyncIOMotorClient(settings.MONGODB_URI)
    db = mongo[settings.MONGODB_DB_NAME]

    corp = await db["corporates"].find_one({"corporateType": "corporate"})
    if not corp:
        raise RuntimeError("alpha法人が見つかりません")
    cid = str(corp["_id"])

    # 佐藤花子 → role: accounting に変更
    await db["employees"].update_one(
        {"corporate_id": cid, "name": "佐藤 花子"},
        {"$set": {"role": "accounting"}},
    )

    # 鈴木一郎 → 存在しなければ追加
    ichiro = await db["employees"].find_one({"corporate_id": cid, "name": "鈴木 一郎"})
    if not ichiro:
        result = await db["employees"].insert_one({
            "corporate_id": cid,
            "name": "鈴木 一郎",
            "email": "ichiro.suzuki@alpha.co.jp",
            "role": "approver",
            "firebase_uid": f"seed_alpha_ichiro_{cid[:8]}",
            "permissions": {},
            "usageFee": 0,
            "departmentId": "",
            "groupId": "",
        })
        ichiro_id = str(result.inserted_id)
    else:
        ichiro_id = str(ichiro["_id"])

    # 山田太郎・佐藤花子のIDを取得
    yamada = await db["employees"].find_one({"corporate_id": cid, "name": "山田 太郎"})
    sato = await db["employees"].find_one({"corporate_id": cid, "name": "佐藤 花子"})

    yamada_id = str(yamada["_id"]) if yamada else None
    sato_id = str(sato["_id"]) if sato else None

    mongo.close()

    ids = [i for i in [yamada_id, ichiro_id, sato_id] if i]
    print(f"  👥 alpha従業員ID: 山田={yamada_id}, 鈴木一郎={ichiro_id}, 佐藤={sato_id}")
    return ids


async def import_from_cache(
    client: httpx.AsyncClient,
    month_num: int,
    employee_ids: Optional[List[str]] = None,
) -> dict:
    """キャッシュJSONからDBに投入。件数dictを返す"""
    cache_dir = cache_path_for_month(month_num)
    counts = {"transactions": 0, "receipts": 0, "invoices_received": 0, "invoices_issued": 0}

    # ── transactions ─────────────────────────────────────────
    tx_file = cache_dir / "transactions.json"
    if tx_file.exists():
        tx_groups = json.loads(tx_file.read_text())
        for group in tx_groups:
            res = await client.post("/transactions", json=group)
            if res.status_code == 200:
                cnt = res.json().get("imported_count", 0)
                counts["transactions"] += cnt
                print(f"    ✅ {group['file_name']}: {cnt}件投入")
            else:
                print(f"    ❌ {group['file_name']}: {res.text[:100]}")

    # ── receipts ─────────────────────────────────────────────
    r_file = cache_dir / "receipts.json"
    if r_file.exists():
        receipts = json.loads(r_file.read_text())
        for i, r in enumerate(receipts):
            if employee_ids:
                r["submitted_by"] = employee_ids[i % len(employee_ids)]
            if "receipt_type" not in r:
                r["receipt_type"] = "expense"
            res = await client.post("/receipts", json=r)
            if res.status_code == 200:
                counts["receipts"] += 1
            else:
                print(f"    ❌ receipt: {res.text[:100]}")

    # ── invoices ─────────────────────────────────────────────
    inv_file = cache_dir / "invoices.json"
    if inv_file.exists():
        invoices = json.loads(inv_file.read_text())
        received_idx = 0
        for inv in invoices:
            if employee_ids and inv.get("document_type") == "received":
                inv["submitted_by"] = employee_ids[received_idx % len(employee_ids)]
                received_idx += 1
            if inv.get("document_type") == "issued":
                inv["approval_status"] = "auto_approved"
            res = await client.post("/invoices", json=inv)
            if res.status_code == 200:
                if inv.get("document_type") == "received":
                    counts["invoices_received"] += 1
                else:
                    counts["invoices_issued"] += 1
            else:
                print(f"    ❌ invoice: {res.text[:100]}")

    return counts


async def import_bank_image(
    client: httpx.AsyncClient,
    file_path: Path,
    source_type: str,
    account_name: str,
    month_str_val: str,
):
    """JPG/PNG の銀行明細画像をGemini Visionで読み込んで投入（キャッシュなし時）"""
    txs = await extract_bank_image_transactions(file_path, source_type, account_name)
    if not txs:
        return

    anon_account = account_name
    res = await client.post("/transactions", json={
        "source_type": source_type,
        "account_name": anon_account,
        "file_name": file_path.name,
        "transactions": txs,
    })
    if res.status_code == 200:
        print(f"    ✅ {file_path.name}（画像）: {res.json().get('imported_count', 0)}件投入")
    else:
        print(f"    ❌ {file_path.name}（画像）: {res.text[:100]}")


async def import_bank_pdf(
    client: httpx.AsyncClient,
    file_path: Path,
    source_type: str,
    account_name: str,
    month_str_val: str,
):
    """銀行・カードPDFを投入（キャッシュなし時）"""
    if file_path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        await import_bank_image(client, file_path, source_type, account_name, month_str_val)
        return

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    anon_account = account_name
    res = await client.post(
        "/transactions/import-pdf",
        files={"file": (file_path.name, file_bytes, "application/pdf")},
        data={"source_type": source_type, "account_name": anon_account, "file_name": file_path.name},
    )
    if res.status_code == 200:
        print(f"    ✅ {file_path.name}: {res.json().get('imported_count', 0)}件投入")
    else:
        print(f"    ❌ {file_path.name}: {res.text[:100]}")


async def process_month(
    token: str,
    month_num: int,
    month_folder: Path,
    employee_ids: Optional[List[str]] = None,
) -> dict:
    """1ヶ月分のデータを処理。キャッシュがあればそれを使う。件数dictを返す"""
    headers = {"Authorization": f"Bearer {token}"}
    mstr = month_str(month_num)
    cache_dir = cache_path_for_month(month_num)
    counts = {"transactions": 0, "receipts": 0, "invoices_received": 0, "invoices_issued": 0}

    async with httpx.AsyncClient(base_url=API_BASE, headers=headers, timeout=120.0) as client:

        # キャッシュがあれば使う
        if (cache_dir / "transactions.json").exists():
            print(f"  📦 キャッシュから投入中...")
            counts = await import_from_cache(client, month_num, employee_ids)
            return counts

        # キャッシュなし → 従来通りOCR
        print(f"  ⚠️  キャッシュなし → OCRで処理（時間がかかります）")

        for sub_folder in sorted(month_folder.iterdir()):
            if not sub_folder.is_dir():
                continue

            name = sub_folder.name
            name_lower = name.lower()

            if any(n in name_lower for n in BANK_FOLDER_NAMES):
                print(f"\n  🏦 銀行データ（{name}）:")
                for pdf in get_pdf_files(sub_folder):
                    await import_bank_pdf(client, pdf, "bank", name, mstr)

            elif any(n in name_lower for n in CARD_FOLDER_NAMES):
                print(f"\n  💳 カードデータ（{name}）:")
                for pdf in get_pdf_files(sub_folder):
                    await import_bank_pdf(client, pdf, "card", name, mstr)

            elif any(n in name_lower for n in RECEIPT_FOLDER_NAMES):
                print(f"\n  🧾 領収書（{name}）:")
                for f in get_pdf_files(sub_folder):
                    data = await extract_receipt(f, month_num)
                    if data:
                        res = await client.post("/receipts", json=data)
                        if res.status_code == 200:
                            counts["receipts"] += 1
                            print(f"    ✅ {f.name}")
                        else:
                            print(f"    ❌ {f.name}: {res.text[:100]}")
                    else:
                        print(f"    ⚠️  {f.name}: スキップ")

            elif any(n in name_lower for n in INVOICE_FOLDER_NAMES):
                print(f"\n  📄 受領請求書（{name}）:")
                for pdf in get_pdf_files(sub_folder):
                    data = await extract_invoice(pdf, month_num, "received")
                    if data:
                        res = await client.post("/invoices", json=data)
                        if res.status_code == 200:
                            counts["invoices_received"] += 1
                            print(f"    ✅ {pdf.name}")
                        else:
                            print(f"    ❌ {pdf.name}: {res.text[:100]}")

            elif any(n in name_lower for n in SALES_FOLDER_NAMES):
                print(f"\n  📊 発行請求書（{name}）:")
                for pdf in get_pdf_files(sub_folder):
                    data = await extract_invoice(pdf, month_num, "issued")
                    if data:
                        data["approval_status"] = "auto_approved"
                        res = await client.post("/invoices", json=data)
                        if res.status_code == 200:
                            counts["invoices_issued"] += 1
                            print(f"    ✅ {pdf.name}")
                        else:
                            print(f"    ❌ {pdf.name}: {res.text[:100]}")

            else:
                print(f"\n  ⚠️  不明なフォルダ: {name}（スキップ）")

    return counts


# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Tax-Agent テストデータ投入")
    parser.add_argument("--reset", action="store_true", help="Layer 1をリセットしてから投入")
    parser.add_argument("--full-reset", action="store_true", dest="full_reset",
                        help="全データ（Layer1 + vendor clients + bank_display_names）を削除")
    parser.add_argument("--month", type=int, help="特定月のみ投入（例: --month 1）")
    parser.add_argument("--all-months", action="store_true", dest="all_months", help="全月を一括投入")
    parser.add_argument("--generate-cache", action="store_true", dest="generate_cache",
                        help="OCRを実行してキャッシュJSONを生成（DBには投入しない）")
    parser.add_argument("--month-range", type=str, dest="month_range",
                        help="月の範囲を指定（例: --month-range 1-3）")
    args = parser.parse_args()

    print("=== Tax-Agent テストデータ投入 ===\n")

    # ── フルリセット ──────────────────────────────────────────
    if args.full_reset:
        await full_reset()
        return

    if not SEED_DIR.exists():
        print(f"❌ SeedDataReference フォルダが見つかりません: {SEED_DIR}")
        return

    # ── キャッシュ生成モード ──────────────────────────────────
    if args.generate_cache:
        month_folders = get_month_folders()
        if not month_folders:
            print("❌ 月フォルダが見つかりません")
            return

        # 月の絞り込み
        if args.month:
            month_folders = [(n, p) for n, p in month_folders if n == args.month]
        elif args.month_range:
            parts = args.month_range.split("-")
            start, end = int(parts[0]), int(parts[1])
            month_folders = [(n, p) for n, p in month_folders if start <= n <= end]

        print(f"📷 OCRキャッシュ生成モード（{len(month_folders)}ヶ月分）\n")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        headers = {"Authorization": f"Bearer {DEV_TOKEN}"}
        async with httpx.AsyncClient(base_url=API_BASE, headers=headers, timeout=120.0) as client:
            for month_num, month_folder in month_folders:
                print(f"\n📅 {month_num}月 のキャッシュ生成中...")
                await generate_cache_for_month(client, month_num, month_folder)

        print("\n\n=== キャッシュ生成完了 ===")
        print(f"保存先: {CACHE_DIR}")
        print("\n次のコマンドでDBに投入してください:")
        print("  PYTHONPATH=. venv/bin/python3 scripts/seed.py --all-months")
        return

    # ── DB投入モード ──────────────────────────────────────────
    token = DEV_TOKEN

    if args.reset:
        print("🔄 Layer 1 リセット中...")
        await reset_layer1(token)
        print()

    month_folders = get_month_folders()
    if not month_folders:
        print("❌ 月フォルダが見つかりません")
        return

    # 月の絞り込み
    if args.month:
        month_folders = [(n, p) for n, p in month_folders if n == args.month]
        if not month_folders:
            print(f"❌ {args.month}月のフォルダが見つかりません")
            return
    elif args.month_range:
        parts = args.month_range.split("-")
        start, end = int(parts[0]), int(parts[1])
        month_folders = [(n, p) for n, p in month_folders if start <= n <= end]
    elif not args.all_months:
        print("❌ --month / --all-months / --month-range のいずれかを指定してください")
        parser.print_help()
        return

    print("👥 alpha従業員を確認・更新中...")
    employee_ids = await ensure_alpha_employees()
    print()

    total = {"transactions": 0, "receipts": 0, "invoices_received": 0, "invoices_issued": 0}

    for month_num, month_folder in month_folders:
        print(f"\n📅 {month_num}月 のデータを投入中...")
        counts = await process_month(token, month_num, month_folder, employee_ids)
        for k, v in counts.items():
            total[k] += v
        print(f"  → transactions: {counts['transactions']}, receipts: {counts['receipts']}, "
              f"invoices(受): {counts['invoices_received']}, invoices(発): {counts['invoices_issued']}")

    print("\n\n=== 完了 ===")
    print(f"  transactions  : {total['transactions']}件")
    print(f"  receipts      : {total['receipts']}件")
    print(f"  invoices(受領): {total['invoices_received']}件")
    print(f"  invoices(発行): {total['invoices_issued']}件")
    print("\n次のコマンドで検証してください:")
    print("  PYTHONPATH=. venv/bin/python3 scripts/verify_data.py")


if __name__ == "__main__":
    asyncio.run(main())
