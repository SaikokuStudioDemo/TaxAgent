"""
Tests for JournalRules CRUD endpoints + tenant isolation.

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_journal_rules.py -v
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
    "name": "テスト仕訳ルール",
    "keyword": "AMAZON",
    "target_field": "取引先名",
    "account_subject": "消耗品費",
    "tax_division": "課税仕入 10%",
    "is_active": True,
}


# ─────────────── CRUD ───────────────

async def test_create_journal_rule(client: AsyncClient, registered_corp):
    """POST /journal-rules でルールを作成できること。"""
    resp = await client.post("/api/v1/journal-rules", json=_RULE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["keyword"] == "AMAZON"
    assert data["account_subject"] == "消耗品費"
    assert data["tax_division"] == "課税仕入 10%"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


async def test_list_journal_rules(client: AsyncClient, registered_corp):
    """GET /journal-rules で作成したルールが一覧に含まれること。"""
    create_resp = await client.post("/api/v1/journal-rules", json=_RULE_PAYLOAD)
    assert create_resp.status_code == 200
    created_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/journal-rules")
    assert list_resp.status_code == 200
    ids = [r["id"] for r in list_resp.json()]
    assert created_id in ids


async def test_patch_journal_rule_updates_account_subject(client: AsyncClient, registered_corp):
    """PATCH /journal-rules/{id} で勘定科目が更新されること。"""
    create_resp = await client.post("/api/v1/journal-rules", json=_RULE_PAYLOAD)
    rule_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/api/v1/journal-rules/{rule_id}", json={"account_subject": "通信費"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["account_subject"] == "通信費"
    # 他フィールドは変わっていないこと
    assert patch_resp.json()["keyword"] == _RULE_PAYLOAD["keyword"]


async def test_patch_journal_rule_deactivate(client: AsyncClient, registered_corp):
    """PATCH で is_active を False に変更できること。"""
    create_resp = await client.post("/api/v1/journal-rules", json=_RULE_PAYLOAD)
    rule_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/api/v1/journal-rules/{rule_id}", json={"is_active": False})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False


async def test_delete_journal_rule(client: AsyncClient, registered_corp):
    """DELETE /journal-rules/{id} でルールが削除されること。"""
    create_resp = await client.post("/api/v1/journal-rules", json=_RULE_PAYLOAD)
    rule_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/journal-rules/{rule_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    list_resp = await client.get("/api/v1/journal-rules")
    ids = [r["id"] for r in list_resp.json()]
    assert rule_id not in ids


async def test_patch_nonexistent_rule_returns_404(client: AsyncClient, registered_corp):
    """存在しない ID に PATCH すると 404 が返ること。"""
    from bson import ObjectId
    fake_id = str(ObjectId())
    resp = await client.patch(f"/api/v1/journal-rules/{fake_id}", json={"keyword": "幻のキーワード"})
    assert resp.status_code == 404


async def test_delete_nonexistent_rule_returns_404(client: AsyncClient, registered_corp):
    """存在しない ID に DELETE すると 404 が返ること。"""
    from bson import ObjectId
    fake_id = str(ObjectId())
    resp = await client.delete(f"/api/v1/journal-rules/{fake_id}")
    assert resp.status_code == 404


# ─────────────── テナント分離 ───────────────

async def test_tenant_isolation(client: AsyncClient, registered_corp):
    """他テナントが作成したルールは一覧に含まれないこと。"""
    db = get_database()

    # 別テナントのルールを DB に直接挿入
    from datetime import datetime
    other_corp_id = "other_corp_000000000000"
    await db["journal_rules"].insert_one({
        "name": "他社仕訳ルール",
        "keyword": "他社キーワード",
        "target_field": "品目・摘要",
        "account_subject": "交際費",
        "tax_division": "課税仕入 10%",
        "is_active": True,
        "corporate_id": other_corp_id,
        "created_at": datetime.utcnow(),
    })

    list_resp = await client.get("/api/v1/journal-rules")
    assert list_resp.status_code == 200
    keywords = [r["keyword"] for r in list_resp.json()]
    assert "他社キーワード" not in keywords
