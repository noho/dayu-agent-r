"""为步骤 2.3 语义判定追踪 missing token 的去向（块级证据）。

对每份 digest：

- 对 missing_merged 中每个疑似财务数字 token，定位其在 diff_blocks 中出现的位置
  （tag、块长度、moved_to_table_ratio）；
- 按「落在高 ratio delete 块（数字仍在新版表格，计数差来自重排/去重）」与
  「落在低 ratio 或 replace/insert 块（可能真丢）」分类；
- 对消化内无法定位的 token（不在 20 个限量块中）标注「块外」。

:用法: python utils/trace_missing_tokens.py <stem> [stem ...]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[1] / "workspace/tmp/docling-regression"
DIGEST_ROOT = DATA_ROOT / "digests"
NUMBER_TOKEN_PATTERN = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")
YEAR_PATTERN = re.compile(r"^(19|20)\d{2}$")


def _is_financial_number(token: str) -> bool:
    """判断数字 token 是否疑似财务数字。

    :param token: 数字 token 字符串。
    :returns: 疑似财务数字返回 True。
    :raises Exception: 不主动抛出异常。
    """

    body = token.rstrip("%")
    if YEAR_PATTERN.match(body):
        return False
    return "," in body or "." in body or len(body) > 2


def _token_block_evidence(digest: dict, token: str) -> list[str]:
    """返回 token 在 diff_blocks 中的证据行列表。

    :param digest: digest dict。
    :param token: 待追踪 token。
    :returns: 证据描述列表。
    :raises Exception: 不主动抛出异常。
    """

    evidence: list[str] = []
    for index, block in enumerate(digest["diff_blocks"]):
        base_tokens = NUMBER_TOKEN_PATTERN.findall(block["base_snippet"])
        if token in base_tokens:
            ratio = block.get("moved_to_table_ratio")
            ratio_text = "None" if ratio is None else str(ratio)
            evidence.append(
                f"块[{index}] {block['tag']} base_len={block['base_len']} ratio={ratio_text}"
            )
    return evidence


def main() -> int:
    """追踪 missing token 并分类。

    :returns: 成功返回 0。
    :raises Exception: 不主动抛出异常。
    """

    parser = argparse.ArgumentParser(description="步骤 2.3 语义判定 missing token 追踪")
    parser.add_argument("stems", nargs="+", help="stem 列表")
    args = parser.parse_args()

    for stem in args.stems:
        digest = json.loads((DIGEST_ROOT / f"{stem}.json").read_text(encoding="utf-8"))
        numbers = digest["numbers"]
        missing = numbers["missing_merged"]
        print(f"\n{'=' * 100}\nSTEM {stem}")
        print(f"merged delta = {numbers['merged_new_total'] - numbers['merged_base_total']}")
        print(f"added = {numbers['added_merged']}")
        for token in missing:
            if not _is_financial_number(token):
                continue
            evidence = _token_block_evidence(digest, token)
            if not evidence:
                print(f"  {token!r}: 块外（不在限量 20 块内）")
            for line in evidence:
                print(f"  {token!r}: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
