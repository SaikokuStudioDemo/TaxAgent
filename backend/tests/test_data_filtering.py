"""
Tests for API-level data filtering (Task#9).
Verifies that build_scope_filter returns the correct MongoDB filter
based on the user's role, department, and project memberships.

追加テスト (意地悪版):
  ① スコープ境界値テスト  - 他部門・無関係プロジェクトの遮断、自己提出の透過
  ② ロール昇格・降格テスト - accounting/manager は全件, approver は staff 扱い
  ③ 空データ・エッジケース - 部門/プロジェクトなし staff、複数プロジェクト
  ④ CorporateContext 整合性 - DB値がContextに正しく反映されるか
  ⑤ 悪意あるリクエスト    - クエリパラメータによるスコープ回避が不可能なことを確認
"""
import pytest
import pytest_asyncio
from datetime import datetime

from app.main import app
from app.db.mongodb import get_database
from app.api.deps import get_current_user
from app.api.helpers import (
    CorporateContext,
    build_scope_filter,
    FULL_ACCESS_ROLES,
    get_corporate_context,
)

# UIDs for integration tests - unique to this module to avoid collision
CORP_OWNER_UID  = "filter_corp_owner_uid"
STAFF_A_UID     = "filter_staff_a_uid"       # dept_a
STAFF_B_UID     = "filter_staff_b_uid"       # dept_b
ACCOUNTING_UID  = "filter_accounting_uid"    # dept_a, full access
MANAGER_UID     = "filter_manager_uid"       # dept_a, full access
APPROVER_UID    = "filter_approver_uid"      # dept_a, NOT full access


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_ctx(role: str, user_id: str = "user_001", department_id=None, project_ids=None) -> CorporateContext:
    return CorporateContext(
        corporate_id="corp_001",
        user_id=user_id,
        firebase_uid="fb_uid_001",
        db=None,
        role=role,
        department_id=department_id,
        project_ids=project_ids or [],
    )


def _receipt(corp_id: str, submitted_by: str, department_id: str = None, project_id: str = None) -> dict:
    doc: dict = {"corporate_id": corp_id, "submitted_by": submitted_by, "created_at": datetime.utcnow()}
    if department_id:
        doc["department_id"] = department_id
    if project_id:
        doc["project_id"] = project_id
    return doc


def _invoice(corp_id: str, submitted_by: str, department_id: str = None, project_id: str = None) -> dict:
    doc: dict = {
        "corporate_id": corp_id,
        "submitted_by": submitted_by,
        "is_deleted": False,
        "created_at": datetime.utcnow(),
    }
    if department_id:
        doc["department_id"] = department_id
    if project_id:
        doc["project_id"] = project_id
    return doc


def _auth_as(uid: str):
    """Switch the authenticated user for subsequent requests."""
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}


def _reset_auth():
    app.dependency_overrides[get_current_user] = lambda: {"uid": "test_tax_firm_uid"}


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def clear_filter_collections():
    """Clear receipts / invoices / project_members before and after every test."""
    db = get_database()
    for col in ["receipts", "invoices", "project_members"]:
        await db[col].delete_many({})
    yield
    for col in ["receipts", "invoices", "project_members"]:
        await db[col].delete_many({})


@pytest_asyncio.fixture
async def corp_setup():
    """
    Set up a corporate with employees across departments and roles.
    Yields a dict of IDs so individual tests can reference them.
    """
    db = get_database()

    corp_res = await db["corporates"].insert_one({
        "firebase_uid": CORP_OWNER_UID,
        "corporateType": "corporate",
        "companyName": "フィルターテスト法人",
    })
    corp_id = str(corp_res.inserted_id)

    async def _emp(uid, role, dept=None):
        doc = {"firebase_uid": uid, "corporate_id": corp_id, "role": role, "name": f"emp_{uid}"}
        if dept:
            doc["department_id"] = dept
        r = await db["employees"].insert_one(doc)
        return str(r.inserted_id)

    staff_a_id   = await _emp(STAFF_A_UID,    "staff",      "dept_a")
    staff_b_id   = await _emp(STAFF_B_UID,    "staff",      "dept_b")
    accounting_id = await _emp(ACCOUNTING_UID, "accounting", "dept_a")
    manager_id   = await _emp(MANAGER_UID,    "manager",    "dept_a")
    approver_id  = await _emp(APPROVER_UID,   "approver",   "dept_a")

    yield {
        "corp_id":       corp_id,
        "staff_a_id":    staff_a_id,
        "staff_b_id":    staff_b_id,
        "accounting_id": accounting_id,
        "manager_id":    manager_id,
        "approver_id":   approver_id,
    }

    _reset_auth()


