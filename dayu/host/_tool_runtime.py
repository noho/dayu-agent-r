"""Host 内部 ToolRuntime 最小实现。

本模块只服务 P2 的工具执行代理、schema-driven 截断、cursor 生命周期与
RunEvent 事实写入。它不是 Host public surface，也不实现完整 ToolRegistry。
"""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, TypeAlias, cast

from dayu.contracts import JsonValue, ToolExecutor, ToolTruncateSpec
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
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

_DEFAULT_CURSOR_TTL_SECONDS: int = 300
_ERROR_CURSOR_NOT_FOUND: str = "cursor_not_found"
_ERROR_CURSOR_EXPIRED: str = "cursor_expired"
_ERROR_CURSOR_SCOPE_MISMATCH: str = "cursor_scope_mismatch"
_ERROR_RUN_TERMINAL: str = "run_terminal"
_ERROR_TOOL_RUNTIME_FAILED: str = "tool_runtime_failed"
_FINGERPRINT_LENGTH: int = 16
_TOKEN_BYTES: int = 32
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


@dataclass(slots=True)
class InMemoryToolRuntime:
    """单进程内存态 ToolRuntime。

    :param executor: 底层业务 ToolExecutor。
    :param event_store: Host RunEventStore。
    :param truncate_specs: 按工具名注入的显式截断声明。
    :param clock: monotonic clock。
    :param token_generator: cursor 原文生成器。
    """

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

    async def execute_tool_call(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """执行底层工具并在成功结果上应用截断。

        :param request: 工具执行请求。
        :returns: 截断后的工具执行 outcome。
        :raises Exception: 不主动抛出异常，ToolRuntime 自身异常转失败 outcome。
        """

        try:
            outcome = await self.executor.execute(request)
            if not isinstance(outcome, ToolCompletedOutcome):
                return outcome
            spec = self.truncate_specs.get(request.call.name)
            truncated = self._apply_truncation(
                request=request,
                value=cast(_TargetValue, outcome.result.value),
                spec=spec,
            )
            if truncated is None:
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
            return ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value=truncated.value,
                    truncation=ToolTruncationInfo(
                        scope_token="",
                        scope_hash=cursor_creation.record.scope_hash,
                        has_more=True,
                        ttl_seconds=cursor_creation.record.ttl_seconds,
                    ),
                    meta=outcome.result.meta,
                )
            )
        except Exception as exc:
            return ToolFailedOutcome(
                result=ToolResultFailure(
                    ok=False,
                    error=_ERROR_TOOL_RUNTIME_FAILED,
                    message=str(exc),
                    hint=None,
                    meta=None,
                )
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
            await self._append_cursor_expired(record=record)
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
                await self._append_cursor_expired(record=record)
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
    ) -> _CursorCreation:
        """从旧 cursor 记录派生下一页 cursor。

        :param record: 已消费 cursor 记录。
        :param offset: 下一页起始 offset。
        :param parent_cursor_fingerprint: 父 cursor 指纹。
        :returns: 新 cursor 创建结果。
        :raises Exception: 不主动抛出异常。
        """

        return self._create_cursor(
            session_id=record.session_id,
            run_id=record.run_id,
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

        event = await self.event_store.append(
            RunEventDraft(
                run_id=request.context.run_id,
                session_id=request.context.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_RESULT_TRUNCATED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolResultTruncatedData(
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

        event = await self.event_store.append(
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

        event = await self.event_store.append(
            RunEventDraft(
                run_id=record.run_id,
                session_id=record.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_FETCH_MORE_REQUESTED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolFetchMoreRequestedData(
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

        event = await self.event_store.append(
            RunEventDraft(
                run_id=record.run_id,
                session_id=record.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_FETCH_MORE_COMPLETED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolFetchMoreCompletedData(
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
    ) -> RunEventCursor:
        """追加 cursor 过期事实。

        :param record: cursor 记录。
        :returns: RunEvent cursor。
        :raises Exception: append 失败时透传。
        """

        event = await self.event_store.append(
            RunEventDraft(
                run_id=record.run_id,
                session_id=record.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_CURSOR_EXPIRED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolCursorExpiredData(
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
    ) -> RunEventCursor:
        """追加 cursor 拒绝事实。

        :param record: cursor owner 记录。
        :param reason: 拒绝原因。
        :returns: RunEvent cursor。
        :raises Exception: append 失败时透传。
        """

        event = await self.event_store.append(
            RunEventDraft(
                run_id=record.run_id,
                session_id=record.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_CURSOR_DENIED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolCursorDeniedData(
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

        event = await self.event_store.append(
            RunEventDraft(
                run_id=record.run_id,
                session_id=record.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.TOOL_FETCH_MORE_FAILED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=ToolFetchMoreFailedData(
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
