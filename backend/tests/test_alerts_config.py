"""
Tests for Task#26・#27: alerts_config API + 法人横断アラート一覧

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_alerts_config.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

# ── テスト用固定 UID ────────────────────────────────────────────────────────
TAX_FIRM_A_UID = "tax_firm_a_uid"
TAX_FIRM_B_UID = "tax_firm_b_uid"
CORP_C_ID = str(ObjectId())   # 顧客C（法人B配下）

# ── ドキュメントの雛形 ──────────────────────────────────────────────────────
TAX_FIRM_A_DOC = {
    "_id": ObjectId(),
    "firebase_uid": TAX_FIRM_A_UID,
    "corporateType": "tax_firm",
    "name": "税理士法人A",
}
TAX_FIRM_B_DOC = {
    "_id": ObjectId(),
    "firebase_uid": TAX_FIRM_B_UID,
    "corporateType": "tax_firm",
    "name": "税理士法人B",
}
CORP_C_DOC = {
    "_id": ObjectId(CORP_C_ID),
    "firebase_uid": "corp_c_uid",
    "corporateType": "corporate",
    "name": "顧客C株式会社",
    "advising_tax_firm_id": TAX_FIRM_B_UID,  # BのUID で紐付いている
}


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_col(find_one=None, find_data=None, count=0):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    col.count_documents = AsyncMock(return_value=count)
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return col


def build_mock_db(collections: dict):
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


def make_multi_find_col(docs_by_query: list):
    """
    ⑤ 複数ドキュメントを持つコレクションで _id / firebase_uid をキーに検索するモック。
    find_one が呼ばれた際に query の内容でフィルタして返す。
    """
    col = MagicMock()

    async def _find_one(query: dict, *args, **kwargs):
        uid = query.get("firebase_uid")
        oid = query.get("_id")
        for d in docs_by_query:
            if uid is not None and d.get("firebase_uid") != uid:
                continue
            if oid is not None and d.get("_id") != oid:
                continue
            return d
        return None

    col.find_one = _find_one
    col.find = MagicMock(return_value=make_cursor([]))
    col.count_documents = AsyncMock(return_value=0)
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return col


# ─────────────────────────────────────────────────────────────────────────────
# test_tax_firm_can_get_config
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_firm_can_get_config():
    """税理士法人Bが配下法人Cの設定を GET できること。未設定ならデフォルト値が返ること。"""
    from app.api.routes.alerts_config import get_alerts_config
    from app.services.alert_service import DEFAULT_THRESHOLDS

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(find_one=None),  # 未設定
    })
    current_user = {"uid": TAX_FIRM_B_UID}

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await get_alerts_config(CORP_C_ID, current_user)

    assert result["corporate_id"] == CORP_C_ID
    for key, default_val in DEFAULT_THRESHOLDS.items():
        assert result[key] == default_val, f"{key} のデフォルト値が返ること"


@pytest.mark.asyncio
async def test_tax_firm_gets_custom_config():
    """カスタム設定がある場合にカスタム値が返ること。"""
    from app.api.routes.alerts_config import get_alerts_config

    custom_config = {
        "_id": ObjectId(),
        "corporate_id": CORP_C_ID,
        "rejected_stale_days": 1,
        "no_attachment_days": 2,
    }
    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(find_one=custom_config),
    })
    current_user = {"uid": TAX_FIRM_B_UID}

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await get_alerts_config(CORP_C_ID, current_user)

    assert result["rejected_stale_days"] == 1
    assert result["no_attachment_days"] == 2
    # 未設定のキーはデフォルト値
    from app.services.alert_service import DEFAULT_THRESHOLDS
    assert result["unreconciled_days"] == DEFAULT_THRESHOLDS["unreconciled_days"]


# ─────────────────────────────────────────────────────────────────────────────
# test_corporate_cannot_get_config
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_corporate_cannot_get_config():
    """一般法人が GET すると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import get_alerts_config

    # corporateType が "corporate" の呼び出し元
    caller_doc = {
        "_id": ObjectId(),
        "firebase_uid": "corp_user_uid",
        "corporateType": "corporate",
    }
    corporates_col = make_col(find_one=caller_doc)
    mock_db = build_mock_db({"corporates": corporates_col})
    current_user = {"uid": "corp_user_uid"}

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await get_alerts_config(CORP_C_ID, current_user)

    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# test_tax_firm_can_update_config
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_firm_can_update_config():
    """税理士法人Bが設定を PUT できること。③ updated_by が firebase_uid であること。"""
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    alerts_config_col = make_col()
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": alerts_config_col,
    })
    current_user = {"uid": TAX_FIRM_B_UID}
    payload = {"rejected_stale_days": 5, "approval_delay_days": 2}

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await update_alerts_config(CORP_C_ID, payload, current_user)

    assert result["status"] == "updated"
    assert result["rejected_stale_days"] == 5
    assert result["approval_delay_days"] == 2
    # ③ updated_by は firebase_uid で統一されていること
    assert result["updated_by"] == TAX_FIRM_B_UID
    assert result["tax_firm_id"] == TAX_FIRM_B_UID
    # upsert が呼ばれていること
    alerts_config_col.update_one.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# test_invalid_key_rejected
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_key_rejected():
    """無効なキーを PUT すると 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(),
    })
    current_user = {"uid": TAX_FIRM_B_UID}

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID,
                {"invalid_key": 5},
                current_user,
            )

    assert exc.value.status_code == 400
    assert "無効なキー" in exc.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# test_non_positive_value_rejected
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_positive_value_rejected():
    """値が0または負の場合に 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(),
    })
    current_user = {"uid": TAX_FIRM_B_UID}

    for bad_val in [0, -1, -999]:
        with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
            with pytest.raises(HTTPException) as exc:
                await update_alerts_config(
                    CORP_C_ID,
                    {"rejected_stale_days": bad_val},
                    current_user,
                )

        assert exc.value.status_code == 400, f"value={bad_val} で 400 が返ること"


