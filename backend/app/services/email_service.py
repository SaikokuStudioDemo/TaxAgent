"""
Email Service — SendGrid integration.

All public functions return bool (True=success/skipped, False=failed).
If SENDGRID_API_KEY is not configured, sending is skipped and a warning is logged.
The blocking SendGrid SDK call is wrapped in asyncio.to_thread() to avoid
blocking the async event loop.
"""
import asyncio
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


async def _send(to_email: str, subject: str, html_body: str) -> bool:
    """Internal: send one email via SendGrid. Silently skips if API key is absent."""
    if not to_email:
        return False
    if not settings.SENDGRID_API_KEY:
        logger.warning(
            "[Email] SENDGRID_API_KEY not set — skipping send to %s: %s",
            to_email,
            subject,
        )
        return False

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        message = Mail(
            from_email=settings.SENDGRID_FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html_body,
        )
        sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        response = await asyncio.to_thread(
            sg.client.mail.send.post, request_body=message.get()
        )
        logger.info(
            "[Email] Sent to %s: %s (status=%s)",
            to_email,
            subject,
            response.status_code,
        )
        return True
    except Exception as exc:
        logger.error("[Email] Failed to send to %s: %s", to_email, exc)
        return False


async def send_invitation_email(
    to_email: str,
    token: str,
    tax_firm_name: str,
) -> bool:
    """税理士法人からの招待メールを送信する。"""
    invite_url = f"{settings.APP_BASE_URL}/register/corporate?token={token}"
    subject = f"【Tax Agent】{tax_firm_name}からのご招待"
    html_body = f"""
<p>{tax_firm_name} から Tax Agent へのご招待が届きました。</p>
<p>下記リンクから法人登録を行ってください（有効期限：7日間）。</p>
<p><a href="{invite_url}">{invite_url}</a></p>
"""
    return await _send(to_email, subject, html_body)


async def send_linkage_approved_email(
    to_email: str,
    tax_firm_name: str,
) -> bool:
    """紐付け承認メールを法人（申請者）に送信する。"""
    subject = "【Tax Agent】税理士法人との連携が完了しました"
    html_body = f"""
<p>{tax_firm_name} との連携が完了しました。</p>
<p>Tax Agent にログインして書類管理を開始してください。</p>
"""
    return await _send(to_email, subject, html_body)


async def send_tax_advisor_notification_email(
    to_email: str,
    message: str,
    corporate_name: str,
) -> bool:
    """法人から税理士へのメッセージ通知メールを送信する。"""
    subject = f"【Tax Agent】{corporate_name} からメッセージが届きました"
    html_body = f"""
<p>{corporate_name} からメッセージが届きました：</p>
<blockquote style="border-left:4px solid #e5e7eb;padding:8px 16px;color:#374151;">
  <p>{message}</p>
</blockquote>
<p>Tax Agent にログインして詳細をご確認ください。</p>
"""
    return await _send(to_email, subject, html_body)


async def send_alert_notification_email(
    to_email: str,
    message: str,
) -> bool:
    """アラート通知メールを担当者に送信する。"""
    subject = "【Tax Agent】アラート通知"
    html_body = f"""
<p>以下のアラートが発生しました：</p>
<p style="color:#b45309;">{message}</p>
<p>Tax Agent にログインして対応してください。</p>
"""
    return await _send(to_email, subject, html_body)
