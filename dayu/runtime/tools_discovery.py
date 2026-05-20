"""层中立工具发现与 ``ToolBundle`` 聚合。

``ToolsDiscovery`` 只负责按显式 provider spec 解析 provider callable、调用
provider 并聚合 ``ToolDefinition``。本模块不扫描包、不 import Host /
Engine / Service / UI / Fins / 具体业务工具包，也不把 provider callable
或 discovery adapter 放入输出结果。
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata as importlib_metadata
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import ModuleType
from typing import Protocol, TypeAlias, cast

from dayu.contracts import (
    JsonValue,
    ToolBundle,
    ToolBundleSourceRef,
    ToolDefinition,
)

_IMPORT_PATH_SEPARATOR = ":"
_ATTRIBUTE_PATH_SEPARATOR = "."
_CONTENT_DIGEST_PREFIX = "sha256:"
_RESERVED_FRAMEWORK_TOOL_NAMES: frozenset[str] = frozenset({"fetch_more"})


class ToolsDiscoveryError(ValueError):
    """工具发现配置或 provider 输出违反契约时抛出的错误。"""


@dataclass(frozen=True, slots=True)
class PythonImportPathProvider:
    """通过显式 Python import path 解析 provider callable。

    :param import_path: ``module:attribute`` 形式的显式 import path；attribute
        可使用点号访问嵌套属性。
    """

    import_path: str

    def __post_init__(self) -> None:
        """校验 import path 存在非空白内容。

        :returns: 无返回值。
        :raises ValueError: ``import_path`` 为空时抛出。
        """

        _require_non_empty_text(
            self.import_path,
            field_name="PythonImportPathProvider.import_path",
        )


@dataclass(frozen=True, slots=True)
class PackageEntryPointProvider:
    """通过 package entry point 解析 provider callable。

    :param group: entry point group 名称。
    :param name: entry point 名称。
    """

    group: str
    name: str

    def __post_init__(self) -> None:
        """校验 entry point group 与 name 存在非空白内容。

        :returns: 无返回值。
        :raises ValueError: ``group`` 或 ``name`` 为空时抛出。
        """

        _require_non_empty_text(self.group, field_name="PackageEntryPointProvider.group")
        _require_non_empty_text(self.name, field_name="PackageEntryPointProvider.name")


ToolsDiscoveryProviderLocation = PythonImportPathProvider | PackageEntryPointProvider
"""provider callable 的显式解析位置。"""


@dataclass(frozen=True, slots=True)
class ToolsDiscoveryProviderSpec:
    """工具发现 provider 的显式配置。

    spec 是传给 provider callable 的唯一上下文；其中不包含 Host、Service、
    UI、Engine 或业务仓储对象。

    :param spec_id: 装配配置中的 provider spec 稳定标识，用于错误定位。
    :param location: provider callable 的显式解析位置。
    :param enabled: 为 ``False`` 时跳过解析和调用。
    :param allow_empty: provider 返回空工具集合时是否允许通过。
    :param config: provider 自身的结构化 JSON 配置。
    """

    spec_id: str
    location: ToolsDiscoveryProviderLocation
    enabled: bool = True
    allow_empty: bool = False
    config: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 provider spec 的最小完整性。

        :returns: 无返回值。
        :raises ValueError: ``spec_id`` 为空时抛出。
        """

        _require_non_empty_text(self.spec_id, field_name="ToolsDiscoveryProviderSpec.spec_id")


@dataclass(frozen=True, slots=True)
class ToolsDiscoveryProviderOutput:
    """provider callable 的返回值。

    :param provider_id: provider 自声明身份，必须非空且在本次聚合内唯一。
    :param version_ref: provider 可解释版本引用；无版本时为 ``None``。
    :param source_refs: provider 产出工具的来源引用，必须非空。
    :param definitions: provider 产出的工具声明集合。
    """

    provider_id: str
    version_ref: str | None
    source_refs: tuple[ToolBundleSourceRef, ...]
    definitions: tuple[ToolDefinition, ...]


_ProviderCandidate: TypeAlias = Callable[[ToolsDiscoveryProviderSpec], ToolsDiscoveryProviderOutput]
"""动态解析得到的 provider callable 候选形状。"""


