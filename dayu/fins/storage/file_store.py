"""文件存储接口定义。"""

from __future__ import annotations

from typing import BinaryIO, Optional, Protocol

from dayu.fins.domain.document_models import FileObjectMeta


class FileStore(Protocol):
    """对象存储接口协议。"""

    def put_object(
        self,
        key: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """写入对象内容并返回元数据。

        Args:
            key: 对象键（如 `bucket/key` 风格的逻辑路径）。
            data: 二进制流。
            content_type: 可选内容类型。
            metadata: 可选扩展元数据。

        Returns:
            文件对象元数据。

        Raises:
            OSError: 写入失败时抛出。
        """

        ...

    def get_object(self, key: str) -> BinaryIO:
        """读取对象内容。

        Args:
            key: 对象键。

        Returns:
            二进制流。

        Raises:
            FileNotFoundError: 对象不存在时抛出。
        """

        ...

    def stat_object(self, key: str) -> FileObjectMeta:
        """查询对象元数据。

        Args:
            key: 对象键。

        Returns:
            文件对象元数据。

        Raises:
            FileNotFoundError: 对象不存在时抛出。
        """

        ...

    def delete_object(self, key: str) -> None:
        """删除对象。

        Args:
            key: 对象键。

        Returns:
            无。

        Raises:
            FileNotFoundError: 对象不存在时抛出。
        """

        ...

    def get_presigned_url(self, key: str, expires_in: int) -> str:
        """获取预签名 URL（可选实现）。

        Args:
            key: 对象键。
            expires_in: 过期秒数。

        Returns:
            预签名 URL。

        Raises:
            NotImplementedError: 未实现时抛出。
        """

        ...

    def list_objects(self, prefix: str) -> list[FileObjectMeta]:
        """按前缀列出对象。

        Args:
            prefix: 对象前缀。

        Returns:
            对象元数据列表。

        Raises:
            OSError: 读取失败时抛出。
        """

        ...
