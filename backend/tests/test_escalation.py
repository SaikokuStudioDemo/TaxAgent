"""
Tests for Task#19: [[TAX_ADVISOR_REQUIRED]] エスカレーションフロー

Usage:
    cd backend
    pytest tests/test_escalation.py -v
"""
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

CORP_ID = str(ObjectId())
USER_ID = str(ObjectId())

MOCK_CONTEXT = {
    "company_name": "テスト株式会社",
    "pending_receipts_count": 0,
    "pending_invoices_count": 0,
    "unmatched_transactions_count": 0,
    "pending_documents": [],
    "recent_deposits": [],
    "days_until_month_end": 10,
    "is_first_access_today": True,
    "alerts": "特になし",
}


# ── モックヘルパー ─────────────────────────────────────────────────────────────

def make_col(insert_result=None):
    col = MagicMock()
    col.insert_one = AsyncMock(return_value=insert_result or MagicMock())
    col.insert_many = AsyncMock(return_value=MagicMock())
    return col


def build_mock_db(collections: dict):
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


# ── 定数の確認 ────────────────────────────────────────────────────────────────

def test_markers_defined_as_constants():
    """LAW_AGENT_REQUIRED_MARKER と TAX_ADVISOR_REQUIRED_MARKER が定数として定義されていること"""
    import app.services.chat_service as cs

    assert hasattr(cs, "LAW_AGENT_REQUIRED_MARKER")
    assert hasattr(cs, "TAX_ADVISOR_REQUIRED_MARKER")
    assert cs.LAW_AGENT_REQUIRED_MARKER == "[[LAW_AGENT_REQUIRED]]"
    assert cs.TAX_ADVISOR_REQUIRED_MARKER == "[[TAX_ADVISOR_REQUIRED]]"


# ═══════════════════════════════════════════════════════════════════════════
# エスカレーションフローのテスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_law_agent_required_escalates_to_law_agent():
    """[[LAW_AGENT_REQUIRED]] が返った時に query_law_agent() が呼ばれること"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch.object(AIService, "chat_advisor", new_callable=AsyncMock, return_value="[[LAW_AGENT_REQUIRED]]"),
        patch.object(ChatService, "query_law_agent", new_callable=AsyncMock, return_value="Law回答") as mock_law,
        patch.object(ChatService, "notify_tax_advisor", new_callable=AsyncMock),
    ):
        await ChatService.process_query(CORP_ID, "法令に関する質問")

    mock_law.assert_called_once()


@pytest.mark.asyncio
async def test_law_agent_answers_successfully():
    """Law Agent が正常回答した場合にその回答が返り、notify_tax_advisor が呼ばれないこと"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    law_answer = "消費税の計算は課税売上高に税率をかけます。"

    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch.object(AIService, "chat_advisor", new_callable=AsyncMock, return_value="[[LAW_AGENT_REQUIRED]]"),
        patch.object(ChatService, "query_law_agent", new_callable=AsyncMock, return_value=law_answer),
        patch.object(ChatService, "notify_tax_advisor", new_callable=AsyncMock) as mock_notify,
    ):
        result = await ChatService.process_query(CORP_ID, "消費税の計算方法は？")

    assert result == law_answer
    mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_law_agent_no_answer_triggers_tax_advisor():
    """Law Agent が None を返した場合に notify_tax_advisor() が reason='law_agent_no_answer' で呼ばれること"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    notifications_col = make_col()
    db = build_mock_db({"notifications": notifications_col})

    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch.object(AIService, "chat_advisor", new_callable=AsyncMock, return_value="[[LAW_AGENT_REQUIRED]]"),
        patch.object(ChatService, "query_law_agent", new_callable=AsyncMock, return_value=None),
        patch("app.services.chat_service.get_database", return_value=db),
    ):
        result = await ChatService.process_query(CORP_ID, "難解な税務質問", USER_ID)

    # notify_tax_advisor が呼ばれて notifications に記録されること
    notifications_col.insert_one.assert_called_once()
    saved = notifications_col.insert_one.call_args[0][0]
    assert saved["reason"] == "law_agent_no_answer"
    assert saved["corporate_id"] == CORP_ID
    assert saved["type"] == "tax_advisor_required"

    # レスポンスに「税理士」が含まれること
    assert "税理士" in result
    assert "[[LAW_AGENT_REQUIRED]]" not in result


@pytest.mark.asyncio
async def test_tax_advisor_required_direct():
    """Claude Sonnet が直接 [[TAX_ADVISOR_REQUIRED]] を返した場合に notify_tax_advisor() が呼ばれること"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    notifications_col = make_col()
    db = build_mock_db({"notifications": notifications_col})

    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch.object(AIService, "chat_advisor", new_callable=AsyncMock, return_value="[[TAX_ADVISOR_REQUIRED]]"),
        patch("app.services.chat_service.get_database", return_value=db),
    ):
        result = await ChatService.process_query(CORP_ID, "複雑な税務判断が必要な質問", USER_ID)

    # notify_tax_advisor が呼ばれること
    notifications_col.insert_one.assert_called_once()
    saved = notifications_col.insert_one.call_args[0][0]
    assert saved["reason"] == "direct_escalation"
    assert "税理士" in result


