"""
暫定請求書OCRサービス
本番OCR実装後に削除予定
"""
import os
import io
import zipfile
import tempfile
import json
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path

import PIL.Image
import google.generativeai as genai
from app.core.config import settings

logger = logging.getLogger(__name__)

if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

_TEMP_DIR = Path(tempfile.gettempdir()) / "invoice_extracted"

PROMPT = """この請求書から情報を抽出してください。必ずJSON形式のみで返答し、前後に説明文を入れないでください。
{
  "invoice_number": "請求書番号（不明な場合は空文字）",
  "client_name": "請求先（宛先）会社名",
  "vendor_name": "発行元（請求元）会社名",
  "issue_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD（不明な場合は発行日+30日）",
  "subtotal": 税抜合計金額の整数,
  "tax_amount": 消費税額の整数,
  "total_amount": 税込合計金額の整数,
  "line_items": [
    {"description": "品目名", "category": "勘定科目", "amount": 金額の整数, "tax_rate": 10}
  ]
}

勘定科目は請求内容から最も適切な日本の勘定科目を判断してください。
一般的な企業会計の勘定科目体系に従い、内容を正確に反映した科目を選んでください。
日付はYYYY-MM-DD形式で返してください。金額は整数で返してください。"""


def _is_zip(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(4) == b"PK\x03\x04"


def extract_jpeg_from_file(file_path: str) -> list:
    """
    ファイルからJPEGを抽出する。
    - iOSスキャンアプリ形式（Zip内にJPEG）
    - 通常のJPEG/PNG
    - PDF（PyMuPDFで画像変換）
    に対応する。
    返り値: 一時JPEGファイルパスのリスト（ページ順）
    """
    path = Path(file_path)
    _TEMP_DIR.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    # JPEG/PNG: そのままパスを返す
    if suffix in (".jpg", ".jpeg", ".png"):
        return [str(path)]

    # ZIP形式（iOSスキャンアプリ等）
    if suffix == ".pdf" and _is_zip(path):
        results = []
        with zipfile.ZipFile(path) as zf:
            for name in sorted(zf.namelist()):
                if name.lower().endswith((".jpg", ".jpeg")):
                    data = zf.read(name)
                    out = _TEMP_DIR / f"{path.stem}_{Path(name).name}"
                    out.write_bytes(data)
                    results.append(str(out))
        if not results:
            raise ValueError(f"ZIP内にJPEGが見つかりませんでした: {path.name}")
        return results

    # 標準PDF: PyMuPDFで各ページをJPEGに変換
    if suffix == ".pdf":
        import fitz
        results = []
        doc = fitz.open(str(path))
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            out = _TEMP_DIR / f"{path.stem}_page{i+1:02d}.jpg"
            out.write_bytes(pix.tobytes("jpeg"))
            results.append(str(out))
        doc.close()
        if not results:
            raise ValueError(f"PDFにページがありませんでした: {path.name}")
        return results

    raise ValueError(f"未対応の形式: {suffix}")


async def extract_invoice_data_with_gemini(image_path: str) -> dict:
    """
    Gemini Vision APIで請求書画像からデータを抽出する。
    """
    image = PIL.Image.open(image_path)
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content([PROMPT, image])
    text = response.text.strip()

    # コードブロック除去
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()

    data = json.loads(text)

    # due_date が空の場合: issue_date + 30日
    if not data.get("due_date") and data.get("issue_date"):
        try:
            issue = datetime.strptime(data["issue_date"], "%Y-%m-%d")
            data["due_date"] = (issue + timedelta(days=30)).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return data


async def process_invoice_files(source_dir: str) -> list:
    """
    source_dir内の全ファイルを処理してinvoices_data.jsonを生成する。
    エラーが出たファイルはスキップしてログ出力。
    最後に件数を表示。
    出力: scripts/test_data/invoices_data.json
    """
    source_path = Path(source_dir)
    output_file = Path(__file__).parent.parent.parent.parent / "scripts" / "test_data" / "invoices_data.json"

    files = sorted(
        f for f in source_path.iterdir()
        if f.suffix.lower() in (".pdf", ".jpg", ".jpeg", ".png") and not f.name.startswith(".")
    )

    if not files:
        logger.warning("処理対象のファイルが見つかりませんでした: %s", source_dir)
        return []

    results = []
    failures = []

    for i, file_path in enumerate(files, 1):
        print(f"[{i:02d}/{len(files)}] {file_path.name} ... ", end="", flush=True)
        try:
            image_paths = extract_jpeg_from_file(str(file_path))
            # 複数ページある場合は最初のページのみ使用（表紙が請求書情報を含む）
            data = await extract_invoice_data_with_gemini(image_paths[0])
            data["source_file"] = file_path.name
            results.append(data)
            vendor = data.get("vendor_name") or data.get("client_name") or "?"
            total = data.get("total_amount", "?")
            print(f"OK  ({vendor} / ¥{total})")
        except Exception as e:
            failures.append(file_path.name)
            print(f"SKIP  ({e})")
            logger.exception("Failed to process %s", file_path.name)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n出力: {output_file}")
    print(f"{len(results)}件抽出成功、{len(failures)}件失敗")
    if failures:
        print("失敗ファイル:")
        for name in failures:
            print(f"  - {name}")

    return results
