"""P5 工具声明契约测试。"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from datetime import datetime, timezone

from dayu.contracts import (
    AsyncDirectToolExecutionCapability,
    BatchToolExecutionContext,
    JsonValue,
    ProcessBackedToolContext,
    ProcessBackedToolExecutionCapability,
    ProcessBackedToolTarget,
    ThreadBackedToolExecutionCapability,
    ToolBundle,
    ToolCallRequest,
    ToolCallable,
    ToolCompletedOutcome,
    ToolDefinition,
    ToolDisplayInfo,
    ToolExecutionOutcome,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolResultMeta,
    ToolResultSuccess,
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
    tool,
)


@dataclass(frozen=True, slots=True)
class _PickleRoundTripProcessTarget:
    """测试用 process-backed 目标。

    :param value: 目标返回的 JSON 值。
    """

    value: JsonValue

    def __call__(self) -> JsonValue:
        """返回 completed JSON 信封。

        :returns: process-backed completed 信封。
        :raises Exception: 不主动抛出异常。
        """

        return {"status": "completed", "value": self.value}


@dataclass(frozen=True, slots=True)
class _PickleRoundTripProcessTargetFactory:
    """测试用 process-backed target factory。

    :param value: target 返回值。
    """

    value: JsonValue

    def build_process_target(
        self,
        call: ToolCallRequest,
        context: ProcessBackedToolContext,
    ) -> ProcessBackedToolTarget:
        """构造测试 process target。

        :param call: 单次工具调用请求。
        :param context: 可序列化 process-backed 上下文。
        :returns: 可 pickle 的 process target。
        :raises Exception: 不主动抛出异常。
        """

        del call
        del context
        return _PickleRoundTripProcessTarget(value=self.value)


async def _echo_tool(
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
) -> ToolExecutionOutcome:
    """测试用单工具调用实现。

    :param call: 单次工具调用请求。
    :param context: 批式握手共享的运行期上下文。
    :returns: 直接成功的 outcome。
    :raises Exception: 不主动抛出异常。
    """

    del call
    del context
    now = datetime.now(tz=timezone.utc)
    return ToolCompletedOutcome(
        result=ToolResultSuccess(
            ok=True,
            value={"echo": "ok"},
            meta=ToolResultMeta(
                tool_name="echo",
                started_at=now,
                finished_at=now,
            ),
        )
    )


def _parameters() -> ToolParametersSchema:
    """构造测试参数 schema。

    :returns: 参数 schema。
    :raises Exception: 不主动抛出异常。
    """

    return ToolParametersSchema(
        type="object",
        properties={"text": {"type": "string"}},
        required=("text",),
        additional_properties=False,
    )


def _truncate_spec() -> ToolTruncateSpec:
    """构造测试截断声明。

    :returns: 截断声明。
    :raises Exception: 不主动抛出异常。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": 8},
        target_field=None,
        field_path=None,
        ttl_seconds=60,
    )


def test_tool_declaration_keeps_schema_runtime_and_display_metadata_separate() -> None:
    """``@tool`` 同源声明，但投影给 Engine 时只剩 ``ToolSchema``。"""

    definition = tool(
        name="huge_echo",
        description="return a large echo",
        parameters=_parameters(),
        truncate=_truncate_spec(),
        display_name="Huge Echo",
        tags=("smoke", "phase5"),
    )(_echo_tool)
    bundle = ToolBundle(definitions=(definition,))

    projected = definition.to_tool_schema()
    bundle_projected = bundle.to_tool_schemas()
    truncate_specs = bundle.truncate_specs()

    assert definition.name == "huge_echo"
    assert definition.callable is _echo_tool
    assert definition.execution == AsyncDirectToolExecutionCapability()
    assert isinstance(definition.callable, ToolCallable)
    assert not hasattr(definition, "executor")
    assert definition.truncate == _truncate_spec()
    assert definition.display == ToolDisplayInfo(name="Huge Echo")
    assert not hasattr(definition, "display_name")
    assert definition.tags == ("smoke", "phase5")
    assert isinstance(projected, ToolSchema)
    assert bundle_projected == (projected,)
    assert truncate_specs == {"huge_echo": _truncate_spec()}
    assert projected.function.name == "huge_echo"
    assert projected.function.description == "return a large echo"
    assert projected.function.parameters == _parameters()
    assert not hasattr(projected, "callable")
    assert not hasattr(projected, "truncate")
    assert not hasattr(projected, "display")
    assert not hasattr(projected, "display_name")
    assert not hasattr(projected, "tags")
    assert "fetch_more" not in projected.function.parameters.properties


