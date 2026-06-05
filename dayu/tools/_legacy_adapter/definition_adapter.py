"""OLD 风格同步工具到 current ``ToolDefinition`` 的适配器。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import (
    ToolDefinition,
    ToolDisplayInfo,
)
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultMeta,
    ToolResultSuccess,
)

from .argument_validator import (
    ArgumentValidationFailure,
    ArgumentValidationSuccess,
    validate_tool_arguments,
)
from .exceptions import FileAccessError, ToolArgumentError
from .registry_collector import (
    CollectedLegacyTool,
    LegacySyncToolCallable,
    LegacyToolKeywordValue,
)
from .tool_errors import ToolBusinessError

_RESERVED_FETCH_MORE_TOOL_NAME = "fetch_more"


@dataclass(frozen=True, slots=True)
class ToolPathValidationPolicy:
    """工具路径参数验证策略。

    :param allowed_roots: 允许访问的路径根。
    :param file_path_params: 需要验证的参数名。
    :param must_exist: 路径是否必须已经存在。
    """

    allowed_roots: tuple[Path, ...]
    file_path_params: tuple[str, ...]
    must_exist: bool


@dataclass(frozen=True, slots=True)
class ProjectedLegacyCall:
    """迁移同步函数调用参数。

    :param keyword_arguments: 将传入迁移函数的 JSON keyword arguments。
    """

    keyword_arguments: Mapping[str, JsonValue]


class LegacyToolConcurrencyPolicy(StrEnum):
    """迁移同步工具并发策略。"""

    SERIAL_PER_TOOL = "serial_per_tool"
    SERIAL_PER_PROVIDER = "serial_per_provider"
    CONCURRENT_AFTER_EVIDENCE = "concurrent_after_evidence"


@dataclass(slots=True)
class _AdaptedLegacyCallable:
    """current ``ToolCallable`` 实现。

    :param declaration: 收集到的迁移工具声明。
    :param path_policy: 路径验证策略。
    :param lock: 需要序列化执行时使用的异步锁。
    """

    declaration: CollectedLegacyTool
    path_policy: ToolPathValidationPolicy | None
    lock: asyncio.Lock | None

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolCompletedOutcome | ToolFailedOutcome:
        """执行 current 单工具调用协议。

        :param call: current 工具调用请求。
        :param context: 批式执行上下文。
        :returns: current 工具执行 outcome。
        :raises Exception: 不主动抛出异常；迁移工具异常会被投影为失败 outcome。
        """

        projected = project_tool_call_arguments(
            self.declaration,
            call,
            self.path_policy,
        )
        if isinstance(projected, ToolFailedOutcome):
            return projected
        keyword_arguments: dict[str, LegacyToolKeywordValue] = dict(
            projected.keyword_arguments
        )
        if self.declaration.execution_context_param_name is not None:
            keyword_arguments[self.declaration.execution_context_param_name] = context
        started_at = datetime.now(UTC)
        try:
            if self.lock is None:
                raw_value = await asyncio.to_thread(
                    _invoke_sync_tool,
                    self.declaration.callable,
                    keyword_arguments,
                )
            else:
                async with self.lock:
                    raw_value = await asyncio.to_thread(
                        _invoke_sync_tool,
                        self.declaration.callable,
                        keyword_arguments,
                    )
        except Exception as error:
            finished_at = datetime.now(UTC)
            return project_legacy_exception(
                self.declaration.name,
                error,
                started_at,
                finished_at,
            )
        finished_at = datetime.now(UTC)
        return project_legacy_return(
            self.declaration.name,
            raw_value,
            started_at,
            finished_at,
        )


def project_tool_call_arguments(
    declaration: CollectedLegacyTool,
    call: ToolCallRequest,
    path_policy: ToolPathValidationPolicy | None,
) -> ProjectedLegacyCall | ToolFailedOutcome:
    """把 current 工具调用参数投影为迁移函数 keyword arguments。

    :param declaration: 迁移工具声明。
    :param call: current 工具调用请求。
    :param path_policy: 外部路径验证策略。
    :returns: 投影结果；失败时返回 current ``ToolFailedOutcome``。
    :raises Exception: 不主动抛出异常。
    """

    started_at = datetime.now(UTC)
    validation = validate_tool_arguments(declaration, call)
    finished_at = datetime.now(UTC)
    if isinstance(validation, ArgumentValidationFailure):
        return _failed_outcome(
            tool_name=declaration.name,
            error=validation.error,
            message=validation.message,
            hint=validation.hint,
            started_at=started_at,
            finished_at=finished_at,
        )
    if isinstance(validation, ArgumentValidationSuccess):
        path_projection = _project_paths(
            declaration=declaration,
            arguments=validation.arguments,
            path_policy=path_policy,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        if isinstance(path_projection, ToolFailedOutcome):
            return path_projection
        return ProjectedLegacyCall(keyword_arguments=path_projection)
    return _failed_outcome(
        tool_name=declaration.name,
        error="invalid_argument",
        message="Tool argument validation returned an unknown result.",
        hint="Retry with arguments matching the tool schema.",
        started_at=started_at,
        finished_at=finished_at,
    )


def project_legacy_return(
    tool_name: str,
    raw_value: JsonValue,
    started_at: datetime,
    finished_at: datetime,
) -> ToolCompletedOutcome | ToolFailedOutcome:
    """把迁移函数返回值投影为 current outcome。

    :param tool_name: 工具名。
    :param raw_value: 迁移函数原始 JSON 返回值。
    :param started_at: 执行开始时间。
    :param finished_at: 执行结束时间。
    :returns: current 成功或失败 outcome。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(raw_value, Mapping):
        ok_value = raw_value.get("ok")
        if ok_value is True and "value" in raw_value:
            return _completed_outcome(
                tool_name=tool_name,
                value=raw_value.get("value"),
                started_at=started_at,
                finished_at=finished_at,
            )
        if ok_value is False:
            return _failed_outcome(
                tool_name=tool_name,
                error=_text_or_default(raw_value.get("error"), "execution_error"),
                message=_text_or_default(raw_value.get("message"), "Tool execution failed."),
                hint=_optional_text(raw_value.get("hint")),
                started_at=started_at,
                finished_at=finished_at,
            )
    return _completed_outcome(
        tool_name=tool_name,
        value=raw_value,
        started_at=started_at,
        finished_at=finished_at,
    )


