"""
reseed_transactions.py
transactions / cash_transactions / bank_import_files / auto_expense matches を
一度クリアし、ATMデータを含むテスト用銀行・カード明細を再投入する。

インポートAPIを直接呼ぶことで
  - match_auto_expense（自動経費ルール）
  - match_cash_transaction（現金検知: ATM出金→income / ATM入金→expense）
の両ロジックが正しく動作するかを確認できる。

使い方:
    cd backend
    PYTHONPATH=. venv/bin/python scripts/reseed_transactions.py
"""
import asyncio
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.services.auto_expense_rules import match_auto_expense, match_cash_transaction

CORPORATE_ID = "69cb2265e0396c54a7c7f932"  # seed_corp_a_uid

# ──────────────────────────────────────────────
# テスト用銀行明細データ
# ATM出金（debit）→ cash_direction=income（現金受取）
# ATM入金（credit）→ cash_direction=expense（現金預入）
# ──────────────────────────────────────────────
BANK_TRANSACTIONS = [
    # ─── ATM系（現金検知対象）───
    {"transaction_date": "2025-01-10", "description": "セブンATM出金",      "amount": 50000,  "transaction_type": "debit",  "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-01-15", "description": "セブンATM入金",      "amount": 30000,  "transaction_type": "credit", "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-01-20", "description": "EネットATM出金",     "amount": 100000, "transaction_type": "debit",  "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-01-22", "description": "EネットATM入金",     "amount": 80000,  "transaction_type": "credit", "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-02-05", "description": "セブンATM出金",      "amount": 200000, "transaction_type": "debit",  "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-02-10", "description": "ローソンATM出金",    "amount": 30000,  "transaction_type": "debit",  "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-02-24", "description": "ATM出金",            "amount": 10000,  "transaction_type": "debit",  "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-02-28", "description": "引出し",             "amount": 20000,  "transaction_type": "debit",  "account_name": "みずほ銀行 渋谷支店"},
    # ─── 通常の銀行取引 ───
    {"transaction_date": "2025-01-05", "description": "振込 カ）エースリメイク", "amount": 260000, "transaction_type": "credit", "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-01-08", "description": "振込手数料",              "amount": 165,    "transaction_type": "debit",  "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-02-15", "description": "スピー 紹介料",           "amount": 396000, "transaction_type": "debit",  "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-02-20", "description": "まもりす倶楽部 会費",     "amount": 40800,  "transaction_type": "debit",  "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-03-01", "description": "売上入金 モックアルファ", "amount": 550000, "transaction_type": "credit", "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-03-10", "description": "決算利息",               "amount": 32,     "transaction_type": "credit", "account_name": "みずほ銀行 渋谷支店"},
    # ─── 自動経費マッチ対象 ───
    {"transaction_date": "2025-01-31", "description": "アマゾン ウェブ サービス", "amount": 12000, "transaction_type": "debit", "account_name": "みずほ銀行 渋谷支店"},
    {"transaction_date": "2025-02-28", "description": "freee",                   "amount": 3980,  "transaction_type": "debit", "account_name": "みずほ銀行 渋谷支店"},
]

CARD_TRANSACTIONS = [
    {"transaction_date": "2025-01-12", "description": "ビックカメラ",        "amount": 55000,  "transaction_type": "debit",  "account_name": "オリコカード"},
    {"transaction_date": "2025-01-25", "description": "ヤマト運輸",          "amount": 2200,   "transaction_type": "debit",  "account_name": "オリコカード"},
    {"transaction_date": "2025-02-03", "description": "アマゾン",            "amount": 8800,   "transaction_type": "debit",  "account_name": "オリコカード"},
    {"transaction_date": "2025-02-18", "description": "コーヒーショップ",    "amount": 1500,   "transaction_type": "debit",  "account_name": "オリコカード"},
    {"transaction_date": "2025-03-05", "description": "交通費 Suica",        "amount": 15000,  "transaction_type": "debit",  "account_name": "オリコカード"},
]


