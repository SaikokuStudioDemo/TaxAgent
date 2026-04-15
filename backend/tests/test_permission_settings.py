"""
Tests for Task#10: permission_settings endpoints.
追加テスト（意地悪版）:
  ① 権限昇格攻撃   - staff/accounting は PUT 不可、未知キー拒否、空リスト NOP、部分更新
  ② データ整合性   - min_role 不正値拒否、全7件保証、デフォルト上書き確認
  ③ project_members - role デフォルト、不正 role 拒否、ロール変更、既存 DB フォールバック
  ⑤ 境界値         - min_role 階層値が API から正しく返る
"""
import pytest
import pytest_asyncio
from datetime import datetime

from app.main import app
from app.db.mongodb import get_database
from app.api.deps import get_current_user
from app.api.routes.permission_settings import (
    DEFAULT_PERMISSIONS,
    FLEXIBLE_FEATURE_KEYS,
    VALID_MIN_ROLES,
)

CORP_UID       = "perm_test_corporate_uid"
STAFF_UID      = "perm_test_staff_uid"
ACCOUNTING_UID = "perm_test_accounting_uid"


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def clear_permission_settings():
    db = get_database()
    for col in ["permission_settings", "projects", "project_members"]:
        await db[col].delete_many({})
    yield
    for col in ["permission_settings", "projects", "project_members"]:
        await db[col].delete_many({})


@pytest_asyncio.fixture
async def corp_setup():
    """法人代表（admin扱い）と staff を DB に登録し、認証を切り替えるフィクスチャ。"""
    db = get_database()

    corp_res = await db["corporates"].insert_one({
        "firebase_uid": CORP_UID,
        "corporateType": "corporate",
        "companyName": "権限テスト法人",
    })
    corp_id = str(corp_res.inserted_id)

    await db["employees"].insert_one({
        "firebase_uid": STAFF_UID,
        "corporate_id": corp_id,
        "role": "staff",
        "name": "テストスタッフ",
    })
    await db["employees"].insert_one({
        "firebase_uid": ACCOUNTING_UID,
        "corporate_id": corp_id,
        "role": "accounting",
        "name": "テスト経理",
    })

    yield {"corp_id": corp_id, "staff_uid": STAFF_UID, "accounting_uid": ACCOUNTING_UID}

    # Reset auth to default
    app.dependency_overrides[get_current_user] = lambda: {"uid": "test_tax_firm_uid"}


