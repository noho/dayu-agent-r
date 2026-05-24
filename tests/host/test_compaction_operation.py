"""Host compaction operation async retry tests。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.host.compact_material import (
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    build_initial_material_pack,
    initial_segment_selection,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactSegmentTrigger,
    CompactionCandidate,
    CompactionRequest,
    ContextCompactor,
    EpisodeSummaryCandidate,
    PinnedPatchOperation,
    PinnedStatePatchCandidate,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
    PreservationEvidence,
)
from dayu.host.compaction_evidence import (
    SelectedEvidenceBlockRef,
    collect_compaction_request_evidence_inputs,
    collect_selected_compaction_request_evidence_inputs,
)
from dayu.host.compaction_operation import run_compaction_operation
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.errors import HostDurableError
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
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    accepted_evidence_envelope_to_json_value,
)
from dayu.host.durable.transaction import HostTransaction
from tests.host.fake_cancellation import StubCancellationToken
from tests.host.fake_compaction import FakeContextCompactor

_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_NOW = datetime(2026, 5, 22, 1, 2, 3, tzinfo=UTC)


class _FailOnceCompactor(ContextCompactor):
    """首次 proposal 失败，第二次返回 fake candidate。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """执行可重试 proposal。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake compaction candidate。
        :raises RuntimeError: 首次调用时模拟 proposal failure。
        """

        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("proposal failed once")
        return await self._fake.compact(request, cancellation_token)


class _AlwaysFailingCompactor(ContextCompactor):
    """始终 proposal 失败的 compactor。"""

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """模拟 proposal failure。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出 proposal failure。
        """

        del request
        del cancellation_token
        raise RuntimeError("proposal failed")


class _SensitiveFailingCompactor(ContextCompactor):
    """始终抛出带敏感字段的 proposal 异常。"""

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """模拟 provider 错误消息携带 secret。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出带敏感字段的 proposal failure。
        """

        del request
        del cancellation_token
        raise RuntimeError(
            "provider failed Bearer secret-token "
            "api_key=plain-secret token=token-secret secret=raw-secret"
        )


class _CancelAfterFailureCompactor(ContextCompactor):
    """首次失败后请求取消的 compactor。"""

    def __init__(self, token: StubCancellationToken) -> None:
        """初始化可控 token 与调用计数。

        :param token: 测试用可控 cancellation token。
        :returns: ``None``。
        """

        self.calls = 0
        self._token = token

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """首次 proposal 失败并在重试前请求取消。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 不会返回。
        :raises RuntimeError: 首次调用时模拟 proposal failure。
        """

        del request
        del cancellation_token
        self.calls += 1
        self._token.request_cancel("test_cancelled")
        raise RuntimeError("proposal failed before cancellation")


class _QualityRejectOnceCompactor(ContextCompactor):
    """首次返回 quality reject candidate，第二次返回 accepted candidate。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """返回可修复 quality rejection 后的成功 candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: compaction candidate。
        """

        self.calls += 1
        candidate = await self._fake.compact(request, cancellation_token)
        if self.calls == 1:
            return replace(candidate, retained_current_user_input_ref="wrong-input")
        return candidate


class _HardThresholdOnceCompactor(ContextCompactor):
    """首次 compact 后仍越过 hard threshold，第二次返回 accepted candidate。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """返回 hard-threshold rejection 后的成功 candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: compaction candidate。
        """

        self.calls += 1
        candidate = await self._fake.compact(request, cancellation_token)
        if self.calls == 1:
            return replace(
                candidate,
                budget_after_compact=(
                    request.budget_before_compact.hard_threshold_tokens
                ),
            )
        return candidate


class _RecordingCompactor(ContextCompactor):
    """记录 multi-pass request 并返回 fake candidate。"""

    def __init__(self) -> None:
        """初始化 recorder。

        :returns: ``None``。
        """

        self.requests: list[CompactionRequest] = []
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """记录 request 并返回 fake candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake compaction candidate。
        """

        self.requests.append(request)
        return await self._fake.compact(request, cancellation_token)


