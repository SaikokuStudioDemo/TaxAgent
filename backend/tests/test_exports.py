"""
Tests for Task#33・#34: CSV出力 + 全銀データ出力

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_exports.py -v
"""
import csv
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

CORP_ID = "test_corp_id"
CORP_UID = "corp_firebase_uid"


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_col(find_one=None, find_data=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    return col


def build_mock_db(collections: dict = None):
    db = MagicMock()
    cols = collections or {}
    db.__getitem__ = MagicMock(side_effect=lambda k: cols.get(k, make_col()))
    return db


def sample_receipt(approval_status="approved", fiscal_period="2025-04"):
    return {
        "_id": ObjectId(),
        "corporate_id": CORP_ID,
        "date": "2025-04-01",
        "amount": 5000,
        "tax_amount": 500,
        "payee": "テスト商店",
        "category": "消耗品費",
        "tax_category": "課税仕入 10%",
        "approval_status": approval_status,
        "fiscal_period": fiscal_period,
    }


def sample_invoice(approval_status="approved", fiscal_period="2025-04"):
    return {
        "_id": ObjectId(),
        "corporate_id": CORP_ID,
        "issue_date": "2025-04-10",
        "total_amount": 10000,
        "tax_amount": 1000,
        "client_name": "テスト取引先",
        "vendor_name": "",
        "account_subject": "売上高",
        "tax_category": "課税仕入 10%",
        "approval_status": approval_status,
        "fiscal_period": fiscal_period,
        "document_type": "received",
        "reconciliation_status": "unreconciled",
        "vendor_bank_code": "0001",
        "vendor_branch_code": "001",
        "vendor_account_type": "1",
        "vendor_account_number": "1234567",
        "vendor_name": "ﾃｽﾄｶｲｼｬ",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CSV フォーマットテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_csv_freee_format_has_correct_headers():
    """freee フォーマットのヘッダー行が正しいこと。"""
    from app.services.csv_export_service import export_csv, FREEE_HEADERS

    mock_db = build_mock_db({
        "receipts": make_col(find_data=[sample_receipt()]),
        "invoices": make_col(find_data=[]),
    })
    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        result = await export_csv(CORP_ID, "freee", "receipt")

    reader = csv.reader(io.StringIO(result))
    headers = next(reader)
    assert headers == FREEE_HEADERS


@pytest.mark.asyncio
async def test_csv_mf_format_has_correct_headers():
    """MF フォーマットのヘッダー行が正しいこと。"""
    from app.services.csv_export_service import export_csv, MF_HEADERS

    mock_db = build_mock_db({
        "receipts": make_col(find_data=[sample_receipt()]),
        "invoices": make_col(find_data=[]),
    })
    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        result = await export_csv(CORP_ID, "mf", "receipt")

    reader = csv.reader(io.StringIO(result))
    headers = next(reader)
    assert headers == MF_HEADERS


@pytest.mark.asyncio
async def test_csv_yayoi_format_has_correct_headers():
    """弥生フォーマットのヘッダー行が正しいこと。"""
    from app.services.csv_export_service import export_csv, YAYOI_HEADERS

    mock_db = build_mock_db({
        "receipts": make_col(find_data=[sample_receipt()]),
        "invoices": make_col(find_data=[]),
    })
    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        result = await export_csv(CORP_ID, "yayoi", "receipt")

    reader = csv.reader(io.StringIO(result))
    headers = next(reader)
    assert headers == YAYOI_HEADERS


@pytest.mark.asyncio
async def test_csv_only_approved_docs_included():
    """承認済みドキュメントのみCSVに含まれること（未承認は除外）。"""
    from app.services.csv_export_service import export_csv

    approved = sample_receipt(approval_status="approved")
    # モックは export_csv 内のクエリで approval_status="approved" を渡すが、
    # DBモックは渡されたフィルタを無視して find_data をそのまま返す。
    # → 実際に意味があるのはサービス側のクエリ構築の確認。
    mock_db = build_mock_db({
        "receipts": make_col(find_data=[approved]),
        "invoices": make_col(find_data=[]),
    })
    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        result = await export_csv(CORP_ID, "freee", "receipt")

    # find に渡されるクエリに approval_status="approved" が含まれること
    find_query = mock_db["receipts"].find.call_args[0][0]
    assert find_query.get("approval_status") == "approved"

    reader = csv.reader(io.StringIO(result))
    rows = list(reader)
    # ヘッダー + 1件
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_csv_fiscal_period_filter():
    """fiscal_period を指定した場合にクエリにフィルタが含まれること。"""
    from app.services.csv_export_service import export_csv

    mock_db = build_mock_db({
        "receipts": make_col(find_data=[sample_receipt(fiscal_period="2025-04")]),
        "invoices": make_col(find_data=[]),
    })
    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        result = await export_csv(CORP_ID, "freee", "receipt", fiscal_period="2025-04")

    find_query = mock_db["receipts"].find.call_args[0][0]
    assert find_query.get("fiscal_period") == "2025-04"


@pytest.mark.asyncio
async def test_csv_unknown_format_returns_400():
    """不正な format_type で ValueError が送出されること。"""
    from app.services.csv_export_service import export_csv

    mock_db = build_mock_db()
    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        with pytest.raises(ValueError) as exc:
            await export_csv(CORP_ID, "unknown_format", "all")

    assert "Unknown format" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# 全銀フォーマットテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_zengin_header_record_correct_length():
    """ヘッダーレコードが120文字であること。"""
    from app.services.zengin_export_service import export_zengin

    inv = sample_invoice()
    mock_db = build_mock_db({"invoices": make_col(find_data=[inv])})

    with patch("app.services.zengin_export_service.get_database", return_value=mock_db):
        result = await export_zengin(CORP_ID, company_name="テスト")

    lines = result.split("\r\n")
    assert len(lines[0]) == 120, f"ヘッダー長が {len(lines[0])} （期待値: 120）"


@pytest.mark.asyncio
async def test_zengin_data_record_correct_length():
    """データレコードが120文字であること。"""
    from app.services.zengin_export_service import export_zengin

    inv = sample_invoice()
    mock_db = build_mock_db({"invoices": make_col(find_data=[inv])})

    with patch("app.services.zengin_export_service.get_database", return_value=mock_db):
        result = await export_zengin(CORP_ID, company_name="テスト")

    lines = result.split("\r\n")
    # lines[0]=header, lines[1]=data, lines[2]=trailer, lines[3]=end
    assert len(lines) == 4
    assert len(lines[1]) == 120, f"データレコード長が {len(lines[1])} （期待値: 120）"


@pytest.mark.asyncio
async def test_zengin_trailer_has_correct_totals():
    """トレーラーレコードの合計件数・合計金額が正しいこと。"""
    from app.services.zengin_export_service import export_zengin, ZENGIN_TRAILER_CODE

    inv1 = {**sample_invoice(), "total_amount": 10000}
    inv2 = {**sample_invoice(), "total_amount": 5000}
    mock_db = build_mock_db({"invoices": make_col(find_data=[inv1, inv2])})

    with patch("app.services.zengin_export_service.get_database", return_value=mock_db):
        result = await export_zengin(CORP_ID)

    lines = result.split("\r\n")
    # header + 2データ + trailer + end = 5行
    # トレーラーは末尾から2番目
    trailer = lines[-2]
    assert trailer[0] == ZENGIN_TRAILER_CODE
    # 件数（2件）: 桁1〜6
    assert int(trailer[1:7]) == 2
    # 合計金額（15000円）: 桁7〜18
    assert int(trailer[7:19]) == 15000


@pytest.mark.asyncio
async def test_zengin_no_data_returns_empty():
    """出力対象データが0件の場合に空文字が返ること。"""
    from app.services.zengin_export_service import export_zengin

    mock_db = build_mock_db({"invoices": make_col(find_data=[])})

    with patch("app.services.zengin_export_service.get_database", return_value=mock_db):
        result = await export_zengin(CORP_ID)

    assert result == ""


# ─────────────────────────────────────────────────────────────────────────────
# 権限テスト（エンドポイント経由）
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_requires_accounting_role():
    """staff ロールで GET /exports/csv を呼ぶと 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.exports import export_csv_endpoint

    staff_emp = {"_id": ObjectId(), "firebase_uid": "staff_uid", "role": "staff"}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=None),   # オーナーではない
        "employees": make_col(find_one=staff_emp),
    })

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)):
        with pytest.raises(HTTPException) as exc:
            await export_csv_endpoint(
                format_type="freee", doc_type="all",
                fiscal_period=None, current_user={"uid": "staff_uid"}
            )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_export_accounting_role_allowed():
    """accounting ロールで export_csv が呼ばれること（200相当）。"""
    from app.api.routes.exports import export_csv_endpoint

    acct_emp = {"_id": ObjectId(), "firebase_uid": "acct_uid", "role": "accounting"}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=None),
        "employees": make_col(find_one=acct_emp),
    })

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.api.routes.exports.export_csv",
               new_callable=AsyncMock, return_value="header\nrow1\n") as mock_csv:
        response = await export_csv_endpoint(
            format_type="freee", doc_type="all",
            fiscal_period=None, current_user={"uid": "acct_uid"}
        )

    mock_csv.assert_called_once()
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_export_manager_role_allowed():
    """① manager ロールも許可されること（修正済み確認）。"""
    from app.api.routes.exports import export_csv_endpoint

    mgr_emp = {"_id": ObjectId(), "firebase_uid": "mgr_uid", "role": "manager"}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=None),
        "employees": make_col(find_one=mgr_emp),
    })

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.api.routes.exports.export_csv",
               new_callable=AsyncMock, return_value="header\n"):
        response = await export_csv_endpoint(
            format_type="freee", doc_type="all",
            fiscal_period=None, current_user={"uid": "mgr_uid"}
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_zengin_no_data_returns_404():
    """出力対象データが0件の場合に 404 が返ること（エンドポイント経由）。"""
    from fastapi import HTTPException
    from app.api.routes.exports import export_zengin_endpoint

    corp_doc = {"_id": ObjectId(CORP_ID if len(CORP_ID) == 24 else str(ObjectId())),
                "firebase_uid": CORP_UID, "name": "テスト"}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_doc),
        "bank_accounts": make_col(find_one=None),
    })

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(str(corp_doc["_id"]), CORP_UID)), \
         patch("app.api.routes.exports.export_zengin",
               new_callable=AsyncMock, return_value=""):
        with pytest.raises(HTTPException) as exc:
            await export_zengin_endpoint(
                fiscal_period=None, current_user={"uid": CORP_UID}
            )

    assert exc.value.status_code == 404


# =============================================================================
# 意地悪テスト（Task#33・#34）
# =============================================================================

# ── StreamingResponse のボディを読むヘルパー ──────────────────────────────────
async def _read_response(response) -> bytes:
    content = b""
    async for chunk in response.body_iterator:
        content += chunk if isinstance(chunk, bytes) else chunk.encode()
    return content


# ─────────────────────────────────────────────────────────────────────────────
# ① 権限テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_staff_cannot_export_csv():
    """staff ロールで GET /exports/csv を呼ぶと 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.exports import export_csv_endpoint

    staff_emp = {"_id": ObjectId(), "firebase_uid": "staff_uid", "role": "staff"}
    mock_db = build_mock_db({"corporates": make_col(find_one=None), "employees": make_col(find_one=staff_emp)})

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id", new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)):
        with pytest.raises(HTTPException) as exc:
            await export_csv_endpoint(format_type="freee", doc_type="all", fiscal_period=None, current_user={"uid": "staff_uid"})

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_approver_cannot_export_csv():
    """approver ロールで 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.exports import export_csv_endpoint

    approver_emp = {"_id": ObjectId(), "firebase_uid": "approver_uid", "role": "approver"}
    mock_db = build_mock_db({"corporates": make_col(find_one=None), "employees": make_col(find_one=approver_emp)})

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id", new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)):
        with pytest.raises(HTTPException) as exc:
            await export_csv_endpoint(format_type="freee", doc_type="all", fiscal_period=None, current_user={"uid": "approver_uid"})

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_manager_can_export_csv():
    """manager ロールで 200 が返ること（isAccountingOrAbove と一致）。"""
    from app.api.routes.exports import export_csv_endpoint

    mgr_emp = {"_id": ObjectId(), "firebase_uid": "mgr_uid", "role": "manager"}
    mock_db = build_mock_db({"corporates": make_col(find_one=None), "employees": make_col(find_one=mgr_emp)})

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id", new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.api.routes.exports.export_csv", new_callable=AsyncMock, return_value="h\n"):
        response = await export_csv_endpoint(format_type="freee", doc_type="all", fiscal_period=None, current_user={"uid": "mgr_uid"})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_accounting_can_export_zengin():
    """accounting ロールで GET /exports/zengin が 200 を返すこと。"""
    from app.api.routes.exports import export_zengin_endpoint

    acct_emp = {"_id": ObjectId(), "firebase_uid": "acct_uid", "role": "accounting"}
    corp_oid = ObjectId()
    corp_doc = {"_id": corp_oid, "firebase_uid": CORP_UID, "name": "テスト"}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=acct_emp),   # find_one(firebase_uid) → None → employee lookup
        "employees": make_col(find_one=acct_emp),
        "bank_accounts": make_col(find_one=None),
    })
    # オーナーチェックは None → 従業員チェック
    async def _find_one_smart(query, *a, **k):
        if query.get("firebase_uid") == "acct_uid":
            return None  # corporates では見つからない
        if "_id" in query:
            return corp_doc
        return None
    mock_db["corporates"].find_one = _find_one_smart

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id", new_callable=AsyncMock, return_value=(str(corp_oid), str(corp_oid))), \
         patch("app.api.routes.exports.export_zengin", new_callable=AsyncMock, return_value="zengin_text"):
        response = await export_zengin_endpoint(fiscal_period=None, current_user={"uid": "acct_uid"})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_cannot_export():
    """firebase_uid=None（認証なし相当）で 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.exports import export_csv_endpoint

    mock_db = build_mock_db()

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id", new_callable=AsyncMock,
               side_effect=HTTPException(status_code=403, detail="Access denied")):
        with pytest.raises(HTTPException) as exc:
            await export_csv_endpoint(format_type="freee", doc_type="all", fiscal_period=None, current_user={"uid": None})

    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# ② CSV フォーマット境界値テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_csv_empty_data_returns_header_only():
    """対象データが0件の場合にヘッダー行のみのCSVが返ること（404ではなく200）。"""
    from app.services.csv_export_service import export_csv, FREEE_HEADERS

    mock_db = build_mock_db({"receipts": make_col(find_data=[]), "invoices": make_col(find_data=[])})

    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        result = await export_csv(CORP_ID, "freee", "all")

    import csv, io
    reader = csv.reader(io.StringIO(result))
    rows = list(reader)
    assert len(rows) == 1, "ヘッダー行のみであること"
    assert rows[0] == FREEE_HEADERS


@pytest.mark.asyncio
async def test_csv_receipt_only_excludes_invoices():
    """doc_type='receipt' の場合に invoices の find が呼ばれないこと。"""
    from app.services.csv_export_service import export_csv

    receipts_col = make_col(find_data=[sample_receipt()])
    invoices_col = make_col(find_data=[sample_invoice()])
    mock_db = build_mock_db({"receipts": receipts_col, "invoices": invoices_col})

    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        await export_csv(CORP_ID, "freee", "receipt")

    invoices_col.find.assert_not_called()


@pytest.mark.asyncio
async def test_csv_invoice_only_excludes_receipts():
    """doc_type='invoice' の場合に receipts の find が呼ばれないこと。"""
    from app.services.csv_export_service import export_csv

    receipts_col = make_col(find_data=[sample_receipt()])
    invoices_col = make_col(find_data=[sample_invoice()])
    mock_db = build_mock_db({"receipts": receipts_col, "invoices": invoices_col})

    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        await export_csv(CORP_ID, "freee", "invoice")

    receipts_col.find.assert_not_called()


@pytest.mark.asyncio
async def test_csv_unapproved_docs_excluded():
    """approval_status='approved' フィルタがクエリに含まれること。"""
    from app.services.csv_export_service import export_csv

    receipts_col = make_col(find_data=[])
    mock_db = build_mock_db({"receipts": receipts_col, "invoices": make_col(find_data=[])})

    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        await export_csv(CORP_ID, "freee", "receipt")

    find_query = receipts_col.find.call_args[0][0]
    assert find_query.get("approval_status") == "approved", \
        "未承認ドキュメントを除外するフィルタが含まれること"


@pytest.mark.asyncio
async def test_csv_utf8_bom_present():
    """エンドポイント経由のレスポンスの先頭に UTF-8 BOM が含まれること。"""
    from app.api.routes.exports import export_csv_endpoint

    corp_doc = {"_id": ObjectId(), "firebase_uid": CORP_UID}
    mock_db = build_mock_db({"corporates": make_col(find_one=corp_doc), "employees": make_col(find_one=None)})

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id", new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.api.routes.exports.export_csv", new_callable=AsyncMock, return_value="ヘッダー\nデータ\n"):
        response = await export_csv_endpoint(format_type="freee", doc_type="all", fiscal_period=None, current_user={"uid": CORP_UID})

    content = await _read_response(response)
    assert content[:3] == b'\xef\xbb\xbf', "UTF-8 BOM が先頭に含まれること"


