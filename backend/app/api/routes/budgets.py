"""
予算管理 API。
予算の CRUD と予算対比レポートを提供する。

権限：
- 予算登録・編集・削除：admin のみ
- 予算一覧参照：全ロール可（③）
- 予算対比レポート：permission_settings の budget_comparison_view に従う（①）
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.helpers import (
    CorporateContext,
    get_corporate_context,
    serialize_doc as _serialize,   # ② helpers.py の serialize_doc を使う（重複排除）
)
from app.services.budget_report_service import get_budget_report

logger = logging.getLogger(__name__)
router = APIRouter()

# ① ROLE_RANK（approver は group_leader 相当の rank 2 として扱う）
ROLE_RANK: Dict[str, int] = {
    "staff":       1,
    "approver":    2,   # permission_settings で使用される仮想ロール
    "group_leader": 2,
    "manager":     3,
    "accounting":  3,
    "director":    4,
    "president":   5,
    "admin":       6,
}


def _check_admin(ctx: CorporateContext) -> None:
    """管理者チェック。admin のみ予算の編集が可能。"""
    if (ctx.role or "") != "admin":
        raise HTTPException(
            status_code=403,
            detail="予算の編集は管理者のみ実行できます",
        )


# ─────────────────────────────────────────────────────────────────────────────
# GET /budgets/report
# 注意事項6：/{budget_id} より前に定義すること
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/report", summary="予算対比レポートを取得する")
async def get_report(
    fiscal_year: int,
    month: Optional[int] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    ① permission_settings の budget_comparison_view で参照権限を管理。
    デフォルト min_role = group_leader（approver 相当）。
    予算未登録でも 200 を返す（has_budget=False）。
    """
    # permission_settings から min_role を取得
    perm = await ctx.db["permission_settings"].find_one({
        "corporate_id": ctx.corporate_id,
        "feature_key": "budget_comparison_view",
    })
    min_role = perm.get("min_role", "group_leader") if perm else "group_leader"

    user_rank = ROLE_RANK.get(ctx.role or "", 1)
    required_rank = ROLE_RANK.get(min_role, 2)

    if user_rank < required_rank:
        raise HTTPException(
            status_code=403,
            detail="予算対比レポートの閲覧権限がありません",
        )

    report = await get_budget_report(
        corporate_id=ctx.corporate_id,
        fiscal_year=fiscal_year,
        month=month,
    )
    return report


# ─────────────────────────────────────────────────────────────────────────────
# GET /budgets
# ③ 全ロールが参照可能
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", summary="予算一覧を取得する")
async def list_budgets(
    fiscal_year: Optional[int] = None,
    month: Optional[int] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """③ 全ロールが参照可能（権限チェックなし）。"""
    query: Dict = {"corporate_id": ctx.corporate_id}
    if fiscal_year:
        query["fiscal_year"] = fiscal_year
    if month:
        query["month"] = month

    cursor = ctx.db["budgets"].find(query).sort([("fiscal_year", -1), ("month", 1)])
    docs = await cursor.to_list(length=1000)
    return [_serialize(doc) for doc in docs]


# ─────────────────────────────────────────────────────────────────────────────
# POST /budgets
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", summary="予算を登録する")
async def create_budget(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """管理者のみ登録可能。"""
    _check_admin(ctx)

    fiscal_year  = payload.get("fiscal_year")
    month        = payload.get("month")
    account_subject = payload.get("account_subject", "")
    amount       = payload.get("amount", 0)

    if not fiscal_year or not month or not account_subject:
        raise HTTPException(
            status_code=400,
            detail="fiscal_year・month・account_subject は必須です",
        )
    if isinstance(fiscal_year, bool) or not isinstance(fiscal_year, int) or fiscal_year < 2000:
        raise HTTPException(
            status_code=400,
            detail="fiscal_year は2000以上の整数である必要があります",
        )
    if isinstance(month, bool) or not isinstance(month, int) or not (1 <= month <= 12):
        raise HTTPException(
            status_code=400,
            detail="month は1〜12の整数である必要があります",
        )
    # ② bool チェック先行
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise HTTPException(
            status_code=400,
            detail="amount は0以上の整数である必要があります",
        )

    now = datetime.utcnow()
    doc = {
        "corporate_id":   ctx.corporate_id,
        "fiscal_year":    fiscal_year,
        "month":          month,
        "department_id":  payload.get("department_id"),
        "project_id":     payload.get("project_id"),
        "account_subject": account_subject,
        "amount":         amount,
        "created_by":     ctx.user_id or "",
        "created_at":     now,
        "updated_at":     now,
    }
    result = await ctx.db["budgets"].insert_one(doc)
    created = await ctx.db["budgets"].find_one({"_id": result.inserted_id})
    return _serialize(created)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /budgets/{budget_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/{budget_id}", summary="予算を更新する")
async def update_budget(
    budget_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """管理者のみ更新可能。"""
    _check_admin(ctx)

    try:
        oid = ObjectId(budget_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid budget_id")

    existing = await ctx.db["budgets"].find_one(
        {"_id": oid, "corporate_id": ctx.corporate_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="予算が見つかりません")

    update_data: Dict = {}
    if "amount" in payload:
        amount = payload["amount"]
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise HTTPException(
                status_code=400,
                detail="amount は0以上の整数である必要があります",
            )
        update_data["amount"] = amount
    if "account_subject" in payload:
        update_data["account_subject"] = payload["account_subject"]

    if not update_data:
        raise HTTPException(status_code=400, detail="更新するデータがありません")

    update_data["updated_at"] = datetime.utcnow()
    await ctx.db["budgets"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    updated = await ctx.db["budgets"].find_one({"_id": oid})
    return _serialize(updated)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /budgets/{budget_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/{budget_id}", summary="予算を削除する")
async def delete_budget(
    budget_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """管理者のみ削除可能。"""
    _check_admin(ctx)

    try:
        oid = ObjectId(budget_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid budget_id")

    result = await ctx.db["budgets"].delete_one(
        {"_id": oid, "corporate_id": ctx.corporate_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="予算が見つかりません")

    return {"status": "deleted", "budget_id": budget_id}
