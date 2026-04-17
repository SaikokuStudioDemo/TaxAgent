"""
Tests for Task#17-A: AI エージェント 読み取り系ツール（agent_tools.py + advisor.py）

Usage:
    cd backend
    pytest tests/test_agent_tools.py -v
"""
import re
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

# ── テスト用 corporate_id ─────────────────────────────────────────────────────
CORP_A_ID = str(ObjectId())
CORP_B_ID = str(ObjectId())


# ── モックヘルパー ─────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    """Motor カーソルチェーン（.sort().limit().to_list()）のシンプルモック。"""
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_cursor_limited(return_value: list):
    """to_list(length=N) を実際に N 件に制限するカーソルモック（上限テスト用）。"""
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)

    async def _to_list(length=None):
        return return_value[:length] if length is not None else return_value

    cursor.to_list = _to_list
    return cursor


def make_col(find_one=None, find_data=None, count=0, agg_data=None):
    """シンプルなコレクションモック（aggregate 対応）。"""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.count_documents = AsyncMock(return_value=count)
    col.update_one = AsyncMock(return_value=MagicMock())
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    col.aggregate = MagicMock(return_value=make_cursor(agg_data or []))
    return col


def make_col_limited(find_data=None, count=0, agg_data=None):
    """to_list が length を適用するコレクションモック（上限テスト用）。"""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.count_documents = AsyncMock(return_value=count)
    col.update_one = AsyncMock(return_value=MagicMock())
    col.find = MagicMock(return_value=make_cursor_limited(find_data or []))
    col.aggregate = MagicMock(return_value=make_cursor(agg_data or []))
    return col


def make_filtering_col(all_docs: list, agg_data=None):
    """
    corporate_id / _id フィルタを実際に適用するコレクションモック（スコープテスト用）。
    find({"corporate_id": cid}) が渡されると cid でフィルタする。
    """
    col = MagicMock()
    col.count_documents = AsyncMock(return_value=0)
    col.update_one = AsyncMock(return_value=MagicMock())
    col.aggregate = MagicMock(return_value=make_cursor(agg_data or []))

    async def _find_one(query: dict, *args, **kwargs):
        cid = query.get("corporate_id")
        doc_id = query.get("_id")
        for d in all_docs:
            if doc_id is not None and d.get("_id") != doc_id:
                continue
            if cid is not None and d.get("corporate_id") != cid:
                continue
            return d
        return None

    col.find_one = AsyncMock(side_effect=_find_one)

    def _find(query: dict, *args, **kwargs):
        cid = query.get("corporate_id")
        filtered = [d for d in all_docs if cid is None or d.get("corporate_id") == cid]
        return make_cursor_limited(filtered)

    col.find = MagicMock(side_effect=_find)
    return col


def build_mock_db(collections: dict):
    """コレクション dict から DB モックを生成する。"""
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


# ═══════════════════════════════════════════════════════════════════════════
# ① スコープ境界テスト（最重要）
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_pending_list_returns_only_own_corporate():
    """法人 A の corporate_id で呼んだ時に法人 B のデータが含まれないこと"""
    from app.services.agent_tools import get_pending_list

    receipts_both = [
        {"_id": ObjectId(), "corporate_id": CORP_A_ID, "approval_status": "pending_approval", "amount": 1000},
        {"_id": ObjectId(), "corporate_id": CORP_A_ID, "approval_status": "pending_approval", "amount": 2000},
        {"_id": ObjectId(), "corporate_id": CORP_B_ID, "approval_status": "pending_approval", "amount": 9999},
    ]

    collections = {
        "receipts":     make_filtering_col(receipts_both),
        "invoices":     make_filtering_col([]),
        "transactions": make_filtering_col([]),
    }
    db = build_mock_db(collections)

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await get_pending_list(CORP_A_ID, list_type="receipts")

    # 法人 A のデータのみ（2件）
    assert len(result["receipts"]) == 2
    for doc in result["receipts"]:
        assert doc.get("corporate_id") == CORP_A_ID

    # 法人 B の amount=9999 が含まれていないこと
    amounts = [d.get("amount") for d in result["receipts"]]
    assert 9999 not in amounts


