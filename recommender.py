from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from models.schema import ProposedOutfitText, RecommendInput, RecommendOutput
from vlm import DEFAULT_OLLAMA_URL, DEFAULT_VISION_MODEL, narrate_outfit

# --- Heuristics: situation -> target formality (1-5) ---------------------------------

_SITUATION_KEYWORDS: list[tuple[str, int]] = [
    ("会議", 4),
    ("面接", 5),
    ("仕事", 4),
    ("オフィス", 4),
    ("式典", 5),
    ("結婚式", 4),
    ("参観", 3),
    ("学校", 3),
    ("デート", 3),
    ("お食事", 3),
    ("食事会", 3),
    ("カフェ", 2),
    ("買い物", 2),
    ("普段", 2),
    ("旅行", 2),
    ("遊び", 2),
    ("スポーツ", 1),
    ("部屋着", 1),
]


def _infer_target_formality(situation: str) -> int:
    s = situation.strip()
    for k, f in _SITUATION_KEYWORDS:
        if k in s:
            return f
    return 3


def _temp_to_seasons(feel: str) -> set[str] | None:
    if feel == "暑い":
        return {"夏", "春"}
    if feel == "寒い":
        return {"冬", "秋", "春"}
    return None  # any


def _tokenize(jp: str) -> set[str]:
    t = re.sub(r"\s+", " ", jp.strip().lower())
    if not t:
        return set()
    parts = re.split(r"[,、/|]+", t)
    out: set[str] = set()
    for p in parts:
        w = p.strip()
        if len(w) >= 1:
            out.add(w)
    return out


# --- Color buckets (same-tone avoidance) ----------------------------------------


def _color_bucket(text: str) -> str:
    t = (text or "").lower()
    pairs: list[tuple[str, str]] = [
        ("白", "白_系"),
        ("off", "白_系"),
        ("ivory", "白_系"),
        ("アイボリー", "白_系"),
        ("黒", "黒_系"),
        ("black", "黒_系"),
        ("紺", "紺_系"),
        ("ネイビー", "紺_系"),
        ("navy", "紺_系"),
        ("紺色", "紺_系"),
        ("青", "青_系"),
        ("blue", "青_系"),
        ("ブルー", "青_系"),
        ("グレー", "灰_系"),
        ("灰", "灰_系"),
        ("gray", "灰_系"),
        ("茶", "茶_系"),
        ("ベージュ", "茶_系"),
        ("キャメル", "茶_系"),
        ("brawn", "茶_系"),  # typo safety
        ("棕", "茶_系"),
        ("緑", "緑_系"),
        ("olive", "緑_系"),
        ("カーキ", "緑_系"),
        ("グリーン", "緑_系"),
        ("茶色", "茶_系"),
        ("ピンク", "ピンク_系"),
        ("赤", "赤_系"),
        ("黄", "黄_系"),
        ("オレンジ", "黄_系"),
    ]
    for sub, b in pairs:
        if sub in t:
            return b
    if not t:
        return "unknown"
    return t[:8]


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    u = sa | sb
    if not u:
        return 0.0
    return len(sa & sb) / len(u)


@dataclass
class _Scored:
    top: dict[str, Any]
    bottom: dict[str, Any]
    shoes: dict[str, Any]
    outer: dict[str, Any] | None
    base: float
    key: str


PATTERN_META = [
    ("safe", "無難", "定番のバランス。シーンに馴染みやすく、失敗しにくい着こなし。"),
    ("clean", "きれいめ", "清潔感と品格を出し、きちんと見せる。"),
    ("bold", "攻め", "トレンド感や個性を出し、印象に残るコーディネート。"),
]


def _item_affinity(
    it: dict[str, Any],
    user_tokens: set[str],
    target_f: int,
    seasons: set[str] | None,
) -> float:
    st = it.get("style") or []
    st_l = [x.lower() for x in st]
    ut_l = [x.lower() for x in user_tokens]
    sc = 2.0 * _jaccard(st_l, ut_l)
    f = int(it.get("formality", 3))
    sc -= 0.4 * abs(f - target_f)
    se = set(it.get("season") or [])
    if seasons is not None and se:
        overlap = len(se & (seasons | {"通年", "オールシーズン"})) / max(1, len(se))
        sc += 0.5 * overlap
    elif seasons is not None and not se:
        sc += 0.0
    return sc


