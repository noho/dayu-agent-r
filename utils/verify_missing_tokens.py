"""显式样本的 missing/added 数字验证。

用法：python -m utils.verify_missing_tokens --sample-root DIR --manifest FILE --out DIR
输入为 UTF-8 JSON 非空数组，仅允许 pdf/id/kind 字段。pdf 必需，为相对 sample-root 的非空字符串，使用 / 分隔且不得含 ..；id/kind 可省略，提供时必须为非空字符串（A/B 两者必需且 id 唯一）。例子：[{"pdf":"nested/example.pdf","id":"example-1","kind":"合成对照"}]。CLI sample-root/manifest/out 相对启动 cwd 解析，清单内 pdf 始终相对 sample-root；基线为 PDF 同目录 <stem>_docling.json。同 stem 跨运行结果/缓存仍直接复用，包括错误结果；更换输入或配置须使用新的 --out，不校验缓存来源。
"""

from __future__ import annotations

import argparse
import json
import sys
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Final, NotRequired, Required, TypedDict, cast

from dayu.contracts.json_value import JsonValue
from dayu.documents import docling_runtime
from utils.analysis_sample_inputs import baseline_json_path, load_samples, require_distinct_sample_targets, resolve_analysis_input_path

DATA_ROOT = Path(__file__).resolve().parents[1] / "workspace/tmp/docling-regression"
_DIGEST_DIRECTORY: Final[str] = "digests"
_CACHE_DIRECTORY: Final[str] = "verify-cache"
_JSON_SUFFIX: Final[str] = ".json"


def _verify_paths(data_root: Path, stem: str) -> tuple[Path, Path]:
    """推导既有 digest 读址和 cache 读写址，不读写文件。

    :param data_root: 明确的数据根目录。
    :param stem: 已解析 PDF 的 stem。
    :returns: 依次为 digest 路径和 verify-cache 路径。
    :raises: 无；本函数只拼接路径。
    """

    name = f"{stem}{_JSON_SUFFIX}"
    return data_root / _DIGEST_DIRECTORY / name, data_root / _CACHE_DIRECTORY / name


class TokenText(TypedDict):
    """verify 仅 get 消费文本。"""

    text: NotRequired[JsonValue]


class TokenCell(TypedDict):
    """verify 仅 get 消费单元格文本。"""

    text: NotRequired[JsonValue]


class TokenTableData(TypedDict):
    """verify 的表格单元格视图。"""

    table_cells: NotRequired[list[TokenCell] | None]


class TokenTable(TypedDict):
    """verify 的可空表格数据。"""

    data: NotRequired[TokenTableData | None]


class TokenDocument(TypedDict):
    """verify 的导出与缓存视图。"""

    texts: NotRequired[list[TokenText] | None]
    tables: NotRequired[list[TokenTable] | None]


class VerifyNumbers(TypedDict):
    """verify 以下标读取的两个必需数组。"""

    missing_merged: Required[list[str]]
    added_merged: Required[list[str]]


class VerifyDigest(TypedDict):
    """verify 以下标读取的必需 numbers。"""

    numbers: Required[VerifyNumbers]


class VerifyResult(TypedDict):
    """verify 既有返回字段。"""

    stem: str
    new_texts: str
    missing: list[str]
    added: list[str]
    base_count: dict[str, int]
    new_count: dict[str, int]
    added_new_count: dict[str, int]
    added_base_count: dict[str, int]

NUMBER_TOKEN_PATTERN = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")


def _merge_counters(exported: TokenDocument) -> Counter[str]:
    """按 merged 口径计数数字 token。

    :param exported: export_to_dict 输出。
    :returns: merged 计数。
    :raises OSError, ValueError, KeyError, TypeError: 读取、转换或原结构消费错误直接传播。
    """

    texts = exported.get("texts") or []
    tables = exported.get("tables") or []
    text_counter = Counter(NUMBER_TOKEN_PATTERN.findall("\n".join(str(t.get("text", "")) for t in texts)))
    table_counter = Counter(
        NUMBER_TOKEN_PATTERN.findall(
            "\n".join(str(c.get("text", "")) for t in tables for c in ((t.get("data") or {}).get("table_cells") or []))
        )
    )
    return text_counter + table_counter


def _verify_one(pdf_path: Path, baseline_path: Path, data_root: Path) -> VerifyResult:
    """验证单份样本的 missing/added token。

    :param pdf_path: 已解析并预检的 PDF 路径。
    :param baseline_path: 该 PDF 的必需同目录基线。
    :param data_root: digest 和 verify-cache 的明确根目录。
    :returns: 验证结果 dict。
    :raises OSError, ValueError, KeyError, TypeError: 读取、转换或原结构消费错误直接传播。
    """

    stem = pdf_path.stem
    digest_path, cache_path = _verify_paths(data_root, stem)
    if cache_path.exists():
        exported = cast(TokenDocument, json.loads(cache_path.read_text(encoding="utf-8")))
    else:
        raw_bytes = pdf_path.read_bytes()
        conversion = docling_runtime.convert_pdf_bytes_with_docling(raw_bytes, stream_name=pdf_path.name)
        exported = cast(TokenDocument, conversion.document.export_to_dict())
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(exported, ensure_ascii=False), encoding="utf-8")

    new_merged = _merge_counters(exported)
    new_texts = "\n".join(str(t.get("text", "")) for t in (exported.get("texts") or []))

    baseline = cast(TokenDocument, json.loads(baseline_path.read_text(encoding="utf-8")))
    base_merged = _merge_counters(baseline)

    digest = cast(VerifyDigest, json.loads(digest_path.read_text(encoding="utf-8")))
    missing = digest["numbers"]["missing_merged"]
    added = digest["numbers"]["added_merged"]
    return {
        "stem": stem,
        "base_count": {t: base_merged[t] for t in missing},
        "new_count": {t: new_merged[t] for t in missing},
        "added_new_count": {t: new_merged[t] for t in added},
        "added_base_count": {t: base_merged[t] for t in added},
        "new_texts": new_texts,
        "missing": missing,
        "added": added,
    }


