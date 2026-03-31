"""
extract_receipts.py
source/receipts/ 内の全ファイルをGemini Visionで解析し、receipts_data.json を生成する。

実行方法（backend/ ディレクトリから）:
    python scripts/test_data/extract_receipts.py
"""

import os
import sys
import json
import zipfile
import io
from pathlib import Path

from dotenv import load_dotenv
import PIL.Image
import google.generativeai as genai

# backend/.env を読み込む
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent.parent
load_dotenv(BACKEND_DIR / ".env")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

SOURCE_DIR = SCRIPT_DIR / "source" / "receipts"
OUTPUT_FILE = SCRIPT_DIR / "receipts_data.json"
EXTRACT_DIR = Path("/tmp/receipt_extracted")

PROMPT = """この領収書から情報を抽出してください。必ずJSON形式のみで返答し、前後に説明文を入れないでください。
{"date":"YYYY-MM-DD","amount":数値,"tax_rate":10,"payee":"店舗名","category":"カテゴリ","payment_method":"支払方法"}

categoryは["交通費","駐車場代","食費・会議費","消耗品費","通信費","その他"]から最も適切なものを選んでください。
payment_methodは"現金","カード","電子マネー","立替"のいずれかにしてください。
tax_rateは10または8の整数で、不明な場合は10にしてください。"""


def is_zip_file(path: Path) -> bool:
    """ファイルがZIPかどうかをマジックバイトで判定"""
    with open(path, "rb") as f:
        return f.read(4) == b"PK\x03\x04"


def pdf_to_pil_image(pdf_path: Path) -> PIL.Image.Image:
    """標準PDFの最初のページをPIL Imageに変換（PyMuPDF使用）"""
    import fitz  # pymupdf

    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("jpeg")
    doc.close()
    return PIL.Image.open(io.BytesIO(img_bytes))


def extract_image_from_zip(zip_path: Path) -> PIL.Image.Image:
    """iOSスキャンアプリ形式（Zip内にJPEG格納）からJPEGを展開してPIL Imageを返す"""
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name.lower().endswith((".jpg", ".jpeg")):
                data = zf.read(name)
                return PIL.Image.open(io.BytesIO(data))
    raise ValueError(f"ZIP内にJPEGが見つかりませんでした: {zip_path.name}")


def load_image(file_path: Path) -> PIL.Image.Image:
    """ファイル形式に応じてPIL Imageを返す"""
    suffix = file_path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return PIL.Image.open(file_path)
    elif suffix == ".pdf":
        if is_zip_file(file_path):
            return extract_image_from_zip(file_path)
        else:
            return pdf_to_pil_image(file_path)
    else:
        raise ValueError(f"未対応の形式: {suffix}")


def extract_with_gemini(image: PIL.Image.Image) -> dict:
    """Gemini Vision APIで領収書情報を抽出"""
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content([PROMPT, image])
    text = response.text.strip()

    # コードブロック（```json ... ```）が含まれる場合は除去
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()

    return json.loads(text)


def main():
    if not GOOGLE_API_KEY:
        print("ERROR: GOOGLE_API_KEY が .env に設定されていません")
        sys.exit(1)

    genai.configure(api_key=GOOGLE_API_KEY)

    if not SOURCE_DIR.exists():
        print(f"ERROR: ソースディレクトリが見つかりません: {SOURCE_DIR}")
        sys.exit(1)

    files = sorted(
        f
        for f in SOURCE_DIR.iterdir()
        if f.suffix.lower() in (".pdf", ".jpg", ".jpeg") and not f.name.startswith(".")
    )

    if not files:
        print("処理対象のファイルが見つかりませんでした")
        sys.exit(0)

    print(f"処理対象: {len(files)} 件\n")

    results = []
    failures = []

    for i, file_path in enumerate(files, 1):
        print(f"[{i:02d}/{len(files)}] {file_path.name} ... ", end="", flush=True)
        try:
            image = load_image(file_path)
            data = extract_with_gemini(image)
            data["source_file"] = file_path.name
            results.append(data)
            print(f"OK  ({data.get('payee', '?')} / ¥{data.get('amount', '?')})")
        except Exception as e:
            failures.append(file_path.name)
            print(f"SKIP  ({e})")

    OUTPUT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n出力: {OUTPUT_FILE}")
    print(f"{len(results)}件抽出成功、{len(failures)}件失敗")
    if failures:
        print("失敗ファイル:")
        for name in failures:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
