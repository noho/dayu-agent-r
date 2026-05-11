"""Host 私有工具结果截断管理器。

本模块承载 ToolRuntime 内部的截断状态机、短期 cursor registry、
scope/binding 校验、limit clamp、chunk 构造与 single-use 消费。它不定义
Host RunEvent，也不属于 public Host contract；对 Engine 来说，截断和补读
只表现为普通工具调用的成功或失败结果。
"""

from __future__ import annotations

import _thread
import asyncio
import base64
import copy
import hashlib
import hmac
import json
import math
import secrets
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias, cast

from dayu.contracts import JsonValue, ToolTruncateSpec
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultSuccess,
)
from dayu.host._tool_result_truncation import (
    ToolResultTruncationHint,
    inject_truncation_hint,
)

_DEFAULT_CURSOR_TTL_SECONDS: int = 300
_ERROR_CURSOR_NOT_FOUND: str = "cursor_not_found"
_ERROR_CURSOR_EXPIRED: str = "cursor_expired"
_ERROR_CURSOR_SCOPE_MISMATCH: str = "cursor_scope_mismatch"
_ERROR_RUN_TERMINAL: str = "run_terminal"
_ERROR_INVALID_FETCH_MORE_ARGS: str = "invalid_fetch_more_args"
_ERROR_UNSUPPORTED_TRUNCATE_STRATEGY: str = "unsupported_truncate_strategy"
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


class RuntimeClock(Protocol):
    """截断管理器使用的 monotonic clock 协议。"""

    def __call__(self) -> float:
        """返回当前 monotonic 时间。

        :returns: 当前 monotonic 秒数。
        :raises Exception: 具体 clock 失败时透传。
        """
        ...


class RuntimeTokenGenerator(Protocol):
    """截断管理器 cursor 原文生成器协议。"""

    def __call__(self) -> str:
        """生成新的 cursor 原文。

        :returns: cursor 原文。
        :raises Exception: 具体生成器失败时透传。
        """
        ...


class RuntimeTerminalChecker(Protocol):
    """Host 私有 run 终态检查协议。"""

    async def is_terminal(self, run_id: str) -> bool:
        """判断 run 是否已经终态。

        :param run_id: Run id。
        :returns: 已终态返回 ``True``。
        :raises Exception: 读取终态状态失败时透传。
        """
        ...


class RuntimeOwnerVerifier(Protocol):
    """截断状态 mutation 前的 attempt owner 校验协议。"""

    async def verify_active_owner(self, *, run_id: str) -> None:
        """校验当前 owner 仍可写指定 run。

        :param run_id: Run id。
        :returns: 无返回值。
        :raises Exception: owner 失效或底层校验失败时透传。
        """
        ...


@dataclass(frozen=True, slots=True)
class _TruncateTarget:
    """已解析的截断目标。

    :param value: 待截断的目标值。
    :param field_path: wrapper dict 中的目标路径；顶层值为 ``None``。
    """

    value: _TargetValue
    field_path: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class _TruncatedValue:
    """截断后的值与 cursor 记录材料。

    :param value: 返回给 LLM 的截断 JSON 值。
    :param data: 原始目标数据。
    :param offset: 下一页起始位置。
    :param total: 原始总量估计。
    :param chunk_size: 当前块大小。
    :param template: wrapper 模板；顶层值为 ``None``。
    :param field_path: wrapper dict 中的目标路径；顶层值为 ``None``。
    """

    value: JsonValue
    data: _StoredData
    offset: int
    total: int
    chunk_size: int
    template: JsonValue | None
    field_path: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class _RuntimeCursorRecord:
    """Host 私有内存态 cursor 记录。

    :param cursor: cursor 原文。
    :param cursor_fingerprint: cursor 短指纹。
    :param scope_token: 单次 scope 校验 token。
    :param scope_hash: scope 内容 hash。
    :param session_id: 所属 session id。
    :param run_id: 所属 Run id。
    :param tool_call_id: 原始业务工具调用 id。
    :param tool_name: 原始业务工具名。
    :param strategy: 截断策略。
    :param unit: 截断单位。
    :param limit: 默认补读上限。
    :param total: 原始总量估计。
    :param data: 原始目标数据。
    :param offset: 下一页起始位置。
    :param template: wrapper 模板；顶层值为 ``None``。
    :param field_path: wrapper dict 中的目标路径；顶层值为 ``None``。
    :param created_at_monotonic: 创建时间。
    :param expires_at_monotonic: 过期时间。
    :param ttl_seconds: TTL 秒数。
    """

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


