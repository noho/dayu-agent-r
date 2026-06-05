"""XBRL 关联文件发现公共 helper。

该模块承载 filing 目录中 XBRL 关联文件的文件名发现规则，供：
- processor 在读取文档时定位 instance/schema/linkbase 文件
- storage 在不暴露底层目录结构的前提下回答“某 filing 是否已落盘 XBRL instance”

规则必须保持单一真源，避免 processor 与 storage 各自复制一套文件名判断逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def discover_xbrl_files(directory: Path) -> dict[str, Optional[Path]]:
    """发现 XBRL 关联文件。

    Args:
        directory: filing 文档目录。

    Returns:
        XBRL 文件映射，键包含 `instance/schema/presentation/calculation/definition/label`。

    Raises:
        OSError: 目录访问失败时抛出。
    """

    instance = _first_existing(
        [
            sorted(directory.glob("*_htm.xml")),
            sorted(directory.glob("*_ins.xml")),
            _fallback_instance_files(directory),
        ]
    )
    schema = _first_existing([sorted(directory.glob("*.xsd"))])
    presentation = _first_existing([sorted(directory.glob("*_pre.xml"))])
    calculation = _first_existing([sorted(directory.glob("*_cal.xml"))])
    definition = _first_existing([sorted(directory.glob("*_def.xml"))])
    label = _first_existing([sorted(directory.glob("*_lab.xml"))])
    return {
        "instance": instance,
        "schema": schema,
        "presentation": presentation,
        "calculation": calculation,
        "definition": definition,
        "label": label,
    }


def has_xbrl_instance(directory: Path) -> bool:
    """判断目录内是否存在 XBRL instance 文件。

    Args:
        directory: filing 文档目录。

    Returns:
        若存在可识别的 instance 文件则返回 `True`，否则返回 `False`。

    Raises:
        OSError: 目录访问失败时抛出。
    """

    return discover_xbrl_files(directory).get("instance") is not None


def _fallback_instance_files(directory: Path) -> list[Path]:
    """回退查找 XBRL instance 文件。

    Args:
        directory: filing 文档目录。

    Returns:
        候选 instance 文件列表。

    Raises:
        OSError: 目录访问失败时抛出。
    """

    candidates: list[Path] = []
    for file_path in sorted(directory.glob("*.xml")):
        lowered = file_path.name.lower()
        if any(token in lowered for token in ("_pre.xml", "_cal.xml", "_def.xml", "_lab.xml")):
            continue
        candidates.append(file_path)
    return candidates


def _first_existing(path_groups: list[list[Path]]) -> Optional[Path]:
    """从候选列表中取首个存在路径。

    Args:
        path_groups: 候选路径分组。

    Returns:
        首个可用路径；若不存在则返回 `None`。

    Raises:
        RuntimeError: 匹配失败时由底层调用方处理。
    """

    for group in path_groups:
        for file_path in group:
            if file_path.exists() and file_path.is_file():
                return file_path
    return None