class _SecondPassFailingCompactor(ContextCompactor):
    """第一 pass 成功，第二 pass proposal 失败。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """第二次调用抛出 proposal failure。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake compaction candidate。
        :raises RuntimeError: 第二次调用时抛出。
        """

        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("second pass failed")
        return await self._fake.compact(request, cancellation_token)


class _DistinctPassCompactor(ContextCompactor):
    """每个 pass 返回不同 summary / patch 的 deterministic compactor。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """返回带 pass 差异的 accepted candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: compaction candidate。
        """

        self.calls += 1
        candidate = await self._fake.compact(request, cancellation_token)
        evidence = PreservationEvidence(
            evidence_id=f"pass-evidence:{self.calls}",
            material_source_refs=request.material_source_refs,
            canonical_evidence_refs=request.canonical_evidence_refs,
            memory_snapshot_cursor=request.memory_snapshot_cursor,
            compact_input_range=None,
        )
        evidence_refs = (evidence.evidence_id,)
        return replace(
            candidate,
            candidate_id=f"pass-candidate:{self.calls}",
            episode_summary_candidate=EpisodeSummaryCandidate(
                candidate_id=f"pass-summary:{self.calls}",
                episode_title=f"Pass {self.calls} summary",
                goal=f"goal from pass {self.calls}",
                completed_actions=(f"action from pass {self.calls}",),
                confirmed_fact_refs=request.evidence_backed_fact_refs,
                confirmed_fact_summaries=(f"fact summary {self.calls}",),
                user_constraints=(f"constraint from pass {self.calls}",),
                open_questions=(f"question from pass {self.calls}",),
                next_step=f"next step from pass {self.calls}",
                tool_finding_refs=request.canonical_evidence_refs,
                source_event_refs=request.material_source_refs,
                evidence_refs=evidence_refs,
            ),
            pinned_state_patch_candidate=PinnedStatePatchCandidate(
                candidate_id=f"pass-patch:{self.calls}",
                current_goal=PinnedTextFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=f"current goal from pass {self.calls}",
                    evidence_refs=evidence_refs,
                ),
                confirmed_subjects=PinnedStringTupleFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=(f"subject from pass {self.calls}",),
                    evidence_refs=evidence_refs,
                ),
                user_constraints=PinnedStringTupleFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=(f"constraint from pass {self.calls}",),
                    evidence_refs=evidence_refs,
                ),
                open_questions=PinnedStringTupleFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=(f"question from pass {self.calls}",),
                    evidence_refs=evidence_refs,
                ),
            ),
            preservation_evidence=(evidence,),
        )


@pytest.mark.asyncio
async def test_run_compaction_operation_retries_async_proposal_failure() -> None:
    """operation await async compactor，并保留 proposal failure 后 retry 行为。"""

    compactor = _FailOnceCompactor()
    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
        cancellation_token=StubCancellationToken(),
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is not None
    assert result.quality_result is not None
    assert result.quality_result.accepted is True
    assert len(result.rejected_attempts) == 1
    assert result.rejected_attempts[0].repairable is True
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_retries_quality_rejection() -> None:
    """quality_check_rejected 后 retry，并接受第二次 candidate。"""

    compactor = _QualityRejectOnceCompactor()
    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
        cancellation_token=StubCancellationToken(),
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is not None
    assert len(result.rejected_attempts) == 1
    assert result.rejected_attempts[0].failure_category == "quality_check_rejected"
    assert result.rejected_attempts[0].repairable is True
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_retries_hard_threshold_after_compact() -> None:
    """proactive hard_threshold_after_compact 后 retry，并接受第二次 candidate。"""

    compactor = _HardThresholdOnceCompactor()
    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
        cancellation_token=StubCancellationToken(),
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is not None
    assert len(result.rejected_attempts) == 1
    assert (
        result.rejected_attempts[0].failure_category
        == "hard_threshold_after_compact"
    )
    assert result.rejected_attempts[0].repairable is True
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_accepts_reactive_budget_estimate_overflow() -> None:
    """reactive compact 不用 compact 后估算值阻断 recovery dispatch。

    :returns: ``None``。
    :raises AssertionError: reactive path 仍按估算 hard threshold reject 时抛出。
    """

    compactor = _HardThresholdOnceCompactor()
    result = await run_compaction_operation(
        request=_request(trigger_source=ContextCompactionTriggerSource.REACTIVE),
        compactor=compactor,
        max_attempts=2,
        cancellation_token=StubCancellationToken(),
    )

    assert compactor.calls == 1
    assert result.accepted_candidate is not None
    assert result.quality_result is not None
    assert len(result.rejected_attempts) == 0
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_fails_after_async_attempt_budget() -> None:
    """operation await async compactor，并在 proposal attempts 耗尽后失败。"""

    result = await run_compaction_operation(
        request=_request(),
        compactor=_AlwaysFailingCompactor(),
        max_attempts=2,
        cancellation_token=StubCancellationToken(),
    )

    assert result.accepted_candidate is None
    assert result.quality_result is None
    assert len(result.rejected_attempts) == 2
    assert result.rejected_attempts[0].repairable is True
    assert result.rejected_attempts[1].repairable is False
    assert "proposal failed" in result.rejected_attempts[0].diagnostic_refs[0]
    assert result.failure_reason is not None


@pytest.mark.asyncio
async def test_run_compaction_operation_stops_before_retry_when_cancelled() -> None:
    """首次失败后 token 被取消时，不发起第二次 compactor 调用。"""

    token = StubCancellationToken()
    compactor = _CancelAfterFailureCompactor(token)

    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
        cancellation_token=token,
    )

    assert compactor.calls == 1
    assert result.accepted_candidate is None
    assert result.quality_result is None
    assert result.failure_reason == "cancellation_requested"
    assert len(result.rejected_attempts) == 2
    assert result.rejected_attempts[1].attempt_number == 2
    assert result.rejected_attempts[1].failure_category == "cancellation_requested"
    assert result.rejected_attempts[1].repairable is False
    assert "test_cancelled" in result.rejected_attempts[1].diagnostic_refs[0]


