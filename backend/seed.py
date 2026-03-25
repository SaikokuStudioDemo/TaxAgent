"""
seed.py - 開発・テスト用シードデータ投入スクリプト

使用方法:
    cd backend
    PYTHONPATH=. venv/bin/python seed.py

フィールド設計:
    invoices:
        - document_type: "issued" | "received"  (旧: direction)
        - approval_status: "draft" | "pending_approval" | "approved" | "auto_approved" | "rejected"
          (旧: status + review_status を統合)
        - delivery_status: "unsent" | "sent"  (旧: approval_status="sent")
        - reconciliation_status: "unreconciled" | "reconciled"  (新規)
    receipts:
        - document_type: "receipt"  (新規・統一)
        - approval_status: 同上
        - reconciliation_status: 同上
    bank_transactions:
        - transaction_type: "credit" | "debit"  (旧: direction)
"""

import asyncio
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "tax_agent"

# Firebase UID（テスト環境用固定値）
TAX_FIRM_UID   = "tax_firm_uid"
CORP_A_UID     = "seed_corp_a_uid"
CORP_B_UID     = "seed_corp_b_uid"

# 従業員 Firebase UID
EMP_TAX_STAFF_UID    = "tax_emp_staff_uid"
EMP_TAX_MANAGER_UID  = "tax_emp_manager_uid"
EMP_A_STAFF_UID      = "seed_emp_a_staff"
EMP_A_MANAGER_UID    = "seed_emp_a_manager"
EMP_B_STAFF_UID      = "seed_emp_b_staff"
EMP_B_MANAGER_UID    = "seed_emp_b_manager"

ALL_CORP_UIDS = [TAX_FIRM_UID, CORP_A_UID, CORP_B_UID]
ALL_EMP_UIDS  = [
    EMP_TAX_STAFF_UID, EMP_TAX_MANAGER_UID,
    EMP_A_STAFF_UID, EMP_A_MANAGER_UID,
    EMP_B_STAFF_UID, EMP_B_MANAGER_UID,
]


