from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import streamlit as st

import db
from image_tools import PortraitOptions, make_profile_portrait
from models.schema import ClothesAttributes, RecommendInput
from recommender import recommend_outfits
from vlm import DEFAULT_OLLAMA_URL, DEFAULT_VISION_MODEL, extract_clothing_attributes


ROOT = Path(__file__).resolve().parent


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _save_upload(upload: Any, dst_dir: Path) -> Path:
    data = upload.getvalue()
    h = _sha256_bytes(data)
    suffix = Path(upload.name).suffix.lower() if getattr(upload, "name", "") else ""
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        suffix = ".png"
    dst_dir.mkdir(parents=True, exist_ok=True)
    p = (dst_dir / f"{h}{suffix}").resolve()
    if not p.exists():
        p.write_bytes(data)
    return p


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _truthy(s: str) -> bool:
    t = s.strip().lower()
    return t in ("1", "true", "yes", "on", "y")


def _insert_sample_wardrobe_3(dpath: Path) -> int:
    """Inserts 3 items from repo demo PNGs (no Ollama). For LP / GIF / offline demos."""
    items: list[tuple[Path, ClothesAttributes]] = [
        (
            ROOT / "docs/assets/wardrobe-demo/tops_white_tee.png",
            ClothesAttributes(
                category="tops",
                color="白",
                style=["カジュアル"],
                season=["春", "夏"],
                formality=2,
                fit="レギュラー",
                notes="(demo) wardrobe sample",
            ),
        ),
        (
            ROOT / "docs/assets/wardrobe-demo/bottoms_navy_slacks.png",
            ClothesAttributes(
                category="bottoms",
                color="ネイビー",
                style=["きれいめ", "カジュアル"],
                season=["春", "秋", "冬"],
                formality=3,
                fit="スリム",
                notes="(demo) wardrobe sample",
            ),
        ),
        (
            ROOT / "docs/assets/wardrobe-demo/shoes_black_leather.png",
            ClothesAttributes(
                category="shoes",
                color="黒",
                style=["きれいめ"],
                season=["通年"],
                formality=3,
                fit="",
                notes="(demo) wardrobe sample",
            ),
        ),
    ]
    n = 0
    for p, attrs in items:
        if not p.is_file():
            raise FileNotFoundError(f"demo image missing: {p}")
        data = p.read_bytes()
        h = _sha256_bytes(data)
        if db.find_by_hash(h, dpath) is not None:
            continue
        raw = attrs.model_dump()
        db.insert_item(str(p.resolve()), h, attrs, raw, path=dpath)
        n += 1
    return n


