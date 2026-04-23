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
    from app.api.routes.alerts_config import get_corporate_alerts

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

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
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
    from app.api.routes.alerts_config import get_corporate_alerts

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

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
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
    from app.api.routes.alerts_config import get_corporate_alerts

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

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await get_corporate_alerts({"uid": TAX_FIRM_B_UID})

    assert len(result["data"]) == 3


@pytest.mark.asyncio
async def test_corporate_alerts_sorted_by_total_alerts():
    """アラート件数の多い順に並んでいること（rejected_stale + approval_delay 合計）。"""
    from app.api.routes.alerts_config import get_corporate_alerts

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

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await get_corporate_alerts({"uid": TAX_FIRM_B_UID})

    data = result["data"]
    assert data[0]["total_alerts"] >= data[1]["total_alerts"]


@pytest.mark.asyncio
async def test_corporate_alerts_zero_when_no_alerts():
    """全法人でアラートなしの場合に has_alerts=False・total_alerts=0 であること。"""
    from app.api.routes.alerts_config import get_corporate_alerts

    client = {"_id": ObjectId(), "name": "正常法人", "corporateType": "corporate",
              "advising_tax_firm_id": TAX_FIRM_B_UID}
    mock_db = build_mock_db({
        "corporates": make_col(find_one=TAX_FIRM_B_DOC, find_data=[client]),
        "receipts": make_col(count=0),
        "invoices": make_col(count=0),
        "transactions": make_col(count=0),
    })

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await get_corporate_alerts({"uid": TAX_FIRM_B_UID})

    assert len(result["data"]) == 1
    item = result["data"][0]
    assert item["has_alerts"] is False
    assert item["total_alerts"] == 0


@pytest.mark.asyncio
async def test_corporate_cannot_call_corporate_alerts():
    """一般法人が GET /admin/corporate-alerts を呼ぶと 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import get_corporate_alerts

    corp_doc = {
        "_id": ObjectId(),
        "firebase_uid": "corp_uid",
        "corporateType": "corporate",  # tax_firm ではない
    }
    mock_db = build_mock_db({"corporates": make_col(find_one=corp_doc)})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
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


# =============================================================================
# Task#47 追加テスト：email_enabled / /self エンドポイント / 通知メール制御
# =============================================================================

CORP_C_FIREBASE_UID = CORP_C_DOC["firebase_uid"]  # "corp_c_uid"
EMPLOYEE_UID = "corp_employee_uid"
EMPLOYEE_DOC = {
    "_id": ObjectId(),
    "firebase_uid": EMPLOYEE_UID,
    "corporate_id": CORP_C_ID,
    "role": "accounting",
    "email": "employee@example.com",
}


# ─────────────────────────────────────────────────────────────────────────────
# test_email_enabled_default_is_false
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_enabled_default_is_false():
    """alerts_config 未設定時に email_enabled が全て False で返ること。"""
    from app.api.routes.alerts_config import get_alerts_config, DEFAULT_EMAIL_ENABLED

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(find_one=None),
    })

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await get_alerts_config(CORP_C_ID, {"uid": TAX_FIRM_B_UID})

    assert "email_enabled" in result
    for k, default_val in DEFAULT_EMAIL_ENABLED.items():
        assert result["email_enabled"][k] == default_val, f"{k} のデフォルトは False であること"


# ─────────────────────────────────────────────────────────────────────────────
# test_update_email_enabled
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_email_enabled():
    """PUT で email_enabled を更新できること（閾値と同時更新も可）。"""
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    alerts_config_col = make_col()
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": alerts_config_col,
    })

    payload = {
        "rejected_stale_days": 5,
        "email_enabled": {
            "rejected_stale_alert": True,
            "no_attachment_alert": False,
        },
    }

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await update_alerts_config(CORP_C_ID, payload, {"uid": TAX_FIRM_B_UID})

    assert result["status"] == "updated"
    # update_one が呼ばれていること
    alerts_config_col.update_one.assert_called_once()
    call_args = alerts_config_col.update_one.call_args
    set_data = call_args[0][1]["$set"]
    assert set_data["rejected_stale_days"] == 5
    assert set_data["email_enabled.rejected_stale_alert"] is True
    assert set_data["email_enabled.no_attachment_alert"] is False


# ─────────────────────────────────────────────────────────────────────────────
# test_invalid_email_key_ignored
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_email_key_ignored():
    """VALID_EMAIL_KEYS 以外のキーは無視され、400 にならないこと。"""
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    alerts_config_col = make_col()
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": alerts_config_col,
    })

    payload = {
        "rejected_stale_days": 3,
        "email_enabled": {
            "rejected_stale_alert": True,
            "completely_unknown_alert_key": True,  # 無視されるべき
        },
    }

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await update_alerts_config(CORP_C_ID, payload, {"uid": TAX_FIRM_B_UID})

    assert result["status"] == "updated"
    set_data = alerts_config_col.update_one.call_args[0][1]["$set"]
    assert "email_enabled.rejected_stale_alert" in set_data
    assert "email_enabled.completely_unknown_alert_key" not in set_data


# ─────────────────────────────────────────────────────────────────────────────
# test_non_bool_email_enabled_rejected
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_bool_email_enabled_rejected():
    """email_enabled の値が bool 以外（文字列・数値）の場合に 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "alerts_config": make_col(),
    })

    for bad_val in ["true", 1, 0, None]:
        with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
            with pytest.raises(HTTPException) as exc:
                await update_alerts_config(
                    CORP_C_ID,
                    {"email_enabled": {"rejected_stale_alert": bad_val}},
                    {"uid": TAX_FIRM_B_UID},
                )
        assert exc.value.status_code == 400, f"value={bad_val!r} で 400 が返ること"


