"""Host Phase 5 RunInputBuilder 与 no-tool provider 测试。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    AssistantMessage,
    SystemMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host._event_payload import (
    payload_object as _payload_object,
    required_payload_text as _required_payload_text,
)
from dayu.host.api import (
    AttemptDispatchSnapshot,
    AttemptStatus,
    AuthorizationClaim,
    EnsureSessionRequest,
    HostCallContext,
    HostMetadataEntry,
    OperationContext,
    RunStatus,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.memory import write_memory_snapshot_with_checkpoint
from dayu.host.durable.projection import read_projection_checkpoint
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    register_current_instance,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.run_transition import (
    CreateRunningRunInput,
    StartRecoveryRunInput,
    create_running_run_with_starting_attempt_in_transaction,
    start_recovery_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    DispatchRecordStatus,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactMaterialSection,
    EvidenceBackedFactKind,
    MinimumPreserveReason,
)
from dayu.host.compact_payload import preserved_fact_refs_summary
from dayu.host.memory_repair import catch_up_conversation_memory_projection
from dayu.host.run_input import (
    DurableCurrentRunFactProvider,
    DurableMemorySnapshotProvider,
    MemoryProjectionRepairRequired,
    NoopMemorySnapshotProvider,
    NoToolExecutor,
    PolicySnapshot,
    ToolExecutionMode,
    create_no_tool_run_input_builder,
    create_tool_enabled_run_input_builder,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationContinuityItem,
    ConversationContinuityKind,
    ConversationContinuityView,
    ConversationMemorySnapshot,
    HostNeutralRefKind,
    MemoryClaimStatus,
    MemoryDiagnosticReason,
    MemoryIncludedReason,
    MemoryProducerKind,
    MemoryProjectionEvent,
    MemoryProjectionPolicy,
    MemoryProvenanceRef,
    MemoryRepairReason,
    MemorySizeUnits,
    MemorySnapshotCursor,
    OpaqueMemoryRef,
    PinnedStateView,
    EvidenceBackedFactView,
    WorkingAssumptionView,
    build_conversation_memory_snapshot_from_events,
    calculate_memory_snapshot_digest,
    digest_memory_projection_policy,
)
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    ToolRuntimeHandle,
    ToolRuntimeBuildRequest,
)
from dayu.host.tooling import (
    default_framework_tool_policy_view,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "run-input-test"})
_INPUT_DIGEST = sha256_digest_json({"input": "current"})
_POLICY_REF = "policy-snapshot-p5-s2"
_DIGEST_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的当前 running Run。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        :returns: 始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        """

        return None


def test_current_user_message_comes_from_durable_user_input(
    tmp_path: Path,
) -> None:
    """当前用户消息只来自 durable USER_INPUT_ACCEPTED canonical fact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        payload: dict[str, JsonValue] = _user_input_payload("durable prompt")
        seeded = _seed_current_run(store, session_id=session_id, payload=payload)
        payload["display_text"] = "mutated transient prompt"

        request = _build_request(store, seeded)

        assert isinstance(request.messages[-1], UserMessage)
        assert request.messages[-1].content == "durable prompt"


def test_current_user_message_resolves_descriptor_payload(
    tmp_path: Path,
) -> None:
    """RunInputBuilder 跟随 descriptor 读取完整当前用户 prompt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run_with_descriptor(
            store,
            session_id=session_id,
            payload=_user_input_payload("descriptor durable prompt"),
        )

        input_event = _read_event_by_id(
            store.transaction_runner, "event-current-input"
        )
        request = _build_request(store, seeded)

        assert input_event.payload_ref is not None
        assert "descriptor durable prompt" not in input_event.payload_json
        assert isinstance(request.messages[-1], UserMessage)
        assert request.messages[-1].content == "descriptor durable prompt"


def test_recovery_attempt_rebuilds_current_prompt_from_same_run_eventlog_descriptor(
    tmp_path: Path,
) -> None:
    """recovery Attempt 仍从同一 Run 的 canonical USER_INPUT descriptor 重建消息。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        payload = _user_input_payload("descriptor recovery prompt")
        old = _seed_current_run_with_descriptor(
            store,
            session_id=session_id,
            payload=payload,
        )
        payload["display_text"] = "mutated old attempt snapshot"

        recovery = _start_recovery_attempt(store.transaction_runner, old)
        request = _build_request(store, recovery)

        assert recovery.run_id == old.run_id
        assert recovery.attempt_id != old.attempt_id
        assert recovery.execution_id != old.execution_id
        assert isinstance(request.messages[-1], UserMessage)
        assert request.messages[-1].content == "descriptor recovery prompt"


def test_build_is_deterministic_for_same_eventlog_and_policy(
    tmp_path: Path,
) -> None:
    """同一 EventLog 与 policy snapshot 多次 build 输出稳定 messages。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user_and_success(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior",
            user_text="earlier question",
            answer_text="earlier answer",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )

        first = _build_request(store, seeded)
        second = _build_request(store, seeded)

        assert tuple(_message_content(message) for message in first.messages) == tuple(
            _message_content(message) for message in second.messages
        )


def test_session_continuity_does_not_emit_unbudgeted_historical_raw_turns(
    tmp_path: Path,
) -> None:
    """SessionContinuityProvider 不再绕过 memory budget 注入历史 raw turns。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-1",
            event_id="event-prior-user-1",
            text="first question",
        )
        _append_projection_signal(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-ignored",
        )
        _append_prior_success(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-1",
            event_id="event-prior-success-1",
            answer_text="first answer",
        )
        _append_preview_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-preview",
        )
        _append_prior_user(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-2",
            event_id="event-prior-user-2",
            text="second question",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )

        request = _build_request(store, seeded)
        contents = tuple(_message_content(message) for message in request.messages)

        assert contents == (
            _expected_system_content(),
            "current question",
        )


def test_continuity_skips_unsuccessful_prior_runs(tmp_path: Path) -> None:
    """failed/cancelled/lost 历史 Run 不留下孤立 user message。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user_and_terminal(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-failed",
            user_text="failed question",
            terminal_event_type="RUN_FAILED",
        )
        _append_prior_user_and_terminal(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-cancelled",
            user_text="cancelled question",
            terminal_event_type="RUN_CANCELLED",
        )
        _append_prior_user_and_terminal(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-lost",
            user_text="lost question",
            terminal_event_type="RUN_LOST",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )

        request = _build_request(store, seeded)
        contents = tuple(_message_content(message) for message in request.messages)

        assert contents == (_expected_system_content(), "current question")


def test_noop_providers_do_not_create_durable_rows(tmp_path: Path) -> None:
    """noop memory / compact / tool schema provider 不创建 durable rows。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )
        before = _table_counts(store.transaction_runner)

        _build_request(store, seeded)

        assert _table_counts(store.transaction_runner) == before


def test_no_tool_request_fields_are_disabled(tmp_path: Path) -> None:
    """RunInputBuilder 输出 no-tool AgentRunRequest。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )

        request = _build_request(store, seeded)

        assert request.disable_tools is True
        assert request.tool_schemas == ()
        assert request.agent_policy.allow_tool_calls is False
        assert isinstance(request.tool_executor, NoToolExecutor)


def test_tool_enabled_request_uses_toolruntime_handle(tmp_path: Path) -> None:
    """tool-enabled RunInputBuilder 使用同一个 ToolRuntimeHandle 暴露 schema 与 executor。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )
        tool_runtime_handle = _tool_runtime_handle()
        policy_snapshot = _policy_snapshot(allow_tool_calls=True)

        request = create_tool_enabled_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=policy_snapshot,
            tool_runtime_handle=tool_runtime_handle,
        ).build(_attempt_snapshot(seeded))

        assert request.disable_tools is False
        assert request.agent_policy.allow_tool_calls is True
        assert request.tool_schemas == tool_runtime_handle.tool_schemas
        assert request.tool_executor is tool_runtime_handle.tool_executor
        assert "tools=disabled" not in _message_content(request.messages[0])
        assert "tools=enabled" in _message_content(request.messages[0])


def test_replay_no_tool_request_keeps_tools_disabled(tmp_path: Path) -> None:
    """replay no-tool 模式不暴露 schema，且 scene 仍表达工具禁用。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )

        builder = create_no_tool_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=_policy_snapshot(),
            tool_execution_mode=ToolExecutionMode.NO_TOOL_REPLAY,
        )
        request = builder.build(_attempt_snapshot(seeded))

        assert request.disable_tools is True
        assert request.tool_schemas == ()
        assert request.agent_policy.allow_tool_calls is False
        assert isinstance(request.tool_executor, NoToolExecutor)
        assert "tools=disabled" in _message_content(request.messages[0])


def test_no_tool_builder_rejects_tool_enabled_mode(tmp_path: Path) -> None:
    """no-tool builder 拒绝 TOOL_ENABLED 模式。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(ValueError, match="no-tool mode"):
            create_no_tool_run_input_builder(
                transaction_runner=store.transaction_runner,
                policy_snapshot=_policy_snapshot(),
                tool_execution_mode=ToolExecutionMode.TOOL_ENABLED,
            )


def test_policy_snapshot_allows_tool_policy_for_tool_enabled() -> None:
    """PolicySnapshot 构造期不再把 allow_tool_calls=True 当作 no-tool 错误。"""

    snapshot = _policy_snapshot(allow_tool_calls=True)

    assert snapshot.agent_policy.allow_tool_calls is True


def test_durable_memory_provider_uses_covered_snapshot(tmp_path: Path) -> None:
    """cursor 已覆盖 required sequence 时直接使用 durable snapshot。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_rich_memory_source_events(store.transaction_runner, session_id)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        cursor = _required_memory_cursor(store.transaction_runner, seeded)
        snapshot = _rich_memory_snapshot(session_id, policy, cursor)
        _write_memory_snapshot(store.transaction_runner, snapshot)

        request = _build_request_with_memory(store, seeded, policy)
        current_facts = DurableCurrentRunFactProvider(
            store.transaction_runner
        ).load_current_run_facts(_attempt_snapshot(seeded))
        memory_view = DurableMemorySnapshotProvider(
            store.transaction_runner, policy
        ).load_memory_snapshot(_attempt_snapshot(seeded), current_facts)
        contents = tuple(_message_content(message) for message in request.messages)

        assert contents[0] == _expected_system_content()
        assert contents[1].startswith("Memory user goals and constraints:")
        assert contents[2].startswith("Memory evidence-backed facts:")
        assert "claim_text=Revenue increased year over year" in contents[2]
        assert "evidence_refs=evidence:memory-tool" in contents[2]
        assert "evidence_kind=observed_value" in contents[2]
        assert "extraction_operation_ref=event:event-memory-episode" in contents[2]
        assert "event_id=event-memory-episode" in contents[2]
        assert "event_sequence=5" in contents[2]
        assert "digest_ref=" not in contents[2]
        assert "fact_summary=" not in contents[2]
        assert contents[3].startswith("Memory confirmed subjects and methodology:")
        assert contents[4].startswith("Memory open questions and working assumptions:")
        assert contents[5] == "recent raw user"
        assert contents[6] == "recent assistant conclusion"
        assert contents[7].startswith("Memory minimum preserve continuity:")
        assert "label=factor-2" in contents[7]
        assert "text=second factor: margin mix" in contents[7]
        assert "source_refs=event-memory-raw-user" in contents[7]
        assert (
            "preserve_reason=needed_for_ordered_item_reference"
            in contents[7]
        )
        assert contents[8].startswith("Memory episode summaries:")
        assert contents[-1] == "current prompt"
        assert all("inline delta" not in content for content in contents)
        assert all(
            diagnostic.reason is not MemoryDiagnosticReason.INLINE_DELTA_REPAIR_INCLUDED
            for diagnostic in memory_view.diagnostics
        )


