"""
Tests for Task#30追加: 解約エンドポイント（POST /users/cancel）

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_cancel.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime

CORP_ID = str(ObjectId())
TAX_FIRM_UID = "tax_firm_firebase_uid"
CORP_UID = "corp_firebase_uid"

ACTIVE_CORP = {
    "_id": ObjectId(CORP_ID),
    "firebase_uid": CORP_UID,
    "corporateType": "corporate",
    "is_active": True,
    "stripe_subscription_id": "sub_test_123",
}
ACTIVE_TAX_FIRM = {
    "_id": ObjectId(CORP_ID),
    "firebase_uid": TAX_FIRM_UID,
    "corporateType": "tax_firm",
    "is_active": True,
    "stripe_subscription_id": "sub_taxfirm_456",
}
ALREADY_CANCELLED = {
    "_id": ObjectId(CORP_ID),
    "firebase_uid": CORP_UID,
    "corporateType": "corporate",
    "is_active": False,
}


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_col(find_one=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    col.update_many = AsyncMock(return_value=MagicMock(modified_count=2))
    return col


def build_mock_db(corp_doc=None):
    db = MagicMock()
    corp_col = make_col(find_one=corp_doc)
    db.__getitem__ = MagicMock(side_effect=lambda k: corp_col if k == "corporates" else make_col())
    return db, corp_col


async def _call_cancel(corp_doc, firebase_uid=CORP_UID, mock_cancel_sub=None):
    """cancel_service を直接呼ぶヘルパー。"""
    from app.api.routes.users import cancel_service

    mock_db, corp_col = build_mock_db(corp_doc)
    current_user = {"uid": firebase_uid}

    patches = [
        patch("app.api.routes.users.get_database", return_value=mock_db),
        patch("app.api.routes.users.resolve_corporate_id",
              new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)),
    ]
    if mock_cancel_sub is not None:
        patches.append(
            patch("app.services.stripe_service.cancel_subscription",
                  new_callable=AsyncMock, return_value=mock_cancel_sub)
        )

    with patches[0], patches[1]:
        if len(patches) > 2:
            with patches[2] as mock_stripe:
                result = await cancel_service(current_user)
            return result, corp_col, mock_stripe
        result = await cancel_service(current_user)
    return result, corp_col, None


# ─────────────────────────────────────────────────────────────────────────────
# test_cancel_sets_inactive
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_sets_inactive():
    """POST /users/cancel で is_active=False になること。"""
    result, corp_col, _ = await _call_cancel(ACTIVE_CORP, mock_cancel_sub=True)

    assert result["status"] == "cancelled"
    corp_col.update_one.assert_called_once()
    _, update_arg = corp_col.update_one.call_args[0]
    assert update_arg["$set"]["is_active"] is False


# ─────────────────────────────────────────────────────────────────────────────
# test_cancel_records_cancelled_at
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_records_cancelled_at():
    """cancelled_at が記録されること・レスポンスに含まれること。"""
    result, corp_col, _ = await _call_cancel(ACTIVE_CORP, mock_cancel_sub=True)

    assert "cancelled_at" in result
    # update_one の $set にも cancelled_at が含まれること
    _, update_arg = corp_col.update_one.call_args[0]
    assert "cancelled_at" in update_arg["$set"]


# ─────────────────────────────────────────────────────────────────────────────
# test_cancel_already_cancelled_returns_400
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_already_cancelled_returns_400():
    """既に解約済みの場合に 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.users import cancel_service

    mock_db, _ = build_mock_db(ALREADY_CANCELLED)
    current_user = {"uid": CORP_UID}

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)):
        with pytest.raises(HTTPException) as exc:
            await cancel_service(current_user)

    assert exc.value.status_code == 400
    assert "解約済み" in exc.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# test_cancel_tax_firm_deactivates_clients
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_tax_firm_deactivates_clients():
    """税理士法人が解約すると update_many で配下法人も is_active=False になること。"""
    from app.api.routes.users import cancel_service

    mock_db, corp_col = build_mock_db(ACTIVE_TAX_FIRM)
    current_user = {"uid": TAX_FIRM_UID}

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.services.stripe_service.cancel_subscription",
               new_callable=AsyncMock, return_value=True):
        result = await cancel_service(current_user)

    assert result["status"] == "cancelled"
    # update_many が呼ばれること
    corp_col.update_many.assert_called_once()
    filter_arg, update_arg = corp_col.update_many.call_args[0]
    assert filter_arg == {"advising_tax_firm_id": TAX_FIRM_UID}
    assert update_arg["$set"]["is_active"] is False


