"""
「ATM入金」系のtransactionが誤ってdebitで保存されているものを修正するスクリプト。
合わせてcash_transactionsのdirectionとcash_accountsの残高も修正する。

対象: description に「入金」を含み「出金」を含まない bank transactions で transaction_type=debit のもの
修正:
  1. transactions.transaction_type: debit → credit
  2. cash_transactions.direction: income → expense（linked_bank_transaction_idで紐付け）
  3. cash_accounts.current_balance を再計算
     （誤ってincomeとして +amount した分を戻し、expenseとして -amount する → 合計 -2*amount）
"""
import asyncio
from bson import ObjectId
from app.db.mongodb import connect_to_mongo, get_database


# 「入金」を示すキーワード（「出金」を含むものは除外）
CREDIT_KEYWORDS = ["ATM入金", "ＡＴＭ入金"]


async def fix():
    await connect_to_mongo()
    db = get_database()

    # 修正対象のtransactionsを検索
    # - source_type: bank
    # - transaction_type: debit（誤保存）
    # - description に入金キーワードを含み、出金キーワードを含まない
    all_bank_txs = await db["transactions"].find({
        "source_type": "bank",
        "transaction_type": "debit",
    }).to_list(length=10000)

    target_txs = [
        t for t in all_bank_txs
        if any(kw in t.get("description", "") for kw in CREDIT_KEYWORDS)
        and "出金" not in t.get("description", "")
    ]

    print(f"修正対象transactions: {len(target_txs)}件")
    if not target_txs:
        print("対象なし。終了します。")
        return

    for tx in target_txs:
        tx_id = str(tx["_id"])
        desc = tx.get("description", "")
        amount = tx.get("amount", 0)
        print(f"  {tx.get('transaction_date')} / {desc} / ¥{amount:,}")

        # 1. transaction_type を credit に修正
        await db["transactions"].update_one(
            {"_id": tx["_id"]},
            {"$set": {"transaction_type": "credit"}}
        )

        # 2. 対応するcash_transactionを検索して direction を修正
        cash_tx = await db["cash_transactions"].find_one({
            "linked_bank_transaction_id": tx_id
        })
        if cash_tx is None:
            print(f"    [INFO] 対応するcash_transactionなし（スキップ）")
            continue

        old_direction = cash_tx.get("direction")
        if old_direction == "expense":
            print(f"    [SKIP] direction既にexpense")
            continue

        await db["cash_transactions"].update_one(
            {"_id": cash_tx["_id"]},
            {"$set": {"direction": "expense"}}
        )
        print(f"    cash_transaction direction: income → expense")

        # 3. cash_accounts残高を修正
        # バックフィル時に誤って +amount したので、-2*amount で補正
        account_id = cash_tx.get("cash_account_id")
        if not account_id:
            continue
        await db["cash_accounts"].update_one(
            {"_id": ObjectId(account_id)},
            {"$inc": {"current_balance": -2 * amount}}
        )
        print(f"    cash_accounts残高: -{2 * amount:,}（補正）")

    print(f"\n完了: {len(target_txs)}件修正")

    # 修正後の口座残高を表示
    accounts = await db["cash_accounts"].find().to_list(length=10)
    print("\n=== 修正後の口座残高 ===")
    for a in accounts:
        print(f"  {a.get('name')}: ¥{a.get('current_balance', 0):,}")


asyncio.run(fix())
