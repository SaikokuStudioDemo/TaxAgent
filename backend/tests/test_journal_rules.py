"""
Tests for JournalRules CRUD endpoints + tenant isolation.

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_journal_rules.py -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.db.mongodb import get_database


# ─────────────── Fixtures ───────────────

@pytest_asyncio.fixture
async def registered_corp(client: AsyncClient):
    """
    Register a tax firm corporate so get_corporate_context can resolve the UID.
    conftest の clear_db が毎テスト前に corporates を削除するため、
    CRUD テストの前にこの fixture で corporate を作成する。
    """
    resp = await client.post("/api/v1/users/register", json={
        "corporateType": "tax_firm",
        "planId": "plan-standard",
        "monthlyFee": 30000,
    })
    assert resp.status_code == 201
    return resp.json()["data"]


_RULE_PAYLOAD = {
    "name": "テスト仕訳ルール",
    "keyword": "AMAZON",
    "target_field": "取引先名",
    "account_subject": "消耗品費",
    "tax_division": "課税仕入 10%",
    "is_active": True,
}


# ─────────────── CRUD ───────────────

async def test_create_journal_rule(client: AsyncClient, registered_corp):
    """POST /journal-rules でルールを作成できること。"""
    resp = await client.post("/api/v1/journal-rules", json=_RULE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["keyword"] == "AMAZON"
    assert data["account_subject"] == "消耗品費"
    assert data["tax_division"] == "課税仕入 10%"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


async def test_list_journal_rules(client: AsyncClient, registered_corp):
    """GET /journal-rules で作成したルールが一覧に含まれること。"""
    create_resp = await client.post("/api/v1/journal-rules", json=_RULE_PAYLOAD)
    assert create_resp.status_code == 200
    created_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/journal-rules")
    assert list_resp.status_code == 200
    ids = [r["id"] for r in list_resp.json()]
    assert created_id in ids


async def test_patch_journal_rule_updates_account_subject(client: AsyncClient, registered_corp):
    """PATCH /journal-rules/{id} で勘定科目が更新されること。"""
    create_resp = await client.post("/api/v1/journal-rules", json=_RULE_PAYLOAD)
    rule_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/api/v1/journal-rules/{rule_id}", json={"account_subject": "通信費"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["account_subject"] == "通信費"
    # 他フィールドは変わっていないこと
    assert patch_resp.json()["keyword"] == _RULE_PAYLOAD["keyword"]


async def test_patch_journal_rule_deactivate(client: AsyncClient, registered_corp):
    """PATCH で is_active を False に変更できること。"""
    create_resp = await client.post("/api/v1/journal-rules", json=_RULE_PAYLOAD)
    rule_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/api/v1/journal-rules/{rule_id}", json={"is_active": False})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False


async def test_delete_journal_rule(client: AsyncClient, registered_corp):
    """DELETE /journal-rules/{id} でルールが削除されること。"""
    create_resp = await client.post("/api/v1/journal-rules", json=_RULE_PAYLOAD)
    rule_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/journal-rules/{rule_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    list_resp = await client.get("/api/v1/journal-rules")
    ids = [r["id"] for r in list_resp.json()]
    assert rule_id not in ids


async def test_patch_nonexistent_rule_returns_404(client: AsyncClient, registered_corp):
    """存在しない ID に PATCH すると 404 が返ること。"""
    from bson import ObjectId
    fake_id = str(ObjectId())
    resp = await client.patch(f"/api/v1/journal-rules/{fake_id}", json={"keyword": "幻のキーワード"})
    assert resp.status_code == 404


async def test_delete_nonexistent_rule_returns_404(client: AsyncClient, registered_corp):
    """存在しない ID に DELETE すると 404 が返ること。"""
    from bson import ObjectId
    fake_id = str(ObjectId())
    resp = await client.delete(f"/api/v1/journal-rules/{fake_id}")
    assert resp.status_code == 404


# ─────────────── テナント分離 ───────────────

async def test_tenant_isolation(client: AsyncClient, registered_corp):
    """他テナントが作成したルールは一覧に含まれないこと。"""
    db = get_database()

    # 別テナントのルールを DB に直接挿入
    from datetime import datetime
    other_corp_id = "other_corp_000000000000"
    await db["journal_rules"].insert_one({
        "name": "他社仕訳ルール",
        "keyword": "他社キーワード",
        "target_field": "品目・摘要",
        "account_subject": "交際費",
        "tax_division": "課税仕入 10%",
        "is_active": True,
        "corporate_id": other_corp_id,
        "created_at": datetime.utcnow(),
    })

    list_resp = await client.get("/api/v1/journal-rules")
    assert list_resp.status_code == 200
    keywords = [r["keyword"] for r in list_resp.json()]
    assert "他社キーワード" not in keywords


# ─────────────── フォールバックロジック (Service Unit Tests) ───────────────

from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId as BsonObjectId
from app.services.journal_rule_service import apply_journal_rules


def _make_cursor(items):
    c = MagicMock()
    c.sort = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=items)))
    return c


def _make_fallback_db(corp_id: str, corporate_rules, tax_firm_rules=None, *, has_tax_firm=True, journal_map_value=None):
    tf_oid = BsonObjectId()

    corp_doc = {"_id": BsonObjectId(corp_id), "advising_tax_firm_id": "tf_firebase_uid" if has_tax_firm else None}
    tf_doc = {"_id": tf_oid, "firebase_uid": "tf_firebase_uid"} if has_tax_firm else None

    jrc = MagicMock()
    def _find(query):
        cid = query.get("corporate_id", "")
        items = corporate_rules if cid == corp_id else (tax_firm_rules or [])
        return _make_cursor(items)
    jrc.find = MagicMock(side_effect=_find)

    cc = MagicMock()
    async def _find_one_corp(query):
        if "_id" in query:
            return corp_doc if query["_id"] == BsonObjectId(corp_id) else None
        if "firebase_uid" in query:
            return tf_doc if has_tax_firm and query.get("firebase_uid") == "tf_firebase_uid" else None
        return None
    cc.find_one = AsyncMock(side_effect=_find_one_corp)

    sc = MagicMock()
    sc.find_one = AsyncMock(
        return_value={"key": "journal_map", "value": journal_map_value} if journal_map_value else None
    )

    db = MagicMock()
    _map = {"journal_rules": jrc, "corporates": cc, "system_settings": sc}
    db.__getitem__ = MagicMock(side_effect=lambda k: _map.get(k, MagicMock()))
    return db, jrc


@pytest.mark.asyncio
async def test_fallback_to_tax_firm_rules():
    """配下法人のルールに一致しない場合に税理士法人のルールが適用されること。"""
    corp_id = str(BsonObjectId())
    tf_rule_oid = BsonObjectId()
    tax_firm_rules = [{
        "_id": tf_rule_oid,
        "keyword": "電車",
        "target_field": "取引先名",
        "account_subject": "旅費交通費",
        "is_active": True,
    }]
    db, _ = _make_fallback_db(corp_id, corporate_rules=[], tax_firm_rules=tax_firm_rules)

    result = await apply_journal_rules(db, corp_id, [{"payee": "電車代", "category": ""}], "receipt")
    assert result[0]["category"] == "旅費交通費"
    assert result[0]["applied_journal_rule_id"] == str(tf_rule_oid)


@pytest.mark.asyncio
async def test_corporate_rule_takes_priority():
    """配下法人と税理士法人に同じキーワードのルールがある場合に配下法人のルールが優先されること。"""
    corp_id = str(BsonObjectId())
    corp_rule_oid = BsonObjectId()
    tf_rule_oid = BsonObjectId()

    corporate_rules = [{
        "_id": corp_rule_oid,
        "keyword": "電車",
        "target_field": "取引先名",
        "account_subject": "旅費交通費",
        "is_active": True,
        "corporate_id": corp_id,
    }]
    tax_firm_rules = [{
        "_id": tf_rule_oid,
        "keyword": "電車",
        "target_field": "取引先名",
        "account_subject": "交際費",  # 意図的に違う科目
        "is_active": True,
    }]
    db, _ = _make_fallback_db(corp_id, corporate_rules=corporate_rules, tax_firm_rules=tax_firm_rules)

    result = await apply_journal_rules(db, corp_id, [{"payee": "電車代", "category": ""}], "receipt")
    assert result[0]["category"] == "旅費交通費"
    assert result[0]["applied_journal_rule_id"] == str(corp_rule_oid)


@pytest.mark.asyncio
async def test_fallback_to_journal_map():
    """配下法人・税理士法人のどちらにも一致しない場合にAdmin標準マスターが適用されること。"""
    corp_id = str(BsonObjectId())
    custom_map = {
        "テスト科目": {
            "debit": "テスト科目", "credit": "未払金",
            "tax_category": "課税仕入 10%",
            "keywords": ["タクシー"],
        }
    }
    db, _ = _make_fallback_db(corp_id, corporate_rules=[], tax_firm_rules=[], journal_map_value=custom_map)

    result = await apply_journal_rules(db, corp_id, [{"payee": "タクシー乗車", "category": ""}], "receipt")
    assert result[0]["category"] == "テスト科目"
    assert result[0]["applied_journal_map_subject"] == "テスト科目"


@pytest.mark.asyncio
async def test_no_tax_firm_no_fallback():
    """税理士法人未紐付けの法人では税理士法人ルールの検索が行われないこと。"""
    corp_id = str(BsonObjectId())
    corp_rule_oid = BsonObjectId()
    corporate_rules = [{
        "_id": corp_rule_oid,
        "keyword": "AMAZON",
        "target_field": "取引先名",
        "account_subject": "消耗品費",
        "is_active": True,
    }]
    db, jrc = _make_fallback_db(corp_id, corporate_rules=corporate_rules, has_tax_firm=False)

    result = await apply_journal_rules(db, corp_id, [{"payee": "AMAZON購入", "category": ""}], "receipt")
    assert result[0]["category"] == "消耗品費"
    # 税理士法人ルールの検索は発生しない（配下法人分1回のみ）
    assert jrc.find.call_count == 1


# ─────────────── ① 境界値テスト ───────────────

@pytest.mark.asyncio
async def test_corporate_rule_matches_partial_keyword():
    """配下法人ルールのキーワードが取引先名に部分一致する場合に適用されること（完全一致不要）。"""
    corp_id = str(BsonObjectId())
    rule_oid = BsonObjectId()
    corporate_rules = [{
        "_id": rule_oid,
        "keyword": "Amazon",
        "target_field": "取引先名",
        "account_subject": "消耗品費",
        "is_active": True,
    }]
    db, _ = _make_fallback_db(corp_id, corporate_rules=corporate_rules)

    result = await apply_journal_rules(db, corp_id, [{"payee": "Amazon Japan合同会社", "category": ""}], "receipt")
    assert result[0]["category"] == "消耗品費"
    assert result[0]["applied_journal_rule_id"] == str(rule_oid)


@pytest.mark.asyncio
async def test_tax_firm_rule_applied_when_no_corporate_match():
    """配下法人にルールがあるがキーワードが一致しない場合に税理士法人のルールが適用されること。"""
    corp_id = str(BsonObjectId())
    tf_rule_oid = BsonObjectId()
    corporate_rules = [{
        "_id": BsonObjectId(),
        "keyword": "AMAZON",
        "target_field": "取引先名",
        "account_subject": "消耗品費",
        "is_active": True,
    }]
    tax_firm_rules = [{
        "_id": tf_rule_oid,
        "keyword": "タクシー",
        "target_field": "取引先名",
        "account_subject": "旅費交通費",
        "is_active": True,
    }]
    db, _ = _make_fallback_db(corp_id, corporate_rules=corporate_rules, tax_firm_rules=tax_firm_rules)

    # AMAZONルールは一致しない → タクシールール（税理士法人）が適用される
    result = await apply_journal_rules(db, corp_id, [{"payee": "タクシー乗車", "category": ""}], "receipt")
    assert result[0]["category"] == "旅費交通費"
    assert result[0]["applied_journal_rule_id"] == str(tf_rule_oid)


@pytest.mark.asyncio
async def test_journal_map_keyword_partial_match():
    """Admin標準マスターのキーワードが line_items の摘要に部分一致する場合にその科目に分類されること。"""
    corp_id = str(BsonObjectId())
    custom_map = {
        "旅費交通費": {
            "debit": "旅費交通費", "credit": "未払金",
            "tax_category": "課税仕入 10%",
            "keywords": ["タクシー"],
        }
    }
    db, _ = _make_fallback_db(corp_id, corporate_rules=[], tax_firm_rules=[], journal_map_value=custom_map)

    doc = {"payee": "", "line_items": [{"description": "タクシー代金 1,200円"}], "category": ""}
    result = await apply_journal_rules(db, corp_id, [doc], "receipt")
    assert result[0]["category"] == "旅費交通費"
    assert result[0]["applied_journal_map_subject"] == "旅費交通費"


@pytest.mark.asyncio
async def test_no_match_returns_original_doc():
    """配下法人・税理士法人・Admin標準いずれにも一致しない場合に元のドキュメントがそのまま返ること。"""
    corp_id = str(BsonObjectId())
    custom_map = {
        "消耗品費": {
            "debit": "消耗品費", "credit": "未払金",
            "tax_category": "課税仕入 10%",
            "keywords": ["文具"],
        }
    }
    db, _ = _make_fallback_db(corp_id, corporate_rules=[], tax_firm_rules=[], journal_map_value=custom_map)

    doc = {"payee": "未知の取引先XYZ", "category": "未分類"}
    result = await apply_journal_rules(db, corp_id, [doc], "receipt")
    # category は変化しない
    assert result[0]["category"] == "未分類"
    assert "applied_journal_rule_id" not in result[0]
    assert "applied_journal_map_subject" not in result[0]


@pytest.mark.asyncio
async def test_inactive_rule_not_applied():
    """is_active=False のルールが適用されないこと（DBクエリが is_active:True で発行されること）。"""
    corp_id = str(BsonObjectId())
    tf_rule_oid = BsonObjectId()
    # corp_rules=[] はDBが is_active:True でフィルタした結果（非アクティブルールは返らない）
    tax_firm_rules = [{
        "_id": tf_rule_oid,
        "keyword": "Amazon",
        "target_field": "取引先名",
        "account_subject": "消耗品費",
        "is_active": True,
    }]
    db, jrc = _make_fallback_db(corp_id, corporate_rules=[], tax_firm_rules=tax_firm_rules)

    result = await apply_journal_rules(db, corp_id, [{"payee": "Amazon購入", "category": ""}], "receipt")
    # 非アクティブ配下法人ルールはスキップ → 税理士法人ルールが適用される
    assert result[0]["category"] == "消耗品費"
    # DBクエリに is_active: True が含まれていること
    corp_query = jrc.find.call_args_list[0][0][0]
    assert corp_query.get("is_active") is True


@pytest.mark.asyncio
async def test_tax_firm_inactive_rule_skipped():
    """税理士法人のルールが is_active=False の場合にAdmin標準マスターにフォールバックすること。"""
    corp_id = str(BsonObjectId())
    custom_map = {
        "旅費交通費": {
            "debit": "旅費交通費", "credit": "未払金",
            "tax_category": "課税仕入 10%",
            "keywords": ["タクシー"],
        }
    }
    # tax_firm_rules=[] はDBが非アクティブルールをフィルタ済みの状態
    db, jrc = _make_fallback_db(corp_id, corporate_rules=[], tax_firm_rules=[], journal_map_value=custom_map)

    result = await apply_journal_rules(db, corp_id, [{"payee": "タクシー乗車", "category": ""}], "receipt")
    # 税理士法人ルールなし → Admin標準マスターが適用される
    assert result[0]["category"] == "旅費交通費"
    # 税理士法人用クエリも is_active: True を含むこと
    tf_query = jrc.find.call_args_list[1][0][0]
    assert tf_query.get("is_active") is True


# ─────────────── ② 優先順位テスト ───────────────

@pytest.mark.asyncio
async def test_same_keyword_corporate_wins():
    """配下法人と税理士法人に同じキーワードがある場合に配下法人のルールが優先され、税理士法人のルールが適用されないこと。"""
    corp_id = str(BsonObjectId())
    corp_rule_oid = BsonObjectId()
    tf_rule_oid = BsonObjectId()

    corporate_rules = [{
        "_id": corp_rule_oid,
        "keyword": "タクシー",
        "target_field": "取引先名",
        "account_subject": "旅費交通費",
        "is_active": True,
    }]
    tax_firm_rules = [{
        "_id": tf_rule_oid,
        "keyword": "タクシー",
        "target_field": "取引先名",
        "account_subject": "交際費",  # 異なる科目
        "is_active": True,
    }]
    db, _ = _make_fallback_db(corp_id, corporate_rules=corporate_rules, tax_firm_rules=tax_firm_rules)

    result = await apply_journal_rules(db, corp_id, [{"payee": "タクシー乗車", "category": ""}], "receipt")
    assert result[0]["category"] == "旅費交通費"
    assert result[0]["applied_journal_rule_id"] == str(corp_rule_oid)
    # 税理士法人ルールの ID が適用されていないこと
    assert result[0]["applied_journal_rule_id"] != str(tf_rule_oid)


@pytest.mark.asyncio
async def test_same_keyword_tax_firm_wins_over_map():
    """税理士法人ルールとAdmin標準マスターに同じキーワードがある場合に税理士法人のルールが優先されること。"""
    corp_id = str(BsonObjectId())
    tf_rule_oid = BsonObjectId()
    tax_firm_rules = [{
        "_id": tf_rule_oid,
        "keyword": "タクシー",
        "target_field": "取引先名",
        "account_subject": "旅費交通費",
        "is_active": True,
    }]
    # Admin標準マスターも同じキーワードで違う科目
    custom_map = {
        "交通費（汎用）": {
            "debit": "交通費（汎用）", "credit": "未払金",
            "tax_category": "課税仕入 10%",
            "keywords": ["タクシー"],
        }
    }
    db, _ = _make_fallback_db(corp_id, corporate_rules=[], tax_firm_rules=tax_firm_rules, journal_map_value=custom_map)

    result = await apply_journal_rules(db, corp_id, [{"payee": "タクシー乗車", "category": ""}], "receipt")
    # 税理士法人ルールが優先される
    assert result[0]["category"] == "旅費交通費"
    assert result[0]["applied_journal_rule_id"] == str(tf_rule_oid)
    assert "applied_journal_map_subject" not in result[0]


# ─────────────── ③ スコープテスト ───────────────

@pytest.mark.asyncio
async def test_other_corporate_rules_not_applied():
    """別法人の journal_rules が適用されないこと（クエリに自分の corporate_id のみ使われること）。"""
    corp_id = str(BsonObjectId())
    corporate_rules = [{
        "_id": BsonObjectId(),
        "keyword": "Amazon",
        "target_field": "取引先名",
        "account_subject": "消耗品費",
        "is_active": True,
    }]
    db, jrc = _make_fallback_db(corp_id, corporate_rules=corporate_rules, has_tax_firm=False)

    await apply_journal_rules(db, corp_id, [{"payee": "Amazon購入", "category": ""}], "receipt")
    # 最初のfindクエリのcorporate_idが自分のIDであること
    corp_query = jrc.find.call_args_list[0][0][0]
    assert corp_query["corporate_id"] == corp_id


@pytest.mark.asyncio
async def test_unrelated_tax_firm_rules_not_applied():
    """自分の advising_tax_firm_id ではない別の税理士法人のルールが適用されないこと。"""
    corp_id = str(BsonObjectId())
    # has_tax_firm=True のとき advising_tax_firm_id = "tf_firebase_uid" のみ参照される
    db, _ = _make_fallback_db(corp_id, corporate_rules=[], tax_firm_rules=[], has_tax_firm=True)
    cc = db["corporates"]

    await apply_journal_rules(db, corp_id, [{"payee": "何かの取引", "category": ""}], "receipt")

    # corporates.find_one は自分のadvisedTaxFirmのfirebase_uidでのみ呼ばれること
    uid_queries = [
        call[0][0].get("firebase_uid")
        for call in cc.find_one.call_args_list
        if "firebase_uid" in call[0][0]
    ]
    assert all(uid == "tf_firebase_uid" for uid in uid_queries)
    assert "other_tf_firebase_uid" not in uid_queries


@pytest.mark.asyncio
async def test_independent_corporate_no_tax_firm_fallback():
    """advising_tax_firm_id が未設定の法人では税理士法人ルール検索が発生せず、Admin標準マスターには進むこと。"""
    corp_id = str(BsonObjectId())
    custom_map = {
        "消耗品費": {
            "debit": "消耗品費", "credit": "未払金",
            "tax_category": "課税仕入 10%",
            "keywords": ["文具"],
        }
    }
    db, jrc = _make_fallback_db(corp_id, corporate_rules=[], has_tax_firm=False, journal_map_value=custom_map)

    result = await apply_journal_rules(db, corp_id, [{"payee": "文具購入", "category": ""}], "receipt")
    # Admin標準マスターが適用されること
    assert result[0]["category"] == "消耗品費"
    # 税理士法人ルールの検索は1回（配下法人分）のみ
    assert jrc.find.call_count == 1


# ─────────────── ④ Admin勘定科目マスターのテスト ───────────────

from unittest.mock import patch as _patch
from httpx import ASGITransport
from app.main import app as _app
from app.api.deps import get_current_user as _get_current_user, verify_admin as _verify_admin
from app.core.config import settings as _settings

_ADMIN_UID_JM = "admin_uid_journal_map_test"
_VALID_JM = {
    "新科目": {
        "debit": "新科目", "credit": "未払金",
        "tax_category": "課税仕入 10%",
        "keywords": ["新キーワード"],
    }
}


def _set_jm_admin():
    _app.dependency_overrides[_get_current_user] = lambda: {"uid": _ADMIN_UID_JM, "email": "admin@test.com"}
    _app.dependency_overrides.pop(_verify_admin, None)


def _make_jm_db(find_one_return=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one_return)
    col.update_one = AsyncMock(return_value=MagicMock())
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)
    return db, col


@pytest.fixture(autouse=False)
def _jm_admin_setup(monkeypatch):
    monkeypatch.setattr(_settings, "ADMIN_UIDS", [_ADMIN_UID_JM])
    yield
    _app.dependency_overrides[_get_current_user] = lambda: {"uid": "test_tax_firm_uid"}
    _app.dependency_overrides.pop(_verify_admin, None)


@pytest.mark.asyncio
async def test_journal_map_update_affects_fallback(_jm_admin_setup):
    """Admin が勘定科目マスターを更新した後に新しい科目でマッチングが機能すること。"""
    corp_id = str(BsonObjectId())
    updated_map = {
        "新勘定科目": {
            "debit": "新勘定科目", "credit": "未払金",
            "tax_category": "課税仕入 10%",
            "keywords": ["新キーワード"],
        }
    }
    db, _ = _make_fallback_db(corp_id, corporate_rules=[], tax_firm_rules=[], journal_map_value=updated_map)

    result = await apply_journal_rules(db, corp_id, [{"payee": "新キーワードを含む取引先", "category": ""}], "receipt")
    assert result[0]["category"] == "新勘定科目"
    assert result[0]["applied_journal_map_subject"] == "新勘定科目"


@pytest.mark.asyncio
async def test_journal_map_empty_keywords_rejected(_jm_admin_setup):
    """keywords が空配列の科目で 400 が返ること。"""
    _set_jm_admin()
    bad_map = {
        "消耗品費": {
            "debit": "消耗品費", "credit": "未払金",
            "tax_category": "課税仕入 10%",
            "keywords": [],  # 空配列
        }
    }
    db, _ = _make_jm_db()
    with _patch("app.api.routes.system_settings.get_database", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as client:
            res = await client.put(
                "/api/v1/system-settings/journal-map",
                json={"journal_map": bad_map},
                headers={"Authorization": "Bearer test"},
            )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_journal_map_put_requires_all_fields(_jm_admin_setup):
    """debit・credit・tax_category・keywords のいずれかが欠けると 400 が返ること。"""
    _set_jm_admin()
    base_entry = {"debit": "消耗品費", "credit": "未払金", "tax_category": "課税仕入 10%", "keywords": ["文具"]}
    for missing_key in ("debit", "credit", "tax_category", "keywords"):
        entry = {k: v for k, v in base_entry.items() if k != missing_key}
        db, _ = _make_jm_db()
        with _patch("app.api.routes.system_settings.get_database", return_value=db):
            async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/system-settings/journal-map",
                    json={"journal_map": {"消耗品費": entry}},
                    headers={"Authorization": "Bearer test"},
                )
        assert res.status_code == 400, f"{missing_key} が欠けた場合に 400 が返ること"
