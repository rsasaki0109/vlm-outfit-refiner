"""Pydantic schemas and domain types for outfit items and recommendations."""

from .schema import (
    ClothesAttributes,
    OutfitCandidate,
    ProposedOutfitText,
    RecommendInput,
    RecommendOutput,
    RecommendPattern,
)

__all__ = [
    "ClothesAttributes",
    "OutfitCandidate",
    "ProposedOutfitText",
    "RecommendInput",
    "RecommendOutput",
    "RecommendPattern",
]
