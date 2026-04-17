"""
Tests for Task#30: Stripe Webhook + stripe_service

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_stripe_webhook.py -v
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

SUB_ID = "sub_test_123"
CUSTOMER_ID = "cus_test_456"


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_col():
    col = MagicMock()
    col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    return col


def build_mock_db(collections: dict = None):
    db = MagicMock()
    cols = collections or {}
    db.__getitem__ = MagicMock(side_effect=lambda k: cols.get(k, make_col()))
    return db


def make_stripe_event(event_type: str, data: dict) -> MagicMock:
    """Stripe イベントオブジェクトのモックを生成する。"""
    event = MagicMock()
    event.__getitem__ = MagicMock(side_effect=lambda k: {
        "type": event_type,
        "data": {"object": data},
    }[k])
    return event


async def _call_webhook(event_type: str, data: dict, mock_db=None):
    """Webhook エンドポイントを直接呼ぶヘルパー。"""
    from fastapi import Request
    from app.api.routes.stripe_webhook import stripe_webhook

    body = json.dumps({"type": event_type, "data": {"object": data}}).encode()
    mock_request = MagicMock(spec=Request)
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = {"stripe-signature": "test_sig"}

    mock_event = make_stripe_event(event_type, data)

    with patch("app.api.routes.stripe_webhook.construct_webhook_event", return_value=mock_event), \
         patch("app.api.routes.stripe_webhook.get_database", return_value=mock_db or build_mock_db()):
        return await stripe_webhook(mock_request)


# ─────────────────────────────────────────────────────────────────────────────
# test_webhook_invalid_signature_returns_400
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_400():
    """不正なシグネチャで 400 が返ること。"""
    import stripe
    from fastapi import HTTPException, Request
    from app.api.routes.stripe_webhook import stripe_webhook

    mock_request = MagicMock(spec=Request)
    mock_request.body = AsyncMock(return_value=b"payload")
    mock_request.headers = {"stripe-signature": "invalid_sig"}

    with patch(
        "app.api.routes.stripe_webhook.construct_webhook_event",
        side_effect=stripe.SignatureVerificationError("bad sig", "invalid_sig"),
    ):
        with pytest.raises(HTTPException) as exc:
            await stripe_webhook(mock_request)

    assert exc.value.status_code == 400
    assert "signature" in exc.value.detail.lower()


# ─────────────────────────────────────────────────────────────────────────────
# test_payment_succeeded_sets_active
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_payment_succeeded_sets_active():
    """invoice.payment_succeeded イベントで is_active=True になること。"""
    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "invoice.payment_succeeded",
        {"subscription": SUB_ID},
        mock_db,
    )

    assert result == {"status": "ok"}
    corp_col.update_one.assert_called_once()
    filter_arg, update_arg = corp_col.update_one.call_args[0]
    assert filter_arg == {"stripe_subscription_id": SUB_ID}
    assert update_arg["$set"]["is_active"] is True


# ─────────────────────────────────────────────────────────────────────────────
# test_payment_failed_logs_warning
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_payment_failed_logs_warning():
    """invoice.payment_failed イベントでクラッシュしないこと。200 が返ること。"""
    result = await _call_webhook(
        "invoice.payment_failed",
        {"subscription": SUB_ID, "customer": CUSTOMER_ID},
    )
    assert result == {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# test_subscription_deleted_sets_inactive
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscription_deleted_sets_inactive():
    """customer.subscription.deleted イベントで is_active=False になること。"""
    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "customer.subscription.deleted",
        {"id": SUB_ID},
        mock_db,
    )

    assert result == {"status": "ok"}
    corp_col.update_one.assert_called_once()
    filter_arg, update_arg = corp_col.update_one.call_args[0]
    assert filter_arg == {"stripe_subscription_id": SUB_ID}
    assert update_arg["$set"]["is_active"] is False
    assert update_arg["$set"]["stripe_subscription_id"] is None


# ─────────────────────────────────────────────────────────────────────────────
# test_subscription_updated_changes_plan
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscription_updated_changes_plan():
    """customer.subscription.updated イベントで planId が更新されること。"""
    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "customer.subscription.updated",
        {"id": SUB_ID, "metadata": {"plan_id": "plan_premium"}},
        mock_db,
    )

    assert result == {"status": "ok"}
    corp_col.update_one.assert_called_once()
    _, update_arg = corp_col.update_one.call_args[0]
    assert update_arg["$set"]["planId"] == "plan_premium"


# ─────────────────────────────────────────────────────────────────────────────
# test_unknown_event_returns_ok
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_event_returns_ok():
    """未知のイベントタイプで 200 が返ること・クラッシュしないこと。"""
    result = await _call_webhook(
        "some.unknown.event",
        {"id": "unknown_id"},
    )
    assert result == {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# test_stripe_customer_created_on_registration
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stripe_customer_created_on_registration():
    """新規登録時に stripe_customer_id が corporates に保存されること。"""
    from app.api.routes.users import register_corporate_user
    from app.models.user import CorporateUserCreate

    corp_col = make_col()
    corp_col.find_one = AsyncMock(return_value=None)
    profile_col = make_col()
    mock_db = build_mock_db({
        "corporates": corp_col,
        "company_profiles": profile_col,
    })

    payload = CorporateUserCreate(
        corporateType="corporate",
        companyName="テスト株式会社",
        planId="plan_basic",
        monthlyFee=15000,
    )
    current_user = {"uid": "test_firebase_uid"}

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.services.stripe_service.create_stripe_customer",
               new_callable=AsyncMock, return_value="cus_new_123") as mock_stripe, \
         patch("firebase_admin.firestore", create=True):
        result = await register_corporate_user(payload, current_user)

    mock_stripe.assert_called_once_with(
        firebase_uid="test_firebase_uid",
        email="",
        name="テスト株式会社",
    )
    # stripe_customer_id が update_one で保存されること
    update_calls = [c for c in corp_col.update_one.call_args_list]
    stripe_update = next(
        (c for c in update_calls if c[0][1].get("$set", {}).get("stripe_customer_id")),
        None,
    )
    assert stripe_update is not None
    assert stripe_update[0][1]["$set"]["stripe_customer_id"] == "cus_new_123"


# ─────────────────────────────────────────────────────────────────────────────
# test_stripe_failure_does_not_break_registration
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stripe_failure_does_not_break_registration():
    """Stripe API が失敗しても登録フロー自体は成功すること。"""
    from app.api.routes.users import register_corporate_user
    from app.models.user import CorporateUserCreate

    corp_col = make_col()
    corp_col.find_one = AsyncMock(return_value=None)
    profile_col = make_col()
    mock_db = build_mock_db({
        "corporates": corp_col,
        "company_profiles": profile_col,
    })

    payload = CorporateUserCreate(
        corporateType="corporate",
        companyName="テスト株式会社",
        planId="plan_basic",
        monthlyFee=15000,
    )
    current_user = {"uid": "test_firebase_uid"}

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.services.stripe_service.create_stripe_customer",
               new_callable=AsyncMock, return_value=None) as mock_stripe, \
         patch("firebase_admin.firestore", create=True):
        result = await register_corporate_user(payload, current_user)

    # Stripe 失敗でも登録は成功
    assert "message" in result
    # Stripe 失敗時は stripe_customer_id の update_one が呼ばれないこと
    update_calls = [c for c in corp_col.update_one.call_args_list]
    stripe_update = next(
        (c for c in update_calls if c[0][1].get("$set", {}).get("stripe_customer_id")),
        None,
    )
    assert stripe_update is None


# =============================================================================
# 意地悪テスト（Task#30）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① シグネチャ検証テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_missing_signature_header_returns_400():
    """stripe-signature ヘッダーなしで 400 が返ること。"""
    import stripe
    from fastapi import HTTPException, Request
    from app.api.routes.stripe_webhook import stripe_webhook

    mock_request = MagicMock(spec=Request)
    mock_request.body = AsyncMock(return_value=b"payload")
    mock_request.headers = {}  # ヘッダーなし → sig_header = ""

    with patch(
        "app.api.routes.stripe_webhook.construct_webhook_event",
        side_effect=stripe.SignatureVerificationError("missing sig", ""),
    ):
        with pytest.raises(HTTPException) as exc:
            await stripe_webhook(mock_request)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_webhook_empty_signature_returns_400():
    """stripe-signature="" （空文字）で 400 が返ること。"""
    import stripe
    from fastapi import HTTPException, Request
    from app.api.routes.stripe_webhook import stripe_webhook

    mock_request = MagicMock(spec=Request)
    mock_request.body = AsyncMock(return_value=b"payload")
    mock_request.headers = {"stripe-signature": ""}

    with patch(
        "app.api.routes.stripe_webhook.construct_webhook_event",
        side_effect=stripe.SignatureVerificationError("empty sig", ""),
    ):
        with pytest.raises(HTTPException) as exc:
            await stripe_webhook(mock_request)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_webhook_tampered_payload_returns_400():
    """正しいシグネチャだがペイロードを改ざんした場合に 400 が返ること。"""
    import stripe
    from fastapi import HTTPException, Request
    from app.api.routes.stripe_webhook import stripe_webhook

    mock_request = MagicMock(spec=Request)
    mock_request.body = AsyncMock(return_value=b"tampered_payload")
    mock_request.headers = {"stripe-signature": "valid_sig_for_original"}

    with patch(
        "app.api.routes.stripe_webhook.construct_webhook_event",
        side_effect=stripe.SignatureVerificationError("payload mismatch", "valid_sig"),
    ):
        with pytest.raises(HTTPException) as exc:
            await stripe_webhook(mock_request)

    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# ② payment_succeeded の耐久テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_payment_succeeded_without_subscription_id():
    """subscription フィールドが null の場合にクラッシュしないこと・DB 更新なし。"""
    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "invoice.payment_succeeded",
        {"subscription": None},  # null
        mock_db,
    )

    assert result == {"status": "ok"}
    corp_col.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_payment_succeeded_unknown_subscription():
    """存在しない subscription_id でも matched_count=0 で 200 が返ること。"""
    corp_col = make_col()
    corp_col.update_one = AsyncMock(return_value=MagicMock(modified_count=0))
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "invoice.payment_succeeded",
        {"subscription": "sub_nonexistent"},
        mock_db,
    )

    assert result == {"status": "ok"}
    corp_col.update_one.assert_called_once()  # 呼ばれるが更新なし（正常）


# ─────────────────────────────────────────────────────────────────────────────
# ③ subscription.deleted の耐久テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscription_deleted_clears_subscription_id():
    """subscription.deleted 後に stripe_subscription_id=None・is_active=False になること。"""
    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "customer.subscription.deleted",
        {"id": SUB_ID},
        mock_db,
    )

    assert result == {"status": "ok"}
    _, update_arg = corp_col.update_one.call_args[0]
    assert update_arg["$set"]["is_active"] is False
    assert update_arg["$set"]["stripe_subscription_id"] is None


@pytest.mark.asyncio
async def test_subscription_deleted_unknown_id():
    """存在しない subscription_id でもクラッシュしないこと。"""
    corp_col = make_col()
    corp_col.update_one = AsyncMock(return_value=MagicMock(modified_count=0))
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "customer.subscription.deleted",
        {"id": "sub_unknown_xyz"},
        mock_db,
    )

    assert result == {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# ④ subscription.updated のテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscription_updated_without_plan_id_in_metadata():
    """metadata に plan_id がない場合に planId が更新されないこと。"""
    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "customer.subscription.updated",
        {"id": SUB_ID, "metadata": {"other_key": "other_value"}},  # plan_id なし
        mock_db,
    )

    assert result == {"status": "ok"}
    corp_col.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_subscription_updated_empty_metadata():
    """metadata が空の場合にクラッシュしないこと。"""
    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "customer.subscription.updated",
        {"id": SUB_ID, "metadata": {}},
        mock_db,
    )

    assert result == {"status": "ok"}
    corp_col.update_one.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ payment_intent.succeeded のテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_payment_intent_succeeded_without_customer():
    """customer フィールドが null の場合にクラッシュしないこと。"""
    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "payment_intent.succeeded",
        {"customer": None},
        mock_db,
    )

    assert result == {"status": "ok"}
    corp_col.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_payment_intent_succeeded_unknown_customer():
    """存在しない stripe_customer_id でもクラッシュしないこと・200 が返ること。"""
    corp_col = make_col()
    corp_col.update_one = AsyncMock(return_value=MagicMock(modified_count=0))
    mock_db = build_mock_db({"corporates": corp_col})

    result = await _call_webhook(
        "payment_intent.succeeded",
        {"customer": "cus_nonexistent"},
        mock_db,
    )

    assert result == {"status": "ok"}
    corp_col.update_one.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ Stripe Customer 作成のテスト
# ─────────────────────────────────────────────────────────────────────────────

def _make_register_db():
    corp_col = make_col()
    corp_col.find_one = AsyncMock(return_value=None)
    profile_col = make_col()
    return build_mock_db({"corporates": corp_col, "company_profiles": profile_col}), corp_col


@pytest.mark.asyncio
async def test_stripe_customer_id_saved_on_register():
    """登録時に stripe_customer_id が corporates に保存されること。"""
    from app.api.routes.users import register_corporate_user
    from app.models.user import CorporateUserCreate

    mock_db, corp_col = _make_register_db()
    payload = CorporateUserCreate(corporateType="corporate", companyName="テスト", planId="plan_basic", monthlyFee=0)

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.services.stripe_service.create_stripe_customer", new_callable=AsyncMock, return_value="cus_saved"), \
         patch("firebase_admin.firestore", create=True):
        await register_corporate_user(payload, {"uid": "uid_save"})

    calls = corp_col.update_one.call_args_list
    stripe_call = next((c for c in calls if c[0][1].get("$set", {}).get("stripe_customer_id")), None)
    assert stripe_call is not None
    assert stripe_call[0][1]["$set"]["stripe_customer_id"] == "cus_saved"


@pytest.mark.asyncio
async def test_billing_type_tax_firm_covered_for_client():
    """advising_tax_firm_id がある法人は billing_type='tax_firm_covered' になること。"""
    from app.api.routes.users import register_corporate_user
    from app.models.user import CorporateUserCreate

    mock_db, corp_col = _make_register_db()
    payload = CorporateUserCreate(
        corporateType="corporate", companyName="顧客A", planId="plan_basic", monthlyFee=0,
        advising_tax_firm_id="tax_firm_uid_123",
    )

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.services.stripe_service.create_stripe_customer", new_callable=AsyncMock, return_value="cus_client"), \
         patch("firebase_admin.firestore", create=True):
        await register_corporate_user(payload, {"uid": "uid_client"})

    calls = corp_col.update_one.call_args_list
    stripe_call = next((c for c in calls if c[0][1].get("$set", {}).get("stripe_customer_id")), None)
    assert stripe_call is not None
    assert stripe_call[0][1]["$set"]["billing_type"] == "tax_firm_covered"


@pytest.mark.asyncio
async def test_billing_type_self_pay_for_independent():
    """advising_tax_firm_id がない法人は billing_type='self_pay' になること。"""
    from app.api.routes.users import register_corporate_user
    from app.models.user import CorporateUserCreate

    mock_db, corp_col = _make_register_db()
    payload = CorporateUserCreate(
        corporateType="corporate", companyName="独立法人", planId="plan_basic", monthlyFee=0,
        # advising_tax_firm_id なし
    )

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.services.stripe_service.create_stripe_customer", new_callable=AsyncMock, return_value="cus_indep"), \
         patch("firebase_admin.firestore", create=True):
        await register_corporate_user(payload, {"uid": "uid_indep"})

    calls = corp_col.update_one.call_args_list
    stripe_call = next((c for c in calls if c[0][1].get("$set", {}).get("stripe_customer_id")), None)
    assert stripe_call is not None
    assert stripe_call[0][1]["$set"]["billing_type"] == "self_pay"


@pytest.mark.asyncio
async def test_stripe_api_failure_does_not_block_registration():
    """stripe.Customer.create が例外を投げても登録が成功すること。"""
    from app.api.routes.users import register_corporate_user
    from app.models.user import CorporateUserCreate

    mock_db, corp_col = _make_register_db()
    payload = CorporateUserCreate(corporateType="corporate", companyName="テスト", planId="plan_basic", monthlyFee=0)

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.services.stripe_service.create_stripe_customer",
               new_callable=AsyncMock, return_value=None) as mock_create, \
         patch("firebase_admin.firestore", create=True):
        result = await register_corporate_user(payload, {"uid": "uid_fail"})

    assert "message" in result
    # Stripe 失敗時は stripe_customer_id の update_one が呼ばれないこと
    calls = corp_col.update_one.call_args_list
    stripe_call = next((c for c in calls if c[0][1].get("$set", {}).get("stripe_customer_id")), None)
    assert stripe_call is None, "Stripe 失敗時に stripe_customer_id を保存してはいけない"


# ─────────────────────────────────────────────────────────────────────────────
# ⑦ 冪等性テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_same_event_processed_twice_no_duplicate():
    """
    同じ invoice.payment_succeeded を2回送っても
    is_active=True の $set が2回呼ばれるだけで異常な状態にならないこと。
    （Stripe は $set で冪等に更新するため重複は無害）
    """
    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    result1 = await _call_webhook("invoice.payment_succeeded", {"subscription": SUB_ID}, mock_db)
    result2 = await _call_webhook("invoice.payment_succeeded", {"subscription": SUB_ID}, mock_db)

    assert result1 == {"status": "ok"}
    assert result2 == {"status": "ok"}
    # 2回 update_one が呼ばれること（$set は冪等）
    assert corp_col.update_one.call_count == 2
    # 両方とも is_active=True を $set していること
    for call in corp_col.update_one.call_args_list:
        assert call[0][1]["$set"]["is_active"] is True


@pytest.mark.asyncio
async def test_subscription_deleted_then_payment_succeeded():
    """
    subscription.deleted の後に payment_succeeded が来た場合に
    is_active が True に戻ること（Stripe のリトライを想定）。
    """
    corp_col = make_col()
    mock_db = build_mock_db({"corporates": corp_col})

    # 1. 解約イベント
    await _call_webhook("customer.subscription.deleted", {"id": SUB_ID}, mock_db)
    deleted_call = corp_col.update_one.call_args_list[0]
    assert deleted_call[0][1]["$set"]["is_active"] is False

    # 2. その後に決済成功（リトライ想定）
    await _call_webhook("invoice.payment_succeeded", {"subscription": SUB_ID}, mock_db)
    succeeded_call = corp_col.update_one.call_args_list[1]
    assert succeeded_call[0][1]["$set"]["is_active"] is True, \
        "payment_succeeded が来たら is_active が True に戻ること"
