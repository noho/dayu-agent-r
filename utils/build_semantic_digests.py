"""为步骤 2.3 语义判定生成紧凑 digest（供 LLM 判定，不含原始大 JSON）。

对 ``samples-2.3.json`` 清单内每份样本：

- 重新执行生产转换（do_ocr=True），抽取新全文；
- 与历史基线（docling 2.90 产物）对比生成：
  - 文本 diff 摘要（新增/删除/修改片段限量采样，带前后文）；
  - 数字 token 多重集合对比（缺失/新增的关键数字限量）；
  - 表格数量与结构变化摘要（新/旧最大表格的 rows×cols）；
  - heading 层级对比（section-header/title 序列数量与前 10 条）；
  - 阅读顺序抽样（新/旧 texts 前 10 条开头片段）。

产物写 ``workspace/tmp/docling-regression/digests/<stem>.json``，重跑跳过已完成项。

:用法: python utils/build_semantic_digests.py [--parallel N]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[1] / "workspace/tmp/docling-regression"
SAMPLE_LIBRARY_ROOT = Path("/Users/leo/Documents/_2我的投资/workspace/portfolio")
NUMBER_TOKEN_PATTERN = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")
MAX_DIFF_BLOCKS = 20
MAX_NUMBER_TOKENS = 30
MAX_TABLE_SAMPLES = 5
MAX_HEADING_SAMPLES = 10
MAX_ORDER_SAMPLES = 10


def _texts_from_exported(exported: dict) -> list[dict]:
    """取出 exported 顶层 texts 条目列表。

    :param exported: export_to_dict 输出。
    :returns: texts 条目列表（缺省为空列表）。
    :raises Exception: 不主动抛出异常。
    """

    texts = exported.get("texts") or []
    return texts if isinstance(texts, list) else []


def _join_texts(texts: list[dict]) -> str:
    """拼接 texts 条目的 text 字段。

    :param texts: texts 条目列表。
    :returns: 换行分隔全文。
    :raises Exception: 不主动抛出异常。
    """

    return "\n".join(str(item.get("text", "")) for item in texts)


def _diff_blocks(new_text: str, base_text: str, new_table_cells_text: str) -> list[dict]:
    """生成限量文本 diff 摘要块（delete 块附带 moved_to_table 命中率）。

    :param new_text: 新全文（texts 口径）。
    :param base_text: 基线全文（texts 口径）。
    :param new_table_cells_text: 新版表格单元格拼接文本。
    :returns: 按块长度降序、限量采样的差异块摘要。
    :raises Exception: 不主动抛出异常。
    """

    matcher = SequenceMatcher(None, base_text, new_text)
    blocks = [
        opcode for opcode in matcher.get_opcodes() if opcode[0] in ("replace", "insert", "delete")
    ]
    blocks.sort(key=lambda opcode: -(opcode[4] - opcode[3]) - (opcode[2] - opcode[1]))
    digested: list[dict] = []
    for tag, base_start, base_end, new_start, new_end in blocks[:MAX_DIFF_BLOCKS]:
        base_snippet = base_text[base_start:base_end]
        entry: dict = {
            "tag": tag,
            "base_snippet": base_text[max(0, base_start - 50) : base_end + 50],
            "new_snippet": new_text[max(0, new_start - 50) : new_end + 50],
            "base_len": base_end - base_start,
            "new_len": new_end - new_start,
        }
        if tag == "delete":
            # moved_to_table：delete 块内数字 token 在新版表格单元格中的命中率，
            # 用于区分「内容移入表格」与「真丢失」。
            block_tokens = NUMBER_TOKEN_PATTERN.findall(base_snippet)
            if block_tokens:
                table_tokens = NUMBER_TOKEN_PATTERN.findall(new_table_cells_text)
                hits = sum(1 for token in block_tokens if token in table_tokens)
                entry["moved_to_table_ratio"] = round(hits / len(block_tokens), 3)
            else:
                entry["moved_to_table_ratio"] = None
        digested.append(entry)
    return digested


def _table_cells_text(tables: list[dict]) -> str:
    """拼接 tables 全部单元格文本。

    :param tables: exported tables 列表。
    :returns: 换行分隔的单元格文本。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = []
    for table in tables:
        table_data = table.get("data") or {}
        table_cells = table_data.get("table_cells") or []
        for cell in table_cells:
            parts.append(str(cell.get("text", "")))
    return "\n".join(parts)


