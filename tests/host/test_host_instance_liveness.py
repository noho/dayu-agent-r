"""Host instance liveness primitive 测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dayu.host.dispatch import _new_dispatch_host_instance_identity
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import (
    HostInstanceIdentityConflictError,
    HostInstanceLifecycleConflictError,
    HostInstanceNotRegisteredError,
)
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    HostInstanceStatus,
    heartbeat_current_instance,
    mark_current_instance_stopped,
    mark_current_instance_stopping,
    read_host_instance,
    register_current_instance,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_HOST_INSTANCES
from dayu.host.durable.transaction import (
    HostExecuteResult,
    HostRow,
    HostTransaction,
    SQLParameters,
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


def _identity(
    *,
    host_instance_id: str = "host-instance-1",
    process_start_token: str = "token-1",
    boot_id: str | None = "boot-1",
) -> HostInstanceIdentity:
    """构造测试用 Host instance identity。

    :param host_instance_id: Host instance id。
    :param process_start_token: 进程启动指纹。
    :param boot_id: 可选 boot id。
    :returns: Host instance identity。
    """

    return HostInstanceIdentity(
        host_instance_id=host_instance_id,
        pid=os.getpid(),
        process_start_token=process_start_token,
        boot_id=boot_id,
    )


def _force_instance_status(
    transaction: HostTransaction,
    identity: HostInstanceIdentity,
    status: HostInstanceStatus,
) -> None:
    """测试内直接设置 liveness row 状态。

    :param transaction: Host transaction。
    :param identity: 目标 Host instance identity。
    :param status: 目标状态。
    :returns: ``None``。
    :raises AssertionError: 状态写入未命中唯一 row 时抛出。
    """

    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_INSTANCES}
        SET status = ?
        WHERE host_instance_id = ?
        """,
        (status.value, identity.host_instance_id),
    )
    assert result.rowcount == 1


class _IdentityDriftTransaction(HostTransaction):
    """在 identity precheck 后制造 UPDATE 零命中的测试 transaction。"""

    _delegate: HostTransaction
    _identity: HostInstanceIdentity
    _changed: bool

    def __init__(
        self, delegate: HostTransaction, identity: HostInstanceIdentity
    ) -> None:
        """初始化测试 transaction wrapper。

        :param delegate: 实际 Host transaction。
        :param identity: 需要制造身份漂移的 Host instance identity。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._delegate = delegate
        self._identity = identity
        self._changed = False

    def execute(
        self, sql: str, parameters: SQLParameters = ()
    ) -> HostExecuteResult:
        """执行 SQL，并在第一次 liveness UPDATE 前改写 token。

        :param sql: SQL statement。
        :param parameters: SQLite scalar 参数。
        :returns: 写入摘要。
        :raises Exception: 透传底层 transaction 写入异常。
        """

        if (
            not self._changed
            and f"UPDATE {TABLE_HOST_INSTANCES}" in sql
            and "heartbeat_at" in sql
            and "process_start_token" in sql
        ):
            self._changed = True
            self._delegate.execute(
                f"""
                UPDATE {TABLE_HOST_INSTANCES}
                SET process_start_token = ?
                WHERE host_instance_id = ?
                """,
                ("token-after-precheck", self._identity.host_instance_id),
            )
        return self._delegate.execute(sql, parameters)

    def fetchone(
        self, sql: str, parameters: SQLParameters = ()
    ) -> HostRow | None:
        """委托单行查询。

        :param sql: SQL query。
        :param parameters: SQLite scalar 参数。
        :returns: 查询结果 row；无结果时为 ``None``。
        :raises Exception: 透传底层 transaction 查询异常。
        """

        return self._delegate.fetchone(sql, parameters)


def test_register_inserts_running_instance_with_timestamps(
    tmp_path: Path,
) -> None:
    """register 会插入 running row，并写入 created_at / heartbeat_at。"""

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[HostInstanceStatus, bool]:
            """注册当前 instance。

            :param transaction: Host transaction。
            :returns: status 与 timestamp 是否存在。
            """

            row = register_current_instance(transaction, identity)
            return row.status, row.created_at != "" and row.heartbeat_at != ""

        assert store.transaction_runner.run_write(operation) == (
            HostInstanceStatus.RUNNING,
            True,
        )


def test_repeated_register_same_identity_refreshes_heartbeat_and_status(
    tmp_path: Path,
) -> None:
    """RUNNING 同一 identity 重复 register 会幂等刷新 heartbeat。"""

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:

        def first_operation(transaction: HostTransaction) -> str:
            """首次注册后返回 created_at。

            :param transaction: Host transaction。
            :returns: created_at。
            """

            return register_current_instance(transaction, identity).created_at

        created_at = store.transaction_runner.run_write(first_operation)

        def second_operation(
            transaction: HostTransaction,
        ) -> tuple[str, str, HostInstanceStatus]:
            """重复 register。

            :param transaction: Host transaction。
            :returns: created_at、heartbeat_at 与 status。
            """

            row = register_current_instance(transaction, identity)
            return row.created_at, row.heartbeat_at, row.status

        refreshed_created_at, heartbeat_at, status = store.transaction_runner.run_write(
            second_operation
        )
        assert refreshed_created_at == created_at
        assert heartbeat_at != ""
        assert status is HostInstanceStatus.RUNNING


def test_stopping_instance_register_does_not_revert_to_running(
    tmp_path: Path,
) -> None:
    """STOPPING 不能被 repeated register 回刷为 RUNNING。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )
        store.transaction_runner.run_write(
            lambda transaction: mark_current_instance_stopping(
                transaction, identity
            )
        )

        with pytest.raises(HostInstanceLifecycleConflictError):
            store.transaction_runner.run_write(
                lambda transaction: register_current_instance(transaction, identity)
            )

        row = store.transaction_runner.run_write(
            lambda transaction: read_host_instance(
                transaction, identity.host_instance_id
            )
        )
        assert row is not None
        assert row.status is HostInstanceStatus.STOPPING


