"""迁移后的真实 scene asset 装配测试。"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Final, cast

from dayu.contracts import JsonValue
from dayu.runtime.scene_prepare import (
    ScenePrepareRequest,
    SceneToolCatalog,
    SceneToolInfo,
    prepare_scene,
)

_OLD_SCENE_MAX_ITERATIONS: Final[Mapping[str, int]] = {
    "audit": 16,
    "confirm": 20,
    "decision": 12,
    "fix": 12,
    "infer": 12,
    "interactive": 20,
    "overview": 12,
    "prompt": 24,
    "regenerate": 24,
    "repair": 16,
    "smoke_host_public_conversation_memory": 20,
    "smoke_host_public_conversation_memory_scenarios": 32,
    "smoke_host_public_multiturn": 20,
    "wechat": 16,
    "write": 24,
}
_COMPACTOR_POLICY_SCENES: Final[frozenset[str]] = frozenset(
    {"conversation_compaction"}
)
_LEGACY_TOOLS_CONDITIONAL_MARKERS: Final[tuple[str, ...]] = (
    "<when_tag doc>",
    "</when_tag>",
    "<when_tag fins>",
    "<when_tag ingestion>",
    "<when_tag web>",
    "<when_tool get_current_time>",
    "</when_tool>",
)
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
_ALLOWED_MODEL_FIELDS: Final[frozenset[str]] = frozenset(
    {"default_model_id", "runner_option_hint_id"}
)


def _repo_root() -> Path:
    """返回当前仓库根目录。

    :returns: 仓库根目录路径。
    """

    return Path(__file__).resolve().parents[2]


def _prompt_asset_root() -> Path:
    """返回包内 prompt asset 根目录。

    :returns: prompt asset 根目录。
    """

    return _repo_root() / "dayu" / "config" / "prompts"


def _manifest_root() -> Path:
    """返回包内 scene manifest 根目录。

    :returns: scene manifest 根目录。
    """

    return _prompt_asset_root() / "manifests"


def _iter_manifest_paths() -> Iterator[Path]:
    """遍历所有迁移后的 scene manifest。

    :returns: manifest 路径迭代器。
    """

    yield from sorted(_manifest_root().glob("*.json"))


def _load_manifest(path: Path) -> Mapping[str, JsonValue]:
    """读取单个 scene manifest。

    :param path: manifest 文件路径。
    :returns: manifest JSON object。
    :raises AssertionError: manifest 顶层不是 JSON object 时抛出。
    """

    value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(value, Mapping)
    return value


def _load_package_execution_profiles() -> Mapping[str, JsonValue]:
    """读取包内 execution profiles 配置。

    :returns: execution profiles JSON object。
    :raises AssertionError: 配置顶层不是 JSON object 时抛出。
    """

    path = _repo_root() / "dayu" / "config" / "execution_profiles.json"
    value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(value, Mapping)
    return value


def _required_context_slot_values(
    manifest: Mapping[str, JsonValue],
) -> dict[str, str]:
    """为 manifest 必需 context slot 构造测试值。

    :param manifest: manifest JSON object。
    :returns: 可传给 ScenePrepare 的 context slot values。
    :raises AssertionError: context slot 结构不符合 schema 时抛出。
    """

    slots = manifest["context_slots"]
    assert isinstance(slots, list)
    values: dict[str, str] = {}
    for slot in slots:
        assert isinstance(slot, Mapping)
        name = slot["name"]
        assert isinstance(name, str)
        required_value = slot.get("required")
        required = True if required_value is None else required_value
        assert isinstance(required, bool)
        if required:
            values[name] = f"测试值-{name}"
    return values


def _direct_fragment_paths(manifest: Mapping[str, JsonValue]) -> tuple[Path, ...]:
    """返回 manifest 直接装配的 fragment 绝对路径。

    :param manifest: manifest JSON object。
    :returns: manifest ``fragments`` 直接引用的 fragment 路径。
    :raises AssertionError: fragment 路径不存在、非字符串或逃逸 root 时抛出。
    """

    prompt_root = _prompt_asset_root().resolve()
    fragments = manifest["fragments"]
    assert isinstance(fragments, list)
    paths: list[Path] = []
    for fragment in fragments:
        assert isinstance(fragment, Mapping)
        relative_path = fragment["path"]
        assert isinstance(relative_path, str)
        resolved_path = (prompt_root / relative_path).resolve()
        assert resolved_path.exists()
        assert resolved_path.is_file()
        assert resolved_path.relative_to(prompt_root) == Path(relative_path)
        paths.append(resolved_path)
    return tuple(paths)


def _fake_tool_catalog() -> SceneToolCatalog:
    """构造覆盖迁移 manifest 工具标签的 fake 工具目录。

    :returns: ScenePrepare 可使用的工具目录。
    """

    return SceneToolCatalog(
        tools=(
            SceneToolInfo(name="list_documents", tags=frozenset({"fins"})),
            SceneToolInfo(name="get_document_sections", tags=frozenset({"fins"})),
            SceneToolInfo(name="read_section", tags=frozenset({"fins"})),
            SceneToolInfo(name="search_document", tags=frozenset({"fins"})),
            SceneToolInfo(name="list_tables", tags=frozenset({"fins"})),
            SceneToolInfo(name="get_table", tags=frozenset({"fins"})),
            SceneToolInfo(name="get_page_content", tags=frozenset({"fins"})),
            SceneToolInfo(name="get_financial_statement", tags=frozenset({"fins"})),
            SceneToolInfo(name="query_xbrl_facts", tags=frozenset({"fins"})),
            SceneToolInfo(name="start_fins_download", tags=frozenset({"fins"})),
            SceneToolInfo(name="start_fins_preprocess", tags=frozenset({"fins"})),
            SceneToolInfo(name="fake_web_search", tags=frozenset({"web"})),
            SceneToolInfo(name="fake_ingestion", tags=frozenset({"ingestion"})),
            SceneToolInfo(
                name="fake_smoke_fact",
                tags=frozenset({"manual-smoke"}),
            ),
        )
    )


def _assert_fragment_paths_exist_under_prompt_root(
    manifest: Mapping[str, JsonValue],
) -> None:
    """校验 manifest 直接引用的 fragment 路径存在且未逃逸 prompt root。

    :param manifest: manifest JSON object。
    :returns: ``None``。
    :raises AssertionError: fragment 路径不存在、非字符串或逃逸 root 时抛出。
    """

    _direct_fragment_paths(manifest)


def test_all_migrated_scene_assets_prepare_successfully() -> None:
    """所有迁移 manifest 都能用 fake 工具目录完成 ScenePrepare 装配。"""

    paths = tuple(_iter_manifest_paths())
    assert paths
    for path in paths:
        manifest = _load_manifest(path)
        scene = manifest["scene"]
        assert isinstance(scene, str)
        _assert_fragment_paths_exist_under_prompt_root(manifest)

        result = prepare_scene(
            ScenePrepareRequest(
                scene_id=scene,
                scene_manifest_root=_manifest_root(),
                prompt_asset_root=_prompt_asset_root(),
                context_slot_values=_required_context_slot_values(manifest),
                available_tools=_fake_tool_catalog(),
            )
        )

        assert result.system_messages
        assert result.fragment_refs
        assert result.capability_tags == (scene,)


def test_migrated_scene_manifest_schema_excludes_legacy_fields() -> None:
    """迁移后 manifest 只能使用 scene-only 顶层字段和新 model hint 字段。"""

    paths = tuple(_iter_manifest_paths())
    assert paths
    for path in paths:
        manifest = _load_manifest(path)
        assert not (frozenset(manifest) - _ALLOWED_MANIFEST_FIELDS)
        assert "conversation" not in manifest
        assert "runtime" not in manifest
        model = manifest.get("model")
        if model is not None:
            assert isinstance(model, Mapping)
            assert not (frozenset(model) - _ALLOWED_MODEL_FIELDS)
            assert "default_name" not in model
            assert "temperature_profile" not in model
            assert "default_model_id" in model


def test_conversation_compaction_default_model_matches_default_profile_compactor() -> None:
    """conversation_compaction 默认模型必须对齐默认 execution profile compactor。

    :returns: ``None``。
    :raises AssertionError: scene manifest 与默认 profile compactor 模型不一致时抛出。
    """

    manifest = _load_manifest(_manifest_root() / "conversation_compaction.json")
    profiles = _load_package_execution_profiles()
    default_profile_id = profiles["default_execution_profile_id"]
    assert isinstance(default_profile_id, str)
    execution_profiles = profiles["execution_profiles"]
    assert isinstance(execution_profiles, Mapping)
    default_profile = execution_profiles[default_profile_id]
    assert isinstance(default_profile, Mapping)
    compactor_baseline = default_profile["compactor_baseline"]
    assert isinstance(compactor_baseline, Mapping)
    expected_model_id = compactor_baseline["model_id"]
    assert isinstance(expected_model_id, str)
    model = manifest["model"]
    assert isinstance(model, Mapping)

    assert model["default_model_id"] == expected_model_id


def test_prompt_mt_scene_asset_is_removed_and_smoke_scene_is_ordinary_asset() -> None:
    """prompt_mt 不再作为 scene；smoke_host_public_multiturn 必须是普通资产。"""

    manifest_root = _manifest_root()
    prompt_root = _prompt_asset_root()

    assert not (manifest_root / "prompt_mt.json").exists()
    assert not (prompt_root / "scenes" / "prompt_mt.md").exists()
    assert (manifest_root / "smoke_host_public_multiturn.json").exists()
    assert (prompt_root / "scenes" / "smoke_host_public_multiturn.md").exists()


def test_scene_manifest_agent_policy_carries_old_max_iterations_only() -> None:
    """旧 scene 只迁移 max_iterations，compactor scene 可声明完整 policy。"""

    paths = tuple(_iter_manifest_paths())
    assert paths
    for path in paths:
        manifest = _load_manifest(path)
        scene = manifest["scene"]
        assert isinstance(scene, str)
        agent_policy = manifest.get("agent_policy")
        expected_max_iterations = _OLD_SCENE_MAX_ITERATIONS.get(scene)
        if expected_max_iterations is None:
            if scene in _COMPACTOR_POLICY_SCENES:
                assert isinstance(agent_policy, Mapping)
                assert agent_policy.get("max_iterations") == 1
                assert agent_policy.get("allow_tool_calls") is False
                assert agent_policy.get("fallback_mode") == "raise_error"
                continue
            assert agent_policy is None
            continue

        assert isinstance(agent_policy, Mapping)
        assert agent_policy.get("max_iterations") == expected_max_iterations
        assert "tool_timeout_seconds" not in agent_policy
        assert "tool_execution_timeout_seconds" not in agent_policy

        result = prepare_scene(
            ScenePrepareRequest(
                scene_id=scene,
                scene_manifest_root=_manifest_root(),
                prompt_asset_root=_prompt_asset_root(),
                context_slot_values=_required_context_slot_values(manifest),
                available_tools=_fake_tool_catalog(),
            )
        )
        assert result.agent_policy_override is not None
        assert result.agent_policy_override.max_iterations == expected_max_iterations


def test_migrated_base_prompt_assets_preserve_legacy_text_boundaries() -> None:
    """base prompt 资产保留旧项目文本边界，不混入未裁决的新占位段。"""

    prompt_root = _prompt_asset_root()
    agents_content = (prompt_root / "base" / "agents.md").read_text(encoding="utf-8")
    fact_rules_content = (prompt_root / "base" / "fact_rules.md").read_text(
        encoding="utf-8"
    )
    tools_content = (prompt_root / "base" / "tools.md").read_text(encoding="utf-8")

    assert "当前研究主体" not in agents_content
    assert "fins_default_subject" not in agents_content
    assert "用户任务边界" not in fact_rules_content
    assert "base_user" not in fact_rules_content
    for marker in _LEGACY_TOOLS_CONDITIONAL_MARKERS:
        assert marker in tools_content


def test_migrated_prompt_assets_exclude_forbidden_legacy_files() -> None:
    """迁移资产不得包含旧 tasks、contract 文件或未引用模板。"""

    prompt_root = _prompt_asset_root()
    assert not (prompt_root / "tasks").exists()
    assert not (prompt_root / "base" / "directories.md").exists()
    assert not tuple(prompt_root.rglob("*.contract.yaml"))
    assert not tuple(prompt_root.rglob("*.contract.yml"))
