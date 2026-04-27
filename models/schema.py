from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field, field_validator


class ClothesAttributes(BaseModel):
    category: Literal["tops", "bottoms", "outer", "shoes", "bag", "accessory"]
    color: str = ""
    style: list[str] = Field(default_factory=list)
    season: list[str] = Field(default_factory=list)
    formality: int = Field(default=3, ge=1, le=5)
    fit: str = ""
    notes: str = ""

    @field_validator("style", "season", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, Sequence) and not isinstance(v, (str, bytes)):
            return [str(x).strip() for x in v if str(x).strip()]
        return []


class RecommendInput(BaseModel):
    """User preferences for a recommendation run."""

    situation: str
    temp_feel: Literal["暑い", "普通", "寒い"]
    style: str
    # Optional tuning from CLI flags later
    model: str | None = None


class OutfitCandidate(BaseModel):
    top_id: int
    bottom_id: int
    shoes_id: int
    score: float
    outer_id: int | None = None
    bag_id: int | None = None


class RecommendPattern(str, Enum):
    SAFE = "safe"  # 無難
    CLEAN = "clean"  # きれいめ
    BOLD = "bold"  # 攻め


class ProposedOutfitText(BaseModel):
    """Narration JSON from the VLM/LLM."""

    pattern_label: str
    pattern_ja: str
    item_ids: dict[str, int]
    summary: str
    reason: str
    tips: str = ""


class RecommendOutput(BaseModel):
    """CLI JSON output for `recommend`."""

    situation: str
    temp_feel: str
    user_style: str
    model: str
    proposals: list[ProposedOutfitText]