@pytest.mark.parametrize(
    "terminal_status",
    (HostInstanceStatus.STOPPED, HostInstanceStatus.CRASHED_SUSPECTED),
)
def test_terminal_instance_does_not_revert_to_running_or_stopping(
    tmp_path: Path, terminal_status: HostInstanceStatus
) -> None:
    """STOPPED / CRASHED_SUSPECTED 不能被 register、heartbeat 或 stopping 复活。

    :param tmp_path: pytest 临时目录。
    :param terminal_status: 被验证的终态状态。
    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )
        store.transaction_runner.run_write(
            lambda transaction: _force_instance_status(
                transaction, identity, terminal_status
            )
        )

        with pytest.raises(HostInstanceLifecycleConflictError):
            store.transaction_runner.run_write(
                lambda transaction: register_current_instance(transaction, identity)
            )
        with pytest.raises(HostInstanceLifecycleConflictError):
            store.transaction_runner.run_write(
                lambda transaction: heartbeat_current_instance(transaction, identity)
            )
        with pytest.raises(HostInstanceLifecycleConflictError):
            store.transaction_runner.run_write(
                lambda transaction: mark_current_instance_stopping(
                    transaction, identity
                )
            )
        with pytest.raises(HostInstanceLifecycleConflictError):
            store.transaction_runner.run_write(
                lambda transaction: mark_current_instance_stopped(
                    transaction, identity
                )
            )

        row = store.transaction_runner.run_write(
            lambda transaction: read_host_instance(
                transaction, identity.host_instance_id
            )
        )
        assert row is not None
        assert row.status is terminal_status


def test_stopping_instance_heartbeat_does_not_revert_to_running(
    tmp_path: Path,
) -> None:
    """STOPPING 不能被自动 heartbeat 静默回退为 RUNNING。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )
        store.transaction_runner.run_write(
            lambda transaction: mark_current_instance_stopping(
                transaction, identity
            )
        )

        with pytest.raises(HostInstanceLifecycleConflictError):
            store.transaction_runner.run_write(
                lambda transaction: heartbeat_current_instance(transaction, identity)
            )

        row = store.transaction_runner.run_write(
            lambda transaction: read_host_instance(
                transaction, identity.host_instance_id
            )
        )
        assert row is not None
        assert row.status is HostInstanceStatus.STOPPING


