from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageDraw, ImageFont

from app.core.config import ROOT, Settings

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "kindle/templates")
NO_CACHE = {"Cache-Control": "no-store"}


@dataclass(frozen=True)
class RenderContext:
    width: int
    height: int
    now: datetime

    @property
    def scale(self) -> int:
        return min(self.width, self.height * 3 // 4)


Widget = Callable[[ImageDraw.ImageDraw, RenderContext], None]


def draw_title(draw: ImageDraw.ImageDraw, context: RenderContext) -> None:
    width, height = context.width, context.height
    margin = width // 12
    draw.rectangle((margin, height // 8, width - margin, height // 8 + 4), fill=0)
    draw.text((margin, height // 5), "Kindle Dashboard", fill=0,
              font=ImageFont.load_default(size=context.scale // 16))
    draw.text((margin, height // 5 + context.scale // 10), "Test display", fill=0,
              font=ImageFont.load_default(size=context.scale // 25))


def draw_clock(draw: ImageDraw.ImageDraw, context: RenderContext) -> None:
    x, y = context.width // 12, context.height // 2
    draw.text((x, y), context.now.strftime("%H:%M:%S"), fill=0,
              font=ImageFont.load_default(size=context.scale // 8))
    draw.text((x, y + context.scale // 6), context.now.strftime("%Y-%m-%d %Z"), fill=0,
              font=ImageFont.load_default(size=context.scale // 24))


def render_png(settings: Settings, widgets: tuple[Widget, ...] = (draw_title, draw_clock)) -> bytes:
    context = RenderContext(
        settings.kindle_width, settings.kindle_height,
        datetime.now(ZoneInfo(settings.app_timezone)),
    )
    with Image.new("L", (context.width, context.height), 255) as image:
        draw = ImageDraw.Draw(image)
        for widget in widgets:
            widget(draw, context)
        with BytesIO() as buffer:
            image.save(buffer, format="PNG")
            return buffer.getvalue()


def kindle_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="display.html", context={"settings": request.app.state.settings},
        headers=NO_CACHE,
    )


@router.get("/api/kindle/image.png", response_class=Response)
def kindle_image(request: Request) -> Response:
    return Response(render_png(request.app.state.settings), media_type="image/png", headers=NO_CACHE)
