"""OpenAI-compatible choice 与 finish_reason 私有规范化策略。

本模块只服务 OpenAI-compatible Runner adapter。它把 provider wire
response 中的 ``choices`` 与 ``finish_reason`` 在 adapter 边界先行校验，
避免 SSE 与 non-stream 路径各自选择、合并或默认终态。
"""

from __future__ import annotations

from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.finish_reason import FinishReason

_CHOICES_FIELD: str = "choices"
_DELTA_FIELD: str = "delta"
_FINISH_REASON_FIELD: str = "finish_reason"
_INDEX_FIELD: str = "index"
_MESSAGE_FIELD: str = "message"
_SSE_SEMANTIC_DELTA_FIELDS: frozenset[str] = frozenset(
    {
        "role",
        "content",
        "reasoning_content",
        "tool_calls",
    }
)
_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "tool_calls": FinishReason.TOOL_CALLS,
    "content_filter": FinishReason.CONTENT_FILTER,
}

SSE_MISSING_CHOICES_CODE: str = "sse_missing_choices"
SSE_INVALID_CHOICE_SHAPE_CODE: str = "sse_invalid_choice_shape"
SSE_CHOICE_INDEX_NON_ZERO_CODE: str = "sse_choice_index_non_zero"
SSE_MULTIPLE_VALID_CHOICES_CODE: str = "sse_multiple_valid_choices"
SSE_INVALID_FINISH_REASON_CODE: str = "sse_invalid_finish_reason"
SSE_CONFLICTING_FINISH_REASON_CODE: str = "sse_conflicting_finish_reason"
SSE_MISSING_FINISH_REASON_CODE: str = "sse_missing_finish_reason"
SSE_TOOL_CALLS_FINISH_REASON_MISMATCH_CODE: str = (
    "sse_tool_calls_finish_reason_mismatch"
)

NON_STREAM_MISSING_CHOICES_CODE: str = "non_stream_missing_choices"
NON_STREAM_CHOICE_NOT_OBJECT_CODE: str = "non_stream_choice_not_object"
NON_STREAM_MULTIPLE_CHOICES_CODE: str = "non_stream_multiple_choices"
NON_STREAM_CHOICE_INDEX_NON_ZERO_CODE: str = "non_stream_choice_index_non_zero"
NON_STREAM_INVALID_CHOICE_SHAPE_CODE: str = "non_stream_invalid_choice_shape"
NON_STREAM_INVALID_FINISH_REASON_CODE: str = "non_stream_invalid_finish_reason"
NON_STREAM_MISSING_FINISH_REASON_CODE: str = "non_stream_missing_finish_reason"
NON_STREAM_TOOL_CALLS_FINISH_REASON_MISMATCH_CODE: str = (
    "non_stream_tool_calls_finish_reason_mismatch"
)

_REASON_CHOICES_MISSING: str = "choices_missing"
_REASON_CHOICES_NOT_LIST: str = "choices_not_list"
_REASON_CHOICES_EMPTY: str = "choices_empty"
_REASON_SSE_CHOICES_EMPTY_WITHOUT_USAGE: str = "choices_empty_without_usage"
_REASON_CHOICE_NOT_OBJECT: str = "choice_not_object"
_REASON_CHOICE_INDEX_NOT_INT: str = "choice_index_not_int"
_REASON_CHOICE_INDEX_NON_ZERO: str = "choice_index_non_zero"
_REASON_DELTA_MISSING: str = "delta_missing"
_REASON_DELTA_NOT_OBJECT: str = "delta_not_object"
_REASON_NO_VALID_ASSISTANT_CHOICE: str = "no_valid_assistant_choice"
_REASON_MULTIPLE_VALID_CHOICES: str = "multiple_valid_choices"
_REASON_FINISH_REASON_EMPTY: str = "finish_reason_empty"
_REASON_FINISH_REASON_UNKNOWN: str = "finish_reason_unknown"
_REASON_FINISH_REASON_NOT_STRING: str = "finish_reason_not_string"
_REASON_FINISH_REASON_CONFLICT: str = "finish_reason_conflict"
_REASON_NON_STREAM_MULTIPLE_CHOICES: str = "non_stream_multiple_choices"
_REASON_NON_STREAM_MESSAGE_MISSING: str = "message_missing"
_REASON_NON_STREAM_MESSAGE_NOT_OBJECT: str = "message_not_object"
_REASON_MISSING_FINISH_REASON: str = "missing_finish_reason"
_REASON_TOOL_CALLS_FINISH_REASON_MISMATCH: str = (
    "tool_calls_finish_reason_mismatch"
)


