"""HTML page endpoints using Jinja2 templates."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request) -> HTMLResponse:
    """Render home landing page."""
    return templates.TemplateResponse(
        request=request,
        name="base.html",
        context={"title": "BreatheMap — Air Quality Decision Support"},
    )
