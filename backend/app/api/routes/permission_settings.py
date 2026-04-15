"""
permission_settings エンドポイント

GET  /permission-settings → 全機能キーの設定を返す（未設定はデフォルト補完）
PUT  /permission-settings → 管理者のみ一括更新

DEFAULT_PERMISSIONS に存在しないキーは固定権限とみなし PUT で 400 を返す。
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from datetime import datetime
from pydantic import BaseModel

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
)

router = APIRouter()


# 変更可能な柔軟権限キーとそのデフォルト値
DEFAULT_PERMISSIONS: dict = {
    'client_management':      {'min_role': 'staff',      'require_approval': True},
    'journal_rule_settings':  {'min_role': 'accounting', 'require_approval': False},
    'matching_rule_settings': {'min_role': 'accounting', 'require_approval': False},
    'report_view':            {'min_role': 'approver',   'require_approval': False},
    'budget_comparison_view': {'min_role': 'approver',   'require_approval': False},
    'ai_chat_basic':          {'min_role': 'staff',      'require_approval': False},
    'ai_chat_accounting':     {'min_role': 'accounting', 'require_approval': False},
}

# 変更可能なキーの集合（DEFAULT_PERMISSIONS のキーと同一）
FLEXIBLE_FEATURE_KEYS: set = set(DEFAULT_PERMISSIONS.keys())

# min_role として受け付ける値（昇順）
VALID_MIN_ROLES: List[str] = ['staff', 'approver', 'accounting', 'manager', 'admin']


class PermissionSettingUpdate(BaseModel):
    feature_key: str
    min_role: str
    require_approval: bool


@router.get("", summary="権限設定一覧を取得する")
async def get_permissions(ctx: CorporateContext = Depends(get_corporate_context)):
    """
    全機能キーの権限設定を返す。
    DB に設定が存在しない機能は DEFAULT_PERMISSIONS で補完するため、
    常に全 7 件が返る。
    """
    cursor = ctx.db["permission_settings"].find({"corporate_id": ctx.corporate_id})
    db_docs = await cursor.to_list(length=100)
    db_map = {doc["feature_key"]: doc for doc in db_docs}

    result = []
    for key, default in DEFAULT_PERMISSIONS.items():
        if key in db_map:
            doc = db_map[key].copy()
            doc["is_default"] = False
            result.append(_serialize(doc))
        else:
            result.append({
                "feature_key": key,
                "min_role": default["min_role"],
                "require_approval": default["require_approval"],
                "is_default": True,
            })
    return result


@router.put("", summary="権限設定を一括更新する")
async def update_permissions(
    payload: List[PermissionSettingUpdate],
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    管理者のみ権限設定を一括更新する。
    DEFAULT_PERMISSIONS に存在しないキー（固定権限含む）は 400 を返す。
    """
    if ctx.role != "admin":
        raise HTTPException(status_code=403, detail="管理者のみ権限設定を変更できます")

    for item in payload:
        if item.feature_key not in FLEXIBLE_FEATURE_KEYS:
            raise HTTPException(
                status_code=400,
                detail=f"'{item.feature_key}' は変更できない権限キーです",
            )
        if item.min_role not in VALID_MIN_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"min_role '{item.min_role}' は無効な値です。有効な値: {VALID_MIN_ROLES}",
            )

    now = datetime.utcnow()
    updated = []
    for item in payload:
        await ctx.db["permission_settings"].update_one(
            {"corporate_id": ctx.corporate_id, "feature_key": item.feature_key},
            {"$set": {
                "corporate_id": ctx.corporate_id,
                "feature_key": item.feature_key,
                "min_role": item.min_role,
                "require_approval": item.require_approval,
                "updated_at": now,
                "updated_by": ctx.user_id,
            }},
            upsert=True,
        )
        updated.append(item.feature_key)

    return {"updated": updated}
