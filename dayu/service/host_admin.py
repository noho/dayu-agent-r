"""Service 层 Host durable 管理装配边界。

本模块只加载 Host runtime 存储配置并映射为 ``OpenHostAdminOptions``。
它不加载 model、execution profile、runtime lane、tool discovery 或 scene，
也不读取、解析或要求 provider secret。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dayu.host.api import OpenHostAdminOptions
from dayu.runtime.config_loader import ConfigLoader, HostRuntimeProfileConfig
from dayu.runtime.location import resolve_runtime_locations
from dayu.runtime.workspace_paths import resolve_workspace_path


@dataclass(frozen=True, slots=True)
class ServiceHostAdminRequest:
    """Service 装配 HostAdmin opener 的请求。

    :param workspace_root: 当前 workspace 根目录。
    :param package_config_root: 包内默认配置目录。
    :param host_runtime_id: 显式 Host runtime id；``None`` 使用配置默认值。
    """

    workspace_root: Path
    package_config_root: Path
    host_runtime_id: str | None = None

    def __post_init__(self) -> None:
        """校验 admin assembly 请求的路径与可选 id。

        :returns: ``None``。
        :raises TypeError: 路径字段类型非法时抛出。
        :raises ValueError: 显式 Host runtime id 为空时抛出。
        """

        if not isinstance(self.workspace_root, Path):
            raise TypeError("ServiceHostAdminRequest.workspace_root must be Path")
        if not isinstance(self.package_config_root, Path):
            raise TypeError(
                "ServiceHostAdminRequest.package_config_root must be Path"
            )
        if self.host_runtime_id is not None and self.host_runtime_id.strip() == "":
            raise ValueError(
                "ServiceHostAdminRequest.host_runtime_id must be non-empty"
            )


@dataclass(frozen=True, slots=True)
class ServiceHostAdminResult:
    """Service HostAdmin 装配结果。

    :param options: 可直接传给 ``open_host_admin`` 的 typed options。
    :param host_runtime_id: 本次实际选择的 Host runtime id。
    """

    options: OpenHostAdminOptions
    host_runtime_id: str


def prepare_host_admin(request: ServiceHostAdminRequest) -> ServiceHostAdminResult:
    """只从 Host runtime 配置装配纯 durable admin opener。

    :param request: admin assembly 请求。
    :returns: admin opener options 与实际 runtime id。
    :raises RuntimeLocationError: runtime location 依赖的包内资产缺失时抛出。
    :raises ConfigLoadError: Host runtime 配置缺失或字段非法时抛出。
    :raises ValueError: 显式 runtime id 不存在或路径逃逸 workspace 时抛出。
    """

    locations = resolve_runtime_locations(
        workspace_root=request.workspace_root,
        package_config_root=request.package_config_root,
    )
    host_runtime_config = ConfigLoader(
        package_config_dir=request.package_config_root
    ).load_host_runtime(workspace_config_dir=locations.config_overlay_dir)
    host_runtime_id = (
        request.host_runtime_id
        if request.host_runtime_id is not None
        else host_runtime_config.default_host_runtime_id
    )
    try:
        host_runtime = host_runtime_config.runtimes[host_runtime_id]
    except KeyError as exc:
        raise ValueError(f"unknown host runtime id: {host_runtime_id}") from exc
    return ServiceHostAdminResult(
        options=_admin_options_from_runtime(
            workspace_root=request.workspace_root,
            host_runtime=host_runtime,
        ),
        host_runtime_id=host_runtime_id,
    )


def _admin_options_from_runtime(
    *,
    workspace_root: Path,
    host_runtime: HostRuntimeProfileConfig,
) -> OpenHostAdminOptions:
    """把唯一 Host runtime owner 映射为 admin durable options。

    :param workspace_root: 当前 workspace 根目录。
    :param host_runtime: ConfigLoader 产出的 typed Host runtime profile。
    :returns: 不含 execution capability 的 admin options。
    :raises ValueError: 配置路径为空或逃逸 workspace 时抛出。
    """

    return OpenHostAdminOptions(
        db_path=resolve_workspace_path(workspace_root, host_runtime.sqlite.path),
        artifact_root=resolve_workspace_path(
            workspace_root,
            host_runtime.artifact_root,
        ),
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=host_runtime.sqlite.busy_timeout_seconds,
        sqlite_write_busy_retry_count=host_runtime.sqlite.write_busy_retry_count,
        sqlite_write_retry_initial_delay_seconds=(
            host_runtime.sqlite.write_retry_initial_delay_seconds
        ),
        sqlite_write_retry_backoff_multiplier=(
            host_runtime.sqlite.write_retry_backoff_multiplier
        ),
        sqlite_write_retry_max_delay_seconds=(
            host_runtime.sqlite.write_retry_max_delay_seconds
        ),
        payload_inline_threshold_bytes=host_runtime.payload_inline_threshold_bytes,
    )


__all__ = [
    "ServiceHostAdminRequest",
    "ServiceHostAdminResult",
    "prepare_host_admin",
]