@pytest.mark.asyncio
async def test_run_compaction_operation_redacts_exception_diagnostic_refs() -> None:
    """proposal 异常诊断 ref 不能持久化 Bearer token 或 secret 赋值。"""

    result = await run_compaction_operation(
        request=_request(),
        compactor=_SensitiveFailingCompactor(),
        max_attempts=1,
        cancellation_token=StubCancellationToken(),
    )

    diagnostic_ref = result.rejected_attempts[0].diagnostic_refs[0]
    assert "secret-token" not in diagnostic_ref
    assert "plain-secret" not in diagnostic_ref
    assert "token-secret" not in diagnostic_ref
    assert "raw-secret" not in diagnostic_ref
    assert "<redacted>" in diagnostic_ref


@pytest.mark.asyncio
async def test_reactive_multi_pass_commits_single_merged_context_compacted() -> None:
    """reactive multi-pass 全部成功后只返回一个 merged accepted candidate。"""

    request = _request(trigger_source=ContextCompactionTriggerSource.REACTIVE)
    compactor = _RecordingCompactor()

    result = await run_compaction_operation(
        request=request,
        compactor=compactor,
        max_attempts=2,
        cancellation_token=StubCancellationToken(),
        pass_queue=(request, request),
    )

    assert len(compactor.requests) == 2
    assert result.accepted_candidate is not None
    assert result.accepted_candidate.candidate_id.startswith("merged:")
    assert result.accepted_candidate.preserved_material_source_refs == (
        request.material_source_refs
    )
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_reactive_multi_pass_merges_distinct_summary_and_patch() -> None:
    """reactive multi-pass merge 不丢弃前序 pass 的 summary / tuple patch。"""

    request = _request(trigger_source=ContextCompactionTriggerSource.REACTIVE)
    compactor = _DistinctPassCompactor()

    result = await run_compaction_operation(
        request=request,
        compactor=compactor,
        max_attempts=2,
        cancellation_token=StubCancellationToken(),
        pass_queue=(request, request),
    )

    assert result.accepted_candidate is not None
    summary = result.accepted_candidate.episode_summary_candidate
    assert summary.goal == "goal from pass 1\n\ngoal from pass 2"
    assert summary.completed_actions == (
        "action from pass 1",
        "action from pass 2",
    )
    assert summary.user_constraints == (
        "constraint from pass 1",
        "constraint from pass 2",
    )
    assert summary.open_questions == (
        "question from pass 1",
        "question from pass 2",
    )
    assert summary.next_step == "next step from pass 1\n\nnext step from pass 2"
    assert summary.evidence_refs == ("pass-evidence:1", "pass-evidence:2")
    patch = result.accepted_candidate.pinned_state_patch_candidate
    assert patch.current_goal.value == "current goal from pass 2"
    assert patch.current_goal.evidence_refs == ("pass-evidence:2",)
    assert patch.confirmed_subjects.value == (
        "subject from pass 1",
        "subject from pass 2",
    )
    assert patch.user_constraints.value == (
        "constraint from pass 1",
        "constraint from pass 2",
    )
    assert patch.open_questions.value == (
        "question from pass 1",
        "question from pass 2",
    )
    assert patch.open_questions.evidence_refs == (
        "pass-evidence:1",
        "pass-evidence:2",
    )


