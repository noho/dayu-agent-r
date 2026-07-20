"""Host canonical ``TOOL_CALL_REQUESTED`` request atom writer。

本模块拥有普通工具接受与等待工具接受共享的 request atom 构造契约。它只把
Host 已接受的精确参数、调用身份和可选业务 query 编码为 append request；
EventLog 的真实序号仍由调用方 append 后取得。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.host.api import HostPayloadRef
from dayu.host.durable.codec import canonical_json_dumps, is_sha256_digest, sha256_digest_json
from dayu.host.durable.errors import HostPayloadReferenceError
from dayu.host.durable.event_log import EventClass, EventLogAppendRequest
from dayu.host.durable.payload import PayloadStore, SQLitePayloadFormat, SQLitePayloadWriteRequest
from dayu.host.durable.schema import (
    PayloadDescriptorKind,
    TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
    TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_PAYLOAD_DESCRIPTOR,
    payload_descriptor_metadata,
)
from dayu.host.durable.transaction import HostTransaction

_EVENT_TYPE_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_TOOL_CALL_REQUEST_EVENT_ACTOR = "host.tool_runtime"
_TOOL_CALL_ARGUMENTS_PAYLOAD_REF_PREFIX = "payload-tool-call-arguments"
_TOOL_CALL_ARGUMENTS_SQLITE_PAYLOAD_ID_PREFIX = "sqlite-payload-tool-call-arguments"
_TOOL_CALL_SEMANTIC_QUERY_PAYLOAD_REF_PREFIX = "payload-tool-call-semantic-query"
_TOOL_CALL_SEMANTIC_QUERY_SQLITE_PAYLOAD_ID_PREFIX = (
    "sqlite-payload-tool-call-semantic-query"
)


class ToolCallRequestEventOrigin(StrEnum):
    """``TOOL_CALL_REQUESTED`` canonical fact 的接受入口。"""

    ORDINARY_ACCEPT = "host.tool_runtime.accept"
    AWAITING_ACCEPT = "host.tool_runtime.awaiting_accept"


@dataclass(frozen=True, slots=True)
class AcceptedToolCallRequestAtomInput:
    """Host 已接受工具调用的 canonical request atom 输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param iteration_id: Engine iteration id。
    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :param tool_schema_digest: 工具 schema digest。
    :param tool_identity_digest: 调用方确定的工具身份 digest。
    :param accepted_arguments: Host 已接受的精确 canonical 参数。
    :param normalized_arguments_digest: 与精确参数同源的 canonical digest。
    :param tool_fact_kind: 本次工具事实类别。
    :param accept_idempotency_key: Host accept 幂等键。
    :param semantic_input_digest: Host accept 语义输入 digest。
    :param semantic_query_text: producer 显式提供的可选业务 query；缺失为
        ``None``。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    iteration_id: str
    tool_call_id: str
    tool_name: str
    tool_schema_digest: str
    tool_identity_digest: str
    accepted_arguments: Mapping[str, JsonValue]
    normalized_arguments_digest: str
    tool_fact_kind: str
    accept_idempotency_key: str
    semantic_input_digest: str
    semantic_query_text: str | None

    def __post_init__(self) -> None:
        """校验 request atom 输入的稳定字段。

        :returns: ``None``。
        :raises ValueError: 必填文本为空、digest 非法或 query 为空白时抛出。
        """

        for field_name, value in (
            ("session_id", self.session_id),
            ("run_id", self.run_id),
            ("attempt_id", self.attempt_id),
            ("execution_id", self.execution_id),
            ("iteration_id", self.iteration_id),
            ("tool_call_id", self.tool_call_id),
            ("tool_name", self.tool_name),
            ("tool_fact_kind", self.tool_fact_kind),
            ("accept_idempotency_key", self.accept_idempotency_key),
        ):
            if value.strip() == "":
                raise ValueError(f"{field_name} must be non-empty")
        for field_name, value in (
            ("tool_schema_digest", self.tool_schema_digest),
            ("tool_identity_digest", self.tool_identity_digest),
            ("normalized_arguments_digest", self.normalized_arguments_digest),
            ("semantic_input_digest", self.semantic_input_digest),
        ):
            if not is_sha256_digest(value):
                raise ValueError(f"{field_name} must be sha256 digest")
        if self.semantic_query_text is not None and self.semantic_query_text.strip() == "":
            raise ValueError("semantic_query_text must be non-empty when present")