# ─────────────────────────────────────────────────────────────────────────────
# test_alert_notification_email_sent_when_enabled
# ─────────────────────────────────────────────────────────────────────────────

def _make_notif_col():
    """insert_one を AsyncMock にした通知コレクションモック。"""
    col = make_col()
    col.insert_one = AsyncMock(return_value=MagicMock())
    return col


def _make_notif_db(alerts_config_find_one):
    """通知テスト用 mock_db（notifications + alerts_config）。"""
    return build_mock_db({
        "notifications": _make_notif_col(),
        "alerts_config": make_col(find_one=alerts_config_find_one),
    })


@pytest.mark.asyncio
async def test_alert_notification_email_sent_when_enabled():
    """email_enabled=True かつ SENDGRID_API_KEY 設定済みの場合にメールが送信されること。"""
    from app.services.notification_service import create_notification
    from app.core.config import settings

    original_key = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = "SG.test_key"
    alerts_config_doc = {"corporate_id": CORP_C_ID, "email_enabled": {"rejected_stale_alert": True}}
    send_mock = AsyncMock(return_value=True)

    try:
        with patch("app.services.notification_service.get_database", return_value=_make_notif_db(alerts_config_doc)):
            with patch("app.services.notification_service.send_email_notification", send_mock):
                await create_notification(
                    corporate_id=CORP_C_ID, notification_type="rejected_stale_alert",
                    recipient_employee_id="emp_id", recipient_email="employee@example.com",
                    related_document_type="receipt", related_document_id="doc_id",
                    message="差し戻しされた領収書が3日以上放置されています。",
                )
        send_mock.assert_called_once()
    finally:
        settings.SENDGRID_API_KEY = original_key


