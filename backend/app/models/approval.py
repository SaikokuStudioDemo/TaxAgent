from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime

class ApprovalCondition(BaseModel):
    field: str # e.g., "amount"
    operator: str # e.g., ">="
    value: float # or Union[int, float, str]

class ApprovalStep(BaseModel):
    step: int
    role: str # "group_leader" / "dept_manager" / "admin" etc.
    required: bool = True

class ApprovalHistoryItem(BaseModel):
    step: int
    roleId: str
    roleName: Optional[str] = None
    status: str = "pending" # pending / approved / rejected / returned
    approverName: Optional[str] = None
    actionDate: Optional[str] = None
    comment: Optional[str] = None

class ApprovalRuleCreate(BaseModel):
    name: str
    applies_to: List[Literal["receipt", "received_invoice", "issued_invoice"]]
    conditions: List[ApprovalCondition] = []
    steps: List[ApprovalStep]
    active: bool = True

class ApprovalRuleInDB(ApprovalRuleCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AddedApprovalStep(BaseModel):
    roleId: str
    roleName: str
    approverName: Optional[str] = None

class ApprovalEventCreate(BaseModel):
    document_type: Literal["receipt", "invoice", "received_invoice", "issued_invoice"]
    document_id: str
    step: int
    approver_id: str
    action: Literal["approved", "rejected", "returned"]
    comment: Optional[str] = None
    added_steps: Optional[List[AddedApprovalStep]] = None

class ApprovalPreviewRequest(BaseModel):
    document_type: Literal["receipt", "received_invoice", "issued_invoice"]
    amount: float
    payload: Optional[dict] = None

class ApprovalEventInDB(ApprovalEventCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
