from contextlib import asynccontextmanager
from secrets import token_bytes

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.api.kindle_diagnostic import router as diagnostic_router
from app.api.kindle_display import router as display_router
from app.api.kindle_landscape import router as landscape_router
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.health import router as health_router
from app.core.config import ROOT, Settings
from app.core.logging import configure_logging, logger
from app.db.database import Database
from app.rendering.kindle import router as kindle_router
from app.schemas.api import APIError, ErrorResponse
from app.services.auth import LoginLimiter
from app.services.weather import WeatherCache


def error_response(status: int, code: str, message: str, headers=None) -> JSONResponse:
    body = ErrorResponse(error=APIError(code=code, message=message))
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        handler = configure_logging(settings)
        database = Database(settings.sqlite_path)
        try:
            try:
                database.migrate()
            except Exception:
                logger.exception("Database startup migration failed")
                raise
            app.state.database = database
            logger.info("Application started")
            yield
        finally:
            database.close()
            logger.info("Application stopped")
            logger.removeHandler(handler)
            handler.close()

    app = FastAPI(title="Kindle Dashboard", lifespan=lifespan)
    app.state.settings = settings
    app.state.landscape_signing_key = token_bytes(32)
    app.state.login_limiter = LoginLimiter()
    app.state.weather = WeatherCache()
    app.state.kindle_diagnostic_last_press = None
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(kindle_router)
    app.include_router(display_router)
    app.include_router(landscape_router)
    app.include_router(diagnostic_router)

    @app.exception_handler(HTTPException)
    async def handle_http_error(_request: Request, exc: HTTPException):
        return error_response(exc.status_code, f"http_{exc.status_code}", str(exc.detail), exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, _exc: RequestValidationError):
        return error_response(422, "validation_error", "Request validation failed")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception):
        logger.error("Unhandled request error", exc_info=exc)
        return error_response(500, "internal_error", "Internal server error")

    dist = ROOT / "frontend/dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def administration():
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(503, "Build the administration frontend before opening this page")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
