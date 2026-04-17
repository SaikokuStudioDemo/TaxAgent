"""
Tests for Task#35・#36: 予算管理 + 予算対比レポート

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_budgets.py -v
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


def make_ctx(role: str = "admin", corporate_id: str = CORP_ID, user_id: str = "user1"):
    """CorporateContext のモック。"""
    from app.api.helpers import CorporateContext
    ctx = MagicMock(spec=CorporateContext)
    ctx.corporate_id = corporate_id
    ctx.user_id = user_id
    ctx.role = role
    ctx.db = build_mock_db()
    return ctx


def sample_budget(corporate_id: str = CORP_ID, fiscal_year: int = 2025, month: int = 4,
                  account_subject: str = "交通費", amount: int = 50000) -> dict:
    oid = ObjectId()
    return {
        "_id": oid,
        "corporate_id": corporate_id,
        "fiscal_year": fiscal_year,
        "month": month,
        "account_subject": account_subject,
        "amount": amount,
        "created_by": "user1",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# test_admin_can_create_budget
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_can_create_budget():
    """管理者が予算を登録できること。"""
    from app.api.routes.budgets import create_budget

    budget_doc = sample_budget()
    budgets_col = make_col(find_one=budget_doc, insert_id=budget_doc["_id"])
    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"budgets": budgets_col})

    result = await create_budget(
        {"fiscal_year": 2025, "month": 4, "account_subject": "交通費", "amount": 50000},
        ctx,
    )

    budgets_col.insert_one.assert_called_once()
    assert result["account_subject"] == "交通費"


# ─────────────────────────────────────────────────────────────────────────────
# test_staff_cannot_create_budget
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_staff_cannot_create_budget():
    """staff が POST すると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import create_budget

    ctx = make_ctx(role="staff")

    with pytest.raises(HTTPException) as exc:
        await create_budget(
            {"fiscal_year": 2025, "month": 4, "account_subject": "交通費", "amount": 50000},
            ctx,
        )
    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# test_budget_list_filtered_by_year
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_budget_list_filtered_by_year():
    """fiscal_year で絞り込めること（クエリに fiscal_year が含まれること）。"""
    from app.api.routes.budgets import list_budgets

    budgets_col = make_col(find_data=[sample_budget()])
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"budgets": budgets_col})

    result = await list_budgets(fiscal_year=2025, month=None, ctx=ctx)

    find_query = budgets_col.find.call_args[0][0]
    assert find_query.get("fiscal_year") == 2025


# ─────────────────────────────────────────────────────────────────────────────
# test_budget_update_changes_amount
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_budget_update_changes_amount():
    """PUT で amount が更新されること。"""
    from app.api.routes.budgets import update_budget

    budget_doc = sample_budget()
    updated_doc = {**budget_doc, "amount": 99000}
    budgets_col = make_col(find_one=updated_doc)
    budgets_col.find_one = AsyncMock(side_effect=[budget_doc, updated_doc])

    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"budgets": budgets_col})

    result = await update_budget(str(budget_doc["_id"]), {"amount": 99000}, ctx)

    budgets_col.update_one.assert_called_once()
    update_arg = budgets_col.update_one.call_args[0][1]
    assert update_arg["$set"]["amount"] == 99000


# ─────────────────────────────────────────────────────────────────────────────
# test_budget_delete_removes_record
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_budget_delete_removes_record():
    """DELETE で削除されること。"""
    from app.api.routes.budgets import delete_budget

    budget_doc = sample_budget()
    budgets_col = make_col()

    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"budgets": budgets_col})

    result = await delete_budget(str(budget_doc["_id"]), ctx)

    budgets_col.delete_one.assert_called_once()
    assert result["status"] == "deleted"


