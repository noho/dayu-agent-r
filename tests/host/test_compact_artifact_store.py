"""vNext compact artifact store 测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dayu.host.compact_artifact import (
    CompactArtifactStore,
    CompactArtifactWriteRequest,
    compact_artifact_json,
)
from dayu.host.compact_material import (
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    build_initial_material_pack,
    conversation_compact_input_vnext_from_material_pack,
    initial_segment_selection,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactQualityCheckResultVNext,
    CompactQualityIssueVNext,
    CompactSegmentTrigger,
    CompactionRequest,
    ConversationCompactOutputVNext,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_governance import check_conversation_compact_output_vnext
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.artifact import LocalArtifactStore
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_bytes
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDigestMismatchError
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import PayloadKind, read_payload_descriptor
from dayu.host.durable.schema import TABLE_PAYLOAD_DESCRIPTORS
from dayu.host.durable.transaction import HostTransaction
from tests.host.fake_cancellation import ControllableCancellationToken
from tests.host.fake_compaction import FakeContextCompactor

_POLICY_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.mark.asyncio
async def test_compact_artifact_store_writes_deterministic_descriptor_with_digest(
    tmp_path: Path,
) -> None:
    """Artifact store 写 deterministic descriptor 与 digest。"""

    options = _options(tmp_path)
    write_request = await _write_request()
    expected_bytes = canonical_json_dumps(compact_artifact_json(write_request)).encode(
        "utf-8"
    )
    expected_digest = sha256_digest_bytes(expected_bytes)

    with open_host_durable_store(options) as durable_store:

        def operation(transaction: HostTransaction) -> tuple[str, str, str, str]:
            """写入 compact artifact。

            :param transaction: Host transaction。
            :returns: payload ref、payload digest、artifact digest 与 metadata JSON。
            """

            result = CompactArtifactStore(
                LocalArtifactStore(options.payload_policy.artifact_root)
            ).write_compact_artifact(transaction, write_request)
            return (
                result.payload_descriptor.payload_ref,
                result.payload_descriptor.payload_digest,
                result.artifact_ref.artifact_digest,
                result.payload_descriptor.metadata_json,
            )

        payload_ref, payload_digest, artifact_digest, metadata_json = (
            durable_store.transaction_runner.run_write(operation)
        )
        assert payload_ref == expected_digest.replace("sha256:", "compact-artifact:")
        assert payload_digest == expected_digest
        assert artifact_digest == expected_digest
        metadata = json.loads(metadata_json)
        assert metadata["artifact_kind"] == "context_compaction"
        assert metadata["schema_version"] == 3
        assert metadata["compaction_request_digest"] == (
            write_request.compaction_request.digest()
        )
        assert metadata["accepted_candidate_digest"] == (
            write_request.accepted_candidate.digest()
        )


@pytest.mark.asyncio
async def test_compact_artifact_content_contains_required_vnext_fields() -> None:
    """Artifact content 包含 vNext canonical 字段且不输出旧 payload 字段。"""

    write_request = await _write_request()
    artifact_json = compact_artifact_json(write_request)

    assert isinstance(artifact_json, dict)
    assert artifact_json["schema_version"] == 3
    assert artifact_json["compaction_request_digest"] == (
        write_request.compaction_request.digest()
    )
    assert artifact_json["accepted_candidate"] == (
        write_request.accepted_candidate.to_json()
    )
    assert artifact_json["quality_result"] == write_request.quality_result.to_json()
    assert artifact_json["budget_after_compact"] == write_request.budget_after_compact
    assert artifact_json["policy_digest"] == write_request.policy_digest
    assert artifact_json["accepted_evidence_mapping_refs"] == ["evidence:accepted-1"]
    assert "preserved_fact_refs" not in artifact_json
    assert "canonical_evidence_refs" not in artifact_json
    assert "evidence_backed_fact_refs" not in artifact_json


@pytest.mark.asyncio
async def test_compact_artifact_store_rejects_corrupted_expected_digest(
    tmp_path: Path,
) -> None:
    """Artifact expected digest 损坏时拒绝写 descriptor。"""

    options = _options(tmp_path)
    wrong_digest = sha256_digest_bytes(b"wrong")
    write_request = await _write_request(expected_artifact_digest=wrong_digest)

    with open_host_durable_store(options) as durable_store:

        def operation(transaction: HostTransaction) -> None:
            """尝试写入 compact artifact。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostDigestMismatchError: expected digest 不匹配时抛出。
            """

            CompactArtifactStore(
                LocalArtifactStore(options.payload_policy.artifact_root)
            ).write_compact_artifact(transaction, write_request)

        with pytest.raises(HostDigestMismatchError):
            durable_store.transaction_runner.run_write(operation)

        def count_descriptors(transaction: HostTransaction) -> int:
            """统计 descriptor rows。

            :param transaction: Host transaction。
            :returns: descriptor row count。
            """

            row = transaction.fetchone(
                f"SELECT COUNT(*) AS total FROM {TABLE_PAYLOAD_DESCRIPTORS}"
            )
            assert row is not None
            total = row.get("total")
            assert isinstance(total, int)
            return total

        assert durable_store.transaction_runner.run_read(count_descriptors) == 0


@pytest.mark.asyncio
async def test_compact_artifact_write_request_rejects_unaccepted_quality_result() -> None:
    """Artifact 写入请求拒绝未通过 vNext quality check 的候选。"""

    request, candidate, quality_result = await _candidate_bundle()
    rejected_quality = CompactQualityCheckResultVNext(
        accepted=False,
        rejection_reasons=(CompactQualityIssueVNext.UNKNOWN_SOURCE_LABEL,),
    )
    write_request = CompactArtifactWriteRequest(
        compaction_request=request,
        accepted_candidate=candidate,
        quality_result=quality_result,
        policy_digest=_POLICY_DIGEST,
        budget_after_compact=700,
    )
    assert write_request.accepted_candidate.digest() == candidate.digest()

    with pytest.raises(ValueError, match="accepted quality result"):
        CompactArtifactWriteRequest(
            compaction_request=request,
            accepted_candidate=candidate,
            quality_result=rejected_quality,
            policy_digest=_POLICY_DIGEST,
            budget_after_compact=700,
        )


@pytest.mark.asyncio
async def test_compact_artifact_descriptor_can_be_read_back(tmp_path: Path) -> None:
    """写入后的 artifact descriptor 可通过 PayloadStore helper 读回。"""

    options = _options(tmp_path)
    write_request = await _write_request(payload_ref="compact-artifact:test-ref")

    with open_host_durable_store(options) as durable_store:

        def operation(transaction: HostTransaction) -> tuple[str, PayloadKind]:
            """写入并读回 descriptor。

            :param transaction: Host transaction。
            :returns: payload ref 与 kind。
            """

            CompactArtifactStore(
                LocalArtifactStore(options.payload_policy.artifact_root)
            ).write_compact_artifact(transaction, write_request)
            descriptor = read_payload_descriptor(transaction, "compact-artifact:test-ref")
            assert descriptor is not None
            return descriptor.payload_ref, descriptor.payload_kind

        assert durable_store.transaction_runner.run_write(operation) == (
            "compact-artifact:test-ref",
            PayloadKind.ARTIFACT_REF,
        )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.05,
            write_busy_retry_count=2,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.0,
            write_retry_max_delay_seconds=0.001,
        ),
    )


async def _write_request(
    *,
    payload_ref: str | None = None,
    expected_artifact_digest: str | None = None,
) -> CompactArtifactWriteRequest:
    """构造 compact artifact 写入请求。

    :param payload_ref: payload ref；无时自动派生。
    :param expected_artifact_digest: 预期 artifact digest。
    :returns: compact artifact 写入请求。
    """

    request, candidate, quality_result = await _candidate_bundle()
    return CompactArtifactWriteRequest(
        compaction_request=request,
        accepted_candidate=candidate,
        quality_result=quality_result,
        policy_digest=_POLICY_DIGEST,
        budget_after_compact=700,
        payload_ref=payload_ref,
        expected_artifact_digest=expected_artifact_digest,
    )


async def _candidate_bundle() -> tuple[
    CompactionRequest, ConversationCompactOutputVNext, CompactQualityCheckResultVNext
]:
    """构造已通过 vNext quality check 的 candidate bundle。

    :returns: request、candidate 与 quality result。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, ControllableCancellationToken())
    compact_input = conversation_compact_input_vnext_from_material_pack(
        request.material_pack
    )
    quality_result = check_conversation_compact_output_vnext(compact_input, candidate)
    assert quality_result.accepted is True
    return request, candidate, quality_result


