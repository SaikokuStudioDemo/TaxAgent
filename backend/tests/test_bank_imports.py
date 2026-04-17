"""
bank_imports.py エラーハンドリング 意地悪テスト

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_bank_imports.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
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
# test_delete_import_file_db_error_returns_500
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_import_file_db_error_returns_500():
    """
    MongoDB の delete_many が例外を投げた場合に
    - HTTPException(500) が返ること
    - クラッシュしないこと
    """
    from fastapi import HTTPException
    from app.api.routes.bank_imports import delete_import_file

    file_id = str(ObjectId())
    oid = ObjectId(file_id)
    tx_oid = ObjectId()

    file_doc = {"_id": oid, "corporate_id": CORP_ID}
    tx_doc = {"_id": tx_oid, "import_file_id": file_id}

    file_col = make_col(find_one=file_doc)

    txs_col = make_col()
    txs_col.find = MagicMock(return_value=make_cursor([tx_doc]))
    txs_col.delete_many = AsyncMock(side_effect=Exception("DB connection error"))

    matches_col = make_col(find_data=[])

    ctx = make_ctx()
    ctx.db = build_mock_db({
        "bank_import_files": file_col,
        "transactions": txs_col,
        "matches": matches_col,
    })

    with pytest.raises(HTTPException) as exc:
        await delete_import_file(file_id, ctx)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_import_file_not_found_returns_404():
    """ファイルが存在しない場合に 404 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.bank_imports import delete_import_file

    file_col = make_col(find_one=None)

    ctx = make_ctx()
    ctx.db = build_mock_db({"bank_import_files": file_col})

    with pytest.raises(HTTPException) as exc:
        await delete_import_file(str(ObjectId()), ctx)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_import_file_no_transactions_succeeds():
    """紐付く transactions がない場合は正常に削除されること。"""
    from app.api.routes.bank_imports import delete_import_file

    file_id = str(ObjectId())
    oid = ObjectId(file_id)

    file_doc = {"_id": oid, "corporate_id": CORP_ID}

    file_col = make_col(find_one=file_doc)
    txs_col = make_col(find_data=[])  # transactions なし

    ctx = make_ctx()
    ctx.db = build_mock_db({
        "bank_import_files": file_col,
        "transactions": txs_col,
    })

    result = await delete_import_file(file_id, ctx)

    assert result["status"] == "deleted"
    assert result["deleted_transactions"] == 0
    file_col.delete_one.assert_called_once()
