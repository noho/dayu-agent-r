"""Service HostAdmin 纯存储装配测试。"""

from __future__ import annotations

import json
from pathlib import Path

from dayu.service.host_admin import (
    ServiceHostAdminRequest,
    prepare_host_admin,
)


def _write_host_runtime(config_root: Path) -> None:
    """写入不依赖其它 runtime catalog 的 Host runtime 配置。

    :param config_root: 测试 package config 根目录。
    :returns: ``None``。
    :raises OSError: 文件写入失败时透传。
    """

    config_root.mkdir(parents=True, exist_ok=True)
    (config_root / "host_runtime.json").write_text(
        json.dumps(
            {
                "default_host_runtime_id": "admin-test",
                "runtimes": {
                    "admin-test": {
                        "store_root": ".dayu/host",
                        "artifact_root": ".dayu/artifacts",
                        "sqlite": {
                            "path": ".dayu/host/admin.sqlite3",
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
    _write_host_runtime(package_config_root)

    result = prepare_host_admin(
        ServiceHostAdminRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root,
            config_overlay_dir=None,
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
