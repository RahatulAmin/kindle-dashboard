from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import ROOT

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=ROOT / "kindle/templates")
NO_CACHE = {"Cache-Control": "no-store"}


def server_time(request: Request) -> str:
    timezone = ZoneInfo(request.app.state.settings.app_timezone)
    return datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S %Z (%z)")


@router.get("/kindle/test")
async def kindle_test(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="diagnostic.html",
        context={
            "server_time": server_time(request),
            "last_press": request.app.state.kindle_diagnostic_last_press,
        },
        headers=NO_CACHE,
    )


@router.post("/kindle/test")
async def kindle_test_press(request: Request):
    request.app.state.kindle_diagnostic_last_press = server_time(request)
    return RedirectResponse(request.url_for("kindle_test").path, status_code=303, headers=NO_CACHE)