def project_legacy_exception(
    tool_name: str,
    error: Exception,
    started_at: datetime,
    finished_at: datetime,
) -> ToolFailedOutcome:
    """把迁移函数异常投影为 current 失败 outcome。

    :param tool_name: 工具名。
    :param error: 捕获到的异常。
    :param started_at: 执行开始时间。
    :param finished_at: 执行结束时间。
    :returns: current 失败 outcome。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(error, ToolBusinessError):
        return _failed_outcome(
            tool_name=tool_name,
            error=error.code,
            message=error.message,
            hint=_blank_to_none(error.hint),
            started_at=started_at,
            finished_at=finished_at,
        )
    if isinstance(error, ToolArgumentError):
        return _failed_outcome(
            tool_name=tool_name,
            error="invalid_argument",
            message=str(error),
            hint="Fix arguments to match the tool schema and retry.",
            started_at=started_at,
            finished_at=finished_at,
        )
    if isinstance(error, FileAccessError) or isinstance(error, PermissionError):
        return _failed_outcome(
            tool_name=tool_name,
            error="permission_denied",
            message=str(error),
            hint="Use a path allowed by the provider configuration.",
            started_at=started_at,
            finished_at=finished_at,
        )
    if isinstance(error, FileNotFoundError):
        return _failed_outcome(
            tool_name=tool_name,
            error="file_not_found",
            message=str(error),
            hint="Verify the file path and retry.",
            started_at=started_at,
            finished_at=finished_at,
        )
    return _failed_outcome(
        tool_name=tool_name,
        error="execution_error",
        message=f"Tool {tool_name!r} execution failed.",
        hint="Inspect provider diagnostics or retry with narrower arguments.",
        started_at=started_at,
        finished_at=finished_at,
    )


def adapt_collected_tool(
    declaration: CollectedLegacyTool,
    path_policy: ToolPathValidationPolicy | None,
    concurrency_policy: LegacyToolConcurrencyPolicy,
) -> ToolDefinition:
    """把单个迁移工具声明适配为 current ``ToolDefinition``。

    :param declaration: 迁移工具声明。
    :param path_policy: 路径验证策略。
    :param concurrency_policy: 同步工具并发策略。
    :returns: current 工具定义。
    :raises ValueError: 尝试适配 reserved framework 工具名时抛出。
    """

    if declaration.name == _RESERVED_FETCH_MORE_TOOL_NAME:
        raise ValueError("legacy adapter must not expose fetch_more as a business tool")
    lock = (
        None
        if concurrency_policy is LegacyToolConcurrencyPolicy.CONCURRENT_AFTER_EVIDENCE
        else asyncio.Lock()
    )
    return _build_definition(declaration=declaration, path_policy=path_policy, lock=lock)


def adapt_collected_tools(
    declarations: Sequence[CollectedLegacyTool],
    path_policy_by_tool: Mapping[str, ToolPathValidationPolicy],
    concurrency_policy_by_tool: Mapping[str, LegacyToolConcurrencyPolicy],
) -> tuple[ToolDefinition, ...]:
    """批量适配迁移工具声明。

    :param declarations: 迁移工具声明序列。
    :param path_policy_by_tool: 按工具名索引的路径策略。
    :param concurrency_policy_by_tool: 按工具名索引的并发策略。
    :returns: current 工具定义元组。
    :raises Exception: 单工具适配失败时透出对应异常。
    """

    provider_lock = asyncio.Lock()
    definitions: list[ToolDefinition] = []
    for declaration in declarations:
        if declaration.name == _RESERVED_FETCH_MORE_TOOL_NAME:
            raise ValueError("legacy adapter must not expose fetch_more as a business tool")
        concurrency_policy = concurrency_policy_by_tool.get(
            declaration.name,
            LegacyToolConcurrencyPolicy.SERIAL_PER_TOOL,
        )
        if concurrency_policy is LegacyToolConcurrencyPolicy.CONCURRENT_AFTER_EVIDENCE:
            lock: asyncio.Lock | None = None
        elif concurrency_policy is LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER:
            lock = provider_lock
        else:
            lock = asyncio.Lock()
        definitions.append(
            _build_definition(
                declaration=declaration,
                path_policy=path_policy_by_tool.get(declaration.name),
                lock=lock,
            )
        )
    return tuple(definitions)


def _build_definition(
    *,
    declaration: CollectedLegacyTool,
    path_policy: ToolPathValidationPolicy | None,
    lock: asyncio.Lock | None,
) -> ToolDefinition:
    """构造 current 工具定义。

    :param declaration: 迁移工具声明。
    :param path_policy: 路径策略。
    :param lock: 执行锁。
    :returns: current 工具定义。
    :raises Exception: current 契约构造失败时透出异常。
    """

    display = (
        ToolDisplayInfo(name=declaration.display_name)
        if declaration.display_name is not None
        else None
    )
    return ToolDefinition(
        name=declaration.name,
        schema=declaration.schema,
        callable=_AdaptedLegacyCallable(
            declaration=declaration,
            path_policy=path_policy,
            lock=lock,
        ),
        truncate=declaration.truncate,
        display=display,
        tags=declaration.tags,
    )


def _project_paths(
    *,
    declaration: CollectedLegacyTool,
    arguments: Mapping[str, JsonValue],
    path_policy: ToolPathValidationPolicy | None,
    started_at: datetime,
    finished_at: datetime,
) -> Mapping[str, JsonValue] | ToolFailedOutcome:
    """按外部策略验证并归一化路径参数。

    :param declaration: 迁移工具声明。
    :param arguments: 已通过 schema 校验的参数。
    :param path_policy: 路径策略。
    :param started_at: 投影开始时间。
    :param finished_at: 投影结束时间。
    :returns: 归一化后的参数，或失败 outcome。
    :raises Exception: 不主动抛出异常。
    """

    if path_policy is not None:
        missing_path_params = tuple(
            sorted(set(declaration.file_path_params) - set(path_policy.file_path_params))
        )
        if missing_path_params:
            return _failed_outcome(
                tool_name=declaration.name,
                error="permission_denied",
                message=(
                    "Tool path policy does not cover declared path arguments: "
                    f"{', '.join(missing_path_params)}."
                ),
                hint="Fix provider path policy before enabling this tool.",
                started_at=started_at,
                finished_at=finished_at,
            )
    path_param_names = declaration.file_path_params
    if not path_param_names:
        return arguments
    if path_policy is None or not path_policy.allowed_roots:
        return _failed_outcome(
            tool_name=declaration.name,
            error="permission_denied",
            message="Tool path arguments require an explicit provider path policy.",
            hint="Configure allowed path roots for this provider before enabling the tool.",
            started_at=started_at,
            finished_at=finished_at,
        )
    projected = dict(arguments)
    allowed_roots = tuple(root.expanduser().resolve(strict=False) for root in path_policy.allowed_roots)
    for parameter_name in path_param_names:
        value = arguments.get(parameter_name)
        if not isinstance(value, str):
            return _failed_outcome(
                tool_name=declaration.name,
                error="invalid_argument",
                message=f"Path argument {parameter_name!r} must be a string.",
                hint=f"Set {parameter_name} to a file path string and retry.",
                started_at=started_at,
                finished_at=finished_at,
            )
        candidate = Path(value).expanduser().resolve(strict=False)
        if path_policy.must_exist and not candidate.exists():
            return _failed_outcome(
                tool_name=declaration.name,
                error="file_not_found",
                message=f"Path does not exist: {value}",
                hint="Verify the file path and retry.",
                started_at=started_at,
                finished_at=finished_at,
            )
        if not any(_is_relative_to(candidate, root) for root in allowed_roots):
            return _failed_outcome(
                tool_name=declaration.name,
                error="permission_denied",
                message=f"Path is outside allowed provider roots: {value}",
                hint="Use a path under the provider configured allowed roots.",
                started_at=started_at,
                finished_at=finished_at,
            )
        projected[parameter_name] = str(candidate)
    return projected


def _is_relative_to(candidate: Path, root: Path) -> bool:
    """判断候选路径是否在 root 下。

    :param candidate: 候选路径。
    :param root: 允许根路径。
    :returns: 在 root 下或等于 root 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return candidate == root or root in candidate.parents


