from __future__ import annotations

from pathlib import Path

from PIL import Image

from image_tools import PortraitOptions, make_profile_portrait


def test_make_profile_portrait_outputs_square_png(tmp_path: Path) -> None:
    src = tmp_path / "src.png"
    Image.new("RGB", (1200, 800), (200, 180, 160)).save(src)
    dst = tmp_path / "out.png"
    out = make_profile_portrait(src, dst, opt=PortraitOptions(size=512, bg_style="solid"))
    assert out.exists()
    im = Image.open(out)
    assert im.size == (512, 512)

