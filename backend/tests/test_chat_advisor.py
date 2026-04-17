"""
Tests for Task#14: chat_advisor migration from Gemini to Claude Sonnet.

Usage:
    cd backend
    pytest tests/test_chat_advisor.py -v
"""
import asyncio
import ast
import inspect
import os
import re
import pytest
import httpx
import anthropic
from anthropic._exceptions import OverloadedError as AnthropicOverloadedError
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_mock_client(response_text="テスト回答"):
    """正常系レスポンスを返すモッククライアントを生成する"""
    text_block = MagicMock()
    text_block.text = response_text
    message = MagicMock()
    message.content = [text_block]
    mock_create = AsyncMock(return_value=message)
    mock_client = MagicMock()
    mock_client.messages.create = mock_create
    return mock_client, mock_create


def _make_status_error(cls, status_code):
    """anthropic.APIStatusError サブクラスのインスタンスを生成するヘルパー"""
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(status_code)
    resp.request = req  # httpx バージョン互換のため constructor ではなく属性で設定
    return cls(message="test error", response=resp, body={})


def _make_overloaded_error():
    """529 OverloadedError を生成する（anthropic._exceptions 経由）"""
    return _make_status_error(AnthropicOverloadedError, 529)


MOCK_CONTEXT = {
    "company_name": "テスト株式会社",
    "pending_invoices_count": 3,
    "unmatched_transactions_count": 1,
    "alerts": "特になし",
}


# ─────────────────────────────────────────────
# test_chat_advisor_returns_string
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_chat_advisor_returns_string():
    """chat_advisor() が文字列を返すこと（正常系）"""
    from app.services.ai_service import AIService

    mock_text_block = MagicMock()
    mock_text_block.text = "承認待ちの請求書は3件です。"

    mock_message = MagicMock()
    mock_message.content = [mock_text_block]

    mock_create = AsyncMock(return_value=mock_message)

    with patch("anthropic.AsyncAnthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create = mock_create

        result = await AIService.chat_advisor("承認待ちの請求書は何件？", MOCK_CONTEXT)

    assert isinstance(result, str)
    assert len(result) > 0


# ─────────────────────────────────────────────
# test_law_agent_required_marker_passthrough
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_law_agent_required_marker_passthrough():
    """[[LAW_AGENT_REQUIRED]] がそのまま返り、process_query でエスカレーションが発生すること"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    mock_text_block = MagicMock()
    mock_text_block.text = "[[LAW_AGENT_REQUIRED]]"

    mock_message = MagicMock()
    mock_message.content = [mock_text_block]

    mock_create = AsyncMock(return_value=mock_message)

    # chat_advisor が [[LAW_AGENT_REQUIRED]] を返すことを確認
    with patch("anthropic.AsyncAnthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create = mock_create
        advisor_result = await AIService.chat_advisor("消費税の計算方法を教えてください", MOCK_CONTEXT)

    assert "[[LAW_AGENT_REQUIRED]]" in advisor_result

    # process_query でエスカレーションが発生することを確認
    law_agent_response = "消費税は課税対象売上高に税率を掛けて計算します。"

    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch.object(AIService, "chat_advisor", new_callable=AsyncMock, return_value="[[LAW_AGENT_REQUIRED]]"),
        patch.object(ChatService, "query_law_agent", new_callable=AsyncMock, return_value=law_agent_response),
    ):
        result = await ChatService.process_query("corp_001", "消費税の計算方法を教えてください")

    assert result == law_agent_response


# ─────────────────────────────────────────────
# test_gemini_methods_unchanged
# ─────────────────────────────────────────────
def test_gemini_methods_unchanged():
    """fuzzy_match_names と analyze_invoice_pdf が引き続き Gemini を使っていること"""
    import inspect
    import app.services.ai_service as ai_module

    # google.generativeai の import が残っていること
    assert hasattr(ai_module, "genai"), "google.generativeai (genai) が import されていない"

    # fuzzy_match_names のソースに genai が含まれること
    fuzzy_source = inspect.getsource(ai_module.AIService.fuzzy_match_names)
    assert "genai" in fuzzy_source, "fuzzy_match_names が Gemini (genai) を使っていない"

    # analyze_invoice_pdf のソースに genai が含まれること
    analyze_source = inspect.getsource(ai_module.AIService.analyze_invoice_pdf)
    assert "genai" in analyze_source, "analyze_invoice_pdf が Gemini (genai) を使っていない"

    # chat_advisor のソースに AsyncAnthropic が含まれること
    chat_source = inspect.getsource(ai_module.AIService.chat_advisor)
    assert "AsyncAnthropic" in chat_source, "chat_advisor が AsyncAnthropic を使っていない"
    assert "genai" not in chat_source, "chat_advisor に Gemini (genai) が残っている"


# ═══════════════════════════════════════════════════════════════════════════
# ① AsyncAnthropic の正しい使われ方確認
# ═══════════════════════════════════════════════════════════════════════════

def test_chat_advisor_uses_async_client():
    """AsyncAnthropic が使われており、同期クライアント anthropic.Anthropic は使われていないこと"""
    import app.services.ai_service as ai_module

    source = inspect.getsource(ai_module.AIService.chat_advisor)

    # AsyncAnthropic が使われていること
    assert "AsyncAnthropic" in source, "chat_advisor が AsyncAnthropic を使っていない"

    # "anthropic.Anthropic(" は "anthropic.AsyncAnthropic(" とは別の文字列なので区別できる
    # ※ "AsyncAnthropic" には "Anthropic(" の直前に "Async" が付くため部分一致しない
    assert "anthropic.Anthropic(" not in source, "同期クライアント anthropic.Anthropic( が使われている"

    # await が client.messages.create に付いていること
    assert "await client.messages.create" in source, "await が client.messages.create に付いていない"


def test_chat_advisor_is_awaitable():
    """chat_advisor() が coroutine function であること"""
    from app.services.ai_service import AIService

    assert asyncio.iscoroutinefunction(AIService.chat_advisor), \
        "chat_advisor が coroutine function でない（async def になっていない）"


# ═══════════════════════════════════════════════════════════════════════════
# ② エスカレーションフローの確認
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_law_agent_escalation_on_marker():
    """[[LAW_AGENT_REQUIRED]] 時に Law Agent を呼び、正常応答をそのまま返すこと"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    law_response = "消費税は課税対象売上高に税率を掛けて計算します。"

    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch.object(AIService, "chat_advisor", new_callable=AsyncMock, return_value="[[LAW_AGENT_REQUIRED]]"),
        patch.object(ChatService, "query_law_agent", new_callable=AsyncMock, return_value=law_response) as mock_law,
    ):
        result = await ChatService.process_query("corp_001", "消費税の計算方法を教えてください")

    mock_law.assert_called_once()
    assert result == law_response


