"""
Tests for Task#21: GET /advisor/greeting・generate_greeting()

Usage:
    cd backend
    pytest tests/test_greeting.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

CORP_ID = str(ObjectId())
USER_ID = str(ObjectId())


# ── モックヘルパー ─────────────────────────────────────────────────────────────

def _base_context(**overrides) -> dict:
    """generate_greeting() に渡す最小コンテキストを生成する。"""
    base = {
        "company_name": "テスト株式会社",
        "is_first_access_today": True,
        "pending_receipts_count": 0,
        "pending_invoices_count": 0,
        "unmatched_transactions_count": 0,
        "pending_documents": [],
        "recent_deposits": [],
        "days_until_month_end": 10,
        "alerts": "特になし",
    }
    base.update(overrides)
    return base


def _make_emp_col(name: str = ""):
    """employees コレクションのモックを生成する。"""
    col = MagicMock()
    emp_doc = {"_id": ObjectId(USER_ID), "name": name} if name else None
    col.find_one = AsyncMock(return_value=emp_doc)
    return col


def _make_db(emp_name: str = ""):
    """② chat_service.get_database のモック DB を生成する。"""
    db = MagicMock()
    db.__getitem__ = MagicMock(
        side_effect=lambda k: _make_emp_col(emp_name) if k == "employees" else MagicMock()
    )
    return db


# ── ルールベース挨拶のテスト ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_greeting_first_access_uses_ohayou():
    """is_first_access_today=True の場合に「おはようございます」が含まれること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(is_first_access_today=True)),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "おはようございます" in result
    assert "おかえりなさい" not in result


@pytest.mark.asyncio
async def test_greeting_revisit_uses_okaerinasai():
    """is_first_access_today=False の場合に「おかえりなさい」が含まれること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(is_first_access_today=False)),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "おかえりなさい" in result
    assert "おはようございます" not in result


@pytest.mark.asyncio
async def test_greeting_with_name_includes_name():
    """employees に name がある場合に「田中さん」のように名前が含まれること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context()),
        patch("app.services.chat_service.get_database",
              return_value=_make_db(emp_name="田中太郎")),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "田中太郎さん" in result


@pytest.mark.asyncio
async def test_greeting_no_tasks_returns_simple_message():
    """pending・unmatched・deposits が全て 0 の場合に「対応が必要な作業はありません」が含まれること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         pending_receipts_count=0,
                         pending_invoices_count=0,
                         unmatched_transactions_count=0,
                         recent_deposits=[],
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "対応が必要な作業はありません" in result


@pytest.mark.asyncio
async def test_greeting_with_pending_receipts():
    """pending_receipts_count=3 の場合に「未承認の領収書が3件」が含まれること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(pending_receipts_count=3)),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "未承認の領収書が3件" in result


@pytest.mark.asyncio
async def test_greeting_with_deadline_warning():
    """days_until_month_end=2 の場合に「締め日まであと2日」が含まれること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         days_until_month_end=2,
                         pending_receipts_count=1,  # 警告を表示させるためタスクを1件追加
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "締め日まであと2日" in result


@pytest.mark.asyncio
async def test_greeting_deadline_not_shown_when_far():
    """days_until_month_end=10 の場合に締め日の警告が含まれないこと"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         days_until_month_end=10,
                         pending_receipts_count=2,
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "締め日" not in result


@pytest.mark.asyncio
async def test_greeting_no_user_id_still_works():
    """user_id=None でもクラッシュせず名前なしの挨拶が返ること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context()),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, user_id=None)

    assert isinstance(result, str)
    assert len(result) > 0
    # 名前なしなので「さん」を含まないこと（「おはようございます。」の形）
    assert "、" not in result.split("\n")[0] or "さん" not in result.split("\n")[0]


# ── エンドポイントテスト ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_greeting_endpoint_returns_200():
    """GET /advisor/greeting が 200 を返し greeting キーを持つこと"""
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
            with (
                patch("app.api.routes.advisor.resolve_corporate_id",
                      new=AsyncMock(return_value=(CORP_ID, USER_ID))),
                patch("app.api.routes.advisor.ChatService.generate_greeting",
                      new=AsyncMock(return_value="おはようございます。")),
            ):
                resp = await client.get("/api/v1/advisor/greeting")

        assert resp.status_code == 200
        data = resp.json()
        assert "greeting" in data
        assert isinstance(data["greeting"], str)
        assert len(data["greeting"]) > 0

    finally:
        app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════
# 意地悪テスト（Task#21 追加）
# ══════════════════════════════════════════════════════════════════════════

# ── ① 挨拶文の境界値テスト ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_greeting_deadline_exactly_3_days_shows_warning():
    """days_until_month_end=3 の場合に締め日警告が表示されること（境界値・含む）"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         days_until_month_end=3,
                         pending_receipts_count=1,   # 警告表示に必要なタスクを1件追加
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "締め日まであと3日" in result


@pytest.mark.asyncio
async def test_greeting_deadline_exactly_0_days_shows_warning():
    """days_until_month_end=0 の場合に「締め日まであと0日」が含まれること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         days_until_month_end=0,
                         pending_receipts_count=1,
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "締め日まであと0日" in result


@pytest.mark.asyncio
async def test_greeting_deadline_negative_not_shown():
    """days_until_month_end=-1 の場合に締め日警告が含まれないこと（月またぎの安全確認）"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         days_until_month_end=-1,
                         pending_receipts_count=1,
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "締め日" not in result


