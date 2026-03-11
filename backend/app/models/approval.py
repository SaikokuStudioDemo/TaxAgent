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

class ApprovalEventCreate(BaseModel):
    document_type: Literal["receipt", "invoice"]
    document_id: str
    step: int
    approver_id: str
    action: Literal["approved", "rejected", "returned"]
    comment: Optional[str] = None

class ApprovalEventInDB(ApprovalEventCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