def _number_diff(
    new_texts: list[dict],
    base_texts: list[dict],
    new_tables: list[dict],
    base_tables: list[dict],
) -> dict:
    """对比数字 token 多重集合，区分「移动」与「真丢失」。

    :param new_texts: 新 texts 条目列表。
    :param base_texts: 基线 texts 条目列表。
    :param new_tables: 新 tables 列表。
    :param base_tables: 基线 tables 列表。
    :returns: 多口径数字对比摘要（merged 为数字保真的正确口径）。
    :raises Exception: 不主动抛出异常。
    """

    def counters(texts: list[dict], tables: list[dict]) -> tuple[Counter[str], Counter[str], Counter[str]]:
        """计算 texts-only / tables-only / merged 三口径计数。

        :param texts: texts 条目列表。
        :param tables: tables 列表。
        :returns: (texts 计数, tables 计数, merged 计数)。
        :raises Exception: 不主动抛出异常。
        """

        text_counter = Counter(NUMBER_TOKEN_PATTERN.findall(_join_texts(texts)))
        table_counter = Counter(NUMBER_TOKEN_PATTERN.findall(_table_cells_text(tables)))
        return text_counter, table_counter, text_counter + table_counter

    new_texts_counter, new_tables_counter, new_merged = counters(new_texts, new_tables)
    base_texts_counter, base_tables_counter, base_merged = counters(base_texts, base_tables)
    missing_merged = base_merged - new_merged
    added_merged = new_merged - base_merged
    return {
        "base_total": {"texts": sum(base_texts_counter.values()), "tables": sum(base_tables_counter.values())},
        "new_total": {"texts": sum(new_texts_counter.values()), "tables": sum(new_tables_counter.values())},
        "merged_base_total": sum(base_merged.values()),
        "merged_new_total": sum(new_merged.values()),
        "missing_merged": [token for token, _ in missing_merged.most_common(MAX_NUMBER_TOKENS)],
        "added_merged": [token for token, _ in added_merged.most_common(MAX_NUMBER_TOKENS)],
    }


def _table_summary(tables: list[dict]) -> dict:
    """摘要 tables 数组的规模与最大表格结构。

    :param tables: exported tables 列表。
    :returns: 数量、总行数、最大表格 rows×cols 样本。
    :raises Exception: 不主动抛出异常。
    """

    grid_samples: list[dict] = []
    total_rows = 0
    for table in tables:
        grid = (table.get("data") or {}).get("grid") or []
        rows = len(grid)
        cols = len(grid[0]) if grid else 0
        total_rows += rows
        grid_samples.append({"rows": rows, "cols": cols})
    grid_samples.sort(key=lambda item: -item["rows"])
    return {
        "count": len(tables),
        "total_rows": total_rows,
        "largest_grids": grid_samples[:MAX_TABLE_SAMPLES],
    }


def _headings(texts: list[dict]) -> list[str]:
    """抽取标题序列（label 为 section-header 或 title）。

    :param texts: texts 条目列表。
    :returns: 标题文本列表。
    :raises Exception: 不主动抛出异常。
    """

    return [
        str(item["text"])
        for item in texts
        if str(item.get("label", "")) in ("section-header", "title")
    ]


def _order_samples(texts: list[dict]) -> list[str]:
    """抽样阅读顺序开头片段。

    :param texts: texts 条目列表。
    :returns: 前 N 条文本开头 40 字符。
    :raises Exception: 不主动抛出异常。
    """

    return [str(item.get("text", ""))[:40] for item in texts[:MAX_ORDER_SAMPLES]]


