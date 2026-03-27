"""
Tests for ApprovalRules: rule_evaluation_service and CRUD endpoints.

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_approval_rules.py -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from bson import ObjectId

from app.db.mongodb import get_database
from app.services.rule_evaluation_service import evaluate_approval_rules


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


# ─────────────── 4-a: "always" バグ修正の検証 ───────────────

async def test_always_condition_matches(client: AsyncClient):
    """field: 'always' のルールは任意の書類にマッチすること。"""
    db = get_database()
    corp_id = await _get_or_create_corp_id(db)

    # ルールを DB に直接挿入
    rule_doc = {
        "corporate_id": corp_id,
        "name": "常に対象ルール",
        "applies_to": ["receipt"],
        "conditions": [{"field": "always", "operator": "", "value": ""}],
        "steps": [{"step": 1, "role": "direct_manager", "required": True}],
        "active": True,
    }
    result = await db["approval_rules"].insert_one(rule_doc)
    rule_id = str(result.inserted_id)

    # 任意の金額のドキュメントで評価
    document = {"amount": 500, "total_amount": 500}
    matched_rule_id, steps = await evaluate_approval_rules(corp_id, "receipt", document)

    assert matched_rule_id == rule_id, f"Expected rule_id={rule_id}, got {matched_rule_id}"
    assert len(steps) == 1


async def test_always_condition_matches_with_high_amount(client: AsyncClient):
    """field: 'always' のルールは高額書類にもマッチすること。"""
    db = get_database()
    corp_id = await _get_or_create_corp_id(db)

    rule_doc = {
        "corporate_id": corp_id,
        "name": "常に対象（高額）",
        "applies_to": ["receipt"],
        "conditions": [{"field": "always", "operator": "", "value": ""}],
        "steps": [{"step": 1, "role": "ceo", "required": True}],
        "active": True,
    }
    result = await db["approval_rules"].insert_one(rule_doc)
    rule_id = str(result.inserted_id)

    document = {"amount": 5000000, "total_amount": 5000000}
    matched_rule_id, steps = await evaluate_approval_rules(corp_id, "receipt", document)

    assert matched_rule_id == rule_id
    assert steps[0]["role"] == "ceo"


# ─────────────── 4-b: 金額条件ルールの検証 ───────────────

async def test_amount_condition_matches_above_threshold(client: AsyncClient):
    """amount >= 10000 のルールは amount=15000 の書類にマッチすること。"""
    db = get_database()
    corp_id = await _get_or_create_corp_id(db)

    rule_doc = {
        "corporate_id": corp_id,
        "name": "1万円以上ルール",
        "applies_to": ["receipt"],
        "conditions": [{"field": "amount", "operator": ">=", "value": 10000}],
        "steps": [{"step": 1, "role": "direct_manager", "required": True}],
        "active": True,
    }
    result = await db["approval_rules"].insert_one(rule_doc)
    rule_id = str(result.inserted_id)

    document = {"amount": 15000, "total_amount": 15000}
    matched_rule_id, steps = await evaluate_approval_rules(corp_id, "receipt", document)

    assert matched_rule_id == rule_id


async def test_amount_condition_does_not_match_below_threshold(client: AsyncClient):
    """amount >= 10000 のルールは amount=5000 の書類にマッチしないこと。"""
    db = get_database()
    corp_id = await _get_or_create_corp_id(db)

    rule_doc = {
        "corporate_id": corp_id,
        "name": "1万円以上ルール（不一致確認）",
        "applies_to": ["receipt"],
        "conditions": [{"field": "amount", "operator": ">=", "value": 10000}],
        "steps": [{"step": 1, "role": "direct_manager", "required": True}],
        "active": True,
    }
    await db["approval_rules"].insert_one(rule_doc)

    document = {"amount": 5000, "total_amount": 5000}
    matched_rule_id, steps = await evaluate_approval_rules(corp_id, "receipt", document)

    assert matched_rule_id is None
    assert steps == []


# ─────────────── 4-c: 承認ルール CRUD の検証 ───────────────

async def test_create_approval_rule(client: AsyncClient, registered_corp):
    """POST /approvals/rules でルールを作成できること。"""
    payload = {
        "name": "テストルール",
        "applies_to": ["receipt"],
        "conditions": [{"field": "amount", "operator": ">=", "value": 5000}],
        "steps": [{"step": 1, "role": "direct_manager", "required": True}],
        "active": True,
    }
    resp = await client.post("/api/v1/approvals/rules", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "テストルール"
    assert "id" in data


async def test_list_approval_rules(client: AsyncClient, registered_corp):
    """GET /approvals/rules で作成したルールが一覧に含まれること。"""
    payload = {
        "name": "一覧確認ルール",
        "applies_to": ["receipt"],
        "conditions": [],
        "steps": [{"step": 1, "role": "accounting", "required": True}],
        "active": True,
    }
    create_resp = await client.post("/api/v1/approvals/rules", json=payload)
    assert create_resp.status_code == 200
    created_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/approvals/rules")
    assert list_resp.status_code == 200
    ids = [r["id"] for r in list_resp.json()]
    assert created_id in ids


async def test_patch_approval_rule_updates_name(client: AsyncClient, registered_corp):
    """PATCH /approvals/rules/{id} でルール名が更新されること。"""
    create_resp = await client.post("/api/v1/approvals/rules", json={
        "name": "変更前ルール",
        "applies_to": ["receipt"],
        "conditions": [],
        "steps": [{"step": 1, "role": "direct_manager", "required": True}],
        "active": True,
    })
    rule_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/api/v1/approvals/rules/{rule_id}", json={"name": "変更後ルール"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "変更後ルール"


async def test_patch_ignores_forbidden_fields(client: AsyncClient, registered_corp):
    """PATCH に corporate_id を含めても DB の corporate_id が上書きされないこと。"""
    create_resp = await client.post("/api/v1/approvals/rules", json={
        "name": "禁止フィールドテスト",
        "applies_to": ["receipt"],
        "conditions": [],
        "steps": [{"step": 1, "role": "direct_manager", "required": True}],
        "active": True,
    })
    rule_id = create_resp.json()["id"]

    # corporate_id は ApprovalRuleUpdate に定義されていないため
    # model_dump(exclude_unset=True) に含まれず DB に書き込まれない
    patch_resp = await client.patch(f"/api/v1/approvals/rules/{rule_id}", json={
        "name": "名前だけ更新",
        "corporate_id": "malicious_corp_id",
    })
    assert patch_resp.status_code == 200
    db = get_database()
    doc = await db["approval_rules"].find_one({"_id": ObjectId(rule_id)})
    assert doc["corporate_id"] != "malicious_corp_id"
    assert doc["name"] == "名前だけ更新"


async def test_delete_approval_rule(client: AsyncClient, registered_corp):
    """DELETE /approvals/rules/{id} でルールが削除されること。"""
    create_resp = await client.post("/api/v1/approvals/rules", json={
        "name": "削除対象ルール",
        "applies_to": ["receipt"],
        "conditions": [],
        "steps": [{"step": 1, "role": "direct_manager", "required": True}],
        "active": True,
    })
    rule_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/approvals/rules/{rule_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # 一覧から消えていること
    list_resp = await client.get("/api/v1/approvals/rules")
    ids = [r["id"] for r in list_resp.json()]
    assert rule_id not in ids


# ─────────────── Helper ───────────────

async def _get_or_create_corp_id(db) -> str:
    """conftest の setup_db が作る corporate を取得して ID を返す。"""
    corp = await db["corporates"].find_one({"firebase_uid": "test_tax_firm_uid"})
    if corp:
        return str(corp["_id"])
    result = await db["corporates"].insert_one({"firebase_uid": "test_tax_firm_uid"})
    return str(result.inserted_id)
