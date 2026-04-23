"""
Tests for Task#40・#41: プラン管理・手数料率設定 Admin API

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_system_settings_admin.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.deps import get_current_user, verify_admin
from app.core.config import settings

ADMIN_UID = "admin_uid_for_settings_test"
NON_ADMIN_UID = "non_admin_uid_for_settings_test"

VALID_PLANS = [
    {
        "id": "plan_basic",
        "name": "ベーシックプラン",
        "price": 30000,
        "max_client_corporates": 3,
        "max_users_per_corporate": 5,
        "features": ["基本機能"],
        "is_active": True,
    }
]


@pytest.fixture(autouse=True)
def reset_overrides(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_UIDS", [ADMIN_UID])
    yield
    app.dependency_overrides[get_current_user] = lambda: {"uid": "test_tax_firm_uid"}
    app.dependency_overrides.pop(verify_admin, None)


def _set_admin():
    app.dependency_overrides[get_current_user] = lambda: {"uid": ADMIN_UID, "email": "admin@example.com"}
    app.dependency_overrides.pop(verify_admin, None)


def _set_non_admin():
    app.dependency_overrides[get_current_user] = lambda: {"uid": NON_ADMIN_UID}
    app.dependency_overrides.pop(verify_admin, None)


def _make_db(find_one_return=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one_return)
    col.update_one = AsyncMock(return_value=MagicMock())
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)
    return db, col


# =============================================================================
# GET /plans
# =============================================================================

@pytest.mark.asyncio
async def test_get_plans_returns_default_when_empty():
    """DB 未設定時にデフォルトプランが返ること。"""
    db, _ = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/system-settings/plans")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 3
    ids = [p["id"] for p in data]
    assert "plan_basic" in ids and "plan_standard" in ids and "plan_premium" in ids


@pytest.mark.asyncio
async def test_get_plans_returns_db_value_when_exists():
    """DB にプランが存在する場合はそれを返すこと。"""
    db_plans = [{"id": "plan_custom", "name": "カスタムプラン", "price": 9999}]
    db, _ = _make_db(find_one_return={"key": "plans", "value": db_plans})
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/system-settings/plans")
    assert res.status_code == 200
    assert res.json()[0]["id"] == "plan_custom"


# =============================================================================
# PUT /plans
# =============================================================================

@pytest.mark.asyncio
async def test_admin_can_update_plans():
    """Admin が PUT /system-settings/plans でプランを更新できること。"""
    _set_admin()
    db, col = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/plans",
                json={"plans": VALID_PLANS},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    assert res.json()["status"] == "updated"
    col.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_non_admin_cannot_update_plans():
    """一般ユーザーが PUT すると 403 が返ること。"""
    _set_non_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/plans",
            json={"plans": VALID_PLANS},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_plans_cannot_be_empty_array():
    """plans=[] で 400 が返ること。"""
    _set_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/plans",
            json={"plans": []},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_plan_price_must_be_non_negative():
    """price が負の値で 400 が返ること。"""
    _set_admin()
    bad_plan = {**VALID_PLANS[0], "price": -1}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/plans",
            json={"plans": [bad_plan]},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_plan_max_client_corporates_allows_unlimited():
    """max_client_corporates=-1（無制限）は有効であること。"""
    _set_admin()
    plan = {**VALID_PLANS[0], "max_client_corporates": -1}
    db, _ = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/plans",
                json={"plans": [plan]},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_plan_max_users_invalid_zero():
    """max_users_per_corporate=0 は無効で 400 が返ること（-1 か 1以上）。"""
    _set_admin()
    bad_plan = {**VALID_PLANS[0], "max_users_per_corporate": 0}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/plans",
            json={"plans": [bad_plan]},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


# =============================================================================
# GET /fee-rate
# =============================================================================

@pytest.mark.asyncio
async def test_get_fee_rate_returns_default():
    """DB 未設定時にデフォルト手数料率（0.20）が返ること。"""
    db, _ = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/system-settings/fee-rate")
    assert res.status_code == 200
    assert res.json()["platform_fee_rate"] == 0.20


@pytest.mark.asyncio
async def test_get_fee_rate_returns_db_value():
    """DB に値がある場合はそれを返すこと。"""
    db, _ = _make_db(find_one_return={"key": "platform_fee_rate", "value": 0.15})
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/system-settings/fee-rate")
    assert res.status_code == 200
    assert res.json()["platform_fee_rate"] == 0.15


# =============================================================================
# PUT /fee-rate
# =============================================================================

@pytest.mark.asyncio
async def test_admin_can_update_fee_rate():
    """Admin が PUT /system-settings/fee-rate で手数料率を更新できること。"""
    _set_admin()
    db, col = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/fee-rate",
                json={"platform_fee_rate": 0.25},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    assert res.json()["platform_fee_rate"] == 0.25
    col.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_non_admin_cannot_update_fee_rate():
    """一般ユーザーが PUT すると 403 が返ること。"""
    _set_non_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/fee-rate",
            json={"platform_fee_rate": 0.25},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_fee_rate_out_of_range_rejected():
    """platform_fee_rate=1.5（150%）で 400 が返ること。"""
    _set_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/fee-rate",
            json={"platform_fee_rate": 1.5},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_fee_rate_zero_accepted():
    """platform_fee_rate=0.0 は有効であること。"""
    _set_admin()
    db, _ = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/fee-rate",
                json={"platform_fee_rate": 0.0},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    assert res.json()["platform_fee_rate"] == 0.0


@pytest.mark.asyncio
async def test_fee_rate_one_accepted():
    """platform_fee_rate=1.0（100%）は有効であること。"""
    _set_admin()
    db, _ = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/fee-rate",
                json={"platform_fee_rate": 1.0},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_fee_rate_negative_rejected():
    """platform_fee_rate=-0.1 で 400 が返ること。"""
    _set_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/fee-rate",
            json={"platform_fee_rate": -0.1},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


# =============================================================================
# ① プラン管理のバリデーション（意地悪テスト）
# =============================================================================

@pytest.mark.asyncio
async def test_plan_price_negative_rejected():
    """price=-1 で 400 が返ること。"""
    _set_admin()
    bad = {**VALID_PLANS[0], "price": -1}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/plans",
            json={"plans": [bad]},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_plan_price_zero_accepted():
    """price=0 は有効であること。"""
    _set_admin()
    plan = {**VALID_PLANS[0], "price": 0}
    db, _ = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/plans",
                json={"plans": [plan]},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_plan_max_client_corporates_zero_rejected():
    """max_client_corporates=0 は無効で 400 が返ること（-1=無制限 or 1以上のみ有効）。"""
    _set_admin()
    bad = {**VALID_PLANS[0], "max_client_corporates": 0}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/plans",
            json={"plans": [bad]},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_plan_max_client_corporates_minus1_accepted():
    """max_client_corporates=-1 は有効（無制限）であること。"""
    _set_admin()
    plan = {**VALID_PLANS[0], "max_client_corporates": -1}
    db, _ = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/plans",
                json={"plans": [plan]},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_plan_max_client_corporates_minus2_rejected():
    """-1 以外の負数は無効で 400 が返ること。"""
    _set_admin()
    bad = {**VALID_PLANS[0], "max_client_corporates": -2}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/plans",
            json={"plans": [bad]},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_plan_empty_array_rejected():
    """plans=[] で 400 が返ること。"""
    _set_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/plans",
            json={"plans": []},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_plan_missing_required_fields_rejected():
    """id・name・price のいずれかが欠けると 400 が返ること。"""
    _set_admin()
    base = {"id": "p1", "name": "テスト", "price": 1000}

    for missing_field in ("id", "name", "price"):
        bad = {k: v for k, v in base.items() if k != missing_field}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/plans",
                json={"plans": [bad]},
                headers={"Authorization": "Bearer test"},
            )
        assert res.status_code == 400, f"{missing_field} が欠けている場合に 400 が返ること"


@pytest.mark.asyncio
async def test_plan_is_active_false_excluded_from_public():
    """is_active=False のプランが GET /plans に含まれないこと（登録画面に表示しない）。"""
    active_plan = {**VALID_PLANS[0], "id": "active", "is_active": True}
    inactive_plan = {**VALID_PLANS[0], "id": "inactive", "is_active": False}
    db, _ = _make_db(find_one_return={"key": "plans", "value": [active_plan, inactive_plan]})
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/system-settings/plans")
    assert res.status_code == 200
    ids = [p["id"] for p in res.json()]
    assert "active" in ids
    assert "inactive" not in ids, "is_active=False のプランは返さないこと"


# =============================================================================
# ② 手数料率のバリデーション（意地悪テスト）
# =============================================================================

@pytest.mark.asyncio
async def test_fee_rate_over_100_percent_rejected():
    """platform_fee_rate=1.01（101%）で 400 が返ること。"""
    _set_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/fee-rate",
            json={"platform_fee_rate": 1.01},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_fee_rate_exactly_0_accepted():
    """platform_fee_rate=0.0 は有効であること。"""
    _set_admin()
    db, _ = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/fee-rate",
                json={"platform_fee_rate": 0.0},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    assert res.json()["platform_fee_rate"] == 0.0


@pytest.mark.asyncio
async def test_fee_rate_exactly_1_accepted():
    """platform_fee_rate=1.0（100%）は有効であること。"""
    _set_admin()
    db, _ = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/fee-rate",
                json={"platform_fee_rate": 1.0},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    assert res.json()["platform_fee_rate"] == 1.0


@pytest.mark.asyncio
async def test_fee_rate_integer_input_converted():
    """platform_fee_rate=20（整数）を渡した場合に 0.20 として保存されること。"""
    _set_admin()
    db, col = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/fee-rate",
                json={"platform_fee_rate": 20},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    assert abs(res.json()["platform_fee_rate"] - 0.20) < 1e-9
    saved_rate = col.update_one.call_args[0][1]["$set"]["value"]
    assert abs(saved_rate - 0.20) < 1e-9


# =============================================================================
# ③ 上書き・永続化テスト
# =============================================================================

@pytest.mark.asyncio
async def test_plans_update_overwrites_previous():
    """PUT を2回呼んだ場合に2回目の内容で上書きされること。"""
    _set_admin()

    plans_v1 = [{**VALID_PLANS[0], "id": "v1_only", "name": "V1プラン"}]
    plans_v2 = [{**VALID_PLANS[0], "id": "v2_only", "name": "V2プラン"}]

    stored: dict = {"value": None}

    async def mock_update_one(query, update, upsert=False):
        stored["value"] = update["$set"]["value"]
        return MagicMock()

    async def mock_find_one(query):
        if stored["value"] is not None:
            return {"key": "plans", "value": [p for p in stored["value"] if p.get("is_active", True) is not False]}
        return None

    col = MagicMock()
    col.update_one = mock_update_one
    col.find_one = mock_find_one
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)

    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.put(
                "/api/v1/system-settings/plans",
                json={"plans": plans_v1},
                headers={"Authorization": "Bearer test"},
            )
            await client.put(
                "/api/v1/system-settings/plans",
                json={"plans": plans_v2},
                headers={"Authorization": "Bearer test"},
            )
            res = await client.get("/api/v1/system-settings/plans")

    ids = [p["id"] for p in res.json()]
    assert "v2_only" in ids, "2回目のデータが存在すること"
    assert "v1_only" not in ids, "1回目のデータが残らないこと"


@pytest.mark.asyncio
async def test_fee_rate_update_persists():
    """PUT で 0.15 に更新後 GET で 0.15 が返ること。"""
    _set_admin()

    stored: dict = {"value": None}

    async def mock_update_one(query, update, upsert=False):
        stored["value"] = update["$set"]["value"]
        return MagicMock()

    async def mock_find_one(query):
        if stored["value"] is not None:
            return {"key": "platform_fee_rate", "value": stored["value"]}
        return None

    col = MagicMock()
    col.update_one = mock_update_one
    col.find_one = mock_find_one
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)

    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.put(
                "/api/v1/system-settings/fee-rate",
                json={"platform_fee_rate": 0.15},
                headers={"Authorization": "Bearer test"},
            )
            res = await client.get("/api/v1/system-settings/fee-rate")

    assert res.status_code == 200
    assert res.json()["platform_fee_rate"] == 0.15


@pytest.mark.asyncio
async def test_default_plans_returned_after_delete():
    """system_settings から plans を削除した場合に GET がデフォルト値を返すこと。"""
    db, _ = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/system-settings/plans")

    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    assert all(p.get("is_active", True) is not False for p in data), "デフォルトプランは全て有効であること"
    ids = {p["id"] for p in data}
    assert ids == {"plan_basic", "plan_standard", "plan_premium"}


# =============================================================================
# ④ 権限テスト（意地悪）
# =============================================================================

@pytest.mark.asyncio
async def test_tax_firm_cannot_update_plans():
    """税理士法人ユーザーが PUT /system-settings/plans で 403 が返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": "tax_firm_uid_xyz"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/plans",
            json={"plans": VALID_PLANS},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_corporate_user_cannot_update_fee_rate():
    """一般法人ユーザーが PUT /system-settings/fee-rate で 403 が返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": "corporate_uid_xyz"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/fee-rate",
            json={"platform_fee_rate": 0.25},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_anyone_can_read_plans():
    """未認証ユーザーでも GET /system-settings/plans が 200 を返すこと。"""
    db, _ = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/system-settings/plans")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_anyone_can_read_fee_rate():
    """未認証ユーザーでも GET /system-settings/fee-rate が 200 を返すこと。"""
    db, _ = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/system-settings/fee-rate")
    assert res.status_code == 200
    assert "platform_fee_rate" in res.json()


# =============================================================================
# Task#42: Law Agent URL
# =============================================================================

@pytest.mark.asyncio
async def test_admin_can_update_law_agent_url():
    """Admin が PUT /system-settings/law-agent-url で URL を更新できること。"""
    _set_admin()
    db, col = _make_db()
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/law-agent-url",
                json={"law_agent_url": "https://law-agent.example.com"},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    assert res.json()["law_agent_url"] == "https://law-agent.example.com"
    col.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_invalid_url_rejected():
    """http:// / https:// で始まらない URL で 400 が返ること。"""
    _set_admin()
    for bad_url in ["ftp://example.com", "example.com", "//no-scheme.com"]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/law-agent-url",
                json={"law_agent_url": bad_url},
                headers={"Authorization": "Bearer test"},
            )
        assert res.status_code == 400, f"{bad_url!r} は 400 が返ること"


