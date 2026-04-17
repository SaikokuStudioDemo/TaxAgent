"""
OCR エンドポイント

Firebase Storage の URL からファイルを取得し、
Gemini Flash OCR → JOURNAL_MAP 仕訳提案 のパイプラインを実行する。
"""
import logging
import os
import tempfile

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.services.ai_service import AIService
from app.services.agent_tools import _lookup_journal  # ④ ファイルトップでインポート

logger = logging.getLogger(__name__)
router = APIRouter()


async def _download_url(url: str) -> bytes:
    """
    Firebase Storage の URL からファイルをダウンロードして bytes を返す。
    403/401 は URL 期限切れとして HTTPException(400) に変換する。
    テストでは app.api.routes.ocr._download_url をパッチして差し替える。
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # ③ 403/401 は URL 期限切れの可能性
            if e.response.status_code in (401, 403):
                raise HTTPException(
                    status_code=400,
                    detail="ファイルにアクセスできませんでした。URLが期限切れの可能性があります。",
                )
            raise
    return response.content


@router.post("/extract", summary="ファイルから OCR でデータを抽出する")
async def extract_document(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Firebase Storage の URL からファイルを取得し、
    Gemini Flash で OCR → JOURNAL_MAP で仕訳提案を返す。

    リクエスト：
      file_url : str  - Firebase Storage のダウンロード URL
      doc_type : str  - "receipt" | "invoice"

    レスポンス：
      ocr_result            : dict  - OCR 抽出データ
      journal_suggestion    : dict  - 仕訳提案
      confirmation_required : True

    注意：
      AIService.analyze_invoice_pdf は現状モック実装。
      TODO: Gemini Flash OCR に差し替え予定（⑤）
    """
    file_url = payload.get("file_url")
    doc_type = payload.get("doc_type", "receipt")

    if not file_url:
        raise HTTPException(status_code=400, detail="file_url is required")
    if doc_type not in ("receipt", "invoice"):
        raise HTTPException(
            status_code=400,
            detail="doc_type must be 'receipt' or 'invoice'",
        )

    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)

    tmp_path = None
    try:
        # ── 1. Firebase Storage からファイルをダウンロード ─────────────
        # _download_url 経由でテスト時にパッチ可能にしている
        file_bytes = await _download_url(file_url)

        suffix = ".pdf" if "pdf" in file_url.lower() else ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        # ── 2. OCR（現状モック実装。TODO: Gemini Flash OCR に差し替え予定） ──
        ocr_result = await AIService.analyze_invoice_pdf(tmp_path)
        if not ocr_result:
            raise HTTPException(
                status_code=422,
                detail="OCRでデータを抽出できませんでした。",
            )

        # ── 3. JOURNAL_MAP で仕訳提案 ─────────────────────────────────
        category = ocr_result.get("category")
        if not category and ocr_result.get("line_items"):
            category = (ocr_result["line_items"][0] or {}).get("category")
        description = ocr_result.get("description", "")

        journal = _lookup_journal(description, category)

        return {
            "ocr_result": ocr_result,
            "journal_suggestion": {
                "suggested_debit": journal.get("debit", "雑費"),
                "suggested_credit": journal.get("credit", "未払金"),
                "suggested_tax_category": journal.get("tax_category", "課税仕入 10%"),
                "confidence": journal.get("confidence", "default"),
            },
            "confirmation_required": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OCR extract failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"OCR処理に失敗しました: {str(e)}",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
