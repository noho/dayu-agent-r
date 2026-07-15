"""Host durable store 配置类型与 construction 投影。

本模块定义 Host SQLite durable store 与 payload artifact 根目录的显式配置。
本模块同时拥有 Host construction options 到 durable store options 的唯一 typed
投影；它不实现 EventLog、payload descriptor、artifact 写入或 host instance
liveness 行为。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from dayu.host.durable.errors import HostDurableConfigError

_DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0
_DEFAULT_WRITE_BUSY_RETRY_COUNT = 3
_DEFAULT_WRITE_RETRY_INITIAL_DELAY_SECONDS = 0.01
_DEFAULT_WRITE_RETRY_BACKOFF_MULTIPLIER = 2.0
_DEFAULT_WRITE_RETRY_MAX_DELAY_SECONDS = 0.1
_DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES = 65536


class HostDurableStoreOptionsSource(Protocol):
    """Host durable store construction 投影所需的最小 typed 输入。

    Host command、execution opener、admin opener 与诊断脚本可以各自拥有更宽的
    construction options，但 durable owner 只读取这里列出的存储字段。该协议避免
    上层调用方复制嵌套 policy 构造，也不让 durable 层依赖具体 opener 类型。
    """

    @property
    def db_path(self) -> Path:
        """返回 Host durable SQLite DB 路径。

        :returns: durable SQLite DB 路径。
        :raises Exception: 具体实现可在读取失败时抛出。
        """

        ...

    @property
    def artifact_root(self) -> Path:
        """返回 Host payload artifact 根目录。

        :returns: payload artifact 根目录。
        :raises Exception: 具体实现可在读取失败时抛出。
        """

        ...

    @property
    def create_parent_dirs(self) -> bool:
        """返回是否允许创建 durable parent directories。

        :returns: 允许创建时返回 ``True``。
        :raises Exception: 具体实现可在读取失败时抛出。
        """

        ...

    @property
    def sqlite_busy_timeout_seconds(self) -> float:
        """返回 SQLite busy timeout 秒数。

        :returns: SQLite busy timeout 秒数。
        :raises Exception: 具体实现可在读取失败时抛出。
        """

        ...

    @property
    def sqlite_write_busy_retry_count(self) -> int:
        """返回 SQLite 写事务 busy 重试次数。

        :returns: 写事务 busy 重试次数。
        :raises Exception: 具体实现可在读取失败时抛出。
        """

        ...

    @property
    def sqlite_write_retry_initial_delay_seconds(self) -> float:
        """返回 SQLite 首次写重试等待秒数。

        :returns: 首次写重试等待秒数。
        :raises Exception: 具体实现可在读取失败时抛出。
        """

        ...

    @property
    def sqlite_write_retry_backoff_multiplier(self) -> float:
        """返回 SQLite 写重试退避倍率。

        :returns: 写重试退避倍率。
        :raises Exception: 具体实现可在读取失败时抛出。
        """

        ...

    @property
    def sqlite_write_retry_max_delay_seconds(self) -> float:
        """返回 SQLite 单次写重试最大等待秒数。

        :returns: 单次写重试最大等待秒数。
        :raises Exception: 具体实现可在读取失败时抛出。
        """

        ...

    @property
    def payload_inline_threshold_bytes(self) -> int:
        """返回 payload inline 存储阈值。

        :returns: payload inline threshold 字节数。
        :raises Exception: 具体实现可在读取失败时抛出。
        """

        ...


def _require_positive_float(value: float, *, field_name: str) -> None:
    """校验浮点配置值必须为正数。

    :param value: 待校验的浮点配置值。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises HostDurableConfigError: ``value`` 小于或等于零时抛出。
    """

    if value <= 0.0:
        raise HostDurableConfigError(f"{field_name} must be positive")


def _require_positive_int(value: int, *, field_name: str) -> None:
    """校验整数配置值必须为正数。

    :param value: 待校验的整数配置值。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises HostDurableConfigError: ``value`` 小于或等于零时抛出。
    """

    if value <= 0:
        raise HostDurableConfigError(f"{field_name} must be positive")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验整数配置值必须非负。

    :param value: 待校验的整数配置值。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises HostDurableConfigError: ``value`` 小于零时抛出。
    """

    if value < 0:
        raise HostDurableConfigError(f"{field_name} must be non-negative")


def _require_path_has_name(value: Path, *, field_name: str) -> None:
    """校验路径包含最后一级名称。

    :param value: 待校验路径。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises HostDurableConfigError: 路径缺少文件名或目录名时抛出。
    """

    if value.name == "":
        raise HostDurableConfigError(f"{field_name} must include a name")


