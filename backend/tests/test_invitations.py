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


# =============================================================================
# Task#45: GET /invitations（招待リンク一覧）
# =============================================================================

OTHER_TAX_FIRM_UID = "other_tax_firm_uid_task45"


@pytest_asyncio.fixture
async def other_tax_firm_corporate():
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": OTHER_TAX_FIRM_UID,
        "corporateType": "tax_firm",
        "is_active": True,
        "created_at": datetime.utcnow(),
    })


@pytest.mark.asyncio
async def test_tax_firm_can_list_invitations(client, tax_firm_corporate):
    """税理士法人が GET /invitations で自分が発行した招待リンク一覧を取得できること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    await db["invitations"].insert_many([
        {
            "token": "list-token-1",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": "a@example.com",
            "status": "pending",
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow(),
        },
        {
            "token": "list-token-2",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": None,
            "status": "accepted",
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow() - timedelta(days=1),
        },
    ])

    response = await client.get("/api/v1/invitations", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    tokens = [d["token"] for d in data]
    assert "list-token-1" in tokens
    assert "list-token-2" in tokens


@pytest.mark.asyncio
async def test_list_excludes_linkage_requests(client, tax_firm_corporate):
    """type='linkage_request' の招待が一覧に含まれないこと。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    await db["invitations"].insert_many([
        {
            "token": "normal-invite",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": "b@example.com",
            "status": "pending",
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow(),
        },
        {
            "token": "linkage-token",
            "tax_firm_id": TAX_FIRM_UID,
            "corporate_id": "some_corp_uid",
            "type": "linkage_request",
            "status": "pending",
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow(),
        },
    ])

    response = await client.get("/api/v1/invitations", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    data = response.json()
    tokens = [d["token"] for d in data]
    assert "normal-invite" in tokens
    assert "linkage-token" not in tokens, "linkage_request は一覧に含まれないこと"


@pytest.mark.asyncio
async def test_corporate_cannot_list_invitations(client, non_tax_firm_corporate):
    """一般法人ユーザーが GET /invitations で 403 が返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": CORPORATE_UID}

    response = await client.get("/api/v1/invitations", headers={"Authorization": "Bearer test"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_only_shows_own_invitations(client, tax_firm_corporate, other_tax_firm_corporate):
    """別の税理士法人が発行した招待が一覧に含まれないこと。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    await db["invitations"].insert_many([
        {
            "token": "my-token",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": "mine@example.com",
            "status": "pending",
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow(),
        },
        {
            "token": "other-token",
            "tax_firm_id": OTHER_TAX_FIRM_UID,
            "invited_email": "other@example.com",
            "status": "pending",
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow(),
        },
    ])

    response = await client.get("/api/v1/invitations", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    data = response.json()
    tokens = [d["token"] for d in data]
    assert "my-token" in tokens
    assert "other-token" not in tokens, "他の税理士法人の招待は返さないこと"


# =============================================================================
# Task#45 意地悪テスト
# =============================================================================

# ─── ① スコープテスト ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_invitations_cross_tax_firm_blocked(client, tax_firm_corporate, other_tax_firm_corporate):
    """税理士法人Aが発行した招待が税理士法人Bの一覧に含まれないこと。"""
    db = get_database()
    await db["invitations"].insert_many([
        {
            "token": "firm-a-token",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": "a@example.com",
            "status": "pending",
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow(),
        },
        {
            "token": "firm-b-token",
            "tax_firm_id": OTHER_TAX_FIRM_UID,
            "invited_email": "b@example.com",
            "status": "pending",
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow(),
        },
    ])

    # 税理士法人Bとしてアクセス → Aの招待は見えないこと
    app.dependency_overrides[get_current_user] = lambda: {"uid": OTHER_TAX_FIRM_UID}
    response = await client.get("/api/v1/invitations", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    tokens = [d["token"] for d in response.json()]
    assert "firm-b-token" in tokens
    assert "firm-a-token" not in tokens, "他の税理士法人の招待はBには見えないこと"


@pytest.mark.asyncio
async def test_accepted_invitation_appears_in_list(client, tax_firm_corporate):
    """status='accepted' の招待も一覧に含まれること（使用済み記録も表示される）。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    await db["invitations"].insert_one({
        "token": "accepted-token",
        "tax_firm_id": TAX_FIRM_UID,
        "invited_email": "used@example.com",
        "status": "accepted",
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "created_at": datetime.utcnow(),
    })

    response = await client.get("/api/v1/invitations", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    data = response.json()
    tokens = [d["token"] for d in data]
    assert "accepted-token" in tokens, "status=accepted の招待も一覧に含まれること"
    accepted = next(d for d in data if d["token"] == "accepted-token")
    assert accepted["status"] == "accepted"


@pytest.mark.asyncio
async def test_expired_invitation_appears_in_list(client, tax_firm_corporate):
    """expires_at が過去の招待も一覧に含まれること（フロントで期限切れ判定するためDBには残る）。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    await db["invitations"].insert_one({
        "token": "expired-token",
        "tax_firm_id": TAX_FIRM_UID,
        "invited_email": "expired@example.com",
        "status": "pending",
        "expires_at": datetime.utcnow() - timedelta(days=1),
        "created_at": datetime.utcnow() - timedelta(days=8),
    })

    response = await client.get("/api/v1/invitations", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    tokens = [d["token"] for d in response.json()]
    assert "expired-token" in tokens, "期限切れ招待もDBには残りフロントで判定すること"


# ─── ② 招待発行のバリデーションテスト ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_invitation_without_email(client, tax_firm_corporate):
    """invited_email を省略して発行でき、invited_email=None で保存されること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}

    response = await client.post("/api/v1/invitations", json={}, headers={"Authorization": "Bearer test"})

    assert response.status_code == 201
    data = response.json()
    assert "token" in data

    db = get_database()
    saved = await db["invitations"].find_one({"token": data["token"]})
    assert saved is not None
    assert saved["invited_email"] is None


@pytest.mark.asyncio
async def test_create_invitation_with_invalid_email(client, tax_firm_corporate):
    """
    不正なメールアドレス形式での発行動作を確認する。

    【バリデーション状況】
    InvitationCreate.invited_email は Optional[str] のみで
    EmailStr バリデーションが未実装のため、
    不正な文字列でも 201 で保存される（バリデーションなし）。
    """
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}

    response = await client.post(
        "/api/v1/invitations",
        json={"invited_email": "not-an-email"},
        headers={"Authorization": "Bearer test"},
    )

    # 現状バリデーションなし → 201 で保存される
    assert response.status_code == 201, (
        "invited_email に EmailStr バリデーションが未実装のため "
        "不正な形式でも 201 が返る（現状仕様）"
    )


@pytest.mark.asyncio
async def test_create_multiple_invitations_same_email(client, tax_firm_corporate):
    """同じメールアドレスで複数の招待を発行できること（重複チェックなし仕様の確認）。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    email = "dup@example.com"

    res1 = await client.post("/api/v1/invitations", json={"invited_email": email}, headers={"Authorization": "Bearer test"})
    res2 = await client.post("/api/v1/invitations", json={"invited_email": email}, headers={"Authorization": "Bearer test"})

    assert res1.status_code == 201
    assert res2.status_code == 201
    assert res1.json()["token"] != res2.json()["token"], "発行ごとに異なるトークンが生成されること"

    db = get_database()
    count = await db["invitations"].count_documents({"invited_email": email})
    assert count == 2, "同じメールで2件発行されること（重複チェックなし仕様）"


# ─── ③ 件数・ソートテスト ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_returns_latest_first(client, tax_firm_corporate):
    """複数の招待が created_at の降順で返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    now = datetime.utcnow()
    await db["invitations"].insert_many([
        {
            "token": "oldest",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": None,
            "status": "pending",
            "expires_at": now + timedelta(days=7),
            "created_at": now - timedelta(days=2),
        },
        {
            "token": "middle",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": None,
            "status": "pending",
            "expires_at": now + timedelta(days=7),
            "created_at": now - timedelta(days=1),
        },
        {
            "token": "newest",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": None,
            "status": "pending",
            "expires_at": now + timedelta(days=7),
            "created_at": now,
        },
    ])

    response = await client.get("/api/v1/invitations", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    tokens = [d["token"] for d in response.json()]
    assert tokens.index("newest") < tokens.index("middle") < tokens.index("oldest"), \
        "created_at の降順（新しい順）で返ること"


@pytest.mark.asyncio
async def test_list_returns_maximum_100(client, tax_firm_corporate):
    """101件の招待を発行した場合に最大100件が返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    now = datetime.utcnow()
    docs = [
        {
            "token": f"bulk-token-{i:03d}",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": None,
            "status": "pending",
            "expires_at": now + timedelta(days=7),
            "created_at": now - timedelta(seconds=i),
        }
        for i in range(101)
    ]
    await db["invitations"].insert_many(docs)

    response = await client.get("/api/v1/invitations", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    assert len(response.json()) == 100, "上限100件が返ること"


# ─── ④ linkage_request 除外テスト ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_linkage_request_excluded_from_list(client, tax_firm_corporate):
    """通常の招待と linkage_request が混在する場合、通常招待のみ返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    now = datetime.utcnow()
    await db["invitations"].insert_many([
        {
            "token": "normal-1",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": "c1@example.com",
            "status": "pending",
            "expires_at": now + timedelta(days=7),
            "created_at": now,
        },
        {
            "token": "normal-2",
            "tax_firm_id": TAX_FIRM_UID,
            "invited_email": "c2@example.com",
            "status": "accepted",
            "expires_at": now + timedelta(days=7),
            "created_at": now - timedelta(hours=1),
        },
        {
            "token": "linkage-1",
            "tax_firm_id": TAX_FIRM_UID,
            "corporate_id": "corp_x",
            "type": "linkage_request",
            "status": "pending",
            "expires_at": now + timedelta(days=7),
            "created_at": now - timedelta(hours=2),
        },
        {
            "token": "linkage-2",
            "tax_firm_id": TAX_FIRM_UID,
            "corporate_id": "corp_y",
            "type": "linkage_request",
            "status": "accepted",
            "expires_at": now + timedelta(days=7),
            "created_at": now - timedelta(hours=3),
        },
    ])

    response = await client.get("/api/v1/invitations", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    data = response.json()
    tokens = [d["token"] for d in data]
    assert "normal-1" in tokens
    assert "normal-2" in tokens
    assert "linkage-1" not in tokens, "linkage_request は除外されること"
    assert "linkage-2" not in tokens, "linkage_request（accepted）も除外されること"
    assert len(data) == 2, "通常招待2件のみ返ること"
