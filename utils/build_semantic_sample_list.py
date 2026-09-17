"""构建步骤 2.3 语义层判定样本清单（约 100 份）。

分层规则（按方案 2.3）：

1. 全部扫描件（文本层密度最低 31 份）；
2. 每公司至少 2 份（按 texts delta 绝对值降序补足）；
3. 表格密度分层：基线 tables>=10 的样本中按 texts delta 绝对值取 43 份；
4. texts delta 绝对值最大的样本优先纳入，合计约 100 份。

:用法: python utils/build_semantic_sample_list.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_OUT = (
    Path(__file__).resolve().parents[1] / "workspace/tmp/docling-regression/samples-2.3.json"
)
DATA_ROOT = DEFAULT_OUT.parent
TARGET_TOTAL = 100
SCANNED_COUNT = 31
TABLE_STRATUM_COUNT = 43
PER_TICKER_MIN = 2
DELTA_TOP_COUNT = 25


def _load_layers() -> tuple[dict[str, dict], dict[str, dict]]:
    """读取文本层密度与回归结果两层数据。

    :returns: (stem 到密度行, stem 到回归摘要) 二元组。
    :raises Exception: 数据文件缺失时由 Path 抛出。
    """

    density_rows = json.loads((DATA_ROOT / "pdf-textlayers.json").read_text(encoding="utf-8"))
    layer_map = {row["stem"]: row for row in density_rows}
    summary_map: dict[str, dict] = {}
    for result_path in (DATA_ROOT / "results").glob("*.json"):
        summary = json.loads(result_path.read_text(encoding="utf-8"))
        if "error" in summary or "new_counts" not in summary:
            continue
        texts_delta = summary["new_counts"]["texts"] - summary["base_counts"]["texts"]
        summary_map[summary["stem"]] = {**summary, "texts_delta": texts_delta}
    return layer_map, summary_map


def main() -> int:
    """生成清单并写 JSON。

    :returns: 成功返回 0。
    :raises Exception: 不主动抛出。
    """

    parser = argparse.ArgumentParser(description="构建 2.3 语义层样本清单")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="清单输出路径")
    args = parser.parse_args()

    layer_map, summary_map = _load_layers()
    picked: dict[str, str] = {}

    # 1. 全部扫描件：密度最低 31 份。
    for stem in sorted(layer_map, key=lambda s: layer_map[s]["density"])[:SCANNED_COUNT]:
        if stem in summary_map:
            picked[stem] = "scanned"

    # 2. 每公司至少 2 份（|texts delta| 降序）。
    by_ticker: dict[str, list[str]] = {}
    for stem, summary in summary_map.items():
        ticker = layer_map[stem]["ticker"]
        by_ticker.setdefault(ticker, []).append(stem)
    for ticker, stems in by_ticker.items():
        stems.sort(key=lambda s: -abs(summary_map[s]["texts_delta"]))
        for stem in stems[:PER_TICKER_MIN]:
            picked.setdefault(stem, "ticker-quota")

    # 3. 表格密度分层：基线 tables>=10 按 |delta| 取 43 份。
    table_rich = [
        stem for stem in summary_map if summary_map[stem]["base_counts"]["tables"] >= 10
    ]
    table_rich.sort(key=lambda s: -abs(summary_map[s]["texts_delta"]))
    for stem in table_rich[:TABLE_STRATUM_COUNT]:
        picked.setdefault(stem, "table-stratum")

    # 4. delta top 补足：|texts delta| 最大的 25 份。
    delta_ranked = sorted(summary_map, key=lambda s: -abs(summary_map[s]["texts_delta"]))
    for stem in delta_ranked[:DELTA_TOP_COUNT]:
        picked.setdefault(stem, "delta-top")

    # 5. 若不足 100，按 |delta| 顺序继续补足。
    for stem in delta_ranked:
        if len(picked) >= TARGET_TOTAL:
            break
        picked.setdefault(stem, "delta-fill")

    samples = [
        {
            "stem": stem,
            "ticker": layer_map[stem]["ticker"],
            "source": source,
            "pages": layer_map[stem]["pages"],
            "density": layer_map[stem]["density"],
            "texts_delta": summary_map[stem]["texts_delta"],
            "base_counts": summary_map[stem]["base_counts"],
            "new_counts": summary_map[stem]["new_counts"],
        }
        for stem, source in picked.items()
    ]
    samples.sort(key=lambda s: (s["ticker"], s["stem"]))
    Path(args.out).write_text(json.dumps(samples, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import Counter

    source_dist = Counter(s["source"] for s in samples)
    ticker_count = len({s["ticker"] for s in samples})
    print(f"清单样本数: {len(samples)}（ticker 数 {ticker_count}）")
    print("来源分布:", dict(source_dist))
    print("已写:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
