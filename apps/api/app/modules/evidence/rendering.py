# SPDX-License-Identifier: MIT
from __future__ import annotations

import io
import math

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

from .schemas import AnnotationData


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _image(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as source:
        source.seek(0)
        source.load()
        return source.convert("RGBA")


def thumbnail(data: bytes) -> bytes:
    image = _image(data)
    image.thumbnail((512, 512), Image.Resampling.LANCZOS)
    result = io.BytesIO()
    image.save(result, format="PNG")
    return result.getvalue()


def render_annotation(original: bytes, annotations: AnnotationData) -> bytes:
    image = _image(original)
    if image.size != (annotations.width, annotations.height):
        raise ValueError("Dimensões da anotação diferentes do original")
    for shape in annotations.shapes:
        x, y = round(shape.x), round(shape.y)
        color = ImageColor.getrgb(shape.color) + (255,)
        width = max(1, round(shape.stroke_width))
        draw = ImageDraw.Draw(image)
        box = (x, y, round(shape.x + (shape.width or 0)), round(shape.y + (shape.height or 0)))
        if shape.type == "rect":
            draw.rectangle(box, outline=color, width=width)
        elif shape.type == "circle":
            draw.ellipse(box, outline=color, width=width)
        elif shape.type in {"line", "arrow"}:
            end = (round(shape.x2), round(shape.y2))
            draw.line((x, y, *end), fill=color, width=width)
            if shape.type == "arrow":
                angle = math.atan2(end[1] - y, end[0] - x)
                length = max(10, width * 4)
                left = (end[0] - length * math.cos(angle - math.pi / 6), end[1] - length * math.sin(angle - math.pi / 6))
                right = (end[0] - length * math.cos(angle + math.pi / 6), end[1] - length * math.sin(angle + math.pi / 6))
                draw.polygon((end, left, right), fill=color)
        elif shape.type == "text":
            draw.text((x, y), shape.text, fill=color, font=_font(max(12, width * 5)))
        elif shape.type == "step":
            radius = 14
            draw.ellipse((max(0, x - radius), max(0, y - radius), x + radius, y + radius), fill=color)
            draw.text((x, y), str(shape.number), anchor="mm", fill="white", font=_font(17))
        elif shape.type == "highlight":
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            ImageDraw.Draw(overlay).rectangle(box, fill=color[:3] + (85,))
            image = Image.alpha_composite(image, overlay)
        elif shape.type == "blur":
            region = image.crop(box).filter(ImageFilter.GaussianBlur(radius=max(8, width * 3)))
            image.paste(region, box)
        elif shape.type == "redact":
            # Redação opaca destrói os pixels somente no derivado PNG.
            draw.rectangle(box, fill=(0, 0, 0, 255))
    if annotations.crop:
        crop = annotations.crop
        image = image.crop((crop.x, crop.y, crop.x + crop.width, crop.y + crop.height))
    result = io.BytesIO()
    # Nenhum metadado EXIF/original é copiado ao derivado.
    image.save(result, format="PNG")
    return result.getvalue()
