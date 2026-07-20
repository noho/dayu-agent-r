"""Engine run 失败码契约。

本模块是 Engine-owned run 失败码与 provider / runner 扩展失败码的类型
真源。Engine 自己产生的失败原因必须使用 :class:`EngineRunErrorCode`；
provider / runner adapter 产生的专有协议码必须使用
:class:`RunnerSpecificErrorCode`，并在 Host / public 边界通过
:func:`serialize_engine_error_code` 序列化为 durable 文本。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self, TypeAlias, cast

_RUNNER_SPECIFIC_ERROR_CODE_MAX_CHARS: int = 128


class EngineRunErrorCode(StrEnum):
    """Engine-owned Agent run 失败码闭集。"""

    MAX_ITERATIONS_EXCEEDED = "max_iterations_exceeded"
    RUNNER_EXCEPTION = "runner_exception"
    RUNNER_ABNORMAL_STOP = "runner_abnormal_stop"
    RUNNER_ERROR_DONE_WITHOUT_DETAIL = "runner_error_done_without_detail"
    CONTEXT_COMPACTION_REQUIRED = "context_compaction_required"
    TOOL_CALL_NOT_ENABLED = "tool_call_not_enabled"
    MISSING_TERMINAL = "missing_terminal"
    RUNNER_TOOL_CALLS_MISSING = "runner_tool_calls_missing"
    RUNNER_TOOL_CALLS_FINISH_REASON_MISMATCH = (
        "runner_tool_calls_finish_reason_mismatch"
    )
    RUNNER_EMPTY_FINAL_CONTENT = "runner_empty_final_content"
    DUPLICATE_TOOL_CALL_ID = "duplicate_tool_call_id"
    TOOL_EXECUTOR_EXCEPTION = "tool_executor_exception"
    TOOL_EXECUTION_TIMEOUT = "tool_execution_timeout"
    TOOL_BATCH_OUTCOME_MISMATCH = "tool_batch_outcome_mismatch"
    FORCE_ANSWER_EMPTY = "force_answer_empty"
    CONSECUTIVE_FAILED_TOOL_BATCHES = "consecutive_failed_tool_batches"
    CONTINUATION_TOOL_CALL_NOT_ALLOWED = "continuation_tool_call_not_allowed"


class RunnerSpecificErrorSource(StrEnum):
    """provider / runner 专有失败码来源闭集。"""

    RUNNER_PROTOCOL = "runner_protocol"
    HTTP_PROVIDER = "http_provider"
    ADAPTER = "adapter"


class RunnerSpecificErrorCode(str):
    """provider / runner 专有失败码。

    :param value: provider / runner 专有错误码文本；构造时会去除首尾空白，
        并要求非空且不超过 128 个字符。
    :param source: 错误码来源闭集，用于保留扩展码来源语义。
    :raises ValueError: ``value`` 去空白后为空或超过长度上限时抛出。
    """

    __slots__ = ("source",)

    source: RunnerSpecificErrorSource

    def __new__(
        cls, value: str, source: RunnerSpecificErrorSource
    ) -> Self:
        """构造 provider / runner 专有失败码。

        :param value: provider / runner 专有错误码文本。
        :param source: 错误码来源闭集。
        :returns: 已校验并归一化的错误码实例。
        :raises ValueError: 错误码为空、仅空白或超过长度上限时抛出。
        """

        normalized = value.strip()
        if normalized == "":
            raise ValueError("RunnerSpecificErrorCode.value must be non-empty")
        if len(normalized) > _RUNNER_SPECIFIC_ERROR_CODE_MAX_CHARS:
            raise ValueError("RunnerSpecificErrorCode.value is too long")
        instance = cast(Self, str.__new__(cls, normalized))
        instance.source = source
        return instance

    @property
    def value(self) -> str:
        """返回已归一化的错误码文本。

        :returns: 已去除首尾空白的错误码文本。
        """

        return str(self)


EngineErrorCode: TypeAlias = EngineRunErrorCode | RunnerSpecificErrorCode
"""Engine run 失败码联合类型。"""


def runner_protocol_error_code(value: str) -> RunnerSpecificErrorCode:
    """构造 Runner protocol 专有失败码。

    :param value: provider / runner 协议错误码文本。
    :returns: 带 ``RUNNER_PROTOCOL`` 来源的专有失败码。
    :raises ValueError: 错误码为空、仅空白或超过长度上限时抛出。
    """

    return RunnerSpecificErrorCode(
        value=value,
        source=RunnerSpecificErrorSource.RUNNER_PROTOCOL,
    )


def http_provider_error_code(value: str) -> RunnerSpecificErrorCode:
    """构造 provider HTTP / payload 专有失败码。

    :param value: provider 错误码文本。
    :returns: 带 ``HTTP_PROVIDER`` 来源的专有失败码。
    :raises ValueError: 错误码为空、仅空白或超过长度上限时抛出。
    """

    return RunnerSpecificErrorCode(
        value=value,
        source=RunnerSpecificErrorSource.HTTP_PROVIDER,
    )


def adapter_error_code(value: str) -> RunnerSpecificErrorCode:
    """构造 adapter 专有失败码。

    :param value: adapter 错误码文本。
    :returns: 带 ``ADAPTER`` 来源的专有失败码。
    :raises ValueError: 错误码为空、仅空白或超过长度上限时抛出。
    """

    return RunnerSpecificErrorCode(
        value=value,
        source=RunnerSpecificErrorSource.ADAPTER,
    )


def serialize_engine_error_code(code: EngineErrorCode) -> str:
    """把 typed Engine 错误码序列化为 Host durable/public 文本。

    :param code: Engine-owned 或 provider / runner 专有错误码。
    :returns: 可写入 Host durable JSON 和 public projection 的文本。
    :raises TypeError: 调用方传入非 Engine 错误码类型时抛出。
    """

    if isinstance(code, EngineRunErrorCode):
        return code.value
    if isinstance(code, RunnerSpecificErrorCode):
        return code.value
    raise TypeError("unsupported Engine error code type")


def validate_engine_error_code(code: EngineErrorCode, *, field_name: str) -> None:
    """校验 Engine 错误码联合类型。

    :param code: 待校验错误码。
    :param field_name: 报错中使用的字段名。
    :returns: ``None``。
    :raises TypeError: ``code`` 不是 Engine 错误码联合成员时抛出。
    """

    if isinstance(code, (EngineRunErrorCode, RunnerSpecificErrorCode)):
        return
    raise TypeError(f"{field_name} must be an Engine error code")


def validate_runner_specific_error_code(
    code: RunnerSpecificErrorCode, *, field_name: str
) -> None:
    """校验 provider / runner 专有错误码类型。

    :param code: 待校验错误码。
    :param field_name: 报错中使用的字段名。
    :returns: ``None``。
    :raises TypeError: ``code`` 不是专有错误码 wrapper 时抛出。
    """

    if isinstance(code, RunnerSpecificErrorCode):
        return
    raise TypeError(f"{field_name} must be a RunnerSpecificErrorCode")


__all__ = [
    "EngineErrorCode",
    "EngineRunErrorCode",
    "RunnerSpecificErrorCode",
    "RunnerSpecificErrorSource",
    "adapter_error_code",
    "http_provider_error_code",
    "runner_protocol_error_code",
    "serialize_engine_error_code",
    "validate_engine_error_code",
    "validate_runner_specific_error_code",
]
