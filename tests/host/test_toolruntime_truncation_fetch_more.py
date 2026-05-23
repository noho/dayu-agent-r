"""Host ToolRuntime P6-S4 截断与 fetch_more 测试。"""

from __future__ import annotations

import base64
from dataclasses import replace
from datetime import datetime

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    FetchMoreToolCallable,
    HostEventRef,
    HostPayloadRef,
    HostToolFactAcceptPort,
    TextCharsRemainderRef,
    ToolAcceptRetryPolicy,
    ToolFactAcceptCandidate,
    ToolFactAcceptResult,
    ToolFactAcceptedAck,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
    ToolRuntimeHandle,
    TruncationManager,
)
from dayu.host.tooling import (
    FrameworkToolName,
    FrameworkToolPolicyView,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
)
from dayu.runtime.tool_truncation import effective_tool_truncate_spec

_SESSION_ID = "session-truncation"
_RUN_ID = "run-truncation"
_ATTEMPT_ID = "attempt-truncation"
_EXECUTION_ID = "execution-truncation"
_ITERATION_ID = "iteration-truncation"
_POLICY_DIGEST = "sha256:4444444444444444444444444444444444444444444444444444444444444444"
_DEFAULT_TEXT_CHARS_LIMIT = 8
_DEFAULT_TTL_SECONDS = 30


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终为 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        """

        return None


class _TextTool:
    """返回固定 JSON 值并记录调用次数的测试工具。"""

    def __init__(self, value: JsonValue) -> None:
        """初始化测试工具。

        :param value: 工具返回 JSON 值。
        :returns: ``None``。
        """

        self._value = value
        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回固定文本。

        :param call: 单次工具调用请求。
        :param context: 批式工具上下文。
        :returns: 成功 outcome。
        """

        del call, context
        self.call_count += 1
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value=self._value, meta=None)
        )