# ─────────────────────────────────────────────────────────────────────────────
# test_alert_notification_email_not_sent_when_disabled
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alert_notification_email_not_sent_when_disabled():
    """email_enabled=False の場合にメールが送信されないこと。"""
    from app.services.notification_service import create_notification
    from app.core.config import settings

    original_key = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = "SG.test_key"
    alerts_config_doc = {"corporate_id": CORP_C_ID, "email_enabled": {"rejected_stale_alert": False}}
    send_mock = AsyncMock(return_value=True)

    try:
        with patch("app.services.notification_service.get_database", return_value=_make_notif_db(alerts_config_doc)):
            with patch("app.services.notification_service.send_email_notification", send_mock):
                await create_notification(
                    corporate_id=CORP_C_ID, notification_type="rejected_stale_alert",
                    recipient_employee_id="emp_id", recipient_email="employee@example.com",
                    related_document_type="receipt", related_document_id="doc_id",
                    message="差し戻しされた領収書が3日以上放置されています。",
                )
        send_mock.assert_not_called()
    finally:
        settings.SENDGRID_API_KEY = original_key


# ─────────────────────────────────────────────────────────────────────────────
# test_business_notification_always_sends_email
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_business_notification_always_sends_email():
    """approval_request など業務系通知は email_enabled に関係なく送信されること。"""
    from app.services.notification_service import create_notification
    from app.core.config import settings

    original_key = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = "SG.test_key"
    # alerts_config が全て空でも業務系は送信される
    send_mock = AsyncMock(return_value=True)

    try:
        with patch("app.services.notification_service.get_database", return_value=_make_notif_db(None)):
            with patch("app.services.notification_service.send_email_notification", send_mock):
                await create_notification(
                    corporate_id=CORP_C_ID, notification_type="approval_request",
                    recipient_employee_id="emp_id", recipient_email="approver@example.com",
                    related_document_type="receipt", related_document_id="doc_id",
                    message="承認依頼が届きました。",
                )
        send_mock.assert_called_once()
    finally:
        settings.SENDGRID_API_KEY = original_key


# ─────────────────────────────────────────────────────────────────────────────
# test_no_double_send_after_merge
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_double_send_after_merge():
    """create_notification_with_email 削除後、メールが1回だけ送信されること。"""
    from app.services.notification_service import create_notification
    from app.core.config import settings

    original_key = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = "SG.test_key"
    send_mock = AsyncMock(return_value=True)

    try:
        with patch("app.services.notification_service.get_database", return_value=_make_notif_db(None)):
            with patch("app.services.notification_service.send_email_notification", send_mock):
                await create_notification(
                    corporate_id=CORP_C_ID, notification_type="approved_notification",
                    recipient_employee_id="emp_id", recipient_email="submitter@example.com",
                    related_document_type="invoice", related_document_id="inv_id",
                    message="請求書が承認されました。",
                )
        assert send_mock.call_count == 1, f"1回のみ呼ばれること（実際: {send_mock.call_count}回）"
    finally:
        settings.SENDGRID_API_KEY = original_key


# =============================================================================
# 意地悪テスト（Task#47）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① email_enabled の境界値テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_enabled_partial_update():
    """rejected_stale_alert のみ True に更新した場合に他のキーは変更されないこと。"""
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    alerts_config_col = make_col()
    mock_db = build_mock_db({"corporates": corporates_col, "alerts_config": alerts_config_col})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await update_alerts_config(
            CORP_C_ID,
            {"email_enabled": {"rejected_stale_alert": True}},
            {"uid": TAX_FIRM_B_UID},
        )

    assert result["status"] == "updated"
    set_data = alerts_config_col.update_one.call_args[0][1]["$set"]
    # 更新したキーのみ $set に含まれること（他のキーは含まれない）
    assert set_data["email_enabled.rejected_stale_alert"] is True
    assert "email_enabled.no_attachment_alert" not in set_data
    assert "email_enabled.unreconciled_alert" not in set_data
    assert "email_enabled.approval_delay_alert" not in set_data
    assert "email_enabled.tax_advisor_escalation_alert" not in set_data


