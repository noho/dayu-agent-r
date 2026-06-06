"""适配器内部工具业务错误。"""

from __future__ import annotations

from collections.abc import Mapping

from dayu.contracts.json_value import JsonValue


class ToolBusinessError(Exception):
    """工具业务错误。

    :param code: 错误码。
    :param message: 面向 LLM 的错误说明。
    :param hint: 可选恢复提示。
    :param extra: 附加业务上下文。
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str = "",
        extra: Mapping[str, JsonValue] | None = None,
    ) -> None:
        """初始化业务错误。

        :param code: 错误码。
        :param message: 错误说明。
        :param hint: 恢复提示。
        :param extra: 附加业务上下文。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.extra = extra if extra is not None else {}