@pytest.mark.asyncio
async def test_reactive_multi_pass_intermediate_failure_commits_single_failed_event() -> None:
    """reactive multi-pass 中间 pass 失败时 operation 整体失败且无 partial candidate。"""

    request = _request(trigger_source=ContextCompactionTriggerSource.REACTIVE)
    compactor = _SecondPassFailingCompactor()

    result = await run_compaction_operation(
        request=request,
        compactor=compactor,
        max_attempts=2,
        cancellation_token=StubCancellationToken(),
        pass_queue=(request, request),
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is None
    assert result.failure_reason == "proposal_failed"
    assert len(result.rejected_attempts) == 1
    assert result.rejected_attempts[0].attempt_number == 2


@pytest.mark.asyncio
async def test_reactive_passes_share_operation_attempt_budget() -> None:
    """operation attempt budget 是所有 reactive passes 共享的总 proposal 上限。"""

    request = _request(trigger_source=ContextCompactionTriggerSource.REACTIVE)
    compactor = _RecordingCompactor()

    result = await run_compaction_operation(
        request=request,
        compactor=compactor,
        max_attempts=1,
        cancellation_token=StubCancellationToken(),
        pass_queue=(request, request),
    )

    assert len(compactor.requests) == 1
    assert result.accepted_candidate is None
    assert result.failure_reason == "max_compaction_attempts_exhausted"


def test_compaction_request_evidence_inputs_are_bounded_for_proactive_and_reactive(
    tmp_path: Path,
) -> None:
    """共享 helper 只读取 compact input range 内证据与 raw 内容。"""

    session_id = "session-evidence-range"
    outside_session_id = "session-outside"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_rows(transaction: HostTransaction) -> int:
            """追加测试 EventLog rows。

            :param transaction: Host transaction。
            :returns: compact input range 结束 event sequence。
            """

            inside_event_id = "event-tool-result-inside"
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=inside_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(
                                    inside_event_id
                                )
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(inside_event_id),
                    },
                ),
            )
            end_row = event_log.append_event(
                transaction,
                _event_request(
                    event_id="event-current-input",
                    session_id=session_id,
                    event_type="USER_INPUT_ACCEPTED",
                    payload={"display_text": "current input"},
                ),
            ).row
            outside_event_id = "event-tool-result-after-range"
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=outside_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(
                                    outside_event_id
                                )
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(outside_event_id),
                    },
                ),
            )
            other_session_event_id = "event-tool-result-other-session"
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=other_session_event_id,
                    session_id=outside_session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(
                                    other_session_event_id
                                )
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(other_session_event_id),
                    },
                ),
            )
            return end_row.event_sequence

        end_event_sequence = store.transaction_runner.run_write(append_rows)

        def read_inputs(
            transaction: HostTransaction,
        ) -> tuple[tuple[str, ...], tuple[tuple[str, str, tuple[str, ...]], ...]]:
            """读取共享 helper 输出的 evidence ids 与 raw context。

            :param transaction: Host transaction。
            :returns: evidence id tuple 与 raw context 摘要。
            """

            inputs = collect_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                start_event_sequence=1,
                end_event_sequence=end_event_sequence,
            )
            return (
                tuple(
                    material.accepted_evidence_id
                    for material in inputs.evidence_materials
                ),
                tuple(
                    (
                        item.tool_result_event_ref,
                        item.raw_result_text,
                        (item.accepted_evidence_id,),
                    )
                    for item in inputs.evidence_materials
                ),
            )

        assert store.transaction_runner.run_read(read_inputs) == (
            ("evidence:event-tool-result-inside",),
                (
                    (
                        "event-tool-result-inside",
                        (
                            '{"kind":"completed","result":{"meta":null,"ok":true,'
                            '"value":{"content":"raw content event-tool-result-inside",'
                            '"event_id":"event-tool-result-inside"}}}'
                        ),
                        ("evidence:event-tool-result-inside",),
                    ),
                ),
            )


def test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview(
    tmp_path: Path,
) -> None:
    """Selected evidence reader 从 descriptor 读取 raw payload，不读 envelope preview。"""

    session_id = "session-selected-descriptor"
    event_id = "event-tool-result-descriptor"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_row(transaction: HostTransaction) -> None:
            """写入 descriptor payload 与 selected TOOL_RESULT_ACCEPTED。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            payload = {
                "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
                    _accepted_evidence_envelope_for_event_with_payload_ref(
                        event_id,
                        payload_ref="payload-selected-descriptor",
                        payload_digest=None,
                    )
                ),
                "raw_tool_outcome": _raw_tool_outcome(event_id),
            }
            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-selected-descriptor",
                    payload_id="sqlite-payload-selected-descriptor",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json=payload,
                ),
            )
            event_log.append_event(
                transaction,
                _event_request_with_payload_ref(
                    event_id=event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload_ref=descriptor.payload_ref,
                    payload_digest=descriptor.payload_digest,
                ),
            )

        store.transaction_runner.run_write(append_row)

        def read_inputs(transaction: HostTransaction) -> tuple[str, str, tuple[str, ...]]:
            """读取 selected evidence material。

            :param transaction: Host transaction。
            :returns: raw text、query text 与 payload refs。
            """

            inputs = collect_selected_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                selected_evidence_block_refs=(
                    SelectedEvidenceBlockRef(
                        block_id="selected-evidence-1",
                        tool_result_event_ref=event_id,
                    ),
                ),
            )
            material = inputs.evidence_materials[0]
            return (
                material.raw_result_text,
                material.readable_query_text,
                material.payload_refs,
            )

        assert store.transaction_runner.run_read(read_inputs) == (
            (
                '{"kind":"completed","result":{"meta":null,"ok":true,'
                '"value":{"content":"raw content event-tool-result-descriptor",'
                '"event_id":"event-tool-result-descriptor"}}}'
            ),
            "tool_call_id=tool-call:event-tool-result-descriptor",
            ("payload-selected-descriptor",),
        )


def test_missing_or_digest_mismatch_raw_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    """Selected evidence 缺 raw payload 或 envelope digest 不匹配时 fail closed。"""

    session_id = "session-selected-digest-mismatch"
    missing_raw_event_id = "event-tool-result-missing-raw-selected"
    mismatch_event_id = "event-tool-result-digest-mismatch"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_rows(transaction: HostTransaction) -> None:
            """写入缺 raw 与 digest mismatch 的 selected events。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            event_log.append_event(
                transaction,
                _event_request(
                    event_id=missing_raw_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(
                                    missing_raw_event_id
                                )
                            )
                        )
                    },
                ),
            )
            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-digest-mismatch",
                    payload_id="sqlite-payload-digest-mismatch",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event_with_payload_ref(
                                    mismatch_event_id,
                                    payload_ref="payload-digest-mismatch",
                                    payload_digest=_DIGEST,
                                )
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(mismatch_event_id),
                    },
                ),
            )
            event_log.append_event(
                transaction,
                _event_request_with_payload_ref(
                    event_id=mismatch_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload_ref=descriptor.payload_ref,
                    payload_digest=descriptor.payload_digest,
                ),
            )

        store.transaction_runner.run_write(append_rows)

        with pytest.raises(HostDurableError, match="raw_tool_outcome"):
            _collect_selected_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                event_id=missing_raw_event_id,
            )
        with pytest.raises(HostDurableError, match="payload digest mismatch"):
            _collect_selected_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                event_id=mismatch_event_id,
            )


