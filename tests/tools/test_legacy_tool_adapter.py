"""OLD 风格工具适配器测试。"""

from __future__ import annotations

import ast
import asyncio
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

import dayu.tools as tools_package
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_schema import (
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)
from dayu.tools._legacy_adapter.definition_adapter import (
    LegacyToolConcurrencyPolicy,
    ProjectedLegacyCall,
    ToolPathValidationPolicy,
    adapt_collected_tool,
    adapt_collected_tools,
    project_legacy_exception,
    project_legacy_return,
    project_tool_call_arguments,
)
from dayu.tools._legacy_adapter.registry_collector import (
    CollectedLegacyTool,
    LegacySyncToolCallable,
    LegacyToolDeclarationCollector,
    LegacyToolKeywordValue,
)
from dayu.tools._legacy_adapter.tool_decorator import tool
from dayu.tools._legacy_adapter.tool_errors import ToolBusinessError

_FORBIDDEN_OLD_IMPORT_PREFIXES: tuple[str, ...] = (
    "dayu.engine.tool_registry",
    "dayu.engine.truncation_manager",
    "dayu.engine.tool_result",
)


class _CancellationToken:
    """测试用取消观察 token。"""

    def is_cancelled(self) -> bool:
        """返回是否取消。

        :returns: 始终返回 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


def test_collector_and_adapter_create_async_current_tool_callable() -> None:
    """同步 OLD 风格 callable 必须适配为 current async ToolCallable。

    :returns: ``None``。
    :raises AssertionError: 适配结果不是 current ToolDefinition 或执行失败时抛出。
    """

    collector = LegacyToolDeclarationCollector()

    def raw_echo(query: LegacyToolKeywordValue) -> JsonValue:
        """返回查询参数。

        :param query: 查询参数。
        :returns: JSON 结果。
        :raises Exception: 不主动抛出异常。
        """

        return {"query": query if isinstance(query, str) else ""}

    decorated = tool(
        collector,
        name="echo",
        description="Echo query.",
        parameters=_parameters(
            properties={"query": {"type": "string"}},
            required=("query",),
        ),
        tags=("demo",),
        display_name="Echo",
    )(raw_echo)
    collector.register("echo", decorated, _schema(decorated))

    definition = adapt_collected_tool(
        collector.collected_tools()[0],
        path_policy=None,
        concurrency_policy=LegacyToolConcurrencyPolicy.SERIAL_PER_TOOL,
    )
    outcome = asyncio.run(definition.callable(_call("echo", {"query": "AAPL"}), _context()))

    assert isinstance(definition, ToolDefinition)
    assert definition.display is not None
    assert definition.display.name == "Echo"
    assert definition.tags == ("demo",)
    assert isinstance(outcome, ToolCompletedOutcome)
    assert outcome.result.value == {"query": "AAPL"}


def test_direct_argument_pass_through_uses_original_mapping() -> None:
    """安全直接透传必须复用 ToolCallRequest.arguments。

    :returns: ``None``。
    :raises AssertionError: 透传结果不是原始 mapping 时抛出。
    """

    declaration = _single_tool_declaration(
        name="direct",
        parameters=_parameters(
            properties={"query": {"type": "string"}},
            required=("query",),
        ),
    )
    call = _call("direct", {"query": "revenue"})

    projected = project_tool_call_arguments(declaration, call, path_policy=None)

    assert isinstance(projected, ProjectedLegacyCall)
    assert projected.keyword_arguments is call.arguments


def test_projection_coerces_defaults_and_rejects_invalid_arguments() -> None:
    """需要投影时必须先校验/转换，失败不能进入迁移函数。

    :returns: ``None``。
    :raises AssertionError: 投影或失败语义不符合预期时抛出。
    """

    calls: list[Mapping[str, JsonValue]] = []

    def raw_limit(limit: LegacyToolKeywordValue = None) -> JsonValue:
        """记录 limit 并返回。

        :param limit: 限制数量。
        :returns: JSON 结果。
        :raises Exception: 不主动抛出异常。
        """

        recorded = {"limit": limit if isinstance(limit, int) else 0}
        calls.append(recorded)
        return recorded

    declaration = _single_tool_declaration(
        name="limit_tool",
        raw_callable=raw_limit,
        parameters=_parameters(
            properties={
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 3,
                }
            },
            required=(),
        ),
    )

    projected = project_tool_call_arguments(
        declaration,
        _call("limit_tool", {"limit": 2.0}),
        path_policy=None,
    )
    failed = project_tool_call_arguments(
        declaration,
        _call("limit_tool", {"limit": 9}),
        path_policy=None,
    )
    definition = adapt_collected_tool(
        declaration,
        path_policy=None,
        concurrency_policy=LegacyToolConcurrencyPolicy.SERIAL_PER_TOOL,
    )
    outcome = asyncio.run(definition.callable(_call("limit_tool", {"limit": 9}), _context()))

    assert isinstance(projected, ProjectedLegacyCall)
    assert projected.keyword_arguments == {"limit": 2}
    assert isinstance(failed, ToolFailedOutcome)
    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    assert calls == []


def test_path_projection_uses_explicit_policy_not_collector_allowed_paths(
    tmp_path: Path,
) -> None:
    """路径安全只能来自显式 path policy，不能来自 collector 记录值。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 路径策略未 fail closed 或未归一化时抛出。
    """

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    target = allowed_root / "report.md"
    target.write_text("report", encoding="utf-8")
    collector = LegacyToolDeclarationCollector()
    collector.register_allowed_paths((tmp_path / "not-trusted",))
    declaration = _single_tool_declaration(
        name="read_path",
        parameters=_parameters(
            properties={"file_path": {"type": "string"}},
            required=("file_path",),
        ),
        file_path_params=("file_path",),
    )

    no_policy = project_tool_call_arguments(
        declaration,
        _call("read_path", {"file_path": str(target)}),
        path_policy=None,
    )
    projected = project_tool_call_arguments(
        declaration,
        _call("read_path", {"file_path": str(target)}),
        path_policy=ToolPathValidationPolicy(
            allowed_roots=(allowed_root,),
            file_path_params=("file_path",),
            must_exist=True,
        ),
    )

    assert isinstance(no_policy, ToolFailedOutcome)
    assert no_policy.result.error == "permission_denied"
    assert isinstance(projected, ProjectedLegacyCall)
    assert projected.keyword_arguments["file_path"] == str(target.resolve())


def test_incomplete_path_policy_coverage_fails_before_calling_migrated_function(
    tmp_path: Path,
) -> None:
    """路径策略漏掉声明路径参数时必须 fail-closed 且不调用工具。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 不完整策略未阻止工具调用时抛出。
    """

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    target = allowed_root / "report.md"
    target.write_text("report", encoding="utf-8")
    calls: list[str] = []

    def raw_path_tool(
        file_path: LegacyToolKeywordValue,
        directory: LegacyToolKeywordValue,
    ) -> JsonValue:
        """记录路径工具调用。

        :param file_path: 文件路径。
        :param directory: 目录路径。
        :returns: JSON 结果。
        :raises Exception: 不主动抛出异常。
        """

        calls.append(f"{file_path}:{directory}")
        return {"called": True}

    declaration = _single_tool_declaration(
        name="read_two_paths",
        raw_callable=raw_path_tool,
        parameters=_parameters(
            properties={
                "file_path": {"type": "string"},
                "directory": {"type": "string"},
            },
            required=("file_path", "directory"),
        ),
        file_path_params=("file_path", "directory"),
    )
    definition = adapt_collected_tool(
        declaration,
        path_policy=ToolPathValidationPolicy(
            allowed_roots=(allowed_root,),
            file_path_params=("file_path",),
            must_exist=True,
        ),
        concurrency_policy=LegacyToolConcurrencyPolicy.SERIAL_PER_TOOL,
    )

    outcome = asyncio.run(
        definition.callable(
            _call(
                "read_two_paths",
                {
                    "file_path": str(target),
                    "directory": str(allowed_root),
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "permission_denied"
    assert "directory" in outcome.result.message
    assert calls == []


def test_legacy_return_envelopes_project_to_current_outcomes() -> None:
    """OLD ok/value envelope 必须解包为 current outcome。

    :returns: ``None``。
    :raises AssertionError: 仍保留 OLD 嵌套或 projection-only 字段时抛出。
    """

    started_at = datetime.now(UTC)
    finished_at = datetime.now(UTC)

    success = project_legacy_return(
        "legacy",
        {
            "ok": True,
            "value": {"answer": "42"},
            "truncation": {"ignored": True},
            "fetch_more_args": {"ignored": True},
        },
        started_at,
        finished_at,
    )
    failure = project_legacy_return(
        "legacy",
        {"ok": False, "error": "not_found", "message": "Missing.", "hint": "List first."},
        started_at,
        finished_at,
    )

    assert isinstance(success, ToolCompletedOutcome)
    assert success.result.value == {"answer": "42"}
    assert "ok" not in cast(Mapping[str, JsonValue], success.result.value)
    assert isinstance(failure, ToolFailedOutcome)
    assert failure.result.error == "not_found"
    assert failure.result.hint == "List first."


def test_plain_business_dict_with_ok_field_is_preserved() -> None:
    """非 OLD envelope 的业务 dict 即使含 ok 字段也必须原样保留。

    :returns: ``None``。
    :raises AssertionError: 业务 dict 被误判为 OLD envelope 时抛出。
    """

    value: dict[str, JsonValue] = {"ok": True, "status": "ready"}

    outcome = project_legacy_return(
        "legacy",
        value,
        datetime.now(UTC),
        datetime.now(UTC),
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    assert outcome.result.value == {"ok": True, "status": "ready"}


def test_legacy_exceptions_project_to_current_failures() -> None:
    """OLD 业务异常必须投影为 current ToolFailedOutcome。

    :returns: ``None``。
    :raises AssertionError: 业务错误映射不符合预期时抛出。
    """

    outcome = project_legacy_exception(
        "legacy",
        ToolBusinessError("not_found", "Document missing.", hint="List documents first."),
        datetime.now(UTC),
        datetime.now(UTC),
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "not_found"
    assert outcome.result.message == "Document missing."
    assert outcome.result.hint == "List documents first."


def test_generic_exception_projects_to_execution_error_failure() -> None:
    """普通异常必须投影为 execution_error 失败 outcome。

    :returns: ``None``。
    :raises AssertionError: 普通异常分类不符合预期时抛出。
    """

    def raw_broken() -> JsonValue:
        """抛出普通运行时错误。

        :returns: 不返回。
        :raises RuntimeError: 始终抛出。
        """

        raise RuntimeError("database temporarily unavailable")

    definition = adapt_collected_tool(
        _single_tool_declaration(
            name="broken",
            raw_callable=raw_broken,
            parameters=_parameters(properties={}, required=()),
        ),
        path_policy=None,
        concurrency_policy=LegacyToolConcurrencyPolicy.SERIAL_PER_TOOL,
    )

    outcome = asyncio.run(definition.callable(_call("broken", {}), _context()))

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "execution_error"
    assert outcome.result.message == "Tool 'broken' execution failed."


def test_fetch_more_is_not_emitted_as_business_tool() -> None:
    """OLD fetch_more 不能作为业务工具输出，batch adapter 也必须 fail-fast。

    :returns: ``None``。
    :raises AssertionError: fetch_more 未 fail-fast 时抛出。
    """

    with pytest.raises(ValueError, match="fetch_more"):
        adapt_collected_tools(
            (
                _single_tool_declaration(name="fetch_more"),
                _single_tool_declaration(name="normal_tool"),
            ),
            path_policy_by_tool={},
            concurrency_policy_by_tool={},
        )


def test_current_truncate_spec_is_used_for_legacy_declarations() -> None:
    """OLD 风格 truncate mapping 必须转换为 current ToolTruncateSpec。

    :returns: ``None``。
    :raises AssertionError: 截断声明不是 current contract 时抛出。
    """

    declaration = _single_tool_declaration(
        name="truncating",
        truncate={
            "enabled": True,
            "strategy": "text_chars",
            "limits": {"max_chars": 100},
            "target_field": "content",
            "continuation_hint": {"ignored": True},
        },
    )

    assert isinstance(declaration.truncate, ToolTruncateSpec)
    assert declaration.truncate.strategy is ToolTruncationStrategy.TEXT_CHARS
    assert declaration.truncate.limits == {"max_chars": 100}
    assert declaration.truncate.target_field == "content"
    assert declaration.truncate.field_path is None
    assert declaration.truncate.ttl_seconds is None


def test_default_per_tool_serialization_prevents_concurrent_entry() -> None:
    """默认 per-tool serialization 必须防止同一同步 callable 并发进入。

    :returns: ``None``。
    :raises AssertionError: 同一迁移函数发生并发进入时抛出。
    """

    active_lock = threading.Lock()
    active_count = 0
    concurrent_entries = 0

    def raw_slow(value: LegacyToolKeywordValue) -> JsonValue:
        """模拟慢同步工具。

        :param value: 输入值。
        :returns: JSON 结果。
        :raises Exception: 不主动抛出异常。
        """

        nonlocal active_count, concurrent_entries
        with active_lock:
            active_count += 1
            if active_count > 1:
                concurrent_entries += 1
        time.sleep(0.05)
        with active_lock:
            active_count -= 1
        return {"value": value if isinstance(value, str) else ""}

    declaration = _single_tool_declaration(
        name="slow",
        raw_callable=raw_slow,
        parameters=_parameters(
            properties={"value": {"type": "string"}},
            required=("value",),
        ),
    )
    definition = adapt_collected_tool(
        declaration,
        path_policy=None,
        concurrency_policy=LegacyToolConcurrencyPolicy.SERIAL_PER_TOOL,
    )

    async def run_two_calls() -> tuple[ToolCompletedOutcome | ToolFailedOutcome, ...]:
        """并发执行两次 current callable。

        :returns: 两次调用 outcome。
        :raises Exception: callable 抛出的异常会透出。
        """

        first = definition.callable(_call("slow", {"value": "a"}), _context())
        second = definition.callable(_call("slow", {"value": "b"}), _context())
        return cast(
            tuple[ToolCompletedOutcome | ToolFailedOutcome, ...],
            await asyncio.gather(first, second),
        )

    outcomes = asyncio.run(run_two_calls())

    assert all(isinstance(outcome, ToolCompletedOutcome) for outcome in outcomes)
    assert concurrent_entries == 0


def test_serial_per_provider_shares_lock_across_tool_names() -> None:
    """provider-wide serialization 必须让不同工具名共享同一把锁。

    :returns: ``None``。
    :raises AssertionError: 不同工具名并发进入同步函数时抛出。
    """

    active_lock = threading.Lock()
    active_count = 0
    concurrent_entries = 0

    def make_raw_tool(tool_label: str) -> Callable[[LegacyToolKeywordValue], JsonValue]:
        """构造记录 provider-wide 并发进入的同步工具。

        :param tool_label: 工具标签。
        :returns: 同步工具函数。
        :raises Exception: 不主动抛出异常。
        """

        def raw_tool(value: LegacyToolKeywordValue) -> JsonValue:
            """模拟共享 provider 状态的慢同步工具。

            :param value: 输入值。
            :returns: JSON 结果。
            :raises Exception: 不主动抛出异常。
            """

            nonlocal active_count, concurrent_entries
            with active_lock:
                active_count += 1
                if active_count > 1:
                    concurrent_entries += 1
            time.sleep(0.05)
            with active_lock:
                active_count -= 1
            return {
                "tool": tool_label,
                "value": value if isinstance(value, str) else "",
            }

        return raw_tool

    declarations = (
        _single_tool_declaration(
            name="provider_tool_a",
            raw_callable=make_raw_tool("a"),
            parameters=_parameters(
                properties={"value": {"type": "string"}},
                required=("value",),
            ),
        ),
        _single_tool_declaration(
            name="provider_tool_b",
            raw_callable=make_raw_tool("b"),
            parameters=_parameters(
                properties={"value": {"type": "string"}},
                required=("value",),
            ),
        ),
    )
    definitions = adapt_collected_tools(
        declarations,
        path_policy_by_tool={},
        concurrency_policy_by_tool={
            "provider_tool_a": LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER,
            "provider_tool_b": LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER,
        },
    )
    definitions_by_name = {definition.name: definition for definition in definitions}

    async def run_two_provider_calls() -> tuple[ToolCompletedOutcome | ToolFailedOutcome, ...]:
        """并发执行两个不同工具名的 provider-wide callable。

        :returns: 两次调用 outcome。
        :raises Exception: callable 抛出的异常会透出。
        """

        first = definitions_by_name["provider_tool_a"].callable(
            _call("provider_tool_a", {"value": "a"}),
            _context(),
        )
        second = definitions_by_name["provider_tool_b"].callable(
            _call("provider_tool_b", {"value": "b"}),
            _context(),
        )
        return cast(
            tuple[ToolCompletedOutcome | ToolFailedOutcome, ...],
            await asyncio.gather(first, second),
        )

    outcomes = asyncio.run(run_two_provider_calls())

    assert all(isinstance(outcome, ToolCompletedOutcome) for outcome in outcomes)
    assert concurrent_entries == 0


def test_tools_adapter_import_boundary_excludes_old_runtime_owners() -> None:
    """适配器不得导入 OLD registry/truncation/projection owner。

    :returns: ``None``。
    :raises AssertionError: 发现禁止导入时抛出。
    """

    root = Path(cast(str, tools_package.__file__)).resolve().parent / "_legacy_adapter"
    violations: list[tuple[str, str]] = []
    for file_path in sorted(root.rglob("*.py")):
        imported_modules = _imported_module_names(file_path.read_text(encoding="utf-8"))
        for module in imported_modules:
            if _matches_prefix(module, _FORBIDDEN_OLD_IMPORT_PREFIXES):
                violations.append((str(file_path), module))

    assert not violations


def _single_tool_declaration(
    *,
    name: str,
    raw_callable: Callable[..., JsonValue] | None = None,
    parameters: Mapping[str, JsonValue] | None = None,
    file_path_params: tuple[str, ...] = (),
    truncate: Mapping[str, JsonValue] | ToolTruncateSpec | None = None,
) -> CollectedLegacyTool:
    """构造单个收集工具声明。

    :param name: 工具名。
    :param raw_callable: 可选同步函数。
    :param parameters: 参数 schema。
    :param file_path_params: 文件路径参数名。
    :param truncate: 截断声明。
    :returns: ``CollectedLegacyTool``。
    :raises Exception: 声明构造失败时透出异常。
    """

    collector = LegacyToolDeclarationCollector()

    def raw_default(**keyword_arguments: LegacyToolKeywordValue) -> JsonValue:
        """默认同步工具。

        :param keyword_arguments: 关键字参数。
        :returns: 原样参数。
        :raises Exception: 不主动抛出异常。
        """

        received_fields: list[JsonValue] = list(sorted(keyword_arguments.keys()))
        return {"received_fields": received_fields}

    func = raw_callable if raw_callable is not None else raw_default
    decorated = tool(
        collector,
        name=name,
        description=f"{name} tool.",
        parameters=parameters
        if parameters is not None
        else _parameters(properties={"query": {"type": "string"}}, required=()),
        file_path_params=file_path_params,
        truncate=truncate,
    )(func)
    collector.register(name, decorated, _schema(decorated))
    return collector.collected_tools()[0]


def _schema(func: LegacySyncToolCallable) -> ToolSchema:
    """读取 decorator 写入的 schema metadata。

    :param func: 已装饰函数。
    :returns: current ToolSchema。
    :raises Exception: metadata 缺失时抛出异常。
    """

    return cast(ToolSchema, getattr(func, "__tool_schema__"))


def _parameters(
    *,
    properties: Mapping[str, JsonValue],
    required: tuple[str, ...],
) -> Mapping[str, JsonValue]:
    """构造参数 schema。

    :param properties: properties 字段。
    :param required: required 字段。
    :returns: JSON Schema object。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
    }


def _call(name: str, arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造工具调用请求。

    :param name: 工具名。
    :param arguments: 工具参数。
    :returns: current ToolCallRequest。
    :raises Exception: current 契约构造失败时透出异常。
    """

    return ToolCallRequest(
        tool_call_id=f"{name}-call",
        name=name,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _context() -> BatchToolExecutionContext:
    """构造批式工具上下文。

    :returns: current BatchToolExecutionContext。
    :raises Exception: current 契约构造失败时透出异常。
    """

    return BatchToolExecutionContext(
        run_id="run",
        session_id="session",
        iteration_id="iteration",
        timeout_seconds=30.0,
        cancellation_token=_CancellationToken(),
        correlation_id="run:iteration:tool_batch",
    )


def _imported_module_names(source: str) -> list[str]:
    """从 Python 源码读取 import 模块名。

    :param source: Python 源码。
    :returns: import 模块名列表。
    :raises SyntaxError: 源码无法解析时抛出。
    """

    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                names.append(node.module)
    return names


def _matches_prefix(module: str, prefixes: tuple[str, ...]) -> bool:
    """判断模块是否命中禁止前缀。

    :param module: 模块名。
    :param prefixes: 前缀集合。
    :returns: 命中返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)
