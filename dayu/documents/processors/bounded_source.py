"""层中立的有界文档 Source 快照。

本模块只依赖标准库与 :mod:`dayu.documents` 内部 ``Source`` 协议。它在
处理器读取前，从同一次 ``Source.open()`` 得到的流按块复制最多
``max_bytes + 1`` 字节，并用 typed exception 拒绝超预算输入。
"""

from __future__ import annotations

import io
import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, cast

from .source import Source

_COPY_CHUNK_BYTES = 64 * 1024
_SPOOL_MEMORY_BYTES = 1024 * 1024
_MATERIALIZED_PREFIX = "dayu-doc-bounded-"


class SourceBudgetExceeded(Exception):
    """Source 实读字节数超过预算。

    Args:
        source_uri: Source 标识。
        limit_bytes: 允许读取的最大字节数。
        observed_bytes: 已观察到的最小字节数。

    Raises:
        无。
    """

    def __init__(self, source_uri: str, limit_bytes: int, observed_bytes: int) -> None:
        """初始化资源超限异常。

        Args:
            source_uri: Source 标识。
            limit_bytes: 允许读取的最大字节数。
            observed_bytes: 已观察到的最小字节数。

        Returns:
            无。

        Raises:
            无。
        """

        self.source_uri = source_uri
        self.limit_bytes = limit_bytes
        self.observed_bytes = observed_bytes
        super().__init__(
            f"source exceeds byte budget: limit={limit_bytes}, observed>={observed_bytes}"
        )


class _SnapshotBinaryReader(io.RawIOBase):
    """共享快照上的独立只读游标。"""

    def __init__(self, snapshot: BoundedSourceSnapshot) -> None:
        """初始化游标。

        Args:
            snapshot: 已进入上下文的有界快照。

        Returns:
            无。

        Raises:
            ValueError: 快照尚未就绪时由后续读取抛出。
        """

        super().__init__()
        self._snapshot = snapshot
        self._position = 0

    def readable(self) -> bool:
        """返回流是否可读。

        Returns:
            始终为 ``True``。

        Raises:
            无。
        """

        return True

    def seekable(self) -> bool:
        """返回流是否支持定位。

        Returns:
            始终为 ``True``。

        Raises:
            无。
        """

        return True

    def tell(self) -> int:
        """返回当前游标位置。

        Returns:
            当前字节偏移。

        Raises:
            ValueError: reader 已关闭时抛出。
        """

        self._checkClosed()
        return self._position

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        """移动只读游标。

        Args:
            offset: 相对 ``whence`` 的字节偏移。
            whence: ``SEEK_SET``、``SEEK_CUR`` 或 ``SEEK_END``。

        Returns:
            移动后的绝对字节位置。

        Raises:
            ValueError: whence 非法、目标为负或 reader 已关闭时抛出。
        """

        self._checkClosed()
        if whence == os.SEEK_SET:
            position = offset
        elif whence == os.SEEK_CUR:
            position = self._position + offset
        elif whence == os.SEEK_END:
            position = self._snapshot.snapshot_size + offset
        else:
            raise ValueError(f"unsupported whence: {whence}")
        if position < 0:
            raise ValueError("negative seek position")
        self._position = position
        return position

    def read(self, size: int = -1) -> bytes:
        """从当前游标读取字节。

        Args:
            size: 最大读取字节数；负数表示读取到末尾。

        Returns:
            读取到的字节。

        Raises:
            ValueError: reader 已关闭或快照上下文已结束时抛出。
        """

        self._checkClosed()
        data = self._snapshot._read_at(self._position, size)
        self._position += len(data)
        return data

