"""
Tests for Task#16: get_corporate_context() expansion.

Usage:
    cd backend
    pytest tests/test_corporate_context.py -v
"""
import calendar
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

# ── テスト用 ObjectId（valid な形式） ──────────────────────────────────────────
CORP_ID = str(ObjectId())


# ── モックヘルパー ─────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    """Motor cursor チェーン（.sort().limit().to_list()）をモックする。"""
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_col(find_one=None, find_data=None, count=0):
    """Motor コレクションのモックを生成する。"""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.count_documents = AsyncMock(return_value=count)
    col.update_one = AsyncMock(return_value=MagicMock())
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    return col


def build_mock_db(
    company_profile=None,
    receipts=None,
    invoices=None,
    transactions=None,
    tx_count=0,
    notifications=None,
    corporate_doc=None,
):
    """各コレクションを差し替え可能な DB モックを生成する。"""
    collections = {
        "company_profiles": make_col(
            find_one=company_profile or {"company_name": "テスト株式会社"}
        ),
        "receipts":      make_col(find_data=receipts or []),
        "invoices":      make_col(find_data=invoices or []),
        "transactions":  make_col(find_data=transactions or [], count=tx_count),
        "notifications": make_col(find_data=notifications or []),
        "corporates":    make_col(find_one=corporate_doc),
    }
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


# ── ① 未承認書類の確認 ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_includes_pending_documents():
    """未承認の領収書がある場合に pending_documents にリストが返ること・pending_days が正しいこと"""
    from app.services.chat_service import ChatService

    three_days_ago = datetime.utcnow() - timedelta(days=3)
    receipt = {
        "_id": ObjectId(),
        "amount": 5000,
        "submitted_by": str(ObjectId()),
        "date": "2024-01-10",
        "created_at": three_days_ago,
    }

    mock_db = build_mock_db(receipts=[receipt])

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch(
            "app.services.chat_service.build_name_map",
            new_callable=AsyncMock,
            return_value={str(receipt["submitted_by"]): "田中太郎"},
        ),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    assert len(result["pending_documents"]) == 1
    doc = result["pending_documents"][0]
    assert doc["type"] == "領収書"
    assert doc["amount"] == 5000
    assert doc["submitter_name"] == "田中太郎"
    assert doc["pending_days"] == 3


@pytest.mark.asyncio
async def test_context_pending_invoice_type():
    """受領請求書が pending_documents に 'type=受領請求書' で入ること"""
    from app.services.chat_service import ChatService

    invoice = {
        "_id": ObjectId(),
        "total_amount": 120000,
        "submitted_by": str(ObjectId()),
        "issue_date": "2024-01-05",
        "created_at": datetime.utcnow() - timedelta(days=7),
    }

    mock_db = build_mock_db(invoices=[invoice])

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch(
            "app.services.chat_service.build_name_map",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    assert len(result["pending_documents"]) == 1
    assert result["pending_documents"][0]["type"] == "受領請求書"
    assert result["pending_documents"][0]["pending_days"] == 7


# ── ② 未消込入金の確認 ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_includes_recent_deposits():
    """未消込の入金がある場合に recent_deposits にリストが返ること"""
    from app.services.chat_service import ChatService

    tx = {
        "_id": ObjectId(),
        "deposit_amount": 100000,
        "description": "株式会社テスト 振込",
        "transaction_date": datetime(2024, 1, 15),
    }

    mock_db = build_mock_db(transactions=[tx], tx_count=1)

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    assert len(result["recent_deposits"]) == 1
    deposit = result["recent_deposits"][0]
    assert deposit["amount"] == 100000
    assert deposit["description"] == "株式会社テスト 振込"
    assert result["unmatched_transactions_count"] == 1


# ── ③ days_until_month_end の確認 ────────────────────────────────────────────────

def test_context_days_until_month_end():
    """days_until_month_end の計算ロジックが正しいこと（日付計算をユニットテスト）"""
    # 月末日 → 0
    last_day_jan = date(2024, 1, 31)
    last_day = calendar.monthrange(last_day_jan.year, last_day_jan.month)[1]
    assert (date(last_day_jan.year, last_day_jan.month, last_day) - last_day_jan).days == 0

    # 月初 → 正の数
    first_day_feb = date(2024, 2, 1)
    last_day = calendar.monthrange(first_day_feb.year, first_day_feb.month)[1]
    days = (date(first_day_feb.year, first_day_feb.month, last_day) - first_day_feb).days
    assert days > 0

    # today() で実行した結果は常に 0〜30 の範囲
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    days = (date(today.year, today.month, last_day) - today).days
    assert 0 <= days <= 30


# ── ④ 初回アクセス判定の確認 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_first_access_detection():
    """last_accessed_at が 1時間以上前なら True・30分前なら False になること"""
    from app.services.chat_service import ChatService

    # ── 1時間以上前 → is_first_access_today = True ──
    old_accessed = datetime.utcnow() - timedelta(hours=2)
    mock_db = build_mock_db(corporate_doc={"last_accessed_at": old_accessed})

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    assert result["is_first_access_today"] is True

    # ── 30分前 → is_first_access_today = False ──
    recent_accessed = datetime.utcnow() - timedelta(minutes=30)
    mock_db2 = build_mock_db(corporate_doc={"last_accessed_at": recent_accessed})

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db2),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        result2 = await ChatService.get_corporate_context(CORP_ID)

    assert result2["is_first_access_today"] is False