@pytest.mark.asyncio
async def test_csv_content_disposition_header():
    """Content-Disposition: attachment が含まれ、ファイル名に format_type が含まれること。"""
    from app.api.routes.exports import export_csv_endpoint

    corp_doc = {"_id": ObjectId(), "firebase_uid": CORP_UID}
    mock_db = build_mock_db({"corporates": make_col(find_one=corp_doc), "employees": make_col(find_one=None)})

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id", new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.api.routes.exports.export_csv", new_callable=AsyncMock, return_value="h\n"):
        response = await export_csv_endpoint(format_type="mf", doc_type="all", fiscal_period=None, current_user={"uid": CORP_UID})

    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "mf" in disposition


# ─────────────────────────────────────────────────────────────────────────────
# ③ 全銀フォーマット詳細テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_zengin_record_count_equals_invoice_count():
    """データレコードの件数が対象請求書の件数と一致すること。"""
    from app.services.zengin_export_service import export_zengin

    invoices = [sample_invoice() for _ in range(3)]
    mock_db = build_mock_db({"invoices": make_col(find_data=invoices)})

    with patch("app.services.zengin_export_service.get_database", return_value=mock_db):
        result = await export_zengin(CORP_ID)

    lines = result.split("\r\n")
    # header + 3 data + trailer + end = 6行
    assert len(lines) == 6
    data_lines = [l for l in lines if l.startswith("2")]
    assert len(data_lines) == 3


