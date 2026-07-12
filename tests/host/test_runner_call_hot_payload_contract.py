"""Host runner-call fixed hot payload owner contract 测试。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.engine_events import (
    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
    runner_role_sequence_digest,
)
from dayu.host import compaction_operation, engine_ingest, run_input
from dayu.host._runner_call_manifest import parse_runner_call_hot_payload
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.errors import HostDurableError

_MESSAGE_COUNTS = (0, 1, 12, 300)
_EXPECTED_HOT_FIELDS = frozenset(
    {
        "session_id",
        "host_run_id",
        "attempt_id",
        "execution_id",
        "runner_call_index",
        "runner_call_kind",
        "runner_call_trigger_reason",
        "iteration_id",
        "iteration_index",
        "manifest_payload_ref",
        "manifest_digest",
        "manifest_schema_version",
        "validation_status",
        "message_count",
        "role_sequence_digest",
        "input_projection_digest",
        "runner_call_projection_artifact_ref",
        "runner_call_projection_artifact_digest",
        "runner_call_projection_artifact_size_bytes",
        "diagnostic",
    }
)


class _HotPayloadTamperKind(StrEnum):
    """shared hot parser 的封闭篡改分类。"""

    MISSING_DIAGNOSTIC = "missing_diagnostic"
    NULL_DIAGNOSTIC = "null_diagnostic"
    MALFORMED_DIAGNOSTIC = "malformed_diagnostic"
    LEGACY_METADATA_ARRAY = "legacy_metadata_array"
    STATUS_MISMATCH = "status_mismatch"
    COUNT_MISMATCH = "count_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"


def _projector_metadata(index: int) -> Mapping[str, JsonValue]:
    """构造 synthetic manifest 使用的完整六字段 projector metadata。

    :param index: message/projector 顺序。
    :returns: 六字段 projector metadata JSON object。
    :raises TypeError: 无主动抛出。
    """

    source_contract_refs: list[JsonValue] = [f"contract:message:{index}"]
    projector_id = "user_input_message"
    schema_version = "run_input_projector.v1"
    purpose = "ordinary_run_input"
    return {
        "projector_metadata_id": f"projector:{index}:user",
        "projector_id": projector_id,
        "projector_schema_version": schema_version,
        "projector_digest": sha256_digest_json(
            {
                "projector_id": projector_id,
                "projector_schema_version": schema_version,
                "purpose": purpose,
                "source_contract_refs": source_contract_refs,
            }
        ),
        "purpose": purpose,
        "source_contract_refs": source_contract_refs,
    }


def _manifest(message_count: int) -> Mapping[str, JsonValue]:
    """构造三个 producer hot adapter 共用的 synthetic full manifest。

    :param message_count: synthetic message/projector 数量。
    :returns: runner-call manifest JSON object。
    :raises TypeError: 无主动抛出。
    """

    roles = tuple("user" for _index in range(message_count))
    projector_metadata: list[JsonValue] = [
        _projector_metadata(index) for index in range(message_count)
    ]
    projection_digest = sha256_digest_json({"projection": message_count})
    message_entries: list[JsonValue] = [
        {
            "index": index,
            "role": role,
            "content_digest": sha256_digest_json(
                {"message": index, "role": role}
            ),
            "content_size_bytes": len(str(index).encode("utf-8")),
            "source_refs": [f"event:message:{index}"],
            "projection_artifact_ref": "payload-runner-projection",
            "projection_artifact_digest": projection_digest,
            "projector_metadata_id": f"projector:{index}:user",
            "provider_tool_calls_digest": None,
            "reasoning_content_digest": None,
        }
        for index, role in enumerate(roles)
    ]
    return {
        "schema_version": "runner_call_input_manifest.v1",
        "manifest_id": "runner-call-manifest:hot-contract",
        "session_id": "session-hot-contract",
        "host_run_id": "run-hot-contract",
        "attempt_id": "attempt-hot-contract",
        "execution_id": "execution-hot-contract",
        "runner_call_index": 0,
        "runner_call_kind": "initial_user_dispatch",
        "runner_call_trigger_reason": "initial_user_input",
        "iteration_id": None,
        "iteration_index": None,
        "message_count": message_count,
        "role_sequence_digest": runner_role_sequence_digest(roles),
        "runner_input_serializer_schema_version": (
            RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
        ),
        "input_projection_digest": sha256_digest_json(
            {"message_count": message_count}
        ),
        "runner_call_projection_artifact_ref": "payload-runner-projection",
        "runner_call_projection_artifact_digest": projection_digest,
        "runner_call_projection_artifact_size_bytes": 128,
        "message_entries": message_entries,
        "source_cursor_refs": ["event:input"],
        "tool_schema_snapshot_refs": [],
        "memory_snapshot_cursor_ref": None,
        "compact_artifact_refs": [],
        "context_fallback_decision_ref": None,
        "projector_metadata": projector_metadata,
        "compactor_identity": None,
        "diagnostic": None,
    }


def _ordinary_hot_payload(
    manifest: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """通过 ordinary producer adapter 构造 hot payload。

    :param manifest: synthetic manifest。
    :returns: ordinary hot payload。
    :raises HostDurableError: manifest 非法时由 production adapter 抛出。
    """

    return run_input._runner_call_manifest_hot_payload(
        manifest=manifest,
        manifest_payload_ref="payload-manifest-ordinary",
        manifest_digest=sha256_digest_json(manifest),
    )


def _engine_hot_payload(
    manifest: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """通过 Engine continuation producer adapter 构造 hot payload。

    :param manifest: synthetic manifest。
    :returns: Engine continuation hot payload。
    :raises HostDurableError: manifest 非法时由 production adapter 抛出。
    """

    return engine_ingest._runner_call_manifest_hot_payload(
        manifest=manifest,
        manifest_payload_ref="payload-manifest-engine",
        manifest_digest=sha256_digest_json(manifest),
    )


def _compactor_hot_payload(
    manifest: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """通过 compactor producer adapter 构造 hot payload。

    :param manifest: synthetic manifest。
    :returns: compactor hot payload。
    :raises HostDurableError: manifest 非法时由 production adapter 抛出。
    """

    compactor_manifest = _compactor_manifest(manifest)
    return compaction_operation._compactor_runner_call_hot_payload(
        manifest=compactor_manifest,
        manifest_payload_ref="payload-manifest-compactor",
        manifest_digest=sha256_digest_json(compactor_manifest),
    )


def _compactor_manifest(
    manifest: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """把完整 synthetic ordinary manifest 改写为完整 compactor manifest。

    :param manifest: 基础 full manifest。
    :returns: 与 compactor producer hot atoms 同源的 full manifest。
    :raises AssertionError: 基础 metadata 不是数组时抛出。
    """

    raw_metadata = manifest["projector_metadata"]
    assert isinstance(raw_metadata, list)
    metadata: list[JsonValue] = []
    for raw_item in raw_metadata:
        assert isinstance(raw_item, Mapping)
        metadata_id = raw_item["projector_metadata_id"]
        assert isinstance(metadata_id, str)
        source_contract_refs: list[JsonValue] = [
            f"contract:compactor:{metadata_id}"
        ]
        projector_id = "compactor_user_prompt"
        schema_version = "compactor_projector.v1"
        purpose = "compactor_proposal_input"
        metadata.append(
            {
                "projector_metadata_id": metadata_id,
                "projector_id": projector_id,
                "projector_schema_version": schema_version,
                "projector_digest": sha256_digest_json(
                    {
                        "projector_id": projector_id,
                        "projector_schema_version": schema_version,
                        "purpose": purpose,
                        "source_contract_refs": source_contract_refs,
                    }
                ),
                "purpose": purpose,
                "source_contract_refs": source_contract_refs,
            }
        )
    value: dict[str, JsonValue] = dict(manifest)
    value.pop("runner_call_projection_artifact_ref")
    value.pop("runner_call_projection_artifact_digest")
    value.pop("runner_call_projection_artifact_size_bytes")
    value["runner_call_kind"] = "compactor_proposal"
    value["runner_call_trigger_reason"] = "context_compaction_initial_proposal"
    value["projector_metadata"] = metadata
    value["compactor_identity"] = {
        "parent_host_run_id": value["host_run_id"],
        "parent_session_id": value["session_id"],
        "compaction_operation_id": "compaction-operation-hot-contract",
        "compactor_engine_run_id": "compactor-engine-run-hot-contract",
        "compaction_attempt_number": 1,
        "compaction_request_digest": sha256_digest_json(
            {"compaction_request": "hot-contract"}
        ),
        "compactor_input_projection_ref": "payload-compactor-input-projection",
    }
    return value


@pytest.mark.parametrize("message_count", _MESSAGE_COUNTS)
def test_runner_call_producers_share_fixed_hot_schema(message_count: int) -> None:
    """ordinary、continuation、compactor 对 0/1/12/300 使用同一 bounded schema。

    :param message_count: synthetic message/projector 数量。
    :returns: ``None``。
    :raises AssertionError: producer 重新复制逐消息数组或 shape 分叉时抛出。
    """

    manifest = _manifest(message_count)
    payloads = (
        _ordinary_hot_payload(manifest),
        _engine_hot_payload(manifest),
        _compactor_hot_payload(manifest),
    )
    for payload in payloads:
        assert frozenset(payload) == _EXPECTED_HOT_FIELDS
        assert "projector_metadata_summary" not in payload
        assert payload["message_count"] == message_count
        assert len(canonical_json_dumps(payload).encode("utf-8")) < 4096
        for value in payload.values():
            assert not isinstance(value, list)


@pytest.mark.parametrize(
    "producer",
    (_ordinary_hot_payload, _engine_hot_payload, _compactor_hot_payload),
)
def test_runner_call_hot_payload_size_does_not_scale_with_message_count(
    producer: Callable[[Mapping[str, JsonValue]], Mapping[str, JsonValue]],
) -> None:
    """逐消息 descriptor 从 0 增至 300 时 hot bytes 只允许数字宽度差异。

    :param producer: 待验证 producer adapter。
    :returns: ``None``。
    :raises AssertionError: hot payload 随逐消息 metadata 线性增长时抛出。
    """

    sizes = tuple(
        len(canonical_json_dumps(producer(_manifest(count))).encode("utf-8"))
        for count in _MESSAGE_COUNTS
    )
    assert max(sizes) - min(sizes) <= 8


def test_projector_metadata_descriptor_keeps_exact_six_fields() -> None:
    """完整 manifest projector metadata 维持六字段且不使用旧 metadata_id。

    :returns: ``None``。
    :raises AssertionError: descriptor 字段缺失、扩散或保留旧字段名时抛出。
    """

    metadata = _manifest(12)["projector_metadata"]
    assert isinstance(metadata, list)
    for item in metadata:
        assert isinstance(item, Mapping)
        assert frozenset(item) == frozenset(
            {
                "projector_metadata_id",
                "projector_id",
                "projector_schema_version",
                "projector_digest",
                "purpose",
                "source_contract_refs",
            }
        )
        assert "metadata_id" not in item


def test_shared_hot_parser_accepts_explicit_complete_diagnostic() -> None:
    """shared owner 接受 producer 写出的显式 complete diagnostic。

    :returns: ``None``。
    :raises AssertionError: typed parser 丢失 complete count/digest 时抛出。
    """

    payload = _ordinary_hot_payload(_manifest(2))
    parsed = parse_runner_call_hot_payload(payload)

    assert parsed.validation_status == "complete"
    assert parsed.diagnostic.status == "complete"
    assert parsed.diagnostic.observed_count == 2
    assert parsed.diagnostic.expected_count == 2
    assert parsed.diagnostic.observed_digest == parsed.role_sequence_digest
    assert parsed.diagnostic.expected_digest == parsed.role_sequence_digest


@pytest.mark.parametrize("tamper_kind", tuple(_HotPayloadTamperKind))
def test_shared_hot_parser_rejects_incomplete_or_conflicting_payload(
    tamper_kind: _HotPayloadTamperKind,
) -> None:
    """缺失/旧 shape/跨字段冲突 hot payload 必须 fail closed。

    :param tamper_kind: 单一 hot contract 篡改分类。
    :returns: ``None``。
    :raises AssertionError: shared owner 接受损坏 hot payload 时抛出。
    """

    payload: dict[str, JsonValue] = dict(_ordinary_hot_payload(_manifest(2)))
    diagnostic_value = payload["diagnostic"]
    assert isinstance(diagnostic_value, Mapping)
    diagnostic: dict[str, JsonValue] = dict(diagnostic_value)
    if tamper_kind is _HotPayloadTamperKind.MISSING_DIAGNOSTIC:
        del payload["diagnostic"]
    elif tamper_kind is _HotPayloadTamperKind.NULL_DIAGNOSTIC:
        payload["diagnostic"] = None
    elif tamper_kind is _HotPayloadTamperKind.MALFORMED_DIAGNOSTIC:
        payload["diagnostic"] = []
    elif tamper_kind is _HotPayloadTamperKind.LEGACY_METADATA_ARRAY:
        payload["projector_metadata_summary"] = []
    elif tamper_kind is _HotPayloadTamperKind.STATUS_MISMATCH:
        payload["validation_status"] = "limited_signal"
    elif tamper_kind is _HotPayloadTamperKind.COUNT_MISMATCH:
        diagnostic["observed_count"] = 3
        payload["diagnostic"] = diagnostic
    else:
        diagnostic["expected_digest"] = sha256_digest_json(
            {"roles": ["tampered"]}
        )
        payload["diagnostic"] = diagnostic

    with pytest.raises(HostDurableError):
        parse_runner_call_hot_payload(payload)
