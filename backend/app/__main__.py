import uvicorn

from app.core.config import Settings

if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(
        "app.main:create_app", factory=True, host=settings.app_host,
        port=settings.app_port, proxy_headers=False,
    )
