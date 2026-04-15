"""
Tests for Task#7: Linkage Request endpoints.

Tests:
  1. linkage_request_success - corporate → 200, invitation created
  2. linkage_request_already_linked - already linked → 400
  3. linkage_request_invalid_email - unknown email → 404
  4. linkage_request_by_tax_firm - tax_firm tries → 403
  5. linkage_approve_success - valid token → DB updated
  6. linkage_approve_invalid_token - nonexistent → 400 HTML
  7. linkage_approve_wrong_type - wrong type → 400 HTML

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_linkage.py -v
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.main import app
from app.db.mongodb import get_database
from app.api.deps import get_current_user

TAX_FIRM_UID = "test_tax_firm_uid"
TAX_FIRM_EMAIL = "taxfirm@example.com"
CORPORATE_UID = "linkage_test_corporate_uid"


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def clean_invitations():
    db = get_database()
    await db["invitations"].delete_many({})
    yield
    await db["invitations"].delete_many({})


@pytest_asyncio.fixture
async def tax_firm_corp():
    """税理士法人のMongoDBレコードを作成する"""
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": TAX_FIRM_UID,
        "corporateType": "tax_firm",
        "is_active": True,
        "created_at": datetime.utcnow(),
    })


@pytest_asyncio.fixture
async def corporate_unlinked():
    """advising_tax_firm_id が未設定の法人 + 認証を法人UIDに切り替える"""
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": CORPORATE_UID,
        "corporateType": "corporate",
        "is_active": True,
        "created_at": datetime.utcnow(),
        # advising_tax_firm_id なし（未紐付け）
    })
    app.dependency_overrides[get_current_user] = lambda: {"uid": CORPORATE_UID}
    yield
    # リセット：conftest デフォルト (TAX_FIRM_UID) に戻す
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}


@pytest_asyncio.fixture
async def corporate_linked():
    """既に advising_tax_firm_id が設定されている法人"""
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": CORPORATE_UID,
        "corporateType": "corporate",
        "advising_tax_firm_id": TAX_FIRM_UID,
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    app.dependency_overrides[get_current_user] = lambda: {"uid": CORPORATE_UID}
    yield
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}


def _mock_firebase_user(uid: str):
    """firebase_auth.get_user_by_email の戻り値となるモックユーザー"""
    mock_user = MagicMock()
    mock_user.uid = uid
    return mock_user


# ─── Tests ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_linkage_request_success(client, tax_firm_corp, corporate_unlinked, mocker):
    """未紐付けの法人が有効な税理士法人メールで紐付けリクエストを送信できる"""
    mocker.patch(
        'app.api.routes.invitations.firebase_auth.get_user_by_email',
        return_value=_mock_firebase_user(TAX_FIRM_UID)
    )

    response = await client.post(
        "/api/v1/invitations/linkage-request",
        json={"tax_firm_email": TAX_FIRM_EMAIL}
    )

    assert response.status_code == 200
    assert "承認リクエストを送信しました" in response.json()["message"]

    # invitations コレクションに type='linkage_request' のレコードが作成される
    db = get_database()
    invitation = await db["invitations"].find_one({
        "corporate_id": CORPORATE_UID,
        "type": "linkage_request"
    })
    assert invitation is not None
    assert invitation["tax_firm_id"] == TAX_FIRM_UID
    assert invitation["status"] == "pending"


@pytest.mark.asyncio
async def test_linkage_request_already_linked(client, tax_firm_corp, corporate_linked, mocker):
    """既に紐付け済みの法人は 400 エラーが返る"""
    mocker.patch(
        'app.api.routes.invitations.firebase_auth.get_user_by_email',
        return_value=_mock_firebase_user(TAX_FIRM_UID)
    )

    response = await client.post(
        "/api/v1/invitations/linkage-request",
        json={"tax_firm_email": TAX_FIRM_EMAIL}
    )

    assert response.status_code == 400
    assert "既に税理士法人と紐付けられています" in response.json()["detail"]


@pytest.mark.asyncio
async def test_linkage_request_invalid_email(client, corporate_unlinked, mocker):
    """存在しないメールアドレスは 404 エラーが返る"""
    # UserNotFoundError をパッチして発生させる
    mocker.patch('app.api.routes.invitations.firebase_auth.UserNotFoundError', ValueError)
    mocker.patch(
        'app.api.routes.invitations.firebase_auth.get_user_by_email',
        side_effect=ValueError("User not found")
    )

    response = await client.post(
        "/api/v1/invitations/linkage-request",
        json={"tax_firm_email": "notfound@example.com"}
    )

    assert response.status_code == 404
    assert "税理士法人が見つかりません" in response.json()["detail"]


@pytest.mark.asyncio
async def test_linkage_request_by_tax_firm(client, mocker):
    """税理士法人が叩くと 403 エラーが返る（法人専用エンドポイント）"""
    # デフォルト認証は TAX_FIRM_UID なので、対応する tax_firm レコードを作成
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": TAX_FIRM_UID,
        "corporateType": "tax_firm",
    })

    mocker.patch(
        'app.api.routes.invitations.firebase_auth.get_user_by_email',
        return_value=_mock_firebase_user(TAX_FIRM_UID)
    )

    response = await client.post(
        "/api/v1/invitations/linkage-request",
        json={"tax_firm_email": TAX_FIRM_EMAIL}
    )

    assert response.status_code == 403
    assert "一般法人のみ" in response.json()["detail"]


@pytest.mark.asyncio
async def test_linkage_approve_success(client):
    """有効な linkage_request トークンで承認すると DB が更新される"""
    db = get_database()

    # 法人と税理士法人のレコードを作成
    await db["corporates"].insert_one({
        "firebase_uid": CORPORATE_UID,
        "corporateType": "corporate",
    })
    await db["corporates"].insert_one({
        "firebase_uid": TAX_FIRM_UID,
        "corporateType": "tax_firm",
    })

    token = "approve-test-token-linkage"
    await db["invitations"].insert_one({
        "token": token,
        "tax_firm_id": TAX_FIRM_UID,
        "corporate_id": CORPORATE_UID,
        "type": "linkage_request",
        "status": "pending",
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "created_at": datetime.utcnow(),
    })

    response = await client.get(f"/api/v1/invitations/linkage-approve?token={token}")

    assert response.status_code == 200

    # corporates の advising_tax_firm_id が更新されている
    corporate = await db["corporates"].find_one({"firebase_uid": CORPORATE_UID})
    assert corporate["advising_tax_firm_id"] == TAX_FIRM_UID

    # invitations の status が accepted になっている
    invitation = await db["invitations"].find_one({"token": token})
    assert invitation["status"] == "accepted"


@pytest.mark.asyncio
async def test_linkage_approve_invalid_token(client):
    """存在しないトークンは 400 HTML レスポンスが返る"""
    response = await client.get("/api/v1/invitations/linkage-approve?token=nonexistent-token")

    assert response.status_code == 400
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_linkage_approve_wrong_type(client):
    """type='invitation' の通常トークンで linkage-approve を叩くと 400 が返る"""
    db = get_database()
    token = "wrong-type-token-linkage"
    await db["invitations"].insert_one({
        "token": token,
        "tax_firm_id": TAX_FIRM_UID,
        "type": "invitation",   # linkage_request ではない
        "status": "pending",
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "created_at": datetime.utcnow(),
    })

    response = await client.get(f"/api/v1/invitations/linkage-approve?token={token}")

    assert response.status_code == 400
    assert "text/html" in response.headers["content-type"]