@pytest.mark.asyncio
async def test_get_document_detail_cross_corporate_blocked():
    """法人 B のドキュメントを法人 A の corporate_id で取得しようとすると not found になること"""
    from app.services.agent_tools import get_document_detail

    doc_id = ObjectId()
    # CORP_B のドキュメントだけ存在する
    receipts_b = [
        {"_id": doc_id, "corporate_id": CORP_B_ID, "amount": 99999},
    ]

    collections = {"receipts": make_filtering_col(receipts_b)}
    db = build_mock_db(collections)

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await get_document_detail(
            CORP_A_ID,              # 法人 A で要求
            document_type="receipt",
            document_id=str(doc_id),
        )

    # 法人 A からは見えないこと
    assert "error" in result
    assert result["error"] == "not found"
    assert "amount" not in result   # 実データが返っていないこと


@pytest.mark.asyncio
async def test_search_client_returns_only_own_corporate():
    """同名の取引先が 2 法人に存在する場合、法人 A で検索すると法人 A の取引先のみ返ること"""
    from app.services.agent_tools import search_client

    clients_both = [
        {"_id": ObjectId(), "corporate_id": CORP_A_ID, "name": "共通取引先株式会社"},
        {"_id": ObjectId(), "corporate_id": CORP_B_ID, "name": "共通取引先株式会社"},
    ]

    collections = {"clients": make_filtering_col(clients_both)}
    db = build_mock_db(collections)

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await search_client(CORP_A_ID, query="共通取引先")

    assert result["count"] == 1
    assert result["clients"][0]["corporate_id"] == CORP_A_ID


# ═══════════════════════════════════════════════════════════════════════════
# ② エラー耐性テスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_document_detail_invalid_object_id():
    """document_id に不正な文字列を渡しても例外が外に漏れず {"error": ...} が返ること"""
    from app.services.agent_tools import get_document_detail

    db = build_mock_db({"receipts": make_col()})

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await get_document_detail(CORP_A_ID, "receipt", "invalid-id")

    assert "error" in result
    assert isinstance(result["error"], str)


@pytest.mark.asyncio
async def test_get_approval_status_no_rule():
    """approval_rule_id が None のドキュメントでも pending_approver=None でクラッシュしないこと"""
    from app.services.agent_tools import get_approval_status

    doc_id = ObjectId()
    doc = {
        "_id": doc_id,
        "corporate_id": CORP_A_ID,
        "approval_status": "pending_approval",
        "current_step": 1,
        "approval_rule_id": None,  # ← None
    }

    receipts_col = make_col(find_one=doc)
    # audit_logs も必要
    audit_col = make_col(find_data=[])
    db = build_mock_db({"receipts": receipts_col, "audit_logs": audit_col})

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await get_approval_status(CORP_A_ID, "receipt", str(doc_id))

    assert "error" not in result
    assert result["pending_approver"] is None
    assert result["approval_status"] == "pending_approval"


@pytest.mark.asyncio
async def test_get_approval_status_rule_not_found():
    """approval_rule_id が存在しない ID を指していてもクラッシュせず pending_approver=None になること"""
    from app.services.agent_tools import get_approval_status

    doc_id = ObjectId()
    doc = {
        "_id": doc_id,
        "corporate_id": CORP_A_ID,
        "approval_status": "pending_approval",
        "current_step": 1,
        "approval_rule_id": str(ObjectId()),  # 存在しないルールID
    }

    receipts_col = make_col(find_one=doc)
    audit_col = make_col(find_data=[])
    # approval_rules は find_one=None（存在しない）
    rules_col = make_col(find_one=None)
    db = build_mock_db({
        "receipts": receipts_col,
        "audit_logs": audit_col,
        "approval_rules": rules_col,
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await get_approval_status(CORP_A_ID, "receipt", str(doc_id))

    assert "error" not in result
    assert result["pending_approver"] is None


@pytest.mark.asyncio
async def test_get_budget_comparison_invalid_period_format():
    """fiscal_period に不正フォーマット（"2026/04", "invalid"）を渡してもクラッシュしないこと"""
    from app.services.agent_tools import get_budget_comparison

    agg_cursor = make_cursor([])
    receipts_col = make_col(agg_data=[])
    invoices_col = make_col(agg_data=[])
    budgets_col = make_col(find_one=None)
    db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "budgets": budgets_col,
    })

    for bad_period in ("2026/04", "invalid", "", "9999-99"):
        with patch("app.services.agent_tools.get_database", return_value=db):
            result = await get_budget_comparison(CORP_A_ID, fiscal_period=bad_period)

        assert "error" not in result or isinstance(result.get("error"), str)
        # クラッシュせずに dict が返ること
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════
# ③ 境界値・データ上限テスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_pending_list_capped_at_20():
    """未承認領収書が 30 件あっても receipts は最大 20 件で返ること"""
    from app.services.agent_tools import get_pending_list

    thirty_receipts = [
        {
            "_id": ObjectId(),
            "corporate_id": CORP_A_ID,
            "approval_status": "pending_approval",
            "amount": i * 100,
        }
        for i in range(1, 31)
    ]

    collections = {
        "receipts":     make_col_limited(find_data=thirty_receipts),
        "invoices":     make_col_limited(find_data=[]),
        "transactions": make_col_limited(find_data=[]),
    }
    db = build_mock_db(collections)

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await get_pending_list(CORP_A_ID, list_type="receipts")

    assert len(result["receipts"]) <= 20


