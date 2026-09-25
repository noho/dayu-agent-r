"""把 PDF 指定页栅格化为 PNG，供目视复核使用。

背景：本机 Read 工具无法直读 PDF —— 当前 API 端点会把 ``document`` 内容块静默
替换为字面文本 ``[Unsupported Document]`` 并返回 HTTP 200（与 poppler 是否安装、
session 是否重启均无关）。因此任何目视复核都必须先经本脚本把页面转成 PNG。

输出文件名形如 ``<prefix>_p03.png``，页码固定两位补零、按页码升序返回，便于批处理引用。

:用法:
    python utils/rasterize_pdf.py <pdf>                          # 全部页，300 DPI
    python utils/rasterize_pdf.py <pdf> --pages 3                # 单页
    python utils/rasterize_pdf.py <pdf> --pages 3,7-9            # 逗号 + 区间混用
    python utils/rasterize_pdf.py <pdf> --pages 3 --out-dir /tmp/pages --dpi 150
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_DPI = 300
PAGE_LIST_SEPARATOR = ","
PAGE_RANGE_SEPARATOR = "-"
PDFINFO_PAGES_PREFIX = "Pages:"


class RasterizeError(RuntimeError):
    """栅格化流程中的可预期错误（依赖缺失、输入非法、渲染失败）。"""


def _require_binary(name: str) -> str:
    """查找外部可执行文件。

    :param name: 可执行文件名（如 ``pdftoppm``）。
    :returns: 可执行文件的绝对路径。
    :raises RasterizeError: 未找到该可执行文件时抛出。
    """

    found = shutil.which(name)
    if found is None:
        raise RasterizeError(f"未找到 {name}，请先安装 poppler（macOS: brew install poppler）")
    return found


def _pdf_page_count(pdf_path: Path) -> int:
    """读取 PDF 总页数。

    :param pdf_path: PDF 文件路径。
    :returns: PDF 总页数。
    :raises RasterizeError: 文件不存在、pdfinfo 执行失败或输出无法解析时抛出。
    """

    if not pdf_path.is_file():
        raise RasterizeError(f"源 PDF 不存在: {pdf_path}")

    pdfinfo = _require_binary("pdfinfo")
    completed = subprocess.run(
        [pdfinfo, str(pdf_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RasterizeError(f"pdfinfo 读取失败: {completed.stderr.strip()}")

    for line in completed.stdout.splitlines():
        if line.startswith(PDFINFO_PAGES_PREFIX):
            raw = line[len(PDFINFO_PAGES_PREFIX) :].strip()
            if raw.isdigit():
                return int(raw)
    raise RasterizeError("pdfinfo 输出中未找到页数字段")


def _parse_pages(spec: str, page_count: int) -> list[int]:
    """解析页码表达式并做越界校验。

    支持单个页码、逗号列表与闭区间混用，例如 ``"3"``、``"3,7"``、``"3-5"``、``"1,3-5"``。

    :param spec: 页码表达式字符串。
    :param page_count: PDF 总页数，用于越界校验。
    :returns: 去重并升序排列的页码列表（1 起）。
    :raises RasterizeError: 表达式非法或无页码越界时抛出。
    """

    pages: set[int] = set()
    for chunk in spec.split(PAGE_LIST_SEPARATOR):
        piece = chunk.strip()
        if not piece:
            continue
        if PAGE_RANGE_SEPARATOR in piece:
            start_raw, _, end_raw = piece.partition(PAGE_RANGE_SEPARATOR)
            if not start_raw.strip().isdigit() or not end_raw.strip().isdigit():
                raise RasterizeError(f"非法页码范围: {piece!r}")
            start, end = int(start_raw), int(end_raw)
            if start > end:
                raise RasterizeError(f"页码区间起点大于终点: {piece!r}")
            pages.update(range(start, end + 1))
        else:
            if not piece.isdigit():
                raise RasterizeError(f"非法页码: {piece!r}")
            pages.add(int(piece))

    if not pages:
        raise RasterizeError("页码表达式未解析出任何页码")

    out_of_range = sorted(page for page in pages if page < 1 or page > page_count)
    if out_of_range:
        raise RasterizeError(f"页码越界（PDF 共 {page_count} 页）: {out_of_range}")
    return sorted(pages)


def rasterize_pdf(
    pdf_path: Path,
    out_dir: Path,
    pages: Sequence[int] | None = None,
    dpi: int = DEFAULT_DPI,
    prefix: str | None = None,
) -> list[Path]:
    """把 PDF 指定页栅格化为 PNG。

    :param pdf_path: 源 PDF 路径。
    :param out_dir: 输出目录，不存在时自动创建。
    :param pages: 待栅格化页码（1 起，含端点）；``None`` 表示全部页。
    :param dpi: 渲染分辨率，默认 300；目视复核建议不低于 300。
    :param prefix: 输出文件名前缀，``None`` 表示取源文件名 stem。
    :returns: 已写出的 PNG 路径列表，按页码升序。
    :raises RasterizeError: 源文件缺失、依赖缺失、页码非法或渲染失败时抛出。
    """

    if dpi <= 0:
        raise RasterizeError(f"dpi 必须为正整数: {dpi}")

    pdftoppm = _require_binary("pdftoppm")
    page_count = _pdf_page_count(pdf_path)

    targets = list(range(1, page_count + 1)) if pages is None else sorted(set(pages))
    if not targets:
        raise RasterizeError("未指定任何页码")
    out_of_range = [page for page in targets if page < 1 or page > page_count]
    if out_of_range:
        raise RasterizeError(f"页码越界（PDF 共 {page_count} 页）: {out_of_range}")

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = prefix if prefix is not None else pdf_path.stem

    written: list[Path] = []
    for page in targets:
        out_prefix = out_dir / f"{stem}_p{page:02d}"
        completed = subprocess.run(
            [
                pdftoppm,
                "-png",
                "-r",
                str(dpi),
                "-f",
                str(page),
                "-l",
                str(page),
                "-singlefile",
                str(pdf_path),
                str(out_prefix),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RasterizeError(f"第 {page} 页渲染失败: {completed.stderr.strip()}")

        produced = out_prefix.with_suffix(".png")
        if not produced.is_file():
            raise RasterizeError(f"第 {page} 页渲染后未找到输出文件: {produced}")
        written.append(produced)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：解析参数并执行栅格化。

    :param argv: 参数列表，``None`` 表示取 ``sys.argv[1:]``。
    :returns: 进程退出码，成功为 0。
    :raises RasterizeError: 参数非法或渲染失败时抛出。
    """

    parser = argparse.ArgumentParser(
        description="把 PDF 指定页栅格化为 PNG（读图前必须先转图）",
        epilog="示例: python utils/rasterize_pdf.py report.pdf --pages 3,7-9 --out-dir /tmp/pages",
    )
    parser.add_argument("pdf", help="源 PDF 路径")
    parser.add_argument(
        "--pages",
        default=None,
        help="页码，支持 3 / 3,7 / 3-5 / 1,3-5；省略表示全部页",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录，默认取源文件同级的 <stem>_pages/",
    )
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help=f"渲染分辨率，默认 {DEFAULT_DPI}")
    parser.add_argument("--prefix", default=None, help="输出文件名前缀，默认取源文件名")
    args = parser.parse_args(argv)

    pdf_path = Path(args.pdf)
    out_dir = Path(args.out_dir) if args.out_dir else pdf_path.parent / f"{pdf_path.stem}_pages"
    page_count = _pdf_page_count(pdf_path)
    pages = _parse_pages(args.pages, page_count) if args.pages else None

    for path in rasterize_pdf(pdf_path, out_dir, pages=pages, dpi=args.dpi, prefix=args.prefix):
        print(path)
    return 0


if __name__ == "__main__":
    try:
        _exit_code = main()
    except RasterizeError as _exc:
        print(f"错误: {_exc}", file=sys.stderr)
        raise SystemExit(2) from _exc
    raise SystemExit(_exit_code)
