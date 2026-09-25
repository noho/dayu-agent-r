"""docling 2.127 升级 schema 层样本回归。

对样本库（只读）每份 ``fil_cn_*.pdf`` 执行生产转换路径并与其历史基线
``fil_cn_*_docling.json``（docling 2.90 产物）逐项对比：

- closed-JSON 校验（复用 ``_is_closed_json_value`` 真源）
- 新产出可被 ``DoclingDocument.model_validate_json`` 解析
- 历史基线可被 docling-core 2.96 的 ``load_from_json`` 解析（本层核心断言）
- 顶层 key 集合 diff、texts/tables/pictures 计数与 schema version 对比

产物写 ``workspace/tmp/docling-regression/``；结果按样本落盘，重跑自动跳过
已完成样本，可分批续跑。

:用法: python utils/docling_schema_regression.py [--limit N] [--samples stem1 stem2 ...]
       [--parallel N] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

SAMPLE_LIBRARY_ROOT = Path("/Users/leo/Documents/_2我的投资/workspace/portfolio")
DEFAULT_OUT_ROOT = Path(__file__).resolve().parents[1] / "workspace/tmp/docling-regression"
TOP_LEVEL_KEY_CANONICAL: tuple[str, ...] = (
    "body",
    "form_items",
    "furniture",
    "groups",
    "key_value_items",
    "name",
    "origin",
    "pages",
    "pictures",
    "schema_name",
    "tables",
    "texts",
    "version",
)


def _process_one(pdf_path_str: str, out_root_str: str) -> dict:
    """转换单份样本并对比基线，返回结果摘要 dict。

    :param pdf_path_str: 样本 PDF 绝对路径字符串。
    :param out_root_str: 产物根目录字符串。
    :returns: 含逐项校验结果与计数的摘要；异常时返回 ``error`` 字段摘要。
    :raises Exception: 不主动抛出，异常折叠进返回值。
    """

    pdf_path = Path(pdf_path_str)
    out_root = Path(out_root_str)
    stem = pdf_path.stem
    result_path = out_root / "results" / f"{stem}.json"
    baseline_path = pdf_path.with_name(f"{stem}_docling.json")
    summary: dict = {"stem": stem}

    try:
        from dayu.fins.pipelines.docling_process_converter import _is_closed_json_value
        from dayu.documents.docling_runtime import convert_pdf_bytes_with_docling
        from docling_core.types.doc.document import DoclingDocument

        raw_bytes = pdf_path.read_bytes()
        conversion = convert_pdf_bytes_with_docling(raw_bytes, stream_name=pdf_path.name)
        exported = conversion.document.export_to_dict()

        summary["closed_json"] = isinstance(exported, dict) and _is_closed_json_value(exported)

        try:
            DoclingDocument.model_validate_json(json.dumps(exported, ensure_ascii=False))
            summary["new_parseable"] = True
        except Exception as exc:
            summary["new_parseable"] = False
            summary["new_parse_error"] = f"{type(exc).__name__}: {exc}"

        summary["new_top_keys"] = sorted(exported.keys())
        summary["new_version"] = exported.get("version")
        summary["new_counts"] = {
            "texts": len(exported.get("texts", [])),
            "tables": len(exported.get("tables", [])),
            "pictures": len(exported.get("pictures", [])),
        }

        if baseline_path.exists():
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            summary["base_top_keys"] = sorted(baseline.keys())
            summary["base_version"] = baseline.get("version")
            summary["base_counts"] = {
                "texts": len(baseline.get("texts", [])),
                "tables": len(baseline.get("tables", [])),
                "pictures": len(baseline.get("pictures", [])),
            }
            summary["top_key_diff"] = sorted(set(summary["base_top_keys"]) ^ set(summary["new_top_keys"]))
            try:
                DoclingDocument.load_from_json(str(baseline_path))
                summary["base_parseable"] = True
            except Exception as exc:
                summary["base_parseable"] = False
                summary["base_parse_error"] = f"{type(exc).__name__}: {exc}"
        else:
            summary["base_parseable"] = None
            summary["top_key_diff"] = None
    except Exception:
        summary["error"] = traceback.format_exc(limit=3)

    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _collect_pdf_paths(samples: list[str] | None, limit: int | None) -> list[Path]:
    """收集样本 PDF 路径（只读枚举样本库）。

    :param samples: 指定 stem 列表；为 ``None`` 时枚举全部。
    :param limit: 全量模式下最多处理的样本数；``None`` 为不限制。
    :returns: 有序 PDF 路径列表。
    :raises Exception: 样本库不可读时由 Path 抛出。
    """

    if samples:
        paths = [
            next(SAMPLE_LIBRARY_ROOT.rglob(f"{stem}.pdf"))
            for stem in samples
        ]
        return paths
    paths = sorted(SAMPLE_LIBRARY_ROOT.rglob("fil_cn_*.pdf"))
    return paths[:limit]


def main() -> int:
    """执行回归并打印汇总。

    :returns: 全部成功返回 0，存在失败样本返回 1。
    :raises Exception: 不主动抛出。
    """

    parser = argparse.ArgumentParser(description="docling 2.127 schema 层样本回归")
    parser.add_argument("--samples", nargs="*", default=None, help="指定 stem 列表（2.1 冒烟用）")
    parser.add_argument("--limit", type=int, default=None, help="全量模式最多处理的样本数")
    parser.add_argument("--parallel", type=int, default=2, help="并行 worker 数")
    parser.add_argument("--out", default=str(DEFAULT_OUT_ROOT), help="产物根目录")
    args = parser.parse_args()

    out_root = Path(args.out)
    (out_root / "results").mkdir(parents=True, exist_ok=True)

    pdf_paths = _collect_pdf_paths(args.samples, args.limit)
    todo = [
        pdf_path
        for pdf_path in pdf_paths
        if not (out_root / "results" / f"{pdf_path.stem}.json").exists()
    ]
    print(f"样本总数 {len(pdf_paths)}，待处理 {len(todo)}（已完成 {len(pdf_paths) - len(todo)}）")

    summaries: list[dict] = []
    failed: list[str] = []
    if todo:
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            future_map = {
                executor.submit(_process_one, str(pdf_path), str(out_root)): pdf_path
                for pdf_path in todo
            }
            for index, future in enumerate(as_completed(future_map), start=1):
                pdf_path = future_map[future]
                summary = future.result()
                summaries.append(summary)
                if "error" in summary:
                    failed.append(pdf_path.stem)
                    print(f"[{index}/{len(todo)}] FAIL {pdf_path.stem}")
                else:
                    print(f"[{index}/{len(todo)}] OK {pdf_path.stem} "
                          f"new={summary.get('new_counts')} base={summary.get('base_counts')}")

    # 汇总：合并落盘结果（含续跑历史）统计。
    all_summaries: list[dict] = []
    for result_path in sorted((out_root / "results").glob("*.json")):
        all_summaries.append(json.loads(result_path.read_text(encoding="utf-8")))

    error_count = sum(1 for s in all_summaries if "error" in s)
    closed_fail = sum(1 for s in all_summaries if "error" not in s and not s.get("closed_json"))
    new_parse_fail = sum(1 for s in all_summaries if "error" not in s and not s.get("new_parseable"))
    base_parse_fail = sum(
        1 for s in all_summaries if "error" not in s and s.get("base_parseable") is False
    )
    key_diff_count = sum(1 for s in all_summaries if "error" not in s and s.get("top_key_diff"))
    version_same = sum(
        1 for s in all_summaries
        if "error" not in s and s.get("new_version") == s.get("base_version")
    )
    identical = sum(
        1 for s in all_summaries
        if "error" not in s
        and not s.get("top_key_diff")
        and s.get("new_version") == s.get("base_version")
        and s.get("new_counts") == s.get("base_counts")
    )
    version_values: dict[str, int] = {}
    for s in all_summaries:
        if "error" not in s and s.get("new_version") is not None:
            version_values[str(s["new_version"])] = version_values.get(str(s["new_version"]), 0) + 1

    summary_payload = {
        "total": len(all_summaries),
        "error_count": error_count,
        "failed_stems": sorted(failed),
        "closed_json_fail": closed_fail,
        "new_parse_fail": new_parse_fail,
        "base_parse_fail": base_parse_fail,
        "top_key_diff_count": key_diff_count,
        "version_same_count": version_same,
        "identical_count": identical,
        "new_version_distribution": version_values,
    }
    (out_root / "summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"=== 汇总（当前落盘 {summary_payload['total']} 份）===")
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))
    return 1 if (error_count or closed_fail or new_parse_fail) else 0


if __name__ == "__main__":
    raise SystemExit(main())
