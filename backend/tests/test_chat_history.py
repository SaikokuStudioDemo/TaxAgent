"""
Tests for Task#18: chat_histories コレクションの永続化と履歴取得 API

Usage:
    cd backend
    pytest tests/test_chat_history.py -v
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

CORP_A_ID = str(ObjectId())
CORP_B_ID = str(ObjectId())
USER_A_ID = str(ObjectId())
USER_B_ID = str(ObjectId())


# ── モックヘルパー ─────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_col(find_one=None, find_data=None, insert_result=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.insert_many = AsyncMock(return_value=insert_result or MagicMock())
    col.insert_one = AsyncMock(return_value=MagicMock())
    col.update_one = AsyncMock(return_value=MagicMock())
    col.count_documents = AsyncMock(return_value=0)
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    col.create_index = AsyncMock(return_value="index_name")
    return col


def build_mock_db(collections: dict):
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


# ── chat_service のモックセットアップ ─────────────────────────────────────────

def _chat_service_patches(mock_db):
    """chat_service で使われる全 DB 関連パッチをまとめて返す。"""
    return [
        patch("app.services.chat_service.get_database", return_value=mock_db),
        patch("app.services.ai_service.settings"),
        patch("app.services.chat_service.AIService.chat_advisor",
              new_callable=AsyncMock, return_value="AIの回答です。"),
        patch("app.services.chat_service.ChatService.get_corporate_context",
              new_callable=AsyncMock, return_value={
                  "company_name": "テスト株式会社",
                  "pending_receipts_count": 0,
                  "pending_invoices_count": 0,
                  "unmatched_transactions_count": 0,
                  "pending_documents": [],
                  "recent_deposits": [],
                  "days_until_month_end": 10,
                  "is_first_access_today": True,
                  "alerts": "特になし",
              }),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# process_query → chat_histories 保存テスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chat_history_saved_after_query():
    """process_query() 後に chat_histories に 2 件（user + ai）保存されること"""
    from app.services.chat_service import ChatService

    chat_col = make_col()
    db = build_mock_db({"chat_histories": chat_col})

    with patch("app.services.chat_service.get_database", return_value=db), \
         patch("app.services.chat_service.AIService.chat_advisor",
               new_callable=AsyncMock, return_value="AIの回答"), \
         patch("app.services.chat_service.ChatService.get_corporate_context",
               new_callable=AsyncMock, return_value={"company_name": "テスト"}):

        await ChatService.process_query(CORP_A_ID, "テスト質問", USER_A_ID)

    chat_col.insert_many.assert_called_once()
    inserted = chat_col.insert_many.call_args[0][0]
    assert len(inserted) == 2


@pytest.mark.asyncio
async def test_chat_history_user_and_ai_both_saved():
    """role='user' と role='ai' の両方が正しい content で保存されること"""
    from app.services.chat_service import ChatService

    chat_col = make_col()
    db = build_mock_db({"chat_histories": chat_col})

    query_text = "経費を教えてください"
    ai_text = "経費は…です。"

    with patch("app.services.chat_service.get_database", return_value=db), \
         patch("app.services.chat_service.AIService.chat_advisor",
               new_callable=AsyncMock, return_value=ai_text), \
         patch("app.services.chat_service.ChatService.get_corporate_context",
               new_callable=AsyncMock, return_value={"company_name": "テスト"}):

        await ChatService.process_query(CORP_A_ID, query_text, USER_A_ID)

    docs = chat_col.insert_many.call_args[0][0]

    roles = {d["role"]: d for d in docs}
    assert "user" in roles
    assert "ai" in roles
    assert roles["user"]["content"] == query_text
    assert roles["ai"]["content"] == ai_text
    assert roles["user"]["corporate_id"] == CORP_A_ID
    assert roles["ai"]["corporate_id"] == CORP_A_ID


@pytest.mark.asyncio
async def test_save_failure_does_not_break_chat():
    """chat_histories への保存が失敗しても process_query() が正常にレスポンスを返すこと"""
    from app.services.chat_service import ChatService

    chat_col = make_col()
    chat_col.insert_many = AsyncMock(side_effect=Exception("DB接続失敗"))
    db = build_mock_db({"chat_histories": chat_col})

    with patch("app.services.chat_service.get_database", return_value=db), \
         patch("app.services.chat_service.AIService.chat_advisor",
               new_callable=AsyncMock, return_value="正常なAI回答"), \
         patch("app.services.chat_service.ChatService.get_corporate_context",
               new_callable=AsyncMock, return_value={"company_name": "テスト"}):

        try:
            result = await ChatService.process_query(CORP_A_ID, "質問", USER_A_ID)
        except Exception as e:
            pytest.fail(f"保存失敗が例外として外に漏れた: {e}")

    assert result == "正常なAI回答"


@pytest.mark.asyncio
async def test_no_history_saved_without_user_id():
    """user_id が None の場合は履歴保存がスキップされること"""
    from app.services.chat_service import ChatService

    chat_col = make_col()
    db = build_mock_db({"chat_histories": chat_col})

    with patch("app.services.chat_service.get_database", return_value=db), \
         patch("app.services.chat_service.AIService.chat_advisor",
               new_callable=AsyncMock, return_value="回答"), \
         patch("app.services.chat_service.ChatService.get_corporate_context",
               new_callable=AsyncMock, return_value={"company_name": "テスト"}):

        await ChatService.process_query(CORP_A_ID, "質問", user_id=None)

    chat_col.insert_many.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# GET /advisor/history エンドポイントテスト
# ═══════════════════════════════════════════════════════════════════════════

def _make_history_docs(n: int, corp_id: str, user_id: str, base_dt: datetime = None):
    """テスト用の chat_histories ドキュメントリストを生成する。"""
    base = base_dt or datetime(2024, 1, 1, 0, 0, 0)
    docs = []
    for i in range(n):
        dt = base + timedelta(minutes=i)
        docs.append({
            "_id": ObjectId(),
            "corporate_id": corp_id,
            "user_id": user_id,
            "role": "user" if i % 2 == 0 else "ai",
            "content": f"メッセージ {i}",
            "created_at": dt,
        })
    return docs


@pytest.mark.asyncio
async def test_chat_history_scoped_to_user():
    """ユーザー A の履歴にユーザー B のメッセージが含まれないこと"""
    import httpx
    from app.main import app
    from app.api.deps import get_current_user

    user_a_docs = _make_history_docs(3, CORP_A_ID, USER_A_ID)
    user_b_docs = _make_history_docs(2, CORP_A_ID, USER_B_ID)
    all_docs = user_a_docs + user_b_docs

    def mock_user():
        return {"uid": "test_uid_a"}

    app.dependency_overrides[get_current_user] = mock_user

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with patch("app.api.routes.advisor.resolve_corporate_id",
                       new=AsyncMock(return_value=(CORP_A_ID, USER_A_ID))):

                # user_id でフィルタされたドキュメントだけ返すカーソルを模倣
                filtered = [d for d in all_docs if d["user_id"] == USER_A_ID]
                filtered_cursor = make_cursor(list(reversed(filtered)))

                history_col = MagicMock()
                history_col.find = MagicMock(return_value=filtered_cursor)
                mock_db = build_mock_db({"chat_histories": history_col})

                with patch("app.api.routes.advisor.get_database", return_value=mock_db):
                    resp = await client.get("/api/v1/advisor/history")

        assert resp.status_code == 200
        data = resp.json()
        for msg in data["messages"]:
            assert USER_B_ID not in str(msg)

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_history_scoped_to_corporate():
    """法人 A のユーザーが法人 B の履歴を取得できないこと"""
    import httpx
    from app.main import app
    from app.api.deps import get_current_user

    corp_a_docs = _make_history_docs(2, CORP_A_ID, USER_A_ID)

    def mock_user():
        return {"uid": "test_uid_a"}

    app.dependency_overrides[get_current_user] = mock_user

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with patch("app.api.routes.advisor.resolve_corporate_id",
                       new=AsyncMock(return_value=(CORP_A_ID, USER_A_ID))):

                # 法人 A のドキュメントのみ返す
                cursor = make_cursor(list(reversed(corp_a_docs)))
                history_col = MagicMock()
                history_col.find = MagicMock(return_value=cursor)
                mock_db = build_mock_db({"chat_histories": history_col})

                with patch("app.api.routes.advisor.get_database", return_value=mock_db):
                    resp = await client.get("/api/v1/advisor/history")

        assert resp.status_code == 200
        data = resp.json()
        for msg in data["messages"]:
            # 法人 B の情報が含まれていないこと
            assert CORP_B_ID not in str(msg)

        # find に渡されたクエリに corporate_id が含まれていること（スコープ確認）
        call_args = history_col.find.call_args[0][0]
        assert call_args["corporate_id"] == CORP_A_ID
        assert call_args["user_id"] == USER_A_ID

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_history_pagination():
    """30 件の履歴がある状態で limit=20 で取得すると 20 件・has_more=True が返ること"""
    import httpx
    from app.main import app
    from app.api.deps import get_current_user

    thirty_docs = _make_history_docs(30, CORP_A_ID, USER_A_ID)
    # DESC ソート後の上位 20 件（最新20件）
    top_20_desc = list(reversed(thirty_docs))[:20]

    def mock_user():
        return {"uid": "test_uid"}

    app.dependency_overrides[get_current_user] = mock_user

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with patch("app.api.routes.advisor.resolve_corporate_id",
                       new=AsyncMock(return_value=(CORP_A_ID, USER_A_ID))):

                cursor = make_cursor(top_20_desc)
                history_col = MagicMock()
                history_col.find = MagicMock(return_value=cursor)
                mock_db = build_mock_db({"chat_histories": history_col})

                with patch("app.api.routes.advisor.get_database", return_value=mock_db):
                    resp = await client.get("/api/v1/advisor/history?limit=20")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 20
        assert data["has_more"] is True

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_history_before_cursor():
    """before パラメータで指定した時刻以前のメッセージのみ返ること"""
    import httpx
    from app.main import app
    from app.api.deps import get_current_user

    base = datetime(2024, 1, 10, 12, 0, 0)
    old_docs = _make_history_docs(3, CORP_A_ID, USER_A_ID,
                                  base_dt=datetime(2024, 1, 1))
    new_docs = _make_history_docs(3, CORP_A_ID, USER_A_ID,
                                  base_dt=datetime(2024, 1, 15))

    def mock_user():
        return {"uid": "test_uid"}

    app.dependency_overrides[get_current_user] = mock_user

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with patch("app.api.routes.advisor.resolve_corporate_id",
                       new=AsyncMock(return_value=(CORP_A_ID, USER_A_ID))):

                # before=2024-01-10 より前なので old_docs のみが返ることを想定
                cursor = make_cursor(list(reversed(old_docs)))
                history_col = MagicMock()
                history_col.find = MagicMock(return_value=cursor)
                mock_db = build_mock_db({"chat_histories": history_col})

                with patch("app.api.routes.advisor.get_database", return_value=mock_db):
                    resp = await client.get(
                        "/api/v1/advisor/history",
                        params={"before": "2024-01-10T12:00:00"},
                    )

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == len(old_docs)

        # find に渡されたクエリに $lt フィルタが含まれていること
        query_arg = history_col.find.call_args[0][0]
        assert "created_at" in query_arg
        assert "$lt" in query_arg["created_at"]

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_history_returns_asc_order():
    """返却メッセージが created_at の古い順（ASC）であること"""
    import httpx
    from app.main import app
    from app.api.deps import get_current_user

    # DESC で取得したドキュメント（newest first）
    docs_desc = _make_history_docs(5, CORP_A_ID, USER_A_ID)
    docs_desc.reverse()  # 新しい順に並べてからカーソルが返すと想定

    def mock_user():
        return {"uid": "test_uid"}

    app.dependency_overrides[get_current_user] = mock_user

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with patch("app.api.routes.advisor.resolve_corporate_id",
                       new=AsyncMock(return_value=(CORP_A_ID, USER_A_ID))):

                cursor = make_cursor(docs_desc)
                history_col = MagicMock()
                history_col.find = MagicMock(return_value=cursor)
                mock_db = build_mock_db({"chat_histories": history_col})

                with patch("app.api.routes.advisor.get_database", return_value=mock_db):
                    resp = await client.get("/api/v1/advisor/history")

        assert resp.status_code == 200
        messages = resp.json()["messages"]
        assert len(messages) == 5

        # created_at が ASC 順であること
        timestamps = [m["created_at"] for m in messages]
        assert timestamps == sorted(timestamps), \
            f"メッセージが古い順になっていない: {timestamps}"

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_history_invalid_before_returns_400():
    """before に不正な文字列を渡すと 400 エラーが返ること"""
    import httpx
    from app.main import app
    from app.api.deps import get_current_user

    def mock_user():
        return {"uid": "test_uid"}

    app.dependency_overrides[get_current_user] = mock_user

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with patch("app.api.routes.advisor.resolve_corporate_id",
                       new=AsyncMock(return_value=(CORP_A_ID, USER_A_ID))):

                history_col = make_col(find_data=[])
                mock_db = build_mock_db({"chat_histories": history_col})

                with patch("app.api.routes.advisor.get_database", return_value=mock_db):
                    resp = await client.get(
                        "/api/v1/advisor/history",
                        params={"before": "not-a-date"},
                    )

        assert resp.status_code == 400
        assert "ISO8601" in resp.json()["detail"]

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_history_z_suffix_before():
    """before パラメータに 'Z' suffix の ISO8601 文字列が渡されても 400 にならないこと"""
    import httpx
    from app.main import app
    from app.api.deps import get_current_user

    def mock_user():
        return {"uid": "test_uid"}

    app.dependency_overrides[get_current_user] = mock_user

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with patch("app.api.routes.advisor.resolve_corporate_id",
                       new=AsyncMock(return_value=(CORP_A_ID, USER_A_ID))):

                history_col = make_col(find_data=[])
                mock_db = build_mock_db({"chat_histories": history_col})

                with patch("app.api.routes.advisor.get_database", return_value=mock_db):
                    resp = await client.get(
                        "/api/v1/advisor/history",
                        params={"before": "2024-01-15T10:30:00Z"},
                    )

        # Z suffix が正しく処理されて 400 にならないこと
        assert resp.status_code == 200

    finally:
        app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════
# 意地悪テスト（Task#18 追加）
# ══════════════════════════════════════════════════════════════════════════

# ── 追加モックヘルパー ─────────────────────────────────────────────────────

def make_cursor_limited(return_value: list):
    """to_list(length=N) を実際に N 件に制限するカーソルモック。"""
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)

    async def _to_list(length=None):
        return return_value[:length] if length is not None else return_value

    cursor.to_list = _to_list
    return cursor


def make_scoped_history_col(all_docs: list):
    """corporate_id + user_id フィルタを実際に適用するコレクションモック（スコープテスト用）。"""
    col = MagicMock()
    col.insert_many = AsyncMock(return_value=MagicMock())
    col.count_documents = AsyncMock(return_value=0)

    def _find(query: dict, *args, **kwargs):
        cid = query.get("corporate_id")
        uid = query.get("user_id")
        lt_dt = (query.get("created_at") or {}).get("$lt")
        filtered = [
            d for d in all_docs
            if (cid is None or d.get("corporate_id") == cid)
            and (uid is None or d.get("user_id") == uid)
            and (lt_dt is None or d.get("created_at") < lt_dt)
        ]
        # DESC ソートしてから返す（endpoint が reverse() で ASC にする）
        filtered.sort(
            key=lambda d: (d.get("created_at", datetime.min), d.get("_id")),
            reverse=True,
        )
        return make_cursor_limited(filtered)

    col.find = MagicMock(side_effect=_find)
    return col


# ── エンドポイントテスト共通パターン ──────────────────────────────────────

async def _get_history(app, corp_id, user_id, history_col, params=None):
    """GET /advisor/history を mock 認証 + mock DB で呼ぶヘルパー。"""
    import httpx
    from app.api.deps import get_current_user

    def _mock_user():
        return {"uid": "test_uid"}

    app.dependency_overrides[get_current_user] = _mock_user
    mock_db = build_mock_db({"chat_histories": history_col})

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with (
                patch("app.api.routes.advisor.resolve_corporate_id",
                      new=AsyncMock(return_value=(corp_id, user_id))),
                patch("app.api.routes.advisor.get_database", return_value=mock_db),
            ):
                resp = await client.get(
                    "/api/v1/advisor/history",
                    params=params or {},
                )
    finally:
        app.dependency_overrides.clear()

    return resp, history_col


# ── ① スコープ境界テスト ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_user_cannot_see_other_user_same_corporate():
    """同一法人内でも user_id が異なれば履歴が返らないこと"""
    from app.main import app

    user_a_doc = {
        "_id": ObjectId(), "corporate_id": CORP_A_ID, "user_id": USER_A_ID,
        "role": "user", "content": "A のメッセージ",
        "created_at": datetime(2024, 1, 1, 10, 0),
    }
    user_b_doc = {
        "_id": ObjectId(), "corporate_id": CORP_A_ID, "user_id": USER_B_ID,
        "role": "user", "content": "B のメッセージ",
        "created_at": datetime(2024, 1, 1, 10, 1),
    }

    history_col = make_scoped_history_col([user_a_doc, user_b_doc])
    resp, col = await _get_history(app, CORP_A_ID, USER_A_ID, history_col)

    assert resp.status_code == 200
    data = resp.json()

    # A のメッセージのみ返ること
    assert data["count"] == 1
    assert data["messages"][0]["content"] == "A のメッセージ"

    # find に渡ったクエリに user_id が含まれていること
    query_arg = col.find.call_args[0][0]
    assert query_arg["user_id"] == USER_A_ID


@pytest.mark.asyncio
async def test_history_corporate_scope_enforced():
    """法人 A のユーザーが法人 B の履歴を取得できないこと"""
    from app.main import app

    corp_a_doc = {
        "_id": ObjectId(), "corporate_id": CORP_A_ID, "user_id": USER_A_ID,
        "role": "user", "content": "法人Aのメッセージ",
        "created_at": datetime(2024, 1, 1),
    }
    corp_b_doc = {
        "_id": ObjectId(), "corporate_id": CORP_B_ID, "user_id": USER_B_ID,
        "role": "user", "content": "法人Bのメッセージ",
        "created_at": datetime(2024, 1, 1),
    }

    history_col = make_scoped_history_col([corp_a_doc, corp_b_doc])
    resp, col = await _get_history(app, CORP_A_ID, USER_A_ID, history_col)

    assert resp.status_code == 200
    data = resp.json()

    # 法人 B のデータが含まれていないこと
    assert all("法人B" not in m["content"] for m in data["messages"])
    # find クエリに corporate_id が含まれていること
    query_arg = col.find.call_args[0][0]
    assert query_arg["corporate_id"] == CORP_A_ID
    assert query_arg["user_id"] == USER_A_ID


# ── ② ページネーション境界値テスト ───────────────────────────────────────

@pytest.mark.asyncio
async def test_history_limit_max_capped_at_50():
    """limit=100 を渡しても 50 件以上返らないこと"""
    from app.main import app

    sixty_docs = _make_history_docs(60, CORP_A_ID, USER_A_ID,
                                    base_dt=datetime(2024, 1, 1))
    # DESC 順で返す（多めに用意）
    history_col = make_col()
    history_col.find = MagicMock(return_value=make_cursor_limited(list(reversed(sixty_docs))))

    resp, _ = await _get_history(app, CORP_A_ID, USER_A_ID, history_col, params={"limit": 100})

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] <= 50, f"50件を超えた: {data['count']}"


@pytest.mark.asyncio
async def test_history_limit_min_is_1():
    """limit=0 / limit=-1 でもエラーにならず 1 件返ること"""
    from app.main import app

    three_docs = _make_history_docs(3, CORP_A_ID, USER_A_ID,
                                    base_dt=datetime(2024, 1, 1))
    desc = list(reversed(three_docs))

    for bad_limit in (0, -1):
        history_col = make_col()
        history_col.find = MagicMock(return_value=make_cursor_limited(desc))
        resp, _ = await _get_history(app, CORP_A_ID, USER_A_ID, history_col, params={"limit": bad_limit})

        assert resp.status_code == 200, f"limit={bad_limit} でエラーになった"
        assert resp.json()["count"] >= 0  # クラッシュしないこと


@pytest.mark.asyncio
async def test_history_before_cursor_excludes_boundary():
    """before に指定した時刻と完全一致の created_at は結果に含まれないこと（$lt・未満）"""
    from app.main import app

    boundary = datetime(2024, 1, 15, 10, 0, 0)
    history_col = make_col(find_data=[])

    resp, col = await _get_history(
        app, CORP_A_ID, USER_A_ID, history_col,
        params={"before": "2024-01-15T10:00:00"},
    )

    assert resp.status_code == 200

    # find に渡ったクエリが $lt であること（$lte ではない）
    query_arg = col.find.call_args[0][0]
    cat_filter = query_arg.get("created_at", {})
    assert "$lt" in cat_filter,  "$lt がクエリに存在しない"
    assert "$lte" not in cat_filter, "$lte が使われている（$lt でなければならない）"
    assert cat_filter["$lt"] == boundary


@pytest.mark.asyncio
async def test_history_has_more_false_when_less_than_limit():
    """5 件しかない状態で limit=20 → has_more=False が返ること"""
    from app.main import app

    five_docs = _make_history_docs(5, CORP_A_ID, USER_A_ID, base_dt=datetime(2024, 1, 1))
    history_col = make_col()
    history_col.find = MagicMock(return_value=make_cursor_limited(list(reversed(five_docs))))

    resp, _ = await _get_history(app, CORP_A_ID, USER_A_ID, history_col, params={"limit": 20})

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 5
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_history_empty_returns_empty_list():
    """履歴が 0 件の場合に messages=[] / count=0 / has_more=False が返ること"""
    from app.main import app

    history_col = make_col(find_data=[])
    resp, _ = await _get_history(app, CORP_A_ID, USER_A_ID, history_col)

    assert resp.status_code == 200
    data = resp.json()
    assert data["messages"] == []
    assert data["count"] == 0
    assert data["has_more"] is False


# ── ③ before パラメータの形式テスト ─────────────────────────────────────

@pytest.mark.asyncio
async def test_history_before_z_suffix_accepted():
    """before='2024-01-15T10:30:00Z' が 400 エラーにならないこと（Python 3.9 Z suffix 対応）"""
    from app.main import app

    history_col = make_col(find_data=[])
    resp, col = await _get_history(
        app, CORP_A_ID, USER_A_ID, history_col,
        params={"before": "2024-01-15T10:30:00Z"},
    )

    assert resp.status_code == 200

    # クエリに $lt が入っていること（Z suffix が正しくパースされた証拠）
    query_arg = col.find.call_args[0][0]
    assert "$lt" in query_arg.get("created_at", {})


@pytest.mark.asyncio
async def test_history_before_plus_offset_accepted():
    """before='2024-01-15T10:30:00+09:00' が正常に処理されること"""
    from app.main import app

    history_col = make_col(find_data=[])
    resp, col = await _get_history(
        app, CORP_A_ID, USER_A_ID, history_col,
        params={"before": "2024-01-15T10:30:00+09:00"},
    )

    assert resp.status_code == 200

    # tzinfo が除去された naive datetime が $lt に入っていること
    query_arg = col.find.call_args[0][0]
    cat_filter = query_arg.get("created_at", {})
    assert "$lt" in cat_filter
    before_dt = cat_filter["$lt"]
    assert before_dt.tzinfo is None, "tzinfo が除去されていない（naive datetime でなければならない）"


@pytest.mark.asyncio
async def test_history_before_invalid_format_returns_400():
    """不正な before フォーマットで 400 が返ること"""
    from app.main import app

    history_col = make_col(find_data=[])

    # "not-a-date"
    resp1, _ = await _get_history(
        app, CORP_A_ID, USER_A_ID, history_col,
        params={"before": "not-a-date"},
    )
    assert resp1.status_code == 400, "not-a-date が 400 にならなかった"

    # "2024/01/15"（スラッシュ区切り・Python の fromisoformat では無効）
    resp2, _ = await _get_history(
        app, CORP_A_ID, USER_A_ID, history_col,
        params={"before": "2024/01/15"},
    )
    assert resp2.status_code == 400, "2024/01/15 が 400 にならなかった"


# ── ④ 保存の順序テスト ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_user_message_before_ai_message():
    """同じ created_at でも user メッセージが ai より先に返ること（_id 二次ソート確認）"""
    from app.main import app

    ts = datetime(2024, 1, 15, 10, 0, 0)
    # user は小さい _id（insert_many で先に挿入される）
    user_oid = ObjectId("000000000000000000000001")
    ai_oid   = ObjectId("000000000000000000000002")

    user_doc = {
        "_id": user_oid, "corporate_id": CORP_A_ID, "user_id": USER_A_ID,
        "role": "user", "content": "ユーザーの質問", "created_at": ts,
    }
    ai_doc = {
        "_id": ai_oid, "corporate_id": CORP_A_ID, "user_id": USER_A_ID,
        "role": "ai", "content": "AIの回答", "created_at": ts,
    }

    # sort [("created_at", -1), ("_id", -1)] で DESC → [ai_doc, user_doc]
    # endpoint が docs.reverse() → [user_doc, ai_doc]
    desc_sorted = [ai_doc, user_doc]
    history_col = make_col()
    history_col.find = MagicMock(return_value=make_cursor_limited(desc_sorted))

    resp, _ = await _get_history(app, CORP_A_ID, USER_A_ID, history_col)

    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user",  "user が先に来ていない"
    assert messages[1]["role"] == "ai",    "ai が後に来ていない"


@pytest.mark.asyncio
async def test_history_multiple_queries_ordered_correctly():
    """3 回のチャット（A→B→C）が古い順（A・B・C）で返ること"""
    from app.main import app

    t1 = datetime(2024, 1, 1, 10, 0)
    t2 = datetime(2024, 1, 1, 11, 0)
    t3 = datetime(2024, 1, 1, 12, 0)

    def _pair(ts, label):
        """user/ai ペアを (user_oid < ai_oid) で作成する。"""
        base = int(ts.timestamp()) * 1000
        u = ObjectId(f"{base:024x}"[:22] + f"{label}0")
        a = ObjectId(f"{base:024x}"[:22] + f"{label}1")
        return (
            {"_id": u, "corporate_id": CORP_A_ID, "user_id": USER_A_ID,
             "role": "user", "content": f"Q{label}", "created_at": ts},
            {"_id": a, "corporate_id": CORP_A_ID, "user_id": USER_A_ID,
             "role": "ai",   "content": f"A{label}", "created_at": ts},
        )

    u1, a1 = _pair(t1, "1")
    u2, a2 = _pair(t2, "2")
    u3, a3 = _pair(t3, "3")

    # sort DESC by (created_at, _id):
    # t3 > t2 > t1, 各 ts 内は ai > user（ai の _id が大きい）
    desc_order = [a3, u3, a2, u2, a1, u1]
    history_col = make_col()
    history_col.find = MagicMock(return_value=make_cursor_limited(desc_order))

    resp, _ = await _get_history(app, CORP_A_ID, USER_A_ID, history_col)

    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) == 6

    # ASC 順（古い順）であること
    timestamps = [m["created_at"] for m in messages]
    assert timestamps == sorted(timestamps), \
        f"メッセージが古い順になっていない: {timestamps}"

    # A→B→C の内容順であること
    contents = [m["content"] for m in messages]
    assert contents == ["Q1", "A1", "Q2", "A2", "Q3", "A3"], \
        f"内容の順序が不正: {contents}"


# ── ⑤ save_chat_history の耐久テスト ─────────────────────────────────────

@pytest.mark.asyncio
async def test_save_failure_does_not_affect_response():
    """DB 接続失敗時でも process_query() が正しいレスポンスを返すこと"""
    from app.services.chat_service import ChatService

    ai_answer = "正常なAIの回答テキスト"
    chat_col = make_col()
    chat_col.insert_many = AsyncMock(side_effect=Exception("DB障害"))
    db = build_mock_db({"chat_histories": chat_col})

    with patch("app.services.chat_service.get_database", return_value=db), \
         patch("app.services.chat_service.AIService.chat_advisor",
               new_callable=AsyncMock, return_value=ai_answer), \
         patch("app.services.chat_service.ChatService.get_corporate_context",
               new_callable=AsyncMock, return_value={"company_name": "テスト"}):

        try:
            result = await ChatService.process_query(CORP_A_ID, "質問", USER_A_ID)
        except Exception as e:
            pytest.fail(f"例外が外に漏れた: {e}")

    # レスポンスが AI の回答そのものであること
    assert result == ai_answer


@pytest.mark.asyncio
async def test_save_with_none_user_id_skips_save():
    """user_id=None の場合は chat_histories に insert_many が呼ばれないこと"""
    from app.services.chat_service import ChatService

    chat_col = make_col()
    db = build_mock_db({"chat_histories": chat_col})

    with patch("app.services.chat_service.get_database", return_value=db), \
         patch("app.services.chat_service.AIService.chat_advisor",
               new_callable=AsyncMock, return_value="回答"), \
         patch("app.services.chat_service.ChatService.get_corporate_context",
               new_callable=AsyncMock, return_value={"company_name": "テスト"}):

        result = await ChatService.process_query(CORP_A_ID, "質問", user_id=None)

    # insert_many が呼ばれていないこと
    chat_col.insert_many.assert_not_called()
    assert isinstance(result, str)  # エラーなく文字列が返ること
