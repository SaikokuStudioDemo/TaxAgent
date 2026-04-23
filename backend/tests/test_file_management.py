"""
Tests for file management: logical delete, approved-receipt guard, search filters, signed URL.

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_file_management.py -v
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

from app.db.mongodb import get_database
from app.main import app
from app.api.deps import get_current_user

_UID_A = "test_tax_firm_uid"   # conftest のデフォルト UID（法人A）
_UID_B = "other_corp_uid_b"    # 別法人B の UID


# ─────────────── Fixtures ───────────────

@pytest_asyncio.fixture
async def registered_corp(client: AsyncClient):
    resp = await client.post("/api/v1/users/register", json={
        "corporateType": "corporate",
        "planId": "plan-standard",
        "monthlyFee": 10000,
    })
    assert resp.status_code == 201
    return resp.json()["data"]


_RECEIPT_PAYLOAD = {
    "date": "2026-04-01",
    "amount": 5500,
    "tax_rate": 10,
    "payee": "タクシー会社",
    "category": "旅費交通費",
    "payment_method": "立替",
    "fiscal_period": "2026-04",
    "attachments": [],
    "storage_path": "receipts/corp/123_test.pdf",
    "storage_url": "https://storage.example.com/file.pdf",
}


# ─────────────── 論理削除テスト ───────────────

async def test_receipt_delete_changes_to_logical_delete(
    client: AsyncClient, registered_corp
):
    """DELETE /receipts/:id が物理削除ではなく is_deleted=True になること。"""
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    assert create.status_code == 200
    receipt_id = create.json()["id"]

    delete = await client.delete(f"/api/v1/receipts/{receipt_id}")
    assert delete.status_code == 200

    # DB を直接確認して物理削除されていないこと
    db = get_database()
    from bson import ObjectId
    doc = await db["receipts"].find_one({"_id": ObjectId(receipt_id)})
    assert doc is not None, "物理削除されてはいけない"
    assert doc.get("is_deleted") is True
    assert doc.get("deleted_at") is not None
    assert doc.get("deleted_by") is not None


async def test_approved_receipt_cannot_be_deleted(
    client: AsyncClient, registered_corp
):
    """approval_status='approved' の領収書を DELETE すると 400 が返ること。"""
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    assert create.status_code == 200
    receipt_id = create.json()["id"]

    db = get_database()
    from bson import ObjectId
    await db["receipts"].update_one(
        {"_id": ObjectId(receipt_id)},
        {"$set": {"approval_status": "approved"}},
    )

    delete = await client.delete(f"/api/v1/receipts/{receipt_id}")
    assert delete.status_code == 400
    assert "承認済み" in delete.json()["detail"]


async def test_receipt_list_excludes_deleted(
    client: AsyncClient, registered_corp
):
    """is_deleted=True の領収書が GET /receipts に含まれないこと。"""
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    assert create.status_code == 200
    receipt_id = create.json()["id"]

    await client.delete(f"/api/v1/receipts/{receipt_id}")

    lst = await client.get("/api/v1/receipts")
    assert lst.status_code == 200
    ids = [r["id"] for r in lst.json()]
    assert receipt_id not in ids, "論理削除済みの領収書が一覧に含まれている"


# ─────────────── 署名付きURLテスト ───────────────

@patch(
    "app.api.routes.receipts.generate_signed_url",
    new_callable=AsyncMock,
    return_value="https://mock-url.com/file.pdf",
)
async def test_file_url_endpoint_returns_signed_url(
    mock_signed_url, client: AsyncClient, registered_corp
):
    """storage_path がある領収書で GET /receipts/:id/file-url が URL を返すこと。"""
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    assert create.status_code == 200
    receipt_id = create.json()["id"]

    resp = await client.get(f"/api/v1/receipts/{receipt_id}/file-url")
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://mock-url.com/file.pdf"
    assert resp.json()["expires_in"] == 3600


@patch(
    "app.api.routes.receipts.generate_signed_url",
    new_callable=AsyncMock,
    return_value="https://mock-url.com/file.pdf",
)
async def test_file_url_endpoint_requires_storage_path(
    mock_signed_url, client: AsyncClient, registered_corp
):
    """storage_path がない領収書で GET /receipts/:id/file-url を叩くと 404 が返ること。"""
    payload_no_path = {**_RECEIPT_PAYLOAD, "storage_path": None}
    create = await client.post("/api/v1/receipts", json=payload_no_path)
    assert create.status_code == 200
    receipt_id = create.json()["id"]

    resp = await client.get(f"/api/v1/receipts/{receipt_id}/file-url")
    assert resp.status_code == 404


# ─────────────── 検索フィルターテスト ───────────────

async def test_receipt_search_by_date_range(
    client: AsyncClient, registered_corp
):
    """date_from・date_to で正しく絞り込めること。"""
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "date": "2026-03-01"})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "date": "2026-04-15"})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "date": "2026-05-01"})

    resp = await client.get("/api/v1/receipts?date_from=2026-04-01&date_to=2026-04-30")
    assert resp.status_code == 200
    dates = [r["date"] for r in resp.json()]
    assert all("2026-04" in d for d in dates), f"期間外のデータが含まれている: {dates}"
    assert "2026-04-15" in dates


async def test_receipt_search_by_amount_range(
    client: AsyncClient, registered_corp
):
    """amount_min・amount_max で正しく絞り込めること。"""
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "amount": 1000})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "amount": 5000})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "amount": 50000})

    resp = await client.get("/api/v1/receipts?amount_min=3000&amount_max=10000")
    assert resp.status_code == 200
    amounts = [r["amount"] for r in resp.json()]
    assert 5000 in amounts
    assert 1000 not in amounts
    assert 50000 not in amounts


async def test_receipt_search_by_payee(
    client: AsyncClient, registered_corp
):
    """payee の部分一致検索が正しく機能すること。"""
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "payee": "山田タクシー"})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "payee": "PCショップ田中"})

    resp = await client.get("/api/v1/receipts?payee=タクシー")
    assert resp.status_code == 200
    payees = [r["payee"] for r in resp.json()]
    assert "山田タクシー" in payees
    assert "PCショップ田中" not in payees


# ─────────────── 請求書フィルターテスト ───────────────

_INVOICE_PAYLOAD = {
    "document_type": "received",
    "invoice_number": "REC-001",
    "client_name": "テスト株式会社",
    "recipient_email": "",
    "issue_date": "2026-04-01",
    "due_date": "2026-04-30",
    "subtotal": 10000,
    "tax_amount": 1000,
    "total_amount": 11000,
    "fiscal_period": "2026-04",
    "line_items": [],
    "storage_path": "invoices/corp/456_test.pdf",
    "storage_url": "https://storage.example.com/invoice.pdf",
}


async def test_invoice_search_filters(
    client: AsyncClient, registered_corp
):
    """invoices にも date_from・amount_min フィルターが機能すること。"""
    await client.post("/api/v1/invoices", json={
        **_INVOICE_PAYLOAD, "issue_date": "2026-03-01", "total_amount": 5000,
        "subtotal": 4545, "tax_amount": 455, "invoice_number": "REC-002"
    })
    await client.post("/api/v1/invoices", json={
        **_INVOICE_PAYLOAD, "issue_date": "2026-04-15", "total_amount": 11000,
        "invoice_number": "REC-003"
    })

    resp = await client.get(
        "/api/v1/invoices?date_from=2026-04-01&amount_min=10000"
    )
    assert resp.status_code == 200
    results = resp.json()
    assert all(r["issue_date"] >= "2026-04-01" for r in results)
    assert all(r["total_amount"] >= 10000 for r in results)


# ═══════════════════════════════════════════════════════════════════
# ① 論理削除の境界値テスト
# ═══════════════════════════════════════════════════════════════════

async def test_delete_pending_receipt_succeeds(client: AsyncClient, registered_corp):
    """approval_status='pending_approval' の領収書は論理削除できること。"""
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    assert create.status_code == 200
    receipt_id = create.json()["id"]

    # デフォルトが pending_approval なのでそのまま削除
    resp = await client.delete(f"/api/v1/receipts/{receipt_id}")
    assert resp.status_code == 200

    db = get_database()
    from bson import ObjectId
    doc = await db["receipts"].find_one({"_id": ObjectId(receipt_id)})
    assert doc["is_deleted"] is True


async def test_delete_rejected_receipt_succeeds(client: AsyncClient, registered_corp):
    """approval_status='rejected' の領収書は論理削除できること。"""
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    receipt_id = create.json()["id"]

    db = get_database()
    from bson import ObjectId
    await db["receipts"].update_one(
        {"_id": ObjectId(receipt_id)},
        {"$set": {"approval_status": "rejected"}},
    )

    resp = await client.delete(f"/api/v1/receipts/{receipt_id}")
    assert resp.status_code == 200


async def test_delete_approved_receipt_blocked(client: AsyncClient, registered_corp):
    """approval_status='approved' の領収書は 400 が返ること。"""
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    receipt_id = create.json()["id"]

    db = get_database()
    from bson import ObjectId
    await db["receipts"].update_one(
        {"_id": ObjectId(receipt_id)},
        {"$set": {"approval_status": "approved"}},
    )

    resp = await client.delete(f"/api/v1/receipts/{receipt_id}")
    assert resp.status_code == 400
    assert "承認済み" in resp.json()["detail"]


async def test_deleted_receipt_not_in_list(client: AsyncClient, registered_corp):
    """論理削除した領収書が GET /receipts に含まれないこと。"""
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    receipt_id = create.json()["id"]

    await client.delete(f"/api/v1/receipts/{receipt_id}")

    lst = await client.get("/api/v1/receipts")
    ids = [r["id"] for r in lst.json()]
    assert receipt_id not in ids


async def test_deleted_receipt_detail_returns_404(client: AsyncClient, registered_corp):
    """論理削除した領収書の GET /receipts/:id が 404 を返すこと。"""
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    receipt_id = create.json()["id"]

    await client.delete(f"/api/v1/receipts/{receipt_id}")

    resp = await client.get(f"/api/v1/receipts/{receipt_id}")
    assert resp.status_code == 404


@patch(
    "app.api.routes.receipts.generate_signed_url",
    new_callable=AsyncMock,
    return_value="https://mock-url.com/file.pdf",
)
async def test_deleted_receipt_file_url_returns_404(
    mock_signed_url, client: AsyncClient, registered_corp
):
    """論理削除した領収書の GET /receipts/:id/file-url が 404 を返すこと。"""
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    receipt_id = create.json()["id"]

    await client.delete(f"/api/v1/receipts/{receipt_id}")

    resp = await client.get(f"/api/v1/receipts/{receipt_id}/file-url")
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# ② 検索フィルターの境界値テスト
# ═══════════════════════════════════════════════════════════════════

async def test_date_from_inclusive(client: AsyncClient, registered_corp):
    """date_from の境界日付当日のデータが含まれること。"""
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "date": "2025-03-01", "fiscal_period": "2025-03"})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "date": "2025-02-28", "fiscal_period": "2025-02"})

    resp = await client.get("/api/v1/receipts?date_from=2025-03-01")
    assert resp.status_code == 200
    dates = [r["date"] for r in resp.json()]
    assert "2025-03-01" in dates
    assert "2025-02-28" not in dates


async def test_date_to_inclusive(client: AsyncClient, registered_corp):
    """date_to の境界日付当日のデータが含まれること。"""
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "date": "2025-03-31", "fiscal_period": "2025-03"})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "date": "2025-04-01", "fiscal_period": "2025-04"})

    resp = await client.get("/api/v1/receipts?date_to=2025-03-31")
    assert resp.status_code == 200
    dates = [r["date"] for r in resp.json()]
    assert "2025-03-31" in dates
    assert "2025-04-01" not in dates


async def test_date_range_excludes_outside(client: AsyncClient, registered_corp):
    """範囲外の日付が含まれないこと。"""
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "date": "2025-02-28", "fiscal_period": "2025-02"})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "date": "2025-03-15", "fiscal_period": "2025-03"})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "date": "2025-04-01", "fiscal_period": "2025-04"})

    resp = await client.get("/api/v1/receipts?date_from=2025-03-01&date_to=2025-03-31")
    assert resp.status_code == 200
    dates = [r["date"] for r in resp.json()]
    assert "2025-02-28" not in dates
    assert "2025-04-01" not in dates
    assert "2025-03-15" in dates


async def test_amount_min_boundary(client: AsyncClient, registered_corp):
    """amount_min=1000 の場合に 999 が除外され 1000 が含まれること。"""
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "amount": 999})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "amount": 1000})

    resp = await client.get("/api/v1/receipts?amount_min=1000")
    assert resp.status_code == 200
    amounts = [r["amount"] for r in resp.json()]
    assert 1000 in amounts
    assert 999 not in amounts


async def test_amount_max_boundary(client: AsyncClient, registered_corp):
    """amount_max=5000 の場合に 5001 が除外され 5000 が含まれること。"""
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "amount": 5000})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "amount": 5001})

    resp = await client.get("/api/v1/receipts?amount_max=5000")
    assert resp.status_code == 200
    amounts = [r["amount"] for r in resp.json()]
    assert 5000 in amounts
    assert 5001 not in amounts


async def test_payee_partial_match(client: AsyncClient, registered_corp):
    """payee 部分一致で複数件ヒットすること。"""
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "payee": "株式会社ABC"})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "payee": "株式会社XYZ"})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "payee": "個人事業主田中"})

    resp = await client.get("/api/v1/receipts?payee=株式会社")
    assert resp.status_code == 200
    payees = [r["payee"] for r in resp.json()]
    assert "株式会社ABC" in payees
    assert "株式会社XYZ" in payees
    assert "個人事業主田中" not in payees


async def test_payee_case_insensitive(client: AsyncClient, registered_corp):
    """英字 payee 検索が大文字小文字を区別しないこと。"""
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "payee": "Amazon Japan"})
    await client.post("/api/v1/receipts", json={**_RECEIPT_PAYLOAD, "payee": "google LLC"})

    resp = await client.get("/api/v1/receipts?payee=amazon")
    assert resp.status_code == 200
    payees = [r["payee"] for r in resp.json()]
    assert "Amazon Japan" in payees
    assert "google LLC" not in payees


async def test_combined_filters(client: AsyncClient, registered_corp):
    """date_from・amount_min・payee を同時指定した場合に全条件を満たすデータのみ返ること。"""
    # 全条件を満たす
    await client.post("/api/v1/receipts", json={
        **_RECEIPT_PAYLOAD,
        "date": "2025-04-10", "amount": 3000, "payee": "株式会社テスト",
        "fiscal_period": "2025-04",
    })
    # date が範囲外
    await client.post("/api/v1/receipts", json={
        **_RECEIPT_PAYLOAD,
        "date": "2025-03-01", "amount": 3000, "payee": "株式会社テスト",
        "fiscal_period": "2025-03",
    })
    # amount が不足
    await client.post("/api/v1/receipts", json={
        **_RECEIPT_PAYLOAD,
        "date": "2025-04-10", "amount": 500, "payee": "株式会社テスト",
        "fiscal_period": "2025-04",
    })
    # payee が違う
    await client.post("/api/v1/receipts", json={
        **_RECEIPT_PAYLOAD,
        "date": "2025-04-10", "amount": 3000, "payee": "別会社",
        "fiscal_period": "2025-04",
    })

    resp = await client.get(
        "/api/v1/receipts?date_from=2025-04-01&amount_min=1000&payee=株式会社テスト"
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["payee"] == "株式会社テスト"
    assert results[0]["date"] == "2025-04-10"
    assert results[0]["amount"] == 3000


# ═══════════════════════════════════════════════════════════════════
# ③ ファイル URL のテスト
# ═══════════════════════════════════════════════════════════════════

async def test_file_url_without_storage_path(client: AsyncClient, registered_corp):
    """storage_path が空の領収書で file-url が 404 を返すこと。"""
    payload_no_path = {**_RECEIPT_PAYLOAD, "storage_path": None}
    create = await client.post("/api/v1/receipts", json=payload_no_path)
    receipt_id = create.json()["id"]

    resp = await client.get(f"/api/v1/receipts/{receipt_id}/file-url")
    assert resp.status_code == 404


@patch(
    "app.api.routes.receipts.generate_signed_url",
    new_callable=AsyncMock,
    return_value="https://mock-url.com/file.pdf",
)
async def test_file_url_cross_corporate_blocked(
    mock_signed_url, client: AsyncClient, registered_corp
):
    """別法人の領収書の file-url にアクセスすると 404 が返ること。"""
    # 法人A（デフォルト UID）で領収書作成
    create = await client.post("/api/v1/receipts", json=_RECEIPT_PAYLOAD)
    assert create.status_code == 200
    receipt_id_a = create.json()["id"]

    # 法人B に切り替えて登録
    app.dependency_overrides[get_current_user] = lambda: {"uid": _UID_B}
    try:
        await client.post("/api/v1/users/register", json={
            "corporateType": "corporate",
            "planId": "plan-standard",
            "monthlyFee": 10000,
        })
        # 法人B から法人A の領収書 file-url にアクセス → 404
        resp = await client.get(f"/api/v1/receipts/{receipt_id_a}/file-url")
        assert resp.status_code == 404, f"別法人の file-url にアクセスできてしまった: {resp.status_code}"
    finally:
        app.dependency_overrides[get_current_user] = lambda: {"uid": _UID_A}


@patch(
    "app.api.routes.invoices.generate_signed_url",
    new_callable=AsyncMock,
    return_value="https://mock-url.com/invoice.pdf",
)
async def test_invoice_file_url_works(
    mock_signed_url, client: AsyncClient, registered_corp
):
    """請求書の GET /invoices/:id/file-url が署名付きURLを返すこと。"""
    create = await client.post("/api/v1/invoices", json=_INVOICE_PAYLOAD)
    assert create.status_code == 200
    invoice_id = create.json()["id"]

    resp = await client.get(f"/api/v1/invoices/{invoice_id}/file-url")
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://mock-url.com/invoice.pdf"
    assert resp.json()["expires_in"] == 3600


# ═══════════════════════════════════════════════════════════════════
# ④ スコープテスト
# ═══════════════════════════════════════════════════════════════════

async def test_search_filters_respect_corporate_scope(
    client: AsyncClient, registered_corp
):
    """検索フィルター使用時も別法人のデータが含まれないこと。"""
    # 法人A で領収書作成
    await client.post("/api/v1/receipts", json={
        **_RECEIPT_PAYLOAD,
        "date": "2025-04-10", "payee": "株式会社テスト", "fiscal_period": "2025-04",
    })

    # 法人B に切り替えて別のデータを作成
    app.dependency_overrides[get_current_user] = lambda: {"uid": _UID_B}
    try:
        await client.post("/api/v1/users/register", json={
            "corporateType": "corporate",
            "planId": "plan-standard",
            "monthlyFee": 10000,
        })
        await client.post("/api/v1/receipts", json={
            **_RECEIPT_PAYLOAD,
            "date": "2025-04-10", "payee": "株式会社テスト", "fiscal_period": "2025-04",
        })

        # 法人B から検索 → 法人B のデータのみ返ること（法人Aのデータが混入しないこと）
        resp = await client.get("/api/v1/receipts?date_from=2025-04-01&payee=株式会社テスト")
        assert resp.status_code == 200
        results = resp.json()
        # 法人B のコーポレートIDで絞られているはず
        corp_b = await client.get("/api/v1/users/me")
        # 全件が法人B の corporate_id に属することを確認
        assert len(results) == 1, f"法人Bには1件のみのはずが {len(results)} 件返った（スコープ漏洩の可能性）"
    finally:
        app.dependency_overrides[get_current_user] = lambda: {"uid": _UID_A}


async def test_deleted_invoice_not_in_list(client: AsyncClient, registered_corp):
    """論理削除した請求書が GET /invoices に含まれないこと。"""
    create = await client.post("/api/v1/invoices", json=_INVOICE_PAYLOAD)
    assert create.status_code == 200
    invoice_id = create.json()["id"]

    delete = await client.delete(f"/api/v1/invoices/{invoice_id}")
    assert delete.status_code == 200

    lst = await client.get("/api/v1/invoices")
    assert lst.status_code == 200
    ids = [r["id"] for r in lst.json()]
    assert invoice_id not in ids, "論理削除済みの請求書が一覧に含まれている"
