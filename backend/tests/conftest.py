import os
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport

os.environ["MONGODB_DB_NAME"] = "tax_agent_test"

from app.main import app
from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database
from app.api.deps import get_current_user

import pytest_asyncio

# Default dependency override
app.dependency_overrides[get_current_user] = lambda: {"uid": "test_tax_firm_uid"}

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    await connect_to_mongo()
    yield
    try:
        db = get_database()
        # Explicitly drop the entire test database to prevent cluttering the user's MongoDB
        await db.client.drop_database("tax_agent_test")
        await close_mongo_connection()
    except Exception:
        pass  # Ignore cleanup errors caused by event loop closure on session teardown

@pytest_asyncio.fixture(autouse=True)
async def clear_db():
    db = get_database()
    await db["corporates"].delete_many({})
    await db["employees"].delete_many({})
    yield
    await db["corporates"].delete_many({})
    await db["employees"].delete_many({})

@pytest.fixture
def mock_auth(mocker):
    def _override(uid="test_tax_firm_uid"):
        app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    yield _override
    # Reset to default
    app.dependency_overrides[get_current_user] = lambda: {"uid": "test_tax_firm_uid"}

@pytest.fixture
def mock_firestore(mocker):
    class MockDoc:
        def __init__(self, doc_id, data, exists=True):
            self.id = doc_id
            self._data = data
            self.exists = exists
        def to_dict(self):
            return self._data

    class FakeDocumentRef:
        def __init__(self, doc_id):
            self.id = doc_id
        def get(self):
            return MockDoc(self.id, {"companyName": f"Mock {self.id}"})

    class FakeCollection:
        def __init__(self, name):
            self.name = name
        def document(self, doc_id):
            return FakeDocumentRef(doc_id)

    class FakeFirestore:
        def collection(self, name):
            return FakeCollection(name)
        def get_all(self, refs):
            return [MockDoc(ref.id, {"companyName": f"Mock {ref.id}"}) for ref in refs]
            
    mock_db = FakeFirestore()
    mocker.patch('firebase_admin.firestore.client', return_value=mock_db)
    return mock_db

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
