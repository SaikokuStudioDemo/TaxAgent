from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class DepartmentGroup(BaseModel):
    id: str
    name: str


class DepartmentInDB(BaseModel):
    corporate_id: str
    name: str
    groups: List[DepartmentGroup] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