@pytest.mark.asyncio
async def test_law_agent_escalation_fallback_when_none():
    """Law Agent が None を返した場合はフォールバックメッセージが返ること"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch.object(AIService, "chat_advisor", new_callable=AsyncMock, return_value="[[LAW_AGENT_REQUIRED]]"),
        patch.object(ChatService, "query_law_agent", new_callable=AsyncMock, return_value=None),
        # ① notify_tax_advisor をモック：実 DB 書き込みを防ぐ
        patch.object(ChatService, "notify_tax_advisor", new_callable=AsyncMock),
    ):
        result = await ChatService.process_query("corp_001", "答えられない質問")

    assert isinstance(result, str)
    assert len(result) > 0
    assert "[[LAW_AGENT_REQUIRED]]" not in result  # マーカーがそのまま返らないこと


@pytest.mark.asyncio
async def test_law_agent_not_called_without_marker():
    """[[LAW_AGENT_REQUIRED]] が含まれない応答の場合は query_law_agent() が呼ばれないこと"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    normal_response = "承認待ちの請求書は3件です。"

    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch.object(AIService, "chat_advisor", new_callable=AsyncMock, return_value=normal_response),
        patch.object(ChatService, "query_law_agent", new_callable=AsyncMock) as mock_law,
    ):
        result = await ChatService.process_query("corp_001", "承認待ちの請求書は何件？")

    assert mock_law.call_count == 0, "Law Agent が不要なのに呼ばれた"
    assert result == normal_response


# ═══════════════════════════════════════════════════════════════════════════
# ③ エラーハンドリングの確認
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_overloaded_error_returns_japanese_message():
    """OverloadedError（529）発生時に日本語メッセージが返り、例外が外に漏れないこと"""
    from app.services.ai_service import AIService

    mock_client, mock_create = _make_mock_client()
    mock_create.side_effect = _make_overloaded_error()

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value = mock_client
        result = await AIService.chat_advisor("テスト質問", MOCK_CONTEXT)

    assert isinstance(result, str)
    assert "混み合っています" in result


@pytest.mark.asyncio
async def test_rate_limit_error_returns_japanese_message():
    """RateLimitError（429）発生時に日本語メッセージが返ること"""
    from app.services.ai_service import AIService

    mock_client, mock_create = _make_mock_client()
    mock_create.side_effect = _make_status_error(anthropic.RateLimitError, 429)

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value = mock_client
        result = await AIService.chat_advisor("テスト質問", MOCK_CONTEXT)

    assert isinstance(result, str)
    assert "集中しています" in result