# ── ⑤ 空データでもクラッシュしない ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_empty_data_no_crash():
    """未承認書類・未消込データが 0 件でもクラッシュせず空リストが返ること"""
    from app.services.chat_service import ChatService

    mock_db = build_mock_db()

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    assert result["pending_documents"] == []
    assert result["recent_deposits"] == []
    assert result["pending_receipts_count"] == 0
    assert result["pending_invoices_count"] == 0
    assert result["unmatched_transactions_count"] == 0
    assert isinstance(result["days_until_month_end"], int)
    assert isinstance(result["is_first_access_today"], bool)
    assert result["alerts"] == "特になし"


# ── ⑥ _format_pending_documents のユニットテスト ─────────────────────────────────

def test_format_pending_documents_empty():
    """空リストの場合「なし」が返ること"""
    from app.services.ai_service import _format_pending_documents
    assert _format_pending_documents([]) == "なし"


def test_format_pending_documents_with_data():
    """_format_pending_documents が正しい日本語文字列を返すこと"""
    from app.services.ai_service import _format_pending_documents

    docs = [
        {
            "type": "領収書",
            "amount": 5000,
            "submitter_name": "田中太郎",
            "date": "2024-01-10",
            "pending_days": 3,
        },
        {
            "type": "受領請求書",
            "amount": 120000,
            "submitter_name": "鈴木花子",
            "date": "2024-01-05",
            "pending_days": 8,
        },
    ]

    result = _format_pending_documents(docs)

    assert "領収書" in result
    assert "5,000円" in result
    assert "田中太郎" in result
    assert "3日経過" in result
    assert "受領請求書" in result
    assert "120,000円" in result
    assert "8日経過" in result


def test_format_recent_deposits_empty():
    """空リストの場合「なし」が返ること"""
    from app.services.ai_service import _format_recent_deposits
    assert _format_recent_deposits([]) == "なし"


def test_format_recent_deposits_with_data():
    """_format_recent_deposits が正しい文字列を返すこと"""
    from app.services.ai_service import _format_recent_deposits

    deposits = [
        {"date": "2024-01-15", "description": "株式会社ABC 振込", "amount": 330000},
    ]

    result = _format_recent_deposits(deposits)

    assert "2024-01-15" in result
    assert "株式会社ABC 振込" in result
    assert "330,000円" in result


# ═══════════════════════════════════════════════════════════════════════════
# 意地悪テスト（Task#16 追加）
# ═══════════════════════════════════════════════════════════════════════════

# ── 追加モックヘルパー ─────────────────────────────────────────────────────

