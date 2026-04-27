from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlencode

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "gif_capture.db"
OUT_GIF = ROOT / "docs" / "assets" / "demo-ui-flow.gif"
TMP_DIR = ROOT / "data" / "_demo_video_tmp"


def wait_for_http(url: str, timeout_s: float = 30.0) -> None:
    import urllib.error
    import urllib.request

    start = time.time()
    while True:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        if time.time() - start > timeout_s:
            raise RuntimeError(f"timeout waiting for {url}")
        time.sleep(0.3)


def _run_ffmpeg_webm_to_gif(src: Path, dst: Path) -> None:
    which = shutil.which("ffmpeg")
    if which is None:
        raise FileNotFoundError("ffmpeg not found in PATH; install ffmpeg to build .gif")
    # Palette + scale for smaller file; ~45–60s typical flow
    filter_chain = (
        "fps=7,scale=720:-1:flags=lanczos,split[s0][s1];"
        "[s0]palettegen=stats_mode=full[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3"
    )
    cmd = [
        which,
        "-y",
        "-i",
        str(src),
        "-vf",
        filter_chain,
        "-loop",
        "0",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def main() -> int:
    port = int(os.environ.get("DEMO_GIF_PORT", "8505"))
    base = f"http://127.0.0.1:{port}"
    db_abs = DB.resolve()
    if db_abs.exists():
        db_abs.unlink()

    q = {
        "page": "add",
        "db": str(db_abs),
        "demo": "1",
        "no_llm": "1",
    }
    start_url = f"{base}/?{urlencode(q, quote_via=quote, safe='')}"

    env = os.environ.copy()
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    env["PYTHONUNBUFFERED"] = "1"

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ROOT / "app.py"),
        "--server.headless=true",
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_http(base, timeout_s=45.0)
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        edit_q = {**q, "page": "edit", "id": "1"}
        rec_q = {**q, "page": "recommend"}
        edit_url = f"{base}/?{urlencode(edit_q, quote_via=quote, safe='')}"
        rec_url = f"{base}/?{urlencode(rec_q, quote_via=quote, safe='')}"

        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                record_video_dir=str(TMP_DIR),
                record_video_size={"width": 1200, "height": 760},
            )
            page = context.new_page()
            page.set_viewport_size({"width": 1200, "height": 760})
            page.goto(start_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2200)
            page.get_by_role(
                "button", name="Load 3 sample items (wardrobe, no Ollama)"
            ).click()
            page.wait_for_timeout(3200)

            page.goto(edit_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            page.get_by_role("textbox", name="color (optional)").fill("オフホワイト")
            page.wait_for_timeout(500)
            page.get_by_role("button", name="Apply edit").click()
            page.wait_for_timeout(3200)

            page.goto(rec_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1800)
            page.get_by_role("button", name="Run 3-pattern recommend").click()
            page.wait_for_timeout(5000)
            page.close()
            vpath = page.video.path() if page.video else None
            context.close()
            browser.close()

        if not vpath or not Path(vpath).is_file():
            print("error: no video path from Playwright", file=sys.stderr)
            return 1

        _run_ffmpeg_webm_to_gif(Path(vpath), OUT_GIF)
        print(f"wrote {OUT_GIF} ({OUT_GIF.stat().st_size // 1024} KiB)")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        if TMP_DIR.exists():
            shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