def test_memory_provider_applies_stable_layer_budget(tmp_path: Path) -> None:
    """stable layer 超预算时跳过 stable blocks 并保留 continuity 与当前 prompt。"""

    policy = _memory_policy(stable_layer_size_units=24)
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_rich_memory_source_events(store.transaction_runner, session_id)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        cursor = _required_memory_cursor(store.transaction_runner, seeded)
        snapshot = _rich_memory_snapshot(session_id, policy, cursor)
        _write_memory_snapshot(store.transaction_runner, snapshot)

        request = _build_request_with_memory(store, seeded, policy)
        current_facts = DurableCurrentRunFactProvider(
            store.transaction_runner
        ).load_current_run_facts(_attempt_snapshot(seeded))
        memory_view = DurableMemorySnapshotProvider(
            store.transaction_runner, policy
        ).load_memory_snapshot(_attempt_snapshot(seeded), current_facts)
        contents = tuple(_message_content(message) for message in request.messages)

        assert all(
            not content.startswith("Memory evidence-backed facts:")
            for content in contents
        )
        assert "recent raw user" in contents
        assert contents[-1] == "current prompt"
        assert any(
            diagnostic.reason is MemoryDiagnosticReason.BUDGET_LIMIT_REACHED
            and diagnostic.item_id == "stable:evidence_backed_facts"
            for diagnostic in memory_view.diagnostics
        )


def test_stable_budget_prioritizes_evidence_backed_facts_over_subjects(
    tmp_path: Path,
) -> None:
    """stable 预算紧张时 confirmed subjects 不能饿死 evidence-backed facts。"""

    policy = _memory_policy(stable_layer_size_units=512)
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_rich_memory_source_events(store.transaction_runner, session_id)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        cursor = _required_memory_cursor(store.transaction_runner, seeded)
        snapshot = _stable_budget_pressure_snapshot(session_id, policy, cursor)
        _write_memory_snapshot(store.transaction_runner, snapshot)

        request = _build_request_with_memory(store, seeded, policy)
        current_facts = DurableCurrentRunFactProvider(
            store.transaction_runner
        ).load_current_run_facts(_attempt_snapshot(seeded))
        memory_view = DurableMemorySnapshotProvider(
            store.transaction_runner, policy
        ).load_memory_snapshot(_attempt_snapshot(seeded), current_facts)
        contents = tuple(_message_content(message) for message in request.messages)

        assert any(
            content.startswith("Memory evidence-backed facts:")
            for content in contents
        )
        assert all(
            not content.startswith("Memory confirmed subjects and methodology:")
            for content in contents
        )
        assert any(
            diagnostic.reason is MemoryDiagnosticReason.BUDGET_LIMIT_REACHED
            and diagnostic.item_id == "stable:subjects"
            for diagnostic in memory_view.diagnostics
        )


def test_noop_memory_snapshot_provider_returns_empty_typed_view(
    tmp_path: Path,
) -> None:
    """Noop memory provider 保持空 messages 并返回新增 typed 字段。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        attempt_snapshot = _attempt_snapshot(seeded)
        current_facts = DurableCurrentRunFactProvider(
            store.transaction_runner
        ).load_current_run_facts(attempt_snapshot)

        view = NoopMemorySnapshotProvider().load_memory_snapshot(
            snapshot=attempt_snapshot,
            current_facts=current_facts,
        )

        assert view.messages == ()
        assert view.memory_snapshot_cursor is None
        assert view.policy_digest is None
        assert view.diagnostics == ()


def test_run_input_builder_exposes_shared_material_block_source(
    tmp_path: Path,
) -> None:
    """RunInputBuilder 暴露与 compact builder 共用的 ordinary material view。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        builder = create_no_tool_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=_policy_snapshot(),
        )

        blocks = builder.build_material_blocks(_attempt_snapshot(seeded))

        assert len(blocks) == 1
        assert blocks[0].section is CompactMaterialSection.CURRENT_INPUT_ANCHOR
        assert blocks[0].kind is CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR
        assert blocks[0].text == "current prompt"
        assert blocks[0].canonical_source_refs == ("event-current-input",)


def test_covered_memory_snapshot_filters_current_user_input(
    tmp_path: Path,
) -> None:
    """covered snapshot 含当前 USER_INPUT_ACCEPTED 时不重复渲染当前 prompt。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        current_input = _read_event_by_id(
            store.transaction_runner, "event-current-input"
        )
        cursor = _required_memory_cursor(store.transaction_runner, seeded)
        snapshot = _current_input_memory_snapshot(
            session_id=session_id,
            policy=policy,
            cursor=cursor,
            current_input=current_input,
            current_prompt="current prompt",
        )
        _write_memory_snapshot(store.transaction_runner, snapshot)

        request = _build_request_with_memory(store, seeded, policy)
        contents = tuple(_message_content(message) for message in request.messages)

        assert contents[-1] == "current prompt"
        assert _message_occurrences(contents, "current prompt") == 1


def test_inline_delta_filters_current_user_input(tmp_path: Path) -> None:
    """inline delta 含当前 USER_INPUT_ACCEPTED 时不重复渲染当前 prompt。"""

    policy = _memory_policy(max_lag_events_for_inline_delta=16)
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        snapshot = build_conversation_memory_snapshot_from_events(
            events=(),
            session_id=session_id,
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            policy=policy,
            built_at="2026-05-15T01:02:03.000000Z",
        )
        _write_memory_snapshot(store.transaction_runner, snapshot)

        request = _build_request_with_memory(store, seeded, policy)
        contents = tuple(_message_content(message) for message in request.messages)

        assert contents[-1] == "current prompt"
        assert _message_occurrences(contents, "current prompt") == 1


def test_inline_delta_applies_stable_layer_budget(tmp_path: Path) -> None:
    """inline delta 修复后的 stable blocks 仍受 stable layer budget 约束。"""

    policy = _memory_policy(
        max_lag_events_for_inline_delta=16,
        stable_layer_size_units=24,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_rich_memory_source_events(store.transaction_runner, session_id)
        snapshot = build_conversation_memory_snapshot_from_events(
            events=(),
            session_id=session_id,
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            policy=policy,
            built_at="2026-05-15T01:02:03.000000Z",
        )
        _write_memory_snapshot(store.transaction_runner, snapshot)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )

        current_facts = DurableCurrentRunFactProvider(
            store.transaction_runner
        ).load_current_run_facts(_attempt_snapshot(seeded))
        memory_view = DurableMemorySnapshotProvider(
            store.transaction_runner, policy
        ).load_memory_snapshot(_attempt_snapshot(seeded), current_facts)

        assert any(
            diagnostic.reason is MemoryDiagnosticReason.INLINE_DELTA_REPAIR_INCLUDED
            for diagnostic in memory_view.diagnostics
        )
        assert any(
            diagnostic.reason is MemoryDiagnosticReason.BUDGET_LIMIT_REACHED
            and diagnostic.item_id == "stable:evidence_backed_facts"
            for diagnostic in memory_view.diagnostics
        )


def test_missing_memory_snapshot_raises_repair_without_state_mutation(
    tmp_path: Path,
) -> None:
    """snapshot 缺失时进入 repair-required，且不改 Run / Attempt / EventLog。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_rich_memory_source_events(store.transaction_runner, session_id)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        before = _run_attempt_eventlog_state(store.transaction_runner, seeded)

        with pytest.raises(MemoryProjectionRepairRequired) as exc_info:
            _build_request_with_memory(store, seeded, policy)

        after = _run_attempt_eventlog_state(store.transaction_runner, seeded)
        assert exc_info.value.repair_request.reason is MemoryRepairReason.SNAPSHOT_MISSING
        assert after == before


def test_damaged_memory_snapshot_raises_repair_required(tmp_path: Path) -> None:
    """snapshot digest 损坏时进入结构化 repair-required。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_rich_memory_source_events(store.transaction_runner, session_id)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        cursor = _required_memory_cursor(store.transaction_runner, seeded)
        snapshot = _rich_memory_snapshot(session_id, policy, cursor)
        _write_memory_snapshot(store.transaction_runner, snapshot)
        _damage_memory_snapshot_json(store.transaction_runner, snapshot.snapshot_id)

        with pytest.raises(MemoryProjectionRepairRequired) as exc_info:
            _build_request_with_memory(store, seeded, policy)

        assert exc_info.value.repair_request.reason is MemoryRepairReason.SNAPSHOT_DAMAGED


def test_small_memory_lag_repairs_inline_without_checkpoint_advance(
    tmp_path: Path,
) -> None:
    """小滞后从 EventLog delta 临时补齐，并且不推进 projection checkpoint。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        prior_event = _append_prior_user_event(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-memory",
            event_id="event-prior-memory-input",
            text="prior memory prompt",
        )
        snapshot = build_conversation_memory_snapshot_from_events(
            events=(
                _memory_projection_event_from_test_row(prior_event),
            ),
            session_id=session_id,
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            policy=policy,
            built_at="2026-05-15T01:02:03.000000Z",
        )
        _write_memory_snapshot(store.transaction_runner, snapshot)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )

        request = _build_request_with_memory(store, seeded, policy)
        current_facts = DurableCurrentRunFactProvider(
            store.transaction_runner
        ).load_current_run_facts(_attempt_snapshot(seeded))
        memory_view = DurableMemorySnapshotProvider(
            store.transaction_runner, policy
        ).load_memory_snapshot(_attempt_snapshot(seeded), current_facts)
        checkpoint = _read_memory_checkpoint_sequence(store.transaction_runner)
        contents = tuple(_message_content(message) for message in request.messages)

        assert checkpoint == prior_event.event_sequence
        assert any(
            diagnostic.reason is MemoryDiagnosticReason.INLINE_DELTA_REPAIR_INCLUDED
            for diagnostic in memory_view.diagnostics
        )
        assert "current prompt" in contents[-1]
        assert any("current_goal=prior memory prompt" in content for content in contents)