@pytest.mark.asyncio
async def test_empty_url_rejected():
    """URL が空文字で 400 が返ること。"""
    _set_admin()
    for empty in ["", "   "]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/law-agent-url",
                json={"law_agent_url": empty},
                headers={"Authorization": "Bearer test"},
            )
        assert res.status_code == 400, f"{empty!r} は 400 が返ること"


@pytest.mark.asyncio
async def test_law_agent_url_fallback_to_env():
    """system_settings に未設定の場合に GET が .env の LAW_AGENT_URL 値を返すこと。"""
    _set_admin()
    monkeypatch_url = "http://env-fallback.local:9999"
    settings.LAW_AGENT_URL = monkeypatch_url
    db, _ = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get(
                "/api/v1/system-settings/law-agent-url",
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    assert res.json()["law_agent_url"] == monkeypatch_url


@pytest.mark.asyncio
async def test_non_admin_cannot_update_law_agent_url():
    """一般ユーザーが PUT /system-settings/law-agent-url で 403 が返ること。"""
    _set_non_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/law-agent-url",
            json={"law_agent_url": "https://law-agent.example.com"},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 403


# =============================================================================
# GET/PUT /journal-map
# =============================================================================

_VALID_JOURNAL_MAP = {
    "消耗品費": {
        "debit": "消耗品費",
        "credit": "未払金",
        "tax_category": "課税仕入 10%",
        "keywords": ["文具", "コピー用紙"],
    }
}


@pytest.mark.asyncio
async def test_journal_map_returns_default_when_empty():
    """DB 未設定時に DEFAULT_JOURNAL_MAP が返ること。"""
    db, _ = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/system-settings/journal-map")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, dict)
    assert "旅費交通費" in data
    assert "keywords" in data["旅費交通費"]


@pytest.mark.asyncio
async def test_admin_can_update_journal_map():
    """Admin が PUT /system-settings/journal-map で更新できること。"""
    _set_admin()
    db, col = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/journal-map",
                json={"journal_map": _VALID_JOURNAL_MAP},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "updated"
    assert "消耗品費" in data["journal_map"]
    col.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_journal_map_missing_required_fields():
    """debit・credit・tax_category・keywords のいずれかが欠けると 400 が返ること。"""
    _set_admin()
    for missing_key in ("debit", "credit", "tax_category", "keywords"):
        entry = {k: v for k, v in _VALID_JOURNAL_MAP["消耗品費"].items() if k != missing_key}
        db, _ = _make_db(find_one_return=None)
        with patch("app.api.routes.system_settings.get_database", return_value=db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/system-settings/journal-map",
                    json={"journal_map": {"消耗品費": entry}},
                    headers={"Authorization": "Bearer test"},
                )
        assert res.status_code == 400, f"{missing_key} が欠けた場合に 400 が返ること"


@pytest.mark.asyncio
async def test_non_admin_cannot_update_journal_map():
    """一般ユーザーが PUT /system-settings/journal-map で 403 が返ること。"""
    _set_non_admin()
    db, _ = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/journal-map",
                json={"journal_map": _VALID_JOURNAL_MAP},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 403


# =============================================================================
# GET/PUT /tax-rates
# =============================================================================

@pytest.mark.asyncio
async def test_tax_rates_default_when_empty():
    """DB 未設定時に standard=10・reduced=8・exempt=0 が返ること。"""
    db, _ = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/system-settings/tax-rates")
    assert res.status_code == 200
    data = res.json()
    assert data["standard"] == 10
    assert data["reduced"] == 8
    assert data["exempt"] == 0


@pytest.mark.asyncio
async def test_admin_can_update_tax_rates():
    """Admin が PUT /system-settings/tax-rates で更新できること。"""
    _set_admin()
    db, col = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/tax-rates",
                json={"standard": 10, "reduced": 8, "exempt": 0},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    data = res.json()
    assert data["standard"] == 10
    assert data["reduced"] == 8
    col.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_non_admin_cannot_update_tax_rates():
    """一般ユーザーが PUT /system-settings/tax-rates で 403 が返ること。"""
    _set_non_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/tax-rates",
            json={"standard": 10, "reduced": 8, "exempt": 0},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_tax_rate_bool_rejected():
    """standard=True で 400 が返ること（bool 先行チェック）。"""
    _set_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/tax-rates",
            json={"standard": True, "reduced": 8, "exempt": 0},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_tax_rate_out_of_range_rejected():
    """standard=101 で 400 が返ること。"""
    _set_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/tax-rates",
            json={"standard": 101, "reduced": 8, "exempt": 0},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_default_tax_rate_used_in_receipt_creation():
    """system_settings の standard が 8 の場合に新規領収書のデフォルト税率が 8 になること。"""
    from unittest.mock import MagicMock, AsyncMock
    from bson import ObjectId
    from app.api.routes.receipts import submit_receipts_batch
    from app.api.helpers import CorporateContext

    # system_settings で standard=8 を返すモック DB
    sys_doc = {"key": "tax_rates", "value": {"standard": 8, "reduced": 5, "exempt": 0}}
    inserted_id = ObjectId()

    receipts_col = MagicMock()
    receipts_col.insert_many = AsyncMock(return_value=MagicMock(inserted_ids=[inserted_id]))
    system_settings_col = MagicMock()
    system_settings_col.find_one = AsyncMock(return_value=sys_doc)
    audit_col = MagicMock()
    audit_col.insert_one = AsyncMock()
    approval_rules_col = MagicMock()
    approval_rules_col.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    ))

    mock_db = MagicMock()
    def _getitem(k):
        return {
            "receipts": receipts_col,
            "system_settings": system_settings_col,
            "audit_logs": audit_col,
            "approval_rules": approval_rules_col,
        }.get(k, MagicMock())
    mock_db.__getitem__ = MagicMock(side_effect=_getitem)

    ctx = MagicMock(spec=CorporateContext)
    ctx.corporate_id = "corp_test"
    ctx.user_id = "user_test"
    ctx.db = mock_db

    payload = {"receipts": [{"amount": 1000, "date": "2025-01-01", "payee": "テスト"}]}

    with patch("app.api.routes.receipts.evaluate_approval_rules", AsyncMock(return_value=(None, []))):
        with patch("app.api.routes.receipts.apply_journal_rules", AsyncMock(side_effect=lambda db, cid, docs: docs)):
            await submit_receipts_batch(payload=payload, ctx=ctx)

    inserted_docs = receipts_col.insert_many.call_args[0][0]
    assert len(inserted_docs) == 1
    assert inserted_docs[0]["tax_rate"] == 8, f"Expected tax_rate=8, got {inserted_docs[0].get('tax_rate')}"


@pytest.mark.asyncio
async def test_tax_rate_negative_rejected():
    """standard=-1 で 400 が返ること。"""
    _set_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/system-settings/tax-rates",
            json={"standard": -1, "reduced": 8, "exempt": 0},
            headers={"Authorization": "Bearer test"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_tax_rate_zero_accepted():
    """exempt=0 は有効であること（非課税 0% は正当な値）。"""
    _set_admin()
    db, col = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/tax-rates",
                json={"standard": 10, "reduced": 8, "exempt": 0},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    assert res.json()["exempt"] == 0


@pytest.mark.asyncio
async def test_tax_rate_100_accepted():
    """standard=100 は有効であること（境界値）。"""
    _set_admin()
    db, col = _make_db(find_one_return=None)
    with patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/tax-rates",
                json={"standard": 100, "reduced": 8, "exempt": 0},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 200
    assert res.json()["standard"] == 100