@pytest.mark.asyncio
async def test_tax_advisor_notification_saved_to_db():
    """notify_tax_advisor() 後に notifications コレクションに正しいフィールドで保存されること"""
    from app.services.chat_service import ChatService

    notifications_col = make_col()
    db = build_mock_db({"notifications": notifications_col})

    with patch("app.services.chat_service.get_database", return_value=db):
        await ChatService.notify_tax_advisor(
            corporate_id=CORP_ID,
            user_id=USER_ID,
            query="複雑な質問",
            reason="direct_escalation",
        )

    notifications_col.insert_one.assert_called_once()
    saved = notifications_col.insert_one.call_args[0][0]

    assert saved["corporate_id"] == CORP_ID
    assert saved["user_id"] == USER_ID
    assert saved["query"] == "複雑な質問"
    assert saved["reason"] == "direct_escalation"
    assert saved["type"] == "tax_advisor_required"
    assert saved["status"] == "pending"
    assert saved["read"] is False


@pytest.mark.asyncio
async def test_notification_failure_does_not_break_chat():
    """notify_tax_advisor() で例外が発生しても process_query() が正常にレスポンスを返すこと"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    # insert_one が例外を投げる状況
    notifications_col = make_col()
    notifications_col.insert_one = AsyncMock(side_effect=Exception("DB障害"))
    db = build_mock_db({"notifications": notifications_col})

    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch.object(AIService, "chat_advisor", new_callable=AsyncMock, return_value="[[TAX_ADVISOR_REQUIRED]]"),
        patch("app.services.chat_service.get_database", return_value=db),
    ):
        try:
            result = await ChatService.process_query(CORP_ID, "質問", USER_ID)
        except Exception as e:
            pytest.fail(f"例外が外に漏れた: {e}")

    # 例外が吸収されてレスポンスが返ること
    assert isinstance(result, str)
    assert len(result) > 0
    assert "税理士" in result


@pytest.mark.asyncio
async def test_normal_response_no_escalation():
    """通常の回答（マーカーなし）の場合 query_law_agent も notify_tax_advisor も呼ばれないこと"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    normal_answer = "承認待ちの領収書は2件です。"

    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch.object(AIService, "chat_advisor", new_callable=AsyncMock, return_value=normal_answer),
        patch.object(ChatService, "query_law_agent", new_callable=AsyncMock) as mock_law,
        patch.object(ChatService, "notify_tax_advisor", new_callable=AsyncMock) as mock_notify,
    ):
        result = await ChatService.process_query(CORP_ID, "承認待ちの書類を教えてください")

    assert result == normal_answer
    mock_law.assert_not_called()
    mock_notify.assert_not_called()


# ── ③ system_prompt への [[TAX_ADVISOR_REQUIRED]] 追加確認 ──────────────────

def test_system_prompt_includes_tax_advisor_required():
    """chat_advisor の system_prompt に [[TAX_ADVISOR_REQUIRED]] が制約4として含まれること"""
    import app.services.ai_service as ai_module

    source = inspect.getsource(ai_module.AIService.chat_advisor)

    assert "TAX_ADVISOR_REQUIRED" in source, \
        "system_prompt に [[TAX_ADVISOR_REQUIRED]] が含まれていない"
    # 制約4として追加されていること
    assert "4." in source, \
        "制約4が system_prompt に存在しない"
    # LAW_AGENT_REQUIRED と TAX_ADVISOR_REQUIRED が両方存在すること
    assert "LAW_AGENT_REQUIRED" in source, \
        "system_prompt に [[LAW_AGENT_REQUIRED]] が含まれていない"
