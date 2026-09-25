"""OCR 引擎 A/B 实测：单臂单样本转换脚本。

由各臂 venv 的 python 运行，走 dayu.documents.docling_runtime 的生产转换路径
（do_ocr 默认 True），输出：

- 引擎选择证据（docling/rapidocr 日志关键行）
- 全量 text item 拼接文本（按文档阅读顺序）
- 数字 token 多重集合（千分位/小数/百分比）
- 转换耗时与基本统计

文本抽取方式与 compare 脚本、基线抽取保持一致：全量 TextItem 按
``iterate_items()`` 顺序拼接（换行分隔）。

:用法: python utils/ab_ocr_convert.py --pdf <path> --arm <r|v> --out <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from collections import Counter
from pathlib import Path

NUMBER_TOKEN_PATTERN = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")


class _LogCapture(logging.Handler):
    """收集日志行的内存 handler。"""

    def __init__(self) -> None:
        """初始化行缓冲。"""
        super().__init__(level=logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """把格式化日志行追加到缓冲。

        :param record: 日志记录。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """
        self.lines.append(self.format(record))


def _extract_number_counter(text: str) -> Counter[str]:
    """抽取文本中的数字 token 多重集合。

    :param text: 目标文本。
    :returns: 数字 token 到出现次数的计数。
    :raises Exception: 不主动抛出异常。
    """

    return Counter(NUMBER_TOKEN_PATTERN.findall(text))


def _extract_full_text(document: object) -> str:
    """按阅读顺序拼接文档全部 TextItem 文本。

    :param document: DoclingDocument 实例。
    :returns: 换行分隔的全文。
    :raises Exception: 文档不支持 iterate_items 时由调用方处理。
    """

    from docling_core.types.doc.items.text import TextItem

    # docling-core 2.96 起 iterate_items 产出 (item, level) 二元组。
    iterate_items = getattr(document, "iterate_items")
    parts: list[str] = []
    for item, _level in iterate_items():
        if isinstance(item, TextItem):
            parts.append(item.text)
    return "\n".join(parts)


def main() -> int:
    """执行单臂转换并写出 JSON 产物。

    :returns: 成功返回 0，失败返回 1。
    :raises Exception: 不主动抛出，失败以退出码呈现。
    """

    parser = argparse.ArgumentParser(description="OCR 引擎 A/B 单臂转换")
    parser.add_argument("--pdf", required=True, help="样本 PDF 路径")
    parser.add_argument("--arm", required=True, choices=("r", "v"), help="臂标识")
    parser.add_argument("--out", required=True, help="产物输出目录")
    parser.add_argument("--no-ocr", action="store_true", help="关闭 OCR（do_ocr=False 对照）")
    parser.add_argument("--debug-ocr", action="store_true", help="把 docling OCR logger 提升到 DEBUG")
    args = parser.parse_args()

    sample_path = Path(args.pdf)
    out_dir = Path(args.out) / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)

    capture = _LogCapture()
    capture.setFormatter(logging.Formatter("%(name)s|%(levelname)s|%(message)s"))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(capture)
    if args.debug_ocr:
        logging.getLogger("docling.models.stages.ocr").setLevel(logging.DEBUG)

    from dayu.documents.docling_runtime import convert_pdf_bytes_with_docling

    raw_bytes = sample_path.read_bytes()
    started = time.monotonic()
    result = convert_pdf_bytes_with_docling(
        raw_bytes,
        stream_name=sample_path.name,
        do_ocr=not args.no_ocr,
    )
    duration_seconds = round(time.monotonic() - started, 1)
    document = result.document
    exported = document.export_to_dict()
    full_text = _extract_full_text(document)
    number_counter = _extract_number_counter(full_text)

    engine_evidence = [
        line
        for line in capture.lines
        if any(
            marker in line
            for marker in ("Auto OCR model selected", "ocrmac cannot be used", "RapidOCR", "Auto OCR: skipping")
        )
    ]

    payload = {
        "arm": args.arm,
        "sample_stem": sample_path.stem,
        "sample_path": str(sample_path),
        "engine_evidence": engine_evidence,
        "duration_seconds": duration_seconds,
        "text_len": len(full_text),
        "number_total_tokens": sum(number_counter.values()),
        "number_unique_tokens": len(number_counter),
        "number_counter": dict(number_counter),
        "top_level_keys": sorted(exported.keys()),
        "full_text": full_text,
    }
    variant_suffix = "-noocr" if args.no_ocr else ""
    output_path = out_dir / f"{sample_path.stem}{variant_suffix}.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{args.arm}] {sample_path.stem}: text_len={len(full_text)} "
          f"numbers={sum(number_counter.values())} duration={duration_seconds}s "
          f"engine_evidence={len(engine_evidence)} lines -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
