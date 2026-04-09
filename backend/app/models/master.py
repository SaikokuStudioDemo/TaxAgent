from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class BankDisplayName(BaseModel):
    """取引先の銀行振込表示名パターン（自動マッチングに使用）"""
    pattern: str
    source: str = "manual"  # "manual" | "ai"
    confidence: float = 1.0
    added_at: Optional[str] = None


class ClientCreate(BaseModel):
    name: str
    client_type: str = "customer"  # "customer" | "vendor" | "both"
    client_category: Optional[str] = None  # "company" | "individual"
    registration_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    payment_terms: Optional[str] = None
    department_id: Optional[str] = None
    contact_person: Optional[str] = None
    postal_code: Optional[str] = None
    internal_notes: Optional[str] = None
    bank_display_names: List[BankDisplayName] = []

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

class MatchingPatternCreate(BaseModel):
    """マッチングパターン（bank_display_names の後継）"""
    client_id: str
    pattern: str
    source: str = "manual"  # "manual_match" | "ai_suggest" | "manual"
    confidence: float = 1.0

class MatchingPatternInDB(MatchingPatternCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    used_count: int = 0


class TaxRateResponse(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    label: str
    rate: int
    applies_to: str # e.g. "standard", "food_beverage"
    effective_from: str
    effective_until: Optional[str] = None
    is_active: bool = True
