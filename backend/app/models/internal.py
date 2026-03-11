from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime

class NotificationInDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    type: str # approval_request / due_date_alert / overdue_alert etc.
    recipient_employee_id: str
    recipient_email: str
    related_document_type: Literal["receipt", "invoice"]
    related_document_id: str
    message: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    status: str # sent / failed

class SalesAgentInDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    name: str
    role: Literal["agent", "team_leader"]
    parent_agent_id: Optional[str] = None
    commission_rate: float
    is_active: bool = True

class DeveloperProfileInDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    name: str
    company: str = "SAIKOKU STUDIO"
    revenue_ratio: float
    role: str
    is_active: bool = True

class RevenueDistributionSplit(BaseModel):
    type: Literal["sales_agent", "tax_firm", "developer", "company", "taxagent"]
    id: str
    name: str
    ratio: float
    amount: int

class RevenueDistributionInDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    fiscal_period: str # YYYY-MM
    total_revenue: int
    client_count: int
    splits: List[RevenueDistributionSplit]
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
