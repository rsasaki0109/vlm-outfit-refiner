# Contributing

Issue / PR は日本語・英語どちらでも歓迎です。

## 開発セットアップ

```bash
git clone https://github.com/rsasaki0109/vlm-outfit-refiner.git
cd vlm-outfit-refiner
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest
```

Ollama はユニットテストでは不要です（外部呼び出しはモック）。

## PR のガイドライン

- 変更理由が README や Issue で追えると助かります。
- 機能追加は可能なら `tests/` にテストを追加（レコメンド・DB・パース周りは特に）。
- 大きな変更は Issue で先に相談してもらえると、方向性のズレが減ります。

## GitHub リポジトリの「Topics」候補（任意）

発見性向上のため、About にトピックを足す例です。

`ollama`, `vision-language-model`, `local-ai`, `sqlite`, `streamlit`, `wardrobe`, `outfit`, `python`

Fork した場合は、README や Issue テンプレ内の **`rsasaki0109` を自分のユーザー名に置き換える**と、バッジやリンクが正しくなります。
