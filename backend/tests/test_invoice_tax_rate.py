"""
Invoice tax_rate フィールドのテスト

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_invoice_tax_rate.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

CORP_ID = str(ObjectId())
USER_ID = str(ObjectId())


# ─────────────── モックヘルパー ───────────────

def make_cursor(data=None):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=data or [])
    return cursor


def make_col(find_one=None, find_data=None):
    col = MagicMock()
    inserted_id = ObjectId()
    col.find_one = AsyncMock(return_value=find_one)
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inserted_id))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return col


def build_mock_db(collections=None):
    db = MagicMock()
    cols = collections or {}
    db.__getitem__ = MagicMock(side_effect=lambda k: cols.get(k, make_col()))
    return db


def make_ctx(db=None, corporate_id=CORP_ID, user_id=USER_ID):
    from app.api.helpers import CorporateContext
    ctx = MagicMock(spec=CorporateContext)
    ctx.corporate_id = corporate_id
    ctx.user_id = user_id
    ctx.firebase_uid = "test_uid"
    ctx.db = db or build_mock_db()
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# test_invoice_create_saves_tax_rate
# POST /invoices に top-level tax_rate が含まれていれば DB に保存される
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invoice_create_saves_tax_rate():
    from app.api.routes.invoices import create_invoice
    from app.models.invoice import InvoiceCreate

    inv_id = ObjectId()
    saved_doc = {
        "_id": inv_id,
        "corporate_id": CORP_ID,
        "tax_rate": 8,
        "invoice_number": "INV-001",
        "document_type": "issued",
        "client_name": "テスト株式会社",
        "recipient_email": "test@example.com",
        "issue_date": "2025-01-01",
        "due_date": "2025-01-31",
        "subtotal": 10000,
        "tax_amount": 800,
        "total_amount": 10800,
        "line_items": [{"description": "作業費", "category": "役務", "amount": 10000, "tax_rate": 8}],
        "approval_status": "draft",
    }

    invoices_col = make_col(find_one=saved_doc)
    invoices_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inv_id))
    db = build_mock_db({
        "invoices": invoices_col,
        "audit_logs": make_col(),
    })
    ctx = make_ctx(db=db)

    payload = InvoiceCreate(
        document_type="issued",
        invoice_number="INV-001",
        tax_rate=8,
        client_name="テスト株式会社",
        recipient_email="test@example.com",
        issue_date="2025-01-01",
        due_date="2025-01-31",
        subtotal=10000,
        tax_amount=800,
        total_amount=10800,
        line_items=[{"description": "作業費", "category": "役務", "amount": 10000, "tax_rate": 8}],
    )

    with (
        patch("app.api.routes.invoices.evaluate_approval_rules", AsyncMock(return_value=(None, []))),
        patch("app.api.routes.invoices.apply_journal_rules", AsyncMock(side_effect=lambda db, cid, docs, **kw: docs)),
    ):
        await create_invoice(payload=payload, ctx=ctx)

    inserted = invoices_col.insert_one.call_args[0][0]
    assert inserted["tax_rate"] == 8, f"Expected tax_rate=8, got {inserted.get('tax_rate')}"


# ─────────────────────────────────────────────────────────────────────────────
# test_invoice_tax_rate_default
# tax_rate 未指定の場合、モデルは None、エンドポイントが DB から動的に補完する
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invoice_tax_rate_default():
    from app.api.routes.invoices import create_invoice
    from app.models.invoice import InvoiceCreate
    from app.services.alert_service import DEFAULT_TAX_RATES

    inv_id = ObjectId()
    saved_doc = {
        "_id": inv_id,
        "corporate_id": CORP_ID,
        "tax_rate": DEFAULT_TAX_RATES["standard"],
        "invoice_number": "INV-002",
        "document_type": "issued",
        "client_name": "テスト株式会社",
        "recipient_email": "test@example.com",
        "issue_date": "2025-01-01",
        "due_date": "2025-01-31",
        "subtotal": 10000,
        "tax_amount": 1000,
        "total_amount": 11000,
        "line_items": [],
        "approval_status": "draft",
    }

    invoices_col = make_col(find_one=saved_doc)
    invoices_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inv_id))
    # system_settings コレクションは未設定（None を返す）→ DEFAULT_TAX_RATES["standard"] が使われる
    db = build_mock_db({
        "invoices": invoices_col,
        "audit_logs": make_col(),
        "system_settings": make_col(find_one=None),
    })
    ctx = make_ctx(db=db)

    payload = InvoiceCreate(
        document_type="issued",
        invoice_number="INV-002",
        # tax_rate not specified — None になる
        client_name="テスト株式会社",
        recipient_email="test@example.com",
        issue_date="2025-01-01",
        due_date="2025-01-31",
        subtotal=10000,
        tax_amount=1000,
        total_amount=11000,
    )

    assert payload.tax_rate is None  # モデルデフォルトは None（動的補完）

    with (
        patch("app.api.routes.invoices.evaluate_approval_rules", AsyncMock(return_value=(None, []))),
        patch("app.api.routes.invoices.apply_journal_rules", AsyncMock(side_effect=lambda db, cid, docs, **kw: docs)),
    ):
        await create_invoice(payload=payload, ctx=ctx)

    inserted = invoices_col.insert_one.call_args[0][0]
    assert inserted["tax_rate"] == DEFAULT_TAX_RATES["standard"]


# ─────────────────────────────────────────────────────────────────────────────
# test_invoice_edit_preserves_tax_rate
# PATCH /invoices/{id} に tax_rate を含めると更新される
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invoice_edit_preserves_tax_rate():
    from app.api.routes.invoices import update_invoice

    inv_id = ObjectId()
    existing_doc = {
        "_id": inv_id,
        "corporate_id": CORP_ID,
        "tax_rate": 10,
        "document_type": "issued",
        "approval_status": "draft",
        "approval_rule_id": None,
    }
    updated_doc = {**existing_doc, "tax_rate": 8}

    invoices_col = MagicMock()
    invoices_col.find_one = AsyncMock(side_effect=[existing_doc, updated_doc])
    invoices_col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    db = build_mock_db({"invoices": invoices_col})
    ctx = make_ctx(db=db)

    await update_invoice(invoice_id=str(inv_id), payload={"tax_rate": 8}, ctx=ctx)

    update_call = invoices_col.update_one.call_args
    update_set = update_call[0][1]["$set"]
    assert update_set.get("tax_rate") == 8, f"Expected tax_rate=8 in $set, got {update_set}"


# ─────────────────────────────────────────────────────────────────────────────
# test_invoice_tax_rate_fallback_to_line_items
# InvoiceCreate モデルの tax_rate フィールドが Optional であり
# 未指定時は DEFAULT_TAX_RATE になることを確認
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invoice_tax_rate_fallback_to_line_items():
    from app.models.invoice import InvoiceCreate, InvoiceLineItem

    # top-level tax_rate あり
    inv_with_top = InvoiceCreate(
        document_type="issued",
        invoice_number="INV-003",
        tax_rate=8,
        client_name="テスト株式会社",
        recipient_email="test@example.com",
        issue_date="2025-01-01",
        due_date="2025-01-31",
        subtotal=10000,
        tax_amount=800,
        total_amount=10800,
        line_items=[InvoiceLineItem(description="作業費", category="役務", amount=10000, tax_rate=8)],
    )
    assert inv_with_top.tax_rate == 8

    # top-level tax_rate 未指定 → None（エンドポイントが DB から動的補完する）
    inv_no_top = InvoiceCreate(
        document_type="issued",
        invoice_number="INV-004",
        client_name="テスト株式会社",
        recipient_email="test@example.com",
        issue_date="2025-01-01",
        due_date="2025-01-31",
        subtotal=10000,
        tax_amount=1000,
        total_amount=11000,
        line_items=[InvoiceLineItem(description="作業費", category="役務", amount=10000, tax_rate=10)],
    )
    assert inv_no_top.tax_rate is None  # モデルは None、エンドポイントが動的補完する
    assert inv_no_top.line_items[0].tax_rate == 10


# =============================================================================
# ② 動的取得テスト
# =============================================================================

@pytest.mark.asyncio
async def test_default_tax_rate_used_when_not_specified():
    """tax_rate 省略時に system_settings 未設定なら DEFAULT_TAX_RATES["standard"] が使われること。"""
    from app.api.routes.invoices import create_invoice
    from app.models.invoice import InvoiceCreate
    from app.services.alert_service import DEFAULT_TAX_RATES

    inv_id = ObjectId()
    invoices_col = make_col(find_one={"_id": inv_id, "corporate_id": CORP_ID, "tax_rate": DEFAULT_TAX_RATES["standard"]})
    invoices_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inv_id))
    db = build_mock_db({
        "invoices": invoices_col,
        "audit_logs": make_col(),
        "system_settings": make_col(find_one=None),  # 未設定
    })
    ctx = make_ctx(db=db)

    payload = InvoiceCreate(
        document_type="issued", invoice_number="INV-D1",
        client_name="テスト", recipient_email="t@example.com",
        issue_date="2025-01-01", due_date="2025-01-31",
        subtotal=0, tax_amount=0, total_amount=0,
    )
    assert payload.tax_rate is None

    with (
        patch("app.api.routes.invoices.evaluate_approval_rules", AsyncMock(return_value=(None, []))),
        patch("app.api.routes.invoices.apply_journal_rules", AsyncMock(side_effect=lambda db, cid, docs, **kw: docs)),
    ):
        await create_invoice(payload=payload, ctx=ctx)

    inserted = invoices_col.insert_one.call_args[0][0]
    assert inserted["tax_rate"] == DEFAULT_TAX_RATES["standard"]


@pytest.mark.asyncio
async def test_system_settings_standard_8_used_as_default():
    """system_settings の standard が 8 の場合、新規請求書のデフォルト税率が 8 になること。"""
    from app.api.routes.invoices import create_invoice
    from app.models.invoice import InvoiceCreate

    inv_id = ObjectId()
    invoices_col = make_col(find_one={"_id": inv_id, "corporate_id": CORP_ID, "tax_rate": 8})
    invoices_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inv_id))
    sys_col = make_col(find_one={"key": "tax_rates", "value": {"standard": 8, "reduced": 5, "exempt": 0}})
    db = build_mock_db({
        "invoices": invoices_col,
        "audit_logs": make_col(),
        "system_settings": sys_col,
    })
    ctx = make_ctx(db=db)

    payload = InvoiceCreate(
        document_type="issued", invoice_number="INV-D2",
        client_name="テスト", recipient_email="t@example.com",
        issue_date="2025-01-01", due_date="2025-01-31",
        subtotal=0, tax_amount=0, total_amount=0,
    )

    with (
        patch("app.api.routes.invoices.evaluate_approval_rules", AsyncMock(return_value=(None, []))),
        patch("app.api.routes.invoices.apply_journal_rules", AsyncMock(side_effect=lambda db, cid, docs, **kw: docs)),
    ):
        await create_invoice(payload=payload, ctx=ctx)

    inserted = invoices_col.insert_one.call_args[0][0]
    assert inserted["tax_rate"] == 8, f"Expected 8, got {inserted.get('tax_rate')}"


@pytest.mark.asyncio
async def test_explicit_tax_rate_overrides_default():
    """明示的な tax_rate=0 を送ると system_settings の値に上書きされないこと。"""
    from app.api.routes.invoices import create_invoice
    from app.models.invoice import InvoiceCreate

    inv_id = ObjectId()
    invoices_col = make_col(find_one={"_id": inv_id, "corporate_id": CORP_ID, "tax_rate": 0})
    invoices_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inv_id))
    sys_col = make_col(find_one={"key": "tax_rates", "value": {"standard": 10}})
    db = build_mock_db({
        "invoices": invoices_col,
        "audit_logs": make_col(),
        "system_settings": sys_col,
    })
    ctx = make_ctx(db=db)

    payload = InvoiceCreate(
        document_type="issued", invoice_number="INV-D3",
        tax_rate=0,  # 非課税として明示
        client_name="テスト", recipient_email="t@example.com",
        issue_date="2025-01-01", due_date="2025-01-31",
        subtotal=0, tax_amount=0, total_amount=0,
    )

    with (
        patch("app.api.routes.invoices.evaluate_approval_rules", AsyncMock(return_value=(None, []))),
        patch("app.api.routes.invoices.apply_journal_rules", AsyncMock(side_effect=lambda db, cid, docs, **kw: docs)),
    ):
        await create_invoice(payload=payload, ctx=ctx)

    inserted = invoices_col.insert_one.call_args[0][0]
    assert inserted["tax_rate"] == 0, f"tax_rate=0 は system_settings で上書きされないこと (got {inserted.get('tax_rate')})"


@pytest.mark.asyncio
async def test_receipt_batch_uses_system_tax_rate():
    """system_settings.standard=8 の場合、バッチ領収書登録のデフォルト税率が 8 になること。"""
    from app.api.routes.receipts import submit_receipts_batch
    from app.api.helpers import CorporateContext

    inv_id = ObjectId()
    receipts_col = MagicMock()
    receipts_col.insert_many = AsyncMock(return_value=MagicMock(inserted_ids=[inv_id]))
    sys_col = make_col(find_one={"key": "tax_rates", "value": {"standard": 8}})
    audit_col = make_col()
    approval_rules_col = MagicMock()
    approval_rules_col.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    ))

    db = build_mock_db({
        "receipts": receipts_col,
        "system_settings": sys_col,
        "audit_logs": audit_col,
        "approval_rules": approval_rules_col,
    })
    ctx = make_ctx(db=db)

    payload = {"receipts": [{"amount": 1000, "date": "2025-01-01", "payee": "テスト"}]}

    with (
        patch("app.api.routes.receipts.evaluate_approval_rules", AsyncMock(return_value=(None, []))),
        patch("app.api.routes.receipts.apply_journal_rules", AsyncMock(side_effect=lambda db, cid, docs: docs)),
    ):
        await submit_receipts_batch(payload=payload, ctx=ctx)

    inserted_docs = receipts_col.insert_many.call_args[0][0]
    assert inserted_docs[0]["tax_rate"] == 8, f"Expected 8, got {inserted_docs[0].get('tax_rate')}"


# =============================================================================
# ③ 既存データ保護テスト
# =============================================================================

@pytest.mark.asyncio
async def test_existing_invoice_tax_rate_unchanged_after_settings_update():
    """
    system_settings.standard を 8 に変更した後でも、
    tax_rate=10 で登録済みの請求書は GET で 10 を返すこと。
    既存ドキュメントは作成時の値で保存されており、参照時に再計算されない。
    """
    from app.api.routes.invoices import get_invoice

    inv_id = ObjectId()
    stored_doc = {
        "_id": inv_id,
        "corporate_id": CORP_ID,
        "tax_rate": 10,  # 作成時に standard=10 で登録済み
        "document_type": "issued",
        "invoice_number": "INV-E1",
        "client_name": "テスト",
        "approval_status": "draft",
        "is_deleted": False,
    }
    # system_settings は standard=8 に変更された後を想定
    sys_doc = {"key": "tax_rates", "value": {"standard": 8}}

    db = build_mock_db({
        "invoices": make_col(find_one=stored_doc),
        "system_settings": make_col(find_one=sys_doc),
        "approval_events": make_col(find_data=[]),
    })
    ctx = make_ctx(db=db)

    with patch("app.api.routes.invoices.enrich_with_approval_history",
               AsyncMock(side_effect=lambda db, doc, *a, **kw: doc)):
        result = await get_invoice(invoice_id=str(inv_id), ctx=ctx)

    assert result["tax_rate"] == 10, (
        f"既存請求書の tax_rate は system_settings 変更後も 10 のままであること (got {result.get('tax_rate')})"
    )


@pytest.mark.asyncio
async def test_existing_receipt_tax_rate_unchanged():
    """
    system_settings.standard を 8 に変更した後でも、
    tax_rate=10 で登録済みの領収書は GET で 10 を返すこと。
    """
    from app.api.routes.receipts import get_receipt

    rec_id = ObjectId()
    stored_doc = {
        "_id": rec_id,
        "corporate_id": CORP_ID,
        "tax_rate": 10,
        "amount": 1000,
        "payee": "テスト",
        "date": "2025-01-01",
        "approval_status": "draft",
        "is_deleted": False,
    }
    sys_doc = {"key": "tax_rates", "value": {"standard": 8}}

    db = build_mock_db({
        "receipts": make_col(find_one=stored_doc),
        "system_settings": make_col(find_one=sys_doc),
        "approval_events": make_col(find_data=[]),
    })
    ctx = make_ctx(db=db)

    with patch("app.api.routes.receipts.enrich_with_approval_history",
               AsyncMock(side_effect=lambda db, doc, *a, **kw: doc)):
        result = await get_receipt(receipt_id=str(rec_id), ctx=ctx)

    assert result["tax_rate"] == 10, (
        f"既存領収書の tax_rate は system_settings 変更後も 10 のままであること (got {result.get('tax_rate')})"
    )


@pytest.mark.asyncio
async def test_invoice_with_explicit_rate_preserved():
    """
    tax_rate=8 で明示登録した請求書は、
    system_settings.standard=10 に変更した後も 8 を返すこと。
    """
    from app.api.routes.invoices import get_invoice

    inv_id = ObjectId()
    stored_doc = {
        "_id": inv_id,
        "corporate_id": CORP_ID,
        "tax_rate": 8,  # 軽減税率で明示登録
        "document_type": "issued",
        "invoice_number": "INV-E3",
        "client_name": "テスト",
        "approval_status": "approved",
        "is_deleted": False,
    }
    sys_doc = {"key": "tax_rates", "value": {"standard": 10}}  # standard=10 でも

    db = build_mock_db({
        "invoices": make_col(find_one=stored_doc),
        "system_settings": make_col(find_one=sys_doc),
        "approval_events": make_col(find_data=[]),
    })
    ctx = make_ctx(db=db)

    with patch("app.api.routes.invoices.enrich_with_approval_history",
               AsyncMock(side_effect=lambda db, doc, *a, **kw: doc)):
        result = await get_invoice(invoice_id=str(inv_id), ctx=ctx)

    assert result["tax_rate"] == 8, (
        f"明示的に登録した tax_rate=8 は system_settings=10 の後も 8 のままであること (got {result.get('tax_rate')})"
    )


# =============================================================================
# ④ フォールバックチェーンテスト
# =============================================================================

@pytest.mark.asyncio
async def test_tax_rate_fallback_chain_line_items():
    """
    top-level tax_rate がなく line_items[0].tax_rate がある場合に
    line_items の値（8）が請求書の tax_rate として保存されること。
    フォールバック優先度: explicit > line_items[0] > system_settings > DEFAULT
    """
    from app.api.routes.invoices import create_invoice
    from app.models.invoice import InvoiceCreate

    inv_id = ObjectId()
    invoices_col = make_col(find_one={"_id": inv_id, "corporate_id": CORP_ID, "tax_rate": 8})
    invoices_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inv_id))
    sys_col = make_col(find_one={"key": "tax_rates", "value": {"standard": 10}})
    db = build_mock_db({
        "invoices": invoices_col,
        "audit_logs": make_col(),
        "system_settings": sys_col,
    })
    ctx = make_ctx(db=db)

    payload = InvoiceCreate(
        document_type="issued", invoice_number="INV-F1",
        # tax_rate 未指定 → None
        client_name="テスト", recipient_email="t@example.com",
        issue_date="2025-01-01", due_date="2025-01-31",
        subtotal=10000, tax_amount=800, total_amount=10800,
        line_items=[{"description": "食品", "category": "仕入", "amount": 10000, "tax_rate": 8}],
    )
    assert payload.tax_rate is None  # top-level は None

    with (
        patch("app.api.routes.invoices.evaluate_approval_rules", AsyncMock(return_value=(None, []))),
        patch("app.api.routes.invoices.apply_journal_rules", AsyncMock(side_effect=lambda db, cid, docs, **kw: docs)),
    ):
        await create_invoice(payload=payload, ctx=ctx)

    inserted = invoices_col.insert_one.call_args[0][0]
    assert inserted["tax_rate"] == 8, (
        f"line_items[0].tax_rate=8 が top-level tax_rate に使われること (got {inserted.get('tax_rate')})"
    )


@pytest.mark.asyncio
async def test_tax_rate_fallback_chain_system_settings():
    """
    top-level tax_rate も line_items もない場合に
    system_settings.standard（8）が使われること。
    """
    from app.api.routes.invoices import create_invoice
    from app.models.invoice import InvoiceCreate

    inv_id = ObjectId()
    invoices_col = make_col(find_one={"_id": inv_id, "corporate_id": CORP_ID, "tax_rate": 8})
    invoices_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inv_id))
    sys_col = make_col(find_one={"key": "tax_rates", "value": {"standard": 8}})
    db = build_mock_db({
        "invoices": invoices_col,
        "audit_logs": make_col(),
        "system_settings": sys_col,
    })
    ctx = make_ctx(db=db)

    payload = InvoiceCreate(
        document_type="issued", invoice_number="INV-F2",
        # tax_rate 未指定、line_items なし
        client_name="テスト", recipient_email="t@example.com",
        issue_date="2025-01-01", due_date="2025-01-31",
        subtotal=0, tax_amount=0, total_amount=0,
    )

    with (
        patch("app.api.routes.invoices.evaluate_approval_rules", AsyncMock(return_value=(None, []))),
        patch("app.api.routes.invoices.apply_journal_rules", AsyncMock(side_effect=lambda db, cid, docs, **kw: docs)),
    ):
        await create_invoice(payload=payload, ctx=ctx)

    inserted = invoices_col.insert_one.call_args[0][0]
    assert inserted["tax_rate"] == 8, (
        f"system_settings.standard=8 がフォールバックとして使われること (got {inserted.get('tax_rate')})"
    )


@pytest.mark.asyncio
async def test_tax_rate_fallback_final_default():
    """
    top-level tax_rate も line_items も system_settings も未設定の場合に
    DEFAULT_TAX_RATES["standard"]（10）が最終フォールバックとして使われること。
    """
    from app.api.routes.invoices import create_invoice
    from app.models.invoice import InvoiceCreate
    from app.services.alert_service import DEFAULT_TAX_RATES

    inv_id = ObjectId()
    invoices_col = make_col(find_one={"_id": inv_id, "corporate_id": CORP_ID})
    invoices_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inv_id))
    sys_col = make_col(find_one=None)  # system_settings 未設定
    db = build_mock_db({
        "invoices": invoices_col,
        "audit_logs": make_col(),
        "system_settings": sys_col,
    })
    ctx = make_ctx(db=db)

    payload = InvoiceCreate(
        document_type="issued", invoice_number="INV-F3",
        # tax_rate 未指定、line_items なし、system_settings も None
        client_name="テスト", recipient_email="t@example.com",
        issue_date="2025-01-01", due_date="2025-01-31",
        subtotal=0, tax_amount=0, total_amount=0,
    )

    with (
        patch("app.api.routes.invoices.evaluate_approval_rules", AsyncMock(return_value=(None, []))),
        patch("app.api.routes.invoices.apply_journal_rules", AsyncMock(side_effect=lambda db, cid, docs, **kw: docs)),
    ):
        await create_invoice(payload=payload, ctx=ctx)

    inserted = invoices_col.insert_one.call_args[0][0]
    assert inserted["tax_rate"] == DEFAULT_TAX_RATES["standard"], (
        f"最終フォールバックは DEFAULT_TAX_RATES['standard']={DEFAULT_TAX_RATES['standard']} であること "
        f"(got {inserted.get('tax_rate')})"
    )
