"""
Tests for Task#46: 税理士向けレビュー API

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_tax_firm_reviews.py -v
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from bson import ObjectId

from app.main import app
from app.db.mongodb import get_database
from app.api.deps import get_current_user

TAX_FIRM_UID = "review_tax_firm_uid"
CLIENT_UID = "review_client_uid"
OTHER_TAX_FIRM_UID = "other_review_tax_firm_uid"
OTHER_USER_UID = "other_user_review_uid"


@pytest_asyncio.fixture(autouse=True)
async def clean_review_collections():
    db = get_database()
    await db["tax_firm_reviews"].delete_many({})
    await db["receipts"].delete_many({})
    await db["invoices"].delete_many({})
    await db["notifications"].delete_many({})
    yield
    await db["tax_firm_reviews"].delete_many({})
    await db["receipts"].delete_many({})
    await db["invoices"].delete_many({})
    await db["notifications"].delete_many({})


@pytest_asyncio.fixture
async def setup_firms():
    """
    税理士法人と配下法人を作成し、
    配下法人の MongoDB ObjectId（文字列）を返す。
    """
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": TAX_FIRM_UID,
        "corporateType": "tax_firm",
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    result = await db["corporates"].insert_one({
        "firebase_uid": CLIENT_UID,
        "corporateType": "corporate",
        "advising_tax_firm_id": TAX_FIRM_UID,
        "companyName": "テスト法人",
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    return str(result.inserted_id)


# =============================================================================
# GET /summary
# =============================================================================

@pytest.mark.asyncio
async def test_tax_firm_can_get_summary(client, setup_firms):
    """税理士法人が配下法人のサマリーを取得できること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    corporate_oid = setup_firms
    db = get_database()
    await db["receipts"].insert_one({
        "corporate_id": corporate_oid,
        "approval_status": "pending_approval",
        "is_deleted": False,
        "amount": 1000,
        "created_at": datetime.utcnow(),
    })

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/summary",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["corporate_id"] == CLIENT_UID
    assert data["pending_receipts_count"] == 1
    assert "corporate_name" in data
    assert "pending_invoices_count" in data
    assert "unreconciled_count" in data
    assert isinstance(data["recent_alerts"], list)


@pytest.mark.asyncio
async def test_non_tax_firm_cannot_get_summary(client):
    """一般法人ユーザーが GET /summary で 403 が返ること。"""
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": "plain_corp_uid_46",
        "corporateType": "corporate",
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    app.dependency_overrides[get_current_user] = lambda: {"uid": "plain_corp_uid_46"}

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/summary",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cannot_access_other_tax_firms_corporate(client):
    """別の税理士法人の配下法人にアクセスすると 404 が返ること。"""
    db = get_database()
    await db["corporates"].insert_many([
        {
            "firebase_uid": TAX_FIRM_UID,
            "corporateType": "tax_firm",
            "is_active": True,
            "created_at": datetime.utcnow(),
        },
        {
            "firebase_uid": OTHER_TAX_FIRM_UID,
            "corporateType": "tax_firm",
            "is_active": True,
            "created_at": datetime.utcnow(),
        },
        {
            "firebase_uid": CLIENT_UID,
            "corporateType": "corporate",
            "advising_tax_firm_id": TAX_FIRM_UID,  # TAX_FIRMの配下
            "is_active": True,
            "created_at": datetime.utcnow(),
        },
    ])
    # OTHER_TAX_FIRM からアクセス → 自分の配下ではないので 404
    app.dependency_overrides[get_current_user] = lambda: {"uid": OTHER_TAX_FIRM_UID}

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/summary",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 404


# =============================================================================
# POST /comments
# =============================================================================

