from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ProjectMember(BaseModel):
    user_id: str
    name: str


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    members: List[ProjectMember] = []


class ProjectInDB(ProjectCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
