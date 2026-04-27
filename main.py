from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# Run from project root: python main.py
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

import db
from models.schema import RecommendInput
from recommender import recommend_outfits
from vlm import (
    DEFAULT_OLLAMA_URL,
    DEFAULT_VISION_MODEL,
    extract_clothing_attributes,
)
from image_tools import PortraitOptions, make_profile_portrait
from presets import find_preset, load_presets, presets_to_json


def _file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _add_one_image(
    image_path: Path,
    *,
    dpath: Path | None,
    model: str | None,
    ollama: str | None,
) -> dict:
    p = image_path.expanduser().resolve()
    if not p.is_file():
        return {"ok": False, "error": f"file not found: {p}", "image_path": str(p)}
    fhash = _file_sha256(p)
    db.init_db(dpath)
    existing = db.find_by_hash(fhash, dpath)
    if existing is not None:
        return {
            "ok": True,
            "deduplicated": True,
            "message": "同じ内容の服は既に登録済みです。",
            "existing_id": existing,
            "file_hash": fhash,
            "image_path": str(p),
        }
    attrs = extract_clothing_attributes(p, model=model, base_url=ollama or DEFAULT_OLLAMA_URL)
    row_dict = attrs.model_dump()
    iid = db.insert_item(str(p), fhash, attrs, row_dict, path=dpath)
    return {
        "ok": True,
        "deduplicated": False,
        "id": iid,
        "file_hash": fhash,
        "image_path": str(p),
        "attributes": row_dict,
    }


def _cmd_add(args: argparse.Namespace) -> int:
    dpath: Path | None = Path(args.db) if args.db else None
    if dpath:
        dpath = dpath.expanduser().resolve()
    try:
        out = _add_one_image(
            Path(args.image_path),
            dpath=dpath,
            model=args.model,
            ollama=args.ollama,
        )
    except Exception as e:  # noqa: BLE001 — surface to CLI user
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 2


def _cmd_add_batch(args: argparse.Namespace) -> int:
    dpath: Path | None = Path(args.db) if args.db else None
    if dpath:
        dpath = dpath.expanduser().resolve()
    root = Path(args.dir).expanduser().resolve()
    if not root.exists():
        print(json.dumps({"ok": False, "error": f"dir not found: {root}"}, ensure_ascii=False), file=sys.stderr)
        return 2

    exts = {".jpg", ".jpeg", ".png", ".webp"}
    paths = list(root.rglob("*")) if args.recursive else list(root.glob("*"))
    imgs = [p for p in paths if p.is_file() and p.suffix.lower() in exts]
    imgs.sort()
    if args.limit and args.limit > 0:
        imgs = imgs[: int(args.limit)]

    results: list[dict] = []
    ok_n = dedup_n = fail_n = 0
    for p in imgs:
        try:
            r = _add_one_image(p, dpath=dpath, model=args.model, ollama=args.ollama)
        except Exception as e:  # noqa: BLE001
            r = {"ok": False, "error": str(e), "image_path": str(p)}
        results.append(r)
        if r.get("ok"):
            ok_n += 1
            if r.get("deduplicated"):
                dedup_n += 1
        else:
            fail_n += 1

    out = {
        "ok": True,
        "dir": str(root),
        "recursive": bool(args.recursive),
        "scanned": len(imgs),
        "added_or_deduped": ok_n,
        "deduplicated": dedup_n,
        "failed": fail_n,
        "results": results if args.verbose else [],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _read_line(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _parse_temp(s: str) -> str:
    t = s.strip()
    if t in ("1", "暑い"):
        return "暑い"
    if t in ("2", "寒い"):
        return "寒い"
    if t in ("0", "3", "普通"):
        return "普通"
    return t if t in ("暑い", "寒い", "普通") else "普通"


def _cmd_recommend(args: argparse.Namespace) -> int:
    dpath: Path | None = Path(args.db) if args.db else None
    if dpath:
        dpath = dpath.expanduser().resolve()
    db.init_db(dpath)
    g = db.get_items_by_categories(
        ["tops", "bottoms", "shoes", "outer", "bag", "accessory"],
        dpath,
    )
    preset_name = (args.preset or "").strip()
    if preset_name:
        presets_path = Path(args.presets).expanduser().resolve() if args.presets else (_ROOT / "presets" / "presets.json")
        try:
            presets = load_presets(presets_path)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"failed to load presets: {e}"}, ensure_ascii=False), file=sys.stderr)
            return 2
        pr = find_preset(presets, preset_name)
        if pr is None:
            print(json.dumps({"ok": False, "error": f"unknown preset: {preset_name}", "available": [p.name for p in presets]}, ensure_ascii=False), file=sys.stderr)
            return 2
        sit = pr.situation
        temp = pr.temp_feel
        st = pr.style
    elif args.situation:
        sit = args.situation
        temp = _parse_temp(args.temp or "普通")
        st = args.style or "カジュアル"
    else:
        print("シチュエーション（例: デート, 仕事, カフェ）: ", end="")
        sit = _read_line("").strip() or "普段"
        print("気温感 [0=普通, 1=暑い, 2=寒い] もしくは 漢字で: ", end="")
        temp = _parse_temp(_read_line("") or "普通")
        print("好みのスタイル（例: きれいめ, カジュアル）: ", end="")
        st = _read_line("").strip() or "カジュアル"

    inp = RecommendInput(situation=sit, temp_feel=temp, style=st, model=args.model)  # type: ignore[arg-type]
    ollama_base = args.ollama or os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_URL)
    try:
        res = recommend_outfits(
            g,
            inp,
            ollama_model=args.model,
            ollama_base=ollama_base,
            use_llm=not bool(args.no_llm),
        )
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    payload = json.loads(res.model_dump_json())
    out = {"ok": True, **payload}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    dpath: Path | None = Path(_args.db) if _args.db else None
    if dpath:
        dpath = dpath.expanduser().resolve()
    db.init_db(dpath)
    rows = db.list_all_items(dpath)
    print(json.dumps({"count": len(rows), "items": rows}, ensure_ascii=False, indent=2))
    return 0