class ToolsDiscoveryProviderCallable(Protocol):
    """工具发现 provider callable 协议。"""

    def __call__(self, spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
        """根据显式 provider spec 返回工具声明。

        :param spec: 无 Host / Service 上下文的 provider 显式配置。
        :returns: provider 身份、版本、来源引用与工具声明集合。
        :raises Exception: provider 可抛出自身配置或加载错误。
        """

        ...


@dataclass(frozen=True, slots=True)
class ToolsDiscoveryProviderBinding:
    """已解析 provider callable 与其 spec 的绑定。

    :param spec: provider 显式配置。
    :param provider: 已解析 callable；只作为 runtime discovery 输入存在，
        不会进入 ``ToolsDiscoveryResult``。
    """

    spec: ToolsDiscoveryProviderSpec
    provider: ToolsDiscoveryProviderCallable


@dataclass(frozen=True, slots=True)
class ToolsDiscoveryProviderReport:
    """provider 聚合报告。

    :param provider_id: provider 自声明身份。
    :param spec_id: provider spec 稳定标识。
    :param version_ref: provider 可解释版本引用；无版本时为 ``None``。
    :param source_refs: provider 产出工具的来源引用。
    :param tool_names: provider 产出的工具名元组。
    """

    provider_id: str
    spec_id: str
    version_ref: str | None
    source_refs: tuple[ToolBundleSourceRef, ...]
    tool_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolsDiscoveryResult:
    """工具发现聚合结果。

    :param tool_bundle: 聚合后的业务工具 bundle。
    :param provider_reports: provider 级别报告，不包含 callable 或 adapter。
    :param source_refs: 按 provider 输出顺序拼接的来源引用。
    """

    tool_bundle: ToolBundle
    provider_reports: tuple[ToolsDiscoveryProviderReport, ...]
    source_refs: tuple[ToolBundleSourceRef, ...]


class ToolsDiscovery:
    """层中立工具发现聚合器。"""

    def discover(self, provider_specs: Sequence[ToolsDiscoveryProviderSpec]) -> ToolsDiscoveryResult:
        """解析并聚合启用的 provider specs。

        :param provider_specs: provider 显式配置序列。
        :returns: 聚合后的 ``ToolBundle``、provider report 与 source refs。
        :raises ToolsDiscoveryError: provider 解析、身份、空输出或工具名重复
            违反契约时抛出。
        """

        bindings: list[ToolsDiscoveryProviderBinding] = []
        for spec in provider_specs:
            if spec.enabled:
                bindings.append(
                    ToolsDiscoveryProviderBinding(
                        spec=spec,
                        provider=resolve_provider_callable(spec),
                    )
                )
        return self.discover_from_bindings(tuple(bindings))

    def discover_from_bindings(
        self, provider_bindings: Sequence[ToolsDiscoveryProviderBinding]
    ) -> ToolsDiscoveryResult:
        """聚合已解析的 provider callable。

        :param provider_bindings: provider spec 与 callable 的绑定序列。
        :returns: 聚合后的 ``ToolBundle``、provider report 与 source refs。
        :raises ToolsDiscoveryError: provider 身份、空输出或工具名重复违反契约
            时抛出。
        """

        provider_ids: set[str] = set()
        definitions: list[ToolDefinition] = []
        reports: list[ToolsDiscoveryProviderReport] = []
        source_refs: list[ToolBundleSourceRef] = []
        for binding in provider_bindings:
            if not binding.spec.enabled:
                continue
            output = binding.provider(binding.spec)
            provider_id = _require_provider_identity(output.provider_id)
            if provider_id in provider_ids:
                raise ToolsDiscoveryError(f"duplicate provider identity: {provider_id}")
            provider_ids.add(provider_id)
            _validate_provider_output(
                spec=binding.spec,
                output=output,
            )
            _validate_reserved_tool_names(output.definitions)
            normalized_source_refs = _normalize_source_refs_with_digest(
                source_refs=output.source_refs,
                content_digest=_tool_definitions_digest(output.definitions),
            )
            tool_names = tuple(definition.name for definition in output.definitions)
            reports.append(
                ToolsDiscoveryProviderReport(
                    provider_id=provider_id,
                    spec_id=binding.spec.spec_id,
                    version_ref=output.version_ref,
                    source_refs=normalized_source_refs,
                    tool_names=tool_names,
                )
            )
            definitions.extend(output.definitions)
            source_refs.extend(normalized_source_refs)
        _validate_unique_tool_names(tuple(definitions))
        return ToolsDiscoveryResult(
            tool_bundle=ToolBundle(definitions=tuple(definitions)),
            provider_reports=tuple(reports),
            source_refs=tuple(source_refs),
        )


def discover_tools(
    provider_specs: Sequence[ToolsDiscoveryProviderSpec],
) -> ToolsDiscoveryResult:
    """使用默认 ``ToolsDiscovery`` 聚合 provider specs。

    :param provider_specs: provider 显式配置序列。
    :returns: 聚合后的 ``ToolBundle``、provider report 与 source refs。
    :raises ToolsDiscoveryError: provider 解析、身份、空输出或工具名重复违反
        契约时抛出。
    """

    return ToolsDiscovery().discover(provider_specs)


def resolve_provider_callable(
    spec: ToolsDiscoveryProviderSpec,
) -> ToolsDiscoveryProviderCallable:
    """按 provider spec 的显式位置解析 callable。

    :param spec: provider 显式配置。
    :returns: 已解析 provider callable。
    :raises ToolsDiscoveryError: 位置类型未知、import path / entry point 缺失、
        重复或解析结果不可调用时抛出。
    """

    location = spec.location
    if isinstance(location, PythonImportPathProvider):
        return _resolve_import_path(location.import_path)
    if isinstance(location, PackageEntryPointProvider):
        return _resolve_entry_point(location)
    raise ToolsDiscoveryError(f"unsupported provider location for spec: {spec.spec_id}")


def _resolve_import_path(import_path: str) -> ToolsDiscoveryProviderCallable:
    """解析 ``module:attribute`` 形式的 provider callable。

    :param import_path: 显式 import path。
    :returns: provider callable。
    :raises ToolsDiscoveryError: import path 格式非法或解析结果不可调用时抛出。
    """

    module_name, separator, attribute_path = import_path.partition(_IMPORT_PATH_SEPARATOR)
    if not separator or not module_name.strip() or not attribute_path.strip():
        raise ToolsDiscoveryError("provider import_path must use non-empty module:attribute format")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ToolsDiscoveryError(f"provider import_path cannot import module: {module_name}") from exc
    provider = _resolve_attribute_path(
        root=module,
        attribute_path=attribute_path,
        source=f"provider import_path {import_path}",
    )
    return _require_callable(provider, source=f"provider import_path {import_path}")


def _resolve_entry_point(
    location: PackageEntryPointProvider,
) -> ToolsDiscoveryProviderCallable:
    """解析 package entry point provider callable。

    :param location: entry point 位置。
    :returns: provider callable。
    :raises ToolsDiscoveryError: entry point 缺失、重复或解析结果不可调用时抛出。
    """

    entry_points = importlib_metadata.entry_points(group=location.group)
    matches: list[importlib_metadata.EntryPoint] = []
    for entry_point in entry_points:
        if entry_point.name == location.name:
            matches.append(entry_point)
    if not matches:
        raise ToolsDiscoveryError("provider entry point not found:" f" group={location.group} name={location.name}")
    if len(matches) > 1:
        raise ToolsDiscoveryError("provider entry point is ambiguous:" f" group={location.group} name={location.name}")
    provider = matches[0].load()
    return _require_callable(
        provider,
        source=f"provider entry point {location.group}:{location.name}",
    )


def _resolve_attribute_path(*, root: ModuleType, attribute_path: str, source: str) -> _ProviderCandidate:
    """解析动态 import path 的属性路径。

    ``getattr`` 只在这里用于显式 import path 契约解析；业务边界不通过它逃逸
    类型设计。

    :param root: 属性解析起点。
    :param attribute_path: 点号分隔的属性路径。
    :param source: 错误消息中的来源描述。
    :returns: 解析出的候选 provider callable。
    :raises ToolsDiscoveryError: 属性路径为空或任一属性不存在时抛出。
    """

    current: ModuleType | _ProviderCandidate = root
    for attribute_name in attribute_path.split(_ATTRIBUTE_PATH_SEPARATOR):
        if not attribute_name.strip():
            raise ToolsDiscoveryError(f"{source} contains empty attribute segment")
        try:
            current = cast(_ProviderCandidate, getattr(current, attribute_name))
        except AttributeError as exc:
            raise ToolsDiscoveryError(f"{source} cannot resolve attribute: {attribute_name}") from exc
    return cast(_ProviderCandidate, current)


def _require_callable(candidate: _ProviderCandidate, *, source: str) -> ToolsDiscoveryProviderCallable:
    """校验动态解析结果可调用并投影为 provider callable。

    :param candidate: 动态解析得到的候选值。
    :param source: 错误消息中的来源描述。
    :returns: provider callable。
    :raises ToolsDiscoveryError: 候选值不可调用时抛出。
    """

    if not callable(candidate):
        raise ToolsDiscoveryError(f"{source} did not resolve to a callable")
    return cast(ToolsDiscoveryProviderCallable, candidate)


def _tool_definitions_digest(definitions: tuple[ToolDefinition, ...]) -> str:
    """计算 provider 工具声明内容摘要。

    摘要只覆盖工具声明内容：工具名、LLM-facing schema、截断声明、标签与
    展示 metadata。它不包含 callable 引用、模块路径对象身份、权限、lease、
    fencing、Host truth 或 owner 信息；仅用于解释、诊断、trace、audit 与
    后续 snapshot refs。

    :param definitions: provider 按声明顺序返回的工具定义。
    :returns: ``sha256:<hex>`` 形式的稳定内容摘要。
    :raises TypeError: 声明中的 JSON 值无法规范化时抛出。
    :raises ValueError: 声明中的浮点数不是合法 JSON number 时抛出。
    """

    tools: list[JsonValue] = [
        _tool_definition_json_value(definition) for definition in definitions
    ]
    payload: dict[str, JsonValue] = {"tools": tools}
    return _canonical_json_digest(payload)


def _normalize_source_refs_with_digest(
    *,
    source_refs: tuple[ToolBundleSourceRef, ...],
    content_digest: str,
) -> tuple[ToolBundleSourceRef, ...]:
    """把 provider 来源引用规范化为统一计算的内容摘要。

    provider 可以返回已有 ``content_digest``，但 discovery 是声明摘要真源，
    因此这里总是以本次 provider 声明内容重新计算的摘要替换。

    :param source_refs: provider 返回的来源引用。
    :param content_digest: discovery 计算出的 provider 声明摘要。
    :returns: 保留来源类别、来源标识与版本引用的新来源引用元组。
    :raises ValueError: 来源引用字段非法时由 ``ToolBundleSourceRef`` 抛出。
    """

    return tuple(
        ToolBundleSourceRef(
            source_kind=source_ref.source_kind,
            source_id=source_ref.source_id,
            version_ref=source_ref.version_ref,
            content_digest=content_digest,
        )
        for source_ref in source_refs
    )


def _tool_definition_json_value(definition: ToolDefinition) -> JsonValue:
    """把工具声明投影为用于 digest 的 JSON 值。

    :param definition: 工具定义。
    :returns: 不包含 callable 的工具声明 JSON 投影。
    :raises Exception: 不主动抛出异常。
    """

    value: dict[str, JsonValue] = {
        "name": definition.name,
        "schema": _tool_schema_json_value(definition),
        "truncate": _tool_truncate_json_value(definition),
        "tags": list(definition.tags),
        "display": (
            definition.display.name
            if definition.display is not None
            else None
        ),
    }
    return value


def _tool_schema_json_value(definition: ToolDefinition) -> JsonValue:
    """把 LLM-facing schema 投影为用于 digest 的 JSON 值。

    :param definition: 工具定义。
    :returns: schema JSON 投影。
    :raises Exception: 不主动抛出异常。
    """

    schema = definition.schema
    function = schema.function
    parameters = function.parameters
    value: dict[str, JsonValue] = {
        "type": schema.type,
        "function": {
            "name": function.name,
            "description": function.description,
            "parameters": {
                "type": parameters.type,
                "properties": _normalize_json_value(parameters.properties),
                "required": list(parameters.required),
                "additional_properties": parameters.additional_properties,
            },
        },
    }
    return value


def _tool_truncate_json_value(definition: ToolDefinition) -> JsonValue:
    """把截断声明投影为用于 digest 的 JSON 值。

    :param definition: 工具定义。
    :returns: 截断声明 JSON 投影；未声明截断时为 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    truncate = definition.truncate
    if truncate is None:
        return None
    value: dict[str, JsonValue] = {
        "enabled": truncate.enabled,
        "strategy": (
            truncate.strategy.value
            if truncate.strategy is not None
            else None
        ),
        "limits": _int_mapping_json_value(truncate.limits),
        "target_field": truncate.target_field,
        "field_path": (
            list(truncate.field_path)
            if truncate.field_path is not None
            else None
        ),
        "ttl_seconds": truncate.ttl_seconds,
    }
    return value


def _int_mapping_json_value(values: Mapping[str, int]) -> JsonValue:
    """把整数映射投影为 JSON object。

    :param values: 字符串到整数的映射。
    :returns: JSON object 投影。
    :raises Exception: 不主动抛出异常。
    """

    result: dict[str, JsonValue] = {}
    for key, value in values.items():
        result[key] = value
    return result


def _canonical_json_digest(value: JsonValue) -> str:
    """对 JSON 值计算 canonical SHA-256 摘要。

    本 helper 只依赖 stdlib ``json`` 与 ``hashlib``，不复用 Host durable
    codec，避免 runtime 反向依赖 Host。

    :param value: 待摘要的 JSON 值。
    :returns: ``sha256:<hex>`` 形式的摘要。
    :raises TypeError: JSON 值中包含无法序列化的值时抛出。
    :raises ValueError: JSON 值中包含 NaN 或无穷浮点数时抛出。
    """

    normalized = _normalize_json_value(value)
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return _CONTENT_DIGEST_PREFIX + hashlib.sha256(payload).hexdigest()


def _normalize_json_value(value: JsonValue) -> JsonValue:
    """把 ``JsonValue`` 递归转换为 stdlib ``json`` 可稳定处理的结构。

    :param value: 待规范化的 JSON 值。
    :returns: 只包含 JSON 基本类型、``list`` 与 ``dict`` 的值。
    :raises TypeError: 输入不是合法 ``JsonValue`` 形态时抛出。
    """

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JsonValue object key must be str")
            result[key] = _normalize_json_value(item)
        return result
    raise TypeError("JsonValue contains unsupported value")


def _validate_provider_output(
    *,
    spec: ToolsDiscoveryProviderSpec,
    output: ToolsDiscoveryProviderOutput,
) -> None:
    """校验 provider 输出的最小完整性。

    :param spec: provider 显式配置。
    :param output: provider 输出。
    :returns: 无返回值。
    :raises ToolsDiscoveryError: source refs 为空、version 为空字符串，或空工具
        输出未显式允许时抛出。
    """

    _require_optional_non_empty_text(
        output.version_ref,
        field_name="ToolsDiscoveryProviderOutput.version_ref",
    )
    if not output.source_refs:
        raise ToolsDiscoveryError(f"provider {output.provider_id} must return non-empty source_refs")
    if not output.definitions and not spec.allow_empty:
        raise ToolsDiscoveryError(f"provider {output.provider_id} returned empty tools")


def _validate_unique_tool_names(definitions: tuple[ToolDefinition, ...]) -> None:
    """校验聚合后的工具名唯一。

    :param definitions: 聚合后的工具定义。
    :returns: 无返回值。
    :raises ToolsDiscoveryError: 出现重复工具名时抛出。
    """

    names: set[str] = set()
    for definition in definitions:
        if definition.name in names:
            raise ToolsDiscoveryError(f"duplicate tool name: {definition.name}")
        names.add(definition.name)


def _validate_reserved_tool_names(definitions: tuple[ToolDefinition, ...]) -> None:
    """校验业务工具未占用 framework 预留名称。

    ``ToolsDiscovery`` 只做 runtime assembly 阶段的业务工具声明校验，不注入
    framework tool，也不改变 ToolRuntime accept barrier。

    :param definitions: provider 返回的工具定义。
    :returns: 无返回值。
    :raises ToolsDiscoveryError: 业务工具名占用 framework 预留名称时抛出。
    """

    for definition in definitions:
        if definition.name in _RESERVED_FRAMEWORK_TOOL_NAMES:
            raise ToolsDiscoveryError(
                "business tool name is reserved for framework tool:"
                f" {definition.name}"
            )


def _require_provider_identity(provider_id: str) -> str:
    """校验 provider 身份非空。

    :param provider_id: provider 自声明身份。
    :returns: 去除首尾空白后的 provider 身份。
    :raises ToolsDiscoveryError: 身份为空时抛出。
    """

    stripped = provider_id.strip()
    if not stripped:
        raise ToolsDiscoveryError("provider identity must be non-empty")
    return stripped


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验字符串存在非空白内容。

    :param value: 待校验字符串。
    :param field_name: 错误消息中的字段名。
    :returns: 无返回值。
    :raises ValueError: 字符串为空或只包含空白时抛出。
    """

    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty_text(value: str | None, *, field_name: str) -> None:
    """校验可选字符串在存在时包含非空白内容。

    :param value: 待校验字符串；``None`` 表示未提供。
    :param field_name: 错误消息中的字段名。
    :returns: 无返回值。
    :raises ValueError: 字符串存在但为空或只包含空白时抛出。
    """

    if value is not None:
        _require_non_empty_text(value, field_name=field_name)


__all__ = [
    "PackageEntryPointProvider",
    "PythonImportPathProvider",
    "ToolsDiscovery",
    "ToolsDiscoveryError",
    "ToolsDiscoveryProviderBinding",
    "ToolsDiscoveryProviderCallable",
    "ToolsDiscoveryProviderLocation",
    "ToolsDiscoveryProviderOutput",
    "ToolsDiscoveryProviderReport",
    "ToolsDiscoveryProviderSpec",
    "ToolsDiscoveryResult",
    "discover_tools",
    "resolve_provider_callable",
]
