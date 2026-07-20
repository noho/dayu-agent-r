"""Host durable construction options owner contract 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.host.api import HostCommandHandleOptions
from dayu.host.durable.errors import HostDurableConfigError
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
    project_host_durable_store_options,
)


def _command_options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造每个 durable storage 字段都可区分的 command options。

    :param tmp_path: pytest 临时目录。
    :returns: 可投影为 durable store options 的真实 Host command options。
    :raises Exception: typed options 校验失败时透出。
    """

    return HostCommandHandleOptions(
        host_handle_id="durable-options-owner-test",
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=False,
        sqlite_busy_timeout_seconds=1.25,
        sqlite_write_busy_retry_count=7,
        sqlite_write_retry_initial_delay_seconds=0.02,
        sqlite_write_retry_backoff_multiplier=3.0,
        sqlite_write_retry_max_delay_seconds=0.4,
        payload_inline_threshold_bytes=8192,
        context_window_size=4096,
        reserved_output_tokens=512,
    )


def test_project_host_durable_store_options_maps_every_storage_field(
    tmp_path: Path,
) -> None:
    """断言唯一 projection helper 精确映射全部 durable construction 字段。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises Exception: projection 或断言失败时由 pytest 报告。
    """

    options = _command_options(tmp_path)

    actual = project_host_durable_store_options(options)

    assert actual == HostDurableStoreOptions(
        db_path=options.db_path,
        payload_policy=PayloadStoragePolicy(
            artifact_root=options.artifact_root,
            payload_inline_threshold_bytes=options.payload_inline_threshold_bytes,
            create_artifact_root=options.create_parent_dirs,
        ),
        create_parent_dirs=options.create_parent_dirs,
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
            write_busy_retry_count=options.sqlite_write_busy_retry_count,
            write_retry_initial_delay_seconds=(
                options.sqlite_write_retry_initial_delay_seconds
            ),
            write_retry_backoff_multiplier=(
                options.sqlite_write_retry_backoff_multiplier
            ),
            write_retry_max_delay_seconds=(
                options.sqlite_write_retry_max_delay_seconds
            ),
        ),
    )


def test_sqlite_policy_rejects_non_positive_busy_timeout() -> None:
    """断言 SQLite busy timeout 必须为正数。

    :returns: ``None``。
    :raises Exception: 预期异常未出现或错误消息不匹配时由 pytest 报告。
    """

    with pytest.raises(HostDurableConfigError, match="busy_timeout_seconds"):
        HostSQLiteStoragePolicy(busy_timeout_seconds=0.0)


def test_sqlite_policy_rejects_negative_write_retry_count() -> None:
    """断言 SQLite 写重试次数不得为负数。

    :returns: ``None``。
    :raises Exception: 预期异常未出现或错误消息不匹配时由 pytest 报告。
    """

    with pytest.raises(HostDurableConfigError, match="write_busy_retry_count"):
        HostSQLiteStoragePolicy(write_busy_retry_count=-1)


def test_sqlite_policy_rejects_non_positive_retry_initial_delay() -> None:
    """断言 SQLite 首次重试等待必须为正数。

    :returns: ``None``。
    :raises Exception: 预期异常未出现或错误消息不匹配时由 pytest 报告。
    """

    with pytest.raises(
        HostDurableConfigError,
        match="write_retry_initial_delay_seconds",
    ):
        HostSQLiteStoragePolicy(write_retry_initial_delay_seconds=0.0)


def test_sqlite_policy_rejects_non_positive_retry_multiplier() -> None:
    """断言 SQLite 写重试退避倍率必须为正数。

    :returns: ``None``。
    :raises Exception: 预期异常未出现或错误消息不匹配时由 pytest 报告。
    """

    with pytest.raises(
        HostDurableConfigError,
        match="write_retry_backoff_multiplier",
    ):
        HostSQLiteStoragePolicy(write_retry_backoff_multiplier=0.0)


def test_sqlite_policy_rejects_non_positive_retry_max_delay() -> None:
    """断言 SQLite 单次最大重试等待必须为正数。

    :returns: ``None``。
    :raises Exception: 预期异常未出现或错误消息不匹配时由 pytest 报告。
    """

    with pytest.raises(
        HostDurableConfigError,
        match="write_retry_max_delay_seconds",
    ):
        HostSQLiteStoragePolicy(write_retry_max_delay_seconds=0.0)


def test_payload_policy_rejects_artifact_root_without_name() -> None:
    """断言 payload artifact root 必须包含末级名称。

    :returns: ``None``。
    :raises Exception: 预期异常未出现或错误消息不匹配时由 pytest 报告。
    """

    with pytest.raises(HostDurableConfigError, match="artifact_root"):
        PayloadStoragePolicy(artifact_root=Path("/"))


def test_payload_policy_rejects_non_positive_inline_threshold() -> None:
    """断言 payload inline threshold 必须为正整数。

    :returns: ``None``。
    :raises Exception: 预期异常未出现或错误消息不匹配时由 pytest 报告。
    """

    with pytest.raises(
        HostDurableConfigError,
        match="payload_inline_threshold_bytes",
    ):
        PayloadStoragePolicy(
            artifact_root=Path("artifacts"),
            payload_inline_threshold_bytes=0,
        )


def test_durable_store_options_reject_db_path_without_name() -> None:
    """断言 durable SQLite DB 路径必须包含文件名。

    :returns: ``None``。
    :raises Exception: 预期异常未出现或错误消息不匹配时由 pytest 报告。
    """

    with pytest.raises(HostDurableConfigError, match="db_path"):
        HostDurableStoreOptions(
            db_path=Path("/"),
            payload_policy=PayloadStoragePolicy(artifact_root=Path("artifacts")),
        )
