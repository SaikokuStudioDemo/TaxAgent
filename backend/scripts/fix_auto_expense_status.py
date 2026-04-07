"""
既存の auto_expense マッチング済みデータの status を修正するワンタイムスクリプト。
実装前にインポートされた振込手数料・ETCデータを matched に更新する。

実行方法:
  cd backend
  PYTHONPATH=. python scripts/fix_auto_expense_status.py
"""
import asyncio
from bson import ObjectId
from app.db.mongodb import get_database
from app.services.auto_expense_rules import match_auto_expense


async def fix():
    from app.db.mongodb import connect_to_mongo, close_mongo_connection
    await connect_to_mongo()
    db = get_database()

    # unmatched の全 transactions を取得
    txs = await db["transactions"].find(
        {"status": {"$in": ["unmatched", None, ""]}}
    ).to_list(length=10000)

    fixed_count = 0
    for tx in txs:
        rule = match_auto_expense(tx)
        if rule is None:
            continue

        # 既に matches に auto_expense レコードがあるか確認
        existing = await db["matches"].find_one({
            "transaction_ids": str(tx["_id"]),
            "match_type": "auto_expense",
        })

        if existing is None:
            # matches に追加
            from datetime import datetime
            match_doc = {
                "corporate_id": tx["corporate_id"],
                "match_type": "auto_expense",
                "transaction_ids": [str(tx["_id"])],
                "document_ids": [],
                "total_transaction_amount": tx.get("amount", 0),
                "total_document_amount": 0,
                "difference": 0,
                "matched_by": "system",
                "no_document_reason": rule["name"],
                "auto_rule_key": rule["key"],
                "account_subject": rule["account_subject"],
                "tax_division": rule["tax_division"],
                "fiscal_period": tx.get("fiscal_period", ""),
                "matched_at": datetime.utcnow(),
                "auto_suggested": False,
                "user_action": "system",
                "score": None,
                "score_breakdown": None,
            }
            await db["matches"].insert_one(match_doc)

        # transaction の status を matched に更新
        await db["transactions"].update_one(
            {"_id": tx["_id"]},
            {"$set": {"status": "matched"}}
        )
        fixed_count += 1
        print(f"Fixed: {tx.get('description')} ({tx.get('amount')}円)")

    print(f"\n完了: {fixed_count}件を修正しました")


if __name__ == "__main__":
    asyncio.run(fix())