def _context(new_texts: str, token: str, max_hits: int = 3) -> list[str]:
    """在新版 texts 全文中找 token 的上下文片段。

    :param new_texts: 新版 texts 全文。
    :param token: 待定位 token。
    :param max_hits: 最多返回的命中数。
    :returns: 上下文片段列表。
    :raises Exception: 不主动抛出异常。
    """

    hits: list[str] = []
    for match in re.finditer(re.escape(token), new_texts):
        start = max(0, match.start() - 45)
        end = min(len(new_texts), match.end() + 45)
        hits.append(new_texts[start:end].replace("\n", "⏎"))
        if len(hits) >= max_hits:
            break
    return hits


def main() -> int:
    """预检整份显式清单后执行原分析流程。

    :param: 无显式参数；从命令行读取 root、manifest、out 与并行参数。
    :returns: 分析完成返回 0。
    :raises SystemExit: 缺失参数或目标冲突等输入错误以 2 退出，无分析写入。
    :raises OSError, ValueError, KeyError, TypeError: 原分析读取、结构消费或结果写出错误按既有路径传播。
    """

    parser = argparse.ArgumentParser(epilog='输入为 UTF-8 JSON 非空数组，仅允许 pdf/id/kind 字段。pdf 必需，为相对 sample-root 的非空字符串，使用 / 分隔且不得含 ..；id/kind 可省略，提供时必须为非空字符串（A/B 两者必需且 id 唯一）。例子：[{"pdf":"nested/example.pdf","id":"example-1","kind":"合成对照"}]。CLI sample-root/manifest/out 相对启动 cwd 解析，清单内 pdf 始终相对 sample-root；基线为 PDF 同目录 <stem>_docling.json。同 stem 跨运行结果/缓存仍直接复用，包括错误结果；更换输入或配置须使用新的 --out，不校验缓存来源。', description="步骤 2.3 语义判定 token 级全文验证")
    parser.add_argument("--workers", type=int, default=2, help="并行 worker 数")
    parser.add_argument("--sample-root", required=True, type=Path, help="样本根目录，相对启动 cwd")
    parser.add_argument("--manifest", required=True, type=Path, help="UTF-8 非空 JSON 数组清单，pdf 相对样本根")
    parser.add_argument("--out", type=Path, default=DATA_ROOT, help="digest/cache 根目录，默认仓库 workspace/tmp/docling-regression")
    try:
        args = parser.parse_args()
    except SystemExit as exc:
        if exc.code == 2:
            print("verify 参数错误：必须显式提供 --sample-root 样本根和 --manifest 清单；其余参数请查看 --help。", file=sys.stderr)
        raise

    try:
        samples = load_samples(args.sample_root, args.manifest)
        data_root = resolve_analysis_input_path(args.out, "输出根")
        if args.workers <= 0:
            raise ValueError("--workers 必须为正整数")
        if data_root.exists() and not data_root.is_dir():
            raise ValueError(f"输出根必须为目录: {data_root}")
        for index, sample in enumerate(samples, start=1):
            for required_path in (baseline_json_path(sample.pdf_path), _verify_paths(data_root, sample.pdf_path.stem)[0]):
                if not required_path.is_file():
                    raise ValueError(f"记录 {index} 缺少必需文件: {required_path}")
        require_distinct_sample_targets(
            samples, [_verify_paths(data_root, sample.pdf_path.stem) for sample in samples],
        )
    except (OSError, ValueError) as exc:
        parser.error(f"verify 输入错误: {exc}")

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(_verify_one, s.pdf_path, baseline_json_path(s.pdf_path), data_root): s.pdf_path.stem for s in samples}
        for future in as_completed(future_map):
            stem = future_map[future]
            result = future.result()
            print(f"\n{'=' * 100}\nSTEM {stem}")
            print("missing token（token: base 计数 → new 计数）:")
            for token in result["missing"]:
                new_count = result["new_count"].get(token, 0)
                mark = "★真丢" if new_count == 0 else "  (仍存在)"
                print(f"  {token!r}: {result['base_count'].get(token, 0)} → {new_count}{mark}")
            print("added token（token: base 计数 → new 计数）:")
            for token in result["added"]:
                print(f"  {token!r}: {result['added_base_count'].get(token, 0)} → {result['added_new_count'].get(token, 0)}")
                for ctx in _context(result["new_texts"], token):
                    print(f"     ctx: {ctx!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