@dataclass(frozen=True, slots=True)
class ChoicePolicyError:
    """choice policy 校验失败。

    :param error_code: adapter 内部 fatal provider protocol error code。
    :param message: 面向诊断的人类可读错误说明。
    :param diagnostic_reason: 有界 raw payload 中记录的稳定错误原因。
    """

    error_code: str
    message: str
    diagnostic_reason: str


@dataclass(frozen=True, slots=True)
class SSEChoiceSelection:
    """单个 SSE chunk 的 choice 校验结果。

    :param choice: 唯一合法 assistant choice；usage-only chunk 时为
        ``None``。
    :param finish_reason: 当前 choice 携带的终态原因；未携带时为
        ``None``。
    """

    choice: dict[str, JsonValue] | None
    finish_reason: FinishReason | None


@dataclass(frozen=True, slots=True)
class NonStreamChoiceSelection:
    """非流式 response 的 choice 校验结果。

    :param choice: 唯一合法 assistant choice。
    :param finish_reason: provider 明确给出的终态原因；``null`` 或缺失时
        为 ``None``，必须由 terminal shape policy fail closed。
    """

    choice: dict[str, JsonValue]
    finish_reason: FinishReason | None


def validate_sse_chunk_choices(
    parsed: dict[str, JsonValue],
    *,
    has_valid_usage: bool,
    current_finish_reason: FinishReason | None,
) -> SSEChoiceSelection | ChoicePolicyError:
    """校验单个 SSE chunk 的 ``choices`` 策略。

    ``choices=[]`` 仅在 usage-only chunk 中合法。非空 ``choices`` 必须
    恰好包含一个有效 assistant choice；任何非法 shape、显式非零 index、
    未知 finish_reason 或跨 chunk 终态冲突都会 fail closed。

    :param parsed: 已解析的 SSE JSON object。
    :param has_valid_usage: 当前 chunk 是否包含合法 usage object。
    :param current_finish_reason: 之前 chunk 已接受的终态原因。
    :returns: 校验后的唯一 choice 或 fatal policy error。
    :raises Exception: 不主动抛出异常。
    """

    choices = parsed.get(_CHOICES_FIELD)
    if choices is None:
        return ChoicePolicyError(
            error_code=SSE_MISSING_CHOICES_CODE,
            message="SSE data line must contain choices",
            diagnostic_reason=_REASON_CHOICES_MISSING,
        )
    if not isinstance(choices, list):
        return ChoicePolicyError(
            error_code=SSE_MISSING_CHOICES_CODE,
            message="SSE data line choices must be a JSON array",
            diagnostic_reason=_REASON_CHOICES_NOT_LIST,
        )
    if not choices:
        if has_valid_usage:
            return SSEChoiceSelection(choice=None, finish_reason=None)
        return ChoicePolicyError(
            error_code=SSE_MISSING_CHOICES_CODE,
            message="SSE data line choices may be empty only for usage chunks",
            diagnostic_reason=_REASON_SSE_CHOICES_EMPTY_WITHOUT_USAGE,
        )

    valid_choices: list[tuple[dict[str, JsonValue], FinishReason | None]] = []
    for position, raw_choice in enumerate(choices):
        if not isinstance(raw_choice, dict):
            return ChoicePolicyError(
                error_code=SSE_INVALID_CHOICE_SHAPE_CODE,
                message=f"SSE choices[{position}] is not a JSON object",
                diagnostic_reason=_REASON_CHOICE_NOT_OBJECT,
            )
        index_error = _validate_choice_index(
            raw_choice,
            non_zero_code=SSE_CHOICE_INDEX_NON_ZERO_CODE,
            shape_code=SSE_INVALID_CHOICE_SHAPE_CODE,
        )
        if index_error is not None:
            return index_error
        finish_result = _resolve_finish_reason(
            raw_choice,
            invalid_code=SSE_INVALID_FINISH_REASON_CODE,
        )
        if isinstance(finish_result, ChoicePolicyError):
            return finish_result
        if (
            current_finish_reason is not None
            and finish_result is not None
            and finish_result is not current_finish_reason
        ):
            return ChoicePolicyError(
                error_code=SSE_CONFLICTING_FINISH_REASON_CODE,
                message="SSE finish_reason conflicts with an earlier terminal finish_reason",
                diagnostic_reason=_REASON_FINISH_REASON_CONFLICT,
            )
        shape_error = _validate_sse_delta_shape(raw_choice)
        if shape_error is not None:
            return shape_error
        if _is_valid_sse_assistant_choice(raw_choice, finish_result):
            valid_choices.append((raw_choice, finish_result))

    if len(valid_choices) > 1:
        return ChoicePolicyError(
            error_code=SSE_MULTIPLE_VALID_CHOICES_CODE,
            message="SSE data line contains multiple valid assistant choices",
            diagnostic_reason=_REASON_MULTIPLE_VALID_CHOICES,
        )
    if not valid_choices:
        return ChoicePolicyError(
            error_code=SSE_MISSING_CHOICES_CODE,
            message="SSE data line choices contain no valid assistant choice",
            diagnostic_reason=_REASON_NO_VALID_ASSISTANT_CHOICE,
        )
    selected, finish_reason = valid_choices[0]
    return SSEChoiceSelection(choice=selected, finish_reason=finish_reason)


