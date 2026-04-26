from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def wait_for_http(url: str, timeout_s: float = 20.0) -> None:
    import urllib.request

    start = time.time()
    while True:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        if time.time() - start > timeout_s:
            raise RuntimeError(f"timeout waiting for {url}")
        time.sleep(0.3)


def main() -> int:
    out = ROOT / "assets" / "ui-real-edit.png"
    db_path = ROOT / "data" / "readme_demo.db"
    port = int(os.environ.get("SCREENSHOT_PORT", "8502"))
    base = f"http://127.0.0.1:{port}"

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
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_for_http(base, timeout_s=30.0)
        url = (
            f"{base}/?page=edit"
            f"&db={db_path.as_posix()}"
            f"&id=2"
        )
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(url, wait_until="networkidle")
            # Give Streamlit a moment to render widgets.
            page.wait_for_timeout(1200)
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out), full_page=True)
            browser.close()
        print(f"wrote {out}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

