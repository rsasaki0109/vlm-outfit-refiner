from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from models.schema import ClothesAttributes

ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = ROOT / "prompts"
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")


def _read_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def _encode_image_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def ollama_chat(
    model: str,
    user_text: str,
    *,
    image_paths: Sequence[Path] | None = None,
    base_url: str = DEFAULT_OLLAMA_URL,
    force_json: bool = True,
) -> str:
    """Call Ollama /api/chat. Pass one or more local images for vision models."""
    images: list[str] = []
    if image_paths:
        for p in image_paths:
            images.append(_encode_image_b64(Path(p)))
    body: dict[str, Any] = {
        "model": model,
        "stream": False,
        **({"format": "json"} if force_json else {}),
        "messages": [
            {
                "role": "user",
                "content": user_text,
                **({"images": images} if images else {}),
            }
        ],
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ollama HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}") from e
    except OSError as e:
        raise RuntimeError(
            f"Failed to connect to Ollama at {base_url}. Is `ollama serve` running? ({e})"
        ) from e
    message = (raw or {}).get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"Unexpected Ollama response: {raw!r}")
    return content


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract a single JSON object from model output (tolerate markdown fences)."""
    s = text.strip()
    if "```" in s:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, re.IGNORECASE)
        if m:
            s = m.group(1).strip()
    s = s.strip()
    if s.startswith("{"):
        # Prefer brace-balanced segment
        depth = 0
        for i, ch in enumerate(s):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    s = s[: i + 1]
                    break
    return json.loads(s)


def extract_clothing_attributes(
    image_path: str | Path,
    *,
    model: str | None = None,
    base_url: str = DEFAULT_OLLAMA_URL,
) -> ClothesAttributes:
    prompt = _read_prompt("extract_attributes.md")
    p = Path(image_path)
    content = ollama_chat(
        model or DEFAULT_VISION_MODEL,
        prompt,
        image_paths=[p],
        base_url=base_url,
        force_json=True,
    )
    data = parse_json_object(content)
    return ClothesAttributes.model_validate(data)


def narrate_outfit(
    user_context: str,
    outfit_lines: str,
    vibe_name: str,
    vibe_desc: str,
    *,
    model: str | None = None,
    base_url: str = DEFAULT_OLLAMA_URL,
) -> dict[str, str]:
    """Text-only call for natural language. Uses vision model if set, or OLLAMA_TEXT_MODEL."""
    text_model = model or os.environ.get("OLLAMA_TEXT_MODEL", os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b"))
    template = _read_prompt("recommend_narration.md")
    user_text = (
        template.replace("{{USER_CONTEXT}}", user_context)
        .replace("{{OUTFIT_CONTEXT}}", outfit_lines)
        .replace("{{VIBE_NAME}}", vibe_name)
        .replace("{{VIBE_DESCRIPTION}}", vibe_desc)
    )
    content = ollama_chat(
        text_model,
        user_text,
        image_paths=None,
        base_url=base_url,
        force_json=True,
    )
    return parse_json_object(content)
