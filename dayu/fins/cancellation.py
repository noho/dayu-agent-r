"""Fins 层中立协作式取消信号与检查规则。"""

from typing import NoReturn
from dayu.contracts.cancellation import CancellationToken


class FinsReadCancelledError(Exception):
    """Fins read 深层 helper 观察到 Host 取消时的本地信号。

    Args:
        message: 取消说明。
        hint: 恢复提示。

    Returns:
        无。

    Raises:
        无。
    """

    def __init__(self, message: str, hint: str) -> None:
        """初始化取消信号。

        Args:
            message: 取消说明。
            hint: 恢复提示。

        Returns:
            无。

        Raises:
            无。
        """

        self.message = message
        self.hint = hint
        super().__init__(message)


def raise_if_fins_cancelled(cancellation_token: CancellationToken | None, *, message: str) -> None:
    """在 Fins read 慢边界执行协作式取消检查。

    Args:
        cancellation_token: Host 注入的取消观察令牌；未注入时为 None。
        message: 面向 LLM 的业务可读取消说明。

    Returns:
        无。

    Raises:
        FinsReadCancelledError: 当前工具调用已被 Host 取消时抛出。
    """

    if cancellation_token is not None and cancellation_token.is_cancelled():
        raise_fins_cancelled(cancellation_token, message=message)


def raise_fins_cancelled(cancellation_token: CancellationToken, *, message: str) -> NoReturn:
    """抛出 Fins read 本地取消信号。

    Args:
        cancellation_token: 已处于取消状态的 Host 取消观察令牌。
        message: 面向 LLM 的业务可读取消说明。

    Returns:
        不返回。

    Raises:
        FinsReadCancelledError: 始终抛出。
    """

    del cancellation_token
    raise FinsReadCancelledError(
        message=message,
        hint="当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。",
    )