# ─────────────────────────────────────────────────────────────────────────────
# test_budget_delete_nonexistent_returns_404
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_budget_delete_nonexistent_returns_404():
    """存在しない budget_id で 404 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import delete_budget

    budgets_col = make_col()
    budgets_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))

    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"budgets": budgets_col})

    with pytest.raises(HTTPException) as exc:
        await delete_budget(str(ObjectId()), ctx)

    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# test_report_includes_actual_without_budget
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_includes_actual_without_budget():
    """予算未登録でも実績が含まれること・has_budget=False が返ること。"""
    from app.services.budget_report_service import get_budget_report

    receipt = {
        "_id": ObjectId(), "corporate_id": CORP_ID, "category": "交通費",
        "amount": 3000, "approval_status": "approved", "fiscal_period": "2025-04",
    }
    mock_db = build_mock_db({
        "budgets": make_col(find_data=[]),
        "receipts": make_col(find_data=[receipt]),
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        result = await get_budget_report(CORP_ID, fiscal_year=2025, month=4)

    assert result["has_budget"] is False
    assert len(result["rows"]) == 1
    assert result["rows"][0]["actual_amount"] == 3000


# ─────────────────────────────────────────────────────────────────────────────
# test_report_calculates_difference_correctly
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_calculates_difference_correctly():
    """予算100・実績80 → 差額20・達成率80% が返ること。"""
    from app.services.budget_report_service import get_budget_report

    budget = sample_budget(amount=100, account_subject="消耗品費")
    receipt = {
        "_id": ObjectId(), "corporate_id": CORP_ID, "category": "消耗品費",
        "amount": 80, "approval_status": "approved", "fiscal_period": "2025-04",
    }
    mock_db = build_mock_db({
        "budgets": make_col(find_data=[budget]),
        "receipts": make_col(find_data=[receipt]),
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        result = await get_budget_report(CORP_ID, fiscal_year=2025, month=4)

    row = result["rows"][0]
    assert row["budget_amount"] == 100
    assert row["actual_amount"] == 80
    assert row["difference"] == 20
    assert row["achievement_rate"] == 80.0


# ─────────────────────────────────────────────────────────────────────────────
# test_report_zero_budget_rate_is_null
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_zero_budget_rate_is_null():
    """予算0の勘定科目の achievement_rate が None であること（ゼロ除算なし）。"""
    from app.services.budget_report_service import get_budget_report

    budget = sample_budget(amount=0, account_subject="接待費")
    receipt = {
        "_id": ObjectId(), "corporate_id": CORP_ID, "category": "接待費",
        "amount": 5000, "approval_status": "approved", "fiscal_period": "2025-04",
    }
    mock_db = build_mock_db({
        "budgets": make_col(find_data=[budget]),
        "receipts": make_col(find_data=[receipt]),
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        result = await get_budget_report(CORP_ID, fiscal_year=2025, month=4)

    row = result["rows"][0]
    assert row["achievement_rate"] is None, "ゼロ除算で None が返ること"


# ─────────────────────────────────────────────────────────────────────────────
# test_report_cross_corporate_blocked
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_cross_corporate_blocked():
    """別法人の予算・実績が含まれないこと（クエリに corporate_id フィルタが含まれること）。"""
    from app.services.budget_report_service import get_budget_report

    budgets_col = make_col(find_data=[])
    receipts_col = make_col(find_data=[])
    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({
        "budgets": budgets_col,
        "receipts": receipts_col,
        "invoices": invoices_col,
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        await get_budget_report(CORP_ID, fiscal_year=2025, month=4)

    for col_name, col in [("budgets", budgets_col), ("receipts", receipts_col), ("invoices", invoices_col)]:
        q = col.find.call_args[0][0]
        assert q.get("corporate_id") == CORP_ID, f"{col_name} のクエリに corporate_id フィルタが含まれること"


# ─────────────────────────────────────────────────────────────────────────────
# test_manager_can_view_report  （① test_approver → test_manager に変更）
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manager_can_view_report():
    """manager ロールで GET /budgets/report が 200 を返すこと。"""
    from app.api.routes.budgets import get_report

    ctx = make_ctx(role="manager")
    ctx.db = build_mock_db({"permission_settings": make_col(find_one=None)})

    with patch("app.services.budget_report_service.get_budget_report",
               new_callable=AsyncMock, return_value={"rows": [], "has_budget": False, "total": {}}):
        result = await get_report(fiscal_year=2025, month=None, ctx=ctx)

    assert "rows" in result


# ─────────────────────────────────────────────────────────────────────────────
# test_staff_cannot_view_report
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_staff_cannot_view_report():
    """staff ロールで GET /budgets/report が 403 を返すこと。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import get_report

    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"permission_settings": make_col(find_one=None)})

    with pytest.raises(HTTPException) as exc:
        await get_report(fiscal_year=2025, month=None, ctx=ctx)

    assert exc.value.status_code == 403


