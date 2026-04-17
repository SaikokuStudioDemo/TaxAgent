"""
billing_settings API
税理士法人が配下法人への課金設定を管理するエンドポイント。
設計ドキュメント Section 2・3.3 に基づく。

target_corporate_id は firebase_uid（MongoDB _id ではない）で統一する。
"""
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.api.helpers import verify_tax_firm
from app.db.mongodb import get_database

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# 共通ヘルパー：税理士法人チェック + 顧客確認
# ─────────────────────────────────────────────────────────────────────────────

async def _verify_tax_firm_and_client(
    firebase_uid: str,
    target_corporate_firebase_uid: str,
    db: Any,
) -> dict:
    """
    税理士法人チェック + 顧客確認の共通ヘルパー。
    問題があれば HTTPException を raise する。
    問題なければ対象法人ドキュメントを返す。
    """
    # 1. 税理士法人チェック
    caller = await verify_tax_firm(firebase_uid, db)

    # 2. 対象法人が存在するか確認
    target = await db["corporates"].find_one(
        {"firebase_uid": target_corporate_firebase_uid}
    )
    if not target:
        raise HTTPException(status_code=404, detail="法人が見つかりません")

    # 3. 対象法人が自分の配下かどうか確認
    if target.get("advising_tax_firm_id") != firebase_uid:
        raise HTTPException(
            status_code=403,
            detail="この法人の設定を変更する権限がありません。",
        )
    return target


# ─────────────────────────────────────────────────────────────────────────────
# GET：課金設定を取得する
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{target_firebase_uid}", summary="課金設定を取得する")
async def get_billing_settings(
    target_firebase_uid: str,
    current_user: dict = Depends(get_current_user),
):
    """
    指定法人の課金設定を取得する。
    未設定の場合はデフォルト値（全て0・is_active=False）を返す。
    税理士法人のみ呼び出し可能。
    """
    firebase_uid = current_user.get("uid")
    db = get_database()

    await _verify_tax_firm_and_client(firebase_uid, target_firebase_uid, db)

    settings = await db["billing_settings"].find_one({
        "tax_firm_id": firebase_uid,
        "target_corporate_id": target_firebase_uid,
    })

    if not settings:
        return {
            "tax_firm_id": firebase_uid,
            "target_corporate_id": target_firebase_uid,
            "corporate_unit_price": 0,
            "user_unit_price": 0,
            "is_active": False,
        }

    settings["id"] = str(settings.pop("_id"))
    # datetime は文字列に変換
    for key in ("created_at", "updated_at"):
        if key in settings and hasattr(settings[key], "isoformat"):
            settings[key] = settings[key].isoformat()
    return settings


# ─────────────────────────────────────────────────────────────────────────────
# PUT：課金設定を更新する
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/{target_firebase_uid}", summary="課金設定を更新する")
async def update_billing_settings(
    target_firebase_uid: str,
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    指定法人の課金設定を更新する（upsert）。
    ② 初期レコードは upsert で自動作成されるため事前作成は不要。
    """
    firebase_uid = current_user.get("uid")
    db = get_database()

    await _verify_tax_firm_and_client(firebase_uid, target_firebase_uid, db)

    corporate_unit_price = payload.get("corporate_unit_price", 0)
    user_unit_price = payload.get("user_unit_price", 0)
    is_active = payload.get("is_active", False)

    # ① bool チェックを先行させる（bool は int のサブクラスのため）
    if isinstance(corporate_unit_price, bool) or \
            not isinstance(corporate_unit_price, int) or \
            corporate_unit_price < 0:
        raise HTTPException(
            status_code=400,
            detail="corporate_unit_price は0以上の整数である必要があります",
        )
    if isinstance(user_unit_price, bool) or \
            not isinstance(user_unit_price, int) or \
            user_unit_price < 0:
        raise HTTPException(
            status_code=400,
            detail="user_unit_price は0以上の整数である必要があります",
        )
    if not isinstance(is_active, bool):
        raise HTTPException(
            status_code=400,
            detail="is_active は真偽値である必要があります",
        )

    now = datetime.utcnow()
    update_data = {
        "tax_firm_id": firebase_uid,
        "target_corporate_id": target_firebase_uid,
        "corporate_unit_price": corporate_unit_price,
        "user_unit_price": user_unit_price,
        "is_active": is_active,
        "updated_at": now,
    }

    # 新規の場合は created_at も設定（$setOnInsert は使わず $set で統一）
    existing = await db["billing_settings"].find_one({
        "tax_firm_id": firebase_uid,
        "target_corporate_id": target_firebase_uid,
    })
    if not existing:
        update_data["created_at"] = now

    await db["billing_settings"].update_one(
        {
            "tax_firm_id": firebase_uid,
            "target_corporate_id": target_firebase_uid,
        },
        {"$set": update_data},
        upsert=True,
    )

    return {
        "status": "updated",
        "tax_firm_id": firebase_uid,
        "target_corporate_id": target_firebase_uid,
        "corporate_unit_price": corporate_unit_price,
        "user_unit_price": user_unit_price,
        "is_active": is_active,
    }
