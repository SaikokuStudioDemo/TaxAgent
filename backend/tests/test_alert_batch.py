"""
Tests for Task#22・#23: アラートバッチ処理

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_alert_batch.py -v
"""
import pytest
import logging
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

CORP_A_ID = str(ObjectId())
CORP_B_ID = str(ObjectId())


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_col(find_one=None, find_data=None, distinct_data=None, count=0):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.count_documents = AsyncMock(return_value=count)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    col.distinct = AsyncMock(return_value=distinct_data or [])
    return col


def build_mock_db(collections: dict):
    """任意のコレクションマップから DB モックを生成する。"""
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


def old_doc(days: int, corporate_id: str, **extra) -> dict:
    """N日前に作成・更新されたドキュメントを返す。"""
    ts = datetime.utcnow() - timedelta(days=days)
    return {"_id": ObjectId(), "corporate_id": corporate_id, "created_at": ts, **extra}


# ─────────────────────────────────────────────────────────────────────────────
# test_rejected_stale_alert_generated
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejected_stale_alert_generated():
    """approval_status='rejected' かつ N日以上前のドキュメントに通知が生成されること。"""
    doc = old_doc(
        days=4,
        corporate_id=CORP_A_ID,
        approval_status="rejected",
        amount=3000,
        submitted_by=str(ObjectId()),
    )
    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    invoices_col = make_col(distinct_data=[])
    employees_col = make_col(find_one={"_id": ObjectId(), "email": "user@example.com"})
    alerts_config_col = make_col(find_one=None)  # デフォルト閾値を使う

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "employees": employees_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:

        from app.services.alert_service import check_rejected_stale_alerts
        result = await check_rejected_stale_alerts()

    assert result["rejected_stale"] == 1
    mock_notif.assert_called_once()
    call_kwargs = mock_notif.call_args.kwargs
    assert call_kwargs["notification_type"] == "rejected_stale_alert"
    assert call_kwargs["corporate_id"] == CORP_A_ID
    # update_one でフラグが立てられること
    receipts_col.update_one.assert_called_once()
    update_arg = receipts_col.update_one.call_args[0][1]
    assert update_arg["$set"]["rejected_stale_alerted"] is True


# ─────────────────────────────────────────────────────────────────────────────
# test_rejected_stale_alert_not_duplicate
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejected_stale_alert_not_duplicate():
    """rejected_stale_alerted=True のドキュメントには通知が生成されないこと。"""
    # フィルタが "$ne": True なので、alerted 済みは find に返らない想定
    receipts_col = make_col(find_data=[], distinct_data=[CORP_A_ID])
    invoices_col = make_col(distinct_data=[])
    alerts_config_col = make_col(find_one=None)

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:

        from app.services.alert_service import check_rejected_stale_alerts
        result = await check_rejected_stale_alerts()

    assert result["rejected_stale"] == 0
    mock_notif.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# test_no_attachment_alert_generated
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_attachment_alert_generated():
    """file_url が空で N日以上前のドキュメントに通知が生成されること。"""
    doc = old_doc(
        days=4,
        corporate_id=CORP_A_ID,
        approval_status="pending_approval",
        file_url="",
        submitted_by=str(ObjectId()),
    )
    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    employees_col = make_col(find_one={"_id": ObjectId(), "email": "user@example.com"})
    alerts_config_col = make_col(find_one=None)

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "employees": employees_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:

        from app.services.alert_service import check_no_attachment_alerts
        result = await check_no_attachment_alerts()

    assert result["no_attachment"] == 1
    mock_notif.assert_called_once()
    call_kwargs = mock_notif.call_args.kwargs
    assert call_kwargs["notification_type"] == "no_attachment_alert"
    receipts_col.update_one.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# test_unreconciled_alert_generated
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unreconciled_alert_generated():
    """approved かつ unreconciled で N日以上のドキュメントに通知が生成されること。"""
    doc = old_doc(
        days=8,
        corporate_id=CORP_A_ID,
        approval_status="approved",
        reconciliation_status="unreconciled",
        amount=5000,
    )
    accountant = {"_id": ObjectId(), "email": "accountant@example.com", "role": "accounting"}
    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    invoices_col = make_col(find_data=[], distinct_data=[])
    employees_col = make_col(find_one=accountant)
    alerts_config_col = make_col(find_one=None)

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "employees": employees_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:

        from app.services.alert_service import check_unreconciled_alerts
        result = await check_unreconciled_alerts()

    assert result["unreconciled"] == 1
    mock_notif.assert_called_once()
    call_kwargs = mock_notif.call_args.kwargs
    assert call_kwargs["notification_type"] == "unreconciled_alert"
    assert call_kwargs["recipient_email"] == "accountant@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# test_approval_delay_alert_generated
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approval_delay_alert_generated():
    """pending_approval のまま N日以上のドキュメントに通知が生成されること。"""
    doc = old_doc(
        days=4,
        corporate_id=CORP_A_ID,
        approval_status="pending_approval",
        amount=2000,
        approval_rule_id=None,  # ルールなし → approver_id は空
    )
    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    invoices_col = make_col(find_data=[], distinct_data=[])
    alerts_config_col = make_col(find_one=None)

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:

        from app.services.alert_service import check_approval_delay_alerts
        result = await check_approval_delay_alerts()

    assert result["approval_delay"] == 1
    mock_notif.assert_called_once()
    call_kwargs = mock_notif.call_args.kwargs
    assert call_kwargs["notification_type"] == "approval_delay_alert"


