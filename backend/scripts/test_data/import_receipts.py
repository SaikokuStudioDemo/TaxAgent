"""
import_receipts.py
receipts_data.json を読み込み POST /api/v1/receipts/batch に投入する。

実行方法（backend/ ディレクトリから）:
    python scripts/test_data/import_receipts.py
"""

import os
import sys
import json
from pathlib import Path

import httpx
from dotenv import load_dotenv

# backend/.env を読み込む
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent.parent
load_dotenv(BACKEND_DIR / ".env")

DEV_AUTH_TOKEN = os.environ.get("DEV_AUTH_TOKEN", "test-token")
BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

INPUT_FILE = SCRIPT_DIR / "receipts_data.json"
IDS_FILE = SCRIPT_DIR / "imported_ids.json"

# receipts_data.json に含まれるがAPIペイロードには不要なキー
_EXCLUDE_KEYS = {"source_file"}


def build_receipt_payload(raw: dict) -> dict:
    return {
        "date": raw.get("date", ""),
        "amount": raw.get("amount", 0),
        "tax_rate": raw.get("tax_rate", 10),
        "payee": raw.get("payee", ""),
        "category": raw.get("category", ""),
        "payment_method": raw.get("payment_method", "立替"),
        "line_items": raw.get("line_items", []),
        "attachments": raw.get("attachments", []),
    }


def main():
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} が見つかりません。先に extract_receipts.py を実行してください。")
        sys.exit(1)

    raw_list = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    if not raw_list:
        print("receipts_data.json にデータがありません")
        sys.exit(0)

    receipts = [build_receipt_payload(r) for r in raw_list]
    payload = {"receipts": receipts}

    print(f"投入件数: {len(receipts)} 件")
    print(f"エンドポイント: POST {BASE_URL}/api/v1/receipts/batch\n")

    headers = {
        "Authorization": f"Bearer {DEV_AUTH_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{BASE_URL}/api/v1/receipts/batch",
                json=payload,
                headers=headers,
            )
    except httpx.ConnectError:
        print(f"ERROR: バックエンドに接続できませんでした ({BASE_URL})")
        print("バックエンドが起動しているか確認してください。")
        sys.exit(1)

    print(f"ステータス: {response.status_code}")

    if response.status_code not in (200, 201):
        print(f"ERROR: {response.text}")
        sys.exit(1)

    result = response.json()
    print(f"レスポンス: {json.dumps(result, ensure_ascii=False)}")

    inserted_ids = result.get("inserted_ids")
    if inserted_ids:
        IDS_FILE.write_text(
            json.dumps(inserted_ids, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\ninserted_ids を保存: {IDS_FILE} ({len(inserted_ids)}件)")
    else:
        print("\ninserted_ids はレスポンスに含まれていないため、imported_ids.json は生成しません。")
        print("cleanup_receipts.py を使用するには、IDを手動で imported_ids.json に記録してください。")


if __name__ == "__main__":
    main()