@pytest_asyncio.fixture
async def project_setup(corp_setup):
    """プロジェクト + メンバー用追加フィクスチャ。corp_setup に依存。"""
    db = get_database()
    result = await db["projects"].insert_one({
        "corporate_id": corp_setup["corp_id"],
        "name": "テストプロジェクト",
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    project_id = str(result.inserted_id)

    # staff_member として使う employee を取得
    emp = await db["employees"].find_one({"firebase_uid": STAFF_UID})
    staff_emp_id = str(emp["_id"])

    yield {**corp_setup, "project_id": project_id, "staff_emp_id": staff_emp_id}


def _auth_as(uid: str):
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_permissions_returns_all_features(client, corp_setup):
    """
    DB が空の状態でも GET /permission-settings が
    DEFAULT_PERMISSIONS の全機能キーを返すことを確認する。
    """
    _auth_as(CORP_UID)
    resp = await client.get("/api/v1/permission-settings")
    assert resp.status_code == 200

    data = resp.json()
    returned_keys = {item["feature_key"] for item in data}

    # 全7キーが揃っていること
    assert returned_keys == set(DEFAULT_PERMISSIONS.keys())
    assert len(data) == len(DEFAULT_PERMISSIONS)

    # DB に未設定の項目は is_default=True
    for item in data:
        assert item["is_default"] is True
        assert "min_role" in item
        assert "require_approval" in item


@pytest.mark.asyncio
async def test_admin_can_update_permissions(client, corp_setup):
    """admin ロール（法人代表）は PUT /permission-settings が成功する。"""
    _auth_as(CORP_UID)

    payload = [
        {"feature_key": "report_view", "min_role": "staff", "require_approval": False},
    ]
    resp = await client.put("/api/v1/permission-settings", json=payload)
    assert resp.status_code == 200
    assert "report_view" in resp.json()["updated"]


@pytest.mark.asyncio
async def test_non_admin_cannot_update(client, corp_setup):
    """staff ロールは PUT /permission-settings で 403 が返る。"""
    _auth_as(STAFF_UID)

    payload = [
        {"feature_key": "report_view", "min_role": "staff", "require_approval": False},
    ]
    resp = await client.put("/api/v1/permission-settings", json=payload)
    assert resp.status_code == 403
    assert "管理者のみ" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_fixed_permission_key_rejected(client, corp_setup):
    """
    DEFAULT_PERMISSIONS に存在しないキー（固定権限扱い）を
    PUT で送ると 400 が返ることを確認する。
    """
    _auth_as(CORP_UID)

    payload = [
        {"feature_key": "user_management", "min_role": "staff", "require_approval": False},
    ]
    resp = await client.put("/api/v1/permission-settings", json=payload)
    assert resp.status_code == 400
    assert "変更できない権限キー" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_updated_permission_persists(client, corp_setup):
    """PUT で更新した値が GET で正しく取得できることを確認する。"""
    _auth_as(CORP_UID)

    # ai_chat_basic を staff → manager に変更
    payload = [
        {"feature_key": "ai_chat_basic", "min_role": "manager", "require_approval": False},
    ]
    put_resp = await client.put("/api/v1/permission-settings", json=payload)
    assert put_resp.status_code == 200

    # GET で確認
    get_resp = await client.get("/api/v1/permission-settings")
    assert get_resp.status_code == 200

    ai_chat_entry = next(
        (item for item in get_resp.json() if item["feature_key"] == "ai_chat_basic"),
        None,
    )
    assert ai_chat_entry is not None
    assert ai_chat_entry["min_role"] == "manager"
    assert ai_chat_entry["is_default"] is False  # DB に保存済みなのでデフォルトではない


@pytest.mark.asyncio
async def test_accounting_can_read_permissions(client, corp_setup):
    """accounting ロールも GET /permission-settings で読み取りできる。"""
    _auth_as(ACCOUNTING_UID)

    resp = await client.get("/api/v1/permission-settings")
    assert resp.status_code == 200
    assert len(resp.json()) == len(DEFAULT_PERMISSIONS)


@pytest.mark.asyncio
async def test_flexible_feature_keys_match_defaults(client, corp_setup):
    """FLEXIBLE_FEATURE_KEYS と DEFAULT_PERMISSIONS のキーが一致することを確認する。"""
    assert FLEXIBLE_FEATURE_KEYS == set(DEFAULT_PERMISSIONS.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# ① 権限昇格攻撃テスト
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_staff_cannot_update_permissions(client, corp_setup):
    """staff は PUT /permission-settings で 403 が返る（昇格攻撃拒否）。"""
    _auth_as(STAFF_UID)
    payload = [{"feature_key": "ai_chat_basic", "min_role": "staff", "require_approval": False}]
    resp = await client.put("/api/v1/permission-settings", json=payload)
    assert resp.status_code == 403
    assert "管理者のみ" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_accounting_cannot_update_permissions(client, corp_setup):
    """accounting も PUT /permission-settings で 403 が返る（admin 専用）。"""
    _auth_as(ACCOUNTING_UID)
    payload = [{"feature_key": "ai_chat_basic", "min_role": "staff", "require_approval": False}]
    resp = await client.put("/api/v1/permission-settings", json=payload)
    assert resp.status_code == 403
    assert "管理者のみ" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unknown_feature_key_rejected(client, corp_setup):
    """任意の未知キー（super_admin_mode・delete_all_data）は 400 で拒否される。"""
    _auth_as(CORP_UID)
    for bad_key in ["super_admin_mode", "delete_all_data", "hack_the_system"]:
        resp = await client.put(
            "/api/v1/permission-settings",
            json=[{"feature_key": bad_key, "min_role": "staff", "require_approval": False}],
        )
        assert resp.status_code == 400, f"expected 400 for key '{bad_key}'"
        assert "変更できない権限キー" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_empty_list_put_is_noop(client, corp_setup):
    """PUT で空リスト [] を送ると 200 が返り DB は変更されない。"""
    _auth_as(CORP_UID)
    resp = await client.put("/api/v1/permission-settings", json=[])
    assert resp.status_code == 200
    assert resp.json()["updated"] == []

    db = get_database()
    count = await db["permission_settings"].count_documents({"corporate_id": corp_setup["corp_id"]})
    assert count == 0  # DB は空のまま


@pytest.mark.asyncio
async def test_partial_update_does_not_reset_others(client, corp_setup):
    """
    全7件を PUT したあと1件だけ PUT しても、残り6件の値はリセットされない。
    upsert による部分更新の正確性確認。
    """
    _auth_as(CORP_UID)

    # Step1: 全7件を min_role='manager' で書き込む
    all_payload = [
        {"feature_key": key, "min_role": "manager", "require_approval": False}
        for key in DEFAULT_PERMISSIONS.keys()
    ]
    r1 = await client.put("/api/v1/permission-settings", json=all_payload)
    assert r1.status_code == 200

    # Step2: 1件だけ min_role='admin' に変更
    r2 = await client.put(
        "/api/v1/permission-settings",
        json=[{"feature_key": "report_view", "min_role": "admin", "require_approval": False}],
    )
    assert r2.status_code == 200

    # Step3: GET で全件確認
    r3 = await client.get("/api/v1/permission-settings")
    assert r3.status_code == 200
    data = {item["feature_key"]: item for item in r3.json()}

    assert data["report_view"]["min_role"] == "admin"           # 更新された
    for key in DEFAULT_PERMISSIONS.keys():
        if key != "report_view":
            assert data[key]["min_role"] == "manager", f"{key} が意図せずリセットされた"


# ═══════════════════════════════════════════════════════════════════════════════
# ② データ整合性テスト
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_min_role_invalid_value_rejected(client, corp_setup):
    """存在しないロール名（superuser・god・空文字）は 400 で拒否される。"""
    _auth_as(CORP_UID)
    for bad_role in ["superuser", "god", "", "root", "owner"]:
        resp = await client.put(
            "/api/v1/permission-settings",
            json=[{"feature_key": "ai_chat_basic", "min_role": bad_role, "require_approval": False}],
        )
        assert resp.status_code == 400, f"expected 400 for min_role='{bad_role}'"
        assert "無効な値" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_always_returns_all_7_features(client, corp_setup):
    """DB が完全に空でも GET で必ず全7件が返る。feature_key の集合も一致する。"""
    _auth_as(CORP_UID)
    db = get_database()
    await db["permission_settings"].delete_many({})  # 念のため空に

    resp = await client.get("/api/v1/permission-settings")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) == 7
    assert {d["feature_key"] for d in data} == set(DEFAULT_PERMISSIONS.keys())
    for item in data:
        assert item["is_default"] is True


@pytest.mark.asyncio
async def test_updated_value_overrides_default(client, corp_setup):
    """
    'ai_chat_basic' の min_role を 'admin' に変更後、
    GET で 'admin' が返り、デフォルト値 'staff' が返ってこないことを確認する。
    """
    _auth_as(CORP_UID)

    await client.put(
        "/api/v1/permission-settings",
        json=[{"feature_key": "ai_chat_basic", "min_role": "admin", "require_approval": False}],
    )

    resp = await client.get("/api/v1/permission-settings")
    entry = next(d for d in resp.json() if d["feature_key"] == "ai_chat_basic")

    assert entry["min_role"] == "admin"
    assert entry["min_role"] != DEFAULT_PERMISSIONS["ai_chat_basic"]["min_role"]  # "staff" ではない
    assert entry["is_default"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# ③ project_members の role テスト
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_project_member_default_role_is_member(client, project_setup):
    """role を指定せずメンバー追加 → GET で role='member' が返る。"""
    _auth_as(CORP_UID)
    ids = project_setup

    # role 未指定で追加
    resp = await client.post(
        f"/api/v1/projects/{ids['project_id']}/members",
        json={"user_id": ids["staff_emp_id"]},  # role フィールドなし
    )
    assert resp.status_code == 200

    members_resp = await client.get(f"/api/v1/projects/{ids['project_id']}/members")
    assert members_resp.status_code == 200
    members = members_resp.json()
    assert len(members) == 1
    assert members[0]["role"] == "member"


@pytest.mark.asyncio
async def test_project_member_invalid_role_rejected(client, project_setup):
    """
    プロジェクト外のロール（staff・superuser）でメンバー追加すると 400 が返る。
    valid: admin / approver / member のみ。
    """
    _auth_as(CORP_UID)
    ids = project_setup

    for bad_role in ["staff", "superuser", "accounting", "god"]:
        resp = await client.post(
            f"/api/v1/projects/{ids['project_id']}/members",
            json={"user_id": ids["staff_emp_id"], "role": bad_role},
        )
        assert resp.status_code == 400, f"expected 400 for role='{bad_role}'"


@pytest.mark.asyncio
async def test_project_member_role_update(client, project_setup):
    """member → approver にロール変更後、GET で変更が反映されていることを確認する。"""
    _auth_as(CORP_UID)
    ids = project_setup

    # まず member で追加
    await client.post(
        f"/api/v1/projects/{ids['project_id']}/members",
        json={"user_id": ids["staff_emp_id"], "role": "member"},
    )

    # approver に変更
    patch_resp = await client.patch(
        f"/api/v1/projects/{ids['project_id']}/members/{ids['staff_emp_id']}",
        json={"role": "approver"},
    )
    assert patch_resp.status_code == 200

    # GET で確認
    members_resp = await client.get(f"/api/v1/projects/{ids['project_id']}/members")
    members = members_resp.json()
    assert members[0]["role"] == "approver"


@pytest.mark.asyncio
async def test_existing_member_without_role_returns_member(client, project_setup):
    """
    role フィールドが存在しない既存ドキュメントを直接 DB に挿入しても、
    GET /projects/{id}/members で role='member' として返るフォールバックを確認する。
    """
    _auth_as(CORP_UID)
    ids = project_setup
    db = get_database()

    # role フィールドなしで直接 DB に挿入（旧データの再現）
    await db["project_members"].insert_one({
        "project_id": ids["project_id"],
        "employee_id": ids["staff_emp_id"],
        "joined_at": datetime.utcnow(),
        # role フィールド意図的に省略
    })

    members_resp = await client.get(f"/api/v1/projects/{ids['project_id']}/members")
    assert members_resp.status_code == 200
    members = members_resp.json()
    assert len(members) == 1
    assert members[0]["role"] == "member"  # フォールバックで 'member' になること


# ═══════════════════════════════════════════════════════════════════════════════
# ⑤ 境界値：min_role 階層テスト
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_min_role_hierarchy_respected(client, corp_setup):
    """
    'client_management' の min_role を 'accounting' に変更後、
    accounting ロールのユーザーが GET で 'accounting' を取得できることを確認する。
    API が設定値を正確に返すことの検証（アクセス制御はフロント側）。
    """
    _auth_as(CORP_UID)

    # admin で min_role を 'accounting' に変更
    await client.put(
        "/api/v1/permission-settings",
        json=[{"feature_key": "client_management", "min_role": "accounting", "require_approval": True}],
    )

    # accounting ロールで GET して確認
    _auth_as(ACCOUNTING_UID)
    resp = await client.get("/api/v1/permission-settings")
    assert resp.status_code == 200

    entry = next(d for d in resp.json() if d["feature_key"] == "client_management")
    assert entry["min_role"] == "accounting"
    assert entry["require_approval"] is True