# ─────────────────────────────────────────────────────────────────────────────
# test_approval_delay_notifies_correct_approver  ⑦ 2段階モック
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approval_delay_notifies_correct_approver():
    """現在の承認ステップの担当ロールの従業員に通知が届くこと。"""
    rule_id = str(ObjectId())
    approver = {
        "_id": ObjectId(),
        "corporate_id": CORP_A_ID,
        "role": "manager",
        "email": "manager@example.com",
    }
    rule_doc = {
        "_id": ObjectId(rule_id),
        "steps": [{"step": 1, "role": "manager", "required": True}],
    }
    doc = old_doc(
        days=4,
        corporate_id=CORP_A_ID,
        approval_status="pending_approval",
        approval_rule_id=rule_id,
        current_step=1,
        amount=10000,
    )

    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    invoices_col = make_col(find_data=[], distinct_data=[])
    alerts_config_col = make_col(find_one=None)

    # ⑦ approval_rules → employees の2段階モック
    approval_rules_col = make_col(find_one=rule_doc)
    employees_col = make_col(find_one=approver)

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "alerts_config": alerts_config_col,
        "approval_rules": approval_rules_col,
        "employees": employees_col,
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:

        from app.services.alert_service import check_approval_delay_alerts
        result = await check_approval_delay_alerts()

    assert result["approval_delay"] == 1
    mock_notif.assert_called_once()
    call_kwargs = mock_notif.call_args.kwargs
    assert call_kwargs["recipient_email"] == "manager@example.com"
    assert call_kwargs["recipient_employee_id"] == str(approver["_id"])


