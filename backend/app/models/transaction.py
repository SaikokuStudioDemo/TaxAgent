from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from app.models.approval import ApprovalHistoryItem, AddedApprovalStep
from app.models.project import ProjectApprover

class ReceiptLineItem(BaseModel):
    description: str
    category: str
    amount: int
    tax_rate: int

class ReceiptCreate(BaseModel):
    date: str # YYYY-MM-DD
    amount: int
    tax_rate: int
    payee: str
    category: str
    payment_method: Literal["立替", "法人カード", "銀行振込"]
    line_items: List[ReceiptLineItem] = []
    attachments: List[str] = []
    fiscal_period: str
    ai_extracted: bool = False
    project_id: Optional[str] = None
    custom_approvers: Optional[List[ProjectApprover]] = None

class ReceiptInDB(ReceiptCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    submitted_by: str
    approval_status: str = "pending_approval"
    reconciliation_status: Literal["unreconciled", "reconciled"] = "unreconciled"
    approval_rule_id: Optional[str] = None
    approval_history: List[ApprovalHistoryItem] = []
    extra_approval_steps: List[AddedApprovalStep] = []
    current_step: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TransactionInDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    source_type: Literal["bank", "card"]
    account_name: str
    transaction_date: str # YYYY-MM-DD
    description: str
    normalized_name: Optional[str] = None
    amount: int
    transaction_type: Literal["credit", "debit"]
    status: Literal["unmatched", "matched"] = "unmatched"
    fiscal_period: str
    imported_at: datetime = Field(default_factory=datetime.utcnow)

class MatchCreate(BaseModel):
    match_type: Literal["receipt", "invoice"]
    transaction_ids: List[str]
    document_ids: List[str]
    total_transaction_amount: int
    total_document_amount: int
    difference: int
    difference_treatment: Optional[str] = None
    matched_by: Literal["ai", "manual"]
    journal_entries: List[dict] = []
    fiscal_period: str

class MatchInDB(MatchCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    matched_at: datetime = Field(default_factory=datetime.utcnow)
