"""Host ToolRuntime 的 attempt-local typed ports。

本模块只落地 Phase 6 S1 需要的 ToolRuntime 装配边界：把外部业务
``ToolBundle`` 与可选 framework tool 注入合成为同一个
``EffectiveToolBundle``，并由 ``ToolRuntimeHandle`` 同时暴露 Engine
可见 schema 与批式 ``ToolExecutor``。本 slice 不实现 Host accept
barrier、真实工具调用、截断、fetch_more callable、重复治理或 durable
工具事实写入。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure
from dayu.contracts.tool_schema import (
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.tooling import (
    FrameworkToolName,
    FrameworkToolPolicyView,
    ToolBundleSourceRef,
)

_UNSUPPORTED_EXECUTOR_ERROR = "tool_runtime_not_connected"
_UNSUPPORTED_EXECUTOR_MESSAGE = (
    "ToolRuntime executor is not connected in Phase 6 S1"
)


class ToolPolicyDecisionKind(StrEnum):
    """工具治理决策类别。

    当前 slice 只定义后续端口会复用的稳定枚举，不实现决策算法。
    """

    ALLOW = "allow"
    GOVERNED_ERROR = "governed_error"
    REUSE = "reuse"
    HINT = "hint"
    REQUIRE_JUSTIFICATION = "require_justification"
    HARD_STOP = "hard_stop"


class DuplicateDecisionKind(StrEnum):
    """同 Run 语义级重复工具调用决策类别。"""

    ALLOW = "allow"
    REUSE = "reuse"
    HINT = "hint"
    REQUIRE_JUSTIFICATION = "require_justification"
    HARD_STOP = "hard_stop"


@dataclass(frozen=True, slots=True)
class ToolPolicyDecision:
    """工具调用治理决策。

    :param kind: 决策类别。
    :param reason_code: 机器可读原因；无原因时为 ``None``。
    :param message: 面向诊断或 LLM 的说明；无说明时为 ``None``。
    """

    kind: ToolPolicyDecisionKind
    reason_code: str | None
    message: str | None


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    """重复工具调用治理决策。

    :param kind: 重复治理类别。
    :param duplicate_key: 当前调用的重复键；未产生时为 ``None``。
    :param prior_event_refs: 可复用的既有事件引用；无复用时为空元组。
    """

    kind: DuplicateDecisionKind
    duplicate_key: str | None
    prior_event_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TruncationAppliedOutcome:
    """截断端口输出。

    :param outcome: 可能已被截断改写的工具 outcome。
    :param cursor_hint: 普通工具结果中可提示 ``fetch_more`` 的 cursor；无为 ``None``。
    """

    outcome: ToolExecutionOutcome
    cursor_hint: str | None


@dataclass(frozen=True, slots=True)
class ToolTraceDiagnosticRecord:
    """ToolRuntime 诊断记录。

    :param reason_code: 诊断机器码。
    :param message: 人类可读诊断说明。
    """

    reason_code: str
    message: str


@dataclass(frozen=True, slots=True)
class ToolTraceDiagnosticRef:
    """ToolRuntime 诊断引用。

    :param ref_id: 诊断记录引用 id。
    """

    ref_id: str


class FrameworkToolInjector(Protocol):
    """framework tool 注入 hook 协议。"""

    def build_framework_tool(self, tool_name: FrameworkToolName) -> ToolDefinition:
        """构造指定 framework tool 的声明。

        :param tool_name: framework tool 名称。
        :returns: 对应工具声明。
        :raises ValueError: 不支持指定 framework tool 时抛出。
        """
        ...


class ToolDispatcher(Protocol):
    """单工具 dispatch 端口协议。"""

    async def dispatch_tool_call(
        self, call: ToolCallRequest, context: BatchToolExecutionContext
    ) -> ToolExecutionOutcome:
        """分发单次工具调用。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行共享上下文。
        :returns: 工具执行 outcome。
        :raises Exception: 实现可抛出运行期异常，由 ToolRuntime 外层归一。
        """
        ...


class ToolRuntimePolicyPort(Protocol):
    """ToolRuntime 治理决策端口协议。"""

    def decide_tool_call(self, call: ToolCallRequest) -> ToolPolicyDecision:
        """为单次工具调用生成治理决策。

        :param call: 单次工具调用请求。
        :returns: 治理决策。
        """
        ...


class TruncationPort(Protocol):
    """工具结果截断端口协议。"""

    def apply_truncation(
        self,
        tool_name: str,
        outcome: ToolExecutionOutcome,
        truncate_spec: ToolTruncateSpec | None,
    ) -> TruncationAppliedOutcome:
        """应用工具结果截断策略。

        :param tool_name: 工具名。
        :param outcome: 原始工具 outcome。
        :param truncate_spec: effective bundle 中同名工具的截断声明。
        :returns: 截断后的 outcome 与 cursor hint。
        """
        ...


class DuplicateGovernancePort(Protocol):
    """重复工具调用治理端口协议。"""

    def decide_duplicate(
        self, tool_name: str, normalized_arguments_digest: str
    ) -> DuplicateDecision:
        """判断当前工具调用是否与同 Run 既有调用重复。

        :param tool_name: 工具名。
        :param normalized_arguments_digest: canonical 参数摘要。
        :returns: 重复治理决策。
        """
        ...


class HostToolFactAcceptPort(Protocol):
    """工具 canonical fact accept barrier 端口协议。"""

    def accept_tool_fact(self, candidate_digest: str) -> str:
        """接受工具事实候选。

        :param candidate_digest: 工具事实候选的 canonical digest。
        :returns: accepted ack 引用。
        :raises RuntimeError: accept path 不可用或拒绝时抛出。
        """
        ...


class ToolTraceDiagnosticEmitter(Protocol):
    """ToolRuntime 诊断发射端口协议。"""

    def emit(self, record: ToolTraceDiagnosticRecord) -> ToolTraceDiagnosticRef:
        """发出一条诊断记录。

        :param record: 诊断记录。
        :returns: 诊断引用。
        """
        ...


@dataclass(frozen=True, slots=True)
class EffectiveToolBundle:
    """Attempt-local effective 工具集合。

    :param business_bundle: 外部装配传入的业务工具集合。
    :param definitions_by_name: effective 工具声明映射。
    :param tool_schemas: 从同一 effective bundle 投影出的 Engine schema。
    :param truncate_specs_by_name: 从同一 effective bundle 投影出的截断声明。
    :param source_refs: 业务工具来源引用。
    :param enabled_framework_tools: policy view 中启用的 framework tool 集合。
    :param injected_framework_tool_names: 本次实际注入的 framework tool 名称。
    :param business_bundle_digest: 业务 bundle 诊断摘要。
    :param effective_schema_digest: effective schema 诊断摘要。
    :param policy_snapshot_digest: policy snapshot 摘要；无时为 ``None``。
    """

    business_bundle: ToolBundle
    definitions_by_name: Mapping[str, ToolDefinition]
    tool_schemas: tuple[ToolSchema, ...]
    truncate_specs_by_name: Mapping[str, ToolTruncateSpec]
    source_refs: tuple[ToolBundleSourceRef, ...]
    enabled_framework_tools: frozenset[FrameworkToolName]
    injected_framework_tool_names: frozenset[FrameworkToolName]
    business_bundle_digest: str
    effective_schema_digest: str
    policy_snapshot_digest: str | None


@dataclass(frozen=True, slots=True)
class EffectiveToolBundleBuildRequest:
    """EffectiveToolBundleBuilder 的输入。

    :param business_tool_bundle: 外部装配好的业务工具集合。
    :param source_refs: 业务工具来源引用。
    :param framework_tool_policy: framework tool policy view。
    :param policy_snapshot_digest: policy snapshot 摘要；无时为 ``None``。
    """

    business_tool_bundle: ToolBundle
    source_refs: tuple[ToolBundleSourceRef, ...]
    framework_tool_policy: FrameworkToolPolicyView
    policy_snapshot_digest: str | None


class EffectiveToolBundleBuilder:
    """构造 attempt-local effective 工具集合。"""

    def __init__(
        self, framework_injector: FrameworkToolInjector | None = None
    ) -> None:
        """初始化 builder。

        :param framework_injector: 可选 framework tool 注入 hook；无 hook 时不注入。
        :returns: ``None``。
        """

        self._framework_injector = framework_injector

    def build(
        self, request: EffectiveToolBundleBuildRequest
    ) -> EffectiveToolBundle:
        """从业务 bundle 与 framework policy 构造 effective bundle。

        :param request: effective bundle 构造输入。
        :returns: attempt-local effective bundle。
        :raises ValueError: 来源引用为空、业务工具占用预留名或注入结果非法时抛出。
        """

        if not request.source_refs:
            raise ValueError("EffectiveToolBundle.source_refs must be non-empty")
        _validate_reserved_name_conflicts(
            request.business_tool_bundle,
            request.framework_tool_policy,
        )
        definitions = list(request.business_tool_bundle.definitions)
        injected = self._inject_framework_definitions(request.framework_tool_policy)
        definitions.extend(injected)
        definitions_by_name = _definitions_by_name(definitions)
        tool_schemas = tuple(
            definition.to_tool_schema() for definition in definitions
        )
        truncate_specs = {
            definition.name: definition.truncate
            for definition in definitions
            if definition.truncate is not None
        }
        return EffectiveToolBundle(
            business_bundle=request.business_tool_bundle,
            definitions_by_name=MappingProxyType(definitions_by_name),
            tool_schemas=tool_schemas,
            truncate_specs_by_name=MappingProxyType(truncate_specs),
            source_refs=request.source_refs,
            enabled_framework_tools=request.framework_tool_policy.enabled_framework_tools,
            injected_framework_tool_names=frozenset(
                FrameworkToolName(definition.name) for definition in injected
            ),
            business_bundle_digest=_business_bundle_digest(
                request.business_tool_bundle
            ),
            effective_schema_digest=_tool_schemas_digest(tool_schemas),
            policy_snapshot_digest=request.policy_snapshot_digest,
        )

    def _inject_framework_definitions(
        self, policy: FrameworkToolPolicyView
    ) -> tuple[ToolDefinition, ...]:
        """按 policy 通过 hook 注入 framework tool。

        :param policy: framework tool policy view。
        :returns: 实际注入的工具声明元组。
        :raises ValueError: hook 返回的工具名与请求名称不一致时抛出。
        """

        if self._framework_injector is None:
            return ()
        definitions: list[ToolDefinition] = []
        for tool_name in sorted(
            policy.enabled_framework_tools, key=lambda item: item.value
        ):
            definition = self._framework_injector.build_framework_tool(tool_name)
            if definition.name != tool_name.value:
                raise ValueError(
                    "framework injector returned mismatched tool name:"
                    f" {definition.name}"
                )
            definitions.append(definition)
        return tuple(definitions)


@dataclass(frozen=True, slots=True)
class ToolRuntimeBuildRequest:
    """ToolRuntime factory 构造输入。

    :param effective_bundle_request: effective bundle 构造输入。
    """

    effective_bundle_request: EffectiveToolBundleBuildRequest


@dataclass(frozen=True, slots=True)
class ToolRuntimeUnsupportedExecutor:
    """P6-S1 明确不执行真实工具的 ToolExecutor stub。

    :param effective_bundle: 与 schema provider 同源的 effective bundle。
    """

    effective_bundle: EffectiveToolBundle

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """返回与输入双射的 unsupported tool failure。

        :param request: 批式工具执行请求。
        :returns: 每个 call 对应一条 unsupported failure record。
        """

        return BatchToolExecutionOutcome(
            records=tuple(
                BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=ToolFailedOutcome(
                        result=ToolResultFailure(
                            ok=False,
                            error=_UNSUPPORTED_EXECUTOR_ERROR,
                            message=_UNSUPPORTED_EXECUTOR_MESSAGE,
                            hint=None,
                            meta=None,
                        )
                    ),
                )
                for call in request.calls
            )
        )


@dataclass(frozen=True, slots=True)
class ToolRuntimeHandle:
    """RunInputBuilder 与 EngineWorker 使用的 ToolRuntime handle。

    :param effective_bundle: attempt-local effective bundle。
    :param tool_schemas: Engine 可见 schemas，必须来自 ``effective_bundle``。
    :param tool_executor: Engine 使用的批式 ToolExecutor。
    """

    effective_bundle: EffectiveToolBundle
    tool_schemas: tuple[ToolSchema, ...]
    tool_executor: ToolExecutor

    def __post_init__(self) -> None:
        """校验 handle 中 schemas 与 effective bundle 同源。

        :returns: ``None``。
        :raises ValueError: ``tool_schemas`` 不是 effective bundle 的投影时抛出。
        """

        if self.tool_schemas != self.effective_bundle.tool_schemas:
            raise ValueError(
                "ToolRuntimeHandle.tool_schemas must come from effective bundle"
            )


class ToolRuntimeFactory(Protocol):
    """ToolRuntime handle factory 协议。"""

    def create_tool_runtime(
        self, request: ToolRuntimeBuildRequest
    ) -> ToolRuntimeHandle:
        """构造 ToolRuntime handle。

        :param request: ToolRuntime 构造输入。
        :returns: ToolRuntimeHandle。
        """
        ...


class DefaultToolRuntimeFactory:
    """默认 ToolRuntime handle factory。

    本 factory 只创建 P6-S1 的 unsupported executor，不执行真实工具。
    """

    def __init__(self, bundle_builder: EffectiveToolBundleBuilder) -> None:
        """初始化 factory。

        :param bundle_builder: effective bundle builder。
        :returns: ``None``。
        """

        self._bundle_builder = bundle_builder

    def create_tool_runtime(
        self, request: ToolRuntimeBuildRequest
    ) -> ToolRuntimeHandle:
        """构造 ToolRuntimeHandle。

        :param request: ToolRuntime 构造输入。
        :returns: 同源暴露 schema 与 executor 的 handle。
        """

        effective_bundle = self._bundle_builder.build(
            request.effective_bundle_request
        )
        return ToolRuntimeHandle(
            effective_bundle=effective_bundle,
            tool_schemas=effective_bundle.tool_schemas,
            tool_executor=ToolRuntimeUnsupportedExecutor(effective_bundle),
        )


def _validate_reserved_name_conflicts(
    bundle: ToolBundle, policy: FrameworkToolPolicyView
) -> None:
    """校验业务工具没有占用 framework 预留名。

    :param bundle: 业务工具集合。
    :param policy: framework tool policy view。
    :returns: ``None``。
    :raises ValueError: 业务工具名占用预留名时抛出。
    """

    reserved = frozenset(
        tool_name.value for tool_name in policy.reserved_framework_tool_names
    )
    for definition in bundle.definitions:
        if definition.name in reserved:
            raise ValueError(
                "business ToolBundle contains reserved framework tool name:"
                f" {definition.name}"
            )


def _definitions_by_name(
    definitions: list[ToolDefinition],
) -> dict[str, ToolDefinition]:
    """按工具名索引工具声明并拒绝重复名称。

    :param definitions: effective 工具声明列表。
    :returns: 按名称索引的声明字典。
    :raises ValueError: 出现重复工具名时抛出。
    """

    result: dict[str, ToolDefinition] = {}
    for definition in definitions:
        if definition.name in result:
            raise ValueError(f"duplicate effective tool name: {definition.name}")
        result[definition.name] = definition
    return result


def _business_bundle_digest(bundle: ToolBundle) -> str:
    """计算业务 bundle 诊断摘要。

    :param bundle: 业务工具集合。
    :returns: Host canonical sha256 digest。
    """

    return sha256_digest_json(
        {
            "definitions": [
                _tool_definition_digest_json(definition)
                for definition in bundle.definitions
            ]
        }
    )


def _tool_schemas_digest(tool_schemas: tuple[ToolSchema, ...]) -> str:
    """计算 effective schema 诊断摘要。

    :param tool_schemas: effective schema 元组。
    :returns: Host canonical sha256 digest。
    """

    return sha256_digest_json(
        {"tool_schemas": [_tool_schema_json(schema) for schema in tool_schemas]}
    )


def _tool_definition_digest_json(definition: ToolDefinition) -> JsonValue:
    """把工具声明投影为 digest JSON。

    :param definition: 工具声明。
    :returns: 可用于 canonical digest 的 JSON 值。
    """

    return {
        "name": definition.name,
        "schema": _tool_schema_json(definition.schema),
        "truncate": _truncate_spec_json(definition.truncate),
        "tags": list(definition.tags),
    }


def _tool_schema_json(schema: ToolSchema) -> JsonValue:
    """把 ToolSchema 投影为 digest JSON。

    :param schema: 工具 schema。
    :returns: JSON 形态 schema。
    """

    return {
        "type": schema.type,
        "function": {
            "name": schema.function.name,
            "description": schema.function.description,
            "parameters": _parameters_json(schema.function.parameters),
        },
    }


def _parameters_json(parameters: ToolParametersSchema) -> JsonValue:
    """把工具参数 schema 投影为 digest JSON。

    :param parameters: 工具参数 schema。
    :returns: JSON 形态参数 schema。
    """

    result: dict[str, JsonValue] = {
        "type": parameters.type,
        "properties": parameters.properties,
        "required": list(parameters.required),
    }
    if parameters.additional_properties is not None:
        result["additionalProperties"] = parameters.additional_properties
    return result


def _truncate_spec_json(spec: ToolTruncateSpec | None) -> JsonValue:
    """把截断声明投影为 digest JSON。

    :param spec: 截断声明；无声明时为 ``None``。
    :returns: JSON 形态截断声明。
    """

    if spec is None:
        return None
    return {
        "enabled": spec.enabled,
        "strategy": spec.strategy,
        "limits": spec.limits,
        "target_field": spec.target_field,
        "field_path": list(spec.field_path) if spec.field_path is not None else None,
        "ttl_seconds": spec.ttl_seconds,
    }


__all__ = [
    "DefaultToolRuntimeFactory",
    "DuplicateDecision",
    "DuplicateDecisionKind",
    "DuplicateGovernancePort",
    "EffectiveToolBundle",
    "EffectiveToolBundleBuildRequest",
    "EffectiveToolBundleBuilder",
    "FrameworkToolInjector",
    "HostToolFactAcceptPort",
    "ToolDispatcher",
    "ToolPolicyDecision",
    "ToolPolicyDecisionKind",
    "ToolRuntimeBuildRequest",
    "ToolRuntimeFactory",
    "ToolRuntimeHandle",
    "ToolRuntimePolicyPort",
    "ToolRuntimeUnsupportedExecutor",
    "ToolTraceDiagnosticEmitter",
    "ToolTraceDiagnosticRecord",
    "ToolTraceDiagnosticRef",
    "TruncationAppliedOutcome",
    "TruncationPort",
]
