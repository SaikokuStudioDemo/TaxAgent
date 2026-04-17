"""
Tests for Task#17-C: 実行系エージェントツール

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_agent_tools_exec.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime

CORP_ID = str(ObjectId())
USER_ID = str(ObjectId())
CORP_B_ID = str(ObjectId())


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_col(find_one=None, find_data=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=find_data or [])))
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return col


def build_mock_db(collections: dict = None):
    db = MagicMock()
    cols = collections or {}
    db.__getitem__ = MagicMock(side_effect=lambda k: cols.get(k, make_col()))
    return db


# ─────────────────────────────────────────────────────────────────────────────
# test_submit_expense_claim_confirmation_required
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_expense_claim_confirmation_required():
    """confirmed=False で confirmation_required=True が返ること。"""
    from app.services.agent_tools import exec_submit_expense_claim

    result = await exec_submit_expense_claim(
        corporate_id=CORP_ID, user_id=USER_ID,
        date="2025-04-01", amount=5000, payee="テスト商店",
        category="消耗品費", payment_method="現金", confirmed=False,
    )

    assert result["confirmation_required"] is True
    assert "5,000" in result["message"]
    assert result["tool_name"] == "submit_expense_claim"


# ─────────────────────────────────────────────────────────────────────────────
# test_submit_expense_claim_executes_when_confirmed
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_expense_claim_executes_when_confirmed():
    """confirmed=True で receipts に登録されること。"""
    from app.services.agent_tools import exec_submit_expense_claim

    receipts_col = make_col(find_one=None)
    mock_db = build_mock_db({"receipts": receipts_col})

    with patch("app.services.agent_tools.get_database", return_value=mock_db), \
         patch("app.services.rule_evaluation_service.evaluate_approval_rules",
               new_callable=AsyncMock, return_value=(None, [])):
        result = await exec_submit_expense_claim(
            corporate_id=CORP_ID, user_id=USER_ID,
            date="2025-04-01", amount=5000, payee="テスト商店",
            category="消耗品費", payment_method="現金", confirmed=True,
        )

    assert result.get("success") is True
    assert "receipt_id" in result
    receipts_col.insert_one.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# test_approve_document_rejected_requires_comment
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_document_rejected_requires_comment():
    """action='rejected' かつ comment なしで HTTPException(400) が返ること。"""
    from fastapi import HTTPException
    from app.services.agent_tools import exec_approve_document

    with pytest.raises(HTTPException) as exc:
        await exec_approve_document(
            corporate_id=CORP_ID, user_id=USER_ID,
            document_type="receipt", document_id=str(ObjectId()),
            action="rejected", comment=None, confirmed=True,
        )

    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# test_approve_document_confirmed
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_document_confirmed():
    """confirmed=True で approval_status が更新されること。"""
    from app.services.agent_tools import exec_approve_document

    doc = {
        "_id": ObjectId(), "corporate_id": CORP_ID,
        "amount": 3000, "approval_status": "pending_approval",
    }
    receipts_col = make_col(find_one=doc)
    audit_col = make_col()
    mock_db = build_mock_db({"receipts": receipts_col, "audit_logs": audit_col})

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_approve_document(
            corporate_id=CORP_ID, user_id=USER_ID,
            document_type="receipt", document_id=str(doc["_id"]),
            action="approved", comment=None, confirmed=True,
        )

    assert result.get("success") is True
    receipts_col.update_one.assert_called_once()
    update_arg = receipts_col.update_one.call_args[0][1]
    assert update_arg["$set"]["approval_status"] == "approved"
    audit_col.insert_one.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# test_execute_reconciliation_confirmed
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_reconciliation_confirmed():
    """confirmed=True で matches コレクションに登録されること。"""
    from app.services.agent_tools import exec_execute_reconciliation

    tx_id = str(ObjectId())
    doc_id = str(ObjectId())
    tx_doc = {
        "_id": ObjectId(tx_id), "corporate_id": CORP_ID,
        "deposit_amount": 10000, "status": "unmatched",
    }
    matches_col = make_col()
    txs_col = make_col(find_one=tx_doc)
    receipts_col = make_col()
    mock_db = build_mock_db({
        "transactions": txs_col,
        "matches": matches_col,
        "receipts": receipts_col,
    })

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_execute_reconciliation(
            corporate_id=CORP_ID, user_id=USER_ID,
            transaction_ids=[tx_id], document_ids=[doc_id],
            match_type="receipt", confirmed=True,
        )

    assert result.get("success") is True
    matches_col.insert_one.assert_called_once()
    txs_col.update_one.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# test_notify_tax_advisor_no_tax_firm_returns_400
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_tax_advisor_no_tax_firm_returns_400():
    """advising_tax_firm_id がない法人が呼ぶと HTTPException(400) が返ること。"""
    from fastapi import HTTPException
    from app.services.agent_tools import exec_notify_tax_advisor

    corp_no_firm = {
        "_id": ObjectId(CORP_ID), "firebase_uid": "corp_uid",
        # advising_tax_firm_id なし
    }
    mock_db = build_mock_db({"corporates": make_col(find_one=corp_no_firm)})

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await exec_notify_tax_advisor(
                corporate_id=CORP_ID, user_id=USER_ID,
                message="相談したいことがあります。", confirmed=True,
            )

    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# test_notify_tax_advisor_confirmed
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_tax_advisor_confirmed():
    """confirmed=True で notifications に記録されること。"""
    from app.services.agent_tools import exec_notify_tax_advisor

    corp_with_firm = {
        "_id": ObjectId(CORP_ID),
        "advising_tax_firm_id": "tax_firm_uid",
    }
    notifications_col = make_col()
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_with_firm),
        "notifications": notifications_col,
    })

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_notify_tax_advisor(
            corporate_id=CORP_ID, user_id=USER_ID,
            message="確認をお願いします。", confirmed=True,
        )

    assert result.get("success") is True
    notifications_col.insert_one.assert_called_once()
    inserted = notifications_col.insert_one.call_args[0][0]
    assert inserted["notification_type"] == "tax_advisor_message"
    assert inserted["tax_firm_id"] == "tax_firm_uid"


# ─────────────────────────────────────────────────────────────────────────────
# test_export_csv_returns_download_url
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_csv_returns_download_url():
    """confirmed=True で download_url が返ること。"""
    from app.services.agent_tools import exec_export_csv

    result = await exec_export_csv(
        corporate_id=CORP_ID,
        format_type="freee",
        doc_type="all",
        fiscal_period="2025-04",
        confirmed=True,
    )

    assert result.get("success") is True
    assert "download_url" in result
    assert "freee" in result["download_url"]
    assert "2025-04" in result["download_url"]


# ─────────────────────────────────────────────────────────────────────────────
# test_tool_cross_corporate_blocked
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_cross_corporate_blocked():
    """別法人のドキュメントを操作しようとすると error が返ること。"""
    from app.services.agent_tools import exec_send_invoice

    # 法人Bの請求書（法人Aからは見えない）
    mock_db = build_mock_db({"invoices": make_col(find_one=None)})

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_send_invoice(
            corporate_id=CORP_ID,  # 法人A として
            user_id=USER_ID,
            invoice_id=str(ObjectId()),  # 法人Bの ID
            confirmed=True,
        )

    assert "error" in result, "別法人のドキュメントにアクセスできてはいけない"


# =============================================================================
# ① confirmed=false の確認テスト
# =============================================================================

@pytest.mark.asyncio
async def test_all_tools_return_confirmation_by_default():
    """全7ツールで confirmed を省略した場合に confirmation_required=True が返ること。"""
    from app.services.agent_tools import (
        exec_submit_expense_claim, exec_send_invoice, exec_approve_document,
        exec_execute_reconciliation, exec_export_csv, exec_export_zengin,
        exec_notify_tax_advisor,
    )

    inv_id = str(ObjectId())
    doc_id = str(ObjectId())
    tx_id = str(ObjectId())

    inv_doc = {
        "_id": ObjectId(inv_id), "corporate_id": CORP_ID,
        "document_type": "issued", "client_name": "A社", "total_amount": 50000,
    }
    receipt_doc = {
        "_id": ObjectId(doc_id), "corporate_id": CORP_ID,
        "amount": 3000, "approval_status": "pending_approval",
    }
    tx_doc = {
        "_id": ObjectId(tx_id), "corporate_id": CORP_ID,
        "deposit_amount": 10000, "status": "unmatched",
    }
    corp_doc = {"_id": ObjectId(CORP_ID), "advising_tax_firm_id": "firm_uid"}

    mock_db = build_mock_db({
        "invoices": make_col(find_one=inv_doc),
        "receipts": make_col(find_one=receipt_doc),
        "transactions": make_col(find_one=tx_doc),
        "corporates": make_col(find_one=corp_doc),
    })

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        r1 = await exec_submit_expense_claim(
            corporate_id=CORP_ID, user_id=USER_ID,
            date="2025-04-01", amount=5000, payee="テスト商店",
            category="消耗品費", payment_method="現金",
        )
        r2 = await exec_send_invoice(
            corporate_id=CORP_ID, user_id=USER_ID, invoice_id=inv_id,
        )
        r3 = await exec_approve_document(
            corporate_id=CORP_ID, user_id=USER_ID,
            document_type="receipt", document_id=doc_id, action="approved",
        )
        r4 = await exec_execute_reconciliation(
            corporate_id=CORP_ID, user_id=USER_ID,
            transaction_ids=[tx_id], document_ids=[doc_id],
            match_type="receipt",
        )
        r5 = await exec_export_csv(
            corporate_id=CORP_ID, format_type="freee", doc_type="all",
        )
        r6 = await exec_export_zengin(corporate_id=CORP_ID)
        r7 = await exec_notify_tax_advisor(
            corporate_id=CORP_ID, user_id=USER_ID,
            message="確認をお願いします。",
        )

    tool_names = [
        "submit_expense_claim", "send_invoice", "approve_document",
        "execute_reconciliation", "export_csv", "export_zengin", "notify_tax_advisor",
    ]
    for name, r in zip(tool_names, [r1, r2, r3, r4, r5, r6, r7]):
        assert r.get("confirmation_required") is True, \
            f"{name} が confirmation_required=True を返していない: {r}"


@pytest.mark.asyncio
async def test_confirmation_message_contains_key_info():
    """submit_expense_claim の確認メッセージに amount と payee が含まれること。"""
    from app.services.agent_tools import exec_submit_expense_claim

    result = await exec_submit_expense_claim(
        corporate_id=CORP_ID, user_id=USER_ID,
        date="2025-04-01", amount=12345, payee="テスト商店ABC",
        category="消耗品費", payment_method="現金",
    )

    assert result["confirmation_required"] is True
    assert "12,345" in result["message"]
    assert "テスト商店ABC" in result["message"]


@pytest.mark.asyncio
async def test_send_invoice_confirmation_contains_client_name():
    """send_invoice の確認メッセージに client_name と total_amount が含まれること。"""
    from app.services.agent_tools import exec_send_invoice

    inv_id = str(ObjectId())
    inv_doc = {
        "_id": ObjectId(inv_id), "corporate_id": CORP_ID,
        "document_type": "issued", "client_name": "株式会社テスト顧客",
        "total_amount": 55000,
    }
    mock_db = build_mock_db({"invoices": make_col(find_one=inv_doc)})

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_send_invoice(
            corporate_id=CORP_ID, user_id=USER_ID, invoice_id=inv_id,
        )

    assert result["confirmation_required"] is True
    assert "株式会社テスト顧客" in result["message"]
    assert "55,000" in result["message"]


# =============================================================================
# ② 二重実行防止テスト
# =============================================================================

@pytest.mark.asyncio
async def test_submit_expense_claim_not_duplicate_on_retry():
    """
    confirmed=True を2回呼んだ場合に receipts が2件登録されること。
    重複防止はフロント側の責任（ボタン disabled）であり、
    バックエンドは2件とも登録する仕様の確認。
    """
    from app.services.agent_tools import exec_submit_expense_claim

    receipts_col = make_col(find_one=None)
    mock_db = build_mock_db({"receipts": receipts_col})

    with patch("app.services.agent_tools.get_database", return_value=mock_db), \
         patch("app.services.rule_evaluation_service.evaluate_approval_rules",
               new_callable=AsyncMock, return_value=(None, [])):
        result1 = await exec_submit_expense_claim(
            corporate_id=CORP_ID, user_id=USER_ID,
            date="2025-04-01", amount=5000, payee="テスト商店",
            category="消耗品費", payment_method="現金", confirmed=True,
        )
        result2 = await exec_submit_expense_claim(
            corporate_id=CORP_ID, user_id=USER_ID,
            date="2025-04-01", amount=5000, payee="テスト商店",
            category="消耗品費", payment_method="現金", confirmed=True,
        )

    assert result1.get("success") is True
    assert result2.get("success") is True
    assert receipts_col.insert_one.call_count == 2, \
        "バックエンドは重複防止せず2件登録する仕様（フロントで制御）"


# =============================================================================
# ③ スコープテスト
# =============================================================================

@pytest.mark.asyncio
async def test_send_invoice_cross_corporate_blocked():
    """別法人の invoice_id を送付しようとすると error が返ること。"""
    from app.services.agent_tools import exec_send_invoice

    mock_db = build_mock_db({"invoices": make_col(find_one=None)})

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_send_invoice(
            corporate_id=CORP_ID,
            user_id=USER_ID,
            invoice_id=str(ObjectId()),
            confirmed=True,
        )

    assert "error" in result, "別法人の請求書にアクセスできてはいけない"


@pytest.mark.asyncio
async def test_approve_document_cross_corporate_blocked():
    """別法人のドキュメントを承認しようとすると error が返ること。"""
    from app.services.agent_tools import exec_approve_document

    mock_db = build_mock_db({"receipts": make_col(find_one=None)})

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_approve_document(
            corporate_id=CORP_ID,
            user_id=USER_ID,
            document_type="receipt",
            document_id=str(ObjectId()),
            action="approved",
            confirmed=True,
        )

    assert "error" in result, "別法人のドキュメントを承認できてはいけない"


@pytest.mark.asyncio
async def test_execute_reconciliation_cross_corporate_blocked():
    """別法人の transaction_id を使うと error が返ること。"""
    from app.services.agent_tools import exec_execute_reconciliation

    mock_db = build_mock_db({"transactions": make_col(find_one=None)})

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_execute_reconciliation(
            corporate_id=CORP_ID,
            user_id=USER_ID,
            transaction_ids=[str(ObjectId())],
            document_ids=[str(ObjectId())],
            match_type="receipt",
            confirmed=True,
        )

    assert "error" in result, "別法人のトランザクションにアクセスできてはいけない"


# =============================================================================
# ④ バリデーションテスト
# =============================================================================

@pytest.mark.asyncio
async def test_approve_document_rejected_no_comment_returns_400():
    """action='rejected' かつ comment=None で 400 が返ること。"""
    from fastapi import HTTPException
    from app.services.agent_tools import exec_approve_document

    with pytest.raises(HTTPException) as exc:
        await exec_approve_document(
            corporate_id=CORP_ID, user_id=USER_ID,
            document_type="receipt", document_id=str(ObjectId()),
            action="rejected", comment=None, confirmed=True,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_approve_document_rejected_empty_comment_returns_400():
    """action='rejected' かつ comment='' （空文字）でも 400 が返ること。"""
    from fastapi import HTTPException
    from app.services.agent_tools import exec_approve_document

    with pytest.raises(HTTPException) as exc:
        await exec_approve_document(
            corporate_id=CORP_ID, user_id=USER_ID,
            document_type="receipt", document_id=str(ObjectId()),
            action="rejected", comment="", confirmed=True,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_submit_expense_claim_negative_amount_rejected():
    """amount=-1 で 400 が返ること。"""
    from fastapi import HTTPException
    from app.services.agent_tools import exec_submit_expense_claim

    with pytest.raises(HTTPException) as exc:
        await exec_submit_expense_claim(
            corporate_id=CORP_ID, user_id=USER_ID,
            date="2025-04-01", amount=-1, payee="テスト商店",
            category="消耗品費", payment_method="現金", confirmed=False,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_submit_expense_claim_invalid_tax_rate():
    """tax_rate=5（0・8・10 以外）で 400 が返ること。"""
    from fastapi import HTTPException
    from app.services.agent_tools import exec_submit_expense_claim

    with pytest.raises(HTTPException) as exc:
        await exec_submit_expense_claim(
            corporate_id=CORP_ID, user_id=USER_ID,
            date="2025-04-01", amount=5000, payee="テスト商店",
            category="消耗品費", payment_method="現金",
            tax_rate=5, confirmed=False,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_notify_tax_advisor_empty_message_rejected():
    """message='' で 400 が返ること。"""
    from fastapi import HTTPException
    from app.services.agent_tools import exec_notify_tax_advisor

    with pytest.raises(HTTPException) as exc:
        await exec_notify_tax_advisor(
            corporate_id=CORP_ID, user_id=USER_ID,
            message="", confirmed=True,
        )

    assert exc.value.status_code == 400


# =============================================================================
# ⑤ notify_tax_advisor のテスト
# =============================================================================

@pytest.mark.asyncio
async def test_notify_tax_advisor_creates_notification():
    """confirmed=True で notifications に notification_type='tax_advisor_message' が記録されること。"""
    from app.services.agent_tools import exec_notify_tax_advisor

    corp_doc = {"_id": ObjectId(CORP_ID), "advising_tax_firm_id": "firm_uid_123"}
    notifications_col = make_col()
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_doc),
        "notifications": notifications_col,
    })

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_notify_tax_advisor(
            corporate_id=CORP_ID, user_id=USER_ID,
            message="月次確認をお願いします。", confirmed=True,
        )

    assert result.get("success") is True
    notifications_col.insert_one.assert_called_once()
    inserted = notifications_col.insert_one.call_args[0][0]
    assert inserted["notification_type"] == "tax_advisor_message"


@pytest.mark.asyncio
async def test_notify_tax_advisor_urgent_priority():
    """priority='urgent' で送信した場合に notifications に priority フィールドが記録されること。"""
    from app.services.agent_tools import exec_notify_tax_advisor

    corp_doc = {"_id": ObjectId(CORP_ID), "advising_tax_firm_id": "firm_uid"}
    notifications_col = make_col()
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_doc),
        "notifications": notifications_col,
    })

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_notify_tax_advisor(
            corporate_id=CORP_ID, user_id=USER_ID,
            message="至急ご確認ください。", priority="urgent", confirmed=True,
        )

    assert result.get("success") is True
    inserted = notifications_col.insert_one.call_args[0][0]
    assert inserted.get("priority") == "urgent"


@pytest.mark.asyncio
async def test_notify_tax_advisor_no_tax_firm_error_message():
    """advising_tax_firm_id がない法人が呼ぶと 400 かつエラーメッセージに「税理士」が含まれること。"""
    from fastapi import HTTPException
    from app.services.agent_tools import exec_notify_tax_advisor

    corp_no_firm = {"_id": ObjectId(CORP_ID)}  # advising_tax_firm_id なし
    mock_db = build_mock_db({"corporates": make_col(find_one=corp_no_firm)})

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await exec_notify_tax_advisor(
                corporate_id=CORP_ID, user_id=USER_ID,
                message="相談したいことがあります。", confirmed=True,
            )

    assert exc.value.status_code == 400
    assert "税理士" in exc.value.detail


# =============================================================================
# ⑥ export ツールのテスト
# =============================================================================

@pytest.mark.asyncio
async def test_export_csv_confirmed_returns_download_url():
    """confirmed=True で download_url が返り、format_type が URL に含まれること。"""
    from app.services.agent_tools import exec_export_csv

    result = await exec_export_csv(
        corporate_id=CORP_ID,
        format_type="mf",
        doc_type="receipts",
        fiscal_period="2025-03",
        confirmed=True,
    )

    assert result.get("success") is True
    assert "download_url" in result
    assert "mf" in result["download_url"]
    assert "2025-03" in result["download_url"]


@pytest.mark.asyncio
async def test_export_zengin_confirmed_returns_download_url():
    """confirmed=True で download_url が返ること。"""
    from app.services.agent_tools import exec_export_zengin

    result = await exec_export_zengin(
        corporate_id=CORP_ID,
        fiscal_period="2025-03",
        confirmed=True,
    )

    assert result.get("success") is True
    assert "download_url" in result


@pytest.mark.asyncio
async def test_export_csv_invalid_format_type():
    """format_type='unknown' で error が返ること。"""
    from app.services.agent_tools import exec_export_csv

    result = await exec_export_csv(
        corporate_id=CORP_ID,
        format_type="unknown",
        doc_type="all",
        confirmed=True,
    )

    assert "error" in result


# =============================================================================
# ⑦ execute_reconciliation のテスト
# =============================================================================

@pytest.mark.asyncio
async def test_execute_reconciliation_creates_match():
    """confirmed=True で matches コレクションに match_type 等が登録されること。"""
    from app.services.agent_tools import exec_execute_reconciliation

    tx_id = str(ObjectId())
    doc_id = str(ObjectId())
    tx_doc = {
        "_id": ObjectId(tx_id), "corporate_id": CORP_ID,
        "deposit_amount": 10000, "status": "unmatched",
    }
    matches_col = make_col()
    txs_col = make_col(find_one=tx_doc)
    receipts_col = make_col()
    mock_db = build_mock_db({
        "transactions": txs_col,
        "matches": matches_col,
        "receipts": receipts_col,
    })

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_execute_reconciliation(
            corporate_id=CORP_ID, user_id=USER_ID,
            transaction_ids=[tx_id], document_ids=[doc_id],
            match_type="receipt", confirmed=True,
        )

    assert result.get("success") is True
    matches_col.insert_one.assert_called_once()
    inserted = matches_col.insert_one.call_args[0][0]
    assert inserted["corporate_id"] == CORP_ID
    assert inserted["match_type"] == "receipt"
    assert tx_id in inserted["transaction_ids"]
    assert doc_id in inserted["document_ids"]


@pytest.mark.asyncio
async def test_execute_reconciliation_updates_transaction_status():
    """confirmed=True で transaction の status が 'matched' に更新されること。"""
    from app.services.agent_tools import exec_execute_reconciliation

    tx_id = str(ObjectId())
    doc_id = str(ObjectId())
    tx_doc = {
        "_id": ObjectId(tx_id), "corporate_id": CORP_ID,
        "deposit_amount": 10000, "status": "unmatched",
    }
    matches_col = make_col()
    txs_col = make_col(find_one=tx_doc)
    receipts_col = make_col()
    mock_db = build_mock_db({
        "transactions": txs_col,
        "matches": matches_col,
        "receipts": receipts_col,
    })

    with patch("app.services.agent_tools.get_database", return_value=mock_db):
        result = await exec_execute_reconciliation(
            corporate_id=CORP_ID, user_id=USER_ID,
            transaction_ids=[tx_id], document_ids=[doc_id],
            match_type="receipt", confirmed=True,
        )

    assert result.get("success") is True
    txs_col.update_one.assert_called_once()
    update_filter, update_body = txs_col.update_one.call_args[0]
    assert update_body["$set"]["status"] == "matched"
