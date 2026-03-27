from pydantic import BaseModel
from typing import Optional


class MatchingRuleCreate(BaseModel):
    name: str = ""
    target_field: str
    condition_type: str
    condition_value: str
    action: str
    is_active: bool = True


class MatchingRuleUpdate(BaseModel):
    name: Optional[str] = None
    target_field: Optional[str] = None
    condition_type: Optional[str] = None
    condition_value: Optional[str] = None
    action: Optional[str] = None
    is_active: Optional[bool] = None