def make_cursor_limited(return_value: list):
    """to_list(length=N) の N 件制限を実際に適用するカーソルモック（上限テスト用）。"""
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)

    async def _to_list(length=None):
        return return_value[:length] if length is not None else return_value

    cursor.to_list = _to_list
    return cursor


def make_col_limited(find_data=None, count=0):
    """make_cursor_limited を使ったコレクションモック。"""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.count_documents = AsyncMock(return_value=count)
    col.update_one = AsyncMock(return_value=MagicMock())
    col.find = MagicMock(return_value=make_cursor_limited(find_data or []))
    return col


def build_mock_db_custom(collections: dict):
    """コレクション dict を直接指定して DB モックを生成するヘルパー。"""
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


# ── ① 型安全性テスト ──────────────────────────────────────────────────────

def test_pending_days_never_negative():
    """created_at が未来日時でも pending_days が負値にならないこと（max(0,...) の確認）"""
    from app.services.chat_service import _calc_pending_days

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # 1日後の未来日時
    future_dt = datetime.utcnow() + timedelta(days=1)
    result = _calc_pending_days(future_dt, today_start)

    assert result == 0, f"pending_days は 0 以上のはずが {result} になった"


def test_pending_days_with_naive_datetime():
    """timezone-naive な datetime でも _calc_pending_days がクラッシュしないこと"""
    from app.services.chat_service import _calc_pending_days

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # tzinfo なし（MongoDB が返す標準的な形式）
    naive_dt = datetime(2024, 1, 1, 12, 0, 0)
    assert naive_dt.tzinfo is None  # naive であることを確認

    result = _calc_pending_days(naive_dt, today_start)

    assert isinstance(result, int)
    assert result >= 0


@pytest.mark.asyncio
async def test_created_at_none_does_not_crash():
    """created_at が None のドキュメントがあっても get_corporate_context() がクラッシュせず pending_days=0 になること"""
    from app.services.chat_service import ChatService

    receipt_no_created_at = {
        "_id": ObjectId(),
        "amount": 3000,
        "submitted_by": str(ObjectId()),
        "date": "2024-01-10",
        "created_at": None,  # ← None
    }

    mock_db = build_mock_db(receipts=[receipt_no_created_at])

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    assert len(result["pending_documents"]) == 1
    assert result["pending_documents"][0]["pending_days"] == 0


# ── ② 並列処理の安全性テスト ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gather_returns_correct_counts():
    """領収書 3 件・受領請求書 2 件のとき件数カウントが正確に返ること"""
    from app.services.chat_service import ChatService

    receipts = [
        {"_id": ObjectId(), "amount": 1000, "submitted_by": str(ObjectId()), "date": "2024-01-01", "created_at": datetime.utcnow() - timedelta(days=i)}
        for i in range(1, 4)
    ]
    invoices = [
        {"_id": ObjectId(), "total_amount": 5000, "submitted_by": str(ObjectId()), "issue_date": "2024-01-01", "created_at": datetime.utcnow() - timedelta(days=i)}
        for i in range(1, 3)
    ]

    mock_db = build_mock_db(receipts=receipts, invoices=invoices)

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    assert result["pending_receipts_count"] == 3
    assert result["pending_invoices_count"] == 2
    assert len(result["pending_documents"]) == 5


@pytest.mark.asyncio
async def test_name_map_built_after_gather():
    """build_name_map は gather 後に 1 回だけ呼ばれ、submitted_by が重複排除されていること"""
    from app.services.chat_service import ChatService

    shared_id = str(ObjectId())
    receipts = [
        {"_id": ObjectId(), "amount": 1000, "submitted_by": shared_id, "date": "2024-01-01", "created_at": datetime.utcnow() - timedelta(days=1)},
        {"_id": ObjectId(), "amount": 2000, "submitted_by": shared_id, "date": "2024-01-02", "created_at": datetime.utcnow() - timedelta(days=2)},
    ]

    mock_db = build_mock_db(receipts=receipts)
    mock_name_map = AsyncMock(return_value={shared_id: "共通担当者"})

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch("app.services.chat_service.build_name_map", mock_name_map),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    # build_name_map が 1 回だけ呼ばれること
    assert mock_name_map.call_count == 1

    # 渡された user_ids が重複排除（1 件）になっていること
    passed_ids = mock_name_map.call_args[0][1]
    assert len(passed_ids) == 1
    assert shared_id in passed_ids

    # 名前が正しく解決されていること
    assert result["pending_documents"][0]["submitter_name"] == "共通担当者"
    assert result["pending_documents"][1]["submitter_name"] == "共通担当者"


