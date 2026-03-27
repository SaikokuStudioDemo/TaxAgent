"""
Tests for MatchingRules CRUD endpoints + tenant isolation.

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_matching_rules.py -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.db.mongodb import get_database


# ─────────────── Fixtures ───────────────

@pytest_asyncio.fixture
async def registered_corp(client: AsyncClient):
    """
    Register a tax firm corporate so get_corporate_context can resolve the UID.
    conftest の clear_db が毎テスト前に corporates を削除するため、
    CRUD テストの前にこの fixture で corporate を作成する。
    """
    resp = await client.post("/api/v1/users/register", json={
        "corporateType": "tax_firm",
        "planId": "plan-standard",
        "monthlyFee": 30000,
    })
    assert resp.status_code == 201
    return resp.json()["data"]


_RULE_PAYLOAD = {
    "name": "テスト消込ルール",
    "target_field": "取引先グループ化（親会社等への名寄せ）",
    "condition_type": "請求書自動合算",
    "condition_value": "A社とB社の請求はC社名義で振り込まれる",
    "action": "複数請求書を束ねて一括消込候補に提示",
    "is_active": True,
}


# ─────────────── CRUD ───────────────

async def test_create_matching_rule(client: AsyncClient, registered_corp):
    """POST /matching-rules でルールを作成できること。"""
    resp = await client.post("/api/v1/matching-rules", json=_RULE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "テスト消込ルール"
    assert data["target_field"] == "取引先グループ化（親会社等への名寄せ）"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


async def test_list_matching_rules(client: AsyncClient, registered_corp):
    """GET /matching-rules で作成したルールが一覧に含まれること。"""
    create_resp = await client.post("/api/v1/matching-rules", json=_RULE_PAYLOAD)
    assert create_resp.status_code == 200
    created_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/matching-rules")
    assert list_resp.status_code == 200
    ids = [r["id"] for r in list_resp.json()]
    assert created_id in ids


async def test_patch_matching_rule_updates_name(client: AsyncClient, registered_corp):
    """PATCH /matching-rules/{id} でルール名が更新されること。"""
    create_resp = await client.post("/api/v1/matching-rules", json=_RULE_PAYLOAD)
    rule_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/api/v1/matching-rules/{rule_id}", json={"name": "変更後ルール"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "変更後ルール"
    # 他フィールドは変わっていないこと
    assert patch_resp.json()["target_field"] == _RULE_PAYLOAD["target_field"]


async def test_patch_matching_rule_deactivate(client: AsyncClient, registered_corp):
    """PATCH で is_active を False に変更できること。"""
    create_resp = await client.post("/api/v1/matching-rules", json=_RULE_PAYLOAD)
    rule_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/api/v1/matching-rules/{rule_id}", json={"is_active": False})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False


async def test_delete_matching_rule(client: AsyncClient, registered_corp):
    """DELETE /matching-rules/{id} でルールが削除されること。"""
    create_resp = await client.post("/api/v1/matching-rules", json=_RULE_PAYLOAD)
    rule_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/matching-rules/{rule_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    list_resp = await client.get("/api/v1/matching-rules")
    ids = [r["id"] for r in list_resp.json()]
    assert rule_id not in ids


async def test_patch_nonexistent_rule_returns_404(client: AsyncClient, registered_corp):
    """存在しない ID に PATCH すると 404 が返ること。"""
    from bson import ObjectId
    fake_id = str(ObjectId())
    resp = await client.patch(f"/api/v1/matching-rules/{fake_id}", json={"name": "幻のルール"})
    assert resp.status_code == 404


async def test_delete_nonexistent_rule_returns_404(client: AsyncClient, registered_corp):
    """存在しない ID に DELETE すると 404 が返ること。"""
    from bson import ObjectId
    fake_id = str(ObjectId())
    resp = await client.delete(f"/api/v1/matching-rules/{fake_id}")
    assert resp.status_code == 404


# ─────────────── テナント分離 ───────────────

async def test_tenant_isolation(client: AsyncClient, registered_corp):
    """他テナントが作成したルールは一覧に含まれないこと。"""
    db = get_database()

    # 別テナントのルールを DB に直接挿入
    from datetime import datetime
    other_corp_id = "other_corp_000000000000"
    await db["matching_rules"].insert_one({
        "name": "他社ルール",
        "target_field": "特殊な振込先名義の紐付け",
        "condition_type": "除外キーワード指定",
        "condition_value": "他社専用",
        "action": "自動消込を実行",
        "is_active": True,
        "corporate_id": other_corp_id,
        "created_at": datetime.utcnow(),
    })

    list_resp = await client.get("/api/v1/matching-rules")
    assert list_resp.status_code == 200
    names = [r["name"] for r in list_resp.json()]
    assert "他社ルール" not in names