def _request() -> CompactionRequest:
    """构造标准 compaction request。

    :returns: compaction request。
    """

    material_pack = build_initial_material_pack(
        current_input_ref="event-current",
        current_input_text="分析 A 公司 2025 年年报",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="event-old",
                text="上一轮回答摘要",
                kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            ),
        ),
        evidence_materials=(
            InitialEvidenceMaterial(
                canonical_source_ref="evidence:accepted-1",
                accepted_evidence_id="evidence:accepted-1",
                tool_result_event_ref="event-tool-result-accepted-1",
                tool_call_event_ref="event-tool-call-accepted-1",
                readable_tool_name="fins.search",
                readable_query_text="accepted tool query",
                raw_result_text="canonical evidence raw content accepted-1",
                readable_source_text="accepted tool evidence",
                payload_refs=("payload:accepted-1",),
            ),
        ),
    )
    return CompactionRequest(
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        session_id="session-1",
        run_id="run-1",
        attempt_id=None,
        execution_id=None,
        memory_snapshot_cursor=7,
        material_pack=material_pack,
        segment_selection=initial_segment_selection(
            trigger_source=CompactSegmentTrigger.PROACTIVE,
            input_cursor=2,
            material_pack=material_pack,
        ),
        evidence_backed_fact_refs=("fact-existing-1",),
        recent_raw_turn_refs=("event-current",),
        older_raw_turn_refs=("event-old",),
        existing_episode_summary_refs=("summary-prev",),
        budget_before_compact=BudgetEstimate(
            estimated_input_tokens=900,
            input_budget_tokens=4096,
            soft_threshold_tokens=3200,
            hard_threshold_tokens=3900,
            safety_margin_tokens=200,
            estimator_digest="estimate-digest",
            overage_reason=None,
        ),
    )