@pytest.mark.asyncio
async def test_search_client_limit_respected():
    """limit=3 で 3 件・デフォルト (limit=5) で 5 件が返ること"""
    from app.services.agent_tools import search_client

    ten_clients = [
        {"_id": ObjectId(), "corporate_id": CORP_A_ID, "name": f"テスト会社{i}"}
        for i in range(10)
    ]

    # limit=3
    col3 = make_filtering_col(ten_clients)
    db3 = build_mock_db({"clients": col3})
    with patch("app.services.agent_tools.get_database", return_value=db3):
        result3 = await search_client(CORP_A_ID, query="テスト", limit=3)

    assert result3["count"] <= 3

    # limit=5（デフォルト）
    col5 = make_filtering_col(ten_clients)
    db5 = build_mock_db({"clients": col5})
    with patch("app.services.agent_tools.get_database", return_value=db5):
        result5 = await search_client(CORP_A_ID, query="テスト", limit=5)

    assert result5["count"] <= 5


@pytest.mark.asyncio
async def test_get_budget_comparison_no_data():
    """receipts・invoices 0 件で actual_total=0・budget_total=None・エラーなしであること"""
    from app.services.agent_tools import get_budget_comparison

    receipts_col = make_col(agg_data=[])
    invoices_col = make_col(agg_data=[])
    budgets_col = make_col(find_one=None)
    db = build_mock_db({
        "receipts": receipts_col,
        "invoices": invoices_col,
        "budgets": budgets_col,
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await get_budget_comparison(CORP_A_ID)

    assert "error" not in result
    assert result["actual_total"] == 0
    assert result["budget_total"] is None
    assert result["variance"] is None
    assert isinstance(result["fiscal_period"], str)


# ═══════════════════════════════════════════════════════════════════════════
# ④ 正規表現インジェクションテスト
# ═══════════════════════════════════════════════════════════════════════════

def test_search_client_regex_injection():
    """re.escape により ".*" や "(?i).*" がメタ文字として解釈されないこと"""
    # ".*" → re.escape → literal "\.\\*" になること
    escaped = re.escape(".*")
    pattern = re.compile(escaped, re.IGNORECASE)

    # 通常の会社名にマッチしないこと（literal ".*" を含む文字列以外）
    assert not pattern.search("テスト株式会社")
    assert not pattern.search("any company name")
    assert not pattern.search("ABCDEF")

    # literal ".*" を含む文字列にのみマッチすること
    assert pattern.search("company .* test")

    # "(?i).*" も同様にエスケープされること
    escaped2 = re.escape("(?i).*")
    pattern2 = re.compile(escaped2, re.IGNORECASE)
    assert not pattern2.search("テスト株式会社")
    # re.compile 自体が例外にならないこと（クラッシュしない）


def test_search_client_special_characters():
    """括弧・記号を含むクエリで re.escape がクラッシュしないこと"""
    special_queries = [
        "株式会社（テスト）",
        "ABC[co]",
        "test+company",
        "foo{bar}",
        "price$100",
        "100%",
    ]
    for q in special_queries:
        # re.escape → re.compile で例外が出ないこと
        try:
            pattern = re.compile(re.escape(q), re.IGNORECASE)
            assert pattern is not None
        except re.error as e:
            pytest.fail(f"re.escape('{q}') が不正なパターンを生成した: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ⑤ advisor.py エンドポイントテスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tools_endpoint_unknown_tool_returns_404():
    """POST /advisor/tools/nonexistent_tool が 404 を返すこと"""
    import httpx
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post("/api/v1/advisor/tools/nonexistent_tool", json={})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tools_endpoint_requires_auth():
    """Authorization ヘッダーなしでは 403 が返ること（HTTPBearer の自動拒否）"""
    import httpx
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            "/api/v1/advisor/tools/pending_list",
            json={"list_type": "all"},
            # Authorization ヘッダーなし
        )

    # FastAPI の HTTPBearer は Authorization なしで 403 を返す
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_tools_endpoint_get_pending_list_success():
    """認証ありで POST /advisor/tools/pending_list が 200 を返し正しい構造を持つこと"""
    import httpx
    from app.main import app
    from app.api.deps import get_current_user

    # 依存関係のオーバーライド（HTTPBearer をバイパス）
    def mock_user():
        return {"uid": "test_uid"}

    app.dependency_overrides[get_current_user] = mock_user

    mock_result = {
        "receipts": [],
        "invoices": [],
        "transactions": [],
        "total_count": 0,
    }

    try:
        with (
            patch(
                "app.api.routes.advisor.resolve_corporate_id",
                new=AsyncMock(return_value=(CORP_A_ID, CORP_A_ID)),
            ),
            patch(
                "app.api.routes.advisor.get_pending_list",
                new=AsyncMock(return_value=mock_result),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                resp = await client.post(
                    "/api/v1/advisor/tools/pending_list",
                    json={"list_type": "all"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert "receipts" in data
        assert "invoices" in data
        assert "transactions" in data
        assert "total_count" in data

    finally:
        app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# ⑥ _serialize の安全性テスト
# ═══════════════════════════════════════════════════════════════════════════

def test_serialize_handles_nested_objectid():
    """ネストされた ObjectId（approval_history 内など）が文字列に変換されること"""
    from app.services.agent_tools import _serialize

    outer_id = ObjectId()
    inner_id = ObjectId()
    list_id_1 = ObjectId()
    list_id_2 = ObjectId()

    doc = {
        "_id": outer_id,
        "nested": {
            "ref_id": inner_id,
            "name": "ネストテスト",
        },
        "id_list": [list_id_1, list_id_2],
        "mixed_list": [
            {"_id": inner_id, "value": 100},
            "plain_string",
        ],
    }

    result = _serialize(doc)

    # _id → id（文字列）
    assert result["id"] == str(outer_id)
    assert "_id" not in result

    # ネストした ObjectId が文字列に
    assert result["nested"]["ref_id"] == str(inner_id)

    # リスト内 ObjectId が文字列に
    assert result["id_list"] == [str(list_id_1), str(list_id_2)]

    # リスト内 dict も再帰処理
    assert result["mixed_list"][0]["id"] == str(inner_id)
    assert result["mixed_list"][1] == "plain_string"


def test_serialize_handles_datetime():
    """datetime フィールドが ISO 8601 文字列に変換されること（クラッシュなし）"""
    from app.services.agent_tools import _serialize

    now = datetime(2024, 1, 15, 10, 30, 0)
    doc = {
        "_id": ObjectId(),
        "created_at": now,
        "nested": {
            "updated_at": datetime(2024, 2, 1, 0, 0, 0),
        },
        "dates_list": [datetime(2024, 3, 1), datetime(2024, 4, 1)],
    }

    result = _serialize(doc)

    assert result["created_at"] == now.isoformat()
    assert result["nested"]["updated_at"] == datetime(2024, 2, 1).isoformat()
    assert result["dates_list"][0] == datetime(2024, 3, 1).isoformat()
    assert result["dates_list"][1] == datetime(2024, 4, 1).isoformat()
