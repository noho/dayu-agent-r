"""P8.5 RunInput raw payload side-store 单元测试。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from dayu.host._host_storage_transaction import HostStorage
from dayu.host._run_input_raw_payload_store import (
    RunInputRawPayloadKind,
    RunInputRawPayloadReadError,
    RunInputRawPayloadReadErrorCode,
    RunInputRawPayloadRef,
    RunInputRawPayloadWriteSet,
    ensure_run_input_raw_payload_schema,
    get_run_input_raw_payload,
    put_run_input_raw_payloads,
)


async def _write_payloads(storage: HostStorage) -> RunInputRawPayloadRef:
    """写入测试 payload 并返回 input_messages 引用。

    :param storage: HostStorage。
    :returns: input_messages payload 引用。
    :raises Exception: 写入失败时透传。
    """

    async with storage.transaction() as tx:
        refs = put_run_input_raw_payloads(
            tx=tx,
            session_id="s1",
            run_id="r1",
            attempt_index=0,
            iteration_index=0,
            iteration_id="iter-1",
            payloads=RunInputRawPayloadWriteSet(
                input_messages_json='[{"role": "user", "content": "hi"}]',
                tool_schemas_json="[]",
            ),
            created_at=datetime.now(tz=timezone.utc),
        )
    return refs.input_messages


def _memory_storage() -> HostStorage:
    """构造已初始化 schema 的内存 storage。

    :returns: HostStorage。
    :raises Exception: schema 初始化失败时透传。
    """

    storage = HostStorage(database_path=":memory:")
    ensure_run_input_raw_payload_schema(storage)
    return storage


@pytest.mark.asyncio
async def test_get_run_input_raw_payload_round_trip() -> None:
    """写入后可按 ref 读取并校验 JSON。"""

    storage = _memory_storage()
    ref = await _write_payloads(storage)

    record = get_run_input_raw_payload(
        storage=storage,
        ref=ref,
        expected_kind=RunInputRawPayloadKind.INPUT_MESSAGES,
    )

    assert record.ref == ref
    assert record.kind is RunInputRawPayloadKind.INPUT_MESSAGES
    assert record.payload_json == '[{"role": "user", "content": "hi"}]'
    assert record.parsed_payload == [{"role": "user", "content": "hi"}]


def test_get_run_input_raw_payload_missing_row() -> None:
    """缺失 blob row 返回 typed MISSING_ROW。"""

    storage = _memory_storage()
    ref = RunInputRawPayloadRef(
        blob_id="missing",
        content_sha256="0" * 64,
        byte_size=2,
    )

    with pytest.raises(RunInputRawPayloadReadError) as excinfo:
        get_run_input_raw_payload(
            storage=storage,
            ref=ref,
            expected_kind=RunInputRawPayloadKind.INPUT_MESSAGES,
        )
    assert excinfo.value.code is RunInputRawPayloadReadErrorCode.MISSING_ROW


@pytest.mark.asyncio
async def test_get_run_input_raw_payload_rejects_hash_mismatch() -> None:
    """ref sha256 与行内容不一致返回 HASH_MISMATCH。"""

    storage = _memory_storage()
    ref = await _write_payloads(storage)
    bad_ref = RunInputRawPayloadRef(
        blob_id=ref.blob_id,
        content_sha256="0" * 64,
        byte_size=ref.byte_size,
    )

    with pytest.raises(RunInputRawPayloadReadError) as excinfo:
        get_run_input_raw_payload(
            storage=storage,
            ref=bad_ref,
            expected_kind=RunInputRawPayloadKind.INPUT_MESSAGES,
        )
    assert excinfo.value.code is RunInputRawPayloadReadErrorCode.HASH_MISMATCH


@pytest.mark.asyncio
async def test_get_run_input_raw_payload_rejects_byte_size_mismatch() -> None:
    """ref byte_size 与行内容不一致返回 BYTE_SIZE_MISMATCH。"""

    storage = _memory_storage()
    ref = await _write_payloads(storage)
    bad_ref = RunInputRawPayloadRef(
        blob_id=ref.blob_id,
        content_sha256=ref.content_sha256,
        byte_size=ref.byte_size + 1,
    )

    with pytest.raises(RunInputRawPayloadReadError) as excinfo:
        get_run_input_raw_payload(
            storage=storage,
            ref=bad_ref,
            expected_kind=RunInputRawPayloadKind.INPUT_MESSAGES,
        )
    assert excinfo.value.code is RunInputRawPayloadReadErrorCode.BYTE_SIZE_MISMATCH


@pytest.mark.asyncio
async def test_get_run_input_raw_payload_rejects_kind_mismatch() -> None:
    """期望 kind 与行内 kind 不一致返回 KIND_MISMATCH。"""

    storage = _memory_storage()
    ref = await _write_payloads(storage)

    with pytest.raises(RunInputRawPayloadReadError) as excinfo:
        get_run_input_raw_payload(
            storage=storage,
            ref=ref,
            expected_kind=RunInputRawPayloadKind.TOOL_SCHEMAS,
        )
    assert excinfo.value.code is RunInputRawPayloadReadErrorCode.KIND_MISMATCH


@pytest.mark.asyncio
async def test_get_run_input_raw_payload_rejects_invalid_json() -> None:
    """行内 payload_json 非法返回 INVALID_JSON。"""

    storage = _memory_storage()
    ref = await _write_payloads(storage)
    invalid = "{"
    invalid_sha256 = hashlib.sha256(invalid.encode("utf-8")).hexdigest()
    async with storage.transaction() as tx:
        tx.execute(
            """
            UPDATE run_input_raw_payloads
            SET payload_json = ?, content_sha256 = ?, byte_size = ?
            WHERE blob_id = ?
            """,
            (
                invalid,
                invalid_sha256,
                len(invalid.encode("utf-8")),
                ref.blob_id,
            ),
        )
    invalid_ref = RunInputRawPayloadRef(
        blob_id=ref.blob_id,
        content_sha256=invalid_sha256,
        byte_size=len(invalid.encode("utf-8")),
    )

    with pytest.raises(RunInputRawPayloadReadError) as excinfo:
        get_run_input_raw_payload(
            storage=storage,
            ref=invalid_ref,
            expected_kind=RunInputRawPayloadKind.INPUT_MESSAGES,
        )
    assert excinfo.value.code is RunInputRawPayloadReadErrorCode.INVALID_JSON
