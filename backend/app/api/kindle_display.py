from secrets import compare_digest
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.models.dashboard import Deadline, Task
from app.rendering.dashboard import render_dashboard
from app.rendering.kindle import NO_CACHE, kindle_page, templates
from app.services.auth import DB
from app.services.dashboard import deadline_query, preferences, task_query
from app.services.weather import Weather

router = APIRouter(include_in_schema=False)


@router.get("/api/display")
def trmnl_display(
    request: Request,
    access_token: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    configured_token = request.app.state.settings.trmnl_access_token
    expected = configured_token.get_secret_value() if configured_token else ""
    if not expected or not access_token or not compare_digest(access_token.encode(), expected.encode()):
        raise HTTPException(401, "Invalid access token", headers=NO_CACHE)

    return JSONResponse(
        {
            "image_url": str(request.url_for("kindle_dashboard_image")),
            "refresh_rate": 30,
            "filename": f"dashboard-{uuid4().hex}.png",
        },
        headers=NO_CACHE,
    )


@router.get("/kindle")
def kindle_display(request: Request, db: DB):
    config = preferences(db)
    if not config.kindle_data_enabled:
        return kindle_page(request)
    return templates.TemplateResponse(request=request, name="dashboard.html",
                                      context={"preferences": config}, headers=NO_CACHE)


@router.get("/api/kindle/dashboard.png")
def kindle_dashboard_image(request: Request, db: DB) -> Response:
    config = preferences(db)
    if not config.kindle_data_enabled:
        raise HTTPException(404, "Kindle dashboard data sharing is disabled.", headers=NO_CACHE)
    widgets = {widget.key: widget.limit for widget in config.widgets if widget.visible}
    tasks = list(db.scalars(task_query().where(
        Task.kindle_visible.is_(True), Task.completed.is_(False),
    ).limit(widgets["tasks"]))) if "tasks" in widgets else []
    deadlines = list(db.scalars(deadline_query().where(
        Deadline.kindle_visible.is_(True), Deadline.archived.is_(False), Deadline.completed.is_(False),
    ).limit(widgets["deadlines"]))) if "deadlines" in widgets else []
    db.expunge_all()
    db.rollback()
    weather = request.app.state.weather.get(config.weather) if "weather" in widgets else Weather("unavailable")
    image = render_dashboard(request.app.state.settings, config, tasks, deadlines, weather)
    return Response(image, media_type="image/png", headers=NO_CACHE)
