"""
debug_matching.py
未消込の transactions と receipts を金額で突合し、
実際にどんなペアが組まれうるかを可視化する。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.mongodb import connect_to_mongo, get_database, close_mongo_connection

CORP_A_UID = "seed_corp_a_uid"


async def main():
    await connect_to_mongo()
    db = get_database()

    # 法人A の corporate_id を取得
    corp = await db["corporates"].find_one({"firebase_uid": CORP_A_UID})
    if not corp:
        print("❌ 法人A が見つかりません")
        return
    corp_id = str(corp["_id"])
    print(f"法人A corporate_id: {corp_id}\n")

    # 未消込の transactions（bank/card）
    txs = await db["transactions"].find({
        "corporate_id": corp_id,
        "status": {"$in": ["unmatched", None, ""]},
    }).sort("date", 1).to_list(length=500)

    # 未消込の receipts
    receipts = await db["receipts"].find({
        "corporate_id": corp_id,
        "reconciliation_status": {"$in": ["unreconciled", None, ""]},
    }).sort("date", 1).to_list(length=500)

    print(f"未消込 transactions: {len(txs)} 件")
    print(f"未消込 receipts:     {len(receipts)} 件\n")

    # 金額 → receipts のマップ（複数ある場合も保持）
    receipt_by_amount: dict[int, list] = {}
    for r in receipts:
        amt = int(r.get("amount", 0))
        receipt_by_amount.setdefault(amt, []).append(r)

    # 突合結果
    exact_pairs = []      # 1対1で確定
    ambiguous_pairs = []  # 1対多（曖昧）
    unmatched_txs = []    # 対応なし

    for t in txs:
        amt = int(t.get("amount", 0))
        matched = receipt_by_amount.get(amt, [])
        if len(matched) == 1:
            exact_pairs.append((t, matched[0]))
        elif len(matched) > 1:
            ambiguous_pairs.append((t, matched))
        else:
            unmatched_txs.append(t)

    # ── 表示 ───────────────────────────────────────────────────────
    W = 100
    print("=" * W)
    print(f"【確定ペア】 {len(exact_pairs)} 件  （金額が1対1で一致）")
    print("=" * W)
    if exact_pairs:
        hdr = f"{'明細日付':<12} {'明細摘要':<30} {'金額':>8}    {'領収書日付':<12} {'領収書支払先':<30} {'カテゴリ'}"
        print(hdr)
        print("-" * W)
        for t, r in exact_pairs:
            t_date = t.get("date", "")[:10]
            t_desc = (t.get("description") or "")[:28]
            amt    = int(t.get("amount", 0))
            r_date = (r.get("date") or "")[:10]
            r_pay  = (r.get("payee") or "")[:28]
            r_cat  = r.get("category", "")
            print(f"{t_date:<12} {t_desc:<30} {amt:>8,}    {r_date:<12} {r_pay:<30} {r_cat}")
    else:
        print("  （なし）")

    print()
    print("=" * W)
    print(f"【曖昧ペア】 {len(ambiguous_pairs)} 件  （同額の領収書が複数存在）")
    print("=" * W)
    if ambiguous_pairs:
        for t, candidates in ambiguous_pairs:
            t_date = t.get("date", "")[:10]
            t_desc = (t.get("description") or "")[:40]
            amt    = int(t.get("amount", 0))
            print(f"  明細: {t_date}  {t_desc:<40}  ¥{amt:,}")
            for r in candidates:
                r_date = (r.get("date") or "")[:10]
                r_pay  = (r.get("payee") or "")[:35]
                r_cat  = r.get("category", "")
                print(f"    ↔ {r_date}  {r_pay:<35}  [{r_cat}]")
            print()
    else:
        print("  （なし）")

    print()
    print("=" * W)
    print(f"【対応なし】 {len(unmatched_txs)} 件  （金額が一致する領収書なし）")
    print("=" * W)
    if unmatched_txs:
        for t in unmatched_txs:
            t_date = t.get("date", "")[:10]
            t_desc = (t.get("description") or "")[:50]
            amt    = int(t.get("amount", 0))
            t_type = t.get("source_type") or t.get("type") or ""
            print(f"  {t_date}  {t_desc:<50}  ¥{amt:,}  [{t_type}]")
    else:
        print("  （なし）")

    print()
    print("=" * W)
    print(f"【金額別 領収書分布】（同額が複数ある金額のみ）")
    print("=" * W)
    dupes = {amt: rs for amt, rs in receipt_by_amount.items() if len(rs) > 1}
    if dupes:
        for amt in sorted(dupes):
            rs = dupes[amt]
            print(f"  ¥{amt:,} — {len(rs)} 件")
            for r in rs:
                print(f"    {(r.get('date') or '')[:10]}  {(r.get('payee') or '')[:35]}  [{r.get('category','')}]")
    else:
        print("  （重複なし）")

    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