def validate_non_stream_choice(
    parsed: dict[str, JsonValue],
) -> NonStreamChoiceSelection | ChoicePolicyError:
    """校验非流式 response 的 response-level ``choices`` 策略。

    非流式响应必须有且只有一个 assistant choice；缺失、非数组、空数组、
    多 choice、choice 非 object、显式非零 index 或非法 finish_reason
    均为 fatal provider protocol error。

    :param parsed: 已解析的非流式 JSON object。
    :returns: 唯一合法 choice 或 fatal policy error。
    :raises Exception: 不主动抛出异常。
    """

    choices = parsed.get(_CHOICES_FIELD)
    if choices is None:
        return ChoicePolicyError(
            error_code=NON_STREAM_MISSING_CHOICES_CODE,
            message="non-stream response missing choices",
            diagnostic_reason=_REASON_CHOICES_MISSING,
        )
    if not isinstance(choices, list):
        return ChoicePolicyError(
            error_code=NON_STREAM_MISSING_CHOICES_CODE,
            message="non-stream response choices must be a JSON array",
            diagnostic_reason=_REASON_CHOICES_NOT_LIST,
        )
    if not choices:
        return ChoicePolicyError(
            error_code=NON_STREAM_MISSING_CHOICES_CODE,
            message="non-stream response choices must contain exactly one choice",
            diagnostic_reason=_REASON_CHOICES_EMPTY,
        )
    if len(choices) != 1:
        return ChoicePolicyError(
            error_code=NON_STREAM_MULTIPLE_CHOICES_CODE,
            message="non-stream response choices must contain exactly one choice",
            diagnostic_reason=_REASON_NON_STREAM_MULTIPLE_CHOICES,
        )
    raw_choice = choices[0]
    if not isinstance(raw_choice, dict):
        return ChoicePolicyError(
            error_code=NON_STREAM_CHOICE_NOT_OBJECT_CODE,
            message="non-stream choice is not a JSON object",
            diagnostic_reason=_REASON_CHOICE_NOT_OBJECT,
        )
    index_error = _validate_choice_index(
        raw_choice,
        non_zero_code=NON_STREAM_CHOICE_INDEX_NON_ZERO_CODE,
        shape_code=NON_STREAM_INVALID_CHOICE_SHAPE_CODE,
    )
    if index_error is not None:
        return index_error
    finish_result = _resolve_finish_reason(
        raw_choice,
        invalid_code=NON_STREAM_INVALID_FINISH_REASON_CODE,
    )
    if isinstance(finish_result, ChoicePolicyError):
        return finish_result
    return NonStreamChoiceSelection(choice=raw_choice, finish_reason=finish_result)


