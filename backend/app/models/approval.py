from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime

class ApprovalCondition(BaseModel):
    field: str # e.g., "amount"
    operator: str # e.g., ">="
    value: float # or Union[int, float, str]

class ApprovalStep(BaseModel):
    step: int
    role: str  # "group_leader" / "dept_manager" / "specific_person" etc.
    required: bool = True
    user_id: Optional[str] = None       # specific person assignment
    approver_name: Optional[str] = None # display name for specific person

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
    applies_to: List[Literal["receipt", "received_invoice", "issued_invoice", "project"]]
    conditions: List[ApprovalCondition] = []
    steps: List[ApprovalStep]
    active: bool = True
    project_id: Optional[str] = None  # for project-specific rules

class ApprovalRuleUpdate(BaseModel):
    name: Optional[str] = None
    applies_to: Optional[List[Literal["receipt", "received_invoice", "issued_invoice", "project"]]] = None
    conditions: Optional[List[ApprovalCondition]] = None
    steps: Optional[List[ApprovalStep]] = None
    active: Optional[bool] = None
    project_id: Optional[str] = None

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
    approver_id: str = ""  # Overridden by ctx.user_id on the server
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