class _AcceptingPort(HostToolFactAcceptPort):
    """始终 accepted 的测试 accept port。"""

    def __init__(self) -> None:
        """初始化测试 port。

        :returns: ``None``。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """记录 candidate 并返回 accepted ack。

        :param candidate: 工具事实候选。
        :returns: accepted ack。
        """

        self.candidates.append(candidate)
        return _accepted_ack(candidate)


def test_truncate_declaration_allows_missing_limit_and_ttl() -> None:
    """截断声明允许省略策略 limit 与 TTL，由 effective helper 补齐。"""

    declaration = ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={},
        target_field=None,
        field_path=None,
        ttl_seconds=None,
    )

    effective = effective_tool_truncate_spec(
        declaration,
        default_limits_by_strategy={
            ToolTruncationStrategy.TEXT_CHARS: _DEFAULT_TEXT_CHARS_LIMIT,
        },
        default_ttl_seconds=_DEFAULT_TTL_SECONDS,
    )

    assert effective.limits == {"max_chars": _DEFAULT_TEXT_CHARS_LIMIT}
    assert effective.ttl_seconds == _DEFAULT_TTL_SECONDS


def test_truncate_declaration_rejects_ambiguous_target() -> None:
    """截断声明不能同时设置 target_field 与 field_path。"""

    with pytest.raises(ValueError, match="target_field and field_path"):
        ToolTruncateSpec(
            enabled=True,
            strategy=ToolTruncationStrategy.TEXT_CHARS,
            limits={},
            target_field="value",
            field_path=("payload",),
            ttl_seconds=None,
        )


@pytest.mark.asyncio
async def test_truncated_result_exposes_only_cursor_and_scope_token() -> None:
    """普通工具截断结果只暴露不透明 cursor 与 scope token。"""

    tool = _TextTool("ABCDEFGHIJ")
    handle, accept_port = _handle(tool, _truncate_spec(max_chars=4))

    outcome = await handle.tool_executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolCompletedOutcome)
    value = record.outcome.result.value
    assert isinstance(value, dict)
    assert value["truncated"] is True
    assert value["value"] == "ABCD"
    fetch_more = value["fetch_more"]
    assert isinstance(fetch_more, dict)
    assert isinstance(fetch_more["cursor"], str)
    assert isinstance(fetch_more["scope_token"], str)
    assert "EFGHIJ" not in str(value)
    assert accept_port.candidates[0].truncation is not None
    assert accept_port.candidates[0].truncation.cursor_hint == fetch_more["cursor"]


@pytest.mark.asyncio
async def test_fetch_more_dispatches_as_normal_tool_and_is_single_use() -> None:
    """fetch_more 走普通 executor / accept path，且 cursor 只能使用一次。"""

    tool = _TextTool("ABCDEFGHIJ")
    handle, accept_port = _handle(tool, _truncate_spec(max_chars=4))
    cursor, scope_token = await _create_cursor(handle)

    first = await handle.tool_executor.execute(
        _request(_fetch_more_call("fetch-call-1", cursor, scope_token))
    )
    second = await handle.tool_executor.execute(
        _request(_fetch_more_call("fetch-call-2", cursor, scope_token))
    )

    first_outcome = first.records[0].outcome
    second_outcome = second.records[0].outcome
    assert isinstance(first_outcome, ToolCompletedOutcome)
    assert first_outcome.result.value == "EFGHIJ"
    assert cursor not in _manager_from_handle(handle)._cursors
    assert isinstance(second_outcome, ToolFailedOutcome)
    assert second_outcome.result.hint == "missing_cursor"
    assert [candidate.tool_name for candidate in accept_port.candidates] == [
        "fake_tool",
        "fetch_more",
        "fetch_more",
    ]
    assert tool.call_count == 1


@pytest.mark.asyncio
async def test_text_lines_truncation_fetch_more_returns_remaining_lines() -> None:
    """text_lines 截断只公开可见行并通过 fetch_more 补读剩余行。"""

    handle, _accept_port = _handle(
        _TextTool("line-1\nline-2\nline-3\nline-4"),
        _truncate_strategy_spec(
            strategy=ToolTruncationStrategy.TEXT_LINES,
            limits={"max_lines": 2},
        ),
    )

    outcome = await handle.tool_executor.execute(_request(_call("tool-call-1")))
    record = outcome.records[0]
    assert isinstance(record.outcome, ToolCompletedOutcome)
    value = record.outcome.result.value
    assert isinstance(value, dict)
    assert value["value"] == "line-1\nline-2"
    fetch_more = value["fetch_more"]
    assert isinstance(fetch_more, dict)
    fetched = await handle.tool_executor.execute(
        _request(
            _fetch_more_call(
                "fetch-call-1",
                str(fetch_more["cursor"]),
                str(fetch_more["scope_token"]),
            )
        )
    )

    fetched_record = fetched.records[0]
    assert isinstance(fetched_record.outcome, ToolCompletedOutcome)
    assert fetched_record.outcome.result.value == "line-3\nline-4"


@pytest.mark.asyncio
async def test_list_items_truncation_fetch_more_returns_remaining_items() -> None:
    """list_items 截断只公开可见项并通过 fetch_more 补读剩余项。"""

    handle, _accept_port = _handle(
        _TextTool(["first", {"second": True}, 3]),
        _truncate_strategy_spec(
            strategy=ToolTruncationStrategy.LIST_ITEMS,
            limits={"max_items": 1},
        ),
    )

    outcome = await handle.tool_executor.execute(_request(_call("tool-call-1")))
    record = outcome.records[0]
    assert isinstance(record.outcome, ToolCompletedOutcome)
    value = record.outcome.result.value
    assert isinstance(value, dict)
    assert value["value"] == ["first"]
    fetch_more = value["fetch_more"]
    assert isinstance(fetch_more, dict)
    fetched = await handle.tool_executor.execute(
        _request(
            _fetch_more_call(
                "fetch-call-1",
                str(fetch_more["cursor"]),
                str(fetch_more["scope_token"]),
            )
        )
    )

    fetched_record = fetched.records[0]
    assert isinstance(fetched_record.outcome, ToolCompletedOutcome)
    assert fetched_record.outcome.result.value == [{"second": True}, 3]


@pytest.mark.asyncio
async def test_binary_bytes_truncation_fetch_more_returns_base64_remainder() -> None:
    """binary_bytes 截断 base64 字符串并按字节补读 base64 剩余内容。"""

    encoded = base64.b64encode(b"abcdef").decode("ascii")
    handle, _accept_port = _handle(
        _TextTool(encoded),
        _truncate_strategy_spec(
            strategy=ToolTruncationStrategy.BINARY_BYTES,
            limits={"max_bytes": 2},
        ),
    )

    outcome = await handle.tool_executor.execute(_request(_call("tool-call-1")))
    record = outcome.records[0]
    assert isinstance(record.outcome, ToolCompletedOutcome)
    value = record.outcome.result.value
    assert isinstance(value, dict)
    assert value["value"] == base64.b64encode(b"ab").decode("ascii")
    fetch_more = value["fetch_more"]
    assert isinstance(fetch_more, dict)
    fetched = await handle.tool_executor.execute(
        _request(
            _fetch_more_call(
                "fetch-call-1",
                str(fetch_more["cursor"]),
                str(fetch_more["scope_token"]),
                limit=2,
            )
        )
    )

    fetched_record = fetched.records[0]
    assert isinstance(fetched_record.outcome, ToolCompletedOutcome)
    assert fetched_record.outcome.result.value == base64.b64encode(b"cd").decode(
        "ascii"
    )


@pytest.mark.asyncio
async def test_fetch_more_limit_returns_prefix_of_remaining_value() -> None:
    """fetch_more 的 limit 只返回剩余内容前缀。"""

    handle, _accept_port = _handle(_TextTool("ABCDEFGHIJ"), _truncate_spec(max_chars=4))
    cursor, scope_token = await _create_cursor(handle)

    outcome = await handle.tool_executor.execute(
        _request(_fetch_more_call("fetch-call-1", cursor, scope_token, limit=2))
    )

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolCompletedOutcome)
    assert record.outcome.result.value == "EF"


@pytest.mark.asyncio
async def test_fetch_more_missing_cursor_returns_ordinary_tool_error() -> None:
    """不存在 cursor 时 fetch_more 返回普通工具错误。"""

    handle, _accept_port = _handle(_TextTool("ABCDEFGHIJ"), _truncate_spec(max_chars=4))

    outcome = await handle.tool_executor.execute(
        _request(_fetch_more_call("fetch-call-1", "missing", "token"))
    )

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "missing_cursor"


@pytest.mark.asyncio
async def test_fetch_more_rejects_token_mismatch() -> None:
    """scope token 不匹配时 fetch_more 返回普通工具错误。"""

    handle, _accept_port = _handle(_TextTool("ABCDEFGHIJ"), _truncate_spec(max_chars=4))
    cursor, _scope_token = await _create_cursor(handle)

    outcome = await handle.tool_executor.execute(
        _request(_fetch_more_call("fetch-call-1", cursor, "wrong-token"))
    )

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "scope_token_mismatch"


@pytest.mark.asyncio
async def test_fetch_more_rejects_used_cursor() -> None:
    """cursor 已标记使用时 fetch_more 返回普通工具错误。"""

    handle, _accept_port = _handle(_TextTool("ABCDEFGHIJ"), _truncate_spec(max_chars=4))
    cursor, scope_token = await _create_cursor(handle)
    manager = _manager_from_handle(handle)
    stored = manager._cursors[cursor]
    manager._cursors[cursor] = replace(stored, used_at=stored.created_at)

    outcome = await handle.tool_executor.execute(
        _request(_fetch_more_call("fetch-call-1", cursor, scope_token))
    )

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "cursor_already_used"


@pytest.mark.asyncio
async def test_fetch_more_rejects_invalid_limit() -> None:
    """非正 limit 在 fetch_more 普通工具路径中返回普通工具错误。"""

    handle, _accept_port = _handle(_TextTool("ABCDEFGHIJ"), _truncate_spec(max_chars=4))
    cursor, scope_token = await _create_cursor(handle)

    outcome = await handle.tool_executor.execute(
        _request(_fetch_more_call("fetch-call-1", cursor, scope_token, limit=0))
    )

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "invalid_fetch_more_request"


@pytest.mark.asyncio
async def test_fetch_more_rejects_ttl_expiry() -> None:
    """TTL 过期时 fetch_more 返回普通工具错误。"""

    handle, _accept_port = _handle(_TextTool("ABCDEFGHIJ"), _truncate_spec(max_chars=4, ttl_seconds=0))
    cursor, scope_token = await _create_cursor(handle)

    outcome = await handle.tool_executor.execute(
        _request(_fetch_more_call("fetch-call-1", cursor, scope_token))
    )

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "cursor_expired"
    assert cursor not in _manager_from_handle(handle)._cursors


@pytest.mark.asyncio
async def test_store_cursor_cleans_expired_cursors_bounded() -> None:
    """新增 cursor 时有界清理已过期 cursor。"""

    handle, _accept_port = _handle(_TextTool("ABCDEFGHIJ"), _truncate_spec(max_chars=4))
    first_cursor, _first_scope_token = await _create_cursor(handle)
    manager = _manager_from_handle(handle)
    stored = manager._cursors[first_cursor]
    manager._cursors[first_cursor] = replace(
        stored,
        expires_at=stored.created_at,
    )

    second_cursor, _second_scope_token = await _create_cursor(handle)

    assert first_cursor not in manager._cursors
    assert second_cursor in manager._cursors


@pytest.mark.asyncio
async def test_fetch_more_rejects_scope_mismatch() -> None:
    """cursor scope 不匹配时 fetch_more 返回普通工具错误。"""

    handle, _accept_port = _handle(_TextTool("ABCDEFGHIJ"), _truncate_spec(max_chars=4))
    cursor, scope_token = await _create_cursor(handle)
    manager = _manager_from_handle(handle)
    stored = manager._cursors[cursor]
    manager._cursors[cursor] = replace(stored, run_id="other-run")

    outcome = await handle.tool_executor.execute(
        _request(_fetch_more_call("fetch-call-1", cursor, scope_token))
    )

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "scope_mismatch"


@pytest.mark.asyncio
async def test_fetch_more_rejects_remainder_digest_mismatch() -> None:
    """剩余内容 digest 不匹配时 fetch_more 返回普通工具错误。"""

    handle, _accept_port = _handle(_TextTool("ABCDEFGHIJ"), _truncate_spec(max_chars=4))
    cursor, scope_token = await _create_cursor(handle)
    manager = _manager_from_handle(handle)
    stored = manager._cursors[cursor]
    assert isinstance(stored.remaining_ref, TextCharsRemainderRef)
    manager._cursors[cursor] = replace(
        stored,
        remaining_ref=TextCharsRemainderRef(
            remaining_text="tampered",
            digest=stored.remaining_ref.digest,
        ),
    )

    outcome = await handle.tool_executor.execute(
        _request(_fetch_more_call("fetch-call-1", cursor, scope_token))
    )

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "remainder_digest_mismatch"


def _handle(
    tool: _TextTool,
    truncate_spec: ToolTruncateSpec,
) -> tuple[ToolRuntimeHandle, _AcceptingPort]:
    """构造启用 truncation / fetch_more 的 ToolRuntimeHandle。

    :param tool: 测试工具 callable。
    :param truncate_spec: 截断声明。
    :returns: handle 与 accept port。
    """

    accept_port = _AcceptingPort()
    handle = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(
                    definitions=(_definition(tool, truncate_spec),)
                ),
                source_refs=(_source_ref(),),
                framework_tool_policy=FrameworkToolPolicyView(
                    reserved_framework_tool_names=frozenset(
                        {FrameworkToolName.FETCH_MORE}
                    ),
                    enabled_framework_tools=frozenset({FrameworkToolName.FETCH_MORE}),
                ),
                policy_snapshot_digest=_POLICY_DIGEST,
                enable_truncation_manager=True,
            ),
            execution_scope=ToolRuntimeExecutionScope(
                session_id=_SESSION_ID,
                run_id=_RUN_ID,
                attempt_id=_ATTEMPT_ID,
                execution_id=_EXECUTION_ID,
                allow_tool_calls=True,
            ),
            accept_port=accept_port,
            retry_policy=ToolAcceptRetryPolicy(max_attempts=1, backoff_seconds=0.0),
        )
    )
    return handle, accept_port


async def _create_cursor(handle: ToolRuntimeHandle) -> tuple[str, str]:
    """执行一次普通工具调用并提取 cursor 与 scope token。

    :param handle: ToolRuntime handle。
    :returns: cursor 与 scope token。
    """

    outcome = await handle.tool_executor.execute(_request(_call("tool-call-1")))
    record = outcome.records[0]
    assert isinstance(record.outcome, ToolCompletedOutcome)
    value = record.outcome.result.value
    assert isinstance(value, dict)
    fetch_more = value["fetch_more"]
    assert isinstance(fetch_more, dict)
    cursor = fetch_more["cursor"]
    scope_token = fetch_more["scope_token"]
    assert isinstance(cursor, str)
    assert isinstance(scope_token, str)
    return cursor, scope_token


def _manager_from_handle(handle: ToolRuntimeHandle) -> TruncationManager:
    """从注入的 fetch_more callable 读取测试中的 manager。

    :param handle: ToolRuntime handle。
    :returns: TruncationManager。
    :raises AssertionError: manager 未绑定时抛出。
    """

    callable_ = handle.effective_bundle.fetch_more_callable
    assert isinstance(callable_, FetchMoreToolCallable)
    manager = callable_._manager
    assert isinstance(manager, TruncationManager)
    return manager


def _request(*calls: ToolCallRequest) -> BatchToolExecutionRequest:
    """构造批式工具执行请求。

    :param calls: 工具调用请求。
    :returns: 批式工具请求。
    """

    return BatchToolExecutionRequest(
        calls=calls,
        context=BatchToolExecutionContext(
            run_id=_RUN_ID,
            session_id=_SESSION_ID,
            iteration_id=_ITERATION_ID,
            timeout_seconds=10.0,
            cancellation_token=_OpenCancellationToken(),
            correlation_id="correlation-truncation",
        ),
    )


def _call(tool_call_id: str) -> ToolCallRequest:
    """构造普通 fake tool 调用。

    :param tool_call_id: 工具调用 id。
    :returns: 工具调用请求。
    """

    return ToolCallRequest(
        tool_call_id=tool_call_id,
        name="fake_tool",
        arguments={"ticker": "DAYU"},
        index_in_iteration=0,
        provider_state=None,
    )


def _fetch_more_call(
    tool_call_id: str,
    cursor: str,
    scope_token: str,
    *,
    limit: int | None = None,
) -> ToolCallRequest:
    """构造 fetch_more 工具调用。

    :param tool_call_id: 工具调用 id。
    :param cursor: cursor。
    :param scope_token: scope token。
    :param limit: 可选补读上限。
    :returns: 工具调用请求。
    """

    arguments: dict[str, JsonValue] = {"cursor": cursor, "scope_token": scope_token}
    if limit is not None:
        arguments["limit"] = limit
    return ToolCallRequest(
        tool_call_id=tool_call_id,
        name=FrameworkToolName.FETCH_MORE.value,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _definition(tool: _TextTool, truncate_spec: ToolTruncateSpec) -> ToolDefinition:
    """构造带截断声明的 fake tool definition。

    :param tool: 测试工具 callable。
    :param truncate_spec: 截断声明。
    :returns: 工具声明。
    """

    return ToolDefinition(
        name="fake_tool",
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name="fake_tool",
                description="fake tool",
                parameters=_parameters(),
            ),
        ),
        callable=tool,
        truncate=truncate_spec,
        display=None,
        tags=("test",),
    )


def _parameters() -> ToolParametersSchema:
    """构造 fake tool 参数 schema。

    :returns: 参数 schema。
    """

    properties: dict[str, JsonValue] = {"ticker": {"type": "string"}}
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker",),
        additional_properties=False,
    )


def _truncate_spec(max_chars: int, ttl_seconds: int | None = None) -> ToolTruncateSpec:
    """构造 text_chars 截断声明。

    :param max_chars: 最大可见字符数。
    :param ttl_seconds: cursor TTL。
    :returns: 截断声明。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": max_chars},
        target_field=None,
        field_path=None,
        ttl_seconds=ttl_seconds,
    )


