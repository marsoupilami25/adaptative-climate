"""Brand icon of Adaptative Climate: a heat/cool cycle around a thermometer.

Usage: python dev/brand/make_icon.py custom_components/adaptative_climate/brand

Drawn at 2048 px, then reduced (smooth edges). Writes icon.png (256), icon@2x.png (512),
dark_icon.png and dark_icon@2x.png (thermometer light, for dark themes).
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

S = 2048
C = S / 2
R = 760  # radius of the cycle
W = 150  # width of the arrows
ORANGE = (255, 138, 0, 255)
BLUE = (33, 150, 243, 255)


def arrow(draw: ImageDraw.ImageDraw, start: float, end: float, color: tuple) -> None:
    """An arc from start to end (degrees, clockwise from 3 o'clock), arrowhead at end."""
    box = (C - R, C - R, C + R, C + R)
    draw.arc(box, start, end, fill=color, width=W)
    a = math.radians(end)
    mid = R - W / 2  # radius of the middle of the arc
    px, py = C + mid * math.cos(a), C + mid * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)  # clockwise tangent
    nx, ny = math.cos(a), math.sin(a)  # radial
    head, half = W * 1.5, W * 1.15
    back = 4  # a little under the arc end: no seam
    bx, by = px - tx * back, py - ty * back
    tip = (px + tx * head, py + ty * head)
    left = (bx + nx * half, by + ny * half)
    right = (bx - nx * half, by - ny * half)
    draw.polygon([tip, left, right], fill=color)


def thermometer(draw: ImageDraw.ImageDraw, body: tuple, inner: tuple) -> None:
    tube_w, bulb_r = 230, 250
    top, bulb_y = 470, 1330
    draw.rounded_rectangle((C - tube_w / 2, top, C + tube_w / 2, bulb_y), radius=tube_w / 2, fill=body)
    draw.ellipse((C - bulb_r, bulb_y - bulb_r, C + bulb_r, bulb_y + bulb_r), fill=body)
    # mercury: half orange (heat) half blue (cool)
    col_w, inner_r = 100, 160
    draw.rounded_rectangle((C - col_w / 2, 760, C + col_w / 2, bulb_y), radius=col_w / 2, fill=inner)
    draw.ellipse((C - inner_r, bulb_y - inner_r, C + inner_r, bulb_y + inner_r), fill=inner)


def icon(body: tuple, inner: tuple) -> Image.Image:
    image = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    arrow(draw, 165, 295, ORANGE)
    arrow(draw, 345, 475, BLUE)
    thermometer(draw, body, inner)
    return image


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for prefix, body, inner in (
        ("", (55, 71, 79, 255), (255, 255, 255, 255)),
        ("dark_", (236, 239, 241, 255), (38, 50, 56, 255)),
    ):
        image = icon(body, inner)
        image.resize((512, 512), Image.LANCZOS).save(out / f"{prefix}icon@2x.png", optimize=True)
        image.resize((256, 256), Image.LANCZOS).save(out / f"{prefix}icon.png", optimize=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
