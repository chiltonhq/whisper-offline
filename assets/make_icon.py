#!/usr/bin/env python3
"""Generate the Whisper Offline app icon.

Run once after editing; commit the resulting app_icon.png and app_icon.ico.
Not part of the runtime path.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent

NAVY = (1, 33, 105, 255)
GREEN = (46, 189, 107, 255)


def render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = int(size * 0.22)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=NAVY)

    # 5 vertical bars, varying heights, rounded
    n = 5
    pad_x = size * 0.18
    avail_w = size - 2 * pad_x
    bar_w = avail_w / (n * 2 - 1)
    cx = size / 2
    cy = size / 2
    heights = [0.32, 0.62, 0.86, 0.52, 0.40]
    bar_radius = max(1, int(bar_w * 0.45))

    for i, h in enumerate(heights):
        x0 = pad_x + i * (bar_w * 2)
        bh = size * h
        y0 = cy - bh / 2
        y1 = cy + bh / 2
        draw.rounded_rectangle((x0, y0, x0 + bar_w, y1), radius=bar_radius, fill=GREEN)

    return img


def main() -> None:
    base = render(512)
    png_path = ASSETS / "app_icon.png"
    ico_path = ASSETS / "app_icon.ico"

    base.resize((256, 256), Image.LANCZOS).save(png_path, format="PNG")

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(ico_path, format="ICO", sizes=sizes)
    print(f"wrote {png_path}")
    print(f"wrote {ico_path}")


if __name__ == "__main__":
    main()