async def reseed():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]

    print(f"\n対象 corporate_id: {CORPORATE_ID}\n")

    # ─── Step 1: クリア ───
    print("=== Step 1: 既存データ削除 ===")

    tx_ids = [str(t["_id"]) async for t in db["transactions"].find({"corporate_id": CORPORATE_ID})]
    print(f"  transactions: {len(tx_ids)}件削除予定")

    # transactions に紐づく matches（auto_expense）を削除
    match_del = await db["matches"].delete_many({
        "corporate_id": CORPORATE_ID,
        "match_type": "auto_expense",
    })
    print(f"  auto_expense matches: {match_del.deleted_count}件削除")

    tx_del = await db["transactions"].delete_many({"corporate_id": CORPORATE_ID})
    print(f"  transactions: {tx_del.deleted_count}件削除")

    cash_del = await db["cash_transactions"].delete_many({"corporate_id": CORPORATE_ID})
    print(f"  cash_transactions: {cash_del.deleted_count}件削除")

    file_del = await db["bank_import_files"].delete_many({"corporate_id": CORPORATE_ID})
    print(f"  bank_import_files: {file_del.deleted_count}件削除")

    # cash_account 残高をリセット
    cash_account = await db["cash_accounts"].find_one({"corporate_id": CORPORATE_ID})
    if cash_account:
        initial = cash_account.get("initial_balance", 100000)
        await db["cash_accounts"].update_one(
            {"_id": cash_account["_id"]},
            {"$set": {"current_balance": initial}}
        )
        print(f"  cash_account残高リセット → ¥{initial:,}")
    else:
        # cash_accountがなければ作成
        res = await db["cash_accounts"].insert_one({
            "corporate_id": CORPORATE_ID,
            "name": "現金",
            "initial_balance": 100000,
            "current_balance": 100000,
            "created_at": datetime.utcnow(),
        })
        cash_account = await db["cash_accounts"].find_one({"_id": res.inserted_id})
        print(f"  cash_account新規作成: ¥100,000")

    # ─── Step 2: インポートファイルレコード作成 ───
    print("\n=== Step 2: インポートファイル登録 ===")

    bank_file = await db["bank_import_files"].insert_one({
        "corporate_id": CORPORATE_ID,
        "source_type": "bank",
        "account_name": "みずほ銀行 渋谷支店",
        "file_name": "seed_bank_2025.csv",
        "file_type": "csv",
        "row_count": len(BANK_TRANSACTIONS),
        "status": "completed",
        "imported_at": datetime.utcnow(),
    })
    card_file = await db["bank_import_files"].insert_one({
        "corporate_id": CORPORATE_ID,
        "source_type": "card",
        "account_name": "オリコカード",
        "file_name": "seed_card_2025.csv",
        "file_type": "csv",
        "row_count": len(CARD_TRANSACTIONS),
        "status": "completed",
        "imported_at": datetime.utcnow(),
    })
    print(f"  bank_import_files: 2件登録")

    # ─── Step 3: transactions 投入 + ロジック実行 ───
    print("\n=== Step 3: transactions 投入 + 自動処理 ===")

    all_entries = (
        [(t, "bank", str(bank_file.inserted_id)) for t in BANK_TRANSACTIONS] +
        [(t, "card", str(card_file.inserted_id)) for t in CARD_TRANSACTIONS]
    )

    auto_expense_count = 0
    cash_transfer_count = 0

    for tx_data, source_type, import_file_id in all_entries:
        date_str = tx_data["transaction_date"]
        fiscal_period = date_str[:7]

        doc = {
            "corporate_id": CORPORATE_ID,
            "source_type": source_type,
            "account_name": tx_data["account_name"],
            "transaction_date": date_str,
            "description": tx_data["description"],
            "amount": tx_data["amount"],
            "transaction_type": tx_data["transaction_type"],
            "status": "unmatched",
            "fiscal_period": fiscal_period,
            "import_file_id": import_file_id,
            "imported_at": datetime.utcnow(),
        }

        result = await db["transactions"].insert_one(doc)
        inserted_id = result.inserted_id

        # 自動経費ルール照合
        rule = match_auto_expense(doc)
        if rule:
            await db["matches"].insert_one({
                "corporate_id": CORPORATE_ID,
                "match_type": "auto_expense",
                "transaction_ids": [str(inserted_id)],
                "document_ids": [],
                "total_transaction_amount": doc["amount"],
                "total_document_amount": 0,
                "difference": 0,
                "matched_by": "system",
                "no_document_reason": rule["name"],
                "auto_rule_key": rule["key"],
                "account_subject": rule["account_subject"],
                "tax_division": rule["tax_division"],
                "fiscal_period": fiscal_period,
                "matched_at": datetime.utcnow(),
                "auto_suggested": False,
                "user_action": "system",
            })
            await db["transactions"].update_one(
                {"_id": inserted_id}, {"$set": {"status": "matched"}}
            )
            auto_expense_count += 1
            print(f"  [AUTO] {date_str} | {tx_data['description']} | ¥{tx_data['amount']:,} → {rule['name']}")
            continue

        # 現金検知ルール照合
        cash_rule = match_cash_transaction(doc)
        if cash_rule:
            cash_acct = await db["cash_accounts"].find_one({"corporate_id": CORPORATE_ID})
            if cash_acct:
                await db["cash_transactions"].insert_one({
                    "corporate_id": CORPORATE_ID,
                    "cash_account_id": str(cash_acct["_id"]),
                    "transaction_date": date_str,
                    "amount": doc["amount"],
                    "direction": cash_rule["cash_direction"],
                    "description": doc["description"],
                    "category": cash_rule["category"],
                    "fiscal_period": fiscal_period,
                    "source": "bank_import",
                    "linked_bank_transaction_id": str(inserted_id),
                    "status": "unmatched",
                    "created_at": datetime.utcnow(),
                })
                balance = cash_acct.get("current_balance", 0)
                new_balance = balance + doc["amount"] if cash_rule["cash_direction"] == "income" else balance - doc["amount"]
                await db["cash_accounts"].update_one(
                    {"_id": cash_acct["_id"]}, {"$set": {"current_balance": new_balance}}
                )
                cash_acct["current_balance"] = new_balance

                await db["transactions"].update_one(
                    {"_id": inserted_id}, {"$set": {"status": "transferred"}}
                )
                cash_transfer_count += 1
                direction_label = "→ 現金受取(income)" if cash_rule["cash_direction"] == "income" else "→ 現金預入(expense)"
                print(f"  [CASH] {date_str} | {tx_data['description']} ({tx_data['transaction_type']}) | ¥{doc['amount']:,} {direction_label}")

    # ─── Step 4: 結果サマリー ───
    print("\n=== 結果サマリー ===")
    total_tx = await db["transactions"].count_documents({"corporate_id": CORPORATE_ID})
    matched = await db["transactions"].count_documents({"corporate_id": CORPORATE_ID, "status": "matched"})
    transferred = await db["transactions"].count_documents({"corporate_id": CORPORATE_ID, "status": "transferred"})
    unmatched = await db["transactions"].count_documents({"corporate_id": CORPORATE_ID, "status": "unmatched"})
    total_cash = await db["cash_transactions"].count_documents({"corporate_id": CORPORATE_ID})
    cash_acct = await db["cash_accounts"].find_one({"corporate_id": CORPORATE_ID})

    print(f"  transactions: {total_tx}件")
    print(f"    matched(自動経費):    {matched}件")
    print(f"    transferred(現金移管): {transferred}件")
    print(f"    unmatched:            {unmatched}件")
    print(f"  cash_transactions: {total_cash}件")
    print(f"  cash_account残高: ¥{cash_acct['current_balance']:,}")

    client.close()
    print("\n✅ 完了")


asyncio.run(reseed())
