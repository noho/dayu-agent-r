"""``ToolsDiscovery`` source refs 与 digest 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from dayu.contracts import (
    BatchToolExecutionContext,
    JsonValue,
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    ToolCallRequest,
    ToolCallable,
    ToolCancelledOutcome,
    ToolDefinition,
    ToolDisplayInfo,
    ToolExecutionOutcome,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryError,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
)


async def _noop_tool(
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
) -> ToolExecutionOutcome:
    """测试用工具 callable。

    :param call: 单次工具调用请求。
    :param context: 批式工具执行上下文。
    :returns: 取消 outcome。
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


async def _alternate_noop_tool(
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
) -> ToolExecutionOutcome:
    """测试用替代工具 callable。

    :param call: 单次工具调用请求。
    :param context: 批式工具执行上下文。
    :returns: 取消 outcome。
    :raises Exception: 不主动抛出异常。
    """

    del call
    del context
    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
        message="alternate tool disabled in test",
        hint=None,
        meta=None,
    )


def _parameters(*, property_description: str = "company id") -> ToolParametersSchema:
    """构造测试用参数 schema。

    :param property_description: 参数描述。
    :returns: 工具参数 schema。
    :raises Exception: 不主动抛出异常。
    """

    properties: dict[str, JsonValue] = {
        "company_id": {
            "type": "string",
            "description": property_description,
        }
    }
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("company_id",),
        additional_properties=False,
    )


def _definition(
    *,
    name: str = "lookup_filing",
    description: str = "Lookup filing",
    property_description: str = "company id",
    truncate: ToolTruncateSpec | None = None,
    display: ToolDisplayInfo | None = None,
    tags: tuple[str, ...] = (),
    callable_: ToolCallable = _noop_tool,
) -> ToolDefinition:
    """构造测试用工具声明。

    :param name: 工具名。
    :param description: LLM-facing 描述。
    :param property_description: 参数描述。
    :param truncate: 截断声明。
    :param display: 展示 metadata。
    :param tags: 工具标签。
    :param callable_: 测试 callable。
    :returns: 工具定义。
    :raises ValueError: 工具声明名称与 schema 名称不一致时抛出。
    """

    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=description,
                parameters=_parameters(
                    property_description=property_description,
                ),
            ),
        ),
        callable=callable_,
        truncate=truncate,
        display=display,
        tags=tags,
    )


