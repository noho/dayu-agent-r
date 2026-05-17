"""Host 等待适配器 registry 与最小 poller 的层内契约。

本模块只定义 Host 内部如何为 ``ToolAwaitingOutcome`` 选择等待适配器
binding，并提供 Phase 7 的最小 poll adapter 轮询编排。它不实现 callback
endpoint 或外部系统协议，也不让 Engine 选择 adapter。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, TypeAlias

from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.host.api import (
    HostCallContext,
    ResolveWaitLostOutcome,
    ResolveWaitOutcome,
    ResolveWaitRequest,
    RunSnapshot,
    WaitAdapterKey,
    WaitResolutionSource,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.state import (
    ExternalJobRef,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
    read_wait_records_for_poll_observation,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner

_LOGGER = logging.getLogger(__name__)


class WaitExternalJobRefSource(StrEnum):
    """外部 job id 的 Host 派生来源。"""

    NONE = "none"
    RESUME_TOKEN = "resume_token"


@dataclass(frozen=True, slots=True)
class WaitPollNotReady:
    """poll adapter 观察到外部 job 尚未完成。"""


@dataclass(frozen=True, slots=True)
class WaitPollReady:
    """poll adapter 观察到外部 job 已产生可恢复结果。

    :param outcome: 交给 ``resolve_wait`` 的 typed 等待结果 envelope。
    """

    outcome: ResolveWaitOutcome


@dataclass(frozen=True, slots=True)
class WaitPollLost:
    """poll adapter 观察到外部 job 状态已不可确认。

    :param outcome: 交给 ``resolve_wait`` 的 lost envelope。
    """

    outcome: ResolveWaitLostOutcome


WaitPollResult: TypeAlias = WaitPollNotReady | WaitPollReady | WaitPollLost
"""poll adapter 单次观察结果封闭联合。"""


class WaitPollAdapter(Protocol):
    """外部等待系统 poll adapter 端口。"""

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """在 Host transaction 外观察外部 job 状态。

        :param wait_record: 当前 wait record 快照。
        :returns: poll 结果。
        :raises Exception: adapter 可在外部系统调用失败时抛出普通异常。
        """

        ...

    def abandon_wait(self, wait_record: WaitRecordRow) -> None:
        """在 wait 已取消时放弃外部 job。

        :param wait_record: 已取消 wait record 快照。
        :returns: ``None``。
        :raises Exception: adapter 可在外部系统调用失败时抛出普通异常。
        """

        ...


class WaitResolvePort(Protocol):
    """poller 依赖的 resolve_wait 端口。"""

    def resolve_wait(
        self, wait_id: str, request: ResolveWaitRequest
    ) -> RunSnapshot:
        """接收 poller 观察到的等待结果。

        :param wait_id: wait record id。
        :param request: typed resolve wait 请求。
        :returns: resolve 后 Run snapshot。
        :raises Exception: 具体实现按公共 Host API 抛出结构化错误。
        """

        ...


class WaitPollClock(Protocol):
    """poller 使用的 UTC 时钟端口。"""

    def now(self) -> datetime:
        """返回当前 UTC aware 时间。

        :returns: timezone-aware UTC ``datetime``。
        """

        ...


@dataclass(frozen=True, slots=True)
class WaitPollAdapterRegistration:
    """poll adapter 注册项。

    :param adapter_key: adapter 稳定注册键。
    :param adapter: poll adapter 实例。
    """

    adapter_key: WaitAdapterKey
    adapter: WaitPollAdapter


@dataclass(frozen=True, slots=True)
class WaitPollOnceResult:
    """单轮 poller 执行摘要。

    :param observed: 本轮读取到的 poll wait 数。
    :param not_ready: adapter 返回未就绪的 wait 数。
    :param resolved: 通过 ``resolve_wait`` 接收 completed/failed/cancelled 的数。
    :param lost: 通过 ``resolve_wait`` 接收 lost 的数。
    :param abandoned: 因 wait 已取消而通知 adapter 放弃的数。
    :param adapter_errors: adapter 调用失败的数。
    """

    observed: int
    not_ready: int
    resolved: int
    lost: int
    abandoned: int
    adapter_errors: int


class _SystemUtcClock:
    """系统 UTC 时钟。"""

    def now(self) -> datetime:
        """返回当前 UTC aware 时间。

        :returns: 当前 UTC 时间。
        """

        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class WaitAdapterBinding:
    """单个工具等待适配器 binding。

    :param tool_name: 适用工具名。
    :param await_kind: 适用等待类型。
    :param adapter_key: Host registry 中的稳定 adapter key。
    :param resume_policy: 等待恢复策略。
    :param external_job_ref_source: 外部 job id 的派生来源。
    """

    tool_name: str
    await_kind: ToolAwaitKind
    adapter_key: WaitAdapterKey
    resume_policy: WaitResumePolicy
    external_job_ref_source: WaitExternalJobRefSource

    def __post_init__(self) -> None:
        """校验 binding 字段。

        :returns: ``None``。
        :raises ValueError: 工具名为空或 enum 类型非法时抛出。
        """

        if self.tool_name.strip() == "":
            raise ValueError("tool_name must be non-empty")
        if not isinstance(self.await_kind, ToolAwaitKind):
            raise ValueError("await_kind must be ToolAwaitKind")
        if not isinstance(self.adapter_key, WaitAdapterKey):
            raise ValueError("adapter_key must be WaitAdapterKey")
        if not isinstance(self.resume_policy, WaitResumePolicy):
            raise ValueError("resume_policy must be WaitResumePolicy")
        if not isinstance(self.external_job_ref_source, WaitExternalJobRefSource):
            raise ValueError(
                "external_job_ref_source must be WaitExternalJobRefSource"
            )

    def external_job_ref(self, await_spec: ToolAwaitSpec) -> ExternalJobRef | None:
        """根据 Host binding 从等待规约派生外部 job 引用。

        :param await_spec: 工具等待规约。
        :returns: 外部 job 引用；当前 binding 不需要时为 ``None``。
        """

        if self.external_job_ref_source is WaitExternalJobRefSource.NONE:
            return None
        if self.external_job_ref_source is WaitExternalJobRefSource.RESUME_TOKEN:
            return ExternalJobRef(
                adapter_key=self.adapter_key,
                external_job_id=await_spec.resume_token,
            )
        raise ValueError("unsupported external job ref source")


class WaitAdapterRegistry:
    """Host 等待适配器 registry。

    registry 只按 Host 配置过的 tool name 与 await kind 选择 binding，不读取
    Engine event，也不反序列化业务 payload。
    """

    def __init__(self, bindings: tuple[WaitAdapterBinding, ...]) -> None:
        """初始化 registry。

        :param bindings: 可用 binding 列表。
        :returns: ``None``。
        :raises ValueError: 出现重复 binding key 时抛出。
        """

        self._bindings: dict[tuple[str, ToolAwaitKind], WaitAdapterBinding] = {}
        for binding in bindings:
            key = (binding.tool_name, binding.await_kind)
            if key in self._bindings:
                raise ValueError("duplicate wait adapter binding")
            self._bindings[key] = binding

    def resolve_binding(
        self, *, tool_name: str, await_kind: ToolAwaitKind
    ) -> WaitAdapterBinding | None:
        """解析工具等待 binding。

        :param tool_name: 工具名。
        :param await_kind: 等待类型。
        :returns: 匹配 binding；未配置时为 ``None``。
        :raises ValueError: 工具名为空或等待类型非法时抛出。
        """

        if tool_name.strip() == "":
            raise ValueError("tool_name must be non-empty")
        if not isinstance(await_kind, ToolAwaitKind):
            raise ValueError("await_kind must be ToolAwaitKind")
        return self._bindings.get((tool_name, await_kind))


class WaitPollAdapterRegistry:
    """Host poll adapter registry。"""

    def __init__(
        self, registrations: tuple[WaitPollAdapterRegistration, ...]
    ) -> None:
        """初始化 poll adapter registry。

        :param registrations: adapter 注册项。
        :returns: ``None``。
        :raises ValueError: adapter key 重复时抛出。
        """

        self._adapters: dict[WaitAdapterKey, WaitPollAdapter] = {}
        for registration in registrations:
            if registration.adapter_key in self._adapters:
                raise ValueError("duplicate wait poll adapter registration")
            self._adapters[registration.adapter_key] = registration.adapter

    def resolve_adapter(self, adapter_key: WaitAdapterKey) -> WaitPollAdapter | None:
        """按 adapter key 解析 poll adapter。

        :param adapter_key: wait record 上持久化的 adapter key。
        :returns: adapter；未注册时为 ``None``。
        """

        return self._adapters.get(adapter_key)


class WaitPoller:
    """最小 wait poller。

    poller 只读取 Host durable 中 active poll wait 快照；外部 adapter 调用发生
    在 Host transaction 外，ready/lost 结果统一交回 ``resolve_wait``。
    """

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        adapter_registry: WaitPollAdapterRegistry,
        resolver: WaitResolvePort,
        context: HostCallContext,
        clock: WaitPollClock | None = None,
    ) -> None:
        """初始化 poller。

        :param transaction_runner: Host transaction runner。
        :param adapter_registry: poll adapter registry。
        :param resolver: resolve_wait 端口。
        :param context: poller 调用上下文。
        :param clock: UTC 时钟；缺省使用系统 UTC 时间。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._adapter_registry = adapter_registry
        self._resolver = resolver
        self._context = context
        self._clock = clock if clock is not None else _SystemUtcClock()

    def poll_once(self) -> WaitPollOnceResult:
        """执行单轮 poll。

        :returns: 本轮 poll 摘要。
        """

        records = self._transaction_runner.run_read(
            _read_wait_records_for_poll_observation
        )
        not_ready = 0
        resolved = 0
        lost = 0
        abandoned = 0
        adapter_errors = 0
        for record in records:
            adapter = self._adapter_registry.resolve_adapter(record.adapter_key)
            if adapter is None:
                _LOGGER.warning(
                    "wait poll adapter not registered; skipping wait_id=%s "
                    "adapter_key=%s",
                    record.wait_id,
                    record.adapter_key.value,
                )
                adapter_errors += 1
                continue
            if record.status is WaitRecordStatus.CANCELLED:
                try:
                    adapter.abandon_wait(record)
                    abandoned += 1
                except Exception as exc:
                    _LOGGER.warning(
                        "wait adapter abandon failed; continuing wait_id=%s "
                        "adapter_key=%s error_type=%s",
                        record.wait_id,
                        record.adapter_key.value,
                        exc.__class__.__name__,
                    )
                    adapter_errors += 1
                continue
            try:
                poll_result = adapter.poll_wait(record)
            except Exception as exc:
                _LOGGER.warning(
                    "wait adapter poll failed; continuing wait_id=%s "
                    "adapter_key=%s error_type=%s",
                    record.wait_id,
                    record.adapter_key.value,
                    exc.__class__.__name__,
                )
                adapter_errors += 1
                continue
            if isinstance(poll_result, WaitPollNotReady):
                not_ready += 1
                continue
            request = ResolveWaitRequest(
                context=self._context,
                idempotency_key=_poll_idempotency_key(record),
                outcome=poll_result.outcome,
                source=WaitResolutionSource.POLL,
                observed_at=self._clock.now(),
            )
            self._resolver.resolve_wait(record.wait_id, request)
            if isinstance(poll_result, WaitPollLost):
                lost += 1
            else:
                resolved += 1
        return WaitPollOnceResult(
            observed=len(records),
            not_ready=not_ready,
            resolved=resolved,
            lost=lost,
            abandoned=abandoned,
            adapter_errors=adapter_errors,
        )


def _read_wait_records_for_poll_observation(
    transaction: HostTransaction,
) -> tuple[WaitRecordRow, ...]:
    """读取 poller 可观察 wait records。

    :param transaction: Host transaction。
    :returns: wait record 元组。
    """

    return read_wait_records_for_poll_observation(transaction)


def _poll_idempotency_key(wait_record: WaitRecordRow) -> str:
    """构造 poll source 的稳定 resolve_wait 幂等键。

    :param wait_record: wait record。
    :returns: 幂等键。
    """

    digest = sha256_digest_json(
        {
            "source": WaitResolutionSource.POLL.value,
            "wait_id": wait_record.wait_id,
        }
    ).removeprefix("sha256:")
    return f"poll-{digest}"


__all__ = [
    "WaitAdapterBinding",
    "WaitAdapterRegistry",
    "WaitExternalJobRefSource",
    "WaitPollAdapter",
    "WaitPollAdapterRegistration",
    "WaitPollAdapterRegistry",
    "WaitPollLost",
    "WaitPollNotReady",
    "WaitPollOnceResult",
    "WaitPollReady",
    "WaitPollResult",
    "WaitPoller",
    "WaitResolvePort",
]