def _pair_color_penalty(top: dict[str, Any], bottom: dict[str, Any], weight: float) -> float:
    bt = _color_bucket(str(top.get("color", "")))
    bb = _color_bucket(str(bottom.get("color", "")))
    if bt == bb and bt not in ("unknown",):
        return 3.0 * weight
    if bt == bb and bt in ("白_系", "黒_系", "灰_系", "紺_系", "茶_系"):
        return 2.0 * weight
    if bt in ("紺_系", "黒_系", "青_系") and bb in ("紺_系", "黒_系", "青_系"):
        return 1.2 * weight
    return 0.0


def _formality_nudge(items: list[dict[str, Any]], want_high: bool) -> float:
    fs = [int(x.get("formality", 3)) for x in items]
    avg = sum(fs) / max(1, len(fs))
    if want_high:
        return 0.5 * (avg - 2.5)
    return 0.2 * (3.0 - abs(avg - 3.0))


def _style_hit(styles: list[str], subs: list[str]) -> int:
    s = " ".join(styles)
    return sum(1 for w in subs if w in s)


def _all_triplets(
    tops: list[dict[str, Any]],
    bottoms: list[dict[str, Any]],
    shoes: list[dict[str, Any]],
) -> list[_Scored]:
    out: list[_Scored] = []
    for top in tops:
        for bottom in bottoms:
            for shoe in shoes:
                out.append(
                    _Scored(
                        top=top,
                        bottom=bottom,
                        shoes=shoe,
                        outer=None,
                        base=0.0,
                        key=f"{top['id']}-{bottom['id']}-{shoe['id']}",
                    )
                )
    return out


def _score_for_pattern(
    s: _Scored,
    inp: RecommendInput,
    target_f: int,
    seasons: set[str] | None,
    user_toks: set[str],
    pat: str,
) -> float:
    items = [s.top, s.bottom, s.shoes]
    t = 0.0
    for it in items:
        t += _item_affinity(it, user_toks, target_f, seasons)
    t /= 3.0

    if pat == "safe":
        t -= _pair_color_penalty(s.top, s.bottom, 1.0)
        t += _formality_nudge(items, want_high=False)
    elif pat == "clean":
        t -= 0.6 * _pair_color_penalty(s.top, s.bottom, 1.0)
        t += 0.4 * _style_hit(
            s.top.get("style", []) + s.bottom.get("style", []) + s.shoes.get("style", []),
            ["きれいめ", "清潔", "上品", "シック", "オフィス"],
        )
        t += _formality_nudge(items, want_high=True)
    else:  # bold
        t -= 0.3 * _pair_color_penalty(s.top, s.bottom, 1.0)
        t += 0.3 * _style_hit(
            s.top.get("style", []) + s.bottom.get("style", []) + s.shoes.get("style", []),
            ["トレンド", "個性", "抜け感", "主役", "柄", "ビッグ", "抜群"],
        )

    # User requested style (e.g. カジュアル) extra weight
    if user_toks:
        for w in list(user_toks)[:4]:
            for it in items:
                if w in " ".join(it.get("style", [])).lower() or w in (it.get("notes") or ""):
                    t += 0.2

    return t


def _select_outer_if_any(
    outer_items: list[dict[str, Any]], inp: RecommendInput, t: _Scored
) -> None:
    if not outer_items:
        return
    if inp.temp_feel != "寒い":
        return
    # Pick outer that best matches first top color bucket / formality
    best: dict[str, Any] | None = None
    best_sc = -1e9
    b_top = _color_bucket(str(t.top.get("color", "")))
    for o in outer_items:
        s_o = _item_affinity(
            o,
            _tokenize(inp.style),
            _infer_target_formality(inp.situation),
            _temp_to_seasons(inp.temp_feel) or set(),
        )
        if _color_bucket(str(o.get("color", ""))) == b_top:
            s_o -= 0.2
        if s_o > best_sc:
            best_sc = s_o
            best = o
    t.outer = best