# ═══════════════════════════════════════════════════════════════════════════════
# [Original] Unit tests — build_scope_filter pure logic
# ═══════════════════════════════════════════════════════════════════════════════

def test_admin_gets_no_scope_filter():
    """admin → empty filter (sees everything)."""
    assert build_scope_filter(_make_ctx("admin")) == {}


def test_accounting_gets_no_scope_filter():
    """accounting → empty filter."""
    assert build_scope_filter(_make_ctx("accounting")) == {}


def test_manager_gets_no_scope_filter():
    """manager → empty filter."""
    assert build_scope_filter(_make_ctx("manager")) == {}


def test_staff_with_department_gets_or_filter():
    """staff + department → $or with submitted_by and department_id."""
    ctx = _make_ctx("staff", department_id="dept_sales")
    result = build_scope_filter(ctx)
    assert "$or" in result
    assert {"submitted_by": "user_001"} in result["$or"]
    assert {"department_id": "dept_sales"} in result["$or"]


def test_staff_with_projects_gets_or_filter():
    """staff + projects → $or with submitted_by and project_id $in."""
    ctx = _make_ctx("staff", project_ids=["proj_a", "proj_b"])
    result = build_scope_filter(ctx)
    assert "$or" in result
    assert {"submitted_by": "user_001"} in result["$or"]
    assert {"project_id": {"$in": ["proj_a", "proj_b"]}} in result["$or"]


def test_staff_with_no_dept_or_project_gets_submitted_by_only():
    """staff with no department or projects → only submitted_by clause."""
    result = build_scope_filter(_make_ctx("staff"))
    assert result == {"$or": [{"submitted_by": "user_001"}]}


def test_full_access_roles_set():
    """FULL_ACCESS_ROLES must be exactly {admin, accounting, manager}."""
    assert FULL_ACCESS_ROLES == {"admin", "accounting", "manager"}


# ═══════════════════════════════════════════════════════════════════════════════
# ① スコープ境界値テスト (endpoint integration)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_staff_cannot_see_other_department(client, corp_setup):
    """dept_a の staff は dept_b のデータを取得できない。"""
    db = get_database()
    ids = corp_setup

    # dept_b の receipt (staff_b が提出)
    dept_b_receipt = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_b_id"], department_id="dept_b")
    )
    # dept_a の receipt (staff_a が提出) — これは見えるべき
    dept_a_receipt = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_a_id"], department_id="dept_a")
    )

    _auth_as(STAFF_A_UID)
    resp = await client.get("/api/v1/receipts")
    assert resp.status_code == 200

    returned_ids = {r["id"] for r in resp.json()}
    assert str(dept_a_receipt.inserted_id) in returned_ids      # 自部門 → 見える
    assert str(dept_b_receipt.inserted_id) not in returned_ids  # 他部門 → 見えない


