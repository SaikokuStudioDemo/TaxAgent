"""
予算対比レポートサービス。
budgets コレクションの予算と
receipts・invoices の承認済み実績を比較する。
"""
import logging
from typing import Dict, List, Optional

from app.db.mongodb import get_database

logger = logging.getLogger(__name__)


async def get_budget_report(
    corporate_id: str,
    fiscal_year: int,
    month: Optional[int] = None,
) -> Dict:
    """
    予算対比レポートを生成する。
    month が指定された場合は月次、省略した場合は年次。
    予算未登録の場合は実績のみ返す（has_budget=False）。
    """
    db = get_database()

    # ── 予算データの取得 ──────────────────────────────────────────────────
    budget_query: Dict = {
        "corporate_id": corporate_id,
        "fiscal_year": fiscal_year,
    }
    if month:
        budget_query["month"] = month

    budget_docs = await db["budgets"].find(budget_query).to_list(length=1000)

    # 予算を勘定科目ごとに集計
    budget_map: Dict[str, int] = {}
    for b in budget_docs:
        subject = b.get("account_subject", "")
        budget_map[subject] = budget_map.get(subject, 0) + int(b.get("amount") or 0)

    # ── 実績データの取得（承認済みのみ） ─────────────────────────────────
    # fiscal_period は "YYYY-MM" 形式
    if month:
        fiscal_periods: List[str] = [f"{fiscal_year}-{month:02d}"]
    else:
        fiscal_periods = [f"{fiscal_year}-{m:02d}" for m in range(1, 13)]

    actual_map: Dict[str, int] = {}

    receipts = await db["receipts"].find({
        "corporate_id": corporate_id,
        "approval_status": "approved",
        "fiscal_period": {"$in": fiscal_periods},
    }).to_list(length=10000)
    for r in receipts:
        subject = r.get("category") or r.get("account_subject", "その他")
        actual_map[subject] = actual_map.get(subject, 0) + int(r.get("amount") or 0)

    invoices = await db["invoices"].find({
        "corporate_id": corporate_id,
        "document_type": "received",
        "approval_status": "approved",
        "fiscal_period": {"$in": fiscal_periods},
    }).to_list(length=10000)
    for inv in invoices:
        subject = inv.get("account_subject") or inv.get("category", "その他")
        actual_map[subject] = actual_map.get(subject, 0) + int(inv.get("total_amount") or 0)

    # ── 全勘定科目の和集合で対比レポートを生成 ────────────────────────────
    all_subjects = sorted(set(list(budget_map.keys()) + list(actual_map.keys())))

    rows = []
    total_budget = 0
    total_actual = 0

    for subject in all_subjects:
        budget_amount = budget_map.get(subject, 0)
        actual_amount = actual_map.get(subject, 0)
        diff = budget_amount - actual_amount
        # ゼロ除算防止
        rate: Optional[float] = (
            round(actual_amount / budget_amount * 100, 1)
            if budget_amount > 0 else None
        )
        rows.append({
            "account_subject": subject,
            "budget_amount": budget_amount,
            "actual_amount": actual_amount,
            "difference": diff,
            "achievement_rate": rate,
            "has_budget": subject in budget_map,
        })
        total_budget += budget_amount
        total_actual += actual_amount

    total_rate: Optional[float] = (
        round(total_actual / total_budget * 100, 1)
        if total_budget > 0 else None
    )

    return {
        "fiscal_year": fiscal_year,
        "month": month,
        "has_budget": len(budget_docs) > 0,
        "rows": rows,
        "total": {
            "budget_amount": total_budget,
            "actual_amount": total_actual,
            "difference": total_budget - total_actual,
            "achievement_rate": total_rate,
        },
    }