def test_no_result_preview_field_is_read_or_rendered(tmp_path: Path) -> None:
    """旧 result_preview 字段出现时不读取、不渲染、不回退。"""

    session_id = "session-result-preview-rejected"
    event_id = "event-tool-result-preview"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
                    _accepted_evidence_envelope_for_event(event_id)
                ),
                "raw_tool_outcome": _raw_tool_outcome(event_id),
                "result_preview": "legacy preview must not be used",
            },
        )

        with pytest.raises(HostDurableError, match="result_preview"):
            _collect_selected_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                event_id=event_id,
            )


def test_compaction_request_evidence_inputs_allow_empty_when_range_has_no_envelope(
    tmp_path: Path,
) -> None:
    """range 内没有 accepted_evidence_envelope 时允许显式空 evidence 输入。"""

    session_id = "session-no-evidence"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_rows(transaction: HostTransaction) -> int:
            """追加无 envelope 的 accepted tool result。

            :param transaction: Host transaction。
            :returns: range 结束 event sequence。
            """

            return event_log.append_event(
                transaction,
                _event_request(
                    event_id="event-tool-result-without-envelope",
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={"tool_name": "legacy-free"},
                ),
            ).row.event_sequence

        end_event_sequence = store.transaction_runner.run_write(append_rows)

        def read_inputs(transaction: HostTransaction) -> tuple[str, ...]:
            """读取 helper 输出的 evidence ids。

            :param transaction: Host transaction。
            :returns: evidence id tuple。
            """

            inputs = collect_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                start_event_sequence=1,
                end_event_sequence=end_event_sequence,
            )
            return tuple(
                material.accepted_evidence_id
                for material in inputs.evidence_materials
            )

        assert store.transaction_runner.run_read(read_inputs) == ()


def test_compaction_request_evidence_inputs_reject_malformed_envelope(
    tmp_path: Path,
) -> None:
    """accepted_evidence_envelope 结构损坏时 fail closed。"""

    session_id = "session-malformed-envelope"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        end_event_sequence = _append_event_and_return_sequence(
            store,
            event_log,
            event_id="event-tool-result-malformed-envelope",
            session_id=session_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={"accepted_evidence_envelope": {"evidence_id": "evidence:bad"}},
        )

        with pytest.raises(HostDurableError, match="canonical evidence envelope"):
            _collect_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                end_event_sequence=end_event_sequence,
            )


def test_compaction_request_evidence_inputs_reject_missing_raw_tool_outcome(
    tmp_path: Path,
) -> None:
    """canonical evidence 对应 raw 工具结果缺失时 fail closed。"""

    session_id = "session-missing-raw-tool-outcome"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        event_id = "event-tool-result-missing-raw"
        end_event_sequence = _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
                    _accepted_evidence_envelope_for_event(event_id)
                )
            },
        )

        with pytest.raises(HostDurableError, match="raw_tool_outcome"):
            _collect_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                end_event_sequence=end_event_sequence,
            )


def test_compaction_request_evidence_inputs_reject_envelope_producer_mismatch(
    tmp_path: Path,
) -> None:
    """canonical evidence producer_event_ref 必须匹配 EventLog row id。"""

    session_id = "session-envelope-mismatch"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        end_event_sequence = _append_event_and_return_sequence(
            store,
            event_log,
            event_id="event-tool-result-mismatch",
            session_id=session_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
                    _accepted_evidence_envelope_for_event("event-tool-result-other")
                ),
                "raw_tool_outcome": _raw_tool_outcome("event-tool-result-mismatch"),
            },
        )

        with pytest.raises(HostDurableError, match="producer_event_ref mismatch"):
            _collect_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                end_event_sequence=end_event_sequence,
            )


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (
            {"evidence_backed_fact_candidates": "not-list"},
            "evidence_backed_fact_candidates must be list",
        ),
        (
            {"evidence_backed_fact_candidates": ["not-object"]},
            "evidence_backed_fact_candidate must be object",
        ),
        (
            {"evidence_backed_fact_candidates": [{"candidate_id": ""}]},
            "candidate_id is invalid",
        ),
        (
            {"preserved_fact_refs": "not-object"},
            "preserved_fact_refs is invalid",
        ),
        (
            {"preserved_fact_refs": {"evidence_backed_fact_refs": "not-list"}},
            "evidence_backed_fact_refs must be list",
        ),
        (
            {"preserved_fact_refs": {"evidence_backed_fact_refs": [""]}},
            "evidence_backed_fact_refs item is invalid",
        ),
    ),
)
def test_compaction_request_evidence_inputs_reject_malformed_compacted_payload(
    tmp_path: Path, payload: JsonValue, message: str
) -> None:
    """CONTEXT_COMPACTED fact refs 相关 payload 损坏时 fail closed。

    :param tmp_path: pytest 临时目录。
    :param payload: malformed CONTEXT_COMPACTED payload。
    :param message: 期望错误消息片段。
    """

    session_id = "session-malformed-compacted"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        end_event_sequence = _append_event_and_return_sequence(
            store,
            event_log,
            event_id="event-context-compacted-malformed",
            session_id=session_id,
            event_type="CONTEXT_COMPACTED",
            payload=payload,
        )

        with pytest.raises(HostDurableError, match=message):
            _collect_fact_refs(
                store,
                event_log,
                session_id=session_id,
                end_event_sequence=end_event_sequence,
            )