def test_over_threshold_memory_lag_raises_repair_required(
    tmp_path: Path,
) -> None:
    """超过 inline threshold 的 snapshot lag 进入 repair-required。"""

    policy = _memory_policy(max_lag_events_for_inline_delta=0)
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_rich_memory_source_events(store.transaction_runner, session_id)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        snapshot = _rich_memory_snapshot(
            session_id,
            policy,
            MemorySnapshotCursor(
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                checkpoint_event_sequence=0,
                checkpoint_event_id=None,
                session_id=session_id,
            ),
        )
        _write_memory_snapshot(store.transaction_runner, snapshot)

        with pytest.raises(MemoryProjectionRepairRequired) as exc_info:
            _build_request_with_memory(store, seeded, policy)

        assert (
            exc_info.value.repair_request.reason
            is MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD
        )


def test_only_future_memory_snapshot_raises_missing_repair_required(
    tmp_path: Path,
) -> None:
    """只有未来 snapshot 时不得注入未来 memory。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        future_event = _append_prior_user_event(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-future-memory",
            event_id="event-future-memory-input",
            text="future prompt must not leak",
        )
        snapshot = build_conversation_memory_snapshot_from_events(
            events=(
                _memory_projection_event_from_test_row(future_event),
            ),
            session_id=session_id,
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            policy=policy,
            built_at="2026-05-15T01:02:03.000000Z",
        )
        _write_memory_snapshot(store.transaction_runner, snapshot)

        with pytest.raises(MemoryProjectionRepairRequired) as exc_info:
            _build_request_with_memory(store, seeded, policy)

        assert (
            exc_info.value.repair_request.reason
            is MemoryRepairReason.SNAPSHOT_MISSING
        )


def test_memory_provider_uses_latest_snapshot_before_required_cursor(
    tmp_path: Path,
) -> None:
    """同一 Session 有 queued future input 时读取 required cursor 前的 snapshot。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        prior_event = _append_prior_user_event(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-memory",
            event_id="event-prior-memory-input",
            text="prior prompt should be visible",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        future_event = _append_prior_user_event(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-future-memory",
            event_id="event-future-memory-input",
            text="future prompt must not leak",
        )
        del prior_event, future_event
        required_cursor = _required_memory_cursor(store.transaction_runner, seeded)
        catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=16,
            max_event_sequence=required_cursor.checkpoint_event_sequence,
        )

        request = _build_request_with_memory(store, seeded, policy)
        contents = tuple(_message_content(message) for message in request.messages)

        assert "prior prompt should be visible" in contents
        assert "future prompt must not leak" not in contents
        assert contents[-1] == "current prompt"


def test_run_input_memory_messages_include_context_compacted_projection(
    tmp_path: Path,
) -> None:
    """projection catch-up 后 RunInputBuilder 注入 compacted pinned state 与 summary。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_rich_memory_source_events(store.transaction_runner, session_id)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        required_cursor = _required_memory_cursor(store.transaction_runner, seeded)
        catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=16,
            max_event_sequence=required_cursor.checkpoint_event_sequence,
        )

        request = _build_request_with_memory(store, seeded, policy)
        contents = tuple(_message_content(message) for message in request.messages)

        assert any("current_goal=compact pinned goal" in content for content in contents)
        assert any("confirmed_subject=subject:issuer-a" in content for content in contents)
        assert any("open_question=compact open question" in content for content in contents)
        assert any("episode_summary=episode navigation only" in content for content in contents)
        assert contents[-1] == "current prompt"


def test_gross_margin_followup_uses_post_compaction_evidence_backed_facts(
    tmp_path: Path,
) -> None:
    """毛利率追问通过 post-compaction facts 读取收入与毛利。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_compacted_gross_margin_facts(store.transaction_runner, session_id)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("请基于已确认的收入和毛利计算毛利率"),
        )
        required_cursor = _required_memory_cursor(store.transaction_runner, seeded)
        catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=16,
            max_event_sequence=required_cursor.checkpoint_event_sequence,
        )

        request = _build_request_with_memory(store, seeded, policy)
        contents = tuple(_message_content(message) for message in request.messages)
        fact_blocks = tuple(
            content
            for content in contents
            if content.startswith("Memory evidence-backed facts:")
        )

        assert len(fact_blocks) == 1
        assert "claim_text=Revenue was 100." in fact_blocks[0]
        assert "claim_text=Gross profit was 40." in fact_blocks[0]
        assert "evidence_refs=evidence:memory-tool" in fact_blocks[0]
        assert all(
            "older raw says revenue 100 and gross profit 40" not in content
            for content in contents
        )
        assert contents[-1] == "请基于已确认的收入和毛利计算毛利率"


def test_run_input_builder_renders_claim_text_and_evidence_refs_not_digest_only(
    tmp_path: Path,
) -> None:
    """RunInputBuilder 渲染 stable facts 时必须包含 claim_text 与 evidence_refs。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_compacted_gross_margin_facts(store.transaction_runner, session_id)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("继续分析收入质量"),
        )
        required_cursor = _required_memory_cursor(store.transaction_runner, seeded)
        catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=16,
            max_event_sequence=required_cursor.checkpoint_event_sequence,
        )

        request = _build_request_with_memory(store, seeded, policy)
        fact_blocks = tuple(
            _message_content(message)
            for message in request.messages
            if _message_content(message).startswith("Memory evidence-backed facts:")
        )

        assert len(fact_blocks) == 1
        assert "claim_text=Revenue was 100." in fact_blocks[0]
        assert "claim_text=Gross profit was 40." in fact_blocks[0]
        assert "evidence_refs=evidence:memory-tool" in fact_blocks[0]
        assert "digest_ref=" not in fact_blocks[0]
        assert "fact_summary=" not in fact_blocks[0]


def test_no_compaction_recent_raw_turns_continuity_still_works(
    tmp_path: Path,
) -> None:
    """未发生 compact 时，memory recent raw turns 仍提供连续性。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user_and_success(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-no-compact",
            user_text="上轮问题：收入增长来自哪里？",
            answer_text="上轮回答：收入增长主要来自订阅业务。",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("继续说明这个增长因素"),
        )
        required_cursor = _required_memory_cursor(store.transaction_runner, seeded)
        catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=16,
            max_event_sequence=required_cursor.checkpoint_event_sequence,
        )

        request = _build_request_with_memory(store, seeded, policy)
        contents = tuple(_message_content(message) for message in request.messages)

        assert "上轮问题：收入增长来自哪里？" in contents
        assert "上轮回答：收入增长主要来自订阅业务。" in contents
        assert all(
            not content.startswith("Memory evidence-backed facts:")
            for content in contents
        )
        assert contents[-1] == "继续说明这个增长因素"


def test_compact_artifact_preserved_fact_refs_reads_canonical_evidence_key() -> None:
    """compact artifact message 从 canonical evidence refs 字段读取 refs。"""

    payload: dict[str, JsonValue] = {
        "preserved_fact_refs": {
            "canonical_evidence_refs": ["evidence:memory-tool"],
            "evidence_backed_fact_refs": ["fact:memory-revenue"],
        }
    }

    assert preserved_fact_refs_summary(payload) == (
        "canonical_evidence_refs=evidence:memory-tool; "
        "evidence_backed_fact_refs=fact:memory-revenue"
    )


def test_minimum_preserve_resolves_second_factor_without_full_long_input(
    tmp_path: Path,
) -> None:
    """长输入 compact 后只靠 minimum preserve 解析“第二个因素”。"""

    policy = _memory_policy()
    long_input = (
        "第一因素是收入确认节奏。" * 20
        + "第二个因素是毛利率受云业务拖累。"
        + "第三因素是费用投放。" * 20
    )
    preserve_text = "第二个因素：毛利率受云业务拖累"
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        source_event = _append_prior_user_event(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-long-input",
            event_id="event-long-input",
            text=long_input,
        )
        compact_event = _append_minimum_preserve_compact_marker(
            store.transaction_runner,
            session_id=session_id,
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("第二个因素具体影响是什么？"),
        )
        cursor = _required_memory_cursor(store.transaction_runner, seeded)
        snapshot = _minimum_preserve_only_snapshot(
            session_id=session_id,
            policy=policy,
            cursor=cursor,
            source_event=source_event,
            producer_event=compact_event,
            preserve_text=preserve_text,
        )
        _write_memory_snapshot(store.transaction_runner, snapshot)

        request = _build_request_with_memory(store, seeded, policy)
        contents = tuple(_message_content(message) for message in request.messages)
        preserve_blocks = tuple(
            content
            for content in contents
            if content.startswith("Memory minimum preserve continuity:")
        )

        assert len(preserve_blocks) == 1
        assert "label=第二个因素" in preserve_blocks[0]
        assert f"text={preserve_text}" in preserve_blocks[0]
        assert "source_refs=event-long-input" in preserve_blocks[0]
        assert all(long_input not in content for content in contents)
        assert contents[-1] == "第二个因素具体影响是什么？"


def test_memory_messages_are_stable_for_same_eventlog_and_policy(
    tmp_path: Path,
) -> None:
    """同一 EventLog 与同一 memory policy 生成稳定 memory messages。"""

    policy = _memory_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        prior_event = _append_prior_user_event(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-memory",
            event_id="event-prior-memory-input",
            text="prior memory prompt",
        )
        snapshot = build_conversation_memory_snapshot_from_events(
            events=(
                _memory_projection_event_from_test_row(prior_event),
            ),
            session_id=session_id,
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            policy=policy,
            built_at="2026-05-15T01:02:03.000000Z",
        )
        _write_memory_snapshot(store.transaction_runner, snapshot)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )

        first = _build_request_with_memory(store, seeded, policy)
        second = _build_request_with_memory(store, seeded, policy)

        assert tuple(_message_content(message) for message in first.messages) == tuple(
            _message_content(message) for message in second.messages
        )


