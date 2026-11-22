from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import logger
from app.schemas.api import Health, HealthResponse

router = APIRouter(prefix="/api/v1")


@router.get("/health", responses={503: {"model": HealthResponse}})
def health(request: Request, response: Response) -> HealthResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        with request.app.state.database.sessions() as session:
            session.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        response.status_code = 503
        return HealthResponse(data=Health(status="degraded", database="unavailable"))
    return HealthResponse(data=Health(status="ok", database="available"))
