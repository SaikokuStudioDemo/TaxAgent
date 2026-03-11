"""
seed_data.py - テスト用シードデータ投入スクリプト

使用方法:
    cd backend
    PYTHONPATH=. venv/bin/python seed_data.py

内容:
    - 2法人（A社: tax_firm, B社: corporate）を作成
    - 各社に従業員（staff / manager）を追加
    - 承認ルール（3万円以上で2ステップ）を設定
    - 取引先マスターを設定
    - 自社プロファイルを設定
    - 領収書（低額/高額）を投入
    - 受領請求書（期限切れ/正常）を投入

目的:
    - データ分離（A社のデータがB社から見えないこと）の確認
    - 承認ルール自動適用の確認
    - アラート生成の確認
"""

import asyncio
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "tax_agent"

# Firebase UID の代わりに固定の識別子を使用（テスト環境用）
CORP_A_UID = "seed_corp_a_uid"  # 税理士事務所
CORP_B_UID = "seed_corp_b_uid"  # 一般法人
EMP_A_STAFF_UID = "seed_emp_a_staff"
EMP_A_MANAGER_UID = "seed_emp_a_manager"
EMP_B_STAFF_UID = "seed_emp_b_staff"


async def seed():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    print(f"\n🌱 Seeding database: {DB_NAME}\n")

    # ─────── 全シードデータをクリア ───────
    seed_uids = [CORP_A_UID, CORP_B_UID]
    for uid in seed_uids:
        corp = await db["corporates"].find_one({"firebase_uid": uid})
        if corp:
            cid = str(corp["_id"])
            for col in ["employees", "receipts", "invoices", "approval_rules",
                        "clients", "company_profiles", "notifications",
                        "bank_transactions", "matches", "approval_events"]:
                await db[col].delete_many({"corporate_id": cid})
    await db["corporates"].delete_many({"firebase_uid": {"$in": seed_uids}})
    await db["employees"].delete_many({"firebase_uid": {
        "$in": [EMP_A_STAFF_UID, EMP_A_MANAGER_UID, EMP_B_STAFF_UID]
    }})
    print("✅ 既存シードデータをクリアしました")

    # ─────── 法人A（税理士事務所） ───────
    res_a = await db["corporates"].insert_one({
        "firebase_uid": CORP_A_UID,
        "corporateType": "tax_firm",
        "planId": "plan_premium",
        "monthlyFee": 30000,
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    corp_a_id = str(res_a.inserted_id)
    print(f"✅ 法人A (tax_firm) 作成: {corp_a_id}")

    # ─────── 法人B（一般法人） ───────
    res_b = await db["corporates"].insert_one({
        "firebase_uid": CORP_B_UID,
        "corporateType": "corporate",
        "planId": "plan_basic",
        "monthlyFee": 10000,
        "advising_tax_firm_id": CORP_A_UID,
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    corp_b_id = str(res_b.inserted_id)
    print(f"✅ 法人B (corporate) 作成: {corp_b_id}")

    # ─────── 従業員（A社: staff / manager） ───────
    await db["employees"].insert_one({
        "firebase_uid": EMP_A_STAFF_UID,
        "parent_corporate_firebase_uid": CORP_A_UID,
        "corporate_id": corp_a_id,
        "role": "staff",
        "email": "staff_a@example.com",
        "permissions": {"submit_receipt": True},
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    emp_manager_res = await db["employees"].insert_one({
        "firebase_uid": EMP_A_MANAGER_UID,
        "parent_corporate_firebase_uid": CORP_A_UID,
        "corporate_id": corp_a_id,
        "role": "dept_manager",
        "email": "manager_a@example.com",
        "permissions": {"approve": True},
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    emp_manager_id = str(emp_manager_res.inserted_id)
    await db["employees"].insert_one({
        "firebase_uid": EMP_B_STAFF_UID,
        "parent_corporate_firebase_uid": CORP_B_UID,
        "corporate_id": corp_b_id,
        "role": "staff",
        "email": "staff_b@example.com",
        "permissions": {"submit_receipt": True},
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    print("✅ 従業員を作成しました（A社: staff + manager, B社: staff）")

    # ─────── 承認ルール（A社用） ───────
    rule_res = await db["approval_rules"].insert_one({
        "corporate_id": corp_a_id,
        "name": "3万円以上の経費承認",
        "applies_to": ["receipt", "received_invoice"],
        "conditions": [{"field": "amount", "operator": ">=", "value": 30000}],
        "steps": [
            {"step": 1, "role": "group_leader", "required": True},
            {"step": 2, "role": "dept_manager", "required": True},
        ],
        "active": True,
        "created_at": datetime.utcnow(),
    })
    rule_id = str(rule_res.inserted_id)
    print(f"✅ 承認ルール作成: {rule_id}")

    # ─────── 取引先（A社） ───────
    await db["clients"].insert_many([
        {
            "corporate_id": corp_a_id,
            "name": "株式会社サンプル商事",
            "registration_number": "T1234567890123",
            "email": "contact@sample-trading.co.jp",
            "phone": "03-1234-5678",
            "address": "東京都港区1-1-1",
            "payment_terms": "月末締め翌月末払い",
            "created_at": datetime.utcnow(),
        },
        {
            "corporate_id": corp_a_id,
            "name": "テックスタート株式会社",
            "email": "billing@techstart.co.jp",
            "payment_terms": "30日以内",
            "created_at": datetime.utcnow(),
        },
    ])
    print("✅ 取引先マスター作成（A社: 2件）")

    # ─────── 自社プロファイル（A社） ───────
    await db["company_profiles"].insert_one({
        "corporate_id": corp_a_id,
        "profile_name": "メインプロファイル",
        "company_name": "青山税理士事務所",
        "registration_number": "T9876543210987",
        "address": "東京都渋谷区2-2-2",
        "bank_info": "三井住友銀行 新宿支店 普通 1234567",
        "is_default": True,
        "created_at": datetime.utcnow(),
    })
    print("✅ 自社プロファイル作成（A社）")

    today = datetime.utcnow()

    # ─────── 領収書（A社） ───────
    # 低額: ルール適用なし
    await db["receipts"].insert_one({
        "corporate_id": corp_a_id,
        "submitted_by": corp_a_id,
        "date": today.strftime("%Y-%m-%d"),
        "amount": 3500,
        "tax_rate": 10,
        "payee": "コンビニエンスストア",
        "category": "雑費",
        "payment_method": "立替",
        "fiscal_period": today.strftime("%Y-%m"),
        "status": "pending_approval",
        "review_status": "unreviewed",
        "approval_rule_id": None,  # 低額なのでルールなし
        "current_step": 1,
        "high_amount_alerted": False,
        "ai_extracted": False,
        "created_at": today,
    })

    # 高額: ルール適用あり
    await db["receipts"].insert_one({
        "corporate_id": corp_a_id,
        "submitted_by": corp_a_id,
        "date": today.strftime("%Y-%m-%d"),
        "amount": 85000,
        "tax_rate": 10,
        "payee": "株式会社オフィス用品",
        "category": "消耗品費",
        "payment_method": "法人カード",
        "fiscal_period": today.strftime("%Y-%m"),
        "status": "pending_approval",
        "review_status": "unreviewed",
        "approval_rule_id": rule_id,  # ルール適用
        "current_step": 1,
        "high_amount_alerted": False,
        "ai_extracted": False,
        "created_at": today,
    })

    # 超高額（アラート対象）
    await db["receipts"].insert_one({
        "corporate_id": corp_a_id,
        "submitted_by": corp_a_id,
        "date": today.strftime("%Y-%m-%d"),
        "amount": 150000,
        "tax_rate": 10,
        "payee": "パソコン専門店",
        "category": "備品費",
        "payment_method": "銀行振込",
        "fiscal_period": today.strftime("%Y-%m"),
        "status": "pending_approval",
        "review_status": "unreviewed",
        "approval_rule_id": rule_id,
        "current_step": 1,
        "high_amount_alerted": False,
        "ai_extracted": True,
        "created_at": today,
    })
    print("✅ 領収書作成（A社: 3件 — 低額/高額/超高額）")

    # ─────── 請求書（A社） ───────
    # 発行請求書（正常）
    await db["invoices"].insert_one({
        "corporate_id": corp_a_id,
        "direction": "issued",
        "invoice_number": "INV-2025-001",
        "client_id": None,
        "client_name": "株式会社サンプル商事",
        "recipient_email": "contact@sample-trading.co.jp",
        "issue_date": today.strftime("%Y-%m-%d"),
        "due_date": (today + timedelta(days=30)).strftime("%Y-%m-%d"),
        "subtotal": 100000,
        "tax_amount": 10000,
        "total_amount": 110000,
        "status": "sent",
        "review_status": "approved",
        "current_step": 1,
        "approval_rule_id": None,
        "is_temporary_approval_needed": False,
        "is_auto_send_enabled": True,
        "fiscal_period": today.strftime("%Y-%m"),
        "ai_extracted": False,
        "created_by": corp_a_id,
        "created_at": today,
        "paid_at": None,
        "line_items": [
            {"description": "税務顧問料 3月分", "category": "売上", "amount": 100000, "tax_rate": 10}
        ],
        "high_amount_alerted": False,
    })

    # 受領請求書（期限切れ: アラート対象）
    overdue_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    await db["invoices"].insert_one({
        "corporate_id": corp_a_id,
        "direction": "received",
        "invoice_number": "REC-INV-001",
        "client_name": "テックスタート株式会社",
        "recipient_email": "billing@techstart.co.jp",
        "issue_date": (today - timedelta(days=37)).strftime("%Y-%m-%d"),
        "due_date": overdue_date,  # 期限切れ
        "subtotal": 200000,
        "tax_amount": 20000,
        "total_amount": 220000,
        "status": "received",
        "review_status": "unreviewed",
        "current_step": 1,
        "approval_rule_id": rule_id,
        "is_temporary_approval_needed": False,
        "is_auto_send_enabled": False,
        "fiscal_period": today.strftime("%Y-%m"),
        "ai_extracted": False,
        "created_by": corp_a_id,
        "created_at": today,
        "paid_at": None,
        "high_amount_alerted": False,
    })

    # 受領請求書（期限3日前: 警告対象）
    near_due = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    await db["invoices"].insert_one({
        "corporate_id": corp_a_id,
        "direction": "received",
        "invoice_number": "REC-INV-002",
        "client_name": "株式会社サンプル商事",
        "recipient_email": "contact@sample-trading.co.jp",
        "issue_date": (today - timedelta(days=28)).strftime("%Y-%m-%d"),
        "due_date": near_due,
        "subtotal": 50000,
        "tax_amount": 5000,
        "total_amount": 55000,
        "status": "received",
        "review_status": "unreviewed",
        "current_step": 1,
        "approval_rule_id": rule_id,
        "is_temporary_approval_needed": False,
        "is_auto_send_enabled": False,
        "fiscal_period": today.strftime("%Y-%m"),
        "ai_extracted": False,
        "created_by": corp_a_id,
        "created_at": today,
        "paid_at": None,
        "high_amount_alerted": False,
    })
    print("✅ 請求書作成（A社: 3件 — 発行1/受領期限切れ1/受領期限3日前1）")

    # ─────── B社にも領収書を追加（データ分離テスト用） ───────
    await db["receipts"].insert_one({
        "corporate_id": corp_b_id,
        "submitted_by": corp_b_id,
        "date": today.strftime("%Y-%m-%d"),
        "amount": 12000,
        "tax_rate": 10,
        "payee": "B社の取引先",
        "category": "交際費",
        "payment_method": "立替",
        "fiscal_period": today.strftime("%Y-%m"),
        "status": "pending_approval",
        "review_status": "unreviewed",
        "approval_rule_id": None,
        "current_step": 1,
        "created_at": today,
    })
    print("✅ B社にも領収書1件追加（データ分離テスト用）")

    print("\n" + "=" * 60)
    print("🎉 シードデータの投入が完了しました！")
    print("=" * 60)
    print(f"\n【確認用情報】")
    print(f"  法人A (tax_firm)  corporate_id : {corp_a_id}")
    print(f"  法人A Firebase UID             : {CORP_A_UID}")
    print(f"  法人B (corporate) corporate_id : {corp_b_id}")
    print(f"  法人B Firebase UID             : {CORP_B_UID}")
    print(f"\n  ※ API テスト時は Authorization: Bearer test-token を使用してください")
    print(f"  ※ テスト用トークンは conftest.py の mock UID と紐付いています")
    print(f"\n  Swagger UI: http://localhost:8000/api/v1/openapi.json")
    print(f"  Swagger Docs: http://localhost:8000/docs\n")

    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