# ─────────────────────────────────────────────────────────────────────────────
# test_run_all_alerts_returns_all_counts
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_all_alerts_returns_all_counts():
    """run_all_alerts() が6種全てのカウントキーを返すこと。"""
    empty_col = make_col(find_data=[], distinct_data=[])

    mock_db = build_mock_db({
        "receipts": empty_col,
        "invoices": empty_col,
        "employees": make_col(),
        "alerts_config": make_col(find_one=None),
        "approval_rules": make_col(),
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock):

        from app.services.alert_service import run_all_alerts
        result = await run_all_alerts()

    expected_keys = {
        "overdue", "due_soon",
        "high_amount_flagged",
        "rejected_stale",
        "no_attachment",
        "unreconciled",
        "approval_delay",
    }
    assert expected_keys == set(result.keys()), f"不足キー: {expected_keys - set(result.keys())}"


# ─────────────────────────────────────────────────────────────────────────────
# test_custom_threshold_respected  ⑥ alerts_config モック
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_custom_threshold_respected():
    """alerts_config に rejected_stale_days=1 を設定した場合、1日後からアラートが発生すること。"""
    # 1.5日前に差し戻されたドキュメント（デフォルト3日では対象外、カスタム1日では対象）
    doc = old_doc(
        days=2,  # 2日前 → カスタム1日閾値では対象
        corporate_id=CORP_A_ID,
        approval_status="rejected",
        amount=1000,
        submitted_by=str(ObjectId()),
    )

    # ⑥ alerts_config コレクションのモック（rejected_stale_days=1）
    custom_config = {
        "_id": ObjectId(),
        "corporate_id": CORP_A_ID,
        "rejected_stale_days": 1,
    }
    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    invoices_col = make_col(distinct_data=[])
    employees_col = make_col(find_one={"_id": ObjectId(), "email": "u@example.com"})
    alerts_config_col = make_col(find_one=custom_config)

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "employees": employees_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:

        from app.services.alert_service import check_rejected_stale_alerts
        result = await check_rejected_stale_alerts()

    # カスタム閾値1日が有効 → 2日前のドキュメントはアラート対象
    assert result["rejected_stale"] == 1
    mock_notif.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# test_email_placeholder_logs_not_sends
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_placeholder_logs_not_sends(caplog):
    """send_email_notification がログ出力のみで実際の送信を行わないこと。"""
    from app.services.notification_service import send_email_notification

    with caplog.at_level(logging.INFO, logger="app.services.notification_service"):
        result = await send_email_notification(
            recipient_email="test@example.com",
            subject="テスト件名",
            body="テスト本文",
        )

    assert result is True
    assert "[EMAIL PLACEHOLDER]" in caplog.text
    assert "test@example.com" in caplog.text


@pytest.mark.asyncio
async def test_email_placeholder_empty_email():
    """recipient_email が空の場合は False を返すこと。"""
    from app.services.notification_service import send_email_notification

    result = await send_email_notification(
        recipient_email="",
        subject="件名",
        body="本文",
    )
    assert result is False


# =============================================================================
# 意地悪テスト（Task#22・#23）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① 重複通知防止テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejected_stale_alert_not_regenerated_after_flag():
    """
    rejected_stale_alerted=True のドキュメントに対して
    check_rejected_stale_alerts() を2回呼んでも通知が1件しか生成されないこと。
    モックの find が 1回目のみドキュメントを返し、2回目は空を返すことで
    フィルタ（$ne: True）が機能していることを確認する。
    """
    doc = old_doc(days=4, corporate_id=CORP_A_ID, approval_status="rejected", amount=1000,
                  submitted_by=str(ObjectId()))

    # 1回目: ドキュメントあり → 2回目: alerted フラグ付きなので返さない（空）
    call_count = {"n": 0}
    def find_side_effect(query):
        call_count["n"] += 1
        return make_cursor([doc] if call_count["n"] == 1 else [])

    receipts_col = make_col(distinct_data=[CORP_A_ID])
    receipts_col.find = MagicMock(side_effect=find_side_effect)
    receipts_col.update_one = AsyncMock(return_value=MagicMock())

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": make_col(distinct_data=[]),
        "employees": make_col(find_one={"_id": ObjectId(), "email": "u@example.com"}),
        "alerts_config": make_col(find_one=None),
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_rejected_stale_alerts
        result1 = await check_rejected_stale_alerts()
        result2 = await check_rejected_stale_alerts()

    assert result1["rejected_stale"] == 1
    assert result2["rejected_stale"] == 0
    assert mock_notif.call_count == 1


@pytest.mark.asyncio
async def test_no_attachment_alert_not_duplicate():
    """no_attachment_alerted=True のドキュメントに対して重複通知が生成されないこと。"""
    receipts_col = make_col(find_data=[], distinct_data=[CORP_A_ID])
    mock_db = build_mock_db({
        "receipts": receipts_col,
        "alerts_config": make_col(find_one=None),
    })
    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_no_attachment_alerts
        result = await check_no_attachment_alerts()

    assert result["no_attachment"] == 0
    mock_notif.assert_not_called()


@pytest.mark.asyncio
async def test_unreconciled_alert_not_duplicate():
    """unreconciled_alerted=True のドキュメントに対して重複通知が生成されないこと。"""
    receipts_col = make_col(find_data=[], distinct_data=[CORP_A_ID])
    invoices_col = make_col(find_data=[], distinct_data=[])
    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "employees": make_col(find_one=None),
        "alerts_config": make_col(find_one=None),
    })
    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_unreconciled_alerts
        result = await check_unreconciled_alerts()

    assert result["unreconciled"] == 0
    mock_notif.assert_not_called()