def test_register_same_id_different_token_raises_identity_conflict(
    tmp_path: Path,
) -> None:
    """同一 host_instance_id 绑定不同 token 时 register 失败。"""

    identity = _identity()
    wrong_identity = _identity(process_start_token="token-2")
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )
        with pytest.raises(HostInstanceIdentityConflictError):
            store.transaction_runner.run_write(
                lambda transaction: register_current_instance(
                    transaction, wrong_identity
                )
            )


def test_heartbeat_updates_only_same_identity(tmp_path: Path) -> None:
    """heartbeat 只刷新相同 host_instance_id 与 process_start_token 的 row。"""

    identity = _identity()
    other_identity = _identity(
        host_instance_id="host-instance-2",
        process_start_token="token-2",
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, other_identity)
        )

        def operation(
            transaction: HostTransaction,
        ) -> tuple[str, str, HostInstanceStatus]:
            """刷新第一个 instance，并读取第二个 instance。

            :param transaction: Host transaction。
            :returns: 第一个 heartbeat、第二个 heartbeat、第二个 status。
            """

            first = heartbeat_current_instance(transaction, identity)
            second = read_host_instance(transaction, other_identity.host_instance_id)
            assert second is not None
            return first.heartbeat_at, second.heartbeat_at, second.status

        first_heartbeat, second_heartbeat, second_status = (
            store.transaction_runner.run_write(operation)
        )
        assert first_heartbeat != ""
        assert second_heartbeat != ""
        assert second_status is HostInstanceStatus.RUNNING


def test_heartbeat_missing_registration_raises(tmp_path: Path) -> None:
    """未注册的当前 instance heartbeat 会结构化失败。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(HostInstanceNotRegisteredError):
            store.transaction_runner.run_write(
                lambda transaction: heartbeat_current_instance(
                    transaction, _identity()
                )
            )


def test_heartbeat_wrong_token_raises_identity_conflict(
    tmp_path: Path,
) -> None:
    """错误 token 不会刷新既有 instance，会抛出 identity conflict。"""

    identity = _identity()
    wrong_identity = _identity(process_start_token="wrong-token")
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )

        def read_heartbeat(transaction: HostTransaction) -> str:
            """读取当前 heartbeat。

            :param transaction: Host transaction。
            :returns: heartbeat_at。
            """

            row = read_host_instance(transaction, identity.host_instance_id)
            assert row is not None
            return row.heartbeat_at

        before = store.transaction_runner.run_write(read_heartbeat)
        with pytest.raises(HostInstanceIdentityConflictError):
            store.transaction_runner.run_write(
                lambda transaction: heartbeat_current_instance(
                    transaction, wrong_identity
                )
            )
        after = store.transaction_runner.run_write(read_heartbeat)
        assert after == before


def test_heartbeat_rowcount_zero_after_identity_precheck_raises_conflict(
    tmp_path: Path,
) -> None:
    """heartbeat identity precheck 后 UPDATE 零命中会作为结构化身份冲突暴露。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )

        def operation(transaction: HostTransaction) -> None:
            """用测试 wrapper 在 heartbeat UPDATE 前制造身份漂移。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostInstanceIdentityConflictError: UPDATE 零命中分类为身份冲突时抛出。
            """

            heartbeat_current_instance(
                _IdentityDriftTransaction(transaction, identity), identity
            )

        with pytest.raises(HostInstanceIdentityConflictError):
            store.transaction_runner.run_write(operation)


def test_status_mark_rowcount_zero_after_identity_precheck_raises_conflict(
    tmp_path: Path,
) -> None:
    """status mark identity precheck 后 UPDATE 零命中会作为结构化身份冲突暴露。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )

        def operation(transaction: HostTransaction) -> None:
            """用测试 wrapper 在 status mark UPDATE 前制造身份漂移。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostInstanceIdentityConflictError: UPDATE 零命中分类为身份冲突时抛出。
            """

            mark_current_instance_stopping(
                _IdentityDriftTransaction(transaction, identity), identity
            )

        with pytest.raises(HostInstanceIdentityConflictError):
            store.transaction_runner.run_write(operation)


def test_register_rowcount_zero_after_identity_precheck_raises_conflict(
    tmp_path: Path,
) -> None:
    """register identity precheck 后 UPDATE 零命中会作为结构化身份冲突暴露。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )

        def operation(transaction: HostTransaction) -> None:
            """用测试 wrapper 在 register UPDATE 前制造身份漂移。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostInstanceIdentityConflictError: UPDATE 零命中分类为身份冲突时抛出。
            """

            register_current_instance(
                _IdentityDriftTransaction(transaction, identity), identity
            )

        with pytest.raises(HostInstanceIdentityConflictError):
            store.transaction_runner.run_write(operation)