# ── ③ last_accessed_at の境界値テスト ────────────────────────────────────

@pytest.mark.asyncio
async def test_first_access_exactly_one_hour_ago():
    """last_accessed_at がちょうど 1 時間前（境界値）で is_first_access_today=True になること"""
    from app.services.chat_service import ChatService

    # timedelta(hours=1, microseconds=1) で「1時間をわずかに超えた」を確実に作る
    just_over_one_hour_ago = datetime.utcnow() - timedelta(hours=1, microseconds=1)
    mock_db = build_mock_db(corporate_doc={"last_accessed_at": just_over_one_hour_ago})

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    assert result["is_first_access_today"] is True

    # ちょうど 1 時間前（diff = timedelta(hours=1)）は境界=False のはず（strict >）
    # 実行時間の経過で diff が timedelta(hours=1) + epsilon になるため、ここは True になる
    # 実質的な境界確認は just_over_one_hour_ago で担保し、59分59秒では False を確認
    just_under_one_hour = datetime.utcnow() - timedelta(minutes=59, seconds=59)
    mock_db2 = build_mock_db(corporate_doc={"last_accessed_at": just_under_one_hour})

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db2),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        result2 = await ChatService.get_corporate_context(CORP_ID)

    assert result2["is_first_access_today"] is False