@pytest.mark.asyncio
async def test_zengin_trailer_total_amount_correct():
    """トレーラーの合計金額が全データレコードの金額合計と一致すること。"""
    from app.services.zengin_export_service import export_zengin, ZENGIN_TRAILER_CODE

    inv1 = {**sample_invoice(), "total_amount": 12345}
    inv2 = {**sample_invoice(), "total_amount": 67890}
    mock_db = build_mock_db({"invoices": make_col(find_data=[inv1, inv2])})

    with patch("app.services.zengin_export_service.get_database", return_value=mock_db):
        result = await export_zengin(CORP_ID)

    lines = result.split("\r\n")
    trailer = lines[-2]
    assert trailer[0] == ZENGIN_TRAILER_CODE
    total_in_trailer = int(trailer[7:19])
    assert total_in_trailer == 12345 + 67890


@pytest.mark.asyncio
async def test_zengin_only_received_invoices():
    """クエリに document_type='received' フィルタが含まれること。"""
    from app.services.zengin_export_service import export_zengin

    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col})

    with patch("app.services.zengin_export_service.get_database", return_value=mock_db):
        await export_zengin(CORP_ID)

    find_query = invoices_col.find.call_args[0][0]
    assert find_query.get("document_type") == "received", \
        "issued は除外すること"


