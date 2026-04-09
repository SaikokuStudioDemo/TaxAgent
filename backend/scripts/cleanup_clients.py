"""
取引先（clients）の重複クリーンアップスクリプト

OCRの表記ゆれで重複した取引先を正規化・統合する。

使い方:
    cd backend
    venv/bin/python3 scripts/cleanup_clients.py          # dry-run（確認のみ）
    venv/bin/python3 scripts/cleanup_clients.py --execute # 実行
"""
import asyncio
import argparse
import re
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from app.core.config import settings


# ── 正規化 ────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """
    取引先名を名寄せ用キーに変換する。
    - 敬称（様・御中）除去
    - 法人格（株式会社・(株)等）除去
    - スペース・記号除去
    - カタカナ→ひらがな
    - 小文字化
    """
    n = name.strip()

    # 敬称除去（末尾）
    for suffix in ['様', '御中', '殿', 'さん']:
        if n.endswith(suffix):
            n = n[:-len(suffix)].strip()

    # 法人格プレフィックス除去
    for prefix in ['株式会社', '有限会社', '合同会社', '合名会社', '合資会社',
                   '一般社団法人', '公益社団法人', '一般財団法人', '公益財団法人']:
        if n.startswith(prefix):
            n = n[len(prefix):].strip()
            break

    # 法人格サフィックス除去
    for suffix in ['株式会社', '有限会社', '合同会社']:
        if n.endswith(suffix):
            n = n[:-len(suffix)].strip()
            break

    # 略称 (株) (有) 等を除去
    n = re.sub(r'[\(（][株有合社][）\)]', '', n)
    n = re.sub(r'[（(]株[）)]', '', n)

    # スペース・句読点・記号を除去
    n = re.sub(r'[\s\u3000・、。,，\-\.＿_/／]', '', n)

    # カタカナ→ひらがな
    result = []
    for c in n:
        code = ord(c)
        if 0x30A1 <= code <= 0x30F6:  # ァ〜ヶ
            result.append(chr(code - 0x60))
        else:
            result.append(c)

    return ''.join(result).lower()


def pick_canonical(clients_in_group: list) -> dict:
    """
    グループ内から正規クライアントを1件選ぶ。
    優先順：
    1. 法人格プレフィックスあり（株式会社等）
    2. 敬称なし（様・御中なし）
    3. bank_display_names が登録済み
    4. 余分なスペース・記号なし
    5. 正規化後の名前が長い（フルネームに近い）
    6. created_at が古い
    """
    CORP_PREFIXES = ('株式会社', '有限会社', '合同会社', '一般社団法人')
    HONORIFICS = ('様', '御中', '殿', 'さん')

    def _ts(dt):
        if dt is None:
            return 0
        try:
            return int(dt.timestamp())
        except Exception:
            return 0

    def score(c):
        name = c.get('name', '')
        has_corp = any(name.startswith(p) for p in CORP_PREFIXES)
        has_honorific = any(name.endswith(h) for h in HONORIFICS)
        has_bank_display = len(c.get('bank_display_names', [])) > 0
        has_extra_space = bool(re.search(r'[\s\u3000]{2,}|[、，]', name))
        norm_len = len(normalize_name(name))
        return (
            int(has_corp),
            int(not has_honorific),
            int(has_bank_display),
            int(not has_extra_space),
            norm_len,
            -_ts(c.get('created_at')),
        )

    return max(clients_in_group, key=score)


# ── メイン ────────────────────────────────────────────────────────

async def main(execute: bool = False):
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]

    # 対象 corporate を取得
    corp = await db["corporates"].find_one({"corporateType": "corporate"})
    cid = str(corp["_id"])
    print(f"対象 corporate: {corp.get('name')}  (id={cid})")
    print(f"モード: {'🚀 実行' if execute else '🔍 DRY RUN（確認のみ）'}\n")

    # ── 全クライアントを取得 ────────────────────────────────────
    all_clients = await db["clients"].find({"corporate_id": cid}).to_list(length=10000)
    print(f"現在の取引先件数: {len(all_clients)}件\n")

    # ── 正規化キーでグループ化 ────────────────────────────────
    groups: dict[str, list] = defaultdict(list)
    for c in all_clients:
        key = normalize_name(c.get("name", ""))
        if key:
            groups[key].append(c)
        else:
            # 空キーは単独グループ
            groups[f"__empty_{c['_id']}__"].append(c)

    # 重複グループのみ抽出
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    single_groups = {k: v for k, v in groups.items() if len(v) == 1}

    print(f"正規化後ユニーク件数: {len(groups)}件")
    print(f"  重複グループ: {len(dup_groups)}件")
    print(f"  単独（重複なし）: {len(single_groups)}件\n")

    if not dup_groups:
        print("✅ 重複なし。クリーンアップ不要です。")
        client.close()
        return

    # ── 重複グループの詳細表示 ─────────────────────────────────
    print("=" * 60)
    print("【重複グループ一覧】")
    print("=" * 60)

    merge_plan: list[dict] = []  # { canonical, duplicates }

    for key, members in sorted(dup_groups.items(), key=lambda x: -len(x[1])):
        canonical = pick_canonical(members)
        duplicates = [m for m in members if str(m["_id"]) != str(canonical["_id"])]

        print(f"\n正規化キー: [{key}]  ({len(members)}件)")
        print(f"  ✅ 正規（保持）: {canonical.get('name')}  (id={canonical['_id']})")
        for d in duplicates:
            bdns = d.get("bank_display_names", [])
            print(f"  ❌ 削除対象:    {d.get('name')}  (id={d['_id']})  bank_display_names={len(bdns)}件")

        # 関連 invoices を確認
        dup_ids = [str(d["_id"]) for d in duplicates]
        inv_by_vendor = await db["invoices"].count_documents({"vendor_id": {"$in": dup_ids}})
        inv_by_client = await db["invoices"].count_documents({"client_id": {"$in": dup_ids}})
        if inv_by_vendor or inv_by_client:
            print(f"  📄 影響 invoices: vendor_id={inv_by_vendor}件 / client_id={inv_by_client}件 → 正規IDに付け替え")

        merge_plan.append({
            "canonical": canonical,
            "duplicates": duplicates,
        })

    # ── 削除件数サマリー ──────────────────────────────────────
    total_to_delete = sum(len(p["duplicates"]) for p in merge_plan)
    print(f"\n{'=' * 60}")
    print(f"削除予定: {total_to_delete}件  保持: {len(all_clients) - total_to_delete}件")
    print("=" * 60)

    if not execute:
        print("\n⚠️  DRY RUN 完了。実際に実行するには --execute オプションをつけてください。")
        client.close()
        return

    # ── 実行確認 ─────────────────────────────────────────────
    print("\n上記の内容で実行します。よろしいですか？ [y/N]: ", end="")
    ans = input().strip().lower()
    if ans != "y":
        print("キャンセルしました。")
        client.close()
        return

    # ── 実行 ─────────────────────────────────────────────────
    print("\n実行中...\n")
    deleted_total = 0
    inv_updated_total = 0

    for plan in merge_plan:
        canonical = plan["canonical"]
        canonical_id = str(canonical["_id"])

        for dup in plan["duplicates"]:
            dup_id = str(dup["_id"])

            # bank_display_names を正規クライアントに移行
            for entry in dup.get("bank_display_names", []):
                existing = {
                    e.get("pattern")
                    for e in canonical.get("bank_display_names", [])
                }
                if entry.get("pattern") not in existing:
                    await db["clients"].update_one(
                        {"_id": canonical["_id"]},
                        {"$push": {"bank_display_names": entry}},
                    )
                    # canonical のローカルキャッシュも更新
                    canonical.setdefault("bank_display_names", []).append(entry)

            # invoices の vendor_id を付け替え
            r = await db["invoices"].update_many(
                {"vendor_id": dup_id},
                {"$set": {"vendor_id": canonical_id}},
            )
            inv_updated_total += r.modified_count

            # invoices の client_id を付け替え
            r = await db["invoices"].update_many(
                {"client_id": dup_id},
                {"$set": {"client_id": canonical_id}},
            )
            inv_updated_total += r.modified_count

            # 重複クライアントを削除
            await db["clients"].delete_one({"_id": dup["_id"]})
            print(f"  🗑️  削除: {dup.get('name')}")
            deleted_total += 1

    # ── 結果確認 ─────────────────────────────────────────────
    remaining = await db["clients"].count_documents({"corporate_id": cid})
    print(f"\n✅ 完了")
    print(f"  削除件数:          {deleted_total}件")
    print(f"  invoices 更新:     {inv_updated_total}件")
    print(f"  残り取引先件数:    {remaining}件")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="実際に削除・更新を実行する（デフォルトはDRY RUN）")
    args = parser.parse_args()
    asyncio.run(main(execute=args.execute))
