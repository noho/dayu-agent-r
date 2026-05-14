"""Host Phase 3 Session lifecycle 与 slot binding 测试。"""

from __future__ import annotations

from multiprocessing import Process
from pathlib import Path

import pytest

from dayu.host.api import (
    AuthorizationClaim,
    CloseSessionRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostMetadataEntry,
    OperationContext,
    SessionStatus,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_SESSIONS,
    TABLE_HOST_SESSION_SLOTS,
)
from dayu.host.durable.session_lifecycle import (
    close_session,
    create_session,
    ensure_session,
)
from dayu.host.durable.state import read_session_by_id, read_session_slot
from dayu.host.durable.transaction import HostRow, HostTransaction

_PROCESS_COUNT = 6


def _options(
    db_path: Path,
    artifact_root: Path,
    *,
    busy_timeout_seconds: float = 1.0,
) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :param busy_timeout_seconds: SQLite busy timeout 秒数。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=db_path,
        payload_policy=PayloadStoragePolicy(artifact_root=artifact_root),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=busy_timeout_seconds,
            write_busy_retry_count=20,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _tmp_options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造单进程测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return _options(tmp_path / "durable.sqlite3", tmp_path / "artifacts")


def _context(request_id: str = "request-trace-1") -> HostCallContext:
    """构造标准 Host call context。

    :param request_id: tracing request id。
    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=request_id,
        authorization_claims=(
            AuthorizationClaim(name="role", value="research"),
        ),
        operation_context=OperationContext(
            operation_name="session_lifecycle_test",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase3",
            correlation_id="corr-1",
        ),
    )


def _metadata(value: str) -> tuple[HostMetadataEntry, ...]:
    """构造测试 metadata。

    :param value: metadata 值。
    :returns: Host metadata entries。
    """

    return (HostMetadataEntry(key="case", value=value),)


def _caller_digest(value: str) -> str:
    """构造调用方 semantic digest。

    :param value: digest 输入值。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json({"caller": value})


