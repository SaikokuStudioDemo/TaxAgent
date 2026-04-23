"""
Notification service: creates notification records in MongoDB and sends emails.
"""
from datetime import datetime
from app.db.mongodb import get_database
from app.core.config import settings

# アラート系通知のみ alerts_config.email_enabled でメール送否を制御する。
# 業務系通知（承認依頼・承認結果等）は常に送信。
ALERT_TYPES = frozenset({
    "rejected_stale_alert",
    "no_attachment_alert",
    "unreconciled_alert",
    "approval_delay_alert",
    "tax_advisor_escalation_alert",
})


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
    通知を DB に保存し、条件を満たす場合にメールを送信する。

    アラート系（ALERT_TYPES）: alerts_config.email_enabled が True のときのみ送信。
    業務系（それ以外）: recipient_email があれば常に送信。
    どちらも SENDGRID_API_KEY が未設定の場合は送信しない。
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
        "status": "pending",
    }
    await db["notifications"].insert_one(doc)

    if not (recipient_email and settings.SENDGRID_API_KEY):
        return

    should_send: bool
    if notification_type in ALERT_TYPES:
        config = await db["alerts_config"].find_one({"corporate_id": corporate_id})
        email_enabled = config.get("email_enabled", {}) if config else {}
        should_send = bool(email_enabled.get(notification_type, False))
    else:
        should_send = True

    if should_send:
        subject = f"【Tax-Agent】{message[:30]}..."
        await send_email_notification(recipient_email, subject, message)


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
        "corporate_id": corporate_id,
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


# ─────────────────────────────────────────────────────────────────────────────
# メール送信プレースホルダー（Task#23）
# 実際の送信は Task#47（メール送信インフラ選定後）に実装する。
# 現時点ではログ出力のみ行い、DB 通知記録は create_notification が担う。
# ─────────────────────────────────────────────────────────────────────────────

async def send_email_notification(
    recipient_email: str,
    subject: str,
    body: str,
) -> bool:
    """メール送信。SendGrid が未設定の場合はスキップして False を返す。"""
    if not recipient_email:
        return False
    from app.services.email_service import _send
    return await _send(recipient_email, subject, f"<p>{body}</p>")


async def create_notification_with_email(
    corporate_id: str,
    notification_type: str,
    recipient_employee_id: str,
    recipient_email: str,
    related_document_type: str,
    related_document_id: str,
    message: str,
) -> None:
    """DB 通知記録とメール送信を同時に行う便利関数。"""
    await create_notification(
        corporate_id=corporate_id,
        notification_type=notification_type,
        recipient_employee_id=recipient_employee_id,
        recipient_email=recipient_email,
        related_document_type=related_document_type,
        related_document_id=related_document_id,
        message=message,
    )
    if recipient_email:
        subject = f"【Tax-Agent】{message[:30]}..."
        await send_email_notification(
            recipient_email=recipient_email,
            subject=subject,
            body=message,
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
