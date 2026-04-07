"""
Bank PDF Parser
銀行・カードのPDF明細からトランザクションデータを抽出する。

現在: Gemini Vision による簡易OCR実装
将来: OCRチームの実装に差し替える場合は
      parse_bank_pdf() の中身のみ変更すればよい。
      呼び出し側（APIルート）の変更は不要。
"""
import base64
import json
import logging
import re
from app.core.config import settings

logger = logging.getLogger(__name__)

# OCRチーム実装時の差し替えポイント
# この定数を False にすると Gemini を使わず
# _ocr_team_extract() にフォールバックする
USE_GEMINI = True


async def parse_bank_pdf(
    file_bytes: bytes,
    source_type: str = "bank",
) -> list[dict]:
    """
    PDFから取引明細リストを抽出する。

    Returns:
        [
            {
                "transaction_date": "2025-02-24",
                "description": "ローソンATM 出金",
                "withdrawal_amount": 200000,
                "deposit_amount": 0,
                "amount": 200000,
            },
            ...
        ]
    """
    if USE_GEMINI:
        return await _gemini_extract(file_bytes, source_type)
    else:
        return await _ocr_team_extract(file_bytes, source_type)


async def _gemini_extract(
    file_bytes: bytes,
    source_type: str,
) -> list[dict]:
    """Gemini Vision による簡易OCR実装（暫定）"""
    try:
        if not settings.GOOGLE_API_KEY:
            logger.warning("GOOGLE_API_KEY not set. PDF parsing skipped.")
            return []

        import google.generativeai as genai
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")

        pdf_b64 = base64.b64encode(file_bytes).decode()

        prompt = """
この銀行・カード明細PDFから取引データを抽出してください。

以下のJSON配列形式のみで返答してください（他のテキスト不要）:
[
  {
    "transaction_date": "YYYY-MM-DD",
    "description": "摘要・取引内容",
    "withdrawal_amount": 出金額（数値・なければ0）,
    "deposit_amount": 入金額（数値・なければ0）,
    "amount": 出金額と入金額の大きい方（数値）
  }
]

注意：
- 日付はYYYY-MM-DD形式に変換すること
- 和暦（元号）が使われている場合は必ず西暦に変換すること:
    令和(R) = 2018年 + 年号数字　例: R7.03.27 → 2025-03-27、R1.05.01 → 2019-05-01
    平成(H) = 1988年 + 年号数字　例: H30.04.01 → 2018-04-01
    昭和(S) = 1925年 + 年号数字
- 「R7」「令7」「令和7年」などの表記はすべて令和7年（2025年）として処理すること
- 金額はカンマなしの整数
- 繰越・合計行・ヘッダー行は除外
- 摘要が空の行は除外
"""
        response = model.generate_content([
            {
                "parts": [
                    {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}},
                    {"text": prompt},
                ]
            }
        ])

        text = response.text.strip()
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if not match:
            logger.error("Gemini response did not contain JSON array")
            return []

        return json.loads(match.group())

    except Exception as e:
        logger.error(f"Gemini PDF extraction failed: {e}")
        return []


async def _ocr_team_extract(
    file_bytes: bytes,
    source_type: str,
) -> list[dict]:
    """
    OCRチーム実装用プレースホルダー。
    実装時はこの関数の中身を置き換える。
    """
    raise NotImplementedError(
        "OCR team implementation not yet available. "
        "Set USE_GEMINI=True to use Gemini fallback."
    )
