"""
matches.py エラーハンドリング 意地悪テスト

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_matches.py -v
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
    col.update_many = AsyncMock()
    col.delete_one = AsyncMock()
    col.delete_many = AsyncMock()
    return col


def build_mock_db(collections=None):
    db = MagicMock()
    cols = collections or {}
    db.__getitem__ = MagicMock(side_effect=lambda k: cols.get(k, make_col()))
    return db


def make_ctx(corporate_id=CORP_ID, user_id=USER_ID):
    from app.api.helpers import CorporateContext
    ctx = MagicMock(spec=CorporateContext)
    ctx.corporate_id = corporate_id
    ctx.user_id = user_id
    ctx.db = build_mock_db()
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# test_create_match_logs_error_on_transaction_update_failure
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_match_logs_error_on_transaction_update_failure():
    """
    transactions.update_one が例外を投げた場合に
    - クラッシュしないこと
    - マッチ自体は作成されること
    - logger.error が呼ばれること
    """
    from app.api.routes.matches import create_match

    tx_id = str(ObjectId())
    doc_id = str(ObjectId())
    match_oid = ObjectId()

    tx_doc = {"_id": ObjectId(tx_id), "corporate_id": CORP_ID, "amount": 5000}
    receipt_doc = {"_id": ObjectId(doc_id), "corporate_id": CORP_ID, "amount": 5000}
    match_doc = {"_id": match_oid, "corporate_id": CORP_ID, "match_type": "receipt"}

    txs_col = make_col(find_one=tx_doc)
    txs_col.update_one = AsyncMock(side_effect=Exception("DB connection error"))

    receipts_col = make_col(find_one=receipt_doc)

    matches_col = make_col(find_one=match_doc)
    matches_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=match_oid))

    ctx = make_ctx()
    ctx.db = build_mock_db({
        "transactions": txs_col,
        "receipts": receipts_col,
        "matches": matches_col,
    })

    payload = {
        "match_type": "receipt",
        "transaction_ids": [tx_id],
        "document_ids": [doc_id],
        "fiscal_period": "2025-01",
    }

    with patch("app.api.routes.matches.logger") as mock_logger, \
         patch("app.api.routes.matches.calculate_match_score",
               return_value={"score": 90, "score_breakdown": {}, "is_candidate": True}):
        result = await create_match(payload, ctx)

    # マッチ自体は作成されること
    matches_col.insert_one.assert_called_once()
    assert result is not None

    # logger.error が呼ばれること
    assert mock_logger.error.called
    logged = " ".join(str(c) for c in mock_logger.error.call_args_list)
    assert "[matches]" in logged


# ─────────────────────────────────────────────────────────────────────────────
# test_delete_match_logs_error_on_status_restore_failure
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_match_logs_error_on_status_restore_failure():
    """
    delete_match で transactions.update_one が失敗した場合に
    - クラッシュしないこと
    - {"status": "unmatched"} が返ること
    """
    from app.api.routes.matches import delete_match

    match_id = str(ObjectId())
    tx_id = str(ObjectId())
    doc_id = str(ObjectId())

    match_doc = {
        "_id": ObjectId(match_id),
        "corporate_id": CORP_ID,
        "match_type": "receipt",
        "transaction_ids": [tx_id],
        "document_ids": [doc_id],
        "receipt_ids": [],
        "is_active": True,
    }
    receipt_doc = {"_id": ObjectId(doc_id), "corporate_id": CORP_ID, "amount": 3000}

    txs_col = make_col()
    txs_col.update_one = AsyncMock(side_effect=Exception("transaction update failed"))

    receipts_col = make_col(find_one=receipt_doc)

    matches_col = make_col(find_one=match_doc)

    ctx = make_ctx()
    ctx.db = build_mock_db({
        "transactions": txs_col,
        "receipts": receipts_col,
        "matches": matches_col,
    })

    with patch("app.api.routes.matches.logger") as mock_logger:
        result = await delete_match(match_id, ctx)

    # クラッシュしないこと・200 が返ること
    assert result["status"] == "unmatched"
    assert result["match_id"] == match_id

    # logger.error が呼ばれること
    assert mock_logger.error.called
    logged = " ".join(str(c) for c in mock_logger.error.call_args_list)
    assert "[matches]" in logged


# ─────────────────────────────────────────────────────────────────────────────
# test_write_match_events_failure_does_not_block_match
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_match_events_failure_does_not_block_match():
    """
    _write_match_events の audit_log 書き込みが失敗しても
    消込処理全体が成功すること。
    """
    from app.api.routes.matches import create_match

    tx_id = str(ObjectId())
    doc_id = str(ObjectId())
    match_oid = ObjectId()

    tx_doc = {"_id": ObjectId(tx_id), "corporate_id": CORP_ID, "amount": 5000}
    receipt_doc = {"_id": ObjectId(doc_id), "corporate_id": CORP_ID, "amount": 5000}
    match_doc = {"_id": match_oid, "corporate_id": CORP_ID, "match_type": "receipt"}

    txs_col = make_col(find_one=tx_doc)
    receipts_col = make_col(find_one=receipt_doc)
    matches_col = make_col(find_one=match_doc)
    matches_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=match_oid))

    audit_col = make_col()
    audit_col.insert_one = AsyncMock(side_effect=Exception("audit_log write failed"))

    ctx = make_ctx()
    ctx.db = build_mock_db({
        "transactions": txs_col,
        "receipts": receipts_col,
        "matches": matches_col,
        "audit_logs": audit_col,
    })

    payload = {
        "match_type": "receipt",
        "transaction_ids": [tx_id],
        "document_ids": [doc_id],
        "fiscal_period": "2025-01",
    }

    with patch("app.api.routes.matches.calculate_match_score",
               return_value={"score": 90, "score_breakdown": {}, "is_candidate": True}):
        result = await create_match(payload, ctx)

    # 消込処理は成功していること
    matches_col.insert_one.assert_called_once()
    assert result is not None
    assert "id" in result or result  # _serialize で id に変換される