async def seed():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    today = datetime.utcnow()

    print(f"\n🌱 Seeding database: {DB_NAME}\n")

    # ─────── 既存シードデータをクリア ───────
    for uid in ALL_CORP_UIDS:
        corp = await db["corporates"].find_one({"firebase_uid": uid})
        if corp:
            cid = str(corp["_id"])
            for col in [
                "employees", "receipts", "invoices", "approval_rules",
                "clients", "company_profiles", "bank_accounts", "notifications",
                "bank_transactions", "matches", "approval_events",
                "departments",
            ]:
                await db[col].delete_many({"corporate_id": cid})
    await db["corporates"].delete_many({"firebase_uid": {"$in": ALL_CORP_UIDS}})
    await db["employees"].delete_many({"firebase_uid": {"$in": ALL_EMP_UIDS}})
    print("✅ 既存シードデータをクリアしました")

    # ═══════════════════════════════════════════
    # 税理士法人
    # ═══════════════════════════════════════════
    res_tax = await db["corporates"].insert_one({
        "firebase_uid": TAX_FIRM_UID,
        "name": "青山税理士法人",
        "corporateType": "tax_firm",
        "planId": "plan_premium",
        "is_active": True,
        "created_at": today,
    })
    tax_id = str(res_tax.inserted_id)
    print(f"✅ 税理士法人 作成: {tax_id}")

    # 自社情報（税理士法人）
    tax_profile_res = await db["company_profiles"].insert_one({
        "corporate_id": tax_id,
        "profile_name": "メインプロファイル",
        "company_name": "青山税理士法人",
        "phone": "03-1234-5678",
        "address": "東京都港区青山1-1-1",
        "registration_number": "T1234567890123",
        "is_default": True,
        "created_at": today,
    })
    tax_profile_id = str(tax_profile_res.inserted_id)

    await db["bank_accounts"].insert_many([
        {
            "corporate_id": tax_id, "profile_id": tax_profile_id,
            "bank_name": "三菱UFJ銀行", "branch_name": "青山支店",
            "account_type": "ordinary", "account_number": "1234567",
            "account_holder": "アオヤマゼイリシホウジン",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": tax_id, "profile_id": tax_profile_id,
            "bank_name": "三井住友銀行", "branch_name": "渋谷支店",
            "account_type": "ordinary", "account_number": "7654321",
            "account_holder": "アオヤマゼイリシホウジン",
            "is_default": False, "is_active": True, "created_at": today, "updated_at": today,
        },
    ])
    print("✅ 税理士法人 自社情報・銀行口座作成")

    await db["employees"].insert_many([
        {
            "firebase_uid": EMP_TAX_STAFF_UID,
            "corporate_id": tax_id,
            "name": "鈴木 誠",
            "role": "staff",
            "email": "staff@aoyama-tax.co.jp",
            "is_active": True,
            "created_at": today,
        },
        {
            "firebase_uid": EMP_TAX_MANAGER_UID,
            "corporate_id": tax_id,
            "name": "田中 克彦",
            "role": "dept_manager",
            "email": "manager@aoyama-tax.co.jp",
            "is_active": True,
            "created_at": today,
        },
    ])
    print("✅ 税理士法人 従業員2名作成")

    # 承認ルール（税理士法人）
    tax_rules_res = await db["approval_rules"].insert_many([
        {
            "corporate_id": tax_id,
            "name": "基本承認ルート（全件）",
            "applies_to": ["receipt", "received_invoice", "issued_invoice"],
            "conditions": [{"field": "always", "operator": "", "value": ""}],
            "steps": [{"step": 1, "role": "dept_manager", "required": True}],
            "active": True,
            "created_at": today,
        },
        {
            "corporate_id": tax_id,
            "name": "高額承認ルート（10万円以上）",
            "applies_to": ["receipt", "received_invoice"],
            "conditions": [{"field": "amount", "operator": ">=", "value": 100000}],
            "steps": [
                {"step": 1, "role": "accounting", "required": True},
                {"step": 2, "role": "dept_manager", "required": True},
            ],
            "active": True,
            "created_at": today,
        },
    ])
    tax_base_rule_id   = str(tax_rules_res.inserted_ids[0])
    tax_strict_rule_id = str(tax_rules_res.inserted_ids[1])

    # 請求書（税理士法人）
    await db["invoices"].insert_many([
        {
            "corporate_id": tax_id,
            "document_type": "issued",
            "invoice_number": "TAX-INV-001",
            "client_name": "株式会社サンプル商事",
            "recipient_email": "contact@sample.co.jp",
            "issue_date": today.strftime("%Y-%m-%d"),
            "due_date": (today + timedelta(days=30)).strftime("%Y-%m-%d"),
            "subtotal": 100000,
            "tax_amount": 10000,
            "total_amount": 110000,
            "line_items": [{"description": "税務顧問料 3月分", "category": "売上", "amount": 100000, "tax_rate": 10}],
            "approval_status": "approved",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": tax_base_rule_id,
            "approval_history": [{"step": 1, "roleId": "dept_manager", "roleName": "部門長", "status": "approved"}],
            "fiscal_period": today.strftime("%Y-%m"),
            "created_by": tax_id,
            "created_at": today,
            "is_deleted": False,
        },
        {
            "corporate_id": tax_id,
            "document_type": "received",
            "invoice_number": "TAX-REC-001",
            "client_name": "クラウドサービス株式会社",
            "recipient_email": "billing@cloud.co.jp",
            "issue_date": (today - timedelta(days=10)).strftime("%Y-%m-%d"),
            "due_date": (today + timedelta(days=20)).strftime("%Y-%m-%d"),
            "subtotal": 150000,
            "tax_amount": 15000,
            "total_amount": 165000,
            "line_items": [{"description": "サーバー利用料", "category": "通信費", "amount": 150000, "tax_rate": 10}],
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": tax_strict_rule_id,
            "approval_history": [
                {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                {"step": 2, "roleId": "dept_manager", "roleName": "部門長", "status": "pending"},
            ],
            "fiscal_period": today.strftime("%Y-%m"),
            "created_by": tax_id,
            "created_at": today,
            "is_deleted": False,
        },
    ])

    # 領収書（税理士法人）
    await db["receipts"].insert_many([
        {
            "corporate_id": tax_id,
            "document_type": "receipt",
            "date": today.strftime("%Y-%m-%d"),
            "amount": 5500,
            "tax_rate": 10,
            "payee": "タクシー会社",
            "category": "旅費交通費",
            "payment_method": "立替",
            "line_items": [{"description": "移動費", "category": "旅費交通費", "amount": 5000, "tax_rate": 10}],
            "attachments": [],
            "fiscal_period": today.strftime("%Y-%m"),
            "ai_extracted": True,
            "submitted_by": tax_id,
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": tax_base_rule_id,
            "approval_history": [{"step": 1, "roleId": "dept_manager", "roleName": "部門長", "status": "pending"}],
            "created_at": today,
        },
        {
            "corporate_id": tax_id,
            "document_type": "receipt",
            "date": today.strftime("%Y-%m-%d"),
            "amount": 120000,
            "tax_rate": 10,
            "payee": "PCショップ",
            "category": "消耗品費",
            "payment_method": "法人カード",
            "line_items": [{"description": "ノートPC", "category": "消耗品費", "amount": 120000, "tax_rate": 10}],
            "attachments": [],
            "fiscal_period": today.strftime("%Y-%m"),
            "ai_extracted": False,
            "submitted_by": tax_id,
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": tax_strict_rule_id,
            "approval_history": [
                {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                {"step": 2, "roleId": "dept_manager", "roleName": "部門長", "status": "pending"},
            ],
            "created_at": today,
        },
    ])
    print("✅ 税理士法人 承認ルール2件 / 請求書2件 / 領収書2件 作成")

    # ═══════════════════════════════════════════
    # 一般法人A（seed_corp_a_uid: test-token でアクセスする法人）
    # ═══════════════════════════════════════════
    res_a = await db["corporates"].insert_one({
        "firebase_uid": CORP_A_UID,
        "name": "株式会社アルファ",
        "corporateType": "corporate",
        "planId": "plan_standard",
        "advising_tax_firm_id": TAX_FIRM_UID,
        "is_active": True,
        "created_at": today,
    })
    corp_a_id = str(res_a.inserted_id)
    print(f"✅ 一般法人A 作成: {corp_a_id}")

    # 自社情報（法人A）
    corp_a_profile_res = await db["company_profiles"].insert_one({
        "corporate_id": corp_a_id,
        "profile_name": "メインプロファイル",
        "company_name": "株式会社アルファ",
        "phone": "03-9876-5432",
        "address": "東京都渋谷区渋谷2-2-2",
        "registration_number": "T9876543210123",
        "is_default": True,
        "created_at": today,
    })
    corp_a_profile_id = str(corp_a_profile_res.inserted_id)

    await db["bank_accounts"].insert_many([
        {
            "corporate_id": corp_a_id, "profile_id": corp_a_profile_id,
            "bank_name": "みずほ銀行", "branch_name": "新宿支店",
            "account_type": "ordinary", "account_number": "1111111",
            "account_holder": "カブシキガイシャアルファ",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": corp_a_id, "profile_id": corp_a_profile_id,
            "bank_name": "三井住友銀行", "branch_name": "新宿支店",
            "account_type": "checking", "account_number": "2222222",
            "account_holder": "カブシキガイシャアルファ",
            "is_default": False, "is_active": True, "created_at": today, "updated_at": today,
        },
    ])
    print("✅ 一般法人A 自社情報・銀行口座作成")

    # 部門データ（法人A）
    dept_res = await db["departments"].insert_many([
        {"corporate_id": corp_a_id, "name": "経営陣", "groups": [], "created_at": today},
        {"corporate_id": corp_a_id, "name": "営業部", "groups": [
            {"id": "grp-sales-1", "name": "営業1課"},
            {"id": "grp-sales-2", "name": "営業2課"},
        ], "created_at": today},
        {"corporate_id": corp_a_id, "name": "システム開発部", "groups": [
            {"id": "grp-dev-1", "name": "フロントエンドチーム"},
            {"id": "grp-dev-2", "name": "バックエンドチーム"},
        ], "created_at": today},
    ])
    print("✅ 一般法人A 部門3件作成")

    await db["employees"].insert_many([
        {
            "firebase_uid": EMP_A_STAFF_UID,
            "corporate_id": corp_a_id,
            "name": "山田 太郎",
            "role": "staff",
            "email": "staff@alpha.co.jp",
            "is_active": True,
            "created_at": today,
        },
        {
            "firebase_uid": EMP_A_MANAGER_UID,
            "corporate_id": corp_a_id,
            "name": "佐藤 花子",
            "role": "dept_manager",
            "email": "manager@alpha.co.jp",
            "is_active": True,
            "created_at": today,
        },
    ])
    print("✅ 一般法人A 従業員2名作成")

    # 取引先（法人A）
    await db["clients"].insert_many([
        {
            "corporate_id": corp_a_id,
            "name": "株式会社モックアルファ",
            "registration_number": "T1111111111111",
            "email": "contact@mockalpha.co.jp",
            "phone": "03-1111-1111",
            "postal_code": "150-0001",
            "address": "東京都渋谷区神宮前1-1-1",
            "department": "経理部",
            "contact_person": "田中 誠",
            "payment_terms": "月末締め翌月末払い",
            "internal_notes": "メインの取引先",
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "デザイン事務所クリエイト",
            "registration_number": "T2222222222222",
            "email": "info@design-create.co.jp",
            "phone": "03-2222-2222",
            "postal_code": "160-0022",
            "address": "東京都新宿区新宿3-3-3",
            "department": "制作部",
            "contact_person": "鈴木 美穂",
            "payment_terms": "納品後30日以内",
            "internal_notes": "ロゴ・デザイン担当",
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "クラウドサービス株式会社",
            "registration_number": "T3333333333333",
            "email": "billing@cloudservice.co.jp",
            "phone": "03-3333-3333",
            "postal_code": "100-0005",
            "address": "東京都千代田区丸の内1-1-1",
            "department": "営業部",
            "contact_person": "山本 健太",
            "payment_terms": "月末締め翌々月払い",
            "internal_notes": "サーバー・SaaS費用",
            "created_at": today,
        },
    ])
    print("✅ 一般法人A 取引先3件作成")

    # 承認ルール（法人A）
    a_rules_res = await db["approval_rules"].insert_many([
        {
            "corporate_id": corp_a_id,
            "name": "（テスト）基本ルート（全件対象）",
            "applies_to": ["receipt", "received_invoice", "issued_invoice"],
            "conditions": [{"field": "always", "operator": "", "value": ""}],
            "steps": [{"step": 1, "role": "direct_manager", "required": True}],
            "active": True,
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "（テスト）経理確認＋部長承認（10万円以上）",
            "applies_to": ["receipt", "received_invoice", "issued_invoice"],
            "conditions": [{"field": "amount", "operator": ">=", "value": 100000}],
            "steps": [
                {"step": 1, "role": "accounting", "required": True},
                {"step": 2, "role": "direct_manager", "required": True},
            ],
            "active": True,
            "created_at": today,
        },
    ])
    a_base_rule_id   = str(a_rules_res.inserted_ids[0])
    a_strict_rule_id = str(a_rules_res.inserted_ids[1])

    # 請求書（法人A）
    await db["invoices"].insert_many([
        {
            "corporate_id": corp_a_id,
            "document_type": "issued",
            "invoice_number": "INV-MOCK-001",
            "client_name": "株式会社モックアルファ",
            "recipient_email": "alpha@example.com",
            "issue_date": "2024-03-01",
            "due_date": "2024-03-31",
            "subtotal": 50000,
            "tax_amount": 5000,
            "total_amount": 55000,
            "line_items": [{"description": "コンサルティング費用", "category": "売上", "amount": 50000, "tax_rate": 10}],
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": a_base_rule_id,
            "approval_history": [{"step": 1, "roleId": "direct_manager", "roleName": "直属の部門長", "status": "pending"}],
            "fiscal_period": "2024-03",
            "created_by": corp_a_id,
            "created_at": today,
            "is_deleted": False,
        },
        {
            "corporate_id": corp_a_id,
            "document_type": "received",
            "invoice_number": "REC-MOCK-001",
            "client_name": "（受領）デザイン事務所",
            "recipient_email": "design@example.com",
            "issue_date": "2024-03-10",
            "due_date": "2024-04-10",
            "subtotal": 150000,
            "tax_amount": 15000,
            "total_amount": 165000,
            "line_items": [{"description": "ロゴデザイン費用", "category": "外注費", "amount": 150000, "tax_rate": 10}],
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": a_strict_rule_id,
            "approval_history": [
                {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                {"step": 2, "roleId": "direct_manager", "roleName": "直属の部門長", "status": "pending"},
            ],
            "fiscal_period": "2024-03",
            "created_by": corp_a_id,
            "created_at": today,
            "is_deleted": False,
        },
        {
            "corporate_id": corp_a_id,
            "document_type": "received",
            "invoice_number": "REC-MOCK-002",
            "client_name": "（受領）クラウドサービス",
            "recipient_email": "cloud@example.com",
            "issue_date": "2024-02-28",
            "due_date": (today - timedelta(days=7)).strftime("%Y-%m-%d"),
            "subtotal": 80000,
            "tax_amount": 8000,
            "total_amount": 88000,
            "line_items": [{"description": "サーバー利用料", "category": "通信費", "amount": 80000, "tax_rate": 10}],
            "approval_status": "approved",
            "reconciliation_status": "unreconciled",
            "current_step": 2,
            "approval_rule_id": a_base_rule_id,
            "approval_history": [
                {"step": 1, "roleId": "direct_manager", "roleName": "直属の部門長", "status": "approved", "approverName": "山田太郎", "actionDate": "2024-03-01"}
            ],
            "fiscal_period": "2024-02",
            "created_by": corp_a_id,
            "created_at": today,
            "is_deleted": False,
        },
    ])

    # 領収書（法人A）
    await db["receipts"].insert_many([
        {
            "corporate_id": corp_a_id,
            "document_type": "receipt",
            "date": "2024-03-05",
            "amount": 5500,
            "tax_rate": 10,
            "payee": "タクシー会社",
            "category": "旅費交通費",
            "payment_method": "法人カード",
            "line_items": [{"description": "移動費", "category": "旅費交通費", "amount": 5000, "tax_rate": 10}],
            "attachments": [],
            "fiscal_period": "2024-03",
            "ai_extracted": True,
            "submitted_by": corp_a_id,
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": a_base_rule_id,
            "approval_history": [{"step": 1, "roleId": "direct_manager", "roleName": "直属の部門長", "status": "pending"}],
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "document_type": "receipt",
            "date": "2024-03-08",
            "amount": 110000,
            "tax_rate": 10,
            "payee": "PCショップ",
            "category": "消耗品費",
            "payment_method": "立替",
            "line_items": [{"description": "ディスプレイ", "category": "消耗品費", "amount": 100000, "tax_rate": 10}],
            "attachments": [],
            "fiscal_period": "2024-03",
            "ai_extracted": False,
            "submitted_by": corp_a_id,
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": a_strict_rule_id,
            "approval_history": [
                {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                {"step": 2, "roleId": "direct_manager", "roleName": "直属の部門長", "status": "pending"},
            ],
            "created_at": today,
        },
    ])

    # 銀行取引（法人A）
    await db["bank_transactions"].insert_many([
        {
            "corporate_id": corp_a_id,
            "source_type": "bank",
            "account_name": "三井住友銀行 新宿支店",
            "transaction_date": (today - timedelta(days=5)).strftime("%Y-%m-%d"),
            "description": "モックアルファ 売上入金",
            "normalized_name": "モックアルファ",
            "amount": 55000,
            "transaction_type": "credit",
            "status": "unmatched",
            "fiscal_period": today.strftime("%Y-%m"),
            "imported_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "source_type": "bank",
            "account_name": "三井住友銀行 新宿支店",
            "transaction_date": (today - timedelta(days=3)).strftime("%Y-%m-%d"),
            "description": "デザイン事務所 支払",
            "normalized_name": "デザイン事務所",
            "amount": 165000,
            "transaction_type": "debit",
            "status": "unmatched",
            "fiscal_period": today.strftime("%Y-%m"),
            "imported_at": today,
        },
    ])

    print("✅ 一般法人A 承認ルール2件 / 請求書3件 / 領収書2件 / 銀行取引2件 作成")

    # ═══════════════════════════════════════════
    # 一般法人B（データ分離テスト用）
    # ═══════════════════════════════════════════
    res_b = await db["corporates"].insert_one({
        "firebase_uid": CORP_B_UID,
        "name": "株式会社ベータ",
        "corporateType": "corporate",
        "planId": "plan_basic",
        "advising_tax_firm_id": TAX_FIRM_UID,
        "is_active": True,
        "created_at": today,
    })
    corp_b_id = str(res_b.inserted_id)
    print(f"✅ 一般法人B 作成: {corp_b_id}")

    # 自社情報（法人B）
    corp_b_profile_res = await db["company_profiles"].insert_one({
        "corporate_id": corp_b_id,
        "profile_name": "メインプロファイル",
        "company_name": "株式会社ベータ",
        "phone": "03-5555-6666",
        "address": "東京都品川区大崎3-3-3",
        "registration_number": "T5555666677778",
        "is_default": True,
        "created_at": today,
    })
    corp_b_profile_id = str(corp_b_profile_res.inserted_id)

    await db["bank_accounts"].insert_many([
        {
            "corporate_id": corp_b_id, "profile_id": corp_b_profile_id,
            "bank_name": "りそな銀行", "branch_name": "品川支店",
            "account_type": "ordinary", "account_number": "3333333",
            "account_holder": "カブシキガイシャベータ",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": corp_b_id, "profile_id": corp_b_profile_id,
            "bank_name": "三菱UFJ銀行", "branch_name": "五反田支店",
            "account_type": "ordinary", "account_number": "4444444",
            "account_holder": "カブシキガイシャベータ",
            "is_default": False, "is_active": True, "created_at": today, "updated_at": today,
        },
    ])
    print("✅ 一般法人B 自社情報・銀行口座作成")

    await db["employees"].insert_many([
        {
            "firebase_uid": EMP_B_STAFF_UID,
            "corporate_id": corp_b_id,
            "name": "伊藤 翔太",
            "role": "staff",
            "email": "staff@beta.co.jp",
            "is_active": True,
            "created_at": today,
        },
        {
            "firebase_uid": EMP_B_MANAGER_UID,
            "corporate_id": corp_b_id,
            "name": "渡辺 美咲",
            "role": "dept_manager",
            "email": "manager@beta.co.jp",
            "is_active": True,
            "created_at": today,
        },
    ])
    print("✅ 一般法人B 従業員2名作成")

    # 取引先（法人B）
    await db["clients"].insert_many([
        {
            "corporate_id": corp_b_id,
            "name": "株式会社ガンマ商事",
            "registration_number": "T4444444444444",
            "email": "contact@gamma.co.jp",
            "phone": "03-4444-4444",
            "postal_code": "140-0002",
            "address": "東京都品川区東品川2-2-2",
            "department": "購買部",
            "contact_person": "小林 直樹",
            "payment_terms": "末日締め翌月末払い",
            "internal_notes": "主要顧客",
            "created_at": today,
        },
        {
            "corporate_id": corp_b_id,
            "name": "広告代理店デルタ",
            "registration_number": "T5555555555555",
            "email": "billing@delta-ad.co.jp",
            "phone": "03-5555-5555",
            "postal_code": "105-0011",
            "address": "東京都港区芝公園1-1-1",
            "department": "営業部",
            "contact_person": "高橋 由美",
            "payment_terms": "納品後45日以内",
            "internal_notes": "広告・宣伝費担当",
            "created_at": today,
        },
        {
            "corporate_id": corp_b_id,
            "name": "オフィス用品エプシロン",
            "registration_number": "T6666666666666",
            "email": "order@epsilon-office.co.jp",
            "phone": "03-6666-6666",
            "postal_code": "108-0075",
            "address": "東京都港区港南3-3-3",
            "department": "総務部",
            "contact_person": "中村 朋子",
            "payment_terms": "月末締め翌々月払い",
            "internal_notes": "消耗品・備品の仕入先",
            "created_at": today,
        },
    ])
    print("✅ 一般法人B 取引先3件作成")

    # 承認ルール（法人B）
    b_rules_res = await db["approval_rules"].insert_many([
        {
            "corporate_id": corp_b_id,
            "name": "B社 基本承認ルート",
            "applies_to": ["receipt", "received_invoice", "issued_invoice"],
            "conditions": [{"field": "always", "operator": "", "value": ""}],
            "steps": [{"step": 1, "role": "dept_manager", "required": True}],
            "active": True,
            "created_at": today,
        },
        {
            "corporate_id": corp_b_id,
            "name": "B社 高額承認ルート（5万円以上）",
            "applies_to": ["receipt", "received_invoice"],
            "conditions": [{"field": "amount", "operator": ">=", "value": 50000}],
            "steps": [
                {"step": 1, "role": "accounting", "required": True},
                {"step": 2, "role": "dept_manager", "required": True},
            ],
            "active": True,
            "created_at": today,
        },
    ])
    b_base_rule_id   = str(b_rules_res.inserted_ids[0])
    b_strict_rule_id = str(b_rules_res.inserted_ids[1])

    # 請求書（法人B）
    await db["invoices"].insert_many([
        {
            "corporate_id": corp_b_id,
            "document_type": "issued",
            "invoice_number": "B-INV-001",
            "client_name": "株式会社ガンマ",
            "recipient_email": "gamma@example.com",
            "issue_date": today.strftime("%Y-%m-%d"),
            "due_date": (today + timedelta(days=30)).strftime("%Y-%m-%d"),
            "subtotal": 30000,
            "tax_amount": 3000,
            "total_amount": 33000,
            "line_items": [{"description": "業務委託費", "category": "売上", "amount": 30000, "tax_rate": 10}],
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": b_base_rule_id,
            "approval_history": [{"step": 1, "roleId": "dept_manager", "roleName": "部門長", "status": "pending"}],
            "fiscal_period": today.strftime("%Y-%m"),
            "created_by": corp_b_id,
            "created_at": today,
            "is_deleted": False,
        },
        {
            "corporate_id": corp_b_id,
            "document_type": "received",
            "invoice_number": "B-REC-001",
            "client_name": "（受領）B社の取引先",
            "recipient_email": "vendor@example.com",
            "issue_date": (today - timedelta(days=5)).strftime("%Y-%m-%d"),
            "due_date": (today + timedelta(days=25)).strftime("%Y-%m-%d"),
            "subtotal": 75000,
            "tax_amount": 7500,
            "total_amount": 82500,
            "line_items": [{"description": "広告費", "category": "広告宣伝費", "amount": 75000, "tax_rate": 10}],
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": b_strict_rule_id,
            "approval_history": [
                {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                {"step": 2, "roleId": "dept_manager", "roleName": "部門長", "status": "pending"},
            ],
            "fiscal_period": today.strftime("%Y-%m"),
            "created_by": corp_b_id,
            "created_at": today,
            "is_deleted": False,
        },
    ])

    # 領収書（法人B）
    await db["receipts"].insert_many([
        {
            "corporate_id": corp_b_id,
            "document_type": "receipt",
            "date": today.strftime("%Y-%m-%d"),
            "amount": 12000,
            "tax_rate": 10,
            "payee": "B社の取引先",
            "category": "交際費",
            "payment_method": "立替",
            "line_items": [{"description": "会食費", "category": "交際費", "amount": 12000, "tax_rate": 10}],
            "attachments": [],
            "fiscal_period": today.strftime("%Y-%m"),
            "ai_extracted": False,
            "submitted_by": corp_b_id,
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": b_base_rule_id,
            "approval_history": [{"step": 1, "roleId": "dept_manager", "roleName": "部門長", "status": "pending"}],
            "created_at": today,
        },
        {
            "corporate_id": corp_b_id,
            "document_type": "receipt",
            "date": today.strftime("%Y-%m-%d"),
            "amount": 68000,
            "tax_rate": 10,
            "payee": "オフィス用品店",
            "category": "消耗品費",
            "payment_method": "法人カード",
            "line_items": [{"description": "オフィスチェア", "category": "消耗品費", "amount": 68000, "tax_rate": 10}],
            "attachments": [],
            "fiscal_period": today.strftime("%Y-%m"),
            "ai_extracted": False,
            "submitted_by": corp_b_id,
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": b_strict_rule_id,
            "approval_history": [
                {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                {"step": 2, "roleId": "dept_manager", "roleName": "部門長", "status": "pending"},
            ],
            "created_at": today,
        },
    ])
    print("✅ 一般法人B 承認ルール2件 / 請求書2件 / 領収書2件 作成")

    # ─────── 完了メッセージ ───────
    print("\n" + "=" * 60)
    print("🎉 シードデータの投入が完了しました！")
    print("=" * 60)
    print(f"\n【確認用情報】")
    print(f"  税理士法人  corporate_id : {tax_id}   (firebase_uid: {TAX_FIRM_UID})")
    print(f"  一般法人A   corporate_id : {corp_a_id}  (firebase_uid: {CORP_A_UID})")
    print(f"  一般法人B   corporate_id : {corp_b_id}  (firebase_uid: {CORP_B_UID})")
    print(f"\n  ※ API テスト時: Authorization: Bearer test-token")
    print(f"     → uid=seed_corp_a_uid → 一般法人A としてアクセス")
    print(f"\n  Swagger Docs: http://localhost:8000/docs\n")

    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