@dataclass(frozen=True, slots=True)
class _ToolCallRequestPayloadPlan:
    """request atom 的 bounded payload 与 descriptor 计划。

    :param payload: 写入 EventLog 的 canonical hot payload。
    :param arguments_payload_ref: 大参数 descriptor；inline 时为 ``None``。
    :param semantic_query_payload_ref: 长 query descriptor；缺失或 inline 时为
        ``None``。
    """

    payload: Mapping[str, JsonValue]
    arguments_payload_ref: HostPayloadRef | None
    semantic_query_payload_ref: HostPayloadRef | None


@dataclass(frozen=True, slots=True)
class _SemanticQueryPayloadPlan:
    """可选 semantic query 的冷热存储计划。

    :param storage_kind: query 存储形态。
    :param inline_text: inline query；其它形态为 ``None``。
    :param payload_ref: descriptor 引用；其它形态为 ``None``。
    :param digest: query digest；缺失 query 时为 ``None``。
    """

    storage_kind: str
    inline_text: str | None
    payload_ref: HostPayloadRef | None
    digest: str | None


def build_tool_call_requested_event_request(
    transaction: HostTransaction,
    *,
    atom: AcceptedToolCallRequestAtomInput,
    event_id: str,
    occurred_at: datetime,
    origin: ToolCallRequestEventOrigin,
) -> EventLogAppendRequest:
    """构造共享 ``TOOL_CALL_REQUESTED`` append request。

    本函数不 append EventLog，也不分配或预测 ``event_sequence``。调用方必须
    使用 ``append_event(...).row`` 取得数据库返回的真实 row。

    :param transaction: 当前 Host write transaction。
    :param atom: Host 已接受的 canonical request atom 输入。
    :param event_id: 稳定 EventLog event id。
    :param occurred_at: 事件发生时间。
    :param origin: 普通或 awaiting 接受入口。
    :returns: 可交给 EventLogStore 的 append request。
    :raises ValueError: event id 为空时抛出。
    :raises HostPayloadReferenceError: accepted arguments 与 normalized digest
        不同源时抛出。
    :raises HostDurableError: payload descriptor 写入失败时由 durable store 抛出。
    """

    if event_id.strip() == "":
        raise ValueError("event_id must be non-empty")
    payload_plan = _tool_call_request_payload_plan(
        transaction=transaction,
        atom=atom,
        requested_event_id=event_id,
    )
    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=atom.session_id,
        run_id=atom.run_id,
        attempt_id=atom.attempt_id,
        execution_id=atom.execution_id,
        event_type=_EVENT_TYPE_TOOL_CALL_REQUESTED,
        occurred_at=occurred_at,
        actor=_TOOL_CALL_REQUEST_EVENT_ACTOR,
        source=origin.value,
        client_request_id=None,
        idempotency_key=atom.accept_idempotency_key,
        policy_decision=None,
        reason=None,
        payload_json=payload_plan.payload,
        payload_ref=None,
        payload_digest=None,
    )