def validate_non_stream_terminal_shape(
    choice: dict[str, JsonValue],
    *,
    finish_reason: FinishReason | None,
    has_tool_calls: bool,
) -> ChoicePolicyError | None:
    """校验非流式 assistant message 与 terminal tool-call shape。

    非流式成功响应必须包含 assistant message，并由共用 terminal helper
    校验显式 finish reason 与 tool-call presence 严格一致。

    :param choice: 已通过 response-level policy 的单个 choice。
    :param finish_reason: 已规范化的终态原因；缺失或 ``null`` 时为
        ``None``。
    :param has_tool_calls: message 是否携带非空 tool_calls 列表。
    :returns: 需要 fatal 收口时返回 policy error，否则返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    message = choice.get(_MESSAGE_FIELD)
    if message is None:
        return ChoicePolicyError(
            error_code=NON_STREAM_INVALID_CHOICE_SHAPE_CODE,
            message="non-stream choice missing assistant message",
            diagnostic_reason=_REASON_NON_STREAM_MESSAGE_MISSING,
        )
    if not isinstance(message, dict):
        return ChoicePolicyError(
            error_code=NON_STREAM_INVALID_CHOICE_SHAPE_CODE,
            message="non-stream choice message is not a JSON object",
            diagnostic_reason=_REASON_NON_STREAM_MESSAGE_NOT_OBJECT,
        )
    return _validate_terminal_shape(
        finish_reason=finish_reason,
        has_tool_calls=has_tool_calls,
        missing_code=NON_STREAM_MISSING_FINISH_REASON_CODE,
        mismatch_code=NON_STREAM_TOOL_CALLS_FINISH_REASON_MISMATCH_CODE,
        transport_name="non-stream",
    )


def validate_sse_terminal_shape(
    *,
    finish_reason: FinishReason | None,
    has_tool_calls: bool,
) -> ChoicePolicyError | None:
    """校验 SSE 聚合终态的 finish reason 与 tool-call presence。

    :param finish_reason: 跨 chunks 聚合后的显式 provider finish reason。
    :param has_tool_calls: 本次 stream 是否观察到 tool-call 列表。
    :returns: 需要 fatal 收口时返回 policy error，否则返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    return _validate_terminal_shape(
        finish_reason=finish_reason,
        has_tool_calls=has_tool_calls,
        missing_code=SSE_MISSING_FINISH_REASON_CODE,
        mismatch_code=SSE_TOOL_CALLS_FINISH_REASON_MISMATCH_CODE,
        transport_name="SSE",
    )


def _validate_terminal_shape(
    *,
    finish_reason: FinishReason | None,
    has_tool_calls: bool,
    missing_code: str,
    mismatch_code: str,
    transport_name: str,
) -> ChoicePolicyError | None:
    """校验成功终态必须显式且与 tool-call presence 双向一致。

    :param finish_reason: 已规范化的显式 provider finish reason。
    :param has_tool_calls: 当前 response 是否包含 tool calls。
    :param missing_code: 当前 transport 的 missing error code。
    :param mismatch_code: 当前 transport 的 mismatch error code。
    :param transport_name: 当前 transport 诊断前缀。
    :returns: fatal policy error；shape 一致时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if finish_reason is None:
        return ChoicePolicyError(
            error_code=missing_code,
            message=f"{transport_name} response missing terminal finish_reason",
            diagnostic_reason=_REASON_MISSING_FINISH_REASON,
        )
    finish_declares_tool_calls = finish_reason is FinishReason.TOOL_CALLS
    if has_tool_calls is finish_declares_tool_calls:
        return None
    return ChoicePolicyError(
        error_code=mismatch_code,
        message=(
            f"{transport_name} tool-call presence does not match "
            "terminal finish_reason"
        ),
        diagnostic_reason=_REASON_TOOL_CALLS_FINISH_REASON_MISMATCH,
    )


def _validate_choice_index(
    choice: dict[str, JsonValue],
    *,
    non_zero_code: str,
    shape_code: str,
) -> ChoicePolicyError | None:
    """校验 choice index 只能缺失或显式为整数零。

    :param choice: provider choice object。
    :param non_zero_code: 显式非零 index 对应错误码。
    :param shape_code: index 类型非法对应错误码。
    :returns: fatal policy error；合法时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    index = choice.get(_INDEX_FIELD)
    if index is None:
        return None
    if isinstance(index, bool) or not isinstance(index, int):
        return ChoicePolicyError(
            error_code=shape_code,
            message="provider choice index must be integer zero when present",
            diagnostic_reason=_REASON_CHOICE_INDEX_NOT_INT,
        )
    if index != 0:
        return ChoicePolicyError(
            error_code=non_zero_code,
            message="provider choice index must be zero",
            diagnostic_reason=_REASON_CHOICE_INDEX_NON_ZERO,
        )
    return None


