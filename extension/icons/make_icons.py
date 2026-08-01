"""Draw the AgentBattleground toolbar icons.

The extension shipped without an ``icons`` block, so Chrome rendered the
default puzzle piece. Rather than commit four opaque binaries, the mark is
generated here: crossed swords on the panel's own dark surface, in the panel's
own accent colour, so the toolbar button matches the UI behind it.

No third-party dependency — the repo venv has no Pillow, and adding one for
four small PNGs isn't worth the lockfile churn. Geometry is rendered at 4x and
box-downsampled for antialiasing; PNG bytes are assembled by hand.

    .\\.venv\\Scripts\\python.exe extension\\icons\\make_icons.py

Re-run after editing the geometry; the PNGs are checked in so a plain
"Load unpacked" needs no build step.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZES = (16, 32, 48, 128)
SS = 4  # supersampling factor

BG = (0x14, 0x16, 0x1A)      # panel --bg
BLADE = (0xE8, 0xEA, 0xED)   # panel --ink
GRIP = (0xD4, 0x55, 0x2F)    # panel --accent

# Unit-square geometry: two swords, hilts at the bottom corners, tips crossing
# up through the opposite corners.
CORNER_RADIUS = 0.22
BLADE_WIDTH = 0.105
GUARD_WIDTH = 0.065
GUARD_SPAN = 0.20
GRIP_FRACTION = 0.30  # portion of the sword, from the hilt, that isn't blade

SWORDS = (
    ((0.17, 0.85), (0.85, 0.15)),  # hilt bottom-left  → tip top-right
    ((0.83, 0.85), (0.15, 0.15)),  # hilt bottom-right → tip top-left
)


def _dist_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Shortest distance from a point to a line segment."""
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    t = 0.0 if span == 0 else ((px - ax) * dx + (py - ay) * dy) / span
    t = max(0.0, min(1.0, t))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def _inside_rounded_square(x: float, y: float, r: float) -> bool:
    cx = min(max(x, r), 1.0 - r)
    cy = min(max(y, r), 1.0 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _sample(x: float, y: float) -> tuple[int, int, int, int]:
    """Colour of the unit-square point (x, y)."""
    if not _inside_rounded_square(x, y, CORNER_RADIUS):
        return (0, 0, 0, 0)

    for (hx, hy), (tx, ty) in SWORDS:
        # Grip: the stretch nearest the hilt. Guard: a short perpendicular bar
        # where grip meets blade.
        gx = hx + (tx - hx) * GRIP_FRACTION
        gy = hy + (ty - hy) * GRIP_FRACTION
        if _dist_to_segment(x, y, hx, hy, gx, gy) <= BLADE_WIDTH / 2:
            return (*GRIP, 255)

        nx, ny = -(ty - hy), (tx - hx)
        norm = (nx * nx + ny * ny) ** 0.5 or 1.0
        nx, ny = nx / norm, ny / norm
        half = GUARD_SPAN / 2
        if (
            _dist_to_segment(
                x, y, gx - nx * half, gy - ny * half, gx + nx * half, gy + ny * half
            )
            <= GUARD_WIDTH / 2
        ):
            return (*GRIP, 255)

        if _dist_to_segment(x, y, gx, gy, tx, ty) <= BLADE_WIDTH / 2:
            return (*BLADE, 255)

    return (*BG, 255)


def _render(size: int) -> bytes:
    """RGBA rows for one icon, supersampled and box-filtered."""
    big = size * SS
    hi: list[tuple[int, int, int, int]] = []
    for py in range(big):
        for px in range(big):
            hi.append(_sample((px + 0.5) / big, (py + 0.5) / big))

    rows = bytearray()
    per_pixel = SS * SS
    for y in range(size):
        rows.append(0)  # PNG filter type: none
        for x in range(size):
            r = g = b = a = 0
            for sy in range(SS):
                base = (y * SS + sy) * big + x * SS
                for sx in range(SS):
                    pr, pg, pb, pa = hi[base + sx]
                    # Premultiply so transparent corners don't bleed dark edges.
                    r += pr * pa
                    g += pg * pa
                    b += pb * pa
                    a += pa
            if a:
                rows.extend((r // a, g // a, b // a, a // per_pixel))
            else:
                rows.extend((0, 0, 0, 0))
    return bytes(rows)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, size: int) -> None:
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(_render(size), 9))
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def main() -> None:
    out = Path(__file__).resolve().parent
    for size in SIZES:
        target = out / f"icon-{size}.png"
        write_png(target, size)
        print(f"wrote {target.name} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
