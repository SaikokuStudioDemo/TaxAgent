"""
import_invoices.py
invoices_data.json を読み込み POST /api/v1/invoices に1件ずつ投入する。

実行方法（backend/ ディレクトリから）:
    python scripts/test_data/import_invoices.py
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

# backend/.env を読み込む
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent.parent
load_dotenv(BACKEND_DIR / ".env")

DEV_AUTH_TOKEN = os.environ.get("DEV_AUTH_TOKEN", "test-token")
BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

INPUT_FILE = SCRIPT_DIR / "invoices_data.json"
IDS_FILE = SCRIPT_DIR / "imported_invoice_ids.json"


def _fallback_date(base_date: str, days: int = 30) -> str:
    try:
        d = datetime.strptime(base_date, "%Y-%m-%d")
        return (d + timedelta(days=days)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return datetime.utcnow().strftime("%Y-%m-%d")


def build_invoice_payload(raw: dict, index: int) -> dict:
    issue_date = raw.get("issue_date") or datetime.utcnow().strftime("%Y-%m-%d")
    due_date = raw.get("due_date") or _fallback_date(issue_date, 30)

    invoice_number = raw.get("invoice_number") or f"INV-{index:03d}"

    # 受領請求書: client_name には発行元（請求元）会社名を入れる
    client_name = raw.get("vendor_name") or raw.get("client_name") or "不明"

    total_amount = int(raw.get("total_amount") or 0)
    subtotal = int(raw.get("subtotal") or 0)
    tax_amount = int(raw.get("tax_amount") or 0)

    # subtotal/tax_amount が不明な場合の補完
    if total_amount > 0 and subtotal == 0 and tax_amount == 0:
        tax_amount = round(total_amount * 10 / 110)
        subtotal = total_amount - tax_amount

    line_items = []
    for item in raw.get("line_items", []):
        line_items.append({
            "description": item.get("description", ""),
            "category": item.get("category", "外注費"),
            "amount": int(item.get("amount", 0)),
            "tax_rate": int(item.get("tax_rate", 10)),
        })

    return {
        "document_type": "received",
        "invoice_number": invoice_number,
        "client_name": client_name,
        "recipient_email": "",
        "issue_date": issue_date,
        "due_date": due_date,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
        "line_items": line_items,
        "attachments": [],
        "approval_status": "pending_approval",
    }


def main():
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} が見つかりません。先に extract_invoices.py を実行してください。")
        sys.exit(1)

    raw_list = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    if not raw_list:
        print("invoices_data.json にデータがありません")
        sys.exit(0)

    print(f"投入件数: {len(raw_list)} 件")
    print(f"エンドポイント: POST {BASE_URL}/api/v1/invoices\n")

    headers = {
        "Authorization": f"Bearer {DEV_AUTH_TOKEN}",
        "Content-Type": "application/json",
    }

    inserted_ids = []
    failures = []

    with httpx.Client(timeout=30.0) as client:
        for i, raw in enumerate(raw_list, 1):
            payload = build_invoice_payload(raw, i)
            src = raw.get("source_file", f"item{i}")
            print(f"[{i:02d}/{len(raw_list)}] {src} ({payload['client_name']}) ... ", end="", flush=True)
            try:
                resp = client.post(
                    f"{BASE_URL}/api/v1/invoices",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    inv_id = data.get("id")
                    if inv_id:
                        inserted_ids.append(inv_id)
                    print(f"OK  (id={inv_id})")
                else:
                    failures.append(src)
                    print(f"FAILED ({resp.status_code}: {resp.text[:80]})")
            except httpx.ConnectError:
                failures.append(src)
                print("FAILED (接続エラー)")

    print(f"\n{len(inserted_ids)}件投入成功、{len(failures)}件失敗")
    if failures:
        print("失敗ファイル:")
        for name in failures:
            print(f"  - {name}")

    if inserted_ids:
        IDS_FILE.write_text(
            json.dumps(inserted_ids, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\ninserted_ids を保存: {IDS_FILE} ({len(inserted_ids)}件)")
    else:
        print("\n投入成功件数が0件のため、imported_invoice_ids.json は生成しません。")
        sys.exit(1)


if __name__ == "__main__":
    main()