@pytest.mark.asyncio
async def test_staff_cannot_see_unrelated_project(client, corp_setup):
    """参加していないプロジェクトのデータは取得できない。"""
    db = get_database()
    ids = corp_setup

    # staff_a を project_x にのみ登録
    await db["project_members"].insert_one({
        "employee_id": ids["staff_a_id"],
        "project_id":  "project_x",
    })

    # project_y (非参加) の receipt — 見えてはいけない
    r_y = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_b_id"], project_id="project_y")
    )
    # project_x (参加) の receipt — 見えるべき
    r_x = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_b_id"], project_id="project_x")
    )

    _auth_as(STAFF_A_UID)
    resp = await client.get("/api/v1/receipts")
    assert resp.status_code == 200

    returned_ids = {r["id"] for r in resp.json()}
    assert str(r_x.inserted_id) in returned_ids      # project_x → 見える
    assert str(r_y.inserted_id) not in returned_ids  # project_y → 見えない


@pytest.mark.asyncio
async def test_staff_can_see_own_submission_across_departments(client, corp_setup):
    """自分が提出したデータは部門が違っても必ず取得できる ($or の submitted_by 節)。"""
    db = get_database()
    ids = corp_setup

    # staff_a (dept_a) が dept_b に提出した receipt
    cross_dept_receipt = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_a_id"], department_id="dept_b")
    )

    _auth_as(STAFF_A_UID)
    resp = await client.get("/api/v1/receipts")
    assert resp.status_code == 200

    returned_ids = {r["id"] for r in resp.json()}
    assert str(cross_dept_receipt.inserted_id) in returned_ids  # 自己提出 → 必ず見える


# ═══════════════════════════════════════════════════════════════════════════════
# ② ロール昇格・降格テスト
# ═══════════════════════════════════════════════════════════════════════════════

def test_accounting_sees_all_departments():
    """accounting は FULL_ACCESS_ROLES → scope filter は空。"""
    assert build_scope_filter(_make_ctx("accounting", department_id="dept_a")) == {}


def test_manager_sees_all_departments():
    """manager は FULL_ACCESS_ROLES → scope filter は空。"""
    assert build_scope_filter(_make_ctx("manager", department_id="dept_a")) == {}


def test_approver_scoped_like_staff():
    """approver は FULL_ACCESS_ROLES に含まれない → staff と同様に $or 制限がかかる。"""
    ctx = _make_ctx("approver", department_id="dept_a")
    result = build_scope_filter(ctx)
    assert "$or" in result
    assert {"department_id": "dept_a"} in result["$or"]
    assert {"submitted_by": "user_001"} in result["$or"]


@pytest.mark.asyncio
async def test_accounting_sees_all_departments_endpoint(client, corp_setup):
    """accounting ロールは dept_a 所属でも dept_b のデータも全件取得できる。"""
    db = get_database()
    ids = corp_setup

    r_a = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_a_id"], department_id="dept_a")
    )
    r_b = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_b_id"], department_id="dept_b")
    )

    _auth_as(ACCOUNTING_UID)
    resp = await client.get("/api/v1/receipts")
    assert resp.status_code == 200

    returned_ids = {r["id"] for r in resp.json()}
    assert str(r_a.inserted_id) in returned_ids  # dept_a → 見える
    assert str(r_b.inserted_id) in returned_ids  # dept_b → 見える (full access)


@pytest.mark.asyncio
async def test_manager_sees_all_departments_endpoint(client, corp_setup):
    """manager ロールは全部門の receipts を取得できる。"""
    db = get_database()
    ids = corp_setup

    r_a = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_a_id"], department_id="dept_a")
    )
    r_b = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_b_id"], department_id="dept_b")
    )

    _auth_as(MANAGER_UID)
    resp = await client.get("/api/v1/receipts")
    assert resp.status_code == 200

    returned_ids = {r["id"] for r in resp.json()}
    assert str(r_a.inserted_id) in returned_ids
    assert str(r_b.inserted_id) in returned_ids


# ═══════════════════════════════════════════════════════════════════════════════
# ③ 空データ・エッジケーステスト
# ═══════════════════════════════════════════════════════════════════════════════

def test_staff_no_department_no_project_sees_only_own():
    """dept/project なし staff の scope は submitted_by のみ → 他人のデータはゼロ。"""
    result = build_scope_filter(_make_ctx("staff"))
    assert result == {"$or": [{"submitted_by": "user_001"}]}


