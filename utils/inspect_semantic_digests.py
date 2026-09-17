"""为步骤 2.3 语义判定详读指定 digest（供 LLM 判定修复/退化/中性）。

对每份样本输出：

- 数字保真：missing/added_merged 全列表，并对 missing token 做「变形配对」检查
  （去逗号/去百分号后在 added 中出现 → 只是格式变化，不是丢失）；
- diff_blocks：每块一行摘要（tag/长度/moved_to_table_ratio）+ 裁剪后的片段；
- 表格结构与阅读顺序对比。

:用法: python utils/inspect_semantic_digests.py <stem> [stem ...] [--snippet 220]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[1] / "workspace/tmp/docling-regression"
DIGEST_ROOT = DATA_ROOT / "digests"


def _normalize(token: str) -> str:
    """规范化数字 token（去千分位逗号、去百分号），用于变形配对。

    :param token: 数字 token 字符串。
    :returns: 规范化后的字符串。
    :raises Exception: 不主动抛出异常。
    """

    return token.replace(",", "").replace("%", "")


def _pair_missing_with_added(missing: list[str], added: list[str]) -> tuple[list[str], list[str]]:
    """将 missing token 分为「变形配对」与「未配对」两类。

    :param missing: 缺失 token 列表。
    :param added: 新增 token 列表。
    :returns: (变形配对的 missing token, 未配对的 missing token)。
    :raises Exception: 不主动抛出异常。
    """

    added_norms = {_normalize(t) for t in added}
    paired = [t for t in missing if _normalize(t) in added_norms]
    unpaired = [t for t in missing if _normalize(t) not in added_norms]
    return paired, unpaired


def _print_diff_blocks(digest: dict, snippet_chars: int) -> None:
    """打印 diff_blocks 摘要。

    :param digest: digest dict。
    :param snippet_chars: 每块片段裁剪字符数。
    :returns: 无。
    :raises Exception: 不主动抛出异常。
    """

    print(f"\n--- diff_blocks（{len(digest['diff_blocks'])} 块） ---")
    for index, block in enumerate(digest["diff_blocks"]):
        ratio = block.get("moved_to_table_ratio")
        ratio_text = "None" if ratio is None else str(ratio)
        print(
            f"[{index}] {block['tag']} base_len={block['base_len']} new_len={block['new_len']} "
            f"moved_to_table_ratio={ratio_text}"
        )
        print(f"  base: {block['base_snippet'][:snippet_chars]!r}")
        print(f"  new : {block['new_snippet'][:snippet_chars]!r}")


def _print_numbers(digest: dict) -> None:
    """打印数字保真指标与变形配对结果。

    :param digest: digest dict。
    :returns: 无。
    :raises Exception: 不主动抛出异常。
    """

    numbers = digest["numbers"]
    missing = numbers["missing_merged"]
    added = numbers["added_merged"]
    paired, unpaired = _pair_missing_with_added(missing, added)
    print(
        f"merged_base={numbers['merged_base_total']} merged_new={numbers['merged_new_total']} "
        f"(delta={numbers['merged_new_total'] - numbers['merged_base_total']})"
    )
    print(f"missing({len(missing)}) = {missing}")
    print(f"added({len(added)}) = {added}")
    print(f"missing 中变形配对({len(paired)}) = {paired}")
    print(f"missing 中未配对({len(unpaired)}) = {unpaired}")


def _print_structure(digest: dict) -> None:
    """打印表格与阅读顺序对比。

    :param digest: digest dict。
    :returns: 无。
    :raises Exception: 不主动抛出异常。
    """

    tables = digest["tables"]
    print(f"tables.new = {tables['new']}")
    print(f"tables.base = {tables['base']}")
    headings = digest["headings"]
    print(
        f"headings: new_count={headings['new_count']} base_count={headings['base_count']} "
        f"new_samples={headings['new_samples']} base_samples={headings['base_samples']}"
    )
    order = digest["order"]
    print(f"order.new = {order['new']}")
    print(f"order.base = {order['base']}")
    print(f"text_lens = {digest['text_lens']}")


def main() -> int:
    """详读指定样本并打印判定证据。

    :returns: 成功返回 0。
    :raises Exception: 不主动抛出异常。
    """

    parser = argparse.ArgumentParser(description="步骤 2.3 语义判定详读")
    parser.add_argument("stems", nargs="+", help="stem 列表")
    parser.add_argument("--snippet", type=int, default=220, help="diff 块片段裁剪字符数")
    parser.add_argument("--no-blocks", action="store_true", help="跳过 diff_blocks 打印")
    args = parser.parse_args()

    for stem in args.stems:
        digest = json.loads((DIGEST_ROOT / f"{stem}.json").read_text(encoding="utf-8"))
        print(f"\n{'=' * 100}\nSTEM {stem}")
        _print_numbers(digest)
        if not args.no_blocks:
            _print_diff_blocks(digest, args.snippet)
        _print_structure(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
