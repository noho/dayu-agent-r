"""跨进程具名容量 lane 协调器。

本模块提供层中立的 async named semaphore / capacity guard primitive。
它只表达运行期资源容量 claim，不表达 Host durable truth、lease /
fencing、Attempt owner、EventLog ordering、admission 或 recovery proof。
第一版使用独立 SQLite runtime lane DB 做跨进程原子 claim。
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Final, TypeAlias, cast

from dayu.contracts.cancellation import CancellationToken

_DEFAULT_CLAIM_TTL_SECONDS: Final[float] = 30.0
_DEFAULT_HEARTBEAT_INTERVAL_SECONDS: Final[float] = 10.0
_DEFAULT_BUSY_TIMEOUT_SECONDS: Final[float] = 5.0
_DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 0.05
_SQLITE_MILLISECONDS_PER_SECOND: Final[int] = 1000
_CLAIM_ID_BYTES: Final[int] = 16
_OWNER_ID_BYTES: Final[int] = 8
_CLAIMS_TABLE: Final[str] = "runtime_lane_claims"


class RuntimeLaneError(Exception):
    """runtime lane 基础异常。

    所有 lane 运行期错误都派生自本异常，便于调用方只捕获 runtime lane
    语义错误。
    """


class RuntimeLaneConfigError(RuntimeLaneError):
    """runtime lane 配置错误。

    配置错误包括重复 lane name、非法容量、非法 TTL / heartbeat、未知
    lane name、缺失 DB parent directory 等。
    """


class RuntimeLaneClosedError(RuntimeLaneError):
    """已关闭 controller 上的新 acquire 请求错误。"""


class RuntimeLaneClaimLostError(RuntimeLaneError):
    """claim 已丢失或已过期错误。

    当 heartbeat / refresh 无法按 ``lane_name + claim_id + owner_id`` 找到
    仍未过期的 claim 时抛出。
    """


@dataclass(frozen=True, slots=True)
class LaneConfig:
    """单个具名 lane 的容量与 claim 生命周期配置。

    :param name: lane 名称，必须为非空字符串。
    :param capacity: lane 容量，必须为正整数。
    :param default_timeout_seconds: acquire 未显式传入 timeout 时使用的默认
        timeout；``None`` 表示无限等待。
    :param claim_ttl_seconds: claim 过期秒数，必须大于 heartbeat 间隔。
    :param heartbeat_interval_seconds: heartbeat 刷新间隔秒数，必须为正数。
    :raises RuntimeLaneConfigError: 配置字段非法时抛出。
    """

    name: str
    capacity: int
    default_timeout_seconds: float | None = None
    claim_ttl_seconds: float = _DEFAULT_CLAIM_TTL_SECONDS
    heartbeat_interval_seconds: float = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        """校验 lane 配置。

        :returns: ``None``。
        :raises RuntimeLaneConfigError: 任一配置字段非法时抛出。
        """

        _require_non_blank(self.name, field_name="LaneConfig.name")
        if self.capacity <= 0:
            raise RuntimeLaneConfigError("LaneConfig.capacity 必须为正整数")
        if (
            self.default_timeout_seconds is not None
            and self.default_timeout_seconds < 0
        ):
            raise RuntimeLaneConfigError(
                "LaneConfig.default_timeout_seconds 不能为负数"
            )
        if self.claim_ttl_seconds <= 0:
            raise RuntimeLaneConfigError("LaneConfig.claim_ttl_seconds 必须为正数")
        if self.heartbeat_interval_seconds <= 0:
            raise RuntimeLaneConfigError(
                "LaneConfig.heartbeat_interval_seconds 必须为正数"
            )
        if self.claim_ttl_seconds <= self.heartbeat_interval_seconds:
            raise RuntimeLaneConfigError(
                "LaneConfig.claim_ttl_seconds 必须大于 heartbeat_interval_seconds"
            )


@dataclass(frozen=True, slots=True)
class LaneOwner:
    """runtime capacity claim 的进程 owner 诊断身份。

    :param owner_id: owner 标识，必须为非空字符串。
    :param pid: owner 所在进程 pid。
    :param process_start_token: 可选进程启动 token，仅用于 runtime 诊断。
    :raises RuntimeLaneConfigError: owner_id 为空或 pid 非正时抛出。
    """

    owner_id: str
    pid: int
    process_start_token: str | None = None

    def __post_init__(self) -> None:
        """校验 owner 诊断身份。

        :returns: ``None``。
        :raises RuntimeLaneConfigError: owner 字段非法时抛出。
        """

        _require_non_blank(self.owner_id, field_name="LaneOwner.owner_id")
        if self.pid <= 0:
            raise RuntimeLaneConfigError("LaneOwner.pid 必须为正整数")
        if self.process_start_token is not None:
            _require_non_blank(
                self.process_start_token,
                field_name="LaneOwner.process_start_token",
            )


@dataclass(frozen=True, slots=True)
class SQLiteLaneCoordinatorConfig:
    """SQLite runtime lane coordinator 配置。

    :param db_path: 独立 runtime lane DB 路径，调用方必须显式提供。
    :param create_parent_dirs: parent directory 缺失时是否创建。
    :param busy_timeout_seconds: SQLite busy timeout 秒数，仅作用于 runtime
        lane DB connection。
    :param poll_interval_seconds: 等待 acquire 的轮询间隔秒数。
    :raises RuntimeLaneConfigError: 路径或 timeout 配置非法时抛出。
    """

    db_path: Path
    create_parent_dirs: bool = True
    busy_timeout_seconds: float = _DEFAULT_BUSY_TIMEOUT_SECONDS
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        """校验 SQLite coordinator 配置。

        :returns: ``None``。
        :raises RuntimeLaneConfigError: 配置字段非法时抛出。
        """

        if self.db_path.name.strip() == "":
            raise RuntimeLaneConfigError("SQLite lane db_path 必须包含文件名")
        if self.busy_timeout_seconds <= 0:
            raise RuntimeLaneConfigError(
                "SQLite lane busy_timeout_seconds 必须为正数"
            )
        if self.poll_interval_seconds <= 0:
            raise RuntimeLaneConfigError(
                "SQLite lane poll_interval_seconds 必须为正数"
            )


@dataclass(slots=True, init=False)
class LaneClaimToken:
    """已获取 lane capacity claim 的 token。

    :param name: lane 名称。
    :param claim_id: 不可猜测的 claim id。
    :param owner: claim owner 诊断身份。
    :param expires_at: 当前 claim 过期时间。
    :param controller: 管理该 claim 的 controller。
    """

    name: str
    claim_id: str
    owner: LaneOwner
    expires_at: datetime
    released: bool
    _controller: LaneController = field(repr=False, compare=False)
    _lost: bool = field(default=False, repr=False, compare=False)

    def __init__(
        self,
        *,
        name: str,
        claim_id: str,
        owner: LaneOwner,
        expires_at: datetime,
        controller: LaneController,
    ) -> None:
        """初始化 claim token。

        :param name: lane 名称。
        :param claim_id: claim id。
        :param owner: claim owner。
        :param expires_at: 当前过期时间。
        :param controller: 管理该 claim 的 controller。
        :returns: ``None``。
        :raises RuntimeLaneConfigError: name 或 claim_id 为空时抛出。
        """

        _require_non_blank(name, field_name="LaneClaimToken.name")
        _require_non_blank(claim_id, field_name="LaneClaimToken.claim_id")
        self.name = name
        self.claim_id = claim_id
        self.owner = owner
        self.expires_at = expires_at
        self.released = False
        self._controller = controller
        self._lost = False

    async def refresh(self) -> None:
        """刷新当前 claim 的 heartbeat 与过期时间。

        :returns: ``None``。
        :raises RuntimeLaneClaimLostError: claim 已 release、丢失或过期时抛出。
        :raises RuntimeLaneError: SQLite 操作失败时抛出。
        """

        await self._controller._refresh_token(self)

    async def release(self) -> None:
        """释放当前 claim。

        释放按 ``lane_name + claim_id + owner_id`` 删除 DB row，并保持幂等；
        重复 release 不影响其它 owner 的 claim。

        :returns: ``None``。
        :raises RuntimeLaneError: SQLite 操作失败时抛出。
        """

        await self._controller._release_token(self)


@dataclass(frozen=True, slots=True)
class LaneAcquired:
    """acquire 成功结果。

    :param token: 已获取的 claim token。
    """

    token: LaneClaimToken


@dataclass(frozen=True, slots=True)
class LaneAcquireCancelled:
    """acquire 被 cancellation token 或 controller close 取消。

    :param reason: 中性取消原因。
    """

    reason: str | None = None


@dataclass(frozen=True, slots=True)
class LaneAcquireTimedOut:
    """acquire 等待超时。

    :param elapsed_seconds: 从 acquire 开始到 timeout 命中的秒数。
    """

    elapsed_seconds: float


LaneAcquireOutcome: TypeAlias = (
    LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut
)
"""lane acquire 的封闭联合结果。"""


@dataclass(frozen=True, slots=True)
class _LaneClock:
    """基于 monotonic anchor 的 UTC 时钟。

    :param monotonic_anchor: 进程内 monotonic 起点。
    :param utc_anchor: 与 monotonic 起点对应的 UTC 时间。
    """

    monotonic_anchor: float
    utc_anchor: datetime

    @classmethod
    def start(cls) -> _LaneClock:
        """创建当前进程使用的 lane 时钟。

        :returns: 新的 :class:`_LaneClock`。
        """

        return cls(
            monotonic_anchor=time.monotonic(),
            utc_anchor=datetime.now(UTC),
        )

    def now(self) -> datetime:
        """返回当前 UTC 时间。

        :returns: 基于 monotonic elapsed 推导出的 UTC 时间。
        """

        elapsed_seconds = time.monotonic() - self.monotonic_anchor
        return self.utc_anchor + timedelta(seconds=elapsed_seconds)

    def monotonic(self) -> float:
        """返回当前 monotonic 时间。

        :returns: :func:`time.monotonic` 的当前值。
        """

        return time.monotonic()


@dataclass(frozen=True, slots=True)
class _ClaimAttempt:
    """单次 DB claim 尝试结果。

    :param acquired: 是否成功插入 claim。
    :param claim_id: 成功时的 claim id。
    :param expires_at: 成功时的过期时间。
    """

    acquired: bool
    claim_id: str | None
    expires_at: datetime | None


class LaneController:
    """跨进程 runtime lane controller。

    controller 显式持有 lane 配置、SQLite runtime lane DB 配置和 owner 诊断
    身份。它不读取 Host 默认路径，不保存 Host / Fins / Engine 字段。
    """

    def __init__(
        self,
        *,
        configs: tuple[LaneConfig, ...],
        coordinator: SQLiteLaneCoordinatorConfig,
        owner: LaneOwner,
        clock: _LaneClock,
    ) -> None:
        """初始化 controller。

        :param configs: 已校验的 lane 配置元组。
        :param coordinator: SQLite coordinator 配置。
        :param owner: 当前 controller owner。
        :param clock: 当前进程 lane 时钟。
        :returns: ``None``。
        """

        self._configs: dict[str, LaneConfig] = {item.name: item for item in configs}
        self._coordinator = coordinator
        self._owner = owner
        self._clock = clock
        self._closed = False
        self._close_completed = False
        self._close_reason: str | None = None
        self._heartbeat_error: RuntimeLaneError | None = None
        self._held_tokens: dict[tuple[str, str], LaneClaimToken] = {}
        self._waiters: set[asyncio.Event] = set()
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._heartbeat_interval_seconds = min(
            item.heartbeat_interval_seconds for item in configs
        )

    @classmethod
    async def open(
        cls,
        configs: Sequence[LaneConfig],
        *,
        coordinator: SQLiteLaneCoordinatorConfig,
        owner: LaneOwner | None = None,
    ) -> LaneController:
        """打开 runtime lane controller 并初始化独立 SQLite DB。

        :param configs: lane 配置序列，不允许为空或重复 name。
        :param coordinator: SQLite runtime lane DB 配置，必须显式传入。
        :param owner: 可选 owner；未传入时使用随机 owner_id 与当前 pid。
        :returns: 已打开的 :class:`LaneController`。
        :raises RuntimeLaneConfigError: 配置非法或 DB parent 缺失时抛出。
        :raises RuntimeLaneError: SQLite 初始化失败时抛出。
        """

        config_tuple = tuple(configs)
        if not config_tuple:
            raise RuntimeLaneConfigError("LaneController 至少需要一个 LaneConfig")
        names = [item.name for item in config_tuple]
        if len(set(names)) != len(names):
            raise RuntimeLaneConfigError("LaneConfig.name 不允许重复")
        resolved_owner = owner or LaneOwner(
            owner_id=secrets.token_hex(_OWNER_ID_BYTES),
            pid=os.getpid(),
            process_start_token=None,
        )
        await asyncio.to_thread(_prepare_and_initialize_database, coordinator)
        return cls(
            configs=config_tuple,
            coordinator=coordinator,
            owner=resolved_owner,
            clock=_LaneClock.start(),
        )

    async def acquire(
        self,
        name: str,
        *,
        token: CancellationToken | None = None,
        timeout_seconds: float | None = None,
    ) -> LaneAcquireOutcome:
        """获取指定 lane 的 capacity claim。

        :param name: lane 名称。
        :param token: 可选协作式取消观察 token；命中时返回
            :class:`LaneAcquireCancelled`。
        :param timeout_seconds: acquire timeout；``0`` 为 non-blocking，
            正数为最多等待秒数，``None`` 使用 lane 默认 timeout。
        :returns: :class:`LaneAcquired`、:class:`LaneAcquireCancelled` 或
            :class:`LaneAcquireTimedOut`。
        :raises RuntimeLaneConfigError: lane 未知或 timeout 为负数时抛出。
        :raises RuntimeLaneClosedError: controller 已关闭后新 acquire 时抛出。
        :raises RuntimeLaneError: SQLite 操作失败时抛出。
        :raises asyncio.CancelledError: 外层 task cancel 时透传。
        """

        lane_config = self._get_config(name)
        self._raise_heartbeat_error_if_present()
        if self._closed:
            raise RuntimeLaneClosedError("LaneController 已关闭，拒绝新的 acquire")
        effective_timeout = _resolve_timeout(
            explicit_timeout_seconds=timeout_seconds,
            default_timeout_seconds=lane_config.default_timeout_seconds,
        )
        started_at = self._clock.monotonic()
        deadline = (
            None
            if effective_timeout is None
            else started_at + effective_timeout
        )

        while True:
            self._raise_heartbeat_error_if_present()
            if token is not None and token.is_cancelled():
                return LaneAcquireCancelled(reason=token.cancel_reason())
            if self._closed:
                return LaneAcquireCancelled(reason=self._close_reason)

            claim = await self._try_claim_once(lane_config)
            if claim.acquired:
                if claim.claim_id is None or claim.expires_at is None:
                    raise RuntimeLaneError("SQLite lane claim 成功结果缺少 claim 字段")
                elapsed_after_claim = self._clock.monotonic() - started_at
                if token is not None and token.is_cancelled():
                    await self._release_untracked_claim(name, claim.claim_id)
                    return LaneAcquireCancelled(reason=token.cancel_reason())
                if self._heartbeat_error is not None:
                    await self._release_untracked_claim(name, claim.claim_id)
                    self._raise_heartbeat_error_if_present()
                if self._closed:
                    await self._release_untracked_claim(name, claim.claim_id)
                    return LaneAcquireCancelled(reason=self._close_reason)
                if (
                    effective_timeout != 0
                    and deadline is not None
                    and self._clock.monotonic() >= deadline
                ):
                    await self._release_untracked_claim(name, claim.claim_id)
                    return LaneAcquireTimedOut(elapsed_seconds=elapsed_after_claim)
                lane_token = LaneClaimToken(
                    name=name,
                    claim_id=claim.claim_id,
                    owner=self._owner,
                    expires_at=claim.expires_at,
                    controller=self,
                )
                self._held_tokens[(lane_token.name, lane_token.claim_id)] = lane_token
                self._ensure_heartbeat_task()
                return LaneAcquired(token=lane_token)

            elapsed_seconds = self._clock.monotonic() - started_at
            if effective_timeout == 0:
                return LaneAcquireTimedOut(elapsed_seconds=elapsed_seconds)
            if deadline is not None and self._clock.monotonic() >= deadline:
                if token is not None and token.is_cancelled():
                    return LaneAcquireCancelled(reason=token.cancel_reason())
                return LaneAcquireTimedOut(elapsed_seconds=elapsed_seconds)

            await self._wait_before_retry(
                deadline=deadline,
                token=token,
            )

    async def close(self, reason: str | None = None) -> None:
        """关闭 controller，取消 pending acquire 并尽力释放当前 tokens。

        :param reason: 关闭原因，会传给 pending acquire 的 cancelled outcome。
        :returns: ``None``。
        :raises RuntimeLaneError: SQLite release 操作失败时抛出。
        """

        if self._close_completed:
            return
        self._closed = True
        if reason is not None:
            self._close_reason = reason
        self._wake_waiters()
        tokens = tuple(self._held_tokens.values())
        first_release_error: RuntimeLaneError | None = None
        for lane_token in tokens:
            try:
                await lane_token.release()
            except RuntimeLaneError as exc:
                if first_release_error is None:
                    first_release_error = exc
        heartbeat_task = self._heartbeat_task
        if heartbeat_task is not None and heartbeat_task is not asyncio.current_task():
            heartbeat_task.cancel()
            with _suppress_cancelled_error():
                await heartbeat_task
        self._close_completed = True
        if first_release_error is not None:
            raise first_release_error

    async def _try_claim_once(self, lane_config: LaneConfig) -> _ClaimAttempt:
        """执行一次 SQLite 短事务 claim。

        :param lane_config: lane 配置。
        :returns: claim 成功或容量已满结果。
        :raises RuntimeLaneError: SQLite 操作失败时抛出。
        :raises asyncio.CancelledError: 外层 task cancel 时透传，且若 DB 已插入
            claim 会先做 best-effort release。
        """

        claim_task = asyncio.create_task(
            asyncio.to_thread(self._try_claim_once_sync, lane_config)
        )
        try:
            return await asyncio.shield(claim_task)
        except asyncio.CancelledError:
            claim = await claim_task
            if claim.acquired and claim.claim_id is not None:
                await self._release_untracked_claim(lane_config.name, claim.claim_id)
            raise

    def _try_claim_once_sync(self, lane_config: LaneConfig) -> _ClaimAttempt:
        """同步执行一次 SQLite claim 短事务。

        :param lane_config: lane 配置。
        :returns: claim 尝试结果。
        :raises RuntimeLaneError: SQLite 操作失败时抛出。
        """

        claim_id = secrets.token_hex(_CLAIM_ID_BYTES)
        now = self._clock.now()
        expires_at = now + timedelta(seconds=lane_config.claim_ttl_seconds)
        connection = _connect(self._coordinator)
        try:
            connection.execute("BEGIN IMMEDIATE")
            # stale cleanup、active count 与 insert 必须在同一事务内完成，
            # 否则跨进程竞争下可能突破 capacity。
            connection.execute(
                f"DELETE FROM {_CLAIMS_TABLE} "
                "WHERE lane_name = ? AND expires_at <= ?",
                (lane_config.name, _format_datetime(now)),
            )
            row = connection.execute(
                f"SELECT COUNT(*) FROM {_CLAIMS_TABLE} "
                "WHERE lane_name = ? AND expires_at > ?",
                (lane_config.name, _format_datetime(now)),
            ).fetchone()
            active_count = _read_count(row)
            if active_count >= lane_config.capacity:
                connection.execute("COMMIT")
                return _ClaimAttempt(
                    acquired=False,
                    claim_id=None,
                    expires_at=None,
                )
            connection.execute(
                f"INSERT INTO {_CLAIMS_TABLE} "
                "(lane_name, claim_id, owner_id, owner_pid, "
                "owner_process_start_token, created_at, heartbeat_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    lane_config.name,
                    claim_id,
                    self._owner.owner_id,
                    self._owner.pid,
                    self._owner.process_start_token,
                    _format_datetime(now),
                    _format_datetime(now),
                    _format_datetime(expires_at),
                ),
            )
            connection.execute("COMMIT")
            return _ClaimAttempt(
                acquired=True,
                claim_id=claim_id,
                expires_at=expires_at,
            )
        except sqlite3.Error as exc:
            _rollback(connection)
            raise RuntimeLaneError("SQLite runtime lane claim 失败") from exc
        finally:
            connection.close()

    async def _refresh_token(self, token: LaneClaimToken) -> None:
        """刷新 token 的 DB heartbeat。

        :param token: 待刷新的 token。
        :returns: ``None``。
        :raises RuntimeLaneClaimLostError: token 已 release、丢失或过期时抛出。
        :raises RuntimeLaneError: SQLite 操作失败时抛出。
        """

        if token.released:
            raise RuntimeLaneClaimLostError("lane claim 已 release 或丢失")
        refresh_task = asyncio.create_task(
            asyncio.to_thread(self._refresh_token_sync, token)
        )
        try:
            expires_at = await asyncio.shield(refresh_task)
        except RuntimeLaneClaimLostError:
            self._mark_token_lost(token)
            raise
        token.expires_at = expires_at

    def _refresh_token_sync(self, token: LaneClaimToken) -> datetime:
        """同步刷新 token heartbeat。

        :param token: 待刷新的 token。
        :returns: 新的过期时间。
        :raises RuntimeLaneClaimLostError: DB row 不存在或已过期时抛出。
        :raises RuntimeLaneError: SQLite 操作失败时抛出。
        """

        lane_config = self._get_config(token.name)
        now = self._clock.now()
        expires_at = now + timedelta(seconds=lane_config.claim_ttl_seconds)
        connection = _connect(self._coordinator)
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                f"UPDATE {_CLAIMS_TABLE} "
                "SET heartbeat_at = ?, expires_at = ? "
                "WHERE lane_name = ? AND claim_id = ? AND owner_id = ? "
                "AND expires_at > ?",
                (
                    _format_datetime(now),
                    _format_datetime(expires_at),
                    token.name,
                    token.claim_id,
                    token.owner.owner_id,
                    _format_datetime(now),
                ),
            )
            if cursor.rowcount != 1:
                connection.execute("ROLLBACK")
                raise RuntimeLaneClaimLostError("lane claim 已丢失或过期")
            connection.execute("COMMIT")
            return expires_at
        except RuntimeLaneClaimLostError:
            raise
        except sqlite3.Error as exc:
            _rollback(connection)
            raise RuntimeLaneError("SQLite runtime lane heartbeat 失败") from exc
        finally:
            connection.close()

    async def _release_token(self, token: LaneClaimToken) -> None:
        """按 token 释放 DB claim。

        :param token: 待释放 token。
        :returns: ``None``。
        :raises RuntimeLaneError: SQLite 操作失败时抛出。
        """

        if token.released:
            return
        release_task = asyncio.create_task(
            asyncio.to_thread(self._release_claim_sync, token.name, token.claim_id)
        )
        await asyncio.shield(release_task)
        token.released = True
        self._held_tokens.pop((token.name, token.claim_id), None)
        self._wake_waiters()

    async def _release_untracked_claim(self, lane_name: str, claim_id: str) -> None:
        """释放尚未登记到 held token 集合的 claim。

        该路径用于 acquire 与 close / cancellation / timeout 竞态：SQLite 短
        事务可能已经插入 claim，但调用方语义已经不应持有容量，因此必须先
        best-effort 删除该 claim，再返回 cancelled / timed out 或透传
        ``CancelledError``。

        :param lane_name: lane 名称。
        :param claim_id: claim id。
        :returns: ``None``。
        :raises RuntimeLaneError: SQLite 操作失败时抛出。
        """

        release_task = asyncio.create_task(
            asyncio.to_thread(self._release_claim_sync, lane_name, claim_id)
        )
        await asyncio.shield(release_task)

    def _release_claim_sync(self, lane_name: str, claim_id: str) -> None:
        """同步删除一个 claim row。

        :param lane_name: lane 名称。
        :param claim_id: claim id。
        :returns: ``None``。
        :raises RuntimeLaneError: SQLite 操作失败时抛出。
        """

        connection = _connect(self._coordinator)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                f"DELETE FROM {_CLAIMS_TABLE} "
                "WHERE lane_name = ? AND claim_id = ? AND owner_id = ?",
                (lane_name, claim_id, self._owner.owner_id),
            )
            connection.execute("COMMIT")
        except sqlite3.Error as exc:
            _rollback(connection)
            raise RuntimeLaneError("SQLite runtime lane release 失败") from exc
        finally:
            connection.close()

    async def _wait_before_retry(
        self,
        *,
        deadline: float | None,
        token: CancellationToken | None,
    ) -> None:
        """等待下一次 acquire poll 或 close / release 唤醒。

        :param deadline: monotonic deadline；``None`` 表示无限等待。
        :param token: 可选取消观察 token。
        :returns: ``None``。
        :raises asyncio.CancelledError: 外层 task cancel 时透传。
        """

        if token is not None and token.is_cancelled():
            return
        wait_seconds = self._coordinator.poll_interval_seconds
        if deadline is not None:
            remaining = deadline - self._clock.monotonic()
            if remaining <= 0:
                return
            wait_seconds = min(wait_seconds, remaining)
        waiter = asyncio.Event()
        self._waiters.add(waiter)
        try:
            try:
                await asyncio.wait_for(waiter.wait(), timeout=wait_seconds)
            except TimeoutError:
                return
        finally:
            self._waiters.discard(waiter)

    def _ensure_heartbeat_task(self) -> None:
        """确保 controller-managed heartbeat task 已启动。

        :returns: ``None``。
        """

        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        """后台刷新当前 controller 持有的 tokens。

        :returns: ``None``。
        :raises asyncio.CancelledError: controller close 取消 heartbeat 时透传。
        """

        try:
            while not self._closed:
                await asyncio.sleep(self._heartbeat_interval_seconds)
                for token in tuple(self._held_tokens.values()):
                    if token.released:
                        continue
                    try:
                        await token.refresh()
                    except RuntimeLaneClaimLostError:
                        self._mark_token_lost(token)
                        continue
                    except RuntimeLaneError as exc:
                        self._record_heartbeat_error(exc)
                        return
        except asyncio.CancelledError:
            raise

    def _record_heartbeat_error(self, error: RuntimeLaneError) -> None:
        """记录首次 heartbeat 不可恢复错误并停止新 acquire。

        :param error: heartbeat 刷新时捕获的结构化 runtime lane 错误。
        :returns: ``None``。
        """

        if self._heartbeat_error is None:
            self._heartbeat_error = error
        self._closed = True
        self._close_reason = "lane heartbeat error"
        self._wake_waiters()

    def _raise_heartbeat_error_if_present(self) -> None:
        """若 heartbeat 已记录不可恢复错误，则抛出该结构化错误。

        :returns: ``None``。
        :raises RuntimeLaneError: heartbeat 已失败时抛出首次记录的错误。
        """

        if self._heartbeat_error is not None:
            raise self._heartbeat_error

    def _mark_token_lost(self, token: LaneClaimToken) -> None:
        """把 token 标记为 lost / released 并从 held 集合移除。

        :param token: 丢失的 token。
        :returns: ``None``。
        """

        token._lost = True
        token.released = True
        self._held_tokens.pop((token.name, token.claim_id), None)

    def _wake_waiters(self) -> None:
        """唤醒所有 pending acquire waiter。

        :returns: ``None``。
        """

        for waiter in tuple(self._waiters):
            waiter.set()

    def _get_config(self, name: str) -> LaneConfig:
        """读取指定 lane 配置。

        :param name: lane 名称。
        :returns: 对应 :class:`LaneConfig`。
        :raises RuntimeLaneConfigError: name 为空或未知时抛出。
        """

        _require_non_blank(name, field_name="lane name")
        lane_config = self._configs.get(name)
        if lane_config is None:
            raise RuntimeLaneConfigError(f"未知 runtime lane: {name}")
        return lane_config


class _suppress_cancelled_error:
    """压制 ``asyncio.CancelledError`` 的局部 context manager。

    该 helper 只用于 close 等 cleanup 路径，避免引入 ``contextlib.suppress``
    对 ``BaseException`` 子类类型推断不稳定的问题。
    """

    def __enter__(self) -> None:
        """进入 context manager。

        :returns: ``None``。
        """

        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        """退出 context manager，并只压制 ``asyncio.CancelledError``。

        :param exc_type: 异常类型。
        :param exc: 异常实例。
        :param tb: traceback。
        :returns: 若异常是 ``asyncio.CancelledError`` 返回 ``True``。
        """

        return exc_type is asyncio.CancelledError


def _require_non_blank(value: str, *, field_name: str) -> None:
    """校验字符串非空且非纯空白。

    :param value: 待校验字符串。
    :param field_name: 字段名称，用于错误信息。
    :returns: ``None``。
    :raises RuntimeLaneConfigError: 字符串为空或纯空白时抛出。
    """

    if value.strip() == "":
        raise RuntimeLaneConfigError(f"{field_name} 不允许为空")


def _resolve_timeout(
    *,
    explicit_timeout_seconds: float | None,
    default_timeout_seconds: float | None,
) -> float | None:
    """解析 acquire timeout。

    :param explicit_timeout_seconds: acquire 显式 timeout。
    :param default_timeout_seconds: lane 默认 timeout。
    :returns: 实际 timeout；``None`` 表示无限等待。
    :raises RuntimeLaneConfigError: timeout 为负数时抛出。
    """

    timeout = (
        explicit_timeout_seconds
        if explicit_timeout_seconds is not None
        else default_timeout_seconds
    )
    if timeout is not None and timeout < 0:
        raise RuntimeLaneConfigError("timeout_seconds 不能为负数")
    return timeout


def _prepare_database_parent(config: SQLiteLaneCoordinatorConfig) -> None:
    """准备 SQLite lane DB parent directory。

    :param config: SQLite coordinator 配置。
    :returns: ``None``。
    :raises RuntimeLaneConfigError: parent 缺失且禁止创建时抛出。
    """

    parent = config.db_path.parent
    if parent.exists():
        if not parent.is_dir():
            raise RuntimeLaneConfigError("SQLite lane db_path parent 不是目录")
        return
    if not config.create_parent_dirs:
        raise RuntimeLaneConfigError("SQLite lane db_path parent 不存在")
    parent.mkdir(parents=True, exist_ok=True)


def _prepare_and_initialize_database(config: SQLiteLaneCoordinatorConfig) -> None:
    """准备 parent directory 并初始化 SQLite runtime lane DB。

    该函数供 async ``LaneController.open`` 通过 ``asyncio.to_thread`` 调用，
    避免目录创建与 SQLite 初始化阻塞事件循环。

    :param config: SQLite coordinator 配置。
    :returns: ``None``。
    :raises RuntimeLaneConfigError: parent 缺失且禁止创建时抛出。
    :raises RuntimeLaneError: SQLite 初始化失败时抛出。
    """

    _prepare_database_parent(config)
    _initialize_database(config)


def _initialize_database(config: SQLiteLaneCoordinatorConfig) -> None:
    """初始化独立 SQLite runtime lane DB。

    :param config: SQLite coordinator 配置。
    :returns: ``None``。
    :raises RuntimeLaneError: SQLite 初始化失败时抛出。
    """

    connection = _connect(config)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            f"CREATE TABLE IF NOT EXISTS {_CLAIMS_TABLE} ("
            "lane_name TEXT NOT NULL, "
            "claim_id TEXT NOT NULL, "
            "owner_id TEXT NOT NULL, "
            "owner_pid INTEGER NOT NULL, "
            "owner_process_start_token TEXT, "
            "created_at TEXT NOT NULL, "
            "heartbeat_at TEXT NOT NULL, "
            "expires_at TEXT NOT NULL, "
            "PRIMARY KEY (lane_name, claim_id)"
            ")"
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_CLAIMS_TABLE}_active "
            f"ON {_CLAIMS_TABLE} (lane_name, expires_at)"
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_CLAIMS_TABLE}_owner "
            f"ON {_CLAIMS_TABLE} (lane_name, owner_id)"
        )
        connection.commit()
    except sqlite3.Error as exc:
        raise RuntimeLaneError("SQLite runtime lane DB 初始化失败") from exc
    finally:
        connection.close()


def _connect(config: SQLiteLaneCoordinatorConfig) -> sqlite3.Connection:
    """打开 SQLite runtime lane DB 短连接并设置 busy timeout。

    :param config: SQLite coordinator 配置。
    :returns: SQLite connection。
    :raises RuntimeLaneError: SQLite connection 创建失败时抛出。
    """

    try:
        connection = sqlite3.connect(
            config.db_path,
            timeout=config.busy_timeout_seconds,
            isolation_level=None,
        )
        busy_timeout_ms = int(
            config.busy_timeout_seconds * _SQLITE_MILLISECONDS_PER_SECOND
        )
        connection.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        return connection
    except sqlite3.Error as exc:
        raise RuntimeLaneError("SQLite runtime lane DB 连接失败") from exc


def _rollback(connection: sqlite3.Connection) -> None:
    """尽力回滚当前 SQLite transaction。

    :param connection: SQLite connection。
    :returns: ``None``。
    """

    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error:
        return


def _format_datetime(value: datetime) -> str:
    """格式化 UTC datetime，供 SQLite text 比较使用。

    :param value: timezone-aware datetime。
    :returns: ISO-8601 字符串。
    """

    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _read_count(row: tuple[int] | None) -> int:
    """读取 SQLite ``COUNT(*)`` 结果。

    :param row: SQLite fetchone 返回的单列 row。
    :returns: count 整数。
    :raises RuntimeLaneError: row 为空时抛出。
    """

    if row is None:
        raise RuntimeLaneError("SQLite COUNT(*) 未返回结果")
    return cast(int, row[0])


__all__ = [
    "LaneAcquireCancelled",
    "LaneAcquireOutcome",
    "LaneAcquireTimedOut",
    "LaneAcquired",
    "LaneClaimToken",
    "LaneConfig",
    "LaneController",
    "LaneOwner",
    "RuntimeLaneClaimLostError",
    "RuntimeLaneClosedError",
    "RuntimeLaneConfigError",
    "RuntimeLaneError",
    "SQLiteLaneCoordinatorConfig",
]
