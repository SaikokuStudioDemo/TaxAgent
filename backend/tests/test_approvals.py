"""
approvals.py エラーハンドリング 意地悪テスト

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_approvals.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

CORP_ID = str(ObjectId())
USER_ID = str(ObjectId())


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_cursor(data=None):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=data or [])
    return cursor


def make_col(find_one=None, find_data=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock()
    return col


def build_mock_db(collections=None):
    db = MagicMock()
    cols = collections or {}
    db.__getitem__ = MagicMock(side_effect=lambda k: cols.get(k, make_col()))
    return db


def make_ctx(corporate_id=CORP_ID, user_id=USER_ID, firebase_uid="test_uid"):
    from app.api.helpers import CorporateContext
    ctx = MagicMock(spec=CorporateContext)
    ctx.corporate_id = corporate_id
    ctx.user_id = user_id
    ctx.firebase_uid = firebase_uid
    ctx.db = build_mock_db()
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# test_record_approval_unexpected_error_returns_500
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_approval_unexpected_error_returns_500():
    """
    record_approval_action 内で予期しない例外が発生した場合に
    - HTTPException(500) が返ること
    - HTTPException ではない例外でも適切にハンドリングされること
    """
    from fastapi import HTTPException
    from app.api.routes.approvals import record_approval_action
    from app.models.approval import ApprovalEventCreate

    doc_id = str(ObjectId())

    doc = {
        "_id": ObjectId(doc_id),
        "corporate_id": CORP_ID,
        "amount": 5000,
        "approval_rule_id": None,
        "current_step": 1,
    }

    receipts_col = make_col(find_one=doc)

    audit_col = make_col()
    audit_col.insert_one = AsyncMock(side_effect=Exception("Unexpected DB error"))

    ctx = make_ctx()
    ctx.db = build_mock_db({
        "receipts": receipts_col,
        "audit_logs": audit_col,
    })

    payload = ApprovalEventCreate(
        document_type="receipt",
        document_id=doc_id,
        step=1,
        action="approved",
        comment=None,
    )

    # audit_logs.insert_one が raise するのは通知より前なのでモック不要
    with pytest.raises(HTTPException) as exc:
        await record_approval_action(payload, ctx)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_record_approval_http_exception_propagates():
    """
    action='rejected' かつ comment=None の場合に
    HTTPException(400) がそのまま伝播すること（500 に変換されないこと）。
    """
    from fastapi import HTTPException
    from app.api.routes.approvals import record_approval_action
    from app.models.approval import ApprovalEventCreate

    doc_id = str(ObjectId())
    ctx = make_ctx()

    payload = ApprovalEventCreate(
        document_type="receipt",
        document_id=doc_id,
        step=1,
        action="rejected",
        comment=None,
    )

    with pytest.raises(HTTPException) as exc:
        await record_approval_action(payload, ctx)

    # 400 のまま（500 に変換されていないこと）
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# test_get_pending_for_me_skips_invalid_rule
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_pending_for_me_skips_invalid_rule():
    """
    approval_rules に不正な rule_id がある場合に
    - クラッシュしないこと
    - 有効なドキュメントのみ返ること
    """
    from app.api.routes.approvals import _get_pending_for_me

    valid_rule_id = str(ObjectId())
    invalid_rule_id = "not-a-valid-objectid"

    pending_docs = [
        {
            "_id": ObjectId(),
            "corporate_id": CORP_ID,
            "approval_status": "pending_approval",
            "approval_rule_id": invalid_rule_id,  # ObjectId() で例外発生
            "current_step": 1,
        },
        {
            "_id": ObjectId(),
            "corporate_id": CORP_ID,
            "approval_status": "pending_approval",
            "approval_rule_id": valid_rule_id,
            "current_step": 1,
        },
    ]

    valid_rule = {
        "_id": ObjectId(valid_rule_id),
        "steps": [{"step": 1, "role": "manager"}],
    }

    employees_col = make_col(find_one={"firebase_uid": "test_uid", "role": "manager"})

    receipts_col = make_col()
    receipts_col.find = MagicMock(return_value=make_cursor(pending_docs))

    approval_rules_col = make_col(find_one=valid_rule)

    db = build_mock_db({
        "employees": employees_col,
        "receipts": receipts_col,
        "approval_rules": approval_rules_col,
    })

    result = await _get_pending_for_me(db, CORP_ID, "test_uid", "receipt")

    # クラッシュしないこと
    assert isinstance(result, list)
    # 有効なドキュメント（valid_rule_id を持つ）のみ返ること
    assert len(result) == 1
    assert str(result[0].get("approval_rule_id")) == valid_rule_id
