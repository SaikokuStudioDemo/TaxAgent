from pydantic import BaseModel
from typing import Optional


class JournalRuleCreate(BaseModel):
    name: str = ""
    keyword: str
    target_field: str
    account_subject: str
    tax_division: str
    is_active: bool = True


class JournalRuleUpdate(BaseModel):
    name: Optional[str] = None
    keyword: Optional[str] = None
    target_field: Optional[str] = None
    account_subject: Optional[str] = None
    tax_division: Optional[str] = None
    is_active: Optional[bool] = None
