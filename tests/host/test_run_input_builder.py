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
from dayu.contracts.tool_execution import AsyncDirectToolExecutionCapability
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
from dayu.engine.contracts.engine_events import runner_role_sequence_digest
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
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
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
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
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
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
)
from dayu.host.compact_material import (
    RunInputMaterialBlock,
    run_input_material_block,
    selected_material_view_digest,
)
from dayu.host.context_fallback import (
    ActiveRecentWindowFallback,
    EventLogContextFallbackProvider,
    build_recent_window_fallback_selection,
    estimate_recent_window_fallback_budget,
    fallback_window_digest,
)
from dayu.host.context_policy import (
    ContextCompactionTriggerSource,
    context_budget_policy_from_threshold_tokens,
)
from dayu.host.memory_repair import catch_up_conversation_memory_projection
from dayu.host.payload_resolution import event_payload_object
from dayu.host.run_input import (
    CompactArtifactView,
    CurrentRunFacts,
    DurableCompactArtifactProvider,
    DurableCurrentRunFactProvider,
    DurableMemorySnapshotProvider,
    MemoryProjectionRepairRequired,
    NoopMemorySnapshotProvider,
    NoToolExecutor,
    PolicySnapshot,
    ToolExecutionMode,
    MemorySnapshotView,
    _SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS,
    _accepted_evidence_mapping_refs,
    _compact_artifact_message_content,
    _fallback_context_messages,
    _is_internal_evidence_source_part,
    _llm_facing_evidence_source_text,
    _normalize_ordinary_run_messages,
    _resume_wait_message_from_current_start,
    _vnext_compact_candidate_semantic_lines,
    create_no_tool_run_input_builder,
    create_tool_enabled_run_input_builder,
)
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    OpaqueEvidenceRef,
    accepted_evidence_envelope_to_json_value,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    AnswerAnchor,
    AnswerAnchorChild,
    AnswerAnchorMemoryView,
    ConversationMemorySnapshotVNext,
    EvidenceFactMemoryView,
    ForwardIntent,
    ForwardIntentMemoryView,
    MemoryClaimStatus,
    MemoryDiagnosticReason,
    MemoryEvidenceBackedFactKind,
    MemoryIncludedReason,
    MemoryProducerKind,
    MemoryProjectionEvent,
    MemoryProjectionPolicy,
    MemoryProvenanceRef,
    MemoryRepairReason,
    MemorySizeUnits,
    MemorySnapshotCursor,
    EvidenceBackedFactView,
    ReferenceContinuityItem,
    SelectedRecentWindowItem,
    SelectedRecentWindowRole,
    SessionSummaryMemoryView,
    TraceMemoryView,
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


@dataclass(frozen=True, slots=True)
class _SeededAcceptedEvidence:
    """测试中创建的 accepted tool evidence。"""

    tool_call_event_id: str
    tool_result_event_id: str
    accepted_evidence_id: str
    semantic_query_text: str
    raw_outcome: JsonValue


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


@dataclass(frozen=True, slots=True)
class _StaticContextFallbackProvider:
    """测试用静态 fallback provider。"""

    fallback: ActiveRecentWindowFallback | None

    def load_context_fallback(
        self,
        *,
        run_id: str,
        run_started_event_sequence: int,
        current_input_ref: str,
    ) -> ActiveRecentWindowFallback | None:
        """返回预置 fallback view。

        :param run_id: 当前 Run id。
        :param run_started_event_sequence: 当前 ``RUN_STARTED`` event sequence。
        :param current_input_ref: 当前输入 ref。
        :returns: 预置 fallback view。
        """

        del run_id, run_started_event_sequence, current_input_ref
        return self.fallback


@dataclass(frozen=True, slots=True)
class _StaticMemorySnapshotProvider:
    """测试用静态 memory snapshot provider。"""

    view: MemorySnapshotView

    def load_memory_snapshot(
        self,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
    ) -> MemorySnapshotView:
        """返回预置 memory view。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: 预置 memory view。
        """

        del snapshot, current_facts
        return self.view


@dataclass(frozen=True, slots=True)
class _StaticCompactArtifactProvider:
    """测试用静态 compact artifact provider。"""

    view: CompactArtifactView

    def load_compact_artifact(
        self,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
    ) -> CompactArtifactView:
        """返回预置 compact artifact view。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: 预置 compact artifact view。
        """

        del snapshot, current_facts
        return self.view


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


def test_resume_wait_message_appends_shared_duplicate_result_guidance(
    tmp_path: Path,
) -> None:
    """resume wait result message 追加重复请求共享结果说明且不泄漏内部 ref。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("resume prompt"),
        )
        _append_resume_wait_projection_events(store.transaction_runner, seeded)
        current_facts = DurableCurrentRunFactProvider(
            store.transaction_runner
        ).load_current_run_facts(_attempt_snapshot(seeded))
        resume_started = _read_event_by_id(
            store.transaction_runner,
            "event-run-started-resume",
        )

        def operation(transaction: HostTransaction) -> SystemMessage:
            """构造 resume wait result message。

            :param transaction: Host durable transaction。
            :returns: resume wait system message。
            """

            message = _resume_wait_message_from_current_start(
                transaction,
                replace(current_facts, run_started_event=resume_started),
            )
            assert message is not None
            return message

        message = store.transaction_runner.run_read(operation)

        assert "A previous interrupted step has an accepted wait result." in (
            message.content
        )
        assert "tool_name=fake_tool" in message.content
        assert "resolution_kind=completed" in message.content
        assert "tool_fact_kind=completed" in message.content
        assert 'result={"ok":true,"value":{"answer":42}}' in message.content
        assert "duplicate requests for the same tool with the same arguments" in (
            message.content
        )
        assert "Do not call the same tool again only to obtain the same result." in (
            message.content
        )
        assert "wait-resume-private" not in message.content
        assert "tool-call-private" not in message.content
        assert "event-tool-result-resume" not in message.content
        assert "payload-ref-private" not in message.content
        assert "sha256:" not in message.content
        assert "attempt-current" not in message.content
        assert "execution-current" not in message.content


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
        assert len(
            _events_by_type(
                store.transaction_runner,
                event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            )
        ) == 1


def test_runner_call_manifest_is_bounded_and_does_not_inline_messages(
    tmp_path: Path,
) -> None:
    """大输入只进入 request message，不完整内联到 runner-call manifest。"""

    large_prompt = "read filing " + ("x" * 20000)
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload(large_prompt),
        )

        request = _build_request(store, seeded)
        manifest_events = _events_by_type(
            store.transaction_runner,
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
        )
        manifest_event = manifest_events[0]
        hot_payload = _payload_object(manifest_event)
        manifest = store.transaction_runner.run_read(
            lambda transaction: event_payload_object(
                transaction,
                manifest_event,
                payload_label="runner-call manifest",
            )
        )
        manifest_text = canonical_json_dumps(manifest)
        hot_text = canonical_json_dumps(hot_payload)

        assert len(manifest_events) == 1
        assert hot_payload["message_count"] == len(request.messages)
        assert hot_payload["role_sequence_digest"] == runner_role_sequence_digest(
            tuple(message.role.value for message in request.messages)
        )
        assert manifest_event.payload_ref == hot_payload["manifest_payload_ref"]
        assert manifest_event.payload_digest == hot_payload["manifest_digest"]
        assert manifest["message_count"] == len(request.messages)
        assert len(manifest_text) < 5000
        assert "x" * 128 not in hot_text
        assert "x" * 128 not in manifest_text
        assert large_prompt == _message_content(request.messages[-1])


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


def test_noop_providers_only_create_runner_call_manifest_rows(tmp_path: Path) -> None:
    """noop providers 只额外创建 runner-call manifest durable rows。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )
        before = _table_counts(store.transaction_runner)

        _build_request(store, seeded)

        after = _table_counts(store.transaction_runner)
        assert after == (before[0] + 1, before[1] + 1, before[2] + 1)


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
        assert "Tools are disabled" not in _message_content(request.messages[0])
        assert "Tools are available for this runner call." in _message_content(
            request.messages[0]
        )


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

        assert request.attempt_id == seeded.attempt_id
        assert request.execution_id == seeded.execution_id
        assert request.disable_tools is True
        assert request.tool_schemas == ()
        assert request.agent_policy.allow_tool_calls is False
        assert isinstance(request.tool_executor, NoToolExecutor)
        assert "Tools are disabled for this runner call." in _message_content(
            request.messages[0]
        )


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


def test_system_envelope_boundedness_allows_multiple_items_in_same_section() -> None:
    """system envelope 有界校验必须允许同一 section 内多条 material。"""

    messages: tuple[AgentMessage, ...] = (
        SystemMessage(role=AgentMessageRole.SYSTEM, content="first instruction"),
        SystemMessage(role=AgentMessageRole.SYSTEM, content="second instruction"),
        UserMessage(role=AgentMessageRole.USER, content="current prompt"),
    )

    normalized = _normalize_ordinary_run_messages(messages)
    system_content = _single_system_content(normalized)

    assert system_content == "\n".join(
        (
            "## Task Instructions",
            "first instruction",
            "second instruction",
        )
    )
    assert _message_content(normalized[-1]) == "current prompt"


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

        system_content = _single_system_content(request.messages)
        assert system_content.startswith(_expected_system_content())
        assert "## Conversation Summary" in system_content
        assert "summary=compare revenue quality; use reported currency" in system_content
        assert "## Verified Evidence and Facts" in system_content
        assert "claim_text=Revenue increased year over year" in system_content
        assert "evidence_kind=derived_from_evidence" in system_content
        assert "evidence_refs=" not in system_content
        assert "extraction_operation_ref=" not in system_content
        assert "event_id=" not in system_content
        assert "event_sequence=" not in system_content
        assert "digest_ref=" not in system_content
        assert "fact_summary=" not in system_content
        assert "## Prior Answer Anchors" in system_content
        assert "## Open Follow-up Context" in system_content
        assert "## Reference Continuity" in system_content
        assert "text=second factor: margin mix" in system_content
        assert contents[1] == "recent raw user"
        assert contents[2] == "recent assistant conclusion"
        assert contents[-1] == "current prompt"
        assert all("inline delta" not in content for content in contents)
        assert all(
            diagnostic.reason is not MemoryDiagnosticReason.INLINE_DELTA_REPAIR_INCLUDED
            for diagnostic in memory_view.diagnostics
        )


def test_memory_provider_renders_vnext_fact_section_from_snapshot(tmp_path: Path) -> None:
    """RunInputBuilder 渲染持久化 vNext fact section。"""

    policy = _memory_policy(evidence_fact_char_cap=24)
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

        assert "## Verified Evidence and Facts" in _single_system_content(
            request.messages
        )
        assert "recent raw user" in contents
        assert contents[-1] == "current prompt"
        assert all(
            diagnostic.reason is not MemoryDiagnosticReason.BUDGET_LIMIT_REACHED
            for diagnostic in memory_view.diagnostics
        )


