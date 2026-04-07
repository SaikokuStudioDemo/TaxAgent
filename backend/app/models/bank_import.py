from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class BankImportFileCreate(BaseModel):
    source_type: Literal["bank", "card"]
    account_name: str
    file_name: str
    row_count: int


class BankImportFileInDB(BankImportFileCreate):
    id: Optional[str] = Field(None, alias="_id")
    corporate_id: str
    status: Literal["completed", "error"] = "completed"
    imported_at: datetime = Field(default_factory=datetime.utcnow)