# ─────────────────────────────────────────────────────────────────────────────
# test_tax_firm_cannot_access_other_clients_config  ⑤ 3ドキュメントモック
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_firm_cannot_access_other_clients_config():
    """
    ⑤ 税理士法人Aが顧客C（法人B配下）にアクセスすると403になること。
    corporates コレクションに以下の3ドキュメントを用意：
      - 税理士法人A（firebase_uid=tax_firm_a_uid）
      - 税理士法人B（firebase_uid=tax_firm_b_uid）
      - 顧客C（advising_tax_firm_id=tax_firm_b_uid）
    """
    from fastapi import HTTPException
    from app.api.routes.alerts_config import get_alerts_config

    # ⑤ 3ドキュメントを持つコレクション
    corporates_col = make_multi_find_col([TAX_FIRM_A_DOC, TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(find_one=None),
    })
    # 法人Aとして法人C（Bの顧客）にアクセス
    current_user = {"uid": TAX_FIRM_A_UID}

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await get_alerts_config(CORP_C_ID, current_user)

    assert exc.value.status_code == 403, "別税理士法人の顧客には 403 が返ること"


@pytest.mark.asyncio
async def test_tax_firm_cannot_update_other_clients_config():
    """法人Aが法人B配下の顧客Cを PUT しようとしても 403 になること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_A_DOC, TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(),
    })
    current_user = {"uid": TAX_FIRM_A_UID}

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID,
                {"rejected_stale_days": 1},
                current_user,
            )

    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# test_corporate_alerts_returns_all_clients
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_corporate_alerts_returns_all_clients():
    """GET /admin/corporate-alerts が配下の全法人の件数を返すこと。"""
    from app.api.routes.admin import get_corporate_alerts

    client1 = {"_id": ObjectId(), "name": "顧客1株式会社", "corporateType": "corporate",
               "advising_tax_firm_id": TAX_FIRM_B_UID}
    client2 = {"_id": ObjectId(), "name": "顧客2株式会社", "corporateType": "corporate",
               "advising_tax_firm_id": TAX_FIRM_B_UID}

    corporates_col = make_col(
        find_one=TAX_FIRM_B_DOC,
        find_data=[client1, client2],
    )
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "receipts": make_col(count=2),
        "invoices": make_col(count=1),
        "transactions": make_col(count=3),
    })
    current_user = {"uid": TAX_FIRM_B_UID}

    with patch("app.db.mongodb.get_database", return_value=mock_db):
        result = await get_corporate_alerts(current_user)

    assert "data" in result
    assert len(result["data"]) == 2
    # 各法人に必須フィールドが含まれること
    for item in result["data"]:
        for key in ("corporate_id", "company_name", "pending_receipts",
                    "pending_invoices", "unmatched_transactions",
                    "rejected_stale_count", "approval_delay_count",
                    "total_alerts", "has_alerts"):
            assert key in item, f"{key} が含まれること"


# ─────────────────────────────────────────────────────────────────────────────
# test_corporate_alerts_sorted_by_alert_count
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_corporate_alerts_sorted_by_alert_count():
    """アラートが多い法人が先頭に来ること。"""
    from app.api.routes.admin import get_corporate_alerts

    corp_low  = {"_id": ObjectId(), "name": "アラート少ない", "corporateType": "corporate",
                 "advising_tax_firm_id": TAX_FIRM_B_UID}
    corp_high = {"_id": ObjectId(), "name": "アラート多い", "corporateType": "corporate",
                 "advising_tax_firm_id": TAX_FIRM_B_UID}

    corp_low_id  = str(corp_low["_id"])
    corp_high_id = str(corp_high["_id"])

    # count_documents の戻り値を法人IDによって変える
    call_count = {"n": 0}
    async def mock_count(query: dict):
        cid = query.get("corporate_id", "")
        # corp_high は stale/delay が多い
        if cid == corp_high_id and query.get("rejected_stale_alerted"):
            return 5
        if cid == corp_high_id and query.get("approval_delay_alerted"):
            return 3
        return 0

    receipts_col = MagicMock()
    receipts_col.count_documents = mock_count
    receipts_col.find = MagicMock(return_value=make_cursor([]))

    invoices_col = make_col(count=0)
    txs_col = make_col(count=0)

    corporates_col = make_col(
        find_one=TAX_FIRM_B_DOC,
        find_data=[corp_low, corp_high],  # low が先
    )

    mock_db = build_mock_db({
        "corporates": corporates_col,
        "receipts": receipts_col,
        "invoices": invoices_col,
        "transactions": txs_col,
    })
    current_user = {"uid": TAX_FIRM_B_UID}

    with patch("app.db.mongodb.get_database", return_value=mock_db):
        result = await get_corporate_alerts(current_user)

    data = result["data"]
    assert len(data) == 2
    # アラートが多い法人（corp_high）が先頭に来ること
    assert data[0]["total_alerts"] >= data[1]["total_alerts"], \
        "アラート降順ソートになっていること"


# =============================================================================
# 意地悪テスト（Task#26・#27）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① 権限チェックの境界値テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_firm_employee_cannot_access():
    """
    税理士法人の従業員（employees コレクション）が GET すると 403 が返ること。
    corporates ドキュメントを持つユーザーのみアクセス可能であること。
    """
    from fastapi import HTTPException
    from app.api.routes.alerts_config import get_alerts_config

    # corporates に存在しない（従業員のみ）
    mock_db = build_mock_db({
        "corporates": make_col(find_one=None),  # corporates に見つからない
    })
    current_user = {"uid": "employee_uid"}

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await get_alerts_config(CORP_C_ID, current_user)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_unrelated_tax_firm_get_returns_403():
    """顧客と紐付いていない別の税理士法人が GET すると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import get_alerts_config

    # 税理士法人Aは顧客C（Bの配下）を GET できない
    corporates_col = make_multi_find_col([TAX_FIRM_A_DOC, TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(find_one=None),
    })
    current_user = {"uid": TAX_FIRM_A_UID}

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await get_alerts_config(CORP_C_ID, current_user)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_unrelated_tax_firm_put_returns_403():
    """顧客と紐付いていない別の税理士法人が PUT すると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_A_DOC, TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(),
    })
    current_user = {"uid": TAX_FIRM_A_UID}

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID, {"rejected_stale_days": 3}, current_user
            )

    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# ② バリデーションテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_put_with_zero_value_rejected():
    """値に 0 を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({"corporates": corporates_col, "alerts_config": make_col()})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID, {"rejected_stale_days": 0}, {"uid": TAX_FIRM_B_UID}
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_put_with_negative_value_rejected():
    """値に -1 を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({"corporates": corporates_col, "alerts_config": make_col()})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID, {"rejected_stale_days": -1}, {"uid": TAX_FIRM_B_UID}
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_put_with_float_value_rejected():
    """値に 1.5（小数）を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({"corporates": corporates_col, "alerts_config": make_col()})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID, {"rejected_stale_days": 1.5}, {"uid": TAX_FIRM_B_UID}
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_put_with_string_value_rejected():
    """値に "3"（文字列）を渡すと 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({"corporates": corporates_col, "alerts_config": make_col()})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID, {"rejected_stale_days": "3"}, {"uid": TAX_FIRM_B_UID}
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_put_with_unknown_key_rejected():
    """存在しないキーを PUT すると 400 が返ること（VALID_KEYS に含まれないキーの確認）。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config, VALID_KEYS

    unknown_key = "completely_nonexistent_key"
    assert unknown_key not in VALID_KEYS  # 本当に存在しないことを確認

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({"corporates": corporates_col, "alerts_config": make_col()})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID,
                {unknown_key: 3},
                {"uid": TAX_FIRM_B_UID},
            )
    assert exc.value.status_code == 400
    assert "無効なキー" in exc.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# ③ デフォルト値のフォールバックテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_returns_default_when_no_config():
    """alerts_config が未設定の法人に GET すると DEFAULT_THRESHOLDS の全キーが返ること。"""
    from app.api.routes.alerts_config import get_alerts_config
    from app.services.alert_service import DEFAULT_THRESHOLDS

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(find_one=None),
    })

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await get_alerts_config(CORP_C_ID, {"uid": TAX_FIRM_B_UID})

    for key, default_val in DEFAULT_THRESHOLDS.items():
        assert key in result, f"{key} がレスポンスに含まれること"
        assert result[key] == default_val, f"{key} のデフォルト値 {default_val} が返ること"