def test_compaction_request_evidence_inputs_deduplicate_accepted_evidence_ids(
    tmp_path: Path,
) -> None:
    """evidence material 按 accepted evidence id 去重并保留首个。"""

    session_id = "session-duplicate-evidence"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_rows(transaction: HostTransaction) -> int:
            """追加重复 evidence id 的 accepted tool events。

            :param transaction: Host transaction。
            :returns: range 结束 event sequence。
            """

            first_event_id = "event-tool-result-duplicate-first"
            second_event_id = "event-tool-result-duplicate-second"
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=first_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(
                                    first_event_id
                                )
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(first_event_id),
                    },
                ),
            )
            duplicate_envelope = AcceptedEvidenceEnvelope(
                evidence_id=f"evidence:{first_event_id}",
                producer_event_ref=second_event_id,
                tool_name="fins.search",
                tool_call_id=f"tool-call:{second_event_id}",
                tool_query=AcceptedEvidenceToolQuery(
                    tool_call_requested_event_ref=None,
                    normalized_arguments_digest=_DIGEST,
                    semantic_input_digest=_DIGEST,
                ),
                result_ref=AcceptedEvidenceResultRef(
                    payload_ref=None,
                    payload_digest=_DIGEST,
                    outcome_digest=_DIGEST,
                    truncation_applied=False,
                ),
                source_refs=(),
                locator_refs=(),
            )
            return event_log.append_event(
                transaction,
                _event_request(
                    event_id=second_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                duplicate_envelope
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(second_event_id),
                    },
                ),
            ).row.event_sequence

        end_event_sequence = store.transaction_runner.run_write(append_rows)

        assert _collect_evidence_ids(
            store,
            event_log,
            session_id=session_id,
            end_event_sequence=end_event_sequence,
        ) == ("evidence:event-tool-result-duplicate-first",)


def test_compaction_request_evidence_inputs_collect_run_succeeded_raw_context(
    tmp_path: Path,
) -> None:
    """RUN_SUCCEEDED assistant conclusion 进入 history material。"""

    session_id = "session-run-succeeded-raw-context"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        event_id = "event-run-succeeded-summary"
        end_event_sequence = _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="RUN_SUCCEEDED",
            payload={"final_answer": "本轮回答中的稳定结论摘要"},
        )

        def read_history_material(
            transaction: HostTransaction,
        ) -> tuple[tuple[str, CompactMaterialBlockKind, str], ...]:
            """读取共享 helper 输出的 history material 摘要。

            :param transaction: Host transaction。
            :returns: history material 摘要 tuple。
            """

            inputs = collect_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                start_event_sequence=1,
                end_event_sequence=end_event_sequence,
            )
            return tuple(
                (
                    item.canonical_source_ref,
                    item.kind,
                    item.text,
                )
                for item in inputs.history_materials
            )

        assert store.transaction_runner.run_read(read_history_material) == (
            (
                event_id,
                CompactMaterialBlockKind.RAW_ASSISTANT_TURN,
                "本轮回答中的稳定结论摘要",
            ),
        )


def test_compaction_request_evidence_inputs_use_stable_derived_fact_refs(
    tmp_path: Path,
) -> None:
    """CONTEXT_COMPACTED candidate refs 派生为跨 compact event 唯一 memory item refs。"""

    session_id = "session-derived-fact-ref"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        compacted_event_id = "event-context-compacted-derived"
        end_event_sequence = _append_event_and_return_sequence(
            store,
            event_log,
            event_id=compacted_event_id,
            session_id=session_id,
            event_type="CONTEXT_COMPACTED",
            payload={
                "preserved_fact_refs": {
                    "evidence_backed_fact_refs": (
                        ["memory-item:evidence_backed_fact:existing:event-old"]
                    )
                },
                "evidence_backed_fact_candidates": [
                    {"candidate_id": "fact-new"},
                    {"candidate_id": "fact-new"},
                ],
            },
        )

        assert _collect_fact_refs(
            store,
            event_log,
            session_id=session_id,
            end_event_sequence=end_event_sequence,
        ) == (
            "memory-item:evidence_backed_fact:existing:event-old",
            f"memory-item:evidence_backed_fact:fact-new:{compacted_event_id}",
        )