@pytest.mark.asyncio
async def test_email_enabled_unknown_key_ignored():
    """VALID_EMAIL_KEYS にない unknown_alert を送っても 400 にならず無視されること。"""
    from app.api.routes.alerts_config import update_alerts_config, VALID_EMAIL_KEYS

    unknown_key = "unknown_alert"
    assert unknown_key not in VALID_EMAIL_KEYS

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    alerts_config_col = make_col()
    mock_db = build_mock_db({"corporates": corporates_col, "alerts_config": alerts_config_col})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await update_alerts_config(
            CORP_C_ID,
            {
                "rejected_stale_days": 3,
                "email_enabled": {
                    "rejected_stale_alert": True,
                    unknown_key: True,  # 無視されるべき
                },
            },
            {"uid": TAX_FIRM_B_UID},
        )

    assert result["status"] == "updated"
    set_data = alerts_config_col.update_one.call_args[0][1]["$set"]
    assert f"email_enabled.{unknown_key}" not in set_data
    assert "email_enabled.rejected_stale_alert" in set_data


@pytest.mark.asyncio
async def test_email_enabled_non_bool_string_rejected():
    """email_enabled の値に文字列 "true" を送ると 400 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({"corporates": corporates_col, "alerts_config": make_col()})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID,
                {"email_enabled": {"rejected_stale_alert": "true"}},
                {"uid": TAX_FIRM_B_UID},
            )
    assert exc.value.status_code == 400
    assert "true/false" in exc.value.detail


@pytest.mark.asyncio
async def test_email_enabled_non_bool_int_rejected():
    """email_enabled の値に整数 1 を送ると 400 が返ること（Python の bool は int の部分型なので注意）。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    # Python では bool は int のサブクラスだが、isinstance(True, int) == True。
    # 整数 1 は bool ではないので 400 になること。
    corporates_col = make_multi_find_col([TAX_FIRM_B_DOC, CORP_C_DOC])
    mock_db = build_mock_db({"corporates": corporates_col, "alerts_config": make_col()})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID,
                {"email_enabled": {"rejected_stale_alert": 1}},
                {"uid": TAX_FIRM_B_UID},
            )
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# ② /self エンドポイントのテスト
# ─────────────────────────────────────────────────────────────────────────────

STAFF_UID = "corp_staff_uid"
STAFF_DOC = {
    "_id": ObjectId(),
    "firebase_uid": STAFF_UID,
    "corporate_id": CORP_C_ID,
    "role": "staff",
}
ACCOUNTING_UID = "corp_accounting_uid"
ACCOUNTING_DOC = {
    "_id": ObjectId(),
    "firebase_uid": ACCOUNTING_UID,
    "corporate_id": CORP_C_ID,
    "role": "accounting",
}


