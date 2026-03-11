import asyncio
import os
import requests
from dotenv import load_dotenv

# Run the backend locally first: `cd backend && uvicorn app.main:app --reload`
# We use a mock token here assuming deps.py falls back to mock if real token fails,
# but it's better to just manually ping the endpoint as a test.

API_URL = "http://localhost:8000/api/v1"
MOCK_TOKEN = "test-token"

def test_employee_registration():
    headers = {
        "Authorization": f"Bearer {MOCK_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = [
        {
            "name": "Employee Alpha",
            "email": "alpha.test@example.com",
            "role": "staff",
            "permissions": {"data_view": True}
        },
        {
            "name": "Employee Beta",
            "email": "beta.test@example.com",
            "role": "manager",
            "permissions": {"data_approve": True}
        }
    ]

    print(f"Testing POST {API_URL}/users/employees")
    try:
        response = requests.post(f"{API_URL}/users/employees", json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    test_employee_registration()
