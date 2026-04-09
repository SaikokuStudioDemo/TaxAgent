"""
bank_display_names → matching_patterns 移行スクリプト

clients コレクションの bank_display_names 配列を
matching_patterns コレクションに移行する。

使い方:
    cd backend
    venv/bin/python3 scripts/migrate_bank_display_names.py          # dry-run
    venv/bin/python3 scripts/migrate_bank_display_names.py --execute # 実行
"""
import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from app.core.config import settings


async def main(execute: bool = False):
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]

    corp = await db["corporates"].find_one({"corporateType": "corporate"})
    cid = str(corp["_id"])
    print(f"対象 corporate: {corp.get('name')}  (id={cid})")
    print(f"モード: {'🚀 実行' if execute else '🔍 DRY RUN（確認のみ）'}\n")

    # bank_display_names を持つクライアントを取得
    all_clients = await db["clients"].find(
        {"corporate_id": cid, "bank_display_names": {"$exists": True, "$ne": []}}
    ).to_list(length=10000)

    print(f"bank_display_names を持つ取引先: {len(all_clients)}件\n")

    total_patterns = 0
    total_inserted = 0
    total_skipped = 0

    for c in all_clients:
        client_id = str(c["_id"])
        patterns = c.get("bank_display_names", [])
        if not patterns:
            continue

        print(f"  取引先: {c.get('name')} ({client_id})  パターン数: {len(patterns)}")
        for entry in patterns:
            pattern = entry.get("pattern", "").strip()
            if not pattern:
                continue
            total_patterns += 1

            # 既存チェック
            existing = await db["matching_patterns"].find_one({
                "corporate_id": cid,
                "client_id": client_id,
                "pattern": pattern,
            })
            if existing:
                print(f"    ⏭  SKIP（既存）: {pattern!r}")
                total_skipped += 1
                continue

            source = entry.get("source", "manual")
            # "ai" → "ai_suggest" に正規化
            if source == "ai":
                source = "ai_suggest"

            doc = {
                "corporate_id": cid,
                "client_id": client_id,
                "pattern": pattern,
                "source": source,
                "confidence": float(entry.get("confidence", 1.0)),
                "created_at": datetime.utcnow(),
                "used_count": 0,
            }

            if execute:
                await db["matching_patterns"].insert_one(doc)
                print(f"    ✅ INSERT: {pattern!r}  source={source}")
            else:
                print(f"    📋 予定: {pattern!r}  source={source}")
            total_inserted += 1

    print(f"\n{'=' * 50}")
    print(f"パターン総数: {total_patterns}")
    print(f"  INSERT {'済み' if execute else '予定'}: {total_inserted}")
    print(f"  SKIP（既存）: {total_skipped}")

    if not execute:
        print("\n⚠️  DRY RUN 完了。実際に実行するには --execute をつけてください。")
        client.close()
        return

    # インデックス作成
    print("\nインデックス作成中...")
    await db["matching_patterns"].create_index(
        [("corporate_id", 1), ("pattern", 1)],
        name="corporate_pattern_idx",
    )
    await db["matching_patterns"].create_index(
        [("corporate_id", 1), ("client_id", 1)],
        name="corporate_client_idx",
    )
    print("  ✅ インデックス作成完了")

    # clients の bank_display_names を空配列に（後方互換のため削除はしない）
    print("\nclients.bank_display_names を空配列に更新中...")
    result = await db["clients"].update_many(
        {"corporate_id": cid, "bank_display_names": {"$exists": True, "$ne": []}},
        {"$set": {"bank_display_names": []}},
    )
    print(f"  ✅ {result.modified_count}件 更新")

    print("\n✅ 移行完了")
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="実際に移行を実行する（デフォルトはDRY RUN）")
    args = parser.parse_args()
    asyncio.run(main(execute=args.execute))
