from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class BankAccountCreate(BaseModel):
    profile_id: str
    bank_name: str
    branch_name: str
    account_type: Literal["ordinary", "checking"] = "ordinary"
    account_number: str
    account_holder: str
    is_default: bool = False


class BankAccountInDB(BaseModel):
    corporate_id: str
    profile_id: str
    bank_name: str
    branch_name: str
    account_type: Literal["ordinary", "checking"] = "ordinary"
    account_number: str
    account_holder: str
    is_default: bool = False
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
