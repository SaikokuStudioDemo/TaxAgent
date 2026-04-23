"""
seed.py - 開発・テスト用シードデータ投入スクリプト

使用方法:
    cd backend
    PYTHONPATH=. venv/bin/python seed.py

フィールド設計:
    invoices:
        - document_type: "issued" | "received"  (旧: direction)
        - approval_status: "draft" | "pending_approval" | "approved" | "auto_approved" | "rejected"
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
import os
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGODB_URI", os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
DB_NAME = os.getenv("MONGODB_DB_NAME", "tax_agent")

if "localhost" not in MONGO_URI and "127.0.0.1" not in MONGO_URI:
    raise Exception(
        "seed.py はローカル環境でのみ実行できます。"
        f"現在の接続先: {MONGO_URI}"
    )

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
                "bank_transactions", "matches", "audit_logs",
                "departments", "projects",
                "matching_rules", "journal_rules",
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
            "owner_type": "corporate",
            "bank_name": "三菱UFJ銀行", "branch_name": "青山支店",
            "bank_code": "0005", "branch_code": "001",
            "account_type": "ordinary", "account_number": "1234567",
            "account_holder": "アオヤマゼイリシホウジン",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": tax_id, "profile_id": tax_profile_id,
            "owner_type": "corporate",
            "bank_name": "三井住友銀行", "branch_name": "渋谷支店",
            "bank_code": "0009", "branch_code": "223",
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

    # 請求書（税理士法人）- ダミーデータなし

    # 税理士法人は領収書を登録しないためシードデータなし
    print("✅ 税理士法人 承認ルール2件 / 請求書2件 作成（消込・仕訳ルールは法人A/Bのみ）")

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
            "owner_type": "corporate",
            "bank_name": "みずほ銀行", "branch_name": "新宿支店",
            "bank_code": "0001", "branch_code": "262",
            "account_type": "ordinary", "account_number": "1111111",
            "account_holder": "カブシキガイシャアルファ",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": corp_a_id, "profile_id": corp_a_profile_id,
            "owner_type": "corporate",
            "bank_name": "三井住友銀行", "branch_name": "新宿支店",
            "bank_code": "0009", "branch_code": "262",
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
    dept_a_ids = [str(i) for i in dept_res.inserted_ids]
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
    emp_a_staff_res  = await db["employees"].find_one({"firebase_uid": EMP_A_STAFF_UID})
    emp_a_manager_res = await db["employees"].find_one({"firebase_uid": EMP_A_MANAGER_UID})
    emp_a_staff_id   = str(emp_a_staff_res["_id"])  if emp_a_staff_res  else ""
    emp_a_manager_id = str(emp_a_manager_res["_id"]) if emp_a_manager_res else ""
    print("✅ 一般法人A 従業員2名作成")

    # プロジェクト（法人A）
    proj_a_res = await db["projects"].insert_many([
        {
            "corporate_id": corp_a_id,
            "name": "社内基幹システムリプレイス",
            "description": "ERP刷新プロジェクト（2025年度）",
            "members": [
                {"user_id": emp_a_manager_id, "name": "佐藤 花子"},
                {"user_id": emp_a_staff_id,   "name": "山田 太郎"},
            ],
            "is_active": True,
            "created_at": today,
            "updated_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "Webサイト制作プロジェクト",
            "description": "コーポレートサイトリニューアル",
            "members": [
                {"user_id": emp_a_manager_id, "name": "佐藤 花子"},
            ],
            "is_active": True,
            "created_at": today,
            "updated_at": today,
        },
    ])
    proj_a_ids = [str(i) for i in proj_a_res.inserted_ids]
    print("✅ 一般法人A プロジェクト2件作成")

    # 取引先（法人A）
    corp_a_client_res = await db["clients"].insert_many([
        {
            "corporate_id": corp_a_id,
            "name": "株式会社モックアルファ",
            "registration_number": "T1111111111111",
            "email": "contact@mockalpha.co.jp",
            "phone": "03-1111-1111",
            "postal_code": "150-0001",
            "address": "東京都渋谷区神宮前1-1-1",
            "department_id": dept_a_ids[0],
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
            "department_id": dept_a_ids[1],
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
            "department_id": dept_a_ids[2],
            "contact_person": "山本 健太",
            "payment_terms": "月末締め翌々月払い",
            "internal_notes": "サーバー・SaaS費用",
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "株式会社テックソリューション",
            "registration_number": "T4444444444441",
            "email": "info@techsolution.co.jp",
            "phone": "03-4444-1111",
            "postal_code": "101-0051",
            "address": "東京都千代田区神田神保町2-2-2",
            "department_id": dept_a_ids[2],
            "contact_person": "木村 浩二",
            "payment_terms": "月末締め翌月末払い",
            "internal_notes": "ITインフラ・クラウド",
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "山田コンサルティング株式会社",
            "registration_number": "T5555555555551",
            "email": "billing@yamada-consulting.co.jp",
            "phone": "03-5555-1111",
            "postal_code": "107-0052",
            "address": "東京都港区赤坂4-4-4",
            "department_id": dept_a_ids[1],
            "contact_person": "山田 一郎",
            "payment_terms": "納品後60日以内",
            "internal_notes": "経営戦略コンサルタント",
            "created_at": today,
        },
    ])
    corp_a_client_ids = [str(i) for i in corp_a_client_res.inserted_ids]
    print("✅ 一般法人A 取引先5件作成")

    # 取引先口座（法人A）
    await db["bank_accounts"].insert_many([
        {
            "corporate_id": corp_a_id,
            "owner_type": "client",
            "client_id": corp_a_client_ids[0],
            "profile_id": None,
            "bank_name": "東京都民銀行", "branch_name": "渋谷支店",
            "bank_code": "0522", "branch_code": "101",
            "account_type": "ordinary", "account_number": "3333333",
            "account_holder": "カブシキガイシャモックアルファ",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "owner_type": "client",
            "client_id": corp_a_client_ids[1],
            "profile_id": None,
            "bank_name": "りそな銀行", "branch_name": "新宿支店",
            "bank_code": "0010", "branch_code": "202",
            "account_type": "ordinary", "account_number": "4444444",
            "account_holder": "デザインジムショクリエイト",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "owner_type": "client",
            "client_id": corp_a_client_ids[2],
            "profile_id": None,
            "bank_name": "みずほ銀行", "branch_name": "丸の内支店",
            "bank_code": "0001", "branch_code": "303",
            "account_type": "ordinary", "account_number": "5555555",
            "account_holder": "クラウドサービスカブシキガイシャ",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "owner_type": "client",
            "client_id": corp_a_client_ids[3],
            "profile_id": None,
            "bank_name": "三井住友銀行", "branch_name": "神田支店",
            "bank_code": "0009", "branch_code": "111",
            "account_type": "ordinary", "account_number": "9999990",
            "account_holder": "カブシキガイシャテックソリューション",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "owner_type": "client",
            "client_id": corp_a_client_ids[4],
            "profile_id": None,
            "bank_name": "みずほ銀行", "branch_name": "赤坂支店",
            "bank_code": "0001", "branch_code": "221",
            "account_type": "ordinary", "account_number": "9999991",
            "account_holder": "ヤマダコンサルティングカブシキガイシャ",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
    ])
    print("✅ 一般法人A 取引先口座5件作成")

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

    # 承認ルール追加（法人A）：高額経費 / 全請求書 / プロジェクト
    await db["approval_rules"].insert_many([
        {
            "corporate_id": corp_a_id,
            "name": "高額経費承認（5万円以上）",
            "applies_to": ["receipt"],
            "conditions": [{"field": "amount", "operator": ">=", "value": 50000}],
            "steps": [
                {"step": 1, "role": "dept_manager", "required": True},
                {"step": 2, "role": "accounting", "required": True},
            ],
            "active": True,
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "全請求書承認",
            "applies_to": ["received_invoice"],
            "conditions": [{"field": "always", "operator": "", "value": ""}],
            "steps": [{"step": 1, "role": "accounting", "required": True}],
            "active": True,
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "プロジェクト承認",
            "applies_to": ["project"],
            "conditions": [{"field": "always", "operator": "", "value": ""}],
            "steps": [
                {"step": 1, "role": "direct_manager", "required": True},
                {"step": 2, "role": "dept_manager", "required": True},
            ],
            "project_id": proj_a_ids[0],
            "active": True,
            "created_at": today,
        },
    ])
    print("✅ 一般法人A 承認ルール追加（高額経費 / 全請求書 / プロジェクト）")

    # 請求書（法人A）- リアル受領請求書5件
    await db["invoices"].insert_many([
        {
            "corporate_id": corp_a_id,
            "document_type": "received",
            "invoice_number": "202502-58306-1",
            "client_id": None,
            "client_name": "株式会社アルダグラム",
            "recipient_email": "",
            "issue_date": "2025-02-24",
            "due_date": "2025-03-31",
            "subtotal": 10000,
            "tax_amount": 1000,
            "total_amount": 11000,
            "line_items": [{"description": "2025年03月分 KANNA利用料 月払", "category": "支払手数料", "amount": 10000, "tax_rate": 10}],
            "attachments": [],
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": a_base_rule_id,
            "approval_steps": [{"step": 1, "role": "direct_manager", "required": True}],
            "approval_history": [{"step": 1, "roleId": "direct_manager", "roleName": "直属上長", "status": "pending"}],
            "fiscal_period": "2025-02",
            "created_by": corp_a_id,
            "created_at": today,
            "is_deleted": False,
        },
        {
            "corporate_id": corp_a_id,
            "document_type": "received",
            "invoice_number": "296365-2",
            "client_id": None,
            "client_name": "株式会社Speee",
            "recipient_email": "",
            "issue_date": "2025-02-28",
            "due_date": "2025-03-27",
            "subtotal": 360000,
            "tax_amount": 36000,
            "total_amount": 396000,
            "line_items": [{"description": "紹介料（外装）", "category": "外注費", "amount": 360000, "tax_rate": 10}],
            "attachments": [],
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": a_strict_rule_id,
            "approval_steps": [
                {"step": 1, "role": "accounting", "required": True},
                {"step": 2, "role": "direct_manager", "required": True},
            ],
            "approval_history": [
                {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                {"step": 2, "roleId": "direct_manager", "roleName": "直属上長", "status": "pending"},
            ],
            "fiscal_period": "2025-02",
            "created_by": corp_a_id,
            "created_at": today,
            "is_deleted": False,
        },
        {
            "corporate_id": corp_a_id,
            "document_type": "received",
            "invoice_number": "202503-P_66c2c4ce47d5f-1",
            "client_id": None,
            "client_name": "株式会社 ドアーズ",
            "recipient_email": "",
            "issue_date": "2025-02-28",
            "due_date": "2025-03-15",
            "subtotal": 108000,
            "tax_amount": 10800,
            "total_amount": 118800,
            "line_items": [{"description": "紹介料", "category": "支払手数料", "amount": 108000, "tax_rate": 10}],
            "attachments": [],
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": a_strict_rule_id,
            "approval_steps": [
                {"step": 1, "role": "accounting", "required": True},
                {"step": 2, "role": "direct_manager", "required": True},
            ],
            "approval_history": [
                {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                {"step": 2, "roleId": "direct_manager", "roleName": "直属上長", "status": "pending"},
            ],
            "fiscal_period": "2025-02",
            "created_by": corp_a_id,
            "created_at": today,
            "is_deleted": False,
        },
        {
            "corporate_id": corp_a_id,
            "document_type": "received",
            "invoice_number": "22023106-20250401",
            "client_id": None,
            "client_name": "住宅保証機構株式会社 まもりす倶楽部事務局",
            "recipient_email": "",
            "issue_date": "2025-03-07",
            "due_date": "2025-03-14",
            "subtotal": 39863,
            "tax_amount": 937,
            "total_amount": 40800,
            "line_items": [
                {"description": "まもりす倶楽部会費", "category": "諸会費", "amount": 9373, "tax_rate": 10},
                {"description": "PL保険料", "category": "保険料", "amount": 9490, "tax_rate": 0},
                {"description": "請負業者賠償責任保険（3億円プラン）", "category": "保険料", "amount": 21000, "tax_rate": 0},
            ],
            "attachments": [],
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": a_base_rule_id,
            "approval_steps": [{"step": 1, "role": "direct_manager", "required": True}],
            "approval_history": [{"step": 1, "roleId": "direct_manager", "roleName": "直属上長", "status": "pending"}],
            "fiscal_period": "2025-03",
            "created_by": corp_a_id,
            "created_at": today,
            "is_deleted": False,
        },
        {
            "corporate_id": corp_a_id,
            "document_type": "received",
            "invoice_number": "20250311-003",
            "client_id": None,
            "client_name": "株式会社エースリメイク",
            "recipient_email": "",
            "issue_date": "2025-03-11",
            "due_date": "2025-03-31",
            "subtotal": 260000,
            "tax_amount": 0,
            "total_amount": 260000,
            "line_items": [{"description": "コーキング打替工事 3/11 完工", "category": "外注費", "amount": 260000, "tax_rate": 0}],
            "attachments": [],
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "current_step": 1,
            "approval_rule_id": a_strict_rule_id,
            "approval_steps": [
                {"step": 1, "role": "accounting", "required": True},
                {"step": 2, "role": "direct_manager", "required": True},
            ],
            "approval_history": [
                {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                {"step": 2, "roleId": "direct_manager", "roleName": "直属上長", "status": "pending"},
            ],
            "fiscal_period": "2025-03",
            "created_by": corp_a_id,
            "created_at": today,
            "is_deleted": False,
        },
    ])
    print("✅ 一般法人A リアル受領請求書5件作成（アルダグラム/Speee/ドアーズ/まもりす倶楽部/エースリメイク）")

    # 領収書（法人A）: import_receipts.py で投入するため seed には含めない

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

    # 銀行取引追加（法人A）- リアル請求書に対応する支払候補
    await db["bank_transactions"].insert_many([
        # 支払・未消込（株式会社Speee 396,000円に対応予定）
        {
            "corporate_id": corp_a_id,
            "source_type": "bank",
            "account_name": "みずほ銀行 新宿支店",
            "transaction_date": "2025-03-27",
            "description": "スピー 紹介料",
            "normalized_name": "スピー",
            "amount": 396000,
            "transaction_type": "debit",
            "status": "unmatched",
            "fiscal_period": "2025-03",
            "imported_at": today,
        },
        # 支払・未消込（株式会社ドアーズ 118,800円に対応予定）
        {
            "corporate_id": corp_a_id,
            "source_type": "bank",
            "account_name": "みずほ銀行 新宿支店",
            "transaction_date": "2025-03-15",
            "description": "ドアーズ 紹介料",
            "normalized_name": "ドアーズ",
            "amount": 118800,
            "transaction_type": "debit",
            "status": "unmatched",
            "fiscal_period": "2025-03",
            "imported_at": today,
        },
        # 支払・未消込（株式会社エースリメイク 260,000円に対応予定）
        {
            "corporate_id": corp_a_id,
            "source_type": "bank",
            "account_name": "三井住友銀行 新宿支店",
            "transaction_date": "2025-03-31",
            "description": "エースリメイク コーキング工事",
            "normalized_name": "エースリメイク",
            "amount": 260000,
            "transaction_type": "debit",
            "status": "unmatched",
            "fiscal_period": "2025-03",
            "imported_at": today,
        },
        # 支払・未消込（まもりす倶楽部 40,800円に対応予定）
        {
            "corporate_id": corp_a_id,
            "source_type": "bank",
            "account_name": "三井住友銀行 新宿支店",
            "transaction_date": "2025-03-14",
            "description": "まもりす倶楽部 会費・保険料",
            "normalized_name": "まもりす倶楽部",
            "amount": 40800,
            "transaction_type": "debit",
            "status": "unmatched",
            "fiscal_period": "2025-03",
            "imported_at": today,
        },
        # 支払・未消込（アルダグラム KANNA利用料 11,000円に対応予定）
        {
            "corporate_id": corp_a_id,
            "source_type": "bank",
            "account_name": "三井住友銀行 新宿支店",
            "transaction_date": "2025-03-31",
            "description": "アルダグラム KANNA利用料",
            "normalized_name": "アルダグラム",
            "amount": 11000,
            "transaction_type": "debit",
            "status": "unmatched",
            "fiscal_period": "2025-03",
            "imported_at": today,
        },
        # 支払・未消込（広告費）
        {
            "corporate_id": corp_a_id,
            "source_type": "bank",
            "account_name": "三井住友銀行 新宿支店",
            "transaction_date": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
            "description": "ネット広告プラットフォーム 広告費",
            "normalized_name": "ネット広告",
            "amount": 165000,
            "transaction_type": "debit",
            "status": "unmatched",
            "fiscal_period": today.strftime("%Y-%m"),
            "imported_at": today,
        },
    ])
    print("✅ 一般法人A 追加銀行取引6件作成（リアル請求書に対応する支払候補5件 + 広告費1件）")

    # 消込条件ルール（法人A）
    await db["matching_rules"].insert_many([
        {
            "corporate_id": corp_a_id,
            "name": "取引先グループ名寄せ",
            "target_field": "振込依頼人名",
            "condition_type": "部分一致",
            "condition_value": "グループ会社・支店名の揺れ（例：エースリメイク東京・西日本エースリメイク等）を親会社名に名寄せする",
            "action": "複数請求書を束ねて一括消込候補に提示",
            "is_active": True,
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "少額差額自動消込",
            "target_field": "入金金額",
            "condition_type": "許容誤差範囲内",
            "condition_value": "500円以内",
            "action": "自動消込",
            "is_active": True,
            "created_at": today,
        },
    ])
    print("✅ 一般法人A 消込条件ルール2件作成")

    # 自動仕訳ルール（法人A）
    await db["journal_rules"].insert_many([
        {
            "corporate_id": corp_a_id,
            "name": "Amazon購入費",
            "keyword": "AMAZON",
            "target_field": "摘要",
            "account_subject": "消耗品費",
            "tax_division": "課税仕入 10%",
            "is_active": True,
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "Slack利用料",
            "keyword": "Slack",
            "target_field": "摘要",
            "account_subject": "通信費",
            "tax_division": "課税仕入 10%",
            "is_active": True,
            "created_at": today,
        },
        {
            "corporate_id": corp_a_id,
            "name": "タクシー交通費",
            "keyword": "タクシー",
            "target_field": "摘要",
            "account_subject": "旅費交通費",
            "tax_division": "課税仕入 10%",
            "is_active": True,
            "created_at": today,
        },
    ])
    print("✅ 一般法人A 自動仕訳ルール3件作成")

    print("✅ 一般法人A 承認ルール5件 / 受領請求書5件（リアルデータ）/ 銀行取引8件 / 消込ルール2件 / 仕訳ルール3件 作成（領収書は import_receipts.py で投入）")

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
            "owner_type": "corporate",
            "bank_name": "りそな銀行", "branch_name": "品川支店",
            "bank_code": "0010", "branch_code": "141",
            "account_type": "ordinary", "account_number": "3333333",
            "account_holder": "カブシキガイシャベータ",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": corp_b_id, "profile_id": corp_b_profile_id,
            "owner_type": "corporate",
            "bank_name": "三菱UFJ銀行", "branch_name": "五反田支店",
            "bank_code": "0005", "branch_code": "631",
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
    emp_b_staff_res   = await db["employees"].find_one({"firebase_uid": EMP_B_STAFF_UID})
    emp_b_manager_res = await db["employees"].find_one({"firebase_uid": EMP_B_MANAGER_UID})
    emp_b_staff_id    = str(emp_b_staff_res["_id"])   if emp_b_staff_res   else ""
    emp_b_manager_id  = str(emp_b_manager_res["_id"]) if emp_b_manager_res else ""
    print("✅ 一般法人B 従業員2名作成")

    # プロジェクト（法人B）
    proj_b_res = await db["projects"].insert_many([
        {
            "corporate_id": corp_b_id,
            "name": "新規事業立ち上げプロジェクト",
            "description": "B社 新規事業開発（2025年度）",
            "members": [
                {"user_id": emp_b_manager_id, "name": "渡辺 美咲"},
                {"user_id": emp_b_staff_id,   "name": "伊藤 翔太"},
            ],
            "is_active": True,
            "created_at": today,
            "updated_at": today,
        },
        {
            "corporate_id": corp_b_id,
            "name": "マーケティングキャンペーン",
            "description": "Q2広告戦略プロジェクト",
            "members": [
                {"user_id": emp_b_manager_id, "name": "渡辺 美咲"},
            ],
            "is_active": True,
            "created_at": today,
            "updated_at": today,
        },
    ])
    proj_b_ids = [str(i) for i in proj_b_res.inserted_ids]
    print("✅ 一般法人B プロジェクト2件作成")

    # 取引先（法人B）
    corp_b_client_res = await db["clients"].insert_many([
        {
            "corporate_id": corp_b_id,
            "name": "株式会社ガンマ商事",
            "registration_number": "T4444444444444",
            "email": "contact@gamma.co.jp",
            "phone": "03-4444-4444",
            "postal_code": "140-0002",
            "address": "東京都品川区東品川2-2-2",
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
            "contact_person": "中村 朋子",
            "payment_terms": "月末締め翌々月払い",
            "internal_notes": "消耗品・備品の仕入先",
            "created_at": today,
        },
    ])
    corp_b_client_ids = [str(i) for i in corp_b_client_res.inserted_ids]
    print("✅ 一般法人B 取引先3件作成")

    # 取引先口座（法人B）
    await db["bank_accounts"].insert_many([
        {
            "corporate_id": corp_b_id,
            "owner_type": "client",
            "client_id": corp_b_client_ids[0],
            "profile_id": None,
            "bank_name": "三菱UFJ銀行", "branch_name": "品川支店",
            "bank_code": "0005", "branch_code": "141",
            "account_type": "ordinary", "account_number": "6666666",
            "account_holder": "カブシキガイシャガンマショウジ",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": corp_b_id,
            "owner_type": "client",
            "client_id": corp_b_client_ids[1],
            "profile_id": None,
            "bank_name": "みずほ銀行", "branch_name": "芝公園支店",
            "bank_code": "0001", "branch_code": "191",
            "account_type": "ordinary", "account_number": "7777777",
            "account_holder": "コウコクダイリテンデルタ",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
        {
            "corporate_id": corp_b_id,
            "owner_type": "client",
            "client_id": corp_b_client_ids[2],
            "profile_id": None,
            "bank_name": "三井住友銀行", "branch_name": "港南支店",
            "bank_code": "0009", "branch_code": "391",
            "account_type": "ordinary", "account_number": "8888888",
            "account_holder": "オフィスヨウヒンエプシロン",
            "is_default": True, "is_active": True, "created_at": today, "updated_at": today,
        },
    ])
    print("✅ 一般法人B 取引先口座3件作成")

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

    # 承認ルール追加（法人B）：領収書向け3万円以上
    await db["approval_rules"].insert_one({
        "corporate_id": corp_b_id,
        "name": "経費承認（B社）",
        "applies_to": ["receipt"],
        "conditions": [{"field": "amount", "operator": ">=", "value": 30000}],
        "steps": [{"step": 1, "role": "dept_manager", "required": True}],
        "active": True,
        "created_at": today,
    })

    # 請求書（法人B）- ダミーデータなし（必要に応じてimport_invoices.pyで投入）

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
            "project_id": proj_b_ids[0],
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
    # 消込条件ルール（法人B）- テナント分離確認用
    await db["matching_rules"].insert_one({
        "corporate_id": corp_b_id,
        "name": "B社 振込名義統一",
        "target_field": "振込依頼人名",
        "condition_type": "完全一致",
        "condition_value": "ガンマ商事グループの振込はすべて株式会社ガンマ商事として扱う",
        "action": "複数請求書を束ねて一括消込候補に提示",
        "is_active": True,
        "created_at": today,
    })
    print("✅ 一般法人B 消込条件ルール1件作成")

    # 自動仕訳ルール（法人B）- テナント分離確認用
    await db["journal_rules"].insert_one({
        "corporate_id": corp_b_id,
        "name": "B社 広告費",
        "keyword": "広告",
        "target_field": "摘要",
        "account_subject": "広告宣伝費",
        "tax_division": "課税仕入 10%",
        "is_active": True,
        "created_at": today,
    })
    print("✅ 一般法人B 自動仕訳ルール1件作成")

    print("✅ 一般法人B 承認ルール3件 / 請求書2件 / 領収書2件 / 消込ルール1件 / 仕訳ルール1件 作成")

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
