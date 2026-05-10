"""Host 内部 ToolRuntime 最小实现。

本模块只服务 P2 的工具执行代理、schema-driven 截断、cursor 生命周期与
RunEvent 事实写入。它不是 Host public surface，也不实现完整 ToolRegistry。
"""

from __future__ import annotations

import asyncio
import base64
import contextvars
import copy
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, TypeAlias, cast

from dayu.contracts import (
    FRAMEWORK_FETCH_MORE_TOOL_NAME,
    JsonValue,
    ToolExecutor,
    ToolTruncateSpec,
)
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultSuccess,
    ToolTruncationInfo,
)
from dayu.host._event_store import RunEventStore
from dayu.host._event_translation import terminal_result_from_event
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    ToolCursorDeniedData,
    ToolCursorExpiredData,
    ToolCursorIssuedData,
    ToolFetchMoreCompletedData,
    ToolFetchMoreFailedData,
    ToolFetchMoreFailedResult,
    ToolFetchMoreHandle,
    ToolFetchMoreHandleFailedResult,
    ToolFetchMoreHandleRequest,
    ToolFetchMoreHandleResult,
    ToolFetchMoreHandleSucceededResult,
    ToolFetchMoreRequest,
    ToolFetchMoreRequestedData,
    ToolFetchMoreResult,
    ToolFetchMoreSucceededResult,
    ToolResultTruncatedData,
    ToolRuntimeCursor,
    ToolValueSizeSummary,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_DEFAULT_CURSOR_TTL_SECONDS: int = 300
_LOGGER: logging.Logger = logging.getLogger(__name__)
_ERROR_CURSOR_NOT_FOUND: str = "cursor_not_found"
_ERROR_CURSOR_EXPIRED: str = "cursor_expired"
_ERROR_CURSOR_SCOPE_MISMATCH: str = "cursor_scope_mismatch"
_ERROR_RUN_TERMINAL: str = "run_terminal"
_ERROR_TOOL_RUNTIME_FAILED: str = "tool_runtime_failed"
_ERROR_INVALID_FETCH_MORE_ARGS: str = "invalid_fetch_more_args"
_FINGERPRINT_LENGTH: int = 16
_TOKEN_BYTES: int = 32
_FETCH_MORE_CURSOR_ARG: str = "cursor"
_FETCH_MORE_SCOPE_TOKEN_ARG: str = "scope_token"
_FETCH_MORE_LIMIT_ARG: str = "limit"
_LIMIT_BY_STRATEGY: Mapping[str, str] = {
    "text_chars": "max_chars",
    "text_lines": "max_lines",
    "list_items": "max_items",
    "binary_bytes": "max_bytes",
}
_UNIT_BY_STRATEGY: Mapping[str, str] = {
    "text_chars": "chars",
    "text_lines": "lines",
    "list_items": "items",
    "binary_bytes": "bytes",
}

_TargetValue: TypeAlias = JsonValue | bytes | bytearray
_StoredData: TypeAlias = str | tuple[str, ...] | list[JsonValue] | bytes


class _Clock(Protocol):
    """ToolRuntime 使用的 monotonic clock 协议。"""

    def __call__(self) -> float:
        """返回当前 monotonic 时间。

        :returns: 当前 monotonic 秒数。
        :raises Exception: 具体 clock 失败时透传。
        """
        ...


class _TokenGenerator(Protocol):
    """ToolRuntime cursor 原文生成器协议。"""

    def __call__(self) -> str:
        """返回新的 cursor 原文。

        :returns: cursor 原文。
        :raises Exception: 具体生成器失败时透传。
        """
        ...


class ToolRuntimeEventAppender(Protocol):
    """ToolRuntime canonical fact append port。

    本 Protocol 是 ToolRuntime 写入 ``TOOL_RESULT_TRUNCATED`` /
    ``TOOL_CURSOR_*`` / ``TOOL_FETCH_MORE_*`` 等 Host-owned canonical
    fact 的唯一入口; ``InMemoryToolRuntime`` 的 7 个 ``_append_*``
    helper 不再直接调用 :class:`RunEventStore.append`, 全部通过当前
    active appender 落库。

    P8-S5 装配规则:

    - durable 路径: 由 :class:`ToolRuntimeOwnerScope` 在每个 attempt
      生命周期内安装绑定 owner 的
      :class:`AttemptScopedRunEventAppender`, 每条 fact append 都在同
      一 ``BEGIN IMMEDIATE`` 事务内完成 ``verify_owner`` + EventLog
      append; stale owner / fenced owner 命中时抛
      ``AttemptFencingError``, 不写诊断 RunEvent;
    - 非 durable / 测试路径: 退化为 :class:`PlainRunEventAppender`,
      仅做 ``RunEventStore.append`` 透传, 不引入 owner 校验;
    - 不允许把 :class:`AttemptOwnerToken` / 任何 owner secret 暴露给
      ToolExecutor 或工具实现, 也不通过 ``ToolExecutionContext`` 传递
      owner 句柄。

    Protocol 只承诺 ``await append(draft)`` 返回 :class:`RunEvent`;
    fenced 失败由具体实现以 ``AttemptFencingError`` 透传给上层 harness,
    Protocol 不暴露 fencing 状态。
    """

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """append 一条 ToolRuntime canonical RunEvent。

        :param draft: RunEvent 草稿。
        :returns: 已落库的 :class:`RunEvent`。
        :raises Exception: 实现自身错误透传; durable 实现可能抛
            ``AttemptFencingError`` / SQLite 错误。
        """
        ...


@dataclass(frozen=True, slots=True)
class PlainRunEventAppender:
    """非 fencing 的 ToolRuntime fact append 实现。

    test-only fallback; never used in durable harness; durable path always
    uses AttemptScopedRunEventAppender via AttemptSupervisor.scoped_appender.

    本实现仅在非 durable / 测试 / bootstrap-without-supervisor 路径下
    使用, 直接透传到 :class:`RunEventStore.append`, 不做 owner CAS,
    也不开 ``BEGIN IMMEDIATE`` 事务。durable 路径必须使用
    :class:`AttemptScopedRunEventAppender`。

    :param event_store: 底层 :class:`RunEventStore`。
    """

    event_store: RunEventStore

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """直接通过 :class:`RunEventStore.append` 落库。

        :param draft: RunEvent 草稿。
        :returns: 已落库的 :class:`RunEvent`。
        :raises Exception: 底层 EventStore 错误透传。
        """

        return await self.event_store.append(draft)


_ACTIVE_TOOL_RUNTIME_APPENDER: contextvars.ContextVar[
    ToolRuntimeEventAppender | None
] = contextvars.ContextVar("dayu_host_tool_runtime_appender", default=None)
"""ToolRuntime 当前 attempt 绑定的 fencing-aware appender。

:class:`ToolRuntimeOwnerScope` 进入时把 owner 绑定的
:class:`AttemptScopedRunEventAppender` 注入本 ContextVar; 退出时恢复
旧值, 异常路径同样恢复。``ContextVar`` 保证并发 run / 嵌套 attempt
不会互相污染, 也避免把 owner secret 通过 ``ToolExecutionContext``
泄漏到工具实现。
"""