def _csv_tags(s: str) -> list[str]:
    return [p.strip() for p in s.split(",") if p.strip()]


def _cmd_edit(args: argparse.Namespace) -> int:
    dpath: Path | None = Path(args.db) if args.db else None
    if dpath:
        dpath = dpath.expanduser().resolve()
    db.init_db(dpath)
    before = db.get_item(int(args.id), dpath)
    if before is None:
        err = {"ok": False, "error": f"no item with id {args.id}"}
        print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
        return 1
    patch: dict = {}
    if args.category is not None:
        patch["category"] = args.category
    if args.color is not None:
        patch["color"] = args.color
    if args.style is not None:
        patch["style"] = _csv_tags(args.style)
    if args.season is not None:
        patch["season"] = _csv_tags(args.season)
    if args.formality is not None:
        patch["formality"] = int(args.formality)
    if args.fit is not None:
        patch["fit"] = args.fit
    if args.notes is not None:
        patch["notes"] = args.notes
    if not patch:
        err = {"ok": False, "error": "1つ以上の --category / --color / --style / などを指定してください"}
        print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        attrs = db.update_item(int(args.id), dpath, **patch)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    if attrs is None:
        err = {"ok": False, "error": f"update failed for id {args.id}"}
        print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
        return 1
    after = db.get_item(int(args.id), dpath)
    out: dict = {
        "ok": True,
        "id": int(args.id),
        "before": {k: v for k, v in before.items() if k != "raw_json"},
        "attributes": attrs.model_dump(),
    }
    if after:
        out["image_path"] = after["image_path"]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_reclassify(args: argparse.Namespace) -> int:
    dpath: Path | None = Path(args.db) if args.db else None
    if dpath:
        dpath = dpath.expanduser().resolve()
    db.init_db(dpath)
    before = db.get_item(int(args.id), dpath)
    if before is None:
        print(
            json.dumps({"ok": False, "error": f"no item with id {args.id}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    p = Path(str(before["image_path"])).expanduser().resolve()
    if not p.is_file():
        err = {
            "ok": False,
            "error": "画像ファイルがありません（パスを直すか、別のディスクにコピーしてください）",
            "image_path": str(p),
        }
        print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
        return 2
    fhash = _file_sha256(p)
    try:
        attrs = extract_clothing_attributes(
            p, model=args.model, base_url=args.ollama or DEFAULT_OLLAMA_URL
        )
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    row_dict = attrs.model_dump()
    ok = db.set_item_attributes(
        int(args.id),
        attrs,
        raw=row_dict,
        file_hash=fhash,
        path=dpath,
    )
    if not ok:
        print(
            json.dumps({"ok": False, "error": f"update failed for id {args.id}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    out = {
        "ok": True,
        "id": int(args.id),
        "reclassified": True,
        "file_hash": fhash,
        "image_path": str(p),
        "before": {k: v for k, v in before.items() if k != "raw_json"},
        "attributes": row_dict,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_portrait(args: argparse.Namespace) -> int:
    src = Path(args.image_path).expanduser().resolve()
    if not src.is_file():
        print(json.dumps({"ok": False, "error": f"file not found: {src}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else (_ROOT / "data" / "portraits")
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / (src.stem + ".portrait.png")

    opt = PortraitOptions(
        size=int(args.size),
        bg_style=args.bg,
        vignette=float(args.vignette),
    )
    try:
        p = make_profile_portrait(src, dst, opt=opt)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "src": str(src), "dst": str(p)}, ensure_ascii=False, indent=2))
    return 0


def _cmd_preset_list(args: argparse.Namespace) -> int:
    presets_path = Path(args.presets).expanduser().resolve() if args.presets else (_ROOT / "presets" / "presets.json")
    try:
        presets = load_presets(presets_path)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "path": str(presets_path), "presets": presets_to_json(presets)}, ensure_ascii=False, indent=2))
    return 0


def _cmd_preset_show(args: argparse.Namespace) -> int:
    presets_path = Path(args.presets).expanduser().resolve() if args.presets else (_ROOT / "presets" / "presets.json")
    presets = load_presets(presets_path)
    pr = find_preset(presets, args.name)
    if pr is None:
        print(json.dumps({"ok": False, "error": f"unknown preset: {args.name}", "available": [p.name for p in presets]}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "preset": presets_to_json([pr])[0]}, ensure_ascii=False, indent=2))
    return 0


def _cmd_dogfood(args: argparse.Namespace) -> int:
    dpath: Path | None = Path(args.db) if args.db else None
    if dpath:
        dpath = dpath.expanduser().resolve()
    db.init_db(dpath)
    grouped = db.get_items_by_categories(
        ["tops", "bottoms", "shoes", "outer", "bag", "accessory"],
        dpath,
    )
    # Build id -> item map for summary enrichment
    id_map: dict[int, dict] = {}
    for cat_items in grouped.values():
        for it in cat_items:
            try:
                id_map[int(it["id"])] = it
            except Exception:
                continue

    def _item_brief(item_id: int) -> dict:
        it = id_map.get(int(item_id))
        if not it:
            return {"id": int(item_id)}
        return {
            "id": int(it.get("id")),
            "category": it.get("category"),
            "color": it.get("color"),
            "formality": it.get("formality"),
            "style": it.get("style", []),
        }

    presets_path = Path(args.presets).expanduser().resolve() if args.presets else (_ROOT / "presets" / "presets.json")
    presets = load_presets(presets_path)
    only = [x.strip() for x in (args.only or "").split(",") if x.strip()]
    if only:
        presets = [p for p in presets if p.name in set(only)]
    if args.limit and args.limit > 0:
        presets = presets[: int(args.limit)]
    ollama_base = args.ollama or os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_URL)
    results = []
    summaries = []
    for p in presets:
        inp = RecommendInput(situation=p.situation, temp_feel=p.temp_feel, style=p.style, model=args.model)  # type: ignore[arg-type]
        try:
            out = recommend_outfits(
                grouped,
                inp,
                ollama_model=args.model,
                ollama_base=ollama_base,
                use_llm=bool(args.llm),
            )
            out_json = json.loads(out.model_dump_json())
            results.append({"preset": p.name, "label": p.label, "ok": True, "output": out_json})
            # summary
            try:
                props = out_json.get("proposals") or []
                by_pat = {}
                for pr in props:
                    pat = pr.get("pattern_label")
                    item_ids = pr.get("item_ids") or {}
                    by_pat[str(pat)] = {
                        "item_ids": item_ids,
                        "items": {k: _item_brief(v) for k, v in item_ids.items()},
                        "summary": pr.get("summary", ""),
                    }
                summaries.append(
                    {
                        "preset": p.name,
                        "label": p.label,
                        "situation": out_json.get("situation"),
                        "temp_feel": out_json.get("temp_feel"),
                        "user_style": out_json.get("user_style"),
                        "by_pattern": by_pat,
                    }
                )
            except Exception:
                summaries.append({"preset": p.name, "label": p.label, "error": "failed to build summary"})
        except Exception as e:  # noqa: BLE001
            results.append({"preset": p.name, "label": p.label, "ok": False, "error": str(e)})
            summaries.append({"preset": p.name, "label": p.label, "error": str(e)})
    payload = {
        "ok": True,
        "db": str(dpath) if dpath else "default",
        "presets_path": str(presets_path),
        "count": len(results),
        "use_llm": bool(args.llm),
        "summaries": summaries if bool(args.summary) else [],
        "results": results if (not bool(args.summary) or bool(args.full)) else [],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="VLM による服属性登録とローカルコーデ提案 (Ollama + SQLite)",
    )
    p.add_argument(
        "--db",
        help="SQLite DB path (default: data/outfit.db)",
    )
    p.add_argument(
        "--ollama",
        default=None,
        help="Ollama base URL (default: env OLLAMA_HOST or http://127.0.0.1:11434)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Vision/LLM model (default: env OLLAMA_VISION_MODEL or qwen2.5vl:7b)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="服画像を登録し、VLMで属性抽出")
    a.add_argument("image_path", type=str, help="画像パス")
    a.set_defaults(func=_cmd_add)

    ab = sub.add_parser("add-batch", help="フォルダ内の画像をまとめて登録（dogfooding向け）")
    ab.add_argument("dir", type=str, help="画像が入ったディレクトリ")
    ab.add_argument("--recursive", action="store_true", help="サブディレクトリも対象")
    ab.add_argument("--limit", type=int, default=0, help="最大件数（0=無制限）")
    ab.add_argument("--verbose", action="store_true", help="results を出力に含める")
    ab.set_defaults(func=_cmd_add_batch)

    r = sub.add_parser("recommend", help="3パターン（無難/きれいめ/攻め）を提案")
    r.add_argument(
        "--situation",
        default="",
        help="非対話: シチュエーション文字列",
    )
    r.add_argument("--temp", default="", help="非対話: 0=普通,1=暑い,2=寒い または 漢字")
    r.add_argument(
        "--style", default="", help="非対話: 好みのスタイル（例: きれいめ）"
    )
    r.add_argument("--preset", default="", help="プリセット名（preset list で確認）")
    r.add_argument("--presets", default="", help="プリセットJSONパス（省略時: presets/presets.json）")
    r.add_argument("--no-llm", action="store_true", help="理由文生成をスキップ（高速 dogfood 向け）")
    r.set_defaults(func=_cmd_recommend)

    l = sub.add_parser("list", help="登録アイテムを一覧 (JSON)")
    l.set_defaults(func=_cmd_list)

    e = sub.add_parser("edit", help="登録済み item の属性を手直し（Ollama 不要）")
    e.add_argument("id", type=int, help="items.id（list で確認）")
    e.add_argument(
        "--category",
        default=None,
        help="tops|bottoms|outer|shoes|bag|accessory",
    )
    e.add_argument("--color", default=None, help="色（日本語など）")
    e.add_argument("--formality", type=int, default=None, help="1-5")
    e.add_argument(
        "--style", default=None, help="タグ。カンマ区切り（例: カジュアル,シンプル）"
    )
    e.add_argument(
        "--season", default=None, help="例: 春,夏,秋,冬。カンマ区切り"
    )
    e.add_argument("--fit", default=None)
    e.add_argument("--notes", default=None)
    e.set_defaults(func=_cmd_edit)

    rc = sub.add_parser(
        "reclassify",
        help="登録済みの画像パスについて VLM で属性を取り直し（edit の前に試すと便利）",
    )
    rc.add_argument("id", type=int, help="items.id（list で確認）")
    rc.set_defaults(func=_cmd_reclassify)

    pr = sub.add_parser(
        "portrait",
        help="背景/色味/トリミングでプロフィール写真っぽく整える（ポーズや体型は変えない）",
    )
    pr.add_argument("image_path", type=str, help="入力画像パス")
    pr.add_argument("--out-dir", default="", help="出力先ディレクトリ（省略時: data/portraits）")
    pr.add_argument("--size", type=int, default=1024, help="出力サイズ（正方形）")
    pr.add_argument("--bg", choices=["solid", "gradient"], default="gradient")
    pr.add_argument("--vignette", type=float, default=0.18, help="周辺減光 0..1")
    pr.set_defaults(func=_cmd_portrait)

    ps = sub.add_parser("preset", help="想定ユーザー（ペルソナ）プリセット")
    ps.add_argument("--presets", default="", help="プリセットJSONパス（省略時: presets/presets.json）")
    pss = ps.add_subparsers(dest="preset_cmd", required=True)
    psl = pss.add_parser("list", help="プリセット一覧")
    psl.set_defaults(func=_cmd_preset_list)
    pshow = pss.add_parser("show", help="プリセット内容を表示")
    pshow.add_argument("name", type=str)
    pshow.set_defaults(func=_cmd_preset_show)

    dg = sub.add_parser("dogfood", help="複数プリセットで recommend をまとめて実行")
    dg.add_argument("--presets", default="", help="プリセットJSONパス（省略時: presets/presets.json）")
    dg.add_argument("--only", default="", help="実行するプリセット名（カンマ区切り）")
    dg.add_argument("--limit", type=int, default=0, help="最大件数（0=無制限）")
    dg.add_argument("--llm", action="store_true", help="理由文生成も回す（遅い）")
    dg.add_argument("--summary", action="store_true", help="比較用の短い summary を含める（既定で results は省略）")
    dg.add_argument("--full", action="store_true", help="--summary 時も results（フル出力）を含める")
    dg.set_defaults(func=_cmd_dogfood)

    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.model:
        args.model = os.environ.get("OLLAMA_VISION_MODEL", DEFAULT_VISION_MODEL)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
