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
from dayu.tools.utils.provider import build_get_current_time_tool_definition

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
_COMPACTOR_POLICY_SCENES: Final[frozenset[str]] = frozenset({"conversation_compaction"})
_LEGACY_TOOLS_CONDITIONAL_MARKERS: Final[tuple[str, ...]] = (
    "<when_tag doc>",
    "</when_tag>",
    "<when_tag fins-read>",
    "<when_tag web>",
    "<when_tool start_fins_download>",
    "<when_tool start_fins_preprocess>",
    "<when_tool get_current_time>",
    "</when_tool>",
)
_PREPARED_CONDITIONAL_MARKERS: Final[tuple[str, ...]] = (
    "<when_tag",
    "</when_tag>",
    "<when_tool",
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
_ALLOWED_MODEL_FIELDS: Final[frozenset[str]] = frozenset({"default_model_id", "runner_option_hint_id"})
_FINS_DEFAULT_SUBJECT_SLOT: Final[str] = "fins_default_subject"
_FINS_DEFAULT_SUBJECT_PLACEHOLDER: Final[str] = "{{fins_default_subject}}"
_FINS_DEFAULT_SUBJECT_TITLE: Final[str] = "# 当前分析对象"
_FINS_DEFAULT_SUBJECT_MARKDOWN: Final[str] = "# 当前分析对象\n你正在分析的是 V（Visa Inc.）。"
_CURRENT_TIME_SLOT: Final[str] = "current_time"
_CURRENT_TIME_PLACEHOLDER: Final[str] = "{{current_time}}"
_CURRENT_TIME_TITLE: Final[str] = "# 当前时间"
_CURRENT_TIME_MARKDOWN: Final[str] = (
    "# 当前时间\n"
    "现在是 2026年7月7日 17:20（Asia/Shanghai，星期二）。\n"
    "这是对话开始时的当前时间；回答“现在/今天/当前时间”默认使用它；该时间不会自动更新。"
)
_NO_DEFAULT_SUBJECT_SCENES: Final[frozenset[str]] = frozenset({"wechat"})
_CONVERSATION_MEMORY_SMOKE_SCENES: Final[frozenset[str]] = frozenset(
    {
        "smoke_host_public_conversation_memory",
        "smoke_host_public_conversation_memory_scenarios",
    }
)
_TIME_TOOL_SCENES: Final[frozenset[str]] = frozenset({"interactive", "wechat"})
_PROMPT_OUTPUT_CONTRACT_LINE: Final[str] = "- 输出 Markdown 格式。"


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


def _manifest_declares_context_slot(
    manifest: Mapping[str, JsonValue],
    slot_name: str,
) -> bool:
    """判断 manifest 是否声明指定 context slot。

    :param manifest: manifest JSON object。
    :param slot_name: context slot 名称。
    :returns: 声明该 slot 时返回 ``True``。
    :raises AssertionError: context slot 结构不符合 schema 时抛出。
    """

    slots = manifest["context_slots"]
    assert isinstance(slots, list)
    for slot in slots:
        assert isinstance(slot, Mapping)
        name = slot["name"]
        assert isinstance(name, str)
        if name == slot_name:
            return True
    return False


def _scene_fragment_path(manifest: Mapping[str, JsonValue]) -> Path:
    """返回当前 manifest 对应的 scene fragment 文件。

    :param manifest: manifest JSON object。
    :returns: ``prompts/scenes`` 下的 scene fragment 路径。
    :raises AssertionError: 找不到唯一 scene fragment 时抛出。
    """

    scene = manifest["scene"]
    assert isinstance(scene, str)
    candidates = tuple(
        path
        for path in _direct_fragment_paths(manifest)
        if path.parts[-2:] == ("scenes", f"{scene}.md")
    )
    assert len(candidates) == 1
    return candidates[0]


def _placeholder_line_indexes(lines: tuple[str, ...], placeholder: str) -> tuple[int, ...]:
    """返回指定占位符所在行号。

    :param lines: scene fragment 按行拆分后的内容。
    :param placeholder: 要查找的占位符文本。
    :returns: 包含占位符的零基行号。
    """

    return tuple(
        index
        for index, line in enumerate(lines)
        if placeholder in line
    )


def _first_contract_content_line_index(lines: tuple[str, ...]) -> int:
    """返回首个执行契约正文行号。

    :param lines: scene fragment 按行拆分后的内容。
    :returns: 首个非空、非 Markdown 标题、非 context slot 占位符的零基行号。
    :raises AssertionError: scene fragment 没有执行契约正文时抛出。
    """

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped == _FINS_DEFAULT_SUBJECT_PLACEHOLDER:
            continue
        if stripped == _CURRENT_TIME_PLACEHOLDER:
            continue
        return index
    raise AssertionError("scene fragment 缺少执行契约正文")


def _last_non_empty_line_index(lines: tuple[str, ...]) -> int:
    """返回最后一个非空内容行号。

    :param lines: scene fragment 按行拆分后的内容。
    :returns: 最后一个非空行的零基行号。
    :raises AssertionError: scene fragment 为空时抛出。
    """

    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip():
            return index
    raise AssertionError("scene fragment 为空")


def _fake_tool_catalog() -> SceneToolCatalog:
    """构造覆盖迁移 manifest 工具标签的 fake 工具目录。

    :returns: ScenePrepare 可使用的工具目录。
    """

    return SceneToolCatalog(
        tools=(
            SceneToolInfo(name="list_documents", tags=frozenset({"fins", "fins-read"})),
            SceneToolInfo(name="get_document_sections", tags=frozenset({"fins", "fins-read"})),
            SceneToolInfo(name="read_section", tags=frozenset({"fins", "fins-read"})),
            SceneToolInfo(name="search_document", tags=frozenset({"fins", "fins-read"})),
            SceneToolInfo(name="list_tables", tags=frozenset({"fins", "fins-read"})),
            SceneToolInfo(name="get_table", tags=frozenset({"fins", "fins-read"})),
            SceneToolInfo(name="get_page_content", tags=frozenset({"fins", "fins-read"})),
            SceneToolInfo(name="get_financial_statement", tags=frozenset({"fins", "fins-read"})),
            SceneToolInfo(name="query_xbrl_facts", tags=frozenset({"fins", "fins-read"})),
            SceneToolInfo(name="start_fins_download", tags=frozenset({"fins", "fins-download"})),
            SceneToolInfo(name="start_fins_preprocess", tags=frozenset({"fins", "fins-preprocess"})),
            SceneToolInfo(name="start_fins_upload", tags=frozenset({"fins", "fins-upload"})),
            SceneToolInfo(name="fake_web_search", tags=frozenset({"web"})),
            SceneToolInfo(name="get_current_time", tags=frozenset({"utils", "time"})),
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


def test_fins_default_subject_slot_is_rendered_by_declaring_scenes() -> None:
    """声明默认研究主体 slot 的 scene 必须在执行契约正文之后渲染该 slot。"""

    for path in _iter_manifest_paths():
        manifest = _load_manifest(path)
        scene = manifest["scene"]
        assert isinstance(scene, str)
        scene_content = _scene_fragment_path(manifest).read_text(encoding="utf-8")
        lines = tuple(scene_content.splitlines())
        placeholder_indexes = _placeholder_line_indexes(lines, _FINS_DEFAULT_SUBJECT_PLACEHOLDER)
        declares_subject = _manifest_declares_context_slot(manifest, _FINS_DEFAULT_SUBJECT_SLOT)

        if declares_subject:
            assert len(placeholder_indexes) == 1, scene
            placeholder_index = placeholder_indexes[0]
            assert lines[placeholder_index] == _FINS_DEFAULT_SUBJECT_PLACEHOLDER, scene
            assert placeholder_index > _first_contract_content_line_index(lines), scene
            assert placeholder_index == _last_non_empty_line_index(lines), scene
        if scene in _NO_DEFAULT_SUBJECT_SCENES:
            assert not declares_subject, scene
            assert not placeholder_indexes, scene


def test_conversation_memory_smoke_scenes_do_not_use_default_subject_slot() -> None:
    """conversation memory smoke scene 不得声明或渲染默认研究主体 slot。"""

    for scene in _CONVERSATION_MEMORY_SMOKE_SCENES:
        manifest = _load_manifest(_manifest_root() / f"{scene}.json")
        scene_content = _scene_fragment_path(manifest).read_text(encoding="utf-8")

        assert not _manifest_declares_context_slot(manifest, _FINS_DEFAULT_SUBJECT_SLOT), scene
        assert _FINS_DEFAULT_SUBJECT_PLACEHOLDER not in scene_content, scene


def test_current_time_slot_is_rendered_by_non_compact_scenes() -> None:
    """除 compact scene 外，所有 scene 必须在执行契约正文之后渲染当前时间 slot。"""

    for path in _iter_manifest_paths():
        manifest = _load_manifest(path)
        scene = manifest["scene"]
        assert isinstance(scene, str)
        scene_content = _scene_fragment_path(manifest).read_text(encoding="utf-8")
        lines = tuple(scene_content.splitlines())
        current_indexes = _placeholder_line_indexes(lines, _CURRENT_TIME_PLACEHOLDER)
        subject_indexes = _placeholder_line_indexes(lines, _FINS_DEFAULT_SUBJECT_PLACEHOLDER)
        declares_current_time = _manifest_declares_context_slot(manifest, _CURRENT_TIME_SLOT)
        is_compact_scene = scene in _COMPACTOR_POLICY_SCENES

        if is_compact_scene:
            assert not declares_current_time, scene
            assert not current_indexes, scene
            continue

        assert declares_current_time, scene
        assert len(current_indexes) == 1, scene
        current_index = current_indexes[0]
        assert lines[current_index] == _CURRENT_TIME_PLACEHOLDER, scene
        assert current_index > _first_contract_content_line_index(lines), scene
        if subject_indexes:
            assert current_index < subject_indexes[0], scene
        else:
            assert current_index == _last_non_empty_line_index(lines), scene

    compaction_user_content = (
        _prompt_asset_root() / "scenes" / "conversation_compaction_user.md"
    ).read_text(encoding="utf-8")
    assert _CURRENT_TIME_PLACEHOLDER not in compaction_user_content


def test_prepared_fins_default_subject_does_not_interrupt_scene_contract() -> None:
    """真实 ScenePrepare 展开后，默认研究主体块不得插入到执行契约正文之前。"""

    for path in _iter_manifest_paths():
        manifest = _load_manifest(path)
        scene = manifest["scene"]
        assert isinstance(scene, str)
        if not _manifest_declares_context_slot(manifest, _FINS_DEFAULT_SUBJECT_SLOT):
            continue

        scene_content = _scene_fragment_path(manifest).read_text(encoding="utf-8")
        lines = tuple(scene_content.splitlines())
        scene_title = lines[0]
        first_contract_line = lines[_first_contract_content_line_index(lines)]
        context_slot_values = _required_context_slot_values(manifest)
        context_slot_values[_FINS_DEFAULT_SUBJECT_SLOT] = _FINS_DEFAULT_SUBJECT_MARKDOWN

        result = prepare_scene(
            ScenePrepareRequest(
                scene_id=scene,
                scene_manifest_root=_manifest_root(),
                prompt_asset_root=_prompt_asset_root(),
                context_slot_values=context_slot_values,
                available_tools=_fake_tool_catalog(),
            )
        )

        system_prompt = result.system_prompt
        scene_title_index = system_prompt.index(scene_title)
        first_contract_index = system_prompt.index(first_contract_line, scene_title_index)
        subject_title_index = system_prompt.index(_FINS_DEFAULT_SUBJECT_TITLE, scene_title_index)

        assert system_prompt.count(_FINS_DEFAULT_SUBJECT_TITLE) == 1, scene
        assert system_prompt.count("你正在分析的是 V（Visa Inc.）。") == 1, scene
        assert scene_title_index < first_contract_index < subject_title_index, scene
        if scene == "prompt":
            prompt_output_index = system_prompt.index(
                _PROMPT_OUTPUT_CONTRACT_LINE,
                scene_title_index,
            )
            assert prompt_output_index < subject_title_index, scene


def test_prepared_current_time_does_not_interrupt_scene_contract() -> None:
    """真实 ScenePrepare 展开后，当前时间块不得插入到执行契约正文之前。"""

    for path in _iter_manifest_paths():
        manifest = _load_manifest(path)
        scene = manifest["scene"]
        assert isinstance(scene, str)
        if scene in _COMPACTOR_POLICY_SCENES:
            continue

        scene_content = _scene_fragment_path(manifest).read_text(encoding="utf-8")
        lines = tuple(scene_content.splitlines())
        scene_title = lines[0]
        first_contract_line = lines[_first_contract_content_line_index(lines)]
        context_slot_values = _required_context_slot_values(manifest)
        context_slot_values[_CURRENT_TIME_SLOT] = _CURRENT_TIME_MARKDOWN
        if _manifest_declares_context_slot(manifest, _FINS_DEFAULT_SUBJECT_SLOT):
            context_slot_values[_FINS_DEFAULT_SUBJECT_SLOT] = _FINS_DEFAULT_SUBJECT_MARKDOWN

        result = prepare_scene(
            ScenePrepareRequest(
                scene_id=scene,
                scene_manifest_root=_manifest_root(),
                prompt_asset_root=_prompt_asset_root(),
                context_slot_values=context_slot_values,
                available_tools=_fake_tool_catalog(),
            )
        )

        system_prompt = result.system_prompt
        scene_title_index = system_prompt.index(scene_title)
        first_contract_index = system_prompt.index(first_contract_line, scene_title_index)
        current_title_index = system_prompt.index(_CURRENT_TIME_TITLE, scene_title_index)

        assert system_prompt.count(_CURRENT_TIME_TITLE) == 1, scene
        assert scene_title_index < first_contract_index < current_title_index, scene
        if _manifest_declares_context_slot(manifest, _FINS_DEFAULT_SUBJECT_SLOT):
            subject_title_index = system_prompt.index(_FINS_DEFAULT_SUBJECT_TITLE, scene_title_index)
            assert current_title_index < subject_title_index, scene
        if scene == "prompt":
            prompt_output_index = system_prompt.index(
                _PROMPT_OUTPUT_CONTRACT_LINE,
                scene_title_index,
            )
            assert prompt_output_index < current_title_index, scene


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


def test_packaged_select_manifests_use_tag_only_tool_selection() -> None:
    """包内 select manifest 不得列非空 tool_names。"""

    paths = tuple(_iter_manifest_paths())
    assert paths
    for path in paths:
        manifest = _load_manifest(path)
        tool_selection = manifest["tool_selection"]
        assert isinstance(tool_selection, Mapping)
        if tool_selection["mode"] == "select":
            tool_names = tool_selection["tool_names"]
            tool_tags_any = tool_selection["tool_tags_any"]
            assert tool_names == []
            assert isinstance(tool_tags_any, list)
            assert tool_tags_any


def test_infer_manifest_selects_read_and_web_without_long_transaction_or_upload() -> None:
    """infer manifest 必须保持 read/web 暴露面并排除长事务与 upload。"""

    result = prepare_scene(
        ScenePrepareRequest(
            scene_id="infer",
            scene_manifest_root=_manifest_root(),
            prompt_asset_root=_prompt_asset_root(),
            context_slot_values={
                "current_time": "测试当前时间",
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_fake_tool_catalog(),
        )
    )

    selected = result.tool_selection.tool_names
    assert selected is not None
    assert "list_documents" in selected
    assert "fake_web_search" in selected
    assert "start_fins_download" not in selected
    assert "start_fins_preprocess" not in selected
    assert "get_current_time" not in selected
    assert "start_fins_upload" not in selected


def test_prompt_prepared_output_filters_long_transaction_guidance() -> None:
    """prompt scene 不得暴露下载、预处理、上传或实时当前时间工具指引。"""

    result = prepare_scene(
        ScenePrepareRequest(
            scene_id="prompt",
            scene_manifest_root=_manifest_root(),
            prompt_asset_root=_prompt_asset_root(),
            context_slot_values={
                "current_time": "测试当前时间",
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_fake_tool_catalog(),
        )
    )

    selected = result.tool_selection.tool_names
    assert selected is not None
    assert "get_financial_statement" in selected
    assert "get_current_time" not in selected
    assert "start_fins_download" not in selected
    assert "start_fins_preprocess" not in selected
    assert "start_fins_upload" not in selected
    assert "财报工具指引" in result.system_prompt
    assert "get_current_time" not in result.system_prompt
    assert "start_fins_download" not in result.system_prompt
    assert "start_fins_preprocess" not in result.system_prompt
    assert "start_fins_upload" not in result.system_prompt
    for marker in _PREPARED_CONDITIONAL_MARKERS:
        assert marker not in result.system_prompt


def test_interactive_and_wechat_prepared_output_keep_download_preprocess_guidance() -> None:
    """interactive/wechat scene 应暴露下载、预处理和当前时间指引。"""

    for scene_id in ("interactive", "wechat"):
        context_slot_values = {"current_time": "测试当前时间"}
        if scene_id == "interactive":
            context_slot_values["fins_default_subject"] = ""
        result = prepare_scene(
            ScenePrepareRequest(
                scene_id=scene_id,
                scene_manifest_root=_manifest_root(),
                prompt_asset_root=_prompt_asset_root(),
                context_slot_values=context_slot_values,
                available_tools=_fake_tool_catalog(),
            )
        )

        selected = result.tool_selection.tool_names
        assert selected is not None
        assert "start_fins_download" in selected
        assert "start_fins_preprocess" in selected
        assert "get_current_time" in selected
        assert "start_fins_upload" not in selected
        assert "start_fins_download" in result.system_prompt
        assert "start_fins_preprocess" in result.system_prompt
        assert "get_current_time" in result.system_prompt
        assert "start_fins_upload" not in result.system_prompt
        for marker in _PREPARED_CONDITIONAL_MARKERS:
            assert marker not in result.system_prompt


def test_get_current_time_tool_is_selected_only_for_interactive_wechat_scenes() -> None:
    """只有 interactive/wechat scene 应暴露真实当前时间工具。"""

    for path in _iter_manifest_paths():
        manifest = _load_manifest(path)
        scene = manifest["scene"]
        assert isinstance(scene, str)
        result = prepare_scene(
            ScenePrepareRequest(
                scene_id=scene,
                scene_manifest_root=_manifest_root(),
                prompt_asset_root=_prompt_asset_root(),
                context_slot_values=_required_context_slot_values(manifest),
                available_tools=_fake_tool_catalog(),
            )
        )

        selected = result.tool_selection.tool_names
        assert selected is not None
        if scene in _TIME_TOOL_SCENES:
            assert "get_current_time" in selected, scene
            assert "get_current_time" in result.system_prompt, scene
        else:
            assert "get_current_time" not in selected, scene
            assert "get_current_time" not in result.system_prompt, scene


def test_current_time_rendering_explains_static_boundary_without_internal_terms() -> None:
    """当前时间文本必须说明静态边界，且不暴露内部实现术语。"""

    result = prepare_scene(
        ScenePrepareRequest(
            scene_id="prompt",
            scene_manifest_root=_manifest_root(),
            prompt_asset_root=_prompt_asset_root(),
            context_slot_values={
                "current_time": _CURRENT_TIME_MARKDOWN,
                "fins_default_subject": _FINS_DEFAULT_SUBJECT_MARKDOWN,
            },
            available_tools=_fake_tool_catalog(),
        )
    )

    assert "对话开始时的当前时间" in result.system_prompt
    assert "该时间不会自动更新" in result.system_prompt
    assert "回答“现在/今天/当前时间”默认使用它" in result.system_prompt
    for internal_term in ("Host", "run input", "context slot", "scene", "tool selection"):
        assert internal_term not in _CURRENT_TIME_MARKDOWN


def test_get_current_time_tool_description_explains_refresh_boundary() -> None:
    """当前时间工具描述必须说明重新确认实时钟的调用边界。"""

    description = build_get_current_time_tool_definition().schema.function.description

    assert "获取调用这一刻的当前时间" in description
    assert "用户明确要求获取此刻最新时间" in description
    assert "等待、查询、下载、上传、处理等动作完成后再确认时间" in description
    assert "普通“现在/今天/当前时间”问题如果不需要重新确认" in description
    assert "不调用本工具" in description
    for internal_term in ("Host", "run input", "context slot", "scene", "tool selection"):
        assert internal_term not in description


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
    fact_rules_content = (prompt_root / "base" / "fact_rules.md").read_text(encoding="utf-8")
    tools_content = (prompt_root / "base" / "tools.md").read_text(encoding="utf-8")

    assert "当前研究主体" not in agents_content
    assert "fins_default_subject" not in agents_content
    assert "用户任务边界" not in fact_rules_content
    assert "<when_tag fins>" not in tools_content
    assert "next_step.action" not in tools_content
    assert "轮询" not in tools_content
    for marker in _LEGACY_TOOLS_CONDITIONAL_MARKERS:
        assert marker in tools_content


def test_migrated_prompt_assets_exclude_forbidden_legacy_files() -> None:
    """迁移资产不得包含旧 tasks、contract 文件或未引用模板。"""

    prompt_root = _prompt_asset_root()
    assert not (prompt_root / "tasks").exists()
    assert not (prompt_root / "base" / "directories.md").exists()
    assert not tuple(prompt_root.rglob("*.contract.yaml"))
    assert not tuple(prompt_root.rglob("*.contract.yml"))