@pytest.mark.asyncio
async def test_generic_api_error_returns_japanese_message():
    """APIError 発生時に日本語メッセージが返り、process_query が例外を raise しないこと"""
    from app.services.ai_service import AIService
    from app.services.chat_service import ChatService

    mock_client, mock_create = _make_mock_client()
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    mock_create.side_effect = anthropic.APIError("generic error", req, body=None)

    # chat_advisor 単体：日本語メッセージが返ること
    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value = mock_client
        result = await AIService.chat_advisor("テスト質問", MOCK_CONTEXT)

    assert isinstance(result, str)
    assert "AIサービス" in result or "アドバイザー" in result

    # process_query 経由でも例外が漏れないこと
    with (
        patch.object(ChatService, "get_corporate_context", new_callable=AsyncMock, return_value=MOCK_CONTEXT),
        patch("anthropic.AsyncAnthropic") as mock_cls2,
    ):
        mock_client2, mock_create2 = _make_mock_client()
        mock_create2.side_effect = anthropic.APIError("generic error", req, body=None)
        mock_cls2.return_value = mock_client2

        try:
            pq_result = await ChatService.process_query("corp_001", "テスト質問")
        except Exception as e:
            pytest.fail(f"process_query が例外を raise した: {e}")

    assert isinstance(pq_result, str)


# ═══════════════════════════════════════════════════════════════════════════
# ④ コンテキスト注入の確認
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_context_injected_into_system_prompt():
    """get_corporate_context() の値が Anthropic API の system prompt に含まれること"""
    from app.services.ai_service import AIService

    mock_client, mock_create = _make_mock_client()

    context = {
        "company_name": "コンテキスト注入テスト株式会社",
        "pending_invoices_count": 7,
        "unmatched_transactions_count": 2,
        "alerts": "テストアラート",
    }

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value = mock_client
        await AIService.chat_advisor("テスト質問", context)

    call_kwargs = mock_create.call_args.kwargs
    system_prompt = call_kwargs.get("system", "")

    assert "コンテキスト注入テスト株式会社" in system_prompt, \
        "company_name が system prompt に含まれていない"
    assert "7" in system_prompt, \
        "pending_invoices_count が system prompt に含まれていない"


@pytest.mark.asyncio
async def test_empty_context_does_not_crash():
    """空の dict を渡してもクラッシュせず文字列が返ること"""
    from app.services.ai_service import AIService

    mock_client, mock_create = _make_mock_client("空コンテキストでも回答します")

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value = mock_client
        result = await AIService.chat_advisor("テスト質問", {})

    assert result is not None
    assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════
# ⑤ モデル名の確認
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_model_name_from_config():
    """DEFAULT_AI_MODEL の値が API 呼び出しの model 引数にそのまま渡されること"""
    from app.services.ai_service import AIService

    mock_client, mock_create = _make_mock_client()

    with (
        patch("anthropic.AsyncAnthropic") as mock_cls,
        patch("app.services.ai_service.settings") as mock_settings,
    ):
        mock_settings.DEFAULT_AI_MODEL = "claude-test-model"
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_cls.return_value = mock_client

        await AIService.chat_advisor("テスト質問", MOCK_CONTEXT)

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs.get("model") == "claude-test-model", \
        f"model がハードコードされている可能性。実際の値: {call_kwargs.get('model')}"


# ═══════════════════════════════════════════════════════════════════════════
# ⑥ Gemini 系メソッドへの影響確認
# ═══════════════════════════════════════════════════════════════════════════

def test_fuzzy_match_names_still_uses_gemini():
    """fuzzy_match_names() が genai を使い、anthropic を使っていないこと"""
    import app.services.ai_service as ai_module

    source = inspect.getsource(ai_module.AIService.fuzzy_match_names)

    assert "genai" in source, "fuzzy_match_names が Gemini (genai) を使っていない"
    assert "anthropic" not in source, "fuzzy_match_names に anthropic が混入している"


def test_gemini_import_still_present():
    """ai_service.py に google.generativeai の import が ast レベルで残っていること"""
    module_path = os.path.join(
        os.path.dirname(__file__), "../app/services/ai_service.py"
    )
    with open(module_path, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)

    google_imported = any(
        (
            isinstance(node, ast.Import)
            and any("google" in alias.name for alias in node.names)
        )
        or (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and "google" in node.module
        )
        for node in ast.walk(tree)
    )

    assert google_imported, \
        "google.generativeai の import が ai_service.py から削除されている"
