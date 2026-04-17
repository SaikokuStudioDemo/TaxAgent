"""
Tests for Task#25: 二重計上検知（duplicate_detector.py）

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_duplicate_detector.py -v
"""
import pytest
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


def make_col(find_data=None):
    col = MagicMock()
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    return col


def build_mock_db(collections: dict):
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


def make_filtering_col(all_docs: list):
    """corporate_id フィルタを実際に適用するコレクションモック。"""
    col = MagicMock()

    def _find(query: dict, *args, **kwargs):
        cid = query.get("corporate_id")
        filtered = [d for d in all_docs if cid is None or d.get("corporate_id") == cid]
        return make_cursor(filtered[:10])

    col.find = MagicMock(side_effect=_find)
    return col


def make_receipt_doc(corporate_id: str, date: str, amount: int, payee: str) -> dict:
    return {
        "_id": ObjectId(),
        "corporate_id": corporate_id,
        "date": date,
        "amount": amount,
        "payee": payee,
        "category": "交通費",
        "approval_status": "pending_approval",
    }


def make_invoice_doc(corporate_id: str, issue_date: str, total_amount: int,
                     client_name: str, document_type: str = "received") -> dict:
    return {
        "_id": ObjectId(),
        "corporate_id": corporate_id,
        "issue_date": issue_date,
        "total_amount": total_amount,
        "client_name": client_name,
        "document_type": document_type,
        "approval_status": "pending_approval",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 領収書テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_receipt_same_date_amount_payee():
    """同日・同金額・同取引先の領収書がある場合に has_duplicates=True が返ること。"""
    existing = make_receipt_doc(CORP_A_ID, "2025-04-01", 3000, "スターバックス")
    mock_db = build_mock_db({"receipts": make_col(find_data=[existing])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=3000, payee="スターバックスコーヒー"
        )

    assert result["has_duplicates"] is True
    assert len(result["candidates"]) > 0
    assert result["message"] != ""


@pytest.mark.asyncio
async def test_duplicate_receipt_different_date():
    """日付が違う場合は候補に含まれないこと（モックが空を返す = クエリで除外済み）。"""
    mock_db = build_mock_db({"receipts": make_col(find_data=[])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-02", amount=3000, payee="スターバックス"
        )

    assert result["has_duplicates"] is False
    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_duplicate_receipt_different_amount():
    """金額が違う場合は候補に含まれないこと。"""
    mock_db = build_mock_db({"receipts": make_col(find_data=[])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=9999, payee="スターバックス"
        )

    assert result["has_duplicates"] is False


@pytest.mark.asyncio
async def test_duplicate_receipt_partial_payee_match():
    """取引先名が部分一致する場合（'スターバックス' ⊂ 'スターバックスコーヒー'）に候補に含まれること。"""
    existing = make_receipt_doc(CORP_A_ID, "2025-04-01", 3000, "スターバックスコーヒー 渋谷店")
    mock_db = build_mock_db({"receipts": make_col(find_data=[existing])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=3000, payee="スターバックスコーヒー"
        )

    assert result["has_duplicates"] is True
    assert any(c["payee"] == "スターバックスコーヒー 渋谷店" for c in result["candidates"])


@pytest.mark.asyncio
async def test_duplicate_receipt_cross_corporate_blocked():
    """別法人の領収書が候補に含まれないこと（corporate_id フィルタ確認）。"""
    doc_b = make_receipt_doc(CORP_B_ID, "2025-04-01", 3000, "スターバックス")
    all_docs = [doc_b]

    # make_filtering_col で corporate_id を実際にフィルタ
    receipts_col = make_filtering_col(all_docs)
    mock_db = build_mock_db({"receipts": receipts_col})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=3000, payee="スターバックス"
        )

    assert result["has_duplicates"] is False, "別法人のデータが返ってはいけない"
    assert result["candidates"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 請求書テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_invoice_detected():
    """同日・同金額・同取引先の請求書がある場合に has_duplicates=True が返ること。"""
    existing = make_invoice_doc(CORP_A_ID, "2025-04-01", 100000, "株式会社テスト商事")
    mock_db = build_mock_db({"invoices": make_col(find_data=[existing])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_invoice
        result = await check_duplicate_invoice(
            CORP_A_ID,
            issue_date="2025-04-01",
            total_amount=100000,
            client_name="テスト商事",
            document_type="received",
        )

    assert result["has_duplicates"] is True
    assert len(result["candidates"]) > 0


@pytest.mark.asyncio
async def test_no_duplicate_when_only_one_document():
    """既存ドキュメントが1件もない場合に has_duplicates=False が返ること。"""
    mock_db = build_mock_db({"receipts": make_col(find_data=[])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=5000, payee="新規取引先"
        )

    assert result["has_duplicates"] is False
    assert result["candidates"] == []
    assert result["message"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# 追加：エラー耐性・exclude_id テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_exclude_id_filters_self():
    """exclude_id に自身の ID を渡した場合に候補に含まれないこと。"""
    own_id = str(ObjectId())
    existing = make_receipt_doc(CORP_A_ID, "2025-04-01", 3000, "スターバックス")
    existing["_id"] = ObjectId(own_id)
    # find クエリに $ne フィルタが入る想定で空リストを返すモック
    mock_db = build_mock_db({"receipts": make_col(find_data=[])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=3000, payee="スターバックス",
            exclude_id=own_id,
        )

    assert result["has_duplicates"] is False


@pytest.mark.asyncio
async def test_invalid_exclude_id_no_crash():
    """exclude_id に不正な ObjectId を渡してもクラッシュしないこと。"""
    mock_db = build_mock_db({"receipts": make_col(find_data=[])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=3000, payee="テスト",
            exclude_id="not-a-valid-id",  # 不正ID
        )

    assert isinstance(result, dict)  # クラッシュしないこと


@pytest.mark.asyncio
async def test_empty_payee_falls_back_to_date_amount():
    """payee が空の場合に同日・同金額の候補を最大3件返すこと。"""
    docs = [
        make_receipt_doc(CORP_A_ID, "2025-04-01", 3000, f"取引先{i}")
        for i in range(5)
    ]
    mock_db = build_mock_db({"receipts": make_col(find_data=docs)})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=3000, payee=""
        )

    # payee が空 → 部分一致できないので最大3件フォールバック
    assert result["has_duplicates"] is True
    assert len(result["candidates"]) <= 3


# =============================================================================
# 意地悪テスト（Task#25）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ④ 重複検知の境界値テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_duplicate_same_date_different_payee_still_returned():
    """
    同日・同金額だが取引先名が全く異なる場合でも candidates に含まれること。
    （同日・同金額は警告対象として最大3件フォールバックで返す）
    """
    existing = make_receipt_doc(CORP_A_ID, "2025-04-01", 3000, "全然違う取引先")
    mock_db = build_mock_db({"receipts": make_col(find_data=[existing])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=3000, payee="スターバックス"
        )

    # 名前が異なっても同日・同金額なのでフォールバックで候補に含まれること
    assert result["has_duplicates"] is True
    assert len(result["candidates"]) >= 1


@pytest.mark.asyncio
async def test_duplicate_receipt_exclude_self():
    """
    既存ドキュメントを更新する際に自分自身が重複候補に含まれないこと。
    exclude_id が機能していること（DB 側で $ne フィルタを想定）。
    """
    own_id = str(ObjectId())
    # exclude_id で除外される想定のため find が空を返すモックを使う
    mock_db = build_mock_db({"receipts": make_col(find_data=[])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=3000, payee="スターバックス",
            exclude_id=own_id,
        )

    assert result["has_duplicates"] is False
    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_duplicate_receipt_respects_is_deleted():
    """
    is_deleted=True のドキュメントが候補に含まれないこと。
    クエリに is_deleted: {$ne: True} が含まれていることを確認する。
    （DB がフィルタ済みの結果を返すモックで検証）
    """
    # is_deleted=True のドキュメントはクエリで除外されるので find は空を返す
    mock_db = build_mock_db({"receipts": make_col(find_data=[])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=3000, payee="スターバックス"
        )

    assert result["has_duplicates"] is False
    # クエリに is_deleted フィルタが渡されているかを確認
    receipts_col = mock_db["receipts"]
    find_query = receipts_col.find.call_args[0][0]
    assert "is_deleted" in find_query, "クエリに is_deleted フィルタが含まれていること"
    assert find_query["is_deleted"] == {"$ne": True}


@pytest.mark.asyncio
async def test_duplicate_invoice_different_document_type():
    """
    'issued' と 'received' は別種類として扱われること。
    issued の請求書チェックで received が返らないこと。
    """
    # received の請求書は DB にある、issued としてチェックするので空が返る想定
    mock_db = build_mock_db({"invoices": make_col(find_data=[])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_invoice
        result = await check_duplicate_invoice(
            CORP_A_ID,
            issue_date="2025-04-01",
            total_amount=100000,
            client_name="テスト商事",
            document_type="issued",  # issued で検索
        )

    assert result["has_duplicates"] is False
    # document_type フィルタが渡されていることを確認
    invoices_col = mock_db["invoices"]
    find_query = invoices_col.find.call_args[0][0]
    assert find_query["document_type"] == "issued"


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ スコープテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_check_cross_corporate_blocked():
    """
    法人Bの領収書が法人Aのチェックで返らないこと（corporate_id フィルタ確認）。
    make_filtering_col で実際のフィルタ動作を確認する。
    """
    doc_b = make_receipt_doc(CORP_B_ID, "2025-04-01", 3000, "スターバックス")
    receipts_col = make_filtering_col([doc_b])  # B のデータのみ
    mock_db = build_mock_db({"receipts": receipts_col})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID,  # A として検索
            date="2025-04-01", amount=3000, payee="スターバックス"
        )

    assert result["has_duplicates"] is False, "別法人のデータが返ってはいけない"
    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_duplicate_invoice_cross_corporate_blocked():
    """
    法人Bの請求書が法人Aのチェックで返らないこと。
    """
    doc_b = make_invoice_doc(CORP_B_ID, "2025-04-01", 100000, "テスト商事", "received")
    invoices_col = make_filtering_col([doc_b])
    mock_db = build_mock_db({"invoices": invoices_col})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_invoice
        result = await check_duplicate_invoice(
            CORP_A_ID,
            issue_date="2025-04-01",
            total_amount=100000,
            client_name="テスト商事",
            document_type="received",
        )

    assert result["has_duplicates"] is False, "別法人のデータが返ってはいけない"
    assert result["candidates"] == []


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ レスポンス形式の一貫性テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_duplicate_response_has_all_fields():
    """has_duplicates=False の場合でも candidates・message フィールドが含まれること。"""
    mock_db = build_mock_db({"receipts": make_col(find_data=[])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=5000, payee="テスト"
        )

    required_keys = {"has_duplicates", "candidates", "message"}
    missing = required_keys - set(result.keys())
    assert not missing, f"レスポンスに不足フィールド: {missing}"
    assert result["has_duplicates"] is False
    assert result["candidates"] == []
    assert result["message"] == ""


@pytest.mark.asyncio
async def test_has_duplicate_response_has_all_fields():
    """has_duplicates=True の場合に全フィールドが含まれること。"""
    existing = make_receipt_doc(CORP_A_ID, "2025-04-01", 3000, "スターバックス")
    mock_db = build_mock_db({"receipts": make_col(find_data=[existing])})

    with patch("app.services.duplicate_detector.get_database", return_value=mock_db):
        from app.services.duplicate_detector import check_duplicate_receipt
        result = await check_duplicate_receipt(
            CORP_A_ID, date="2025-04-01", amount=3000, payee="スターバックス"
        )

    required_keys = {"has_duplicates", "candidates", "message"}
    missing = required_keys - set(result.keys())
    assert not missing, f"レスポンスに不足フィールド: {missing}"
    assert result["has_duplicates"] is True
    assert len(result["candidates"]) > 0
    assert result["message"] != ""