def _invoke_sync_tool(
    callable_: LegacySyncToolCallable,
    keyword_arguments: Mapping[str, LegacyToolKeywordValue],
) -> JsonValue:
    """在线程中调用迁移同步函数。

    :param callable_: 迁移同步工具函数。
    :param keyword_arguments: 投影后的关键字参数。
    :returns: JSON 兼容返回值。
    :raises Exception: 迁移函数抛出的异常原样透出。
    """

    return callable_(**keyword_arguments)


def _completed_outcome(
    *,
    tool_name: str,
    value: JsonValue,
    started_at: datetime,
    finished_at: datetime,
) -> ToolCompletedOutcome:
    """构造成功 outcome。

    :param tool_name: 工具名。
    :param value: 成功值。
    :param started_at: 开始时间。
    :param finished_at: 结束时间。
    :returns: current 成功 outcome。
    :raises Exception: current 契约构造失败时透出异常。
    """

    return ToolCompletedOutcome(
        result=ToolResultSuccess(
            ok=True,
            value=value,
            meta=_meta(tool_name=tool_name, started_at=started_at, finished_at=finished_at),
        )
    )


def _failed_outcome(
    *,
    tool_name: str,
    error: str,
    message: str,
    hint: str | None,
    started_at: datetime,
    finished_at: datetime,
) -> ToolFailedOutcome:
    """构造失败 outcome。

    :param tool_name: 工具名。
    :param error: 错误码。
    :param message: 错误说明。
    :param hint: 恢复提示。
    :param started_at: 开始时间。
    :param finished_at: 结束时间。
    :returns: current 失败 outcome。
    :raises Exception: current 契约构造失败时透出异常。
    """

    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error=_blank_to_default(error, "execution_error"),
            message=_blank_to_default(message, "Tool execution failed."),
            hint=_blank_to_none(hint),
            meta=_meta(tool_name=tool_name, started_at=started_at, finished_at=finished_at),
        )
    )