def test_vnext_fact_section_does_not_depend_on_old_subject_blocks(
    tmp_path: Path,
) -> None:
    """vNext fact section 不依赖旧 subject blocks。"""

    policy = _memory_policy(evidence_fact_char_cap=512)
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

        assert "## Verified Evidence and Facts" in _single_system_content(
            request.messages
        )
        assert all(
            not content.startswith("Memory confirmed subjects and methodology:")
            for content in contents
        )
        assert all(
            diagnostic.reason is not MemoryDiagnosticReason.BUDGET_LIMIT_REACHED
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
        assert blocks[0].turn_group_id == seeded.run_id


def test_run_input_builder_accepted_tool_evidence_material_has_no_private_row_cap(
    tmp_path: Path,
) -> None:
    """真实 provider 入口可读取超过旧 8 条的 accepted evidence blocks。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded_evidence = _append_prior_accepted_tool_evidence_batch(
            store.transaction_runner,
            session_id=session_id,
            count=10,
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt after accepted evidence"),
        )
        builder = create_no_tool_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=_policy_snapshot(),
        )

        blocks = builder.build_material_blocks(_attempt_snapshot(seeded))
        evidence_blocks = _accepted_tool_evidence_blocks(blocks)

        assert len(evidence_blocks) == 10
        assert tuple(block.accepted_evidence_id for block in evidence_blocks) == tuple(
            evidence.accepted_evidence_id for evidence in seeded_evidence
        )
        assert evidence_blocks[-1].text == canonical_json_dumps(
            seeded_evidence[-1].raw_outcome
        )


def test_run_input_builder_represented_refs_exclude_whole_accepted_evidence_blocks(
    tmp_path: Path,
) -> None:
    """memory 与 compact 已表示的 evidence refs 会 whole-block 排除。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded_evidence = _append_prior_accepted_tool_evidence_batch(
            store.transaction_runner,
            session_id=session_id,
            count=3,
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt after represented evidence"),
        )
        memory_view = MemorySnapshotView(
            messages=(),
            memory_snapshot_cursor=None,
            policy_digest=None,
            diagnostics=(),
            represented_evidence_refs=(
                seeded_evidence[0].accepted_evidence_id,
            ),
        )
        compact_view = CompactArtifactView(
            messages=(),
            compact_artifact_ref="compact-artifact:test",
            compact_artifact_digest=None,
            represented_evidence_refs=(
                seeded_evidence[1].accepted_evidence_id,
            ),
        )
        builder = create_no_tool_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=_policy_snapshot(),
            memory_snapshot_provider=_StaticMemorySnapshotProvider(memory_view),
            compact_artifact_provider=_StaticCompactArtifactProvider(compact_view),
        )

        blocks = builder.build_material_blocks(_attempt_snapshot(seeded))
        evidence_blocks = _accepted_tool_evidence_blocks(blocks)

        assert tuple(block.accepted_evidence_id for block in evidence_blocks) == (
            seeded_evidence[2].accepted_evidence_id,
        )
        assert evidence_blocks[0].text == canonical_json_dumps(
            seeded_evidence[2].raw_outcome
        )


def test_run_input_builder_accepted_tool_evidence_uses_raw_outcome_text(
    tmp_path: Path,
) -> None:
    """accepted evidence material 使用 raw outcome 与可读 query，不用 ref/digest。"""

    raw_outcome: JsonValue = {
        "kind": "completed",
        "result": {
            "text": "full raw outcome for LLM material",
            "preview_decoy": "not a result_preview field",
        },
    }
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded_evidence = _append_prior_accepted_tool_evidence_batch(
            store.transaction_runner,
            session_id=session_id,
            count=1,
            raw_outcome=raw_outcome,
            semantic_query_text="Read MSFT FY2025 revenue from filing",
        )[0]
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt after raw evidence"),
        )
        builder = create_no_tool_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=_policy_snapshot(),
        )

        blocks = builder.build_material_blocks(_attempt_snapshot(seeded))
        evidence_block = _accepted_tool_evidence_blocks(blocks)[0]

        assert evidence_block.text == canonical_json_dumps(raw_outcome)
        assert "full raw outcome for LLM material" in evidence_block.text
        assert _DIGEST_A not in evidence_block.text
        assert seeded_evidence.tool_result_event_id not in evidence_block.text
        assert evidence_block.readable_tool_name == "fins.search"
        assert evidence_block.readable_query_text == (
            "Read MSFT FY2025 revenue from filing"
        )
        assert evidence_block.accepted_evidence_id == (
            seeded_evidence.accepted_evidence_id
        )
        assert evidence_block.canonical_source_refs == (
            seeded_evidence.accepted_evidence_id,
        )
        assert evidence_block.payload_refs == (
            f"payload:{seeded_evidence.tool_result_event_id}",
        )
        assert evidence_block.tool_call_event_ref == seeded_evidence.tool_call_event_id


def test_recent_window_fallback_selection_is_stable_and_budget_bounded() -> None:
    """fallback selection 稳定保留 floor，且不会追加超过 hard budget 的下一块。"""

    policy = context_budget_policy_from_threshold_tokens(
        context_window_size=120,
        soft_threshold_tokens=70,
        hard_threshold_tokens=90,
        policy_ref="test-fallback-policy",
    )
    blocks = (
        _material_block(
            "stable:goals",
            CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
            CompactMaterialBlockKind.SESSION_SUMMARY,
            "stable goal",
            event_sequence=None,
        ),
        _material_block(
            "history:old",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "older raw turn",
            event_sequence=1,
            turn_group_id="run-old",
        ),
        _material_block(
            "history:blocked",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            "x" * 180,
            event_sequence=3,
            turn_group_id="run-blocked",
        ),
        _material_block(
            "history:recent",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "recent raw turn",
            event_sequence=4,
            turn_group_id="run-recent",
        ),
        _material_block(
            "current:event-current",
            CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            "current prompt",
            event_sequence=5,
            source_ref="event-current",
        ),
    )

    first = build_recent_window_fallback_selection(
        policy=policy,
        memory_policy=_memory_policy(),
        session_id="session-fallback",
        run_id="run-fallback",
        material_blocks=blocks,
        current_input_ref="event-current",
        input_cursor=5,
        selected_recent_window_turn_floor=1,
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    )
    second = build_recent_window_fallback_selection(
        policy=policy,
        memory_policy=_memory_policy(),
        session_id="session-fallback",
        run_id="run-fallback",
        material_blocks=blocks,
        current_input_ref="event-current",
        input_cursor=5,
        selected_recent_window_turn_floor=1,
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    )
    budget = estimate_recent_window_fallback_budget(
        policy=policy,
        session_id="session-fallback",
        run_id="run-fallback",
        selection_blocks=first.selected_blocks,
        current_input_ref="event-current",
    )

    assert first.selected_block_ids == second.selected_block_ids
    assert first.digest == second.digest
    assert "history:recent" in first.selected_block_ids
    assert "history:old" not in first.selected_block_ids
    assert first.blocked_next_block_id == "history:blocked"
    assert first.to_window_payload()["selected_raw_turn_count"] == 1
    assert budget.hard_budget_passed is True


def test_recent_window_fallback_floor_preserves_turn_group_blocks_over_caps() -> None:
    """fallback floor 按 turn group 保留全部 eligible blocks，且不受 caps 裁剪。"""

    policy = context_budget_policy_from_threshold_tokens(
        context_window_size=500,
        soft_threshold_tokens=300,
        hard_threshold_tokens=420,
        policy_ref="test-fallback-policy",
    )
    memory_policy = MemoryProjectionPolicy(
        context_window_size=8192,
        selected_recent_window_item_cap=4,
        selected_recent_window_char_cap=4096,
        selected_recent_window_turn_floor=1,
        fallback_selected_recent_window_item_cap=1,
        fallback_selected_recent_window_char_cap=10,
        evidence_fact_item_cap=16,
        evidence_fact_char_cap=2048,
        evidence_fact_floor=1,
        session_summary_char_cap=1024,
        answer_anchor_item_cap=4,
        answer_anchor_char_cap=1024,
        forward_intent_item_cap=4,
        forward_intent_char_cap=1024,
        reference_continuity_item_cap=4,
        reference_continuity_char_cap=1024,
        reference_continuity_item_floor=0,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
        policy_ref="run-input-builder-test",
    )
    blocks = (
        _material_block(
            "old:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "old",
            event_sequence=1,
            turn_group_id="run-old",
        ),
        _material_block(
            "new:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "new user",
            event_sequence=2,
            turn_group_id="run-new",
        ),
        _material_block(
            "new:answer",
            CompactMaterialSection.ANSWER_MATERIAL,
            CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            "new answer",
            event_sequence=3,
            turn_group_id="run-new",
        ),
        _material_block(
            "new:evidence",
            CompactMaterialSection.EVIDENCE_MATERIAL,
            CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
            "new evidence",
            event_sequence=4,
            turn_group_id="run-new",
        ),
        _material_block(
            "current:event-current",
            CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            "current",
            event_sequence=5,
            source_ref="event-current",
        ),
    )

    selection = build_recent_window_fallback_selection(
        policy=policy,
        memory_policy=memory_policy,
        session_id="session-fallback",
        run_id="run-fallback",
        material_blocks=blocks,
        current_input_ref="event-current",
        input_cursor=5,
        selected_recent_window_turn_floor=1,
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    )

    assert selection.selected_block_ids == (
        "new:user",
        "new:answer",
        "new:evidence",
        "current:event-current",
    )
    assert "old:user" in selection.dropped_block_ids


def test_recent_window_fallback_caps_stop_without_later_backfill() -> None:
    """fallback caps 拒绝下一 whole block 后不选择更旧 block 规避顺序。"""

    policy = context_budget_policy_from_threshold_tokens(
        context_window_size=500,
        soft_threshold_tokens=300,
        hard_threshold_tokens=420,
        policy_ref="test-fallback-policy",
    )
    memory_policy = _memory_policy(
        selected_recent_window_char_cap=120,
        fallback_selected_recent_window_char_cap=120,
    )
    blocks = (
        _material_block(
            "old:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "old",
            event_sequence=1,
            turn_group_id="run-old",
        ),
        _material_block(
            "mid:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "m" * 150,
            event_sequence=2,
            turn_group_id="run-mid",
        ),
        _material_block(
            "new:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "new",
            event_sequence=3,
            turn_group_id="run-new",
        ),
        _material_block(
            "current:event-current",
            CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            "current",
            event_sequence=4,
            source_ref="event-current",
        ),
    )

    selection = build_recent_window_fallback_selection(
        policy=policy,
        memory_policy=memory_policy,
        session_id="session-fallback",
        run_id="run-fallback",
        material_blocks=blocks,
        current_input_ref="event-current",
        input_cursor=4,
        selected_recent_window_turn_floor=1,
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    )

    assert selection.selected_block_ids == ("new:user", "current:event-current")
    assert selection.blocked_next_block_id == "mid:user"
    assert "old:user" in selection.dropped_block_ids


def test_recent_window_fallback_item_cap_rejects_append() -> None:
    """fallback item cap 到达上限后拒绝追加下一 whole block。"""

    policy = context_budget_policy_from_threshold_tokens(
        context_window_size=500,
        soft_threshold_tokens=300,
        hard_threshold_tokens=420,
        policy_ref="test-fallback-policy",
    )
    memory_policy = _memory_policy(
        fallback_selected_recent_window_item_cap=2,
        fallback_selected_recent_window_char_cap=4096,
    )
    blocks = (
        _material_block(
            "old:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "old",
            event_sequence=1,
            turn_group_id="run-old",
        ),
        _material_block(
            "mid:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "mid",
            event_sequence=2,
            turn_group_id="run-mid",
        ),
        _material_block(
            "new:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "new",
            event_sequence=3,
            turn_group_id="run-new",
        ),
        _material_block(
            "current:event-current",
            CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            "current",
            event_sequence=4,
            source_ref="event-current",
        ),
    )

    selection = build_recent_window_fallback_selection(
        policy=policy,
        memory_policy=memory_policy,
        session_id="session-fallback",
        run_id="run-fallback",
        material_blocks=blocks,
        current_input_ref="event-current",
        input_cursor=4,
        selected_recent_window_turn_floor=1,
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    )

    assert selection.selected_block_ids == ("new:user", "current:event-current")
    assert selection.blocked_next_block_id == "mid:user"
    assert "old:user" in selection.dropped_block_ids


