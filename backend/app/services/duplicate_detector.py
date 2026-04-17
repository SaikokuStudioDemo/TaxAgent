"""
二重計上（重複ドキュメント）検知サービス。
設計ドキュメント Section 13.5 のパターンBに対応。
同日・同金額・同取引先の類似ドキュメントを検知する。
DB への書き込みは行わない（読み取りのみ）。
"""
import logging
import re
from typing import List, Dict, Any, Optional

from bson import ObjectId

from app.db.mongodb import get_database

logger = logging.getLogger(__name__)


async def check_duplicate_receipt(
    corporate_id: str,
    date: str,
    amount: int,
    payee: str,
    exclude_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    新規登録しようとしている領収書と類似する既存ドキュメントを検索する。
    同日・同金額で検索し、取引先名の部分一致で重複候補を絞り込む。
    DB への書き込みは行わない。
    """
    db = get_database()

    query: Dict[str, Any] = {
        "corporate_id": corporate_id,
        "date": date,
        "amount": amount,
        "is_deleted": {"$ne": True},
    }
    if exclude_id:
        try:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        except Exception:
            pass

    candidates = await db["receipts"].find(query).to_list(length=10)

    if not candidates:
        return {"has_duplicates": False, "candidates": [], "message": ""}

    # 取引先名の部分一致チェック（大文字小文字無視・正規表現エスケープ済み）
    payee_lower = payee.lower() if payee else ""
    duplicates: List[Dict[str, Any]] = []

    for doc in candidates:
        existing_payee = (doc.get("payee") or "").lower()
        if payee_lower and existing_payee and (
            payee_lower in existing_payee or existing_payee in payee_lower
        ):
            duplicates.append(_format_receipt_candidate(doc))

    # 取引先名が一致しない場合も同日・同金額なら最大3件を候補として返す
    if not duplicates:
        for doc in candidates[:3]:
            duplicates.append(_format_receipt_candidate(doc))

    return {
        "has_duplicates": len(duplicates) > 0,
        "candidates": duplicates,
        "message": (
            f"似た内容のドキュメントが既に{len(duplicates)}件登録されています。"
            "二重登録の可能性があります。続けますか？"
        ) if duplicates else "",
    }


async def check_duplicate_invoice(
    corporate_id: str,
    issue_date: str,
    total_amount: int,
    client_name: str,
    document_type: str,  # "issued" | "received"
    exclude_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    新規登録しようとしている請求書と類似する既存ドキュメントを検索する。
    同日・同金額・同 document_type で検索し、取引先名の部分一致で絞り込む。
    DB への書き込みは行わない。
    """
    db = get_database()

    query: Dict[str, Any] = {
        "corporate_id": corporate_id,
        "issue_date": issue_date,
        "total_amount": total_amount,
        "document_type": document_type,
        "is_deleted": {"$ne": True},
    }
    if exclude_id:
        try:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        except Exception:
            pass

    candidates = await db["invoices"].find(query).to_list(length=10)

    if not candidates:
        return {"has_duplicates": False, "candidates": [], "message": ""}

    client_lower = client_name.lower() if client_name else ""
    duplicates: List[Dict[str, Any]] = []

    for doc in candidates:
        existing_client = (doc.get("client_name") or "").lower()
        if client_lower and existing_client and (
            client_lower in existing_client or existing_client in client_lower
        ):
            duplicates.append(_format_invoice_candidate(doc))

    if not duplicates:
        for doc in candidates[:3]:
            duplicates.append(_format_invoice_candidate(doc))

    return {
        "has_duplicates": len(duplicates) > 0,
        "candidates": duplicates,
        "message": (
            f"似た内容の請求書が既に{len(duplicates)}件登録されています。"
            "二重登録の可能性があります。続けますか？"
        ) if duplicates else "",
    }


# ── プライベートヘルパー ──────────────────────────────────────────────────────

def _format_receipt_candidate(doc: dict) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "date": doc.get("date"),
        "amount": doc.get("amount"),
        "payee": doc.get("payee"),
        "category": doc.get("category"),
        "submitted_by": doc.get("submitted_by"),
        "approval_status": doc.get("approval_status"),
    }


def _format_invoice_candidate(doc: dict) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "issue_date": doc.get("issue_date"),
        "total_amount": doc.get("total_amount"),
        "client_name": doc.get("client_name"),
        "approval_status": doc.get("approval_status"),
    }
