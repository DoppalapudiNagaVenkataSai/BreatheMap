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
    """Render home landing page with Air view."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "BreatheMap — Air Quality Decision Support", "active_page": "air"},
    )


@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request) -> HTMLResponse:
    """Render about and methodology page."""
    return templates.TemplateResponse(
        request=request,
        name="about.html",
        context={"title": "About BreatheMap", "active_page": "about"},
    )


@router.get("/route", response_class=HTMLResponse)
async def route_page(request: Request) -> HTMLResponse:
    """Render BreatheRoute interactive mode comparison page."""
    return templates.TemplateResponse(
        request=request,
        name="route.html",
        context={
            "title": "BreatheRoute — Route Mode Comparison",
            "active_page": "route",
        },
    )


@router.get("/assistant", response_class=HTMLResponse)
async def assistant_page(request: Request) -> HTMLResponse:
    """Render AI Assistant stub page."""
    return templates.TemplateResponse(
        request=request,
        name="stub.html",
        context={
            "title": "AI Air Assistant",
            "page_title": "AI Air Assistant",
            "description": (
                "Natural language decision support grounded in deterministic environmental data."
            ),
            "active_page": "assistant",
        },
    )


@router.get("/watch", response_class=HTMLResponse)
async def watch_page(request: Request) -> HTMLResponse:
    """Render BreatheWatch community pollution reports page."""
    return templates.TemplateResponse(
        request=request,
        name="watch.html",
        context={
            "title": "BreatheWatch — Community Reports",
            "active_page": "watch",
        },
    )
