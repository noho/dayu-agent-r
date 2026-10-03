"""显式样本的新旧语义摘要。

digest 专属固定汇总保留 ASCII 大小写名族；检查已有链接身份，冲突在执行前拒绝。

用法：python -m utils.build_semantic_digests --sample-root DIR --manifest FILE --out DIR
输入为 UTF-8 JSON 非空数组，仅允许 pdf/id/kind 字段。pdf 必需，为相对 sample-root 的非空字符串，使用 / 分隔且不得含 ..；id/kind 可省略，提供时必须为非空字符串（A/B 两者必需且 id 唯一）。例子：[{"pdf":"nested/example.pdf","id":"example-1","kind":"合成对照"}]。CLI sample-root/manifest/out 相对启动 cwd 解析，清单内 pdf 始终相对 sample-root；基线为 PDF 同目录 <stem>_docling.json。同 stem 跨运行结果/缓存仍直接复用，包括错误结果；更换输入或配置须使用新的 --out，不校验缓存来源。
"""

from __future__ import annotations

import argparse
import json
import sys
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from typing import Final, NotRequired, Required, TypedDict, cast

from dayu.contracts.json_value import JsonValue
from dayu.documents import docling_runtime
from dayu.fins.pipelines.docling_process_converter import _is_closed_json_value
from utils.analysis_sample_inputs import (
    AnalysisSample, analysis_targets_alias, baseline_json_path, load_samples,
    require_distinct_sample_targets, resolve_analysis_input_path,
)

DATA_ROOT = Path(__file__).resolve().parents[1] / "workspace/tmp/docling-regression"
_DIGEST_MANIFEST_NAME: Final[str] = "_manifest.json"
_DIGEST_SUFFIX: Final[str] = ".json"


def _digest_path(digest_root: Path, stem: str) -> Path:
    """推导既有样本摘要写址，不解析或改写名字。

    :param digest_root: 摘要目录。
    :param stem: 已解析 PDF 的 stem。
    :returns: digest_root 下以 stem 和摘要后缀命名的路径。
    :raises: 无；本函数只拼接路径，不读写文件。
    """

    return digest_root / f"{stem}{_DIGEST_SUFFIX}"


def _require_distinct_digest_targets(samples: list[AnalysisSample], digest_root: Path) -> None:
    """完整预检样本摘要与固定汇总分离，不读取摘要或创建目录。

    :param samples: 按清单顺序已验证的样本。
    :param digest_root: 保持原布局的摘要目录。
    :returns: 全部目标通过时返回 None。
    :raises ValueError: ASCII 保留名或实际目标冲突，包含记录、PDF、两目标；
        身份检查失败补具名上下文并链接原 OSError 或 ValueError。
    """

    summary_path = digest_root / _DIGEST_MANIFEST_NAME
    for index, sample in enumerate(samples, start=1):
        target = _digest_path(digest_root, sample.pdf_path.stem)
        context = f"记录 {index} PDF {sample.pdf_path} 的摘要目标 {target} 与固定汇总产物 {summary_path}"
        if target.name.isascii() and target.name.lower() == _DIGEST_MANIFEST_NAME.lower():
            raise ValueError(f"{context} 冲突")
        try:
            alias = analysis_targets_alias(target, summary_path)
        except (OSError, ValueError) as exc:
            raise ValueError(f"{context} 无法检查固定汇总冲突: {exc}") from exc
        if alias:
            raise ValueError(f"{context} 冲突")


class DigestText(TypedDict):
    """下标消费的 text 必需，label 只由 get 消费。"""

    text: Required[JsonValue]
    label: NotRequired[JsonValue]


class DigestCell(TypedDict):
    """既有单元格文本视图。"""

    text: NotRequired[JsonValue]


class DigestTableData(TypedDict):
    """grid 的每一行都是数组，可按原表达式取长度。"""

    table_cells: NotRequired[list[DigestCell] | None]
    grid: NotRequired[list[list[JsonValue]] | None]


class DigestTable(TypedDict):
    """表格可缺省 data。"""

    data: NotRequired[DigestTableData | None]