# =============================================================================
# 意地悪テスト（Task#35・#36）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① 予算 CRUD の権限テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_accounting_cannot_create_budget():
    """accounting ロールが POST /budgets すると 403 が返ること（admin のみ）。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import create_budget

    with pytest.raises(HTTPException) as exc:
        await create_budget(
            {"fiscal_year": 2025, "month": 4, "account_subject": "交通費", "amount": 1000},
            make_ctx(role="accounting"),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_manager_cannot_create_budget():
    """manager ロールが POST /budgets すると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import create_budget

    with pytest.raises(HTTPException) as exc:
        await create_budget(
            {"fiscal_year": 2025, "month": 4, "account_subject": "交通費", "amount": 1000},
            make_ctx(role="manager"),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_update_budget():
    """admin が PUT /budgets/:id で更新できること。"""
    from app.api.routes.budgets import update_budget

    budget_doc = sample_budget()
    updated_doc = {**budget_doc, "amount": 12000}
    budgets_col = make_col()
    budgets_col.find_one = AsyncMock(side_effect=[budget_doc, updated_doc])

    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"budgets": budgets_col})

    await update_budget(str(budget_doc["_id"]), {"amount": 12000}, ctx)
    budgets_col.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_staff_cannot_delete_budget():
    """staff が DELETE /budgets/:id すると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import delete_budget

    with pytest.raises(HTTPException) as exc:
        await delete_budget(str(ObjectId()), make_ctx(role="staff"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_all_roles_can_list_budgets():
    """staff ロールでも GET /budgets が成功すること（全ロール参照可）。"""
    from app.api.routes.budgets import list_budgets

    budgets_col = make_col(find_data=[sample_budget()])
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"budgets": budgets_col})

    result = await list_budgets(fiscal_year=None, month=None, ctx=ctx)
    assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# ② バリデーションテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_budget_missing_required_fields():
    """fiscal_year・month・account_subject のいずれかが欠けると 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import create_budget

    ctx = make_ctx(role="admin")
    for bad_payload in [
        {"month": 4, "account_subject": "交通費", "amount": 0},
        {"fiscal_year": 2025, "account_subject": "交通費", "amount": 0},
        {"fiscal_year": 2025, "month": 4, "amount": 0},
    ]:
        with pytest.raises(HTTPException) as exc:
            await create_budget(bad_payload, ctx)
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_budget_invalid_month_zero():
    """month=0 で 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import create_budget

    with pytest.raises(HTTPException) as exc:
        await create_budget(
            {"fiscal_year": 2025, "month": 0, "account_subject": "交通費", "amount": 0},
            make_ctx(role="admin"),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_budget_invalid_month_13():
    """month=13 で 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import create_budget

    with pytest.raises(HTTPException) as exc:
        await create_budget(
            {"fiscal_year": 2025, "month": 13, "account_subject": "交通費", "amount": 0},
            make_ctx(role="admin"),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_budget_invalid_month_exactly_1():
    """month=1 は有効であること（境界値・下限）。"""
    from app.api.routes.budgets import create_budget

    budget_doc = sample_budget(month=1)
    budgets_col = make_col(find_one=budget_doc, insert_id=budget_doc["_id"])
    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"budgets": budgets_col})

    result = await create_budget(
        {"fiscal_year": 2025, "month": 1, "account_subject": "交通費", "amount": 0},
        ctx,
    )
    assert result["month"] == 1


@pytest.mark.asyncio
async def test_create_budget_invalid_month_exactly_12():
    """month=12 は有効であること（境界値・上限）。"""
    from app.api.routes.budgets import create_budget

    budget_doc = sample_budget(month=12)
    budgets_col = make_col(find_one=budget_doc, insert_id=budget_doc["_id"])
    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"budgets": budgets_col})

    result = await create_budget(
        {"fiscal_year": 2025, "month": 12, "account_subject": "交通費", "amount": 0},
        ctx,
    )
    assert result["month"] == 12


@pytest.mark.asyncio
async def test_create_budget_bool_amount_rejected():
    """amount=True を渡すと 400 が返ること（bool は int のサブクラスのため先行チェック必要）。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import create_budget

    with pytest.raises(HTTPException) as exc:
        await create_budget(
            {"fiscal_year": 2025, "month": 4, "account_subject": "交通費", "amount": True},
            make_ctx(role="admin"),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_budget_negative_amount_rejected():
    """amount=-1 で 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import create_budget

    with pytest.raises(HTTPException) as exc:
        await create_budget(
            {"fiscal_year": 2025, "month": 4, "account_subject": "交通費", "amount": -1},
            make_ctx(role="admin"),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_budget_zero_amount_accepted():
    """amount=0 は有効であること（0=無予算の表現）。"""
    from app.api.routes.budgets import create_budget

    budget_doc = sample_budget(amount=0)
    budgets_col = make_col(find_one=budget_doc, insert_id=budget_doc["_id"])
    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"budgets": budgets_col})

    result = await create_budget(
        {"fiscal_year": 2025, "month": 4, "account_subject": "交通費", "amount": 0},
        ctx,
    )
    assert result["amount"] == 0


