"""
alerts_config API
税理士法人が配下法人ごとのアラート閾値を設定・取得するエンドポイント。
設計ドキュメント Section 13.3 に基づく。
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.api.helpers import verify_tax_firm, resolve_corporate_id, FULL_ACCESS_ROLES
from app.db.mongodb import get_database
from app.services.alert_service import DEFAULT_ALERT_SETTINGS

logger = logging.getLogger(__name__)
router = APIRouter()

# 法人別に設定可能なのは *_days キーのみ（金額閾値はプラットフォーム全体設定）
VALID_KEYS = {k for k in DEFAULT_ALERT_SETTINGS if k.endswith("_days")}

DEFAULT_EMAIL_ENABLED: Dict[str, bool] = {
    "rejected_stale_alert":         False,
    "no_attachment_alert":          False,
    "unreconciled_alert":           False,
    "approval_delay_alert":         False,
    "tax_advisor_escalation_alert": False,
}
VALID_EMAIL_KEYS = set(DEFAULT_EMAIL_ENABLED.keys())


def _merge_email_enabled(config: Optional[dict]) -> Dict[str, bool]:
    """DB の email_enabled をデフォルトとマージして返す。"""
    result = DEFAULT_EMAIL_ENABLED.copy()
    if config:
        stored = config.get("email_enabled", {})
        for k in VALID_EMAIL_KEYS:
            if k in stored:
                result[k] = bool(stored[k])
    return result


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
# /self: 一般法人ユーザー専用（自分の alerts_config を参照・更新）
# ─────────────────────────────────────────────────────────────────────────────

async def _resolve_corporate_self(firebase_uid: str, db) -> tuple:
    """
    firebase_uid から一般法人の (corporate_id, role) を解決する。
    税理士法人・未所属は 403。
    """
    corporate = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if corporate:
        if corporate.get("corporateType") != "corporate":
            raise HTTPException(status_code=403, detail="このエンドポイントは一般法人のみ利用できます")
        return str(corporate["_id"]), "admin"

    employee = await db["employees"].find_one({"firebase_uid": firebase_uid})
    if employee and employee.get("corporate_id"):
        return employee["corporate_id"], employee.get("role", "staff")

    raise HTTPException(status_code=403, detail="法人情報が見つかりません")


@router.get("/self", summary="自分の法人のアラート設定を取得する（一般法人専用）")
async def get_alerts_config_self(
    current_user: dict = Depends(get_current_user),
):
    """
    ログイン中の一般法人ユーザーが自分の alerts_config を取得する。
    未設定の場合はデフォルト値を返す。
    """
    firebase_uid = current_user.get("uid")
    db = get_database()

    corporate_id, _ = await _resolve_corporate_self(firebase_uid, db)

    config = await db["alerts_config"].find_one({"corporate_id": corporate_id})

    result = {k: DEFAULT_ALERT_SETTINGS[k] for k in VALID_KEYS}
    if config:
        result.update({k: v for k, v in config.items() if k in VALID_KEYS})

    return {"corporate_id": corporate_id, **result, "email_enabled": _merge_email_enabled(config)}


@router.put("/self", summary="自分の法人のメール通知設定を更新する（accounting+ のみ）")
async def update_alerts_config_self(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    ログイン中の一般法人ユーザーが email_enabled のみ更新できる。
    閾値（threshold_days）の更新は不可。
    accounting・manager・admin ロールのみ更新可能。
    """
    firebase_uid = current_user.get("uid")
    db = get_database()

    corporate_id, role = await _resolve_corporate_self(firebase_uid, db)

    if role not in FULL_ACCESS_ROLES:
        raise HTTPException(status_code=403, detail="経理担当者以上のロールが必要です")

    email_enabled_update = payload.get("email_enabled")
    if not email_enabled_update or not isinstance(email_enabled_update, dict):
        raise HTTPException(status_code=400, detail="email_enabled を指定してください")

    set_data: Dict[str, Any] = {}
    for k, v in email_enabled_update.items():
        if k not in VALID_EMAIL_KEYS:
            continue
        if not isinstance(v, bool):
            raise HTTPException(
                status_code=400,
                detail=f"{k} は true/false で指定してください",
            )
        set_data[f"email_enabled.{k}"] = v

    if not set_data:
        raise HTTPException(status_code=400, detail="更新するデータがありません")

    set_data["updated_at"] = datetime.utcnow()
    set_data["updated_by"] = firebase_uid
    set_data["corporate_id"] = corporate_id

    await db["alerts_config"].update_one(
        {"corporate_id": corporate_id},
        {"$set": set_data},
        upsert=True,
    )

    return {"status": "updated", "corporate_id": corporate_id}


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

    result = {k: DEFAULT_ALERT_SETTINGS[k] for k in VALID_KEYS}
    if config:
        result.update({k: v for k, v in config.items() if k in VALID_KEYS})

    return {"corporate_id": corporate_id, **result, "email_enabled": _merge_email_enabled(config)}


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

    payload = dict(payload)  # mutable copy
    email_enabled_update = payload.pop("email_enabled", None)

    # 閾値バリデーション（既存ロジック）
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

    # email_enabled バリデーション
    if email_enabled_update is not None:
        for k, v in email_enabled_update.items():
            if k not in VALID_EMAIL_KEYS:
                continue  # 不明キーは無視
            if not isinstance(v, bool):
                raise HTTPException(
                    status_code=400,
                    detail=f"{k} は true/false で指定してください",
                )
            update_data[f"email_enabled.{k}"] = v

    if not update_data:
        raise HTTPException(status_code=400, detail="更新するデータがありません")

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


