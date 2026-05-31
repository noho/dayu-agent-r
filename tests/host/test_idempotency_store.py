"""Host durable idempotency primitive 测试。"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import (
    HostDurableError,
    HostForeignKeyError,
    HostIdempotencyConflictError,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    append_event,
)
from dayu.host.durable.idempotency import (
    IdempotencyResultRef,
    IdempotencyScope,
    IdempotencyStore,
    record_idempotent_result,
    read_idempotency_record,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.durable.transaction import HostExecuteResult, HostRow, SQLParameters


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
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.0,
            write_retry_max_delay_seconds=0.001,
        ),
    )


def _scope() -> IdempotencyScope:
    """构造标准幂等作用域。

    :returns: Idempotency scope。
    """

    return IdempotencyScope(
        scope_kind="session_command",
        scope_id="session-1",
        idempotency_key="key-1",
    )


def _result_ref(
    *,
    created_event_id: str | None = None,
    created_event_sequence: int | None = None,
) -> IdempotencyResultRef:
    """构造标准幂等结果引用。

    :param created_event_id: 结果创建的 EventLog 事件标识。
    :param created_event_sequence: 结果创建的 EventLog 全局序号。
    :returns: Idempotency result ref。
    """

    return IdempotencyResultRef(
        result_kind="event",
        result_ref="event-1",
        created_event_id=created_event_id,
        created_event_sequence=created_event_sequence,
    )


def _event_request(event_id: str) -> EventLogAppendRequest:
    """构造 idempotency FK 测试用 EventLog 请求。

    :param event_id: EventLog 事件标识。
    :returns: EventLog append 请求。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-1",
        run_id=None,
        attempt_id=None,
        execution_id=None,
        event_type="host.idempotent",
        occurred_at=datetime(2026, 5, 14, 1, 2, 3, 123456, tzinfo=UTC),
        actor=None,
        source="test",
        client_request_id=None,
        idempotency_key="key-1",
        policy_decision=None,
        reason=None,
        payload_json={"ok": True},
        payload_ref=None,
        payload_digest=None,
    )


def _idempotency_host_row(semantic_input_digest: str) -> HostRow:
    """构造幂等记录查询 row。

    :param semantic_input_digest: row 中保存的 semantic digest。
    :returns: HostRow。
    """

    return HostRow(
        columns=(
            "scope_kind",
            "scope_id",
            "idempotency_key",
            "semantic_input_digest",
            "result_kind",
            "result_ref",
            "created_event_id",
            "created_event_sequence",
            "created_at",
        ),
        values=(
            "session_command",
            "session-1",
            "key-1",
            semantic_input_digest,
            "event",
            "event-existing",
            None,
            None,
            "2026-05-14T01:02:03.123456Z",
        ),
    )


class _IntegrityInterleavingTransaction:
    """模拟 INSERT 前后发生并发唯一约束冲突的 transaction。"""

    def __init__(self, existing_digest: str) -> None:
        """保存冲突后可回读的既有 digest。

        :param existing_digest: 冲突后回读 row 的 semantic digest。
        :returns: ``None``。
        """

        self._existing_digest = existing_digest
        self.fetchone_calls = 0

    def fetchone(
        self, sql: str, parameters: SQLParameters = ()
    ) -> HostRow | None:
        """首次读返回空，冲突后重读返回既有 row。

        :param sql: SQL 文本，本 fake 不解析。
        :param parameters: SQL 参数，本 fake 不解析。
        :returns: 首次为 ``None``，之后为既有幂等 row。
        """

        del sql, parameters
        self.fetchone_calls += 1
        if self.fetchone_calls == 1:
            return None
        return _idempotency_host_row(self._existing_digest)

    def execute(
        self, sql: str, parameters: SQLParameters = ()
    ) -> HostExecuteResult:
        """模拟 INSERT 命中唯一约束。

        :param sql: SQL 文本，本 fake 不解析。
        :param parameters: SQL 参数，本 fake 不解析。
        :returns: 不会返回。
        :raises sqlite3.IntegrityError: 始终抛出唯一约束冲突。
        """

        del sql, parameters
        raise sqlite3.IntegrityError("UNIQUE constraint failed")