@pytest.mark.asyncio
async def test_update_budget_invalid_id():
    """PUT /budgets/invalid-id で 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import update_budget

    ctx = make_ctx(role="admin")
    ctx.db = build_mock_db({"budgets": make_col()})

    with pytest.raises(HTTPException) as exc:
        await update_budget("invalid-id", {"amount": 1000}, ctx)
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# ③ レポートの権限テスト（permission_settings 動的取得）
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_staff_cannot_view_report_by_default():
    """デフォルト設定（permission_settings 未設定）で staff が 403 になること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import get_report

    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"permission_settings": make_col(find_one=None)})

    with pytest.raises(HTTPException) as exc:
        await get_report(fiscal_year=2025, month=None, ctx=ctx)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_staff_can_view_report_when_permission_set():
    """permission_settings に min_role='staff' を設定すると staff が 200 を返すこと。"""
    from app.api.routes.budgets import get_report

    perm_doc = {"corporate_id": CORP_ID, "feature_key": "budget_comparison_view", "min_role": "staff"}
    ctx = make_ctx(role="staff")
    ctx.db = build_mock_db({"permission_settings": make_col(find_one=perm_doc)})

    with patch("app.services.budget_report_service.get_budget_report",
               new_callable=AsyncMock, return_value={"rows": [], "has_budget": False, "total": {}}):
        result = await get_report(fiscal_year=2025, month=None, ctx=ctx)

    assert "rows" in result


@pytest.mark.asyncio
async def test_manager_can_view_report_by_default():
    """デフォルト設定で manager（rank=3）が 200 を返すこと（required_rank=2）。"""
    from app.api.routes.budgets import get_report

    ctx = make_ctx(role="manager")
    ctx.db = build_mock_db({"permission_settings": make_col(find_one=None)})

    with patch("app.services.budget_report_service.get_budget_report",
               new_callable=AsyncMock, return_value={"rows": [], "has_budget": False, "total": {}}):
        result = await get_report(fiscal_year=2025, month=None, ctx=ctx)

    assert "rows" in result


@pytest.mark.asyncio
async def test_accounting_can_view_report_by_default():
    """デフォルト設定で accounting（rank=3）が 200 を返すこと。"""
    from app.api.routes.budgets import get_report

    ctx = make_ctx(role="accounting")
    ctx.db = build_mock_db({"permission_settings": make_col(find_one=None)})

    with patch("app.services.budget_report_service.get_budget_report",
               new_callable=AsyncMock, return_value={"rows": [], "has_budget": False, "total": {}}):
        result = await get_report(fiscal_year=2025, month=None, ctx=ctx)

    assert "rows" in result


