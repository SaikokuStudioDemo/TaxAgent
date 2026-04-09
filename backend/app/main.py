from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.db.mongodb import connect_to_mongo, close_mongo_connection
from app.api.routes import users, receipts, invoices, approvals, clients, company_profiles, transactions, matches, admin, advisor, departments, bank_accounts, projects, journal_rules, cash, bank_imports, matching_patterns

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_to_mongo()
    yield
    # Shutdown
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


@app.get("/")
def read_root():
    return {"message": "Welcome to Tax-Agent API"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
