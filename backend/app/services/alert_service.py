"""
Alert Service
Generates alert notifications for:
- Overdue invoices (due_date has passed)
- Upcoming due dates (within 3 days)
- High-amount documents matching an alert threshold

Called from a background scheduler (or manually via /admin/run-alerts endpoint).
"""
from datetime import datetime, timedelta
from app.db.mongodb import get_database
from app.services.notification_service import create_notification
import logging

logger = logging.getLogger(__name__)

# Alert threshold: invoices above this amount are flagged as high-amount
HIGH_AMOUNT_THRESHOLD = 100_000  # ¥100,000


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

        # Try to find the creator's email
        if submitter_id:
            from bson import ObjectId
            try:
                emp = await db["employees"].find_one({"_id": ObjectId(submitter_id)})
                if emp:
                    submitter_email = emp.get("email", "")
            except Exception:
                pass

        if due_date < today:
            # Overdue
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
            # Coming up soon
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
                from bson import ObjectId
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

            # Mark as alerted to avoid duplicate notifications
            await db[collection_name].update_one(
                {"_id": doc["_id"]},
                {"$set": {"high_amount_alerted": True}},
            )
            flagged += 1

    logger.info(f"[Alert] high_amount flagged={flagged}")
    return {"high_amount_flagged": flagged}


async def run_all_alerts() -> dict:
    """Entry point to run all alert checks at once (used by admin endpoint or scheduler)."""
    due_result = await check_due_date_alerts()
    high_result = await check_high_amount_alerts()
    return {**due_result, **high_result}