# ── ② 名前取得の耐久テスト ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_greeting_name_fetch_db_error_uses_no_name():
    """employees.find_one が例外を投げた場合でもクラッシュせず名前なしの挨拶が返ること"""
    from app.services.chat_service import ChatService

    error_col = MagicMock()
    error_col.find_one = AsyncMock(side_effect=Exception("DB接続エラー"))
    error_db = MagicMock()
    error_db.__getitem__ = MagicMock(return_value=error_col)

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context()),
        patch("app.services.chat_service.get_database", return_value=error_db),
    ):
        try:
            result = await ChatService.generate_greeting(CORP_ID, USER_ID)
        except Exception as e:
            pytest.fail(f"例外が外に漏れた: {e}")

    assert isinstance(result, str)
    assert len(result) > 0
    # 名前なし → 「さん」は含まれないこと
    assert "さん" not in result.split("\n")[0]


@pytest.mark.asyncio
async def test_greeting_name_empty_string_omitted():
    """employees の name="" の場合に「さん」が含まれないこと"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context()),
        patch("app.services.chat_service.get_database",
              return_value=_make_db(emp_name="")),  # name が空文字
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    # 空文字の名前で「さん」が表示されないこと
    first_line = result.split("\n")[0]
    assert "さん" not in first_line


@pytest.mark.asyncio
async def test_greeting_invalid_user_id_format_no_crash():
    """user_id='invalid-objectid' を渡した場合にクラッシュせず名前なしの挨拶が返ること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context()),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        try:
            result = await ChatService.generate_greeting(CORP_ID, "invalid-objectid")
        except Exception as e:
            pytest.fail(f"不正な user_id で例外が漏れた: {e}")

    assert isinstance(result, str)
    assert len(result) > 0


# ── ③ 複数タスクの表示テスト ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_greeting_multiple_tasks_numbered_correctly():
    """複数タスクが番号付きリストで表示され番号が連続していること"""
    from app.services.chat_service import ChatService
    import re

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         pending_receipts_count=2,
                         pending_invoices_count=1,
                         unmatched_transactions_count=3,
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    # 番号付きリストの行を抽出
    numbered_lines = re.findall(r"^(\d+)\.", result, re.MULTILINE)
    numbers = [int(n) for n in numbered_lines]

    # 少なくとも3件（領収書・請求書・取引）が番号付きで表示されていること
    assert len(numbers) >= 3
    # 番号が 1 から連続していること
    assert numbers == list(range(1, len(numbers) + 1)), f"番号が連続していない: {numbers}"


@pytest.mark.asyncio
async def test_greeting_deposit_description_in_message():
    """recent_deposits の description・amount がメッセージに含まれること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         unmatched_transactions_count=1,
                         recent_deposits=[
                             {"description": "株式会社A", "amount": 50000, "date": "2026-04-15"},
                         ],
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "株式会社A" in result
    assert "50,000円" in result


@pytest.mark.asyncio
async def test_greeting_no_deposits_but_unmatched_tx():
    """unmatched_tx=3 かつ recent_deposits=[] の場合に「未消込の銀行明細が3件」が含まれること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         unmatched_transactions_count=3,
                         recent_deposits=[],    # ← deposits なし
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "未消込の銀行明細が3件" in result


# ── ④ 再アクセス時のメッセージテスト ─────────────────────────────────────

@pytest.mark.asyncio
async def test_greeting_revisit_says_new_activity():
    """is_first_access_today=False かつタスクありの場合に「新しい動きがありました」が含まれること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         is_first_access_today=False,
                         pending_receipts_count=1,
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "新しい動きがありました" in result


@pytest.mark.asyncio
async def test_greeting_revisit_no_tasks_simple_message():
    """is_first_access_today=False かつ全タスク0件の場合に「おかえりなさい」とシンプルメッセージが返ること"""
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context",
                     new_callable=AsyncMock,
                     return_value=_base_context(
                         is_first_access_today=False,
                         pending_receipts_count=0,
                         pending_invoices_count=0,
                         unmatched_transactions_count=0,
                         recent_deposits=[],
                     )),
        patch("app.services.chat_service.get_database", return_value=_make_db()),
    ):
        result = await ChatService.generate_greeting(CORP_ID, USER_ID)

    assert "おかえりなさい" in result
    assert "対応が必要な作業はありません" in result


# ── ⑤ エンドポイントテスト ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_greeting_endpoint_requires_auth():
    """Authorization ヘッダーなしでは 401 または 403 が返ること"""
    import httpx
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/advisor/greeting")

    # FastAPI の HTTPBearer は Authorization なしで 403 を返す
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_greeting_response_is_string():
    """GET /advisor/greeting の greeting が空でない文字列であること"""
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
            with (
                patch("app.api.routes.advisor.resolve_corporate_id",
                      new=AsyncMock(return_value=(CORP_ID, USER_ID))),
                patch("app.api.routes.advisor.ChatService.generate_greeting",
                      new=AsyncMock(return_value="おはようございます。今日の状況をお知らせします。")),
            ):
                resp = await client.get("/api/v1/advisor/greeting")

        assert resp.status_code == 200
        data = resp.json()
        greeting = data.get("greeting")

        assert isinstance(greeting, str), f"greeting が文字列でない: {type(greeting)}"
        assert len(greeting) > 0, "greeting が空文字"
        assert greeting is not None

    finally:
        app.dependency_overrides.clear()