def main() -> None:
    st.set_page_config(page_title="vlm-outfit-refiner", layout="wide")
    st.title("vlm-outfit-refiner (local MVP)")

    qp = st.query_params

    qp_page = str(qp.get("page", "")).strip().lower()
    qp_id_raw = str(qp.get("id", "")).strip()
    qp_db = str(qp.get("db", "")).strip()
    qp_ollama = str(qp.get("ollama", "")).strip()
    qp_model = str(qp.get("model", "")).strip()
    demo_mode = _truthy(str(qp.get("demo", "")))
    no_llm = _truthy(str(qp.get("no_llm", "")))

    page_map = {
        "add": "Add",
        "list": "List",
        "edit": "Edit",
        "reclassify": "Reclassify",
        "recommend": "Recommend",
        "portrait": "Portrait",
    }
    initial_page = page_map.get(qp_page, "Add")
    initial_id = 1
    try:
        if qp_id_raw:
            initial_id = max(1, int(qp_id_raw))
    except ValueError:
        initial_id = 1

    with st.sidebar:
        st.header("Settings")
        db_path = st.text_input(
            "DB path",
            value=qp_db or str(ROOT / "data" / "outfit.db"),
        )
        ollama = st.text_input(
            "Ollama URL",
            value=qp_ollama or os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_URL),
        )
        model = st.text_input(
            "Model",
            value=qp_model or os.environ.get("OLLAMA_VISION_MODEL", DEFAULT_VISION_MODEL),
        )
        pages = ["Add", "List", "Edit", "Reclassify", "Recommend", "Portrait"]
        page = st.radio("Page", pages, index=pages.index(initial_page))

    dpath = Path(db_path).expanduser().resolve()
    db.init_db(dpath)

    if page == "Add":
        st.subheader("Add clothing image")
        if demo_mode:
            st.caption(
                "LP / GIF: VLM なしで3点（tops/bottoms/shoes）を一括登録。通常利用では「画像を VLM 抽出」フロー。"
            )
            if st.button("Load 3 sample items (wardrobe, no Ollama)"):
                try:
                    n = _insert_sample_wardrobe_3(dpath)
                    st.success(f"loaded {n} new item(s) (duplicates skipped).")
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))
        ups = st.file_uploader(
            "Upload images",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
        )
        if ups:
            st.caption(f"{len(ups)} files selected")
            st.image(ups[: min(6, len(ups))])
        if st.button("Extract attributes and save", disabled=not ups):
            results = []
            ok_n = dedup_n = fail_n = 0
            for up in ups:
                try:
                    img_path = _save_upload(up, ROOT / "data" / "uploads")
                    fhash = _sha256_bytes(img_path.read_bytes())
                    existing = db.find_by_hash(fhash, dpath)
                    if existing is not None:
                        dedup_n += 1
                        ok_n += 1
                        results.append({"ok": True, "deduplicated": True, "existing_id": existing, "image_path": str(img_path)})
                        continue
                    attrs = extract_clothing_attributes(img_path, model=model, base_url=ollama)
                    row_dict = attrs.model_dump()
                    iid = db.insert_item(str(img_path), fhash, attrs, row_dict, path=dpath)
                    ok_n += 1
                    results.append({"ok": True, "deduplicated": False, "id": iid, "image_path": str(img_path), "attributes": row_dict})
                except Exception as e:  # noqa: BLE001
                    fail_n += 1
                    results.append({"ok": False, "error": str(e), "filename": getattr(up, "name", "")})
            st.success(f"done: ok={ok_n} (dedup={dedup_n}) failed={fail_n}")
            st.code(_json({"ok": True, "ok": ok_n, "deduplicated": dedup_n, "failed": fail_n, "results": results}), language="json")

    elif page == "List":
        st.subheader("Registered items")
        items = db.list_all_items(dpath)
        st.write(f"count={len(items)}")
        st.dataframe(items, use_container_width=True)
        with st.expander("Raw JSON"):
            st.code(_json({"count": len(items), "items": items}), language="json")

    elif page == "Edit":
        st.subheader("Edit attributes (manual)")
        cols = st.columns(2)
        with cols[0]:
            item_id = st.number_input("id", min_value=1, step=1, value=initial_id)
            before = db.get_item(int(item_id), dpath)
            st.caption("Before")
            st.code(_json(before) if before else _json({"ok": False, "error": "not found"}), language="json")
        with cols[1]:
            st.caption("Patch (only fields you set will be applied)")
            category = st.text_input("category (optional)", value="")
            color = st.text_input("color (optional)", value="")
            style = st.text_input("style tags (comma-separated, optional)", value="")
            season = st.text_input("season tags (comma-separated, optional)", value="")
            set_formality = st.checkbox("set formality", value=False)
            formality = st.number_input(
                "formality (1-5)", min_value=1, max_value=5, value=3, disabled=not set_formality
            )
            fit = st.text_input("fit (optional)", value="")
            notes = st.text_input("notes (optional)", value="")
            apply = st.button("Apply edit")
        if apply:
            if before is None:
                st.error("no such id")
            else:
                patch: dict[str, Any] = {}
                if category.strip():
                    patch["category"] = category.strip()
                if color.strip():
                    patch["color"] = color.strip()
                if style.strip():
                    patch["style"] = [x.strip() for x in style.split(",") if x.strip()]
                if season.strip():
                    patch["season"] = [x.strip() for x in season.split(",") if x.strip()]
                if fit.strip():
                    patch["fit"] = fit.strip()
                if notes.strip():
                    patch["notes"] = notes.strip()
                if set_formality:
                    patch["formality"] = int(formality)
                if not patch:
                    st.warning("Nothing to apply.")
                else:
                    try:
                        attrs = db.update_item(int(item_id), dpath, **patch)
                        if attrs is None:
                            st.error("update failed")
                        else:
                            st.success("Updated.")
                            st.code(_json({"ok": True, "id": int(item_id), "attributes": attrs.model_dump()}), language="json")
                    except Exception as e:  # noqa: BLE001
                        st.error(str(e))

    elif page == "Reclassify":
        st.subheader("Reclassify (run VLM again)")
        item_id = st.number_input("id", min_value=1, step=1, value=initial_id)
        before = db.get_item(int(item_id), dpath)
        st.caption("Current")
        st.code(_json(before) if before else _json({"ok": False, "error": "not found"}), language="json")
        if st.button("Run VLM and overwrite", disabled=before is None):
            try:
                img_path = Path(str(before["image_path"])).expanduser().resolve()
                if not img_path.is_file():
                    st.error(f"image not found: {img_path}")
                else:
                    fhash = _sha256_bytes(img_path.read_bytes())
                    attrs = extract_clothing_attributes(img_path, model=model, base_url=ollama)
                    row_dict = attrs.model_dump()
                    ok = db.set_item_attributes(int(item_id), attrs, raw=row_dict, file_hash=fhash, path=dpath)
                    if not ok:
                        st.error("update failed")
                    else:
                        st.success("Reclassified.")
                        after = db.get_item(int(item_id), dpath)
                        st.code(_json({"ok": True, "before": before, "after": after}), language="json")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))

    elif page == "Recommend":
        st.subheader("Recommend (3 patterns)")
        if no_llm:
            st.caption("no_llm=1: 提案文はローカル補完（Ollama 非使用）。")
        situation = st.text_input("situation", value="カフェ")
        temp = st.selectbox("temp_feel", ["普通", "暑い", "寒い"], index=0)
        pref_style = st.text_input("style", value="カジュアル")
        if st.button("Run 3-pattern recommend"):
            try:
                grouped = db.get_items_by_categories(
                    ["tops", "bottoms", "shoes", "outer", "bag", "accessory"],
                    dpath,
                )
                inp = RecommendInput(situation=situation, temp_feel=temp, style=pref_style)
                out = recommend_outfits(
                    grouped,
                    inp,
                    ollama_model=model,
                    ollama_base=ollama,
                    use_llm=not no_llm,
                )
                payload = json.loads(out.model_dump_json())
                st.code(_json({"ok": True, **payload}), language="json")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))

    else:  # Portrait
        st.subheader("Portrait (profile photo maker)")
        up = st.file_uploader("Upload a selfie/photo", type=["png", "jpg", "jpeg", "webp"])
        size = st.slider("size", min_value=512, max_value=2048, value=1024, step=128)
        bg = st.selectbox("background", ["gradient", "solid"], index=0)
        vignette = st.slider("vignette", min_value=0.0, max_value=0.6, value=0.18, step=0.02)
        if up:
            st.image(up)
        if st.button("Generate portrait", disabled=up is None):
            try:
                src = _save_upload(up, ROOT / "data" / "uploads")
                dst = (ROOT / "data" / "portraits" / (src.stem + ".portrait.png")).resolve()
                opt = PortraitOptions(size=int(size), bg_style=bg, vignette=float(vignette))
                outp = make_profile_portrait(src, dst, opt=opt)
                st.success("Generated.")
                st.image(str(outp))
                st.code(_json({"ok": True, "src": str(src), "dst": str(outp)}), language="json")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))


if __name__ == "__main__":
    main()

