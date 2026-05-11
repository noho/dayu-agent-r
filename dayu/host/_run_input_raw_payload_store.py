"""Host RunInput raw payload durable side-store。

本模块承载 ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` hot fact 的冷 payload
旁路存储。EventLog 只保存 blob 引用、sha256 与 byte size；完整
``input_messages`` / ``tool_schemas`` JSON 只落在本表中。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from dayu.contracts import JsonValue
from dayu.host._host_storage_transaction import HostStorage, HostStorageTransaction

_TABLE_NAME: str = "run_input_raw_payloads"
_KIND_INPUT_MESSAGES: str = "input_messages"
_KIND_TOOL_SCHEMAS: str = "tool_schemas"
_BLOB_ID_SEPARATOR: str = ":"

_DDL: tuple[str, ...] = (
    f"""
    CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
        blob_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        attempt_index INTEGER NOT NULL,
        iteration_index INTEGER NOT NULL,
        iteration_id TEXT NOT NULL,
        payload_kind TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        byte_size INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK (payload_kind IN ('input_messages', 'tool_schemas')),
        UNIQUE (run_id, attempt_index, iteration_index, payload_kind)
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS idx_run_input_raw_payloads_session_run
    ON {_TABLE_NAME} (session_id, run_id)
    """,
)


class RunInputRawPayloadKind(StrEnum):
    """RunInput raw payload 种类。"""

    INPUT_MESSAGES = _KIND_INPUT_MESSAGES
    TOOL_SCHEMAS = _KIND_TOOL_SCHEMAS


class RunInputRawPayloadReadErrorCode(StrEnum):
    """RunInput raw payload 读取校验失败原因。"""

    MISSING_ROW = "missing_row"
    HASH_MISMATCH = "hash_mismatch"
    BYTE_SIZE_MISMATCH = "byte_size_mismatch"
    INVALID_JSON = "invalid_json"
    KIND_MISMATCH = "kind_mismatch"


class RunInputRawPayloadReadError(Exception):
    """RunInput raw payload 读取失败。

    :param code: 失败原因枚举。
    :param blob_id: 触发失败的 blob id。
    :param message: 人类可读诊断。
    """

    def __init__(
        self,
        *,
        code: RunInputRawPayloadReadErrorCode,
        blob_id: str,
        message: str,
    ) -> None:
        """初始化异常。

        :param code: 失败原因枚举。
        :param blob_id: 触发失败的 blob id。
        :param message: 人类可读诊断。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(f"{code.value}: blob_id={blob_id}; {message}")
        self.code = code
        self.blob_id = blob_id


@dataclass(frozen=True, slots=True)
class RunInputRawPayloadRef:
    """RunInput raw payload 引用。

    :param blob_id: payload blob id。
    :param content_sha256: UTF-8 payload JSON 的完整 sha256。
    :param byte_size: UTF-8 payload JSON 字节数。
    """

    blob_id: str
    content_sha256: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class RunInputRawPayloadRefs:
    """两类 RunInput raw payload 引用集合。

    :param input_messages: ``input_messages`` payload 引用。
    :param tool_schemas: ``tool_schemas`` payload 引用。
    """

    input_messages: RunInputRawPayloadRef
    tool_schemas: RunInputRawPayloadRef


@dataclass(frozen=True, slots=True)
class RunInputRawPayloadWriteSet:
    """待写入的 RunInput raw payload 集合。

    :param input_messages_json: model input messages JSON 字符串。
    :param tool_schemas_json: tool schemas JSON 字符串。
    """

    input_messages_json: str
    tool_schemas_json: str


@dataclass(frozen=True, slots=True)
class RunInputRawPayloadRecord:
    """读取并校验后的 RunInput raw payload。

    :param kind: payload 种类。
    :param ref: payload 引用。
    :param payload_json: 原始 JSON 字符串。
    :param parsed_payload: 已解析 JSON，用于证明内容合法。
    """

    kind: RunInputRawPayloadKind
    ref: RunInputRawPayloadRef
    payload_json: str
    parsed_payload: JsonValue


def ensure_run_input_raw_payload_schema(storage: HostStorage) -> None:
    """确保 RunInput raw payload side-store schema 已创建。

    :param storage: Host durable storage。
    :returns: 无返回值。
    :raises sqlite3.DatabaseError: schema 创建失败时抛出。
    """

    storage.apply_schema(_DDL)


