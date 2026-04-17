"""
alerts_config API
税理士法人が配下法人ごとのアラート閾値を設定・取得するエンドポイント。
設計ドキュメント Section 13.3 に基づく。
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.api.helpers import verify_tax_firm
from app.db.mongodb import get_database
from app.services.alert_service import DEFAULT_THRESHOLDS

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_KEYS = set(DEFAULT_THRESHOLDS.keys())


# ─────────────────────────────────────────────────────────────────────────────
# ④ 共通ヘルパー：税理士法人チェック + 顧客確認 + 権限チェック
# ─────────────────────────────────────────────────────────────────────────────

async def _verify_tax_firm_access(
    firebase_uid: str,
    corporate_id: str,
    db: Any,
) -> dict:
    """
    税理士法人チェック + 顧客確認 + 権限チェックの3段ロジック。
    問題があれば HTTPException を raise する。
    問題なければ対象法人ドキュメントを返す。
    """
    # 1. 呼び出し元が税理士法人かどうか確認
    caller = await verify_tax_firm(firebase_uid, db)

    # 2. 対象法人が存在するかどうか確認
    try:
        target = await db["corporates"].find_one({"_id": ObjectId(corporate_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid corporate_id")

    if not target:
        raise HTTPException(status_code=404, detail="法人が見つかりません")

    # 3. 対象法人が自分の配下かどうか確認
    # advising_tax_firm_id には firebase_uid が保存されている（invitations.py 参照）
    if target.get("advising_tax_firm_id") != firebase_uid:
        raise HTTPException(
            status_code=403,
            detail="この法人の設定を変更する権限がありません。",
        )

    return target


# ─────────────────────────────────────────────────────────────────────────────
# GET：法人のアラート閾値設定を取得する
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{corporate_id}", summary="法人のアラート閾値設定を取得する")
async def get_alerts_config(
    corporate_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    指定法人のアラート閾値を取得する。
    未設定の場合はデフォルト値を返す。
    税理士法人のみ呼び出し可能。
    """
    firebase_uid = current_user.get("uid")
    db = get_database()

    await _verify_tax_firm_access(firebase_uid, corporate_id, db)

    config = await db["alerts_config"].find_one({"corporate_id": corporate_id})

    result = DEFAULT_THRESHOLDS.copy()
    if config:
        result.update({k: v for k, v in config.items() if k in VALID_KEYS})

    return {"corporate_id": corporate_id, **result}


# ─────────────────────────────────────────────────────────────────────────────
# PUT：法人のアラート閾値設定を更新する
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/{corporate_id}", summary="法人のアラート閾値設定を更新する")
async def update_alerts_config(
    corporate_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    指定法人のアラート閾値を更新する。
    税理士法人のみ呼び出し可能。
    全ての値は1以上の整数である必要がある。
    """
    firebase_uid = current_user.get("uid")
    db = get_database()

    await _verify_tax_firm_access(firebase_uid, corporate_id, db)

    # 有効なキーのみ・1以上の整数チェック
    update_data: Dict[str, Any] = {}
    for k, v in payload.items():
        if k not in VALID_KEYS:
            raise HTTPException(status_code=400, detail=f"無効なキーです: {k}")
        if not isinstance(v, int) or v < 1:
            raise HTTPException(
                status_code=400,
                detail=f"{k} は1以上の整数である必要があります",
            )
        update_data[k] = v

    if not update_data:
        raise HTTPException(status_code=400, detail="更新するデータがありません")

    # ③ updated_by / tax_firm_id は firebase_uid で統一（resolve_corporate_id 不要）
    update_data["updated_at"] = datetime.utcnow()
    update_data["updated_by"] = firebase_uid
    update_data["corporate_id"] = corporate_id
    update_data["tax_firm_id"] = firebase_uid

    await db["alerts_config"].update_one(
        {"corporate_id": corporate_id},
        {"$set": update_data},
        upsert=True,
    )

    return {"status": "updated", "corporate_id": corporate_id, **update_data}
