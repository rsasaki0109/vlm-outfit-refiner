from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import db
from models.schema import ClothesAttributes, RecommendInput
from recommender import recommend_outfits


def _seed_minimal_wardrobe(dp: Path) -> None:
    db.init_db(dp)
    tops = ClothesAttributes(
        category="tops",
        color="白",
        style=["カジュアル"],
        season=["春", "夏"],
        formality=2,
        fit="",
        notes="",
    )
    bottoms = ClothesAttributes(
        category="bottoms",
        color="紺",
        style=["きれいめ"],
        season=["春", "秋"],
        formality=3,
        fit="",
        notes="",
    )
    shoes = ClothesAttributes(
        category="shoes",
        color="茶",
        style=["カジュアル"],
        season=["通年"],
        formality=2,
        fit="",
        notes="",
    )
    db.insert_item("/t.png", "1" * 64, tops, tops.model_dump(), path=dp)
    db.insert_item("/b.png", "2" * 64, bottoms, bottoms.model_dump(), path=dp)
    db.insert_item("/s.png", "3" * 64, shoes, shoes.model_dump(), path=dp)


def _fake_narrate(*_a: object, **_k: object) -> dict[str, str]:
    return {"summary": "テスト用の要約", "reason": "・理由1\n・理由2", "tips": ""}


def test_recommend_outfits_mocked_ollama(tmp_path: Path) -> None:
    dp = tmp_path / "rec.db"
    _seed_minimal_wardrobe(dp)
    grouped = db.get_items_by_categories(
        ["tops", "bottoms", "shoes", "outer", "bag", "accessory"],
        dp,
    )
    inp = RecommendInput(
        situation="カフェ",
        temp_feel="普通",
        style="カジュアル",
    )
    with patch("recommender.narrate_outfit", side_effect=_fake_narrate):
        out = recommend_outfits(
            grouped,
            inp,
            ollama_model="stub",
            ollama_base="http://127.0.0.1:9",
        )
    assert out.situation == "カフェ"
    assert len(out.proposals) == 3
    labels = {p.pattern_label for p in out.proposals}
    assert labels == {"safe", "clean", "bold"}
    for p in out.proposals:
        assert "top" in p.item_ids
        assert p.summary


def test_recommend_needs_all_categories(tmp_path: Path) -> None:
    dp = tmp_path / "incomplete.db"
    db.init_db(dp)
    a = ClothesAttributes(
        category="tops",
        color="白",
        style=[],
        season=[],
        formality=2,
        fit="",
        notes="",
    )
    db.insert_item("/only.png", "x" * 64, a, a.model_dump(), path=dp)
    grouped = db.get_items_by_categories(["tops", "bottoms", "shoes"], dp)
    inp = RecommendInput(situation="仕事", temp_feel="寒い", style="きれいめ")
    with patch("recommender.narrate_outfit", side_effect=_fake_narrate):
        with pytest.raises(ValueError, match="Need tops|bottoms|shoes"):
            recommend_outfits(grouped, inp, ollama_model="stub", ollama_base="http://x")
