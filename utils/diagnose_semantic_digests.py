"""为步骤 2.3 语义判定做全量分诊（抽取关键指标 + 自动可疑度排序）。

对 ``digests/`` 下指定奇偶索引路的 digest 做文档级聚合指标抽取：

- 数字保真：missing/added_merged、merged 净差（最高优先）；
- 表格结构：count / total_rows / largest_grids 变化；
- heading 层级：new_count vs base_count；
- 文本完整性：delete/insert/replace 块数量与长度、低 moved_to_table_ratio 的 delete 块；
- 阅读顺序：order 抽样前 10 条的差异度。

自动可疑规则（只做候选排序，最终判定需人工详读 diff_blocks 原文）：

- 缺失数字中疑似财务数字（长度>2 且非年份，或含千分位/小数点）个数 > 0；
- merged 净差 <= -3；
- heading 全丢或数量减半；
- 最大表格 grid 面积退化（new 最大 rows*cols < base 最大 rows*cols）；
- 低 moved_to_table_ratio（明确 < 0.5）的 delete 块累计长度大。

:用法: python utils/diagnose_semantic_digests.py [--parity odd|even] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[1] / "workspace/tmp/docling-regression"
YEAR_PATTERN = re.compile(r"^(19|20)\d{2}$")
ORDER_SAMPLES = 10


def _is_financial_number(token: str) -> bool:
    """判断数字 token 是否疑似财务数字（排除纯页码/年份/编号）。

    :param token: 数字 token 字符串。
    :returns: 疑似财务数字返回 True。
    :raises Exception: 不主动抛出异常。
    """

    body = token.rstrip("%")
    if YEAR_PATTERN.match(body):
        return False
    if "," in body or "." in body:
        return True
    return len(body) > 2


def _order_similarity(new_order: list[str], base_order: list[str]) -> float:
    """计算阅读顺序抽样的相似度。

    :param new_order: 新阅读顺序抽样。
    :param base_order: 基线阅读顺序抽样。
    :returns: 0~1 相似度。
    :raises Exception: 不主动抛出异常。
    """

    if not new_order and not base_order:
        return 1.0
    return SequenceMatcher(None, base_order, new_order).ratio()


def _diagnose_one(digest: dict) -> dict:
    """对单份 digest 抽取诊断指标。

    :param digest: digest dict。
    :returns: 诊断指标 dict。
    :raises Exception: 不主动抛出异常。
    """

    numbers = digest["numbers"]
    missing = numbers["missing_merged"]
    added = numbers["added_merged"]
    financial_missing = [t for t in missing if _is_financial_number(t)]
    financial_added = [t for t in added if _is_financial_number(t)]

    tables = digest["tables"]
    new_grids = tables["new"]["largest_grids"]
    base_grids = tables["base"]["largest_grids"]
    new_max_area = (new_grids[0]["rows"] * new_grids[0]["cols"]) if new_grids else 0
    base_max_area = (base_grids[0]["rows"] * base_grids[0]["cols"]) if base_grids else 0

    del_blocks = [b for b in digest["diff_blocks"] if b["tag"] == "delete"]
    ins_blocks = [b for b in digest["diff_blocks"] if b["tag"] == "insert"]
    repl_blocks = [b for b in digest["diff_blocks"] if b["tag"] == "replace"]
    low_moved = [
        b
        for b in del_blocks
        if b.get("moved_to_table_ratio") is not None and b["moved_to_table_ratio"] < 0.5
    ]
    no_token_del = [b for b in del_blocks if b.get("moved_to_table_ratio") is None]

    headings = digest["headings"]
    return {
        "stem": digest["stem"],
        "missing_n": len(missing),
        "missing_fin_n": len(financial_missing),
        "missing_fin": financial_missing[:10],
        "added_n": len(added),
        "added_fin_n": len(financial_added),
        "merged_delta": numbers["merged_new_total"] - numbers["merged_base_total"],
        "texts_delta": numbers["new_total"]["texts"] - numbers["base_total"]["texts"],
        "tbl_count_delta": tables["new"]["count"] - tables["base"]["count"],
        "tbl_rows_delta": tables["new"]["total_rows"] - tables["base"]["total_rows"],
        "grid_max_delta": new_max_area - base_max_area,
        "heading_delta": headings["new_count"] - headings["base_count"],
        "heading_new_count": headings["new_count"],
        "heading_base_count": headings["base_count"],
        "del_blocks": len(del_blocks),
        "del_len": sum(b["base_len"] for b in del_blocks),
        "del_low_moved_n": len(low_moved),
        "del_low_moved_len": sum(b["base_len"] for b in low_moved),
        "del_no_token_n": len(no_token_del),
        "ins_blocks": len(ins_blocks),
        "ins_len": sum(b["new_len"] for b in ins_blocks),
        "repl_blocks": len(repl_blocks),
        "textlen_delta": digest["text_lens"]["new"] - digest["text_lens"]["base"],
        "order_sim": round(_order_similarity(digest["order"]["new"], digest["order"]["base"]), 3),
    }


def _suspect_score(row: dict) -> tuple[float, list[str]]:
    """计算可疑度（降序）与命中规则说明。

    :param row: 诊断指标 dict。
    :returns: (可疑度, 命中规则说明)。
    :raises Exception: 不主动抛出异常。
    """

    score = 0.0
    reasons: list[str] = []
    if row["missing_fin_n"] > 0:
        score += 4.0 + min(row["missing_fin_n"], 5)
        reasons.append(f"疑似财务数字缺失 {row['missing_fin_n']} 个: {row['missing_fin'][:5]}")
    if row["missing_n"] - row["missing_fin_n"] > 3:
        score += 1.0
        reasons.append(f"非财务数字缺失 {row['missing_n'] - row['missing_fin_n']} 个")
    if row["merged_delta"] <= -3:
        score += 2.0 + min(-row["merged_delta"] / 3.0, 3.0)
        reasons.append(f"merged 净差 {row['merged_delta']}")
    if row["grid_max_delta"] < 0:
        score += 2.0
        reasons.append(f"最大表格面积退化 {row['grid_max_delta']}")
    if row["heading_base_count"] > 0 and row["heading_new_count"] == 0:
        score += 2.0
        reasons.append(f"heading 全丢 ({row['heading_base_count']}→0)")
    elif row["heading_base_count"] > 0 and row["heading_new_count"] < row["heading_base_count"] * 0.5:
        score += 1.0
        reasons.append(f"heading 减半 ({row['heading_base_count']}→{row['heading_new_count']})")
    if row["del_low_moved_len"] > 200:
        score += 1.0 + min(row["del_low_moved_len"] / 2000.0, 2.0)
        reasons.append(f"低 moved_to_table 的 delete 长度 {row['del_low_moved_len']}")
    if row["order_sim"] < 0.3:
        score += 1.0
        reasons.append(f"阅读顺序相似度 {row['order_sim']}")
    return score, reasons


def main() -> int:
    """全量分诊并输出 TSV 与可疑排序。

    :returns: 成功返回 0。
    :raises Exception: 不主动抛出。
    """

    parser = argparse.ArgumentParser(description="步骤 2.3 语义判定全量分诊")
    parser.add_argument(
        "--parity",
        choices=("odd", "even"),
        default="odd",
        help="奇数索引路（odd，默认）或偶数索引路（even）。含 _manifest.json 排序后 0-based 奇数位 = stems[0::2]。",
    )
    parser.add_argument("--out", type=str, default=None, help="TSV 输出路径（默认打印到 stdout）")
    parser.add_argument(
        "--from-index",
        type=int,
        default=0,
        help="stems 0-based 起始索引（配合 --parity 做子范围，如 even+51 = 索引 52 起的偶数位）",
    )
    args = parser.parse_args()

    manifest = json.loads((DATA_ROOT / "digests" / "_manifest.json").read_text(encoding="utf-8"))
    stems = manifest["stems"]
    mine = stems[0::2] if args.parity == "odd" else stems[1::2]
    mine = [stem for stem in mine if stems.index(stem) >= args.from_index]
    rows = []
    for stem in mine:
        digest = json.loads((DATA_ROOT / "digests" / f"{stem}.json").read_text(encoding="utf-8"))
        rows.append(_diagnose_one(digest))

    scored = [(row, *_suspect_score(row)) for row in rows]
    scored.sort(key=lambda item: -item[1])

    header = "\t".join(
        [
            "stem", "missing_n", "missing_fin_n", "merged_delta", "texts_delta", "tbl_cnt_delta",
            "tbl_rows_delta", "grid_max_delta", "head_delta(head_new/base)", "del_n/len",
            "del_low_moved_n/len", "ins_n/len", "repl_n", "textlen_delta", "order_sim", "suspect",
        ]
    )
    lines = [header]
    for row, score, reasons in scored:
        lines.append(
            "\t".join(
                [
                    row["stem"],
                    str(row["missing_n"]),
                    str(row["missing_fin_n"]),
                    str(row["merged_delta"]),
                    str(row["texts_delta"]),
                    str(row["tbl_count_delta"]),
                    str(row["tbl_rows_delta"]),
                    str(row["grid_max_delta"]),
                    f"{row['heading_delta']}({row['heading_new_count']}/{row['heading_base_count']})",
                    f"{row['del_blocks']}/{row['del_len']}",
                    f"{row['del_low_moved_n']}/{row['del_low_moved_len']}",
                    f"{row['ins_blocks']}/{row['ins_len']}",
                    str(row["repl_blocks"]),
                    str(row["textlen_delta"]),
                    str(row["order_sim"]),
                    f"{score:.1f}",
                ]
            )
        )
    output = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
        print(f"TSV 已写 {args.out}")
    else:
        print(output)
    print(f"\n=== 可疑排序（{len(mine)} 份） ===")
    for row, score, reasons in scored:
        if score <= 0:
            break
        print(f"[{score:.1f}] {row['stem']} :: {'; '.join(reasons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