@asynccontextmanager
async def ToolRuntimeOwnerScope(  # noqa: N802
    appender: ToolRuntimeEventAppender,
) -> AsyncGenerator[None, None]:
    """以 ContextVar 形式安装 attempt-scoped fencing appender。

    本 async context manager 在每个 attempt 生命周期 (``_run_to_store``)
    外侧被 :mod:`dayu.host._durable_harness` / :mod:`dayu.host._run_harness`
    包裹一次, 进入时把 ``appender`` (通常是
    :class:`AttemptScopedRunEventAppender`) 注入
    :data:`_ACTIVE_TOOL_RUNTIME_APPENDER`, 离开时无条件恢复旧值, 异常
    也不例外。

    并发约束:

    - 不通过模块级 dict / 全局变量保存 appender, 避免跨 attempt /
      跨进程 race;
    - 使用 :class:`contextvars.ContextVar` 让每个 asyncio Task 持有独立
      副本; ``run_in_executor`` 路径会自动复制, 不需要额外封装;
    - framework ``fetch_more`` 嵌套调用本 scope 时, 内层 token 取代外
      层, 退出后还原, 满足 "framework fetch_more 使用发起 fetch_more
      的当前 attempt owner" 的语义。

    本 scope 不持有 owner secret 明文; ``appender`` 只暴露
    :meth:`ToolRuntimeEventAppender.append`, owner token 仅 owner 自己
    持有, 不会通过 ToolRuntime 流向 ToolExecutor。

    :param appender: 当前 attempt 的 fencing-aware appender。
    :yields: 无 yield 值; 在 ``with`` 内部 ToolRuntime 的所有 fact
        append 都会路由到 ``appender``。
    :raises Exception: yield 内部异常透传; 退出时无条件恢复旧 token。
    """

    token = _ACTIVE_TOOL_RUNTIME_APPENDER.set(appender)
    try:
        yield
    finally:
        _ACTIVE_TOOL_RUNTIME_APPENDER.reset(token)