@pytest.mark.asyncio
async def test_get_partial_config_merges_with_defaults():
    """alerts_config に一部のキーしかない場合に未設定のキーはデフォルト値で補完されること。"""
    from app.api.routes.alerts_config import get_alerts_config
    from app.services.alert_service import DEFAULT_THRESHOLDS

    partial_config = {
        "_id": ObjectId(),
        "corporate_id": CORP_C_ID,
        "rejected_stale_days": 10,  # カスタム
        # 他のキーは未設定
    }
    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(find_one=partial_config),
    })

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await get_alerts_config(CORP_C_ID, {"uid": TAX_FIRM_B_UID})

    assert result["rejected_stale_days"] == 10  # カスタム値
    # 未設定のキーはデフォルト値で補完
    assert result["unreconciled_days"] == DEFAULT_THRESHOLDS["unreconciled_days"]
    assert result["approval_delay_days"] == DEFAULT_THRESHOLDS["approval_delay_days"]
    assert result["no_attachment_days"] == DEFAULT_THRESHOLDS["no_attachment_days"]


@pytest.mark.asyncio
async def test_put_partial_update_does_not_reset_others():
    """
    rejected_stale_days のみ更新した場合に他のキーのレスポンスが変わらないこと。
    PUT はリクエストに含まれたキーのみ更新し、他には触れないこと。
    """
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    alerts_config_col = make_col()
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await update_alerts_config(
            CORP_C_ID,
            {"rejected_stale_days": 7},
            {"uid": TAX_FIRM_B_UID},
        )

    # 更新したキーが含まれること
    assert result["rejected_stale_days"] == 7
    # 送っていないキーがレスポンスに含まれていないこと（update_data にのみ含まれる）
    assert "unreconciled_days" not in result
    # upsert で $set にペイロードキーのみが渡されていること
    call_args = alerts_config_col.update_one.call_args
    set_data = call_args[0][1]["$set"]
    assert "rejected_stale_days" in set_data
    assert "unreconciled_days" not in set_data