def test_recent_window_fallback_char_cap_rejects_append() -> None:
    """fallback char cap 到达上限后拒绝追加下一 whole block。"""

    policy = context_budget_policy_from_threshold_tokens(
        context_window_size=500,
        soft_threshold_tokens=300,
        hard_threshold_tokens=420,
        policy_ref="test-fallback-policy",
    )
    memory_policy = _memory_policy(
        fallback_selected_recent_window_item_cap=8,
        fallback_selected_recent_window_char_cap=10,
    )
    blocks = (
        _material_block(
            "old:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "old",
            event_sequence=1,
            turn_group_id="run-old",
        ),
        _material_block(
            "mid:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "mid",
            event_sequence=2,
            turn_group_id="run-mid",
        ),
        _material_block(
            "new:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "new",
            event_sequence=3,
            turn_group_id="run-new",
        ),
        _material_block(
            "current:event-current",
            CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            "current",
            event_sequence=4,
            source_ref="event-current",
        ),
    )

    selection = build_recent_window_fallback_selection(
        policy=policy,
        memory_policy=memory_policy,
        session_id="session-fallback",
        run_id="run-fallback",
        material_blocks=blocks,
        current_input_ref="event-current",
        input_cursor=4,
        selected_recent_window_turn_floor=1,
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    )

    assert selection.selected_block_ids == ("new:user", "current:event-current")
    assert selection.blocked_next_block_id == "mid:user"
    assert "old:user" in selection.dropped_block_ids


def test_recent_window_fallback_without_memory_policy_allows_uncapped_append() -> None:
    """memory_policy 为 None 时保留旧调用点无 caps 追加语义。"""

    policy = context_budget_policy_from_threshold_tokens(
        context_window_size=500,
        soft_threshold_tokens=300,
        hard_threshold_tokens=420,
        policy_ref="test-fallback-policy",
    )
    blocks = (
        _material_block(
            "old:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "old",
            event_sequence=1,
            turn_group_id="run-old",
        ),
        _material_block(
            "mid:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "mid",
            event_sequence=2,
            turn_group_id="run-mid",
        ),
        _material_block(
            "new:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "new",
            event_sequence=3,
            turn_group_id="run-new",
        ),
        _material_block(
            "current:event-current",
            CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            "current",
            event_sequence=4,
            source_ref="event-current",
        ),
    )

    selection = build_recent_window_fallback_selection(
        policy=policy,
        memory_policy=None,
        session_id="session-fallback",
        run_id="run-fallback",
        material_blocks=blocks,
        current_input_ref="event-current",
        input_cursor=4,
        selected_recent_window_turn_floor=1,
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    )

    assert selection.selected_block_ids == (
        "old:user",
        "mid:user",
        "new:user",
        "current:event-current",
    )
    assert selection.blocked_next_block_id is None


def test_recent_window_fallback_hard_budget_rolls_back_appended_block() -> None:
    """追加 block 超 hard budget 时整块回滚并停止。"""

    policy = context_budget_policy_from_threshold_tokens(
        context_window_size=140,
        soft_threshold_tokens=90,
        hard_threshold_tokens=105,
        policy_ref="test-fallback-policy",
    )
    memory_policy = _memory_policy(
        selected_recent_window_char_cap=4096,
        fallback_selected_recent_window_char_cap=4096,
    )
    blocks = (
        _material_block(
            "old:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "old",
            event_sequence=1,
            turn_group_id="run-old",
        ),
        _material_block(
            "mid:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "m" * 2000,
            event_sequence=2,
            turn_group_id="run-mid",
        ),
        _material_block(
            "new:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "new",
            event_sequence=3,
            turn_group_id="run-new",
        ),
        _material_block(
            "current:event-current",
            CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            "current",
            event_sequence=4,
            source_ref="event-current",
        ),
    )

    selection = build_recent_window_fallback_selection(
        policy=policy,
        memory_policy=memory_policy,
        session_id="session-fallback",
        run_id="run-fallback",
        material_blocks=blocks,
        current_input_ref="event-current",
        input_cursor=4,
        selected_recent_window_turn_floor=1,
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    )

    assert selection.selected_block_ids == ("new:user", "current:event-current")
    assert selection.blocked_next_block_id == "mid:user"
    budget = estimate_recent_window_fallback_budget(
        policy=policy,
        session_id="session-fallback",
        run_id="run-fallback",
        selection_blocks=selection.selected_blocks,
        current_input_ref="event-current",
    )
    assert budget.hard_budget_passed is True


def test_recent_window_fallback_floor_only_over_hard_budget_is_fail_closed_input() -> None:
    """floor-only 超 hard budget 时 selection 不裁剪 floor，预算结果由调用方 fail closed。"""

    policy = context_budget_policy_from_threshold_tokens(
        context_window_size=90,
        soft_threshold_tokens=50,
        hard_threshold_tokens=70,
        policy_ref="test-fallback-policy",
    )
    blocks = (
        _material_block(
            "new:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "n" * 210,
            event_sequence=1,
            turn_group_id="run-new",
        ),
        _material_block(
            "current:event-current",
            CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            "current",
            event_sequence=2,
            source_ref="event-current",
        ),
    )

    selection = build_recent_window_fallback_selection(
        policy=policy,
        memory_policy=_memory_policy(),
        session_id="session-fallback",
        run_id="run-fallback",
        material_blocks=blocks,
        current_input_ref="event-current",
        input_cursor=2,
        selected_recent_window_turn_floor=1,
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    )
    budget = estimate_recent_window_fallback_budget(
        policy=policy,
        session_id="session-fallback",
        run_id="run-fallback",
        selection_blocks=selection.selected_blocks,
        current_input_ref="event-current",
    )

    assert selection.selected_block_ids == ("new:user", "current:event-current")
    assert budget.hard_budget_passed is False


def test_recent_window_fallback_rejects_missing_turn_group_id_for_floor() -> None:
    """floor 依赖的 eligible fallback block 缺 turn_group_id 时不静默跳过。"""

    policy = context_budget_policy_from_threshold_tokens(
        context_window_size=500,
        soft_threshold_tokens=300,
        hard_threshold_tokens=420,
        policy_ref="test-fallback-policy",
    )
    blocks = (
        _material_block(
            "missing:user",
            CompactMaterialSection.TRACE_MATERIAL,
            CompactMaterialBlockKind.USER_INPUT,
            "missing",
            event_sequence=1,
        ),
        _material_block(
            "current:event-current",
            CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            "current",
            event_sequence=2,
            source_ref="event-current",
        ),
    )

    with pytest.raises(ValueError, match="missing turn_group_id"):
        build_recent_window_fallback_selection(
            policy=policy,
            memory_policy=_memory_policy(),
            session_id="session-fallback",
            run_id="run-fallback",
            material_blocks=blocks,
            current_input_ref="event-current",
            input_cursor=2,
            selected_recent_window_turn_floor=1,
            trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        )


def test_recent_window_fallback_estimate_covers_normal_empty_stable_and_over_budget() -> None:
    """fallback estimate 覆盖 normal、无 stable input 与 over-budget。"""

    policy = context_budget_policy_from_threshold_tokens(
        context_window_size=90,
        soft_threshold_tokens=50,
        hard_threshold_tokens=70,
        policy_ref="test-fallback-estimate-policy",
    )
    current = _material_block(
        "current:event-current",
        CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
        "current prompt",
        event_sequence=2,
        source_ref="event-current",
    )
    normal = estimate_recent_window_fallback_budget(
        policy=policy,
        session_id="session-fallback",
        run_id="run-fallback",
        selection_blocks=(
            _material_block(
                "stable:goals",
                CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                CompactMaterialBlockKind.SESSION_SUMMARY,
                "stable goal",
                event_sequence=None,
            ),
            current,
        ),
        current_input_ref="event-current",
    )
    empty_stable = estimate_recent_window_fallback_budget(
        policy=policy,
        session_id="session-fallback",
        run_id="run-fallback",
        selection_blocks=(current,),
        current_input_ref="event-current",
    )
    over_budget = estimate_recent_window_fallback_budget(
        policy=policy,
        session_id="session-fallback",
        run_id="run-fallback",
        selection_blocks=(
            _material_block(
                "current:event-current",
                CompactMaterialSection.CURRENT_INPUT_ANCHOR,
                CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
                "x" * 210,
                event_sequence=2,
                source_ref="event-current",
            ),
        ),
        current_input_ref="event-current",
    )

    assert normal.hard_budget_passed is True
    assert empty_stable.hard_budget_passed is True
    assert over_budget.hard_budget_passed is False
    assert over_budget.to_payload()["status"] == "over_hard_budget"


def test_fallback_provider_renders_only_selected_window_and_current_input(
    tmp_path: Path,
) -> None:
    """RunInputBuilder fallback view 只渲染 selected recent window 与当前输入。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        fallback = _active_fallback(
            selected_blocks=(
                _material_block(
                    "memory:2",
                    CompactMaterialSection.TRACE_MATERIAL,
                    CompactMaterialBlockKind.USER_INPUT,
                    "selected recent raw turn",
                    event_sequence=None,
                    source_ref="memory:no-snapshot",
                ),
                _material_block(
                    "current:event-current-input",
                    CompactMaterialSection.CURRENT_INPUT_ANCHOR,
                    CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
                    "current prompt",
                    event_sequence=None,
                    source_ref="event-current-input",
                ),
            ),
            dropped_block_ids=("memory:0", "memory:1"),
            current_input_ref="event-current-input",
        )
        builder = create_no_tool_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=_policy_snapshot(),
            memory_snapshot_provider=_StaticMemorySnapshotProvider(
                MemorySnapshotView(
                    messages=(
                        UserMessage(
                            role=AgentMessageRole.USER,
                            content="dropped older raw turn",
                        ),
                        AssistantMessage(
                            role=AgentMessageRole.ASSISTANT,
                            content="dropped older assistant turn",
                            reasoning_content=None,
                            tool_calls=(),
                        ),
                        UserMessage(
                            role=AgentMessageRole.USER,
                            content="selected recent raw turn",
                        ),
                    ),
                    memory_snapshot_cursor=None,
                    policy_digest=None,
                    diagnostics=(),
                )
            ),
            context_fallback_provider=_StaticContextFallbackProvider(fallback),
        )

        request = builder.build(_attempt_snapshot(seeded))
        contents = tuple(_message_content(message) for message in request.messages)

        assert "selected recent raw turn" in contents
        assert "current prompt" in contents
        assert "dropped older raw turn" not in contents
        assert "dropped older assistant turn" not in contents


def test_fallback_context_messages_render_all_and_only_selected_blocks() -> None:
    """fallback renderer 只消费 selected ids，并保持 source refs 同源校验。"""

    old = _material_block(
        "old:user",
        CompactMaterialSection.TRACE_MATERIAL,
        CompactMaterialBlockKind.USER_INPUT,
        "dropped old user",
        event_sequence=1,
        source_ref="event-old",
        turn_group_id="run-old",
    )
    selected = _material_block(
        "selected:assistant",
        CompactMaterialSection.ANSWER_MATERIAL,
        CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
        "selected answer",
        event_sequence=2,
        source_ref="event-selected-answer",
        turn_group_id="run-selected",
    )
    current = _material_block(
        "current:event-current",
        CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
        "current prompt",
        event_sequence=3,
        source_ref="event-current",
    )
    fallback = _active_fallback(
        selected_blocks=(selected, current),
        dropped_block_ids=(old.block_id,),
        current_input_ref="event-current",
    )

    messages = _fallback_context_messages(
        fallback=fallback,
        material_blocks=(old, selected, current),
    )

    assert tuple(_message_content(message) for message in messages) == (
        "selected answer",
    )
    assert fallback.source_refs == ("event-selected-answer", "event-current")


@pytest.mark.parametrize(
    ("case_name", "message"),
    (
        ("missing_window", "active fallback input window is missing"),
        ("digest_mismatch", "fallback input digest mismatch"),
        ("missing_current_ref", "fallback current_input_ref is missing"),
        ("current_ref_mismatch", "fallback current_input_ref mismatch"),
        ("missing_material_digest", "selected_material_view_digest"),
        ("blank_material_digest", "selected_material_view_digest"),
        ("missing_raw_turn_count", "selected_raw_turn_count"),
        ("negative_raw_turn_count", "selected_raw_turn_count"),
        ("missing_turn_floor", "selected_recent_window_turn_floor"),
        ("bad_turn_floor_type", "selected_recent_window_turn_floor"),
    ),
)
def test_eventlog_context_fallback_provider_fail_closes_on_payload_drift(
    tmp_path: Path,
    case_name: str,
    message: str,
) -> None:
    """EventLog fallback provider 对 active fallback payload 漂移 fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )
        _append_context_fallback_failed_event(
            store.transaction_runner,
            session_id=session_id,
            case_name=case_name,
        )
        provider = EventLogContextFallbackProvider(store.transaction_runner)

        with pytest.raises(HostDurableError, match=message):
            provider.load_context_fallback(
                run_id="run-current",
                run_started_event_sequence=999,
                current_input_ref="event-current-input",
            )


