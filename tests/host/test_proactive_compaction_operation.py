"""WU-CTX-04 proactive durable single-operation owner-boundary 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import runner_role_sequence_digest
from dayu.engine.contracts.messages import (
    AgentMessageRole,
    SystemMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host.compact_material import (
    InitialHistoryMaterial,
    build_initial_material_pack,
    conversation_compact_input_vnext_from_material_pack,
    initial_segment_selection,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactSegmentTrigger,
    CompactionRequest,
)
from dayu.host.compaction_operation import (
    CompactorProposalRunInput,
    DurableCompactorProposalManifestRecorder,
)
from dayu.host.context_events import (
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
    CompactorProposalManifestReference,
    build_context_compaction_attempt_rejected_payload,
    build_context_compaction_failed_payload,
    build_context_compaction_requested_payload,
)
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.context_budget import BudgetEstimate
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import (
    HostDurableStore,
    open_host_durable_store,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.proactive_compaction import (
    ProactiveCompactionAttemptStage,
    ProactiveCompactionDecision,
    ProactiveCompactionPhase,
    ProactiveCompactionProjection,
    ProactiveCompactionState,
    ProactiveCompactionTierRequest,
    build_proactive_compaction_attempt_schedule,
    read_proactive_compaction_projection,
    validate_proactive_compaction_attempt_schedule,
)
from dayu.host.run_input import NoToolExecutor
from tests.host.fake_cancellation import ControllableCancellationToken

_NOW = datetime(2026, 7, 22, 1, 2, 3, tzinfo=UTC)
_SESSION_ID = "session-proactive-owner"
_RUN_ID = "run-proactive-owner"
_DIGEST = sha256_digest_json({"fixture": "proactive-owner"})
_FIXTURE_PROVIDER = "test-proactive-compactor"
_FIXTURE_MODEL = "test-proactive-compactor-model"


def _successful_response_identity_for_agent_request(
    request: AgentRunRequest,
) -> SuccessfulRunnerResponseIdentity:
    """从同一个 proposal AgentRunRequest 构造 fixture 成功响应身份。

    :param request: manifest 与 identity 共用的 prepared Engine request。
    :returns: provider request id 明确不可用的 typed identity。
    :raises ValueError: request identity 字段非法时抛出。
    """

    return SuccessfulRunnerResponseIdentity(
        effective_provider=request.runner_spec.provider,
        effective_model=request.runner_spec.model,
        runner_request_identity=build_runner_request_identity(
            run_id=request.run_id,
            attempt_id=request.attempt_id,
            execution_id=request.execution_id,
            iteration_id=f"{request.run_id}:fixture-final",
            iteration_index=0,
            runner_call_index=1,
        ),
        provider_request_id_availability=(ProviderRequestIdAvailability.UNAVAILABLE),
        provider_request_id=None,
    )


def _schedule_request(label: str) -> CompactionRequest:
    """构造 schedule owner 测试使用的可区分 immutable request。

    :param label: request 与 material 的稳定区分标签。
    :returns: 可计算 digest 的 proactive compaction request。
    :raises Exception: production material/request 校验失败时透传。
    """

    current_input_ref = f"input-{label}"
    material_pack = build_initial_material_pack(
        current_input_ref=current_input_ref,
        current_input_text=f"current input {label}",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref=f"history-{label}",
                text=f"history material {label}",
                kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            ),
        ),
        evidence_materials=(),
    )
    return CompactionRequest(
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        attempt_id=None,
        execution_id=None,
        memory_snapshot_cursor=17,
        material_pack=material_pack,
        segment_selection=initial_segment_selection(
            trigger_source=CompactSegmentTrigger.PROACTIVE,
            input_cursor=17,
            material_pack=material_pack,
        ),
        evidence_backed_fact_refs=(),
        recent_raw_turn_refs=(current_input_ref,),
        older_raw_turn_refs=(f"history-{label}",),
        existing_episode_summary_refs=(),
        budget_before_compact=BudgetEstimate(
            estimated_input_tokens=100,
            input_budget_tokens=200,
            soft_threshold_tokens=120,
            hard_threshold_tokens=400,
            safety_margin_tokens=20,
            estimator_digest=_DIGEST,
            overage_reason=None,
        ),
    )


def _prepare_proposal_evidence(
    *,
    operation_id: str,
    attempt_number: int,
) -> tuple[CompactionRequest, CompactorProposalRunInput]:
    """从一个 synthetic invocation 准备 manifest/identity 共用输入。

    :param operation_id: 当前 proactive compaction operation id。
    :param attempt_number: 当前 proposal attempt number。
    :returns: Host request 与同源 prepared Engine request input。
    :raises Exception: test fake 或 contract 校验失败时透传。
    """

    request = _schedule_request(f"{operation_id}:{attempt_number}")
    agent_request = _proposal_agent_request(
        request=request,
        operation_id=operation_id,
        attempt_number=attempt_number,
    )
    compact_input = conversation_compact_input_vnext_from_material_pack(request.material_pack)
    projection: Mapping[str, JsonValue] = {
        "projection_kind": "proactive_owner_fixture",
        "compaction_request_digest": request.digest(),
    }
    roles = tuple(message.role.value for message in agent_request.messages)
    prepared_input = CompactorProposalRunInput(
        compact_input=compact_input,
        agent_request=agent_request,
        compaction_request_digest=request.digest(),
        compactor_engine_run_id=agent_request.run_id,
        message_count=len(agent_request.messages),
        role_sequence_digest=runner_role_sequence_digest(roles),
        system_prompt_asset_digest=sha256_digest_json({"prompt": "Proactive owner fixture system prompt."}),
        user_prompt_template_digest=sha256_digest_json({"prompt": "Proactive owner fixture input."}),
        user_prompt_digest=sha256_digest_json({"compaction_request_digest": request.digest()}),
        compactor_input_projection=projection,
        compactor_input_projection_digest=sha256_digest_json(projection),
        repair_feedback=None,
    )
    return request, prepared_input


def _proposal_agent_request(
    *,
    request: CompactionRequest,
    operation_id: str,
    attempt_number: int,
) -> AgentRunRequest:
    """构造 manifest 与 response identity 共用的 synthetic Engine request。

    :param request: 当前 proactive compaction request。
    :param operation_id: 当前 compaction operation id。
    :param attempt_number: 当前 proposal attempt number。
    :returns: 无 ordinary attempt/execution 的同源 AgentRunRequest。
    :raises ValueError: request contract 字段非法时抛出。
    """

    return AgentRunRequest(
        run_id=f"proactive-compactor:{operation_id}:{attempt_number}",
        session_id=f"context-compactor:{request.session_id}",
        attempt_id=None,
        execution_id=None,
        messages=(
            SystemMessage(
                role=AgentMessageRole.SYSTEM,
                content="Proactive owner fixture system prompt.",
            ),
            UserMessage(
                role=AgentMessageRole.USER,
                content="Proactive owner fixture input.",
            ),
        ),
        disable_tools=True,
        runner_spec=RunnerSpec(
            provider=_FIXTURE_PROVIDER,
            model=_FIXTURE_MODEL,
            endpoint="https://example.invalid",
            api_key_ref="env:TEST_PROACTIVE_COMPACTOR_API_KEY",
            headers={},
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            default_timeout_seconds=1.0,
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
            allow_tool_calls=False,
            tool_execution_timeout_seconds=1.0,
            fallback_prompt="Proactive owner fixture fallback.",
            continuation_prompt="Proactive owner fixture continuation.",
        ),
        tool_schemas=(),
        tool_executor=NoToolExecutor(),
        cancellation_token=ControllableCancellationToken(),
    )


def _recorded_proposal_evidence(
    store: HostDurableStore,
    *,
    operation_id: str,
    attempt_number: int,
) -> tuple[SuccessfulRunnerResponseIdentity, CompactorProposalManifestReference]:
    """记录 proposal manifest 并返回同一 request 派生的 sibling evidence。

    :param store: 当前测试 durable store。
    :param operation_id: 当前 proactive compaction operation id。
    :param attempt_number: 当前 proposal attempt number。
    :returns: 同一 prepared AgentRunRequest 派生的 response identity 与 manifest。
    :raises Exception: manifest 记录或 identity 校验失败时透传。
    """

    request, prepared_input = _prepare_proposal_evidence(
        operation_id=operation_id,
        attempt_number=attempt_number,
    )
    reference = DurableCompactorProposalManifestRecorder(
        transaction_runner=store.transaction_runner,
        event_log_store=EventLogStore(),
        event_source="pytest",
    ).record_compactor_proposal_manifest(
        request=request,
        prepared_input=prepared_input,
        compaction_operation_id=operation_id,
        compaction_attempt_number=attempt_number,
    )
    return (
        _successful_response_identity_for_agent_request(prepared_input.agent_request),
        reference,
    )


def _unrecorded_proposal_evidence(
    *,
    operation_id: str,
    attempt_number: int,
) -> tuple[SuccessfulRunnerResponseIdentity, CompactorProposalManifestReference]:
    """构造 orphan negative fixture 的同源但未持久化 sibling evidence。

    :param operation_id: 故意缺少 request owner 的 operation id。
    :param attempt_number: 当前 proposal attempt number。
    :returns: 同一 prepared AgentRunRequest 派生的 identity 与未记录 manifest ref。
    :raises Exception: test fixture contract 校验失败时透传。
    """

    _, prepared_input = _prepare_proposal_evidence(
        operation_id=operation_id,
        attempt_number=attempt_number,
    )
    return (
        _successful_response_identity_for_agent_request(prepared_input.agent_request),
        CompactorProposalManifestReference(
            manifest_event_id=(f"unrecorded-manifest:{operation_id}:{attempt_number}"),
            manifest_payload_ref=(f"unrecorded-manifest-payload:{operation_id}:{attempt_number}"),
            manifest_digest=prepared_input.role_sequence_digest,
            compactor_input_projection_ref=(f"unrecorded-projection:{operation_id}:{attempt_number}"),
            compactor_input_projection_digest=(prepared_input.compactor_input_projection_digest),
            compaction_operation_id=operation_id,
            compaction_attempt_number=attempt_number,
            compactor_engine_run_id=prepared_input.compactor_engine_run_id,
        ),
    )


def _schedule_tier_requests() -> tuple[ProactiveCompactionTierRequest, ...]:
    """构造按 canonical tier 顺序排列且 digest 各异的 requests。

    :returns: tier 1、2、3 typed requests。
    :raises Exception: production request 构造失败时透传。
    """

    return (
        ProactiveCompactionTierRequest(
            stage=ProactiveCompactionAttemptStage.TIER_1_FALLBACK_CAPS,
            request=_schedule_request("tier-1"),
        ),
        ProactiveCompactionTierRequest(
            stage=ProactiveCompactionAttemptStage.TIER_2_SECTION_DEGRADE,
            request=_schedule_request("tier-2"),
        ),
        ProactiveCompactionTierRequest(
            stage=ProactiveCompactionAttemptStage.TIER_3_DELTA_ONLY,
            request=_schedule_request("tier-3"),
        ),
    )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 owner 测试专用 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: durable store options。
    :raises Exception: options 校验失败时透传。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _append_event(
    store: HostDurableStore,
    *,
    event_id: str,
    event_type: str,
    payload: Mapping[str, JsonValue],
    attempt_id: str | None = None,
    execution_id: str | None = None,
) -> None:
    """追加 owner 测试所需 canonical event。

    :param store: 已打开的 durable store。
    :param event_id: canonical event id。
    :param event_type: event type。
    :param payload: typed builder 生成的 payload。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :returns: ``None``。
    :raises Exception: durable append 失败时透传。
    """

    def _operation(transaction: HostTransaction) -> None:
        """在单个 write transaction 中追加 event。

        :param transaction: Host write transaction。
        :returns: ``None``。
        :raises Exception: EventLog append 失败时透传。
        """

        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=_SESSION_ID,
                run_id=_RUN_ID,
                attempt_id=attempt_id,
                execution_id=execution_id,
                event_type=event_type,
                occurred_at=_NOW,
                actor="pytest",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=payload,
                payload_ref=None,
                payload_digest=None,
            ),
        )

    store.transaction_runner.run_write(_operation)


def _requested_payload(
    operation_id: str,
    *,
    max_attempt_number: int,
    trigger_source: ContextCompactionTriggerSource = (ContextCompactionTriggerSource.PROACTIVE),
    ordinal: int = 0,
) -> Mapping[str, JsonValue]:
    """构造 strict requested payload。

    :param operation_id: request/event 同源 operation id。
    :param max_attempt_number: 冻结全局 attempt 上限。
    :param trigger_source: proactive 或分页噪声用 reactive source。
    :param ordinal: reactive identity 唯一序号。
    :returns: strict request payload。
    :raises Exception: payload builder 校验失败时透传。
    """

    reactive = trigger_source is ContextCompactionTriggerSource.REACTIVE
    return build_context_compaction_requested_payload(
        operation_id=operation_id,
        max_compaction_attempts_per_operation=max_attempt_number,
        trigger_source=trigger_source,
        budget_reason="compact_soft_threshold",
        budget_snapshot_ref=f"budget-snapshot-{ordinal}",
        input_snapshot_cursor=17,
        estimator_digest=_DIGEST,
        policy_ref="policy-proactive-owner",
        provider_request_id=None,
        provider_error_ref=None,
        attempt_id=f"attempt-reactive-{ordinal}" if reactive else None,
        execution_id=f"execution-reactive-{ordinal}" if reactive else None,
        client_correlation_id=None,
        frozen_material_list_digest=_DIGEST,
        frozen_material_refs=("event-input-owner",),
    )


def _rejected_payload(
    operation_id: str,
    *,
    attempt_number: int,
    successful_response_identity: SuccessfulRunnerResponseIdentity,
    proposal_manifest_reference: CompactorProposalManifestReference,
) -> Mapping[str, JsonValue]:
    """构造 strict rejected attempt payload。

    :param operation_id: proactive operation id。
    :param attempt_number: 全局 attempt number。
    :param successful_response_identity: quality rejection 前的成功 final 身份。
    :param proposal_manifest_reference: 与 operation/attempt/run 同源的 manifest。
    :returns: strict rejected payload。
    :raises Exception: payload builder 校验失败时透传。
    """

    return build_context_compaction_attempt_rejected_payload(
        operation_id=operation_id,
        attempt_number=attempt_number,
        failure_category="quality_check_rejected",
        repairable=True,
        runner_attempt_summary_refs=(f"runner-attempt:{attempt_number}",),
        diagnostic_refs=(f"diagnostic:{attempt_number}",),
        next_policy_decision="retry_semantic_repair",
        budget_after_attempted_compact=81,
        successful_response_identity=successful_response_identity,
        proposal_manifest_reference=proposal_manifest_reference,
    )


def _failed_payload(
    operation_id: str,
    *,
    attempt_count: int = 0,
) -> Mapping[str, JsonValue]:
    """构造 strict failed terminal payload。

    :param operation_id: proactive operation id。
    :param attempt_count: durable history 中已消费的 global attempt 数。
    :returns: strict failed terminal payload。
    :raises Exception: payload builder 校验失败时透传。
    """

    return build_context_compaction_failed_payload(
        operation_id=operation_id,
        failure_reason="fixture_failure",
        policy_decision="compact_soft_threshold",
        retryable=False,
        attempt_count=attempt_count,
        retry_repair_budget_exhausted=True,
        diagnostic_refs=("diagnostic:failed",),
        budget_after_attempted_compact=81,
    )


def _projection(store: HostDurableStore) -> ProactiveCompactionProjection:
    """读取固定目标 Run 的 typed proactive projection。

    :param store: 已打开的 durable store。
    :returns: typed projection。
    :raises Exception: durable owner 读取失败时透传。
    """

    def _operation(transaction: HostTransaction) -> ProactiveCompactionProjection:
        """在一个 read transaction 中执行 owner projection。

        :param transaction: Host read transaction。
        :returns: typed projection。
        :raises Exception: owner reader 异常透传。
        """

        return read_proactive_compaction_projection(
            transaction,
            EventLogStore(),
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
        )

    return store.transaction_runner.run_read(_operation)


@pytest.mark.parametrize(
    ("max_attempt_number", "expected_stages"),
    (
        (1, (ProactiveCompactionAttemptStage.ROOT,)),
        (
            2,
            (
                ProactiveCompactionAttemptStage.ROOT,
                ProactiveCompactionAttemptStage.TIER_1_FALLBACK_CAPS,
            ),
        ),
        (
            3,
            (
                ProactiveCompactionAttemptStage.ROOT,
                ProactiveCompactionAttemptStage.TIER_1_FALLBACK_CAPS,
                ProactiveCompactionAttemptStage.TIER_2_SECTION_DEGRADE,
            ),
        ),
        (
            4,
            (
                ProactiveCompactionAttemptStage.ROOT,
                ProactiveCompactionAttemptStage.TIER_1_FALLBACK_CAPS,
                ProactiveCompactionAttemptStage.TIER_2_SECTION_DEGRADE,
                ProactiveCompactionAttemptStage.TIER_3_DELTA_ONLY,
            ),
        ),
        (
            5,
            (
                ProactiveCompactionAttemptStage.ROOT,
                ProactiveCompactionAttemptStage.ROOT_REPAIR,
                ProactiveCompactionAttemptStage.TIER_1_FALLBACK_CAPS,
                ProactiveCompactionAttemptStage.TIER_2_SECTION_DEGRADE,
                ProactiveCompactionAttemptStage.TIER_3_DELTA_ONLY,
            ),
        ),
        (
            6,
            (
                ProactiveCompactionAttemptStage.ROOT,
                ProactiveCompactionAttemptStage.ROOT_REPAIR,
                ProactiveCompactionAttemptStage.ROOT_REPAIR,
                ProactiveCompactionAttemptStage.TIER_1_FALLBACK_CAPS,
                ProactiveCompactionAttemptStage.TIER_2_SECTION_DEGRADE,
                ProactiveCompactionAttemptStage.TIER_3_DELTA_ONLY,
            ),
        ),
    ),
)
def test_typed_schedule_reserves_available_tiers_after_root_repairs(
    max_attempt_number: int,
    expected_stages: tuple[ProactiveCompactionAttemptStage, ...],
) -> None:
    """frozen budget 唯一决定 root repair 与 tier 1-3 stage 映射。

    :param max_attempt_number: 测试的 frozen semantic budget。
    :param expected_stages: design 明示的 attempt-to-stage contract。
    :returns: ``None``。
    :raises AssertionError: stage、attempt 连续性或 request 映射漂移时抛出。
    """

    root_request = _schedule_request("root")
    tier_requests = _schedule_tier_requests()
    schedule = build_proactive_compaction_attempt_schedule(
        root_request=root_request,
        tier_requests=tier_requests,
        max_attempt_number=max_attempt_number,
    )

    assert tuple(plan.attempt_number for plan in schedule) == tuple(range(1, max_attempt_number + 1))
    assert tuple(plan.stage for plan in schedule) == expected_stages
    for plan in schedule:
        if plan.stage in (
            ProactiveCompactionAttemptStage.ROOT,
            ProactiveCompactionAttemptStage.ROOT_REPAIR,
        ):
            assert plan.request is root_request
            continue
        matching_tier = next(tier for tier in tier_requests if tier.stage is plan.stage)
        assert plan.request is matching_tier.request


def test_schedule_validator_accepts_stage_specific_request_digests() -> None:
    """prepared manifest digest 逐 attempt 对照 schedule，不要求跨 tier 相同。

    :returns: ``None``。
    :raises AssertionError: stage-specific digests 被错误拒绝时抛出。
    """

    schedule = build_proactive_compaction_attempt_schedule(
        root_request=_schedule_request("root"),
        tier_requests=_schedule_tier_requests(),
        max_attempt_number=5,
    )
    state = ProactiveCompactionState(
        phase=ProactiveCompactionPhase.INCOMPLETE,
        operation_id="operation-schedule-valid",
        input_snapshot_cursor=17,
        max_attempt_number=5,
        frozen_material_list_digest=_DIGEST,
        frozen_material_refs=("input-root",),
        prepared_attempt_numbers=tuple(plan.attempt_number for plan in schedule),
        rejected_attempt_numbers=(),
        next_attempt_number=6,
        compacted_event_sequence=None,
        failed_event_sequence=None,
        prepared_request_digests=tuple((plan.attempt_number, plan.request.digest()) for plan in schedule),
        invalid_reason=None,
    )

    validate_proactive_compaction_attempt_schedule(state, schedule)
    assert len({digest for _, digest in state.prepared_request_digests}) == 4


def test_schedule_validator_rejects_digest_for_wrong_attempt_stage() -> None:
    """同一 attempt 引用其它 stage request digest 时 deterministic fail closed。

    :returns: ``None``。
    :raises AssertionError: mismatch 未被 owner validator 拒绝时抛出。
    """

    schedule = build_proactive_compaction_attempt_schedule(
        root_request=_schedule_request("root"),
        tier_requests=_schedule_tier_requests(),
        max_attempt_number=5,
    )
    valid_state = ProactiveCompactionState(
        phase=ProactiveCompactionPhase.INCOMPLETE,
        operation_id="operation-schedule-invalid",
        input_snapshot_cursor=17,
        max_attempt_number=5,
        frozen_material_list_digest=_DIGEST,
        frozen_material_refs=("input-root",),
        prepared_attempt_numbers=(1, 2, 3),
        rejected_attempt_numbers=(),
        next_attempt_number=4,
        compacted_event_sequence=None,
        failed_event_sequence=None,
        prepared_request_digests=(
            (1, schedule[0].request.digest()),
            (2, schedule[1].request.digest()),
            (3, schedule[2].request.digest()),
        ),
        invalid_reason=None,
    )
    invalid_state = replace(
        valid_state,
        prepared_request_digests=(
            *valid_state.prepared_request_digests[:2],
            (3, schedule[3].request.digest()),
        ),
    )

    with pytest.raises(RuntimeError, match="request digest changed"):
        validate_proactive_compaction_attempt_schedule(
            invalid_state,
            schedule,
        )


def test_absent_projection_requests_new_operation(tmp_path: Path) -> None:
    """没有 proactive fact 时 owner 返回 ABSENT/CREATE_NEW。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: typed phase/decision 漂移时抛出。
    """

    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.ABSENT
    assert projection.state.operation_id is None
    assert projection.decision is ProactiveCompactionDecision.CREATE_NEW


@pytest.mark.parametrize(
    "orphan_event_type",
    (
        CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        CONTEXT_COMPACTION_FAILED,
    ),
)
def test_orphan_non_request_row_without_request_is_invalid(
    tmp_path: Path,
    orphan_event_type: str,
) -> None:
    """无 request 的 rejection/terminal 不能被投影为 ABSENT。

    :param tmp_path: pytest 临时目录。
    :param orphan_event_type: 待注入的 orphan event type。
    :returns: ``None``。
    :raises AssertionError: orphan row 被静默忽略或获得 operation id 时抛出。
    """

    orphan_operation_id = "orphan-operation-without-request"
    orphan_identity, orphan_manifest = _unrecorded_proposal_evidence(
        operation_id=orphan_operation_id,
        attempt_number=1,
    )
    payload = (
        _rejected_payload(
            orphan_operation_id,
            attempt_number=1,
            successful_response_identity=orphan_identity,
            proposal_manifest_reference=orphan_manifest,
        )
        if orphan_event_type == CONTEXT_COMPACTION_ATTEMPT_REJECTED
        else _failed_payload(orphan_operation_id)
    )
    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store,
            event_id=f"event-{orphan_event_type.lower()}",
            event_type=orphan_event_type,
            payload=payload,
        )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.INVALID
    assert projection.state.operation_id is None
    assert projection.state.invalid_reason == "HostDurableError"
    assert projection.decision is (ProactiveCompactionDecision.FAIL_EXISTING_OPERATION)


def test_valid_reactive_only_history_remains_absent(tmp_path: Path) -> None:
    """strict reactive-only request/terminal 必须与 proactive projection 隔离。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 合法 reactive history 污染 proactive state 时抛出。
    """

    reactive_operation_id = "event-reactive-only-request"
    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store,
            event_id=reactive_operation_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload=_requested_payload(
                reactive_operation_id,
                max_attempt_number=2,
                trigger_source=ContextCompactionTriggerSource.REACTIVE,
                ordinal=1,
            ),
            attempt_id="attempt-reactive-1",
            execution_id="execution-reactive-1",
        )
        _append_event(
            store,
            event_id="event-reactive-only-failed",
            event_type=CONTEXT_COMPACTION_FAILED,
            payload=_failed_payload(reactive_operation_id),
            attempt_id="attempt-reactive-1",
            execution_id="execution-reactive-1",
        )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.ABSENT
    assert projection.state.operation_id is None
    assert projection.decision is ProactiveCompactionDecision.CREATE_NEW


def test_reactive_request_with_unknown_operation_row_is_invalid(
    tmp_path: Path,
) -> None:
    """合法 reactive request 不能掩盖 unknown-operation terminal。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: unknown row 被 reactive 隔离规则吞掉时抛出。
    """

    reactive_operation_id = "event-reactive-before-unknown"
    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store,
            event_id=reactive_operation_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload=_requested_payload(
                reactive_operation_id,
                max_attempt_number=2,
                trigger_source=ContextCompactionTriggerSource.REACTIVE,
                ordinal=2,
            ),
            attempt_id="attempt-reactive-2",
            execution_id="execution-reactive-2",
        )
        _append_event(
            store,
            event_id="event-unknown-operation-failed",
            event_type=CONTEXT_COMPACTION_FAILED,
            payload=_failed_payload("unknown-operation"),
        )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.INVALID
    assert projection.state.operation_id is None
    assert projection.state.invalid_reason == "HostDurableError"
    assert projection.decision is (ProactiveCompactionDecision.FAIL_EXISTING_OPERATION)


def test_incomplete_projection_preserves_frozen_budget_and_rejection(
    tmp_path: Path,
) -> None:
    """INCOMPLETE 投影保留冻结输入，并从全局 rejection 推导 next attempt。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: state/budget/decision 漂移时抛出。
    """

    operation_id = "event-proactive-request-incomplete"
    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store,
            event_id=operation_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload=_requested_payload(operation_id, max_attempt_number=3),
        )
        successful_identity, proposal_manifest = _recorded_proposal_evidence(
            store,
            operation_id=operation_id,
            attempt_number=1,
        )
        _append_event(
            store,
            event_id="event-proactive-rejected-1",
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            payload=_rejected_payload(
                operation_id,
                attempt_number=1,
                successful_response_identity=successful_identity,
                proposal_manifest_reference=proposal_manifest,
            ),
        )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.INCOMPLETE
    assert projection.state.operation_id == operation_id
    assert projection.state.input_snapshot_cursor == 17
    assert projection.state.max_attempt_number == 3
    assert projection.state.frozen_material_list_digest == _DIGEST
    assert projection.state.frozen_material_refs == ("event-input-owner",)
    assert projection.state.prepared_attempt_numbers == (1,)
    assert projection.state.rejected_attempt_numbers == (1,)
    assert projection.state.next_attempt_number == 2
    assert projection.decision is ProactiveCompactionDecision.RESUME_EXISTING


def test_exhausted_incomplete_projection_fails_existing_operation(
    tmp_path: Path,
) -> None:
    """冻结 budget 已耗尽时 owner 只允许 FAIL_EXISTING_OPERATION。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: exhaustion decision 漂移时抛出。
    """

    operation_id = "event-proactive-request-exhausted"
    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store,
            event_id=operation_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload=_requested_payload(operation_id, max_attempt_number=1),
        )
        successful_identity, proposal_manifest = _recorded_proposal_evidence(
            store,
            operation_id=operation_id,
            attempt_number=1,
        )
        _append_event(
            store,
            event_id="event-proactive-rejected-exhausted",
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            payload=_rejected_payload(
                operation_id,
                attempt_number=1,
                successful_response_identity=successful_identity,
                proposal_manifest_reference=proposal_manifest,
            ),
        )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.next_attempt_number == 2
    assert projection.state.max_attempt_number == 1
    assert projection.decision is (ProactiveCompactionDecision.FAIL_EXISTING_OPERATION)


def test_failed_terminal_projection_uses_existing_fallback(tmp_path: Path) -> None:
    """单个 FAILED terminal 投影为 USE_FAILED_FALLBACK。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: terminal phase/decision 漂移时抛出。
    """

    operation_id = "event-proactive-request-failed"
    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store,
            event_id=operation_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload=_requested_payload(operation_id, max_attempt_number=2),
        )
        _append_event(
            store,
            event_id="event-proactive-failed",
            event_type=CONTEXT_COMPACTION_FAILED,
            payload=_failed_payload(operation_id),
        )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.FAILED
    assert projection.state.failed_event_sequence is not None
    assert projection.decision is ProactiveCompactionDecision.USE_FAILED_FALLBACK


def test_completed_proactive_ignores_later_valid_reactive_operations(
    tmp_path: Path,
) -> None:
    """同 Run 后续 strict reactive terminals 不污染已完成 proactive projection。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: reactive operation 被误归并到 proactive 时抛出。
    """

    proactive_operation_id = "event-proactive-request-before-reactive"
    projection: ProactiveCompactionProjection | None = None
    proactive_terminal_sequence: int | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store,
            event_id=proactive_operation_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload=_requested_payload(
                proactive_operation_id,
                max_attempt_number=2,
            ),
        )
        _append_event(
            store,
            event_id="event-proactive-failed-before-reactive",
            event_type=CONTEXT_COMPACTION_FAILED,
            payload=_failed_payload(proactive_operation_id),
        )
        proactive_projection = _projection(store)
        proactive_terminal_sequence = proactive_projection.state.failed_event_sequence
        for ordinal in (1, 2):
            reactive_operation_id = f"event-reactive-later-{ordinal}"
            _append_event(
                store,
                event_id=reactive_operation_id,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                payload=_requested_payload(
                    reactive_operation_id,
                    max_attempt_number=2,
                    trigger_source=ContextCompactionTriggerSource.REACTIVE,
                    ordinal=ordinal,
                ),
                attempt_id=f"attempt-reactive-{ordinal}",
                execution_id=f"execution-reactive-{ordinal}",
            )
            _append_event(
                store,
                event_id=f"event-reactive-failed-later-{ordinal}",
                event_type=CONTEXT_COMPACTION_FAILED,
                payload=_failed_payload(reactive_operation_id),
                attempt_id=f"attempt-reactive-{ordinal}",
                execution_id=f"execution-reactive-{ordinal}",
            )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.FAILED
    assert projection.state.operation_id == proactive_operation_id
    assert projection.state.failed_event_sequence == proactive_terminal_sequence
    assert projection.state.prepared_attempt_numbers == ()
    assert projection.state.rejected_attempt_numbers == ()
    assert projection.decision is ProactiveCompactionDecision.USE_FAILED_FALLBACK


def test_malformed_request_does_not_reuse_earlier_reactive_identity(
    tmp_path: Path,
) -> None:
    """malformed request fail closed，且不能把较早 reactive id 当 proactive id。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: INVALID identity/decision 漂移时抛出。
    """

    reactive_operation_id = "event-reactive-before-malformed"
    malformed_event_id = "event-proactive-request-malformed"
    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store,
            event_id=reactive_operation_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload=_requested_payload(
                reactive_operation_id,
                max_attempt_number=2,
                trigger_source=ContextCompactionTriggerSource.REACTIVE,
                ordinal=3,
            ),
            attempt_id="attempt-reactive-3",
            execution_id="execution-reactive-3",
        )
        _append_event(
            store,
            event_id=malformed_event_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload={"trigger_source": 7},
        )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.INVALID
    assert projection.state.operation_id is None
    assert projection.state.invalid_reason == "ValueError"
    assert projection.decision is (ProactiveCompactionDecision.FAIL_EXISTING_OPERATION)


def test_terminal_operation_mismatch_is_invalid(tmp_path: Path) -> None:
    """terminal operation id 与 request 不同必须 fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: mismatch 被静默接受时抛出。
    """

    operation_id = "event-proactive-request-mismatch"
    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store,
            event_id=operation_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload=_requested_payload(operation_id, max_attempt_number=2),
        )
        _append_event(
            store,
            event_id="event-proactive-failed-mismatch",
            event_type=CONTEXT_COMPACTION_FAILED,
            payload=_failed_payload("different-operation"),
        )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.INVALID
    assert projection.state.operation_id == operation_id
    assert projection.state.failed_event_sequence is not None
    assert projection.decision is (ProactiveCompactionDecision.FAIL_EXISTING_OPERATION)


def test_multiple_terminals_are_invalid(tmp_path: Path) -> None:
    """同 operation 多 terminal 必须投影为 INVALID。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: multi-terminal 被接受时抛出。
    """

    operation_id = "event-proactive-request-multi-terminal"
    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store,
            event_id=operation_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload=_requested_payload(operation_id, max_attempt_number=2),
        )
        for ordinal in (1, 2):
            _append_event(
                store,
                event_id=f"event-proactive-failed-{ordinal}",
                event_type=CONTEXT_COMPACTION_FAILED,
                payload=_failed_payload(operation_id),
            )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.INVALID
    assert projection.state.operation_id == operation_id
    assert projection.state.failed_event_sequence is not None
    assert projection.decision is (ProactiveCompactionDecision.FAIL_EXISTING_OPERATION)


def test_bounded_reader_reaches_proactive_request_after_full_page(
    tmp_path: Path,
) -> None:
    """generic keyset reader 跨完整 page 后仍读取目标 proactive request。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: bounded pagination 截断或 phase 漂移时抛出。
    """

    operation_id = "event-proactive-request-after-page"
    projection: ProactiveCompactionProjection | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        for ordinal in range(64):
            reactive_id = f"event-reactive-request-{ordinal}"
            _append_event(
                store,
                event_id=reactive_id,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                payload=_requested_payload(
                    reactive_id,
                    max_attempt_number=2,
                    trigger_source=ContextCompactionTriggerSource.REACTIVE,
                    ordinal=ordinal,
                ),
                attempt_id=f"attempt-reactive-{ordinal}",
                execution_id=f"execution-reactive-{ordinal}",
            )
        _append_event(
            store,
            event_id=operation_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload=_requested_payload(operation_id, max_attempt_number=2),
        )
        projection = _projection(store)

    assert projection is not None
    assert projection.state.phase is ProactiveCompactionPhase.INCOMPLETE
    assert projection.state.operation_id == operation_id
    assert projection.state.next_attempt_number == 1
    assert projection.decision is ProactiveCompactionDecision.RESUME_EXISTING
