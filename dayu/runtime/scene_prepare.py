"""层中立 scene manifest 装配 helper。

``ScenePrepare`` 只解释调用方显式传入的 scene manifest root、读取 manifest
直接引用的 prompt fragments，并用 Service 提供的 typed context slot values
渲染系统消息。本模块不读取 ConfigLoader，不做工具发现，不 import Host /
Engine / Service / UI / Fins，也不表达 workflow、artifact、parser、retry 或
checkpoint 语义。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeAlias, TypeVar, cast

from dayu.contracts import JsonValue, ToolBundle
from dayu.runtime._digest import canonical_json_digest
from dayu.runtime._agent_policy_constants import (
    AGENT_FALLBACK_MODE_FORCE_ANSWER,
    AGENT_FALLBACK_MODE_RAISE_ERROR,
    AGENT_FALLBACK_MODES,
)

_SCHEMA_VERSION: Final[int] = 1
_SCENE_FILE_SUFFIX: Final[str] = ".json"
_DIGEST_PREFIX: Final[str] = "sha256:"
_MISSING_FRAGMENT_POLICY_FAIL_CLOSED: Final[str] = "fail_closed"
_STRING_VALUE_TYPE: Final[str] = "string"
_SCENE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_CONTEXT_SLOT_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
_UNRESOLVED_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"{{[^{}]*}}")
_ALLOWED_MANIFEST_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "scene",
        "version",
        "description",
        "capability_tags",
        "extends",
        "model",
        "agent_policy",
        "tool_selection",
        "defaults",
        "fragments",
        "context_slots",
    }
)
_ALLOWED_MODEL_FIELDS: Final[frozenset[str]] = frozenset({"default_model_id", "runner_option_hint_id"})
_ALLOWED_AGENT_POLICY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "max_iterations",
        "continuation_max_attempts",
        "allow_tool_calls",
        "tool_execution_timeout_seconds",
        "fallback_mode",
        "fallback_prompt",
        "continuation_prompt",
        "max_consecutive_failed_tool_batches",
    }
)
_ALLOWED_TOOL_SELECTION_FIELDS: Final[frozenset[str]] = frozenset(
    {"mode", "tool_names", "tool_tags_any", "allow_empty"}
)
_ALLOWED_DEFAULTS_FIELDS: Final[frozenset[str]] = frozenset({"missing_required_fragment"})
_ALLOWED_FRAGMENT_FIELDS: Final[frozenset[str]] = frozenset({"id", "path", "order", "required"})
_ALLOWED_CONTEXT_SLOT_FIELDS: Final[frozenset[str]] = frozenset({"name", "value_type", "required"})

JsonObject: TypeAlias = Mapping[str, JsonValue]
"""scene manifest JSON object 的只读映射类型。"""

_ResolvedValueT = TypeVar("_ResolvedValueT")
"""可继承 manifest 字段的内部泛型。"""


class ScenePrepareError(ValueError):
    """scene manifest 解析、校验或装配失败时抛出的错误。"""


class SceneSourceKind(StrEnum):
    """scene 装配来源引用类别。"""

    MANIFEST = "manifest"
    FRAGMENT = "fragment"
    ASSEMBLY_INPUT = "assembly_input"


class SceneToolSelectionMode(StrEnum):
    """scene 工具选择模式。"""

    ALL = "all"
    NONE = "none"
    SELECT = "select"


class SceneAgentFallbackMode(StrEnum):
    """scene agent policy override 支持的 fallback 模式。"""

    FORCE_ANSWER = AGENT_FALLBACK_MODE_FORCE_ANSWER
    RAISE_ERROR = AGENT_FALLBACK_MODE_RAISE_ERROR


@dataclass(frozen=True, slots=True)
class SceneToolInfo:
    """ScenePrepare 可见的层中立工具信息。

    :param name: 工具名。
    :param tags: 工具标签集合。
    """

    name: str
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """校验工具名与标签形态。

        :returns: ``None``。
        :raises ValueError: 工具名或标签为空时抛出。
        """

        _require_non_empty_text(self.name, field_name="SceneToolInfo.name")
        for tag in self.tags:
            _require_non_empty_text(tag, field_name=f"SceneToolInfo.tags[{self.name}]")


@dataclass(frozen=True, slots=True)
class SceneToolCatalog:
    """ScenePrepare 的层中立工具目录。

    目录只保存工具名和标签，不携带 callable，也不进入 ``PreparedSceneInputs``
    输出。

    :param tools: 可供 scene tool_selection 匹配的工具信息。
    """

    tools: tuple[SceneToolInfo, ...]

    def __post_init__(self) -> None:
        """校验工具名唯一。

        :returns: ``None``。
        :raises ValueError: 工具名重复时抛出。
        """

        seen: set[str] = set()
        for tool in self.tools:
            if tool.name in seen:
                raise ValueError(f"duplicate scene tool name: {tool.name}")
            seen.add(tool.name)

    @classmethod
    def from_tool_bundle(cls, tool_bundle: ToolBundle) -> SceneToolCatalog:
        """从业务 ``ToolBundle`` 投影出 ScenePrepare 可见工具目录。

        :param tool_bundle: 已发现并聚合的业务工具 bundle。
        :returns: 只包含工具名与标签的 scene 工具目录。
        :raises ValueError: 工具名重复时由 ``SceneToolCatalog`` 抛出。
        """

        return cls(
            tools=tuple(
                SceneToolInfo(name=definition.name, tags=frozenset(definition.tags))
                for definition in tool_bundle.definitions
            )
        )

    def names(self) -> frozenset[str]:
        """返回目录中的全部工具名。

        :returns: 工具名不可变集合。
        """

        return frozenset(tool.name for tool in self.tools)

    def names_for_any_tag(self, tags: frozenset[str]) -> frozenset[str]:
        """按任一标签命中查找工具名。

        :param tags: 需要匹配的标签集合。
        :returns: 命中任一标签的工具名集合。
        """

        return frozenset(tool.name for tool in self.tools if not tool.tags.isdisjoint(tags))


@dataclass(frozen=True, slots=True)
class ScenePrepareRequest:
    """ScenePrepare 单次装配请求。

    :param scene_id: 要装配的 concrete scene id。
    :param scene_manifest_root: 调用方显式传入的 manifest 根目录。
    :param prompt_asset_root: 调用方显式传入的 prompt fragment 根目录。
    :param context_slot_values: Service 提供的 typed context slot 字符串值。
    :param available_tools: Service / composition root 提供的层中立工具目录。
    """

    scene_id: str
    scene_manifest_root: Path
    prompt_asset_root: Path
    context_slot_values: Mapping[str, str]
    available_tools: SceneToolCatalog

    def __post_init__(self) -> None:
        """校验请求的显式 scene id。

        :returns: ``None``。
        :raises ValueError: scene id 为空或包含路径字符时抛出。
        """

        _require_scene_id(self.scene_id, field_name="ScenePrepareRequest.scene_id")


@dataclass(frozen=True, slots=True)
class SceneModelHints:
    """scene 模型选择 hint。

    :param default_model_id: scene 建议的模型配置 id，由 Service 映射为完整
        Runner 输入。
    :param runner_option_hint_id: scene 建议的 runner options hint id，由
        Service 映射为完整 RunnerCallOptions。
    """

    default_model_id: str
    runner_option_hint_id: str | None

    def __post_init__(self) -> None:
        """校验模型 hint。

        :returns: ``None``。
        :raises ValueError: ``default_model_id`` 为空时抛出。
        """

        _require_non_empty_text(
            self.default_model_id,
            field_name="SceneModelHints.default_model_id",
        )
        if self.runner_option_hint_id is not None:
            _require_non_empty_text(
                self.runner_option_hint_id,
                field_name="SceneModelHints.runner_option_hint_id",
            )


@dataclass(frozen=True, slots=True)
class SceneAgentPolicyOverride:
    """scene 层 AgentPolicy typed override。

    所有字段均为可选字段，调用方负责将其与 execution profile baseline
    合成为完整 Host / Engine ``AgentPolicy`` typed input。

    :param max_iterations: 单次 Agent run 内最大 LLM 迭代次数。
    :param continuation_max_attempts: 同一迭代内 continuation 最大尝试次数。
    :param allow_tool_calls: 是否允许工具调用。
    :param tool_execution_timeout_seconds: 工具执行握手超时秒数。
    :param fallback_mode: 工具轮次耗尽或失败批次阈值命中后的收口模式。
    :param fallback_prompt: force-answer 时追加给 Runner 的用户消息。
    :param continuation_prompt: finish_reason=length 续写提示。
    :param max_consecutive_failed_tool_batches: 连续全失败工具批次阈值。
    """

    max_iterations: int | None = None
    continuation_max_attempts: int | None = None
    allow_tool_calls: bool | None = None
    tool_execution_timeout_seconds: float | None = None
    fallback_mode: SceneAgentFallbackMode | None = None
    fallback_prompt: str | None = None
    continuation_prompt: str | None = None
    max_consecutive_failed_tool_batches: int | None = None


@dataclass(frozen=True, slots=True)
class SceneToolSelection:
    """manifest 中的工具选择配置。

    :param mode: 工具选择模式。
    :param tool_names: ``select`` 模式显式工具名。
    :param tool_tags_any: ``select`` 模式任一标签命中集合。
    :param allow_empty: tag 无匹配或最终选择为空时是否允许通过。
    """

    mode: SceneToolSelectionMode
    tool_names: frozenset[str]
    tool_tags_any: frozenset[str]
    allow_empty: bool


@dataclass(frozen=True, slots=True)
class SceneToolSelectionResult:
    """装配后的工具选择结果。

    :param mode: 工具选择模式。
    :param tool_names: 映射给 per-run ``tool_names`` 的值；``None`` 表示全量，
        空集合表示禁用业务工具，非空集合表示白名单。
    """

    mode: SceneToolSelectionMode
    tool_names: frozenset[str] | None


@dataclass(frozen=True, slots=True)
class SceneFragmentRef:
    """装配后的 prompt fragment 来源引用。

    :param fragment_id: manifest 内 fragment id。
    :param relative_path: fragment 相对 prompt asset root 的路径。
    :param order: fragment 拼接顺序。
    :param required: fragment 是否必需。
    :param content_digest: fragment 原始内容摘要。
    """

    fragment_id: str
    relative_path: str
    order: int
    required: bool
    content_digest: str


@dataclass(frozen=True, slots=True)
class SceneSourceRef:
    """scene 装配来源引用。

    :param source_kind: 来源类别。
    :param source_id: 来源标识，通常是相对路径或 assembly input 名称。
    :param version_ref: 可解释版本引用；无版本时为 ``None``。
    :param content_digest: 来源内容摘要。
    """

    source_kind: SceneSourceKind
    source_id: str
    version_ref: str | None
    content_digest: str

    def __post_init__(self) -> None:
        """校验来源引用字段非空。

        :returns: ``None``。
        :raises ValueError: 来源标识或摘要为空时抛出。
        """

        _require_non_empty_text(self.source_id, field_name="SceneSourceRef.source_id")
        _require_non_empty_text(
            self.content_digest,
            field_name="SceneSourceRef.content_digest",
        )


@dataclass(frozen=True, slots=True)
class PreparedSceneInputs:
    """ScenePrepare 装配输出。

    :param system_messages: 已完成 context slot 渲染的系统消息片段。
    :param system_prompt: 已完成 context slot 渲染并用空行连接的系统提示词。
    :param tool_selection: 工具选择结果。
    :param model_hints: 可选模型 hint。
    :param agent_policy_override: 可选 AgentPolicy typed override。
    :param fragment_refs: 参与装配的 prompt fragment 引用。
    :param source_refs: manifest、fragment 与 assembly input 来源引用。
    :param content_digest: 本次 scene 装配内容摘要。
    :param capability_tags: scene capability tags，父优先去重。
    """

    system_messages: tuple[str, ...]
    system_prompt: str
    tool_selection: SceneToolSelectionResult
    model_hints: SceneModelHints | None
    agent_policy_override: SceneAgentPolicyOverride | None
    fragment_refs: tuple[SceneFragmentRef, ...]
    source_refs: tuple[SceneSourceRef, ...]
    content_digest: str
    capability_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SceneDefaults:
    """manifest defaults typed view。"""

    missing_required_fragment: str


@dataclass(frozen=True, slots=True)
class _ManifestFragment:
    """manifest fragment typed view。"""

    fragment_id: str
    relative_path: str
    order: int
    required: bool


@dataclass(frozen=True, slots=True)
class _ContextSlot:
    """manifest context slot typed view。"""

    name: str
    value_type: str
    required: bool


@dataclass(frozen=True, slots=True)
class _SceneManifest:
    """单个 scene manifest typed view。"""

    scene_id: str
    version: str
    description: str
    capability_tags: tuple[str, ...]
    extends: tuple[str, ...]
    model_hints: SceneModelHints | None
    agent_policy_override: SceneAgentPolicyOverride | None
    tool_selection: SceneToolSelection | None
    defaults: _SceneDefaults
    fragments: tuple[_ManifestFragment, ...]
    context_slots: tuple[_ContextSlot, ...]
    raw: JsonObject
    manifest_path: Path
    relative_manifest_path: str


@dataclass(frozen=True, slots=True)
class _ResolvedScene:
    """继承解析后的 scene typed view。"""

    manifests: tuple[_SceneManifest, ...]
    scene_id: str
    version: str
    description: str
    capability_tags: tuple[str, ...]
    model_hints: SceneModelHints | None
    agent_policy_override: SceneAgentPolicyOverride | None
    tool_selection: SceneToolSelection
    defaults: _SceneDefaults
    fragments: tuple[_ManifestFragment, ...]
    context_slots: tuple[_ContextSlot, ...]


class ScenePrepare:
    """层中立 scene manifest 装配器。"""

    def prepare(self, request: ScenePrepareRequest) -> PreparedSceneInputs:
        """装配单个 concrete scene 的系统消息与运行 hint。

        :param request: 显式 scene 装配请求。
        :returns: 已渲染的 scene 输入。
        :raises ScenePrepareError: manifest、fragment、context slot 或工具选择
            违反契约时抛出。
        """

        _validate_context_slot_values(request.context_slot_values)
        manifest_root = request.scene_manifest_root.resolve()
        prompt_asset_root = request.prompt_asset_root.resolve()
        resolved = _resolve_scene(
            scene_id=request.scene_id,
            manifest_root=manifest_root,
            stack=(),
        )
        fragment_contents = _load_fragment_contents(
            fragments=resolved.fragments,
            prompt_asset_root=prompt_asset_root,
            defaults=resolved.defaults,
        )
        rendered_messages = tuple(
            _render_fragment_content(
                content=content,
                context_slots=resolved.context_slots,
                context_slot_values=request.context_slot_values,
                fragment_id=fragment.fragment_id,
            )
            for fragment, content in fragment_contents
        )
        tool_selection = _select_tools(
            selection=resolved.tool_selection,
            catalog=request.available_tools,
        )
        fragment_refs = tuple(
            SceneFragmentRef(
                fragment_id=fragment.fragment_id,
                relative_path=fragment.relative_path,
                order=fragment.order,
                required=fragment.required,
                content_digest=_text_digest(content),
            )
            for fragment, content in fragment_contents
        )
        source_refs = _build_source_refs(
            resolved=resolved,
            fragment_contents=fragment_contents,
            request=request,
        )
        content_digest = _prepared_scene_digest(
            resolved=resolved,
            fragment_contents=fragment_contents,
            request=request,
            tool_selection=tool_selection,
        )
        return PreparedSceneInputs(
            system_messages=rendered_messages,
            system_prompt="\n\n".join(rendered_messages),
            tool_selection=tool_selection,
            model_hints=resolved.model_hints,
            agent_policy_override=resolved.agent_policy_override,
            fragment_refs=fragment_refs,
            source_refs=source_refs,
            content_digest=content_digest,
            capability_tags=resolved.capability_tags,
        )


def prepare_scene(request: ScenePrepareRequest) -> PreparedSceneInputs:
    """使用默认 ``ScenePrepare`` 装配 scene。

    :param request: 显式 scene 装配请求。
    :returns: 已渲染的 scene 输入。
    :raises ScenePrepareError: manifest、fragment、context slot 或工具选择
        违反契约时抛出。
    """

    return ScenePrepare().prepare(request)


def _resolve_scene(*, scene_id: str, manifest_root: Path, stack: tuple[str, ...]) -> _ResolvedScene:
    """解析 scene manifest 继承链。

    :param scene_id: 当前解析的 scene id。
    :param manifest_root: manifest 根目录。
    :param stack: 当前递归栈，用于循环继承检测。
    :returns: 继承解析后的 scene。
    :raises ScenePrepareError: 父不存在、多继承、循环继承或字段缺失时抛出。
    """

    _require_scene_id(scene_id, field_name="scene_id")
    if scene_id in stack:
        cycle = " -> ".join((*stack, scene_id))
        raise ScenePrepareError(f"scene inheritance cycle detected: {cycle}")
    manifest = _load_manifest(scene_id=scene_id, manifest_root=manifest_root)
    if len(manifest.extends) > 1:
        raise ScenePrepareError(f"scene {scene_id} declares multiple parents")
    if not manifest.extends:
        return _resolved_from_manifest(parent=None, manifest=manifest)
    parent = _resolve_scene(
        scene_id=manifest.extends[0],
        manifest_root=manifest_root,
        stack=(*stack, scene_id),
    )
    return _resolved_from_manifest(parent=parent, manifest=manifest)


def _resolved_from_manifest(*, parent: _ResolvedScene | None, manifest: _SceneManifest) -> _ResolvedScene:
    """把单个 manifest 合并到可选父 scene。

    :param parent: 已解析父 scene；无父时为 ``None``。
    :param manifest: 当前 manifest。
    :returns: 当前 concrete scene 的解析结果。
    :raises ScenePrepareError: 必需 hint 缺失或 fragment 冲突时抛出。
    """

    model_hints = _resolve_optional_inherited_value(
        child=manifest.model_hints,
        parent=None if parent is None else parent.model_hints,
    )
    agent_policy_override = _resolve_optional_inherited_value(
        child=manifest.agent_policy_override,
        parent=None if parent is None else parent.agent_policy_override,
    )
    tool_selection = _resolve_optional_child_value(
        child=manifest.tool_selection,
        parent=None if parent is None else parent.tool_selection,
        field_name=f"scene {manifest.scene_id} tool_selection",
    )
    parent_fragments: tuple[_ManifestFragment, ...] = ()
    parent_context_slots: tuple[_ContextSlot, ...] = ()
    parent_capability_tags: tuple[str, ...] = ()
    parent_manifests: tuple[_SceneManifest, ...] = ()
    if parent is not None:
        parent_fragments = parent.fragments
        parent_context_slots = parent.context_slots
        parent_capability_tags = parent.capability_tags
        parent_manifests = parent.manifests
    fragments = (*parent_fragments, *manifest.fragments)
    _validate_fragment_uniqueness(fragments, scene_id=manifest.scene_id)
    context_slots = _dedupe_context_slots((*parent_context_slots, *manifest.context_slots))
    return _ResolvedScene(
        manifests=(*parent_manifests, manifest),
        scene_id=manifest.scene_id,
        version=manifest.version,
        description=manifest.description,
        capability_tags=_append_unique(parent_capability_tags, manifest.capability_tags),
        model_hints=model_hints,
        agent_policy_override=agent_policy_override,
        tool_selection=tool_selection,
        defaults=manifest.defaults,
        fragments=tuple(sorted(fragments, key=lambda fragment: fragment.order)),
        context_slots=context_slots,
    )


def _resolve_optional_child_value(
    *,
    child: _ResolvedValueT | None,
    parent: _ResolvedValueT | None,
    field_name: str,
) -> _ResolvedValueT:
    """解析可由子 manifest 覆盖的字段。

    :param child: 子 manifest 显式值。
    :param parent: 父 scene 已解析值。
    :param field_name: 错误消息字段名。
    :returns: 子值优先，否则父值。
    :raises ScenePrepareError: 子值和父值均缺失时抛出。
    """

    if child is not None:
        return child
    if parent is not None:
        return parent
    raise ScenePrepareError(f"{field_name} must be declared")


def _resolve_optional_inherited_value(
    *, child: _ResolvedValueT | None, parent: _ResolvedValueT | None
) -> _ResolvedValueT | None:
    """解析可继承但整体可缺省的字段。

    :param child: 子 manifest 显式值。
    :param parent: 父 scene 已解析值。
    :returns: 子值优先，其次父值；两者均缺省时返回 ``None``。
    """

    if child is not None:
        return child
    return parent


def _load_manifest(*, scene_id: str, manifest_root: Path) -> _SceneManifest:
    """从显式 manifest root 加载单个 scene manifest。

    :param scene_id: scene id。
    :param manifest_root: manifest 根目录。
    :returns: 解析后的 manifest typed view。
    :raises ScenePrepareError: 文件不存在、路径逃逸、JSON 非 object 或字段非法
        时抛出。
    """

    path = _resolve_contained_path(
        root=manifest_root,
        relative_path=f"{scene_id}{_SCENE_FILE_SUFFIX}",
        context=f"scene manifest {scene_id}",
    )
    if not path.exists():
        raise ScenePrepareError(f"scene manifest not found: {scene_id}")
    try:
        raw_value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise ScenePrepareError(f"scene manifest is not valid JSON: {scene_id}") from exc
    raw = _require_json_object(raw_value, context=f"scene manifest {scene_id}")
    manifest = _parse_manifest(
        raw=raw,
        manifest_path=path,
        relative_manifest_path=f"{scene_id}{_SCENE_FILE_SUFFIX}",
    )
    if manifest.scene_id != scene_id:
        raise ScenePrepareError(f"scene manifest file {scene_id} declares different scene: {manifest.scene_id}")
    return manifest


def _parse_manifest(*, raw: JsonObject, manifest_path: Path, relative_manifest_path: str) -> _SceneManifest:
    """解析单个 manifest JSON object。

    :param raw: manifest JSON object。
    :param manifest_path: manifest 文件绝对路径。
    :param relative_manifest_path: manifest 相对 root 的路径。
    :returns: manifest typed view。
    :raises ScenePrepareError: 任一字段缺失或非法时抛出。
    """

    _require_no_unknown_fields(raw, allowed=_ALLOWED_MANIFEST_FIELDS, context=relative_manifest_path)
    schema_version = _require_int_field(raw, field_name="schema_version", context=relative_manifest_path)
    if schema_version != _SCHEMA_VERSION:
        raise ScenePrepareError(f"{relative_manifest_path}.schema_version must be 1")
    scene_id = _require_str_field(raw, field_name="scene", context=relative_manifest_path)
    _require_scene_id(scene_id, field_name=f"{relative_manifest_path}.scene")
    extends = _parse_extends(raw, context=relative_manifest_path)
    if len(extends) > 1:
        raise ScenePrepareError(f"{relative_manifest_path}.extends allows only one parent")
    return _SceneManifest(
        scene_id=scene_id,
        version=_require_str_field(raw, field_name="version", context=relative_manifest_path),
        description=_require_str_field(raw, field_name="description", context=relative_manifest_path),
        capability_tags=_parse_text_tuple(raw, field_name="capability_tags", context=relative_manifest_path),
        extends=extends,
        model_hints=_parse_model_hints(_optional_field(raw, "model"), context=relative_manifest_path),
        agent_policy_override=_parse_agent_policy_override(
            _optional_field(raw, "agent_policy"), context=relative_manifest_path
        ),
        tool_selection=_parse_tool_selection(_optional_field(raw, "tool_selection"), context=relative_manifest_path),
        defaults=_parse_defaults(
            _require_mapping_field(raw, field_name="defaults", context=relative_manifest_path),
            context=relative_manifest_path,
        ),
        fragments=_parse_fragments(
            _require_sequence_field(raw, field_name="fragments", context=relative_manifest_path),
            context=relative_manifest_path,
        ),
        context_slots=_parse_context_slots(
            _require_sequence_field(raw, field_name="context_slots", context=relative_manifest_path),
            context=relative_manifest_path,
        ),
        raw=raw,
        manifest_path=manifest_path,
        relative_manifest_path=relative_manifest_path,
    )


def _parse_extends(raw: JsonObject, *, context: str) -> tuple[str, ...]:
    """解析 manifest ``extends`` 字段。

    :param raw: manifest JSON object。
    :param context: 错误消息上下文。
    :returns: 父 scene id 元组。
    :raises ScenePrepareError: 字段缺失、非数组或父 id 非法时抛出。
    """

    values = _require_sequence_field(raw, field_name="extends", context=context)
    parents: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise ScenePrepareError(f"{context}.extends[{index}] must be string")
        _require_scene_id(value, field_name=f"{context}.extends[{index}]")
        parents.append(value)
    return tuple(parents)


def _parse_model_hints(value: JsonValue | None, *, context: str) -> SceneModelHints | None:
    """解析 ``model`` hint。

    :param value: ``model`` 字段值。
    :param context: 错误消息上下文。
    :returns: 模型 hint；``None`` 表示当前 manifest 未显式声明。
    :raises ScenePrepareError: 字段类型或内容非法时抛出。
    """

    if value is None:
        return None
    record = _require_json_object(value, context=f"{context}.model")
    _require_no_unknown_fields(
        record,
        allowed=_ALLOWED_MODEL_FIELDS,
        context=f"{context}.model",
    )
    return SceneModelHints(
        default_model_id=_require_str_field(
            record,
            field_name="default_model_id",
            context=f"{context}.model",
        ),
        runner_option_hint_id=_optional_str_field(
            record,
            field_name="runner_option_hint_id",
            context=f"{context}.model",
        ),
    )


def _parse_agent_policy_override(value: JsonValue | None, *, context: str) -> SceneAgentPolicyOverride | None:
    """解析 ``agent_policy`` typed override。

    :param value: ``agent_policy`` 字段值。
    :param context: 错误消息上下文。
    :returns: AgentPolicy override；``None`` 表示当前 manifest 未声明。
    :raises ScenePrepareError: 字段未知、类型非法或取值越界时抛出。
    """

    if value is None:
        return None
    record = _require_json_object(value, context=f"{context}.agent_policy")
    _require_no_unknown_fields(
        record,
        allowed=_ALLOWED_AGENT_POLICY_FIELDS,
        context=f"{context}.agent_policy",
    )
    return SceneAgentPolicyOverride(
        max_iterations=_optional_positive_int_field(
            record,
            field_name="max_iterations",
            context=f"{context}.agent_policy",
        ),
        continuation_max_attempts=_optional_non_negative_int_field(
            record,
            field_name="continuation_max_attempts",
            context=f"{context}.agent_policy",
        ),
        allow_tool_calls=_optional_bool_field_or_none(
            record,
            field_name="allow_tool_calls",
            context=f"{context}.agent_policy",
        ),
        tool_execution_timeout_seconds=_optional_positive_float_field(
            record,
            field_name="tool_execution_timeout_seconds",
            context=f"{context}.agent_policy",
        ),
        fallback_mode=_parse_optional_fallback_mode(
            record,
            context=f"{context}.agent_policy",
        ),
        fallback_prompt=_optional_str_field(
            record,
            field_name="fallback_prompt",
            context=f"{context}.agent_policy",
        ),
        continuation_prompt=_optional_str_field(
            record,
            field_name="continuation_prompt",
            context=f"{context}.agent_policy",
        ),
        max_consecutive_failed_tool_batches=_optional_positive_int_field(
            record,
            field_name="max_consecutive_failed_tool_batches",
            context=f"{context}.agent_policy",
        ),
    )


def _parse_tool_selection(value: JsonValue | None, *, context: str) -> SceneToolSelection | None:
    """解析 ``tool_selection`` 配置。

    :param value: ``tool_selection`` 字段值。
    :param context: 错误消息上下文。
    :returns: 工具选择配置；``None`` 表示继承父值。
    :raises ScenePrepareError: 模式、工具名或标签非法时抛出。
    """

    if value is None:
        return None
    record = _require_json_object(value, context=f"{context}.tool_selection")
    _require_no_unknown_fields(
        record,
        allowed=_ALLOWED_TOOL_SELECTION_FIELDS,
        context=f"{context}.tool_selection",
    )
    mode_text = _require_str_field(record, field_name="mode", context=f"{context}.tool_selection")
    try:
        mode = SceneToolSelectionMode(mode_text)
    except ValueError as exc:
        raise ScenePrepareError(f"{context}.tool_selection.mode is unsupported: {mode_text}") from exc
    return SceneToolSelection(
        mode=mode,
        tool_names=frozenset(
            _parse_optional_text_tuple(
                record,
                field_name="tool_names",
                context=f"{context}.tool_selection",
            )
        ),
        tool_tags_any=frozenset(
            _parse_optional_text_tuple(
                record,
                field_name="tool_tags_any",
                context=f"{context}.tool_selection",
            )
        ),
        allow_empty=_optional_bool_field(
            record,
            field_name="allow_empty",
            context=f"{context}.tool_selection",
            default=False,
        ),
    )


def _parse_defaults(record: JsonObject, *, context: str) -> _SceneDefaults:
    """解析 ``defaults`` 配置。

    :param record: ``defaults`` JSON object。
    :param context: 错误消息上下文。
    :returns: defaults typed view。
    :raises ScenePrepareError: 缺失或非法 policy 时抛出。
    """

    _require_no_unknown_fields(
        record,
        allowed=_ALLOWED_DEFAULTS_FIELDS,
        context=f"{context}.defaults",
    )
    policy = _require_str_field(
        record,
        field_name="missing_required_fragment",
        context=f"{context}.defaults",
    )
    if policy != _MISSING_FRAGMENT_POLICY_FAIL_CLOSED:
        raise ScenePrepareError(f"{context}.defaults.missing_required_fragment must be fail_closed")
    return _SceneDefaults(missing_required_fragment=policy)


def _parse_fragments(values: Sequence[JsonValue], *, context: str) -> tuple[_ManifestFragment, ...]:
    """解析 ``fragments`` 配置。

    :param values: fragment JSON 值序列。
    :param context: 错误消息上下文。
    :returns: fragment typed view 元组。
    :raises ScenePrepareError: fragment 字段非法或单 manifest 内重复时抛出。
    """

    fragments: list[_ManifestFragment] = []
    for index, value in enumerate(values):
        record = _require_json_object(value, context=f"{context}.fragments[{index}]")
        _require_no_unknown_fields(
            record,
            allowed=_ALLOWED_FRAGMENT_FIELDS,
            context=f"{context}.fragments[{index}]",
        )
        fragment = _ManifestFragment(
            fragment_id=_require_str_field(record, field_name="id", context=f"{context}.fragments[{index}]"),
            relative_path=_require_str_field(record, field_name="path", context=f"{context}.fragments[{index}]"),
            order=_require_int_field(record, field_name="order", context=f"{context}.fragments[{index}]"),
            required=_optional_bool_field(
                record,
                field_name="required",
                context=f"{context}.fragments[{index}]",
                default=True,
            ),
        )
        _require_non_empty_text(
            fragment.fragment_id,
            field_name=f"{context}.fragments[{index}].id",
        )
        _require_non_empty_text(
            fragment.relative_path,
            field_name=f"{context}.fragments[{index}].path",
        )
        fragments.append(fragment)
    _validate_fragment_uniqueness(tuple(fragments), scene_id=context)
    return tuple(fragments)


def _parse_context_slots(values: Sequence[JsonValue], *, context: str) -> tuple[_ContextSlot, ...]:
    """解析 ``context_slots`` 配置。

    :param values: context slot JSON 值序列。
    :param context: 错误消息上下文。
    :returns: context slot typed view 元组。
    :raises ScenePrepareError: slot 名称、类型或重复声明非法时抛出。
    """

    slots: list[_ContextSlot] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        record = _require_json_object(value, context=f"{context}.context_slots[{index}]")
        _require_no_unknown_fields(
            record,
            allowed=_ALLOWED_CONTEXT_SLOT_FIELDS,
            context=f"{context}.context_slots[{index}]",
        )
        name = _require_str_field(record, field_name="name", context=f"{context}.context_slots[{index}]")
        _require_context_slot_name(name, field_name=f"{context}.context_slots[{index}].name")
        if name in seen:
            raise ScenePrepareError(f"duplicate context slot name: {name}")
        seen.add(name)
        value_type = _require_str_field(record, field_name="value_type", context=f"{context}.context_slots[{index}]")
        if value_type != _STRING_VALUE_TYPE:
            raise ScenePrepareError(f"context slot {name} only supports value_type=string")
        slots.append(
            _ContextSlot(
                name=name,
                value_type=value_type,
                required=_optional_bool_field(
                    record,
                    field_name="required",
                    context=f"{context}.context_slots[{index}]",
                    default=True,
                ),
            )
        )
    return tuple(slots)


def _load_fragment_contents(
    *,
    fragments: tuple[_ManifestFragment, ...],
    prompt_asset_root: Path,
    defaults: _SceneDefaults,
) -> tuple[tuple[_ManifestFragment, str], ...]:
    """读取 manifest 直接引用的 prompt fragments。

    :param fragments: 继承解析后的 fragment 列表。
    :param prompt_asset_root: prompt asset 根目录。
    :param defaults: manifest defaults。
    :returns: 按 order 排序的 fragment 与原始内容元组。
    :raises ScenePrepareError: fragment 路径逃逸或必需 fragment 缺失时抛出。
    """

    loaded: list[tuple[_ManifestFragment, str]] = []
    for fragment in fragments:
        path = _resolve_contained_path(
            root=prompt_asset_root,
            relative_path=fragment.relative_path,
            context=f"fragment {fragment.fragment_id}",
        )
        if not path.exists():
            if fragment.required:
                if defaults.missing_required_fragment == _MISSING_FRAGMENT_POLICY_FAIL_CLOSED:
                    raise ScenePrepareError(f"required fragment missing: {fragment.fragment_id}")
                raise ScenePrepareError(f"required fragment missing without fail-closed policy: {fragment.fragment_id}")
            continue
        loaded.append((fragment, path.read_text(encoding="utf-8")))
    return tuple(loaded)


def _render_fragment_content(
    *,
    content: str,
    context_slots: tuple[_ContextSlot, ...],
    context_slot_values: Mapping[str, str],
    fragment_id: str,
) -> str:
    """对 fragment 内容执行确定性 context slot 文本替换。

    :param content: fragment 原始文本。
    :param context_slots: manifest 声明的 context slots。
    :param context_slot_values: Service 提供的 slot 字符串值。
    :param fragment_id: 错误消息中的 fragment id。
    :returns: 渲染后的文本。
    :raises ScenePrepareError: 缺 required slot、未知 placeholder、非字符串值或
        渲染后仍残留 placeholder 时抛出。
    """

    slot_names = frozenset(slot.name for slot in context_slots)
    for slot in context_slots:
        if slot.required and slot.name not in context_slot_values:
            raise ScenePrepareError(f"required context slot missing: {slot.name}")

    rendered = _replace_placeholders(
        content=content,
        slot_names=slot_names,
        context_slot_values=context_slot_values,
        fragment_id=fragment_id,
    )
    if _UNRESOLVED_PLACEHOLDER_PATTERN.search(rendered) is not None:
        raise ScenePrepareError(f"unresolved placeholder remains in fragment {fragment_id}")
    return rendered


def _replace_placeholders(
    *,
    content: str,
    slot_names: frozenset[str],
    context_slot_values: Mapping[str, str],
    fragment_id: str,
) -> str:
    """替换文本中的所有合法 placeholder。

    :param content: fragment 原始文本。
    :param slot_names: manifest 声明的 slot 名称集合。
    :param context_slot_values: Service 提供的 slot 字符串值。
    :param fragment_id: 错误消息中的 fragment id。
    :returns: 替换后的文本。
    :raises ScenePrepareError: placeholder 未声明、值缺失或值非字符串时抛出。
    """

    rendered_parts: list[str] = []
    cursor = 0
    for match in _PLACEHOLDER_PATTERN.finditer(content):
        rendered_parts.append(content[cursor : match.start()])
        slot_name = match.group(1)
        if slot_name not in slot_names:
            raise ScenePrepareError(f"unknown placeholder in fragment {fragment_id}: {slot_name}")
        if slot_name not in context_slot_values:
            raise ScenePrepareError(f"context slot value missing for placeholder {slot_name}")
        value = context_slot_values[slot_name]
        if not isinstance(value, str):
            raise ScenePrepareError(f"context slot value must be string: {slot_name}")
        rendered_parts.append(value)
        cursor = match.end()
    rendered_parts.append(content[cursor:])
    return "".join(rendered_parts)


def _select_tools(*, selection: SceneToolSelection, catalog: SceneToolCatalog) -> SceneToolSelectionResult:
    """根据 manifest tool_selection 和可用工具目录计算工具白名单。

    :param selection: manifest 工具选择配置。
    :param catalog: 可用工具目录。
    :returns: 工具选择结果。
    :raises ScenePrepareError: 未知工具名、tag 无匹配或空选择非法时抛出。
    """

    if selection.mode == SceneToolSelectionMode.ALL:
        return SceneToolSelectionResult(mode=selection.mode, tool_names=None)
    if selection.mode == SceneToolSelectionMode.NONE:
        return SceneToolSelectionResult(
            mode=selection.mode,
            tool_names=frozenset(),
        )
    available_names = catalog.names()
    unknown_names = selection.tool_names - available_names
    if unknown_names:
        raise ScenePrepareError("unknown tool_names: " + ", ".join(sorted(unknown_names)))
    selected_by_tag = catalog.names_for_any_tag(selection.tool_tags_any)
    if selection.tool_tags_any and not selected_by_tag and not selection.allow_empty:
        raise ScenePrepareError("tool_tags_any matched no tools: " + ", ".join(sorted(selection.tool_tags_any)))
    selected = frozenset((*selection.tool_names, *selected_by_tag))
    if not selected and not selection.allow_empty:
        raise ScenePrepareError("tool_selection select produced empty tool set")
    return SceneToolSelectionResult(mode=selection.mode, tool_names=selected)


def _build_source_refs(
    *,
    resolved: _ResolvedScene,
    fragment_contents: tuple[tuple[_ManifestFragment, str], ...],
    request: ScenePrepareRequest,
) -> tuple[SceneSourceRef, ...]:
    """构造 scene 装配来源引用。

    :param resolved: 继承解析后的 scene。
    :param fragment_contents: 已读取 fragment 内容。
    :param request: 原始装配请求。
    :returns: 来源引用元组。
    """

    refs: list[SceneSourceRef] = []
    for manifest in resolved.manifests:
        refs.append(
            SceneSourceRef(
                source_kind=SceneSourceKind.MANIFEST,
                source_id=manifest.relative_manifest_path,
                version_ref=manifest.version,
                content_digest=canonical_json_digest(manifest.raw),
            )
        )
    for fragment, content in fragment_contents:
        refs.append(
            SceneSourceRef(
                source_kind=SceneSourceKind.FRAGMENT,
                source_id=fragment.relative_path,
                version_ref=None,
                content_digest=_text_digest(content),
            )
        )
    refs.append(
        SceneSourceRef(
            source_kind=SceneSourceKind.ASSEMBLY_INPUT,
            source_id=f"scene:{request.scene_id}:assembly_input",
            version_ref=None,
            content_digest=_assembly_input_digest(request),
        )
    )
    return tuple(refs)


def _prepared_scene_digest(
    *,
    resolved: _ResolvedScene,
    fragment_contents: tuple[tuple[_ManifestFragment, str], ...],
    request: ScenePrepareRequest,
    tool_selection: SceneToolSelectionResult,
) -> str:
    """计算本次 scene 装配稳定内容摘要。

    :param resolved: 继承解析后的 scene。
    :param fragment_contents: 已读取 fragment 内容。
    :param request: 原始装配请求。
    :param tool_selection: 工具选择结果。
    :returns: ``sha256:<hex>`` 摘要。
    """

    payload: dict[str, JsonValue] = {
        "scene_id": resolved.scene_id,
        "version": resolved.version,
        "description": resolved.description,
        "capability_tags": _text_sequence_json(resolved.capability_tags),
        "manifests": [manifest.raw for manifest in resolved.manifests],
        "fragments": [
            {
                "id": fragment.fragment_id,
                "path": fragment.relative_path,
                "order": fragment.order,
                "required": fragment.required,
                "content": content,
            }
            for fragment, content in fragment_contents
        ],
        "context_slot_values": _sorted_text_mapping_json(request.context_slot_values),
        "available_tools": _tool_catalog_json(request.available_tools),
        "selected_tool_names": (
            None if tool_selection.tool_names is None else _text_sequence_json(tuple(sorted(tool_selection.tool_names)))
        ),
    }
    return canonical_json_digest(payload)


def _assembly_input_digest(request: ScenePrepareRequest) -> str:
    """计算 assembly input 摘要。

    :param request: 原始装配请求。
    :returns: ``sha256:<hex>`` 摘要。
    """

    payload: dict[str, JsonValue] = {
        "scene_id": request.scene_id,
        "context_slot_values": _sorted_text_mapping_json(request.context_slot_values),
        "available_tools": _tool_catalog_json(request.available_tools),
    }
    return canonical_json_digest(payload)


def _tool_catalog_json(catalog: SceneToolCatalog) -> JsonValue:
    """把工具目录投影为 digest JSON。

    :param catalog: 工具目录。
    :returns: JSON 投影。
    """

    tools: list[JsonValue] = []
    for tool in sorted(catalog.tools, key=lambda item: item.name):
        value: dict[str, JsonValue] = {
            "name": tool.name,
            "tags": _text_sequence_json(tuple(sorted(tool.tags))),
        }
        tools.append(value)
    return tools


def _require_no_unknown_fields(record: JsonObject, *, allowed: frozenset[str], context: str) -> None:
    """校验 JSON object 只包含允许字段。

    :param record: JSON object。
    :param allowed: 允许出现的字段名集合。
    :param context: 错误消息上下文。
    :returns: ``None``。
    :raises ScenePrepareError: 出现未知字段时抛出。
    """

    unknown = frozenset(record) - allowed
    if unknown:
        raise ScenePrepareError(f"{context} contains unsupported fields: " + ", ".join(sorted(unknown)))


def _parse_optional_fallback_mode(record: JsonObject, *, context: str) -> SceneAgentFallbackMode | None:
    """解析可选 fallback mode。

    :param record: agent policy override JSON object。
    :param context: 错误消息上下文。
    :returns: fallback mode 枚举；字段缺省时返回 ``None``。
    :raises ScenePrepareError: 字段类型或枚举值非法时抛出。
    """

    mode = _optional_str_field(record, field_name="fallback_mode", context=context)
    if mode is None:
        return None
    if mode not in AGENT_FALLBACK_MODES:
        raise ScenePrepareError(f"{context}.fallback_mode is unsupported: {mode}")
    return SceneAgentFallbackMode(mode)


def _text_sequence_json(values: tuple[str, ...]) -> JsonValue:
    """把字符串元组投影为 JSON array。

    :param values: 字符串元组。
    :returns: JSON array。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value)
    return result


