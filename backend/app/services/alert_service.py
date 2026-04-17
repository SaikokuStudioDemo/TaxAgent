"""
Alert Service
Generates alert notifications for:
- Overdue invoices (due_date has passed)
- Upcoming due dates (within 3 days)
- High-amount documents matching an alert threshold
- Rejected documents left stale (差し戻し放置)
- Receipts with no attachment (証憑未提出)
- Approved but unreconciled documents (消込滞留)
- Approval flow delays (承認フロー遅延)

Called from APScheduler (daily at 8:00 AM) or manually via /admin/run-alerts.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from bson import ObjectId

from app.db.mongodb import get_database
from app.services.notification_service import create_notification
import logging

logger = logging.getLogger(__name__)

# Alert threshold: invoices above this amount are flagged as high-amount
HIGH_AMOUNT_THRESHOLD = 100_000  # ¥100,000

# デフォルト閾値（alerts_config 未設定時に使用）
DEFAULT_THRESHOLDS: Dict[str, int] = {
    "rejected_stale_days": 3,
    "no_attachment_days": 3,
    "unreconciled_days": 7,
    "approval_delay_days": 3,
    "tax_advisor_escalation_days": 3,
}


# ─────────────────────────────────────────────────────────────────────────────
# 共通ヘルパー
# ─────────────────────────────────────────────────────────────────────────────

async def get_alert_thresholds(corporate_id: str) -> Dict[str, int]:
    """
    alerts_config コレクションから法人別の閾値を取得する。
    未設定の場合は DEFAULT_THRESHOLDS を使う。
    """
    db = get_database()
    config = await db["alerts_config"].find_one({"corporate_id": corporate_id})
    if not config:
        return DEFAULT_THRESHOLDS.copy()
    result = DEFAULT_THRESHOLDS.copy()
    result.update({k: v for k, v in config.items() if k in DEFAULT_THRESHOLDS})
    return result


async def _get_employee_email(db: Any, employee_id: str) -> str:
    """employee_id から email を取得するプライベートヘルパー。"""
    if not employee_id:
        return ""
    try:
        emp = await db["employees"].find_one({"_id": ObjectId(employee_id)})
        return emp.get("email", "") if emp else ""
    except Exception:
        return ""


def _stale_filter(cutoff: datetime) -> Dict[str, Any]:
    """
    updated_at が存在すればそれを、存在しなければ created_at を使って
    cutoff より古いドキュメントを対象にするフィルタを返す。
    （updated_at が設定されていない既存ドキュメントへの対応）
    """
    return {"$or": [
        {"updated_at": {"$lt": cutoff}},
        {"updated_at": {"$exists": False}, "created_at": {"$lt": cutoff}},
    ]}


# ─────────────────────────────────────────────────────────────────────────────
# 既存アラート（変更しない）
# ─────────────────────────────────────────────────────────────────────────────

async def check_due_date_alerts() -> dict:
    """
    Scan all received invoices with status='received' or 'pending_approval'
    and generate due_date_alert / overdue_alert notifications.
    Returns counts for logging.
    """
    db = get_database()
    today = datetime.utcnow().date()
    three_days_later = today + timedelta(days=3)
    sent_due = 0
    sent_overdue = 0

    cursor = db["invoices"].find({
        "document_type": "received",
        "approval_status": {"$nin": ["approved", "auto_approved", "rejected"]},
        "reconciliation_status": {"$ne": "reconciled"},
        "due_date": {"$exists": True, "$ne": None},
    })
    invoices = await cursor.to_list(length=1000)

    for inv in invoices:
        due_str = inv.get("due_date", "")
        if not due_str:
            continue
        try:
            due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        corporate_id = inv.get("corporate_id", "")
        doc_id = str(inv["_id"])
        amount = inv.get("total_amount", 0)
        client_name = inv.get("client_name", "不明")
        summary = f"{client_name} ¥{amount:,}"
        submitter_id = inv.get("created_by", "")
        submitter_email = ""

        if submitter_id:
            try:
                emp = await db["employees"].find_one({"_id": ObjectId(submitter_id)})
                if emp:
                    submitter_email = emp.get("email", "")
            except Exception:
                pass

        if due_date < today:
            await create_notification(
                corporate_id=corporate_id,
                notification_type="overdue_alert",
                recipient_employee_id=submitter_id,
                recipient_email=submitter_email,
                related_document_type="invoice",
                related_document_id=doc_id,
                message=f"【期限超過】{summary} の支払期限が過ぎています。",
            )
            sent_overdue += 1
        elif today <= due_date <= three_days_later:
            days_left = (due_date - today).days
            await create_notification(
                corporate_id=corporate_id,
                notification_type="due_date_alert",
                recipient_employee_id=submitter_id,
                recipient_email=submitter_email,
                related_document_type="invoice",
                related_document_id=doc_id,
                message=f"【期限{days_left}日前】{summary} の支払期限が近づいています。",
            )
            sent_due += 1

    logger.info(f"[Alert] overdue={sent_overdue} due_soon={sent_due}")
    return {"overdue": sent_overdue, "due_soon": sent_due}


async def check_high_amount_alerts(threshold: int = HIGH_AMOUNT_THRESHOLD) -> dict:
    """
    Flag newly submitted documents (receipts/invoices) that exceed the high-amount threshold
    and haven't been alerted yet.
    """
    db = get_database()
    flagged = 0

    for collection_name, amount_field in [("receipts", "amount"), ("invoices", "total_amount")]:
        cursor = db[collection_name].find({
            amount_field: {"$gte": threshold},
            "approval_status": "pending_approval",
            "high_amount_alerted": {"$ne": True},
        })
        docs = await cursor.to_list(length=500)

        for doc in docs:
            corporate_id = doc.get("corporate_id", "")
            doc_id = str(doc["_id"])
            amount = doc.get(amount_field, 0)
            submitter_id = doc.get("submitted_by", doc.get("created_by", ""))
            submitter_email = ""

            if submitter_id:
                try:
                    emp = await db["employees"].find_one({"_id": ObjectId(submitter_id)})
                    if emp:
                        submitter_email = emp.get("email", "")
                except Exception:
                    pass

            doc_type = "receipt" if collection_name == "receipts" else "invoice"
            await create_notification(
                corporate_id=corporate_id,
                notification_type="high_amount_alert",
                recipient_employee_id=submitter_id,
                recipient_email=submitter_email,
                related_document_type=doc_type,
                related_document_id=doc_id,
                message=f"【高額アラート】¥{amount:,} の{doc_type}が提出されました。",
            )
            await db[collection_name].update_one(
                {"_id": doc["_id"]},
                {"$set": {"high_amount_alerted": True}},
            )
            flagged += 1

    logger.info(f"[Alert] high_amount flagged={flagged}")
    return {"high_amount_flagged": flagged}


# ─────────────────────────────────────────────────────────────────────────────
# 新規アラート（Task#22）
# ─────────────────────────────────────────────────────────────────────────────

async def check_rejected_stale_alerts() -> dict:
    """
    差し戻し放置アラート。
    approval_status='rejected' かつ N日以上更新なし（updated_at なければ created_at）。
    申請者に通知する。重複防止のため rejected_stale_alerted フラグを立てる。
    """
    db = get_database()
    count = 0

    corp_ids_receipts: List[str] = await db["receipts"].distinct("corporate_id")
    corp_ids_invoices: List[str] = await db["invoices"].distinct("corporate_id")
    corporate_ids = list(set(corp_ids_receipts + corp_ids_invoices))

    for corp_id in corporate_ids:
        thresholds = await get_alert_thresholds(corp_id)
        days = thresholds["rejected_stale_days"]
        cutoff = datetime.utcnow() - timedelta(days=days)
        stale_filter = _stale_filter(cutoff)

        for col, doc_type in [("receipts", "receipt"), ("invoices", "invoice")]:
            query: Dict[str, Any] = {
                "corporate_id": corp_id,
                "approval_status": "rejected",
                "rejected_stale_alerted": {"$ne": True},
                **stale_filter,
            }
            # $or を含む _stale_filter と既存条件を正しくマージ
            query = {
                "corporate_id": corp_id,
                "approval_status": "rejected",
                "rejected_stale_alerted": {"$ne": True},
                "$or": stale_filter["$or"],
            }
            docs = await db[col].find(query).to_list(length=500)

            for doc in docs:
                submitter_id = doc.get("submitted_by", doc.get("created_by", ""))
                submitter_email = await _get_employee_email(db, submitter_id)
                amount = doc.get("amount") or doc.get("total_amount", 0)

                await create_notification(
                    corporate_id=corp_id,
                    notification_type="rejected_stale_alert",
                    recipient_employee_id=submitter_id,
                    recipient_email=submitter_email,
                    related_document_type=doc_type,
                    related_document_id=str(doc["_id"]),
                    message=(
                        f"差し戻しされた{doc_type}が{days}日以上放置されています。"
                        f"（¥{amount:,}）"
                    ),
                )
                await db[col].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"rejected_stale_alerted": True}},
                )
                count += 1

    logger.info(f"[Alert] rejected_stale count={count}")
    return {"rejected_stale": count}


async def check_no_attachment_alerts() -> dict:
    """
    証憑未提出アラート。
    file_url が空・null で N日以上前の領収書。
    申請者に通知する。重複防止のため no_attachment_alerted フラグを立てる。
    """
    db = get_database()
    count = 0

    corporate_ids: List[str] = await db["receipts"].distinct("corporate_id")

    for corp_id in corporate_ids:
        thresholds = await get_alert_thresholds(corp_id)
        days = thresholds["no_attachment_days"]
        cutoff = datetime.utcnow() - timedelta(days=days)

        docs = await db["receipts"].find({
            "corporate_id": corp_id,
            "approval_status": "pending_approval",
            "created_at": {"$lt": cutoff},
            "$or": [
                {"file_url": {"$exists": False}},
                {"file_url": None},
                {"file_url": ""},
            ],
            "no_attachment_alerted": {"$ne": True},
        }).to_list(length=500)

        for doc in docs:
            submitter_id = doc.get("submitted_by", "")
            submitter_email = await _get_employee_email(db, submitter_id)

            await create_notification(
                corporate_id=corp_id,
                notification_type="no_attachment_alert",
                recipient_employee_id=submitter_id,
                recipient_email=submitter_email,
                related_document_type="receipt",
                related_document_id=str(doc["_id"]),
                message=(
                    f"証憑（ファイル）が未提出の領収書が"
                    f"{days}日以上放置されています。"
                ),
            )
            await db["receipts"].update_one(
                {"_id": doc["_id"]},
                {"$set": {"no_attachment_alerted": True}},
            )
            count += 1

    logger.info(f"[Alert] no_attachment count={count}")
    return {"no_attachment": count}


async def check_unreconciled_alerts() -> dict:
    """
    消込滞留アラート。
    approval_status='approved' かつ reconciliation_status が未消込で N日以上。
    経理担当者に通知する。重複防止のため unreconciled_alerted フラグを立てる。
    """
    db = get_database()
    count = 0

    corp_ids_receipts: List[str] = await db["receipts"].distinct("corporate_id")
    corp_ids_invoices: List[str] = await db["invoices"].distinct("corporate_id")
    corporate_ids = list(set(corp_ids_receipts + corp_ids_invoices))

    for corp_id in corporate_ids:
        thresholds = await get_alert_thresholds(corp_id)
        days = thresholds["unreconciled_days"]
        cutoff = datetime.utcnow() - timedelta(days=days)
        stale_filter = _stale_filter(cutoff)

        # ② 経理担当者はループの外で1回だけ取得
        accountant = await db["employees"].find_one({
            "corporate_id": corp_id,
            "role": "accounting",
        })
        recipient_id = str(accountant["_id"]) if accountant else ""
        recipient_email = accountant.get("email", "") if accountant else ""

        for col, doc_type in [("receipts", "receipt"), ("invoices", "invoice")]:
            query = {
                "corporate_id": corp_id,
                "approval_status": "approved",
                "reconciliation_status": {"$in": ["unreconciled", None, ""]},
                "unreconciled_alerted": {"$ne": True},
                "$or": stale_filter["$or"],
            }
            docs = await db[col].find(query).to_list(length=500)

            for doc in docs:
                amount = doc.get("amount") or doc.get("total_amount", 0)

                await create_notification(
                    corporate_id=corp_id,
                    notification_type="unreconciled_alert",
                    recipient_employee_id=recipient_id,
                    recipient_email=recipient_email,
                    related_document_type=doc_type,
                    related_document_id=str(doc["_id"]),
                    message=(
                        f"承認済みの{doc_type}が{days}日以上消込されていません。"
                        f"（¥{amount:,}）"
                    ),
                )
                await db[col].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"unreconciled_alerted": True}},
                )
                count += 1

    logger.info(f"[Alert] unreconciled count={count}")
    return {"unreconciled": count}


async def check_approval_delay_alerts() -> dict:
    """
    承認フロー遅延アラート。
    approval_status='pending_approval' のまま N日以上。
    approval_rules から current_step の担当ロールを解決し、その担当者に通知する。
    重複防止のため approval_delay_alerted フラグを立てる。
    """
    db = get_database()
    count = 0

    corp_ids_receipts: List[str] = await db["receipts"].distinct("corporate_id")
    corp_ids_invoices: List[str] = await db["invoices"].distinct("corporate_id")
    corporate_ids = list(set(corp_ids_receipts + corp_ids_invoices))

    for corp_id in corporate_ids:
        thresholds = await get_alert_thresholds(corp_id)
        days = thresholds["approval_delay_days"]
        cutoff = datetime.utcnow() - timedelta(days=days)

        for col, doc_type in [("receipts", "receipt"), ("invoices", "invoice")]:
            query = {
                "corporate_id": corp_id,
                "approval_status": "pending_approval",
                "approval_delay_alerted": {"$ne": True},
                "$or": [
                    {"updated_at": {"$lt": cutoff}},
                    {"updated_at": {"$exists": False}, "created_at": {"$lt": cutoff}},
                ],
            }
            docs = await db[col].find(query).to_list(length=500)

            for doc in docs:
                rule_id = doc.get("approval_rule_id")
                current_step = doc.get("current_step", 1)
                approver_id = ""
                approver_email = ""

                # approval_rules → employees の順で承認者を解決
                if rule_id:
                    try:
                        rule = await db["approval_rules"].find_one(
                            {"_id": ObjectId(rule_id)}
                        )
                        if rule:
                            step = next(
                                (s for s in rule.get("steps", [])
                                 if s.get("step") == current_step),
                                None,
                            )
                            if step:
                                approver = await db["employees"].find_one({
                                    "corporate_id": corp_id,
                                    "role": step.get("role"),
                                })
                                if approver:
                                    approver_id = str(approver["_id"])
                                    approver_email = approver.get("email", "")
                    except Exception as e:
                        logger.warning(f"[Alert] approval_delay approver lookup failed: {e}")

                amount = doc.get("amount") or doc.get("total_amount", 0)

                await create_notification(
                    corporate_id=corp_id,
                    notification_type="approval_delay_alert",
                    recipient_employee_id=approver_id,
                    recipient_email=approver_email,
                    related_document_type=doc_type,
                    related_document_id=str(doc["_id"]),
                    message=(
                        f"承認待ちの{doc_type}が{days}日以上止まっています。"
                        f"（¥{amount:,}）"
                    ),
                )
                await db[col].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"approval_delay_alerted": True}},
                )
                count += 1

    logger.info(f"[Alert] approval_delay count={count}")
    return {"approval_delay": count}


# ─────────────────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────────────────

async def run_all_alerts() -> dict:
    """全アラートチェックを一括実行する（APScheduler / admin エンドポイントから呼ぶ）。"""
    due_result = await check_due_date_alerts()
    high_result = await check_high_amount_alerts()
    rejected_result = await check_rejected_stale_alerts()
    no_attach_result = await check_no_attachment_alerts()
    unreconciled_result = await check_unreconciled_alerts()
    delay_result = await check_approval_delay_alerts()
    return {
        **due_result,
        **high_result,
        **rejected_result,
        **no_attach_result,
        **unreconciled_result,
        **delay_result,
    }
