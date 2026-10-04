"""开发分析脚本唯一的显式样本定位规则。

读取操作者给定的 root/manifest，解析 PDF 与同目录基线路径；同时只读检查
调用方明确传入的实际产物身份。不搜索、不写文件、不解析 Docling/分析结果。
清单为非空 JSON 数组，仅含 pdf/id/kind。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from os import stat_result
from pathlib import Path, PurePosixPath
from typing import cast

from dayu.contracts.json_value import JsonValue

_MANIFEST_FIELDS = frozenset({"pdf", "id", "kind"})
_PDF_SUFFIX = ".pdf"
_BASELINE_SUFFIX = "_docling.json"


@dataclass(frozen=True)
class AnalysisSample:
    """已验证的 PDF 定位与可选报告元数据；不拥有 A/B 身份唯一性。"""

    pdf_path: Path
    sample_id: str | None
    kind: str | None


def resolve_analysis_input_path(path: Path, input_name: str) -> Path:
    """解析开发分析输入路径，将解析调用的链接环归为输入错误。

    :param path: 操作者输入或调用方推导的路径；相对路径按启动 cwd 解析。
    :param input_name: 诊断中的中文输入名称，如样本根、清单或输出根。
    :returns: 按原 strict=False 规则解析后的绝对路径，允许目标尚不存在。
    :raises ValueError: 此次路径解析发生符号链接环，包含输入名称和原路径，
        并链接原 RuntimeError；不处理后续分析或写盘异常。
    :raises OSError: 路径解析的其它系统错误直接传播。
    """

    try:
        return path.resolve(strict=False)
    except RuntimeError as exc:
        raise ValueError(f"{input_name} 符号链接环，无法解析路径: {path}") from exc


def _stat_if_present(path: Path) -> stat_result | None:
    """读取目标元数据，仅将文件不存在视为缺失。

    :param path: 原目标或解析后的父目录。
    :returns: 现存目标的元数据；不存在或 dangling 链接返回 None。
    :raises OSError: 权限、非目录组件或其它元数据读取错误。
    """

    try:
        return path.stat()
    except FileNotFoundError:
        return None


def analysis_targets_alias(first: Path, second: Path) -> bool:
    """只读检查实际目标身份及同解析父目录的限定 ASCII 保全规则。

    :param first: 调用方推导的第一实际目标。
    :param second: 调用方推导的第二实际目标。
    :returns: 解析路径相等、同解析父目录 ASCII 名族相等或现存 samefile
        时为真；ASCII 保全命中不代表跨平台同 inode 证明。
    :raises OSError: 身份或权限检查失败，不降级为无冲突。
    :raises ValueError: 符号链接环导致身份无法检查，链接原 RuntimeError。
    """

    resolved_first = resolve_analysis_input_path(first, "第一产物目标")
    resolved_second = resolve_analysis_input_path(second, "第二产物目标")
    # 所有元数据检查先于文字命中的早返回，单目标自检也必须暴露错误。
    first_stat = _stat_if_present(first)
    second_stat = _stat_if_present(second)
    first_parent_stat = _stat_if_present(resolved_first.parent)
    second_parent_stat = _stat_if_present(resolved_second.parent)
    if resolved_first == resolved_second:
        return True
    same_parent = resolved_first.parent == resolved_second.parent
    if not same_parent and first_parent_stat is not None and second_parent_stat is not None:
        same_parent = resolved_first.parent.samefile(resolved_second.parent)
    if (same_parent and resolved_first.name.isascii() and resolved_second.name.isascii()
            and resolved_first.name.lower() == resolved_second.name.lower()):
        return True
    if first_stat is not None and second_stat is not None:
        return first.samefile(second)
    return False


def require_distinct_sample_targets(
    samples: list[AnalysisSample], targets: list[tuple[Path, ...]],
) -> None:
    """完整预检不同记录的全部实际产物目标，不比较同记录内部角色。

    :param samples: loader 按清单顺序返回的有效样本。
    :param targets: 与 samples 等长且每组非空的实际目标路径。
    :returns: 通过时返回 None，不更改样本、目标或文件。
    :raises ValueError: 分组错误、身份检查失败或不同记录产物冲突；包含
        相关记录、PDF 和目标，检查失败链接原 OSError 或 ValueError。
    """

    if len(samples) != len(targets) or any(not group for group in targets):
        raise ValueError("产物目标分组必须与样本等长且每组非空")
    for index, (sample, group) in enumerate(zip(samples, targets), start=1):
        for target in group:
            try:
                analysis_targets_alias(target, target)
            except (OSError, ValueError) as exc:
                raise ValueError(
                    f"记录 {index} PDF {sample.pdf_path} 无法检查产物身份: {target}: {exc}"
                ) from exc
    for later_index, later_group in enumerate(targets):
        for earlier_index in range(later_index):
            for later_target in later_group:
                for earlier_target in targets[earlier_index]:
                    context = (
                        f"记录 {later_index + 1} PDF {samples[later_index].pdf_path} 的产物 {later_target}"
                        f" 与记录 {earlier_index + 1} PDF {samples[earlier_index].pdf_path} 的产物 {earlier_target}"
                    )
                    try:
                        alias = analysis_targets_alias(later_target, earlier_target)
                    except (OSError, ValueError) as exc:
                        raise ValueError(f"{context} 无法检查身份: {exc}") from exc
                    if alias:
                        raise ValueError(f"{context} 冲突")


def baseline_json_path(pdf_path: Path) -> Path:
    """推导唯一的同目录基线路径，不读取文件。

    :param pdf_path: 已解析的 PDF 路径。
    :returns: 同目录 <stem>_docling.json 路径。
    :raises ValueError: 路径没有可替换的文件名。
    """

    return pdf_path.with_name(f"{pdf_path.stem}{_BASELINE_SUFFIX}")


def _read_records(manifest_path: Path) -> list[Mapping[str, JsonValue]]:
    """读取 JSON 出口并逐级验证非空记录数组。

    :param manifest_path: 已解析的清单文件路径。
    :returns: 按输入顺序的映射记录，字段值留待 loader 校验。
    :raises OSError, ValueError: 文件不可读、JSON 错误或顶层/记录形状错误。
    """

    payload = cast(JsonValue, json.loads(manifest_path.read_text(encoding="utf-8")))
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"清单必须是非空 JSON 数组: {manifest_path}")
    records: list[Mapping[str, JsonValue]] = []
    for index, record in enumerate(payload, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"记录 {index} 必须为 JSON 对象: {manifest_path}")
        records.append(record)
    return records


def _resolve_pdf_path(sample_root: Path, relative_pdf: str) -> Path:
    """解析清单 PDF 并验证相对路径、后缀、根内归属与文件存在性。

    :param sample_root: 已 resolve 的现存目录。
    :param relative_pdf: 已验证的非空字符串，以 / 分隔。
    :returns: 根内的已解析普通 PDF 文件路径。
    :raises OSError, ValueError: 非法路径、根外符号链接或缺失/非文件 PDF。
    """

    relative_path = PurePosixPath(relative_pdf)
    if relative_path.is_absolute() or ".." in relative_path.parts or "\\" in relative_pdf:
        raise ValueError(f"PDF 必须为使用 / 分隔且不含 .. 的相对路径: {relative_pdf}")
    if relative_path.suffix.lower() != _PDF_SUFFIX:
        raise ValueError(f"PDF 扩展名必须为 .pdf: {relative_pdf}")
    pdf_path = resolve_analysis_input_path(sample_root / relative_pdf, "清单 PDF")
    if not pdf_path.is_relative_to(sample_root):
        raise ValueError(f"PDF 解析到样本根外: {pdf_path} (根 {sample_root})")
    if not pdf_path.is_file():
        raise ValueError(f"缺少 PDF 普通文件: {pdf_path}")
    return pdf_path


def load_samples(sample_root: Path, manifest_path: Path) -> list[AnalysisSample]:
    """完整校验操作者清单并按顺序返回显式样本，不产生任何输出。

    :param sample_root: 样本根，相对启动 cwd；可为目录符号链接。
    :param manifest_path: UTF-8 清单，相对启动 cwd，可位于样本根外。
    :returns: PDF 路径及 stem 均唯一的非空样本列表；非 A/B 不拒绝重复 id。
    :raises OSError, ValueError: root/manifest/PDF 不可用、记录非法或路径/stem 重复。
    """

    sample_root = resolve_analysis_input_path(sample_root, "样本根")
    manifest_path = resolve_analysis_input_path(manifest_path, "清单")
    if not sample_root.is_dir():
        raise ValueError(f"样本根必须为现存目录: {sample_root}")
    if not manifest_path.is_file():
        raise ValueError(f"清单必须为现存普通文件: {manifest_path}")
    records = _read_records(manifest_path)
    samples: list[AnalysisSample] = []
    pdf_paths: set[Path] = set()
    stems: set[str] = set()
    for index, record in enumerate(records, start=1):
        if set(record) - _MANIFEST_FIELDS:
            raise ValueError(f"记录 {index} 含未知字段: {manifest_path}")
        for field, value in record.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"记录 {index} 字段 {field} 必须为非空字符串: {manifest_path}")
        relative_pdf = record.get("pdf")
        if not isinstance(relative_pdf, str):
            raise ValueError(f"记录 {index} 缺少必需 pdf 字符串: {manifest_path}")
        try:
            pdf_path = _resolve_pdf_path(sample_root, relative_pdf)
        except (OSError, ValueError) as exc:
            raise ValueError(f"记录 {index}: {exc}") from exc
        if pdf_path in pdf_paths or pdf_path.stem in stems:
            raise ValueError(f"记录 {index} PDF 路径或 stem 重复: {pdf_path}")
        pdf_paths.add(pdf_path)
        stems.add(pdf_path.stem)
        sample_id = record.get("id")
        kind = record.get("kind")
        # 值已逐字段检查；此处分支只表达可选字段的类型，不改写值或补默认身份。
        samples.append(AnalysisSample(pdf_path, sample_id if isinstance(sample_id, str) else None, kind if isinstance(kind, str) else None))
    return samples