def active_tool_runtime_appender() -> ToolRuntimeEventAppender | None:
    """返回当前 :class:`ToolRuntimeOwnerScope` 安装的 appender。

    供 :class:`LocalRunHarness` 内部 helper 在不显式持有
    ``_ActiveAttempt`` 句柄时, 仍能命中当前 attempt scope 内的
    fencing-aware appender; 没有 scope 时返回 ``None``, 调用方需自行
    退化到 plain append 路径。

    :returns: 当前生效的 :class:`ToolRuntimeEventAppender`; 无 scope 时
        返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    return _ACTIVE_TOOL_RUNTIME_APPENDER.get()


@dataclass(frozen=True, slots=True)
class _TruncateTarget:
    """已解析的截断目标。"""

    value: _TargetValue
    field_path: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class _TruncatedValue:
    """截断后的值与 cursor 记录材料。"""

    value: JsonValue
    data: _StoredData
    offset: int
    total: int
    chunk_size: int
    template: JsonValue | None
    field_path: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class _CursorRecord:
    """内存态 cursor 记录。"""

    cursor: str
    cursor_fingerprint: str
    scope_token: str
    scope_hash: str
    session_id: str
    run_id: str
    tool_call_id: str
    tool_name: str
    strategy: str
    unit: str
    limit: int
    total: int
    data: _StoredData
    offset: int
    template: JsonValue | None
    field_path: tuple[str, ...] | None
    created_at_monotonic: float
    expires_at_monotonic: float
    ttl_seconds: int
    parent_cursor_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class _CursorCreation:
    """cursor 创建结果。"""

    record: _CursorRecord
    issued_event: ToolCursorIssuedData


@dataclass(frozen=True, slots=True)
class ToolRuntimeToolExecutor:
    """将 Host ToolRuntime 适配为 Engine 可消费的 ToolExecutor。"""

    runtime: "InMemoryToolRuntime"

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """执行工具调用并应用 Host ToolRuntime 治理。

        :param request: 工具执行请求。
        :returns: 工具执行 outcome。
        :raises Exception: 不主动抛出异常，内部异常转为工具失败 outcome。
        """

        return await self.runtime.execute_tool_call(request)


@dataclass(slots=True, kw_only=True)
class InMemoryToolRuntime:
    """单进程内存态 ToolRuntime。

    :param is_durable: P8-S1 装配显式声明位:``True`` 表示由
        :func:`build_durable_harness` 装配的 production / durable runtime,
        ``_resolve_appender`` 必须从 :class:`ToolRuntimeOwnerScope`
        ContextVar 解析 owner-bound appender, 缺失时立即 ``RuntimeError``;
        ``False`` 表示 test-only 装配,允许在 ContextVar 缺失时退化为
        :class:`PlainRunEventAppender`。本字段是 keyword-only 必填参数,
        所有 ``InMemoryToolRuntime(...)`` 构造点必须显式传值。
    :param executor: 底层业务 ToolExecutor。
    :param event_store: Host RunEventStore; 仅用作 ``list_events`` 终态
        cursor 检测以及无 owner scope 路径的回退 fact append。
        canonical fact 写入由 :class:`ToolRuntimeEventAppender`
        统一承担。
    :param truncate_specs: 按工具名注入的显式截断声明。
    :param clock: monotonic clock。
    :param token_generator: cursor 原文生成器。
    """

    is_durable: bool
    executor: ToolExecutor
    event_store: RunEventStore
    truncate_specs: Mapping[str, ToolTruncateSpec] = field(default_factory=dict)
    clock: _Clock = time.monotonic
    token_generator: _TokenGenerator = lambda: secrets.token_hex(_TOKEN_BYTES)
    _records_by_cursor: dict[str, _CursorRecord] = field(
        default_factory=dict,
        init=False,
    )
    _cursor_by_fingerprint: dict[str, str] = field(
        default_factory=dict,
        init=False,
    )
    _fetch_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def _resolve_appender(self) -> ToolRuntimeEventAppender:
        """返回当前 attempt scope 内的 fact appender。

        - ``is_durable=True``: 必须从
          :class:`ToolRuntimeOwnerScope` ContextVar 读到 owner-bound
          fencing-aware appender, 缺失时立即 ``RuntimeError`` fail fast,
          严格阻止 durable 路径退化为非 fenced append;
        - ``is_durable=False`` (test-only): ContextVar 存在时返回安装的
          appender, 缺失时退化为 :class:`PlainRunEventAppender`,
          与 P6/P7 行为一致。

        :returns: 当前生效的 :class:`ToolRuntimeEventAppender`。
        :raises RuntimeError: ``is_durable=True`` 且 ContextVar 中没有
            owner scope 时抛出。
        """

        active = _ACTIVE_TOOL_RUNTIME_APPENDER.get()
        if self.is_durable:
            if active is None:
                raise RuntimeError(
                    "durable runtime requires ToolRuntimeOwnerScope for "
                    "attempt-scoped append"
                )
            return active
        if active is not None:
            return active
        return PlainRunEventAppender(event_store=self.event_store)

    async def execute_tool_call(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """执行工具调用并在成功结果上应用截断或 framework 补读。

        :param request: 工具执行请求。
        :returns: 截断后的工具执行 outcome。
        :raises Exception: 不主动抛出异常，ToolRuntime 自身异常转失败 outcome。
        """

        is_framework_fetch_more = request.call.name == FRAMEWORK_FETCH_MORE_TOOL_NAME
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.tool_runtime.tool_call_start "
            "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
            "framework=%s",
            request.context.session_id,
            request.context.run_id,
            request.call.name,
            request.context.tool_call_id,
            is_framework_fetch_more,
        )
        try:
            if is_framework_fetch_more:
                return await self._execute_framework_fetch_more(request)
            outcome = await self.executor.execute(request)
            if not isinstance(outcome, ToolCompletedOutcome):
                _LOGGER.log(
                    VERBOSE_LOG_LEVEL,
                    "host.tool_runtime.tool_call_finished "
                    "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
                    "framework=False outcome=%s truncated=False",
                    request.context.session_id,
                    request.context.run_id,
                    request.call.name,
                    request.context.tool_call_id,
                    _tool_outcome_name(outcome),
                )
                return outcome
            spec = self.truncate_specs.get(request.call.name)
            truncated = self._apply_truncation(
                request=request,
                value=cast(_TargetValue, outcome.result.value),
                spec=spec,
            )
            if truncated is None:
                _LOGGER.log(
                    VERBOSE_LOG_LEVEL,
                    "host.tool_runtime.tool_call_finished "
                    "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
                    "framework=False outcome=completed truncated=False",
                    request.context.session_id,
                    request.context.run_id,
                    request.call.name,
                    request.context.tool_call_id,
                )
                return outcome
            cursor_creation = self._store_cursor(
                request=request,
                spec=spec,
                truncated=truncated,
                parent_cursor_fingerprint=None,
            )
            await self._append_tool_result_truncated(
                request=request,
                record=cursor_creation.record,
                value=truncated.value,
                chunk_size=truncated.chunk_size,
            )
            await self._append_cursor_issued(
                request=request,
                data=cursor_creation.issued_event,
            )
            completed = ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value=truncated.value,
                    truncation=ToolTruncationInfo(
                        cursor=cursor_creation.record.cursor,
                        scope_token=cursor_creation.record.scope_token,
                        scope_hash=cursor_creation.record.scope_hash,
                        has_more=True,
                        limit=cursor_creation.record.limit,
                        ttl_seconds=cursor_creation.record.ttl_seconds,
                    ),
                    meta=outcome.result.meta,
                )
            )
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.tool_runtime.tool_call_finished "
                "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
                "framework=False outcome=completed truncated=True",
                request.context.session_id,
                request.context.run_id,
                request.call.name,
                request.context.tool_call_id,
            )
            _LOGGER.debug(
                "host.tool_runtime.tool_call_finished "
                "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
                "framework=False outcome=completed truncated=True "
                "strategy=%s limit=%s unit=%s chunk_size=%s total=%s "
                "cursor_fingerprint=%s field_path=%s ttl_seconds=%s",
                request.context.session_id,
                request.context.run_id,
                request.call.name,
                request.context.tool_call_id,
                cursor_creation.record.strategy,
                cursor_creation.record.limit,
                cursor_creation.record.unit,
                truncated.chunk_size,
                truncated.total,
                cursor_creation.record.cursor_fingerprint,
                _format_field_path(truncated.field_path),
                cursor_creation.record.ttl_seconds,
            )
            return completed
        except Exception as exc:
            _LOGGER.error(
                "host.tool_runtime.tool_call_finished "
                "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
                "framework=%s outcome=failed error=%s",
                request.context.session_id,
                request.context.run_id,
                request.call.name,
                request.context.tool_call_id,
                is_framework_fetch_more,
                type(exc).__name__,
            )
            return ToolFailedOutcome(
                result=ToolResultFailure(
                    ok=False,
                    error=_ERROR_TOOL_RUNTIME_FAILED,
                    message=str(exc),
                    hint=None,
                    meta=None,
                )
            )

    async def _execute_framework_fetch_more(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """执行 framework ``fetch_more`` 工具调用。

        该路径只消费模型按 LLM-facing hint 回传的普通 JSON 参数，不调用
        底层业务 executor；RunEvent facts 仍归属原始业务工具 cursor。

        :param request: Engine 发起的 framework 工具执行请求。
        :returns: 配对当前 framework tool call 的工具 outcome。
        :raises Exception: 不主动抛出异常，失败以 ``ToolFailedOutcome`` 返回。
        """

        parsed = self._parse_framework_fetch_more_request(request)
        if isinstance(parsed, ToolFailedOutcome):
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.tool_runtime.tool_call_finished "
                "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
                "framework=True outcome=failed error=%s",
                request.context.session_id,
                request.context.run_id,
                request.call.name,
                request.context.tool_call_id,
                parsed.result.error,
            )
            return parsed
        fetch_result = await self.fetch_more(parsed)
        if isinstance(fetch_result, ToolFetchMoreFailedResult):
            failed = ToolFailedOutcome(
                result=ToolResultFailure(
                    ok=False,
                    error=fetch_result.error_code,
                    message=fetch_result.message,
                    hint=None,
                    meta=None,
                )
            )
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.tool_runtime.tool_call_finished "
                "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
                "framework=True outcome=failed error=%s denied=%s",
                request.context.session_id,
                request.context.run_id,
                request.call.name,
                request.context.tool_call_id,
                fetch_result.error_code,
                fetch_result.denied,
            )
            _LOGGER.debug(
                "host.tool_runtime.tool_call_finished "
                "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
                "framework=True outcome=failed owner_tool_call_id=%s "
                "cursor_fingerprint=%s error=%s denied=%s event_cursor=%s",
                request.context.session_id,
                request.context.run_id,
                request.call.name,
                request.context.tool_call_id,
                fetch_result.tool_call_id,
                parsed.cursor.fingerprint,
                fetch_result.error_code,
                fetch_result.denied,
                _format_event_cursor(fetch_result.event_cursor),
            )
            return failed
        truncation: ToolTruncationInfo | None = None
        if fetch_result.truncation is not None:
            next_record = self._records_by_cursor.get(
                fetch_result.truncation.value
            )
            if next_record is not None:
                truncation = ToolTruncationInfo(
                    cursor=next_record.cursor,
                    scope_token=next_record.scope_token,
                    scope_hash=next_record.scope_hash,
                    has_more=True,
                    limit=next_record.limit,
                    ttl_seconds=next_record.ttl_seconds,
                )
        completed = ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=fetch_result.value,
                truncation=truncation,
                meta=None,
            )
        )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.tool_runtime.tool_call_finished "
            "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
            "framework=True outcome=completed has_more=%s",
            request.context.session_id,
            request.context.run_id,
            request.call.name,
            request.context.tool_call_id,
            fetch_result.truncation is not None,
        )
        _LOGGER.debug(
            "host.tool_runtime.tool_call_finished "
            "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
            "framework=True outcome=completed owner_tool_call_id=%s "
            "cursor_fingerprint=%s has_more=%s event_cursor=%s",
            request.context.session_id,
            request.context.run_id,
            request.call.name,
            request.context.tool_call_id,
            fetch_result.tool_call_id,
            parsed.cursor.fingerprint,
            fetch_result.truncation is not None,
            _format_event_cursor(fetch_result.event_cursor),
        )
        return completed

    def _parse_framework_fetch_more_request(
        self,
        request: ToolExecutionRequest,
    ) -> ToolFetchMoreRequest | ToolFailedOutcome:
        """解析模型回传的 framework ``fetch_more`` 参数。

        :param request: Engine 工具执行请求。
        :returns: Host ToolRuntime 补读请求；参数非法时返回失败 outcome。
        :raises Exception: 不主动抛出异常。
        """

        cursor_value = request.call.arguments.get(_FETCH_MORE_CURSOR_ARG)
        scope_token = request.call.arguments.get(_FETCH_MORE_SCOPE_TOKEN_ARG)
        limit = request.call.arguments.get(_FETCH_MORE_LIMIT_ARG)
        if not isinstance(cursor_value, str) or not cursor_value:
            return _framework_fetch_more_failed(
                message="cursor is required",
            )
        if not isinstance(scope_token, str) or not scope_token:
            return _framework_fetch_more_failed(
                message="scope_token is required",
            )
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0
        ):
            return _framework_fetch_more_failed(
                message="limit must be a positive integer",
            )
        record = self._records_by_cursor.get(cursor_value)
        cursor_fingerprint = (
            record.cursor_fingerprint
            if record is not None
            else _fingerprint_text(cursor_value)
        )
        return ToolFetchMoreRequest(
            session_id=request.context.session_id,
            run_id=request.context.run_id,
            iteration_id=request.context.iteration_id,
            tool_call_id=(
                record.tool_call_id
                if record is not None
                else request.context.tool_call_id
            ),
            cursor=ToolRuntimeCursor(
                value=cursor_value,
                fingerprint=cursor_fingerprint,
            ),
            scope_token=scope_token,
            limit=(
                limit
                if isinstance(limit, int) and not isinstance(limit, bool)
                else None
            ),
        )

    async def get_tool_fetch_more_handle(
        self,
        request: ToolFetchMoreHandleRequest,
    ) -> ToolFetchMoreHandleResult:
        """按非 EventLog 通道读取受控补读 handle。

        :param request: handle 读取请求。
        :returns: handle 读取结果。
        :raises Exception: 不主动抛出异常。
        """

        record = self._record_by_fingerprint(request.cursor_fingerprint)
        if record is None:
            return _handle_failure(
                request=request,
                error_code=_ERROR_CURSOR_NOT_FOUND,
                message="cursor not found",
                denied=False,
            )
        terminal_cursor = await self._terminal_cursor(record.run_id)
        if terminal_cursor is not None:
            return _handle_failure(
                request=request,
                error_code=_ERROR_RUN_TERMINAL,
                message="run is terminal",
                denied=False,
            )
        denied_reason = _binding_denied_reason(
            record=record,
            session_id=request.session_id,
            run_id=request.run_id,
            tool_call_id=request.tool_call_id,
        )
        if denied_reason is not None:
            await self._append_cursor_denied(
                record=record,
                reason=denied_reason,
                iteration_id=request.iteration_id,
            )
            return _handle_failure(
                request=request,
                error_code=_ERROR_CURSOR_SCOPE_MISMATCH,
                message=denied_reason,
                denied=True,
            )
        now = self.clock()
        if record.expires_at_monotonic <= now:
            self._remove_cursor(record.cursor)
            await self._append_cursor_expired(
                record=record,
                iteration_id=request.iteration_id,
            )
            return _handle_failure(
                request=request,
                error_code=_ERROR_CURSOR_EXPIRED,
                message="cursor expired",
                denied=False,
            )
        handle = ToolFetchMoreHandle(
            session_id=record.session_id,
            run_id=record.run_id,
            tool_call_id=record.tool_call_id,
            cursor=ToolRuntimeCursor(
                value=record.cursor,
                fingerprint=record.cursor_fingerprint,
            ),
            scope_token=record.scope_token,
            expires_at_monotonic=record.expires_at_monotonic,
        )
        return ToolFetchMoreHandleSucceededResult(
            run_id=record.run_id,
            session_id=record.session_id,
            tool_call_id=record.tool_call_id,
            handle=handle,
            expires_at_monotonic=record.expires_at_monotonic,
        )

    async def fetch_more(
        self,
        request: ToolFetchMoreRequest,
    ) -> ToolFetchMoreResult:
        """补读已截断工具结果。

        :param request: 补读请求。
        :returns: 补读结果。
        :raises Exception: append RunEvent 失败时透传。
        """

        async with self._fetch_lock:
            record = self._records_by_cursor.get(request.cursor.value)
            if record is None:
                return _fetch_failure_without_event(
                    request=request,
                    error_code=_ERROR_CURSOR_NOT_FOUND,
                    message="cursor not found",
                    denied=False,
                )
            terminal_cursor = await self._terminal_cursor(record.run_id)
            if terminal_cursor is not None:
                return ToolFetchMoreFailedResult(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    tool_call_id=request.tool_call_id,
                    error_code=_ERROR_RUN_TERMINAL,
                    message="run is terminal",
                    denied=False,
                    event_cursor=None,
                )
            binding_reason = _binding_denied_reason(
                record=record,
                session_id=request.session_id,
                run_id=request.run_id,
                tool_call_id=request.tool_call_id,
            )
            if binding_reason is not None:
                await self._append_cursor_denied(
                    record=record,
                    reason=binding_reason,
                    iteration_id=request.iteration_id,
                )
                return await self._fetch_failure(
                    request=request,
                    record=record,
                    error_code=_ERROR_CURSOR_SCOPE_MISMATCH,
                    message=binding_reason,
                    denied=True,
                    expired=False,
                )
            await self._append_fetch_requested(
                request=request,
                record=record,
            )
            now = self.clock()
            if record.expires_at_monotonic <= now:
                self._remove_cursor(record.cursor)
                await self._append_cursor_expired(
                    record=record,
                    iteration_id=request.iteration_id,
                )
                return await self._fetch_failure(
                    request=request,
                    record=record,
                    error_code=_ERROR_CURSOR_EXPIRED,
                    message="cursor expired",
                    denied=False,
                    expired=True,
                )
            denied_reason = self._scope_denied_reason(
                request=request,
                record=record,
            )
            if denied_reason is not None:
                await self._append_cursor_denied(
                    record=record,
                    reason=denied_reason,
                    iteration_id=request.iteration_id,
                )
                return await self._fetch_failure(
                    request=request,
                    record=record,
                    error_code=_ERROR_CURSOR_SCOPE_MISMATCH,
                    message=denied_reason,
                    denied=True,
                    expired=False,
                )
            limit = _resolve_fetch_limit(request.limit, record.limit)
            chunk_value, chunk_size = _build_chunk(record=record, limit=limit)
            output_value = _apply_chunk_to_template(
                original=record.template,
                field_path=record.field_path,
                chunk=chunk_value,
            )
            new_offset = record.offset + chunk_size
            has_more = new_offset < record.total
            self._remove_cursor(record.cursor)
            next_cursor: ToolRuntimeCursor | None = None
            next_issued_event: ToolCursorIssuedData | None = None
            if has_more:
                cursor_creation = self._store_cursor_from_record(
                    record=record,
                    offset=new_offset,
                    parent_cursor_fingerprint=record.cursor_fingerprint,
                    iteration_id=request.iteration_id,
                )
                next_cursor = ToolRuntimeCursor(
                    value=cursor_creation.record.cursor,
                    fingerprint=cursor_creation.record.cursor_fingerprint,
                )
                next_issued_event = cursor_creation.issued_event
            completed_event = await self._append_fetch_completed(
                request=request,
                record=record,
                next_cursor=next_cursor,
                limit=limit,
                chunk_size=chunk_size,
                has_more=has_more,
                value=output_value,
            )
            if next_issued_event is not None:
                await self._append_cursor_issued(
                    request=request,
                    data=next_issued_event,
                )
            return ToolFetchMoreSucceededResult(
                run_id=request.run_id,
                session_id=request.session_id,
                tool_call_id=request.tool_call_id,
                value=output_value,
                truncation=next_cursor,
                event_cursor=completed_event,
            )

    def _apply_truncation(
        self,
        *,
        request: ToolExecutionRequest,
        value: _TargetValue,
        spec: ToolTruncateSpec | None,
    ) -> _TruncatedValue | None:
        """按显式截断声明截断工具结果。

        :param request: 工具执行请求。
        :param value: 工具原始返回值。
        :param spec: 显式截断声明。
        :returns: 发生截断时返回截断结果，否则返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if spec is None or not spec.enabled or spec.strategy is None:
            return None
        limit = _resolve_spec_limit(spec)
        if limit is None:
            return None
        target = _extract_target(value=value, spec=spec)
        if target is None:
            return None
        if spec.strategy == "text_chars" and isinstance(target.value, str):
            return _truncate_text_chars(value, target, limit)
        if spec.strategy == "text_lines" and isinstance(target.value, str):
            return _truncate_text_lines(value, target, limit)
        if spec.strategy == "list_items" and isinstance(target.value, list):
            return _truncate_list_items(value, target, limit)
        if spec.strategy == "binary_bytes" and isinstance(
            target.value, (bytes, bytearray)
        ):
            return _truncate_binary_bytes(value, target, limit)
        _ = request
        return None

    def _store_cursor(
        self,
        *,
        request: ToolExecutionRequest,
        spec: ToolTruncateSpec | None,
        truncated: _TruncatedValue,
        parent_cursor_fingerprint: str | None,
    ) -> _CursorCreation:
        """创建并保存 cursor。

        :param request: 工具执行请求。
        :param spec: 截断声明。
        :param truncated: 截断结果。
        :param parent_cursor_fingerprint: 父 cursor 指纹。
        :returns: cursor 创建结果。
        :raises RuntimeError: spec 为空或非法时抛出。
        """

        if spec is None or spec.strategy is None:
            raise RuntimeError("truncate spec is required")
        limit = _resolve_spec_limit(spec)
        if limit is None:
            raise RuntimeError("valid truncate limit is required")
        ttl_seconds = _resolve_ttl_seconds(
            spec=spec,
            timeout_seconds=request.context.timeout_seconds,
        )
        return self._create_cursor(
            session_id=request.context.session_id,
            run_id=request.context.run_id,
            iteration_id=request.context.iteration_id,
            tool_call_id=request.context.tool_call_id,
            tool_name=request.call.name,
            strategy=spec.strategy,
            unit=_UNIT_BY_STRATEGY[spec.strategy],
            limit=limit,
            total=truncated.total,
            data=truncated.data,
            offset=truncated.offset,
            template=truncated.template,
            field_path=truncated.field_path,
            parent_cursor_fingerprint=parent_cursor_fingerprint,
            arguments=request.call.arguments,
            ttl_seconds=ttl_seconds,
        )

    def _store_cursor_from_record(
        self,
        *,
        record: _CursorRecord,
        offset: int,
        parent_cursor_fingerprint: str,
        iteration_id: str,
    ) -> _CursorCreation:
        """从旧 cursor 记录派生下一页 cursor。

        :param record: 已消费 cursor 记录。
        :param offset: 下一页起始 offset。
        :param parent_cursor_fingerprint: 父 cursor 指纹。
        :param iteration_id: 派生 cursor 所属 Engine iteration id；通常为
            正在调用 framework ``fetch_more`` 的 iteration。
        :returns: 新 cursor 创建结果。
        :raises Exception: 不主动抛出异常。
        """

        return self._create_cursor(
            session_id=record.session_id,
            run_id=record.run_id,
            iteration_id=iteration_id,
            tool_call_id=record.tool_call_id,
            tool_name=record.tool_name,
            strategy=record.strategy,
            unit=record.unit,
            limit=record.limit,
            total=record.total,
            data=record.data,
            offset=offset,
            template=record.template,
            field_path=record.field_path,
            parent_cursor_fingerprint=parent_cursor_fingerprint,
            arguments=None,
            ttl_seconds=record.ttl_seconds,
            scope_hash=record.scope_hash,
        )

    def _create_cursor(
        self,
        *,
        session_id: str,
        run_id: str,
        iteration_id: str,
        tool_call_id: str,
        tool_name: str,
        strategy: str,
        unit: str,
        limit: int,
        total: int,
        data: _StoredData,
        offset: int,
        template: JsonValue | None,
        field_path: tuple[str, ...] | None,
        parent_cursor_fingerprint: str | None,
        arguments: Mapping[str, JsonValue] | None,
        ttl_seconds: int,
        scope_hash: str | None = None,
    ) -> _CursorCreation:
        """保存 cursor record 并返回签发事实材料。

        :param session_id: 会话 id。
        :param run_id: Run id。
        :param tool_call_id: 原始工具调用 id。
        :param tool_name: 工具名。
        :param strategy: 截断策略。
        :param unit: 截断单位。
        :param limit: 截断上限。
        :param total: 原始总量估计。
        :param data: 原始目标数据。
        :param offset: 下一页起始 offset。
        :param template: wrapper 模板。
        :param field_path: wrapper 目标路径。
        :param parent_cursor_fingerprint: 父 cursor 指纹。
        :param arguments: 工具参数；派生 cursor 可为 ``None``。
        :param ttl_seconds: TTL 秒数。
        :param scope_hash: 已有 scope hash。
        :returns: cursor 创建结果。
        :raises Exception: 不主动抛出异常。
        """

        now = self.clock()
        self._cleanup_expired(now)
        cursor = self.token_generator()
        cursor_fingerprint = _fingerprint_text(cursor)
        resolved_scope_hash = scope_hash
        if resolved_scope_hash is None:
            resolved_scope_hash = _scope_hash(
                tool_name=tool_name,
                arguments=arguments if arguments is not None else {},
            )
        expires_at = now + float(ttl_seconds)
        token = _scope_token(
            cursor=cursor,
            scope_hash=resolved_scope_hash,
            session_id=session_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            created_at_monotonic=now,
        )
        record = _CursorRecord(
            cursor=cursor,
            cursor_fingerprint=cursor_fingerprint,
            scope_token=token,
            scope_hash=resolved_scope_hash,
            session_id=session_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            strategy=strategy,
            unit=unit,
            limit=limit,
            total=total,
            data=data,
            offset=offset,
            template=copy.deepcopy(template),
            field_path=field_path,
            created_at_monotonic=now,
            expires_at_monotonic=expires_at,
            ttl_seconds=ttl_seconds,
            parent_cursor_fingerprint=parent_cursor_fingerprint,
        )
        self._records_by_cursor[cursor] = record
        self._cursor_by_fingerprint[cursor_fingerprint] = cursor
        return _CursorCreation(
            record=record,
            issued_event=ToolCursorIssuedData(
                iteration_id=iteration_id,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                cursor_fingerprint=cursor_fingerprint,
                scope_hash=resolved_scope_hash,
                parent_cursor_fingerprint=parent_cursor_fingerprint,
                offset=offset,
                limit=limit,
                total_estimate=total,
                ttl_seconds=ttl_seconds,
                expires_at_monotonic=expires_at,
                single_use=True,
            ),
        )

    def _record_by_fingerprint(
        self, cursor_fingerprint: str
    ) -> _CursorRecord | None:
        """按 cursor 指纹读取记录。

        :param cursor_fingerprint: cursor 指纹。
        :returns: cursor 记录；不存在返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        cursor = self._cursor_by_fingerprint.get(cursor_fingerprint)
        if cursor is None:
            return None
        return self._records_by_cursor.get(cursor)

    def _remove_cursor(self, cursor: str) -> None:
        """删除 cursor 记录。

        :param cursor: cursor 原文。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        record = self._records_by_cursor.pop(cursor, None)
        if record is not None:
            self._cursor_by_fingerprint.pop(record.cursor_fingerprint, None)

    def _cleanup_expired(self, now: float) -> None:
        """清理已过期 cursor。

        :param now: 当前 monotonic 时间。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        expired = tuple(
            cursor
            for cursor, record in self._records_by_cursor.items()
            if record.expires_at_monotonic <= now
        )
        for cursor in expired:
            self._remove_cursor(cursor)

    def _scope_denied_reason(
        self,
        *,
        request: ToolFetchMoreRequest,
        record: _CursorRecord,
    ) -> str | None:
        """返回 cursor 指纹或 scope token 拒绝原因。

        :param request: 补读请求。
        :param record: cursor 记录。
        :returns: 通过返回 ``None``，否则返回原因。
        :raises Exception: 不主动抛出异常。
        """

        if request.cursor.fingerprint != record.cursor_fingerprint:
            return "cursor fingerprint mismatch"
        if not hmac.compare_digest(request.scope_token, record.scope_token):
            return "cursor scope mismatch"
        return None

    async def _terminal_cursor(self, run_id: str) -> RunEventCursor | None:
        """读取 run 终态 cursor。

        当前内存态 EventStore 需要读取并反向扫描 run 的全量事件，复杂度为
        O(n)。P6 持久化 EventStore 应维护 run 级终态 cursor 索引或缓存。

        :param run_id: Run id。
        :returns: 已终态时返回终态 cursor，否则返回 ``None``。
        :raises TypeError: 终态事件数据类型不一致时抛出。
        """

        events = await self.event_store.list_events(run_id=run_id, after=None)
        for event in reversed(events):
            if terminal_result_from_event(event) is not None:
                return event.cursor
        return None

    async def _append_tool_result_truncated(
        self,
        *,
        request: ToolExecutionRequest,
        record: _CursorRecord,
        value: JsonValue,
        chunk_size: int,
    ) -> RunEventCursor:
        """追加工具结果截断事实。

        :param request: 工具执行请求。
        :param record: cursor 记录。
        :param value: 截断后返回值。
        :param chunk_size: 截断后目标大小。
        :returns: RunEvent cursor。
        :raises Exception: append 失败时透传。
        """

        event = await self._resolve_appender().append(
            RunEventDraft(
                run_id=request.context.run_id,
                session_id=request.context.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_RESULT_TRUNCATED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolResultTruncatedData(
                    iteration_id=request.context.iteration_id,
                    tool_name=record.tool_name,
                    tool_call_id=record.tool_call_id,
                    strategy=record.strategy,
                    limit=record.limit,
                    unit=record.unit,
                    total_estimate=record.total,
                    cursor_fingerprint=record.cursor_fingerprint,
                    ttl_seconds=record.ttl_seconds,
                    has_more=True,
                    value_summary=_value_summary(
                        value=value,
                        unit=record.unit,
                        size=chunk_size,
                        total=record.total,
                    ),
                ),
                source_engine_event_id=None,
            )
        )
        return event.cursor

    async def _append_cursor_issued(
        self,
        *,
        request: ToolExecutionRequest | ToolFetchMoreRequest,
        data: ToolCursorIssuedData,
    ) -> RunEventCursor:
        """追加 cursor 签发事实。

        :param request: 工具执行或补读请求。
        :param data: cursor 签发事实 data。
        :returns: RunEvent cursor。
        :raises Exception: append 失败时透传。
        """

        event = await self._resolve_appender().append(
            RunEventDraft(
                run_id=request.context.run_id
                if isinstance(request, ToolExecutionRequest)
                else request.run_id,
                session_id=request.context.session_id
                if isinstance(request, ToolExecutionRequest)
                else request.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_CURSOR_ISSUED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=data,
                source_engine_event_id=None,
            )
        )
        return event.cursor

    async def _append_fetch_requested(
        self,
        *,
        request: ToolFetchMoreRequest,
        record: _CursorRecord,
    ) -> RunEventCursor:
        """追加补读请求事实。

        :param request: 补读请求。
        :param record: cursor owner 记录。
        :returns: RunEvent cursor。
        :raises Exception: append 失败时透传。
        """

        event = await self._resolve_appender().append(
            RunEventDraft(
                run_id=record.run_id,
                session_id=record.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_FETCH_MORE_REQUESTED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolFetchMoreRequestedData(
                    iteration_id=request.iteration_id,
                    tool_call_id=record.tool_call_id,
                    cursor_fingerprint=record.cursor_fingerprint,
                    requested_limit=request.limit,
                ),
                source_engine_event_id=None,
            )
        )
        return event.cursor

    async def _append_fetch_completed(
        self,
        *,
        request: ToolFetchMoreRequest,
        record: _CursorRecord,
        next_cursor: ToolRuntimeCursor | None,
        limit: int,
        chunk_size: int,
        has_more: bool,
        value: JsonValue,
    ) -> RunEventCursor:
        """追加补读完成事实。

        :param request: 补读请求。
        :param record: 已消费 cursor 记录。
        :param next_cursor: 下一页 cursor。
        :param limit: 实际读取 limit。
        :param chunk_size: 本次返回目标大小。
        :param has_more: 是否仍有剩余。
        :param value: 本次返回值。
        :returns: RunEvent cursor。
        :raises Exception: append 失败时透传。
        """

        event = await self._resolve_appender().append(
            RunEventDraft(
                run_id=record.run_id,
                session_id=record.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_FETCH_MORE_COMPLETED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolFetchMoreCompletedData(
                    iteration_id=request.iteration_id,
                    tool_name=record.tool_name,
                    tool_call_id=record.tool_call_id,
                    consumed_cursor_fingerprint=record.cursor_fingerprint,
                    next_cursor_fingerprint=(
                        next_cursor.fingerprint if next_cursor is not None else None
                    ),
                    limit=limit,
                    chunk_size=chunk_size,
                    has_more=has_more,
                    value_summary=_value_summary(
                        value=value,
                        unit=record.unit,
                        size=chunk_size,
                        total=record.total,
                    ),
                ),
                source_engine_event_id=None,
            )
        )
        return event.cursor

    async def _append_cursor_expired(
        self,
        *,
        record: _CursorRecord,
        iteration_id: str,
    ) -> RunEventCursor:
        """追加 cursor 过期事实。

        :param record: cursor 记录。
        :param iteration_id: 触发过期检测的 Engine iteration id；语义上属于
            正在调用 framework ``fetch_more`` 或 handle 读取路径的 iteration。
        :returns: RunEvent cursor。
        :raises Exception: append 失败时透传。
        """

        event = await self._resolve_appender().append(
            RunEventDraft(
                run_id=record.run_id,
                session_id=record.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_CURSOR_EXPIRED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolCursorExpiredData(
                    iteration_id=iteration_id,
                    tool_call_id=record.tool_call_id,
                    cursor_fingerprint=record.cursor_fingerprint,
                    expired_at_monotonic=record.expires_at_monotonic,
                ),
                source_engine_event_id=None,
            )
        )
        return event.cursor

    async def _append_cursor_denied(
        self,
        *,
        record: _CursorRecord,
        reason: str,
        iteration_id: str,
    ) -> RunEventCursor:
        """追加 cursor 拒绝事实。

        :param record: cursor owner 记录。
        :param reason: 拒绝原因。
        :param iteration_id: 触发拒绝检测的 Engine iteration id。
        :returns: RunEvent cursor。
        :raises Exception: append 失败时透传。
        """

        event = await self._resolve_appender().append(
            RunEventDraft(
                run_id=record.run_id,
                session_id=record.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_CURSOR_DENIED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolCursorDeniedData(
                    iteration_id=iteration_id,
                    tool_call_id=record.tool_call_id,
                    cursor_fingerprint=record.cursor_fingerprint,
                    reason=reason,
                ),
                source_engine_event_id=None,
            )
        )
        return event.cursor

    async def _fetch_failure(
        self,
        *,
        request: ToolFetchMoreRequest,
        record: _CursorRecord,
        error_code: str,
        message: str,
        denied: bool,
        expired: bool,
    ) -> ToolFetchMoreFailedResult:
        """追加补读失败事实并返回失败结果。

        :param request: 补读请求。
        :param record: cursor owner 记录。
        :param error_code: 失败错误码。
        :param message: 人类可读错误描述。
        :param denied: 是否为权限拒绝。
        :param expired: 是否为过期。
        :returns: 失败结果。
        :raises Exception: append 失败时透传。
        """

        event = await self._resolve_appender().append(
            RunEventDraft(
                run_id=record.run_id,
                session_id=record.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_FETCH_MORE_FAILED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolFetchMoreFailedData(
                    iteration_id=request.iteration_id,
                    tool_call_id=record.tool_call_id,
                    cursor_fingerprint=record.cursor_fingerprint,
                    error_code=error_code,
                    message=message,
                    denied=denied,
                    expired=expired,
                ),
                source_engine_event_id=None,
            )
        )
        return ToolFetchMoreFailedResult(
            run_id=request.run_id,
            session_id=request.session_id,
            tool_call_id=request.tool_call_id,
            error_code=error_code,
            message=message,
            denied=denied,
            event_cursor=event.cursor,
        )


def _handle_failure(
    *,
    request: ToolFetchMoreHandleRequest,
    error_code: str,
    message: str,
    denied: bool,
) -> ToolFetchMoreHandleFailedResult:
    """构造 handle 读取失败结果。

    :param request: handle 读取请求。
    :param error_code: 失败错误码。
    :param message: 人类可读错误描述。
    :param denied: 是否为权限拒绝。
    :returns: handle 读取失败结果。
    :raises Exception: 不主动抛出异常。
    """

    return ToolFetchMoreHandleFailedResult(
        run_id=request.run_id,
        session_id=request.session_id,
        tool_call_id=request.tool_call_id,
        error_code=error_code,
        message=message,
        denied=denied,
    )


def _fetch_failure_without_event(
    *,
    request: ToolFetchMoreRequest,
    error_code: str,
    message: str,
    denied: bool,
) -> ToolFetchMoreFailedResult:
    """构造不写 RunEvent 的补读失败结果。

    该 helper 只用于 cursor record 不存在等无法可信归属 owner run 的场景，
    避免按请求声称的 run 写入伪造事实。

    :param request: 补读请求。
    :param error_code: 失败错误码。
    :param message: 人类可读错误描述。
    :param denied: 是否为权限拒绝。
    :returns: 补读失败结果。
    :raises Exception: 不主动抛出异常。
    """

    return ToolFetchMoreFailedResult(
        run_id=request.run_id,
        session_id=request.session_id,
        tool_call_id=request.tool_call_id,
        error_code=error_code,
        message=message,
        denied=denied,
        event_cursor=None,
    )


def _format_event_cursor(cursor: RunEventCursor | None) -> int | None:
    """返回日志用 RunEvent cursor 序号。

    :param cursor: RunEvent cursor；``None`` 表示本次没有追加事件。
    :returns: cursor 序号或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if cursor is None:
        return None
    return cursor.sequence


