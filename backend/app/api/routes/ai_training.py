from fastapi import APIRouter, Depends, HTTPException
import os
from typing import List
from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.services.invoice_service import InvoiceService

router = APIRouter()

SAMPLE_DIR = "/Users/yohei/Developer/TaxAgent/InvoiceSample"

@router.get("/samples", summary="サンプル請求書の一覧を取得する")
async def list_invoice_samples(
    current_user: dict = Depends(get_current_user),
):
    """
    List files in the InvoiceSample directory.
    """
    if not os.path.exists(SAMPLE_DIR):
        return {"samples": []}
    
    files = []
    for f in os.listdir(SAMPLE_DIR):
        if f.endswith(".pdf"):
            stats = os.stat(os.path.join(SAMPLE_DIR, f))
            files.append({
                "filename": f,
                "size": stats.st_size,
                "path": os.path.join(SAMPLE_DIR, f)
            })
    return {"samples": files}

@router.post("/train", summary="指定したサンプルでAIをトレーニングする")
async def train_ai_on_sample(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Process a sample PDF with Gemini 3.1 Flash.
    """
    filename = payload.get("filename")
    vendor_name = payload.get("vendor_name", "Unknown Vendor")
    
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    full_path = os.path.join(SAMPLE_DIR, filename)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Sample not found")
    
    
    success = await InvoiceService.train_from_sample(full_path, vendor_name)
    if not success:
        raise HTTPException(status_code=500, detail="AI Training failed")
        
    return {"status": "success", "message": f"Trained on {filename}"}

@router.post("/generate", summary="ドキュメントからHTMLテンプレートを生成する")
async def generate_template_from_file(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Generate an HTML template from an uploaded document.
    """
    from app.services.ai_service import AIService
    
    # In a real scenario, this would handle a Multipart file upload
    # For the prototype, we assume the file is already placed in SAMPLE_DIR 
    # or we simulate the process using a provided filename.
    filename = payload.get("filename")
    if not filename:
        # If no filename is provided, we simulate a generic "new_invoice" analysis
        # to show the AI capability.
        result = await AIService.generate_invoice_html_template("dummy_path")
    else:
        full_path = os.path.join(SAMPLE_DIR, filename)
        if not os.path.exists(full_path):
            result = await AIService.generate_invoice_html_template(filename)
        else:
            result = await AIService.generate_invoice_html_template(full_path)
    
    if not result:
        raise HTTPException(status_code=500, detail="AI Template generation failed")
        
    return result
