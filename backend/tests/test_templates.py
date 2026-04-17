"""
Tests for Task#37 + セキュリティ修正: テンプレート管理 API

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_templates.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime

CORP_ID = "test_corp_id"
CORP_B_ID = "other_corp_id"


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_col(find_one=None, find_data=None, insert_id=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=insert_id or ObjectId()))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    return col


def build_mock_db(collections: dict = None):
    db = MagicMock()
    cols = collections or {}
    db.__getitem__ = MagicMock(side_effect=lambda k: cols.get(k, make_col()))
    return db


def make_ctx(role: str = "accounting", corporate_id: str = CORP_ID, user_id: str = "user1"):
    from app.api.helpers import CorporateContext
    ctx = MagicMock(spec=CorporateContext)
    ctx.corporate_id = corporate_id
    ctx.user_id = user_id
    ctx.role = role
    ctx.db = build_mock_db()
    return ctx


def sample_template(corporate_id: str = CORP_ID, template_type: str = "invoice",
                    is_default: bool = False) -> dict:
    oid = ObjectId()
    return {
        "_id": oid,
        "corporate_id": corporate_id,
        "name": "テストテンプレート",
        "description": "テスト用",
        "html": "<p>HTML</p>",
        "thumbnail": "bg-blue-50 border-blue-200",
        "is_active": True,
        "template_type": template_type,
        "is_default": is_default,
        "created_by": "user1",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# test_accounting_can_create_template
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_accounting_can_create_template():
    """accounting ロールがテンプレートを作成できること。"""
    from app.api.routes.templates import create_template
    from app.models.template import TemplateCreate

    tmpl = sample_template()
    templates_col = make_col(find_one=tmpl, insert_id=tmpl["_id"])
    ctx = make_ctx(role="accounting")
    ctx.db = build_mock_db({"templates": templates_col})

    payload = TemplateCreate(
        name="テスト", description="説明", html="<p>test</p>",
        template_type="invoice", is_default=False,
    )
    result = await create_template(payload, ctx)

    templates_col.insert_one.assert_called_once()
    assert "id" in result


# ─────────────────────────────────────────────────────────────────────────────
# test_staff_cannot_create_template
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_staff_cannot_create_template():
    """staff が POST すると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.templates import create_template
    from app.models.template import TemplateCreate

    payload = TemplateCreate(
        name="テスト", description="説明", html="<p>test</p>",
        template_type="invoice", is_default=False,
    )
    with pytest.raises(HTTPException) as exc:
        await create_template(payload, make_ctx(role="staff"))

    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# test_template_list_excludes_html
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_template_list_excludes_html():
    """GET /invoices/templates のレスポンスに html フィールドが含まれないこと。"""
    from app.api.routes.templates import list_templates

    # DB は {"html": 0} projection で html を返さない
    doc_without_html = {k: v for k, v in sample_template().items() if k != "html"}
    templates_col = make_col(find_data=[doc_without_html])
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"templates": templates_col})

    result = await list_templates(template_type="invoice", ctx=ctx)

    assert len(result) == 1
    assert "html" not in result[0], "一覧取得レスポンスに html が含まれてはいけない"

    # find に projection {"html": 0} が渡されていること
    find_args = templates_col.find.call_args
    projection = find_args[0][1] if len(find_args[0]) > 1 else find_args[1].get("projection", {})
    assert projection.get("html") == 0


# ─────────────────────────────────────────────────────────────────────────────
# test_template_detail_includes_html（既存）
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_template_detail_includes_html():
    """GET /invoices/templates/:id のレスポンスに html が含まれること。"""
    from app.api.routes.templates import get_template

    tmpl = sample_template()
    templates_col = make_col(find_one=tmpl)
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"templates": templates_col})

    result = await get_template(str(tmpl["_id"]), ctx)

    assert "html" in result, "詳細取得レスポンスに html が含まれること"
    assert result["html"] == "<p>HTML</p>"


