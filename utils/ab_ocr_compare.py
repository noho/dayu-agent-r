"""显式样本的 OCR 双臂指标比较。

用法：python -m utils.ab_ocr_compare --sample-root DIR --manifest FILE --out DIR
输入为 UTF-8 JSON 非空数组，仅允许 pdf/id/kind 字段。pdf 必需，为相对 sample-root 的非空字符串，使用 / 分隔且不得含 ..；id/kind 可省略，提供时必须为非空字符串（A/B 两者必需且 id 唯一）。例子：[{"pdf":"nested/example.pdf","id":"example-1","kind":"合成对照"}]。CLI sample-root/manifest/out 相对启动 cwd 解析，清单内 pdf 始终相对 sample-root；基线为 PDF 同目录 <stem>_docling.json。同 stem 跨运行结果/缓存仍直接复用，包括错误结果；更换输入或配置须使用新的 --out，不校验缓存来源。
"""

from __future__ import annotations

import argparse
import json
import sys
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Final

from utils.analysis_sample_inputs import baseline_json_path, load_samples, require_distinct_sample_targets, resolve_analysis_input_path

_ARM_R_DIRECTORY: Final[str] = "r"
_ARM_V_DIRECTORY: Final[str] = "v"
_ARM_SUFFIX: Final[str] = ".json"


def _arm_paths(out_root: Path, stem: str) -> tuple[Path, Path]:
    """推导普通 R/V 臂的既有输入路径，不读写文件。

    :param out_root: 双臂产物根目录。
    :param stem: 已解析 PDF 的 stem。
    :returns: 依次为普通 R 臂和 V 臂 JSON 路径。
    :raises: 无；本函数只拼接路径。
    """

    name = f"{stem}{_ARM_SUFFIX}"
    return out_root / _ARM_R_DIRECTORY / name, out_root / _ARM_V_DIRECTORY / name

NUMBER_TOKEN_PATTERN = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")


def _baseline_text(baseline_path: Path) -> str:
    """抽取历史基线 json（docling 2.90 产物）的全文。

    :param baseline_path: 基线 json 路径。
    :returns: 顶层 texts 数组 text 字段的换行拼接。
    :raises Exception: 文件不存在或结构不符时由 json/索引抛出。
    """

    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    texts = payload["texts"]
    return "\n".join(str(item["text"]) for item in texts)


def _dice(left: Counter[str], right: Counter[str]) -> float:
    """计算两个数字多重集合的 Dice 交集率。

    :param left: 左侧计数。
    :param right: 右侧计数。
    :returns: ``2*|left∩right| / (|left|+|right|)``，空集并集为 0 时返回 0.0。
    :raises Exception: 不主动抛出异常。
    """

    left_total = sum(left.values())
    right_total = sum(right.values())
    if left_total + right_total == 0:
        return 0.0
    intersection = sum(min(count, right.get(token, 0)) for token, count in left.items())
    return round(2 * intersection / (left_total + right_total), 4)


def _diff_excerpts(left_text: str, right_text: str, *, max_blocks: int = 3) -> list[str]:
    """抽取双臂差异最大的文本块摘录。

    :param left_text: 左侧全文。
    :param right_text: 右侧全文。
    :param max_blocks: 最多返回的差异块数量。
    :returns: 差异摘录字符串列表（含上下文与长度信息）。
    :raises Exception: 不主动抛出异常。
    """

    matcher = SequenceMatcher(None, left_text, right_text)
    blocks = [
        opcode for opcode in matcher.get_opcodes() if opcode[0] in ("replace", "insert", "delete")
    ]
    blocks.sort(key=lambda opcode: -(opcode[4] - opcode[3]) - (opcode[2] - opcode[1]))
    excerpts: list[str] = []
    for tag, left_start, left_end, right_start, right_end in blocks[:max_blocks]:
        left_snippet = left_text[max(0, left_start - 40) : left_end + 40]
        right_snippet = right_text[max(0, right_start - 40) : right_end + 40]
        excerpts.append(
            f"[{tag} {left_end - left_start}/{right_end - right_start}]\n"
            f"  R: {left_snippet!r}\n"
            f"  V: {right_snippet!r}"
        )
    return excerpts


