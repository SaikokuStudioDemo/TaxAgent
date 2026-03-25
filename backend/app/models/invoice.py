from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from app.models.approval import ApprovalHistoryItem, AddedApprovalStep

class InvoiceLineItem(BaseModel):
    description: str
    category: str
    amount: int
    tax_rate: int

class InvoiceCreate(BaseModel):
    document_type: Literal["issued", "received"]
    invoice_number: str
    client_id: Optional[str] = None
    client_name: str
    recipient_email: str # Used as "送付先" in the frontend
    issue_date: str # YYYY-MM-DD
    due_date: str # YYYY-MM-DD
    subtotal: int
    tax_amount: int
    total_amount: int
    line_items: List[InvoiceLineItem] = []
    template_id: Optional[str] = None
    bank_account_id: Optional[str] = None
    is_temporary_approval_needed: bool = False
    is_auto_send_enabled: bool = False
    attachments: List[str] = []
    approval_status: Optional[str] = None

class InvoiceInDB(InvoiceCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    approval_status: str = "draft"
    delivery_status: Literal["unsent", "sent"] = "unsent"
    reconciliation_status: Literal["unreconciled", "reconciled"] = "unreconciled"
    current_step: int = 1
    approval_rule_id: Optional[str] = None
    approval_history: List[ApprovalHistoryItem] = []
    extra_approval_steps: List[AddedApprovalStep] = []
    attachments: List[str] = []
    fiscal_period: str # e.g., "2024-03"
    ai_extracted: bool = False
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    paid_at: Optional[datetime] = None
    is_deleted: bool = False

class InvoiceResponse(InvoiceInDB):
    pass