def _ensure_request(metadata_value: str = "initial") -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :param metadata_value: metadata 值。
    :returns: ensure session 请求。
    """

    return EnsureSessionRequest(
        scope="workspace",
        slot_key="slot-a",
        metadata=_metadata(metadata_value),
    )


def _create_request(
    client_request_id: str,
    *,
    bind_slot: bool,
    metadata_value: str = "create",
) -> CreateSessionRequest:
    """构造 create session 请求。

    :param client_request_id: 客户端幂等请求 id。
    :param bind_slot: 是否绑定 slot。
    :param metadata_value: metadata 值。
    :returns: create session 请求。
    """

    return CreateSessionRequest(
        context=_context(),
        client_request_id=client_request_id,
        bind_slot=bind_slot,
        scope="workspace" if bind_slot else None,
        slot_key="slot-a" if bind_slot else None,
        metadata=_metadata(metadata_value),
    )


def _close_request(
    client_request_id: str, *, reason: str = "done"
) -> CloseSessionRequest:
    """构造 close session 请求。

    :param client_request_id: 客户端幂等请求 id。
    :param reason: 关闭原因。
    :returns: close session 请求。
    """

    return CloseSessionRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason=reason,
    )


def _count_rows(
    transaction: HostTransaction, *, table_name: str, where_sql: str = ""
) -> int:
    """读取指定表的 row count。

    :param transaction: Host transaction。
    :param table_name: 表名。
    :param where_sql: 可选 WHERE 子句。
    :returns: row count。
    :raises AssertionError: SQLite 未返回整数 count 时抛出。
    """

    row = transaction.fetchone(
        f"SELECT COUNT(*) AS total FROM {table_name} {where_sql}"
    )
    assert row is not None
    return _required_int(row, "total")


def _required_int(row: HostRow, column: str) -> int:
    """从 HostRow 读取必填整数。

    :param row: Host row。
    :param column: 列名。
    :returns: 整数值。
    :raises AssertionError: 列值不是整数时抛出。
    """

    value = row.get(column)
    assert isinstance(value, int)
    return value


def test_ensure_session_creates_open_session_and_slot(tmp_path: Path) -> None:
    """slot 缺失时 ensure_session 创建 open Session 与 slot binding。"""

    with open_host_durable_store(_tmp_options(tmp_path)) as store:
        result = ensure_session(store.transaction_runner, _ensure_request())

        assert result.created is True
        assert result.rebound_slot is True
        assert result.snapshot.status == SessionStatus.OPEN
        assert result.snapshot.slot is not None
        assert result.snapshot.slot.scope == "workspace"
        assert result.snapshot.slot.slot_key == "slot-a"
        assert result.snapshot.active_run_id is None
        assert result.snapshot.queued_run_ids == ()

        def operation(transaction: HostTransaction) -> tuple[int, int, int]:
            """读取 Session、slot 与 EventLog row 数。

            :param transaction: Host transaction。
            :returns: sessions、slots、created events 数。
            """

            session = read_session_by_id(
                transaction, result.snapshot.session_id
            )
            slot = read_session_slot(transaction, "workspace", "slot-a")
            assert session is not None
            assert slot is not None
            assert slot.session_id == result.snapshot.session_id
            return (
                _count_rows(transaction, table_name=TABLE_HOST_SESSIONS),
                _count_rows(transaction, table_name=TABLE_HOST_SESSION_SLOTS),
                _count_event_type(transaction, "SESSION_CREATED"),
            )

        assert store.transaction_runner.run_write(operation) == (1, 1, 1)


def test_repeated_ensure_session_ignores_metadata_changes(
    tmp_path: Path,
) -> None:
    """重复 ensure_session 只以 slot PK 为幂等真源，不因 metadata 改变冲突。"""

    with open_host_durable_store(_tmp_options(tmp_path)) as store:
        first = ensure_session(
            store.transaction_runner, _ensure_request("first")
        )
        second = ensure_session(
            store.transaction_runner, _ensure_request("second")
        )

        assert second.snapshot.session_id == first.snapshot.session_id
        assert second.created is False
        assert second.idempotent_replay is False

        def operation(transaction: HostTransaction) -> tuple[int, int, int]:
            """读取 Session、slot、idempotency row 数。

            :param transaction: Host transaction。
            :returns: sessions、slots、idempotency rows 数。
            """

            return (
                _count_rows(transaction, table_name=TABLE_HOST_SESSIONS),
                _count_rows(transaction, table_name=TABLE_HOST_SESSION_SLOTS),
                _count_rows(transaction, table_name="idempotency_records"),
            )

        assert store.transaction_runner.run_write(operation) == (1, 1, 0)


def test_concurrent_same_slot_ensure_session_returns_one_bound_session(
    tmp_path: Path,
) -> None:
    """并发 ensure_session 同一 slot 时只留下一个可见绑定 Session。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    result_dir = tmp_path / "worker-results"
    result_dir.mkdir()
    with open_host_durable_store(_options(db_path, artifact_root)):
        pass

    processes = tuple(
        Process(
            target=_ensure_worker,
            args=(
                str(db_path),
                str(artifact_root),
                str(result_dir),
                worker_index,
            ),
        )
        for worker_index in range(_PROCESS_COUNT)
    )
    for process in processes:
        process.start()
    for process in processes:
        process.join()
        assert process.exitcode == 0

    session_ids = tuple(
        (result_dir / f"worker-{index}.txt").read_text(encoding="utf-8")
        for index in range(_PROCESS_COUNT)
    )
    assert len(frozenset(session_ids)) == 1

    with open_host_durable_store(_options(db_path, artifact_root)) as store:

        def operation(transaction: HostTransaction) -> tuple[int, int, str]:
            """读取并发 ensure 后的 durable binding。

            :param transaction: Host transaction。
            :returns: Session row 数、slot row 数、slot 绑定 Session id。
            """

            slot = read_session_slot(transaction, "workspace", "slot-a")
            assert slot is not None
            return (
                _count_rows(transaction, table_name=TABLE_HOST_SESSIONS),
                _count_rows(transaction, table_name=TABLE_HOST_SESSION_SLOTS),
                slot.session_id,
            )

        session_count, slot_count, bound_session_id = (
            store.transaction_runner.run_write(operation)
        )
        assert session_count == 1
        assert slot_count == 1
        assert bound_session_id == session_ids[0]