def _format_field_path(field_path: tuple[str, ...] | None) -> str | None:
    """返回日志用截断字段路径。

    :param field_path: 截断目标字段路径。
    :returns: 点号连接的字段路径；无路径返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if field_path is None:
        return None
    return ".".join(field_path)


def _tool_outcome_name(outcome: ToolExecutionOutcome) -> str:
    """返回日志用工具执行 outcome 名称。

    :param outcome: 工具执行 outcome。
    :returns: ``completed``、``failed`` 或 ``awaiting``。
    :raises Exception: 不主动抛出异常。
    """

    # invariant 校验：ToolExecutionOutcome 为封闭联合，按构造类型枚举即可，无需 fallback。
    if isinstance(outcome, ToolCompletedOutcome):
        return "completed"
    if isinstance(outcome, ToolFailedOutcome):
        return "failed"
    return "awaiting"


def _framework_fetch_more_failed(*, message: str) -> ToolFailedOutcome:
    """构造 framework ``fetch_more`` 参数错误 outcome。

    :param message: 人类可读错误描述。
    :returns: 工具失败 outcome。
    :raises Exception: 不主动抛出异常。
    """

    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error=_ERROR_INVALID_FETCH_MORE_ARGS,
            message=message,
            hint=None,
            meta=None,
        )
    )


def _binding_denied_reason(
    *,
    record: _CursorRecord,
    session_id: str,
    run_id: str,
    tool_call_id: str,
) -> str | None:
    """校验 cursor 与请求的 session / run / 原始 tool_call 绑定。

    :param record: cursor 记录。
    :param session_id: 请求会话 id。
    :param run_id: 请求 Run id。
    :param tool_call_id: 请求原始工具调用 id。
    :returns: 通过返回 ``None``，否则返回拒绝原因。
    :raises Exception: 不主动抛出异常。
    """

    if record.session_id != session_id:
        return "cursor session mismatch"
    if record.run_id != run_id:
        return "cursor run mismatch"
    if record.tool_call_id != tool_call_id:
        return "cursor tool_call mismatch"
    return None


def _resolve_spec_limit(spec: ToolTruncateSpec) -> int | None:
    """解析截断声明中的有效 limit。

    :param spec: 截断声明。
    :returns: 有效正整数 limit；非法返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if spec.strategy is None:
        return None
    limit_key = _LIMIT_BY_STRATEGY.get(spec.strategy)
    if limit_key is None:
        return None
    limit = spec.limits.get(limit_key)
    if limit is None:
        return None
    if limit <= 0:
        return None
    return limit


