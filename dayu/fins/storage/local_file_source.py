"""本地文件 Source 实现。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

@dataclass(frozen=True)
class LocalFileSource:
    """本地文件来源。"""

    path: Path
    uri: str
    media_type: Optional[str] = None
    content_length: Optional[int] = None
    etag: Optional[str] = None

    def open(self) -> BinaryIO:
        """打开只读流。

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

        Args:
            suffix: 可选后缀（本地实现忽略）。

        Returns:
            可读取的本地路径。

        Raises:
            OSError: 路径不可用时抛出。
        """

        return self.path