# ─────────────────────────────────────────────────────────────────────────────
# test_cancel_corporate_does_not_affect_others
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_corporate_does_not_affect_others():
    """一般法人が解約しても他法人に影響しないこと（update_many が呼ばれないこと）。"""
    result, corp_col, _ = await _call_cancel(ACTIVE_CORP, mock_cancel_sub=True)

    assert result["status"] == "cancelled"
    # 一般法人は update_many を呼ばないこと
    corp_col.update_many.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# test_cancel_clears_subscription_id
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_clears_subscription_id():
    """解約後に stripe_subscription_id が None になること。"""
    result, corp_col, _ = await _call_cancel(ACTIVE_CORP, mock_cancel_sub=True)

    _, update_arg = corp_col.update_one.call_args[0]
    assert update_arg["$set"]["stripe_subscription_id"] is None


# ─────────────────────────────────────────────────────────────────────────────
# test_cancel_without_subscription_no_crash
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_without_subscription_no_crash():
    """
    stripe_subscription_id が null の場合でもクラッシュしないこと。
    ③ cancel_subscription が呼ばれないことも確認する。
    """
    from app.api.routes.users import cancel_service

    corp_no_sub = {**ACTIVE_CORP, "stripe_subscription_id": None}
    mock_db, corp_col = build_mock_db(corp_no_sub)
    current_user = {"uid": CORP_UID}

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.services.stripe_service.cancel_subscription",
               new_callable=AsyncMock, return_value=True) as mock_cancel:
        result = await cancel_service(current_user)

    assert result["status"] == "cancelled"
    # subscription_id が null なので cancel_subscription は呼ばれないこと
    mock_cancel.assert_not_called()


# =============================================================================
# 意地悪テスト（Task#30追加 解約）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① 権限テスト
# ─────────────────────────────────────────────────────────────────────────────

async def _call_cancel_as_employee(role: str):
    """指定ロールの従業員として cancel_service を呼ぶヘルパー。"""
    from fastapi import HTTPException
    from app.api.routes.users import cancel_service

    emp_uid = f"emp_{role}_uid"
    emp_doc = {"_id": ObjectId(), "firebase_uid": emp_uid, "role": role}
    mock_db = MagicMock()
    # corporates: オーナーとして存在しない（None）
    # employees: ロール付き従業員として存在
    async def _find_one(query, *a, **k):
        if query.get("firebase_uid") == emp_uid and "firebase_uid" in query:
            # employees検索には返す、corporates検索にはNoneを返す
            return None  # corporates側はNone
        return None
    corp_col = MagicMock()
    corp_col.find_one = AsyncMock(return_value=None)
    emp_col = MagicMock()
    emp_col.find_one = AsyncMock(return_value=emp_doc)

    mock_db.__getitem__ = MagicMock(side_effect=lambda k: corp_col if k == "corporates" else emp_col)

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)):
        return await cancel_service({"uid": emp_uid})


@pytest.mark.asyncio
async def test_staff_cannot_cancel():
    """staff ロールの従業員が POST /users/cancel を呼ぶと 403 が返ること。"""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await _call_cancel_as_employee("staff")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_accounting_cannot_cancel():
    """accounting ロールの従業員が POST /users/cancel を呼ぶと 403 が返ること。"""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await _call_cancel_as_employee("accounting")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_cancel():
    """firebase_uid=None（認証なし相当）で 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.users import cancel_service

    mock_db, _ = build_mock_db(None)

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock,
               side_effect=HTTPException(status_code=403, detail="Access denied")):
        with pytest.raises(HTTPException) as exc:
            await cancel_service({"uid": None})

    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# ② 二重解約・冪等性テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_twice_returns_400():
    """解約済みの法人が再度 POST /users/cancel を呼ぶと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.users import cancel_service

    mock_db, _ = build_mock_db(ALREADY_CANCELLED)

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)):
        with pytest.raises(HTTPException) as exc:
            await cancel_service({"uid": CORP_UID})

    assert exc.value.status_code == 400
    assert "解約済み" in exc.value.detail


@pytest.mark.asyncio
async def test_cancel_after_reactivation():
    """is_active=False → True に戻した後に再度解約できること。"""
    from app.api.routes.users import cancel_service

    reactivated = {**ALREADY_CANCELLED, "is_active": True, "cancelled_at": None,
                   "stripe_subscription_id": None}
    mock_db, corp_col = build_mock_db(reactivated)

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)):
        result = await cancel_service({"uid": CORP_UID})

    assert result["status"] == "cancelled"
    # cancelled_at が更新されること
    _, update_arg = corp_col.update_one.call_args[0]
    assert update_arg["$set"]["cancelled_at"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# ③ 税理士法人解約の影響範囲テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_tax_firm_only_affects_own_clients():
    """税理士法人Aが解約した場合にfilterが自分のfirebase_uidに限定されること。"""
    from app.api.routes.users import cancel_service

    mock_db, corp_col = build_mock_db(ACTIVE_TAX_FIRM)

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.services.stripe_service.cancel_subscription",
               new_callable=AsyncMock, return_value=True):
        await cancel_service({"uid": TAX_FIRM_UID})

    # update_many のフィルタが TAX_FIRM_UID（自分のfirebase_uid）に限定されていること
    filter_arg = corp_col.update_many.call_args[0][0]
    assert filter_arg == {"advising_tax_firm_id": TAX_FIRM_UID}, \
        "別の税理士法人の顧客を巻き込むフィルタになっていないこと"


