"""
Tests for Task #4: Invitation endpoints.

Tests:
  1. create_invitation as tax_firm → 201 + token returned
  2. create_invitation as non-tax_firm → 403
  3. verify valid token → valid:true, tax_firm_id returned
  4. verify expired token → valid:false, reason:expired
  5. verify already-used token → valid:false, reason:already_used
  6. accept valid token → success:true, status becomes accepted

Usage:
    cd backend
    venv/bin/pytest tests/test_invitations.py -v
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from app.main import app
from app.db.mongodb import get_database
from app.api.deps import get_current_user

TAX_FIRM_UID = "test_tax_firm_uid"
CORPORATE_UID = "test_corporate_uid"


@pytest_asyncio.fixture(autouse=True)
async def clean_invitations():
    db = get_database()
    await db["invitations"].delete_many({})
    yield
    await db["invitations"].delete_many({})


@pytest_asyncio.fixture
async def tax_firm_corporate():
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": TAX_FIRM_UID,
        "corporateType": "tax_firm",
        "is_active": True,
        "created_at": datetime.utcnow(),
    })


@pytest_asyncio.fixture
async def non_tax_firm_corporate():
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": CORPORATE_UID,
        "corporateType": "corporate",
        "is_active": True,
        "created_at": datetime.utcnow(),
    })


# ───────────────────────────────────────────────
# Test 1: create invitation as tax_firm → 201 + token
# ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_invitation_as_tax_firm(client, tax_firm_corporate):
    """税理士法人ユーザーが招待トークンを発行できる"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}

    response = await client.post("/api/v1/invitations", json={"invited_email": "client@example.com"})

    assert response.status_code == 201
    data = response.json()
    assert "token" in data
    assert len(data["token"]) == 36  # UUID format
    assert "expires_at" in data


# ───────────────────────────────────────────────
# Test 2: create invitation as non-tax_firm → 403
# ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_invitation_as_non_tax_firm_returns_403(client, non_tax_firm_corporate):
    """一般法人ユーザーは招待トークンを発行できない（403）"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": CORPORATE_UID}

    response = await client.post("/api/v1/invitations", json={})

    assert response.status_code == 403
    assert "税理士法人" in response.json()["detail"]


# ───────────────────────────────────────────────
# Test 3: verify valid token → valid:true
# ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_verify_valid_token(client):
    """有効なトークンを検証すると valid:true と tax_firm_id が返る"""
    db = get_database()
    token = "valid-test-token-1234"
    await db["invitations"].insert_one({
        "token": token,
        "tax_firm_id": TAX_FIRM_UID,
        "invited_email": "invited@example.com",
        "status": "pending",
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "created_at": datetime.utcnow(),
    })

    response = await client.get(f"/api/v1/invitations/verify?token={token}")

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["tax_firm_id"] == TAX_FIRM_UID
    assert data["invited_email"] == "invited@example.com"


# ───────────────────────────────────────────────
# Test 4: verify expired token → valid:false, reason:expired
# ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_verify_expired_token(client):
    """期限切れトークンは valid:false, reason:expired を返す"""
    db = get_database()
    token = "expired-test-token-5678"
    await db["invitations"].insert_one({
        "token": token,
        "tax_firm_id": TAX_FIRM_UID,
        "invited_email": None,
        "status": "pending",
        "expires_at": datetime.utcnow() - timedelta(days=1),  # 昨日期限切れ
        "created_at": datetime.utcnow() - timedelta(days=8),
    })

    response = await client.get(f"/api/v1/invitations/verify?token={token}")

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["reason"] == "expired"


# ───────────────────────────────────────────────
# Test 5: verify already-used token → valid:false, reason:already_used
# ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_verify_already_used_token(client):
    """使用済みトークンは valid:false, reason:already_used を返す"""
    db = get_database()
    token = "used-test-token-9012"
    await db["invitations"].insert_one({
        "token": token,
        "tax_firm_id": TAX_FIRM_UID,
        "invited_email": None,
        "status": "accepted",  # 使用済み
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "created_at": datetime.utcnow(),
    })

    response = await client.get(f"/api/v1/invitations/verify?token={token}")

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["reason"] == "already_used"


# ───────────────────────────────────────────────
# Test 6: accept valid token → success:true
# ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_accept_valid_token(client):
    """有効なトークンをacceptするとステータスがacceptedに変わる"""
    db = get_database()
    token = "accept-test-token-3456"
    await db["invitations"].insert_one({
        "token": token,
        "tax_firm_id": TAX_FIRM_UID,
        "invited_email": None,
        "status": "pending",
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "created_at": datetime.utcnow(),
    })

    response = await client.post("/api/v1/invitations/accept", json={"token": token})

    assert response.status_code == 200
    assert response.json()["success"] is True

    # DBのステータスが実際に変わっていることを確認
    updated = await db["invitations"].find_one({"token": token})
    assert updated["status"] == "accepted"
