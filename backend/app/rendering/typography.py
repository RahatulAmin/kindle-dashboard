from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONT = Path(__file__).with_name("fonts") / "NotoSans.ttf"


@lru_cache(maxsize=48)
def font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    result = ImageFont.truetype(str(FONT), size)
    result.set_variation_by_name(weight)
    return result
