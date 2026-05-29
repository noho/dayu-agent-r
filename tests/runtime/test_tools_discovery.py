"""``dayu.runtime.tools_discovery`` 测试。"""

from __future__ import annotations

import importlib.metadata as importlib_metadata

import pytest

from dayu.contracts import (
    BatchToolExecutionContext,
    JsonValue,
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    ToolCallRequest,
    ToolCancelledOutcome,
    ToolDefinition,
    ToolExecutionOutcome,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.runtime.tools_discovery import (
    PackageEntryPointProvider,
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryError,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
    discover_tools,
    resolve_provider_callable,
)

_ENTRY_POINT_GROUP = "dayu.test_tools"
_ENTRY_POINT_NAME = "fake_entry_provider"


async def _noop_tool(
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
) -> ToolExecutionOutcome:
    """测试用单工具 callable。

    :param call: 单次工具调用请求。
    :param context: 批式工具执行上下文。
    :returns: 一个不会实际执行业务逻辑的取消 outcome。
    :raises Exception: 不主动抛出异常。
    """

    del call
    del context
    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
        message="tool disabled in test",
        hint=None,
        meta=None,
    )


def _parameters() -> ToolParametersSchema:
    """构造测试用空参数 schema。

    :returns: 工具参数 schema。
    :raises Exception: 不主动抛出异常。
    """

    properties: dict[str, JsonValue] = {}
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=(),
        additional_properties=False,
    )


def _definition(name: str) -> ToolDefinition:
    """构造测试用工具声明。

    :param name: 工具名。
    :returns: 对应工具声明。
    :raises ValueError: 工具声明名称与 schema 名称不一致时抛出。
    """

    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=f"{name} test tool",
                parameters=_parameters(),
            ),
        ),
        callable=_noop_tool,
        truncate=None,
        display=None,
        tags=(),
    )


