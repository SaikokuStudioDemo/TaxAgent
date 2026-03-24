from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class TemplateBase(BaseModel):
    name: str
    description: str
    html: str
    thumbnail: str = "bg-blue-50 border-blue-200"
    is_active: bool = True

class TemplateCreate(TemplateBase):
    pass

class TemplateInDB(TemplateBase):
    id: Optional[str] = None
    corporate_id: str
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TemplateResponse(TemplateInDB):
    pass
