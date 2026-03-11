import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_register_tax_firm(client: AsyncClient, mock_auth):
    """Test registering a new Tax Firm"""
    uid = "firm_test_123"
    mock_auth(uid)
    
    payload = {
        "corporateType": "tax_firm",
        "planId": "plan-standard",
        "selectedOptions": [],
        "monthlyFee": 30000
    }
    
    response = await client.post("/api/v1/users/register", json=payload)
    assert response.status_code == 201
    
    data = response.json()
    assert data["data"]["corporateType"] == "tax_firm"
    assert data["data"]["firebase_uid"] == uid
    assert data["data"]["monthlyFee"] == 30000

@pytest.mark.asyncio
async def test_register_corporate_client(client: AsyncClient, mock_auth):
    """Test registering a Corporate client under a Tax Firm"""
    tax_firm_uid = "firm_test_123"
    client_uid = "client_test_456"
    
    # 1. Register Tax Firm
    mock_auth(tax_firm_uid)
    await client.post("/api/v1/users/register", json={
        "corporateType": "tax_firm",
        "planId": "plan-standard",
        "monthlyFee": 30000
    })
    
    # 2. Register Corporate Client (auth as the new client)
    mock_auth(client_uid)
    payload = {
        "corporateType": "corporate",
        "planId": "plan-tax-firm-managed",
        "advising_tax_firm_id": tax_firm_uid,
        "monthlyFee": 0
    }
    
    response = await client.post("/api/v1/users/register", json=payload)
    assert response.status_code == 201
    assert response.json()["data"]["advising_tax_firm_id"] == tax_firm_uid
    assert response.json()["data"]["monthlyFee"] == 0

@pytest.mark.asyncio
async def test_get_clients_from_tax_firm(client: AsyncClient, mock_auth, mock_firestore):
    """Test that a Tax Firm can fetch its attached Corporate clients"""
    tax_firm_uid = "firm_test_123"
    client_uid = "client_test_456"
    
    # Setup Data
    mock_auth(client_uid)
    await client.post("/api/v1/users/register", json={
        "corporateType": "corporate",
        "planId": "plan-tax-firm-managed",
        "advising_tax_firm_id": tax_firm_uid,
        "monthlyFee": 0
    })
    
    # Fetch Clients as the Tax Firm
    mock_auth(tax_firm_uid)
    response = await client.get("/api/v1/users/clients")
    assert response.status_code == 200
    
    clients = response.json().get("data", [])
    assert len(clients) == 1
    assert clients[0]["firebase_uid"] == client_uid
    
    # Verify Firestore mock combined the name
    assert clients[0]["companyName"] == f"Mock {client_uid}"

@pytest.mark.asyncio
async def test_register_standalone_corporate(client: AsyncClient, mock_auth):
    """Test registering an independent Corporate client not affiliated with a Tax Firm"""
    uid = "standalone_corp_999"
    mock_auth(uid)
    
    payload = {
        "corporateType": "corporate",
        "planId": "plan-standard",
        "monthlyFee": 30000
        # No advising_tax_firm_id is sent when they register themselves
    }
    
    response = await client.post("/api/v1/users/register", json=payload)
    assert response.status_code == 201
    
    data = response.json()
    assert data["data"]["corporateType"] == "corporate"
    assert data["data"]["firebase_uid"] == uid
    assert data["data"].get("advising_tax_firm_id") is None
    assert data["data"]["monthlyFee"] == 30000

@pytest.mark.asyncio
async def test_sync_client_employees(client: AsyncClient, mock_auth):
    """Test syncing employees for a client under a Tax Firm (Employee UPSERT via Edit Screen)"""
    tax_firm_uid = "firm_test_sync"
    client_uid = "client_test_sync"
    
    # 1. Start by registering a tax firm
    mock_auth(tax_firm_uid)
    await client.post("/api/v1/users/register", json={
        "corporateType": "tax_firm",
        "planId": "plan-standard",
        "monthlyFee": 30000
    })
    
    # 2. Register the corporate client bound to the tax firm
    mock_auth(client_uid)
    res = await client.post("/api/v1/users/register", json={
        "corporateType": "corporate",
        "planId": "plan-tax-firm-managed",
        "advising_tax_firm_id": tax_firm_uid,
        "monthlyFee": 0
    })
    
    # Switch back to Tax Firm and query their clients list to get the _id
    mock_auth(tax_firm_uid)
    clients_res = await client.get("/api/v1/users/clients")
    client_info = clients_res.json()["data"][0]
    client_mongo_id = client_info["_id"]
    
    # 3. Simulate Tax Firm Edit Action: Sync Employees
    mock_auth(tax_firm_uid)
    payload = [
        {
            "name": "Employee 1",
            "email": "emp1@test.com",
            "role": "staff",
            "permissions": {"dataProcessing": True},
            "usageFee": 3000
        },
        {
            "name": "Employee 2",
            "email": "emp2@test.com",
            "role": "manager",
            "permissions": {"dataProcessing": True, "reportExtraction": True},
            "usageFee": 3000
        }
    ]
    
    # Use PUT route designed for Edit screen
    sync_res = await client.put(f"/api/v1/users/clients/{client_mongo_id}/employees", json=payload)
    assert sync_res.status_code == 200
    
    sync_data = sync_res.json()["data"]
    assert len(sync_data) == 2
    assert sync_data[0]["email"] == "emp1@test.com"
    # The first one should be 'invited' because we mocked new users
    assert sync_data[0]["status"] in ["invited", "synced"] 

