"""
会計ソフト別CSV出力サービス。
freee・MF（マネーフォワード）・弥生の3フォーマットに対応。
出力対象は承認済みの receipts・invoices。
"""
import csv
import io
import logging
from typing import Any, Dict, List, Optional

from app.db.mongodb import get_database

logger = logging.getLogger(__name__)


# ── フォーマット定義 ───────────────────────────────────────────────────────

FREEE_HEADERS = [
    "管理番号", "取引日", "収支区分", "取引先", "品目",
    "税区分", "金額", "税額", "備考",
]

MF_HEADERS = [
    "計算対象", "日付", "内容", "金額（円）", "消費税",
    "取引先", "勘定科目", "税区分", "メモ",
]

YAYOI_HEADERS = [
    "伝票日付", "借方科目", "借方金額", "貸方科目", "貸方金額",
    "取引先", "摘要", "税区分",
]


def _format_freee_row(doc: dict, doc_type: str) -> List[str]:
    """freee 形式の1行を生成する。"""
    date = doc.get("date") or doc.get("issue_date", "")
    amount = doc.get("amount") or doc.get("total_amount", 0)
    tax_amount = doc.get("tax_amount", 0)
    payee = doc.get("payee") or doc.get("client_name") or doc.get("vendor_name", "")
    category = doc.get("category") or doc.get("account_subject", "")
    tax_category = doc.get("tax_category", "課税仕入 10%")
    note = doc.get("note", "")
    収支 = "支出" if doc_type == "receipt" else "収入"
    return [
        str(doc.get("_id", "")),
        date,
        収支,
        payee,
        category,
        tax_category,
        str(amount),
        str(tax_amount),
        note,
    ]


def _format_mf_row(doc: dict, doc_type: str) -> List[str]:
    """マネーフォワード形式の1行を生成する。"""
    date = doc.get("date") or doc.get("issue_date", "")
    amount = doc.get("amount") or doc.get("total_amount", 0)
    tax_amount = doc.get("tax_amount", 0)
    payee = doc.get("payee") or doc.get("client_name") or doc.get("vendor_name", "")
    category = doc.get("category") or doc.get("account_subject", "")
    tax_category = doc.get("tax_category", "課税仕入 10%")
    content = doc.get("note", "") or category
    return [
        "1",        # 計算対象
        date,
        content,
        str(amount),
        str(tax_amount),
        payee,
        category,
        tax_category,
        "",         # メモ
    ]


def _format_yayoi_row(doc: dict, doc_type: str) -> List[str]:
    """弥生形式の1行を生成する。"""
    date = doc.get("date") or doc.get("issue_date", "")
    amount = doc.get("amount") or doc.get("total_amount", 0)
    payee = doc.get("payee") or doc.get("client_name") or doc.get("vendor_name", "")
    category = doc.get("category") or doc.get("account_subject", "")
    tax_category = doc.get("tax_category", "課税仕入10%")
    note = doc.get("note", "") or payee
    if doc_type == "receipt":
        debit = category or "消耗品費"
        credit = "現金"
    else:
        debit = "買掛金"
        credit = category or "売上高"
    return [
        date,
        debit,
        str(amount),
        credit,
        str(amount),
        payee,
        note,
        tax_category,
    ]


VALID_FORMATS = ("freee", "mf", "yayoi")
VALID_DOC_TYPES = ("receipt", "invoice", "all")

_FORMAT_MAP: Dict[str, Any] = {
    "freee": (FREEE_HEADERS, _format_freee_row),
    "mf":    (MF_HEADERS,    _format_mf_row),
    "yayoi": (YAYOI_HEADERS, _format_yayoi_row),
}


async def export_csv(
    corporate_id: str,
    format_type: str,
    doc_type: str,
    fiscal_period: Optional[str] = None,
) -> str:
    """
    指定フォーマットの CSV 文字列を返す。
    fiscal_period が指定された場合はその月のデータのみ出力。
    承認済みデータ（approval_status="approved"）のみ対象。
    """
    if format_type not in VALID_FORMATS:
        raise ValueError(f"Unknown format: {format_type}")
    if doc_type not in VALID_DOC_TYPES:
        raise ValueError(f"Unknown doc_type: {doc_type}")

    db = get_database()
    docs: List[dict] = []

    base_query: Dict[str, Any] = {
        "corporate_id": corporate_id,
        "approval_status": "approved",
    }
    if fiscal_period:
        base_query["fiscal_period"] = fiscal_period

    if doc_type in ("receipt", "all"):
        receipts = await db["receipts"].find(dict(base_query)).to_list(length=10000)
        for r in receipts:
            r["_doc_type"] = "receipt"
            docs.append(r)

    if doc_type in ("invoice", "all"):
        invoices = await db["invoices"].find(dict(base_query)).to_list(length=10000)
        for inv in invoices:
            inv["_doc_type"] = "invoice"
            docs.append(inv)

    # 日付でソート
    docs.sort(key=lambda d: d.get("date") or d.get("issue_date") or "")

    # CSV 生成（UTF-8 BOM 付き・Excel で開いても文字化けしない）
    output = io.StringIO()
    writer = csv.writer(output)
    headers, formatter = _FORMAT_MAP[format_type]
    writer.writerow(headers)

    for doc in docs:
        writer.writerow(formatter(doc, doc.get("_doc_type", "receipt")))

    return output.getvalue()
