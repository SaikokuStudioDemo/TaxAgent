from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class CashAccountCreate(BaseModel):
    name: str
    initial_balance: int = 0


class CashAccountInDB(CashAccountCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    current_balance: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CashTransactionCreate(BaseModel):
    cash_account_id: str
    transaction_date: str
    amount: int
    direction: Literal["income", "expense"]
    description: str
    category: str
    fiscal_period: str
    source: Literal["manual", "bank_import"] = "manual"
    linked_bank_transaction_id: Optional[str] = None
    linked_document_id: Optional[str] = None
    linked_document_type: Optional[Literal["receipt", "invoice"]] = None
    note: Optional[str] = None


class CashTransactionInDB(CashTransactionCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    status: Literal["unmatched", "matched"] = "unmatched"
    created_at: datetime = Field(default_factory=datetime.utcnow)
