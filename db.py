from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from models.schema import ClothesAttributes

# Default DB under data/ for a predictable local layout
_DEFAULT_DB = Path(__file__).resolve().parent / "data" / "outfit.db"
_local = threading.local()


def get_default_db_path() -> Path:
    return _DEFAULT_DB


def _connect(path: Path | None = None) -> sqlite3.Connection:
    dbp = path or get_default_db_path()
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(dbp, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_connection(path: Path | None = None) -> sqlite3.Connection:
    """Thread-local single connection for simple CLI use."""
    key = str(path) if path else "default"
    if not hasattr(_local, "conns"):
        _local.conns = {}
    if key not in _local.conns:
        _local.conns[key] = _connect(path)
    return _local.conns[key]


def init_db(path: Path | None = None) -> None:
    conn = get_connection(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT NOT NULL,
            file_hash TEXT,
            category TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '',
            style_json TEXT NOT NULL DEFAULT '[]',
            season_json TEXT NOT NULL DEFAULT '[]',
            formality INTEGER NOT NULL DEFAULT 3,
            fit TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            raw_json TEXT
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_items_hash ON items(file_hash);")
    conn.commit()


def row_to_attrs(row: sqlite3.Row) -> ClothesAttributes:
    return ClothesAttributes(
        category=row["category"],
        color=row["color"] or "",
        style=json.loads(row["style_json"] or "[]"),
        season=json.loads(row["season_json"] or "[]"),
        formality=int(row["formality"]),
        fit=row["fit"] or "",
        notes=row["notes"] or "",
    )


def insert_item(
    image_path: str,
    file_hash: str | None,
    attrs: ClothesAttributes,
    raw: dict[str, Any] | None = None,
    path: Path | None = None,
) -> int:
    init_db(path)
    conn = get_connection(path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO items (
            image_path, file_hash, category, color, style_json, season_json,
            formality, fit, notes, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            image_path,
            file_hash,
            attrs.category,
            attrs.color,
            json.dumps(list(attrs.style), ensure_ascii=False),
            json.dumps(list(attrs.season), ensure_ascii=False),
            attrs.formality,
            attrs.fit,
            attrs.notes,
            json.dumps(raw, ensure_ascii=False) if raw is not None else None,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_item(
    item_id: int, path: Path | None = None
) -> dict[str, Any] | None:
    init_db(path)
    cur = get_connection(path).cursor()
    cur.execute(
        "SELECT id, image_path, category, color, style_json, season_json, "
        "formality, fit, notes, raw_json FROM items WHERE id = ?",
        (item_id,),
    )
    r = cur.fetchone()
    if r is None:
        return None
    return {
        "id": r["id"],
        "image_path": r["image_path"],
        "category": r["category"],
        "color": r["color"],
        "style": json.loads(r["style_json"] or "[]"),
        "season": json.loads(r["season_json"] or "[]"),
        "formality": r["formality"],
        "fit": r["fit"],
        "notes": r["notes"],
        "raw_json": json.loads(r["raw_json"])
        if r["raw_json"]
        else None,
    }


def update_item(
    item_id: int,
    path: Path | None = None,
    *,
    category: str | None = None,
    color: str | None = None,
    style: list[str] | None = None,
    season: list[str] | None = None,
    formality: int | None = None,
    fit: str | None = None,
    notes: str | None = None,
) -> ClothesAttributes | None:
    """上書きする引数だけ指定。存在しない id のときは None。"""
    cur_row = get_item(item_id, path)
    if cur_row is None:
        return None
    attrs = ClothesAttributes(
        category=category if category is not None else cur_row["category"],
        color=color if color is not None else cur_row["color"],
        style=style if style is not None else cur_row["style"],
        season=season if season is not None else cur_row["season"],
        formality=formality if formality is not None else int(cur_row["formality"]),
        fit=fit if fit is not None else cur_row["fit"],
        notes=notes if notes is not None else cur_row["notes"],
    )
    new_raw = attrs.model_dump()
    init_db(path)
    conn = get_connection(path)
    c = conn.cursor()
    c.execute(
        """
        UPDATE items SET
            category = ?, color = ?, style_json = ?, season_json = ?,
            formality = ?, fit = ?, notes = ?, raw_json = ?
        WHERE id = ?
        """,
        (
            attrs.category,
            attrs.color,
            json.dumps(list(attrs.style), ensure_ascii=False),
            json.dumps(list(attrs.season), ensure_ascii=False),
            attrs.formality,
            attrs.fit,
            attrs.notes,
            json.dumps(new_raw, ensure_ascii=False),
            item_id,
        ),
    )
    conn.commit()
    if c.rowcount == 0:
        return None
    return attrs


def set_item_attributes(
    item_id: int,
    attrs: ClothesAttributes,
    *,
    raw: dict[str, Any] | None = None,
    file_hash: str | None = None,
    path: Path | None = None,
) -> bool:
    """attributes をまとめて置換。存在しない id のときは False。"""
    if get_item(item_id, path) is None:
        return False
    blob_obj = raw if raw is not None else attrs.model_dump()
    blob = json.dumps(blob_obj, ensure_ascii=False)
    init_db(path)
    conn = get_connection(path)
    cur = conn.cursor()
    base_vals: tuple[Any, ...] = (
        attrs.category,
        attrs.color,
        json.dumps(list(attrs.style), ensure_ascii=False),
        json.dumps(list(attrs.season), ensure_ascii=False),
        attrs.formality,
        attrs.fit,
        attrs.notes,
        blob,
    )
    if file_hash is not None:
        cur.execute(
            """
            UPDATE items SET
                category = ?, color = ?, style_json = ?, season_json = ?,
                formality = ?, fit = ?, notes = ?, raw_json = ?,
                file_hash = ?
            WHERE id = ?
            """,
            base_vals + (file_hash, item_id),
        )
    else:
        cur.execute(
            """
            UPDATE items SET
                category = ?, color = ?, style_json = ?, season_json = ?,
                formality = ?, fit = ?, notes = ?, raw_json = ?
            WHERE id = ?
            """,
            base_vals + (item_id,),
        )
    conn.commit()
    return cur.rowcount > 0


def find_by_hash(file_hash: str, path: Path | None = None) -> int | None:
    init_db(path)
    cur = get_connection(path).cursor()
    cur.execute("SELECT id FROM items WHERE file_hash = ? LIMIT 1", (file_hash,))
    r = cur.fetchone()
    return int(r[0]) if r else None


def list_all_items(path: Path | None = None) -> list[dict[str, Any]]:
    init_db(path)
    cur = get_connection(path).cursor()
    cur.execute(
        "SELECT id, image_path, category, color, style_json, season_json, "
        "formality, fit, notes FROM items ORDER BY id"
    )
    rows = []
    for r in cur.fetchall():
        rows.append(
            {
                "id": r["id"],
                "image_path": r["image_path"],
                "category": r["category"],
                "color": r["color"],
                "style": json.loads(r["style_json"] or "[]"),
                "season": json.loads(r["season_json"] or "[]"),
                "formality": r["formality"],
                "fit": r["fit"],
                "notes": r["notes"],
            }
        )
    return rows


def get_items_by_categories(
    categories: list[str], path: Path | None = None
) -> dict[str, list[dict[str, Any]]]:
    init_db(path)
    if not categories:
        return {}
    out: dict[str, list[dict[str, Any]]] = {c: [] for c in categories}
    cur = get_connection(path).cursor()
    q = "SELECT * FROM items WHERE category IN (" + ",".join("?" * len(categories)) + ")"
    cur.execute(q, categories)
    for r in cur.fetchall():
        d: dict[str, Any] = {
            "id": r["id"],
            "image_path": r["image_path"],
            "category": r["category"],
            "color": r["color"],
            "style": json.loads(r["style_json"] or "[]"),
            "season": json.loads(r["season_json"] or "[]"),
            "formality": r["formality"],
            "fit": r["fit"],
            "notes": r["notes"],
        }
        out[r["category"]].append(d)
    return out
