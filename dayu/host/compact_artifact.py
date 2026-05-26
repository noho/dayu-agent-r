"""Host compact artifact store。

本模块把已通过 quality check 的 compaction candidate 写为 canonical JSON
artifact，并在调用方事务内写入 payload descriptor。它不 append EventLog；
后续 slice 只需要使用返回的 descriptor/ref/digest。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.host._public_validation import require_non_empty as _require_non_empty
from dayu.host.compaction import (
    CompactInputRange,
    CompactQualityCheckResult,
    CompactionCandidate,
    CompactionRequest,
    EvidenceBackedFactCandidate,
    MinimumPreserveItemCandidate,
)
from dayu.host.durable.artifact import LocalArtifactRef, LocalArtifactStore
from dayu.host.durable.codec import (
    canonical_json_dumps,
    is_sha256_digest,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.payload import PayloadDescriptor, PayloadStore
from dayu.host.durable.transaction import HostTransaction

_COMPACT_ARTIFACT_MEDIA_TYPE = "application/vnd.dayu.context-compact+json"
_COMPACT_ARTIFACT_KIND = "context_compaction"
_COMPACT_ARTIFACT_SCHEMA_VERSION = 2
_COMPACT_ARTIFACT_REF_PREFIX = "compact-artifact:"
_SHA256_PREFIX = "sha256:"


@dataclass(frozen=True, slots=True)
class CompactArtifactWriteRequest:
    """Compact artifact 写入请求。

    :param compaction_request: 原始 compaction request。
    :param accepted_candidate: 已接受的 compaction candidate。
    :param quality_result: quality check 结果，必须为 accepted。
    :param policy_digest: context policy digest。
    :param payload_ref: descriptor ref；``None`` 时按 artifact digest 派生。
    :param expected_artifact_digest: 预期 artifact digest；无预期时为 ``None``。
    """

    compaction_request: CompactionRequest
    accepted_candidate: CompactionCandidate
    quality_result: CompactQualityCheckResult
    policy_digest: str
    payload_ref: str | None = None
    expected_artifact_digest: str | None = None

    def __post_init__(self) -> None:
        """校验写入请求字段。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        if not isinstance(self.compaction_request, CompactionRequest):
            raise TypeError(
                "CompactArtifactWriteRequest.compaction_request must be "
                "CompactionRequest"
            )
        if not isinstance(self.accepted_candidate, CompactionCandidate):
            raise TypeError(
                "CompactArtifactWriteRequest.accepted_candidate must be "
                "CompactionCandidate"
            )
        if not isinstance(self.quality_result, CompactQualityCheckResult):
            raise TypeError(
                "CompactArtifactWriteRequest.quality_result must be "
                "CompactQualityCheckResult"
            )
        if not self.quality_result.accepted:
            raise ValueError("Compact artifact requires accepted quality result")
        if not is_sha256_digest(self.policy_digest):
            raise ValueError("CompactArtifactWriteRequest.policy_digest is invalid")
        _require_optional_non_empty(
            self.payload_ref, field_name="CompactArtifactWriteRequest.payload_ref"
        )
        if self.expected_artifact_digest is not None and not is_sha256_digest(
            self.expected_artifact_digest
        ):
            raise ValueError(
                "CompactArtifactWriteRequest.expected_artifact_digest is invalid"
            )


@dataclass(frozen=True, slots=True)
class CompactArtifactWriteResult:
    """Compact artifact 写入结果。

    :param payload_descriptor: 已持久化 descriptor。
    :param artifact_ref: 已发布 artifact ref。
    :param compaction_request_digest: compaction request digest。
    :param accepted_candidate_digest: accepted candidate digest。
    """

    payload_descriptor: PayloadDescriptor
    artifact_ref: LocalArtifactRef
    compaction_request_digest: str
    accepted_candidate_digest: str


