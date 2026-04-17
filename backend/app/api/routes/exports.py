"""
データエクスポートエンドポイント。
CSV（freee/MF/弥生）と全銀フォーマットを出力する。
権限：経理担当者（accounting）・manager・admin 以上のみ。
"""
import logging
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.db.mongodb import get_database
from app.services.csv_export_service import export_csv
from app.services.zengin_export_service import export_zengin
from app.services.tax_report_service import get_tax_report

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# 共通権限チェックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

async def _check_accounting_permission(firebase_uid: str, db) -> str:
    """
    経理担当者以上（accounting / manager / admin）かどうかを確認して
    corporate_id を返す。
    権限がない場合は HTTPException(403) を raise する。

    ① manager を追加済み。
    ② resolve_corporate_id はファイル先頭のインポートを使う（インライン import なし）。
    """
    corporate_id, _ = await resolve_corporate_id(firebase_uid)

    # 法人オーナー（corporates に firebase_uid が存在）は常に許可
    corp = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if corp:
        return corporate_id

    # 従業員の場合はロール確認
    emp = await db["employees"].find_one({"firebase_uid": firebase_uid})
    if not emp:
        raise HTTPException(status_code=403, detail="権限がありません")

    # ① accounting・manager・admin のみ許可（manager を追加）
    role = emp.get("role", "staff")
    if role not in ("admin", "accounting", "manager"):
        raise HTTPException(
            status_code=403,
            detail="CSV出力は経理担当者以上のみ利用できます",
        )
    return corporate_id


# ─────────────────────────────────────────────────────────────────────────────
# GET /exports/csv：会計ソフト別 CSV 出力
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/csv", summary="会計ソフト別 CSV を出力する")
async def export_csv_endpoint(
    format_type: str = "freee",
    doc_type: str = "all",
    fiscal_period: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    format_type: freee | mf | yayoi
    doc_type: receipt | invoice | all
    fiscal_period: YYYY-MM（省略時は全期間）
    文字コード：UTF-8 BOM付き（Excel で開いても文字化けしない）
    """
    firebase_uid = current_user.get("uid")
    db = get_database()
    corporate_id = await _check_accounting_permission(firebase_uid, db)

    if format_type not in ("freee", "mf", "yayoi"):
        raise HTTPException(
            status_code=400,
            detail="format_type は freee・mf・yayoi のいずれかです",
        )
    if doc_type not in ("receipt", "invoice", "all"):
        raise HTTPException(
            status_code=400,
            detail="doc_type は receipt・invoice・all のいずれかです",
        )

    csv_text = await export_csv(
        corporate_id=corporate_id,
        format_type=format_type,
        doc_type=doc_type,
        fiscal_period=fiscal_period,
    )

    filename = f"export_{format_type}_{fiscal_period or 'all'}.csv"
    return StreamingResponse(
        iter([csv_text.encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /exports/zengin：全銀データ出力
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/zengin", summary="全銀フォーマットデータを出力する")
async def export_zengin_endpoint(
    fiscal_period: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    承認済みの受領請求書（received）を全銀フォーマット（固定長120バイト）で出力する。
    文字コード：Shift-JIS。
    """
    firebase_uid = current_user.get("uid")
    db = get_database()
    corporate_id = await _check_accounting_permission(firebase_uid, db)

    # 自社法人情報を取得
    corp = await db["corporates"].find_one({"_id": ObjectId(corporate_id)}) or {}
    company_name = corp.get("name", "")

    # デフォルト銀行口座を取得
    bank_account = await db["bank_accounts"].find_one({
        "corporate_id": corporate_id,
        "is_default": True,
    })
    bank_code = branch_code = account_number = ""
    account_type = "1"
    if bank_account:
        bank_code      = str(bank_account.get("bank_code", ""))
        branch_code    = str(bank_account.get("branch_code", ""))
        account_number = str(bank_account.get("account_number", ""))
        account_type   = "2" if bank_account.get("account_type") == "checking" else "1"

    zengin_text = await export_zengin(
        corporate_id=corporate_id,
        fiscal_period=fiscal_period,
        company_name=company_name,
        bank_code=bank_code,
        branch_code=branch_code,
        account_type=account_type,
        account_number=account_number,
    )

    if not zengin_text:
        raise HTTPException(status_code=404, detail="出力対象のデータがありません")

    filename = f"zengin_{fiscal_period or 'all'}.txt"
    return StreamingResponse(
        iter([zengin_text.encode("shift_jis", errors="replace")]),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /exports/tax-report：税務申告サポートデータ
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/tax-report", summary="税務申告サポートデータを取得する")
async def get_tax_report_endpoint(
    fiscal_year: int,
    month: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    消費税集計データを返す（参考値）。
    経理担当者（accounting・manager・admin）以上のみアクセス可能。
    """
    firebase_uid = current_user.get("uid")
    db = get_database()
    corporate_id = await _check_accounting_permission(firebase_uid, db)

    report = await get_tax_report(
        corporate_id=corporate_id,
        fiscal_year=fiscal_year,
        month=month,
    )
    return report
