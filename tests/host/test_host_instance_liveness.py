"""Host instance liveness primitive 测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import (
    HostInstanceIdentityConflictError,
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
from dayu.host.durable.transaction import HostTransaction


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
    """同一 identity 重复 register 会幂等刷新 heartbeat 与 running status。"""

    identity = _identity()
    with open_host_durable_store(_options(tmp_path)) as store:

        def first_operation(transaction: HostTransaction) -> str:
            """首次注册后返回 created_at。

            :param transaction: Host transaction。
            :returns: created_at。
            """

            return register_current_instance(transaction, identity).created_at

        created_at = store.transaction_runner.run_write(first_operation)

        def mark_operation(transaction: HostTransaction) -> HostInstanceStatus | None:
            """先标记 stopping。

            :param transaction: Host transaction。
            :returns: 更新后的 status。
            """

            row = mark_current_instance_stopping(transaction, identity)
            return None if row is None else row.status

        assert (
            store.transaction_runner.run_write(mark_operation)
            is HostInstanceStatus.STOPPING
        )

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