@pytest.mark.asyncio
async def test_cancel_tax_firm_preserves_client_stripe_id():
    """税理士法人が解約しても配下法人の stripe_customer_id は変更されないこと。"""
    from app.api.routes.users import cancel_service

    mock_db, corp_col = build_mock_db(ACTIVE_TAX_FIRM)

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.services.stripe_service.cancel_subscription",
               new_callable=AsyncMock, return_value=True):
        await cancel_service({"uid": TAX_FIRM_UID})

    # update_many の $set に stripe_customer_id が含まれていないこと
    update_arg = corp_col.update_many.call_args[0][1]
    assert "stripe_customer_id" not in update_arg["$set"], \
        "配下法人の stripe_customer_id を変更してはいけない"


@pytest.mark.asyncio
async def test_cancel_corporate_does_not_affect_tax_firm():
    """配下法人が解約しても税理士法人の is_active は変わらないこと。"""
    result, corp_col, _ = await _call_cancel(ACTIVE_CORP, mock_cancel_sub=True)

    assert result["status"] == "cancelled"
    # update_many が呼ばれていないこと（税理士法人に波及しない）
    corp_col.update_many.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# ④ データ保持テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_does_not_delete_receipts():
    """解約処理で receipts コレクションのデータが削除されないこと。"""
    from app.api.routes.users import cancel_service

    mock_db, corp_col = build_mock_db(ACTIVE_CORP)
    receipts_col = make_col()
    mock_db.__getitem__ = MagicMock(side_effect=lambda k: {
        "corporates": corp_col,
        "receipts": receipts_col,
        "employees": make_col(find_one=None),
    }.get(k, make_col()))

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)):
        await cancel_service({"uid": CORP_UID})

    # receipts に対して削除系操作が呼ばれていないこと
    assert not hasattr(receipts_col, "delete_one") or receipts_col.delete_one.call_count == 0
    assert not hasattr(receipts_col, "delete_many") or receipts_col.delete_many.call_count == 0


@pytest.mark.asyncio
async def test_cancel_does_not_delete_invoices():
    """解約処理で invoices コレクションのデータが削除されないこと。"""
    from app.api.routes.users import cancel_service

    mock_db, corp_col = build_mock_db(ACTIVE_CORP)
    invoices_col = make_col()
    mock_db.__getitem__ = MagicMock(side_effect=lambda k: {
        "corporates": corp_col,
        "invoices": invoices_col,
        "employees": make_col(find_one=None),
    }.get(k, make_col()))

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)):
        await cancel_service({"uid": CORP_UID})

    assert not hasattr(invoices_col, "delete_one") or invoices_col.delete_one.call_count == 0
    assert not hasattr(invoices_col, "delete_many") or invoices_col.delete_many.call_count == 0


@pytest.mark.asyncio
async def test_cancelled_at_is_recorded():
    """cancelled_at が None でなく ISO 形式で返ること。"""
    result, _, _ = await _call_cancel(ACTIVE_CORP, mock_cancel_sub=True)

    assert result.get("cancelled_at") is not None
    # ISO 8601 形式であることを確認
    try:
        datetime.fromisoformat(result["cancelled_at"])
    except ValueError:
        pytest.fail(f"cancelled_at が ISO 形式でない: {result['cancelled_at']}")


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ Stripe キャンセルの耐久テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_stripe_failure_still_deactivates():
    """
    cancel_subscription が例外を投げても is_active=False になること。
    ⑤ Stripe 失敗でも解約処理が止まらないことを確認する。
    """
    from app.api.routes.users import cancel_service

    mock_db, corp_col = build_mock_db(ACTIVE_CORP)

    with patch("app.api.routes.users.get_database", return_value=mock_db), \
         patch("app.api.routes.users.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)), \
         patch("app.services.stripe_service.cancel_subscription",
               new_callable=AsyncMock,
               side_effect=RuntimeError("Stripe service unavailable")):
        result = await cancel_service({"uid": CORP_UID})

    # Stripe が失敗しても解約レスポンスが返ること
    assert result["status"] == "cancelled"
    # is_active=False の update が呼ばれていること
    corp_col.update_one.assert_called_once()
    _, update_arg = corp_col.update_one.call_args[0]
    assert update_arg["$set"]["is_active"] is False


@pytest.mark.asyncio
async def test_cancel_subscription_id_cleared_on_success():
    """解約成功後に stripe_subscription_id が None になること。"""
    result, corp_col, _ = await _call_cancel(ACTIVE_CORP, mock_cancel_sub=True)

    assert result["status"] == "cancelled"
    _, update_arg = corp_col.update_one.call_args[0]
    assert update_arg["$set"]["stripe_subscription_id"] is None