@pytest.mark.asyncio
async def test_approval_delay_alert_not_duplicate():
    """approval_delay_alerted=True のドキュメントに対して重複通知が生成されないこと。"""
    receipts_col = make_col(find_data=[], distinct_data=[CORP_A_ID])
    invoices_col = make_col(find_data=[], distinct_data=[])
    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "alerts_config": make_col(find_one=None),
    })
    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_approval_delay_alerts
        result = await check_approval_delay_alerts()

    assert result["approval_delay"] == 0
    mock_notif.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# ② 閾値境界値テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejected_stale_exactly_at_threshold():
    """
    updated_at がちょうど N日前のドキュメントがアラート対象になること（境界値・含む）。
    デフォルト閾値 rejected_stale_days=3 に対して、ちょうど3日前を渡す。
    """
    doc = old_doc(days=3, corporate_id=CORP_A_ID, approval_status="rejected",
                  amount=500, submitted_by=str(ObjectId()))
    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": make_col(distinct_data=[]),
        "employees": make_col(find_one={"_id": ObjectId(), "email": "u@example.com"}),
        "alerts_config": make_col(find_one=None),
    })
    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_rejected_stale_alerts
        result = await check_rejected_stale_alerts()

    assert result["rejected_stale"] == 1
    mock_notif.assert_called_once()


@pytest.mark.asyncio
async def test_rejected_stale_before_threshold_no_alert():
    """
    updated_at が N-1日前のドキュメントがアラート対象にならないこと。
    モックの find が空を返すことで、クエリ時点でフィルタ済みであることを表現する。
    """
    # N-1日前（2日前）のドキュメントはクエリで除外される想定
    receipts_col = make_col(find_data=[], distinct_data=[CORP_A_ID])
    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": make_col(distinct_data=[]),
        "alerts_config": make_col(find_one=None),
    })
    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_rejected_stale_alerts
        result = await check_rejected_stale_alerts()

    assert result["rejected_stale"] == 0
    mock_notif.assert_not_called()


@pytest.mark.asyncio
async def test_custom_threshold_zero_days():
    """
    alerts_config に rejected_stale_days=0 を設定した場合に
    当日更新（0日前）のドキュメントもアラート対象になること。
    """
    doc = old_doc(days=0, corporate_id=CORP_A_ID, approval_status="rejected",
                  amount=100, submitted_by=str(ObjectId()))
    custom_config = {"_id": ObjectId(), "corporate_id": CORP_A_ID, "rejected_stale_days": 0}
    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": make_col(distinct_data=[]),
        "employees": make_col(find_one={"_id": ObjectId(), "email": "u@example.com"}),
        "alerts_config": make_col(find_one=custom_config),
    })
    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_rejected_stale_alerts
        result = await check_rejected_stale_alerts()

    assert result["rejected_stale"] == 1
    mock_notif.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# ③ created_at フォールバックテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_filter_uses_created_at_when_no_updated_at():
    """
    updated_at フィールドが存在しないドキュメントで
    created_at が N日以上前の場合にアラートが生成されること（フォールバック確認）。
    old_doc() は updated_at を持たない（created_at のみ）ため、そのまま使える。
    """
    doc = old_doc(days=4, corporate_id=CORP_A_ID, approval_status="rejected",
                  amount=800, submitted_by=str(ObjectId()))
    assert "updated_at" not in doc  # updated_at が存在しないことを確認

    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": make_col(distinct_data=[]),
        "employees": make_col(find_one={"_id": ObjectId(), "email": "u@example.com"}),
        "alerts_config": make_col(find_one=None),
    })
    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_rejected_stale_alerts
        result = await check_rejected_stale_alerts()

    assert result["rejected_stale"] == 1
    mock_notif.assert_called_once()