def main() -> int:
    """预检整份显式清单后执行原分析流程。

    :param: 无显式参数；从命令行读取 root、manifest、out 与并行参数。
    :returns: 分析完成返回 0。
    :raises SystemExit: 缺失参数或目标冲突等输入错误以 2 退出，无分析写入。
    :raises OSError, ValueError, KeyError, TypeError: 原分析读取、结构消费或结果写出错误按既有路径传播。
    """

    parser = argparse.ArgumentParser(epilog='输入为 UTF-8 JSON 非空数组，仅允许 pdf/id/kind 字段。pdf 必需，为相对 sample-root 的非空字符串，使用 / 分隔且不得含 ..；id/kind 可省略，提供时必须为非空字符串（A/B 两者必需且 id 唯一）。例子：[{"pdf":"nested/example.pdf","id":"example-1","kind":"合成对照"}]。CLI sample-root/manifest/out 相对启动 cwd 解析，清单内 pdf 始终相对 sample-root；基线为 PDF 同目录 <stem>_docling.json。同 stem 跨运行结果/缓存仍直接复用，包括错误结果；更换输入或配置须使用新的 --out，不校验缓存来源。', description="OCR 引擎 A/B 指标汇总")
    parser.add_argument("--out", required=True, help="ab_ocr_convert 产物目录")
    parser.add_argument("--sample-root", required=True, type=Path, help="样本根目录，相对启动 cwd")
    parser.add_argument("--manifest", required=True, type=Path, help="UTF-8 非空 JSON 数组清单，pdf 相对样本根")
    try:
        args = parser.parse_args()
    except SystemExit as exc:
        if exc.code == 2:
            print("A/B 参数错误：必须显式提供 --sample-root 样本根和 --manifest 清单；其余参数请查看 --help。", file=sys.stderr)
        raise
    try:
        samples = load_samples(args.sample_root, args.manifest)
        out_root = resolve_analysis_input_path(Path(args.out), "输出根")
        if not out_root.is_dir():
            raise ValueError(f"输出根必须为已存在目录: {out_root}")
        ids: set[str] = set()
        for index, sample in enumerate(samples, start=1):
            if sample.sample_id is None or sample.kind is None:
                raise ValueError(f"记录 {index} 缺少 A/B 必需 id/kind: {sample.pdf_path}")
            if sample.sample_id in ids:
                raise ValueError(f"记录 {index} A/B id 重复: {sample.sample_id} ({sample.pdf_path})")
            ids.add(sample.sample_id)
            for required_path in (baseline_json_path(sample.pdf_path), *_arm_paths(out_root, sample.pdf_path.stem)):
                if not required_path.is_file():
                    raise ValueError(f"记录 {index} 缺少必需文件: {required_path}")
        require_distinct_sample_targets(
            samples, [_arm_paths(out_root, sample.pdf_path.stem) for sample in samples],
        )
    except (OSError, ValueError) as exc:
        parser.error(f"A/B 输入错误: {exc}")

    summary_lines: list[str] = ["# OCR 引擎 A/B 实测汇总\n"]
    for sample in samples:
        sample_id = sample.sample_id
        kind = sample.kind
        assert sample_id is not None and kind is not None  # 完整预检保证报告身份为显式字符串。
        pdf_file = sample.pdf_path
        arm_r_path, arm_v_path = _arm_paths(out_root, pdf_file.stem)
        baseline_path = baseline_json_path(pdf_file)
        arm_r = json.loads(arm_r_path.read_text(encoding="utf-8"))
        arm_v = json.loads(arm_v_path.read_text(encoding="utf-8"))
        baseline_text = _baseline_text(baseline_path)
        baseline_numbers = Counter(NUMBER_TOKEN_PATTERN.findall(baseline_text))

        similarity_vr = round(SequenceMatcher(None, arm_v["full_text"], arm_r["full_text"]).ratio(), 4)
        similarity_r_base = round(SequenceMatcher(None, arm_r["full_text"], baseline_text).ratio(), 4)
        similarity_v_base = round(SequenceMatcher(None, arm_v["full_text"], baseline_text).ratio(), 4)

        counter_r = Counter(arm_r["number_counter"])
        counter_v = Counter(arm_v["number_counter"])
        dice_vr = _dice(counter_v, counter_r)
        dice_r_base = _dice(counter_r, baseline_numbers)
        dice_v_base = _dice(counter_v, baseline_numbers)

        summary_lines.append(f"## {sample_id}（{kind}，{pdf_file.name}）\n")
        summary_lines.append("| 臂 | 文本长度 | 数字 token 数 | 引擎证据 | 耗时(s) |")
        summary_lines.append("|---|---|---|---|---|")
        for arm, payload in (("R (rapidocr)", arm_r), ("V (ocrmac)", arm_v)):
            evidence = "; ".join(payload["engine_evidence"][:3]) or "(无)"
            summary_lines.append(
                f"| {arm} | {payload['text_len']} | {payload['number_total_tokens']} "
                f"| {evidence} | {payload['duration_seconds']} |"
            )
        summary_lines.append("")
        summary_lines.append(
            "| 对比 | 全文相似度 | 数字 Dice |\n"
            "|---|---|---|\n"
            f"| V vs R | {similarity_vr} | {dice_vr} |\n"
            f"| R vs 基线 | {similarity_r_base} | {dice_r_base} |\n"
            f"| V vs 基线 | {similarity_v_base} | {dice_v_base} |\n"
        )
        summary_lines.extend(_diff_excerpts(arm_r["full_text"], arm_v["full_text"]))
        summary_lines.append("")

    summary_path = out_root / "ab-summary.md"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"汇总已写 {summary_path}")
    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