def _resolve_ttl_seconds(
    *,
    spec: ToolTruncateSpec,
    timeout_seconds: float | None,
) -> int:
    """解析 cursor TTL 秒数。

    :param spec: 截断声明。
    :param timeout_seconds: 工具执行上下文超时时间。
    :returns: 正整数 TTL 秒数。
    :raises Exception: 不主动抛出异常。
    """

    if spec.ttl_seconds is not None and spec.ttl_seconds > 0:
        return spec.ttl_seconds
    if timeout_seconds is not None and timeout_seconds > 0:
        return max(1, int(timeout_seconds))
    return _DEFAULT_CURSOR_TTL_SECONDS


def _extract_target(
    *,
    value: _TargetValue,
    spec: ToolTruncateSpec,
) -> _TruncateTarget | None:
    """按严格显式目标规则提取截断目标。

    :param value: 工具原始返回值。
    :param spec: 截断声明。
    :returns: 目标值与路径；不满足规则时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, (str, list, bytes, bytearray)):
        return _TruncateTarget(value=value, field_path=None)
    if not isinstance(value, Mapping):
        return None
    field_path = _explicit_field_path(spec)
    if field_path is None:
        return None
    target = _lookup_path(value=value, field_path=field_path)
    if target is None:
        return None
    return _TruncateTarget(value=target, field_path=field_path)


def _explicit_field_path(spec: ToolTruncateSpec) -> tuple[str, ...] | None:
    """返回显式字段路径。

    :param spec: 截断声明。
    :returns: 字段路径；未声明返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if spec.field_path is not None and len(spec.field_path) > 0:
        return spec.field_path
    if spec.target_field is not None and spec.target_field:
        return (spec.target_field,)
    return None