def test_create_session_without_slot_retries_by_client_request_id(
    tmp_path: Path,
) -> None:
    """create_session 不绑定 slot 时，同 client_request_id 返回同一 Session。"""

    digest = _caller_digest("create")
    with open_host_durable_store(_tmp_options(tmp_path)) as store:
        first = create_session(
            store.transaction_runner,
            _create_request("create-1", bind_slot=False),
            caller_semantic_digest=digest,
        )
        second = create_session(
            store.transaction_runner,
            _create_request("create-1", bind_slot=False),
            caller_semantic_digest=digest,
        )

        assert second.snapshot.session_id == first.snapshot.session_id
        assert first.snapshot.slot is None
        assert second.idempotent_replay is True

        def operation(transaction: HostTransaction) -> tuple[int, int, int]:
            """读取 Session、slot、created event row 数。

            :param transaction: Host transaction。
            :returns: sessions、slots、created events 数。
            """

            return (
                _count_rows(transaction, table_name=TABLE_HOST_SESSIONS),
                _count_rows(transaction, table_name=TABLE_HOST_SESSION_SLOTS),
                _count_event_type(transaction, "SESSION_CREATED"),
            )

        assert store.transaction_runner.run_write(operation) == (1, 0, 1)


def test_create_session_with_slot_rebinds_without_closing_old_session(
    tmp_path: Path,
) -> None:
    """create_session(bind_slot=true) 原子重绑定 slot，旧 Session 保持 open。"""

    with open_host_durable_store(_tmp_options(tmp_path)) as store:
        first = ensure_session(store.transaction_runner, _ensure_request())
        second = create_session(
            store.transaction_runner,
            _create_request("create-rebind", bind_slot=True),
            caller_semantic_digest=_caller_digest("rebind"),
        )

        assert second.snapshot.session_id != first.snapshot.session_id
        assert second.snapshot.slot is not None
        assert second.snapshot.slot.scope == "workspace"
        assert second.snapshot.slot.slot_key == "slot-a"

        def operation(transaction: HostTransaction) -> tuple[str, SessionStatus]:
            """读取 slot 新绑定和旧 Session 状态。

            :param transaction: Host transaction。
            :returns: slot 绑定 id 与旧 Session 状态。
            """

            slot = read_session_slot(transaction, "workspace", "slot-a")
            old_session = read_session_by_id(
                transaction, first.snapshot.session_id
            )
            assert slot is not None
            assert old_session is not None
            return slot.session_id, old_session.status

        assert store.transaction_runner.run_write(operation) == (
            second.snapshot.session_id,
            SessionStatus.OPEN,
        )


def test_create_session_idempotency_conflict_on_changed_digest(
    tmp_path: Path,
) -> None:
    """create_session 同 key 不同 semantic digest 返回 idempotency conflict。"""

    with open_host_durable_store(_tmp_options(tmp_path)) as store:
        create_session(
            store.transaction_runner,
            _create_request("create-conflict", bind_slot=False),
            caller_semantic_digest=_caller_digest("create"),
        )

        with pytest.raises(HostApiError) as exc_info:
            create_session(
                store.transaction_runner,
                _create_request(
                    "create-conflict",
                    bind_slot=False,
                    metadata_value="changed",
                ),
                caller_semantic_digest=_caller_digest("create"),
            )

        assert exc_info.value.code == HostApiErrorCode.IDEMPOTENCY_CONFLICT


def test_create_session_idempotency_conflict_on_changed_bind_slot(
    tmp_path: Path,
) -> None:
    """create_session 同 key 改变 bind_slot 返回 idempotency conflict。"""

    digest = _caller_digest("create-bind-slot")
    with open_host_durable_store(_tmp_options(tmp_path)) as store:
        create_session(
            store.transaction_runner,
            _create_request("create-bind-slot-conflict", bind_slot=False),
            caller_semantic_digest=digest,
        )

        with pytest.raises(HostApiError) as exc_info:
            create_session(
                store.transaction_runner,
                _create_request("create-bind-slot-conflict", bind_slot=True),
                caller_semantic_digest=digest,
            )

        assert exc_info.value.code == HostApiErrorCode.IDEMPOTENCY_CONFLICT

        def operation(transaction: HostTransaction) -> tuple[int, int, int]:
            """读取 conflict 后的 Session、slot 与创建事件数量。

            :param transaction: Host transaction。
            :returns: sessions、slots、created events 数。
            """

            return (
                _count_rows(transaction, table_name=TABLE_HOST_SESSIONS),
                _count_rows(transaction, table_name=TABLE_HOST_SESSION_SLOTS),
                _count_event_type(transaction, "SESSION_CREATED"),
            )

        assert store.transaction_runner.run_write(operation) == (1, 0, 1)