def test_tool_definition_rejects_name_schema_mismatch() -> None:
    """手动构造声明时，工具名必须与 LLM-facing schema 同源。"""

    schema = ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="schema_name",
            description="schema tool",
            parameters=_parameters(),
        ),
    )

    try:
        ToolDefinition(
            name="runtime_name",
            schema=schema,
            callable=_echo_tool,
            execution=AsyncDirectToolExecutionCapability(),
            truncate=_truncate_spec(),
            display=None,
            tags=(),
        )
    except ValueError as exc:
        assert str(exc) == "ToolDefinition name must match schema.function.name"
    else:
        raise AssertionError("mismatched tool definition was accepted")


def test_tool_definition_rejects_empty_name() -> None:
    """手动构造声明时，工具名不能为空。"""

    schema = ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="",
            description="schema tool",
            parameters=_parameters(),
        ),
    )

    try:
        ToolDefinition(
            name="",
            schema=schema,
            callable=_echo_tool,
            execution=AsyncDirectToolExecutionCapability(),
            truncate=_truncate_spec(),
            display=None,
            tags=(),
        )
    except ValueError as exc:
        assert str(exc) == "ToolDefinition name must be non-empty"
    else:
        raise AssertionError("empty tool definition name was accepted")


def test_tool_display_info_rejects_empty_name() -> None:
    """工具展示名称不能为空。"""

    try:
        ToolDisplayInfo(name="  ")
    except ValueError as exc:
        assert str(exc) == "ToolDisplayInfo.name must be non-empty"
    else:
        raise AssertionError("empty tool display name was accepted")


def test_tool_bundle_rejects_public_empty_definitions() -> None:
    """调用方默认不得直接构造空 ``ToolBundle``。"""

    try:
        ToolBundle(definitions=())
    except ValueError as exc:
        assert str(exc) == "ToolBundle.definitions must be non-empty"
    else:
        raise AssertionError("empty tool bundle was accepted")


def test_tool_bundle_internal_empty_constructor_keeps_real_type() -> None:
    """框架 no-tool 路径可构造类型真实的空 ``ToolBundle``。"""

    bundle = ToolBundle(definitions=(), _allow_empty=True)

    assert isinstance(bundle, ToolBundle)
    assert bundle.definitions == ()
    assert bundle.to_tool_schemas() == ()
    assert bundle.truncate_specs() == {}


def test_tool_bundle_rejects_duplicate_tool_name() -> None:
    """bundle 拒绝重复工具名，避免截断声明静默覆盖。"""

    first = tool(
        name="duplicated",
        description="first",
        parameters=_parameters(),
        truncate=_truncate_spec(),
    )(_echo_tool)
    second = tool(
        name="duplicated",
        description="second",
        parameters=_parameters(),
        truncate=None,
    )(_echo_tool)

    try:
        ToolBundle(definitions=(first, second))
    except ValueError as exc:
        assert str(exc) == "duplicate tool name: duplicated"
    else:
        raise AssertionError("duplicate tool bundle was accepted")


def test_tool_decorator_accepts_explicit_execution_capability() -> None:
    """``@tool`` 支持显式声明非默认 execution capability。"""

    definition = tool(
        name="thread_echo",
        description="return an echo from thread boundary",
        parameters=_parameters(),
        execution=ThreadBackedToolExecutionCapability(),
    )(_echo_tool)

    assert definition.execution == ThreadBackedToolExecutionCapability()
    assert definition.to_tool_schema().function.name == "thread_echo"


def test_thread_backed_capability_guard_is_always_false() -> None:
    """thread_backed 不能作为生产非协作 blocking cancel closeout 证据。"""

    capability = ThreadBackedToolExecutionCapability()

    assert capability.production_safe_non_cooperative_cancel is False


def test_process_backed_context_target_and_envelope_pickle_round_trip() -> None:
    """process-backed context、target 与 JSON 信封必须可 pickle round-trip。"""

    context = ProcessBackedToolContext(
        run_id="run-1",
        session_id="session-1",
        iteration_id="iteration-1",
        timeout_seconds=3.5,
        correlation_id="run-1:iteration-1:tool_batch",
    )
    call = ToolCallRequest(
        tool_call_id="call-1",
        name="process_echo",
        arguments={"text": "hello"},
        index_in_iteration=0,
        provider_state=None,
    )
    factory = _PickleRoundTripProcessTargetFactory(value={"echo": "hello"})
    capability = ProcessBackedToolExecutionCapability(target_factory=factory)

    restored_context = pickle.loads(pickle.dumps(context))
    restored_factory = pickle.loads(pickle.dumps(capability.target_factory))
    target = restored_factory.build_process_target(call, restored_context)
    restored_target = pickle.loads(pickle.dumps(target))
    envelope = restored_target()
    restored_envelope = pickle.loads(pickle.dumps(envelope))

    assert restored_context == context
    assert restored_envelope == {
        "status": "completed",
        "value": {"echo": "hello"},
    }
