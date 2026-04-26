from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


TempFeel = Literal["暑い", "普通", "寒い"]


@dataclass(frozen=True)
class PersonaPreset:
    name: str
    label: str
    situation: str
    temp_feel: TempFeel
    style: str


def load_presets(path: str | Path) -> list[PersonaPreset]:
    p = Path(path).expanduser().resolve()
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data.get("presets") or []
    out: list[PersonaPreset] = []
    for it in items:
        out.append(
            PersonaPreset(
                name=str(it.get("name", "")).strip(),
                label=str(it.get("label", "")).strip() or str(it.get("name", "")).strip(),
                situation=str(it.get("situation", "")).strip(),
                temp_feel=str(it.get("temp_feel", "普通")).strip(),  # type: ignore[arg-type]
                style=str(it.get("style", "")).strip(),
            )
        )
    out = [x for x in out if x.name]
    return out


def find_preset(presets: list[PersonaPreset], name: str) -> PersonaPreset | None:
    key = name.strip().lower()
    for p in presets:
        if p.name.lower() == key:
            return p
    return None


def presets_to_json(presets: list[PersonaPreset]) -> list[dict[str, Any]]:
    return [
        {
            "name": p.name,
            "label": p.label,
            "situation": p.situation,
            "temp_feel": p.temp_feel,
            "style": p.style,
        }
        for p in presets
    ]