@pytest.mark.parametrize(
    ("run_status", "attempt_status", "dispatch_status", "message"),
    (
        (
            RunStatus.FAILED,
            AttemptStatus.STARTING,
            DispatchRecordStatus.DISPATCHING,
            "RUNNING Run",
        ),
        (
            RunStatus.RUNNING,
            AttemptStatus.CANCELLED,
            DispatchRecordStatus.DISPATCHING,
            "STARTING Attempt",
        ),
        (
            RunStatus.RUNNING,
            AttemptStatus.STARTING,
            DispatchRecordStatus.PENDING,
            "DISPATCHING dispatch record",
        ),
    ),
)
def test_current_facts_reject_non_dispatchable_snapshot_state(
    tmp_path: Path,
    run_status: RunStatus,
    attempt_status: AttemptStatus,
    dispatch_status: DispatchRecordStatus,
    message: str,
) -> None:
    """RunInputBuilder 只接受当前 dispatch 快照的可派发 durable 状态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )
        _force_dispatch_snapshot_state(
            store.transaction_runner,
            seeded,
            run_status=run_status,
            attempt_status=attempt_status,
            dispatch_status=dispatch_status,
        )

        with pytest.raises(HostDurableError, match=message):
            _build_request(store, seeded)


@pytest.mark.parametrize(
    ("snapshot_field", "snapshot_value", "message"),
    (
        (
            "execution_id",
            "execution-stale",
            "attempt identity mismatch",
        ),
        (
            "dispatch_record_id",
            "dispatch-stale",
            "dispatch identity mismatch",
        ),
        (
            "execution_target",
            "target-stale",
            "execution_target mismatch",
        ),
    ),
)
def test_current_facts_reject_stale_snapshot_identity(
    tmp_path: Path,
    snapshot_field: Literal[
        "execution_id", "dispatch_record_id", "execution_target"
    ],
    snapshot_value: str,
    message: str,
) -> None:
    """RunInputBuilder 对 stale dispatch snapshot 按既有错误语义 fail closed。

    :param tmp_path: pytest 临时目录。
    :param snapshot_field: 需要覆盖的 snapshot 字段名。
    :param snapshot_value: 需要覆盖的 snapshot 字段值。
    :param message: 期望错误消息片段。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )
        if snapshot_field == "execution_id":
            stale_snapshot = replace(
                _attempt_snapshot(seeded), execution_id=snapshot_value
            )
        elif snapshot_field == "dispatch_record_id":
            stale_snapshot = replace(
                _attempt_snapshot(seeded), dispatch_record_id=snapshot_value
            )
        else:
            stale_snapshot = replace(
                _attempt_snapshot(seeded), execution_target=snapshot_value
            )
        builder = create_no_tool_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=_policy_snapshot(),
        )

        with pytest.raises(HostDurableError, match=message):
            builder.build(stale_snapshot)


def _memory_policy(
    *,
    max_lag_events_for_inline_delta: int = 4,
    history_pool_size_units: int = 4096,
    stable_layer_size_units: int = 2048,
) -> MemoryProjectionPolicy:
    """构造 RunInputBuilder memory provider 测试 policy。

    :param max_lag_events_for_inline_delta: inline repair 最大滞后事件数。
    :param history_pool_size_units: history pool 尺寸。
    :param stable_layer_size_units: stable layer 尺寸。
    :returns: memory projection policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        max_pinned_items=8,
        max_evidence_backed_facts=16,
        max_working_assumptions=8,
        recent_raw_turns_floor=2,
        raw_turn_context_ratio=0.125,
        raw_turn_size_floor=1024,
        raw_turn_size_cap=1024,
        history_pool_context_ratio=0.5,
        history_pool_size_floor=history_pool_size_units,
        history_pool_size_cap=history_pool_size_units,
        stable_layer_context_ratio=0.25,
        stable_layer_size_floor=stable_layer_size_units,
        stable_layer_size_cap=stable_layer_size_units,
        max_lag_events_for_inline_delta=max_lag_events_for_inline_delta,
        max_delta_repair_events=16,
    )


def _build_request_with_memory(
    store: HostDurableStore,
    seeded: _SeededRun,
    policy: MemoryProjectionPolicy,
) -> AgentRunRequest:
    """通过 durable memory provider 构造 AgentRunRequest。

    :param store: Host durable store。
    :param seeded: seeded Run 引用。
    :param policy: memory projection policy。
    :returns: AgentRunRequest。
    """

    provider = DurableMemorySnapshotProvider(store.transaction_runner, policy)
    builder = create_no_tool_run_input_builder(
        transaction_runner=store.transaction_runner,
        policy_snapshot=_policy_snapshot(),
        memory_snapshot_provider=provider,
    )
    return builder.build(_attempt_snapshot(seeded))


def _required_memory_cursor(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> MemorySnapshotCursor:
    """读取当前 Attempt 所需 memory cursor。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded Run 引用。
    :returns: required memory cursor。
    """

    def operation(transaction: HostTransaction) -> MemorySnapshotCursor:
        """读取 ATTEMPT_STARTED 前一条 EventLog row。

        :param transaction: Host transaction。
        :returns: memory cursor。
        """

        started = EventLogStore().read_event_by_id(
            transaction, "event-attempt-started-current"
        )
        assert started is not None
        required_sequence = started.event_sequence - 1
        row = transaction.fetchone(
            """
            SELECT event_id
            FROM event_log
            WHERE event_sequence = ?
            """,
            (required_sequence,),
        )
        assert row is not None
        event_id = row.get("event_id")
        assert isinstance(event_id, str)
        return MemorySnapshotCursor(
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            checkpoint_event_sequence=required_sequence,
            checkpoint_event_id=event_id,
            session_id=seeded.session_id,
        )

    return transaction_runner.run_read(operation)


def _rich_memory_snapshot(
    session_id: str,
    policy: MemoryProjectionPolicy,
    cursor: MemorySnapshotCursor,
) -> ConversationMemorySnapshot:
    """构造覆盖所有 memory message 分组的 snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :returns: memory snapshot。
    """

    policy_digest = digest_memory_projection_policy(policy)
    snapshot_without_digest = ConversationMemorySnapshot(
        snapshot_id=f"memory-snapshot-test-{session_id}",
        session_id=session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        pinned_state=PinnedStateView(
            current_goal="compare revenue quality",
            confirmed_subjects=(
                OpaqueMemoryRef(
                    ref_kind=HostNeutralRefKind.SUBJECT,
                    ref_id="subject:alpha",
                    digest=_DIGEST_A,
                ),
            ),
            user_constraints=("use reported currency",),
            open_questions=("what changed in margin?",),
        ),
        evidence_backed_facts=(
            EvidenceBackedFactView(
                item_id="memory-item:evidence-backed:test",
                claim_text="Revenue increased year over year",
                evidence_kind=EvidenceBackedFactKind.OBSERVED_VALUE,
                evidence_refs=("evidence:memory-tool",),
                attributes={},
                provenance=MemoryProvenanceRef(
                    producer_kind=MemoryProducerKind.HOST_PROJECTION,
                    producer_name="conversation_memory",
                    event_id="event-memory-episode",
                    event_sequence=5,
                    run_id="run-memory",
                    attempt_id=None,
                    execution_id=None,
                    tool_result_ref="event-memory-tool",
                    payload_ref="compact-artifact:test",
                    digest_ref=_DIGEST_A,
                    source_refs=(),
                ),
                extraction_operation_ref="event:event-memory-episode",
                compact_artifact_ref="compact-artifact:test",
                candidate_id="fact-memory-revenue",
                included_reason=MemoryIncludedReason.EVIDENCE_BACKED_FACT,
                excluded_reason=None,
                size_units=MemorySizeUnits(31),
            ),
        ),
        working_assumptions=(
            WorkingAssumptionView(
                item_id="memory-item:assumption:test",
                assumption_summary="margin mix may have shifted",
                claim_status=MemoryClaimStatus.ASSUMPTION,
                producer_kind=MemoryProducerKind.USER,
                event_id="event-memory-assumption",
                event_sequence=2,
                run_id="run-memory",
                subject_refs=(),
                included_reason=MemoryIncludedReason.WORKING_ASSUMPTION,
                excluded_reason=None,
                size_units=MemorySizeUnits(27),
            ),
        ),
        conversation_continuity=ConversationContinuityView(
            items=(
                ConversationContinuityItem(
                    item_id="memory-item:raw-user:test",
                    item_kind=ConversationContinuityKind.RAW_USER_TURN,
                    producer_kind=MemoryProducerKind.USER,
                    claim_status=MemoryClaimStatus.ASSUMPTION,
                    event_id="event-memory-raw-user",
                    event_sequence=3,
                    run_id="run-memory",
                    summary_text="recent raw user",
                    label=None,
                    source_refs=(),
                    preserve_reason=None,
                    payload_ref=None,
                    payload_digest=None,
                    included_reason=MemoryIncludedReason.RECENT_RAW_TURN,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(15),
                ),
                ConversationContinuityItem(
                    item_id="memory-item:assistant:test",
                    item_kind=ConversationContinuityKind.ASSISTANT_CONCLUSION,
                    producer_kind=MemoryProducerKind.ASSISTANT,
                    claim_status=MemoryClaimStatus.ASSUMPTION,
                    event_id="event-memory-assistant",
                    event_sequence=4,
                    run_id="run-memory",
                    summary_text="recent assistant conclusion",
                    label=None,
                    source_refs=(),
                    preserve_reason=None,
                    payload_ref=None,
                    payload_digest=None,
                    included_reason=MemoryIncludedReason.RECENT_RAW_TURN,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(27),
                ),
                ConversationContinuityItem(
                    item_id="memory-item:minimum-preserve:test",
                    item_kind=ConversationContinuityKind.MINIMUM_PRESERVE_ITEM,
                    producer_kind=MemoryProducerKind.HOST_PROJECTION,
                    claim_status=MemoryClaimStatus.ASSUMPTION,
                    event_id="event-memory-episode",
                    event_sequence=5,
                    run_id="run-memory",
                    summary_text="second factor: margin mix",
                    label="factor-2",
                    source_refs=("event-memory-raw-user",),
                    preserve_reason=(
                        MinimumPreserveReason.NEEDED_FOR_ORDERED_ITEM_REFERENCE
                    ),
                    payload_ref=None,
                    payload_digest=None,
                    included_reason=MemoryIncludedReason.MINIMUM_PRESERVE_ITEM,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(25),
                ),
                ConversationContinuityItem(
                    item_id="memory-item:episode:test",
                    item_kind=ConversationContinuityKind.EPISODE_SUMMARY,
                    producer_kind=MemoryProducerKind.HOST_PROJECTION,
                    claim_status=MemoryClaimStatus.ASSUMPTION,
                    event_id="event-memory-episode",
                    event_sequence=5,
                    run_id=None,
                    summary_text="episode navigation only",
                    label=None,
                    source_refs=(),
                    preserve_reason=None,
                    payload_ref=None,
                    payload_digest=None,
                    included_reason=MemoryIncludedReason.EPISODE_SUMMARY,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(23),
                ),
            )
        ),
        diagnostics=(),
        built_at="2026-05-15T01:02:03.000000Z",
        snapshot_digest="pending",
    )
    return ConversationMemorySnapshot(
        snapshot_id=snapshot_without_digest.snapshot_id,
        session_id=snapshot_without_digest.session_id,
        cursor=snapshot_without_digest.cursor,
        policy_digest=snapshot_without_digest.policy_digest,
        pinned_state=snapshot_without_digest.pinned_state,
        evidence_backed_facts=snapshot_without_digest.evidence_backed_facts,
        working_assumptions=snapshot_without_digest.working_assumptions,
        conversation_continuity=snapshot_without_digest.conversation_continuity,
        diagnostics=snapshot_without_digest.diagnostics,
        built_at=snapshot_without_digest.built_at,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def _stable_budget_pressure_snapshot(
    session_id: str,
    policy: MemoryProjectionPolicy,
    cursor: MemorySnapshotCursor,
) -> ConversationMemorySnapshot:
    """构造 subjects 大于预算但 fact 可独立放入的 snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :returns: memory snapshot。
    """

    snapshot = _rich_memory_snapshot(session_id, policy, cursor)
    subjects = tuple(
        OpaqueMemoryRef(
            ref_kind=HostNeutralRefKind.SUBJECT,
            ref_id=f"subject:budget-pressure-{index}",
            digest=_DIGEST_A,
        )
        for index in range(12)
    )
    pinned_state = replace(
        snapshot.pinned_state,
        current_goal=None,
        confirmed_subjects=subjects,
        user_constraints=(),
        open_questions=(),
    )
    updated = replace(
        snapshot,
        pinned_state=pinned_state,
        working_assumptions=(),
    )
    return replace(updated, snapshot_digest=calculate_memory_snapshot_digest(updated))


def _current_input_memory_snapshot(
    *,
    session_id: str,
    policy: MemoryProjectionPolicy,
    cursor: MemorySnapshotCursor,
    current_input: EventLogRow,
    current_prompt: str,
) -> ConversationMemorySnapshot:
    """构造包含当前用户输入的测试 memory snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :param current_input: 当前 USER_INPUT_ACCEPTED event。
    :param current_prompt: 当前 prompt 文本。
    :returns: memory snapshot。
    """

    policy_digest = digest_memory_projection_policy(policy)
    snapshot_without_digest = ConversationMemorySnapshot(
        snapshot_id=f"memory-snapshot-current-{session_id}",
        session_id=session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        pinned_state=PinnedStateView(
            current_goal=current_prompt,
            confirmed_subjects=(),
            user_constraints=(current_prompt,),
            open_questions=(),
        ),
        evidence_backed_facts=(),
        working_assumptions=(),
        conversation_continuity=ConversationContinuityView(
            items=(
                ConversationContinuityItem(
                    item_id="memory-item:raw-user:current",
                    item_kind=ConversationContinuityKind.RAW_USER_TURN,
                    producer_kind=MemoryProducerKind.USER,
                    claim_status=MemoryClaimStatus.ASSUMPTION,
                    event_id=current_input.event_id,
                    event_sequence=current_input.event_sequence,
                    run_id=current_input.run_id,
                    summary_text=current_prompt,
                    label=None,
                    source_refs=(),
                    preserve_reason=None,
                    payload_ref=None,
                    payload_digest=None,
                    included_reason=MemoryIncludedReason.RECENT_RAW_TURN,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(len(current_prompt)),
                ),
            )
        ),
        diagnostics=(),
        built_at="2026-05-15T01:02:03.000000Z",
        snapshot_digest="pending",
    )
    return ConversationMemorySnapshot(
        snapshot_id=snapshot_without_digest.snapshot_id,
        session_id=snapshot_without_digest.session_id,
        cursor=snapshot_without_digest.cursor,
        policy_digest=snapshot_without_digest.policy_digest,
        pinned_state=snapshot_without_digest.pinned_state,
        evidence_backed_facts=snapshot_without_digest.evidence_backed_facts,
        working_assumptions=snapshot_without_digest.working_assumptions,
        conversation_continuity=snapshot_without_digest.conversation_continuity,
        diagnostics=snapshot_without_digest.diagnostics,
        built_at=snapshot_without_digest.built_at,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def _minimum_preserve_only_snapshot(
    *,
    session_id: str,
    policy: MemoryProjectionPolicy,
    cursor: MemorySnapshotCursor,
    source_event: EventLogRow,
    producer_event: EventLogRow,
    preserve_text: str,
) -> ConversationMemorySnapshot:
    """构造只保留 minimum preserve item 的 memory snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :param source_event: compact 前长输入 source event。
    :param producer_event: 生成 minimum preserve item 的 compact event。
    :param preserve_text: minimum preserve item 文本。
    :returns: memory snapshot。
    """

    policy_digest = digest_memory_projection_policy(policy)
    snapshot_without_digest = ConversationMemorySnapshot(
        snapshot_id=f"memory-snapshot-minimum-preserve-{session_id}",
        session_id=session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        pinned_state=PinnedStateView(
            current_goal=None,
            confirmed_subjects=(),
            user_constraints=(),
            open_questions=(),
        ),
        evidence_backed_facts=(),
        working_assumptions=(),
        conversation_continuity=ConversationContinuityView(
            items=(
                ConversationContinuityItem(
                    item_id="memory-item:minimum-preserve:second-factor",
                    item_kind=ConversationContinuityKind.MINIMUM_PRESERVE_ITEM,
                    producer_kind=MemoryProducerKind.HOST_PROJECTION,
                    claim_status=MemoryClaimStatus.ASSUMPTION,
                    event_id=producer_event.event_id,
                    event_sequence=producer_event.event_sequence,
                    run_id=producer_event.run_id,
                    summary_text=preserve_text,
                    label="第二个因素",
                    source_refs=(source_event.event_id,),
                    preserve_reason=(
                        MinimumPreserveReason.NEEDED_FOR_ORDERED_ITEM_REFERENCE
                    ),
                    payload_ref=None,
                    payload_digest=None,
                    included_reason=MemoryIncludedReason.MINIMUM_PRESERVE_ITEM,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(len(preserve_text)),
                ),
            )
        ),
        diagnostics=(),
        built_at="2026-05-15T01:02:03.000000Z",
        snapshot_digest="pending",
    )
    return ConversationMemorySnapshot(
        snapshot_id=snapshot_without_digest.snapshot_id,
        session_id=snapshot_without_digest.session_id,
        cursor=snapshot_without_digest.cursor,
        policy_digest=snapshot_without_digest.policy_digest,
        pinned_state=snapshot_without_digest.pinned_state,
        evidence_backed_facts=snapshot_without_digest.evidence_backed_facts,
        working_assumptions=snapshot_without_digest.working_assumptions,
        conversation_continuity=snapshot_without_digest.conversation_continuity,
        diagnostics=snapshot_without_digest.diagnostics,
        built_at=snapshot_without_digest.built_at,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def _write_memory_snapshot(
    transaction_runner: HostTransactionRunner,
    snapshot: ConversationMemorySnapshot,
) -> None:
    """写入 memory snapshot 与 projection checkpoint。

    :param transaction_runner: Host transaction runner。
    :param snapshot: memory snapshot。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: write_memory_snapshot_with_checkpoint(
            transaction,
            snapshot,
            now="2026-05-15T01:02:03.000000Z",
        )
    )


