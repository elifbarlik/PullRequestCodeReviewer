from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.reviewer import review_diff, truncate_diff

app = FastAPI(title="PR Code Reviewer", version="0.1.0")

class DiffRequest(BaseModel):
    diff_text: str
    file_name: Optional[str] = None
    review_types: Optional[List[str]] = ["short_summary", "bug_detection"]

class ReviewResponse(BaseModel):
    status: str
    file_name: Optional[str] = None
    diff_length: int
    analyses: dict

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/local-review", response_model=ReviewResponse)
async def local_review(request: DiffRequest):
    if not request.diff_text or len(request.diff_text.strip()) == 0:
        raise HTTPException(status_code=400, detail="diff_text boş olamaz")

    diff_to_analyze = truncate_diff(request.diff_text, max_length=3000)

    valid_types = ["short_summary", "bug_detection", "performance", "security"]
    review_types = request.review_types or ["short_summary", "bug_detection"]

    for rt in review_types:
        if rt not in valid_types:
            raise HTTPException(status_code=400, detail=f"Geçersiz review_type: {rt}")

    try:
        result = review_diff(diff_text=diff_to_analyze, review_types=review_types)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM hatası: {str(e)}")

    return ReviewResponse(
        status=result["status"],
        file_name=request.file_name,
        diff_length=len(request.diff_text),
        analyses=result["analyses"]
    )