def _request(
    *,
    trigger_source: ContextCompactionTriggerSource = (
        ContextCompactionTriggerSource.PROACTIVE
    ),
) -> CompactionRequest:
    """构造标准 compaction request。

    :param trigger_source: compaction 触发来源。
    :returns: compaction request。
    """

    is_reactive = trigger_source is ContextCompactionTriggerSource.REACTIVE
    return CompactionRequest(
        trigger_source=trigger_source,
        session_id="session-operation",
        run_id="run-operation",
        attempt_id="attempt-operation" if is_reactive else None,
        execution_id="execution-operation" if is_reactive else None,
        memory_snapshot_cursor=7,
        material_pack=_material_pack(),
        segment_selection=initial_segment_selection(
            trigger_source=(
                CompactSegmentTrigger.REACTIVE
                if is_reactive
                else CompactSegmentTrigger.PROACTIVE
            ),
            input_cursor=2,
            material_pack=_material_pack(),
        ),
        evidence_backed_fact_refs=("fact-existing-1",),
        recent_raw_turn_refs=("input-1",),
        older_raw_turn_refs=("input-2",),
        existing_episode_summary_refs=("summary-1",),
        budget_before_compact=BudgetEstimate(
            estimated_input_tokens=100,
            input_budget_tokens=200,
            soft_threshold_tokens=120,
            hard_threshold_tokens=140,
            safety_margin_tokens=20,
            estimator_digest=_DIGEST,
            overage_reason=None,
        ),
    )


def _material_pack():
    """构造 compaction operation 测试 material pack。

    :returns: material pack。
    """

    return build_initial_material_pack(
        current_input_ref="input-1",
        current_input_text="current user text",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="input-2",
                text="previous assistant turn",
                kind=CompactMaterialBlockKind.RAW_ASSISTANT_TURN,
            ),
        ),
        evidence_materials=(
            InitialEvidenceMaterial(
                canonical_source_ref="evidence:accepted-operation",
                accepted_evidence_id="evidence:accepted-operation",
                tool_result_event_ref="event-tool-result-operation",
                tool_call_event_ref="event-tool-call-operation",
                readable_tool_name="fins.search",
                readable_query_text="accepted tool query",
                raw_result_text="operation canonical evidence raw content",
                readable_source_text="accepted tool evidence",
                payload_refs=("payload:operation",),
            ),
        ),
    )


def _accepted_evidence_envelope() -> AcceptedEvidenceEnvelope:
    """构造测试用 canonical evidence envelope。

    :returns: canonical evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id="evidence:accepted-operation",
        producer_event_ref="event-tool-result-operation",
        tool_name="fins.search",
        tool_call_id="tool-call-operation",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref="event-tool-call-operation",
            normalized_arguments_digest=_DIGEST,
            semantic_input_digest=_DIGEST,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref="payload:operation",
            payload_digest=_DIGEST,
            outcome_digest=_DIGEST,
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )


def _accepted_evidence_envelope_for_event(
    event_id: str,
) -> AcceptedEvidenceEnvelope:
    """构造绑定指定 TOOL_RESULT_ACCEPTED event 的 canonical evidence envelope。

    :param event_id: TOOL_RESULT_ACCEPTED event id。
    :returns: canonical evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{event_id}",
        producer_event_ref=event_id,
        tool_name="fins.search",
        tool_call_id=f"tool-call:{event_id}",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=None,
            normalized_arguments_digest=_DIGEST,
            semantic_input_digest=_DIGEST,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=None,
            payload_digest=_DIGEST,
            outcome_digest=_DIGEST,
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )


