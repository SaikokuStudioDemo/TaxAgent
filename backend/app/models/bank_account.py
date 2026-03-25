from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal
from datetime import datetime


class BankAccountCreate(BaseModel):
    owner_type: Literal["corporate", "client"]
    profile_id: Optional[str] = None   # required when owner_type == "corporate"
    client_id: Optional[str] = None    # required when owner_type == "client"
    bank_name: str
    branch_name: str
    bank_code: Optional[str] = None
    branch_code: Optional[str] = None
    account_type: Literal["ordinary", "checking"] = "ordinary"
    account_number: str
    account_holder: str
    is_default: bool = False

    @model_validator(mode="after")
    def check_owner_fields(self):
        if self.owner_type == "corporate" and not self.profile_id:
            raise ValueError("profile_id is required when owner_type is 'corporate'")
        if self.owner_type == "client" and not self.client_id:
            raise ValueError("client_id is required when owner_type is 'client'")
        return self


class BankAccountInDB(BaseModel):
    corporate_id: str
    owner_type: Literal["corporate", "client"] = "corporate"
    profile_id: Optional[str] = None
    client_id: Optional[str] = None
    bank_name: str
    branch_name: str
    bank_code: Optional[str] = None
    branch_code: Optional[str] = None
    account_type: Literal["ordinary", "checking"] = "ordinary"
    account_number: str
    account_holder: str
    is_default: bool = False
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
