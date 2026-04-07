"""
既存のATM系bank transactionsをcash_transactionsにバックフィルするスクリプト。
インポート時の現金検知ロジックが追加される前に取り込まれたデータを対象とする。
"""
import asyncio
from app.db.mongodb import connect_to_mongo, get_database
from app.services.auto_expense_rules import match_cash_transaction
from datetime import datetime


async def backfill():
    await connect_to_mongo()
    db = get_database()

    # 既にcash_transactionsに登録済みのlinked_bank_transaction_idを収集
    existing = await db["cash_transactions"].distinct("linked_bank_transaction_id")
    existing_ids = set(str(e) for e in existing if e)
    print(f"既存のcash_transactions: {len(existing_ids)}件（スキップ対象）")

    # bank取引のうち status=unmatched のものを対象
    txs = await db["transactions"].find({
        "source_type": "bank",
        "status": "unmatched",
    }).to_list(length=1000)
    print(f"対象transactions: {len(txs)}件")

    matched = 0
    skipped = 0

    for tx in txs:
        tx_id = str(tx["_id"])

        # 既にcash_transactionsに登録済みならスキップ
        if tx_id in existing_ids:
            skipped += 1
            continue

        cash_rule = match_cash_transaction(tx)
        if cash_rule is None:
            continue

        corporate_id = tx.get("corporate_id")
        default_account = await db["cash_accounts"].find_one({
            "corporate_id": corporate_id
        })
        if default_account is None:
            print(f"  [SKIP] cash_accountが存在しない: corporate_id={corporate_id}")
            continue

        cash_doc = {
            "corporate_id": corporate_id,
            "cash_account_id": str(default_account["_id"]),
            "transaction_date": tx.get("transaction_date", ""),
            "amount": tx.get("amount", 0),
            "direction": cash_rule["cash_direction"],
            "description": tx.get("description", ""),
            "category": cash_rule["category"],
            "fiscal_period": tx.get("fiscal_period", ""),
            "source": "bank_import",
            "linked_bank_transaction_id": tx_id,
            "status": "unmatched",
            "created_at": datetime.utcnow(),
        }
        await db["cash_transactions"].insert_one(cash_doc)

        # 口座残高を更新
        amount = tx.get("amount", 0)
        current_balance = default_account.get("current_balance", 0)
        new_balance = current_balance + amount if cash_rule["cash_direction"] == "income" else current_balance - amount
        await db["cash_accounts"].update_one(
            {"_id": default_account["_id"]},
            {"$set": {"current_balance": new_balance}}
        )
        # default_accountのキャッシュを更新（同一ループ内で複数件処理するため）
        default_account["current_balance"] = new_balance

        print(f"  [OK] {tx.get('transaction_date')} / {tx.get('description')} / {cash_rule['cash_direction']} / ¥{amount:,}")
        matched += 1

    print(f"\n完了: {matched}件登録 / {skipped}件スキップ")


asyncio.run(backfill())