def test_close_session_closes_once_and_retry_returns_closed_snapshot(
    tmp_path: Path,
) -> None:
    """close_session 写入 CLOSED 和 SESSION_CLOSED，重复同 digest 返回既有快照。"""

    with open_host_durable_store(_tmp_options(tmp_path)) as store:
        created = create_session(
            store.transaction_runner,
            _create_request("create-close", bind_slot=False),
            caller_semantic_digest=_caller_digest("create-close"),
        )
        closed = close_session(
            store.transaction_runner,
            created.snapshot.session_id,
            _close_request("close-1"),
            caller_semantic_digest=_caller_digest("close"),
        )
        retried = close_session(
            store.transaction_runner,
            created.snapshot.session_id,
            _close_request("close-1"),
            caller_semantic_digest=_caller_digest("close"),
        )

        assert closed.closed is True
        assert closed.snapshot.status == SessionStatus.CLOSED
        assert retried.idempotent_replay is True
        assert retried.snapshot.session_id == created.snapshot.session_id
        assert retried.snapshot.status == SessionStatus.CLOSED

        def operation(transaction: HostTransaction) -> tuple[int, int]:
            """读取 closed Session row 与 SESSION_CLOSED 事件数量。

            :param transaction: Host transaction。
            :returns: closed sessions 数与 close 事件数。
            """

            return (
                _count_rows(
                    transaction,
                    table_name=TABLE_HOST_SESSIONS,
                    where_sql="WHERE status = 'closed'",
                ),
                _count_event_type(transaction, "SESSION_CLOSED"),
            )

        assert store.transaction_runner.run_write(operation) == (1, 1)


def test_close_session_idempotency_conflict_on_changed_digest(
    tmp_path: Path,
) -> None:
    """close_session 同 key 不同 reason 或 digest 返回 idempotency conflict。"""

    with open_host_durable_store(_tmp_options(tmp_path)) as store:
        created = create_session(
            store.transaction_runner,
            _create_request("create-close-conflict", bind_slot=False),
            caller_semantic_digest=_caller_digest("create-close-conflict"),
        )
        close_session(
            store.transaction_runner,
            created.snapshot.session_id,
            _close_request("close-conflict", reason="done"),
            caller_semantic_digest=_caller_digest("close"),
        )

        with pytest.raises(HostApiError) as exc_info:
            close_session(
                store.transaction_runner,
                created.snapshot.session_id,
                _close_request("close-conflict", reason="changed"),
                caller_semantic_digest=_caller_digest("close"),
            )

        assert exc_info.value.code == HostApiErrorCode.IDEMPOTENCY_CONFLICT


def _count_event_type(transaction: HostTransaction, event_type: str) -> int:
    """读取指定 EventLog event_type 的 row count。

    :param transaction: Host transaction。
    :param event_type: EventLog event type。
    :returns: row count。
    """

    row = transaction.fetchone(
        f"""
        SELECT COUNT(*) AS total
        FROM {TABLE_EVENT_LOG}
        WHERE event_type = ?
        """,
        (event_type,),
    )
    assert row is not None
    return _required_int(row, "total")


def _ensure_worker(
    db_path_text: str,
    artifact_root_text: str,
    result_dir_text: str,
    worker_index: int,
) -> None:
    """多进程 ensure worker。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param result_dir_text: 结果目录文本。
    :param worker_index: worker 序号。
    :returns: ``None``。
    """

    options = _options(Path(db_path_text), Path(artifact_root_text))
    with open_host_durable_store(options) as store:
        result = ensure_session(
            store.transaction_runner,
            _ensure_request(f"worker-{worker_index}"),
        )
        result_path = Path(result_dir_text) / f"worker-{worker_index}.txt"
        result_path.write_text(result.snapshot.session_id, encoding="utf-8")