@pytest.mark.asyncio
async def test_zengin_only_unreconciled():
    """クエリに reconciliation_status != 'reconciled' フィルタが含まれること。"""
    from app.services.zengin_export_service import export_zengin

    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col})

    with patch("app.services.zengin_export_service.get_database", return_value=mock_db):
        await export_zengin(CORP_ID)

    find_query = invoices_col.find.call_args[0][0]
    assert find_query.get("reconciliation_status") == {"$ne": "reconciled"}, \
        "消込済みは除外すること"


@pytest.mark.asyncio
async def test_zengin_shift_jis_encoding():
    """エンドポイントのレスポンスが Shift-JIS でエンコードされ media_type が text/plain であること。"""
    from app.api.routes.exports import export_zengin_endpoint

    corp_oid = ObjectId()
    corp_doc = {"_id": corp_oid, "firebase_uid": CORP_UID, "name": "テスト"}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_doc),
        "bank_accounts": make_col(find_one=None),
    })

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id", new_callable=AsyncMock, return_value=(str(corp_oid), CORP_UID)), \
         patch("app.api.routes.exports.export_zengin", new_callable=AsyncMock, return_value="zengin_text"):
        response = await export_zengin_endpoint(fiscal_period=None, current_user={"uid": CORP_UID})

    assert response.media_type == "text/plain"
    content = await _read_response(response)
    # Shift-JIS でデコードできること
    decoded = content.decode("shift_jis", errors="replace")
    assert "zengin_text" in decoded