def _lookup_path(
    *,
    value: Mapping[str, JsonValue],
    field_path: tuple[str, ...],
) -> JsonValue | None:
    """从 wrapper dict 中读取目标路径。

    :param value: wrapper 值。
    :param field_path: 字段路径。
    :returns: 命中值；路径不成立返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    current: JsonValue = value
    for key in field_path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _truncate_text_chars(
    original: _TargetValue,
    target: _TruncateTarget,
    limit: int,
) -> _TruncatedValue | None:
    """按字符数截断文本。

    :param original: 原始返回值。
    :param target: 截断目标。
    :param limit: 截断上限。
    :returns: 截断结果；未超限返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    text = cast(str, target.value)
    total = len(text)
    if total <= limit:
        return None
    chunk = text[:limit]
    return _TruncatedValue(
        value=_apply_chunk_to_template(original, target.field_path, chunk),
        data=text,
        offset=len(chunk),
        total=total,
        chunk_size=len(chunk),
        template=cast(JsonValue, original) if target.field_path is not None else None,
        field_path=target.field_path,
    )


def _truncate_text_lines(
    original: _TargetValue,
    target: _TruncateTarget,
    limit: int,
) -> _TruncatedValue | None:
    """按行数截断文本。

    :param original: 原始返回值。
    :param target: 截断目标。
    :param limit: 截断上限。
    :returns: 截断结果；未超限返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    lines = tuple(cast(str, target.value).splitlines(keepends=True))
    total = len(lines)
    if total <= limit:
        return None
    chunk_lines = lines[:limit]
    chunk = "".join(chunk_lines)
    return _TruncatedValue(
        value=_apply_chunk_to_template(original, target.field_path, chunk),
        data=lines,
        offset=len(chunk_lines),
        total=total,
        chunk_size=len(chunk_lines),
        template=cast(JsonValue, original) if target.field_path is not None else None,
        field_path=target.field_path,
    )


def _truncate_list_items(
    original: _TargetValue,
    target: _TruncateTarget,
    limit: int,
) -> _TruncatedValue | None:
    """按列表元素数截断。

    :param original: 原始返回值。
    :param target: 截断目标。
    :param limit: 截断上限。
    :returns: 截断结果；未超限返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    items = cast(list[JsonValue], target.value)
    total = len(items)
    if total <= limit:
        return None
    chunk = items[:limit]
    return _TruncatedValue(
        value=_apply_chunk_to_template(original, target.field_path, chunk),
        data=list(items),
        offset=len(chunk),
        total=total,
        chunk_size=len(chunk),
        template=cast(JsonValue, original) if target.field_path is not None else None,
        field_path=target.field_path,
    )