@pytest.mark.asyncio
async def test_stale_filter_ignores_recent_created_at():
    """
    updated_at が存在せず created_at が N-1日前の場合にアラートが生成されないこと。
    モックが空リストを返すことでクエリ条件が機能していることを確認。
    """
    receipts_col = make_col(find_data=[], distinct_data=[CORP_A_ID])
    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": make_col(distinct_data=[]),
        "alerts_config": make_col(find_one=None),
    })
    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_rejected_stale_alerts
        result = await check_rejected_stale_alerts()

    assert result["rejected_stale"] == 0
    mock_notif.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# ④ N+1クエリ防止テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unreconciled_alert_accountant_fetched_once_per_corporate():
    """
    同一法人に未消込ドキュメントが3件ある場合に
    employees への find_one が1回だけ呼ばれること（N+1クエリ防止）。
    """
    docs = [
        old_doc(days=8, corporate_id=CORP_A_ID, approval_status="approved",
                reconciliation_status="unreconciled", amount=1000 * i)
        for i in range(1, 4)  # 3件
    ]
    accountant = {"_id": ObjectId(), "email": "accountant@example.com", "role": "accounting"}

    receipts_col = make_col(find_data=docs, distinct_data=[CORP_A_ID])
    invoices_col = make_col(find_data=[], distinct_data=[])
    employees_col = make_col(find_one=accountant)
    alerts_config_col = make_col(find_one=None)

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "employees": employees_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_unreconciled_alerts
        result = await check_unreconciled_alerts()

    assert result["unreconciled"] == 3
    assert mock_notif.call_count == 3
    # employees.find_one はループの外で1回だけ呼ばれること（N+1でないこと）
    assert employees_col.find_one.call_count == 1, (
        f"find_one が {employees_col.find_one.call_count} 回呼ばれた（期待値: 1回）"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ エラー耐性テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approval_delay_missing_rule_no_crash():
    """
    approval_rule_id が存在しない ID を参照していてもクラッシュしないこと。
    通知は recipient_employee_id="" で生成されること。
    """
    doc = old_doc(days=4, corporate_id=CORP_A_ID, approval_status="pending_approval",
                  approval_rule_id=str(ObjectId()), current_step=1, amount=3000)

    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    invoices_col = make_col(find_data=[], distinct_data=[])
    # approval_rules.find_one が None を返す（ルール不在）
    approval_rules_col = make_col(find_one=None)
    alerts_config_col = make_col(find_one=None)

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "approval_rules": approval_rules_col,
        "employees": make_col(find_one=None),
        "alerts_config": alerts_config_col,
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_approval_delay_alerts
        result = await check_approval_delay_alerts()  # クラッシュしないこと

    assert result["approval_delay"] == 1
    mock_notif.assert_called_once()
    assert mock_notif.call_args.kwargs["recipient_employee_id"] == ""


@pytest.mark.asyncio
async def test_approval_delay_missing_step_no_crash():
    """
    approval_rules に current_step に対応するステップが存在しない場合でもクラッシュしないこと。
    """
    rule_id = str(ObjectId())
    rule_doc = {"_id": ObjectId(rule_id), "steps": [{"step": 99, "role": "manager"}]}  # step=1 がない
    doc = old_doc(days=4, corporate_id=CORP_A_ID, approval_status="pending_approval",
                  approval_rule_id=rule_id, current_step=1, amount=2000)

    receipts_col = make_col(find_data=[doc], distinct_data=[CORP_A_ID])
    invoices_col = make_col(find_data=[], distinct_data=[])
    approval_rules_col = make_col(find_one=rule_doc)
    alerts_config_col = make_col(find_one=None)

    mock_db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "approval_rules": approval_rules_col,
        "employees": make_col(find_one=None),
        "alerts_config": alerts_config_col,
    })

    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock) as mock_notif:
        from app.services.alert_service import check_approval_delay_alerts
        result = await check_approval_delay_alerts()  # クラッシュしないこと

    assert result["approval_delay"] == 1
    assert mock_notif.call_args.kwargs["recipient_employee_id"] == ""


@pytest.mark.asyncio
async def test_get_employee_email_invalid_id_returns_empty():
    """_get_employee_email に不正な ID を渡しても空文字が返ること・例外が漏れないこと。"""
    from app.services.alert_service import _get_employee_email

    mock_db = build_mock_db({"employees": make_col(find_one=None)})

    for bad_id in ["invalid-id", "", "abc", "123", "!@#$%"]:
        result = await _get_employee_email(mock_db, bad_id)
        assert result == "", f"bad_id={bad_id!r} で空文字以外が返った: {result!r}"