@dataclass(frozen=True, slots=True)
class HostSQLiteStoragePolicy:
    """Host durable SQLite 存储策略。

    :param busy_timeout_seconds: SQLite busy timeout 秒数。
    :param write_busy_retry_count: ``BEGIN IMMEDIATE`` busy / locked 额外重试次数。
    :param write_retry_initial_delay_seconds: 首次重试前等待秒数。
    :param write_retry_backoff_multiplier: 重试等待退避倍率。
    :param write_retry_max_delay_seconds: 单次重试最大等待秒数。
    """

    busy_timeout_seconds: float = _DEFAULT_BUSY_TIMEOUT_SECONDS
    write_busy_retry_count: int = _DEFAULT_WRITE_BUSY_RETRY_COUNT
    write_retry_initial_delay_seconds: float = (
        _DEFAULT_WRITE_RETRY_INITIAL_DELAY_SECONDS
    )
    write_retry_backoff_multiplier: float = (
        _DEFAULT_WRITE_RETRY_BACKOFF_MULTIPLIER
    )
    write_retry_max_delay_seconds: float = _DEFAULT_WRITE_RETRY_MAX_DELAY_SECONDS

    def __post_init__(self) -> None:
        """校验 SQLite policy 的数值边界。

        :returns: ``None``。
        :raises HostDurableConfigError: 任一配置值越界时抛出。
        """

        _require_positive_float(
            self.busy_timeout_seconds,
            field_name="HostSQLiteStoragePolicy.busy_timeout_seconds",
        )
        _require_non_negative_int(
            self.write_busy_retry_count,
            field_name="HostSQLiteStoragePolicy.write_busy_retry_count",
        )
        _require_positive_float(
            self.write_retry_initial_delay_seconds,
            field_name=(
                "HostSQLiteStoragePolicy.write_retry_initial_delay_seconds"
            ),
        )
        _require_positive_float(
            self.write_retry_backoff_multiplier,
            field_name="HostSQLiteStoragePolicy.write_retry_backoff_multiplier",
        )
        _require_positive_float(
            self.write_retry_max_delay_seconds,
            field_name="HostSQLiteStoragePolicy.write_retry_max_delay_seconds",
        )


@dataclass(frozen=True, slots=True)
class PayloadStoragePolicy:
    """Host payload artifact 存储策略占位。

    :param artifact_root: 调用方显式提供的 artifact 根目录。
    :param payload_inline_threshold_bytes: SQLite inline payload 阈值。
    :param create_artifact_root: 后续 artifact helper 是否可创建根目录。
    """

    artifact_root: Path
    payload_inline_threshold_bytes: int = _DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES
    create_artifact_root: bool = True

    def __post_init__(self) -> None:
        """校验 payload 存储策略。

        :returns: ``None``。
        :raises HostDurableConfigError: artifact 根目录或阈值无效时抛出。
        """

        _require_path_has_name(
            self.artifact_root, field_name="PayloadStoragePolicy.artifact_root"
        )
        _require_positive_int(
            self.payload_inline_threshold_bytes,
            field_name="PayloadStoragePolicy.payload_inline_threshold_bytes",
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class HostDurableStoreOptions:
    """Host durable store 打开选项。

    :param db_path: Host durable SQLite DB 文件路径。
    :param payload_policy: payload artifact 根目录与 inline 阈值策略。
    :param create_parent_dirs: DB parent 目录缺失时是否创建。
    :param sqlite_policy: SQLite busy timeout 与 write retry 策略。
    """

    db_path: Path
    payload_policy: PayloadStoragePolicy
    create_parent_dirs: bool = True
    sqlite_policy: HostSQLiteStoragePolicy = field(
        default_factory=HostSQLiteStoragePolicy
    )

    def __post_init__(self) -> None:
        """校验 durable store 打开选项。

        :returns: ``None``。
        :raises HostDurableConfigError: DB 路径无文件名时抛出。
        """

        _require_path_has_name(
            self.db_path, field_name="HostDurableStoreOptions.db_path"
        )


def project_host_durable_store_options(
    options: HostDurableStoreOptionsSource,
) -> HostDurableStoreOptions:
    """把 Host construction storage 字段投影为 durable store options。

    :param options: 提供完整 Host durable construction 字段的 typed 输入。
    :returns: durable store 与 payload/SQLite policy 的唯一投影结果。
    :raises HostDurableConfigError: 任一 durable 路径或 policy 数值非法时抛出。
    """

    return HostDurableStoreOptions(
        db_path=options.db_path,
        payload_policy=PayloadStoragePolicy(
            artifact_root=options.artifact_root,
            payload_inline_threshold_bytes=(
                options.payload_inline_threshold_bytes
            ),
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
