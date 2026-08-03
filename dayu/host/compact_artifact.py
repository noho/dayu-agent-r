"""Host vNext compact artifact store。

本模块把已通过 vNext quality check 的 compact output 写为 canonical JSON
artifact，并在调用方事务内写入 payload descriptor。它不 append EventLog；
后续 memory projection 只能消费已提交的 compact event / descriptor。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.host._public_validation import require_non_empty as _require_non_empty
from dayu.host.compact_payload import (
    COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT,
    compact_artifact_descriptor_metadata_vnext,
    compact_artifact_json_vnext,
    compact_artifact_payload_ref,
)
from dayu.host.compaction import (
    CompactAcceptedTruthV2,
    CompactionRequest,
)
from dayu.host.durable.artifact import LocalArtifactRef, LocalArtifactStore
from dayu.host.durable.codec import canonical_json_dumps, is_sha256_digest
from dayu.host.durable.payload import PayloadDescriptor, PayloadStore
from dayu.host.durable.transaction import HostTransaction


@dataclass(frozen=True, slots=True)
class CompactArtifactWriteRequest:
    """vNext compact artifact 写入请求。

    :param compaction_request: 原始 compaction request。
    :param accepted_truth: Context Governance final accepted truth。
    :param policy_digest: context policy digest。
    :param budget_after_compact: Host 估算的 compact 后预算。
    :param payload_ref: descriptor ref；``None`` 时按 artifact digest 派生。
    :param expected_artifact_digest: 预期 artifact digest；无预期时为 ``None``。
    """

    compaction_request: CompactionRequest
    accepted_truth: CompactAcceptedTruthV2
    policy_digest: str
    budget_after_compact: int
    payload_ref: str | None = None
    expected_artifact_digest: str | None = None

    def __post_init__(self) -> None:
        """校验写入请求字段。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        if not isinstance(self.compaction_request, CompactionRequest):
            raise TypeError("CompactArtifactWriteRequest.compaction_request must be CompactionRequest")
        if not isinstance(self.accepted_truth, CompactAcceptedTruthV2):
            raise TypeError("CompactArtifactWriteRequest.accepted_truth must be CompactAcceptedTruthV2")
        self.accepted_truth.validate_input_binding(
            self.compaction_request.compact_input
        )
        if not is_sha256_digest(self.policy_digest):
            raise ValueError("CompactArtifactWriteRequest.policy_digest is invalid")
        if self.budget_after_compact < 0:
            raise ValueError("CompactArtifactWriteRequest.budget_after_compact must be non-negative")
        _require_optional_non_empty(self.payload_ref, field_name="CompactArtifactWriteRequest.payload_ref")
        if self.expected_artifact_digest is not None and not is_sha256_digest(self.expected_artifact_digest):
            raise ValueError("CompactArtifactWriteRequest.expected_artifact_digest is invalid")


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
            COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT,
            _descriptor_metadata(request, artifact_ref),
        )
        return CompactArtifactWriteResult(
            payload_descriptor=descriptor,
            artifact_ref=artifact_ref,
            compaction_request_digest=request.compaction_request.digest(),
            accepted_candidate_digest=request.accepted_truth.candidate.digest(),
        )


def compact_artifact_json(request: CompactArtifactWriteRequest) -> JsonValue:
    """构造 vNext compact artifact canonical JSON 值。

    :param request: compact artifact 写入请求。
    :returns: JSON object。
    :raises TypeError: ``request`` 类型非法时抛出。
    """

    if not isinstance(request, CompactArtifactWriteRequest):
        raise TypeError("request must be CompactArtifactWriteRequest")
    return compact_artifact_json_vnext(
        request=request.compaction_request,
        accepted_truth=request.accepted_truth,
        policy_digest=request.policy_digest,
        budget_after_compact=request.budget_after_compact,
    )


def _payload_ref_for_artifact(request: CompactArtifactWriteRequest, artifact_ref: LocalArtifactRef) -> str:
    """返回 descriptor payload ref。

    :param request: compact artifact 写入请求。
    :param artifact_ref: 已发布 artifact ref。
    :returns: payload ref。
    :raises ValueError: artifact digest 格式非法时抛出。
    """

    if request.payload_ref is not None:
        return request.payload_ref
    return compact_artifact_payload_ref(artifact_ref.artifact_digest)


def _descriptor_metadata(
    request: CompactArtifactWriteRequest, artifact_ref: LocalArtifactRef
) -> Mapping[str, JsonValue]:
    """构造 descriptor metadata。

    :param request: compact artifact 写入请求。
    :param artifact_ref: 已发布 artifact ref。
    :returns: metadata JSON object。
    """

    return compact_artifact_descriptor_metadata_vnext(
        request=request.compaction_request,
        accepted_truth=request.accepted_truth,
        artifact_digest=artifact_ref.artifact_digest,
        policy_digest=request.policy_digest,
    )


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