# ─────────────────────────────────────────────────────────────────────────────
# ④ corporate-alerts エンドポイントテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_corporate_alerts_includes_all_clients():
    """配下に3法人ある場合に3件返ること。"""
    from app.api.routes.admin import get_corporate_alerts

    clients = [
        {"_id": ObjectId(), "name": f"顧客{i}", "corporateType": "corporate",
         "advising_tax_firm_id": TAX_FIRM_B_UID}
        for i in range(3)
    ]
    corporates_col = make_col(find_one=TAX_FIRM_B_DOC, find_data=clients)
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "receipts": make_col(count=0),
        "invoices": make_col(count=0),
        "transactions": make_col(count=0),
    })

    with patch("app.db.mongodb.get_database", return_value=mock_db):
        result = await get_corporate_alerts({"uid": TAX_FIRM_B_UID})

    assert len(result["data"]) == 3


@pytest.mark.asyncio
async def test_corporate_alerts_sorted_by_total_alerts():
    """アラート件数の多い順に並んでいること（rejected_stale + approval_delay 合計）。"""
    from app.api.routes.admin import get_corporate_alerts

    corp_a = {"_id": ObjectId(), "name": "アラート0", "corporateType": "corporate",
              "advising_tax_firm_id": TAX_FIRM_B_UID}
    corp_b = {"_id": ObjectId(), "name": "アラート5", "corporateType": "corporate",
              "advising_tax_firm_id": TAX_FIRM_B_UID}

    corp_a_id = str(corp_a["_id"])
    corp_b_id = str(corp_b["_id"])

    async def mock_count(query: dict):
        cid = query.get("corporate_id", "")
        if cid == corp_b_id and (
            query.get("rejected_stale_alerted") or query.get("approval_delay_alerted")
        ):
            return 3
        return 0

    receipts_col = MagicMock()
    receipts_col.count_documents = mock_count
    receipts_col.find = MagicMock(return_value=make_cursor([]))

    mock_db = build_mock_db({
        "corporates": make_col(find_one=TAX_FIRM_B_DOC, find_data=[corp_a, corp_b]),
        "receipts": receipts_col,
        "invoices": make_col(count=0),
        "transactions": make_col(count=0),
    })

    with patch("app.db.mongodb.get_database", return_value=mock_db):
        result = await get_corporate_alerts({"uid": TAX_FIRM_B_UID})

    data = result["data"]
    assert data[0]["total_alerts"] >= data[1]["total_alerts"]