@pytest.mark.parametrize(
    ("case_name", "message"),
    (
        ("missing_id", "missing from material view"),
        ("duplicate_id", "selected block ids must be unique"),
        ("current_input_ref", "current_input_ref mismatch"),
        ("source_refs", "selected source refs mismatch"),
        ("fallback_digest", "input digest mismatch"),
        ("material_view_digest", "material view digest mismatch"),
    ),
)
def test_fallback_context_messages_fail_closed_on_selected_view_drift(
    case_name: str,
    message: str,
) -> None:
    """selected id、source ref、digest 与当前 material view 漂移时 fail closed。"""

    selected = _material_block(
        "selected:user",
        CompactMaterialSection.TRACE_MATERIAL,
        CompactMaterialBlockKind.USER_INPUT,
        "selected",
        event_sequence=1,
        source_ref="event-selected",
        turn_group_id="run-selected",
    )
    current = _material_block(
        "current:event-current",
        CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
        "current",
        event_sequence=2,
        source_ref="event-current",
    )
    material_blocks = (
        selected,
        current,
    )
    selected_block_ids = {
        "missing_id": ("selected:user", "missing:block", "current:event-current"),
        "duplicate_id": ("selected:user", "selected:user", "current:event-current"),
    }.get(case_name)
    fallback = _active_fallback(
        selected_blocks=(selected, current),
        current_input_ref=(
            "event-other-current" if case_name == "current_input_ref" else "event-current"
        ),
        selected_block_ids=selected_block_ids,
        source_refs=(
            ("event-stale", "event-current")
            if case_name == "source_refs"
            else None
        ),
        fallback_input_digest=(
            _DIGEST_A if case_name == "fallback_digest" else None
        ),
        selected_material_view_digest=(
            _DIGEST_B if case_name == "material_view_digest" else None
        ),
    )

    with pytest.raises(HostDurableError, match=message):
        _fallback_context_messages(
            fallback=fallback,
            material_blocks=material_blocks,
    )


def test_fallback_context_messages_fail_closed_on_selected_raw_turn_count_mismatch() -> None:
    """fallback 记录的 selected raw turn count 与当前 selected blocks 不一致时 fail closed。"""

    selected = _material_block(
        "selected:user",
        CompactMaterialSection.TRACE_MATERIAL,
        CompactMaterialBlockKind.USER_INPUT,
        "selected",
        event_sequence=1,
        source_ref="event-selected",
        turn_group_id="run-selected",
    )
    current = _material_block(
        "current:event-current",
        CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
        "current",
        event_sequence=2,
        source_ref="event-current",
    )
    fallback = _active_fallback(
        selected_blocks=(selected, current),
        current_input_ref="event-current",
        selected_raw_turn_count=2,
    )

    with pytest.raises(HostDurableError, match="selected raw turn count mismatch"):
        _fallback_context_messages(
            fallback=fallback,
            material_blocks=(selected, current),
        )


def test_fallback_context_messages_fail_closed_on_protected_group_mismatch() -> None:
    """protected floor group 有 block 缺失于 selected ids 时 fail closed。"""

    protected_user = _material_block(
        "new:user",
        CompactMaterialSection.TRACE_MATERIAL,
        CompactMaterialBlockKind.USER_INPUT,
        "new user",
        event_sequence=2,
        source_ref="event-new-user",
        turn_group_id="run-new",
    )
    protected_answer = _material_block(
        "new:answer",
        CompactMaterialSection.ANSWER_MATERIAL,
        CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
        "new answer",
        event_sequence=3,
        source_ref="event-new-answer",
        turn_group_id="run-new",
    )
    current = _material_block(
        "current:event-current",
        CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
        "current",
        event_sequence=4,
        source_ref="event-current",
    )
    fallback = _active_fallback(
        selected_blocks=(protected_user, current),
        current_input_ref="event-current",
        selected_recent_window_turn_floor=1,
    )

    with pytest.raises(HostDurableError, match="protected group consistency mismatch"):
        _fallback_context_messages(
            fallback=fallback,
            material_blocks=(protected_user, protected_answer, current),
        )


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