def test_first_idempotency_insert_stores_digest_and_result(
    tmp_path: Path,
) -> None:
    """首次幂等记录插入会保存 semantic digest 与 result ref。"""

    digest = sha256_digest_json({"command": "start"})
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[str, str, str]:
            """写入并读取幂等记录。

            :param transaction: Host transaction。
            :returns: digest、result kind、result ref。
            """

            record = record_idempotent_result(
                transaction, _scope(), digest, _result_ref()
            )
            fetched = read_idempotency_record(transaction, _scope())
            assert fetched == record
            return (
                record.semantic_input_digest,
                record.result_kind,
                record.result_ref,
            )

        assert store.transaction_runner.run_write(operation) == (
            digest,
            "event",
            "event-1",
        )


def test_repeat_same_scope_key_and_digest_returns_existing_record(
    tmp_path: Path,
) -> None:
    """相同 scope/key/digest 返回既有记录，不覆盖 result ref。"""

    digest = sha256_digest_json({"command": "start"})
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[str, str]:
            """重复写入同一幂等记录。

            :param transaction: Host transaction。
            :returns: 首次 result ref 与第二次返回 result ref。
            """

            first = record_idempotent_result(
                transaction, _scope(), digest, _result_ref()
            )
            second = record_idempotent_result(
                transaction,
                _scope(),
                digest,
                IdempotencyResultRef(
                    result_kind="event",
                    result_ref="event-other",
                    created_event_id=None,
                    created_event_sequence=None,
                ),
            )
            return first.result_ref, second.result_ref

        assert store.transaction_runner.run_write(operation) == (
            "event-1",
            "event-1",
        )


def test_integrity_error_with_same_digest_returns_concurrent_record() -> None:
    """INSERT 并发唯一冲突后，相同 digest 必须回读并返回既有记录。"""

    digest = sha256_digest_json({"command": "start"})
    transaction = _IntegrityInterleavingTransaction(existing_digest=digest)

    record = record_idempotent_result(
        cast(HostTransaction, transaction),
        _scope(),
        digest,
        _result_ref(),
    )

    assert record.result_ref == "event-existing"
    assert record.semantic_input_digest == digest
    assert transaction.fetchone_calls == 2


def test_integrity_error_with_different_digest_raises_conflict() -> None:
    """INSERT 并发唯一冲突后，不同 digest 必须转为幂等冲突。"""

    first_digest = sha256_digest_json({"command": "start"})
    second_digest = sha256_digest_json({"command": "cancel"})
    transaction = _IntegrityInterleavingTransaction(existing_digest=first_digest)

    with pytest.raises(HostIdempotencyConflictError):
        record_idempotent_result(
            cast(HostTransaction, transaction),
            _scope(),
            second_digest,
            _result_ref(),
        )

    assert transaction.fetchone_calls == 2


def test_idempotency_store_wrapper_methods_delegate_to_functions(
    tmp_path: Path,
) -> None:
    """IdempotencyStore 方法集合会委托 record/read primitive。"""

    digest = sha256_digest_json({"command": "start"})
    idempotency_store = IdempotencyStore()
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[str, str]:
            """通过 IdempotencyStore wrapper 写入并读取记录。

            :param transaction: Host transaction。
            :returns: semantic digest 与 result ref。
            """

            record = idempotency_store.record_idempotent_result(
                transaction, _scope(), digest, _result_ref()
            )
            fetched = idempotency_store.read_idempotency_record(
                transaction, _scope()
            )
            assert fetched == record
            return record.semantic_input_digest, record.result_ref

        assert store.transaction_runner.run_write(operation) == (digest, "event-1")


def test_same_scope_key_different_digest_raises_conflict(
    tmp_path: Path,
) -> None:
    """相同 scope/key 但 semantic digest 不同会抛出幂等冲突。"""

    first_digest = sha256_digest_json({"command": "start"})
    second_digest = sha256_digest_json({"command": "cancel"})
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """触发幂等冲突。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostIdempotencyConflictError: semantic digest 不同时抛出。
            """

            record_idempotent_result(
                transaction, _scope(), first_digest, _result_ref()
            )
            record_idempotent_result(
                transaction, _scope(), second_digest, _result_ref()
            )

        with pytest.raises(HostIdempotencyConflictError):
            store.transaction_runner.run_write(operation)