class DigestDocument(TypedDict):
    """digest 的现有可空数组消费视图。"""

    texts: NotRequired[list[DigestText] | None]
    tables: NotRequired[list[DigestTable] | None]


class DiffBlockContent(TypedDict):
    """所有差异块由生产者写出的公共文本与长度字段。"""

    tag: str
    base_snippet: str
    new_snippet: str
    base_len: int
    new_len: int


class DiffBlock(DiffBlockContent):
    """任意差异块；仅 delete 块由生产者补入表格命中率。"""

    moved_to_table_ratio: NotRequired[float | None]


class DeleteDiffBlock(DiffBlockContent):
    """delete 块的既有字段视图；命中率必写，无数字时为 None。"""

    moved_to_table_ratio: float | None


class NumberTotals(TypedDict):
    """文本与表格两口径合计。"""

    texts: int
    tables: int


class NumberDiff(TypedDict):
    """数字 token 对比。"""

    base_total: NumberTotals
    new_total: NumberTotals
    merged_base_total: int
    merged_new_total: int
    missing_merged: list[str]
    added_merged: list[str]


class GridSize(TypedDict):
    """既有表格行列数。"""

    rows: int
    cols: int


class TableSummary(TypedDict):
    """表格规模摘要。"""

    count: int
    total_rows: int
    largest_grids: list[GridSize]


class TextLens(TypedDict):
    """新旧全文长度。"""

    new: int
    base: int


class PairedTableSummary(TypedDict):
    """新旧表格摘要。"""

    new: TableSummary
    base: TableSummary


class HeadingSummary(TypedDict):
    """新旧标题计数与样本。"""

    new_count: int
    base_count: int
    new_samples: list[str]
    base_samples: list[str]


class OrderSummary(TypedDict):
    """新旧阅读顺序样本。"""

    new: list[str]
    base: list[str]


class DigestResult(TypedDict, total=False):
    """保留异常前已写字段的 digest。"""

    stem: Required[str]
    error: str
    closed_json: bool
    text_lens: TextLens
    diff_blocks: list[DiffBlock]
    numbers: NumberDiff
    tables: PairedTableSummary
    headings: HeadingSummary
    order: OrderSummary


class CompleteDigestResult(TypedDict):
    """成功完成摘要的消费契约；字段源于 _build_one 的原成功路径。

    DigestResult 保留构建中及异常前的部分字段形状；此视图仅供原本就
    下标读取完成摘要的消费者声明输入，不实施运行时完整性校验。
    """

    stem: str
    closed_json: bool
    text_lens: TextLens
    diff_blocks: list[DiffBlock]
    numbers: NumberDiff
    tables: PairedTableSummary
    headings: HeadingSummary
    order: OrderSummary


class DigestManifest(TypedDict):
    """仅所选文件的原清单统计字段。"""

    total: int
    failed: list[str]
    total_bytes: int
    avg_bytes: int
    max_bytes: int
    stems: list[str]

NUMBER_TOKEN_PATTERN = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")
MAX_DIFF_BLOCKS = 20
MAX_NUMBER_TOKENS = 30
MAX_TABLE_SAMPLES = 5
MAX_HEADING_SAMPLES = 10
MAX_ORDER_SAMPLES = 10


def _texts_from_exported(exported: DigestDocument) -> list[DigestText]:
    """取出 exported 顶层 texts 条目列表。

    :param exported: export_to_dict 输出。
    :returns: texts 条目列表（缺省为空列表）。
    :raises Exception: 不主动抛出异常。
    """

    texts = exported.get("texts") or []
    return texts if isinstance(texts, list) else []


def _join_texts(texts: list[DigestText]) -> str:
    """拼接 texts 条目的 text 字段。

    :param texts: texts 条目列表。
    :returns: 换行分隔全文。
    :raises Exception: 不主动抛出异常。
    """

    return "\n".join(str(item.get("text", "")) for item in texts)


