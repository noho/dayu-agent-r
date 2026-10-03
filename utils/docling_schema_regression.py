"""显式样本的 Docling schema 回归。

用法：python -m utils.docling_schema_regression --sample-root DIR --manifest FILE --out DIR
输入为 UTF-8 JSON 非空数组，仅允许 pdf/id/kind 字段。pdf 必需，为相对 sample-root 的非空字符串，使用 / 分隔且不得含 ..；id/kind 可省略，提供时必须为非空字符串（A/B 两者必需且 id 唯一）。例子：[{"pdf":"nested/example.pdf","id":"example-1","kind":"合成对照"}]。CLI sample-root/manifest/out 相对启动 cwd 解析，清单内 pdf 始终相对 sample-root；基线为 PDF 同目录 <stem>_docling.json。同 stem 跨运行结果/缓存仍直接复用，包括错误结果；更换输入或配置须使用新的 --out，不校验缓存来源。
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Final, NotRequired, Required, TypedDict, TypeAlias, cast

from dayu.contracts.json_value import JsonValue
from dayu.documents import docling_runtime
from docling_core.types.doc.document import DoclingDocument
from dayu.fins.pipelines.docling_process_converter import _is_closed_json_value
from utils.analysis_sample_inputs import baseline_json_path, load_samples, require_distinct_sample_targets, resolve_analysis_input_path

DEFAULT_OUT_ROOT = Path(__file__).resolve().parents[1] / "workspace/tmp/docling-regression"
_RESULT_DIRECTORY: Final[str] = "results"
_RESULT_SUFFIX: Final[str] = ".json"


def _schema_result_path(out_root: Path, stem: str) -> Path:
    """推导既有 schema 结果路径，不读写文件。

    :param out_root: 输出根目录。
    :param stem: 已解析 PDF 的 stem。
    :returns: results 子目录下的样本 JSON 路径。
    :raises: 无；本函数只拼接路径。
    """

    return out_root / _RESULT_DIRECTORY / f"{stem}{_RESULT_SUFFIX}"


class SchemaDocument(TypedDict):
    """schema 有效输入视图；cast 不验证内容。"""

    texts: NotRequired[list[JsonValue]]
    tables: NotRequired[list[JsonValue]]
    pictures: NotRequired[list[JsonValue]]
    version: NotRequired[JsonValue]


class ItemCounts(TypedDict):
    """schema 三种条目计数。"""

    texts: int
    tables: int
    pictures: int


class SchemaSummaryFields(TypedDict, total=False):
    """可包含异常前已写字段的单样本结果。"""

    stem: Required[str]
    closed_json: bool
    new_parseable: bool
    new_parse_error: str
    base_parse_error: str
    new_top_keys: list[str]
    base_top_keys: list[str]
    base_version: JsonValue
    new_counts: ItemCounts
    base_counts: ItemCounts
    base_parseable: bool | None
    top_key_diff: list[str] | None


class SchemaPartialSummary(SchemaSummaryFields, total=False):
    """构建中以及异常前可能写入的部分字段。"""

    error: str
    new_version: JsonValue


class SchemaSuccessSummary(SchemaSummaryFields):
    """无 error 的既有完成结果必有 new_version（值可为 null）。"""

    new_version: Required[JsonValue]


class SchemaErrorSummary(SchemaSummaryFields):
    """error 必需，保留异常前可能写入的 version。"""

    error: Required[str]
    new_version: NotRequired[JsonValue]


SchemaSummary: TypeAlias = SchemaSuccessSummary | SchemaErrorSummary


class SchemaAggregate(TypedDict):
    """既有磁盘汇总字段。"""

    total: int
    error_count: int
    failed_stems: list[str]
    closed_json_fail: int
    new_parse_fail: int
    base_parse_fail: int
    top_key_diff_count: int
    version_same_count: int
    identical_count: int
    new_version_distribution: dict[str, int]



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


def _process_one(pdf_path: Path, baseline_path: Path, out_root: Path) -> SchemaSummary:
    """转换单份显式样本并按原规则对比基线。

    :param pdf_path: 已解析并预检的 PDF 路径。
    :param baseline_path: 同目录基线路径，可以不存在。
    :param out_root: 已建立 results 子目录的输出根。
    :returns: 完成结果联合，分析异常保留异常前字段并加入 error。
    :raises OSError: 结果写盘失败；分析和转换异常按原规则折叠到 error。
    """

    stem = pdf_path.stem
    result_path = _schema_result_path(out_root, stem)
    summary: SchemaPartialSummary = {"stem": stem}

    try:

        raw_bytes = pdf_path.read_bytes()
        conversion = docling_runtime.convert_pdf_bytes_with_docling(raw_bytes, stream_name=pdf_path.name)
        exported = cast(SchemaDocument, conversion.document.export_to_dict())

        summary["closed_json"] = isinstance(exported, dict) and _is_closed_json_value(cast(JsonValue, exported))

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
            baseline = cast(SchemaDocument, json.loads(baseline_path.read_text(encoding="utf-8")))
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
    return cast(SchemaSummary, summary)


def main() -> int:
    """预检整份显式清单后执行原分析流程。

    :param: 无显式参数；从命令行读取 root、manifest、out 与并行参数。
    :returns: 成功返回 0，原分析失败返回 1。
    :raises SystemExit: 缺失参数或目标冲突等输入错误以 2 退出，无分析写入。
    :raises OSError, ValueError, KeyError, TypeError: 原分析读取、结构消费或结果写出错误按既有路径传播。
    """

    parser = argparse.ArgumentParser(epilog='输入为 UTF-8 JSON 非空数组，仅允许 pdf/id/kind 字段。pdf 必需，为相对 sample-root 的非空字符串，使用 / 分隔且不得含 ..；id/kind 可省略，提供时必须为非空字符串（A/B 两者必需且 id 唯一）。例子：[{"pdf":"nested/example.pdf","id":"example-1","kind":"合成对照"}]。CLI sample-root/manifest/out 相对启动 cwd 解析，清单内 pdf 始终相对 sample-root；基线为 PDF 同目录 <stem>_docling.json。同 stem 跨运行结果/缓存仍直接复用，包括错误结果；更换输入或配置须使用新的 --out，不校验缓存来源。', description="docling 2.127 schema 层样本回归")
    parser.add_argument("--parallel", type=int, default=2, help="并行 worker 数")
    parser.add_argument("--out", default=str(DEFAULT_OUT_ROOT), help="产物根目录")
    parser.add_argument("--sample-root", required=True, type=Path, help="样本根目录，相对启动 cwd")
    parser.add_argument("--manifest", required=True, type=Path, help="UTF-8 非空 JSON 数组清单，pdf 相对样本根")
    try:
        args = parser.parse_args()
    except SystemExit as exc:
        if exc.code == 2:
            print("schema 参数错误：必须显式提供 --sample-root 样本根和 --manifest 清单；其余参数请查看 --help。", file=sys.stderr)
        raise

    try:
        samples = load_samples(args.sample_root, args.manifest)
        out_root = resolve_analysis_input_path(Path(args.out), "输出根")
        if args.parallel <= 0:
            raise ValueError("--parallel 必须为正整数")
        if out_root.exists() and not out_root.is_dir():
            raise ValueError(f"输出根必须为目录: {out_root}")
        for index, sample in enumerate(samples, start=1):
            baseline = baseline_json_path(sample.pdf_path)
            if baseline.exists() and not baseline.is_file():
                raise ValueError(f"记录 {index} 基线路径不是文件: {baseline}")
        require_distinct_sample_targets(
            samples, [(_schema_result_path(out_root, sample.pdf_path.stem),) for sample in samples],
        )
    except (OSError, ValueError) as exc:
        parser.error(f"schema 输入错误: {exc}")
    (out_root / _RESULT_DIRECTORY).mkdir(parents=True, exist_ok=True)
    pdf_paths = [sample.pdf_path for sample in samples]
    todo = [
        pdf_path
        for pdf_path in pdf_paths
        if not _schema_result_path(out_root, pdf_path.stem).exists()
    ]
    print(f"样本总数 {len(pdf_paths)}，待处理 {len(todo)}（已完成 {len(pdf_paths) - len(todo)}）")

    summaries: list[SchemaSummary] = []
    failed: list[str] = []
    if todo:
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            future_map = {
                executor.submit(_process_one, pdf_path, baseline_json_path(pdf_path), out_root): pdf_path
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

    # 汇总只覆盖本次清单，保留所选结果的续跑统计口径。
    all_summaries: list[SchemaSummary] = []
    for result_path in sorted(_schema_result_path(out_root, path.stem) for path in pdf_paths):
        all_summaries.append(cast(SchemaSummary, json.loads(result_path.read_text(encoding="utf-8"))))

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

    summary_payload: SchemaAggregate = {
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