def _append_rich_memory_source_events(
    transaction_runner: HostTransactionRunner, session_id: str
) -> None:
    """追加 rich snapshot item 需要引用的 EventLog rows。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加 source events。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id="event-memory-tool",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-memory",
                event_type="TOOL_RESULT_ACCEPTED",
                payload={
                    "tool_name": "filing.lookup",
                    "tool_call_id": "call-memory",
                    "tool_fact_kind": "completed",
                    "fact_summary": "tool verified revenue increased",
                    "outcome_digest": _DIGEST_A,
                    "payload_digest": _DIGEST_B,
                },
            ),
        )
        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id="event-memory-assumption",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-memory",
                event_type="USER_INPUT_ACCEPTED",
                payload=_user_input_payload("margin mix may have shifted"),
            ),
        )
        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id="event-memory-raw-user",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-memory",
                event_type="USER_INPUT_ACCEPTED",
                payload=_user_input_payload("recent raw user"),
            ),
        )
        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id="event-memory-assistant",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-memory",
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "recent assistant conclusion"},
            ),
        )
        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id="event-memory-episode",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-memory",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="episode navigation only",
                    pinned_patch={
                        "candidate_id": "patch-memory",
                        "current_goal": {
                            "operation": "replace",
                            "value": "compact pinned goal",
                            "evidence_refs": ["evidence-1"],
                        },
                        "confirmed_subjects": {
                            "operation": "replace",
                            "value": ["subject:issuer-a"],
                            "evidence_refs": ["evidence-1"],
                        },
                        "open_questions": {
                            "operation": "replace",
                            "value": ["compact open question"],
                            "evidence_refs": ["evidence-1"],
                        },
                    },
                ),
            ),
        )

    transaction_runner.run_write(operation)


def _append_compacted_gross_margin_facts(
    transaction_runner: HostTransactionRunner, session_id: str
) -> None:
    """追加 gross-margin follow-up 需要的 compacted facts。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加 canonical evidence 与 compacted fact candidate events。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id="event-memory-gross-tool",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-memory-gross",
                event_type="TOOL_RESULT_ACCEPTED",
                payload={
                    "tool_name": "filing.lookup",
                    "tool_call_id": "call-memory-gross",
                    "tool_fact_kind": "completed",
                    "outcome_digest": _DIGEST_A,
                    "payload_digest": _DIGEST_B,
                },
            ),
        )
        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id="event-memory-gross-compact",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-memory-gross",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="gross margin episode navigation only",
                    pinned_patch={"candidate_id": "patch-gross-margin"},
                    fact_candidates=[
                        {
                            "candidate_id": "fact-revenue",
                            "claim_text": "Revenue was 100.",
                            "evidence_kind": "observed_value",
                            "evidence_refs": ["evidence:memory-tool"],
                            "attributes": {},
                        },
                        {
                            "candidate_id": "fact-gross-profit",
                            "claim_text": "Gross profit was 40.",
                            "evidence_kind": "observed_value",
                            "evidence_refs": ["evidence:memory-tool"],
                            "attributes": {},
                        },
                    ],
                ),
            ),
        )

    transaction_runner.run_write(operation)


