"""Generates the PocketMind app icon: a brain tucked into a chest pocket,
in the app's own warm terracotta/cream palette. Draws at 4x supersample and
downsamples with LANCZOS for antialiased edges (Pillow's ImageDraw has no
native AA).

Run this after any palette or design tweak, then re-run export_icons.py in
this same folder to regenerate icon.ico / the macOS iconset / icon_256.png.
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw

OUT_PATH = Path(__file__).resolve().parent / "icon_master.png"

SCALE = 4
SIZE = 1024 * SCALE

BG = "#B75736"       # --accent
POCKET = "#FAFAF7"   # --bg (cream)
BRAIN = "#A34B2C"    # --accent-hover
LINE = "#7A3620"     # darker warm brown, subtle groove


def s(v):
    return v * SCALE


def pocket_path(x_top_l, x_top_r, y_top, x_bot_l, x_bot_r, y_bot, r_bot, n=24):
    """Flat, sharp-cornered opening at top; wider, rounded-corner base —
    tapered so it reads as a pocket flap rather than a card/rectangle."""
    pts = [(x_top_l, y_top), (x_top_r, y_top)]

    cx, cy = x_bot_r - r_bot, y_bot - r_bot
    for i in range(n + 1):
        t = (math.pi / 2) * i / n
        pts.append((cx + r_bot * math.cos(t), cy + r_bot * math.sin(t)))

    cx, cy = x_bot_l + r_bot, y_bot - r_bot
    for i in range(n + 1):
        t = math.pi / 2 + (math.pi / 2) * i / n
        pts.append((cx + r_bot * math.cos(t), cy + r_bot * math.sin(t)))

    return pts


def thick_curve(draw, pts, width, fill):
    scaled = [(s(x), s(y)) for x, y in pts]
    draw.line(scaled, fill=fill, width=int(s(width)), joint="curve")
    r = s(width) / 2
    for x, y in (scaled[0], scaled[-1]):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def main():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 0, SIZE, SIZE], radius=s(220), fill=BG)

    # --- Brain: main blob + three scalloped top bumps (same fill, drawn
    # together so they read as one silhouette with no seams) ---
    cx, cy = 512, 398
    draw.ellipse([s(cx - 205), s(cy - 165), s(cx + 205), s(cy + 165)], fill=BRAIN)
    for bx, by, r in [(cx - 128, cy - 148, 90), (cx, cy - 175, 96), (cx + 128, cy - 148, 90)]:
        draw.ellipse([s(bx - r), s(by - r), s(bx + r), s(by + r)], fill=BRAIN)

    # Center groove down through the middle bump — the one detail that
    # reads as "brain" rather than a plain cloud/blob
    thick_curve(draw, [(cx, cy - 162), (cx - 6, cy - 88), (cx, cy - 8), (cx + 6, cy + 70)], 14, LINE)

    # --- Pocket: on top, gently tapered, occludes the brain's lower half
    # for the "tucked in" look ---
    pts = pocket_path(x_top_l=272, x_top_r=752, y_top=468, x_bot_l=250, x_bot_r=774, y_bot=826, r_bot=76)
    draw.polygon([(s(x), s(y)) for x, y in pts], fill=POCKET)

    img = img.resize((1024, 1024), Image.LANCZOS)
    img.save(OUT_PATH)
    print("saved", OUT_PATH, img.size)


if __name__ == "__main__":
    main()