def test_inline_delta_includes_vnext_memory_sections(tmp_path: Path) -> None:
    """inline delta 修复后包含 vNext memory sections。"""

    policy = _memory_policy(
        max_lag_events_for_inline_delta=16,
        evidence_fact_char_cap=24,
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
        assert any("prior memory prompt" in content for content in contents)


def test_inline_delta_uses_memory_filter_and_covers_required_cursor(
    tmp_path: Path,
) -> None:
    """inline repair 只投影 memory facts，但 cursor 覆盖 required row。"""

    policy = _memory_policy(max_lag_events_for_inline_delta=16)
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
        _append_inline_repair_filter_noise(store.transaction_runner, session_id)
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
        required_cursor = _required_memory_cursor(store.transaction_runner, seeded)
        contents = tuple(_message_content(message) for message in memory_view.messages)
        cursor_ref = memory_view.memory_snapshot_cursor
        assert cursor_ref is not None

        assert any("prior memory prompt" in content for content in contents)
        assert any("matching assistant answer" in content for content in contents)
        assert all(
            "preview should not enter memory" not in content for content in contents
        )
        assert all(
            "diagnostic should not enter memory" not in content for content in contents
        )
        assert all(
            "canonical unrelated should not enter memory" not in content
            for content in contents
        )
        assert all(
            "foreign session should not enter memory" not in content
            for content in contents
        )
        assert (
            f"checkpoint_event_sequence={required_cursor.checkpoint_event_sequence}"
            in cursor_ref
        )
        assert (
            f"checkpoint_event_id={required_cursor.checkpoint_event_id}" in cursor_ref
        )


def test_inline_delta_no_matching_rows_still_covers_required_cursor(
    tmp_path: Path,
) -> None:
    """无 matching memory rows 时，covered cursor 足够则返回原 snapshot 与诊断。"""

    policy = _memory_policy(max_lag_events_for_inline_delta=16)
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
        snapshot = build_conversation_memory_snapshot_from_events(
            events=(),
            session_id=session_id,
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            policy=policy,
            built_at="2026-05-15T01:02:03.000000Z",
        )
        snapshot = replace(
            snapshot,
            cursor=MemorySnapshotCursor(
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                checkpoint_event_sequence=current_input.event_sequence,
                checkpoint_event_id=current_input.event_id,
                session_id=session_id,
            ),
        )
        snapshot = replace(
            snapshot,
            snapshot_digest=calculate_memory_snapshot_digest(snapshot),
        )
        _write_memory_snapshot(store.transaction_runner, snapshot)

        current_facts = DurableCurrentRunFactProvider(
            store.transaction_runner
        ).load_current_run_facts(_attempt_snapshot(seeded))
        memory_view = DurableMemorySnapshotProvider(
            store.transaction_runner, policy
        ).load_memory_snapshot(_attempt_snapshot(seeded), current_facts)
        required_cursor = _required_memory_cursor(store.transaction_runner, seeded)
        cursor_ref = memory_view.memory_snapshot_cursor
        assert cursor_ref is not None

        assert memory_view.messages == ()
        assert any(
            diagnostic.reason is MemoryDiagnosticReason.INLINE_DELTA_REPAIR_INCLUDED
            for diagnostic in memory_view.diagnostics
        )
        assert (
            f"checkpoint_event_sequence={required_cursor.checkpoint_event_sequence}"
            in cursor_ref
        )
        assert (
            f"checkpoint_event_id={required_cursor.checkpoint_event_id}" in cursor_ref
        )


def test_inline_delta_unable_to_cover_required_cursor_raises_repair_required(
    tmp_path: Path,
) -> None:
    """filtered read 无法证明覆盖 required cursor 时仍要求 projection repair。"""

    policy = _memory_policy(max_lag_events_for_inline_delta=16)
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
        provider = DurableMemorySnapshotProvider(store.transaction_runner, policy)

        with pytest.raises(MemoryProjectionRepairRequired) as exc_info:
            store.transaction_runner.run_read(
                lambda transaction: provider._repair_inline_delta(
                    transaction,
                    snapshot=snapshot,
                    required_event_sequence=prior_event.event_sequence + 1,
                    lag_events=1,
                )
            )

        assert (
            exc_info.value.repair_request.reason is MemoryRepairReason.SNAPSHOT_DAMAGED
        )


def test_inline_delta_uses_terminal_content_and_ignores_summary_fallback(
    tmp_path: Path,
) -> None:
    """inline delta 只用 final_answer / terminal content 渲染 assistant continuity。"""

    policy = _memory_policy(max_lag_events_for_inline_delta=16)
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

        def append_delta_events(transaction: HostTransaction) -> None:
            """追加 inline delta 会消费的 RUN_SUCCEEDED 测试事件。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-terminal-answer",
                    payload_id="sqlite-terminal-answer",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={
                        "content": "terminal artifact final answer",
                        "summary_text": "terminal artifact summary",
                    },
                ),
            )
            EventLogStore().append_event(
                transaction,
                _event_request(
                    event_id="event-terminal-answer",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=session_id,
                    run_id="run-terminal-answer",
                    event_type="RUN_SUCCEEDED",
                    payload={
                        "content": "bare run content should not render",
                        "summary_text": "run summary should not render",
                        "terminal_summary_ref": descriptor.payload_ref,
                        "terminal_summary_digest": descriptor.payload_digest,
                    },
                ),
            )
            EventLogStore().append_event(
                transaction,
                _event_request(
                    event_id="event-summary-only",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=session_id,
                    run_id="run-summary-only",
                    event_type="RUN_SUCCEEDED",
                    payload={
                        "summary_text": "summary-only should not render",
                        "summary": {"summary_text": "nested summary should not render"},
                    },
                ),
            )

        store.transaction_runner.run_write(append_delta_events)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current prompt"),
        )

        request = _build_request_with_memory(store, seeded, policy)
        contents = tuple(_message_content(message) for message in request.messages)

        assert "terminal artifact final answer" in contents
        assert "terminal artifact summary" not in contents
        assert "run summary should not render" not in contents
        assert "summary-only should not render" not in contents
        assert "nested summary should not render" not in contents
        assert "bare run content should not render" not in contents


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
    """ordinary RunInput 读取 accepted compact 物化出的五类 memory section。"""

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
        system_content = _single_system_content(request.messages)

        assert "## Conversation Summary" in system_content
        assert any("summary=episode navigation only" in content for content in contents)
        assert "## Verified Evidence and Facts" in system_content
        assert "claim_text=Revenue increased year over year" in system_content
        assert "## Prior Answer Anchors" in system_content
        assert any("compact pinned goal" in content for content in contents)
        assert "## Open Follow-up Context" in system_content
        assert any("compact open question" in content for content in contents)
        assert "## Reference Continuity" in system_content
        assert any("second factor: margin mix" in content for content in contents)
        assert contents[-1] == "current prompt"


def test_gross_margin_followup_uses_post_compact_evidence_backed_facts(
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
        system_content = _single_system_content(request.messages)

        assert "## Verified Evidence and Facts" in system_content
        assert "claim_text=Revenue was 100." in system_content
        assert "claim_text=Gross profit was 40." in system_content
        assert "evidence_refs=" not in system_content
        assert all(
            "older raw says revenue 100 and gross profit 40" not in content
            for content in contents
        )
        assert contents[-1] == "请基于已确认的收入和毛利计算毛利率"


def test_run_input_builder_renders_claim_text_and_evidence_refs_not_digest_only(
    tmp_path: Path,
) -> None:
    """RunInputBuilder 渲染 stable facts 时包含 claim_text 且不暴露内部 ref。"""

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
        system_content = _single_system_content(request.messages)

        assert "## Verified Evidence and Facts" in system_content
        assert "claim_text=Revenue was 100." in system_content
        assert "claim_text=Gross profit was 40." in system_content
        assert "evidence_refs=" not in system_content
        assert "digest_ref=" not in system_content
        assert "fact_summary=" not in system_content


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
            not content.startswith("Evidence / Fact Memory:")
            for content in contents
        )
        assert contents[-1] == "继续说明这个增长因素"


def test_post_compaction_ordinary_build_preserves_protected_recent_raw_tail(
    tmp_path: Path,
) -> None:
    """compact-success 后普通 build 保留最近历史 raw user / answer / evidence。"""

    policy = _memory_policy()
    answer_text = _four_item_answer()
    current_prompt = "详细解释第三条"
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user_and_success(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-ordinal-answer",
            user_text="请列出四条关键风险",
            answer_text=answer_text,
        )
        _append_prior_accepted_tool_evidence_batch(
            store.transaction_runner,
            session_id=session_id,
            count=1,
            run_id="run-ordinal-answer",
            raw_outcome={
                "kind": "completed",
                "result": {"text": "第三条风险来自客户集中度原始证据"},
            },
            semantic_query_text="读取客户集中度风险证据",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload(current_prompt),
        )
        _append_current_run_compacted_event(store.transaction_runner, seeded)
        recovery = _start_recovery_attempt(store.transaction_runner, seeded)

        request = _build_post_compaction_request(store, recovery, policy)
        contents = tuple(_message_content(message) for message in request.messages)
        system_content = _single_system_content(request.messages)

        assert "请列出四条关键风险" in contents
        assert answer_text in contents
        assert "3. 第三条是客户集中度升高，需要拆解前五大客户变化。" in (
            "\n".join(contents)
        )
        assert "第三条风险来自客户集中度原始证据" in system_content
        assert "## Recent Evidence" in system_content
        assert _message_occurrences(contents, current_prompt) == 1
        assert contents[-1] == current_prompt
        assert all("tool_call_id" not in content for content in contents)
        assert all("event-prior-tool" not in content for content in contents)


def test_post_compaction_raw_tail_dedupes_memory_selected_recent_window(
    tmp_path: Path,
) -> None:
    """memory selected recent window 已覆盖的 raw tail 不重复渲染。"""

    policy = _memory_policy()
    answer_text = _four_item_answer()
    current_prompt = "详细解释第三条"
    memory_view = MemorySnapshotView(
        messages=(
            UserMessage(
                role=AgentMessageRole.USER,
                content="请列出四条关键风险",
            ),
            AssistantMessage(
                role=AgentMessageRole.ASSISTANT,
                content=answer_text,
                reasoning_content=None,
                tool_calls=(),
            ),
        ),
        memory_snapshot_cursor=None,
        policy_digest=None,
        diagnostics=(),
        selected_recent_source_refs=(
            "event-run-ordinal-answer-input",
            "event-run-ordinal-answer-success",
        ),
        selected_recent_content_digests=(
            sha256_digest_json({"text": "请列出四条关键风险"}),
            sha256_digest_json({"text": answer_text}),
        ),
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user_and_success(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-ordinal-answer",
            user_text="请列出四条关键风险",
            answer_text=answer_text,
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload(current_prompt),
        )
        _append_current_run_compacted_event(store.transaction_runner, seeded)
        recovery = _start_recovery_attempt(store.transaction_runner, seeded)

        builder = create_no_tool_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=_policy_snapshot(),
            memory_projection_policy=policy,
            memory_snapshot_provider=_StaticMemorySnapshotProvider(memory_view),
            compact_artifact_provider=DurableCompactArtifactProvider(
                store.transaction_runner
            ),
        )
        request = builder.build(_attempt_snapshot(recovery))
        contents = tuple(_message_content(message) for message in request.messages)

        assert _message_occurrences(contents, "请列出四条关键风险") == 1
        assert _message_occurrences(contents, answer_text) == 1
        assert _message_occurrences(contents, current_prompt) == 1
        assert contents[-1] == current_prompt


def test_post_compaction_raw_tail_skips_without_compact_or_in_fallback(
    tmp_path: Path,
) -> None:
    """raw-tail provider 只在 accepted compact 且非 fallback ordinary path 激活。"""

    policy = _memory_policy()
    answer_text = _four_item_answer()
    current_prompt = "详细解释第三条"
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user_and_success(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-ordinal-answer",
            user_text="请列出四条关键风险",
            answer_text=answer_text,
        )
        seeded_without_compact = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload(current_prompt),
        )
        no_compact = _build_post_compaction_request(
            store,
            seeded_without_compact,
            policy,
        )

        assert all(
            answer_text not in _message_content(message)
            for message in no_compact.messages
        )

    with open_host_durable_store(_options(tmp_path / "fallback")) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user_and_success(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-ordinal-answer",
            user_text="请列出四条关键风险",
            answer_text=answer_text,
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload(current_prompt),
        )
        _append_current_run_compacted_event(store.transaction_runner, seeded)
        recovery = _start_recovery_attempt(store.transaction_runner, seeded)
        fallback = _active_fallback(
            selected_blocks=(
                _material_block(
                    "current:event-current-input",
                    CompactMaterialSection.CURRENT_INPUT_ANCHOR,
                    CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
                    current_prompt,
                    event_sequence=None,
                    source_ref="event-current-input",
                ),
            ),
            dropped_block_ids=(),
            current_input_ref="event-current-input",
        )
        builder = create_no_tool_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=_policy_snapshot(),
            memory_projection_policy=policy,
            compact_artifact_provider=DurableCompactArtifactProvider(
                store.transaction_runner
            ),
            context_fallback_provider=_StaticContextFallbackProvider(fallback),
        )

        request = builder.build(_attempt_snapshot(recovery))
        contents = tuple(_message_content(message) for message in request.messages)

        assert all(answer_text not in content for content in contents)
        assert _message_occurrences(contents, current_prompt) == 1
        assert contents[-1] == current_prompt


@pytest.mark.parametrize(
    ("source_text", "expected"),
    (
        (None, None),
        ("", None),
        ("tool_call_event:event-a, payload:payload-a, digest:sha256-a", None),
        (
            "tool_call_event:event-a, filing:msft-10k, payload:payload-a",
            "filing:msft-10k",
        ),
        ("filing:msft-10k, page:42", "filing:msft-10k, page:42"),
    ),
)
def test_llm_facing_evidence_source_text_filters_internal_provenance(
    source_text: str | None, expected: str | None
) -> None:
    """evidence source 过滤内部 provenance 且保留业务可读 source。"""

    assert _llm_facing_evidence_source_text(source_text) == expected


@pytest.mark.parametrize(
    ("source_part", "expected"),
    (
        ("tool_call_event:event-a", True),
        ("tool_result_event:event-b", True),
        ("event:event-c", True),
        ("eventlog:event-d", True),
        ("payload:payload-a", True),
        ("artifact:artifact-a", True),
        ("digest:sha256-a", True),
        ("filing:msft-10k", False),
    ),
)
def test_internal_evidence_source_part_detection(
    source_part: str, expected: bool
) -> None:
    """内部 evidence source part 检测只匹配治理 provenance 前缀。"""

    assert _is_internal_evidence_source_part(source_part) is expected


def test_compact_artifact_reader_uses_vnext_evidence_mapping_refs() -> None:
    """compact artifact reader 只读取 vNext accepted evidence mapping refs。"""

    payload: dict[str, JsonValue] = {
        "accepted_candidate": {
            "schema_version": "conversation_compact_output_v1",
            "session_summary": {
                "summary_text": "用户关注收入与毛利率。",
                "source_labels": ["T1"],
            },
            "evidence_backed_facts": [
                {"claim_text": "收入增长", "evidence_labels": ["E1"]}
            ],
            "answer_anchors": [
                {
                    "anchor_title": "收入质量",
                    "anchor_items": [
                        {"display_text": "关注经常性收入", "ordinal": 1}
                    ],
                }
            ],
            "forward_intents": [
                {
                    "intent_type": "follow_up",
                    "status": "open",
                    "text": "继续核对毛利率。",
                }
            ],
            "reference_continuity_items": [
                {
                    "reason": "followup_reference",
                    "text": "这个因素指收入增长。",
                    "source_labels": ["T1"],
                }
            ],
            "diagnostics": [],
        },
        "accepted_evidence_mapping_refs": ["evidence:memory-tool"],
    }

    lines = _vnext_compact_candidate_semantic_lines(payload)
    content = _compact_artifact_message_content(
        compacted_event=_event_log_row("event-compact"),
        payload=payload,
    )

    assert _accepted_evidence_mapping_refs(payload) == ("evidence:memory-tool",)
    assert lines == (
        "session_summary=用户关注收入与毛利率。",
        "fact 1: claim_text=收入增长; evidence_labels=E1",
        "answer_anchor 1: title=收入质量; items=1. 关注经常性收入",
        "forward_intent 1: type=follow_up; status=open; text=继续核对毛利率。",
        "reference_continuity 1: text=这个因素指收入增长。; "
        "reason=followup_reference; source_labels=T1",
    )
    assert all("evidence_backed_facts=" not in line for line in lines)
    assert all("answer_anchors=" not in line for line in lines)
    assert content is not None
    assert "Accepted compacted conversation view:" in content
    assert "fact 1: claim_text=收入增长" in content
    assert "evidence_backed_facts=1" not in content
    assert "answer_anchors=1" not in content


@pytest.mark.parametrize(
    ("field_path", "bad_value"),
    (
        ("fact.evidence_kind", 123),
        ("reference.reason", ""),
    ),
)
def test_compact_artifact_semantic_renderer_rejects_invalid_optional_text(
    field_path: str,
    bad_value: JsonValue,
) -> None:
    """accepted compact 新 semantic renderer 对坏可选文本字段 fail closed。"""

    payload: dict[str, JsonValue] = {
        "accepted_candidate": {
            "schema_version": "conversation_compact_output_v1",
            "session_summary": None,
            "evidence_backed_facts": [
                {"claim_text": "收入增长", "evidence_labels": ["E1"]}
            ],
            "answer_anchors": [],
            "forward_intents": [],
            "reference_continuity_items": [
                {"reason": "followup_reference", "text": "这个因素指收入增长。"}
            ],
            "diagnostics": [],
        },
        "accepted_evidence_mapping_refs": ["evidence:memory-tool"],
    }
    candidate = payload["accepted_candidate"]
    assert isinstance(candidate, dict)
    if field_path == "fact.evidence_kind":
        facts = candidate["evidence_backed_facts"]
        assert isinstance(facts, list)
        fact = facts[0]
        assert isinstance(fact, dict)
        fact["evidence_kind"] = bad_value
    else:
        references = candidate["reference_continuity_items"]
        assert isinstance(references, list)
        reference = references[0]
        assert isinstance(reference, dict)
        reference["reason"] = bad_value

    with pytest.raises(HostDurableError, match="must be text"):
        _vnext_compact_candidate_semantic_lines(payload)


def test_reference_continuity_resolves_second_factor_without_full_long_input(
    tmp_path: Path,
) -> None:
    """长输入 compact 后只靠 reference continuity 解析“第二个因素”。"""

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
        compact_event = _append_reference_continuity_compact_marker(
            store.transaction_runner,
            session_id=session_id,
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("第二个因素具体影响是什么？"),
        )
        cursor = _required_memory_cursor(store.transaction_runner, seeded)
        snapshot = _reference_continuity_only_snapshot(
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
        system_content = _single_system_content(request.messages)

        assert "## Reference Continuity" in system_content
        assert f"text={preserve_text}" in system_content
        assert "reason=needed_for_ordered_item_reference" in system_content
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
    selected_recent_window_char_cap: int = 4096,
    fallback_selected_recent_window_item_cap: int = 4,
    fallback_selected_recent_window_char_cap: int = 1024,
    evidence_fact_char_cap: int = 2048,
) -> MemoryProjectionPolicy:
    """构造 RunInputBuilder memory provider 测试 policy。

    :param max_lag_events_for_inline_delta: inline repair 最大滞后事件数。
    :param selected_recent_window_char_cap: selected recent window 字符上限。
    :param fallback_selected_recent_window_item_cap: fallback recent window item 上限。
    :param fallback_selected_recent_window_char_cap: fallback recent window 字符上限。
    :param evidence_fact_char_cap: evidence fact 字符上限。
    :returns: memory projection policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        selected_recent_window_item_cap=8,
        selected_recent_window_char_cap=selected_recent_window_char_cap,
        selected_recent_window_turn_floor=2,
        fallback_selected_recent_window_item_cap=fallback_selected_recent_window_item_cap,
        fallback_selected_recent_window_char_cap=fallback_selected_recent_window_char_cap,
        evidence_fact_item_cap=16,
        evidence_fact_char_cap=evidence_fact_char_cap,
        evidence_fact_floor=1,
        session_summary_char_cap=1024,
        answer_anchor_item_cap=8,
        answer_anchor_char_cap=2048,
        forward_intent_item_cap=8,
        forward_intent_char_cap=2048,
        reference_continuity_item_cap=8,
        reference_continuity_char_cap=2048,
        reference_continuity_item_floor=0,
        max_lag_events_for_inline_delta=max_lag_events_for_inline_delta,
        max_delta_repair_events=16,
        policy_ref="run-input-builder-test",
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
        memory_projection_policy=policy,
        memory_snapshot_provider=provider,
    )
    return builder.build(_attempt_snapshot(seeded))


