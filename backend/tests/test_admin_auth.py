"""
Tests for Task#39: Admin認証・権限制御

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_admin_auth.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.deps import get_current_user
from app.core.config import settings

ADMIN_UID = "admin_test_uid_123"
NON_ADMIN_UID = "regular_user_uid_456"
TAX_FIRM_UID = "tax_firm_uid_789"
CORPORATE_UID = "corporate_uid_012"


@pytest.fixture(autouse=True)
def reset_override():
    """各テスト後に dependency_override をデフォルトに戻す。"""
    yield
    app.dependency_overrides[get_current_user] = lambda: {"uid": "test_tax_firm_uid"}


@pytest.mark.asyncio
async def test_admin_uid_can_access_admin_me(monkeypatch):
    """ADMIN_UIDS に含まれる UID で GET /admin/me が 200 を返すこと。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", [ADMIN_UID])
    app.dependency_overrides[get_current_user] = lambda: {"uid": ADMIN_UID, "email": "admin@example.com"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/me", headers={"Authorization": "Bearer test"})

    assert res.status_code == 200
    data = res.json()
    assert data["uid"] == ADMIN_UID
    assert data["is_admin"] is True
    assert "email" in data


@pytest.mark.asyncio
async def test_non_admin_uid_returns_403(monkeypatch):
    """ADMIN_UIDS に含まれない UID で GET /admin/me が 403 を返すこと。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", [ADMIN_UID])
    app.dependency_overrides[get_current_user] = lambda: {"uid": NON_ADMIN_UID, "email": "user@example.com"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/me", headers={"Authorization": "Bearer test"})

    assert res.status_code == 403
    assert "Admin権限がありません" in res.json()["detail"]


@pytest.mark.asyncio
async def test_unauthenticated_returns_401_or_403(monkeypatch):
    """認証なしで GET /admin/me が 401 または 403 を返すこと。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", [ADMIN_UID])
    # dependency_override を解除してリアルな認証フローへ
    app.dependency_overrides.pop(get_current_user, None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/me")

    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_stats_requires_admin(monkeypatch):
    """一般ユーザーが GET /admin/stats で 403 が返ること。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", [ADMIN_UID])
    app.dependency_overrides[get_current_user] = lambda: {"uid": NON_ADMIN_UID, "email": "user@example.com"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/stats", headers={"Authorization": "Bearer test"})

    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_uid_list_from_env(monkeypatch):
    """ADMIN_UIDS がカンマ区切りで正しくパースされること。"""
    from app.core.config import Settings

    s = Settings(ADMIN_UIDS="uid_a, uid_b , uid_c")
    assert s.ADMIN_UIDS == ["uid_a", "uid_b", "uid_c"]

    s_empty = Settings(ADMIN_UIDS="")
    assert s_empty.ADMIN_UIDS == []

    s_single = Settings(ADMIN_UIDS="only_one")
    assert s_single.ADMIN_UIDS == ["only_one"]


# =============================================================================
# ① 権限テスト（意地悪）
# =============================================================================

@pytest.mark.asyncio
async def test_tax_firm_user_cannot_access_admin(monkeypatch):
    """税理士法人ユーザーが GET /admin/me で 403 が返ること。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", [ADMIN_UID])
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID, "email": "firm@example.com"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/me", headers={"Authorization": "Bearer test"})

    assert res.status_code == 403
    assert "Admin権限がありません" in res.json()["detail"]


@pytest.mark.asyncio
async def test_corporate_user_cannot_access_admin(monkeypatch):
    """一般法人ユーザーが GET /admin/me で 403 が返ること。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", [ADMIN_UID])
    app.dependency_overrides[get_current_user] = lambda: {"uid": CORPORATE_UID, "email": "corp@example.com"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/me", headers={"Authorization": "Bearer test"})

    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_access_with_wrong_uid(monkeypatch):
    """ADMIN_UIDS に登録されていない UID で 403 を返すこと。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", ["correct_admin_uid"])
    app.dependency_overrides[get_current_user] = lambda: {"uid": "wrong_uid", "email": "wrong@example.com"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/me", headers={"Authorization": "Bearer test"})

    assert res.status_code == 403


@pytest.mark.asyncio
async def test_multiple_admin_uids_all_work(monkeypatch):
    """複数の ADMIN_UIDS が全て有効になること。"""
    uid_a, uid_b, uid_c = "admin_a", "admin_b", "admin_c"
    monkeypatch.setattr(settings, "ADMIN_UIDS", [uid_a, uid_b, uid_c])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for uid in [uid_a, uid_b, uid_c]:
            app.dependency_overrides[get_current_user] = lambda u=uid: {"uid": u, "email": f"{u}@example.com"}
            res = await client.get("/api/v1/admin/me", headers={"Authorization": "Bearer test"})
            assert res.status_code == 200, f"uid={uid} が 200 を返すこと"
            assert res.json()["uid"] == uid


# =============================================================================
# ② エンドポイント移動の確認
# =============================================================================

@pytest.mark.asyncio
async def test_notifications_endpoint_accessible(monkeypatch):
    """GET /notifications が一般ユーザーで 200 を返すこと（admin.py から移動後の確認）。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": CORPORATE_UID}

    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[])

    mock_col = MagicMock()
    mock_col.find = MagicMock(return_value=mock_cursor)

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)

    with patch("app.api.helpers.resolve_corporate_id", new=AsyncMock(return_value=("corp_id_001", CORPORATE_UID))):
        with patch("app.db.mongodb.get_database", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/v1/notifications", headers={"Authorization": "Bearer test"})

    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_run_alerts_accessible_for_tax_firm(monkeypatch):
    """税理士法人ユーザーで POST /alerts-config/run-alerts が動作すること（alerts_config.py 移動後の確認）。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}

    tax_firm_doc = {"firebase_uid": TAX_FIRM_UID, "corporateType": "tax_firm"}
    mock_col = MagicMock()
    mock_col.find_one = AsyncMock(return_value=tax_firm_doc)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with patch("app.services.alert_service.run_all_alerts", new=AsyncMock(return_value={"alerts": 0})):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post("/api/v1/alerts-config/run-alerts", headers={"Authorization": "Bearer test"})

    assert res.status_code == 200
    assert res.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_admin_cannot_call_notifications_as_admin_only(monkeypatch):
    """/notifications は Admin専用ではないので一般ユーザーでもアクセスできること。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", [ADMIN_UID])
    app.dependency_overrides[get_current_user] = lambda: {"uid": CORPORATE_UID}

    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_col = MagicMock()
    mock_col.find = MagicMock(return_value=mock_cursor)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)

    with patch("app.api.helpers.resolve_corporate_id", new=AsyncMock(return_value=("corp_id_002", CORPORATE_UID))):
        with patch("app.db.mongodb.get_database", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/v1/notifications", headers={"Authorization": "Bearer test"})

    assert res.status_code == 200


# =============================================================================
# ③ ADMIN_UIDS の境界値テスト
# =============================================================================

@pytest.mark.asyncio
async def test_empty_admin_uids_blocks_everyone(monkeypatch):
    """ADMIN_UIDS が空の場合に全ユーザーが 403 を返すこと。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", [])

    for uid in [ADMIN_UID, TAX_FIRM_UID, CORPORATE_UID, NON_ADMIN_UID]:
        app.dependency_overrides[get_current_user] = lambda u=uid: {"uid": u}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/me", headers={"Authorization": "Bearer test"})
        assert res.status_code == 403, f"uid={uid} は空 ADMIN_UIDS で 403 になること"


@pytest.mark.asyncio
async def test_admin_uids_with_spaces_parsed_correctly(monkeypatch):
    """スペースあり "uid1, uid2, uid3" が正しくパースされて全 UID が有効になること。"""
    from app.core.config import Settings

    s = Settings(ADMIN_UIDS="uid1, uid2, uid3")
    assert s.ADMIN_UIDS == ["uid1", "uid2", "uid3"]

    # 実際のHTTPアクセスでも全UID が通ること
    monkeypatch.setattr(settings, "ADMIN_UIDS", s.ADMIN_UIDS)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for uid in ["uid1", "uid2", "uid3"]:
            app.dependency_overrides[get_current_user] = lambda u=uid: {"uid": u}
            res = await client.get("/api/v1/admin/me", headers={"Authorization": "Bearer test"})
            assert res.status_code == 200, f"スペース含むパース後の uid={uid} が有効なこと"


@pytest.mark.asyncio
async def test_admin_uid_exact_match_required(monkeypatch):
    """前方一致では通らず、完全一致のみ有効なこと。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", ["admin_uid_1"])

    for partial_uid in ["admin_uid_", "admin_uid", "admin", "admin_uid_10"]:
        app.dependency_overrides[get_current_user] = lambda u=partial_uid: {"uid": u}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/me", headers={"Authorization": "Bearer test"})
        assert res.status_code == 403, f"前方一致 uid={partial_uid} は 403 になること"

    # 完全一致は通ること
    app.dependency_overrides[get_current_user] = lambda: {"uid": "admin_uid_1"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/me", headers={"Authorization": "Bearer test"})
    assert res.status_code == 200


# =============================================================================
# ④ stats エンドポイントのテスト
# =============================================================================

@pytest.mark.asyncio
async def test_admin_stats_returns_expected_structure(monkeypatch):
    """GET /admin/stats のレスポンスに tax_firm_count・corporate_count が含まれること。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", [ADMIN_UID])
    app.dependency_overrides[get_current_user] = lambda: {"uid": ADMIN_UID, "email": "admin@example.com"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/stats", headers={"Authorization": "Bearer test"})

    assert res.status_code == 200
    data = res.json()
    assert "tax_firm_count" in data
    assert "corporate_count" in data
    assert isinstance(data["tax_firm_count"], int)
    assert isinstance(data["corporate_count"], int)


@pytest.mark.asyncio
async def test_non_admin_cannot_access_stats(monkeypatch):
    """一般ユーザーで GET /admin/stats が 403 を返すこと。"""
    monkeypatch.setattr(settings, "ADMIN_UIDS", [ADMIN_UID])
    app.dependency_overrides[get_current_user] = lambda: {"uid": CORPORATE_UID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/stats", headers={"Authorization": "Bearer test"})

    assert res.status_code == 403
