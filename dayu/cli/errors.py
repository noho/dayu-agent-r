"""CLI 公共错误类型。

本模块只定义 CLI adapter 层可共享的异常分类，便于 command 入口按
用户用法错误、运行失败等 CLI presentation 语义统一映射退出码；不承载
Host / Service / Fins 业务事实。
"""

from __future__ import annotations


class CliUsageError(ValueError):
    """CLI 用户用法错误基类。"""


class CliResourcePreparationError(RuntimeError):
    """CLI 运行资源或输出目的地准备失败。"""


__all__: tuple[str, ...] = (
    "CliResourcePreparationError",
    "CliUsageError",
)