def _build_post_compaction_request(
    store: HostDurableStore,
    seeded: _SeededRun,
    policy: MemoryProjectionPolicy,
) -> AgentRunRequest:
    """通过 durable compact provider 构造 post-compaction AgentRunRequest。

    :param store: Host durable store。
    :param seeded: post-compaction Attempt 引用。
    :param policy: memory projection policy。
    :returns: AgentRunRequest。
    """

    builder = create_no_tool_run_input_builder(
        transaction_runner=store.transaction_runner,
        policy_snapshot=_policy_snapshot(),
        memory_projection_policy=policy,
        compact_artifact_provider=DurableCompactArtifactProvider(
            store.transaction_runner
        ),
    )
    return builder.build(_attempt_snapshot(seeded))


def _four_item_answer() -> str:
    """构造 ordinal follow-up 回归测试的四条回答。

    :returns: 四条编号回答文本。
    """

    return "\n".join(
        (
            "1. 第一条是收入确认节奏，需要核对合同负债。",
            "2. 第二条是毛利率波动，需要拆解产品结构。",
            "3. 第三条是客户集中度升高，需要拆解前五大客户变化。",
            "4. 第四条是现金流转弱，需要核对回款周期。",
        )
    )


def _append_current_run_compacted_event(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> None:
    """为当前 Run 追加 accepted CONTEXT_COMPACTED fact。

    :param transaction_runner: Host transaction runner。
    :param seeded: 当前 Run 引用。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加 compacted event。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        request_event_id = f"event-{seeded.run_id}-compact-requested"
        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id=request_event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                event_type="CONTEXT_COMPACTION_REQUESTED",
                payload={
                    "trigger_source": ContextCompactionTriggerSource.PROACTIVE.value,
                    "budget_reason": "test_post_compaction_raw_tail",
                    "budget_snapshot_ref": _DIGEST_A,
                    "input_snapshot_cursor": 1,
                    "estimator_digest": _DIGEST_A,
                    "policy_ref": "test-policy",
                    "provider_request_id": None,
                    "provider_error_ref": None,
                    "attempt_id": seeded.attempt_id,
                    "execution_id": seeded.execution_id,
                },
            ),
        )
        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id=f"event-{seeded.run_id}-compacted",
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    operation_id=request_event_id,
                    summary_text="current run compacted semantic view",
                    pinned_patch={"candidate_id": "patch-current-run"},
                    fact_candidates=[],
                ),
            ),
        )

    transaction_runner.run_write(operation)


def _material_block(
    block_id: str,
    section: CompactMaterialSection,
    kind: CompactMaterialBlockKind,
    text: str,
    *,
    event_sequence: int | None,
    source_ref: str | None = None,
    turn_group_id: str | None = None,
) -> RunInputMaterialBlock:
    """构造测试用 material block。

    :param block_id: block id。
    :param section: material section。
    :param kind: material kind。
    :param text: block 文本。
    :param event_sequence: event sequence。
    :param source_ref: canonical source ref；不传时使用 block id。
    :param turn_group_id: Host Run turn group id。
    :returns: RunInputMaterialBlock。
    """

    if kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE:
        return run_input_material_block(
            block_id=block_id,
            section=section,
            kind=kind,
            text=text,
            canonical_source_refs=(block_id if source_ref is None else source_ref,),
            event_sequence=event_sequence,
            turn_group_id=turn_group_id,
            accepted_evidence_id=f"evidence:{block_id}",
            tool_result_event_ref=f"tool-result:{block_id}",
            tool_call_event_ref=f"tool-call:{block_id}",
            readable_tool_name="read_tool",
            readable_query_text="query",
            readable_source_text="source",
        )
    return run_input_material_block(
        block_id=block_id,
        section=section,
        kind=kind,
        text=text,
        canonical_source_refs=(block_id if source_ref is None else source_ref,),
        event_sequence=event_sequence,
        turn_group_id=turn_group_id,
    )


def _active_fallback(
    *,
    selected_blocks: tuple[RunInputMaterialBlock, ...],
    current_input_ref: str,
    dropped_block_ids: tuple[str, ...] = (),
    selected_recent_window_turn_floor: int = 0,
    selected_block_ids: tuple[str, ...] | None = None,
    source_refs: tuple[str, ...] | None = None,
    fallback_input_digest: str | None = None,
    selected_material_view_digest: str | None = None,
    selected_raw_turn_count: int | None = None,
) -> ActiveRecentWindowFallback:
    """从 selected material blocks 构造 active fallback fixture。

    :param selected_blocks: 已选 material blocks。
    :param current_input_ref: current input ref。
    :param dropped_block_ids: dropped block ids。
    :param selected_recent_window_turn_floor: selected recent turn floor。
    :param selected_block_ids: 可选覆盖 selected ids。
    :param source_refs: 可选覆盖 source refs。
    :param fallback_input_digest: 可选覆盖 fallback input digest。
    :param selected_material_view_digest: 可选覆盖 selected material digest。
    :param selected_raw_turn_count: 可选覆盖 selected raw turn count。
    :returns: ActiveRecentWindowFallback。
    """

    actual_selected_ids = (
        tuple(block.block_id for block in selected_blocks)
        if selected_block_ids is None
        else selected_block_ids
    )
    actual_source_refs = (
        _source_refs_from_blocks(selected_blocks) if source_refs is None else source_refs
    )
    actual_view_digest = (
        selected_material_view_digest
        if selected_material_view_digest is not None
        else selected_material_view_digest_from_blocks(selected_blocks)
    )
    actual_selected_raw_turn_count = (
        sum(
            1
            for block in selected_blocks
            if block.kind
            in (
                CompactMaterialBlockKind.USER_INPUT,
                CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
                CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
            )
        )
        if selected_raw_turn_count is None
        else selected_raw_turn_count
    )
    window: dict[str, JsonValue] = {
        "selected_block_ids": list(actual_selected_ids),
        "dropped_block_ids": list(dropped_block_ids),
        "current_input_ref": current_input_ref,
        "source_refs": list(actual_source_refs),
        "selected_recent_window_turn_floor": selected_recent_window_turn_floor,
        "trigger_source": ContextCompactionTriggerSource.PROACTIVE.value,
        "policy_ref": "test-fallback-policy",
        "input_cursor": 1,
        "selected_raw_turn_count": actual_selected_raw_turn_count,
        "selected_material_view_digest": actual_view_digest,
    }
    return ActiveRecentWindowFallback(
        selected_block_ids=actual_selected_ids,
        current_input_ref=current_input_ref,
        source_refs=actual_source_refs,
        fallback_input_digest=(
            fallback_window_digest(window)
            if fallback_input_digest is None
            else fallback_input_digest
        ),
        selected_recent_window_turn_floor=selected_recent_window_turn_floor,
        selected_raw_turn_count=actual_selected_raw_turn_count,
        selected_material_view_digest=actual_view_digest,
        fallback_input_window=window,
    )


def _append_context_fallback_failed_event(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    case_name: str,
) -> None:
    """追加 provider fail-closed 测试用 CONTEXT_COMPACTION_FAILED event。

    :param transaction_runner: transaction runner。
    :param session_id: Session id。
    :param case_name: payload 损坏 case。
    :returns: ``None``。
    """

    payload = _context_fallback_failed_payload(case_name)

    def operation(transaction: HostTransaction) -> None:
        """追加 fallback failed event。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id=f"event-context-fallback-{case_name}",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-current",
                event_type="CONTEXT_COMPACTION_FAILED",
                payload=payload,
            ),
        )

    transaction_runner.run_write(operation)


def _context_fallback_failed_payload(case_name: str) -> dict[str, JsonValue]:
    """构造 provider fail-closed 测试用 fallback failed payload。

    :param case_name: payload 损坏 case。
    :returns: CONTEXT_COMPACTION_FAILED payload。
    """

    window: dict[str, JsonValue] = {
        "selected_block_ids": ["current:event-current-input"],
        "dropped_block_ids": [],
        "current_input_ref": "event-current-input",
        "source_refs": ["event-current-input"],
        "selected_recent_window_turn_floor": 0,
        "trigger_source": ContextCompactionTriggerSource.PROACTIVE.value,
        "policy_ref": "test-fallback-policy",
        "input_cursor": 1,
        "selected_raw_turn_count": 0,
        "selected_material_view_digest": _DIGEST_A,
    }
    if case_name == "missing_current_ref":
        del window["current_input_ref"]
    elif case_name == "current_ref_mismatch":
        window["current_input_ref"] = "event-other-input"
    elif case_name == "missing_material_digest":
        del window["selected_material_view_digest"]
    elif case_name == "blank_material_digest":
        window["selected_material_view_digest"] = ""
    elif case_name == "missing_raw_turn_count":
        del window["selected_raw_turn_count"]
    elif case_name == "negative_raw_turn_count":
        window["selected_raw_turn_count"] = -1
    elif case_name == "missing_turn_floor":
        del window["selected_recent_window_turn_floor"]
    elif case_name == "bad_turn_floor_type":
        window["selected_recent_window_turn_floor"] = "zero"
    payload: dict[str, JsonValue] = {
        "fallback_action": "dispatch",
        "fallback_input_window": window,
        "fallback_input_digest": fallback_window_digest(window),
    }
    if case_name == "missing_window":
        del payload["fallback_input_window"]
    elif case_name == "digest_mismatch":
        payload["fallback_input_digest"] = _DIGEST_B
    return payload


def selected_material_view_digest_from_blocks(
    selected_blocks: tuple[RunInputMaterialBlock, ...],
) -> str:
    """返回 selected material view digest。

    :param selected_blocks: selected material blocks。
    :returns: digest。
    """

    return selected_material_view_digest(selected_blocks)


