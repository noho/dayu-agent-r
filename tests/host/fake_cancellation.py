"""Host 测试专用 cancellation token。

本模块只提供 tests 下的可控 token，避免测试继续复制不可取消 token 名称。
生产代码必须从 Host 生命周期或 durable 状态注入真实 token。
"""

from __future__ import annotations

from datetime import UTC, datetime

from dayu.contracts.cancellation import CancellationToken


class StubCancellationToken(CancellationToken):
    """测试专用可控 cancellation token。

    :param reason: 初始取消原因；不传表示未取消。
    """

    def __init__(self, reason: str | None = None) -> None:
        """初始化测试 token。

        :param reason: 初始取消原因；不传表示未取消。
        :returns: ``None``。
        """

        self._reason = reason
        self._requested_at = datetime.now(UTC) if reason is not None else None

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已取消时返回 ``True``。
        """

        return self._reason is not None

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 取消原因；未取消时返回 ``None``。
        """

        return self._reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 取消时间；未取消时返回 ``None``。
        """

        return self._requested_at

    def request_cancel(self, reason: str) -> None:
        """将 token 标记为已取消。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        if self._reason is None:
            self._reason = reason
            self._requested_at = datetime.now(UTC)
