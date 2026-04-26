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


def test_recommend_avoid_triplet_keys(tmp_path: Path) -> None:
    dp = tmp_path / "avoid.db"
    db.init_db(dp)
    # Two tops so we can avoid one triplet.
    t1 = ClothesAttributes(category="tops", color="白", style=["カジュアル"], season=["春"], formality=2, fit="", notes="")
    t2 = ClothesAttributes(category="tops", color="黒", style=["カジュアル"], season=["春"], formality=2, fit="", notes="")
    b = ClothesAttributes(category="bottoms", color="紺", style=["カジュアル"], season=["春"], formality=2, fit="", notes="")
    s = ClothesAttributes(category="shoes", color="黒", style=["カジュアル"], season=["春"], formality=2, fit="", notes="")
    id_t1 = db.insert_item("/t1.png", "1" * 64, t1, t1.model_dump(), path=dp)
    id_t2 = db.insert_item("/t2.png", "2" * 64, t2, t2.model_dump(), path=dp)
    id_b = db.insert_item("/b.png", "3" * 64, b, b.model_dump(), path=dp)
    id_s = db.insert_item("/s.png", "4" * 64, s, s.model_dump(), path=dp)

    grouped = db.get_items_by_categories(["tops", "bottoms", "shoes"], dp)
    inp = RecommendInput(situation="カフェ", temp_feel="普通", style="カジュアル")
    avoid = {f"{id_t1}-{id_b}-{id_s}"}
    with patch("recommender.narrate_outfit", side_effect=_fake_narrate):
        out = recommend_outfits(
            grouped,
            inp,
            avoid_triplet_keys=avoid,
            avoid_scope="all",
            use_llm=True,
            ollama_model="stub",
            ollama_base="http://x",
        )
    safe = next(p for p in out.proposals if p.pattern_label == "safe")
    assert safe.item_ids["top"] == id_t2


def test_recommend_avoid_scope_safe_only(tmp_path: Path) -> None:
    dp = tmp_path / "avoid_scope.db"
    db.init_db(dp)
    t1 = ClothesAttributes(category="tops", color="白", style=["カジュアル"], season=["春"], formality=2, fit="", notes="")
    t2 = ClothesAttributes(category="tops", color="黒", style=["カジュアル"], season=["春"], formality=2, fit="", notes="")
    b = ClothesAttributes(category="bottoms", color="紺", style=["カジュアル"], season=["春"], formality=2, fit="", notes="")
    s = ClothesAttributes(category="shoes", color="黒", style=["カジュアル"], season=["春"], formality=2, fit="", notes="")
    id_t1 = db.insert_item("/t1.png", "1" * 64, t1, t1.model_dump(), path=dp)
    id_t2 = db.insert_item("/t2.png", "2" * 64, t2, t2.model_dump(), path=dp)
    id_b = db.insert_item("/b.png", "3" * 64, b, b.model_dump(), path=dp)
    id_s = db.insert_item("/s.png", "4" * 64, s, s.model_dump(), path=dp)

    grouped = db.get_items_by_categories(["tops", "bottoms", "shoes"], dp)
    inp = RecommendInput(situation="カフェ", temp_feel="普通", style="カジュアル")
    avoid = {f"{id_t1}-{id_b}-{id_s}"}
    with patch("recommender.narrate_outfit", side_effect=_fake_narrate):
        out = recommend_outfits(
            grouped,
            inp,
            avoid_triplet_keys=avoid,
            avoid_scope="safe",
            use_llm=True,
            ollama_model="stub",
            ollama_base="http://x",
        )
    safe = next(p for p in out.proposals if p.pattern_label == "safe")
    clean = next(p for p in out.proposals if p.pattern_label == "clean")
    assert safe.item_ids["top"] == id_t2  # avoided triplet is skipped for safe
    assert clean.item_ids["top"] == id_t1  # allowed for clean-only scope
