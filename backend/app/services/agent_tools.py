"""
AI エージェント 読み取り系ツール（6本）

設計方針：
- 引数: corporate_id（必須）+ ツール固有パラメータ
- 戻り値: JSON シリアライズ可能な dict
- 例外はすべて内部でキャッチして {"error": ...} を返す
- DB への書き込みは行わない（読み取り専用）
"""
import asyncio
import json
import logging
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.api.helpers import enrich_with_approval_history
from app.db.mongodb import get_database
from app.services.matching_score_service import calculate_match_score
from app.core.config import DEFAULT_TAX_RATE
from app.utils.tax_utils import calc_tax_from_exclusive


# ── JOURNAL_MAP（モジュールロード時に一度だけ読み込む） ───────────────────────

_JOURNAL_MAP_PATH = Path(__file__).parent.parent / "data" / "journal_map.json"


def _load_journal_map() -> dict:
    with open(_JOURNAL_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


JOURNAL_MAP: Dict[str, Any] = _load_journal_map()

logger = logging.getLogger(__name__)


# ── シリアライズユーティリティ ──────────────────────────────────────────────

def _serialize(doc: dict) -> dict:
    """
    MongoDB ドキュメントを JSON シリアライズ可能な dict に変換（非破壊）。
    - _id → id（文字列）
    - ObjectId → 文字列
    - datetime → ISO 8601 文字列
    - ネストした dict / list も再帰的に処理
    """
    result: Dict[str, Any] = {}
    for k, v in doc.items():
        key = "id" if k == "_id" else k
        if isinstance(v, ObjectId):
            result[key] = str(v)
        elif isinstance(v, datetime):
            result[key] = v.isoformat()
        elif isinstance(v, dict):
            result[key] = _serialize(v)
        elif isinstance(v, list):
            result[key] = [
                _serialize(i) if isinstance(i, dict)
                else str(i) if isinstance(i, ObjectId)
                else i.isoformat() if isinstance(i, datetime)
                else i
                for i in v
            ]
        else:
            result[key] = v
    return result


# ── ① get_pending_list ────────────────────────────────────────────────────────

async def get_pending_list(
    corporate_id: str,
    list_type: str = "all",
) -> dict:
    """
    未処理一覧の取得。
    list_type: "receipts" | "invoices" | "transactions" | "all"
    """
    db = get_database()
    result: Dict[str, Any] = {
        "receipts": [],
        "invoices": [],
        "transactions": [],
        "total_count": 0,
    }
    try:
        if list_type in ("receipts", "all"):
            docs = await db["receipts"].find({
                "corporate_id": corporate_id,
                "approval_status": "pending_approval",
                "is_deleted": {"$ne": True},
            }).sort("created_at", 1).to_list(length=20)
            result["receipts"] = [_serialize(d) for d in docs]

        if list_type in ("invoices", "all"):
            docs = await db["invoices"].find({
                "corporate_id": corporate_id,
                "approval_status": "pending_approval",
                "document_type": "received",
                "is_deleted": {"$ne": True},
            }).sort("created_at", 1).to_list(length=20)
            result["invoices"] = [_serialize(d) for d in docs]

        if list_type in ("transactions", "all"):
            docs = await db["transactions"].find({
                "corporate_id": corporate_id,
                "status": "unmatched",
            }).sort("transaction_date", -1).to_list(length=20)
            result["transactions"] = [_serialize(d) for d in docs]

        result["total_count"] = (
            len(result["receipts"]) + len(result["invoices"]) + len(result["transactions"])
        )
        return result

    except Exception as e:
        logger.error(f"get_pending_list error: {e}")
        return {**result, "error": str(e)}


# ── ② get_document_detail ─────────────────────────────────────────────────────

async def get_document_detail(
    corporate_id: str,
    document_type: str,
    document_id: str,
) -> dict:
    """
    特定ドキュメントの詳細取得。
    document_type: "receipt" | "invoice" | "transaction"
    """
    _COLLECTION_MAP = {
        "receipt": "receipts",
        "invoice": "invoices",
        "transaction": "transactions",
    }
    db = get_database()
    try:
        collection = _COLLECTION_MAP.get(document_type)
        if not collection:
            return {"error": f"Unknown document_type: {document_type}"}

        try:
            oid = ObjectId(document_id)
        except Exception:
            return {"error": f"Invalid document_id: {document_id}"}

        doc = await db[collection].find_one({"_id": oid, "corporate_id": corporate_id})
        if not doc:
            return {"error": "not found"}

        # receipts / invoices のみ承認履歴を付加
        if document_type in ("receipt", "invoice"):
            doc = await enrich_with_approval_history(db, doc, document_id, document_type)

        return _serialize(doc)

    except Exception as e:
        logger.error(f"get_document_detail error: {e}")
        return {"error": str(e)}


# ── ③ search_client ──────────────────────────────────────────────────────────

async def search_client(
    corporate_id: str,
    query: str,
    limit: int = 5,
) -> dict:
    """
    取引先情報の部分一致検索（大文字小文字無視）。
    正規表現インジェクション対策として re.escape を適用する。
    """
    db = get_database()
    try:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        docs = await db["clients"].find({
            "corporate_id": corporate_id,
            "name": {"$regex": pattern},
        }).to_list(length=max(1, limit))

        return {
            "clients": [_serialize(d) for d in docs],
            "count": len(docs),
        }

    except Exception as e:
        logger.error(f"search_client error: {e}")
        return {"error": str(e), "clients": [], "count": 0}


# ── ④ get_approval_status ────────────────────────────────────────────────────

async def get_approval_status(
    corporate_id: str,
    document_type: str,
    document_id: str,
) -> dict:
    """
    承認状況・ステップの確認。
    document_type: "receipt" | "invoice"

    pending_approver の取得フロー：
      1. ドキュメントの current_step + approval_rule_id を取得
      2. approval_rules コレクションでルール検索
      3. current_step に一致する step の role を取得
      4. employees から該当 role の担当者名を解決
    """
    collection = "receipts" if document_type == "receipt" else "invoices"
    db = get_database()
    try:
        try:
            oid = ObjectId(document_id)
        except Exception:
            return {"error": f"Invalid document_id: {document_id}"}

        doc = await db[collection].find_one({"_id": oid, "corporate_id": corporate_id})
        if not doc:
            return {"error": "not found"}

        # 承認履歴付加（audit_logs から取得）
        doc = await enrich_with_approval_history(db, doc, document_id, document_type)

        current_step: Optional[int] = doc.get("current_step")
        approval_rule_id: Optional[str] = doc.get("approval_rule_id")

        # ── pending_approver の解決（3ステップ） ──────────────────────
        pending_approver: Optional[str] = None
        if approval_rule_id and current_step is not None:
            try:
                rule = await db["approval_rules"].find_one(
                    {"_id": ObjectId(approval_rule_id)}
                )
                if rule:
                    steps: List[dict] = rule.get("steps", [])
                    matching_step = next(
                        (s for s in steps if s.get("step") == current_step), None
                    )
                    if matching_step:
                        approver_role = matching_step.get("role")
                        if approver_role:
                            emp = await db["employees"].find_one({
                                "corporate_id": corporate_id,
                                "role": approver_role,
                            })
                            # 担当者名が取れればそれを、なければロール名をフォールバック
                            pending_approver = (
                                emp.get("name", approver_role) if emp else approver_role
                            )
            except Exception as sub_e:
                logger.warning(f"get_approval_status: pending_approver lookup failed: {sub_e}")

        return {
            "document_id": document_id,
            "approval_status": doc.get("approval_status"),
            "current_step": current_step,
            "approval_history": doc.get("approval_history", []),
            "pending_approver": pending_approver,
        }

    except Exception as e:
        logger.error(f"get_approval_status error: {e}")
        return {"error": str(e)}


# ── ⑤ get_budget_comparison ──────────────────────────────────────────────────

async def get_budget_comparison(
    corporate_id: str,
    fiscal_period: Optional[str] = None,
) -> dict:
    """
    予算対比・実績確認。

    - fiscal_period は "YYYY-MM" 形式。None の場合は当月を使う。
    - budgets コレクションは未実装のため、budget_total は常に None を返す。
      将来 budgets コレクションが追加された際はここに実装する。
    - 実績は receipts（amount）と received invoices（total_amount）を
      カテゴリ別に集計して返す。
    """
    db = get_database()
    if not fiscal_period:
        fiscal_period = datetime.utcnow().strftime("%Y-%m")

    try:
        # ── 実績集計（receipts + received invoices）── 並列取得 ──────
        receipt_pipeline = [
            {"$match": {
                "corporate_id": corporate_id,
                "fiscal_period": fiscal_period,
                "approval_status": {"$ne": "rejected"},
                "is_deleted": {"$ne": True},
            }},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
        ]
        invoice_pipeline = [
            {"$match": {
                "corporate_id": corporate_id,
                "fiscal_period": fiscal_period,
                "document_type": "received",
                "approval_status": {"$ne": "rejected"},
                "is_deleted": {"$ne": True},
            }},
            {"$group": {"_id": "$category", "total": {"$sum": "$total_amount"}}},
        ]

        receipt_agg, invoice_agg = await asyncio.gather(
            db["receipts"].aggregate(receipt_pipeline).to_list(length=100),
            db["invoices"].aggregate(invoice_pipeline).to_list(length=100),
        )

        # カテゴリ別実績の合算
        actual_by_cat: Dict[str, int] = {}
        for item in receipt_agg + invoice_agg:
            cat = item["_id"] or "未分類"
            actual_by_cat[cat] = actual_by_cat.get(cat, 0) + int(item.get("total") or 0)

        actual_total = sum(actual_by_cat.values())

        # ── 予算データ（budgets コレクション・未実装時は None） ───────
        budget_total: Optional[int] = None
        budget_by_cat: Dict[str, int] = {}
        try:
            budget_doc = await db["budgets"].find_one({
                "corporate_id": corporate_id,
                "fiscal_period": fiscal_period,
            })
            if budget_doc:
                budget_total = budget_doc.get("total_amount")
                for item in budget_doc.get("categories", []):
                    budget_by_cat[item.get("category", "未分類")] = item.get("amount", 0)
        except Exception:
            pass  # budgets コレクション未存在でも継続

        # ── カテゴリ一覧（実績・予算の和集合） ────────────────────────
        all_cats = sorted(set(list(actual_by_cat.keys()) + list(budget_by_cat.keys())))
        categories = [
            {
                "category": cat,
                "budget": budget_by_cat.get(cat),
                "actual": actual_by_cat.get(cat, 0),
            }
            for cat in all_cats
        ]

        return {
            "fiscal_period": fiscal_period,
            "budget_total": budget_total,
            "actual_total": actual_total,
            "variance": (budget_total - actual_total) if budget_total is not None else None,
            "categories": categories,
        }

    except Exception as e:
        logger.error(f"get_budget_comparison error: {e}")
        return {"error": str(e), "fiscal_period": fiscal_period}


# ── ⑥ read_file ──────────────────────────────────────────────────────────────

async def read_file(
    corporate_id: str,
    file_url: str,
    doc_type: str = "receipt",
) -> dict:
    """
    ファイル読み取り（将来の Gemini Flash OCR 連携用プレースホルダー）。
    現時点では not_implemented を返す。
    """
    return {
        "status": "not_implemented",
        "message": "ファイル読み取り機能は現在実装中です。",
        "file_url": file_url,
        "doc_type": doc_type,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 提案系ツール（4本）
# ═══════════════════════════════════════════════════════════════════════════

# ── 共通ヘルパー：JOURNAL_MAP キーワードマッチ ─────────────────────────────

def _lookup_journal(
    description: Optional[str],
    category: Optional[str],
) -> Dict[str, Any]:
    """
    JOURNAL_MAP を使って description / category から仕訳情報を推測する。

    優先順：
    1. category が JOURNAL_MAP のキーと完全一致 → confidence="category_matched"
    2. description が keywords のいずれかを含む → confidence="category_matched"
    3. 一致なし → "雑費" / confidence="default"
    """
    # 1. category 完全一致
    if category and category in JOURNAL_MAP:
        entry = JOURNAL_MAP[category]
        return {
            "account_name": category,
            "debit": entry["debit"],
            "credit": entry["credit"],
            "tax_category": entry["tax_category"],
            "confidence": "category_matched",
        }

    # 2. description が keywords を含む（部分一致）
    if description:
        for name, entry in JOURNAL_MAP.items():
            for kw in entry.get("keywords", []):
                if kw in description:
                    return {
                        "account_name": name,
                        "debit": entry["debit"],
                        "credit": entry["credit"],
                        "tax_category": entry["tax_category"],
                        "confidence": "category_matched",
                    }

    # 3. 雑費フォールバック
    fallback = JOURNAL_MAP.get("雑費", {})
    return {
        "account_name": "雑費",
        "debit": fallback.get("debit", "雑費"),
        "credit": fallback.get("credit", "未払金"),
        "tax_category": fallback.get("tax_category", "課税仕入 10%"),
        "confidence": "default",
    }


# ── ① suggest_journal_entry ──────────────────────────────────────────────

async def suggest_journal_entry(
    corporate_id: str,
    document_type: str,
    document_id: str,
    amount: Optional[int] = None,
    description: Optional[str] = None,
) -> dict:
    """
    仕訳の提案（勘定科目・税区分）。

    優先順：
    1. journal_rules に一致するルールがあれば → confidence="rule_matched"
       ルールのフィールド: keyword（単数）/ target_field / account_subject / tax_division
    2. JOURNAL_MAP でキーワードマッチ → confidence="category_matched"
    3. 一致なし → "雑費" / confidence="default"
    """
    _COLLECTION_MAP = {"receipt": "receipts", "invoice": "invoices"}
    db = get_database()
    try:
        collection = _COLLECTION_MAP.get(document_type)
        if not collection:
            return {"error": f"Unknown document_type: {document_type}"}

        try:
            oid = ObjectId(document_id)
        except Exception:
            return {"error": f"Invalid document_id: {document_id}"}

        doc = await db[collection].find_one({"_id": oid, "corporate_id": corporate_id})
        if not doc:
            return {"error": "not found"}

        doc_description = description or doc.get("description", "") or doc.get("payee", "")
        doc_category = doc.get("category", "")
        doc_amount = amount or doc.get("amount") or doc.get("total_amount") or 0

        # ── journal_rules での照合（keyword: 単数文字列・部分一致） ──────
        rules = await db["journal_rules"].find({
            "corporate_id": corporate_id,
            "is_active": True,
        }).to_list(length=100)

        for rule in rules:
            keyword = rule.get("keyword", "")
            target_field = rule.get("target_field", "description")

            target_value = ""
            if target_field == "description":
                target_value = doc_description
            elif target_field == "category":
                target_value = doc_category
            elif target_field == "payee":
                target_value = doc.get("payee", "")

            if keyword and target_value and keyword in target_value:
                return {
                    "document_id": document_id,
                    "suggested_debit": rule.get("account_subject", ""),
                    "suggested_credit": "未払金",
                    "suggested_tax_category": rule.get("tax_division", ""),
                    "amount": int(doc_amount),
                    "confidence": "rule_matched",
                    "source_rule_id": str(rule.get("_id", "")),
                }

        # ── JOURNAL_MAP キーワードマッチ ─────────────────────────────────
        journal = _lookup_journal(doc_description, doc_category)

        return {
            "document_id": document_id,
            "suggested_debit": journal["debit"],
            "suggested_credit": journal["credit"],
            "suggested_tax_category": journal["tax_category"],
            "amount": int(doc_amount),
            "confidence": journal["confidence"],
            "source_rule_id": None,
        }

    except Exception as e:
        logger.error(f"suggest_journal_entry error: {e}")
        return {"error": str(e)}


# ── ② suggest_reconciliation ────────────────────────────────────────────

async def suggest_reconciliation(
    corporate_id: str,
    transaction_id: str,
) -> dict:
    """
    消込候補のマッチング提案。

    calculate_match_score は同期関数（await 不要）。

    候補フィルタ（仕様 ④）：
    - receipts : approval_status="approved" + reconciliation_status != "reconciled"
    - invoices : document_type="received" + reconciliation_status != "reconciled"
    """
    db = get_database()
    try:
        try:
            oid = ObjectId(transaction_id)
        except Exception:
            return {"error": f"Invalid transaction_id: {transaction_id}"}

        tx_doc = await db["transactions"].find_one({"_id": oid, "corporate_id": corporate_id})
        if not tx_doc:
            return {"error": "not found"}

        # amount は deposit_amount > withdrawal_amount > amount の優先順で取得
        tx_amount = int(
            tx_doc.get("deposit_amount")
            or tx_doc.get("withdrawal_amount")
            or tx_doc.get("amount")
            or 0
        )
        # calculate_match_score は "amount" キーを参照するため上書き
        tx_for_score = {**{k: v for k, v in tx_doc.items()}, "amount": tx_amount}

        # ── 候補取得（並列） ──────────────────────────────────────────────
        receipts_filter = {
            "corporate_id": corporate_id,
            "approval_status": "approved",
            "reconciliation_status": {"$ne": "reconciled"},
        }
        invoices_filter = {
            "corporate_id": corporate_id,
            "document_type": "received",
            "reconciliation_status": {"$ne": "reconciled"},
        }

        receipts, invoices = await asyncio.gather(
            db["receipts"].find(receipts_filter).to_list(length=200),
            db["invoices"].find(invoices_filter).to_list(length=200),
        )

        # ── スコアリング（同期） ───────────────────────────────────────────
        candidates: List[Dict[str, Any]] = []

        for doc in receipts:
            result = calculate_match_score(tx_for_score, doc, "receipt")
            if result["is_candidate"]:
                doc_amount = int(doc.get("amount", 0))
                candidates.append({
                    "document_id": str(doc["_id"]),
                    "document_type": "receipt",
                    "score": result["score"],
                    "amount": doc_amount,
                    "description": doc.get("payee", "") or doc.get("description", ""),
                    "difference": abs(tx_amount - doc_amount),
                })

        for doc in invoices:
            result = calculate_match_score(tx_for_score, doc, "invoice")
            if result["is_candidate"]:
                doc_amount = int(doc.get("total_amount", doc.get("amount", 0)))
                candidates.append({
                    "document_id": str(doc["_id"]),
                    "document_type": "invoice",
                    "score": result["score"],
                    "amount": doc_amount,
                    "description": (
                        doc.get("vendor_name", "") or doc.get("client_name", "")
                    ),
                    "difference": abs(tx_amount - doc_amount),
                })

        # スコア降順・上位5件
        candidates.sort(key=lambda x: x["score"], reverse=True)
        candidates = candidates[:5]

        return {
            "transaction_id": transaction_id,
            "transaction": {
                "date": str(tx_doc.get("transaction_date", ""))[:10],
                "description": tx_doc.get("description", ""),
                "amount": tx_amount,
            },
            "candidates": candidates,
        }

    except Exception as e:
        logger.error(f"suggest_reconciliation error: {e}")
        return {"error": str(e), "candidates": []}


# ── ③ draft_expense_claim ────────────────────────────────────────────────

async def draft_expense_claim(
    corporate_id: str,
    user_id: str,
    amount: int,
    description: str,
    date_str: str,
    category: Optional[str] = None,
    payment_method: Optional[str] = None,
) -> dict:
    """
    経費申請の下書き作成（DB への書き込みなし）。

    category が None の場合は _lookup_journal で description から推測する。
    仕訳提案も _lookup_journal を直接呼ぶ（document_id は使わない）。
    """
    try:
        journal = _lookup_journal(description, category)
        inferred_category = category or journal["account_name"]

        draft = {
            "corporate_id": corporate_id,
            "submitted_by": user_id,
            "date": date_str,
            "amount": amount,
            "tax_rate": 10,
            "payee": description,
            "category": inferred_category,
            "payment_method": payment_method or "現金",
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
        }

        suggested_journal = {
            "suggested_debit": journal["debit"],
            "suggested_credit": journal["credit"],
            "suggested_tax_category": journal["tax_category"],
            "amount": amount,
            "confidence": journal["confidence"],
            "source_rule_id": None,
        }

        return {
            "draft": draft,
            "suggested_journal": suggested_journal,
            "confirmation_required": True,
        }

    except Exception as e:
        logger.error(f"draft_expense_claim error: {e}")
        return {"error": str(e)}


# ── ④ draft_invoice ──────────────────────────────────────────────────────

async def draft_invoice(
    corporate_id: str,
    user_id: str,
    client_id: str,
    amount: int,
    description: str,
    due_date: Optional[str] = None,
    tax_rate: int = DEFAULT_TAX_RATE,
) -> dict:
    """
    請求書の下書き作成（DB への書き込みなし）。

    取引先が見つからない場合は {"error": "取引先が見つかりません"} を返す。
    due_date が None の場合は today + 30 日。
    """
    db = get_database()
    try:
        try:
            client_oid = ObjectId(client_id)
        except Exception:
            return {"error": "取引先が見つかりません"}

        client = await db["clients"].find_one(
            {"_id": client_oid, "corporate_id": corporate_id}
        )
        if not client:
            return {"error": "取引先が見つかりません"}

        today = date.today()
        issue_date_str = today.strftime("%Y-%m-%d")
        resolved_due_date = due_date or (today + timedelta(days=30)).strftime("%Y-%m-%d")

        tax_amount = calc_tax_from_exclusive(amount, tax_rate)
        total_amount = amount + tax_amount

        draft = {
            "corporate_id": corporate_id,
            "created_by": user_id,
            "document_type": "issued",
            "client_id": client_id,
            "client_name": client.get("name", ""),
            "issue_date": issue_date_str,
            "due_date": resolved_due_date,
            "amount": amount,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "description": description,
            "approval_status": "pending_approval",
            "delivery_status": "unsent",
        }

        return {
            "draft": draft,
            "confirmation_required": True,
        }

    except Exception as e:
        logger.error(f"draft_invoice error: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Task#17-C: 実行系ツール（7本）
# ═══════════════════════════════════════════════════════════════════════════
# 共通設計：
#   confirmed=False → confirmation_required=True + プレビューメッセージ
#   confirmed=True  → DB 操作を実行
# ═══════════════════════════════════════════════════════════════════════════

async def exec_submit_expense_claim(
    corporate_id: str,
    user_id: str,
    date: str,
    amount: int,
    payee: str,
    category: str,
    payment_method: str,
    tax_rate: int = DEFAULT_TAX_RATE,
    file_url: Optional[str] = None,
    fiscal_period: str = "",
    confirmed: bool = False,
) -> dict:
    """経費申請を登録する。confirmed=False は確認を求める。"""
    try:
        from fastapi import HTTPException
        if amount < 0:
            raise HTTPException(status_code=400, detail="金額は0以上である必要があります")
        if tax_rate not in (0, 8, 10):
            raise HTTPException(status_code=400, detail="税率は0%・8%・10%のいずれかである必要があります")

        if not confirmed:
            return {
                "confirmation_required": True,
                "tool_name": "submit_expense_claim",
                "message": (
                    f"以下の内容で経費申請を登録しますか？\n"
                    f"日付：{date}\n金額：¥{amount:,}\n"
                    f"取引先：{payee}\n科目：{category}"
                ),
                "data": {
                    "date": date, "amount": amount, "payee": payee,
                    "category": category, "payment_method": payment_method,
                    "tax_rate": tax_rate, "file_url": file_url,
                    "fiscal_period": fiscal_period,
                },
            }

        db = get_database()
        from app.services.rule_evaluation_service import evaluate_approval_rules

        doc = {
            "date": date, "amount": amount, "payee": payee, "category": category,
            "payment_method": payment_method, "tax_rate": tax_rate,
            "file_url": file_url, "fiscal_period": fiscal_period,
            "corporate_id": corporate_id, "submitted_by": user_id,
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "created_at": datetime.utcnow(),
        }
        rule_id, _ = await evaluate_approval_rules(corporate_id, "receipt", doc)
        doc["approval_rule_id"] = rule_id
        doc["current_step"] = 1

        result = await db["receipts"].insert_one(doc)
        return {
            "success": True,
            "receipt_id": str(result.inserted_id),
            "message": "経費申請を登録しました。",
        }
    except Exception as e:
        logger.error(f"exec_submit_expense_claim error: {e}")
        if hasattr(e, "status_code"):
            raise
        return {"error": str(e)}


async def exec_send_invoice(
    corporate_id: str,
    user_id: str,
    invoice_id: str,
    confirmed: bool = False,
) -> dict:
    """発行請求書を送付する。confirmed=False は確認を求める。"""
    try:
        db = get_database()
        oid = ObjectId(invoice_id)
        inv = await db["invoices"].find_one(
            {"_id": oid, "corporate_id": corporate_id, "document_type": "issued"}
        )
        if not inv:
            return {"error": "請求書が見つかりません"}

        client_name = inv.get("client_name", "")
        total_amount = inv.get("total_amount", 0)

        if not confirmed:
            return {
                "confirmation_required": True,
                "tool_name": "send_invoice",
                "message": f"請求書（{client_name}・¥{total_amount:,}）を送付しますか？",
                "data": {"invoice_id": invoice_id},
            }

        await db["invoices"].update_one(
            {"_id": oid, "corporate_id": corporate_id},
            {"$set": {"delivery_status": "sent", "sent_at": datetime.utcnow()}},
        )
        return {"success": True, "message": "請求書を送付しました。"}
    except Exception as e:
        logger.error(f"exec_send_invoice error: {e}")
        return {"error": str(e)}


async def exec_approve_document(
    corporate_id: str,
    user_id: str,
    document_type: str,
    document_id: str,
    action: str,
    comment: Optional[str] = None,
    confirmed: bool = False,
) -> dict:
    """
    ドキュメントを承認または差し戻しする。
    ② A案: agent_tools.py 内で DB 操作を直接記述。
    """
    try:
        if action == "rejected" and not comment:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="差し戻しの場合はコメントが必要です")

        db = get_database()
        collection = "receipts" if document_type == "receipt" else "invoices"
        oid = ObjectId(document_id)
        doc = await db[collection].find_one({"_id": oid, "corporate_id": corporate_id})
        if not doc:
            return {"error": "ドキュメントが見つかりません"}

        amount = doc.get("amount") or doc.get("total_amount", 0)
        action_label = "承認" if action == "approved" else "差し戻し"

        if not confirmed:
            return {
                "confirmation_required": True,
                "tool_name": "approve_document",
                "message": (
                    f"{document_type}（¥{amount:,}）を{action_label}しますか？"
                    + (f"\nコメント：{comment}" if comment else "")
                ),
                "data": {
                    "document_type": document_type, "document_id": document_id,
                    "action": action, "comment": comment,
                },
            }

        now = datetime.utcnow()
        # audit_log を記録
        await db["audit_logs"].insert_one({
            "document_id": document_id,
            "document_type": document_type,
            "action": action,
            "comment": comment,
            "corporate_id": corporate_id,
            "approver_id": user_id,
            "timestamp": now,
        })

        if action == "rejected":
            await db[collection].update_one(
                {"_id": oid},
                {"$set": {"approval_status": "rejected", "rejection_comment": comment, "updated_at": now}},
            )
        else:
            # 簡易承認：single-step として即 approved に更新
            await db[collection].update_one(
                {"_id": oid},
                {"$set": {"approval_status": "approved", "approved_at": now, "updated_at": now}},
            )

        return {"success": True, "message": f"{action_label}処理が完了しました。"}
    except Exception as e:
        logger.error(f"exec_approve_document error: {e}")
        if hasattr(e, "status_code"):
            raise
        return {"error": str(e)}


async def exec_execute_reconciliation(
    corporate_id: str,
    user_id: str,
    transaction_ids: List[str],
    document_ids: List[str],
    match_type: str,
    fiscal_period: str = "",
    confirmed: bool = False,
) -> dict:
    """消込を実行する。confirmed=False は確認を求める。"""
    try:
        db = get_database()
        if not transaction_ids:
            return {"error": "transaction_ids が必要です"}

        # プレビュー用に最初のトランザクションを取得
        tx_doc = await db["transactions"].find_one(
            {"_id": ObjectId(transaction_ids[0]), "corporate_id": corporate_id}
        )
        if not tx_doc:
            return {"error": "取引データが見つかりません"}

        tx_amount = int(
            tx_doc.get("deposit_amount") or tx_doc.get("withdrawal_amount") or tx_doc.get("amount") or 0
        )

        if not confirmed:
            return {
                "confirmation_required": True,
                "tool_name": "execute_reconciliation",
                "message": (
                    f"取引（¥{tx_amount:,}）と{len(document_ids)}件の書類を消込しますか？"
                ),
                "data": {
                    "transaction_ids": transaction_ids, "document_ids": document_ids,
                    "match_type": match_type, "fiscal_period": fiscal_period,
                },
            }

        now = datetime.utcnow()
        # matches コレクションに登録
        match_doc = {
            "corporate_id": corporate_id,
            "transaction_ids": transaction_ids,
            "document_ids": document_ids,
            "match_type": match_type,
            "fiscal_period": fiscal_period,
            "created_by": user_id,
            "created_at": now,
            "is_active": True,
        }
        await db["matches"].insert_one(match_doc)

        # トランザクションを matched に更新
        for tid in transaction_ids:
            await db["transactions"].update_one(
                {"_id": ObjectId(tid), "corporate_id": corporate_id},
                {"$set": {"status": "matched", "updated_at": now}},
            )

        # ドキュメントを reconciled に更新
        collection = "receipts" if match_type == "receipt" else "invoices"
        for did in document_ids:
            await db[collection].update_one(
                {"_id": ObjectId(did), "corporate_id": corporate_id},
                {"$set": {"reconciliation_status": "reconciled", "updated_at": now}},
            )

        return {"success": True, "message": "消込が完了しました。"}
    except Exception as e:
        logger.error(f"exec_execute_reconciliation error: {e}")
        return {"error": str(e)}


async def exec_export_csv(
    corporate_id: str,
    format_type: str,
    doc_type: str,
    fiscal_period: Optional[str] = None,
    confirmed: bool = False,
) -> dict:
    """CSV を出力する（ダウンロード URL を返す）。"""
    try:
        if format_type not in ("freee", "mf", "yayoi"):
            return {"error": f"不正な format_type: {format_type}"}

        if not confirmed:
            return {
                "confirmation_required": True,
                "tool_name": "export_csv",
                "message": (
                    f"{format_type}形式のCSVを出力しますか？\n"
                    f"対象：{doc_type}・期間：{fiscal_period or '全期間'}"
                ),
                "data": {"format_type": format_type, "doc_type": doc_type, "fiscal_period": fiscal_period},
            }

        params = f"format_type={format_type}&doc_type={doc_type}"
        if fiscal_period:
            params += f"&fiscal_period={fiscal_period}"
        return {
            "success": True,
            "message": "CSVを生成しました。ダウンロードリンクから取得してください。",
            "download_url": f"/api/v1/exports/csv?{params}",
        }
    except Exception as e:
        logger.error(f"exec_export_csv error: {e}")
        return {"error": str(e)}


async def exec_export_zengin(
    corporate_id: str,
    fiscal_period: Optional[str] = None,
    confirmed: bool = False,
) -> dict:
    """全銀データを出力する（ダウンロード URL を返す）。"""
    try:
        if not confirmed:
            return {
                "confirmation_required": True,
                "tool_name": "export_zengin",
                "message": f"全銀データ（{fiscal_period or '全期間'}）を出力しますか？",
                "data": {"fiscal_period": fiscal_period},
            }

        params = f"fiscal_period={fiscal_period}" if fiscal_period else ""
        url = f"/api/v1/exports/zengin" + (f"?{params}" if params else "")
        return {
            "success": True,
            "message": "全銀データを生成しました。ダウンロードリンクから取得してください。",
            "download_url": url,
        }
    except Exception as e:
        logger.error(f"exec_export_zengin error: {e}")
        return {"error": str(e)}


async def exec_notify_tax_advisor(
    corporate_id: str,
    user_id: str,
    message: str,
    priority: str = "normal",
    confirmed: bool = False,
) -> dict:
    """税理士にメッセージを送信する。"""
    try:
        if not message:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="メッセージを入力してください")

        db = get_database()

        # advising_tax_firm_id を取得
        corp = await db["corporates"].find_one({"_id": ObjectId(corporate_id)})
        if not corp:
            return {"error": "法人情報が見つかりません"}

        tax_firm_uid = corp.get("advising_tax_firm_id")
        if not tax_firm_uid:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail="紐付いた税理士法人がありません。先に税理士法人との連携を行ってください。",
            )

        if not confirmed:
            return {
                "confirmation_required": True,
                "tool_name": "notify_tax_advisor",
                "message": f"以下の内容を税理士に送信しますか？\n{message}",
                "data": {"message": message, "priority": priority},
            }

        await db["notifications"].insert_one({
            "corporate_id": corporate_id,
            "type": "tax_advisor_message",
            "notification_type": "tax_advisor_message",
            "user_id": user_id,
            "message": message,
            "priority": priority,
            "tax_firm_id": tax_firm_uid,
            "status": "pending",
            "read": False,
            "sent_at": datetime.utcnow(),
        })

        # 税理士にメール通知
        try:
            from firebase_admin import auth as firebase_auth
            from app.services.email_service import send_tax_advisor_notification_email
            tf_user = firebase_auth.get_user(tax_firm_uid)
            tf_email = tf_user.email or ""
            corp_name = corp.get("companyName", corporate_id)
            if tf_email:
                await send_tax_advisor_notification_email(tf_email, message, corp_name)
        except Exception as email_err:
            logger.warning(f"exec_notify_tax_advisor email error: {email_err}")

        return {"success": True, "message": "税理士に送信しました。"}
    except Exception as e:
        logger.error(f"exec_notify_tax_advisor error: {e}")
        if hasattr(e, "status_code"):
            raise
        return {"error": str(e)}