# ─────────────────────────────────────────────────────────────────────────────
# アラート手動実行（税理士法人 or appのadminロール向け）
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/run-alerts", summary="アラートチェックを手動実行する（税理士法人専用）")
async def trigger_alerts(current_user: dict = Depends(get_current_user)):
    from app.services.alert_service import run_all_alerts

    firebase_uid = current_user.get("uid")
    db = get_database()

    corporate = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if corporate:
        if corporate.get("corporateType") != "tax_firm":
            raise HTTPException(status_code=403, detail="この操作は税理士法人のみ実行できます。")
    else:
        employee = await db["employees"].find_one({"firebase_uid": firebase_uid})
        if not employee or employee.get("role") != "admin":
            raise HTTPException(status_code=403, detail="この操作は管理者権限が必要です。")

    logger.info(f"Manual alert run triggered by {firebase_uid}")
    result = await run_all_alerts()
    return {"status": "completed", "results": result}


# ─────────────────────────────────────────────────────────────────────────────
# 配下法人アラート状況一覧（税理士法人向け）
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/corporate-alerts", summary="配下法人のアラート状況一覧を取得する")
async def get_corporate_alerts(current_user: dict = Depends(get_current_user)):
    firebase_uid = current_user.get("uid")
    db = get_database()

    caller = await verify_tax_firm(firebase_uid, db)

    clients = await db["corporates"].find({
        "corporateType": "corporate",
        "advising_tax_firm_id": firebase_uid,
    }).to_list(length=200)

    results = []
    for client in clients:
        corp_id = str(client["_id"])

        (
            pending_receipts,
            pending_invoices,
            unmatched_tx,
            rejected_stale,
            approval_delay,
        ) = await asyncio.gather(
            db["receipts"].count_documents({"corporate_id": corp_id, "approval_status": "pending_approval"}),
            db["invoices"].count_documents({"corporate_id": corp_id, "approval_status": "pending_approval"}),
            db["transactions"].count_documents({"corporate_id": corp_id, "status": "unmatched"}),
            db["receipts"].count_documents({"corporate_id": corp_id, "approval_status": "rejected", "rejected_stale_alerted": True}),
            db["receipts"].count_documents({"corporate_id": corp_id, "approval_status": "pending_approval", "approval_delay_alerted": True}),
        )

        total_alerts = rejected_stale + approval_delay
        results.append({
            "corporate_id": corp_id,
            "company_name": client.get("name", ""),
            "pending_receipts": pending_receipts,
            "pending_invoices": pending_invoices,
            "unmatched_transactions": unmatched_tx,
            "rejected_stale_count": rejected_stale,
            "approval_delay_count": approval_delay,
            "total_alerts": total_alerts,
            "has_alerts": total_alerts > 0,
        })

    results.sort(key=lambda x: x["total_alerts"], reverse=True)
    return {"data": results}
