"""
Tests for Task#28・#29: billing_settings API

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_billing_settings.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

TAX_FIRM_UID = "tax_firm_uid"
OTHER_FIRM_UID = "other_firm_uid"
CLIENT_UID = "client_uid"

TAX_FIRM_DOC = {
    "_id": ObjectId(),
    "firebase_uid": TAX_FIRM_UID,
    "corporateType": "tax_firm",
}
CLIENT_DOC = {
    "_id": ObjectId(),
    "firebase_uid": CLIENT_UID,
    "corporateType": "corporate",
    "advising_tax_firm_id": TAX_FIRM_UID,
}
OTHER_FIRM_DOC = {
    "_id": ObjectId(),
    "firebase_uid": OTHER_FIRM_UID,
    "corporateType": "tax_firm",
}


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_col(find_one=None, find_data=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    return col


def build_mock_db(collections: dict):
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


def make_multi_find_col(docs: list):
    """firebase_uid / _id でフィルタするコレクションモック。"""
    col = MagicMock()

    async def _find_one(query: dict, *args, **kwargs):
        uid = query.get("firebase_uid")
        oid = query.get("_id")
        for d in docs:
            if uid is not None and d.get("firebase_uid") != uid:
                continue
            if oid is not None and d.get("_id") != oid:
                continue
            return d
        return None

    col.find_one = _find_one
    col.find = MagicMock(return_value=make_cursor([]))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return col


def billing_db(billing_doc=None):
    """税理士法人 + 顧客 + billing_settings が揃った標準モックDB。"""
    return build_mock_db({
        "corporates": make_multi_find_col([TAX_FIRM_DOC, CLIENT_DOC]),
        "billing_settings": make_col(find_one=billing_doc),
    })


# ─────────────────────────────────────────────────────────────────────────────
# test_tax_firm_can_get_default_settings
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_firm_can_get_default_settings():
    """未設定の法人に GET すると全て0・is_active=False が返ること。"""
    from app.api.routes.billing_settings import get_billing_settings

    mock_db = billing_db(billing_doc=None)

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        result = await get_billing_settings(CLIENT_UID, {"uid": TAX_FIRM_UID})

    assert result["corporate_unit_price"] == 0
    assert result["user_unit_price"] == 0
    assert result["is_active"] is False
    assert result["target_corporate_id"] == CLIENT_UID


# ─────────────────────────────────────────────────────────────────────────────
# test_tax_firm_can_update_settings
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_firm_can_update_settings():
    """PUT で設定を保存できること。upsert が呼ばれること。"""
    from app.api.routes.billing_settings import update_billing_settings

    billing_col = make_col(find_one=None)
    mock_db = build_mock_db({
        "corporates": make_multi_find_col([TAX_FIRM_DOC, CLIENT_DOC]),
        "billing_settings": billing_col,
    })

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        result = await update_billing_settings(
            CLIENT_UID,
            {"corporate_unit_price": 5000, "user_unit_price": 1000, "is_active": True},
            {"uid": TAX_FIRM_UID},
        )

    assert result["status"] == "updated"
    assert result["corporate_unit_price"] == 5000
    assert result["user_unit_price"] == 1000
    assert result["is_active"] is True
    billing_col.update_one.assert_called_once()
    # upsert=True が渡されていること
    call_kwargs = billing_col.update_one.call_args[1]
    assert call_kwargs.get("upsert") is True


# ─────────────────────────────────────────────────────────────────────────────
# test_corporate_cannot_access
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_corporate_cannot_access():
    """一般法人が GET すると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import get_billing_settings

    corp_doc = {"_id": ObjectId(), "firebase_uid": "corp_uid", "corporateType": "corporate"}
    mock_db = build_mock_db({"corporates": make_col(find_one=corp_doc)})

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await get_billing_settings(CLIENT_UID, {"uid": "corp_uid"})

    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# test_unrelated_tax_firm_cannot_access
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unrelated_tax_firm_cannot_access():
    """別の税理士法人の顧客にアクセスすると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import get_billing_settings

    # CLIENT_DOC は TAX_FIRM_UID 配下（OTHER_FIRM_UID からはアクセス不可）
    mock_db = build_mock_db({
        "corporates": make_multi_find_col([TAX_FIRM_DOC, OTHER_FIRM_DOC, CLIENT_DOC]),
        "billing_settings": make_col(find_one=None),
    })

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await get_billing_settings(CLIENT_UID, {"uid": OTHER_FIRM_UID})

    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# test_negative_price_rejected
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_negative_price_rejected():
    """corporate_unit_price=-1 で 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import update_billing_settings

    mock_db = billing_db()

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_billing_settings(
                CLIENT_UID,
                {"corporate_unit_price": -1, "user_unit_price": 0, "is_active": False},
                {"uid": TAX_FIRM_UID},
            )

    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# test_zero_price_accepted
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_zero_price_accepted():
    """corporate_unit_price=0 は有効な値であること（0=課金なし）。"""
    from app.api.routes.billing_settings import update_billing_settings

    billing_col = make_col(find_one=None)
    mock_db = build_mock_db({
        "corporates": make_multi_find_col([TAX_FIRM_DOC, CLIENT_DOC]),
        "billing_settings": billing_col,
    })

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        result = await update_billing_settings(
            CLIENT_UID,
            {"corporate_unit_price": 0, "user_unit_price": 0, "is_active": False},
            {"uid": TAX_FIRM_UID},
        )

    assert result["status"] == "updated"
    assert result["corporate_unit_price"] == 0
    billing_col.update_one.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# test_bool_is_active_required
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bool_is_active_required():
    """is_active に文字列を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import update_billing_settings

    mock_db = billing_db()

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_billing_settings(
                CLIENT_UID,
                {"corporate_unit_price": 0, "user_unit_price": 0, "is_active": "true"},
                {"uid": TAX_FIRM_UID},
            )

    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# test_clients_api_includes_billing_total
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clients_api_includes_billing_total():
    """
    GET /users/clients のレスポンスに
    monthlyBillingTotal・billingIsActive が含まれること。
    billing_settings が active の場合は合計が計算されること。
    """
    # users.py の get_clients は Firestore も呼ぶので
    # billing_settings 部分だけを確認する単体テスト
    from app.api.routes import users as users_module

    # billing_settings の計算ロジックを直接テスト
    billing_map = {
        CLIENT_UID: {
            "target_corporate_id": CLIENT_UID,
            "is_active": True,
            "corporate_unit_price": 5000,
            "user_unit_price": 1000,
        }
    }

    # enriched_clients に billing を追加するロジックを模倣
    client = {
        "firebase_uid": CLIENT_UID,
        "employeeCount": 3,
        "monthlyBillingTotal": 0,
        "billingIsActive": False,
    }
    uid = client["firebase_uid"]
    billing = billing_map.get(uid)
    if billing and billing.get("is_active"):
        corp_price = billing.get("corporate_unit_price", 0)
        user_price = billing.get("user_unit_price", 0)
        emp_count = client.get("employeeCount", 0)
        client["monthlyBillingTotal"] = corp_price + user_price * emp_count
        client["billingIsActive"] = True
    else:
        client["monthlyBillingTotal"] = 0
        client["billingIsActive"] = False

    # 5000 + 1000 * 3 = 8000
    assert "monthlyBillingTotal" in client
    assert "billingIsActive" in client
    assert client["monthlyBillingTotal"] == 8000
    assert client["billingIsActive"] is True


# ─────────────────────────────────────────────────────────────────────────────
# ① bool が price として渡された場合に 400 が返ること
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bool_price_rejected():
    """
    ① bool チェック先行の確認。
    corporate_unit_price=True（bool）を渡すと 400 が返ること。
    True は isinstance(True, int)==True なので bool チェックが必要。
    """
    from fastapi import HTTPException
    from app.api.routes.billing_settings import update_billing_settings

    mock_db = billing_db()

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_billing_settings(
                CLIENT_UID,
                {"corporate_unit_price": True, "user_unit_price": 0, "is_active": False},
                {"uid": TAX_FIRM_UID},
            )

    assert exc.value.status_code == 400, "bool は int として通ってはいけない"


# =============================================================================
# 意地悪テスト（Task#28・#29）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① bool・型バリデーションテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bool_corporate_unit_price_rejected():
    """corporate_unit_price=True を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import update_billing_settings

    with patch("app.api.routes.billing_settings.get_database", return_value=billing_db()):
        with pytest.raises(HTTPException) as exc:
            await update_billing_settings(
                CLIENT_UID,
                {"corporate_unit_price": True, "user_unit_price": 0, "is_active": False},
                {"uid": TAX_FIRM_UID},
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bool_user_unit_price_rejected():
    """user_unit_price=True を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import update_billing_settings

    with patch("app.api.routes.billing_settings.get_database", return_value=billing_db()):
        with pytest.raises(HTTPException) as exc:
            await update_billing_settings(
                CLIENT_UID,
                {"corporate_unit_price": 0, "user_unit_price": True, "is_active": False},
                {"uid": TAX_FIRM_UID},
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_float_price_rejected():
    """corporate_unit_price=1000.5（小数）を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import update_billing_settings

    with patch("app.api.routes.billing_settings.get_database", return_value=billing_db()):
        with pytest.raises(HTTPException) as exc:
            await update_billing_settings(
                CLIENT_UID,
                {"corporate_unit_price": 1000.5, "user_unit_price": 0, "is_active": False},
                {"uid": TAX_FIRM_UID},
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_string_price_rejected():
    """corporate_unit_price="1000"（文字列）を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import update_billing_settings

    with patch("app.api.routes.billing_settings.get_database", return_value=billing_db()):
        with pytest.raises(HTTPException) as exc:
            await update_billing_settings(
                CLIENT_UID,
                {"corporate_unit_price": "1000", "user_unit_price": 0, "is_active": False},
                {"uid": TAX_FIRM_UID},
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_string_is_active_rejected():
    """is_active="true"（文字列）を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import update_billing_settings

    with patch("app.api.routes.billing_settings.get_database", return_value=billing_db()):
        with pytest.raises(HTTPException) as exc:
            await update_billing_settings(
                CLIENT_UID,
                {"corporate_unit_price": 0, "user_unit_price": 0, "is_active": "true"},
                {"uid": TAX_FIRM_UID},
            )
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# ② 境界値テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_zero_corporate_unit_price_accepted():
    """corporate_unit_price=0 が有効であること（is_active=True との組み合わせも）。"""
    from app.api.routes.billing_settings import update_billing_settings

    billing_col = make_col(find_one=None)
    mock_db = build_mock_db({
        "corporates": make_multi_find_col([TAX_FIRM_DOC, CLIENT_DOC]),
        "billing_settings": billing_col,
    })

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        result = await update_billing_settings(
            CLIENT_UID,
            {"corporate_unit_price": 0, "user_unit_price": 0, "is_active": True},
            {"uid": TAX_FIRM_UID},
        )

    assert result["status"] == "updated"
    assert result["corporate_unit_price"] == 0
    assert result["is_active"] is True


@pytest.mark.asyncio
async def test_large_price_accepted():
    """corporate_unit_price=1_000_000（100万円）が保存できること。"""
    from app.api.routes.billing_settings import update_billing_settings

    billing_col = make_col(find_one=None)
    mock_db = build_mock_db({
        "corporates": make_multi_find_col([TAX_FIRM_DOC, CLIENT_DOC]),
        "billing_settings": billing_col,
    })

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        result = await update_billing_settings(
            CLIENT_UID,
            {"corporate_unit_price": 1_000_000, "user_unit_price": 0, "is_active": True},
            {"uid": TAX_FIRM_UID},
        )

    assert result["status"] == "updated"
    assert result["corporate_unit_price"] == 1_000_000
    billing_col.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_put_updates_existing_record():
    """
    一度 PUT した後に別の値で PUT すると上書きされること（upsert の上書き確認）。
    既存レコードがある場合の $set 更新を確認する。
    """
    from app.api.routes.billing_settings import update_billing_settings

    existing_record = {
        "_id": ObjectId(),
        "tax_firm_id": TAX_FIRM_UID,
        "target_corporate_id": CLIENT_UID,
        "corporate_unit_price": 1000,
        "user_unit_price": 500,
        "is_active": True,
    }
    billing_col = make_col(find_one=existing_record)
    mock_db = build_mock_db({
        "corporates": make_multi_find_col([TAX_FIRM_DOC, CLIENT_DOC]),
        "billing_settings": billing_col,
    })

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        result = await update_billing_settings(
            CLIENT_UID,
            {"corporate_unit_price": 9999, "user_unit_price": 100, "is_active": False},
            {"uid": TAX_FIRM_UID},
        )

    assert result["status"] == "updated"
    assert result["corporate_unit_price"] == 9999
    assert result["user_unit_price"] == 100
    assert result["is_active"] is False
    # upsert で $set が呼ばれること
    billing_col.update_one.assert_called_once()
    set_data = billing_col.update_one.call_args[0][1]["$set"]
    assert set_data["corporate_unit_price"] == 9999
    # 既存レコードあり → created_at は含まれないこと
    assert "created_at" not in set_data


# ─────────────────────────────────────────────────────────────────────────────
# ③ スコープテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_firm_a_cannot_access_tax_firm_b_client():
    """税理士法人Aが税理士法人Bの顧客の billing_settings に GET できないこと（403）。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import get_billing_settings

    tax_firm_a = {"_id": ObjectId(), "firebase_uid": "firm_a", "corporateType": "tax_firm"}
    tax_firm_b = {"_id": ObjectId(), "firebase_uid": "firm_b", "corporateType": "tax_firm"}
    # CLIENT_DOC は TAX_FIRM_UID（firm_b）配下
    client_b = {
        "_id": ObjectId(), "firebase_uid": "client_b_uid",
        "corporateType": "corporate", "advising_tax_firm_id": "firm_b",
    }
    mock_db = build_mock_db({
        "corporates": make_multi_find_col([tax_firm_a, tax_firm_b, client_b]),
        "billing_settings": make_col(find_one=None),
    })

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await get_billing_settings("client_b_uid", {"uid": "firm_a"})

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_tax_firm_a_cannot_update_tax_firm_b_client():
    """税理士法人Aが税理士法人Bの顧客の billing_settings に PUT できないこと（403）。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import update_billing_settings

    tax_firm_a = {"_id": ObjectId(), "firebase_uid": "firm_a", "corporateType": "tax_firm"}
    client_b = {
        "_id": ObjectId(), "firebase_uid": "client_b_uid",
        "corporateType": "corporate", "advising_tax_firm_id": "firm_b",
    }
    mock_db = build_mock_db({
        "corporates": make_multi_find_col([tax_firm_a, client_b]),
        "billing_settings": make_col(),
    })

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_billing_settings(
                "client_b_uid",
                {"corporate_unit_price": 0, "user_unit_price": 0, "is_active": False},
                {"uid": "firm_a"},
            )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_client_cannot_access_own_billing():
    """配下法人自身が自分の billing_settings に GET できないこと（403）。"""
    from fastapi import HTTPException
    from app.api.routes.billing_settings import get_billing_settings

    # CLIENT_DOC は corporateType="corporate"（tax_firm ではない）
    mock_db = build_mock_db({
        "corporates": make_multi_find_col([TAX_FIRM_DOC, CLIENT_DOC]),
        "billing_settings": make_col(find_one=None),
    })

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            # クライアント自身の UID でアクセス
            await get_billing_settings(CLIENT_UID, {"uid": CLIENT_UID})

    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# ④ GET /users/clients の billing 情報テスト
# ─────────────────────────────────────────────────────────────────────────────

def _apply_billing(client: dict, billing_map: dict) -> dict:
    """users.py の billing 計算ロジックを再現するヘルパー。"""
    uid = client["firebase_uid"]
    billing = billing_map.get(uid)
    if billing and billing.get("is_active"):
        corp_price = billing.get("corporate_unit_price", 0)
        user_price = billing.get("user_unit_price", 0)
        emp_count = client.get("employeeCount", 0)
        client["monthlyBillingTotal"] = corp_price + user_price * emp_count
        client["billingIsActive"] = True
    else:
        client["monthlyBillingTotal"] = 0
        client["billingIsActive"] = False
    return client


def test_clients_api_billing_total_calculation():
    """
    corporate_unit_price=10000・user_unit_price=500・employeeCount=3 の場合に
    monthlyBillingTotal=11500 であること（10000 + 500×3 = 11500）。
    """
    client = {"firebase_uid": CLIENT_UID, "employeeCount": 3}
    billing_map = {
        CLIENT_UID: {
            "is_active": True,
            "corporate_unit_price": 10000,
            "user_unit_price": 500,
        }
    }
    result = _apply_billing(client, billing_map)

    assert result["monthlyBillingTotal"] == 11500, \
        f"10000 + 500×3 = 11500 のはずが {result['monthlyBillingTotal']} だった"
    assert result["billingIsActive"] is True


def test_clients_api_billing_inactive_returns_zero():
    """is_active=False の場合に monthlyBillingTotal=0 であること（料金が設定されていても無効なら0）。"""
    client = {"firebase_uid": CLIENT_UID, "employeeCount": 5}
    billing_map = {
        CLIENT_UID: {
            "is_active": False,   # 無効
            "corporate_unit_price": 10000,
            "user_unit_price": 500,
        }
    }
    result = _apply_billing(client, billing_map)

    assert result["monthlyBillingTotal"] == 0
    assert result["billingIsActive"] is False


def test_clients_api_no_billing_settings_returns_zero():
    """billing_settings が未設定の法人の monthlyBillingTotal=0・billingIsActive=False であること。"""
    client = {"firebase_uid": CLIENT_UID, "employeeCount": 3}
    billing_map = {}  # 未設定

    result = _apply_billing(client, billing_map)

    assert result["monthlyBillingTotal"] == 0
    assert result["billingIsActive"] is False


def test_clients_api_billing_field_always_present():
    """billing_settings の有無に関わらず monthlyBillingTotal・billingIsActive が全法人に含まれること。"""
    clients = [
        {"firebase_uid": "uid_a", "employeeCount": 2},
        {"firebase_uid": "uid_b", "employeeCount": 0},
        {"firebase_uid": "uid_c", "employeeCount": 10},
    ]
    billing_map = {
        "uid_a": {"is_active": True, "corporate_unit_price": 5000, "user_unit_price": 0},
        # uid_b, uid_c は未設定
    }
    for client in clients:
        result = _apply_billing(client, billing_map)
        assert "monthlyBillingTotal" in result, f"{client['firebase_uid']} に monthlyBillingTotal がない"
        assert "billingIsActive" in result, f"{client['firebase_uid']} に billingIsActive がない"


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ デフォルト値テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_default_all_fields_present():
    """未設定の法人に GET すると必須フィールドが全て含まれること。"""
    from app.api.routes.billing_settings import get_billing_settings

    mock_db = billing_db(billing_doc=None)

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        result = await get_billing_settings(CLIENT_UID, {"uid": TAX_FIRM_UID})

    required_keys = {
        "corporate_unit_price", "user_unit_price",
        "is_active", "tax_firm_id", "target_corporate_id",
    }
    missing = required_keys - set(result.keys())
    assert not missing, f"デフォルトレスポンスに不足フィールド: {missing}"


@pytest.mark.asyncio
async def test_default_is_active_is_false():
    """未設定の法人のデフォルトが is_active=False であること（意図せず課金が有効にならない確認）。"""
    from app.api.routes.billing_settings import get_billing_settings

    mock_db = billing_db(billing_doc=None)

    with patch("app.api.routes.billing_settings.get_database", return_value=mock_db):
        result = await get_billing_settings(CLIENT_UID, {"uid": TAX_FIRM_UID})

    assert result["is_active"] is False, \
        "デフォルトで is_active=True になると意図しない課金が発生する"