class CompactArtifactStore:
    """Compact artifact store。

    :param artifact_store: 本地 artifact store。
    :param payload_store: payload descriptor store；未传入时使用默认实例。
    """

    def __init__(
        self,
        artifact_store: LocalArtifactStore,
        payload_store: PayloadStore | None = None,
    ) -> None:
        """初始化 compact artifact store。

        :param artifact_store: 本地 artifact store。
        :param payload_store: payload descriptor store；未传入时使用默认实例。
        :returns: ``None``。
        :raises TypeError: store 类型非法时抛出。
        """

        if not isinstance(artifact_store, LocalArtifactStore):
            raise TypeError("artifact_store must be LocalArtifactStore")
        if payload_store is not None and not isinstance(payload_store, PayloadStore):
            raise TypeError("payload_store must be PayloadStore")
        self._artifact_store = artifact_store
        self._payload_store = payload_store if payload_store is not None else PayloadStore()

    def write_compact_artifact(
        self,
        transaction: HostTransaction,
        request: CompactArtifactWriteRequest,
    ) -> CompactArtifactWriteResult:
        """写入 compact artifact 与 payload descriptor。

        :param transaction: 调用方提供的 Host durable transaction。
        :param request: compact artifact 写入请求。
        :returns: compact artifact 写入结果。
        :raises TypeError: ``request`` 类型非法时抛出。
        :raises HostDigestMismatchError: expected digest 与实际 artifact digest 不一致时抛出。
        :raises HostDurableError: descriptor 写入或 artifact metadata 非法时抛出。
        """

        if not isinstance(request, CompactArtifactWriteRequest):
            raise TypeError("request must be CompactArtifactWriteRequest")
        artifact_json = compact_artifact_json(request)
        artifact_bytes = canonical_json_dumps(artifact_json).encode("utf-8")
        artifact_ref = self._artifact_store.write_artifact_bytes(
            artifact_bytes,
            expected_digest=request.expected_artifact_digest,
        )
        payload_ref = _payload_ref_for_artifact(request, artifact_ref)
        descriptor = self._payload_store.write_payload_descriptor_for_artifact(
            transaction,
            payload_ref,
            artifact_ref,
            _COMPACT_ARTIFACT_MEDIA_TYPE,
            _descriptor_metadata(request, artifact_ref),
        )
        return CompactArtifactWriteResult(
            payload_descriptor=descriptor,
            artifact_ref=artifact_ref,
            compaction_request_digest=request.compaction_request.digest(),
            accepted_candidate_digest=request.accepted_candidate.digest(),
        )


def compact_artifact_json(request: CompactArtifactWriteRequest) -> JsonValue:
    """构造 compact artifact canonical JSON 值。

    :param request: compact artifact 写入请求。
    :returns: JSON object。
    :raises TypeError: ``request`` 类型非法时抛出。
    """

    if not isinstance(request, CompactArtifactWriteRequest):
        raise TypeError("request must be CompactArtifactWriteRequest")
    compaction_request = request.compaction_request
    candidate = request.accepted_candidate
    return {
        "artifact_kind": _COMPACT_ARTIFACT_KIND,
        "schema_version": _COMPACT_ARTIFACT_SCHEMA_VERSION,
        "compaction_request_digest": compaction_request.digest(),
        "accepted_candidate_digest": candidate.digest(),
        "accepted_candidate": candidate.to_json(),
        "quality_result": request.quality_result.to_json(),
        "budget_before_compact": _budget_before_json(compaction_request),
        "budget_after_compact": candidate.budget_after_compact,
        "input_snapshot_refs": _input_snapshot_refs_json(compaction_request),
        "evidence_backed_fact_candidates": _fact_candidate_list_json(
            candidate.evidence_backed_fact_candidates
        ),
        "minimum_preserve_item_candidates": (
            _minimum_preserve_candidate_list_json(
                candidate.minimum_preserve_item_candidates
            )
        ),
        "dropped_ranges": _range_list_json(candidate.dropped_ranges),
        "summarized_ranges": _range_list_json(candidate.summarized_ranges),
        "preserved_fact_refs": {
            "canonical_evidence_refs": _string_list_json(
                candidate.preserved_canonical_evidence_refs
            ),
            "evidence_backed_fact_refs": _string_list_json(
                candidate.preserved_evidence_backed_fact_refs
            ),
        },
        "policy_digest": request.policy_digest,
    }


