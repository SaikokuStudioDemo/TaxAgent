"""
孤立 transaction（matches なし）に対して matches レコードをバックフィルする。

パターンA: status=matched  + social_insurance ルール相当
  → match_type: "auto_expense", account_subject: "法定福利費"

パターンB: status=transferred + cash_detection ルール相当（ATM系）
  → match_type: "transfer", account_subject: "現金"

使い方:
    cd backend
    venv/bin/python3 scripts/backfill_orphan_matches.py           # dry-run
    venv/bin/python3 scripts/backfill_orphan_matches.py --execute # 実行
"""
import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.services.auto_expense_rules import match_auto_expense, match_cash_transaction


async def main(execute: bool = False):
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]

    corp = await db["corporates"].find_one({"corporateType": "corporate"})
    cid = str(corp["_id"])
    print(f"corporate: {corp.get('name')} (id={cid})")
    print(f"モード: {'🚀 実行' if execute else '🔍 DRY RUN（確認のみ）'}\n")

    # ── 全 matched/transferred transactions を取得 ─────────────
    matched_txs = await db["transactions"].find(
        {"corporate_id": cid, "status": {"$in": ["matched", "transferred"]}}
    ).to_list(length=10000)

    # ── matches に登録済みの transaction_ids を収集 ────────────
    all_matches = await db["matches"].find(
        {"corporate_id": cid, "is_active": {"$ne": False}}
    ).to_list(length=50000)

    matched_ids_in_matches: set[str] = set()
    for m in all_matches:
        for tid in m.get("transaction_ids", []):
            matched_ids_in_matches.add(str(tid))

    # ── 孤立 transactions を抽出 ───────────────────────────────
    orphans = [t for t in matched_txs if str(t["_id"]) not in matched_ids_in_matches]

    # ── パターン分類 ───────────────────────────────────────────
    pattern_a: list[dict] = []  # social_insurance (auto_expense)
    pattern_b: list[dict] = []  # ATM系 (cash → transfer)
    unclassified: list[dict] = []

    for t in orphans:
        if t.get("status") == "matched":
            rule = match_auto_expense(t)
            if rule:
                t["_matched_rule"] = rule
                pattern_a.append(t)
            else:
                unclassified.append(t)
        elif t.get("status") == "transferred":
            cash_rule = match_cash_transaction(t)
            if cash_rule:
                t["_cash_rule"] = cash_rule
                pattern_b.append(t)
            else:
                unclassified.append(t)

    # ── 確認表示 ───────────────────────────────────────────────
    print(f"孤立 transactions 合計: {len(orphans)} 件")
    print(f"  パターンA (auto_expense): {len(pattern_a)} 件")
    print(f"  パターンB (cash→transfer): {len(pattern_b)} 件")
    print(f"  未分類 (手動確認要): {len(unclassified)} 件")

    if pattern_a:
        print("\n--- パターンA 詳細 ---")
        for t in pattern_a:
            rule = t["_matched_rule"]
            print(f"  [{t.get('transaction_date','')}] {t.get('description','')}  "
                  f"¥{t.get('amount',0):,}  → {rule['account_subject']}")

    if pattern_b:
        print("\n--- パターンB 詳細 ---")
        for t in pattern_b:
            print(f"  [{t.get('transaction_date','')}] {t.get('description','')}  "
                  f"¥{t.get('amount',0):,}")

    if unclassified:
        print("\n--- 未分類（スキップ） ---")
        for t in unclassified:
            print(f"  [{t.get('status','')}] [{t.get('transaction_date','')}] "
                  f"{t.get('description','')}  ¥{t.get('amount',0):,}")

    total_to_insert = len(pattern_a) + len(pattern_b)
    print(f"\n登録予定: {total_to_insert} 件（スキップ: {len(unclassified)} 件）")

    if not execute:
        print("\n⚠️  DRY RUN 完了。実際に実行するには --execute をつけてください。")
        client.close()
        return

    if total_to_insert == 0:
        print("登録対象なし。終了します。")
        client.close()
        return

    # ── 実行 ───────────────────────────────────────────────────
    print("\n実行中...")
    inserted = 0

    # パターンA: auto_expense
    for t in pattern_a:
        rule = t["_matched_rule"]
        tx_id = str(t["_id"])
        match_doc = {
            "corporate_id": cid,
            "match_type": "auto_expense",
            "transaction_ids": [tx_id],
            "document_ids": [],
            "total_transaction_amount": t.get("amount", 0),
            "total_document_amount": 0,
            "difference": 0,
            "matched_by": "system",
            "no_document_reason": rule["name"],
            "auto_rule_key": rule["key"],
            "account_subject": rule["account_subject"],
            "tax_division": rule["tax_division"],
            "fiscal_period": t.get("fiscal_period", ""),
            "matched_at": t.get("imported_at", datetime.utcnow()),
            "is_active": True,
            "auto_suggested": False,
            "user_action": "system",
            "backfilled_at": datetime.utcnow(),
        }
        await db["matches"].insert_one(match_doc)
        print(f"  ✅ [A] {t.get('description','')}  → {rule['account_subject']}")
        inserted += 1

    # パターンB: cash→transfer
    for t in pattern_b:
        tx_id = str(t["_id"])
        match_doc = {
            "corporate_id": cid,
            "match_type": "transfer",
            "transaction_ids": [tx_id],
            "document_ids": [],
            "total_transaction_amount": t.get("amount", 0),
            "total_document_amount": 0,
            "difference": 0,
            "matched_by": "system",
            "account_subject": "現金",
            "tax_division": "対象外",
            "fiscal_period": t.get("fiscal_period", ""),
            "matched_at": t.get("imported_at", datetime.utcnow()),
            "is_active": True,
            "backfilled_at": datetime.utcnow(),
        }
        await db["matches"].insert_one(match_doc)
        print(f"  ✅ [B] {t.get('description','')}  → 現金振替")
        inserted += 1

    print(f"\n✅ 完了: {inserted} 件登録")
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(execute=args.execute))
