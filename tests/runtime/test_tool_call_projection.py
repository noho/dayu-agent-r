"""``dayu.runtime.tool_call_projection`` 参数投影与 outcome helper 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest

from dayu.contracts import (
    JsonValue,
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCallRequest,
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolFailedOutcome,
    ToolParametersSchema,
)
from dayu.runtime.tool_call_projection import (
    INVALID_ARGUMENT_ERROR,
    ToolArgumentValidationFailure,
    ToolBusinessCancelled,
    ValidatedToolArguments,
    completed_outcome,
    failed_outcome,
    host_cancelled_outcome,
    validate_and_project_arguments,
)

_TOOL_NAME = "sample_tool"
_STARTED_AT = datetime(2026, 6, 10, 8, 0, 0, tzinfo=UTC)
_FINISHED_AT = _STARTED_AT + timedelta(seconds=2)


def test_validate_arguments_accepts_valid_values_and_applies_defaults() -> None:
    """合法参数应保留显式值，并按 schema 注入默认值。"""

    schema = _schema(
        properties={
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            "recursive": {"type": "boolean", "default": False},
        },
        required=("query",),
    )

    result = validate_and_project_arguments(
        _call({"query": "revenue"}),
        _TOOL_NAME,
        schema,
    )

    assert isinstance(result, ValidatedToolArguments)
    assert result.arguments == {
        "query": "revenue",
        "limit": 5,
        "recursive": False,
    }


def test_validate_arguments_rejects_missing_required_field() -> None:
    """缺少 required 字段时应返回固定 invalid_argument 失败。"""

    result = validate_and_project_arguments(
        _call({}),
        _TOOL_NAME,
        _schema(
            properties={"query": {"type": "string"}},
            required=("query",),
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name == "query"
    assert "Missing required" in failure.message


def test_validate_arguments_rejects_unknown_field_when_additional_false() -> None:
    """additional_properties=false 时未知字段不得穿透到 callable。"""

    result = validate_and_project_arguments(
        _call({"query": "revenue", "run_id": "run-secret"}),
        _TOOL_NAME,
        _schema(
            properties={"query": {"type": "string"}},
            required=("query",),
            additional_properties=False,
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name == "run_id"
    assert "Unsupported tool argument fields" in failure.message


def test_validate_arguments_rejects_wrong_tool_name() -> None:
    """call.name 与 callable 工具名不一致时应 fail closed。"""

    result = validate_and_project_arguments(
        _call({"query": "revenue"}, name="other_tool"),
        _TOOL_NAME,
        _schema(
            properties={"query": {"type": "string"}},
            required=("query",),
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name is None
    assert "does not match" in failure.message


def test_validate_arguments_checks_enum_and_string_bounds() -> None:
    """字符串字段应校验长度边界和 enum。"""

    schema = _schema(
        properties={
            "mode": {
                "type": "string",
                "enum": ["auto", "exact"],
                "minLength": 3,
                "maxLength": 5,
            }
        },
        required=("mode",),
    )

    enum_result = validate_and_project_arguments(
        _call({"mode": "other"}),
        _TOOL_NAME,
        schema,
    )
    short_result = validate_and_project_arguments(
        _call({"mode": "a"}),
        _TOOL_NAME,
        schema,
    )

    assert "one of" in _assert_validation_failure(enum_result).message
    assert "at least 3 characters" in _assert_validation_failure(short_result).message


def test_validate_arguments_integer_rejects_bool() -> None:
    """integer 字段必须拒绝 Python bool。"""

    result = validate_and_project_arguments(
        _call({"limit": True}),
        _TOOL_NAME,
        _schema(
            properties={"limit": {"type": "integer", "minimum": 1}},
            required=("limit",),
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name == "limit"
    assert "must be integer" in failure.message


def test_validate_arguments_integer_rejects_out_of_range_value() -> None:
    """integer 字段应直接覆盖 maximum 越界失败路径。"""

    result = validate_and_project_arguments(
        _call({"limit": 10}),
        _TOOL_NAME,
        _schema(
            properties={"limit": {"type": "integer", "minimum": 1, "maximum": 5}},
            required=("limit",),
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name == "limit"
    assert "<= 5" in failure.message


def test_validate_arguments_number_rejects_out_of_range_value() -> None:
    """number 字段应直接覆盖 minimum 越界失败路径。"""

    result = validate_and_project_arguments(
        _call({"score": 0.25}),
        _TOOL_NAME,
        _schema(
            properties={"score": {"type": "number", "minimum": 0.5, "maximum": 1.0}},
            required=("score",),
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name == "score"
    assert ">= 0.5" in failure.message


def test_validate_arguments_rejects_non_finite_number_default() -> None:
    """number 字段默认值为非有限浮点数时必须拒绝。"""

    result = validate_and_project_arguments(
        _call({}),
        _TOOL_NAME,
        _schema(
            properties={"score": {"type": "number", "default": float("inf")}},
            required=(),
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name == "score"
    assert "finite number" in failure.message


def test_validate_arguments_rejects_non_finite_number_argument() -> None:
    """number 字段直接参数为非有限浮点数时必须拒绝。"""

    result = validate_and_project_arguments(
        _call_with_unchecked_arguments({"score": float("inf")}),
        _TOOL_NAME,
        _schema(
            properties={"score": {"type": "number"}},
            required=("score",),
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name == "score"
    assert "finite number" in failure.message


def test_validate_arguments_projects_integral_float_to_integer() -> None:
    """integer 字段沿用当前 adapter 行为，把 3.0 投影为 3。"""

    result = validate_and_project_arguments(
        _call({"limit": 3.0}),
        _TOOL_NAME,
        _schema(
            properties={"limit": {"type": "integer", "minimum": 1, "maximum": 5}},
            required=("limit",),
        ),
    )

    assert isinstance(result, ValidatedToolArguments)
    assert result.arguments == {"limit": 3}


def test_validate_arguments_boolean_rejects_non_bool_value() -> None:
    """boolean 字段必须拒绝字符串等非 bool 值。"""

    result = validate_and_project_arguments(
        _call({"recursive": "true"}),
        _TOOL_NAME,
        _schema(
            properties={"recursive": {"type": "boolean"}},
            required=("recursive",),
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name == "recursive"
    assert "must be boolean" in failure.message


def test_validate_arguments_object_rejects_non_mapping_value() -> None:
    """object 字段必须拒绝 list 等非映射值。"""

    result = validate_and_project_arguments(
        _call({"filters": ["region"]}),
        _TOOL_NAME,
        _schema(
            properties={"filters": {"type": "object"}},
            required=("filters",),
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name == "filters"
    assert "must be object" in failure.message


def test_validate_arguments_checks_array_items_and_bounds() -> None:
    """数组字段应校验数量边界与 scalar items。"""

    schema = _schema(
        properties={
            "domains": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 2,
            }
        },
        required=("domains",),
    )

    valid_result = validate_and_project_arguments(
        _call({"domains": ["example.com", "sec.gov"]}),
        _TOOL_NAME,
        schema,
    )
    too_many_result = validate_and_project_arguments(
        _call({"domains": ["a.com", "b.com", "c.com"]}),
        _TOOL_NAME,
        schema,
    )
    item_result = validate_and_project_arguments(
        _call({"domains": ["example.com", 3]}),
        _TOOL_NAME,
        schema,
    )

    assert isinstance(valid_result, ValidatedToolArguments)
    assert valid_result.arguments == {"domains": ["example.com", "sec.gov"]}
    assert "at most 2 items" in _assert_validation_failure(too_many_result).message
    assert _assert_validation_failure(item_result).field_name == "domains[1]"


def test_validate_arguments_rejects_unsupported_advanced_schema_keyword() -> None:
    """未实现的高级 JSON Schema 关键字必须 fail closed。"""

    result = validate_and_project_arguments(
        _call({"query": "revenue"}),
        _TOOL_NAME,
        _schema(
            properties={
                "query": {
                    "type": "string",
                    "oneOf": [{"const": "revenue"}],
                }
            },
            required=("query",),
        ),
    )

    failure = _assert_validation_failure(result)
    assert failure.error == INVALID_ARGUMENT_ERROR
    assert failure.field_name == "query"
    assert "unsupported keyword 'oneOf'" in failure.message


def test_validate_arguments_preserves_unknown_fields_when_additional_true() -> None:
    """additional_properties=true 时 helper 只校验声明字段并保留额外 JSON 字段。"""

    result = validate_and_project_arguments(
        _call({"query": "revenue", "source": "sec"}),
        _TOOL_NAME,
        _schema(
            properties={"query": {"type": "string"}},
            required=("query",),
            additional_properties=True,
        ),
    )

    assert isinstance(result, ValidatedToolArguments)
    assert result.arguments == {"query": "revenue", "source": "sec"}


def test_completed_failed_and_cancelled_outcomes_share_meta() -> None:
    """三类 helper 构造的终态都应携带一致 ToolResultMeta。"""

    completed = completed_outcome(
        tool_name=_TOOL_NAME,
        value={"ok_value": True},
        started_at=_STARTED_AT,
        finished_at=_FINISHED_AT,
    )
    failed = failed_outcome(
        tool_name=_TOOL_NAME,
        error="business_error",
        message="业务失败",
        hint="缩小范围后重试",
        started_at=_STARTED_AT,
        finished_at=_FINISHED_AT,
    )
    cancelled = host_cancelled_outcome(
        tool_name=_TOOL_NAME,
        started_at=_STARTED_AT,
        finished_at=_FINISHED_AT,
        message="用户取消了工具调用",
        hint="稍后重试",
    )

    assert isinstance(completed, ToolCompletedOutcome)
    assert isinstance(failed, ToolFailedOutcome)
    assert isinstance(cancelled, ToolCancelledOutcome)
    for meta in (
        completed.result.meta,
        failed.result.meta,
        cancelled.meta,
    ):
        assert meta is not None
        assert meta.tool_name == _TOOL_NAME
        assert meta.started_at == _STARTED_AT
        assert meta.finished_at == _FINISHED_AT


def test_failed_outcome_normalizes_blank_error_message_and_hint() -> None:
    """失败 outcome helper 应避免构造空白错误码、说明和 hint。"""

    outcome = failed_outcome(
        tool_name=_TOOL_NAME,
        error=" ",
        message=" ",
        hint=" ",
        started_at=_STARTED_AT,
        finished_at=_FINISHED_AT,
    )

    assert outcome.result.error == "execution_error"
    assert outcome.result.message == "Tool execution failed."
    assert outcome.result.hint is None


def test_host_cancelled_outcome_requires_explicit_message_and_hint() -> None:
    """取消 outcome helper 不提供 runtime 默认 Host 治理文案。"""

    with pytest.raises(ValueError, match="message"):
        host_cancelled_outcome(
            tool_name=_TOOL_NAME,
            started_at=_STARTED_AT,
            finished_at=_FINISHED_AT,
            message=" ",
            hint="稍后重试",
        )

    with pytest.raises(ValueError, match="hint"):
        host_cancelled_outcome(
            tool_name=_TOOL_NAME,
            started_at=_STARTED_AT,
            finished_at=_FINISHED_AT,
            message="工具调用已停止",
            hint=" ",
        )


def test_tool_business_cancelled_requires_explicit_message_and_hint() -> None:
    """业务取消传递对象要求调用方显式提供 LLM-facing 文案。"""

    with pytest.raises(ValueError, match="message"):
        ToolBusinessCancelled(message=" ", hint="稍后重试")

    with pytest.raises(ValueError, match="hint"):
        ToolBusinessCancelled(message="工具调用已停止", hint=" ")


def _schema(
    *,
    properties: Mapping[str, JsonValue],
    required: tuple[str, ...],
    additional_properties: bool | None = None,
) -> ToolParametersSchema:
    """构造测试用参数 schema。

    :param properties: 顶层字段 schema。
    :param required: 必填字段名。
    :param additional_properties: additionalProperties 投影。
    :returns: ``ToolParametersSchema``。
    """

    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=required,
        additional_properties=additional_properties,
    )


def _call(
    arguments: Mapping[str, JsonValue],
    *,
    name: str = _TOOL_NAME,
) -> ToolCallRequest:
    """构造测试用工具调用请求。

    :param arguments: 工具参数。
    :param name: 工具名。
    :returns: ``ToolCallRequest``。
    """

    return ToolCallRequest(
        tool_call_id="call-1",
        name=name,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _call_with_unchecked_arguments(arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造绕过契约 JSON 有限数校验的测试调用。

    :param arguments: 要直接送入 helper 的参数映射。
    :returns: 已替换参数映射的 ``ToolCallRequest``。
    :raises Exception: 底层 dataclass 字段替换失败时透出。
    """

    call = _call({})
    # 仅用于覆盖 helper 的防御性非有限 number 分支；正常契约构造会更早拒绝。
    object.__setattr__(call, "arguments", arguments)
    return call


def _assert_validation_failure(
    result: ValidatedToolArguments | ToolArgumentValidationFailure,
) -> ToolArgumentValidationFailure:
    """断言校验结果为失败并返回失败对象。

    :param result: 参数校验结果。
    :returns: ``ToolArgumentValidationFailure``。
    :raises AssertionError: 结果不是失败对象时抛出。
    """

    assert isinstance(result, ToolArgumentValidationFailure)
    return result
