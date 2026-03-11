from pydantic import BaseModel, EmailStr
from typing import Optional, List, Literal
from datetime import datetime

class CorporateUserCreate(BaseModel):
    """
    Data model for the incoming registration payload from the frontend 
    Corporate/TaxFirm registration form.
    Only strictly necessary business and routing data is saved to MongoDB.
    PII (Company Name, Address, etc.) is saved to Firestore by the frontend.
    """
    corporateType: Literal["tax_firm", "corporate"]
    
    # Optional fields (can be handled without PII)
    companyUrl: Optional[str] = None
    maIntent: Optional[str] = None
    
    # Operations
    planId: str
    selectedOptions: List[str] = []
    monthlyFee: int
    
    # Referrer info
    sales_agent_id: Optional[str] = None
    referrer_id: Optional[str] = None
    advising_tax_firm_id: Optional[str] = None

class CorporateUserInDB(BaseModel):
    """
    Data model representing a Corporate or Tax Firm entity stored in MongoDB.
    """
    firebase_uid: str # Link back to the Firebase User
    corporateType: Literal["tax_firm", "corporate"]
    
    companyUrl: Optional[str] = None
    maIntent: Optional[str] = None
    
    planId: str
    selectedOptions: List[str] = []
    monthlyFee: int
    
    sales_agent_id: Optional[str] = None
    referrer_id: Optional[str] = None
    advising_tax_firm_id: Optional[str] = None
    
    created_at: datetime = datetime.utcnow()
    is_active: bool = True

class EmployeeUserCreate(BaseModel):
    """
    Data model for an employee/staff member added to a corporate or tax firm account.
    PII (Name, Email) are NOT stored here.
    """
    role: str
    permissions: dict
    usageFee: Optional[int] = 0

class EmployeeUserInDB(BaseModel):
    """
    Data model representing an employee entity stored in MongoDB.
    """
    firebase_uid: str # Their own Firebase login UID
    parent_corporate_id: str # The Firebase UID of the Tax Firm or Corporate that created them
    role: str
    permissions: dict
    usageFee: Optional[int] = 0
    
    created_at: datetime = datetime.utcnow()
    is_active: bool = True

