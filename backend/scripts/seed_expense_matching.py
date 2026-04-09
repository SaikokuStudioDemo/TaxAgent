"""
seed_expense_matching.py
経費消込（申請者グルーピング）の動作確認用テストデータを投入する。

やること:
  1. 従業員に bank_display_name をセット
  2. 既存の誤った領収書（submitted_by が法人ID）を削除
  3. 各従業員に紐づく領収書を追加（approval_status: approved）
  4. 経費精算振込の bank transactions を追加

使い方:
    cd backend
    PYTHONPATH=. venv/bin/python scripts/seed_expense_matching.py
"""
import asyncio
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

CORPORATE_ID = "69cb2265e0396c54a7c7f932"  # 株式会社アルファ

# 既存の従業員ID
EMP_SUZUKI  = "69cb2265e0396c54a7c7f92a"  # 鈴木 誠
EMP_TANAKA  = "69cb2265e0396c54a7c7f92b"  # 田中 克彦

# ──────────────────────────────────────────
# 従業員の銀行表記名
# ──────────────────────────────────────────
EMPLOYEE_BANK_NAMES = {
    EMP_SUZUKI: "スズキ マコト",
    EMP_TANAKA: "タナカ カツヒコ",
}

# ──────────────────────────────────────────
# 領収書テストデータ
# 合計が振込金額と一致するように設定
#   鈴木: ¥2,800 + ¥3,200 = ¥6,000
#   田中: ¥8,500 + ¥1,500 = ¥10,000
# ──────────────────────────────────────────
RECEIPTS = [
    # 鈴木 誠
    {
        "employee_id": EMP_SUZUKI,
        "payee": "日本交通",
        "amount": 2800,
        "date": "2025-02-10",
        "payment_method": "現金",
        "description": "客先訪問タクシー代",
        "fiscal_period": "2025-02",
    },
    {
        "employee_id": EMP_SUZUKI,
        "payee": "丸善書店",
        "amount": 3200,
        "date": "2025-02-12",
        "payment_method": "現金",
        "description": "業務関連書籍",
        "fiscal_period": "2025-02",
    },
    # 田中 克彦
    {
        "employee_id": EMP_TANAKA,
        "payee": "銀座 一〇八",
        "amount": 8500,
        "date": "2025-02-18",
        "payment_method": "現金",
        "description": "取引先接待会食",
        "fiscal_period": "2025-02",
    },
    {
        "employee_id": EMP_TANAKA,
        "payee": "JR東日本",
        "amount": 1500,
        "date": "2025-02-20",
        "payment_method": "現金",
        "description": "出張交通費",
        "fiscal_period": "2025-02",
    },
]

# ──────────────────────────────────────────
# 経費精算振込トランザクション
# 各従業員の領収書合計と一致させる
# ──────────────────────────────────────────
EXPENSE_TRANSACTIONS = [
    {
        "transaction_date": "2025-02-25",
        "description": "振込 スズキ マコト",
        "amount": 6000,   # 鈴木の合計
        "transaction_type": "debit",
        "account_name": "みずほ銀行 渋谷支店",
    },
    {
        "transaction_date": "2025-02-25",
        "description": "振込 タナカ カツヒコ",
        "amount": 10000,  # 田中の合計
        "transaction_type": "debit",
        "account_name": "みずほ銀行 渋谷支店",
    },
]