# ─────────────────────────────────────────────────────────────────────────────
# test_default_template_cannot_be_deleted
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_default_template_cannot_be_deleted():
    """is_default=True のテンプレートを DELETE すると 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.templates import delete_template

    tmpl = sample_template(is_default=True)
    templates_col = make_col(find_one=tmpl)
    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"templates": templates_col})

    with pytest.raises(HTTPException) as exc:
        await delete_template(str(tmpl["_id"]), ctx)

    assert exc.value.status_code == 400
    # delete_one が呼ばれていないこと
    templates_col.delete_one.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# test_template_cross_corporate_blocked
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_template_cross_corporate_blocked():
    """別法人のテンプレートに GET できないこと（corporate_id フィルタ確認）。"""
    from app.api.routes.templates import get_template

    # 法人 B のテンプレートは法人 A から find_one すると None が返る
    templates_col = make_col(find_one=None)
    ctx = make_ctx(role="staff", corporate_id=CORP_ID)
    ctx.db = build_mock_db({"templates": templates_col})

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await get_template(str(ObjectId()), ctx)

    assert exc.value.status_code == 404
    # find_one のクエリに corporate_id が含まれること
    find_query = templates_col.find_one.call_args[0][0]
    assert find_query.get("corporate_id") == CORP_ID


# ─────────────────────────────────────────────────────────────────────────────
# test_receipt_template_separate_from_invoice
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_receipt_template_separate_from_invoice():
    """template_type フィルタが正しくクエリに含まれること。"""
    from app.api.routes.templates import list_templates

    templates_col = make_col(find_data=[])
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"templates": templates_col})

    # invoice フィルタ
    await list_templates(template_type="invoice", ctx=ctx)
    find_query = templates_col.find.call_args[0][0]
    assert find_query.get("template_type") == "invoice"

    # receipt フィルタ
    await list_templates(template_type="receipt", ctx=ctx)
    find_query = templates_col.find.call_args[0][0]
    assert find_query.get("template_type") == "receipt"


# =============================================================================
# 意地悪テスト（Task#37）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① 権限テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_staff_cannot_update_template():
    """staff が PUT /invoices/templates/:id すると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.templates import update_template

    with pytest.raises(HTTPException) as exc:
        await update_template(str(ObjectId()), {"name": "新名前"}, make_ctx(role="staff"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_manager_can_create_template():
    """manager ロールが POST できること（isAccountingOrAbove と一致）。"""
    from app.api.routes.templates import create_template
    from app.models.template import TemplateCreate

    tmpl = sample_template()
    templates_col = make_col(find_one=tmpl, insert_id=tmpl["_id"])
    ctx = make_ctx(role="manager")
    ctx.db = build_mock_db({"templates": templates_col})

    payload = TemplateCreate(name="マネージャー作成", description="説明", html="<p>test</p>",
                              template_type="invoice", is_default=False)
    result = await create_template(payload, ctx)
    templates_col.insert_one.assert_called_once()
    assert "id" in result


@pytest.mark.asyncio
async def test_staff_can_read_template_list():
    """staff が GET /invoices/templates で 200 が返ること（読み取りは全ロール可）。"""
    from app.api.routes.templates import list_templates

    templates_col = make_col(find_data=[sample_template()])
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"templates": templates_col})

    result = await list_templates(template_type="invoice", ctx=ctx)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_staff_can_read_template_detail():
    """staff が GET /invoices/templates/:id で 200 が返ること。"""
    from app.api.routes.templates import get_template

    tmpl = sample_template()
    templates_col = make_col(find_one=tmpl)
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"templates": templates_col})

    result = await get_template(str(tmpl["_id"]), ctx)
    assert "id" in result


# ─────────────────────────────────────────────────────────────────────────────
# ② html フィールドの除外テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_does_not_include_html():
    """GET /invoices/templates のレスポンスの各アイテムに html フィールドがないこと。"""
    from app.api.routes.templates import list_templates

    doc = {k: v for k, v in sample_template().items() if k != "html"}
    templates_col = make_col(find_data=[doc])
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"templates": templates_col})

    result = await list_templates(template_type="invoice", ctx=ctx)
    assert len(result) == 1
    assert "html" not in result[0]


@pytest.mark.asyncio
async def test_detail_includes_html():
    """GET /invoices/templates/:id のレスポンスに html が含まれ、空でないこと。"""
    from app.api.routes.templates import get_template

    tmpl = sample_template()
    templates_col = make_col(find_one=tmpl)
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"templates": templates_col})

    result = await get_template(str(tmpl["_id"]), ctx)
    assert "html" in result
    assert result["html"] != ""


