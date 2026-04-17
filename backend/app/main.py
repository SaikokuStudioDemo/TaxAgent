import logging
from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database
from app.services.alert_service import run_all_alerts
from app.api.routes import users, receipts, invoices, approvals, clients, company_profiles, transactions, matches, admin, advisor, departments, bank_accounts, projects, journal_rules, cash, bank_imports, matching_patterns, invitations, permission_settings, ocr, alerts_config, billing_settings, system_settings, stripe_webhook, exports, budgets

logger = logging.getLogger(__name__)


async def _seed_system_settings(db) -> None:
    """
    system_settings の初期データを投入する。
    既にデータがある場合はスキップ（冪等性を保つ）。
    """
    existing = await db["system_settings"].find_one({"key": "plans"})
    if existing:
        return

    now = datetime.utcnow()
    await db["system_settings"].insert_many([
        {
            "key": "plans",
            "value": [
                {
                    "id": "plan_basic",
                    "name": "ベーシックプラン",
                    "price": 15000,
                    "max_users": 5,
                    "max_clients": 10,
                    "features": ["基本機能", "月間500件までのデータ処理", "メールサポート"],
                },
                {
                    "id": "plan_standard",
                    "name": "スタンダードプラン",
                    "price": 30000,
                    "max_users": 20,
                    "max_clients": 50,
                    "features": ["全機能アクセス", "無制限のデータ処理", "チャット・電話サポート", "優先処理"],
                },
                {
                    "id": "plan_premium",
                    "name": "プレミアムプラン",
                    "price": 50000,
                    "max_users": None,
                    "max_clients": None,
                    "features": ["AIによる自動仕訳", "専任サポート担当", "カスタムレポート作成", "SLA保証"],
                },
            ],
            "updated_by": "system",
            "updated_at": now,
        },
        {
            "key": "options",
            "value": [
                {"id": "opt-data-storage", "name": "拡張データストレージ (500GB)", "price": 5000},
                {"id": "opt-api-access", "name": "外部API連携オプション", "price": 10000},
            ],
            "updated_by": "system",
            "updated_at": now,
        },
        {
            "key": "ai_credit_limits",
            "value": {"plan_basic": 100, "plan_standard": 500, "plan_premium": 2000},
            "updated_by": "system",
            "updated_at": now,
        },
        {
            "key": "platform_fee_rate",
            "value": 0.20,
            "updated_by": "system",
            "updated_at": now,
        },
    ])
    logger.info("[Seed] system_settings initialized")


async def reset_monthly_ai_usage() -> None:
    """毎月1日0:00（JST = UTC 15:00）に monthly_ai_usage を0にリセット。"""
    db = get_database()
    result = await db["corporates"].update_many(
        {},
        {"$set": {"monthly_ai_usage": 0}},
    )
    logger.info(f"[Scheduler] monthly_ai_usage reset: {result.modified_count} docs")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_to_mongo()

    # system_settings の初期データ投入（冪等）
    db = get_database()
    await _seed_system_settings(db)

    # APScheduler：アラートバッチ + 月次リセット
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_all_alerts,
        "cron",
        hour=8,
        minute=0,
        id="daily_alerts",
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        reset_monthly_ai_usage,
        "cron",
        day=1,
        hour=15,   # UTC 15:00 = JST 0:00
        minute=0,
        id="monthly_ai_usage_reset",
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("APScheduler started: alert batch @ 8:00 AM / AI usage reset @ 1st 15:00 UTC daily")

    yield

    # Shutdown
    scheduler.shutdown()
    await close_mongo_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(receipts.router, prefix=f"{settings.API_V1_STR}/receipts", tags=["receipts"])
app.include_router(invoices.router, prefix=f"{settings.API_V1_STR}/invoices", tags=["invoices"])
app.include_router(approvals.router, prefix=f"{settings.API_V1_STR}/approvals", tags=["approvals"])
app.include_router(clients.router, prefix=f"{settings.API_V1_STR}/clients", tags=["clients"])
app.include_router(company_profiles.router, prefix=f"{settings.API_V1_STR}/company-profiles", tags=["company-profiles"])
app.include_router(transactions.router, prefix=f"{settings.API_V1_STR}/transactions", tags=["transactions"])
app.include_router(matches.router, prefix=f"{settings.API_V1_STR}/matches", tags=["matches"])
app.include_router(admin.router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
app.include_router(advisor.router, prefix=f"{settings.API_V1_STR}/advisor", tags=["advisor"])
app.include_router(departments.router, prefix=f"{settings.API_V1_STR}/departments", tags=["departments"])
app.include_router(bank_accounts.router, prefix=f"{settings.API_V1_STR}/bank-accounts", tags=["bank-accounts"])
app.include_router(projects.router, prefix=f"{settings.API_V1_STR}/projects", tags=["projects"])
app.include_router(journal_rules.router, prefix=f"{settings.API_V1_STR}/journal-rules", tags=["journal-rules"])
app.include_router(cash.router, prefix=f"{settings.API_V1_STR}", tags=["cash"])
app.include_router(bank_imports.router, prefix=f"{settings.API_V1_STR}/bank-import-files", tags=["bank_imports"])
app.include_router(matching_patterns.router, prefix=f"{settings.API_V1_STR}/matching-patterns", tags=["matching-patterns"])
app.include_router(invitations.router, prefix=f"{settings.API_V1_STR}/invitations", tags=["invitations"])
app.include_router(permission_settings.router, prefix=f"{settings.API_V1_STR}/permission-settings", tags=["permission-settings"])
app.include_router(ocr.router, prefix=f"{settings.API_V1_STR}/ocr", tags=["ocr"])
app.include_router(alerts_config.router, prefix=f"{settings.API_V1_STR}/alerts-config", tags=["alerts-config"])
app.include_router(billing_settings.router, prefix=f"{settings.API_V1_STR}/billing-settings", tags=["billing-settings"])
app.include_router(system_settings.router, prefix=f"{settings.API_V1_STR}/system-settings", tags=["system-settings"])
# ⑥ Webhook は /api/v1 プレフィックスなし（Stripe ダッシュボードの URL と一致させる）
app.include_router(stripe_webhook.router, prefix="/webhook", tags=["webhook"])
app.include_router(exports.router, prefix=f"{settings.API_V1_STR}/exports", tags=["exports"])
app.include_router(budgets.router, prefix=f"{settings.API_V1_STR}/budgets", tags=["budgets"])


@app.get("/")
def read_root():
    return {"message": "Welcome to Tax-Agent API"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