def _append_minimum_preserve_compact_marker(
    transaction_runner: HostTransactionRunner, *, session_id: str
) -> EventLogRow:
    """追加 minimum preserve snapshot 的 compact producer event。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :returns: compact producer EventLog row。
    """

    def operation(transaction: HostTransaction) -> EventLogRow:
        """追加 compact marker event。

        :param transaction: Host transaction。
        :returns: compact producer EventLog row。
        """

        return EventLogStore().append_event(
            transaction,
            _event_request(
                event_id="event-compact-second-factor",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-long-input",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="long input compacted to minimum preserve",
                    pinned_patch={"candidate_id": "patch-second-factor"},
                    fact_candidates=[],
                    minimum_preserve_items=[
                        {
                            "item_id": "preserve-second-factor",
                            "label": "第二个因素",
                            "text": "第二个因素：毛利率受云业务拖累",
                            "source_refs": ["event-long-input"],
                            "preserve_reason": (
                                "needed_for_ordered_item_reference"
                            ),
                        }
                    ],
                ),
            ),
        ).row

    return transaction_runner.run_write(operation)


def _read_event_by_id(
    transaction_runner: HostTransactionRunner, event_id: str
) -> EventLogRow:
    """按 event id 读取测试 EventLog row。

    :param transaction_runner: Host transaction runner。
    :param event_id: event id。
    :returns: EventLog row。
    """

    def operation(transaction: HostTransaction) -> EventLogRow:
        """读取 EventLog row。

        :param transaction: Host transaction。
        :returns: EventLog row。
        """

        row = EventLogStore().read_event_by_id(transaction, event_id)
        assert row is not None
        return row

    return transaction_runner.run_read(operation)


def _message_occurrences(contents: tuple[str, ...], needle: str) -> int:
    """统计消息内容中包含指定文本的条数。

    :param contents: message content 元组。
    :param needle: 目标文本。
    :returns: 出现次数。
    """

    return sum(1 for content in contents if needle in content)


