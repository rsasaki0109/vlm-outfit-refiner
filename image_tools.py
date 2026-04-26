from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


try:
    from PIL import Image, ImageEnhance, ImageFilter  # type: ignore
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "Pillow is required for portrait image tools. Install with: pip install Pillow"
    ) from e


BgStyle = Literal["solid", "gradient"]


@dataclass(frozen=True)
class PortraitOptions:
    size: int = 1024  # output is size x size
    bg_style: BgStyle = "gradient"
    bg_color1: tuple[int, int, int] = (15, 23, 42)  # deep slate
    bg_color2: tuple[int, int, int] = (30, 64, 175)  # indigo-ish accent
    blur_radius: float = 0.0  # background blur if we can separate
    enhance_color: float = 1.05
    enhance_contrast: float = 1.06
    enhance_brightness: float = 1.02
    vignette: float = 0.18  # 0..1


def _open_rgb(path: Path) -> Image.Image:
    im = Image.open(path)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    return im


def _make_bg(size: int, opt: PortraitOptions) -> Image.Image:
    if opt.bg_style == "solid":
        return Image.new("RGB", (size, size), opt.bg_color1)

    # diagonal-ish soft gradient
    bg = Image.new("RGB", (size, size), opt.bg_color1)
    px = bg.load()
    for y in range(size):
        for x in range(size):
            t = (x * 0.6 + y * 0.9) / (size * 1.5)
            t = max(0.0, min(1.0, t))
            r = int(opt.bg_color1[0] * (1 - t) + opt.bg_color2[0] * t)
            g = int(opt.bg_color1[1] * (1 - t) + opt.bg_color2[1] * t)
            b = int(opt.bg_color1[2] * (1 - t) + opt.bg_color2[2] * t)
            px[x, y] = (r, g, b)
    return bg


def _center_crop_square(im: Image.Image) -> Image.Image:
    w, h = im.size
    s = min(w, h)
    left = (w - s) // 2
    top = (h - s) // 2
    return im.crop((left, top, left + s, top + s))


def _apply_basic_enhance(im: Image.Image, opt: PortraitOptions) -> Image.Image:
    im = ImageEnhance.Color(im).enhance(opt.enhance_color)
    im = ImageEnhance.Contrast(im).enhance(opt.enhance_contrast)
    im = ImageEnhance.Brightness(im).enhance(opt.enhance_brightness)
    return im


def _vignette_mask(size: int, strength: float) -> Image.Image:
    strength = max(0.0, min(1.0, strength))
    mask = Image.new("L", (size, size), 255)
    px = mask.load()
    cx = cy = (size - 1) / 2.0
    maxd = math.hypot(cx, cy)
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy) / maxd
            # make edges darker
            v = 1.0 - strength * (d**1.8)
            px[x, y] = int(max(0, min(255, 255 * v)))
    return mask


def make_profile_portrait(
    src_path: str | Path,
    dst_path: str | Path,
    *,
    opt: PortraitOptions | None = None,
) -> Path:
    """
    Create a square, profile-photo-like image with background styling.

    Notes:
    - This does NOT change body shape or pose. It only does safe photo polishing
      (crop/resize, color grading, background canvas, vignette).
    - Background replacement with segmentation is intentionally not included in MVP.
      If needed later, we can add optional local segmentation (e.g. rembg) behind a flag.
    """
    opt = opt or PortraitOptions()
    src = Path(src_path).expanduser().resolve()
    dst = Path(dst_path).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    im = _open_rgb(src)
    im = _center_crop_square(im)
    im = im.resize((opt.size, opt.size), resample=Image.Resampling.LANCZOS)
    im = _apply_basic_enhance(im, opt)

    bg = _make_bg(opt.size, opt)

    # simple composition: place the (cropped) photo on styled bg with a tiny shadow
    shadow = Image.new("RGBA", (opt.size, opt.size), (0, 0, 0, 0))
    sh = Image.new("RGBA", (opt.size - 80, opt.size - 80), (0, 0, 0, 110))
    sh = sh.filter(ImageFilter.GaussianBlur(radius=18))
    shadow.paste(sh, (40, 52), sh)

    comp = bg.convert("RGBA")
    comp.alpha_composite(shadow)
    comp.alpha_composite(im.convert("RGBA"), dest=(0, 0))

    # vignette
    if opt.vignette > 0:
        v = _vignette_mask(opt.size, opt.vignette)
        comp = Image.composite(comp, Image.new("RGBA", comp.size, (0, 0, 0, 255)), v)

    out = comp.convert("RGB")
    out.save(dst, format="PNG", optimize=True)
    return dst