def test_staff_with_multiple_projects():
    """複数プロジェクト参加の staff は全プロジェクトを $in でカバーする。"""
    ctx = _make_ctx("staff", project_ids=["proj_a", "proj_b", "proj_c"])
    result = build_scope_filter(ctx)
    assert {"project_id": {"$in": ["proj_a", "proj_b", "proj_c"]}} in result["$or"]


@pytest.mark.asyncio
async def test_staff_no_dept_sees_only_own_endpoint(client, corp_setup):
    """dept/project なし staff は他人の receipt を取得できず、自分の1件のみ取得できる。"""
    db = get_database()
    ids = corp_setup

    # 部門なしの staff を追加
    lone_res = await db["employees"].insert_one({
        "firebase_uid": "filter_lone_uid",
        "corporate_id": ids["corp_id"],
        "role": "staff",
        "name": "部門なしスタッフ",
        # department_id なし
    })
    lone_id = str(lone_res.inserted_id)

    other_receipt = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_a_id"], department_id="dept_a")
    )
    own_receipt = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], lone_id)  # 自分の提出、部門なし
    )

    _auth_as("filter_lone_uid")
    resp = await client.get("/api/v1/receipts")
    assert resp.status_code == 200

    returned_ids = {r["id"] for r in resp.json()}
    assert str(own_receipt.inserted_id) in returned_ids          # 自分のは見える
    assert str(other_receipt.inserted_id) not in returned_ids    # 他人のは見えない
    assert len(resp.json()) == 1                                  # 正確に1件


@pytest.mark.asyncio
async def test_staff_with_multiple_projects_endpoint(client, corp_setup):
    """複数プロジェクト参加の staff は全プロジェクトのデータを取得し、未参加は取得できない。"""
    db = get_database()
    ids = corp_setup

    await db["project_members"].insert_many([
        {"employee_id": ids["staff_a_id"], "project_id": "project_x"},
        {"employee_id": ids["staff_a_id"], "project_id": "project_y"},
    ])

    r_x = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_b_id"], project_id="project_x")
    )
    r_y = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_b_id"], project_id="project_y")
    )
    r_z = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_b_id"], project_id="project_z")  # 未参加
    )

    _auth_as(STAFF_A_UID)
    resp = await client.get("/api/v1/receipts")
    assert resp.status_code == 200

    returned_ids = {r["id"] for r in resp.json()}
    assert str(r_x.inserted_id) in returned_ids      # project_x → 見える
    assert str(r_y.inserted_id) in returned_ids      # project_y → 見える
    assert str(r_z.inserted_id) not in returned_ids  # project_z (未参加) → 見えない


# ═══════════════════════════════════════════════════════════════════════════════
# ④ CorporateContext の整合性テスト
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_corporate_context_role_is_admin_for_corporate_owner(corp_setup):
    """corporates コレクション登録ユーザー (法人代表) の role は 'admin'。"""
    ctx = await get_corporate_context(current_user={"uid": CORP_OWNER_UID})
    assert ctx.role == "admin"
    assert ctx.department_id is None
    assert ctx.project_ids == []


@pytest.mark.asyncio
async def test_corporate_context_employee_role_matches_db(corp_setup):
    """employees コレクションの role が CorporateContext に正確に反映される。"""
    ctx_staff = await get_corporate_context(current_user={"uid": STAFF_A_UID})
    ctx_acc   = await get_corporate_context(current_user={"uid": ACCOUNTING_UID})

    assert ctx_staff.role == "staff"
    assert ctx_staff.department_id == "dept_a"

    assert ctx_acc.role == "accounting"
    assert ctx_acc.department_id == "dept_a"
    # accounting は FULL_ACCESS_ROLES → scope filter は空
    assert build_scope_filter(ctx_acc) == {}