async def seed():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]

    print(f"\n対象 corporate_id: {CORPORATE_ID}\n")

    # ─── Step 1: 従業員に bank_display_name をセット ───
    print("=== Step 1: 従業員の銀行表記名を設定 ===")
    for emp_id, bank_name in EMPLOYEE_BANK_NAMES.items():
        result = await db["employees"].update_one(
            {"_id": ObjectId(emp_id)},
            {"$set": {"bank_display_name": bank_name}},
        )
        emp = await db["employees"].find_one({"_id": ObjectId(emp_id)})
        print(f"  {emp.get('name')} → bank_display_name: {bank_name} (modified: {result.modified_count})")

    # ─── Step 2: 誤った既存領収書を削除 ───
    print("\n=== Step 2: 誤った既存領収書を削除 ===")
    # submitted_by が法人IDになっているものを削除
    bad_receipts = await db["receipts"].delete_many({
        "corporate_id": CORPORATE_ID,
        "submitted_by": {"$in": [
            "69cb2265e0396c54a7c7f926",  # 青山税理士法人
            "69cb2265e0396c54a7c7f932",  # 株式会社アルファ自身
        ]},
    })
    print(f"  削除: {bad_receipts.deleted_count}件")

    # すでに今回のシード済み領収書があれば削除（冪等性のため）
    existing = await db["receipts"].delete_many({
        "corporate_id": CORPORATE_ID,
        "submitted_by": {"$in": [EMP_SUZUKI, EMP_TANAKA]},
        "reconciliation_status": "unreconciled",
    })
    if existing.deleted_count:
        print(f"  既存シードデータ削除: {existing.deleted_count}件（再投入）")

    # ─── Step 3: 正しい領収書を投入 ───
    print("\n=== Step 3: 領収書を投入 ===")
    for r in RECEIPTS:
        emp = await db["employees"].find_one({"_id": ObjectId(r["employee_id"])})
        emp_name = emp.get("name", "不明") if emp else "不明"

        doc = {
            "corporate_id": CORPORATE_ID,
            "submitted_by": r["employee_id"],
            "document_type": "receipt",
            "payee": r["payee"],
            "amount": r["amount"],
            "date": r["date"],
            "payment_method": r["payment_method"],
            "description": r["description"],
            "fiscal_period": r["fiscal_period"],
            "approval_status": "approved",       # 承認済み（消込対象）
            "reconciliation_status": "unreconciled",
            "current_step": 0,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        }
        result = await db["receipts"].insert_one(doc)
        print(f"  [{emp_name}] {r['payee']} ¥{r['amount']:,} → {result.inserted_id}")

    # ─── Step 4: 経費精算振込トランザクションを追加 ───
    print("\n=== Step 4: 経費精算振込トランザクションを追加 ===")

    # 既存の同名シードデータがあれば削除（冪等性）
    for tx in EXPENSE_TRANSACTIONS:
        await db["transactions"].delete_many({
            "corporate_id": CORPORATE_ID,
            "description": tx["description"],
            "amount": tx["amount"],
        })

    bank_file = await db["bank_import_files"].find_one({
        "corporate_id": CORPORATE_ID,
        "account_name": "みずほ銀行 渋谷支店",
    })
    import_file_id = str(bank_file["_id"]) if bank_file else None

    for tx in EXPENSE_TRANSACTIONS:
        doc = {
            "corporate_id": CORPORATE_ID,
            "source_type": "bank",
            "account_name": tx["account_name"],
            "transaction_date": tx["transaction_date"],
            "description": tx["description"],
            "amount": tx["amount"],
            "transaction_type": tx["transaction_type"],
            "status": "unmatched",
            "fiscal_period": tx["transaction_date"][:7],
            "import_file_id": import_file_id,
            "imported_at": datetime.utcnow(),
        }
        result = await db["transactions"].insert_one(doc)
        print(f"  {tx['transaction_date']} | {tx['description']} | ¥{tx['amount']:,} → {result.inserted_id}")

    # ─── 結果サマリー ───
    print("\n=== 結果サマリー ===")
    for emp_id, bank_name in EMPLOYEE_BANK_NAMES.items():
        emp = await db["employees"].find_one({"_id": ObjectId(emp_id)})
        receipts = await db["receipts"].find({
            "corporate_id": CORPORATE_ID,
            "submitted_by": emp_id,
            "reconciliation_status": "unreconciled",
        }).to_list(10)
        total = sum(r.get("amount", 0) for r in receipts)
        print(f"  {emp.get('name')} ({bank_name}): 領収書{len(receipts)}件 合計¥{total:,}")

    unmatched_debit = await db["transactions"].count_documents({
        "corporate_id": CORPORATE_ID,
        "transaction_type": "debit",
        "status": "unmatched",
    })
    print(f"  未消込 debit transactions: {unmatched_debit}件")

    client.close()
    print("\n✅ 完了")


asyncio.run(seed())
