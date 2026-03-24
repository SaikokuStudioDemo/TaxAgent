import sys
import os
import asyncio
from datetime import datetime
from bson import ObjectId

# Add backend directory to sys path so we can import from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.mongodb import get_database, connect_to_mongo, close_mongo_connection

async def seed():
    await connect_to_mongo()
    db = get_database()
    
    print("Finding all corporate_ids...")
    corps = await db["corporates"].find().to_list(100)
    if not corps:
        res = await db["corporates"].insert_one({"name": "Seed Corporate"})
        corps = [{"_id": res.inserted_id}]
        print("Created new corporate since DB was empty.")

    for corp in corps:
        corporate_id = str(corp["_id"])
        print(f"\nProcessing corporate_id: {corporate_id}")

        # Clean existing data to avoid duplicates/bloat
        print(f"  Cleaning old mock data for {corporate_id}...")
        await db["approval_rules"].delete_many({"corporate_id": corporate_id})
        await db["invoices"].delete_many({"corporate_id": corporate_id})
        await db["receipts"].delete_many({"corporate_id": corporate_id})
        await db["approval_events"].delete_many({"corporate_id": corporate_id})

        print("  Inserting Approval Rules...")
        rules = [
            {
                "name": "（テスト）経理確認＋部長承認 (10万円以上)",
                "applies_to": ["receipt", "received_invoice", "issued_invoice"],
                "conditions": [{"field": "amount", "operator": ">=", "value": 100000}],
                "steps": [
                    {"step": 1, "role": "accounting", "required": True},
                    {"step": 2, "role": "direct_manager", "required": True}
                ],
                "active": True,
                "corporate_id": corporate_id,
                "created_at": datetime.utcnow()
            },
            {
                "name": "（テスト）基本ルート (全件対象)",
                "applies_to": ["receipt", "received_invoice", "issued_invoice"],
                "conditions": [{"field": "always", "operator": "", "value": ""}],
                "steps": [
                    {"step": 1, "role": "direct_manager", "required": True}
                ],
                "active": True,
                "corporate_id": corporate_id,
                "created_at": datetime.utcnow()
            }
        ]
        await db["approval_rules"].insert_many(rules)
        
        base_rule = await db["approval_rules"].find_one({"name": "（テスト）基本ルート (全件対象)", "corporate_id": corporate_id})
        strict_rule = await db["approval_rules"].find_one({"name": "（テスト）経理確認＋部長承認 (10万円以上)", "corporate_id": corporate_id})
        base_rule_id = str(base_rule["_id"])
        strict_rule_id = str(strict_rule["_id"])

        print("  Inserting Invoices...")
        invoices = [
            {
                "direction": "issued",
                "invoice_number": "INV-MOCK-001",
                "client_name": "株式会社モックアルファ",
                "recipient_email": "alpha@example.com",
                "issue_date": "2024-03-01",
                "due_date": "2024-03-31",
                "subtotal": 50000,
                "tax_amount": 5000,
                "total_amount": 55000,
                "line_items": [{"description": "コンサルティング費用", "category": "売上", "amount": 50000, "tax_rate": 10}],
                "status": "pending_approval",
                "review_status": "unreviewed",
                "current_step": 1,
                "approval_rule_id": base_rule_id,
                "approval_history": [
                    {"step": 1, "roleId": "direct_manager", "roleName": "直属の部門長", "status": "pending"}
                ],
                "corporate_id": corporate_id,
                "fiscal_period": "2024-03",
                "created_by": "system",
                "created_at": datetime.utcnow(),
                "is_deleted": False
            },
            {
                "direction": "received",
                "invoice_number": "REC-MOCK-001",
                "client_name": "（受領）デザイン事務所",
                "recipient_email": "design@example.com",
                "issue_date": "2024-03-10",
                "due_date": "2024-04-10",
                "subtotal": 150000,
                "tax_amount": 15000,
                "total_amount": 165000,
                "line_items": [{"description": "ロゴデザイン費用", "category": "外注費", "amount": 150000, "tax_rate": 10}],
                "status": "pending_approval",
                "review_status": "unreviewed",
                "current_step": 1,
                "approval_rule_id": strict_rule_id,
                "approval_history": [
                    {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                    {"step": 2, "roleId": "direct_manager", "roleName": "直属の部門長", "status": "pending"}
                ],
                "corporate_id": corporate_id,
                "fiscal_period": "2024-03",
                "created_by": "system",
                "created_at": datetime.utcnow(),
                "is_deleted": False
            },
            {
                "direction": "received",
                "invoice_number": "REC-MOCK-002",
                "client_name": "（受領）クラウドサービス",
                "recipient_email": "cloud@example.com",
                "issue_date": "2024-02-28",
                "due_date": "2024-03-28",
                "subtotal": 80000,
                "tax_amount": 8000,
                "total_amount": 88000,
                "line_items": [{"description": "サーバー利用料", "category": "通信費", "amount": 80000, "tax_rate": 10}],
                "status": "approved",
                "review_status": "approved",
                "current_step": 2,
                "approval_rule_id": base_rule_id,
                "approval_history": [
                    {"step": 1, "roleId": "direct_manager", "roleName": "直属の部門長", "status": "approved", "approverName": "山田太郎", "actionDate": "2024-03-01"}
                ],
                "corporate_id": corporate_id,
                "fiscal_period": "2024-02",
                "created_by": "system",
                "created_at": datetime.utcnow(),
                "is_deleted": False
            }
        ]
        await db["invoices"].insert_many(invoices)

        print("  Inserting Receipts...")
        receipts = [
            {
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
                "corporate_id": corporate_id,
                "submitted_by": "system",
                "status": "pending_approval",
                "review_status": "unreviewed",
                "current_step": 1,
                "approval_rule_id": base_rule_id,
                "approval_history": [
                    {"step": 1, "roleId": "direct_manager", "roleName": "直属の部門長", "status": "pending"}
                ],
                "created_at": datetime.utcnow()
            },
            {
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
                "corporate_id": corporate_id,
                "submitted_by": "system",
                "status": "pending_approval",
                "review_status": "unreviewed",
                "current_step": 1,
                "approval_rule_id": strict_rule_id,
                "approval_history": [
                    {"step": 1, "roleId": "accounting", "roleName": "経理担当", "status": "pending"},
                    {"step": 2, "roleId": "direct_manager", "roleName": "直属の部門長", "status": "pending"}
                ],
                "created_at": datetime.utcnow()
            }
        ]
        await db["receipts"].insert_many(receipts)
    
    print("\nMock data seeded successfully!")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed())
