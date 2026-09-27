"""Web UI routes, isolated from reviewer/webhook logic."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["web"])
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

@router.get("/", include_in_schema=False)
async def landing_page():
    return FileResponse(STATIC_DIR / "index.html")

@router.get("/dashboard", include_in_schema=False)
async def dashboard_page():
    return FileResponse(STATIC_DIR / "dashboard.html")