def test_idempotency_rejects_whitespace_only_text_fields(
    tmp_path: Path,
) -> None:
    """幂等 scope 与 result 文本字段拒绝纯空白字符串。"""

    digest = sha256_digest_json({"command": "start"})
    with open_host_durable_store(_options(tmp_path)) as store:

        def whitespace_scope(transaction: HostTransaction) -> None:
            """触发 scope_kind 纯空白校验失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            record_idempotent_result(
                transaction,
                IdempotencyScope(
                    scope_kind=" \t",
                    scope_id="session-1",
                    idempotency_key="key-1",
                ),
                digest,
                _result_ref(),
            )

        def whitespace_result(transaction: HostTransaction) -> None:
            """触发 result_kind 纯空白校验失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            record_idempotent_result(
                transaction,
                _scope(),
                digest,
                IdempotencyResultRef(
                    result_kind=" \n",
                    result_ref="event-1",
                    created_event_id=None,
                    created_event_sequence=None,
                ),
            )

        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(whitespace_scope)
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(whitespace_result)


def test_idempotency_rejects_one_sided_created_event_ref(
    tmp_path: Path,
) -> None:
    """created_event_id 与 created_event_sequence 必须成对出现。"""

    digest = sha256_digest_json({"command": "start"})
    with open_host_durable_store(_options(tmp_path)) as store:

        def only_event_id(transaction: HostTransaction) -> None:
            """只提供 created_event_id。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            record_idempotent_result(
                transaction,
                _scope(),
                digest,
                _result_ref(
                    created_event_id="event-1",
                    created_event_sequence=None,
                ),
            )

        def only_event_sequence(transaction: HostTransaction) -> None:
            """只提供 created_event_sequence。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            record_idempotent_result(
                transaction,
                _scope(),
                digest,
                _result_ref(
                    created_event_id=None,
                    created_event_sequence=1,
                ),
            )

        for operation in (only_event_id, only_event_sequence):
            with pytest.raises(HostDurableError) as error_info:
                store.transaction_runner.run_write(operation)
            assert str(error_info.value) == (
                "created_event_id and created_event_sequence "
                "must be both set or both unset"
            )


def test_idempotency_conflict_is_not_retried_by_transaction_runner(
    tmp_path: Path,
) -> None:
    """幂等冲突是业务前置条件失败，不会被 transaction runner 重试。"""

    first_digest = sha256_digest_json({"command": "start"})
    second_digest = sha256_digest_json({"command": "cancel"})
    calls: list[str] = []
    with open_host_durable_store(_options(tmp_path)) as store:

        def seed(transaction: HostTransaction) -> None:
            """写入初始幂等记录。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            record_idempotent_result(
                transaction, _scope(), first_digest, _result_ref()
            )

        def conflicting(transaction: HostTransaction) -> None:
            """触发幂等冲突并记录调用次数。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostIdempotencyConflictError: semantic digest 不同时抛出。
            """

            calls.append("called")
            record_idempotent_result(
                transaction, _scope(), second_digest, _result_ref()
            )

        store.transaction_runner.run_write(seed)
        with pytest.raises(HostIdempotencyConflictError):
            store.transaction_runner.run_write(conflicting)
        assert calls == ["called"]


def test_idempotency_record_can_reference_created_event(
    tmp_path: Path,
) -> None:
    """幂等记录可以通过 FK 引用已创建 EventLog event_id 与 event_sequence。"""

    digest = sha256_digest_json({"command": "start"})
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[str | None, int | None]:
            """先创建 EventLog row，再创建引用该事件的幂等记录。

            :param transaction: Host transaction。
            :returns: 幂等记录中的 event id 与 sequence。
            """

            event = append_event(transaction, _event_request("event-1")).row
            record = record_idempotent_result(
                transaction,
                _scope(),
                digest,
                _result_ref(
                    created_event_id=event.event_id,
                    created_event_sequence=event.event_sequence,
                ),
            )
            return record.created_event_id, record.created_event_sequence

        assert store.transaction_runner.run_write(operation) == ("event-1", 1)


def test_idempotency_record_missing_event_fk_raises_structured_error(
    tmp_path: Path,
) -> None:
    """幂等记录引用缺失 EventLog event 会抛出 HostForeignKeyError。"""

    digest = sha256_digest_json({"command": "start"})
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """触发幂等记录 created_event_id FK 失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            record_idempotent_result(
                transaction,
                _scope(),
                digest,
                _result_ref(
                    created_event_id="missing-event",
                    created_event_sequence=1,
                ),
            )

        with pytest.raises(HostForeignKeyError):
            store.transaction_runner.run_write(operation)
