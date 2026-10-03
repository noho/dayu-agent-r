"""集中 Fins 默认转换器的管理员配置装配，不产生部署默认值。"""

from __future__ import annotations

import os
from pathlib import Path

from dayu.documents.xbrl_config import XbrlConfigurationError, load_xbrl_conversion_config
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionError,
    DoclingConversionFailureKind,
    ProcessDoclingConverter,
)

_XBRL_CONFIG_ENV = "DAYU_XBRL_CONFIG"


def create_docling_converter(workspace_root: Path) -> ProcessDoclingConverter:
    """参数：禁止管理员输入进入的工作区；返回：显式配置转换器；异常：坏配置抛 construction 错误。"""
    raw = os.environ.get(_XBRL_CONFIG_ENV)
    try:
        if raw is not None and not raw:
            raise XbrlConfigurationError("显式 XBRL 配置路径不能为空")
        config = load_xbrl_conversion_config(Path(raw) if raw is not None else None, workspace_root)
    except XbrlConfigurationError as exc:
        raise DoclingConversionError(
            DoclingConversionFailureKind.CONVERTER_CONSTRUCTION,
            "Docling converter construction failed",
            None,
        ) from exc
    return ProcessDoclingConverter(xbrl_config=config)