class BoundedSourceSnapshot:
    """从单次 Source 流读取构造的有界临时快照。

    Args:
        source: 文档来源。
        max_bytes: 允许实读的最大字节数。
        cancellation_check: 可选协作取消检查；调用时应在已取消状态抛出。

    Raises:
        ValueError: ``max_bytes`` 不是正整数时抛出。
    """

    def __init__(
        self,
        source: Source,
        max_bytes: int,
        cancellation_check: Callable[[], None] | None = None,
    ) -> None:
        """初始化尚未读取的快照。

        Args:
            source: 文档来源。
            max_bytes: 允许实读的最大字节数。
            cancellation_check: 可选协作取消检查。

        Returns:
            无。

        Raises:
            ValueError: ``max_bytes`` 不是正整数时抛出。
        """

        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        self._source = source
        self._max_bytes = max_bytes
        self._cancellation_check = cancellation_check
        self._spool: BinaryIO | None = None
        self._snapshot_size: int | None = None
        self._materialized_path: Path | None = None
        self._lock = threading.Lock()
        self._entered = False

    @property
    def uri(self) -> str:
        """返回原 Source URI。

        Returns:
            Source URI。

        Raises:
            无。
        """

        return self._source.uri

    @property
    def media_type(self) -> str | None:
        """返回原 Source 媒体类型。

        Returns:
            媒体类型或 ``None``。

        Raises:
            无。
        """

        return self._source.media_type

    @property
    def content_length(self) -> int | None:
        """返回快照精确长度；进入上下文前返回来源声明值。

        Returns:
            字节长度或 ``None``。

        Raises:
            无。
        """

        if self._snapshot_size is not None:
            return self._snapshot_size
        return self._source.content_length

    @property
    def etag(self) -> str | None:
        """返回原 Source etag。

        Returns:
            etag 或 ``None``。

        Raises:
            无。
        """

        return self._source.etag

    @property
    def snapshot_size(self) -> int:
        """返回已完成快照的精确字节数。

        Returns:
            精确字节数。

        Raises:
            ValueError: 快照尚未就绪或已清理时抛出。
        """

        if self._spool is None or self._snapshot_size is None:
            raise ValueError("bounded source snapshot is not active")
        return self._snapshot_size

    def __enter__(self) -> BoundedSourceSnapshot:
        """读取原 Source 并进入快照上下文。

        Returns:
            已就绪的当前快照。

        Raises:
            SourceBudgetExceeded: 声明长度或实读长度超过预算时抛出。
            OSError: Source 打开或读取失败时抛出。
            BaseException: 取消检查抛出的异常原样透出。
        """

        if self._entered:
            raise RuntimeError("bounded source snapshot cannot be reused")
        self._entered = True
        declared_length = self._source.content_length
        if declared_length is not None and declared_length > self._max_bytes:
            raise SourceBudgetExceeded(self.uri, self._max_bytes, declared_length)

        spool_limit = min(self._max_bytes, _SPOOL_MEMORY_BYTES)
        spool = cast(
            BinaryIO,
            tempfile.SpooledTemporaryFile(max_size=spool_limit, mode="w+b"),
        )
        self._spool = spool
        copied = 0
        try:
            self._check_cancellation()
            with self._source.open() as source_stream:
                while True:
                    self._check_cancellation()
                    remaining = self._max_bytes - copied
                    chunk = source_stream.read(min(_COPY_CHUNK_BYTES, remaining + 1))
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > self._max_bytes:
                        raise SourceBudgetExceeded(self.uri, self._max_bytes, copied)
                    spool.write(chunk)
            self._check_cancellation()
            spool.seek(0)
            self._snapshot_size = copied
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出上下文并清理 spool 与物化临时文件。

        Args:
            exc_type: 当前异常类型。
            exc: 当前异常实例。
            traceback: 当前 traceback。

        Returns:
            无。

        Raises:
            无；清理失败被抑制以保留原始异常。
        """

        del exc_type, exc, traceback
        self.close()

    def open(self) -> BinaryIO:
        """打开共享快照上的独立只读游标。

        Returns:
            二进制只读流。

        Raises:
            ValueError: 快照尚未进入上下文或已经清理时抛出。
        """

        self.snapshot_size
        return cast(BinaryIO, _SnapshotBinaryReader(self))

    def materialize(self, suffix: str | None = None) -> Path:
        """把有界快照物化到系统临时目录。

        单个 snapshot 只发布一个物化路径；后续调用复用该路径，确保异常
        终止时至多留下一个受 ``max_bytes`` 限制的命名临时文件。

        Args:
            suffix: 可选文件后缀。

        Returns:
            当前上下文拥有的临时文件路径。

        Raises:
            ValueError: 快照尚未进入上下文或已经清理时抛出。
            OSError: 临时文件创建或写入失败时抛出。
        """

        self.snapshot_size
        if self._materialized_path is not None:
            return self._materialized_path
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                prefix=_MATERIALIZED_PREFIX,
                suffix=suffix or "",
                delete=False,
            ) as output:
                temp_path = Path(output.name)
                with self.open() as reader:
                    while True:
                        chunk = reader.read(_COPY_CHUNK_BYTES)
                        if not chunk:
                            break
                        output.write(chunk)
            self._materialized_path = temp_path
            return temp_path
        except BaseException:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise

    def close(self) -> None:
        """清理当前快照拥有的全部临时资源。

        Returns:
            无。

        Raises:
            无；临时资源清理失败被抑制。
        """

        materialized_path = self._materialized_path
        self._materialized_path = None
        if materialized_path is not None:
            try:
                materialized_path.unlink(missing_ok=True)
            except OSError:
                pass
        spool = self._spool
        self._spool = None
        self._snapshot_size = None
        if spool is not None:
            try:
                spool.close()
            except OSError:
                pass

    def _check_cancellation(self) -> None:
        """执行可选协作取消检查。

        Returns:
            无。

        Raises:
            BaseException: 取消检查抛出的异常原样透出。
        """

        if self._cancellation_check is not None:
            self._cancellation_check()

    def _read_at(self, position: int, size: int) -> bytes:
        """在共享 spool 上按绝对位置读取。

        Args:
            position: 绝对字节位置。
            size: 最大读取字节数；负数表示读取到末尾。

        Returns:
            读取到的字节。

        Raises:
            ValueError: 快照上下文已经结束时抛出。
        """

        with self._lock:
            spool = self._spool
            if spool is None or self._snapshot_size is None:
                raise ValueError("bounded source snapshot is not active")
            spool.seek(position)
            return spool.read(size)