# ─────────────────────────────────────────────────────────────────────────────
# ④ レポートの計算テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_with_both_receipts_and_invoices():
    """同じ勘定科目で receipts と invoices が両方ある場合に合計が正しいこと。"""
    from app.services.budget_report_service import get_budget_report

    receipt = {"_id": ObjectId(), "corporate_id": CORP_ID, "category": "消耗品費",
               "amount": 3000, "approval_status": "approved", "fiscal_period": "2025-04"}
    invoice = {"_id": ObjectId(), "corporate_id": CORP_ID, "account_subject": "消耗品費",
               "total_amount": 7000, "document_type": "received",
               "approval_status": "approved", "fiscal_period": "2025-04"}
    mock_db = build_mock_db({
        "budgets": make_col(find_data=[]),
        "receipts": make_col(find_data=[receipt]),
        "invoices": make_col(find_data=[invoice]),
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        result = await get_budget_report(CORP_ID, fiscal_year=2025, month=4)

    row = next(r for r in result["rows"] if r["account_subject"] == "消耗品費")
    assert row["actual_amount"] == 10000


@pytest.mark.asyncio
async def test_report_unapproved_excluded():
    """approval_status クエリに 'approved' フィルタが含まれること。"""
    from app.services.budget_report_service import get_budget_report

    receipts_col = make_col(find_data=[])
    mock_db = build_mock_db({
        "budgets": make_col(find_data=[]),
        "receipts": receipts_col,
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        await get_budget_report(CORP_ID, fiscal_year=2025, month=4)

    q = receipts_col.find.call_args[0][0]
    assert q.get("approval_status") == "approved"


@pytest.mark.asyncio
async def test_report_yearly_aggregates_all_months():
    """month を省略した場合に全12ヶ月分の fiscal_periods が使われること。"""
    from app.services.budget_report_service import get_budget_report

    receipts_col = make_col(find_data=[])
    mock_db = build_mock_db({
        "budgets": make_col(find_data=[]),
        "receipts": receipts_col,
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        await get_budget_report(CORP_ID, fiscal_year=2025, month=None)

    q = receipts_col.find.call_args[0][0]
    fps = q.get("fiscal_period", {}).get("$in", [])
    assert len(fps) == 12
    assert "2025-01" in fps
    assert "2025-12" in fps


@pytest.mark.asyncio
async def test_report_total_row_matches_sum():
    """total.actual_amount が rows の actual_amount の合計と一致すること。"""
    from app.services.budget_report_service import get_budget_report

    receipts = [
        {"_id": ObjectId(), "corporate_id": CORP_ID, "category": f"科目{i}",
         "amount": 1000 * i, "approval_status": "approved", "fiscal_period": "2025-04"}
        for i in range(1, 4)
    ]
    mock_db = build_mock_db({
        "budgets": make_col(find_data=[]),
        "receipts": make_col(find_data=receipts),
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        result = await get_budget_report(CORP_ID, fiscal_year=2025, month=4)

    rows_total = sum(r["actual_amount"] for r in result["rows"])
    assert result["total"]["actual_amount"] == rows_total


@pytest.mark.asyncio
async def test_report_achievement_rate_100_percent():
    """予算=実績の場合に achievement_rate=100.0 が返ること。"""
    from app.services.budget_report_service import get_budget_report

    budget = sample_budget(amount=5000, account_subject="会議費")
    receipt = {"_id": ObjectId(), "corporate_id": CORP_ID, "category": "会議費",
               "amount": 5000, "approval_status": "approved", "fiscal_period": "2025-04"}
    mock_db = build_mock_db({
        "budgets": make_col(find_data=[budget]),
        "receipts": make_col(find_data=[receipt]),
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        result = await get_budget_report(CORP_ID, fiscal_year=2025, month=4)

    assert result["rows"][0]["achievement_rate"] == 100.0


@pytest.mark.asyncio
async def test_report_achievement_rate_null_when_no_budget():
    """budget_amount=0 の場合に achievement_rate=None であること（ゼロ除算なし）。"""
    from app.services.budget_report_service import get_budget_report

    budget = sample_budget(amount=0, account_subject="接待費")
    receipt = {"_id": ObjectId(), "corporate_id": CORP_ID, "category": "接待費",
               "amount": 100, "approval_status": "approved", "fiscal_period": "2025-04"}
    mock_db = build_mock_db({
        "budgets": make_col(find_data=[budget]),
        "receipts": make_col(find_data=[receipt]),
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        result = await get_budget_report(CORP_ID, fiscal_year=2025, month=4)

    assert result["rows"][0]["achievement_rate"] is None


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ スコープテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_budget_cross_corporate_update_blocked():
    """別法人の budget_id で PUT すると 404 が返ること（corporate_id フィルタ確認）。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import update_budget

    budgets_col = make_col(find_one=None)
    ctx = make_ctx(role="admin", corporate_id=CORP_ID)
    ctx.db = build_mock_db({"budgets": budgets_col})

    with pytest.raises(HTTPException) as exc:
        await update_budget(str(ObjectId()), {"amount": 9999}, ctx)

    assert exc.value.status_code == 404
    find_query = budgets_col.find_one.call_args[0][0]
    assert find_query.get("corporate_id") == CORP_ID


@pytest.mark.asyncio
async def test_budget_cross_corporate_delete_blocked():
    """別法人の budget_id で DELETE すると 404 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.budgets import delete_budget

    budgets_col = make_col()
    budgets_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))

    ctx = make_ctx(role="admin", corporate_id=CORP_ID)
    ctx.db = build_mock_db({"budgets": budgets_col})

    with pytest.raises(HTTPException) as exc:
        await delete_budget(str(ObjectId()), ctx)

    assert exc.value.status_code == 404
    del_query = budgets_col.delete_one.call_args[0][0]
    assert del_query.get("corporate_id") == CORP_ID


@pytest.mark.asyncio
async def test_report_cross_corporate_data_excluded():
    """別法人の receipts がレポートの実績に含まれないこと（corporate_id フィルタ確認）。"""
    from app.services.budget_report_service import get_budget_report

    receipts_col = make_col(find_data=[])
    mock_db = build_mock_db({
        "budgets": make_col(find_data=[]),
        "receipts": receipts_col,
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.budget_report_service.get_database", return_value=mock_db):
        await get_budget_report(CORP_ID, fiscal_year=2025, month=4)

    q = receipts_col.find.call_args[0][0]
    assert q.get("corporate_id") == CORP_ID