def recommend_outfits(
    grouped: dict[str, list[dict[str, Any]]],
    inp: RecommendInput,
    *,
    ollama_model: str | None = None,
    ollama_base: str = DEFAULT_OLLAMA_URL,
    use_llm: bool = True,
) -> RecommendOutput:
    tops = grouped.get("tops") or []
    bottoms = grouped.get("bottoms") or []
    shoes = grouped.get("shoes") or []
    if not tops or not bottoms or not shoes:
        msg = f"Need tops, bottoms, and shoes. Have tops={len(tops)}, bottoms={len(bottoms)}, shoes={len(shoes)}. Use `add` to register more items."
        raise ValueError(msg)

    target_f = _infer_target_formality(inp.situation)
    seasons = _temp_to_seasons(inp.temp_feel)
    user_toks = _tokenize(inp.style)

    triples = _all_triplets(tops, bottoms, shoes)
    outer_list = grouped.get("outer") or []
    chosen: list[tuple[str, str, str, _Scored, float]] = []
    used_keys: set[str] = set()

    for pat, ja, desc in PATTERN_META:
        best: _Scored | None = None
        best_sc = -1e18
        for t in triples:
            if t.key in used_keys:
                continue
            sc = _score_for_pattern(t, inp, target_f, seasons, user_toks, pat)
            if sc > best_sc:
                best_sc = sc
                best = t
        if best is None:
            # All triples used: allow repeat for largest pattern set
            for t in triples:
                sc = _score_for_pattern(t, inp, target_f, seasons, user_toks, pat)
                if sc > best_sc:
                    best_sc = sc
                    best = t
        if best is None:
            best = triples[0]
        _select_outer_if_any(outer_list, inp, best)
        used_keys.add(best.key)
        chosen.append((pat, ja, desc, best, best_sc))

    model_name = ollama_model or DEFAULT_VISION_MODEL
    proposals: list[ProposedOutfitText] = []
    for pat, ja, desc, trip, _ in chosen:
        lines: list[str] = []
        for it in (trip.top, trip.bottom, trip.shoes, trip.outer):
            if it is None:
                continue
            st = " ".join(it.get("style") or [])
            lines.append(
                f"- id {it['id']}: {it['category']} color={it['color']!s} formality={it['formality']} style=[{st}] notes={it.get('notes', '')!s}"
            )
        if use_llm:
            uctx = json_dumps(
                {
                    "situation": inp.situation,
                    "temp_feel": inp.temp_feel,
                    "user_style": inp.style,
                }
            )
            outfit_ctx = "\n".join(lines)
            text = narrate_outfit(
                uctx, outfit_ctx, ja, desc, model=ollama_model, base_url=ollama_base
            )
            summary = str(text.get("summary", "おすすめのコーディネート"))
            reason = str(
                text.get("reason", "・合わせやすいバランス\n・シチュエーションに馴染みます")
            )
            tips = str(text.get("tips", ""))
        else:
            # Deterministic, fast fallback for dogfooding without Ollama.
            summary = f"{inp.situation}向けの{ja}コーデ（{inp.temp_feel}）"
            reason = "\n".join(
                [
                    f"・{desc}",
                    "・トップス/ボトムス/靴の基本3点で組みやすい",
                    f"・スタイル: {inp.style}",
                ]
            )
            tips = "色や小物で微調整して自分寄りに寄せるのがおすすめ"
        oids: dict[str, int] = {
            "top": int(trip.top["id"]),
            "bottom": int(trip.bottom["id"]),
            "shoes": int(trip.shoes["id"]),
        }
        if trip.outer is not None:
            oids["outer"] = int(trip.outer["id"])
        proposals.append(
            ProposedOutfitText(
                pattern_label=pat,
                pattern_ja=ja,
                item_ids=oids,
                summary=summary,
                reason=reason,
                tips=tips,
            )
        )

    return RecommendOutput(
        situation=inp.situation,
        temp_feel=inp.temp_feel,
        user_style=inp.style,
        model=model_name,
        proposals=proposals,
    )


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
