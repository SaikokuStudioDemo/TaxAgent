"""
Tax-Agent データ検証スクリプト
seed.py 実行後に各テーブルのデータを確認する。

使い方:
  cd backend && PYTHONPATH=. python scripts/verify_data.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings


async def verify():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]

    corp = await db["corporates"].find_one(
        {"corporateType": "corporate"}
    )
    if not corp:
        print("❌ 企業データが見つかりません")
        return

    cid = str(corp["_id"])
    print(f"=== Tax-Agent データ検証 ===")
    print(f"対象企業: {corp.get('name', cid)}\n")

    checks = []

    # Layer 1 基本確認
    for label, collection in [
        ("transactions", "transactions"),
        ("receipts", "receipts"),
        ("invoices", "invoices"),
        ("bank_import_files", "bank_import_files"),
    ]:
        count = await db[collection].count_documents(
            {"corporate_id": cid}
        )
        checks.append((f"{label} 件数", count, count > 0))

    # Layer 2: auto_expense
    ae_count = await db["matches"].count_documents({
        "corporate_id": cid,
        "match_type": "auto_expense",
        "is_active": {"$ne": False},
    })
    checks.append(("auto_expense matches", ae_count, ae_count > 0))

    # Layer 2: cash_transactions（自動登録）
    cash_count = await db["cash_transactions"].count_documents({
        "corporate_id": cid,
        "source": "bank_import",
    })
    checks.append(("cash_transactions（自動）", cash_count, cash_count > 0))

    # Layer 2: transferred
    transferred = await db["transactions"].count_documents({
        "corporate_id": cid,
        "status": "transferred",
    })
    checks.append(("status: transferred", transferred, transferred > 0))

    # Layer 2: 承認ルール適用
    rule_applied = await db["receipts"].count_documents({
        "corporate_id": cid,
        "approval_rule_id": {"$exists": True},
    })
    checks.append(("承認ルール適用済み領収書", rule_applied, rule_applied > 0))

    # 現金口座残高
    cash_account = await db["cash_accounts"].find_one(
        {"corporate_id": cid}
    )
    if cash_account:
        balance = cash_account.get("current_balance", 0)
        initial = cash_account.get("initial_balance", 0)
        checks.append((
            f"現金口座残高更新 (¥{balance:,})",
            balance,
            balance != initial
        ))

    # 結果表示
    passed = sum(1 for _, _, ok in checks if ok)
    total = len(checks)

    for label, value, ok in checks:
        icon = "✅" if ok else "❌"
        print(f"{icon} {label}: {value}")

    print(
        f"\n=== 結果: {passed}/{total} PASSED "
        f"{'✅' if passed == total else '❌'} ==="
    )

    if passed < total:
        print("\n⚠️  失敗項目があります。seed.py を再実行してください:")
        print("  PYTHONPATH=. python scripts/seed.py --reset")

    client.close()


if __name__ == "__main__":
    asyncio.run(verify())
