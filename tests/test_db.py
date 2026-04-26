from __future__ import annotations

from pathlib import Path

import db
from models.schema import ClothesAttributes


def _attrs(**kwargs: object) -> ClothesAttributes:
    base = dict(
        category="tops",
        color="白",
        style=["カジュアル"],
        season=["春"],
        formality=2,
        fit="レギュラー",
        notes="",
    )
    base.update(kwargs)
    return ClothesAttributes.model_validate(base)


def test_insert_get_update_set(tmp_path: Path) -> None:
    dp = tmp_path / "wardrobe.db"
    db.init_db(dp)
    a = _attrs()
    iid = db.insert_item("/img/shirt.png", "h" * 64, a, a.model_dump(), path=dp)
    row = db.get_item(iid, dp)
    assert row is not None
    assert row["category"] == "tops"
    assert row["color"] == "白"

    u = db.update_item(iid, dp, category="shoes", color="黒")
    assert u is not None
    assert u.category == "shoes"

    a2 = _attrs(category="bottoms", color="紺", style=["きれいめ"])
    ok = db.set_item_attributes(iid, a2, raw=a2.model_dump(), file_hash="f" * 64, path=dp)
    assert ok
    row2 = db.get_item(iid, dp)
    assert row2["category"] == "bottoms"
    assert row2["formality"] == 2


def test_find_by_hash(tmp_path: Path) -> None:
    dp = tmp_path / "h.db"
    db.init_db(dp)
    h = "a" * 64
    iid = db.insert_item("/a.png", h, _attrs(), None, path=dp)
    assert db.find_by_hash(h, dp) == iid
    assert db.find_by_hash("b" * 64, dp) is None


def test_get_items_by_categories(tmp_path: Path) -> None:
    dp = tmp_path / "g.db"
    db.init_db(dp)
    db.insert_item("/t.png", "1" * 64, _attrs(category="tops"), None, path=dp)
    db.insert_item("/b.png", "2" * 64, _attrs(category="bottoms", color="紺"), None, path=dp)
    db.insert_item("/s.png", "3" * 64, _attrs(category="shoes"), None, path=dp)
    g = db.get_items_by_categories(["tops", "bottoms", "shoes"], dp)
    assert len(g["tops"]) == 1
    assert len(g["bottoms"]) == 1
    assert len(g["shoes"]) == 1