def _truncate_binary_bytes(
    original: _TargetValue,
    target: _TruncateTarget,
    limit: int,
) -> _TruncatedValue | None:
    """按字节数截断二进制，并返回 base64 字符串块。

    :param original: 原始返回值。
    :param target: 截断目标。
    :param limit: 截断上限。
    :returns: 截断结果；未超限返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    binary_value = target.value
    if isinstance(binary_value, bytearray):
        data = bytes(binary_value)
    elif isinstance(binary_value, bytes):
        data = binary_value
    else:
        return None
    total = len(data)
    if total <= limit:
        return None
    chunk = data[:limit]
    encoded = _encode_bytes(chunk)
    return _TruncatedValue(
        value=_apply_chunk_to_template(original, target.field_path, encoded),
        data=data,
        offset=len(chunk),
        total=total,
        chunk_size=len(chunk),
        template=cast(JsonValue, original) if target.field_path is not None else None,
        field_path=target.field_path,
    )


def _build_chunk(
    *,
    record: _CursorRecord,
    limit: int,
) -> tuple[JsonValue, int]:
    """从 cursor 记录取出下一页数据块。

    :param record: cursor 记录。
    :param limit: 本次读取 limit。
    :returns: 块值与块大小。
    :raises Exception: 不主动抛出异常。
    """

    if record.strategy == "text_chars" and isinstance(record.data, str):
        chunk = record.data[record.offset : record.offset + limit]
        return chunk, len(chunk)
    if record.strategy == "text_lines" and isinstance(record.data, tuple):
        lines = record.data[record.offset : record.offset + limit]
        return "".join(lines), len(lines)
    if record.strategy == "binary_bytes" and isinstance(record.data, bytes):
        chunk_bytes = record.data[record.offset : record.offset + limit]
        return _encode_bytes(chunk_bytes), len(chunk_bytes)
    if record.strategy == "list_items" and isinstance(record.data, list):
        chunk_items = record.data[record.offset : record.offset + limit]
        return chunk_items, len(chunk_items)
    return None, 0


def _apply_chunk_to_template(
    original: _TargetValue | JsonValue | None,
    field_path: tuple[str, ...] | None,
    chunk: JsonValue,
) -> JsonValue:
    """将块值写回 wrapper 模板。

    :param original: 原始返回值或模板。
    :param field_path: 目标字段路径。
    :param chunk: 块值。
    :returns: 替换后的 JSON 值。
    :raises Exception: 不主动抛出异常。
    """

    if field_path is None:
        return chunk
    if not isinstance(original, Mapping):
        return chunk
    return _replace_path(value=original, field_path=field_path, chunk=chunk)


def _replace_path(
    *,
    value: Mapping[str, JsonValue],
    field_path: tuple[str, ...],
    chunk: JsonValue,
) -> JsonValue:
    """递归替换 wrapper dict 中的目标路径。

    :param value: wrapper dict。
    :param field_path: 字段路径。
    :param chunk: 块值。
    :returns: 替换后的 JSON 对象。
    :raises RuntimeError: 中间路径不匹配时抛出。
    """

    key = field_path[0]
    copied: dict[str, JsonValue] = dict(value)
    if len(field_path) == 1:
        copied[key] = chunk
        return copied
    child = copied.get(key)
    if isinstance(child, Mapping):
        copied[key] = _replace_path(
            value=child,
            field_path=field_path[1:],
            chunk=chunk,
        )
        return copied
    raise RuntimeError("truncate field_path does not match wrapper template")


def _resolve_fetch_limit(requested: int | None, record_limit: int) -> int:
    """解析补读实际 limit。

    :param requested: 调用方请求 limit。
    :param record_limit: 原始截断上限。
    :returns: 实际读取 limit。
    :raises Exception: 不主动抛出异常。
    """

    if requested is not None and requested > 0:
        return min(requested, record_limit)
    return record_limit


def _scope_hash(
    *,
    tool_name: str,
    arguments: Mapping[str, JsonValue],
) -> str:
    """生成工具名与参数对应的 scope hash。

    :param tool_name: 工具名。
    :param arguments: 工具参数。
    :returns: SHA-256 十六进制摘要。
    :raises Exception: 不主动抛出异常。
    """

    payload: dict[str, JsonValue] = {
        "tool": tool_name,
        "arguments": arguments,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _scope_token(
    *,
    cursor: str,
    scope_hash: str,
    session_id: str,
    run_id: str,
    tool_call_id: str,
    created_at_monotonic: float,
) -> str:
    """生成 scope token。

    :param cursor: cursor 原文。
    :param scope_hash: scope hash。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :param tool_call_id: 原始工具调用 id。
    :param created_at_monotonic: 创建时间。
    :returns: SHA-256 十六进制摘要。
    :raises Exception: 不主动抛出异常。
    """

    payload = {
        "cursor": cursor,
        "scope_hash": scope_hash,
        "session_id": session_id,
        "run_id": run_id,
        "tool_call_id": tool_call_id,
        "created_at": created_at_monotonic,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fingerprint_text(value: str) -> str:
    """生成短指纹。

    :param value: 原文。
    :returns: 短 SHA-256 指纹。
    :raises Exception: 不主动抛出异常。
    """

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[
        :_FINGERPRINT_LENGTH
    ]


def _fingerprint_value(value: JsonValue) -> str:
    """生成 JSON 值短指纹。

    :param value: JSON 值。
    :returns: 短 SHA-256 指纹。
    :raises Exception: 不主动抛出异常。
    """

    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[
        :_FINGERPRINT_LENGTH
    ]


def _value_summary(
    *,
    value: JsonValue,
    unit: str,
    size: int,
    total: int,
) -> ToolValueSizeSummary:
    """构造值大小摘要。

    :param value: JSON 值。
    :param unit: 摘要单位。
    :param size: 当前块大小。
    :param total: 原始总量估计。
    :returns: 值大小摘要。
    :raises Exception: 不主动抛出异常。
    """

    return ToolValueSizeSummary(
        unit=unit,
        size=size,
        total_estimate=total,
        fingerprint=_fingerprint_value(value),
    )


def _encode_bytes(value: bytes) -> str:
    """将二进制块编码为 base64 字符串。

    :param value: 二进制块。
    :returns: base64 字符串。
    :raises Exception: 不主动抛出异常。
    """

    return base64.b64encode(value).decode("ascii")


__all__: list[str] = []