def _truncate_spec(max_chars: int = 1200) -> ToolTruncateSpec:
    """构造测试用截断声明。

    :param max_chars: 最大字符数。
    :returns: 截断声明。
    :raises ValueError: 截断字段组合非法时抛出。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": max_chars},
        target_field="content",
        field_path=None,
        ttl_seconds=60,
    )


def _spec(spec_id: str = "provider") -> ToolsDiscoveryProviderSpec:
    """构造测试用 provider spec。

    :param spec_id: provider spec 标识。
    :returns: provider spec。
    :raises ValueError: spec 字段为空时抛出。
    """

    return ToolsDiscoveryProviderSpec(
        spec_id=spec_id,
        location=PythonImportPathProvider(
            import_path="tests.runtime.test_tools_discovery_digest:_unused_provider"
        ),
    )


def _unused_provider(
    spec: ToolsDiscoveryProviderSpec,
) -> ToolsDiscoveryProviderOutput:
    """占位 provider，仅用于 import path 字段满足 spec 契约。

    :param spec: provider 显式配置。
    :returns: provider 输出。
    :raises AssertionError: 被调用时抛出。
    """

    del spec
    raise AssertionError("test should use resolved provider binding")


def _source_ref(
    *,
    kind: ToolBundleSourceKind = ToolBundleSourceKind.EXPLICIT_PROVIDER,
    source_id: str = "provider",
    version_ref: str | None = "v1",
    content_digest: str | None = None,
) -> ToolBundleSourceRef:
    """构造测试用来源引用。

    :param kind: 来源类别。
    :param source_id: 来源标识。
    :param version_ref: 版本引用。
    :param content_digest: provider 预填摘要。
    :returns: 来源引用。
    :raises ValueError: 来源引用字段非法时抛出。
    """

    return ToolBundleSourceRef(
        source_kind=kind,
        source_id=source_id,
        version_ref=version_ref,
        content_digest=content_digest,
    )


def _discover_digest(definitions: tuple[ToolDefinition, ...]) -> str:
    """执行 discovery 并返回首个来源引用 digest。

    :param definitions: provider 输出的工具声明。
    :returns: 首个 source ref 的 digest。
    :raises AssertionError: discovery 未产出 digest 时抛出。
    """

    def provider(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """测试 provider。

        :param spec: provider 显式配置。
        :returns: provider 输出。
        :raises Exception: 不主动抛出异常。
        """

        return ToolsDiscoveryProviderOutput(
            provider_id=f"{spec.spec_id}-provider",
            version_ref="v1",
            source_refs=(_source_ref(source_id=spec.spec_id),),
            definitions=definitions,
        )

    result = ToolsDiscovery().discover_from_bindings(
        (ToolsDiscoveryProviderBinding(spec=_spec(), provider=provider),)
    )
    digest = result.source_refs[0].content_digest
    assert digest is not None
    return digest


def test_same_provider_declaration_order_produces_stable_digest() -> None:
    """同一 provider 声明顺序稳定时 digest 稳定。"""

    definitions = (
        _definition(name="lookup_filing"),
        _definition(name="quote_metric"),
    )

    assert _discover_digest(definitions) == _discover_digest(definitions)


def test_callable_identity_change_does_not_change_digest() -> None:
    """callable 引用变化但声明内容不变时 digest 不变。"""

    left = _definition(callable_=_noop_tool)
    right = _definition(callable_=_alternate_noop_tool)

    assert _discover_digest((left,)) == _discover_digest((right,))


def test_schema_change_changes_digest() -> None:
    """LLM-facing schema 变化必须改变 digest。"""

    left = _definition(description="Lookup filing")
    right = _definition(description="Lookup annual filing")

    assert _discover_digest((left,)) != _discover_digest((right,))


def test_truncate_change_changes_digest() -> None:
    """截断声明变化必须改变 digest。"""

    left = _definition(truncate=_truncate_spec(max_chars=1200))
    right = _definition(truncate=_truncate_spec(max_chars=1800))

    assert _discover_digest((left,)) != _discover_digest((right,))


def test_tags_change_changes_digest() -> None:
    """标签变化必须改变 digest。"""

    left = _definition(tags=("filing",))
    right = _definition(tags=("filing", "quote"))

    assert _discover_digest((left,)) != _discover_digest((right,))


def test_display_change_changes_digest() -> None:
    """展示 metadata 变化必须改变 digest。"""

    left = _definition(display=ToolDisplayInfo(name="Filing Lookup"))
    right = _definition(display=ToolDisplayInfo(name="Annual Filing Lookup"))

    assert _discover_digest((left,)) != _discover_digest((right,))


def test_schema_mapping_with_non_string_key_is_rejected() -> None:
    """schema 映射包含非字符串 key 时 discovery 必须快速失败。"""

    malformed_properties = cast(
        Mapping[str, JsonValue],
        {1: {"type": "string"}},
    )
    definition = ToolDefinition(
        name="lookup_filing",
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name="lookup_filing",
                description="Lookup filing",
                parameters=ToolParametersSchema(
                    type="object",
                    properties=malformed_properties,
                    required=("company_id",),
                    additional_properties=False,
                ),
            ),
        ),
        callable=_noop_tool,
        truncate=None,
        display=None,
        tags=(),
    )

    with pytest.raises(TypeError, match="JsonValue object key must be str"):
        _discover_digest((definition,))


def test_source_refs_preserve_kind_id_version_and_replace_digest() -> None:
    """provider 来源引用必须保留来源字段并替换为计算 digest。"""

    source_refs = (
        _source_ref(
            kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
            source_id="explicit",
            version_ref="v1",
            content_digest="sha256:stale",
        ),
        _source_ref(
            kind=ToolBundleSourceKind.CONFIG_BINDING,
            source_id="config",
            version_ref="v2",
        ),
        _source_ref(
            kind=ToolBundleSourceKind.PACKAGE_ENTRYPOINT,
            source_id="entry",
            version_ref="v3",
        ),
    )

    def provider(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """测试 provider。

        :param spec: provider 显式配置。
        :returns: provider 输出。
        :raises Exception: 不主动抛出异常。
        """

        del spec
        return ToolsDiscoveryProviderOutput(
            provider_id="provider",
            version_ref="v1",
            source_refs=source_refs,
            definitions=(_definition(),),
        )

    result = ToolsDiscovery().discover_from_bindings(
        (ToolsDiscoveryProviderBinding(spec=_spec(), provider=provider),)
    )

    normalized = result.source_refs
    assert tuple(ref.source_kind for ref in normalized) == (
        ToolBundleSourceKind.EXPLICIT_PROVIDER,
        ToolBundleSourceKind.CONFIG_BINDING,
        ToolBundleSourceKind.PACKAGE_ENTRYPOINT,
    )
    assert tuple(ref.source_id for ref in normalized) == (
        "explicit",
        "config",
        "entry",
    )
    assert tuple(ref.version_ref for ref in normalized) == ("v1", "v2", "v3")
    digests = tuple(ref.content_digest for ref in normalized)
    assert digests[0] is not None
    assert digests[0].startswith("sha256:")
    assert digests == (digests[0], digests[0], digests[0])
    assert result.provider_reports[0].source_refs == normalized


def test_business_tool_named_fetch_more_is_rejected() -> None:
    """业务工具不得占用 framework 保留名称 ``fetch_more``。"""

    def provider(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """测试 provider。

        :param spec: provider 显式配置。
        :returns: provider 输出。
        :raises Exception: 不主动抛出异常。
        """

        return ToolsDiscoveryProviderOutput(
            provider_id=f"{spec.spec_id}-provider",
            version_ref="v1",
            source_refs=(_source_ref(source_id=spec.spec_id),),
            definitions=(_definition(name="fetch_more"),),
        )

    with pytest.raises(ToolsDiscoveryError, match="reserved"):
        ToolsDiscovery().discover_from_bindings(
            (ToolsDiscoveryProviderBinding(spec=_spec(), provider=provider),)
        )
