"""Generate the Notification Center brand icon (PNG) with Pillow.

Draws a rounded blue tile with a white notification bell and a red priority
badge, matching the integration's palette (accent #1f6fdd, critical #EA4D3D).
Renders supersampled then downscales for clean anti-aliased edges.

Run: python3 brands/generate_icon.py
Outputs: brands/custom_integrations/notification_center/{icon,icon@2x}.png
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFilter

SS = 4  # supersample factor
OUT_DIR = os.path.join(os.path.dirname(__file__), "custom_integrations", "notification_center")


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _gradient(size, top, bottom):
    grad = Image.new("RGB", (size, size), top)
    d = ImageDraw.Draw(grad)
    for y in range(size):
        d.line([(0, y), (size, y)], fill=_lerp(top, bottom, y / size))
    return grad


def _bell_polygon(cx, dome_cy, r, rim_y, r_rim, steps=80):
    """Right-side outline (apex -> shoulder -> rim), then mirror for the left."""
    right = []
    for i in range(steps + 1):
        t = (math.pi / 2) * (i / steps)
        right.append((cx + r * math.sin(t), dome_cy - r * math.cos(t)))
    right.append((cx + r_rim, rim_y))
    left = [(2 * cx - x, y) for (x, y) in reversed(right)]
    return right + left


def build(size_master=512):
    m = size_master * SS
    img = Image.new("RGBA", (m, m), (0, 0, 0, 0))

    # Rounded blue tile background.
    radius = int(0.20 * m)
    grad = _gradient(m, (0x3B, 0x8B, 0xFF), (0x14, 0x55, 0xC0)).convert("RGBA")
    img.paste(grad, (0, 0), _rounded_mask(m, radius))

    cx = m / 2
    r = 0.205 * m            # dome radius
    dome_cy = 0.455 * m      # dome circle center
    rim_y = 0.655 * m        # flared rim
    r_rim = 0.30 * m
    poly = _bell_polygon(cx, dome_cy, r, rim_y, r_rim)

    # Soft drop shadow behind the bell.
    shadow = Image.new("RGBA", (m, m), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    off = int(0.012 * m)
    sd.polygon([(x, y + off) for (x, y) in poly], fill=(10, 30, 70, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(0.02 * m))
    img = Image.alpha_composite(img, shadow)

    draw = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)

    # Bell body.
    draw.polygon(poly, fill=white)
    # Top stud.
    stud_r = 0.045 * m
    stud_cy = dome_cy - r - stud_r * 0.6
    draw.ellipse(
        [cx - stud_r, stud_cy - stud_r, cx + stud_r, stud_cy + stud_r], fill=white
    )
    # Flared foot (rounded bar) at the rim.
    foot_h = 0.055 * m
    draw.rounded_rectangle(
        [cx - r_rim, rim_y - foot_h / 2, cx + r_rim, rim_y + foot_h / 2],
        radius=foot_h / 2,
        fill=white,
    )
    # Clapper.
    cl_r = 0.058 * m
    cl_cy = rim_y + 0.052 * m
    draw.ellipse([cx - cl_r, cl_cy - cl_r, cx + cl_r, cl_cy + cl_r], fill=white)

    # Priority badge (red dot with a tile-colored ring so it reads off the bell).
    bx = cx + 0.165 * m
    by = dome_cy - r + 0.05 * m
    ring = 0.135 * m
    dot = 0.10 * m
    draw.ellipse([bx - ring, by - ring, bx + ring, by + ring], fill=(0x16, 0x57, 0xC8, 255))
    draw.ellipse([bx - dot, by - dot, bx + dot, by + dot], fill=(0xEA, 0x4D, 0x3D, 255))

    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    master = build(512)
    for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
        master.resize((size, size), Image.LANCZOS).save(os.path.join(OUT_DIR, name))
    print("wrote", OUT_DIR)


if __name__ == "__main__":
    main()