def _payload_ref_for_artifact(
    request: CompactArtifactWriteRequest, artifact_ref: LocalArtifactRef
) -> str:
    """返回 descriptor payload ref。

    :param request: compact artifact 写入请求。
    :param artifact_ref: 已发布 artifact ref。
    :returns: payload ref。
    :raises HostDurableError: artifact digest 格式非法时抛出。
    """

    if request.payload_ref is not None:
        return request.payload_ref
    if not artifact_ref.artifact_digest.startswith(_SHA256_PREFIX):
        raise HostDurableError("Compact artifact digest has invalid prefix")
    return (
        _COMPACT_ARTIFACT_REF_PREFIX
        + artifact_ref.artifact_digest.removeprefix(_SHA256_PREFIX)
    )


def _descriptor_metadata(
    request: CompactArtifactWriteRequest, artifact_ref: LocalArtifactRef
) -> Mapping[str, JsonValue]:
    """构造 descriptor metadata。

    :param request: compact artifact 写入请求。
    :param artifact_ref: 已发布 artifact ref。
    :returns: metadata JSON object。
    """

    return {
        "artifact_kind": _COMPACT_ARTIFACT_KIND,
        "schema_version": _COMPACT_ARTIFACT_SCHEMA_VERSION,
        "artifact_digest": artifact_ref.artifact_digest,
        "compaction_request_digest": request.compaction_request.digest(),
        "accepted_candidate_digest": request.accepted_candidate.digest(),
        "policy_digest": request.policy_digest,
    }


def _budget_before_json(request: CompactionRequest) -> JsonValue:
    """构造 compact 前预算 JSON。

    :param request: compaction request。
    :returns: budget JSON object。
    """

    estimate = request.budget_before_compact
    return {
        "estimated_input_tokens": estimate.estimated_input_tokens,
        "input_budget_tokens": estimate.input_budget_tokens,
        "soft_threshold_tokens": estimate.soft_threshold_tokens,
        "hard_threshold_tokens": estimate.hard_threshold_tokens,
        "safety_margin_tokens": estimate.safety_margin_tokens,
        "estimator_digest": estimate.estimator_digest,
        "overage_reason": (
            None if estimate.overage_reason is None else estimate.overage_reason.value
        ),
    }


def _input_snapshot_refs_json(request: CompactionRequest) -> JsonValue:
    """构造输入 snapshot refs JSON。

    :param request: compaction request。
    :returns: snapshot refs JSON object。
    """

    return {
        "material_source_refs": _string_list_json(request.material_source_refs),
        "memory_snapshot_cursor": request.memory_snapshot_cursor,
        "current_input_ref": request.current_input_ref,
        "material_pack_digest": request.material_pack.provenance_map[
            request.material_pack.current_input_anchor.anchor_label
        ].content_digest,
        "segment_selection_digest": request.segment_selection.selection_digest,
        "canonical_evidence_refs": _string_list_json(request.canonical_evidence_refs),
        "evidence_backed_fact_refs": _string_list_json(
            request.evidence_backed_fact_refs
        ),
        "recent_raw_turn_refs": _string_list_json(request.recent_raw_turn_refs),
        "older_raw_turn_refs": _string_list_json(request.older_raw_turn_refs),
        "existing_episode_summary_refs": _string_list_json(
            request.existing_episode_summary_refs
        ),
    }


def _range_list_json(values: tuple[CompactInputRange, ...]) -> list[JsonValue]:
    """把 compact range tuple 转换为 JSON 数组。

    :param values: compact range tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _fact_candidate_list_json(
    values: tuple[EvidenceBackedFactCandidate, ...],
) -> list[JsonValue]:
    """把 fact candidate tuple 转换为 JSON 数组。

    :param values: candidate tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _minimum_preserve_candidate_list_json(
    values: tuple[MinimumPreserveItemCandidate, ...],
) -> list[JsonValue]:
    """把 minimum preserve item candidate tuple 转换为 JSON 数组。

    :param values: candidate tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _string_list_json(values: tuple[str, ...]) -> list[JsonValue]:
    """把字符串 tuple 转换为 JSON 数组。

    :param values: 字符串 tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value)
    return result


def _require_optional_non_empty(value: str | None, *, field_name: str) -> None:
    """校验可选非空字符串。

    :param value: 待校验值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises ValueError: 字符串存在但为空时抛出。
    """

    if value is not None:
        _require_non_empty(value, field_name=field_name)


__all__ = [
    "CompactArtifactStore",
    "CompactArtifactWriteRequest",
    "CompactArtifactWriteResult",
    "compact_artifact_json",
]