@pytest.mark.asyncio
async def test_corporate_context_missing_department_is_none(corp_setup):
    """department_id 未設定の従業員は context.department_id が None になる。
    さらに None のまま build_scope_filter を呼んでもエラーにならない。"""
    db = get_database()
    ids = corp_setup

    await db["employees"].insert_one({
        "firebase_uid": "filter_nodept_uid",
        "corporate_id": ids["corp_id"],
        "role": "staff",
        "name": "部門なし従業員",
        # department_id フィールド意図的に省略
    })

    ctx = await get_corporate_context(current_user={"uid": "filter_nodept_uid"})

    assert ctx.department_id is None

    # None でも build_scope_filter がクラッシュしないことを確認
    result = build_scope_filter(ctx)
    assert "$or" in result
    # department_id 節は生成されない
    assert not any("department_id" in clause for clause in result["$or"])
    # submitted_by 節は必ず存在する
    assert any("submitted_by" in clause for clause in result["$or"])


# ═══════════════════════════════════════════════════════════════════════════════
# ⑤ 悪意あるリクエストのテスト
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_scope_filter_not_bypassable_via_query_param(client, corp_setup):
    """
    staff が submitted_by=他人ID を渡してもスコープフィルタが優先される。
    GET /receipts は submitted_by=="me" のみ処理するため、
    任意 ID は無視され、scope の $or だけが効く。
    """
    db = get_database()
    ids = corp_setup

    # staff_b (dept_b) の receipt — staff_a には見えないはず
    other_receipt = await db["receipts"].insert_one(
        _receipt(ids["corp_id"], ids["staff_b_id"], department_id="dept_b")
    )

    _auth_as(STAFF_A_UID)
    # 悪意あるパラメータ: 他人の user_id を submitted_by に渡す
    resp = await client.get(f"/api/v1/receipts?submitted_by={ids['staff_b_id']}")
    assert resp.status_code == 200

    returned_ids = {r["id"] for r in resp.json()}
    # scope の $or に dept_b / staff_b_id が含まれないため取得されない
    assert str(other_receipt.inserted_id) not in returned_ids


@pytest.mark.asyncio
async def test_invoice_scope_same_as_receipts(client, corp_setup):
    """
    GET /invoices にも同様のスコープフィルタが適用される。
    invoices は 'elif submitted_by:' で query["submitted_by"] = 他人ID を追加するが、
    scope $or との AND により他人のデータは取得されない。
    """
    db = get_database()
    ids = corp_setup

    # staff_b (dept_b) の invoice — staff_a (dept_a) には見えないはず
    other_inv = await db["invoices"].insert_one(
        _invoice(ids["corp_id"], ids["staff_b_id"], department_id="dept_b")
    )
    # staff_a の invoice — 正常なら見えるが、悪意あるパラメータの影響を確認
    own_inv = await db["invoices"].insert_one(
        _invoice(ids["corp_id"], ids["staff_a_id"], department_id="dept_a")
    )

    _auth_as(STAFF_A_UID)
    # 攻撃: 他人の ID を submitted_by に渡す
    # invoices は elif 節で query["submitted_by"] = staff_b_id を追加するが、
    # scope $or: [{submitted_by: staff_a_id}, {department_id: dept_a}] との AND で
    # staff_b の invoice は dep_b かつ submitted_by != staff_a_id → 除外
    resp = await client.get(f"/api/v1/invoices?submitted_by={ids['staff_b_id']}")
    assert resp.status_code == 200

    returned_ids = {r["id"] for r in resp.json()}
    assert str(other_inv.inserted_id) not in returned_ids  # 攻撃が防がれた

    # 正常アクセス (submitted_by パラメータなし) では自部門の invoice が見える
    _auth_as(STAFF_A_UID)
    resp2 = await client.get("/api/v1/invoices")
    returned_ids2 = {r["id"] for r in resp2.json()}
    assert str(own_inv.inserted_id) in returned_ids2   # 自部門は正常に見える
    assert str(other_inv.inserted_id) not in returned_ids2  # 他部門は依然見えない