def _truncate_strategy_spec(
    *,
    strategy: ToolTruncationStrategy,
    limits: dict[str, int],
    ttl_seconds: int | None = None,
) -> ToolTruncateSpec:
    """构造指定策略的截断声明。

    :param strategy: 截断策略。
    :param limits: 策略上限配置。
    :param ttl_seconds: cursor TTL。
    :returns: 截断声明。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy=strategy,
        limits=limits,
        target_field=None,
        field_path=None,
        ttl_seconds=ttl_seconds,
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造工具来源引用。

    :returns: 来源引用。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="truncation-test",
    )


def _accepted_ack(candidate: ToolFactAcceptCandidate) -> ToolFactAcceptedAck:
    """按 candidate 构造 accepted ack。

    :param candidate: 工具事实候选。
    :returns: accepted ack。
    """

    requested_ref = HostEventRef(
        event_id=f"event-requested-{candidate.tool_call_id}",
        event_sequence=1,
    )
    result_ref = HostEventRef(
        event_id=f"event-result-{candidate.tool_call_id}",
        event_sequence=2,
    )
    result_payload_ref = (
        HostPayloadRef("payload-ref", candidate.payload_digest)
        if candidate.payload_digest is not None
        else None
    )
    return ToolFactAcceptedAck(
        accepted_event_refs=(requested_ref, result_ref),
        tool_fact_id=f"tool-fact-{candidate.tool_call_id}",
        tool_call_requested_event_ref=requested_ref,
        tool_call_governed_event_ref=None,
        tool_result_event_ref=result_ref,
        result_payload_ref=result_payload_ref,
        result_digest=candidate.outcome_digest
        if candidate.outcome_digest is not None
        else candidate.semantic_input_digest,
        reuse_prior_event_refs=(),
        diagnostic_refs=(),
        idempotency_record_ref=sha256_digest_json(
            {"idempotency": candidate.tool_call_id}
        ),
    )
