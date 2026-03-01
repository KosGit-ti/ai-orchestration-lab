# ノートブック

研究で使用する Jupyter ノートブックを格納する。

## 使い方

```bash
uv sync --extra dev
uv run jupyter lab
```

## 注意

- ノートブックはあくまで探索・可視化用。実装コードは `experiments/` または `src/` に配置する。
- コミット前にセル出力をクリアすること。
