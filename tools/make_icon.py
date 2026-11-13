"""Generate the logo: a shattered keyboard in an angular shield.

Writes assets/icon.ico (multi-size), icon.png (256), logo.png (512) and logo_64.png.
Build-time only, needs Pillow and numpy.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 1024                       # drawing size; downscaled for output (smooth edges)
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

NAVY_TOP = (13, 22, 32)
NAVY_BOTTOM = (26, 38, 52)
GOLD = (200, 161, 90)
GOLD_LIGHT = (232, 201, 133)
STEEL = (74, 92, 112)
STEEL_LIGHT = (176, 190, 204)
BODY = (22, 33, 45)
RED = (255, 70, 85)
SHARDS = 11
IMPACT = (690, 430)            # where the keyboard breaks (also where the red glow sits)

KB_BOX = (130, 300, 894, 724)  # keyboard body


def shield_polygon(inset: int = 0):
    """Angular shield: two opposite corners cut like Valorant's UI shapes."""
    a, b, cut = 40 + inset, S - 40 - inset, 170
    return [(a + cut, a), (b, a), (b, b - cut), (b - cut, b), (a, b), (a, a + cut)]


def background() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(int(NAVY_TOP[i] + (NAVY_BOTTOM[i] - NAVY_TOP[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon(shield_polygon(), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.polygon(shield_polygon(), outline=GOLD, width=14)
    d.polygon(shield_polygon(34), outline=(200, 161, 90, 90), width=4)   # fine inner hairline
    d.line([(60, 330), (60, 220)], fill=RED, width=14)                    # red accent tick
    return img


def keyboard() -> Image.Image:
    """Intact keyboard on a transparent canvas."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = KB_BOX
    d.rounded_rectangle(KB_BOX, radius=46, fill=BODY, outline=GOLD, width=10)
    pad, gap = 34, 16
    rows = [(6, None), (5, None), (None, "space")]
    key_h = (y1 - y0 - 2 * pad - 2 * gap) / 3
    y = y0 + pad
    for count, kind in rows:
        if kind == "space":
            keys = [(x0 + pad, 120), (x0 + pad + 120 + gap, x1 - x0 - 2 * pad - 2 * (120 + gap)),
                    (x1 - pad - 120, 120)]
        else:
            inner = x1 - x0 - 2 * pad
            w = (inner - (count - 1) * gap) / count
            keys = [(x0 + pad + i * (w + gap), w) for i in range(count)]
        for kx, kw in keys:
            d.rounded_rectangle([kx, y, kx + kw, y + key_h], radius=18, fill=STEEL)
            d.rounded_rectangle([kx + 6, y + 6, kx + kw - 6, y + 20], radius=8, fill=STEEL_LIGHT)  # glossy top
        y += key_h + gap
    return img


def shatter(kb: Image.Image) -> Image.Image:
    """Cut the keyboard into Voronoi shards; push them apart from the impact point."""
    rng = np.random.default_rng(11)
    x0, y0, x1, y1 = KB_BOX
    seeds = np.column_stack([rng.uniform(x0, x1, SHARDS), rng.uniform(y0, y1, SHARDS)])
    seeds[0] = IMPACT
    seeds[1] = (IMPACT[0] - 150, IMPACT[1] + 60)
    ys, xs = np.mgrid[0:S, 0:S]
    dist = (xs[..., None] - seeds[:, 0]) ** 2 + (ys[..., None] - seeds[:, 1]) ** 2
    labels = dist.argmin(axis=2)
    alpha = np.array(kb)[..., 3] > 0

    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    for i in range(SHARDS):
        cell = (labels == i) & alpha
        if cell.sum() < 50:
            continue
        cy, cx = np.argwhere(cell).mean(axis=0)
        vx, vy = cx - IMPACT[0], cy - IMPACT[1]
        norm = math.hypot(vx, vy) or 1.0
        near = max(0.0, 1.0 - norm / 520.0)
        push = 14 + 70 * near
        angle = (rng.uniform(3, 11) * (1 if vx >= 0 else -1)) * (0.4 + near)
        shard = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        shard.paste(kb, (0, 0), Image.fromarray((cell * 255).astype(np.uint8)))
        # bright fracture edge
        eroded = np.array(Image.fromarray((cell * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(9))) > 0
        edge = cell & ~eroded
        edge_img = np.zeros((S, S, 4), dtype=np.uint8)
        color = RED if near > 0.45 else STEEL_LIGHT
        edge_img[edge] = color + (255,)
        shard = Image.alpha_composite(shard, Image.fromarray(edge_img))
        moved = shard.rotate(angle, center=(cx, cy), translate=(vx / norm * push, vy / norm * push),
                             resample=Image.BICUBIC)
        out = Image.alpha_composite(out, moved)
    # red glow around the break
    halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([IMPACT[0] - 130, IMPACT[1] - 130, IMPACT[0] + 130, IMPACT[1] + 130],
                                 fill=RED + (70,))
    halo = halo.filter(ImageFilter.GaussianBlur(60))
    return Image.alpha_composite(halo, out)


def flying_shards() -> Image.Image:
    """A few small loose splinters around the break."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    splinters = [
        ([(800, 250), (850, 215), (836, 276)], RED),
        ([(868, 330), (905, 318), (884, 366)], STEEL_LIGHT),
        ([(610, 232), (650, 205), (660, 250)], GOLD_LIGHT),
        ([(760, 790), (812, 800), (776, 840)], RED),
        ([(220, 800), (262, 770), (270, 824)], STEEL_LIGHT),
        ([(922, 470), (946, 440), (952, 492)], GOLD_LIGHT),
    ]
    for pts, color in splinters:
        d.polygon(pts, fill=color)
    return img


def draw_logo() -> Image.Image:
    img = background()
    img = Image.alpha_composite(img, shatter(keyboard()))
    img = Image.alpha_composite(img, flying_shards())
    # keep everything inside the shield
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon(shield_polygon(), fill=255)
    img.putalpha(ImageChops.multiply(img.getchannel("A"), mask))
    return img


def main() -> None:
    assets = Path(__file__).resolve().parent.parent / "assets"
    assets.mkdir(exist_ok=True)
    logo = draw_logo()
    big = logo.resize((512, 512), Image.LANCZOS)
    big.save(assets / "logo.png")
    logo.resize((64, 64), Image.LANCZOS).save(assets / "logo_64.png")   # window header + icon
    logo.resize((256, 256), Image.LANCZOS).save(assets / "icon.png")
    logo.resize((256, 256), Image.LANCZOS).save(assets / "icon.ico", format="ICO",
                                                sizes=[(n, n) for n in ICO_SIZES])
    print(f"wrote logo.png, icon.png, icon.ico in {assets}")


if __name__ == "__main__":
    main()