def _damage_memory_snapshot_json(
    transaction_runner: HostTransactionRunner, snapshot_id: str
) -> None:
    """破坏 durable snapshot JSON 内的 digest。

    :param transaction_runner: Host transaction runner。
    :param snapshot_id: snapshot id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """执行 JSON digest 破坏。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        row = transaction.fetchone(
            "SELECT snapshot_json FROM host_memory_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        assert row is not None
        snapshot_json = row.get("snapshot_json")
        assert isinstance(snapshot_json, str)
        damaged = snapshot_json.replace("sha256:", "sha256-damaged:", 1)
        transaction.execute(
            "UPDATE host_memory_snapshots SET snapshot_json = ? WHERE snapshot_id = ?",
            (damaged, snapshot_id),
        )

    transaction_runner.run_write(operation)


def _run_attempt_eventlog_state(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> tuple[str, str, int]:
    """读取 Run / Attempt 状态与 EventLog row 数。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded Run 引用。
    :returns: run status、attempt status 与 EventLog row 数。
    """

    def operation(transaction: HostTransaction) -> tuple[str, str, int]:
        """读取状态快照。

        :param transaction: Host transaction。
        :returns: 状态快照。
        """

        run = transaction.fetchone(
            "SELECT status FROM host_runs WHERE run_id = ?",
            (seeded.run_id,),
        )
        attempt = transaction.fetchone(
            "SELECT status FROM host_attempts WHERE attempt_id = ?",
            (seeded.attempt_id,),
        )
        total = transaction.fetchone("SELECT COUNT(*) AS total FROM event_log")
        assert run is not None
        assert attempt is not None
        assert total is not None
        run_status = run.get("status")
        attempt_status = attempt.get("status")
        eventlog_count = total.get("total")
        assert isinstance(run_status, str)
        assert isinstance(attempt_status, str)
        assert isinstance(eventlog_count, int)
        return run_status, attempt_status, eventlog_count

    return transaction_runner.run_read(operation)


def _append_prior_user_event(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    text: str,
) -> EventLogRow:
    """追加并返回历史 USER_INPUT_ACCEPTED event。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param text: 用户文本。
    :returns: EventLog row。
    """

    return transaction_runner.run_write(
        lambda transaction: _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=event_id,
            payload=_user_input_payload(text),
            event_class=EventClass.CANONICAL_FACT,
        )
    )


def _memory_projection_event_from_test_row(row: EventLogRow) -> MemoryProjectionEvent:
    """把测试 EventLog row 转成 memory projection event。

    :param row: EventLog row。
    :returns: MemoryProjectionEvent。
    """

    return MemoryProjectionEvent(
        event_sequence=row.event_sequence,
        event_id=row.event_id,
        event_class=row.event_class.value,
        event_type=row.event_type,
        session_id=row.session_id,
        run_id=row.run_id,
        attempt_id=row.attempt_id,
        execution_id=row.execution_id,
        occurred_at=row.occurred_at,
        payload_ref=row.payload_ref,
        payload_digest=row.payload_digest,
        payload={"display_text": _message_text_from_user_event(row)},
    )


def _message_text_from_user_event(row: EventLogRow) -> str:
    """从测试 USER_INPUT_ACCEPTED row 读取 display text。

    :param row: EventLog row。
    :returns: display text。
    """

    return _required_payload_text(_payload_object(row), field_name="display_text")


def _read_memory_checkpoint_sequence(
    transaction_runner: HostTransactionRunner,
) -> int:
    """读取 memory projection checkpoint sequence。

    :param transaction_runner: Host transaction runner。
    :returns: checkpoint sequence。
    """

    def operation(transaction: HostTransaction) -> int:
        """读取 checkpoint row。

        :param transaction: Host transaction。
        :returns: checkpoint sequence。
        """

        checkpoint = read_projection_checkpoint(
            transaction, CONVERSATION_MEMORY_CONSUMER_ID
        )
        assert checkpoint is not None
        return checkpoint.checkpoint_event_sequence

    return transaction_runner.run_read(operation)


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _context() -> HostCallContext:
    """构造标准 Host call context。

    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id="request-trace",
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="run_input_builder_test",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase5",
            correlation_id="corr-run-input",
        ),
    )


def _ensure_session_id(transaction_runner: HostTransactionRunner) -> str:
    """创建测试 Session 并返回 id。

    :param transaction_runner: Host transaction runner。
    :returns: Session id。
    """

    result = ensure_session(
        transaction_runner,
        EnsureSessionRequest(
            scope="workspace",
            slot_key="run-input",
            metadata=(HostMetadataEntry(key="case", value="run-input"),),
        ),
    )
    return result.snapshot.session_id


def _seed_current_run(
    store: HostDurableStore,
    *,
    session_id: str,
    payload: JsonValue,
) -> _SeededRun:
    """写入当前 running Run / STARTING Attempt / pending dispatch。

    :param store: Host durable store。
    :param session_id: Session id。
    :param payload: 当前 USER_INPUT_ACCEPTED payload。
    :returns: seeded Run 引用。
    """

    def operation(transaction: HostTransaction) -> _SeededRun:
        """执行当前 Run 写入。

        :param transaction: Host transaction。
        :returns: seeded Run 引用。
        """

        input_event = _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id="run-current",
            event_id="event-current-input",
            payload=payload,
            event_class=EventClass.CANONICAL_FACT,
        )
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id="run-current",
                client_request_id="request-current",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-current",
                run_started_event_id="event-run-started-current",
                attempt_started_event_id="event-attempt-started-current",
                attempt_id="attempt-current",
                execution_id="execution-current",
                dispatch_record_id="dispatch-current",
                occurred_at=_NOW,
                actor="analyst",
                source="pytest",
                idempotency_key="request-current",
                execution_target="local-default",
                queue_policy="queue",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-run-input",
                pid=1,
                process_start_token="run-input-test",
                boot_id=None,
            ),
        )
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id="attempt-current",
            owner_host_instance_id="host-run-input",
            lane_name="llm",
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id="attempt-current",
            owner_host_instance_id="host-run-input",
            lane_name="llm",
            lane_claim_id="claim-run-input",
            lane_owner_id="owner-run-input",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        return _SeededRun(
            session_id=session_id,
            run_id="run-current",
            attempt_id="attempt-current",
            execution_id="execution-current",
            dispatch_record_id="dispatch-current",
        )

    return store.transaction_runner.run_write(operation)


def _seed_current_run_with_descriptor(
    store: HostDurableStore,
    *,
    session_id: str,
    payload: dict[str, JsonValue],
) -> _SeededRun:
    """写入 descriptor USER_INPUT_ACCEPTED 的当前 running Run。

    :param store: Host durable store。
    :param session_id: Session id。
    :param payload: 完整 USER_INPUT_ACCEPTED payload。
    :returns: seeded Run 引用。
    """

    def operation(transaction: HostTransaction) -> _SeededRun:
        """执行当前 Run 写入。

        :param transaction: Host transaction。
        :returns: seeded Run 引用。
        """

        descriptor = PayloadStore().write_sqlite_payload(
            transaction,
            SQLitePayloadWriteRequest(
                payload_ref="payload-current-input",
                payload_id="sqlite-current-input",
                payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                payload_json=payload,
                media_type="application/json",
                metadata={"kind": "user_input_accepted"},
            ),
        )
        input_event = EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-current-input",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-current",
                attempt_id=None,
                execution_id=None,
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=_NOW,
                actor="analyst",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json={
                    "input_ref": None,
                    "input_digest": _INPUT_DIGEST,
                    "payload_ref": None,
                    "payload_digest": None,
                    "operation_kind": "start_run",
                    "call_context_digest": _CALL_CONTEXT_DIGEST,
                },
                payload_ref=descriptor.payload_ref,
                payload_digest=descriptor.payload_digest,
            ),
        ).row
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id="run-current",
                client_request_id="request-current",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-current",
                run_started_event_id="event-run-started-current",
                attempt_started_event_id="event-attempt-started-current",
                attempt_id="attempt-current",
                execution_id="execution-current",
                dispatch_record_id="dispatch-current",
                occurred_at=_NOW,
                actor="analyst",
                source="pytest",
                idempotency_key="request-current",
                execution_target="local-default",
                queue_policy="queue",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-run-input",
                pid=1,
                process_start_token="run-input-test",
                boot_id=None,
            ),
        )
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id="attempt-current",
            owner_host_instance_id="host-run-input",
            lane_name="llm",
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id="attempt-current",
            owner_host_instance_id="host-run-input",
            lane_name="llm",
            lane_claim_id="claim-run-input",
            lane_owner_id="owner-run-input",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        return _SeededRun(
            session_id=session_id,
            run_id="run-current",
            attempt_id="attempt-current",
            execution_id="execution-current",
            dispatch_record_id="dispatch-current",
        )

    return store.transaction_runner.run_write(operation)


def _force_dispatch_snapshot_state(
    transaction_runner: HostTransactionRunner,
    seeded: _SeededRun,
    *,
    run_status: RunStatus,
    attempt_status: AttemptStatus,
    dispatch_status: DispatchRecordStatus,
) -> None:
    """强制修改 RunInputBuilder 快照关联 durable 状态。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded Run 引用。
    :param run_status: 目标 Run 状态。
    :param attempt_status: 目标 Attempt 状态。
    :param dispatch_status: 目标 dispatch record 状态。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """执行状态改写。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        if run_status in (
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.LOST,
        ):
            run_event = EventLogStore().append_event(
                transaction,
                _event_request(
                    event_id="event-force-run-terminal",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="RUN_FAILED",
                    payload={"reason": "force_run_terminal"},
                ),
            ).row
            transaction.execute(
                "UPDATE host_runs "
                "SET status = ?, terminal_event_id = ?, "
                "terminal_event_sequence = ?, terminal_at = ? WHERE run_id = ?",
                (
                    run_status.value,
                    run_event.event_id,
                    run_event.event_sequence,
                    "2026-05-15T01:02:04.000000Z",
                    seeded.run_id,
                ),
            )
        else:
            transaction.execute(
                "UPDATE host_runs SET status = ? WHERE run_id = ?",
                (run_status.value, seeded.run_id),
            )
        if attempt_status in (
            AttemptStatus.SUCCEEDED,
            AttemptStatus.FAILED,
            AttemptStatus.CANCELLED,
            AttemptStatus.SUSPENDED,
            AttemptStatus.STEERED,
            AttemptStatus.LOST,
        ):
            attempt_event = EventLogStore().append_event(
                transaction,
                _event_request(
                    event_id="event-force-attempt-terminal",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="ATTEMPT_CANCELLED",
                    payload={"reason": "force_attempt_terminal"},
                ),
            ).row
            transaction.execute(
                "UPDATE host_attempts "
                "SET status = ?, terminal_event_id = ?, "
                "terminal_event_sequence = ?, terminal_at = ? WHERE attempt_id = ?",
                (
                    attempt_status.value,
                    attempt_event.event_id,
                    attempt_event.event_sequence,
                    "2026-05-15T01:02:04.000000Z",
                    seeded.attempt_id,
                ),
            )
        else:
            transaction.execute(
                "UPDATE host_attempts SET status = ? WHERE attempt_id = ?",
                (attempt_status.value, seeded.attempt_id),
            )
        if dispatch_status == DispatchRecordStatus.PENDING:
            transaction.execute(
                "UPDATE host_attempt_dispatch_records "
                "SET status = ?, owner_host_instance_id = NULL, "
                "waiting_for_lane_at = NULL, lane_name = NULL, "
                "lane_claim_id = NULL, lane_owner_id = NULL, "
                "lane_acquired_at = NULL, dispatching_at = NULL, "
                "worker_accepted_at = NULL, worker_accept_event_id = NULL, "
                "worker_accept_event_sequence = NULL, cancelled_event_id = NULL, "
                "cancelled_event_sequence = NULL, cancelled_at = NULL "
                "WHERE dispatch_record_id = ?",
                (dispatch_status.value, seeded.dispatch_record_id),
            )
        elif dispatch_status == DispatchRecordStatus.WAITING_FOR_LANE:
            transaction.execute(
                "UPDATE host_attempt_dispatch_records "
                "SET status = ?, owner_host_instance_id = ?, "
                "waiting_for_lane_at = ?, lane_name = ?, "
                "lane_claim_id = NULL, lane_owner_id = NULL, "
                "lane_acquired_at = NULL, dispatching_at = NULL, "
                "worker_accepted_at = NULL, worker_accept_event_id = NULL, "
                "worker_accept_event_sequence = NULL, cancelled_event_id = NULL, "
                "cancelled_event_sequence = NULL, cancelled_at = NULL "
                "WHERE dispatch_record_id = ?",
                (
                    dispatch_status.value,
                    "host-run-input",
                    "2026-05-15T01:02:03.000000Z",
                    "llm",
                    seeded.dispatch_record_id,
                ),
            )
        else:
            transaction.execute(
                "UPDATE host_attempt_dispatch_records "
                "SET status = ?, owner_host_instance_id = ?, "
                "waiting_for_lane_at = ?, lane_name = ?, "
                "lane_claim_id = ?, lane_owner_id = ?, "
                "lane_acquired_at = ?, dispatching_at = ?, "
                "worker_accepted_at = NULL, worker_accept_event_id = NULL, "
                "worker_accept_event_sequence = NULL, cancelled_event_id = NULL, "
                "cancelled_event_sequence = NULL, cancelled_at = NULL "
                "WHERE dispatch_record_id = ?",
                (
                    dispatch_status.value,
                    "host-run-input",
                    "2026-05-15T01:02:03.000000Z",
                    "llm",
                    "claim-run-input",
                    "owner-run-input",
                    "2026-05-15T01:02:03.000000Z",
                    "2026-05-15T01:02:03.000000Z",
                    seeded.dispatch_record_id,
                ),
            )

    transaction_runner.run_write(operation)


def _start_recovery_attempt(
    transaction_runner: HostTransactionRunner,
    old: _SeededRun,
) -> _SeededRun:
    """将旧 Attempt 收口为 RECOVERING 后创建 recovery Attempt。

    :param transaction_runner: Host transaction runner。
    :param old: 旧 Attempt seeded 引用。
    :returns: 新 recovery Attempt seeded 引用。
    """

    _force_dispatch_snapshot_state(
        transaction_runner,
        old,
        run_status=RunStatus.RECOVERING,
        attempt_status=AttemptStatus.LOST,
        dispatch_status=DispatchRecordStatus.DISPATCHING,
    )

    def operation(transaction: HostTransaction) -> _SeededRun:
        """执行 recovery start 并推进 dispatching。

        :param transaction: Host transaction。
        :returns: 新 recovery Attempt seeded 引用。
        """

        result = start_recovery_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            StartRecoveryRunInput(
                run_id=old.run_id,
                source_attempt_id=old.attempt_id,
                run_started_event_id="event-run-started-recovery-current",
                attempt_started_event_id="event-attempt-started-recovery-current",
                attempt_id="attempt-recovery-current",
                execution_id="execution-recovery-current",
                dispatch_record_id="dispatch-recovery-current",
                occurred_at=_NOW,
                actor="host_recovery",
                source="startup_scan",
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id="host-run-input",
                context_compacted_event_id=None,
                context_compacted_event_sequence=None,
            ),
        )
        assert result.status is StateMutationStatus.UPDATED
        assert result.run is not None
        assert result.attempt is not None
        assert result.dispatch_record is not None
        waiting = mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=result.attempt.attempt_id,
            owner_host_instance_id="host-run-input",
            lane_name="llm",
            waiting_for_lane_at="2026-05-15T01:02:05.000000Z",
        )
        assert waiting.status is StateMutationStatus.UPDATED
        dispatching = mark_dispatching_after_lane_row(
            transaction,
            attempt_id=result.attempt.attempt_id,
            owner_host_instance_id="host-run-input",
            lane_name="llm",
            lane_claim_id="claim-run-input-recovery",
            lane_owner_id="owner-run-input-recovery",
            lane_acquired_at="2026-05-15T01:02:05.000000Z",
            dispatching_at="2026-05-15T01:02:05.000000Z",
        )
        assert dispatching.status is StateMutationStatus.UPDATED
        return _SeededRun(
            session_id=old.session_id,
            run_id=old.run_id,
            attempt_id=result.attempt.attempt_id,
            execution_id=result.attempt.execution_id,
            dispatch_record_id=result.dispatch_record.dispatch_record_id,
        )

    return transaction_runner.run_write(operation)


def _build_request(
    store: HostDurableStore, seeded: _SeededRun
) -> AgentRunRequest:
    """通过默认 no-tool RunInputBuilder 构造 AgentRunRequest。

    :param store: Host durable store。
    :param seeded: seeded Run 引用。
    :returns: AgentRunRequest。
    """

    builder = create_no_tool_run_input_builder(
        transaction_runner=store.transaction_runner,
        policy_snapshot=_policy_snapshot(),
    )
    return builder.build(_attempt_snapshot(seeded))


def _attempt_snapshot(seeded: _SeededRun) -> AttemptDispatchSnapshot:
    """构造测试用 AttemptDispatchSnapshot。

    :param seeded: seeded Run 引用。
    :returns: AttemptDispatchSnapshot。
    """

    return AttemptDispatchSnapshot(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        dispatch_record_id=seeded.dispatch_record_id,
        execution_target="local-default",
        policy_snapshot_ref=_POLICY_REF,
        cancellation_token=_token(),
    )


def _token() -> CancellationToken:
    """构造测试用 cancellation token。

    :returns: 未取消 token。
    """

    return _OpenCancellationToken()


def _policy_snapshot(*, allow_tool_calls: bool = False) -> PolicySnapshot:
    """构造测试用 policy snapshot。

    :param allow_tool_calls: AgentPolicy 是否允许工具调用。
    :returns: PolicySnapshot。
    """

    return PolicySnapshot(
        runner_spec=RunnerSpec(
            provider="test",
            model="test-model",
            endpoint="https://example.invalid/v1",
            api_key_ref="test-key",
            headers={},
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            default_timeout_seconds=30.0,
            max_retries=0,
            provider_request=None,
        ),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=False,
        ),
        agent_policy=AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=0,
            allow_tool_calls=allow_tool_calls,
            tool_execution_timeout_seconds=1.0,
        ),
        policy_snapshot_ref=_POLICY_REF,
    )


def _tool_runtime_handle() -> ToolRuntimeHandle:
    """构造测试用 ToolRuntimeHandle。

    :returns: ToolRuntimeHandle。
    """

    return DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(
                    definitions=(_tool_definition("lookup_filing"),)
                ),
                source_refs=(
                    ToolBundleSourceRef(
                        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                        source_id="run-input-test-provider",
                    ),
                ),
                framework_tool_policy=default_framework_tool_policy_view(),
                policy_snapshot_digest=_POLICY_REF,
            )
        )
    )


async def _tool_callable(
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
) -> ToolExecutionOutcome:
    """测试用工具 callable。

    :param call: 单次工具调用请求。
    :param context: 批式工具执行上下文。
    :returns: 测试用取消 outcome。
    :raises Exception: 不主动抛出异常。
    """

    del call, context
    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
        message="test tool callable",
        hint=None,
        meta=None,
    )


def _tool_definition(name: str) -> ToolDefinition:
    """构造测试用工具声明。

    :param name: 工具名。
    :returns: 工具声明。
    """

    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=f"{name} test tool",
                parameters=_tool_parameters(),
            ),
        ),
        callable=_tool_callable,
        truncate=None,
        display=None,
        tags=(),
    )


def _tool_parameters() -> ToolParametersSchema:
    """构造测试用工具参数 schema。

    :returns: 工具参数 schema。
    """

    properties: dict[str, JsonValue] = {
        "ticker": {"type": "string"},
    }
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker",),
        additional_properties=False,
    )


def _append_prior_user_and_success(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    user_text: str,
    answer_text: str,
) -> None:
    """追加一组历史 user / assistant continuity facts。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: 历史 Run id。
    :param user_text: user message 文本。
    :param answer_text: assistant answer 文本。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加历史 facts。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=f"event-{run_id}-input",
            payload=_user_input_payload(user_text),
            event_class=EventClass.CANONICAL_FACT,
        )
        _append_success_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=f"event-{run_id}-success",
            answer_text=answer_text,
            event_class=EventClass.CANONICAL_FACT,
        )

    transaction_runner.run_write(operation)