def _accepted_evidence_envelope_for_event_with_payload_ref(
    event_id: str,
    *,
    payload_ref: str,
    payload_digest: str | None,
) -> AcceptedEvidenceEnvelope:
    """构造带 payload descriptor ref 的 canonical evidence envelope。

    :param event_id: TOOL_RESULT_ACCEPTED event id。
    :param payload_ref: payload descriptor ref。
    :param payload_digest: payload digest；未知时为 ``None``。
    :returns: canonical evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{event_id}",
        producer_event_ref=event_id,
        tool_name="fins.search",
        tool_call_id=f"tool-call:{event_id}",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=None,
            normalized_arguments_digest=_DIGEST,
            semantic_input_digest=_DIGEST,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            outcome_digest=_DIGEST,
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )


def _raw_tool_outcome(event_id: str) -> JsonValue:
    """构造测试用 raw tool outcome。

    :param event_id: 工具结果事件 id。
    :returns: raw tool outcome JSON。
    """

    return {
        "kind": "completed",
        "result": {
            "ok": True,
            "value": {"event_id": event_id, "content": f"raw content {event_id}"},
            "meta": None,
        },
    }


def _append_event_and_return_sequence(
    store: HostDurableStore,
    event_log: EventLogStore,
    *,
    event_id: str,
    session_id: str,
    event_type: str,
    payload: JsonValue,
) -> int:
    """追加单条测试事件并返回 event sequence。

    :param store: Host durable store。
    :param event_log: EventLog store。
    :param event_id: event id。
    :param session_id: Session id。
    :param event_type: event type。
    :param payload: payload JSON。
    :returns: appended event sequence。
    """

    def append_row(transaction: HostTransaction) -> int:
        """在 transaction 内追加事件。

        :param transaction: Host transaction。
        :returns: appended event sequence。
        """

        return event_log.append_event(
            transaction,
            _event_request(
                event_id=event_id,
                session_id=session_id,
                event_type=event_type,
                payload=payload,
            ),
        ).row.event_sequence

    return store.transaction_runner.run_write(append_row)


def _collect_selected_evidence_ids(
    store: HostDurableStore,
    event_log: EventLogStore,
    *,
    session_id: str,
    event_id: str,
) -> tuple[str, ...]:
    """读取 selected helper 输出的 canonical evidence ids。

    :param store: Host durable store。
    :param event_log: EventLog store。
    :param session_id: Session id。
    :param event_id: selected TOOL_RESULT_ACCEPTED event id。
    :returns: evidence id tuple。
    """

    def read_inputs(transaction: HostTransaction) -> tuple[str, ...]:
        """在 transaction 内读取 selected evidence ids。

        :param transaction: Host transaction。
        :returns: evidence id tuple。
        """

        inputs = collect_selected_compaction_request_evidence_inputs(
            transaction,
            event_log,
            session_id=session_id,
            selected_evidence_block_refs=(
                SelectedEvidenceBlockRef(
                    block_id=f"selected:{event_id}",
                    tool_result_event_ref=event_id,
                ),
            ),
        )
        return tuple(
            material.accepted_evidence_id for material in inputs.evidence_materials
        )

    return store.transaction_runner.run_read(read_inputs)


def _collect_evidence_ids(
    store: HostDurableStore,
    event_log: EventLogStore,
    *,
    session_id: str,
    end_event_sequence: int,
) -> tuple[str, ...]:
    """读取共享 helper 输出的 canonical evidence ids。

    :param store: Host durable store。
    :param event_log: EventLog store。
    :param session_id: Session id。
    :param end_event_sequence: compact input range 结束 sequence。
    :returns: evidence id tuple。
    """

    def read_inputs(transaction: HostTransaction) -> tuple[str, ...]:
        """在 transaction 内读取 evidence ids。

        :param transaction: Host transaction。
        :returns: evidence id tuple。
        """

        inputs = collect_compaction_request_evidence_inputs(
            transaction,
            event_log,
            session_id=session_id,
            start_event_sequence=1,
            end_event_sequence=end_event_sequence,
        )
        return tuple(
            material.accepted_evidence_id for material in inputs.evidence_materials
        )

    return store.transaction_runner.run_read(read_inputs)


def _collect_fact_refs(
    store: HostDurableStore,
    event_log: EventLogStore,
    *,
    session_id: str,
    end_event_sequence: int,
) -> tuple[str, ...]:
    """读取共享 helper 输出的 evidence-backed fact refs。

    :param store: Host durable store。
    :param event_log: EventLog store。
    :param session_id: Session id。
    :param end_event_sequence: compact input range 结束 sequence。
    :returns: evidence-backed fact refs。
    """

    def read_inputs(transaction: HostTransaction) -> tuple[str, ...]:
        """在 transaction 内读取 evidence-backed fact refs。

        :param transaction: Host transaction。
        :returns: evidence-backed fact refs。
        """

        inputs = collect_compaction_request_evidence_inputs(
            transaction,
            event_log,
            session_id=session_id,
            start_event_sequence=1,
            end_event_sequence=end_event_sequence,
        )
        return inputs.evidence_backed_fact_refs

    return store.transaction_runner.run_read(read_inputs)


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


def _event_request(
    *,
    event_id: str,
    session_id: str,
    event_type: str,
    payload: JsonValue,
) -> EventLogAppendRequest:
    """构造测试用 EventLog append request。

    :param event_id: event id。
    :param session_id: Session id。
    :param event_type: event type。
    :param payload: payload JSON。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=session_id,
        run_id="run-compaction-operation-test",
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at=_NOW,
        actor="pytest",
        source="test_compaction_operation",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _event_request_with_payload_ref(
    *,
    event_id: str,
    session_id: str,
    event_type: str,
    payload_ref: str,
    payload_digest: str,
) -> EventLogAppendRequest:
    """构造带 payload descriptor ref 的测试 EventLog append request。

    :param event_id: event id。
    :param session_id: Session id。
    :param event_type: event type。
    :param payload_ref: payload descriptor ref。
    :param payload_digest: payload digest。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=session_id,
        run_id="run-compaction-operation-test",
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at=_NOW,
        actor="pytest",
        source="test_compaction_operation",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={"payload_ref": payload_ref},
        payload_ref=payload_ref,
        payload_digest=payload_digest,
    )