def _source_refs_from_blocks(
    blocks: tuple[RunInputMaterialBlock, ...],
) -> tuple[str, ...]:
    """收集测试 material blocks 的 canonical source refs。

    :param blocks: material blocks。
    :returns: 去重 source refs。
    """

    refs: list[str] = []
    for block in blocks:
        refs.extend(block.canonical_source_refs)
    return tuple(dict.fromkeys(refs))


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
) -> ConversationMemorySnapshotVNext:
    """构造覆盖 vNext memory message 分组的 snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :returns: memory snapshot。
    """

    policy_digest = digest_memory_projection_policy(policy)
    snapshot_without_digest = ConversationMemorySnapshotVNext(
        schema_version="conversation_memory_snapshot_v1",
        snapshot_id=f"memory-snapshot-test-{session_id}",
        session_id=session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        latest_compaction_event_ref="event-memory-episode",
        trace_memory=TraceMemoryView(
            selected_recent_window=(
                SelectedRecentWindowItem(
                    item_id="memory-item:selected-user:test",
                    role=SelectedRecentWindowRole.USER,
                    text="recent raw user",
                    event_id="event-memory-raw-user",
                    event_sequence=3,
                    run_id="run-memory",
                    source_refs=("event-memory-raw-user",),
                    included_reason=MemoryIncludedReason.SELECTED_RECENT_WINDOW,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(15),
                ),
                SelectedRecentWindowItem(
                    item_id="memory-item:selected-assistant:test",
                    role=SelectedRecentWindowRole.ASSISTANT,
                    text="recent assistant conclusion",
                    event_id="event-memory-assistant",
                    event_sequence=4,
                    run_id="run-memory",
                    source_refs=("event-memory-assistant",),
                    included_reason=MemoryIncludedReason.SELECTED_RECENT_WINDOW,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(27),
                ),
            ),
            reference_continuity_items=(
                ReferenceContinuityItem(
                    item_id="memory-item:reference-continuity:test",
                    text="second factor: margin mix",
                    reason="needed_for_ordered_item_reference",
                    source_refs=("event-memory-raw-user",),
                    event_id="event-memory-episode",
                    event_sequence=5,
                    size_units=MemorySizeUnits(25),
                ),
            ),
        ),
        evidence_fact_memory=EvidenceFactMemoryView(
            evidence_backed_facts=(_memory_fact_view(),),
            recent_evidence_items=(),
        ),
        session_summary_memory=SessionSummaryMemoryView(
            summary_text="compare revenue quality; use reported currency",
            source_refs=("event-memory-episode",),
            event_id="event-memory-episode",
            event_sequence=5,
            size_units=MemorySizeUnits(46),
        ),
        answer_anchor_memory=AnswerAnchorMemoryView(
            anchors=(
                AnswerAnchor(
                    item_id="memory-item:answer-anchor:test",
                    anchor_title="Revenue quality",
                    anchor_items=(
                        AnswerAnchorChild(
                            display_text="Use reported currency.",
                            ordinal=1,
                        ),
                    ),
                    source_refs=("event-memory-episode",),
                    event_id="event-memory-episode",
                    event_sequence=5,
                    size_units=MemorySizeUnits(42),
                ),
            ),
        ),
        forward_intent_memory=ForwardIntentMemoryView(
            intents=(
                ForwardIntent(
                    item_id="memory-item:forward-intent:test",
                    intent_type="follow_up",
                    text="what changed in margin?",
                    status="open",
                    source_refs=("event-memory-episode",),
                    event_id="event-memory-episode",
                    event_sequence=5,
                    size_units=MemorySizeUnits(23),
                ),
            ),
        ),
        diagnostics=(),
        built_at="2026-05-15T01:02:03.000000Z",
        snapshot_digest="pending",
    )
    return replace(
        snapshot_without_digest,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def _memory_fact_view() -> EvidenceBackedFactView:
    """构造测试用 evidence-backed fact。

    :returns: evidence-backed fact view。
    """

    return EvidenceBackedFactView(
        item_id="memory-item:evidence-backed:test",
        claim_text="Revenue increased year over year",
        evidence_kind=MemoryEvidenceBackedFactKind.DERIVED_FROM_EVIDENCE,
        evidence_refs=("evidence:memory-tool",),
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
    )


def _stable_budget_pressure_snapshot(
    session_id: str,
    policy: MemoryProjectionPolicy,
    cursor: MemorySnapshotCursor,
) -> ConversationMemorySnapshotVNext:
    """构造 vNext fact pressure snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :returns: memory snapshot。
    """

    return _rich_memory_snapshot(session_id, policy, cursor)


def _current_input_memory_snapshot(
    *,
    session_id: str,
    policy: MemoryProjectionPolicy,
    cursor: MemorySnapshotCursor,
    current_input: EventLogRow,
    current_prompt: str,
) -> ConversationMemorySnapshotVNext:
    """构造包含当前用户输入的测试 memory snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :param current_input: 当前 USER_INPUT_ACCEPTED event。
    :param current_prompt: 当前 prompt 文本。
    :returns: memory snapshot。
    """

    policy_digest = digest_memory_projection_policy(policy)
    snapshot_without_digest = ConversationMemorySnapshotVNext(
        schema_version="conversation_memory_snapshot_v1",
        snapshot_id=f"memory-snapshot-current-{session_id}",
        session_id=session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        latest_compaction_event_ref=None,
        trace_memory=TraceMemoryView(
            selected_recent_window=(
                SelectedRecentWindowItem(
                    item_id="memory-item:selected-current",
                    role=SelectedRecentWindowRole.USER,
                    text=current_prompt,
                    event_id=current_input.event_id,
                    event_sequence=current_input.event_sequence,
                    run_id=current_input.run_id,
                    source_refs=(current_input.event_id,),
                    included_reason=MemoryIncludedReason.SELECTED_RECENT_WINDOW,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(len(current_prompt)),
                ),
            ),
            reference_continuity_items=(),
        ),
        evidence_fact_memory=EvidenceFactMemoryView(
            evidence_backed_facts=(),
            recent_evidence_items=(),
        ),
        session_summary_memory=SessionSummaryMemoryView(
            summary_text=None,
            source_refs=(),
            event_id=None,
            event_sequence=None,
            size_units=MemorySizeUnits(0),
        ),
        answer_anchor_memory=AnswerAnchorMemoryView(anchors=()),
        forward_intent_memory=ForwardIntentMemoryView(intents=()),
        diagnostics=(),
        built_at="2026-05-15T01:02:03.000000Z",
        snapshot_digest="pending",
    )
    return replace(
        snapshot_without_digest,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def _reference_continuity_only_snapshot(
    *,
    session_id: str,
    policy: MemoryProjectionPolicy,
    cursor: MemorySnapshotCursor,
    source_event: EventLogRow,
    producer_event: EventLogRow,
    preserve_text: str,
) -> ConversationMemorySnapshotVNext:
    """构造只保留 reference continuity item 的 memory snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :param source_event: compact 前长输入 source event。
    :param producer_event: 生成 reference continuity item 的 compact event。
    :param preserve_text: reference continuity item 文本。
    :returns: memory snapshot。
    """

    policy_digest = digest_memory_projection_policy(policy)
    snapshot_without_digest = ConversationMemorySnapshotVNext(
        schema_version="conversation_memory_snapshot_v1",
        snapshot_id=f"memory-snapshot-reference-continuity-{session_id}",
        session_id=session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        latest_compaction_event_ref=producer_event.event_id,
        trace_memory=TraceMemoryView(
            selected_recent_window=(),
            reference_continuity_items=(
                ReferenceContinuityItem(
                    item_id="memory-item:reference-continuity:second-factor",
                    text=preserve_text,
                    reason="needed_for_ordered_item_reference",
                    source_refs=(source_event.event_id,),
                    event_id=producer_event.event_id,
                    event_sequence=producer_event.event_sequence,
                    size_units=MemorySizeUnits(len(preserve_text)),
                ),
            ),
        ),
        evidence_fact_memory=EvidenceFactMemoryView(
            evidence_backed_facts=(),
            recent_evidence_items=(),
        ),
        session_summary_memory=SessionSummaryMemoryView(
            summary_text=None,
            source_refs=(),
            event_id=None,
            event_sequence=None,
            size_units=MemorySizeUnits(0),
        ),
        answer_anchor_memory=AnswerAnchorMemoryView(anchors=()),
        forward_intent_memory=ForwardIntentMemoryView(intents=()),
        diagnostics=(),
        built_at="2026-05-15T01:02:03.000000Z",
        snapshot_digest="pending",
    )
    return replace(
        snapshot_without_digest,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def _write_memory_snapshot(
    transaction_runner: HostTransactionRunner,
    snapshot: ConversationMemorySnapshotVNext,
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


def _accepted_tool_evidence_blocks(
    blocks: tuple[RunInputMaterialBlock, ...],
) -> tuple[RunInputMaterialBlock, ...]:
    """筛选 accepted tool evidence material blocks。

    :param blocks: RunInputBuilder 输出的 material blocks。
    :returns: accepted tool evidence blocks。
    """

    return tuple(
        block
        for block in blocks
        if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE
    )


def _append_prior_accepted_tool_evidence_batch(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    count: int,
    run_id: str | None = None,
    raw_outcome: JsonValue | None = None,
    semantic_query_text: str | None = None,
) -> tuple[_SeededAcceptedEvidence, ...]:
    """追加当前输入之前的 accepted tool evidence 事件。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param count: 追加的 evidence 数量。
    :param run_id: 可选绑定 evidence 的 Host Run id；缺省按 ordinal 生成。
    :param raw_outcome: 可选覆盖 raw outcome；缺省时按 ordinal 生成。
    :param semantic_query_text: 可选覆盖 semantic query；缺省时按 ordinal 生成。
    :returns: 写入的 evidence 元数据。
    :raises ValueError: count 非正数时抛出。
    """

    if count <= 0:
        raise ValueError("count must be positive")

    def operation(transaction: HostTransaction) -> tuple[_SeededAcceptedEvidence, ...]:
        """在一个 transaction 内追加 prior evidence 事件。

        :param transaction: Host transaction。
        :returns: 写入的 evidence 元数据。
        """

        seeded: list[_SeededAcceptedEvidence] = []
        for ordinal in range(count):
            seeded.append(
                _append_prior_accepted_tool_evidence_tx(
                    transaction,
                    session_id=session_id,
                    ordinal=ordinal,
                    run_id=run_id,
                    raw_outcome=raw_outcome,
                    semantic_query_text=semantic_query_text,
                )
            )
        return tuple(seeded)

    return transaction_runner.run_write(operation)


def _append_prior_accepted_tool_evidence_tx(
    transaction: HostTransaction,
    *,
    session_id: str,
    ordinal: int,
    run_id: str | None,
    raw_outcome: JsonValue | None,
    semantic_query_text: str | None,
) -> _SeededAcceptedEvidence:
    """追加一组 prior TOOL_CALL_REQUESTED / TOOL_RESULT_ACCEPTED 事件。

    :param transaction: Host transaction。
    :param session_id: Session id。
    :param ordinal: 批内序号。
    :param run_id: 可选绑定 evidence 的 Host Run id。
    :param raw_outcome: 可选 raw outcome。
    :param semantic_query_text: 可选 semantic query。
    :returns: 写入的 evidence 元数据。
    """

    tool_call_event_id = f"event-prior-tool-call-{ordinal:02d}"
    tool_result_event_id = f"event-prior-tool-result-{ordinal:02d}"
    tool_call_id = f"tool-call-prior-{ordinal:02d}"
    target_run_id = f"run-prior-evidence-{ordinal:02d}" if run_id is None else run_id
    query_text = (
        f"Read MSFT FY2025 revenue detail {ordinal}"
        if semantic_query_text is None
        else semantic_query_text
    )
    actual_raw_outcome = (
        {
            "kind": "completed",
            "result": {
                "text": f"full raw outcome {ordinal}",
                "ordinal": ordinal,
            },
        }
        if raw_outcome is None
        else raw_outcome
    )
    arguments: dict[str, JsonValue] = {
        "ticker": "MSFT",
        "ordinal": ordinal,
    }
    arguments_json: dict[str, JsonValue] = {"arguments": arguments}
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_query_digest = sha256_digest_json(
        {"semantic_query_text": query_text}
    )
    EventLogStore().append_event(
        transaction,
        _event_request(
            event_id=tool_call_event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=session_id,
            run_id=target_run_id,
            event_type="TOOL_CALL_REQUESTED",
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": "fins.search",
                "normalized_arguments_digest": arguments_digest,
                "arguments_payload_digest": arguments_digest,
                "arguments_storage_kind": TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
                "arguments_inline_json": arguments_json,
                "arguments_payload_ref": None,
                "arguments_json_size_bytes": len(
                    canonical_json_dumps(arguments_json).encode("utf-8")
                ),
                "semantic_input_digest": semantic_query_digest,
                "semantic_query_storage_kind": (
                    TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT
                ),
                "semantic_query_text": query_text,
                "semantic_query_payload_ref": None,
                "semantic_query_digest": semantic_query_digest,
            },
        ),
    )
    evidence_id = f"evidence:{tool_result_event_id}"
    envelope = AcceptedEvidenceEnvelope(
        evidence_id=evidence_id,
        producer_event_ref=tool_result_event_id,
        tool_name="fins.search",
        tool_call_id=tool_call_id,
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=tool_call_event_id,
            normalized_arguments_digest=arguments_digest,
            semantic_input_digest=semantic_query_digest,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=None,
            payload_digest=None,
            outcome_digest=_DIGEST_A,
            truncation_applied=False,
        ),
        source_refs=(
            OpaqueEvidenceRef(
                ref_kind="tool_call_event",
                ref_id=tool_call_event_id,
                digest=None,
            ),
        ),
        locator_refs=(
            OpaqueEvidenceRef(
                ref_kind="filing",
                ref_id=f"msft-fy2025-{ordinal:02d}",
                digest=None,
            ),
        ),
    )
    EventLogStore().append_event(
        transaction,
        _event_request(
            event_id=tool_result_event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=session_id,
            run_id=target_run_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "accepted_evidence_envelope": (
                    accepted_evidence_envelope_to_json_value(envelope)
                ),
                "raw_tool_outcome": actual_raw_outcome,
            },
        ),
    )
    return _SeededAcceptedEvidence(
        tool_call_event_id=tool_call_event_id,
        tool_result_event_id=tool_result_event_id,
        accepted_evidence_id=evidence_id,
        semantic_query_text=query_text,
        raw_outcome=actual_raw_outcome,
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


def _append_reference_continuity_compact_marker(
    transaction_runner: HostTransactionRunner, *, session_id: str
) -> EventLogRow:
    """追加 reference continuity snapshot 的 compact producer event。

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
                    summary_text="long input compacted to reference continuity",
                    pinned_patch={"candidate_id": "patch-second-factor"},
                    fact_candidates=[],
                    reference_continuity_items=[
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


def _events_by_type(
    transaction_runner: HostTransactionRunner, *, event_type: str
) -> tuple[EventLogRow, ...]:
    """读取指定 event type 的 EventLog rows。

    :param transaction_runner: Host transaction runner。
    :param event_type: event type。
    :returns: 按 event_sequence 排序的 EventLog rows。
    """

    def operation(transaction: HostTransaction) -> tuple[EventLogRow, ...]:
        """读取指定事件类型。

        :param transaction: Host transaction。
        :returns: EventLog rows。
        """

        rows = transaction.fetchall(
            f"""
            SELECT event_id
            FROM {TABLE_EVENT_LOG}
            WHERE event_type = ?
            ORDER BY event_sequence
            """,
            (event_type,),
        )
        events: list[EventLogRow] = []
        store = EventLogStore()
        for row in rows:
            event_id = row.get("event_id")
            assert isinstance(event_id, str)
            event = store.read_event_by_id(transaction, event_id)
            assert event is not None
            events.append(event)
        return tuple(events)

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


def _append_inline_repair_filter_noise(
    transaction_runner: HostTransactionRunner,
    session_id: str,
) -> None:
    """追加 inline repair 过滤语义测试所需的 matching 与 non-matching rows。

    :param transaction_runner: Host transaction runner。
    :param session_id: 当前 Session id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加一组跨 class、type 与 session 的 EventLog rows。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        store = EventLogStore()
        store.append_event(
            transaction,
            _event_request(
                event_id="event-inline-preview-noise",
                event_class=EventClass.PREVIEW,
                session_id=session_id,
                run_id="run-inline-preview",
                event_type="USER_INPUT_ACCEPTED",
                payload=_user_input_payload("preview should not enter memory"),
            ),
        )
        store.append_event(
            transaction,
            _event_request(
                event_id="event-inline-diagnostic-noise",
                event_class=EventClass.DIAGNOSTIC,
                session_id=session_id,
                run_id="run-inline-diagnostic",
                event_type="TOOL_RESULT_ACCEPTED",
                payload={"message": "diagnostic should not enter memory"},
            ),
        )
        store.append_event(
            transaction,
            _event_request(
                event_id="event-inline-canonical-noise",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-inline-noise",
                event_type="RUN_ACCEPTED",
                payload={"message": "canonical unrelated should not enter memory"},
            ),
        )
        store.append_event(
            transaction,
            _event_request(
                event_id="event-inline-foreign-memory",
                event_class=EventClass.CANONICAL_FACT,
                session_id="session-inline-foreign",
                run_id="run-inline-foreign",
                event_type="USER_INPUT_ACCEPTED",
                payload=_user_input_payload("foreign session should not enter memory"),
            ),
        )
        store.append_event(
            transaction,
            _event_request(
                event_id="event-inline-matching-success",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-inline-matching",
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "matching assistant answer"},
            ),
        )

    transaction_runner.run_write(operation)


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


def _append_resume_wait_projection_events(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> None:
    """追加 resume wait message 投影所需的最小事件。

    :param transaction_runner: Host transaction runner。
    :param seeded: 当前测试 Run 引用。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加 wait result 与 resume ``RUN_STARTED`` 事件。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        event_log = EventLogStore()
        tool_result = event_log.append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-tool-result-resume",
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                event_type="TOOL_RESULT_ACCEPTED",
                occurred_at=_NOW,
                actor="host",
                source="pytest",
                client_request_id=None,
                idempotency_key="resolve-resume",
                policy_decision=None,
                reason=None,
                payload_json={
                    "wait_id": "wait-resume-private",
                    "tool_call_id": "tool-call-private",
                    "tool_name": "fake_tool",
                    "resolution_kind": "completed",
                    "tool_fact_kind": "completed",
                    "result": {"ok": True, "value": {"answer": 42}},
                    "payload_ref": "payload-ref-private",
                    "result_digest": _DIGEST_A,
                },
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
        event_log.append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-run-started-resume",
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=None,
                execution_id=None,
                event_type="RUN_STARTED",
                occurred_at=_NOW,
                actor="host",
                source="pytest",
                client_request_id=None,
                idempotency_key="resolve-resume",
                policy_decision=None,
                reason={"start_reason": "resume"},
                payload_json={
                    "run_id": seeded.run_id,
                    "start_reason": "resume",
                    "wait_id": "wait-resume-private",
                    "source_attempt_id": seeded.attempt_id,
                    "attempt_id": "attempt-resume-private",
                    "execution_id": "execution-resume-private",
                    "tool_result_event_ref": {
                        "event_id": tool_result.event_id,
                        "event_sequence": tool_result.event_sequence,
                    },
                },
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(operation)


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


def _event_log_row(event_id: str) -> EventLogRow:
    """构造测试用 EventLogRow。

    :param event_id: event id。
    :returns: EventLogRow。
    """

    return EventLogRow(
        event_sequence=1,
        event_id=event_id,
        event_body_digest=_DIGEST_A,
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-test",
        run_id="run-test",
        attempt_id=None,
        execution_id=None,
        event_type="CONTEXT_COMPACTED",
        occurred_at="2026-05-15T01:02:03.000000Z",
        actor="test",
        source="test",
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json="{}",
        payload_ref=None,
        payload_digest=None,
        appended_at="2026-05-15T01:02:03.000000Z",
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
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
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
        execution=AsyncDirectToolExecutionCapability(),
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
    operation_id: str = "event-compact-requested",
    summary_text: str,
    pinned_patch: dict[str, JsonValue],
    fact_candidates: list[JsonValue] | None = None,
    reference_continuity_items: list[JsonValue] | None = None,
) -> dict[str, JsonValue]:
    """构造测试用 CONTEXT_COMPACTED payload。

    :param operation_id: 对应 CONTEXT_COMPACTION_REQUESTED event id。
    :param summary_text: session summary 文本。
    :param pinned_patch: pinned patch candidate。
    :param fact_candidates: 可选 evidence-backed fact candidates。
    :param reference_continuity_items: 可选 reference continuity candidates。
    :returns: compacted payload。
    """

    resolved_fact_candidates: list[JsonValue]
    if fact_candidates is None:
        resolved_fact_candidates = [
            {
                "claim_text": "Revenue increased year over year",
                "evidence_labels": ["evidence:memory-tool"],
            }
        ]
    else:
        resolved_fact_candidates = [
            {
                "claim_text": str(candidate["claim_text"]),
                "evidence_labels": ["evidence:memory-tool"],
            }
            for candidate in fact_candidates
            if isinstance(candidate, dict) and "claim_text" in candidate
        ]
    resolved_reference_continuity_items: list[JsonValue]
    if reference_continuity_items is None:
        resolved_reference_continuity_items = [
            {
                "text": "second factor: margin mix",
                "reason": "needed_for_ordered_item_reference",
                "source_labels": ["event-memory-raw-user"],
            }
        ]
    else:
        resolved_reference_continuity_items = [
            {
                "text": str(candidate["text"]),
                "reason": "needed_for_ordered_item_reference",
                "source_labels": ["event-long-input"],
            }
            for candidate in reference_continuity_items
            if isinstance(candidate, dict) and "text" in candidate
        ]
    anchor_text = "compact pinned goal"
    if isinstance(pinned_patch.get("current_goal"), dict):
        current_goal = pinned_patch["current_goal"]
        if isinstance(current_goal, dict) and isinstance(current_goal.get("value"), str):
            anchor_text = current_goal["value"]
    forward_text = "compact open question"
    if isinstance(pinned_patch.get("open_questions"), dict):
        open_questions = pinned_patch["open_questions"]
        if isinstance(open_questions, dict):
            values = open_questions.get("value")
            if isinstance(values, list) and values and isinstance(values[0], str):
                forward_text = values[0]
    payload: dict[str, JsonValue] = {
        "operation_id": operation_id,
        "accepted_candidate": {
            "schema_version": "conversation_compact_output_v1",
            "session_summary": {
                "summary_text": summary_text,
                "source_labels": ["event-memory-raw-user"],
            },
            "evidence_backed_facts": resolved_fact_candidates,
            "answer_anchors": [
                {
                    "anchor_title": "Compacted answer anchor",
                    "anchor_items": [{"display_text": anchor_text, "ordinal": 1}],
                    "answer_source_labels": ["event-memory-episode"],
                }
            ],
            "forward_intents": [
                {
                    "intent_type": "open_question",
                    "text": forward_text,
                    "status": "open",
                    "source_labels": ["event-memory-episode"],
                }
            ],
            "reference_continuity_items": resolved_reference_continuity_items,
            "diagnostics": [],
        },
        "accepted_evidence_mapping_refs": ["evidence:memory-tool"],
        "compact_artifact_ref": "compact-artifact:test",
        "compact_artifact_digest": _DIGEST_A,
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
            "## Execution Guidance",
            "Use the available context and tools under the current run limits.",
            "Tools are disabled for this runner call.",
        )
    )


def _single_system_content(messages: tuple[AgentMessage, ...]) -> str:
    """读取唯一 system envelope 内容并校验 one-system-message contract。

    :param messages: RunInputBuilder 输出 messages。
    :returns: 唯一 system message content。
    :raises AssertionError: system message 数量或位置非法时抛出。
    """

    system_messages = tuple(
        message for message in messages if isinstance(message, SystemMessage)
    )
    assert len(system_messages) == 1
    assert messages[0] is system_messages[0]
    _assert_system_content_has_no_internal_refs(system_messages[0].content)
    return system_messages[0].content


def _assert_system_content_has_no_internal_refs(content: str) -> None:
    """断言 ordinary system envelope 不暴露内部治理标识。

    :param content: system envelope 内容。
    :returns: ``None``。
    :raises AssertionError: 命中内部治理标识时抛出。
    """

    for fragment in _SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS:
        assert fragment not in content


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
