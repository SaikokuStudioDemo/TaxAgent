"""
extract_invoices.py
source/invoices/ 内の全ファイルをGemini Visionで解析し、invoices_data.json を生成する。

実行方法（backend/ ディレクトリから）:
    python scripts/test_data/extract_invoices.py
"""

import os
import sys
import asyncio
from pathlib import Path

from dotenv import load_dotenv

# backend/.env を読み込む
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

SOURCE_DIR = SCRIPT_DIR / "source" / "invoices"


def main():
    if not os.environ.get("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY が .env に設定されていません")
        sys.exit(1)

    if not SOURCE_DIR.exists():
        print(f"ERROR: ソースディレクトリが見つかりません: {SOURCE_DIR}")
        sys.exit(1)

    from app.services.temp_ocr.invoice_ocr import process_invoice_files

    results = asyncio.run(process_invoice_files(str(SOURCE_DIR)))
    if not results:
        print("抽出結果が0件でした")
        sys.exit(1)


if __name__ == "__main__":
    main()