@pytest.mark.asyncio
async def test_tax_firm_can_post_comment(client, setup_firms):
    """コメントを投稿できること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}

    response = await client.post(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/comments",
        json={"comment": "確認しました。問題ありません。", "fiscal_period": "2026-03"},
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["comment"] == "確認しました。問題ありません。"
    assert data["fiscal_period"] == "2026-03"
    assert data["created_by"] == TAX_FIRM_UID
    assert "id" in data


# =============================================================================
# PUT /comments/{comment_id}
# =============================================================================

@pytest.mark.asyncio
async def test_can_update_own_comment(client, setup_firms):
    """自分のコメントを更新できること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    result = await db["tax_firm_reviews"].insert_one({
        "tax_firm_id": TAX_FIRM_UID,
        "corporate_id": CLIENT_UID,
        "fiscal_period": "2026-03",
        "comment": "元のコメント",
        "created_by": TAX_FIRM_UID,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    comment_id = str(result.inserted_id)

    response = await client.put(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/comments/{comment_id}",
        json={"comment": "更新されたコメント"},
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.json()["comment"] == "更新されたコメント"


@pytest.mark.asyncio
async def test_cannot_update_others_comment(client, setup_firms):
    """他のユーザーのコメントを更新すると 403 が返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    result = await db["tax_firm_reviews"].insert_one({
        "tax_firm_id": TAX_FIRM_UID,
        "corporate_id": CLIENT_UID,
        "fiscal_period": "2026-03",
        "comment": "他のユーザーのコメント",
        "created_by": OTHER_USER_UID,  # 別の firebase_uid が投稿
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    comment_id = str(result.inserted_id)

    response = await client.put(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/comments/{comment_id}",
        json={"comment": "乗っ取りコメント"},
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 403


# =============================================================================
# GET /documents
# =============================================================================

@pytest.mark.asyncio
async def test_documents_filtered_by_fiscal_period(client, setup_firms):
    """fiscal_period フィルターが正しく機能すること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    corporate_oid = setup_firms
    db = get_database()
    await db["receipts"].insert_many([
        {
            "corporate_id": corporate_oid,
            "approval_status": "approved",
            "fiscal_period": "2026-03",
            "date": "2026-03-15",
            "amount": 1000,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        },
        {
            "corporate_id": corporate_oid,
            "approval_status": "approved",
            "fiscal_period": "2026-04",
            "date": "2026-04-01",
            "amount": 2000,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        },
    ])

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/documents?fiscal_period=2026-03",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["fiscal_period"] == "2026-03"


@pytest.mark.asyncio
async def test_documents_only_approved(client, setup_firms):
    """未承認の書類が一覧に含まれないこと。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    corporate_oid = setup_firms
    db = get_database()
    await db["receipts"].insert_many([
        {
            "corporate_id": corporate_oid,
            "approval_status": "approved",
            "fiscal_period": "2026-03",
            "date": "2026-03-10",
            "amount": 1000,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        },
        {
            "corporate_id": corporate_oid,
            "approval_status": "pending_approval",
            "fiscal_period": "2026-03",
            "date": "2026-03-11",
            "amount": 2000,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        },
    ])

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/documents",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "approved"


# =============================================================================
# Task#46 意地悪テスト
# =============================================================================

ANOTHER_CLIENT_UID = "another_client_uid_46"
SECOND_MEMBER_UID = "second_member_uid_46"


# ─── ① 権限・スコープテスト ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_corporate_user_cannot_access_review(client):
    """一般法人ユーザーが GET /summary で 403 が返ること。"""
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": "plain_corp_46",
        "corporateType": "corporate",
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    app.dependency_overrides[get_current_user] = lambda: {"uid": "plain_corp_46"}

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/summary",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_tax_firm_cannot_access_unrelated_corporate(client):
    """税理士法人Aが税理士法人Bの配下法人にアクセスすると 404 が返ること。"""
    db = get_database()
    await db["corporates"].insert_many([
        {"firebase_uid": TAX_FIRM_UID, "corporateType": "tax_firm", "is_active": True, "created_at": datetime.utcnow()},
        {"firebase_uid": OTHER_TAX_FIRM_UID, "corporateType": "tax_firm", "is_active": True, "created_at": datetime.utcnow()},
        {
            "firebase_uid": CLIENT_UID,
            "corporateType": "corporate",
            "advising_tax_firm_id": OTHER_TAX_FIRM_UID,  # BのみがCLIENTの顧問
            "is_active": True,
            "created_at": datetime.utcnow(),
        },
    ])
    # TAX_FIRM_UID（A）でアクセス → advising_tax_firm_id が一致しないので 404
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/summary",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_corporate_without_tax_firm_returns_404(client, setup_firms):
    """advising_tax_firm_id が未設定の法人（独立法人）にアクセスすると 404 が返ること。"""
    db = get_database()
    await db["corporates"].insert_one({
        "firebase_uid": "independent_corp_uid",
        "corporateType": "corporate",
        # advising_tax_firm_id を設定しない
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}

    response = await client.get(
        "/api/v1/tax-firm/reviews/independent_corp_uid/summary",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_others_comment(client, setup_firms):
    """別のユーザーのコメントを DELETE すると 403 が返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    result = await db["tax_firm_reviews"].insert_one({
        "tax_firm_id": TAX_FIRM_UID,
        "corporate_id": CLIENT_UID,
        "fiscal_period": "2026-03",
        "comment": "他のユーザーが投稿したコメント",
        "created_by": OTHER_USER_UID,  # 別ユーザーが投稿
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    comment_id = str(result.inserted_id)

    response = await client.delete(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/comments/{comment_id}",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 403


# ─── ② サマリーの正確性テスト ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summary_pending_count_is_accurate(client, setup_firms):
    """未承認の領収書が3件ある場合に pending_receipts_count=3 が返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    corporate_oid = setup_firms
    db = get_database()
    await db["receipts"].insert_many([
        {
            "corporate_id": corporate_oid,
            "approval_status": "pending_approval",
            "is_deleted": False,
            "amount": i * 1000,
            "created_at": datetime.utcnow(),
        }
        for i in range(1, 4)
    ])

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/summary",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.json()["pending_receipts_count"] == 3


@pytest.mark.asyncio
async def test_summary_excludes_approved_docs(client, setup_firms):
    """承認済みの書類が pending_receipts_count に含まれないこと。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    corporate_oid = setup_firms
    db = get_database()
    await db["receipts"].insert_many([
        {
            "corporate_id": corporate_oid,
            "approval_status": "pending_approval",
            "is_deleted": False,
            "amount": 1000,
            "created_at": datetime.utcnow(),
        },
        {
            "corporate_id": corporate_oid,
            "approval_status": "approved",  # 承認済みはカウントしない
            "is_deleted": False,
            "amount": 2000,
            "created_at": datetime.utcnow(),
        },
    ])

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/summary",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.json()["pending_receipts_count"] == 1


@pytest.mark.asyncio
async def test_summary_unreconciled_count_correct(client, setup_firms):
    """承認済みかつ未消込の領収書が2件ある場合に unreconciled_count=2 が返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    corporate_oid = setup_firms
    db = get_database()
    await db["receipts"].insert_many([
        {
            "corporate_id": corporate_oid,
            "approval_status": "approved",
            "reconciliation_status": "unreconciled",
            "is_deleted": False,
            "amount": 1000,
            "created_at": datetime.utcnow(),
        },
        {
            "corporate_id": corporate_oid,
            "approval_status": "approved",
            "reconciliation_status": "unreconciled",
            "is_deleted": False,
            "amount": 2000,
            "created_at": datetime.utcnow(),
        },
        {
            "corporate_id": corporate_oid,
            "approval_status": "approved",
            "reconciliation_status": "reconciled",  # 消込済みはカウントしない
            "is_deleted": False,
            "amount": 3000,
            "created_at": datetime.utcnow(),
        },
    ])

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/summary",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.json()["unreconciled_count"] == 2


# ─── ③ 書類一覧テスト ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_documents_excludes_pending_approval(client, setup_firms):
    """approval_status='pending_approval' の書類が GET /documents に含まれないこと。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    corporate_oid = setup_firms
    db = get_database()
    await db["receipts"].insert_many([
        {
            "corporate_id": corporate_oid,
            "approval_status": "approved",
            "date": "2026-03-01",
            "amount": 1000,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        },
        {
            "corporate_id": corporate_oid,
            "approval_status": "pending_approval",
            "date": "2026-03-02",
            "amount": 2000,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        },
    ])

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/documents",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    data = response.json()
    statuses = [d["status"] for d in data]
    assert "pending_approval" not in statuses, "未承認の書類は含まれないこと"
    assert all(s == "approved" for s in statuses)


@pytest.mark.asyncio
async def test_documents_fiscal_period_filter(client, setup_firms):
    """fiscal_period='2025-03' 指定で '2025-02' の書類が含まれないこと。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    corporate_oid = setup_firms
    db = get_database()
    await db["receipts"].insert_many([
        {
            "corporate_id": corporate_oid,
            "approval_status": "approved",
            "fiscal_period": "2025-03",
            "date": "2025-03-10",
            "amount": 1000,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        },
        {
            "corporate_id": corporate_oid,
            "approval_status": "approved",
            "fiscal_period": "2025-02",
            "date": "2025-02-15",
            "amount": 2000,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        },
    ])

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/documents?fiscal_period=2025-03",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    data = response.json()
    periods = [d["fiscal_period"] for d in data]
    assert "2025-02" not in periods, "指定期間外の書類は含まれないこと"
    assert all(p == "2025-03" for p in periods)


@pytest.mark.asyncio
async def test_documents_contains_both_receipts_and_invoices(client, setup_firms):
    """領収書と受領請求書が両方含まれ、type フィールドで区別されること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    corporate_oid = setup_firms
    db = get_database()
    await db["receipts"].insert_one({
        "corporate_id": corporate_oid,
        "approval_status": "approved",
        "date": "2026-03-01",
        "amount": 1000,
        "is_deleted": False,
        "created_at": datetime.utcnow(),
    })
    await db["invoices"].insert_one({
        "corporate_id": corporate_oid,
        "approval_status": "approved",
        "issue_date": "2026-03-02",
        "total_amount": 5000,
        "is_deleted": False,
        "created_at": datetime.utcnow(),
    })

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/documents",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    data = response.json()
    types = {d["type"] for d in data}
    assert "receipt" in types, "領収書が含まれること"
    assert "invoice" in types, "請求書が含まれること"


@pytest.mark.asyncio
async def test_documents_cross_corporate_blocked(client, setup_firms):
    """別法人の書類が GET /documents に含まれないこと（firebase_uid → ObjectId 変換の正確性確認）。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    corporate_oid_a = setup_firms  # CLIENT_UID の ObjectId
    db = get_database()

    # 別の配下法人 B を作成して ObjectId を取得
    result_b = await db["corporates"].insert_one({
        "firebase_uid": ANOTHER_CLIENT_UID,
        "corporateType": "corporate",
        "advising_tax_firm_id": TAX_FIRM_UID,
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    corporate_oid_b = str(result_b.inserted_id)

    # 法人Aと法人Bの両方に領収書を挿入
    await db["receipts"].insert_many([
        {
            "corporate_id": corporate_oid_a,
            "approval_status": "approved",
            "date": "2026-03-01",
            "amount": 1000,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        },
        {
            "corporate_id": corporate_oid_b,  # 別法人Bの書類
            "approval_status": "approved",
            "date": "2026-03-02",
            "amount": 9999,
            "is_deleted": False,
            "created_at": datetime.utcnow(),
        },
    ])

    # CLIENT_UID（法人A）のドキュメントを取得 → 法人Bの書類は含まれないこと
    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/documents",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    data = response.json()
    amounts = [d["amount"] for d in data]
    assert 9999 not in amounts, "別法人（B）の書類は法人Aのドキュメント一覧に含まれないこと"
    assert 1000 in amounts, "法人Aの書類は含まれること"


# ─── ④ コメントテスト ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_comment_requires_fiscal_period(client, setup_firms):
    """fiscal_period なしで POST すると 422（バリデーションエラー）が返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}

    response = await client.post(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/comments",
        json={"comment": "fiscal_period なし"},
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 422, "fiscal_period は必須フィールドのため 422 が返ること"


@pytest.mark.asyncio
async def test_comment_requires_content(client, setup_firms):
    """comment が空文字で POST すると 400 が返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}

    response = await client.post(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/comments",
        json={"comment": "", "fiscal_period": "2026-03"},
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_comment_update_changes_content(client, setup_firms):
    """PUT でコメント内容が正しく更新されること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    result = await db["tax_firm_reviews"].insert_one({
        "tax_firm_id": TAX_FIRM_UID,
        "corporate_id": CLIENT_UID,
        "fiscal_period": "2026-03",
        "comment": "変更前のコメント",
        "created_by": TAX_FIRM_UID,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    comment_id = str(result.inserted_id)

    response = await client.put(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/comments/{comment_id}",
        json={"comment": "変更後のコメント"},
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["comment"] == "変更後のコメント"

    # DB でも実際に変わっていること
    updated = await db["tax_firm_reviews"].find_one({"_id": ObjectId(comment_id)})
    assert updated["comment"] == "変更後のコメント"


@pytest.mark.asyncio
async def test_comment_list_newest_first(client, setup_firms):
    """コメント一覧が created_at の降順で返ること。"""
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}
    db = get_database()
    now = datetime.utcnow()
    await db["tax_firm_reviews"].insert_many([
        {
            "tax_firm_id": TAX_FIRM_UID,
            "corporate_id": CLIENT_UID,
            "fiscal_period": "2026-01",
            "comment": "oldest",
            "created_by": TAX_FIRM_UID,
            "created_at": now - timedelta(days=2),
            "updated_at": now,
        },
        {
            "tax_firm_id": TAX_FIRM_UID,
            "corporate_id": CLIENT_UID,
            "fiscal_period": "2026-02",
            "comment": "middle",
            "created_by": TAX_FIRM_UID,
            "created_at": now - timedelta(days=1),
            "updated_at": now,
        },
        {
            "tax_firm_id": TAX_FIRM_UID,
            "corporate_id": CLIENT_UID,
            "fiscal_period": "2026-03",
            "comment": "newest",
            "created_by": TAX_FIRM_UID,
            "created_at": now,
            "updated_at": now,
        },
    ])

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/comments",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    comments_list = response.json()
    contents = [c["comment"] for c in comments_list]
    assert contents.index("newest") < contents.index("middle") < contents.index("oldest"), \
        "created_at の降順（新しい順）で返ること"


@pytest.mark.asyncio
async def test_comment_visible_to_same_tax_firm(client, setup_firms):
    """
    別ユーザー（OTHER_USER_UID）が投稿したコメントが
    同じ税理士法人（TAX_FIRM_UID）のアクセス時に参照できること。
    【設計注記】created_by は投稿者の firebase_uid で管理するが、
    GET /comments は配下法人へのアクセス権を持つ税理士法人全員が参照できる。
    """
    db = get_database()
    # OTHER_USER_UID が投稿したコメントを直接挿入
    await db["tax_firm_reviews"].insert_one({
        "tax_firm_id": TAX_FIRM_UID,
        "corporate_id": CLIENT_UID,
        "fiscal_period": "2026-03",
        "comment": "チームメンバーが投稿したコメント",
        "created_by": OTHER_USER_UID,  # 別ユーザーが投稿
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })

    # TAX_FIRM_UID（同じ税理士法人の別セッション想定）でアクセス
    app.dependency_overrides[get_current_user] = lambda: {"uid": TAX_FIRM_UID}

    response = await client.get(
        f"/api/v1/tax-firm/reviews/{CLIENT_UID}/comments",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    data = response.json()
    contents = [c["comment"] for c in data]
    assert "チームメンバーが投稿したコメント" in contents, \
        "別ユーザーが投稿したコメントも参照できること"