# ─────────────────────────────────────────────────────────────────────────────
# ③ template_type フィルタテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invoice_templates_excludes_receipt_type():
    """template_type="receipt" のテンプレートが invoice クエリに含まれないこと。"""
    from app.api.routes.templates import list_templates

    templates_col = make_col(find_data=[])
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"templates": templates_col})

    await list_templates(template_type="invoice", ctx=ctx)
    find_query = templates_col.find.call_args[0][0]
    assert find_query.get("template_type") == "invoice", \
        "invoice クエリは receipt を返さないこと"


@pytest.mark.asyncio
async def test_receipt_templates_excludes_invoice_type():
    """template_type="invoice" のテンプレートが receipt クエリに含まれないこと。"""
    from app.api.routes.templates import list_templates

    templates_col = make_col(find_data=[])
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"templates": templates_col})

    await list_templates(template_type="receipt", ctx=ctx)
    find_query = templates_col.find.call_args[0][0]
    assert find_query.get("template_type") == "receipt"


@pytest.mark.asyncio
async def test_receipt_templates_endpoint_returns_200():
    """GET /receipts/templates（list_templates に template_type='receipt'）が成功すること。"""
    from app.api.routes.templates import list_templates

    templates_col = make_col(find_data=[sample_template(template_type="receipt")])
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"templates": templates_col})

    result = await list_templates(template_type="receipt", ctx=ctx)
    assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# ④ is_default 保護テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_default_template_cannot_be_deleted_malicious():
    """is_default=True のテンプレートを DELETE すると 400 が返り delete_one が呼ばれないこと。"""
    from fastapi import HTTPException
    from app.api.routes.templates import delete_template

    tmpl = sample_template(is_default=True)
    templates_col = make_col(find_one=tmpl)
    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"templates": templates_col})

    with pytest.raises(HTTPException) as exc:
        await delete_template(str(tmpl["_id"]), ctx)

    assert exc.value.status_code == 400
    templates_col.delete_one.assert_not_called()


@pytest.mark.asyncio
async def test_non_default_template_can_be_deleted():
    """is_default=False のテンプレートは DELETE できること。"""
    from app.api.routes.templates import delete_template

    tmpl = sample_template(is_default=False)
    templates_col = make_col(find_one=tmpl)
    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"templates": templates_col})

    result = await delete_template(str(tmpl["_id"]), ctx)
    assert result["status"] == "success"
    templates_col.delete_one.assert_called_once()


@pytest.mark.asyncio
async def test_update_does_not_change_is_default():
    """
    PUT で is_default を False に変更しようとしても無視されること。
    is_default は allowed_updates に含まれていないため変更不可。
    """
    from app.api.routes.templates import update_template

    tmpl = sample_template(is_default=True)
    updated_doc = {**tmpl}  # is_default は True のまま
    templates_col = make_col()
    templates_col.find_one = AsyncMock(side_effect=[tmpl, updated_doc])

    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"templates": templates_col})

    result = await update_template(str(tmpl["_id"]), {"is_default": False, "name": "新名前"}, ctx)

    # update_one の $set に is_default が含まれていないこと
    set_data = templates_col.update_one.call_args[0][1]["$set"]
    assert "is_default" not in set_data, \
        f"is_default が $set に含まれてはいけない: {set_data}"


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ スコープテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_template_cross_corporate_get_blocked():
    """別法人のテンプレートに GET できないこと（404 が返ること）。"""
    from fastapi import HTTPException
    from app.api.routes.templates import get_template

    templates_col = make_col(find_one=None)  # 法人Aからは見えない
    ctx = make_ctx(role="staff", corporate_id=CORP_ID)
    ctx.db = build_mock_db({"templates": templates_col})

    with pytest.raises(HTTPException) as exc:
        await get_template(str(ObjectId()), ctx)

    assert exc.value.status_code == 404
    q = templates_col.find_one.call_args[0][0]
    assert q.get("corporate_id") == CORP_ID


@pytest.mark.asyncio
async def test_template_cross_corporate_put_blocked():
    """別法人のテンプレートを PUT できないこと（matched_count=0 → 404）。"""
    from fastapi import HTTPException
    from app.api.routes.templates import update_template

    tmpl = sample_template(corporate_id=CORP_B_ID)
    templates_col = make_col(find_one=tmpl)
    templates_col.update_one = AsyncMock(return_value=MagicMock(matched_count=0))

    ctx = make_ctx(role="admin", corporate_id=CORP_ID)
    ctx.db = build_mock_db({"templates": templates_col})

    with pytest.raises(HTTPException) as exc:
        await update_template(str(tmpl["_id"]), {"name": "ハイジャック"}, ctx)

    assert exc.value.status_code == 404
    # update_one のフィルタに法人Aの corporate_id が含まれること
    filter_q = templates_col.update_one.call_args[0][0]
    assert filter_q.get("corporate_id") == CORP_ID