@pytest.mark.asyncio
async def test_self_endpoint_staff_cannot_update():
    """staff ロールが PUT /alerts-config/self を叩くと 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config_self

    def _find_one_side_effect(query, *args, **kwargs):
        uid = query.get("firebase_uid")
        if uid == STAFF_UID:
            if "corporateType" in str(query) or "_id" not in query:
                return None  # corporates に存在しない
        return None

    employees_col = MagicMock()
    employees_col.find_one = AsyncMock(return_value=STAFF_DOC)
    corporates_col = make_col(find_one=None)  # employee なので corporates には見つからない
    mock_db = build_mock_db({
        "corporates": corporates_col,
        "employees": employees_col,
    })

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config_self(
                {"email_enabled": {"rejected_stale_alert": True}},
                {"uid": STAFF_UID},
            )
    assert exc.value.status_code == 403
    assert "経理担当者以上" in exc.value.detail


@pytest.mark.asyncio
async def test_self_endpoint_accounting_can_update():
    """accounting ロールが PUT /alerts-config/self を叩くと更新できること。"""
    from app.api.routes.alerts_config import update_alerts_config_self

    employees_col = MagicMock()
    employees_col.find_one = AsyncMock(return_value=ACCOUNTING_DOC)
    alerts_config_col = make_col()
    mock_db = build_mock_db({
        "corporates": make_col(find_one=None),
        "employees": employees_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await update_alerts_config_self(
            {"email_enabled": {"rejected_stale_alert": True}},
            {"uid": ACCOUNTING_UID},
        )

    assert result["status"] == "updated"
    alerts_config_col.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_self_endpoint_cannot_update_threshold():
    """PUT /alerts-config/self で rejected_stale_days=5 を送っても閾値は変わらないこと。"""
    from app.api.routes.alerts_config import update_alerts_config_self

    employees_col = MagicMock()
    employees_col.find_one = AsyncMock(return_value=ACCOUNTING_DOC)
    alerts_config_col = make_col()
    mock_db = build_mock_db({
        "corporates": make_col(find_one=None),
        "employees": employees_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await update_alerts_config_self(
            {
                "rejected_stale_days": 5,  # 無視されるべき
                "email_enabled": {"no_attachment_alert": True},
            },
            {"uid": ACCOUNTING_UID},
        )

    assert result["status"] == "updated"
    set_data = alerts_config_col.update_one.call_args[0][1]["$set"]
    # 閾値キーは $set に含まれない
    assert "rejected_stale_days" not in set_data
    # email_enabled のみ含まれる
    assert "email_enabled.no_attachment_alert" in set_data


@pytest.mark.asyncio
async def test_self_endpoint_returns_defaults_when_empty():
    """alerts_config 未設定の法人が GET /alerts-config/self を叩くとデフォルト値が返ること。"""
    from app.api.routes.alerts_config import get_alerts_config_self, DEFAULT_EMAIL_ENABLED

    employees_col = MagicMock()
    employees_col.find_one = AsyncMock(return_value=ACCOUNTING_DOC)
    mock_db = build_mock_db({
        "corporates": make_col(find_one=None),
        "employees": employees_col,
        "alerts_config": make_col(find_one=None),  # 未設定
    })

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await get_alerts_config_self({"uid": ACCOUNTING_UID})

    assert "email_enabled" in result
    for k, default_val in DEFAULT_EMAIL_ENABLED.items():
        assert result["email_enabled"][k] == default_val
        assert result["email_enabled"][k] is False, f"{k} のデフォルトは False であること"


# ─────────────────────────────────────────────────────────────────────────────
# ③ 通知メール送信ロジックのテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alert_type_checks_email_enabled():
    """rejected_stale_alert で email_enabled=False の場合に send_email_notification が呼ばれないこと。"""
    from app.services.notification_service import create_notification
    from app.core.config import settings

    original_key = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = "SG.test_key"
    alerts_config_doc = {"corporate_id": CORP_C_ID, "email_enabled": {"rejected_stale_alert": False}}
    send_mock = AsyncMock()

    try:
        with patch("app.services.notification_service.get_database", return_value=_make_notif_db(alerts_config_doc)):
            with patch("app.services.notification_service.send_email_notification", send_mock):
                await create_notification(
                    corporate_id=CORP_C_ID, notification_type="rejected_stale_alert",
                    recipient_employee_id="e", recipient_email="e@example.com",
                    related_document_type="receipt", related_document_id="d",
                    message="アラートメッセージ",
                )
        send_mock.assert_not_called()
    finally:
        settings.SENDGRID_API_KEY = original_key


@pytest.mark.asyncio
async def test_business_type_ignores_email_enabled():
    """approval_request は email_enabled が空でも send_email_notification が呼ばれること。"""
    from app.services.notification_service import create_notification
    from app.core.config import settings

    original_key = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = "SG.test_key"
    # alerts_config が存在しない（email_enabled も存在しない）
    send_mock = AsyncMock()

    try:
        with patch("app.services.notification_service.get_database", return_value=_make_notif_db(None)):
            with patch("app.services.notification_service.send_email_notification", send_mock):
                await create_notification(
                    corporate_id=CORP_C_ID, notification_type="approval_request",
                    recipient_employee_id="e", recipient_email="approver@example.com",
                    related_document_type="invoice", related_document_id="d",
                    message="承認依頼が届きました。",
                )
        send_mock.assert_called_once()
    finally:
        settings.SENDGRID_API_KEY = original_key


@pytest.mark.asyncio
async def test_no_api_key_blocks_all_emails():
    """SENDGRID_API_KEY 未設定の場合は email_enabled=True でもメールが送信されないこと。"""
    from app.services.notification_service import create_notification
    from app.core.config import settings

    original_key = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = ""  # 未設定
    alerts_config_doc = {"corporate_id": CORP_C_ID, "email_enabled": {"rejected_stale_alert": True}}
    send_mock = AsyncMock()

    try:
        with patch("app.services.notification_service.get_database", return_value=_make_notif_db(alerts_config_doc)):
            with patch("app.services.notification_service.send_email_notification", send_mock):
                await create_notification(
                    corporate_id=CORP_C_ID, notification_type="rejected_stale_alert",
                    recipient_employee_id="e", recipient_email="e@example.com",
                    related_document_type="receipt", related_document_id="d",
                    message="アラートメッセージ",
                )
        send_mock.assert_not_called()
    finally:
        settings.SENDGRID_API_KEY = original_key


@pytest.mark.asyncio
async def test_alert_config_not_found_defaults_to_false():
    """alerts_config が DB に存在しない場合はデフォルト False となりメールが送信されないこと。"""
    from app.services.notification_service import create_notification
    from app.core.config import settings

    original_key = settings.SENDGRID_API_KEY
    settings.SENDGRID_API_KEY = "SG.test_key"
    send_mock = AsyncMock()

    try:
        # alerts_config = None（DB に存在しない）
        with patch("app.services.notification_service.get_database", return_value=_make_notif_db(None)):
            with patch("app.services.notification_service.send_email_notification", send_mock):
                await create_notification(
                    corporate_id=CORP_C_ID, notification_type="no_attachment_alert",
                    recipient_employee_id="e", recipient_email="e@example.com",
                    related_document_type="receipt", related_document_id="d",
                    message="証憑未提出アラート",
                )
        send_mock.assert_not_called()
    finally:
        settings.SENDGRID_API_KEY = original_key


# ─────────────────────────────────────────────────────────────────────────────
# ④ スコープテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_self_endpoint_cross_corporate_impossible():
    """PUT /alerts-config/self は常に自分の法人のみ更新されること。
    payload に別の corporate_id を含めても自分の corporate_id で upsert されること。"""
    from app.api.routes.alerts_config import update_alerts_config_self

    other_corporate_id = str(ObjectId())  # 別法人の ID

    employees_col = MagicMock()
    employees_col.find_one = AsyncMock(return_value=ACCOUNTING_DOC)
    alerts_config_col = make_col()
    mock_db = build_mock_db({
        "corporates": make_col(find_one=None),
        "employees": employees_col,
        "alerts_config": alerts_config_col,
    })

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        result = await update_alerts_config_self(
            {
                "corporate_id": other_corporate_id,  # 別法人 ID を混入（無視されるべき）
                "email_enabled": {"rejected_stale_alert": True},
            },
            {"uid": ACCOUNTING_UID},
        )

    assert result["status"] == "updated"
    # upsert フィルタが自分の corporate_id（CORP_C_ID）であること
    call_filter = alerts_config_col.update_one.call_args[0][0]
    assert call_filter["corporate_id"] == CORP_C_ID
    assert call_filter["corporate_id"] != other_corporate_id


@pytest.mark.asyncio
async def test_tax_firm_endpoint_still_blocked_for_corporate():
    """一般法人ユーザーが PUT /{corporate_id}（税理士法人専用）を叩くと 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.alerts_config import update_alerts_config

    # 一般法人ユーザーのドキュメント
    corp_user_doc = {
        "_id": ObjectId(),
        "firebase_uid": CORP_C_FIREBASE_UID,
        "corporateType": "corporate",
    }
    corporates_col = make_col(find_one=corp_user_doc)
    mock_db = build_mock_db({"corporates": corporates_col})

    with patch("app.api.routes.alerts_config.get_database", return_value=mock_db):
        with pytest.raises(HTTPException) as exc:
            await update_alerts_config(
                CORP_C_ID,
                {"rejected_stale_days": 3},
                {"uid": CORP_C_FIREBASE_UID},
            )
    assert exc.value.status_code == 403