@pytest.mark.asyncio
async def test_get_alert_thresholds_partial_config():
    """
    alerts_config に一部のキーしかない場合に
    未設定のキーはデフォルト値、設定済みのキーはカスタム値が使われること。
    """
    from app.services.alert_service import get_alert_thresholds, DEFAULT_THRESHOLDS

    partial_config = {
        "_id": ObjectId(),
        "corporate_id": CORP_A_ID,
        "rejected_stale_days": 1,   # カスタム値
        # unreconciled_days は未設定 → デフォルトの 7 が使われること
    }
    mock_db = build_mock_db({"alerts_config": make_col(find_one=partial_config)})

    with patch("app.services.alert_service.get_database", return_value=mock_db):
        thresholds = await get_alert_thresholds(CORP_A_ID)

    assert thresholds["rejected_stale_days"] == 1, "カスタム値が反映されていない"
    assert thresholds["unreconciled_days"] == DEFAULT_THRESHOLDS["unreconciled_days"], \
        "未設定キーにデフォルト値が使われていない"
    assert thresholds["approval_delay_days"] == DEFAULT_THRESHOLDS["approval_delay_days"]


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ run_all_alerts 統合テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_all_alerts_returns_all_6_keys():
    """run_all_alerts() の戻り値に7種全てのキーが含まれること。"""
    empty_col = make_col(find_data=[], distinct_data=[])
    mock_db = build_mock_db({
        "receipts": empty_col,
        "invoices": empty_col,
        "employees": make_col(find_one=None),
        "alerts_config": make_col(find_one=None),
        "approval_rules": make_col(find_one=None),
    })
    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock):
        from app.services.alert_service import run_all_alerts
        result = await run_all_alerts()

    expected_keys = {
        "overdue", "due_soon", "high_amount_flagged",
        "rejected_stale", "no_attachment", "unreconciled", "approval_delay",
    }
    missing = expected_keys - set(result.keys())
    assert not missing, f"不足キー: {missing}"


@pytest.mark.asyncio
async def test_run_all_alerts_zero_when_no_data():
    """DBが空の状態で run_all_alerts() を呼んでもクラッシュせず全カウント0であること。"""
    empty_col = make_col(find_data=[], distinct_data=[])
    mock_db = build_mock_db({
        "receipts": empty_col,
        "invoices": empty_col,
        "employees": make_col(find_one=None),
        "alerts_config": make_col(find_one=None),
        "approval_rules": make_col(find_one=None),
    })
    with patch("app.services.alert_service.get_database", return_value=mock_db), \
         patch("app.services.alert_service.create_notification", new_callable=AsyncMock):
        from app.services.alert_service import run_all_alerts
        result = await run_all_alerts()

    for key, val in result.items():
        assert val == 0, f"key={key} の値が 0 でない: {val}"


# ─────────────────────────────────────────────────────────────────────────────
# ⑦ メール送信プレースホルダーテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_email_empty_recipient_returns_false():
    """recipient_email="" の場合に False が返ること（送信しない）。"""
    from app.services.notification_service import send_email_notification

    result = await send_email_notification(recipient_email="", subject="件名", body="本文")
    assert result is False


@pytest.mark.asyncio
async def test_create_notification_with_email_calls_both():
    """
    create_notification_with_email を呼んだ時に
    DB への記録（create_notification）と send_email_notification の両方が呼ばれること。
    """
    from app.services import notification_service

    with patch.object(notification_service, "create_notification", new_callable=AsyncMock) as mock_create, \
         patch.object(notification_service, "send_email_notification", new_callable=AsyncMock, return_value=True) as mock_send:

        await notification_service.create_notification_with_email(
            corporate_id=CORP_A_ID,
            notification_type="test_alert",
            recipient_employee_id=str(ObjectId()),
            recipient_email="test@example.com",
            related_document_type="receipt",
            related_document_id=str(ObjectId()),
            message="テスト通知メッセージ",
        )

    mock_create.assert_called_once()
    mock_send.assert_called_once()
    send_kwargs = mock_send.call_args.kwargs
    assert send_kwargs["recipient_email"] == "test@example.com"
    assert "テスト通知メッセージ" in send_kwargs["body"]
