"""
Tests for Task#47: email_service.py

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_email_service.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.services.email_service import (
    _send,
    send_invitation_email,
    send_linkage_approved_email,
    send_tax_advisor_notification_email,
    send_alert_notification_email,
)
from app.core.config import settings


# ──────────────────────────────────────────────────────────────────────────────
# _send: 基本動作
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_skips_when_api_key_not_set(caplog):
    """SENDGRID_API_KEY 未設定時は送信をスキップして False を返す。"""
    import logging
    original = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = ""
    try:
        with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
            result = await _send("user@example.com", "テスト件名", "<p>本文</p>")
        assert result is False
        assert "SENDGRID_API_KEY not set" in caplog.text
    finally:
        settings.SENDGRID_API_KEY = original


@pytest.mark.asyncio
async def test_send_returns_false_for_empty_email():
    """to_email が空文字の場合は False を返す。"""
    original = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = "test_key"
    try:
        result = await _send("", "件名", "<p>本文</p>")
        assert result is False
    finally:
        settings.SENDGRID_API_KEY = original


@pytest.mark.asyncio
async def test_send_succeeds_with_valid_key():
    """SENDGRID_API_KEY が設定されている場合、sendgrid を呼び出して True を返す。"""
    original_key = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = "SG.test_key"

    mock_response = MagicMock()
    mock_response.status_code = 202

    mock_post = MagicMock(return_value=mock_response)
    mock_sg_instance = MagicMock()
    mock_sg_instance.client.mail.send.post = mock_post

    mock_mail_cls = MagicMock()
    mock_mail_cls.return_value.get.return_value = {}

    try:
        with patch("app.services.email_service.asyncio.to_thread", new=AsyncMock(return_value=mock_response)) as mock_thread:
            with patch.dict("sys.modules", {
                "sendgrid": MagicMock(SendGridAPIClient=MagicMock(return_value=mock_sg_instance)),
                "sendgrid.helpers.mail": MagicMock(Mail=mock_mail_cls),
            }):
                result = await _send("user@example.com", "テスト", "<p>本文</p>")
        assert result is True
        mock_thread.assert_called_once()
    finally:
        settings.SENDGRID_API_KEY = original_key


@pytest.mark.asyncio
async def test_send_returns_false_on_exception():
    """sendgrid 呼び出しで例外が発生した場合は False を返す（例外を外に漏らさない）。"""
    original_key = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = "SG.test_key"
    try:
        with patch("app.services.email_service.asyncio.to_thread", new=AsyncMock(side_effect=Exception("network error"))):
            with patch.dict("sys.modules", {
                "sendgrid": MagicMock(SendGridAPIClient=MagicMock()),
                "sendgrid.helpers.mail": MagicMock(Mail=MagicMock(return_value=MagicMock(get=MagicMock(return_value={})))),
            }):
                result = await _send("user@example.com", "件名", "<p>本文</p>")
        assert result is False
    finally:
        settings.SENDGRID_API_KEY = original_key


# ──────────────────────────────────────────────────────────────────────────────
# send_invitation_email: URL フォーマット確認
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_invitation_email_url_contains_token():
    """招待メールの本文に token を含む登録 URL が含まれる。"""
    settings.SENDGRID_API_KEY = ""  # スキップ扱いにする

    captured: dict = {}

    async def mock_send(to_email, subject, html_body):
        captured["to"] = to_email
        captured["subject"] = subject
        captured["body"] = html_body
        return False  # API key なしと同じ扱い

    with patch("app.services.email_service._send", side_effect=mock_send):
        await send_invitation_email(
            to_email="client@example.com",
            token="abc-token-123",
            tax_firm_name="テスト税理士法人",
        )

    assert "abc-token-123" in captured["body"]
    assert "/register/corporate?token=abc-token-123" in captured["body"]
    assert "テスト税理士法人" in captured["subject"]


# ──────────────────────────────────────────────────────────────────────────────
# send_linkage_approved_email: 件名と法人名
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_linkage_approved_email_subject_and_name():
    """紐付け承認メールの件名に定型文が含まれ、本文に税理士法人名が入る。"""
    captured: dict = {}

    async def mock_send(to_email, subject, html_body):
        captured["to"] = to_email
        captured["subject"] = subject
        captured["body"] = html_body
        return True

    with patch("app.services.email_service._send", side_effect=mock_send):
        await send_linkage_approved_email(
            to_email="corp@example.com",
            tax_firm_name="サンプル税理士事務所",
        )

    assert "連携が完了" in captured["subject"]
    assert "サンプル税理士事務所" in captured["body"]
    assert captured["to"] == "corp@example.com"


# ──────────────────────────────────────────────────────────────────────────────
# send_tax_advisor_notification_email: メッセージ本文
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_tax_advisor_notification_email_contains_message():
    """税理士通知メールの本文にメッセージと法人名が含まれる。"""
    captured: dict = {}

    async def mock_send(to_email, subject, html_body):
        captured["to"] = to_email
        captured["subject"] = subject
        captured["body"] = html_body
        return True

    with patch("app.services.email_service._send", side_effect=mock_send):
        await send_tax_advisor_notification_email(
            to_email="taxfirm@example.com",
            message="消費税の確認をお願いします",
            corporate_name="株式会社テスト",
        )

    assert "消費税の確認をお願いします" in captured["body"]
    assert "株式会社テスト" in captured["subject"]
    assert captured["to"] == "taxfirm@example.com"


# ──────────────────────────────────────────────────────────────────────────────
# send_alert_notification_email: アラート内容
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_alert_notification_email_contains_message():
    """アラートメールの本文にアラートメッセージが含まれる。"""
    captured: dict = {}

    async def mock_send(to_email, subject, html_body):
        captured["body"] = html_body
        captured["subject"] = subject
        return True

    with patch("app.services.email_service._send", side_effect=mock_send):
        await send_alert_notification_email(
            to_email="employee@example.com",
            message="差し戻しされた領収書が3日以上放置されています。",
        )

    assert "差し戻しされた領収書" in captured["body"]
    assert "アラート" in captured["subject"]
