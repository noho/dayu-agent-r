"""OCR 引擎 A/B 实测：双臂指标对比汇总。

读取 ``ab_ocr_convert`` 产出的双臂 JSON 与样本库历史基线 ``*_docling.json``，
计算并输出：

- Arm V 与 Arm R 的全文相似度（difflib.SequenceMatcher ratio）
- 各臂与历史基线（docling 2.90 产物）的全文相似度
- 数字 token 多重集合对比：数量、交集率（Dice 系数
  ``2*|A∩B| / (|A|+|B|)``，多重集交集取逐 token 最小计数）
- 双臂差异摘录（最长 3 段）

:用法: python utils/ab_ocr_compare.py --out <dir>
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

NUMBER_TOKEN_PATTERN = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")

# 样本清单：5 份扫描件/图重财报（按文本层从少到多）+ 1 份有文本层对照。
SAMPLES: tuple[dict[str, str], ...] = (
    {
        "id": "s01",
        "pdf": "/Users/leo/Documents/_2我的投资/workspace/portfolio/9961/filings/id-9f7441a73aeb87c14f52b1fb3b43e4c3a71e8f1bec2465d2a9ab260e86cc3f2a/fil_cn_9c9acd3c777494515d34d6fd3e40b5b76c3433a2.pdf",
        "kind": "扫描件",
    },
    {
        "id": "s02",
        "pdf": "/Users/leo/Documents/_2我的投资/workspace/portfolio/0300/filings/id-3ffcf0e1f056d9d2c8ae50a64df9911441edbadb1056dcbafc6abf27b2f7a7e2/fil_cn_5b5a4c6678e8796c94668db2b2ed41e70b8c3c66.pdf",
        "kind": "扫描件",
    },
    {
        "id": "s03",
        "pdf": "/Users/leo/Documents/_2我的投资/workspace/portfolio/000333/filings/id-1784a4ab329e8271250c3fd976a53ff95fe0d6e5534e984debc3136b59457fb0/fil_cn_821200d15a9b0646f57f004804427e4476c66af5.pdf",
        "kind": "扫描件",
    },
    {
        "id": "s04",
        "pdf": "/Users/leo/Documents/_2我的投资/workspace/portfolio/000333/filings/id-7907766b68d41cbcc8c11088b818859a4546f0cae472f6a54de1cb3a75ceccee/fil_cn_f151c6b703769c8efa62974b24e47c8a302c1d1a.pdf",
        "kind": "扫描件",
    },
    {
        "id": "s05",
        "pdf": "/Users/leo/Documents/_2我的投资/workspace/portfolio/9898/filings/id-7b72197b118f313d9b17c2ec77bc466996cbf63e211c232d25518f0f702681cc/fil_cn_98a5a55ef92a4865cb6fd113b92edefbd7805798.pdf",
        "kind": "扫描件",
    },
    {
        "id": "c01",
        "pdf": "/Users/leo/Documents/_2我的投资/workspace/portfolio/1179/filings/id-0b5397ad8e67880411d69f965b87597fcf07ef595612bc3f4b532cff34070779/fil_cn_11502836c8ff8c5a6bf5831012c6d8207f3989dd.pdf",
        "kind": "文本层对照",
    },
)


def _baseline_json_path(pdf_path: str) -> Path:
    """推导样本对应的历史基线 json 路径。

    :param pdf_path: 样本 PDF 路径。
    :returns: 同目录 ``fil_cn_<hash>_docling.json`` 路径。
    :raises Exception: 路径不存在时由调用方发现。
    """

    pdf_file = Path(pdf_path)
    return pdf_file.with_name(f"{pdf_file.stem}_docling.json")


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
    """汇总双臂指标并写 ``ab-summary.md``。

    :returns: 成功返回 0，缺产物或基线时返回 1。
    :raises Exception: 不主动抛出，失败以退出码呈现。
    """

    parser = argparse.ArgumentParser(description="OCR 引擎 A/B 指标汇总")
    parser.add_argument("--out", required=True, help="ab_ocr_convert 产物目录")
    args = parser.parse_args()
    out_root = Path(args.out)

    summary_lines: list[str] = ["# OCR 引擎 A/B 实测汇总\n"]
    for sample in SAMPLES:
        sample_id = sample["id"]
        pdf_file = Path(sample["pdf"])
        stem = pdf_file.stem
        arm_r_path = out_root / "r" / f"{stem}.json"
        arm_v_path = out_root / "v" / f"{stem}.json"
        baseline_path = _baseline_json_path(sample["pdf"])
        if not arm_r_path.exists() or not arm_v_path.exists():
            print(f"[{sample_id}] 缺臂产物，跳过: {arm_r_path} / {arm_v_path}")
            continue
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

        summary_lines.append(f"## {sample_id}（{sample['kind']}，{pdf_file.name}）\n")
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
