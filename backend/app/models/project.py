from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ProjectApprover(BaseModel):
    user_id: str
    name: str
    order: int


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    approvers: List[ProjectApprover] = []


class ProjectInDB(ProjectCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
