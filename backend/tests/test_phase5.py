"""
Tests for Phase 5: Rule Evaluation, Approval Flow, and Alert Service.

Runs against a dedicated `tax_agent_test` MongoDB database (see conftest.py).
Usage:
    cd backend
    venv/bin/pytest tests/test_phase5.py -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from bson import ObjectId
from datetime import datetime, timedelta

from app.main import app
from app.db.mongodb import get_database
from app.api.deps import get_current_user

# ─────────────── Test Fixtures ───────────────

MOCK_UID = "test_corporate_uid"
app.dependency_overrides[get_current_user] = lambda: {"uid": MOCK_UID}


@pytest_asyncio.fixture(autouse=True)
async def clean_collections():
    """Clear test collections before each test."""
    db = get_database()
    for col in ["corporates", "employees", "receipts", "invoices",
                "approval_rules", "audit_logs", "notifications",
                "bank_transactions", "matches"]:
        await db[col].delete_many({})
    yield
    for col in ["corporates", "employees", "receipts", "invoices",
                "approval_rules", "audit_logs", "notifications",
                "bank_transactions", "matches"]:
        await db[col].delete_many({})


@pytest_asyncio.fixture
async def corporate_id() -> str:
    """Insert a mock corporate and return its _id as a string."""
    db = get_database()
    result = await db["corporates"].insert_one({
        "firebase_uid": MOCK_UID,
        "corporateType": "corporate",
        "planId": "plan_basic",
        "monthlyFee": 10000,
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    return str(result.inserted_id)


@pytest_asyncio.fixture
async def approval_rule(corporate_id) -> str:
    """Insert a test approval rule (amount >= 30000) and return its _id."""
    db = get_database()
    result = await db["approval_rules"].insert_one({
        "corporate_id": corporate_id,
        "name": "3万円以上ルール",
        "applies_to": ["receipt"],
        "conditions": [{"field": "amount", "operator": ">=", "value": 30000}],
        "steps": [
            {"step": 1, "role": "group_leader", "required": True},
            {"step": 2, "role": "dept_manager", "required": True},
        ],
        "active": True,
        "created_at": datetime.utcnow(),
    })
    return str(result.inserted_id)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ─────────────── Rule Evaluation Tests ───────────────

@pytest.mark.asyncio
async def test_rule_evaluation_match(corporate_id, approval_rule, client):
    """
    A receipt with amount >= 30000 should have the approval rule auto-applied.
    """
    resp = await client.post("/api/v1/receipts", json={
        "date": "2025-04-01",
        "amount": 50000,
        "tax_rate": 10,
        "payee": "テスト株式会社",
        "category": "消耗品費",
        "payment_method": "立替",
        "fiscal_period": "2025-04",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["approval_rule_id"] == approval_rule
    assert data["approval_status"] == "pending_approval"
    assert data["current_step"] == 1


@pytest.mark.asyncio
async def test_rule_evaluation_no_match(corporate_id, approval_rule, client):
    """
    A receipt below the 30000 threshold should NOT get a rule applied.
    """
    resp = await client.post("/api/v1/receipts", json={
        "date": "2025-04-01",
        "amount": 5000,
        "tax_rate": 10,
        "payee": "コンビニ",
        "category": "雑費",
        "payment_method": "立替",
        "fiscal_period": "2025-04",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["approval_rule_id"] is None


# ─────────────── Approval Flow Tests ───────────────

@pytest.mark.asyncio
async def test_approval_step_progression(corporate_id, approval_rule, client):
    """
    Approving step 1 should advance current_step to 2 (not yet fully approved).
    """
    # Create receipt
    create_resp = await client.post("/api/v1/receipts", json={
        "date": "2025-04-01",
        "amount": 50000,
        "tax_rate": 10,
        "payee": "テスト株式会社",
        "category": "消耗品費",
        "payment_method": "立替",
        "fiscal_period": "2025-04",
    })
    receipt_id = create_resp.json()["id"]

    # Approve step 1
    action_resp = await client.post("/api/v1/approvals/actions", json={
        "document_type": "receipt",
        "document_id": receipt_id,
        "step": 1,
        "approver_id": "approver_001",
        "action": "approved",
        "comment": None,
    })
    assert action_resp.status_code == 200, action_resp.text

    # Check: still unreviewed (step 2 pending)
    db = get_database()
    updated = await db["receipts"].find_one({"_id": ObjectId(receipt_id)})
    assert updated["current_step"] == 2
    assert updated["approval_status"] == "pending_approval"


@pytest.mark.asyncio
async def test_approval_final_step(corporate_id, approval_rule, client):
    """
    Approving the final step (step 2) should set approval_status to 'approved'.
    """
    create_resp = await client.post("/api/v1/receipts", json={
        "date": "2025-04-01",
        "amount": 50000,
        "tax_rate": 10,
        "payee": "テスト株式会社",
        "category": "消耗品費",
        "payment_method": "立替",
        "fiscal_period": "2025-04",
    })
    receipt_id = create_resp.json()["id"]

    # Approve step 1
    await client.post("/api/v1/approvals/actions", json={
        "document_type": "receipt",
        "document_id": receipt_id,
        "step": 1,
        "approver_id": "approver_001",
        "action": "approved",
    })

    # Approve step 2 (final)
    await client.post("/api/v1/approvals/actions", json={
        "document_type": "receipt",
        "document_id": receipt_id,
        "step": 2,
        "approver_id": "approver_002",
        "action": "approved",
    })

    db = get_database()
    updated = await db["receipts"].find_one({"_id": ObjectId(receipt_id)})
    assert updated["approval_status"] == "approved"


@pytest.mark.asyncio
async def test_rejection_requires_comment(corporate_id, approval_rule, client):
    """Reject without comment should return 400."""
    create_resp = await client.post("/api/v1/receipts", json={
        "date": "2025-04-01",
        "amount": 50000,
        "tax_rate": 10,
        "payee": "テスト株式会社",
        "category": "消耗品費",
        "payment_method": "立替",
        "fiscal_period": "2025-04",
    })
    receipt_id = create_resp.json()["id"]

    reject_resp = await client.post("/api/v1/approvals/actions", json={
        "document_type": "receipt",
        "document_id": receipt_id,
        "step": 1,
        "approver_id": "approver_001",
        "action": "rejected",
        "comment": None,
    })
    assert reject_resp.status_code == 400


@pytest.mark.asyncio
async def test_rejection_sets_status(corporate_id, approval_rule, client):
    """Reject with comment should set approval_status to rejected."""
    create_resp = await client.post("/api/v1/receipts", json={
        "date": "2025-04-01",
        "amount": 50000,
        "tax_rate": 10,
        "payee": "テスト株式会社",
        "category": "消耗品費",
        "payment_method": "立替",
        "fiscal_period": "2025-04",
    })
    receipt_id = create_resp.json()["id"]

    await client.post("/api/v1/approvals/actions", json={
        "document_type": "receipt",
        "document_id": receipt_id,
        "step": 1,
        "approver_id": "approver_001",
        "action": "rejected",
        "comment": "金額に誤りがあります",
    })

    db = get_database()
    updated = await db["receipts"].find_one({"_id": ObjectId(receipt_id)})
    assert updated["approval_status"] == "rejected"


# ─────────────── Alert Service Tests ───────────────

@pytest.mark.asyncio
async def test_high_amount_alert_generated(corporate_id, client):
    """A receipt >= 100,000 should generate a high_amount_alert notification."""
    from app.services.alert_service import check_high_amount_alerts

    db = get_database()
    await db["receipts"].insert_one({
        "corporate_id": corporate_id,
        "submitted_by": "user_001",
        "date": "2025-04-01",
        "amount": 150000,
        "tax_rate": 10,
        "payee": "高額テスト株式会社",
        "category": "設備費",
        "payment_method": "銀行振込",
        "fiscal_period": "2025-04",
        "approval_status": "pending_approval",
        "high_amount_alerted": False,
        "created_at": datetime.utcnow(),
    })

    result = await check_high_amount_alerts(threshold=100000)
    assert result["high_amount_flagged"] == 1

    notifications = await db["notifications"].find({
        "type": "high_amount_alert"
    }).to_list(10)
    assert len(notifications) == 1


@pytest.mark.asyncio
async def test_overdue_alert_generated(corporate_id):
    """An overdue received invoice should generate an overdue_alert notification."""
    from app.services.alert_service import check_due_date_alerts

    db = get_database()
    past_due = (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d")

    await db["invoices"].insert_one({
        "corporate_id": corporate_id,
        "document_type": "received",
        "invoice_number": "INV-001",
        "client_name": "遅延テスト株式会社",
        "issue_date": "2025-03-01",
        "due_date": past_due,
        "total_amount": 50000,
        "status": "received",
        "created_by": "user_001",
        "created_at": datetime.utcnow(),
    })

    result = await check_due_date_alerts()
    assert result["overdue"] == 1

    notifications = await db["notifications"].find({
        "type": "overdue_alert"
    }).to_list(10)
    assert len(notifications) == 1


@pytest.mark.asyncio
async def test_matching_flow(corporate_id, client):
    """Create a bank transaction + receipt, then match them."""
    db = get_database()

    # Insert transaction
    t_result = await db["bank_transactions"].insert_one({
        "corporate_id": corporate_id,
        "source_type": "bank",
        "account_name": "三井住友銀行",
        "transaction_date": "2025-04-10",
        "description": "テスト株式会社",
        "amount": 50000,
        "direction": "debit",
        "status": "unmatched",
        "fiscal_period": "2025-04",
        "imported_at": datetime.utcnow(),
    })
    tid = str(t_result.inserted_id)

    # Insert receipt
    r_result = await db["receipts"].insert_one({
        "corporate_id": corporate_id,
        "submitted_by": "user_001",
        "date": "2025-04-10",
        "amount": 50000,
        "tax_rate": 10,
        "payee": "テスト株式会社",
        "category": "消耗品費",
        "payment_method": "銀行振込",
        "fiscal_period": "2025-04",
        "status": "approved",
        "created_at": datetime.utcnow(),
    })
    rid = str(r_result.inserted_id)

    # Create match
    match_resp = await client.post("/api/v1/matches", json={
        "match_type": "receipt",
        "transaction_ids": [tid],
        "document_ids": [rid],
        "fiscal_period": "2025-04",
        "matched_by": "manual",
    })
    assert match_resp.status_code == 200, match_resp.text
    match_data = match_resp.json()
    assert match_data["difference"] == 0

    # Verify statuses updated
    txn = await db["bank_transactions"].find_one({"_id": t_result.inserted_id})
    rcpt = await db["receipts"].find_one({"_id": r_result.inserted_id})
    assert txn["status"] == "matched"
    assert rcpt["reconciliation_status"] == "reconciled"