def describe_run_input_raw_payloads(
    *,
    run_id: str,
    attempt_index: int,
    iteration_index: int,
    iteration_id: str,
    payloads: RunInputRawPayloadWriteSet,
) -> RunInputRawPayloadRefs:
    """根据 payload 内容派生稳定引用。

    :param run_id: Run id。
    :param attempt_index: Host attempt 序号。
    :param iteration_index: attempt 内 Engine iteration 序号。
    :param iteration_id: Engine iteration id。
    :param payloads: 两类 raw payload JSON。
    :returns: 两类 payload 引用。
    :raises Exception: 不主动抛出异常。
    """

    return RunInputRawPayloadRefs(
        input_messages=_payload_ref(
            run_id=run_id,
            attempt_index=attempt_index,
            iteration_index=iteration_index,
            iteration_id=iteration_id,
            kind=RunInputRawPayloadKind.INPUT_MESSAGES,
            payload_json=payloads.input_messages_json,
        ),
        tool_schemas=_payload_ref(
            run_id=run_id,
            attempt_index=attempt_index,
            iteration_index=iteration_index,
            iteration_id=iteration_id,
            kind=RunInputRawPayloadKind.TOOL_SCHEMAS,
            payload_json=payloads.tool_schemas_json,
        ),
    )


def put_run_input_raw_payloads(
    *,
    tx: HostStorageTransaction,
    session_id: str,
    run_id: str,
    attempt_index: int,
    iteration_index: int,
    iteration_id: str,
    payloads: RunInputRawPayloadWriteSet,
    created_at: datetime,
) -> RunInputRawPayloadRefs:
    """在当前事务内写入两类 RunInput raw payload。

    :param tx: 当前 HostStorage transaction。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :param attempt_index: Host attempt 序号。
    :param iteration_index: attempt 内 Engine iteration 序号。
    :param iteration_id: Engine iteration id。
    :param payloads: 两类 raw payload JSON。
    :param created_at: 创建时间。
    :returns: 两类 payload 引用。
    :raises sqlite3.DatabaseError: SQLite 写入失败时抛出。
    """

    refs = describe_run_input_raw_payloads(
        run_id=run_id,
        attempt_index=attempt_index,
        iteration_index=iteration_index,
        iteration_id=iteration_id,
        payloads=payloads,
    )
    rows = (
        (
            refs.input_messages.blob_id,
            session_id,
            run_id,
            attempt_index,
            iteration_index,
            iteration_id,
            RunInputRawPayloadKind.INPUT_MESSAGES.value,
            refs.input_messages.content_sha256,
            refs.input_messages.byte_size,
            payloads.input_messages_json,
            created_at.isoformat(),
        ),
        (
            refs.tool_schemas.blob_id,
            session_id,
            run_id,
            attempt_index,
            iteration_index,
            iteration_id,
            RunInputRawPayloadKind.TOOL_SCHEMAS.value,
            refs.tool_schemas.content_sha256,
            refs.tool_schemas.byte_size,
            payloads.tool_schemas_json,
            created_at.isoformat(),
        ),
    )
    tx.executemany(
        f"""
        INSERT INTO {_TABLE_NAME} (
            blob_id, session_id, run_id, attempt_index, iteration_index,
            iteration_id, payload_kind, content_sha256, byte_size,
            payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return refs


def get_run_input_raw_payload(
    *,
    storage: HostStorage,
    ref: RunInputRawPayloadRef,
    expected_kind: RunInputRawPayloadKind,
) -> RunInputRawPayloadRecord:
    """读取并校验单个 RunInput raw payload。

    :param storage: Host durable storage。
    :param ref: EventLog hot fact 中保存的 payload 引用。
    :param expected_kind: 调用方期望的 payload kind。
    :returns: 校验后的 payload record。
    :raises RunInputRawPayloadReadError: 缺行、kind 不匹配、hash 不匹配、
        byte size 不匹配或 JSON 非法时抛出。
    :raises sqlite3.DatabaseError: SQLite 读取失败时抛出。
    """

    rows = storage.execute_read(
        f"""
        SELECT payload_kind, content_sha256, byte_size, payload_json
        FROM {_TABLE_NAME}
        WHERE blob_id = ?
        """,
        (ref.blob_id,),
    )
    if not rows:
        raise RunInputRawPayloadReadError(
            code=RunInputRawPayloadReadErrorCode.MISSING_ROW,
            blob_id=ref.blob_id,
            message="raw payload row not found",
        )
    row = rows[0]
    kind = _row_str(row, "payload_kind")
    if kind != expected_kind.value:
        raise RunInputRawPayloadReadError(
            code=RunInputRawPayloadReadErrorCode.KIND_MISMATCH,
            blob_id=ref.blob_id,
            message=f"expected={expected_kind.value} actual={kind}",
        )
    payload_json = _row_str(row, "payload_json")
    actual_sha256 = _sha256(payload_json)
    if actual_sha256 != ref.content_sha256 or _row_str(row, "content_sha256") != ref.content_sha256:
        raise RunInputRawPayloadReadError(
            code=RunInputRawPayloadReadErrorCode.HASH_MISMATCH,
            blob_id=ref.blob_id,
            message="content sha256 mismatch",
        )
    byte_size = _byte_size(payload_json)
    if byte_size != ref.byte_size or _row_int(row, "byte_size") != ref.byte_size:
        raise RunInputRawPayloadReadError(
            code=RunInputRawPayloadReadErrorCode.BYTE_SIZE_MISMATCH,
            blob_id=ref.blob_id,
            message="content byte size mismatch",
        )
    try:
        parsed_raw = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise RunInputRawPayloadReadError(
            code=RunInputRawPayloadReadErrorCode.INVALID_JSON,
            blob_id=ref.blob_id,
            message=str(exc),
        ) from exc
    parsed = cast(JsonValue, parsed_raw)
    return RunInputRawPayloadRecord(
        kind=expected_kind,
        ref=ref,
        payload_json=payload_json,
        parsed_payload=parsed,
    )


def _payload_ref(
    *,
    run_id: str,
    attempt_index: int,
    iteration_index: int,
    iteration_id: str,
    kind: RunInputRawPayloadKind,
    payload_json: str,
) -> RunInputRawPayloadRef:
    """构造单个 payload 引用。

    :param run_id: Run id。
    :param attempt_index: Host attempt 序号。
    :param iteration_index: attempt 内 Engine iteration 序号。
    :param iteration_id: Engine iteration id。
    :param kind: payload kind。
    :param payload_json: payload JSON 字符串。
    :returns: payload 引用。
    :raises Exception: 不主动抛出异常。
    """

    content_sha256 = _sha256(payload_json)
    blob_id = _BLOB_ID_SEPARATOR.join(
        (
            run_id,
            str(attempt_index),
            str(iteration_index),
            iteration_id,
            kind.value,
            content_sha256[:16],
        )
    )
    return RunInputRawPayloadRef(
        blob_id=blob_id,
        content_sha256=content_sha256,
        byte_size=_byte_size(payload_json),
    )


def _sha256(payload_json: str) -> str:
    """计算 payload JSON 的完整 sha256。

    :param payload_json: payload JSON 字符串。
    :returns: 十六进制 sha256。
    :raises Exception: 不主动抛出异常。
    """

    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _byte_size(payload_json: str) -> int:
    """计算 payload JSON 的 UTF-8 字节数。

    :param payload_json: payload JSON 字符串。
    :returns: 字节数。
    :raises Exception: 不主动抛出异常。
    """

    return len(payload_json.encode("utf-8"))


def _row_str(row: sqlite3.Row, key: str) -> str:
    """从 SQLite row 读取字符串列。

    :param row: SQLite row。
    :param key: 列名。
    :returns: 字符串值。
    :raises TypeError: 列值不是字符串时抛出。
    """

    value = row[key]
    if not isinstance(value, str):
        raise TypeError(f"sqlite column {key} must be str")
    return value


def _row_int(row: sqlite3.Row, key: str) -> int:
    """从 SQLite row 读取整数列。

    :param row: SQLite row。
    :param key: 列名。
    :returns: 整数值。
    :raises TypeError: 列值不是整数时抛出。
    """

    value = row[key]
    if not isinstance(value, int):
        raise TypeError(f"sqlite column {key} must be int")
    return value


__all__ = [
    "RunInputRawPayloadKind",
    "RunInputRawPayloadReadError",
    "RunInputRawPayloadReadErrorCode",
    "RunInputRawPayloadRecord",
    "RunInputRawPayloadRef",
    "RunInputRawPayloadRefs",
    "RunInputRawPayloadWriteSet",
    "describe_run_input_raw_payloads",
    "ensure_run_input_raw_payload_schema",
    "get_run_input_raw_payload",
    "put_run_input_raw_payloads",
]
