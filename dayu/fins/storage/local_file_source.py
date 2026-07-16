"""本地文件 Source 实现。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional, Protocol


class BinaryFileOpener(Protocol):
    """延迟打开本地二进制文件的窄协议。"""

    def __call__(self, path: Path, /) -> BinaryIO:
        """打开指定路径。

        Args:
            path: 待打开的本地文件路径。

        Returns:
            已打开的二进制只读流。

        Raises:
            RuntimeFileLockError: opener 使用 storage-owned publication guard 且锁操作失败时抛出。
            OSError: 文件打开失败时抛出。
        """

        ...


def _open_binary_file(path: Path, /) -> BinaryIO:
    """直接打开本地二进制文件。

    Args:
        path: 待打开的本地文件路径。

    Returns:
        已打开的二进制只读流。

    Raises:
        OSError: 文件打开失败时抛出。
    """

    return path.open("rb")


@dataclass(frozen=True)
class LocalFileSource:
    """本地文件来源。"""

    path: Path
    uri: str
    media_type: Optional[str] = None
    content_length: Optional[int] = None
    etag: Optional[str] = None
    opener: BinaryFileOpener = _open_binary_file

    def open(self) -> BinaryIO:
        """通过 typed delayed opener 打开只读流。

        storage-owned opener 只在文件描述符打开成功或失败前持 publication guard，
        返回流后不继续持锁。

        Args:
            无。

        Returns:
            二进制只读流。

        Raises:
            RuntimeFileLockError: storage-owned publication guard 获取或释放失败时抛出。
            OSError: 打开失败时抛出。
        """

        return self.opener(self.path)

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
