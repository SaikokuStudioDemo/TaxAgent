"""
SeedDataReference の請求書PDFを OCR して vendor_name を抽出し、
既存の received 請求書ドキュメントを更新するスクリプト。

使い方:
    cd backend
    PYTHONPATH=. venv/bin/python3 scripts/update_vendor_names.py [--dry-run]
"""
import asyncio
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.mongodb import connect_to_mongo, get_database
from app.services.temp_ocr.invoice_ocr import extract_jpeg_from_file, extract_invoice_data_with_gemini

SEED_DIR = Path(__file__).parent.parent.parent / "SeedDataReference"


def find_invoice_pdfs() -> list[Path]:
    return sorted(SEED_DIR.rglob("請求書/*.pdf"))


async def main(dry_run: bool = False):
    await connect_to_mongo()
    db = get_database()

    pdfs = find_invoice_pdfs()
    print(f"対象PDF: {len(pdfs)}件  {'[DRY RUN]' if dry_run else ''}")
    print()

    updated = 0
    skipped = 0
    failed = 0

    for i, pdf_path in enumerate(pdfs, 1):
        print(f"[{i:03d}/{len(pdfs)}] {pdf_path.name[:60]}", end=" ... ", flush=True)
        try:
            image_paths = extract_jpeg_from_file(str(pdf_path))
            data = await extract_invoice_data_with_gemini(image_paths[0])
        except Exception as e:
            print(f"OCR失敗: {e}")
            failed += 1
            continue

        vendor_name = data.get("vendor_name", "").strip()
        invoice_number = data.get("invoice_number", "").strip()

        if not vendor_name:
            print("vendor_name 抽出なし → スキップ")
            skipped += 1
            continue

        # invoice_number で DB を検索、なければ total_amount + issue_date で検索
        doc = None
        if invoice_number:
            doc = await db.invoices.find_one({
                "document_type": "received",
                "invoice_number": invoice_number,
                "vendor_name": {"$in": [None, ""]},
            })

        if not doc:
            total = data.get("total_amount")
            issue = data.get("issue_date", "")[:7]  # YYYY-MM
            if total and issue:
                doc = await db.invoices.find_one({
                    "document_type": "received",
                    "total_amount": total,
                    "issue_date": {"$regex": f"^{issue}"},
                    "vendor_name": {"$in": [None, ""]},
                })

        if not doc:
            print(f"DB未マッチ (inv={invoice_number!r}, vendor={vendor_name!r})")
            skipped += 1
            continue

        print(f"→ {vendor_name!r}  (inv={invoice_number or '?'})", end="")
        if not dry_run:
            await db.invoices.update_one(
                {"_id": doc["_id"]},
                {"$set": {"vendor_name": vendor_name}},
            )
            print(" ✅")
        else:
            print(" [DRY RUN]")
        updated += 1

    print()
    print(f"完了: 更新={updated}件 / スキップ={skipped}件 / OCR失敗={failed}件")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="DBを更新せずに確認のみ")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
