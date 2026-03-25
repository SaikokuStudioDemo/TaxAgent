from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ClientCreate(BaseModel):
    name: str
    registration_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    payment_terms: Optional[str] = None
    department: Optional[str] = None
    contact_person: Optional[str] = None
    postal_code: Optional[str] = None
    internal_notes: Optional[str] = None

class ClientInDB(ClientCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class CompanyProfileCreate(BaseModel):
    profile_name: str
    company_name: str
    phone: Optional[str] = None
    registration_number: Optional[str] = None
    address: Optional[str] = None
    is_default: bool = False

class CompanyProfileInDB(CompanyProfileCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TaxRateResponse(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    label: str
    rate: int
    applies_to: str # e.g. "standard", "food_beverage"
    effective_from: str
    effective_until: Optional[str] = None
    is_active: bool = True