def _resolve_finish_reason(
    choice: dict[str, JsonValue], *, invalid_code: str
) -> FinishReason | ChoicePolicyError | None:
    """把 provider ``finish_reason`` 显式映射为 Engine 枚举。

    :param choice: provider choice object。
    :param invalid_code: 非法 finish_reason 对应错误码。
    :returns: 映射后的 finish reason、fatal policy error，或 absent
        ``None``。
    :raises Exception: 不主动抛出异常。
    """

    raw = choice.get(_FINISH_REASON_FIELD)
    if raw is None:
        return None
    if not isinstance(raw, str):
        return ChoicePolicyError(
            error_code=invalid_code,
            message="provider finish_reason must be a known non-empty string or null",
            diagnostic_reason=_REASON_FINISH_REASON_NOT_STRING,
        )
    if raw == "":
        return ChoicePolicyError(
            error_code=invalid_code,
            message="provider finish_reason must not be an empty string",
            diagnostic_reason=_REASON_FINISH_REASON_EMPTY,
        )
    mapped = _FINISH_REASON_MAP.get(raw)
    if mapped is None:
        return ChoicePolicyError(
            error_code=invalid_code,
            message="provider finish_reason is not supported by this adapter",
            diagnostic_reason=_REASON_FINISH_REASON_UNKNOWN,
        )
    return mapped


def _validate_sse_delta_shape(
    choice: dict[str, JsonValue],
) -> ChoicePolicyError | None:
    """校验 SSE assistant choice 的 ``delta`` shape。

    :param choice: provider choice object。
    :returns: fatal policy error；shape 可判断时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    delta = choice.get(_DELTA_FIELD)
    finish_reason = choice.get(_FINISH_REASON_FIELD)
    if delta is None:
        if finish_reason is None:
            return None
        return ChoicePolicyError(
            error_code=SSE_INVALID_CHOICE_SHAPE_CODE,
            message="SSE choice with finish_reason must contain a delta object",
            diagnostic_reason=_REASON_DELTA_MISSING,
        )
    if not isinstance(delta, dict):
        return ChoicePolicyError(
            error_code=SSE_INVALID_CHOICE_SHAPE_CODE,
            message="SSE choice delta must be a JSON object",
            diagnostic_reason=_REASON_DELTA_NOT_OBJECT,
        )
    return None


def _is_valid_sse_assistant_choice(
    choice: dict[str, JsonValue], finish_reason: FinishReason | None
) -> bool:
    """判断 SSE choice 是否承载 adapter 可消费的 assistant 语义。

    :param choice: provider choice object。
    :param finish_reason: 已规范化的终态原因。
    :returns: 是合法 assistant choice 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    if finish_reason is not None:
        return True
    delta = choice.get(_DELTA_FIELD)
    if not isinstance(delta, dict):
        return False
    for field_name in _SSE_SEMANTIC_DELTA_FIELDS:
        if field_name in delta and delta[field_name] is not None:
            return True
    return False


__all__ = [
    "ChoicePolicyError",
    "NON_STREAM_CHOICE_INDEX_NON_ZERO_CODE",
    "NON_STREAM_CHOICE_NOT_OBJECT_CODE",
    "NON_STREAM_INVALID_CHOICE_SHAPE_CODE",
    "NON_STREAM_INVALID_FINISH_REASON_CODE",
    "NON_STREAM_MISSING_CHOICES_CODE",
    "NON_STREAM_MISSING_FINISH_REASON_CODE",
    "NON_STREAM_MULTIPLE_CHOICES_CODE",
    "NON_STREAM_TOOL_CALLS_FINISH_REASON_MISMATCH_CODE",
    "NonStreamChoiceSelection",
    "SSE_CHOICE_INDEX_NON_ZERO_CODE",
    "SSE_CONFLICTING_FINISH_REASON_CODE",
    "SSE_INVALID_CHOICE_SHAPE_CODE",
    "SSE_INVALID_FINISH_REASON_CODE",
    "SSE_MISSING_CHOICES_CODE",
    "SSE_MISSING_FINISH_REASON_CODE",
    "SSE_MULTIPLE_VALID_CHOICES_CODE",
    "SSE_TOOL_CALLS_FINISH_REASON_MISMATCH_CODE",
    "SSEChoiceSelection",
    "validate_non_stream_choice",
    "validate_non_stream_terminal_shape",
    "validate_sse_chunk_choices",
    "validate_sse_terminal_shape",
]