@pytest.mark.asyncio
async def test_corporate_alerts_zero_when_no_alerts():
    """全法人でアラートなしの場合に has_alerts=False・total_alerts=0 であること。"""
    from app.api.routes.admin import get_corporate_alerts

    client = {"_id": ObjectId(), "name": "正常法人", "corporateType": "corporate",
              "advising_tax_firm_id": TAX_FIRM_B_UID}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=TAX_FIRM_B_DOC, find_data=[client]),
        "receipts": make_col(count=0),
        "invoices": make_col(count=0),
        "transactions": make_col(count=0),
    })

    with patch("app.db.mongodb.get_database", return_value=mock_db):
        result = await get_corporate_alerts({"uid": TAX_FIRM_B_UID})

    assert len(result["data"]) == 1
    item = result["data"][0]
    assert item["has_alerts"] is False
    assert item["total_alerts"] == 0


@pytest.mark.asyncio
async def test_corporate_cannot_call_corporate_alerts():
    """一般法人が GET /admin/corporate-alerts を呼ぶと 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.admin import get_corporate_alerts

    corp_doc = {
        "_id": ObjectId(),
        "firebase_uid": "corp_uid",
        "corporateType": "corporate",  # tax_firm ではない
    }
    mock_db = build_mock_db({"corporates": make_col(find_one=corp_doc)})

    with patch("app.db.mongodb.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await get_corporate_alerts({"uid": "corp_uid"})

    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ _verify_tax_firm_access ヘルパーテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_helper_raises_on_invalid_corporate_id():
    """corporate_id に 'invalid-id' を渡すと HTTPException(400) が raise されること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import _verify_tax_firm_access

    mock_db = build_mock_db({
        "corporates": make_col(find_one=TAX_FIRM_B_DOC),
    })

    with pytest.raises(HTTPException) as exc:
        await _verify_tax_firm_access(TAX_FIRM_B_UID, "invalid-id", mock_db)

    assert exc.value.status_code == 400
    assert "Invalid" in exc.value.detail


@pytest.mark.asyncio
async def test_verify_helper_raises_on_nonexistent_corporate():
    """存在しない corporate_id を渡すと HTTPException(404) が raise されること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import _verify_tax_firm_access

    async def _find_one_none(query, *args, **kwargs):
        # 税理士法人チェック（firebase_uid で検索）は TAX_FIRM_B_DOC を返す
        if query.get("firebase_uid") == TAX_FIRM_B_UID:
            return TAX_FIRM_B_DOC
        # _id での検索は None（法人が存在しない）
        return None

    corporates_col = MagicMock()
    corporates_col.find_one = _find_one_none
    mock_db = build_mock_db({"corporates": corporates_col})

    with pytest.raises(HTTPException) as exc:
        await _verify_tax_firm_access(
            TAX_FIRM_B_UID,
            str(ObjectId()),  # 有効な ObjectId だが DB に存在しない
            mock_db,
        )

    assert exc.value.status_code == 404
    assert "法人が見つかりません" in exc.value.detail
