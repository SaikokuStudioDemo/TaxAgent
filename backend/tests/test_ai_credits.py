"""
Tests for Task#31・#32: AI クレジット管理 + system_settings

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_ai_credits.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

CORP_ID = str(ObjectId())
CORP_DOC_BASIC = {
    "_id": ObjectId(CORP_ID),
    "firebase_uid": "corp_uid",
    "planId": "plan_basic",
    "monthly_ai_usage": 0,
}


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_col(find_one=None, find_data=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=find_data or [])))
    col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    col.update_many = AsyncMock(return_value=MagicMock(modified_count=5))
    col.insert_many = AsyncMock()
    return col


def build_mock_db(collections: dict):
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


# ─────────────────────────────────────────────────────────────────────────────
# test_usage_incremented_after_chat
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_incremented_after_chat():
    """チャット正常レスポンス後に monthly_ai_usage が +1 されること。"""
    from app.services.chat_service import ChatService

    corp_col = make_col(find_one=CORP_DOC_BASIC)
    mock_db = build_mock_db({
        "corporates": corp_col,
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db), \
         patch("app.services.chat_service.ChatService.get_corporate_context", new_callable=AsyncMock, return_value={}), \
         patch("app.services.chat_service.AIService.chat_advisor", new_callable=AsyncMock, return_value="テスト回答"), \
         patch("app.services.chat_service.ChatService.save_chat_history", new_callable=AsyncMock):

        result = await ChatService.process_query(CORP_ID, "テスト質問")

    assert result["response"] == "テスト回答"
    # update_one が $inc: {monthly_ai_usage: 1} で呼ばれること
    corp_col.update_one.assert_called_once()
    call_args = corp_col.update_one.call_args[0]
    assert call_args[0] == {"_id": ObjectId(CORP_ID)}
    assert "$inc" in call_args[1]
    assert call_args[1]["$inc"]["monthly_ai_usage"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# test_usage_not_incremented_on_error
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_not_incremented_on_error():
    """
    process_query がエラー（HTTPException）を raise した場合に
    monthly_ai_usage が記録されないこと。
    上限超過で 429 が raise された場合のテスト。
    """
    from fastapi import HTTPException
    from app.services.chat_service import ChatService

    # 上限到達状態
    corp_at_limit = {**CORP_DOC_BASIC, "monthly_ai_usage": 100}
    corp_col = make_col(find_one=corp_at_limit)
    mock_db = build_mock_db({
        "corporates": corp_col,
        "system_settings": make_col(find_one=None),  # デフォルト上限100
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await ChatService.process_query(CORP_ID, "テスト質問")

    assert exc.value.status_code == 429
    # update_one（利用量記録）が呼ばれていないこと
    corp_col.update_one.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# test_limit_exceeded_returns_429
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_limit_exceeded_returns_429():
    """monthly_ai_usage が上限に達した場合に 429 が返ること。detail に code が含まれること。"""
    from fastapi import HTTPException
    from app.services.chat_service import ChatService

    corp_at_limit = {**CORP_DOC_BASIC, "monthly_ai_usage": 100}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_at_limit),
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await ChatService.process_query(CORP_ID, "質問")

    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "AI_CREDIT_LIMIT_EXCEEDED"
    assert exc.value.detail["current_usage"] == 100
    assert exc.value.detail["limit"] == 100


# ─────────────────────────────────────────────────────────────────────────────
# test_warning_when_near_limit
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_warning_when_near_limit():
    """残り10%以下の場合に warning が返ること（残り9/100 → warning あり）。"""
    from app.services.chat_service import ChatService

    # 91/100 = 残り9（10%以下）
    corp_near_limit = {**CORP_DOC_BASIC, "monthly_ai_usage": 91}
    corp_col = make_col(find_one=corp_near_limit)
    mock_db = build_mock_db({
        "corporates": corp_col,
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db), \
         patch("app.services.chat_service.ChatService.get_corporate_context", new_callable=AsyncMock, return_value={}), \
         patch("app.services.chat_service.AIService.chat_advisor", new_callable=AsyncMock, return_value="回答"), \
         patch("app.services.chat_service.ChatService.save_chat_history", new_callable=AsyncMock):

        result = await ChatService.process_query(CORP_ID, "質問")

    assert result["warning"] is not None
    assert "残り" in result["warning"]


@pytest.mark.asyncio
async def test_no_warning_when_enough_remaining():
    """残り十分な場合に warning=None が返ること（残り50/100 → warning なし）。"""
    from app.services.chat_service import ChatService

    corp_with_usage = {**CORP_DOC_BASIC, "monthly_ai_usage": 50}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_with_usage),
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db), \
         patch("app.services.chat_service.ChatService.get_corporate_context", new_callable=AsyncMock, return_value={}), \
         patch("app.services.chat_service.AIService.chat_advisor", new_callable=AsyncMock, return_value="回答"), \
         patch("app.services.chat_service.ChatService.save_chat_history", new_callable=AsyncMock):

        result = await ChatService.process_query(CORP_ID, "質問")

    assert result["warning"] is None


# ─────────────────────────────────────────────────────────────────────────────
# test_get_credits_returns_correct_remaining
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_credits_returns_correct_remaining():
    """GET /advisor/credits が remaining = limit - current_usage を返すこと。"""
    from app.api.routes.advisor import get_credits

    corp = {**CORP_DOC_BASIC, "monthly_ai_usage": 30}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp),
        "system_settings": make_col(find_one=None),
    })
    current_user = {"uid": "corp_uid"}

    with patch("app.api.routes.advisor.get_database", return_value=mock_db), \
         patch("app.api.routes.advisor.resolve_corporate_id", new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.services.chat_service.get_database", return_value=mock_db):

        result = await get_credits(current_user)

    assert result["current_usage"] == 30
    assert result["limit"] == 100
    assert result["remaining"] == 70
    assert "reset_at" in result


# ─────────────────────────────────────────────────────────────────────────────
# test_monthly_reset_sets_usage_to_zero
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_monthly_reset_sets_usage_to_zero():
    """reset_monthly_ai_usage() 実行後に update_many で monthly_ai_usage=0 が設定されること。"""
    from app.main import reset_monthly_ai_usage

    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    with patch("app.main.get_database", return_value=mock_db):
        await reset_monthly_ai_usage()

    corp_col.update_many.assert_called_once()
    set_data = corp_col.update_many.call_args[0][1]["$set"]
    assert set_data["monthly_ai_usage"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# test_system_settings_plans_endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_system_settings_plans_endpoint():
    """GET /system-settings/plans が3プランを返すこと。"""
    from app.api.routes.system_settings import get_plans

    plans_doc = {
        "key": "plans",
        "value": [
            {"id": "plan_basic", "name": "ベーシックプラン", "price": 15000},
            {"id": "plan_standard", "name": "スタンダードプラン", "price": 30000},
            {"id": "plan_premium", "name": "プレミアムプラン", "price": 50000},
        ],
    }
    mock_db = build_mock_db({"system_settings": make_col(find_one=plans_doc)})

    with patch("app.api.routes.system_settings.get_database", return_value=mock_db):
        result = await get_plans()

    assert len(result) == 3
    assert result[0]["id"] == "plan_basic"
    assert result[2]["id"] == "plan_premium"


# ─────────────────────────────────────────────────────────────────────────────
# test_system_settings_seed_idempotent
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_system_settings_seed_idempotent():
    """_seed_system_settings を2回実行しても重複データが作成されないこと。"""
    from app.main import _seed_system_settings

    # 1回目：既存データなし → insert_many が呼ばれる
    col_empty = make_col(find_one=None)
    mock_db_empty = build_mock_db({"system_settings": col_empty})
    await _seed_system_settings(mock_db_empty)
    col_empty.insert_many.assert_called_once()

    # 2回目：既存データあり → insert_many が呼ばれない（スキップ）
    col_existing = make_col(find_one={"key": "plans", "value": []})
    mock_db_existing = build_mock_db({"system_settings": col_existing})
    await _seed_system_settings(mock_db_existing)
    col_existing.insert_many.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# test_custom_credit_limit_from_db
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_custom_credit_limit_from_db():
    """system_settings に ai_credit_limits を設定した場合に DB の値が優先されること。"""
    from app.services.chat_service import get_ai_credit_limit, DEFAULT_AI_CREDIT_LIMITS

    custom_limits_doc = {
        "key": "ai_credit_limits",
        "value": {"plan_basic": 999, "plan_standard": 9999},
    }
    mock_db = build_mock_db({"system_settings": make_col(find_one=custom_limits_doc)})

    with patch("app.services.chat_service.get_database", return_value=mock_db):
        limit_basic = await get_ai_credit_limit("plan_basic")
        limit_standard = await get_ai_credit_limit("plan_standard")

    # DB の値が使われること（DEFAULT の100・500より大きい）
    assert limit_basic == 999, f"DB値 999 が期待値だが {limit_basic}"
    assert limit_standard == 9999
    assert limit_basic != DEFAULT_AI_CREDIT_LIMITS["plan_basic"]


# =============================================================================
# 意地悪テスト（Task#31・#32）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① 上限チェックの境界値テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_at_exactly_limit_returns_429():
    """monthly_ai_usage がちょうど limit と同じ場合に 429 が返ること（境界値・含む）。"""
    from fastapi import HTTPException
    from app.services.chat_service import ChatService

    corp_at_limit = {**CORP_DOC_BASIC, "monthly_ai_usage": 100}  # 100 == limit
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_at_limit),
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await ChatService.process_query(CORP_ID, "質問")

    assert exc.value.status_code == 429, "ちょうど上限で 429 が返ること"


@pytest.mark.asyncio
async def test_usage_one_below_limit_succeeds():
    """monthly_ai_usage が limit-1（99）の場合にチャットが成功すること。"""
    from app.services.chat_service import ChatService

    corp_one_below = {**CORP_DOC_BASIC, "monthly_ai_usage": 99}  # 99 < 100 → OK
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_one_below),
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db), \
         patch("app.services.chat_service.ChatService.get_corporate_context", new_callable=AsyncMock, return_value={}), \
         patch("app.services.chat_service.AIService.chat_advisor", new_callable=AsyncMock, return_value="回答"), \
         patch("app.services.chat_service.ChatService.save_chat_history", new_callable=AsyncMock):

        result = await ChatService.process_query(CORP_ID, "質問")

    assert "response" in result
    assert result["response"] == "回答"


@pytest.mark.asyncio
async def test_limit_zero_always_blocked():
    """system_settings で plan_basic=0 に設定した場合に最初から 429 が返ること。"""
    from fastapi import HTTPException
    from app.services.chat_service import ChatService

    zero_limit_doc = {"key": "ai_credit_limits", "value": {"plan_basic": 0}}
    corp_fresh = {**CORP_DOC_BASIC, "monthly_ai_usage": 0}  # 0 >= 0 → block
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_fresh),
        "system_settings": make_col(find_one=zero_limit_doc),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await ChatService.process_query(CORP_ID, "質問")

    assert exc.value.status_code == 429, "limit=0 の場合は常にブロックされること"


# ─────────────────────────────────────────────────────────────────────────────
# ② warning フラグの境界値テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_warning_at_exactly_10_percent_remaining():
    """
    remaining がちょうど limit の10%の場合に warning が返ること（境界値・含む）。
    limit=100, current_usage=89 → new_usage=90, remaining=10 → 10 <= 10.0 → warning あり
    """
    from app.services.chat_service import ChatService

    corp = {**CORP_DOC_BASIC, "monthly_ai_usage": 89}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp),
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db), \
         patch("app.services.chat_service.ChatService.get_corporate_context", new_callable=AsyncMock, return_value={}), \
         patch("app.services.chat_service.AIService.chat_advisor", new_callable=AsyncMock, return_value="回答"), \
         patch("app.services.chat_service.ChatService.save_chat_history", new_callable=AsyncMock):

        result = await ChatService.process_query(CORP_ID, "質問")

    assert result["warning"] is not None, "remaining=10（10%）で warning が返ること"


@pytest.mark.asyncio
async def test_warning_at_11_percent_remaining():
    """
    remaining が11%の場合に warning=None が返ること。
    limit=100, current_usage=88 → new_usage=89, remaining=11 → 11 > 10.0 → warning なし
    """
    from app.services.chat_service import ChatService

    corp = {**CORP_DOC_BASIC, "monthly_ai_usage": 88}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp),
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db), \
         patch("app.services.chat_service.ChatService.get_corporate_context", new_callable=AsyncMock, return_value={}), \
         patch("app.services.chat_service.AIService.chat_advisor", new_callable=AsyncMock, return_value="回答"), \
         patch("app.services.chat_service.ChatService.save_chat_history", new_callable=AsyncMock):

        result = await ChatService.process_query(CORP_ID, "質問")

    assert result["warning"] is None, "remaining=11（11%）で warning は返らないこと"


@pytest.mark.asyncio
async def test_warning_false_when_full_credits():
    """monthly_ai_usage=0 の場合に warning=None が返ること。"""
    from app.services.chat_service import ChatService

    corp_fresh = {**CORP_DOC_BASIC, "monthly_ai_usage": 0}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_fresh),
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db), \
         patch("app.services.chat_service.ChatService.get_corporate_context", new_callable=AsyncMock, return_value={}), \
         patch("app.services.chat_service.AIService.chat_advisor", new_callable=AsyncMock, return_value="回答"), \
         patch("app.services.chat_service.ChatService.save_chat_history", new_callable=AsyncMock):

        result = await ChatService.process_query(CORP_ID, "質問")

    assert result["warning"] is None


# ─────────────────────────────────────────────────────────────────────────────
# ③ 利用量記録の耐久テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_not_incremented_on_api_error():
    """
    AIService.chat_advisor が例外を raise した場合に
    monthly_ai_usage が増えないこと。
    （update_one は chat_advisor の後に実行されるため、例外で到達しない）
    """
    from app.services.chat_service import ChatService

    corp_col = make_col(find_one=CORP_DOC_BASIC)
    mock_db = build_mock_db({
        "corporates": corp_col,
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db), \
         patch("app.services.chat_service.ChatService.get_corporate_context", new_callable=AsyncMock, return_value={}), \
         patch("app.services.chat_service.AIService.chat_advisor",
               new_callable=AsyncMock, side_effect=RuntimeError("Anthropic unreachable")):

        with pytest.raises(RuntimeError):
            await ChatService.process_query(CORP_ID, "質問")

    # update_one（利用量記録）が呼ばれていないこと
    corp_col.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_usage_not_incremented_on_limit_exceeded():
    """上限超過（429）時に monthly_ai_usage が追加でカウントアップされないこと。"""
    from fastapi import HTTPException
    from app.services.chat_service import ChatService

    corp_at_limit = {**CORP_DOC_BASIC, "monthly_ai_usage": 100}
    corp_col = make_col(find_one=corp_at_limit)
    mock_db = build_mock_db({
        "corporates": corp_col,
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await ChatService.process_query(CORP_ID, "質問")

    assert exc.value.status_code == 429
    # 上限超過時に update_one が呼ばれていないこと
    corp_col.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_usage_incremented_only_once_per_request():
    """1回のチャットで monthly_ai_usage がちょうど1増えること（2以上増えない）。"""
    from app.services.chat_service import ChatService

    corp_col = make_col(find_one=CORP_DOC_BASIC)
    mock_db = build_mock_db({
        "corporates": corp_col,
        "system_settings": make_col(find_one=None),
    })

    with patch("app.services.chat_service.get_database", return_value=mock_db), \
         patch("app.services.chat_service.ChatService.get_corporate_context", new_callable=AsyncMock, return_value={}), \
         patch("app.services.chat_service.AIService.chat_advisor", new_callable=AsyncMock, return_value="回答"), \
         patch("app.services.chat_service.ChatService.save_chat_history", new_callable=AsyncMock):

        await ChatService.process_query(CORP_ID, "質問")

    # update_one がちょうど1回だけ呼ばれること
    assert corp_col.update_one.call_count == 1, \
        f"update_one が {corp_col.update_one.call_count} 回呼ばれた（期待値: 1回）"
    # $inc の値が 1 であること
    inc_data = corp_col.update_one.call_args[0][1]["$inc"]
    assert inc_data["monthly_ai_usage"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# ④ リセット処理テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_does_not_affect_other_fields():
    """reset_monthly_ai_usage() の $set に monthly_ai_usage のみが含まれること。"""
    from app.main import reset_monthly_ai_usage

    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    with patch("app.main.get_database", return_value=mock_db):
        await reset_monthly_ai_usage()

    set_data = corp_col.update_many.call_args[0][1]["$set"]
    # monthly_ai_usage だけが $set に含まれること
    assert set_data == {"monthly_ai_usage": 0}, \
        f"$set に余分なフィールドが含まれている: {set_data}"
    assert "planId" not in set_data
    assert "name" not in set_data


@pytest.mark.asyncio
async def test_reset_when_already_zero():
    """monthly_ai_usage が既に0の場合でも reset() がクラッシュしないこと。"""
    from app.main import reset_monthly_ai_usage

    corp_col = make_col()
    corp_col.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    mock_db = build_mock_db({"corporates": corp_col})

    with patch("app.main.get_database", return_value=mock_db):
        await reset_monthly_ai_usage()  # クラッシュしないこと

    corp_col.update_many.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ get_credits のテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_credits_remaining_never_negative():
    """monthly_ai_usage が limit を超えていても remaining が 0 以下にならないこと。"""
    from app.api.routes.advisor import get_credits

    corp_over_limit = {**CORP_DOC_BASIC, "monthly_ai_usage": 999}  # 999 > 100
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_over_limit),
        "system_settings": make_col(find_one=None),
    })

    with patch("app.api.routes.advisor.get_database", return_value=mock_db), \
         patch("app.api.routes.advisor.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.services.chat_service.get_database", return_value=mock_db):

        result = await get_credits({"uid": "corp_uid"})

    assert result["remaining"] >= 0, f"remaining が負になった: {result['remaining']}"
    assert result["remaining"] == 0


@pytest.mark.asyncio
async def test_get_credits_uses_db_limit_over_default():
    """system_settings に plan_basic=50 を設定した場合に limit=50 が返ること（DEFAULT の100より優先）。"""
    from app.api.routes.advisor import get_credits

    custom_limits = {"key": "ai_credit_limits", "value": {"plan_basic": 50}}
    corp = {**CORP_DOC_BASIC, "monthly_ai_usage": 10}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp),
        "system_settings": make_col(find_one=custom_limits),
    })

    with patch("app.api.routes.advisor.get_database", return_value=mock_db), \
         patch("app.api.routes.advisor.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.services.chat_service.get_database", return_value=mock_db):

        result = await get_credits({"uid": "corp_uid"})

    assert result["limit"] == 50, f"DB値 50 が期待値だが {result['limit']}"
    assert result["remaining"] == 40  # 50 - 10


@pytest.mark.asyncio
async def test_get_credits_unknown_plan_uses_default():
    """planId が 'plan_unknown' の場合にデフォルト値（100）が返りクラッシュしないこと。"""
    from app.api.routes.advisor import get_credits

    corp_unknown_plan = {**CORP_DOC_BASIC, "planId": "plan_unknown", "monthly_ai_usage": 5}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=corp_unknown_plan),
        "system_settings": make_col(find_one=None),
    })

    with patch("app.api.routes.advisor.get_database", return_value=mock_db), \
         patch("app.api.routes.advisor.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.services.chat_service.get_database", return_value=mock_db):

        result = await get_credits({"uid": "corp_uid"})

    assert result["limit"] == 100, "未知のプランはデフォルト値 100 を使うこと"
    assert result["remaining"] == 95


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ system_settings のテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_does_not_overwrite_existing():
    """system_settings に既にデータがある場合に _seed_system_settings() が上書きしないこと。"""
    from app.main import _seed_system_settings

    existing_doc = {"key": "plans", "value": [{"id": "custom_plan"}]}
    col_existing = make_col(find_one=existing_doc)
    mock_db = build_mock_db({"system_settings": col_existing})

    await _seed_system_settings(mock_db)

    col_existing.insert_many.assert_not_called()
    # find_one が呼ばれたことを確認（既存チェックが行われた）
    col_existing.find_one.assert_called_once()


@pytest.mark.asyncio
async def test_plans_endpoint_returns_3_plans():
    """GET /system-settings/plans が3件返ること。"""
    from app.api.routes.system_settings import get_plans

    plans_doc = {
        "key": "plans",
        "value": [
            {"id": "plan_basic"},
            {"id": "plan_standard"},
            {"id": "plan_premium"},
        ],
    }
    mock_db = build_mock_db({"system_settings": make_col(find_one=plans_doc)})

    with patch("app.api.routes.system_settings.get_database", return_value=mock_db):
        result = await get_plans()

    assert len(result) == 3


@pytest.mark.asyncio
async def test_plans_endpoint_no_auth_required():
    """get_plans() が current_user 引数なしで呼べること（認証不要の確認）。"""
    import inspect
    from app.api.routes.system_settings import get_plans

    # 関数シグネチャに current_user（Depends(get_current_user)）がないこと
    sig = inspect.signature(get_plans)
    assert "current_user" not in sig.parameters, \
        "get_plans() に認証依存が含まれている（認証不要のエンドポイントのはず）"

    # 実際に引数なしで呼べること
    plans_doc = {"key": "plans", "value": [{"id": "plan_basic"}]}
    mock_db = build_mock_db({"system_settings": make_col(find_one=plans_doc)})

    with patch("app.api.routes.system_settings.get_database", return_value=mock_db):
        result = await get_plans()

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_ai_credit_limits_requires_auth():
    """get_ai_credit_limits() が一般法人ユーザーに 403 を返すこと（Admin 以外はアクセス不可）。"""
    from fastapi import HTTPException
    from app.api.routes.system_settings import get_ai_credit_limits

    # corporateType="corporate"（tax_firm でも admin でもない）
    non_admin_corp = {
        "_id": ObjectId(),
        "firebase_uid": "corp_user",
        "corporateType": "corporate",
    }
    mock_db = build_mock_db({
        "corporates": make_col(find_one=non_admin_corp),
        "employees": make_col(find_one=None),
    })

    with patch("app.api.routes.system_settings.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await get_ai_credit_limits({"uid": "corp_user"})

    assert exc.value.status_code == 403
