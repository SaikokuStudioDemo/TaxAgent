"""
system_settings API
プラン・オプション・AI クレジット上限などのシステム設定を管理する。
設計ドキュメント Task#32 に基づく。
"""
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db.mongodb import get_database

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# 公開エンドポイント（認証不要）
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/plans", summary="プラン一覧を取得する")
async def get_plans():
    """system_settings から key='plans' の value を返す。認証不要。"""
    db = get_database()
    doc = await db["system_settings"].find_one({"key": "plans"})
    if doc and isinstance(doc.get("value"), list):
        return doc["value"]
    return []


@router.get("/options", summary="オプション一覧を取得する")
async def get_options():
    """system_settings から key='options' の value を返す。認証不要。"""
    db = get_database()
    doc = await db["system_settings"].find_one({"key": "options"})
    if doc and isinstance(doc.get("value"), list):
        return doc["value"]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# 認証必須エンドポイント（Admin のみ）
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ai-credit-limits", summary="AIクレジット上限設定を取得する（Admin のみ）")
async def get_ai_credit_limits(
    current_user: dict = Depends(get_current_user),
):
    """system_settings から ai_credit_limits を返す。認証必須。"""
    from app.api.helpers import resolve_corporate_id
    from app.db.mongodb import get_database as _get_db

    firebase_uid = current_user.get("uid")
    db = _get_db()

    # Admin チェック（corporateType=tax_firm または admin ロール）
    caller = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if not caller:
        employee = await db["employees"].find_one({"firebase_uid": firebase_uid})
        if not employee or employee.get("role") != "admin":
            raise HTTPException(status_code=403, detail="管理者権限が必要です")
    elif caller.get("corporateType") != "tax_firm":
        raise HTTPException(status_code=403, detail="管理者権限が必要です")

    doc = await db["system_settings"].find_one({"key": "ai_credit_limits"})
    if doc and isinstance(doc.get("value"), dict):
        return doc["value"]
    return {}
