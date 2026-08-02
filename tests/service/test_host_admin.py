"""Service HostAdmin 纯存储装配测试。"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

from dayu.service.host_admin import (
    ServiceHostAdminRequest,
    prepare_host_admin,
)


def _write_host_runtime(
    config_root: Path,
    *,
    runtime_id: str,
    database_path: str,
) -> None:
    """写入不依赖其它 runtime catalog 的 Host runtime 配置。

    :param config_root: 测试 package config 根目录。
    :param runtime_id: 待写入的 Host runtime id。
    :param database_path: 相对 workspace 的 SQLite 路径。
    :returns: ``None``。
    :raises OSError: 文件写入失败时透传。
    """

    config_root.mkdir(parents=True, exist_ok=True)
    (config_root / "prompts" / "manifests").mkdir(parents=True)
    (config_root / "host_runtime.json").write_text(
        json.dumps(
            {
                "default_host_runtime_id": runtime_id,
                "runtimes": {
                    runtime_id: {
                        "store_root": ".dayu/host",
                        "artifact_root": ".dayu/artifacts",
                        "sqlite": {
                            "path": database_path,
                            "busy_timeout_seconds": 0.25,
                            "write_busy_retry_count": 5,
                            "write_retry_initial_delay_seconds": 0.001,
                            "write_retry_backoff_multiplier": 1.5,
                            "write_retry_max_delay_seconds": 0.02,
                        },
                        "host_execution_lane_name": "unused-admin-lane",
                        "worker_backend": "local",
                        "dispatch_poll_interval_seconds": 0.1,
                        "payload_inline_threshold_bytes": 4096,
                        "worker_startup_timeout_seconds": 1.0,
                        "memory_projection_catch_up_batch_size": 50,
                        "session_event_delivery_policy": {
                            "transient_mailbox_max_items": 512,
                            "max_subscriptions_per_session": 4,
                        },
                        "wait_poller_policy": {
                            "enabled": True,
                            "poll_interval_seconds": 1.0,
                            "claim_ttl_seconds": 60.0,
                            "claim_batch_size": 100,
                            "backoff_initial_delay_seconds": 30.0,
                            "backoff_multiplier": 2.0,
                            "backoff_max_delay_seconds": 300.0,
                            "not_ready_observe_interval_seconds": 1.0,
                            "idle_poll_interval_seconds": 5.0,
                            "adapter_call_timeout_seconds": 30.0,
                            "close_drain_timeout_seconds": 5.0,
                            "max_outstanding_adapter_calls": 8,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets(
    tmp_path: Path,
) -> None:
    """admin assembly 缺少 models/scene/tools/secret 时仍成功。"""

    package_config_root = tmp_path / "package-config"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    _write_host_runtime(
        package_config_root,
        runtime_id="admin-test",
        database_path=".dayu/host/admin.sqlite3",
    )

    result = prepare_host_admin(
        ServiceHostAdminRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root,
        )
    )

    assert result.host_runtime_id == "admin-test"
    assert result.options.db_path == (
        workspace_root / ".dayu/host/admin.sqlite3"
    ).resolve()
    assert result.options.artifact_root == (
        workspace_root / ".dayu/artifacts"
    ).resolve()
    assert result.options.sqlite_busy_timeout_seconds == 0.25
    assert result.options.sqlite_write_busy_retry_count == 5
    assert result.options.sqlite_write_retry_initial_delay_seconds == 0.001
    assert result.options.sqlite_write_retry_backoff_multiplier == 1.5
    assert result.options.sqlite_write_retry_max_delay_seconds == 0.02
    assert result.options.payload_inline_threshold_bytes == 4096
    assert not hasattr(result.options, "worker_factory")
    assert not hasattr(result.options, "lane_name")
    assert not hasattr(result.options, "tooling_options")
    assert not hasattr(result.options, "ordinary_run_baseline")


def test_service_host_admin_request_has_no_config_override_field() -> None:
    """Service admin request 不再承诺显式配置覆盖字段。

    :returns: ``None``。
    :raises AssertionError: request schema 仍含旧字段时抛出。
    """

    field_names = {field.name for field in fields(ServiceHostAdminRequest)}

    assert "config_overlay_dir" not in field_names


def test_prepare_host_admin_uses_workspace_config_when_present(
    tmp_path: Path,
) -> None:
    """admin assembly 必须通过 runtime location owner 使用 workspace config。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: workspace 配置未覆盖 package fallback 时抛出。
    """

    package_config_root = tmp_path / "package-config"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    _write_host_runtime(
        package_config_root,
        runtime_id="package-admin",
        database_path=".dayu/host/package.sqlite3",
    )
    _write_host_runtime(
        workspace_root / "config",
        runtime_id="workspace-admin",
        database_path=".dayu/host/workspace.sqlite3",
    )

    result = prepare_host_admin(
        ServiceHostAdminRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root,
        )
    )

    assert result.host_runtime_id == "workspace-admin"
    assert result.options.db_path == (
        workspace_root / ".dayu/host/workspace.sqlite3"
    ).resolve()