def _tool_call_request_payload_plan(
    *,
    transaction: HostTransaction,
    atom: AcceptedToolCallRequestAtomInput,
    requested_event_id: str,
) -> _ToolCallRequestPayloadPlan:
    """准备 request atom 的 exact arguments 与可选 query payload。

    :param transaction: 当前 Host write transaction。
    :param atom: Host 已接受的 request atom 输入。
    :param requested_event_id: 即将写入的 request event id。
    :returns: bounded hot payload 与可选 descriptor 引用。
    :raises HostPayloadReferenceError: accepted arguments digest 不一致时抛出。
    :raises HostDurableError: descriptor 写入失败时由 durable store 抛出。
    """

    arguments_json = _accepted_arguments_json(atom.accepted_arguments)
    arguments_payload_digest = sha256_digest_json(arguments_json)
    if arguments_payload_digest != atom.normalized_arguments_digest:
        raise HostPayloadReferenceError("tool call accepted arguments digest mismatch")
    arguments_size_bytes = _payload_size_bytes(arguments_json)
    arguments_ref: HostPayloadRef | None = None
    arguments_inline_json: JsonValue = None
    arguments_storage_kind = TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON
    if arguments_size_bytes <= transaction.payload_inline_threshold_bytes:
        arguments_inline_json = arguments_json
    else:
        descriptor = PayloadStore().write_sqlite_payload(
            transaction,
            SQLitePayloadWriteRequest(
                payload_ref=_tool_call_arguments_payload_ref(requested_event_id),
                payload_id=_tool_call_arguments_sqlite_payload_id(requested_event_id),
                payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                payload_json=arguments_json,
                media_type="application/json",
                metadata=payload_descriptor_metadata(
                    PayloadDescriptorKind.TOOL_CALL_ARGUMENTS_JSON,
                    {
                        "event_type": _EVENT_TYPE_TOOL_CALL_REQUESTED,
                        "event_id": requested_event_id,
                        "tool_name": atom.tool_name,
                        "tool_call_id": atom.tool_call_id,
                    },
                ),
                expected_digest=arguments_payload_digest,
            ),
        )
        arguments_ref = HostPayloadRef(
            payload_ref=descriptor.payload_ref,
            payload_digest=descriptor.payload_digest,
        )
        arguments_storage_kind = TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR

    semantic_query_plan = _semantic_query_payload_plan(
        transaction=transaction,
        atom=atom,
        requested_event_id=requested_event_id,
    )
    payload: dict[str, JsonValue] = {
        "session_id": atom.session_id,
        "run_id": atom.run_id,
        "attempt_id": atom.attempt_id,
        "execution_id": atom.execution_id,
        "iteration_id": atom.iteration_id,
        "tool_call_id": atom.tool_call_id,
        "tool_name": atom.tool_name,
        "tool_schema_digest": atom.tool_schema_digest,
        "tool_identity_digest": atom.tool_identity_digest,
        "normalized_arguments_digest": atom.normalized_arguments_digest,
        "arguments_json_size_bytes": arguments_size_bytes,
        "arguments_storage_kind": arguments_storage_kind,
        "arguments_inline_json": arguments_inline_json,
        "arguments_payload_ref": (
            arguments_ref.payload_ref if arguments_ref is not None else None
        ),
        "arguments_payload_digest": arguments_payload_digest,
        "tool_fact_kind": atom.tool_fact_kind,
        "accept_idempotency_key": atom.accept_idempotency_key,
        "semantic_input_digest": atom.semantic_input_digest,
        "semantic_query_storage_kind": semantic_query_plan.storage_kind,
        "semantic_query_text": semantic_query_plan.inline_text,
        "semantic_query_payload_ref": (
            semantic_query_plan.payload_ref.payload_ref
            if semantic_query_plan.payload_ref is not None
            else None
        ),
        "semantic_query_digest": semantic_query_plan.digest,
    }
    return _ToolCallRequestPayloadPlan(
        payload=payload,
        arguments_payload_ref=arguments_ref,
        semantic_query_payload_ref=semantic_query_plan.payload_ref,
    )


