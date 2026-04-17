"""
税務申告サポートデータ集計サービス。
receipts・invoices の tax_rate フィールドから
消費税・仕入税額控除の集計を生成する。
DB への書き込みは行わない（読み取りのみ）。

注意：
- tax_rate の保存形式が混在している可能性がある。
  receipts: int（10・8・0）
  invoices: float（0.10・0.08・0）
  line_items: float
  _accumulate_sales / _accumulate_purchases で両方を処理する。
- 消費税計算は税込金額からの逆算。
  10%: 税額 = 税込 × 10 / 110
  8% : 税額 = 税込 × 8  / 108
"""
import logging
import math
from typing import Dict, List, Optional

from app.db.mongodb import get_database

logger = logging.getLogger(__name__)


async def get_tax_report(
    corporate_id: str,
    fiscal_year: int,
    month: Optional[int] = None,
) -> Dict:
    """
    消費税集計レポートを生成する。

    line_items がある場合は明細単位で tax_rate を判定して集計する。
    line_items がない場合は invoice レベルの tax_rate を使う。
    """
    db = get_database()

    fiscal_periods: List[str] = (
        [f"{fiscal_year}-{month:02d}"]
        if month
        else [f"{fiscal_year}-{m:02d}" for m in range(1, 13)]
    )
    period_filter = {"$in": fiscal_periods}

    # ── 売上側（発行請求書）の集計 ──────────────────────────────────────
    sales: Dict = {
        "taxable_10": 0, "taxable_8": 0, "tax_exempt": 0, "total": 0,
        "consumption_tax_10": 0, "consumption_tax_8": 0, "total_consumption_tax": 0,
    }

    issued_invoices = await db["invoices"].find({
        "corporate_id": corporate_id,
        "document_type": "issued",
        "approval_status": "approved",
        "fiscal_period": period_filter,
    }).to_list(length=10000)

    for inv in issued_invoices:
        line_items = inv.get("line_items", [])
        if line_items:
            # ① line_items がある場合: total も item_amount から積み上げる
            #    → taxable_10 + taxable_8 + tax_exempt == total が常に成立する
            for item in line_items:
                tax_rate = item.get("tax_rate", 0.10)
                item_amount = item.get(
                    "subtotal",
                    item.get("unit_price", 0) * item.get("quantity", 1),
                )
                sales["total"] += item_amount
                _accumulate_sales(sales, item_amount, tax_rate)
        else:
            # line_items がない場合は invoice レベルの total_amount で集計
            amount = inv.get("total_amount", 0)
            tax_rate = inv.get("tax_rate", 0.10)
            sales["total"] += amount
            _accumulate_sales(sales, amount, tax_rate)

    # ── 仕入側（受領請求書・領収書）の集計 ──────────────────────────────
    purchases: Dict = {
        "taxable_10": 0, "taxable_8": 0, "tax_exempt": 0, "total": 0,
        "consumption_tax_10": 0, "consumption_tax_8": 0, "total_consumption_tax": 0,
        "deductible_tax": 0,
    }

    # 受領請求書
    received_invoices = await db["invoices"].find({
        "corporate_id": corporate_id,
        "document_type": "received",
        "approval_status": "approved",
        "fiscal_period": period_filter,
    }).to_list(length=10000)

    for inv in received_invoices:
        amount = inv.get("total_amount", 0)
        tax_rate = inv.get("tax_rate", 0.10)
        purchases["total"] += amount
        _accumulate_purchases(purchases, amount, tax_rate)

    # 領収書（tax_rate は int で保存されている）
    receipts = await db["receipts"].find({
        "corporate_id": corporate_id,
        "approval_status": "approved",
        "fiscal_period": period_filter,
    }).to_list(length=10000)

    for r in receipts:
        amount = r.get("amount", 0)
        tax_rate = r.get("tax_rate", 10)  # int（10・8・0）
        purchases["total"] += amount
        _accumulate_purchases(purchases, amount, tax_rate)

    purchases["deductible_tax"] = purchases["total_consumption_tax"]

    # ── 納付税額の計算 ─────────────────────────────────────────────────
    tax_payable = sales["total_consumption_tax"] - purchases["deductible_tax"]

    return {
        "fiscal_year": fiscal_year,
        "month": month,
        "fiscal_periods": fiscal_periods,
        "sales": sales,
        "purchases": purchases,
        "summary": {
            "tax_payable": max(0, tax_payable),
            "tax_refund": max(0, -tax_payable),
            "has_refund": tax_payable < 0,
        },
    }


def _accumulate_sales(sales: dict, amount: int, tax_rate: float) -> None:
    """売上の消費税集計ヘルパー。int/float 両形式の tax_rate に対応。"""
    if tax_rate > 1:
        tax_rate = tax_rate / 100

    if abs(tax_rate - 0.10) < 0.001:
        sales["taxable_10"] += amount
        sales["consumption_tax_10"] += math.floor(amount * 10 / 110)
    elif abs(tax_rate - 0.08) < 0.001:
        sales["taxable_8"] += amount
        sales["consumption_tax_8"] += math.floor(amount * 8 / 108)
    else:
        sales["tax_exempt"] += amount

    sales["total_consumption_tax"] = (
        sales["consumption_tax_10"] + sales["consumption_tax_8"]
    )


def _accumulate_purchases(purchases: dict, amount: int, tax_rate: float) -> None:
    """仕入の消費税集計ヘルパー。int/float 両形式の tax_rate に対応。"""
    if tax_rate > 1:
        tax_rate = tax_rate / 100

    if abs(tax_rate - 0.10) < 0.001:
        purchases["taxable_10"] += amount
        purchases["consumption_tax_10"] += math.floor(amount * 10 / 110)
    elif abs(tax_rate - 0.08) < 0.001:
        purchases["taxable_8"] += amount
        purchases["consumption_tax_8"] += math.floor(amount * 8 / 108)
    else:
        purchases["tax_exempt"] += amount

    purchases["total_consumption_tax"] = (
        purchases["consumption_tax_10"] + purchases["consumption_tax_8"]
    )
