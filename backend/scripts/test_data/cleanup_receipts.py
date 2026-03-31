"""
cleanup_receipts.py
imported_ids.json を読み込み DELETE /api/v1/receipts/{id} を全件実行する。
完了後に imported_ids.json 自体も削除する。

実行方法（backend/ ディレクトリから）:
    python scripts/test_data/cleanup_receipts.py
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

IDS_FILE = SCRIPT_DIR / "imported_ids.json"


def main():
    if not IDS_FILE.exists():
        print(f"ERROR: {IDS_FILE} が見つかりません。")
        print("import_receipts.py が inserted_ids を返した場合のみ cleanup が実行できます。")
        sys.exit(1)

    ids = json.loads(IDS_FILE.read_text(encoding="utf-8"))
    if not ids:
        print("imported_ids.json にIDがありません")
        IDS_FILE.unlink()
        sys.exit(0)

    print(f"削除対象: {len(ids)} 件")
    print(f"エンドポイント: DELETE {BASE_URL}/api/v1/receipts/{{id}}\n")

    headers = {"Authorization": f"Bearer {DEV_AUTH_TOKEN}"}

    success = 0
    failures = []

    with httpx.Client(timeout=30.0) as client:
        for i, receipt_id in enumerate(ids, 1):
            print(f"[{i:02d}/{len(ids)}] DELETE {receipt_id} ... ", end="", flush=True)
            try:
                response = client.delete(
                    f"{BASE_URL}/api/v1/receipts/{receipt_id}",
                    headers=headers,
                )
                if response.status_code in (200, 204):
                    success += 1
                    print("OK")
                else:
                    failures.append(receipt_id)
                    print(f"FAILED ({response.status_code}: {response.text[:80]})")
            except httpx.ConnectError:
                failures.append(receipt_id)
                print("FAILED (接続エラー)")

    print(f"\n{success}件削除成功、{len(failures)}件失敗")

    if failures:
        print("失敗したID:")
        for fid in failures:
            print(f"  - {fid}")
        print(f"\nimported_ids.json は削除しませんでした（失敗分が残っています）")
        # 失敗分だけ残して上書き
        IDS_FILE.write_text(
            json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        IDS_FILE.unlink()
        print(f"imported_ids.json を削除しました")


if __name__ == "__main__":
    main()