@dataclass(frozen=True, slots=True)
class _ParsedReadRequest:
    """已解析的补读请求。

    :param request: Engine 工具执行请求。
    :param cursor: cursor 原文。
    :param cursor_fingerprint: cursor 短指纹。
    :param scope_token: scope 校验 token。
    :param limit: 可选补读上限。
    """

    request: ToolExecutionRequest
    cursor: str
    cursor_fingerprint: str
    scope_token: str
    limit: int | None


@dataclass(frozen=True, slots=True)
class _ChunkBuildResult:
    """补读 chunk 构造结果。

    :param value: 返回给模型的块值。
    :param size: 本次推进的单位数量。
    """

    value: JsonValue
    size: int


@dataclass(slots=True, kw_only=True)
class RuntimeTruncateManager:
    """Host 私有截断与补读状态管理器。

    :param terminal_checker: Host 私有 run 终态检查端口。
    :param clock: monotonic clock。
    :param token_generator: cursor 原文生成器。
    """

    terminal_checker: RuntimeTerminalChecker
    clock: RuntimeClock = time.monotonic
    token_generator: RuntimeTokenGenerator = lambda: secrets.token_hex(_TOKEN_BYTES)
    _records_by_cursor: dict[str, _RuntimeCursorRecord] = field(
        default_factory=dict,
        init=False,
    )
    _cursor_by_fingerprint: dict[str, str] = field(
        default_factory=dict,
        init=False,
    )
    _state_lock: _thread.RLock = field(
        default_factory=threading.RLock,
        init=False,
    )
    _read_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def apply_truncation(
        self,
        *,
        request: ToolExecutionRequest,
        outcome: ToolCompletedOutcome,
        spec: ToolTruncateSpec | None,
    ) -> ToolCompletedOutcome:
        """对成功工具结果做可选截断。

        :param request: 原始工具执行请求。
        :param outcome: 底层业务工具成功结果。
        :param spec: 工具声明的截断配置。
        :returns: 原样或已截断的成功 outcome。
        :raises RuntimeError: cursor 创建所需截断声明不完整时抛出。
        """

        truncated = self._apply_truncation(
            value=cast(_TargetValue, outcome.result.value),
            spec=spec,
        )
        if truncated is None:
            return outcome
        with self._state_lock:
            record = self._build_cursor(
                request=request,
                spec=spec,
                truncated=truncated,
            )
            self._commit_cursor(record)
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=inject_truncation_hint(
                    value=truncated.value,
                    hint=ToolResultTruncationHint(
                        cursor=record.cursor,
                        scope_token=record.scope_token,
                        has_more=True,
                        limit=record.limit,
                        ttl_seconds=record.ttl_seconds,
                    ),
                ),
                meta=outcome.result.meta,
            )
        )

    async def fetch_more(
        self,
        request: ToolExecutionRequest,
        *,
        owner_verifier: RuntimeOwnerVerifier | None = None,
    ) -> ToolExecutionOutcome:
        """执行 Host 私有 ``fetch_more`` framework 工具。

        :param request: Engine 发起的普通工具执行请求。
        :param owner_verifier: durable 路径在 cursor registry mutation 前
            二次校验 attempt owner；非 durable 路径为 ``None``。
        :returns: 普通工具执行 outcome。
        :raises Exception: run 终态检查失败时透传。
        """

        async with self._read_lock:
            parsed = self._parse_fetch_request(request)
            if isinstance(parsed, ToolFailedOutcome):
                return parsed
            with self._state_lock:
                record = self._records_by_cursor.get(parsed.cursor)
            if record is None:
                return _failed_outcome(
                    error_code=_ERROR_CURSOR_NOT_FOUND,
                    message="cursor not found",
                )
            if await self.terminal_checker.is_terminal(record.run_id):
                return _failed_outcome(
                    error_code=_ERROR_RUN_TERMINAL,
                    message="run is terminal",
                )
            if owner_verifier is not None:
                await owner_verifier.verify_active_owner(
                    run_id=parsed.request.context.run_id
                )
            binding_reason = _binding_denied_reason(
                record=record,
                session_id=parsed.request.context.session_id,
                run_id=parsed.request.context.run_id,
            )
            if binding_reason is not None:
                return _failed_outcome(
                    error_code=_ERROR_CURSOR_SCOPE_MISMATCH,
                    message=binding_reason,
                )
            now = self.clock()
            if record.expires_at_monotonic <= now:
                if owner_verifier is not None:
                    await owner_verifier.verify_active_owner(
                        run_id=parsed.request.context.run_id
                    )
                with self._state_lock:
                    self._remove_cursor(record.cursor)
                return _failed_outcome(
                    error_code=_ERROR_CURSOR_EXPIRED,
                    message="cursor expired",
                )
            denied_reason = _scope_denied_reason(parsed=parsed, record=record)
            if denied_reason is not None:
                return _failed_outcome(
                    error_code=_ERROR_CURSOR_SCOPE_MISMATCH,
                    message=denied_reason,
                )
            limit = _resolve_fetch_limit(parsed.limit, record.limit)
            chunk = _build_chunk(record=record, limit=limit)
            if chunk is None:
                with self._state_lock:
                    self._remove_cursor(record.cursor)
                return _failed_outcome(
                    error_code=_ERROR_UNSUPPORTED_TRUNCATE_STRATEGY,
                    message=f"unsupported truncate strategy: {record.strategy}",
                )
            output_value = _apply_chunk_to_template(
                original=record.template,
                field_path=record.field_path,
                chunk=chunk.value,
            )
            new_offset = record.offset + chunk.size
            has_more = new_offset < record.total
            next_hint: ToolResultTruncationHint | None = None
            next_record: _RuntimeCursorRecord | None = None
            if has_more:
                next_record = self._build_cursor_from_record(
                    record=record,
                    offset=new_offset,
                )
                next_hint = ToolResultTruncationHint(
                    cursor=next_record.cursor,
                    scope_token=next_record.scope_token,
                    has_more=True,
                    limit=next_record.limit,
                    ttl_seconds=next_record.ttl_seconds,
                )
            # mutation 紧邻第二次 owner 校验，避免旧 owner 在 await 之后
            # 消费旧 cursor 或提交 next cursor。
            if owner_verifier is not None:
                await owner_verifier.verify_active_owner(
                    run_id=parsed.request.context.run_id
                )
            with self._state_lock:
                if next_record is not None:
                    self._commit_cursor(next_record)
                self._remove_cursor(record.cursor)
            return ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value=(
                        output_value
                        if next_hint is None
                        else inject_truncation_hint(
                            value=output_value,
                            hint=next_hint,
                        )
                    ),
                    meta=None,
                )
            )

    def _parse_fetch_request(
        self,
        request: ToolExecutionRequest,
    ) -> _ParsedReadRequest | ToolFailedOutcome:
        """解析模型回传的 framework 工具参数。

        :param request: Engine 工具执行请求。
        :returns: 解析后的补读请求；参数非法时返回失败 outcome。
        :raises Exception: 不主动抛出异常。
        """

        cursor_value = request.call.arguments.get(_FETCH_MORE_CURSOR_ARG)
        scope_token = request.call.arguments.get(_FETCH_MORE_SCOPE_TOKEN_ARG)
        limit = request.call.arguments.get(_FETCH_MORE_LIMIT_ARG)
        if not isinstance(cursor_value, str) or not cursor_value:
            return _failed_outcome(
                error_code=_ERROR_INVALID_FETCH_MORE_ARGS,
                message="cursor is required",
            )
        if not isinstance(scope_token, str) or not scope_token:
            return _failed_outcome(
                error_code=_ERROR_INVALID_FETCH_MORE_ARGS,
                message="scope_token is required",
            )
        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0):
            return _failed_outcome(
                error_code=_ERROR_INVALID_FETCH_MORE_ARGS,
                message="limit must be a positive integer",
            )
        with self._state_lock:
            record = self._records_by_cursor.get(cursor_value)
        return _ParsedReadRequest(
            request=request,
            cursor=cursor_value,
            cursor_fingerprint=(record.cursor_fingerprint if record is not None else _fingerprint_text(cursor_value)),
            scope_token=scope_token,
            limit=limit if isinstance(limit, int) and not isinstance(limit, bool) else None,
        )

    def _apply_truncation(
        self,
        *,
        value: _TargetValue,
        spec: ToolTruncateSpec | None,
    ) -> _TruncatedValue | None:
        """按显式截断声明截断工具结果。

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
        if spec.strategy == "binary_bytes" and isinstance(target.value, (bytes, bytearray)):
            return _truncate_binary_bytes(value, target, limit)
        return None

    def _build_cursor(
        self,
        *,
        request: ToolExecutionRequest,
        spec: ToolTruncateSpec | None,
        truncated: _TruncatedValue,
    ) -> _RuntimeCursorRecord:
        """构建初始截断 cursor 记录。

        :param request: 工具执行请求。
        :param spec: 截断声明。
        :param truncated: 截断结果。
        :returns: cursor 记录。
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
        self._cleanup_expired(self.clock())
        return self._build_cursor_record(
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
            arguments=request.call.arguments,
            ttl_seconds=ttl_seconds,
            scope_hash=None,
        )

    def _build_cursor_from_record(
        self,
        *,
        record: _RuntimeCursorRecord,
        offset: int,
    ) -> _RuntimeCursorRecord:
        """从已消费记录构建下一页 cursor。

        :param record: 已消费 cursor 记录。
        :param offset: 下一页起始 offset。
        :returns: 新 cursor 记录。
        :raises Exception: 不主动抛出异常。
        """

        return self._build_cursor_record(
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
            arguments=None,
            ttl_seconds=record.ttl_seconds,
            scope_hash=record.scope_hash,
        )

    def _build_cursor_record(
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
        arguments: Mapping[str, JsonValue] | None,
        ttl_seconds: int,
        scope_hash: str | None,
    ) -> _RuntimeCursorRecord:
        """构建 cursor 记录但不注册到 maps。

        :param session_id: 会话 id。
        :param run_id: Run id。
        :param tool_call_id: 原始工具调用 id。
        :param tool_name: 原始工具名。
        :param strategy: 截断策略。
        :param unit: 截断单位。
        :param limit: 默认补读上限。
        :param total: 原始总量估计。
        :param data: 原始目标数据。
        :param offset: 下一页起始 offset。
        :param template: wrapper 模板。
        :param field_path: wrapper 目标路径。
        :param arguments: 原始工具参数；派生 cursor 可为 ``None``。
        :param ttl_seconds: TTL 秒数。
        :param scope_hash: 已有 scope hash；初始 cursor 为 ``None``。
        :returns: cursor 记录。
        :raises Exception: 不主动抛出异常。
        """

        now = self.clock()
        cursor = self.token_generator()
        resolved_scope_hash = scope_hash
        if resolved_scope_hash is None:
            resolved_scope_hash = _scope_hash(
                tool_name=tool_name,
                arguments=arguments if arguments is not None else {},
            )
        return _RuntimeCursorRecord(
            cursor=cursor,
            cursor_fingerprint=_fingerprint_text(cursor),
            scope_token=_scope_token(
                cursor=cursor,
                scope_hash=resolved_scope_hash,
                session_id=session_id,
                run_id=run_id,
                tool_call_id=tool_call_id,
                created_at_monotonic=now,
            ),
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
            expires_at_monotonic=now + float(ttl_seconds),
            ttl_seconds=ttl_seconds,
        )

    def _commit_cursor(self, record: _RuntimeCursorRecord) -> None:
        """注册 cursor 到内存 maps。

        :param record: 待注册的 cursor 记录。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        with self._state_lock:
            self._records_by_cursor[record.cursor] = record
            self._cursor_by_fingerprint[record.cursor_fingerprint] = record.cursor

    def _remove_cursor(self, cursor: str) -> None:
        """删除 cursor 记录。

        :param cursor: cursor 原文。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        with self._state_lock:
            record = self._records_by_cursor.pop(cursor, None)
            if record is not None:
                self._cursor_by_fingerprint.pop(record.cursor_fingerprint, None)

    def _cleanup_expired(self, now: float) -> None:
        """清理已过期 cursor。

        :param now: 当前 monotonic 时间。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        with self._state_lock:
            expired = tuple(
                cursor for cursor, record in self._records_by_cursor.items() if record.expires_at_monotonic <= now
            )
            for cursor in expired:
                self._remove_cursor(cursor)


def _failed_outcome(*, error_code: str, message: str) -> ToolFailedOutcome:
    """构造普通工具失败 outcome。

    :param error_code: 失败错误码。
    :param message: 人类可读错误描述。
    :returns: 工具失败 outcome。
    :raises Exception: 不主动抛出异常。
    """

    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error=error_code,
            message=message,
            hint=None,
            meta=None,
        )
    )


def _binding_denied_reason(
    *,
    record: _RuntimeCursorRecord,
    session_id: str,
    run_id: str,
) -> str | None:
    """校验 cursor 与请求的 session / run 绑定。

    :param record: cursor 记录。
    :param session_id: 请求会话 id。
    :param run_id: 请求 Run id。
    :returns: 通过返回 ``None``，否则返回拒绝原因。
    :raises Exception: 不主动抛出异常。
    """

    if record.session_id != session_id:
        return "cursor session mismatch"
    if record.run_id != run_id:
        return "cursor run mismatch"
    return None


def _scope_denied_reason(
    *,
    parsed: _ParsedReadRequest,
    record: _RuntimeCursorRecord,
) -> str | None:
    """校验 cursor 指纹与 scope token。

    :param parsed: 已解析补读请求。
    :param record: cursor 记录。
    :returns: 通过返回 ``None``，否则返回拒绝原因。
    :raises Exception: 不主动抛出异常。
    """

    if parsed.cursor_fingerprint != record.cursor_fingerprint:
        return "cursor fingerprint mismatch"
    if not hmac.compare_digest(parsed.scope_token, record.scope_token):
        return "cursor scope mismatch"
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
    if limit is None or limit <= 0:
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
    if timeout_seconds is not None and math.isfinite(timeout_seconds) and timeout_seconds > 0:
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
    return _TruncatedValue(
        value=_apply_chunk_to_template(
            original,
            target.field_path,
            "".join(chunk_lines),
        ),
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
    return _TruncatedValue(
        value=_apply_chunk_to_template(
            original,
            target.field_path,
            _encode_bytes(chunk),
        ),
        data=data,
        offset=len(chunk),
        total=total,
        chunk_size=len(chunk),
        template=cast(JsonValue, original) if target.field_path is not None else None,
        field_path=target.field_path,
    )


def _build_chunk(
    *,
    record: _RuntimeCursorRecord,
    limit: int,
) -> _ChunkBuildResult | None:
    """从 cursor 记录取出下一页数据块。

    :param record: cursor 记录。
    :param limit: 本次读取 limit。
    :returns: 块值与块大小；策略和数据形状不匹配时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if record.strategy == "text_chars" and isinstance(record.data, str):
        chunk = record.data[record.offset : record.offset + limit]
        return _ChunkBuildResult(value=chunk, size=len(chunk))
    if record.strategy == "text_lines" and isinstance(record.data, tuple):
        lines = record.data[record.offset : record.offset + limit]
        return _ChunkBuildResult(value="".join(lines), size=len(lines))
    if record.strategy == "binary_bytes" and isinstance(record.data, bytes):
        chunk_bytes = record.data[record.offset : record.offset + limit]
        return _ChunkBuildResult(
            value=_encode_bytes(chunk_bytes),
            size=len(chunk_bytes),
        )
    if record.strategy == "list_items" and isinstance(record.data, list):
        chunk_items = record.data[record.offset : record.offset + limit]
        return _ChunkBuildResult(value=chunk_items, size=len(chunk_items))
    return None


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
    field_path_text = ".".join(field_path)
    raise RuntimeError(
        "truncate field_path does not match wrapper template: "
        f"field_path={field_path_text} key={key} type={type(child).__name__}"
    )


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

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:_FINGERPRINT_LENGTH]


def _encode_bytes(value: bytes) -> str:
    """将二进制块编码为 base64 字符串。

    :param value: 二进制块。
    :returns: base64 字符串。
    :raises Exception: 不主动抛出异常。
    """

    return base64.b64encode(value).decode("ascii")


__all__: list[str] = []
