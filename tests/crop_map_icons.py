from __future__ import annotations

import json
from pathlib import Path
from typing import List

from PIL import Image, ImageChops

# Source icon sprite uploaded by user.
# Target path follows Django MEDIA_ROOT (backend/media).
SOURCE_IMAGE = Path("backend/media/map_icons/map_icon_sprite.png")
OUTPUT_DIR = Path("backend/media/map_icons/items")
MANIFEST_PATH = Path("backend/media/map_icons/icon_manifest.json")

ROWS = 4
COLS = 7
THRESHOLD = 10
INNER_PADDING = 8
OUTER_PADDING = 4

ICON_NAMES: List[str] = [
    "school",
    "hospital",
    "apartment",
    "airport_terminal",
    "museum",
    "classical_building",
    "temple",
    "classroom",
    "art_studio",
    "living_room",
    "bedroom",
    "kitchen",
    "bathroom",
    "office",
    "tree",
    "hedge",
    "tulip",
    "flower",
    "grass",
    "cactus",
    "palm",
    "bus_stop",
    "park_bench",
    "lamp_post",
    "toilet",
    "library",
    "gym",
    "train_station",
]


def _compute_mask(rgb_img: Image.Image, bg_color: tuple[int, int, int]) -> Image.Image:
    bg = Image.new("RGB", rgb_img.size, bg_color)
    diff = ImageChops.difference(rgb_img, bg)
    r, g, b = diff.split()
    max_diff = ImageChops.lighter(ImageChops.lighter(r, g), b)
    return max_diff.point(lambda v: 255 if v > THRESHOLD else 0, mode="L")


def _expand_box(box: tuple[int, int, int, int], w: int, h: int, pad: int) -> tuple[int, int, int, int]:
    l, t, r, b = box
    return (
        max(0, l - pad),
        max(0, t - pad),
        min(w, r + pad),
        min(h, b + pad),
    )


def main() -> None:
    if not SOURCE_IMAGE.exists():
        raise FileNotFoundError(f"Source image not found: {SOURCE_IMAGE}")
    if len(ICON_NAMES) != ROWS * COLS:
        raise ValueError("ICON_NAMES length must equal ROWS * COLS")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sprite_rgb = Image.open(SOURCE_IMAGE).convert("RGB")
    sw, sh = sprite_rgb.size

    # Sample corners to estimate the background color (light gray).
    corners = [
        sprite_rgb.getpixel((0, 0)),
        sprite_rgb.getpixel((sw - 1, 0)),
        sprite_rgb.getpixel((0, sh - 1)),
        sprite_rgb.getpixel((sw - 1, sh - 1)),
    ]
    bg_color = tuple(int(sum(c[i] for c in corners) / len(corners)) for i in range(3))

    manifest: list[dict[str, object]] = []

    icon_index = 0
    for row in range(ROWS):
        for col in range(COLS):
            x0 = round(col * sw / COLS)
            x1 = round((col + 1) * sw / COLS)
            y0 = round(row * sh / ROWS)
            y1 = round((row + 1) * sh / ROWS)

            cell = sprite_rgb.crop((x0, y0, x1, y1))
            cell_mask = _compute_mask(cell, bg_color)
            bbox = cell_mask.getbbox()
            if bbox is None:
                raise ValueError(f"No icon found in grid cell row={row}, col={col}")

            bbox = _expand_box(bbox, cell.width, cell.height, INNER_PADDING)
            icon_rgb = cell.crop(bbox)
            icon_alpha = cell_mask.crop(bbox)
            icon_rgba = icon_rgb.convert("RGBA")
            icon_rgba.putalpha(icon_alpha)

            # Remove empty transparent border after alpha assignment, then add tiny stable padding.
            alpha_box = icon_rgba.getbbox()
            if alpha_box is None:
                raise ValueError(f"Empty alpha icon for row={row}, col={col}")
            icon_rgba = icon_rgba.crop(alpha_box)

            padded = Image.new(
                "RGBA",
                (icon_rgba.width + OUTER_PADDING * 2, icon_rgba.height + OUTER_PADDING * 2),
                (0, 0, 0, 0),
            )
            padded.paste(icon_rgba, (OUTER_PADDING, OUTER_PADDING), icon_rgba)

            icon_name = ICON_NAMES[icon_index]
            file_name = f"{icon_index + 1:02d}_{icon_name}.png"
            out_path = OUTPUT_DIR / file_name
            padded.save(out_path, format="PNG")

            manifest.append(
                {
                    "index": icon_index + 1,
                    "name": icon_name,
                    "row": row,
                    "col": col,
                    "file": str(out_path.as_posix()),
                    "width": padded.width,
                    "height": padded.height,
                }
            )
            icon_index += 1

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps({"source": str(SOURCE_IMAGE.as_posix()), "icons": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Generated {len(manifest)} icons into: {OUTPUT_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
