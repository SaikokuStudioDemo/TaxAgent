"""
Admin専用エンドポイント（ADMIN_UIDS に含まれる UID のみアクセス可）。
"""
import logging

from fastapi import APIRouter, Depends

from app.api.deps import verify_admin
from app.db.mongodb import get_database

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/me", summary="ログイン中の Admin 情報を返す")
async def admin_me(current_user: dict = Depends(verify_admin)):
    return {
        "uid": current_user.get("uid"),
        "email": current_user.get("email", ""),
        "is_admin": True,
    }


@router.get("/stats", summary="KPI ダッシュボード用データ")
async def admin_stats(current_user: dict = Depends(verify_admin)):
    db = get_database()
    tax_firm_count = await db["corporates"].count_documents({"corporateType": "tax_firm"})
    corporate_count = await db["corporates"].count_documents({"corporateType": "corporate"})
    return {
        "tax_firm_count": tax_firm_count,
        "corporate_count": corporate_count,
        "mrr": 3850000,
    }
