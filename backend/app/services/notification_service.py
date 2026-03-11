"""
Notification service: creates notification records in MongoDB.
Actual email delivery will be implemented separately (e.g., SendGrid / SMTP).
"""
from datetime import datetime
from app.db.mongodb import get_database


async def create_notification(
    corporate_id: str,
    notification_type: str,
    recipient_employee_id: str,
    recipient_email: str,
    related_document_type: str,
    related_document_id: str,
    message: str,
) -> None:
    """
    Persist a notification record to the `notifications` collection.
    """
    db = get_database()
    doc = {
        "corporate_id": corporate_id,
        "type": notification_type,
        "recipient_employee_id": recipient_employee_id,
        "recipient_email": recipient_email,
        "related_document_type": related_document_type,
        "related_document_id": related_document_id,
        "message": message,
        "sent_at": datetime.utcnow(),
        "status": "pending",  # Will be updated to "sent" or "failed" by the email sender
    }
    await db["notifications"].insert_one(doc)


async def notify_next_approver(
    corporate_id: str,
    document_type: str,
    document_id: str,
    current_step: int,
    approval_rule_id: str,
    document_summary: str,
) -> None:
    """
    Find the next approver for the given step and create a notification.
    """
    from bson import ObjectId
    db = get_database()

    try:
        rule = await db["approval_rules"].find_one({"_id": ObjectId(approval_rule_id)})
    except Exception:
        return

    if not rule:
        return

    steps = rule.get("steps", [])
    target_step = next((s for s in steps if s.get("step") == current_step), None)
    if not target_step:
        return

    target_role = target_step.get("role")

    # Find an employee with the matching role in this corporate
    employee = await db["employees"].find_one({
        "parent_corporate_firebase_uid": {"$exists": True},
        "role": target_role,
    })

    if not employee:
        return  # No matching approver found; silently skip

    recipient_id = str(employee["_id"])
    recipient_email = employee.get("email", "")

    await create_notification(
        corporate_id=corporate_id,
        notification_type="approval_request",
        recipient_employee_id=recipient_id,
        recipient_email=recipient_email,
        related_document_type=document_type,
        related_document_id=document_id,
        message=f"承認依頼が届きました: {document_summary}",
    )


async def notify_submitter(
    corporate_id: str,
    document_type: str,
    document_id: str,
    submitter_id: str,
    action: str,  # "approved" or "rejected"
    document_summary: str,
) -> None:
    """
    Notify the original submitter about approval outcome.
    """
    db = get_database()
    from bson import ObjectId

    try:
        submitter = await db["employees"].find_one({"_id": ObjectId(submitter_id)})
    except Exception:
        submitter = None

    recipient_email = submitter.get("email", "") if submitter else ""
    notif_type = "approved_notification" if action == "approved" else "rejected_notification"
    label = "承認されました" if action == "approved" else "差し戻されました"

    await create_notification(
        corporate_id=corporate_id,
        notification_type=notif_type,
        recipient_employee_id=submitter_id,
        recipient_email=recipient_email,
        related_document_type=document_type,
        related_document_id=document_id,
        message=f"{document_summary} が{label}。",
    )