def _diff_blocks(new_text: str, base_text: str, new_table_cells_text: str) -> list[DiffBlock]:
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
    digested: list[DiffBlock] = []
    for tag, base_start, base_end, new_start, new_end in blocks[:MAX_DIFF_BLOCKS]:
        base_snippet = base_text[base_start:base_end]
        entry: DiffBlock = {
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


def _table_cells_text(tables: list[DigestTable]) -> str:
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


def _number_counters(texts: list[DigestText], tables: list[DigestTable]) -> tuple[Counter[str], Counter[str], Counter[str]]:
    """计算 texts-only / tables-only / merged 三口径计数。

    :param texts: texts 条目列表。
    :param tables: tables 列表。
    :returns: (texts 计数, tables 计数, merged 计数)。
    :raises KeyError, TypeError: 沿用原结构消费错误，不增加输入校验。
    """

    text_counter = Counter(NUMBER_TOKEN_PATTERN.findall(_join_texts(texts)))
    table_counter = Counter(NUMBER_TOKEN_PATTERN.findall(_table_cells_text(tables)))
    return text_counter, table_counter, text_counter + table_counter


def _number_diff(
    new_texts: list[DigestText],
    base_texts: list[DigestText],
    new_tables: list[DigestTable],
    base_tables: list[DigestTable],
) -> NumberDiff:
    """对比数字 token 多重集合，区分「移动」与「真丢失」。

    :param new_texts: 新 texts 条目列表。
    :param base_texts: 基线 texts 条目列表。
    :param new_tables: 新 tables 列表。
    :param base_tables: 基线 tables 列表。
    :returns: 多口径数字对比摘要（merged 为数字保真的正确口径）。
    :raises Exception: 不主动抛出异常。
    """

    new_texts_counter, new_tables_counter, new_merged = _number_counters(new_texts, new_tables)
    base_texts_counter, base_tables_counter, base_merged = _number_counters(base_texts, base_tables)
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


def _table_summary(tables: list[DigestTable]) -> TableSummary:
    """摘要 tables 数组的规模与最大表格结构。

    :param tables: exported tables 列表。
    :returns: 数量、总行数、最大表格 rows×cols 样本。
    :raises Exception: 不主动抛出异常。
    """

    grid_samples: list[GridSize] = []
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


def _headings(texts: list[DigestText]) -> list[str]:
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


def _order_samples(texts: list[DigestText]) -> list[str]:
    """抽样阅读顺序开头片段。

    :param texts: texts 条目列表。
    :returns: 前 N 条文本开头 40 字符。
    :raises Exception: 不主动抛出异常。
    """

    return [str(item.get("text", ""))[:40] for item in texts[:MAX_ORDER_SAMPLES]]


def _build_one(pdf_path: Path, baseline_path: Path) -> DigestResult:
    """转换单份样本并生成 digest。

    :param pdf_path: 已解析并预检的 PDF 路径。
    :param baseline_path: 该 PDF 的必需同目录基线。
    :returns: digest dict；异常时返回含 error 的 dict。
    :raises Exception: 不主动抛出，异常折叠进返回值。
    """

    stem = pdf_path.stem
    digest: DigestResult = {"stem": stem}
    try:

        raw_bytes = pdf_path.read_bytes()
        conversion = docling_runtime.convert_pdf_bytes_with_docling(raw_bytes, stream_name=pdf_path.name)
        exported = cast(DigestDocument, conversion.document.export_to_dict())
        digest["closed_json"] = isinstance(exported, dict) and _is_closed_json_value(cast(JsonValue, exported))

        new_texts = _texts_from_exported(exported)
        new_text = _join_texts(new_texts)
        new_tables = exported.get("tables") or []
        baseline = cast(DigestDocument, json.loads(baseline_path.read_text(encoding="utf-8")))
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
    """预检整份显式清单后执行原分析流程。

    :param: 无显式参数；从命令行读取 root、manifest、out 与并行参数。
    :returns: 成功返回 0，原分析失败返回 1。
    :raises SystemExit: 缺失参数或目标冲突等输入错误以 2 退出，无分析写入；
        执行后的分析或写盘错误不承诺回滚。
    :raises OSError, ValueError, KeyError, TypeError: 原分析读取、结构消费或结果写出错误按既有路径传播。
    """

    parser = argparse.ArgumentParser(epilog='输入为 UTF-8 JSON 非空数组，仅允许 pdf/id/kind 字段。pdf 必需，为相对 sample-root 的非空字符串，使用 / 分隔且不得含 ..；id/kind 可省略，提供时必须为非空字符串（A/B 两者必需且 id 唯一）。例子：[{"pdf":"nested/example.pdf","id":"example-1","kind":"合成对照"}]。CLI sample-root/manifest/out 相对启动 cwd 解析，清单内 pdf 始终相对 sample-root；基线为 PDF 同目录 <stem>_docling.json。同 stem 跨运行结果/缓存仍直接复用，包括错误结果；更换输入或配置须使用新的 --out，不校验缓存来源。' + f' digest 专属固定汇总 {_DIGEST_MANIFEST_NAME} 保留 ASCII 大小写名族；检查已有链接身份，冲突在执行前拒绝。', description="生成 2.3 语义判定 digest")
    parser.add_argument("--parallel", type=int, default=4, help="并行 worker 数")
    parser.add_argument("--sample-root", required=True, type=Path, help="样本根目录，相对启动 cwd")
    parser.add_argument("--manifest", required=True, type=Path, help="UTF-8 非空 JSON 数组清单，pdf 相对样本根")
    parser.add_argument("--out", type=Path, default=DATA_ROOT, help="产物根目录，默认仓库 workspace/tmp/docling-regression")
    try:
        args = parser.parse_args()
    except SystemExit as exc:
        if exc.code == 2:
            print("digest 参数错误：必须显式提供 --sample-root 样本根和 --manifest 清单；其余参数请查看 --help。", file=sys.stderr)
        raise

    try:
        samples = load_samples(args.sample_root, args.manifest)
        out_root = resolve_analysis_input_path(args.out, "输出根")
        if args.parallel <= 0:
            raise ValueError("--parallel 必须为正整数")
        if out_root.exists() and not out_root.is_dir():
            raise ValueError(f"输出根必须为目录: {out_root}")
        for index, sample in enumerate(samples, start=1):
            baseline = baseline_json_path(sample.pdf_path)
            if not baseline.is_file():
                raise ValueError(f"记录 {index} 缺少基线文件: {baseline}")
        digest_root = out_root / "digests"
        targets = [(_digest_path(digest_root, sample.pdf_path.stem),) for sample in samples]
        _require_distinct_digest_targets(samples, digest_root)
        require_distinct_sample_targets(samples, targets)
    except (OSError, ValueError) as exc:
        parser.error(f"digest 输入错误: {exc}")
    digest_root.mkdir(parents=True, exist_ok=True)
    todo = [s.pdf_path for s in samples if not _digest_path(digest_root, s.pdf_path.stem).exists()]
    print(f"清单 {len(samples)} 份，待生成 {len(todo)} 份")

    failed: list[str] = []
    if todo:
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            future_map = {executor.submit(_build_one, pdf, baseline_json_path(pdf)): pdf.stem for pdf in todo}
            for index, future in enumerate(as_completed(future_map), start=1):
                stem = future_map[future]
                digest = future.result()
                _digest_path(digest_root, stem).write_text(
                    json.dumps(digest, ensure_ascii=False), encoding="utf-8"
                )
                if "error" in digest:
                    failed.append(stem)
                    print(f"[{index}/{len(todo)}] FAIL {stem}: {digest['error'][:120]}")
                else:
                    print(f"[{index}/{len(todo)}] OK {stem}")

    digest_files = sorted(_digest_path(digest_root, s.pdf_path.stem) for s in samples)
    sizes = [f.stat().st_size for f in digest_files]
    manifest: DigestManifest = {
        "total": len(digest_files),
        "failed": sorted(failed),
        "total_bytes": sum(sizes),
        "avg_bytes": round(sum(sizes) / len(sizes)) if sizes else 0,
        "max_bytes": max(sizes, default=0),
        "stems": [f.stem for f in digest_files],
    }
    (digest_root / _DIGEST_MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=1))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