def test_liveness_identity_tolerates_missing_boot_id_on_either_side(
    tmp_path: Path,
) -> None:
    """boot_id 任一侧缺失时不拒绝同 pid 与 token 的当前进程。"""

    none_boot_identity = _identity(boot_id=None)
    value_boot_identity = _identity(boot_id="boot-1")
    second_value_identity = _identity(
        host_instance_id="host-instance-2",
        process_start_token="token-2",
        boot_id="boot-2",
    )
    second_none_identity = _identity(
        host_instance_id="host-instance-2",
        process_start_token="token-2",
        boot_id=None,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(
                transaction, none_boot_identity
            )
        )
        none_to_value = store.transaction_runner.run_write(
            lambda transaction: heartbeat_current_instance(
                transaction, value_boot_identity
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(
                transaction, second_value_identity
            )
        )
        value_to_none = store.transaction_runner.run_write(
            lambda transaction: heartbeat_current_instance(
                transaction, second_none_identity
            )
        )
        assert none_to_value.host_instance_id == "host-instance-1"
        assert value_to_none.host_instance_id == "host-instance-2"


def test_liveness_identity_rejects_different_non_empty_boot_id(
    tmp_path: Path,
) -> None:
    """两侧 boot_id 都存在且不同时仍判定身份冲突。"""

    identity = _identity(boot_id="boot-1")
    wrong_boot_identity = _identity(boot_id="boot-2")
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )
        with pytest.raises(HostInstanceIdentityConflictError):
            store.transaction_runner.run_write(
                lambda transaction: heartbeat_current_instance(
                    transaction, wrong_boot_identity
                )
            )


def test_mark_stopping_and_stopped_are_best_effort_when_absent(
    tmp_path: Path,
) -> None:
    """mark stopping / stopped 缺 row 时返回 None，存在时只更新当前 row。"""

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:
        assert (
            store.transaction_runner.run_write(
                lambda transaction: mark_current_instance_stopping(
                    transaction, identity
                )
            )
            is None
        )
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )
        stopping = store.transaction_runner.run_write(
            lambda transaction: mark_current_instance_stopping(transaction, identity)
        )
        stopped = store.transaction_runner.run_write(
            lambda transaction: mark_current_instance_stopped(transaction, identity)
        )
        assert stopping is not None
        assert stopped is not None
        assert stopping.status is HostInstanceStatus.STOPPING
        assert stopped.status is HostInstanceStatus.STOPPED


def test_read_returns_typed_row_and_liveness_is_not_orphan_proof(
    tmp_path: Path,
) -> None:
    """read 返回 typed row；Phase 2 不提供 orphan classifier 语义。"""

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: register_current_instance(transaction, identity)
        )

        def operation(transaction: HostTransaction) -> tuple[str, HostInstanceStatus]:
            """读取 typed liveness row。

            :param transaction: Host transaction。
            :returns: process token 与 status。
            """

            row = read_host_instance(transaction, identity.host_instance_id)
            assert row is not None
            return row.process_start_token, row.status

        assert store.transaction_runner.run_write(operation) == (
            "token-1",
            HostInstanceStatus.RUNNING,
        )


def test_dispatch_host_instance_identity_uses_high_entropy_token() -> None:
    """dispatch Host instance token 独立于 handle id，且不再使用可预测占位。

    :returns: ``None``。
    :raises AssertionError: token 生成回归时由 pytest 抛出。
    """

    first = _new_dispatch_host_instance_identity("host-dispatch-token-test")
    second = _new_dispatch_host_instance_identity("host-dispatch-token-test")
    assert first.host_instance_id == "host-dispatch-token-test"
    assert first.process_start_token != "host-dispatch-token-test"
    assert first.process_start_token != "dispatch-host-dispatch-token-test"
    assert first.process_start_token != second.process_start_token
    assert len(first.process_start_token) == 32
    assert int(first.process_start_token, 16) >= 0