def _sorted_text_mapping_json(values: Mapping[str, str]) -> JsonValue:
    """把字符串映射投影为排序 JSON object。

    :param values: 字符串映射。
    :returns: 排序后的 JSON object。
    :raises ScenePrepareError: key 或 value 不是字符串时抛出。
    """

    result: dict[str, JsonValue] = {}
    for key in sorted(values):
        value = values[key]
        if not isinstance(key, str):
            raise ScenePrepareError("context slot key must be string")
        if not isinstance(value, str):
            raise ScenePrepareError(f"context slot value must be string: {key}")
        result[key] = value
    return result


def _text_digest(value: str) -> str:
    """计算文本 SHA-256 摘要。

    :param value: 文本内容。
    :returns: ``sha256:<hex>`` 摘要。
    """

    return _DIGEST_PREFIX + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resolve_contained_path(*, root: Path, relative_path: str, context: str) -> Path:
    """解析并校验相对路径不得逃逸 root。

    :param root: 根目录。
    :param relative_path: 相对路径。
    :param context: 错误消息上下文。
    :returns: 解析后的绝对路径。
    :raises ScenePrepareError: 路径为绝对路径或解析后逃逸 root 时抛出。
    """

    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ScenePrepareError(f"{context} path must be relative")
    resolved_root = root.resolve()
    resolved_path = (resolved_root / candidate).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ScenePrepareError(f"{context} path escapes root: {relative_path}") from exc
    return resolved_path