def _append_prior_user(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    text: str,
) -> None:
    """追加历史 USER_INPUT_ACCEPTED canonical fact。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param text: user 文本。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=event_id,
            payload=_user_input_payload(text),
            event_class=EventClass.CANONICAL_FACT,
        )
    )


def _append_prior_user_and_terminal(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    user_text: str,
    terminal_event_type: str,
) -> None:
    """追加一个非成功历史 Run 的 user 与 terminal fact。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param user_text: user 文本。
    :param terminal_event_type: terminal event type。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加测试 facts。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=f"event-{run_id}-input",
            payload=_user_input_payload(user_text),
            event_class=EventClass.CANONICAL_FACT,
        )
        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id=f"event-{run_id}-terminal",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                event_type=terminal_event_type,
                payload={"reason": terminal_event_type.lower()},
            ),
        )

    transaction_runner.run_write(operation)


def _append_prior_success(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    answer_text: str,
) -> None:
    """追加历史 RUN_SUCCEEDED canonical fact。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param answer_text: assistant answer 文本。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: _append_success_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=event_id,
            answer_text=answer_text,
            event_class=EventClass.CANONICAL_FACT,
        )
    )


def _append_projection_signal(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
) -> None:
    """追加应被 RunInputBuilder 忽略的 projection_signal 事件。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: EventLogStore().append_event(
            transaction,
            _event_request(
                event_id="event-projection-signal",
                event_class=EventClass.PROJECTION_SIGNAL,
                session_id=session_id,
                run_id=run_id,
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "ignored projection"},
            ),
        )
    )


def _append_preview_user_input(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
) -> None:
    """追加应被 RunInputBuilder 忽略的 preview user input 事件。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id="event-preview-user",
            payload=_user_input_payload("ignored preview"),
            event_class=EventClass.PREVIEW,
        )
    )


def _append_user_input_tx(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    payload: JsonValue,
    event_class: EventClass,
) -> EventLogRow:
    """在 transaction 内追加 USER_INPUT_ACCEPTED event。

    :param transaction: Host transaction。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param payload: event payload。
    :param event_class: event class。
    :returns: EventLog row。
    """

    return EventLogStore().append_event(
        transaction,
        _event_request(
            event_id=event_id,
            event_class=event_class,
            session_id=session_id,
            run_id=run_id,
            event_type="USER_INPUT_ACCEPTED",
            payload=payload,
        ),
    ).row


def _append_success_tx(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    answer_text: str,
    event_class: EventClass,
) -> EventLogRow:
    """在 transaction 内追加 RUN_SUCCEEDED event。

    :param transaction: Host transaction。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param answer_text: assistant answer 文本。
    :param event_class: event class。
    :returns: EventLog row。
    """

    return EventLogStore().append_event(
        transaction,
        _event_request(
            event_id=event_id,
            event_class=event_class,
            session_id=session_id,
            run_id=run_id,
            event_type="RUN_SUCCEEDED",
            payload={"final_answer": answer_text},
        ),
    ).row


def _event_request(
    *,
    event_id: str,
    event_class: EventClass,
    session_id: str,
    run_id: str,
    event_type: str,
    payload: JsonValue,
) -> EventLogAppendRequest:
    """构造测试用 EventLog append request。

    :param event_id: event id。
    :param event_class: event class。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_type: event type。
    :param payload: payload。
    :returns: EventLogAppendRequest。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=event_class,
        session_id=session_id,
        run_id=run_id,
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _user_input_payload(text: str) -> dict[str, JsonValue]:
    """构造 USER_INPUT_ACCEPTED payload。

    :param text: display text。
    :returns: payload dict。
    """

    return {
        "input_ref": None,
        "input_digest": _INPUT_DIGEST,
        "display_text": text,
        "payload_ref": None,
        "payload_digest": None,
        "operation_kind": "start_run",
        "call_context_digest": _CALL_CONTEXT_DIGEST,
    }


def _compact_payload(
    *,
    summary_text: str,
    pinned_patch: dict[str, JsonValue],
    fact_candidates: list[JsonValue] | None = None,
    minimum_preserve_items: list[JsonValue] | None = None,
) -> dict[str, JsonValue]:
    """构造测试用 CONTEXT_COMPACTED payload。

    :param summary_text: episode summary 文本。
    :param pinned_patch: pinned patch candidate。
    :param fact_candidates: 可选 evidence-backed fact candidates。
    :param minimum_preserve_items: 可选 minimum preserve item candidates。
    :returns: compacted payload。
    """

    resolved_fact_candidates: list[JsonValue]
    if fact_candidates is None:
        resolved_fact_candidates = [
            {
                "candidate_id": "fact-memory-revenue",
                "claim_text": "Revenue increased year over year",
                "evidence_kind": "observed_value",
                "evidence_refs": ["evidence:memory-tool"],
                "attributes": {},
            }
        ]
    else:
        resolved_fact_candidates = fact_candidates
    resolved_minimum_preserve_items: list[JsonValue]
    if minimum_preserve_items is None:
        resolved_minimum_preserve_items = [
            {
                "item_id": "preserve-factor-2",
                "label": "factor-2",
                "text": "second factor: margin mix",
                "source_refs": ["event-memory-raw-user"],
                "preserve_reason": "needed_for_ordered_item_reference",
            }
        ]
    else:
        resolved_minimum_preserve_items = minimum_preserve_items

    episode_summary: dict[str, JsonValue] = {
        "candidate_id": "summary-memory",
        "summary_text": summary_text,
        "episode_title": "episode",
        "goal": "compact goal",
        "completed_actions": [],
        "confirmed_fact_refs": [],
        "confirmed_fact_summaries": [],
        "user_constraints": [],
        "open_questions": ["compact open question"],
        "next_step": None,
        "tool_finding_refs": [],
        "source_event_refs": ["event-memory-raw-user"],
        "evidence_refs": ["evidence-1"],
        "proposed_evidence_backed_fact_refs": [],
    }
    preservation_evidence: list[JsonValue] = [
        {
            "evidence_id": "evidence-1",
            "material_source_refs": ["event-memory-raw-user"],
            "canonical_evidence_refs": ["evidence:memory-tool"],
            "evidence_backed_fact_refs": [],
            "memory_snapshot_cursor": None,
            "compact_input_range": None,
        }
    ]
    preserved_fact_refs: dict[str, JsonValue] = {
        "canonical_evidence_refs": ["evidence:memory-tool"],
        "evidence_backed_fact_refs": [],
    }
    quality_check_result: dict[str, JsonValue] = {
        "accepted": True,
        "rejection_reasons": [],
        "current_user_input_retained": True,
        "canonical_evidence_refs_retained": True,
        "evidence_backed_fact_candidates_accepted": True,
        "minimum_preserve_items_accepted": True,
        "evidence_anchors_retained": True,
        "open_questions_retained": True,
        "retained_canonical_evidence_refs": ["evidence:memory-tool"],
        "dropped_ranges": [],
        "summarized_ranges": [],
    }
    payload: dict[str, JsonValue] = {
        "compact_artifact_ref": "compact-artifact:test",
        "compact_artifact_digest": _DIGEST_A,
        "episode_summary_candidate": episode_summary,
        "pinned_state_patch_candidate": pinned_patch,
        "evidence_backed_fact_candidates": resolved_fact_candidates,
        "minimum_preserve_item_candidates": resolved_minimum_preserve_items,
        "preservation_evidence": preservation_evidence,
        "preserved_fact_refs": preserved_fact_refs,
        "dropped_ranges": [],
        "summarized_ranges": [],
        "evidence_anchors_retained": True,
        "quality_check_result": quality_check_result,
        "budget_after_compact": 128,
    }
    return payload


def _message_content(message: AgentMessage) -> str:
    """读取测试关心的 message 内容。

    :param message: Engine message。
    :returns: message content。
    :raises AssertionError: assistant content 缺失时抛出。
    """

    if isinstance(message, AssistantMessage):
        assert message.content is not None
        return message.content
    if isinstance(message, SystemMessage | UserMessage):
        return message.content
    raise AssertionError("tool messages are not expected in RunInputBuilder tests")


def _expected_system_content() -> str:
    """构造期望 system message 内容。

    :returns: system message content。
    """

    return "\n".join(
        (
            "Host execution context:",
            "operation_kind=start_run",
            "execution_target=local-default",
            "queue_policy=queue",
            f"policy_snapshot_ref={_POLICY_REF}",
            "tools=disabled",
        )
    )


def _table_counts(
    transaction_runner: HostTransactionRunner,
) -> tuple[int, int, int]:
    """统计 RunInputBuilder 不应写入的 durable table 数量。

    :param transaction_runner: Host transaction runner。
    :returns: event_log、payload_descriptors、sqlite_payloads row 数。
    """

    def operation(transaction: HostTransaction) -> tuple[int, int, int]:
        """读取 table counts。

        :param transaction: Host transaction。
        :returns: 三个 table row 数。
        """

        return (
            _count_table(transaction, "event_log"),
            _count_table(transaction, "payload_descriptors"),
            _count_table(transaction, "host_sqlite_payloads"),
        )

    return transaction_runner.run_read(operation)


def _count_table(transaction: HostTransaction, table_name: str) -> int:
    """统计指定 table 的 row 数。

    :param transaction: Host transaction。
    :param table_name: table name。
    :returns: row 数。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {table_name}")
    assert row is not None
    return _required_int(row, "total")


def _required_int(row: HostRow, column: str) -> int:
    """从 HostRow 读取整数。

    :param row: Host row。
    :param column: column name。
    :returns: int 值。
    """

    value = row.get(column)
    assert isinstance(value, int)
    return value
