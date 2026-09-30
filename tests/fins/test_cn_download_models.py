"""CN/HK 下载 pipeline 终态 owner 的封闭词表契约测试。"""

from typing import get_args

from dayu.fins.pipelines import cn_download_models
from dayu.fins.pipelines.cn_download_models import (
    CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES,
    CN_DOWNLOAD_TERMINAL_CANCELLED,
    CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED,
    CN_DOWNLOAD_TERMINAL_OK,
    CnDownloadTerminalStatus,
)


def test_cn_download_terminal_owner_has_exact_native_string_values() -> None:
    """类型与值必须精确承诺已有三值，不能以同一常量自比代替协议预期。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 词表、原生字符串类型或普通入口子集漂移时抛出。
    """

    assert get_args(CnDownloadTerminalStatus) == ("ok", "cancelled", "integrity_failed")
    assert CN_DOWNLOAD_TERMINAL_OK == "ok"
    assert CN_DOWNLOAD_TERMINAL_CANCELLED == "cancelled"
    assert CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED == "integrity_failed"
    assert all(type(value) is str for value in (
        CN_DOWNLOAD_TERMINAL_OK,
        CN_DOWNLOAD_TERMINAL_CANCELLED,
        CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED,
    ))
    assert type(CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES) is tuple
    assert CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES == ("ok", "cancelled")
    assert CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES == (
        CN_DOWNLOAD_TERMINAL_OK, CN_DOWNLOAD_TERMINAL_CANCELLED,
    )
    assert set(CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES) < set(get_args(CnDownloadTerminalStatus))
    assert CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED not in CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES


def test_cn_download_terminal_owner_exports_all_contract_symbols() -> None:
    """共享模型必须显式导出全部终态契约符号。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 公共契约符号未声明导出时抛出。
    """

    assert {
        "CnDownloadTerminalStatus",
        "CN_DOWNLOAD_TERMINAL_OK",
        "CN_DOWNLOAD_TERMINAL_CANCELLED",
        "CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED",
        "CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES",
    } <= set(cn_download_models.__all__)