def _validate_context_slot_values(values: Mapping[str, str]) -> None:
    """校验 Service 传入的 context slot values 仍是字符串映射。

    :param values: context slot values。
    :returns: ``None``。
    :raises ScenePrepareError: key、slot name 或 value 非法时抛出。
    """

    for key, value in values.items():
        if not isinstance(key, str):
            raise ScenePrepareError("context slot key must be string")
        _require_context_slot_name(key, field_name="context_slot_values key")
        if not isinstance(value, str):
            raise ScenePrepareError(f"context slot value must be string: {key}")


def _validate_fragment_uniqueness(fragments: tuple[_ManifestFragment, ...], *, scene_id: str) -> None:
    """校验 fragment id 与 order 唯一。

    :param fragments: fragment 列表。
    :param scene_id: 错误消息中的 scene id。
    :returns: ``None``。
    :raises ScenePrepareError: fragment id 或 order 重复时抛出。
    """

    ids: set[str] = set()
    orders: set[int] = set()
    for fragment in fragments:
        if fragment.fragment_id in ids:
            raise ScenePrepareError(f"duplicate fragment id in {scene_id}: {fragment.fragment_id}")
        if fragment.order in orders:
            raise ScenePrepareError(f"duplicate fragment order in {scene_id}: {fragment.order}")
        ids.add(fragment.fragment_id)
        orders.add(fragment.order)