def _meta(
    *,
    tool_name: str,
    started_at: datetime,
    finished_at: datetime,
) -> ToolResultMeta:
    """构造工具结果元信息。

    :param tool_name: 工具名。
    :param started_at: 开始时间。
    :param finished_at: 结束时间。
    :returns: 工具结果元信息。
    :raises Exception: current 契约构造失败时透出异常。
    """

    return ToolResultMeta(
        tool_name=tool_name,
        started_at=started_at,
        finished_at=finished_at,
    )


def _text_or_default(value: JsonValue, default: str) -> str:
    """读取文本字段并应用默认值。

    :param value: JSON 值。
    :param default: 默认文本。
    :returns: 非空文本。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, str) and value.strip() != "":
        return value
    return default


def _optional_text(value: JsonValue) -> str | None:
    """读取可选文本字段。

    :param value: JSON 值。
    :returns: 非空文本或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _blank_to_default(value: str, default: str) -> str:
    """把空白字符串替换为默认值。

    :param value: 原始文本。
    :param default: 默认文本。
    :returns: 非空文本。
    :raises Exception: 不主动抛出异常。
    """

    return value if value.strip() != "" else default


def _blank_to_none(value: str | None) -> str | None:
    """把空白可选文本归一为 ``None``。

    :param value: 原始文本。
    :returns: 非空文本或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


__all__ = [
    "LegacyToolConcurrencyPolicy",
    "ProjectedLegacyCall",
    "ToolPathValidationPolicy",
    "adapt_collected_tool",
    "adapt_collected_tools",
    "project_legacy_exception",
    "project_legacy_return",
    "project_tool_call_arguments",
]