def _semantic_query_payload_plan(
    *,
    transaction: HostTransaction,
    atom: AcceptedToolCallRequestAtomInput,
    requested_event_id: str,
) -> _SemanticQueryPayloadPlan:
    """准备 producer 显式 query 的 inline 或 descriptor payload。

    :param transaction: 当前 Host write transaction。
    :param atom: Host 已接受的 request atom 输入。
    :param requested_event_id: 即将写入的 request event id。
    :returns: query 冷热存储计划。
    :raises HostDurableError: descriptor 写入失败时由 durable store 抛出。
    """

    query_text = atom.semantic_query_text
    if query_text is None:
        return _SemanticQueryPayloadPlan(
            storage_kind=TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT,
            inline_text=None,
            payload_ref=None,
            digest=None,
        )
    query_json = _semantic_query_json(query_text)
    query_digest = sha256_digest_json(query_json)
    if _payload_size_bytes(query_json) <= transaction.payload_inline_threshold_bytes:
        return _SemanticQueryPayloadPlan(
            storage_kind=TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
            inline_text=query_text,
            payload_ref=None,
            digest=query_digest,
        )
    descriptor = PayloadStore().write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=_tool_call_semantic_query_payload_ref(requested_event_id),
            payload_id=_tool_call_semantic_query_sqlite_payload_id(requested_event_id),
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=query_json,
            media_type="text/plain; charset=utf-8",
            metadata=payload_descriptor_metadata(
                PayloadDescriptorKind.TOOL_CALL_SEMANTIC_QUERY_TEXT,
                {
                    "event_type": _EVENT_TYPE_TOOL_CALL_REQUESTED,
                    "event_id": requested_event_id,
                    "tool_name": atom.tool_name,
                    "tool_call_id": atom.tool_call_id,
                },
            ),
            expected_digest=query_digest,
        ),
    )
    return _SemanticQueryPayloadPlan(
        storage_kind=TOOL_CALL_SEMANTIC_QUERY_STORAGE_PAYLOAD_DESCRIPTOR,
        inline_text=None,
        payload_ref=HostPayloadRef(
            payload_ref=descriptor.payload_ref,
            payload_digest=descriptor.payload_digest,
        ),
        digest=descriptor.payload_digest,
    )


def _accepted_arguments_json(
    arguments: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """构造 exact accepted arguments 的 canonical JSON preimage。

    :param arguments: Host 已接受的精确参数。
    :returns: ``{"arguments": ...}`` canonical object。
    :raises Exception: 不主动抛出异常。
    """

    return {"arguments": dict(arguments)}


def _semantic_query_json(query_text: str) -> Mapping[str, JsonValue]:
    """构造 semantic query descriptor 的 canonical JSON preimage。

    :param query_text: producer 提供的业务 query。
    :returns: query canonical object。
    :raises Exception: 不主动抛出异常。
    """

    return {"semantic_query_text": query_text}


def _payload_size_bytes(payload: Mapping[str, JsonValue]) -> int:
    """计算 canonical JSON 的 UTF-8 字节数。

    :param payload: JSON object。
    :returns: canonical bytes 长度。
    :raises TypeError: payload 不是可编码 JSON 时抛出。
    """

    return len(canonical_json_dumps(payload).encode("utf-8"))


def _tool_call_arguments_payload_ref(requested_event_id: str) -> str:
    """派生 accepted arguments descriptor ref。

    :param requested_event_id: request event id。
    :returns: 稳定 descriptor ref。
    :raises Exception: 不主动抛出异常。
    """

    return f"{_TOOL_CALL_ARGUMENTS_PAYLOAD_REF_PREFIX}-{requested_event_id}"


def _tool_call_arguments_sqlite_payload_id(requested_event_id: str) -> str:
    """派生 accepted arguments SQLite payload id。

    :param requested_event_id: request event id。
    :returns: 稳定 SQLite payload id。
    :raises Exception: 不主动抛出异常。
    """

    return f"{_TOOL_CALL_ARGUMENTS_SQLITE_PAYLOAD_ID_PREFIX}-{requested_event_id}"


def _tool_call_semantic_query_payload_ref(requested_event_id: str) -> str:
    """派生 semantic query descriptor ref。

    :param requested_event_id: request event id。
    :returns: 稳定 descriptor ref。
    :raises Exception: 不主动抛出异常。
    """

    return f"{_TOOL_CALL_SEMANTIC_QUERY_PAYLOAD_REF_PREFIX}-{requested_event_id}"


def _tool_call_semantic_query_sqlite_payload_id(requested_event_id: str) -> str:
    """派生 semantic query SQLite payload id。

    :param requested_event_id: request event id。
    :returns: 稳定 SQLite payload id。
    :raises Exception: 不主动抛出异常。
    """

    return f"{_TOOL_CALL_SEMANTIC_QUERY_SQLITE_PAYLOAD_ID_PREFIX}-{requested_event_id}"