def _source_ref(source_id: str) -> ToolBundleSourceRef:
    """构造测试用工具来源引用。

    :param source_id: 来源标识。
    :returns: 对应来源引用。
    :raises ValueError: 来源引用字段为空时抛出。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id=source_id,
    )


def _spec(spec_id: str, *, enabled: bool = True, allow_empty: bool = False) -> ToolsDiscoveryProviderSpec:
    """构造测试用 provider spec。

    :param spec_id: provider spec 标识。
    :param enabled: 是否启用 provider。
    :param allow_empty: 是否允许空工具输出。
    :returns: provider spec。
    :raises ValueError: spec 字段为空时抛出。
    """

    return ToolsDiscoveryProviderSpec(
        spec_id=spec_id,
        location=PythonImportPathProvider(import_path="tests.runtime.test_tools_discovery:_import_path_provider"),
        enabled=enabled,
        allow_empty=allow_empty,
    )


def _output(
    *,
    provider_id: str,
    source_id: str,
    tool_names: tuple[str, ...],
    version_ref: str | None = "v1",
) -> ToolsDiscoveryProviderOutput:
    """构造测试用 provider 输出。

    :param provider_id: provider 身份。
    :param source_id: 来源标识。
    :param tool_names: 工具名元组。
    :param version_ref: 版本引用；``None`` 表示无版本。
    :returns: provider 输出。
    :raises ValueError: 工具声明或来源引用字段非法时抛出。
    """

    return ToolsDiscoveryProviderOutput(
        provider_id=provider_id,
        version_ref=version_ref,
        source_refs=(_source_ref(source_id),),
        definitions=tuple(_definition(name) for name in tool_names),
    )


def _import_path_provider(
    spec: ToolsDiscoveryProviderSpec,
) -> ToolsDiscoveryProviderOutput:
    """import path 解析测试 provider。

    :param spec: provider 显式配置。
    :returns: provider 输出。
    :raises Exception: 不主动抛出异常。
    """

    return _output(
        provider_id=f"{spec.spec_id}-provider",
        source_id=spec.spec_id,
        tool_names=(f"{spec.spec_id}_tool",),
    )


def _entry_point_provider(
    spec: ToolsDiscoveryProviderSpec,
) -> ToolsDiscoveryProviderOutput:
    """entry point 解析测试 provider。

    :param spec: provider 显式配置。
    :returns: provider 输出。
    :raises Exception: 不主动抛出异常。
    """

    return _output(
        provider_id="entry-provider",
        source_id=spec.spec_id,
        tool_names=("entry_tool",),
    )


def _blank_identity_provider(
    spec: ToolsDiscoveryProviderSpec,
) -> ToolsDiscoveryProviderOutput:
    """空身份解析测试 provider。

    :param spec: provider 显式配置。
    :returns: provider 输出。
    :raises Exception: 不主动抛出异常。
    """

    return _output(
        provider_id="  ",
        source_id=spec.spec_id,
        tool_names=("blank_identity_tool",),
    )


def test_fake_provider_callable_aggregation_success() -> None:
    """已解析 provider callable 可以聚合为 ``ToolBundle`` 与 provider report。"""

    spec = _spec("alpha")

    def provider(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """测试内联 provider。

        :param spec: provider 显式配置。
        :returns: provider 输出。
        :raises Exception: 不主动抛出异常。
        """

        return _output(
            provider_id="alpha-provider",
            source_id=spec.spec_id,
            tool_names=("lookup_filing", "quote_metric"),
        )

    result = ToolsDiscovery().discover_from_bindings((ToolsDiscoveryProviderBinding(spec=spec, provider=provider),))

    assert result.tool_bundle is not None
    assert tuple(definition.name for definition in result.tool_bundle.definitions) == ("lookup_filing", "quote_metric")
    assert result.provider_reports[0].provider_id == "alpha-provider"
    assert result.provider_reports[0].tool_names == (
        "lookup_filing",
        "quote_metric",
    )
    assert result.source_refs[0].source_kind == ToolBundleSourceKind.EXPLICIT_PROVIDER
    assert result.source_refs[0].source_id == "alpha"
    assert result.source_refs[0].content_digest is not None
    assert result.source_refs[0].content_digest.startswith("sha256:")


def test_import_path_resolution_to_callable() -> None:
    """显式 Python import path 可以解析并调用 provider callable。"""

    result = discover_tools((_spec("imported"),))

    assert result.provider_reports[0].provider_id == "imported-provider"
    assert result.tool_bundle is not None
    assert result.tool_bundle.definitions[0].name == "imported_tool"


def test_import_path_missing_module_raises_tools_discovery_error() -> None:
    """显式 import path 模块缺失必须归一为 ``ToolsDiscoveryError``。"""

    spec = ToolsDiscoveryProviderSpec(
        spec_id="missing-module",
        location=PythonImportPathProvider(import_path="tests.runtime.missing_tools_discovery_provider:provider"),
    )

    with pytest.raises(ToolsDiscoveryError, match="cannot import module") as exc_info:
        discover_tools((spec,))

    assert isinstance(exc_info.value.__cause__, ModuleNotFoundError)


def test_package_entry_point_resolution_to_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """package entry point 可以解析并调用 provider callable。"""

    entry_point = importlib_metadata.EntryPoint(
        name=_ENTRY_POINT_NAME,
        value="tests.runtime.test_tools_discovery:_entry_point_provider",
        group=_ENTRY_POINT_GROUP,
    )

    def fake_entry_points(*, group: str) -> importlib_metadata.EntryPoints:
        """测试用 entry_points 替身。

        :param group: entry point group。
        :returns: 测试 entry point 集合。
        :raises Exception: 不主动抛出异常。
        """

        if group == _ENTRY_POINT_GROUP:
            return importlib_metadata.EntryPoints((entry_point,))
        return importlib_metadata.EntryPoints(())

    monkeypatch.setattr(importlib_metadata, "entry_points", fake_entry_points)

    spec = ToolsDiscoveryProviderSpec(
        spec_id="entry",
        location=PackageEntryPointProvider(
            group=_ENTRY_POINT_GROUP,
            name=_ENTRY_POINT_NAME,
        ),
    )
    provider = resolve_provider_callable(spec)
    result = ToolsDiscovery().discover_from_bindings((ToolsDiscoveryProviderBinding(spec=spec, provider=provider),))

    assert result.provider_reports[0].provider_id == "entry-provider"
    assert result.tool_bundle is not None
    assert result.tool_bundle.definitions[0].name == "entry_tool"


def test_duplicate_provider_identity_fails() -> None:
    """重复 provider identity 必须失败。"""

    def left(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """左侧测试 provider。

        :param spec: provider 显式配置。
        :returns: provider 输出。
        :raises Exception: 不主动抛出异常。
        """

        return _output(
            provider_id="same-provider",
            source_id=spec.spec_id,
            tool_names=("left_tool",),
        )

    def right(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """右侧测试 provider。

        :param spec: provider 显式配置。
        :returns: provider 输出。
        :raises Exception: 不主动抛出异常。
        """

        return _output(
            provider_id="same-provider",
            source_id=spec.spec_id,
            tool_names=("right_tool",),
        )

    with pytest.raises(ToolsDiscoveryError, match="duplicate provider identity"):
        ToolsDiscovery().discover_from_bindings(
            (
                ToolsDiscoveryProviderBinding(spec=_spec("left"), provider=left),
                ToolsDiscoveryProviderBinding(spec=_spec("right"), provider=right),
            )
        )


def test_empty_provider_identity_fails_inside_output_validation() -> None:
    """provider 输出身份为空必须在输出校验阶段失败。

    :returns: ``None``。
    :raises AssertionError: 空 provider identity 未 fail-fast 时抛出。
    """

    with pytest.raises(ToolsDiscoveryError, match="provider identity"):
        ToolsDiscovery().discover_from_bindings(
            (
                ToolsDiscoveryProviderBinding(
                    spec=_spec("blank"),
                    provider=_blank_identity_provider,
                ),
            )
        )


def test_duplicate_tool_name_fails() -> None:
    """不同 provider 返回重复工具名必须失败。"""

    def left(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """左侧测试 provider。

        :param spec: provider 显式配置。
        :returns: provider 输出。
        :raises Exception: 不主动抛出异常。
        """

        return _output(
            provider_id="left-provider",
            source_id=spec.spec_id,
            tool_names=("same_tool",),
        )

    def right(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """右侧测试 provider。

        :param spec: provider 显式配置。
        :returns: provider 输出。
        :raises Exception: 不主动抛出异常。
        """

        return _output(
            provider_id="right-provider",
            source_id=spec.spec_id,
            tool_names=("same_tool",),
        )

    with pytest.raises(ToolsDiscoveryError, match="duplicate tool name"):
        ToolsDiscovery().discover_from_bindings(
            (
                ToolsDiscoveryProviderBinding(spec=_spec("left"), provider=left),
                ToolsDiscoveryProviderBinding(spec=_spec("right"), provider=right),
            )
        )


def test_disabled_provider_is_not_resolved_or_called() -> None:
    """禁用 provider 必须跳过解析与调用。"""

    spec = ToolsDiscoveryProviderSpec(
        spec_id="disabled",
        location=PythonImportPathProvider(import_path="tests.runtime.test_tools_discovery:missing_provider"),
        enabled=False,
    )

    result = discover_tools((spec,))

    assert result.tool_bundle.definitions == ()
    assert result.provider_reports == ()
    assert result.source_refs == ()


def test_empty_provider_without_allow_empty_fails() -> None:
    """provider 空工具输出默认失败。"""

    def provider(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """空输出测试 provider。

        :param spec: provider 显式配置。
        :returns: provider 输出。
        :raises Exception: 不主动抛出异常。
        """

        return _output(
            provider_id="empty-provider",
            source_id=spec.spec_id,
            tool_names=(),
        )

    with pytest.raises(ToolsDiscoveryError, match="returned empty tools"):
        ToolsDiscovery().discover_from_bindings(
            (ToolsDiscoveryProviderBinding(spec=_spec("empty"), provider=provider),)
        )


def test_empty_provider_with_allow_empty_succeeds() -> None:
    """provider 显式允许空输出时以 ``None`` 表达无业务工具。"""

    def provider(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """空输出测试 provider。

        :param spec: provider 显式配置。
        :returns: provider 输出。
        :raises Exception: 不主动抛出异常。
        """

        return _output(
            provider_id="empty-provider",
            source_id=spec.spec_id,
            tool_names=(),
        )

    result = ToolsDiscovery().discover_from_bindings(
        (
            ToolsDiscoveryProviderBinding(
                spec=_spec("empty", allow_empty=True),
                provider=provider,
            ),
        )
    )

    assert result.tool_bundle.definitions == ()
    assert result.provider_reports[0].tool_names == ()
    assert result.source_refs[0].source_kind == ToolBundleSourceKind.EXPLICIT_PROVIDER
    assert result.source_refs[0].source_id == "empty"
    assert result.source_refs[0].content_digest is not None
    assert result.source_refs[0].content_digest.startswith("sha256:")
