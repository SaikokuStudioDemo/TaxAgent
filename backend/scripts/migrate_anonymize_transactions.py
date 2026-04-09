"""
銀行取引データの匿名化マイグレーション

ルール:
  1. ETC/ATM/振込手数料/利息/年金/国税 等の業務キーワード → そのまま維持
  2. 「振込 [名前]」「振込入金* [名前]」 → プレフィックス維持、名前部分を匿名化
  3. 「[会社名] 売上入金」「[会社名] 支払」 → サフィックス維持、会社名部分を匿名化
  4. それ以外の会社名・個人名 → テスト会社XXXX に匿名化
  5. 既に「テスト会社XXXX」形式 → スキップ

実行方法:
  cd backend && PYTHONPATH=. python scripts/migrate_anonymize_transactions.py
  # ドライラン（変更なし・確認のみ）
  cd backend && PYTHONPATH=. python scripts/migrate_anonymize_transactions.py --dry-run
"""
import argparse
import re
import sys
from pymongo import MongoClient
from app.services.anonymizer import anonymizer

# ────────────────────────────────────────────────────────────────
# そのまま維持する完全一致セット
# ────────────────────────────────────────────────────────────────
KEEP_EXACT = {
    "振込手数料",
    "ローンゴヘンサイ",
    "ローンゴユウシ",
    "リソク",
    "利息",
    "決算利息",
    "オフリコミ",
    "シンキオトリヒキ",
    "ヨキンキ",
    "ヨキンキ:",
    "前回分口座振替金額",
    "テスウリョウ",
    "引出し378",
    "AD",
    "AD005",
    "AD012",
    "年金",
    "スイカ (ケータイケツサイ)",
}

# ────────────────────────────────────────────────────────────────
# 前方一致でそのまま維持するプレフィックス
# ────────────────────────────────────────────────────────────────
KEEP_STARTS_WITH = (
    "ETC",
    "ＥＴＣ",
    "ATM",
    "ＡＴＭ",
    "E-net ATM",
    "ゆうちょATM",
    "三井住友ATM",
    "セブンATM",
    "ローソンATM",
    "決算お利息",
    "決算利息",
    "年金 ",
    "国税 ",
    "PE ",
    "引出し",
    "テスト会社",
    "テスト個人",
)


def should_keep(desc: str) -> bool:
    """そのまま維持すべき description か判定する。"""
    if not desc:
        return True
    if desc in KEEP_EXACT:
        return True
    for prefix in KEEP_STARTS_WITH:
        if desc.startswith(prefix):
            return True
    return False


def anonymize_description(desc: str) -> str:
    """
    description を匿名化して返す。
    維持すべきものは元の値をそのまま返す。
    """
    if should_keep(desc):
        return desc

    # ── 振込/振込入金 プレフィックスパターン ──────────────────────
    # 例: 「振込 オオニシ タカヒロ」→「振込 テスト会社XXXX」
    # 例: 「振込入金* (カ)フューチャーライフ」→「振込入金* テスト会社XXXX」
    transfer_match = re.match(r'^(振込入金[*＊]?\s*|振込\s*)(.*)', desc)
    if transfer_match:
        prefix_raw = transfer_match.group(1)
        name_part = transfer_match.group(2).strip()
        # プレフィックスを正規化（末尾スペース統一）
        prefix = prefix_raw.rstrip()
        if name_part:
            anon = anonymizer.anonymize(name_part, "company")
            return f"{prefix} {anon}"
        return desc

    # ── サフィックスパターン ──────────────────────────────────────
    # 例: 「モックアルファ 売上入金」→「テスト会社XXXX 売上入金」
    # 例: 「デザイン事務所 支払」→「テスト会社XXXX 支払」
    for suffix in (" 売上入金", " 支払"):
        if desc.endswith(suffix):
            company_part = desc[: -len(suffix)]
            anon = anonymizer.anonymize(company_part, "company")
            return f"{anon}{suffix}"

    # ── それ以外は全体を匿名化 ────────────────────────────────────
    return anonymizer.anonymize(desc, "company")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="変更を加えずに結果を表示のみ")
    args = parser.parse_args()

    client = MongoClient("mongodb://localhost:27017")
    db = client["tax_agent"]
    col = db["transactions"]

    total = 0
    changed = 0
    skipped = 0

    # 変換前→変換後のマッピングをログ出力用に収集
    change_log: list[tuple[str, str]] = []

    for doc in col.find({}, {"_id": 1, "description": 1}):
        total += 1
        original = doc.get("description") or ""
        anonymized = anonymize_description(original)

        if original == anonymized:
            skipped += 1
            continue

        change_log.append((original, anonymized))
        changed += 1

        if not args.dry_run:
            col.update_one({"_id": doc["_id"]}, {"$set": {"description": anonymized}})

    # ── サマリー表示 ─────────────────────────────────────────────
    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"{mode}=== 匿名化マイグレーション結果 ===")
    print(f"  対象件数: {total}")
    print(f"  変更: {changed} 件")
    print(f"  スキップ（変更不要）: {skipped} 件")

    if change_log:
        # ユニーク変換パターンだけ表示
        unique_changes = sorted(set(change_log), key=lambda x: x[0])
        print(f"\n  変換パターン（{len(unique_changes)}種類）:")
        for before, after in unique_changes:
            print(f"    [{before}] → [{after}]")

    if args.dry_run:
        print("\n※ --dry-run モードのため DB は変更されていません")
    else:
        print("\n✓ DB への書き込みが完了しました")


if __name__ == "__main__":
    main()
