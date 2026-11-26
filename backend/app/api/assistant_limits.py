from starlette.responses import JSONResponse

MAX_BODY_BYTES = 32 * 1024


class AssistantBodyLimit:
    """Bound buffered request bytes before FastAPI parses scoped JSON operations."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        parts = scope.get("path", "").strip("/").split("/")
        if (scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}
                or len(parts) < 3 or parts[:2] != ["api", "v1"]
                or parts[2] not in {"tasks", "deadlines", "briefing"}):
            await self.app(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                await JSONResponse({"error": {"code": "http_413", "message": "Request exceeds 32 KiB."}},
                                   status_code=413, headers={"Cache-Control": "no-store"})(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        async def replay():
            nonlocal body
            if body is None:
                return await receive()
            message = {"type": "http.request", "body": bytes(body), "more_body": False}
            body = None
            return message

        await self.app(scope, replay, send)