def _dedupe_context_slots(slots: tuple[_ContextSlot, ...]) -> tuple[_ContextSlot, ...]:
    """按父优先顺序去重 context slots。

    :param slots: 继承链顺序拼接后的 slots。
    :returns: 父优先去重后的 slots。
    """

    seen: set[str] = set()
    result: list[_ContextSlot] = []
    for slot in slots:
        if slot.name in seen:
            continue
        seen.add(slot.name)
        result.append(slot)
    return tuple(result)


def _append_unique(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    """父优先拼接并去重文本元组。

    :param left: 父级文本元组。
    :param right: 子级文本元组。
    :returns: 拼接去重结果。
    """

    result: list[str] = []
    seen: set[str] = set()
    for value in (*left, *right):
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _optional_field(record: JsonObject, field_name: str) -> JsonValue | None:
    """读取可为空字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :returns: 字段值；缺失或 JSON null 返回 ``None``。
    """

    if field_name not in record:
        return None
    return record[field_name]


def _require_mapping_field(record: JsonObject, *, field_name: str, context: str) -> JsonObject:
    """读取必需 JSON object 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段 JSON object。
    :raises ScenePrepareError: 字段缺失或非 object 时抛出。
    """

    if field_name not in record:
        raise ScenePrepareError(f"{context}.{field_name} is required")
    return _require_json_object(record[field_name], context=f"{context}.{field_name}")


def _require_sequence_field(record: JsonObject, *, field_name: str, context: str) -> Sequence[JsonValue]:
    """读取必需 JSON array 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段 JSON array。
    :raises ScenePrepareError: 字段缺失或非 array 时抛出。
    """

    if field_name not in record:
        raise ScenePrepareError(f"{context}.{field_name} is required")
    value = record[field_name]
    if not isinstance(value, list):
        raise ScenePrepareError(f"{context}.{field_name} must be array")
    return value


def _require_json_object(value: JsonValue, *, context: str) -> JsonObject:
    """校验 JSON 值为 object。

    :param value: JSON 值。
    :param context: 错误消息上下文。
    :returns: JSON object。
    :raises ScenePrepareError: 值不是 object 或 key 不是字符串时抛出。
    """

    if not isinstance(value, Mapping):
        raise ScenePrepareError(f"{context} must be object")
    for key in value:
        if not isinstance(key, str):
            raise ScenePrepareError(f"{context} keys must be string")
    return value


def _require_str_field(record: JsonObject, *, field_name: str, context: str) -> str:
    """读取必需字符串字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字符串字段值。
    :raises ScenePrepareError: 字段缺失、非字符串或空白时抛出。
    """

    if field_name not in record:
        raise ScenePrepareError(f"{context}.{field_name} is required")
    value = record[field_name]
    if not isinstance(value, str):
        raise ScenePrepareError(f"{context}.{field_name} must be string")
    return _require_non_empty_text(value, field_name=f"{context}.{field_name}")


def _optional_str_field(record: JsonObject, *, field_name: str, context: str) -> str | None:
    """读取可选字符串字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字符串字段值或 ``None``。
    :raises ScenePrepareError: 字段存在但非字符串或为空时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = record[field_name]
    if not isinstance(value, str):
        raise ScenePrepareError(f"{context}.{field_name} must be string")
    return _require_non_empty_text(value, field_name=f"{context}.{field_name}")


def _require_int_field(record: JsonObject, *, field_name: str, context: str) -> int:
    """读取必需整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 整数字段值。
    :raises ScenePrepareError: 字段缺失、非整数或 bool 时抛出。
    """

    if field_name not in record:
        raise ScenePrepareError(f"{context}.{field_name} is required")
    value = record[field_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ScenePrepareError(f"{context}.{field_name} must be integer")
    return value


def _optional_bool_field(record: JsonObject, *, field_name: str, context: str, default: bool) -> bool:
    """读取可选 bool 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :param default: 字段缺失或为 null 时使用的默认值。
    :returns: bool 字段值。
    :raises ScenePrepareError: 字段存在但非 bool 时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return default
    value = record[field_name]
    if not isinstance(value, bool):
        raise ScenePrepareError(f"{context}.{field_name} must be boolean")
    return value


def _optional_bool_field_or_none(record: JsonObject, *, field_name: str, context: str) -> bool | None:
    """读取可选 bool 字段，缺省时返回 ``None``。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: bool 字段值或 ``None``。
    :raises ScenePrepareError: 字段存在但非 bool 时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = record[field_name]
    if not isinstance(value, bool):
        raise ScenePrepareError(f"{context}.{field_name} must be boolean")
    return value


def _optional_positive_int_field(record: JsonObject, *, field_name: str, context: str) -> int | None:
    """读取可选正整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 正整数或 ``None``。
    :raises ScenePrepareError: 字段存在但不是正整数时抛出。
    """

    value = _optional_int_field(record, field_name=field_name, context=context)
    if value is None:
        return None
    if value < 1:
        raise ScenePrepareError(f"{context}.{field_name} must be >= 1")
    return value


def _optional_non_negative_int_field(record: JsonObject, *, field_name: str, context: str) -> int | None:
    """读取可选非负整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 非负整数或 ``None``。
    :raises ScenePrepareError: 字段存在但不是非负整数时抛出。
    """

    value = _optional_int_field(record, field_name=field_name, context=context)
    if value is None:
        return None
    if value < 0:
        raise ScenePrepareError(f"{context}.{field_name} must be >= 0")
    return value


def _optional_int_field(record: JsonObject, *, field_name: str, context: str) -> int | None:
    """读取可选整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 整数或 ``None``。
    :raises ScenePrepareError: 字段存在但非整数时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = record[field_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ScenePrepareError(f"{context}.{field_name} must be integer")
    return value


def _optional_positive_float_field(record: JsonObject, *, field_name: str, context: str) -> float | None:
    """读取可选有限正数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 有限正数或 ``None``。
    :raises ScenePrepareError: 字段存在但不是有限正数时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = record[field_name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenePrepareError(f"{context}.{field_name} must be number")
    numeric_value = float(value)
    if not math.isfinite(numeric_value) or numeric_value <= 0:
        raise ScenePrepareError(f"{context}.{field_name} must be finite and > 0")
    return numeric_value


def _parse_text_tuple(record: JsonObject, *, field_name: str, context: str) -> tuple[str, ...]:
    """解析必需字符串数组字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字符串元组。
    :raises ScenePrepareError: 字段类型或元素非法时抛出。
    """

    values = _require_sequence_field(record, field_name=field_name, context=context)
    return _text_tuple_from_values(values, context=f"{context}.{field_name}")


def _parse_optional_text_tuple(record: JsonObject, *, field_name: str, context: str) -> tuple[str, ...]:
    """解析可选字符串数组字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字符串元组；缺省为 ``()``。
    :raises ScenePrepareError: 字段存在但类型或元素非法时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return ()
    value = record[field_name]
    if not isinstance(value, list):
        raise ScenePrepareError(f"{context}.{field_name} must be array")
    return _text_tuple_from_values(value, context=f"{context}.{field_name}")


def _text_tuple_from_values(values: Sequence[JsonValue], *, context: str) -> tuple[str, ...]:
    """把 JSON array 解析为字符串元组。

    :param values: JSON 值序列。
    :param context: 错误消息上下文。
    :returns: 字符串元组。
    :raises ScenePrepareError: 元素非字符串或为空时抛出。
    """

    result: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise ScenePrepareError(f"{context}[{index}] must be string")
        result.append(_require_non_empty_text(value, field_name=f"{context}[{index}]"))
    return tuple(result)


def _require_scene_id(value: str, *, field_name: str) -> str:
    """校验 scene id。

    :param value: scene id。
    :param field_name: 错误消息字段名。
    :returns: scene id。
    :raises ScenePrepareError: scene id 为空或含路径字符时抛出。
    """

    text = _require_non_empty_text(value, field_name=field_name)
    if _SCENE_ID_PATTERN.fullmatch(text) is None:
        raise ScenePrepareError(f"{field_name} must be ASCII scene identifier")
    return text


def _require_context_slot_name(value: str, *, field_name: str) -> str:
    """校验 context slot name。

    :param value: context slot name。
    :param field_name: 错误消息字段名。
    :returns: context slot name。
    :raises ScenePrepareError: slot 名称不符合 ASCII identifier 时抛出。
    """

    text = _require_non_empty_text(value, field_name=field_name)
    if _CONTEXT_SLOT_PATTERN.fullmatch(text) is None:
        raise ScenePrepareError(f"{field_name} must be ASCII identifier")
    return text


def _require_non_empty_text(value: str, *, field_name: str) -> str:
    """校验字符串非空白。

    :param value: 字符串值。
    :param field_name: 错误消息字段名。
    :returns: 去掉首尾空白后的字符串。
    :raises ScenePrepareError: 字符串为空白时抛出。
    """

    text = value.strip()
    if not text:
        raise ScenePrepareError(f"{field_name} must not be empty")
    return text


__all__ = [
    "PreparedSceneInputs",
    "SceneFragmentRef",
    "SceneAgentFallbackMode",
    "SceneAgentPolicyOverride",
    "SceneModelHints",
    "ScenePrepare",
    "ScenePrepareError",
    "ScenePrepareRequest",
    "SceneSourceKind",
    "SceneSourceRef",
    "SceneToolCatalog",
    "SceneToolInfo",
    "SceneToolSelectionMode",
    "SceneToolSelectionResult",
    "prepare_scene",
]