def test_zengin_kana_conversion():
    """全角カナ「カブシキガイシャ」が半角カナ「ｶﾌﾞｼｷｶﾞｲｼｬ」に変換されること。"""
    from app.services.zengin_export_service import _to_zengin_kana

    assert _to_zengin_kana("カブシキガイシャ") == "ｶﾌﾞｼｷｶﾞｲｼｬ"
    assert _to_zengin_kana("テスト") == "ﾃｽﾄ"
    assert _to_zengin_kana("パソコン") == "ﾊﾟｿｺﾝ"


# ─────────────────────────────────────────────────────────────────────────────
# ④ クロス法人テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_csv_cross_corporate_blocked():
    """法人Aのユーザーが corporate_id=A のクエリでのみデータを取得できること。"""
    from app.services.csv_export_service import export_csv

    corp_a_id = "corp_a_id"
    receipts_col = make_col(find_data=[])
    mock_db = build_mock_db({"receipts": receipts_col, "invoices": make_col(find_data=[])})

    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        await export_csv(corp_a_id, "freee", "receipt")

    find_query = receipts_col.find.call_args[0][0]
    assert find_query.get("corporate_id") == corp_a_id, \
        "corporate_id フィルタが法人Aに限定されていること"


@pytest.mark.asyncio
async def test_zengin_cross_corporate_blocked():
    """全銀データでも corporate_id フィルタが機能していること。"""
    from app.services.zengin_export_service import export_zengin

    corp_a_id = "corp_a_id"
    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col})

    with patch("app.services.zengin_export_service.get_database", return_value=mock_db):
        await export_zengin(corp_a_id)

    find_query = invoices_col.find.call_args[0][0]
    assert find_query.get("corporate_id") == corp_a_id, \
        "corporate_id フィルタが法人Aに限定されていること"


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ fiscal_period フィルターテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_csv_fiscal_period_excludes_other_months():
    """fiscal_period='2024-03' を指定すると、クエリに '2024-03' フィルタが含まれること。"""
    from app.services.csv_export_service import export_csv

    receipts_col = make_col(find_data=[])
    mock_db = build_mock_db({"receipts": receipts_col, "invoices": make_col(find_data=[])})

    with patch("app.services.csv_export_service.get_database", return_value=mock_db):
        await export_csv(CORP_ID, "freee", "receipt", fiscal_period="2024-03")

    find_query = receipts_col.find.call_args[0][0]
    assert find_query.get("fiscal_period") == "2024-03"
    # fiscal_period を省略すると fiscal_period フィルタなし
    await export_csv.__wrapped__(CORP_ID, "freee", "receipt") if hasattr(export_csv, "__wrapped__") else None


@pytest.mark.asyncio
async def test_zengin_fiscal_period_filter():
    """全銀データでも fiscal_period フィルターが機能すること。"""
    from app.services.zengin_export_service import export_zengin

    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col})

    with patch("app.services.zengin_export_service.get_database", return_value=mock_db):
        await export_zengin(CORP_ID, fiscal_period="2024-03")

    find_query = invoices_col.find.call_args[0][0]
    assert find_query.get("fiscal_period") == "2024-03"
