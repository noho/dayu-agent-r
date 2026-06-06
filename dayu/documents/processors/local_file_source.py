"""本地文件 Source 实现（documents 处理器层）。

提供 documents 层独立的 LocalFileSource，避免从 fins 层导入。
fins 层的同名实现保持不动，两者独立存在，维持层级隔离。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

from .source import Source


@dataclass(frozen=True)
class LocalFileSource:
    """本地文件来源。

    实现 Source 协议，封装本地文件的元信息与流式访问。
    作为 documents 层处理器创建的统一入口。

    Attributes:
        path: 本地文件绝对路径。
        uri: 文件标识符（通常为 str(path)）。
        media_type: MIME 类型（可选）。
        content_length: 字节大小（可选）。
        etag: 内容哈希（可选）。
    """

    path: Path
    uri: str
    media_type: Optional[str] = None
    content_length: Optional[int] = None
    etag: Optional[str] = None

    def open(self) -> BinaryIO:
        """打开只读二进制流。

        Args:
            无。

        Returns:
            二进制只读流。

        Raises:
            OSError: 打开失败时抛出。
        """
        return self.path.open("rb")

    def materialize(self, suffix: Optional[str] = None) -> Path:
        """物化为本地路径。

        本地文件无需额外转换，直接返回原路径。

        Args:
            suffix: 可选后缀（本地实现忽略）。

        Returns:
            可读取的本地路径。

        Raises:
            OSError: 路径不可用时抛出。
        """
        return self.path
