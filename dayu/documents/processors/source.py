"""处理器输入 Source 协议定义。

该模块位于 documents 处理器层，定义文档处理器统一依赖的输入抽象。
设计目标：
- 让处理器只依赖协议，不依赖具体存储实现（本地文件、对象存储、数据库等）。
- 为不同业务域（fins 及未来其它域）提供统一且稳定的处理入口。
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Optional, Protocol


class Source(Protocol):
    """统一文档来源抽象协议。"""

    @property
    def uri(self) -> str:
        """返回资源 URI。"""

        ...

    @property
    def media_type(self) -> Optional[str]:
        """返回媒体类型。"""

        ...

    @property
    def content_length(self) -> Optional[int]:
        """返回内容长度。"""

        ...

    @property
    def etag(self) -> Optional[str]:
        """返回对象 etag。"""

        ...

    def open(self) -> BinaryIO:
        """打开只读流。

        Args:
            无。

        Returns:
            二进制只读流。

        Raises:
            OSError: 打开失败时抛出。
        """

        ...

    def materialize(self, suffix: Optional[str] = None) -> Path:
        """物化为本地可读路径。

        Args:
            suffix: 可选后缀（通常用于临时文件）。

        Returns:
            本地可读取路径。

        Raises:
            OSError: 物化失败时抛出。
        """

        ...
