# vlm-outfit-refiner

[![CI](https://github.com/rsasaki0109/vlm-outfit-refiner/actions/workflows/ci.yml/badge.svg)](https://github.com/rsasaki0109/vlm-outfit-refiner/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub Repo stars](https://img.shields.io/github/stars/rsasaki0109/vlm-outfit-refiner?style=social)](https://github.com/rsasaki0109/vlm-outfit-refiner)

**English:** Local-first wardrobe tool: turn clothing photos into structured attributes with **Ollama Vision**, persist in **SQLite**, and get **3 outfit proposals** (safe / clean / bold) with reasons — **no cloud APIs**.

**日本語:** 手持ちの服の写真をローカル VLM で属性化し、シチュエーションに合わせたコーデ案を**無難 / きれいめ / 攻め**の 3 通り、理由付きで返す CLI（＋ Streamlit）。外部クラウド API は使いません（Ollama 前提）。

|       | Links |
|-------|-------|
| LP | [**GitHub Pages**（デモ・FAQ・公開画像の例）](https://rsasaki0109.github.io/vlm-outfit-refiner/) |
| 貢献 | [CONTRIBUTING.md](CONTRIBUTING.md) · [Issues](https://github.com/rsasaki0109/vlm-outfit-refiner/issues) |

**画面デモ（Streamlit · `demo=1` / `no_llm=1` で収録）**

![UI demo: Add → Edit → Recommend](docs/assets/demo-ui-flow.gif)

![ブランド用バナー（静止画）](assets/banner.png)

## 服の写真の例（実写真・CC0）

`add` に渡すような**実際の服の写真**のイメージです（LP と同じ Wikimedia CC0、720px 版）。

| tops | bottoms | shoes |
|:---:|:---:|:---:|
| ![tops (CC0)](docs/assets/public/optimized/tops_tshirt_cc0_720.jpg) | ![bottoms (CC0)](docs/assets/public/optimized/bottoms_skinny_jeans_cc0_720.jpg) | ![shoes (CC0)](docs/assets/public/optimized/shoes_sports_shoes_cc0_720.jpg) |

出典・作者・ライセンスの全文は [`docs/ATTRIBUTION.md`](docs/ATTRIBUTION.md)。

### デモ用の見本画像（リポジトリ内）

`?demo=1` の一括登録やユニットテストで使う、**軽い見本素材**（実写ではありません）。

| tops | bottoms | shoes |
|:---:|:---:|:---:|
| ![demo tops](docs/assets/wardrobe-demo/tops_white_tee.png) | ![demo bottoms](docs/assets/wardrobe-demo/bottoms_navy_slacks.png) | ![demo shoes](docs/assets/wardrobe-demo/shoes_black_leather.png) |

**ほかのセクション:** [要点](#要点) · [クイックスタート](#クイックスタート) · [トラブルシューティング](#トラブルシューティング)

---

## 要点

| 項目 | 内容 |
|------|------|
| 言語 | Python 3.10+ |
| 推論 | [Ollama](https://ollama.com) + Vision モデル（例: `qwen2.5vl:7b`） |
| 永続化 | SQLite（既定 `data/outfit.db`） |
| 入出力 | 主に **JSON**（登録・提案とも） |

```mermaid
flowchart LR
  A[服の画像] --> B[Ollama Vision]
  B --> C[属性 JSON]
  C --> D[(SQLite)]
  D --> E[スコアリング]
  E --> F[Ollama テキスト]
  F --> G[提案 3 パターン]
```

---

## 前提チェック

1. Ollama が起動している（`ollama serve` または常駐サービス）
2. Vision 用モデルを `ollama pull` 済み
3. コーデ提案は **tops / bottoms / shoes 各1点以上** 登録されていること（服が分かる写真のほうがカテゴリ推定が安定しやすい）

---

## クイックスタート

```bash
cd vlm-outfit-refiner
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
ollama pull qwen2.5vl:7b
```

```bash
# 服を登録（1枚ずつ。成功すると JSON が標準出力に出る）
python main.py add ./photos/shirt.jpg
python main.py add ./photos/pants.jpg
python main.py add ./photos/sneakers.jpg

# 提案（対話式は引数なし / 非対話は下記）
python main.py recommend --situation カフェ --temp 0 --style きれいめ

# VLM の誤分類を直す
python main.py list
python main.py reclassify 2          # 同じ画像ファイルで属性を取り直し（Ollama 利用）
python main.py edit 2 --category bottoms --color ネイビー   # 手で直す（Ollama 不要）
```

`recommend` の `--temp`: `0` か未指定＝普通、`1`＝暑い、`2`＝寒い。漢字（`暑い` 等）も可。成功時は `ok` と `proposals`（最大 3 件）の JSON。

---

## コマンド早見

| コマンド | 役割 |
|----------|------|
| `python main.py add <画像パス>` | VLM で属性抽出 → DB 保存。同一内容（SHA-256）は重複登録しない |
| `python main.py add-batch <dir>` | フォルダ内の画像をまとめて登録（`--recursive` / `--limit` / `--verbose`） |
| `python main.py reclassify <id>` | DB にある `image_path` のファイルを読み直し、VLM で属性を再抽出して上書き（`file_hash` も更新） |
| `python main.py edit <id> --category …` など | 登録済み 1 件の属性を手直し。`--style` / `--season` は**カンマ区切り**（Ollama 不要） |
| `python main.py portrait <photo>` | 背景/トリミング/色味でプロフィール写真っぽく整える（ポーズ/体型は変えない） |
| `python main.py recommend` | シチュエーション等を尋ね、3 パターン＋理由を JSON 出力 |
| `python main.py preset list` | 想定ユーザー（ペルソナ）プリセットの一覧 |
| `python main.py dogfood` | プリセット全部でまとめて `recommend`（比較用JSONを出力） |
| `python main.py list` | 登録アイテム一覧（JSON） |

グローバルオプション: `--db <path>`（DB 指定）、`--ollama <URL>`、`--model <name>`（いずれも省略時は下表と既定値）。

---

## 環境変数

| 変数 | 既定 | 意味 |
|------|------|------|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama のベース URL |
| `OLLAMA_VISION_MODEL` | `qwen2.5vl:7b` | 属性抽出・解説文の既定モデル |
| `OLLAMA_TEXT_MODEL` | 未設定時は上と同じ | 解説だけ別モデルにしたい場合 |

`--model` / `--ollama` はこれらより優先されます。

---

## テスト（開発用）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
# 環境に pytest のグローバルプラグイン（ROS 等）が入っていると衝突することがあるので:
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest
```

`tests/` に SQLite と `recommender.narrate_outfit` のモックを使ったユニットテストがあります（Ollama 不要）。

---

## ローカルUI（Streamlit）

![Streamlit UI (real, Edit page)](assets/ui-real-edit.png)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
streamlit run app.py
```

UI から `add` / `list` / `edit` / `reclassify` / `recommend` を一通り触れます（内部は同じモジュールを呼び出すだけの薄いUI）。

**URL パラメータ（任意）**

- `?demo=1` — Add 画面に「デモ3点（VLMなし）」ボタンを出す（LP / 画面録画向け）
- `?no_llm=1` — `recommend` の説明文をローカル補完のみにする（Ollama 不要で高速）

**GitHub Pages 用のデモ GIF を再生成する（任意）**

`playwright` / `streamlit` / システムの `ffmpeg` が必要です。仮想環境を有効化してから実行してください。

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium
python scripts/capture_demo_gif.py
# → docs/assets/demo-ui-flow.gif
```

---

## 登録される属性（スキーマの目安）

`add` の `attributes` に含まれる想定の形:

```json
{
  "category": "tops|bottoms|outer|shoes|bag|accessory",
  "color": "日本語の短い表現",
  "style": ["タグ", "…"],
  "season": ["春", "夏", "秋", "冬"],
  "formality": 3,
  "fit": "日本語",
  "notes": "1行の補足"
}
```

`formality` は 1（カジュアル）〜5（フォーマル）の想定。

---

## レコメンドの中身（MVP）

- 候補は **tops × bottoms × shoes** の直積から生成し、シチュエーション由来のフォーマリティ、スタイル語、気温感に応じた季節の近さでスコア
- トップスとボトムの**同系色**には簡易ペナルティ
- 無難 / きれいめ / 攻めで重みを変え、**別の組**を取りに行く（枚数が少ないと同じ着合わせになることもある）
- 最後に Ollama で `summary` / `reason` / `tips` を JSON で生成

`temp_feel` が「寒い」で DB に `outer` があると、可能な範囲でアウターを 1 点割り当てます。

---

## トラブルシューティング

| 症状 | まず見る所 |
|------|------------|
| `Connection refused` / Ollama に繋がらない | `ollama serve` か OS の Ollama サービス起動、ファイアウォール |
| カテゴリが偏る（例: 全部 tops） | 無地や抽象画に近い画像は不安定。全身・衣類が写る写真向き |
| `recommend` が服の点数不足で失敗 | `list` で `tops` / `bottoms` / `shoes` の有無を確認 |
| 応答が遅い / メモリを食う | モデルサイズを下げる、同時に動かすアプリを減らす |
| `reclassify` が「画像ファイルがありません」 | `image_path` がずれている。写真をそのパスに戻すか、`edit` で直す前提でデータだけ修正 |

---

## ドッグフーディングのすすめ（おすすめ運用）

最短で価値が出る流れはこれです。

1. **まず10枚だけ登録**（トップス/ボトムス/靴が最低1枚ずつ入るように）
2. `recommend` を回して、ズレたら `reclassify` → だめなら `edit`
3. 登録を増やす（週末にまとめて）

フォルダ一括登録（例）:

```bash
python main.py add-batch ~/Pictures/wardrobe --recursive --limit 30
python main.py list
python main.py recommend
```

`--verbose` を付けると、各ファイルの結果（dedup/失敗理由）を JSON に含めます。

ペルソナ切り替えでまとめて検証（例）:

```bash
python main.py preset list
python main.py dogfood --limit 5        # LLMなしで高速（既定）
python main.py dogfood --summary --limit 5  # 比較向けサマリ（結果を軽量化）
python main.py dogfood --summary --analyze --limit 10  # 偏り検知（頻出/重複率）
python main.py dogfood --summary --diversify --limit 10  # ペルソナ間の被りを減らす
python main.py dogfood --summary --diversify --diversify-scope safe --limit 10  # 無難だけ被り回避
python main.py dogfood --llm --limit 2  # 理由文生成も回す（遅い）
python main.py recommend --preset office_clean
```

---

## 次にやると良いこと

優先度は好みで調整してください。

1. **品質** — プロンプト `prompts/*.md` のチューニング（撮影・照明でも変わるので `reclassify` と併用）
2. **拡張 UI** — `typer` + Rich、または小さな **Streamlit/Gradio** から同モジュールを import
3. **テスト** — さらに `main.py` の統合テストや、VLM 応答パースの境界ケースなど（現状は `tests/test_db.py` / `tests/test_recommender.py`）
4. **パフォーマンス** — 組み合わせ爆発時のサンプリング、カテゴリ内の事前絞り込み
5. **移動・バックアップ** — 画像の実体を `data/` 下にコピーしてパス壊れを防ぐ、DB の JSON エクスポート

**実装済み**: `edit`（手修正）、`reclassify`（VLM で取り直し）、`pytest` 用の DB / レコメンドの基本テスト（`narrate_outfit` はモック）。

---

## Star / 発見してもらうために

役に立ったら **[GitHub で Star](https://github.com/rsasaki0109/vlm-outfit-refiner)** を付けると、同じ課題を持つ人の検索結果に届きやすくなります。リポジトリの **About → Topics** に `ollama`, `vision-language-model`, `local-ai`, `sqlite`, `streamlit` などを足すのも有効です（候補は [CONTRIBUTING.md](CONTRIBUTING.md) に記載）。

**About の説明文の例（コピペ用・英語）:**  
`Local wardrobe assistant: Ollama Vision + SQLite → 3 outfit ideas (safe/clean/bold). CLI & Streamlit. No cloud APIs.`

---

## 免責

学習・自己利用向けの MVP です。モデル出力は誤ることがあります。実際の着用や購入の判断は、必ず自分の目で確認してください。