def _build_one(stem: str) -> dict:
    """转换单份样本并生成 digest。

    :param stem: 样本 stem（fil_cn_<hash>）。
    :returns: digest dict；异常时返回含 error 的 dict。
    :raises Exception: 不主动抛出，异常折叠进返回值。
    """

    digest: dict = {"stem": stem}
    try:
        from dayu.documents.docling_runtime import convert_pdf_bytes_with_docling
        from dayu.fins.pipelines.docling_process_converter import _is_closed_json_value

        pdf_path = next(SAMPLE_LIBRARY_ROOT.rglob(f"{stem}.pdf"))
        baseline_path = pdf_path.with_name(f"{stem}_docling.json")
        raw_bytes = pdf_path.read_bytes()
        conversion = convert_pdf_bytes_with_docling(raw_bytes, stream_name=pdf_path.name)
        exported = conversion.document.export_to_dict()
        digest["closed_json"] = isinstance(exported, dict) and _is_closed_json_value(exported)

        new_texts = _texts_from_exported(exported)
        new_text = _join_texts(new_texts)
        new_tables = exported.get("tables") or []
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        base_texts = _texts_from_exported(baseline)
        base_text = _join_texts(base_texts)
        base_tables = baseline.get("tables") or []

        digest["text_lens"] = {"new": len(new_text), "base": len(base_text)}
        digest["diff_blocks"] = _diff_blocks(new_text, base_text, _table_cells_text(new_tables))
        digest["numbers"] = _number_diff(new_texts, base_texts, new_tables, base_tables)
        digest["tables"] = {
            "new": _table_summary(exported.get("tables") or []),
            "base": _table_summary(baseline.get("tables") or []),
        }
        new_headings = _headings(new_texts)
        base_headings = _headings(base_texts)
        digest["headings"] = {
            "new_count": len(new_headings),
            "base_count": len(base_headings),
            "new_samples": new_headings[:MAX_HEADING_SAMPLES],
            "base_samples": base_headings[:MAX_HEADING_SAMPLES],
        }
        digest["order"] = {
            "new": _order_samples(new_texts),
            "base": _order_samples(base_texts),
        }
    except Exception as exc:
        digest["error"] = f"{type(exc).__name__}: {exc}"
    return digest


def main() -> int:
    """批量生成 digest 并写清单文件。

    :returns: 成功返回 0，存在失败项返回 1。
    :raises Exception: 不主动抛出。
    """

    parser = argparse.ArgumentParser(description="生成 2.3 语义判定 digest")
    parser.add_argument("--parallel", type=int, default=4, help="并行 worker 数")
    args = parser.parse_args()

    samples = json.loads((DATA_ROOT / "samples-2.3.json").read_text(encoding="utf-8"))
    digest_root = DATA_ROOT / "digests"
    digest_root.mkdir(parents=True, exist_ok=True)
    todo = [s["stem"] for s in samples if not (digest_root / f"{s['stem']}.json").exists()]
    print(f"清单 {len(samples)} 份，待生成 {len(todo)} 份")

    failed: list[str] = []
    if todo:
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            future_map = {executor.submit(_build_one, stem): stem for stem in todo}
            for index, future in enumerate(as_completed(future_map), start=1):
                stem = future_map[future]
                digest = future.result()
                (digest_root / f"{stem}.json").write_text(
                    json.dumps(digest, ensure_ascii=False), encoding="utf-8"
                )
                if "error" in digest:
                    failed.append(stem)
                    print(f"[{index}/{len(todo)}] FAIL {stem}: {digest['error'][:120]}")
                else:
                    print(f"[{index}/{len(todo)}] OK {stem}")

    digest_files = sorted(digest_root.glob("*.json"))
    sizes = [f.stat().st_size for f in digest_files]
    manifest = {
        "total": len(digest_files),
        "failed": sorted(failed),
        "total_bytes": sum(sizes),
        "avg_bytes": round(sum(sizes) / len(sizes)) if sizes else 0,
        "max_bytes": max(sizes, default=0),
        "stems": [f.stem for f in digest_files],
    }
    (digest_root / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=1))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