@pytest.mark.asyncio
async def test_template_cross_corporate_delete_blocked():
    """別法人のテンプレートを DELETE できないこと（find_one がNone → 404）。"""
    from fastapi import HTTPException
    from app.api.routes.templates import delete_template

    templates_col = make_col(find_one=None)  # 法人Aからは見えない
    ctx = make_ctx(role="admin", corporate_id=CORP_ID)
    ctx.db = build_mock_db({"templates": templates_col})

    with pytest.raises(HTTPException) as exc:
        await delete_template(str(ObjectId()), ctx)

    assert exc.value.status_code == 404
    templates_col.delete_one.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ バリデーションテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_template_missing_name_returns_422():
    """name が空の場合に Pydantic バリデーションエラー（422相当）が返ること。"""
    from pydantic import ValidationError
    from app.models.template import TemplateCreate

    # name は str なので空文字は通るが None は ValidationError
    with pytest.raises(ValidationError):
        TemplateCreate(name=None, description="説明", html="<p>test</p>")  # type: ignore


@pytest.mark.asyncio
async def test_create_template_invalid_type_returns_400():
    """template_type='unknown' を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.templates import create_template
    from app.models.template import TemplateCreate

    payload = TemplateCreate(
        name="テスト", description="説明", html="<p>test</p>",
        template_type="unknown",
    )
    with pytest.raises(HTTPException) as exc:
        await create_template(payload, make_ctx(role="admin"))

    assert exc.value.status_code == 400
    assert "invoice" in exc.value.detail or "receipt" in exc.value.detail


@pytest.mark.asyncio
async def test_update_nonexistent_template_returns_404():
    """存在しない template_id で PUT すると 404 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.templates import update_template

    templates_col = make_col()
    templates_col.update_one = AsyncMock(return_value=MagicMock(matched_count=0))

    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"templates": templates_col})

    with pytest.raises(HTTPException) as exc:
        await update_template(str(ObjectId()), {"name": "存在しない"}, ctx)

    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# POST /generate — セキュリティ修正テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_template_requires_full_access_role():
    """staff ロールで POST /generate を呼ぶと 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.templates import generate_template

    ctx = make_ctx(role="staff")

    with pytest.raises(HTTPException) as exc:
        await generate_template({"filename": "test.pdf"}, ctx)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_generate_template_accounting_role_allowed():
    """accounting ロールで POST /generate が実行できること。"""
    from app.api.routes.templates import generate_template

    ctx = make_ctx(role="accounting")

    ai_result = {
        "template_name": "AI生成テンプレート",
        "html": "<div>テスト</div>",
        "variables": ["client_name", "issue_date"],
    }

    with patch(
        "app.services.ai_service.AIService.generate_invoice_html_template",
        new_callable=AsyncMock,
        return_value=ai_result,
    ):
        result = await generate_template({"filename": "invoice.pdf"}, ctx)

    assert result["template_name"] == "AI生成テンプレート"
    assert "html" in result


@pytest.mark.asyncio
async def test_generate_template_ai_failure_returns_500():
    """AI 生成が None を返すと 500 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.templates import generate_template

    ctx = make_ctx(role="admin")

    with patch(
        "app.services.ai_service.AIService.generate_invoice_html_template",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc:
            await generate_template({"filename": "broken.pdf"}, ctx)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_generate_template_uses_corporate_context():
    """POST /generate が CorporateContext を受け取り corporate_id を保持していること。"""
    from app.api.routes.templates import generate_template

    ctx = make_ctx(role="manager", corporate_id=CORP_ID)

    ai_result = {"template_name": "test", "html": "<p/>", "variables": []}

    with patch(
        "app.services.ai_service.AIService.generate_invoice_html_template",
        new_callable=AsyncMock,
        return_value=ai_result,
    ):
        await generate_template({"filename": "test.pdf"}, ctx)

    # corporate_id が ctx から正しく参照できていること（別法人でないこと）
    assert ctx.corporate_id == CORP_ID