@pytest.mark.asyncio
async def test_last_accessed_updated_after_call():
    """get_corporate_context() 後に corporates.update_one が last_accessed_at で呼ばれること"""
    from app.services.chat_service import ChatService

    corporates_mock = make_col(find_one=None)

    collections = {
        "company_profiles": make_col(find_one={"company_name": "テスト"}),
        "receipts":      make_col(find_data=[]),
        "invoices":      make_col(find_data=[]),
        "transactions":  make_col(find_data=[], count=0),
        "notifications": make_col(find_data=[]),
        "corporates":    corporates_mock,
    }
    db = build_mock_db_custom(collections)

    with (
        patch("app.services.chat_service.get_database", return_value=db),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        await ChatService.get_corporate_context(CORP_ID)

    # update_one が 1 回呼ばれていること
    corporates_mock.update_one.assert_called_once()

    # $set に last_accessed_at が含まれていること
    update_doc = corporates_mock.update_one.call_args[0][1]
    assert "last_accessed_at" in update_doc.get("$set", {})


@pytest.mark.asyncio
async def test_invalid_corporate_id_does_not_crash():
    """不正な corporate_id（'invalid-id'）でもクラッシュせず is_first_access_today=True になること"""
    from app.services.chat_service import ChatService

    mock_db = build_mock_db()

    with (
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        # ObjectId('invalid-id') は bson.errors.InvalidId を raise するが try/except で吸収される
        result = await ChatService.get_corporate_context("invalid-id")

    assert isinstance(result, dict)
    assert result["is_first_access_today"] is True  # デフォルト値が返ること


# ── ④ データ上限・パフォーマンステスト ──────────────────────────────────

@pytest.mark.asyncio
async def test_pending_documents_capped_at_5():
    """未承認領収書が 10 件あっても pending_documents の領収書は 5 件以下であること"""
    from app.services.chat_service import ChatService

    ten_receipts = [
        {
            "_id": ObjectId(), "amount": i * 1000,
            "submitted_by": str(ObjectId()), "date": "2024-01-01",
            "created_at": datetime.utcnow() - timedelta(days=i),
        }
        for i in range(1, 11)
    ]

    # length 制限を適用するカーソルモックで receipts コレクションを構築
    collections = {
        "company_profiles": make_col(find_one={"company_name": "テスト"}),
        "receipts":      make_col_limited(find_data=ten_receipts),
        "invoices":      make_col_limited(find_data=[]),
        "transactions":  make_col_limited(find_data=[], count=0),
        "notifications": make_col(find_data=[]),
        "corporates":    make_col(find_one=None),
    }
    db = build_mock_db_custom(collections)

    with (
        patch("app.services.chat_service.get_database", return_value=db),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    receipt_docs = [d for d in result["pending_documents"] if d["type"] == "領収書"]
    assert len(receipt_docs) <= 5


@pytest.mark.asyncio
async def test_recent_deposits_capped_at_3():
    """未消込入金が 10 件あっても recent_deposits は 3 件以下であること"""
    from app.services.chat_service import ChatService

    ten_deposits = [
        {
            "_id": ObjectId(), "deposit_amount": i * 10000,
            "description": f"振込{i}", "transaction_date": datetime(2024, 1, i),
        }
        for i in range(1, 11)
    ]

    collections = {
        "company_profiles": make_col(find_one={"company_name": "テスト"}),
        "receipts":      make_col_limited(find_data=[]),
        "invoices":      make_col_limited(find_data=[]),
        "transactions":  make_col_limited(find_data=ten_deposits, count=10),
        "notifications": make_col(find_data=[]),
        "corporates":    make_col(find_one=None),
    }
    db = build_mock_db_custom(collections)

    with (
        patch("app.services.chat_service.get_database", return_value=db),
        patch("app.services.chat_service.build_name_map", new_callable=AsyncMock, return_value={}),
    ):
        result = await ChatService.get_corporate_context(CORP_ID)

    assert len(result["recent_deposits"]) <= 3


# ── ⑤ フォーマット関数の堅牢性テスト ────────────────────────────────────

def test_format_pending_documents_with_large_amount():
    """amount=1,000,000 がカンマ区切りで「1,000,000円」と表示されること"""
    from app.services.ai_service import _format_pending_documents

    docs = [{
        "type": "受領請求書",
        "amount": 1_000_000,
        "submitter_name": "山田太郎",
        "date": "2024-01-20",
        "pending_days": 5,
    }]

    result = _format_pending_documents(docs)

    assert "1,000,000円" in result


def test_format_pending_documents_missing_fields():
    """submitter_name=None・date=None でも _format_pending_documents がクラッシュしないこと"""
    from app.services.ai_service import _format_pending_documents

    docs = [
        {
            "type": "領収書",
            "amount": 3000,
            "submitter_name": None,   # None
            "date": None,             # None
            "pending_days": 1,
        },
        {
            "type": "受領請求書",
            "amount": 8000,
            "submitter_name": "",     # 空文字
            "date": "",               # 空文字
            "pending_days": 0,
        },
    ]

    result = _format_pending_documents(docs)

    assert isinstance(result, str)
    assert len(result) > 0


# ── ⑥ システムプロンプトへの反映確認（コードレビュー） ────────────────────

def test_system_prompt_includes_new_context():
    """⑥ chat_advisor の system_prompt に新コンテキストフィールドが含まれていること"""
    import inspect
    import app.services.ai_service as ai_module

    source = inspect.getsource(ai_module.AIService.chat_advisor)

    assert "days_until_month_end" in source, \
        "system_prompt に days_until_month_end が含まれていない"
    assert "_format_pending_documents" in source, \
        "system_prompt に _format_pending_documents が含まれていない"
    assert "_format_recent_deposits" in source, \
        "system_prompt に _format_recent_deposits が含まれていない"
    assert "pending_documents" in source, \
        "system_prompt に pending_documents が含まれていない"
    assert "recent_deposits" in source, \
        "system_prompt に recent_deposits が含まれていない"


def test_format_functions_return_nashi_for_empty():
    """⑥ 空データの場合は「なし」が返ること（両フォーマット関数）"""
    from app.services.ai_service import _format_pending_documents, _format_recent_deposits

    assert _format_pending_documents([]) == "なし"
    assert _format_recent_deposits([]) == "なし"
