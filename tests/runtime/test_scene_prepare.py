"""``dayu.runtime.scene_prepare`` scene 装配测试。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

import pytest

from dayu.contracts import JsonValue
import dayu.runtime.scene_prepare as scene_prepare_module
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    SceneFragmentRef,
    ScenePrepareError,
    ScenePrepareRequest,
    SceneSourceKind,
    SceneToolCatalog,
    SceneToolInfo,
    prepare_scene,
)

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_PACKAGE_PROMPT_ROOT: Final[Path] = _REPO_ROOT / "dayu" / "config" / "prompts"
_PACKAGE_MANIFEST_ROOT: Final[Path] = _PACKAGE_PROMPT_ROOT / "manifests"
_START_FINS_UPLOAD_TOOL_NAME: Final[str] = "start_fins_upload"
_DEFAULT_FINS_NON_UPLOAD_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "list_documents",
        "get_document_sections",
        "read_section",
        "search_document",
        "list_tables",
        "get_table",
        "get_page_content",
        "get_financial_statement",
        "query_xbrl_facts",
        "start_fins_download",
        "start_fins_preprocess",
    }
)
_DEFAULT_NON_UPLOAD_SCENE_IDS: Final[tuple[str, ...]] = (
    "confirm",
    "decision",
    "fix",
    "infer",
    "interactive",
    "prompt",
    "regenerate",
    "repair",
    "wechat",
    "write",
)
_DEFAULT_WEB_SCENE_IDS: Final[frozenset[str]] = frozenset(
    scene_id for scene_id in _DEFAULT_NON_UPLOAD_SCENE_IDS if scene_id != "infer"
)
_DEFAULT_WEB_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {"search_web", "fetch_web_page"}
)


def test_scene_fragment_ref_is_public_export() -> None:
    """PreparedSceneInputs.fragment_refs 依赖的类型必须在 __all__ 中公开。"""

    assert "SceneFragmentRef" in scene_prepare_module.__all__
    assert SceneFragmentRef.__name__ == "SceneFragmentRef"


def test_require_json_object_rejects_non_string_keys() -> None:
    """scene JSON object 校验必须拒绝 Python runtime 传入的非字符串 key。"""

    invalid_mapping = cast(JsonValue, {1: "value"})

    with pytest.raises(ScenePrepareError, match="keys must be string"):
        scene_prepare_module._require_json_object(
            invalid_mapping,
            context="scene",
        )


def test_manifest_model_missing_required_field_fails_fast(tmp_path: Path) -> None:
    """scene_prepare 缺字段由字段级 required 校验独立 fail-fast。"""

    _write_json(
        tmp_path / "manifests" / "missing_model_field.json",
        _manifest("missing_model_field", model={}),
    )

    with pytest.raises(
        ScenePrepareError,
        match="missing_model_field.json.model.default_model_id is required",
    ):
        prepare_scene(_request(tmp_path, "missing_model_field"))


def _write_json(path: Path, value: JsonValue) -> None:
    """写入 JSON fixture。

    :param path: 目标路径。
    :param value: JSON 值。
    :returns: ``None``。
    :raises OSError: 文件写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    """写入文本 fixture。

    :param path: 目标路径。
    :param value: 文本内容。
    :returns: ``None``。
    :raises OSError: 文件写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _fragment(
    fragment_id: str,
    path: str,
    order: int,
    *,
    required: bool = True,
) -> dict[str, JsonValue]:
    """构造 fragment manifest 记录。

    :param fragment_id: fragment id。
    :param path: 相对 prompt asset root 的路径。
    :param order: 拼接顺序。
    :param required: 是否必需。
    :returns: fragment JSON object。
    """

    return {
        "id": fragment_id,
        "path": path,
        "order": order,
        "required": required,
    }


def _slot(name: str, *, required: bool = True) -> dict[str, JsonValue]:
    """构造 context slot manifest 记录。

    :param name: slot 名称。
    :param required: 是否必需。
    :returns: context slot JSON object。
    """

    return {
        "name": name,
        "value_type": "string",
        "required": required,
    }


def _manifest(
    scene_id: str,
    *,
    extends: list[JsonValue] | None = None,
    model_is_null: bool = False,
    model: JsonValue | None = None,
    agent_policy: JsonValue | None = None,
    tool_selection: JsonValue | None = None,
    fragments: list[JsonValue] | None = None,
    context_slots: list[JsonValue] | None = None,
    capability_tags: list[JsonValue] | None = None,
) -> dict[str, JsonValue]:
    """构造完整 scene manifest JSON object。

    :param scene_id: scene id。
    :param extends: 父 scene id 数组。
    :param model_is_null: 是否显式写入 JSON null 的 model 字段。
    :param model: model hint 字段。
    :param agent_policy: agent policy override 字段。
    :param tool_selection: tool selection 字段。
    :param fragments: fragments 字段。
    :param context_slots: context slots 字段。
    :param capability_tags: capability tags 字段。
    :returns: manifest JSON object。
    """

    return {
        "schema_version": 1,
        "scene": scene_id,
        "version": "v1",
        "description": f"{scene_id} test scene",
        "capability_tags": [] if capability_tags is None else capability_tags,
        "extends": [] if extends is None else extends,
        "model": (None if model_is_null else {"default_model_id": "analyst-model"} if model is None else model),
        "agent_policy": agent_policy,
        "tool_selection": (
            {"mode": "all", "tool_names": [], "tool_tags_any": [], "allow_empty": False}
            if tool_selection is None
            else tool_selection
        ),
        "defaults": {"missing_required_fragment": "fail_closed"},
        "fragments": [] if fragments is None else fragments,
        "context_slots": [] if context_slots is None else context_slots,
    }


def _request(
    tmp_path: Path,
    scene_id: str,
    *,
    context_slot_values: Mapping[str, str] | None = None,
    tools: tuple[SceneToolInfo, ...] = (),
) -> ScenePrepareRequest:
    """构造 ScenePrepareRequest。

    :param tmp_path: pytest 临时目录。
    :param scene_id: scene id。
    :param context_slot_values: context slot values。
    :param tools: 可用工具目录。
    :returns: ScenePrepare 请求。
    """

    return ScenePrepareRequest(
        scene_id=scene_id,
        scene_manifest_root=tmp_path / "manifests",
        prompt_asset_root=tmp_path / "prompts",
        context_slot_values={} if context_slot_values is None else context_slot_values,
        available_tools=SceneToolCatalog(tools=tools),
    )


def _default_manifest_tool_catalog() -> SceneToolCatalog:
    """构造默认 manifest 选择测试用工具目录。

    Returns:
        覆盖 Fins read/download/preprocess/upload 与 Web 工具的目录。

    Raises:
        ValueError: 工具名或标签非法时由 SceneToolInfo 抛出。
    """

    tools = [
        SceneToolInfo(name=tool_name, tags=frozenset({"fins"}))
        for tool_name in sorted(_DEFAULT_FINS_NON_UPLOAD_TOOL_NAMES)
    ]
    tools.append(
        SceneToolInfo(
            name=_START_FINS_UPLOAD_TOOL_NAME,
            tags=frozenset({"fins", "fins-upload"}),
        )
    )
    tools.extend(
        (
            SceneToolInfo(name="search_web", tags=frozenset({"web"})),
            SceneToolInfo(name="fetch_web_page", tags=frozenset({"web"})),
        )
    )
    return SceneToolCatalog(tools=tuple(tools))


def _prepare_single_scene(tmp_path: Path) -> PreparedSceneInputs:
    """准备单 scene 成功装配 fixture。

    :param tmp_path: pytest 临时目录。
    :returns: 装配结果。
    """

    _write_text(
        tmp_path / "prompts" / "base.md",
        "你是{{company}}财报分析员。",
    )
    _write_text(
        tmp_path / "prompts" / "detail.md",
        "分析{{company}}在{{fiscal_year}}年的收入。",
    )
    _write_json(
        tmp_path / "manifests" / "earnings.json",
        _manifest(
            "earnings",
            fragments=[
                _fragment("base", "base.md", 10),
                _fragment("detail", "detail.md", 20),
            ],
            context_slots=[
                _slot("company"),
                _slot("fiscal_year"),
            ],
            capability_tags=["earnings", "analysis"],
        ),
    )
    return prepare_scene(
        _request(
            tmp_path,
            "earnings",
            context_slot_values={
                "company": "Dayu Corp",
                "fiscal_year": "2026",
            },
        )
    )


def test_single_scene_assembly_outputs_stable_refs_and_digest(tmp_path: Path) -> None:
    """单 scene 装配输出稳定 system messages、fragment refs、source refs 与 digest。"""

    result = _prepare_single_scene(tmp_path)
    repeated = prepare_scene(
        _request(
            tmp_path,
            "earnings",
            context_slot_values={
                "company": "Dayu Corp",
                "fiscal_year": "2026",
            },
        )
    )

    assert result.system_messages == (
        "你是Dayu Corp财报分析员。",
        "分析Dayu Corp在2026年的收入。",
    )
    assert result.system_prompt == ("你是Dayu Corp财报分析员。\n\n分析Dayu Corp在2026年的收入。")
    assert tuple(ref.fragment_id for ref in result.fragment_refs) == ("base", "detail")
    assert result.fragment_refs[0].content_digest == "sha256:" + hashlib.sha256(
        "你是{{company}}财报分析员。".encode("utf-8")
    ).hexdigest()
    assert tuple(ref.relative_path for ref in result.fragment_refs) == (
        "base.md",
        "detail.md",
    )
    assert tuple(ref.source_kind for ref in result.source_refs) == (
        SceneSourceKind.MANIFEST,
        SceneSourceKind.FRAGMENT,
        SceneSourceKind.FRAGMENT,
        SceneSourceKind.ASSEMBLY_INPUT,
    )
    assert result.content_digest == repeated.content_digest
    assert result.content_digest.startswith("sha256:")
    assert result.capability_tags == ("earnings", "analysis")


def test_model_runner_option_hint_id_is_preserved(tmp_path: Path) -> None:
    """manifest model.runner_option_hint_id 应保留为 typed model hint。"""

    _write_json(
        tmp_path / "manifests" / "profiled.json",
        _manifest(
            "profiled",
            model={
                "default_model_id": "analyst-model",
                "runner_option_hint_id": "low-variance",
            },
        ),
    )

    result = prepare_scene(_request(tmp_path, "profiled"))

    assert result.model_hints is not None
    assert result.model_hints.default_model_id == "analyst-model"
    assert result.model_hints.runner_option_hint_id == "low-variance"


def test_default_non_upload_scenes_do_not_select_upload_tool() -> None:
    """默认非上传 scene 不得通过 broad fins tag 选中 upload tool。"""

    available_tools = _default_manifest_tool_catalog()
    for scene_id in _DEFAULT_NON_UPLOAD_SCENE_IDS:
        result = prepare_scene(
            ScenePrepareRequest(
                scene_id=scene_id,
                scene_manifest_root=_PACKAGE_MANIFEST_ROOT,
                prompt_asset_root=_PACKAGE_PROMPT_ROOT,
                context_slot_values={
                    "fins_default_subject": "测试财报主体",
                    "base_user": "scene-prepare-test",
                },
                available_tools=available_tools,
            )
        )
        selected = result.tool_selection.tool_names
        assert selected is not None
        assert _START_FINS_UPLOAD_TOOL_NAME not in selected
        assert _DEFAULT_FINS_NON_UPLOAD_TOOL_NAMES.issubset(selected)
        if scene_id in _DEFAULT_WEB_SCENE_IDS:
            assert _DEFAULT_WEB_TOOL_NAMES.issubset(selected)


def test_content_digest_changes_when_runner_option_hint_id_changes(
    tmp_path: Path,
) -> None:
    """只修改 model.runner_option_hint_id 时 content digest 必须变化。"""

    manifest_path = tmp_path / "manifests" / "digest_profile.json"
    _write_json(
        manifest_path,
        _manifest(
            "digest_profile",
            model={
                "default_model_id": "analyst-model",
                "runner_option_hint_id": "analytical",
            },
        ),
    )
    first = prepare_scene(_request(tmp_path, "digest_profile"))

    _write_json(
        manifest_path,
        _manifest(
            "digest_profile",
            model={
                "default_model_id": "analyst-model",
                "runner_option_hint_id": "creative",
            },
        ),
    )
    second = prepare_scene(_request(tmp_path, "digest_profile"))

    assert first.model_hints is not None
    assert second.model_hints is not None
    assert first.model_hints.runner_option_hint_id == "analytical"
    assert second.model_hints.runner_option_hint_id == "creative"
    assert first.content_digest != second.content_digest


def test_required_context_slot_missing_fails_fast(tmp_path: Path) -> None:
    """required context slot 缺失必须失败。"""

    _prepare_single_scene(tmp_path)

    with pytest.raises(ScenePrepareError, match="required context slot missing"):
        prepare_scene(
            _request(
                tmp_path,
                "earnings",
                context_slot_values={"company": "Dayu Corp"},
            )
        )


def test_unknown_placeholder_fails_fast(tmp_path: Path) -> None:
    """fragment 出现未声明 placeholder 必须失败。"""

    _write_text(tmp_path / "prompts" / "base.md", "未知{{unknown_slot}}")
    _write_json(
        tmp_path / "manifests" / "unknown.json",
        _manifest(
            "unknown",
            fragments=[_fragment("base", "base.md", 1)],
            context_slots=[_slot("company")],
        ),
    )

    with pytest.raises(ScenePrepareError, match="unknown placeholder"):
        prepare_scene(
            _request(
                tmp_path,
                "unknown",
                context_slot_values={"company": "Dayu Corp"},
            )
        )


def test_non_string_context_slot_value_fails_fast(tmp_path: Path) -> None:
    """外部错误传入非字符串 slot value 时必须失败。"""

    _prepare_single_scene(tmp_path)
    bad_values = cast(Mapping[str, str], {"company": "Dayu Corp", "fiscal_year": 2026})

    with pytest.raises(ScenePrepareError, match="must be string"):
        prepare_scene(
            _request(
                tmp_path,
                "earnings",
                context_slot_values=bad_values,
            )
        )


def test_literal_double_braces_without_placeholder_pattern_are_preserved(
    tmp_path: Path,
) -> None:
    """不构成完整 placeholder 的双花括号字面量必须保留。"""

    _write_text(tmp_path / "prompts" / "base.md", "代码示例：{{ company")
    _write_json(
        tmp_path / "manifests" / "literal.json",
        _manifest(
            "literal",
            fragments=[_fragment("base", "base.md", 1)],
            context_slots=[_slot("company")],
        ),
    )

    result = prepare_scene(
        _request(
            tmp_path,
            "literal",
            context_slot_values={"company": "Dayu Corp"},
        )
    )

    assert result.system_messages == ("代码示例：{{ company",)


def test_single_inheritance_merges_parent_first_and_child_overrides(
    tmp_path: Path,
) -> None:
    """单继承应父优先继承 slots，子追加 fragments，并覆盖 typed scene 字段。"""

    _write_text(tmp_path / "prompts" / "parent.md", "公司：{{company}}")
    _write_text(tmp_path / "prompts" / "child.md", "日期：{{filing_date}}")
    _write_json(
        tmp_path / "manifests" / "base_scene.json",
        _manifest(
            "base_scene",
            fragments=[_fragment("parent", "parent.md", 10)],
            context_slots=[_slot("company")],
            tool_selection={"mode": "all", "tool_names": [], "tool_tags_any": []},
            capability_tags=["base"],
        ),
    )
    _write_json(
        tmp_path / "manifests" / "child_scene.json",
        _manifest(
            "child_scene",
            extends=["base_scene"],
            model={"default_model_id": "child-model"},
            agent_policy={
                "max_iterations": 4,
                "fallback_mode": "raise_error",
            },
            tool_selection={
                "mode": "select",
                "tool_names": ["quote_metric"],
                "tool_tags_any": [],
            },
            fragments=[_fragment("child", "child.md", 20)],
            context_slots=[_slot("company"), _slot("filing_date")],
            capability_tags=["child"],
        ),
    )

    result = prepare_scene(
        _request(
            tmp_path,
            "child_scene",
            context_slot_values={
                "company": "Dayu Corp",
                "filing_date": "2026-05-21",
            },
            tools=(SceneToolInfo(name="quote_metric"),),
        )
    )

    assert result.system_messages == ("公司：Dayu Corp", "日期：2026-05-21")
    assert tuple(ref.fragment_id for ref in result.fragment_refs) == (
        "parent",
        "child",
    )
    assert result.model_hints is not None
    assert result.model_hints.default_model_id == "child-model"
    assert result.agent_policy_override is not None
    assert result.agent_policy_override.max_iterations == 4
    assert result.agent_policy_override.fallback_mode == "raise_error"
    assert result.tool_selection.tool_names == frozenset({"quote_metric"})
    assert result.capability_tags == ("base", "child")

    with pytest.raises(ScenePrepareError, match="required context slot missing: company"):
        prepare_scene(
            _request(
                tmp_path,
                "child_scene",
                context_slot_values={},
                tools=(SceneToolInfo(name="quote_metric"),),
            )
        )


def test_child_scene_inherits_parent_model_when_omitted(tmp_path: Path) -> None:
    """子 scene 未显式声明 model 时应继承父 scene model。"""

    _write_text(tmp_path / "prompts" / "parent.md", "父")
    _write_text(tmp_path / "prompts" / "child.md", "子")
    _write_json(
        tmp_path / "manifests" / "base_scene.json",
        _manifest(
            "base_scene",
            fragments=[_fragment("parent", "parent.md", 10)],
        ),
    )
    _write_json(
        tmp_path / "manifests" / "child_scene.json",
        _manifest(
            "child_scene",
            extends=["base_scene"],
            model_is_null=True,
            fragments=[_fragment("child", "child.md", 20)],
        ),
    )

    result = prepare_scene(_request(tmp_path, "child_scene"))

    assert result.model_hints is not None
    assert result.model_hints.default_model_id == "analyst-model"


def test_scene_without_model_outputs_no_model_hints(tmp_path: Path) -> None:
    """scene 未声明 model 时应输出空 model hints，由调用方映射 execution baseline。"""

    _write_json(
        tmp_path / "manifests" / "baseline_model.json",
        _manifest("baseline_model", model_is_null=True),
    )

    result = prepare_scene(_request(tmp_path, "baseline_model"))

    assert result.model_hints is None


def test_legacy_conversation_and_runtime_fields_fail_fast(tmp_path: Path) -> None:
    """旧 conversation 与 runtime 字段出现时必须按未知顶层字段失败。"""

    manifest = _manifest("legacy")
    manifest["conversation"] = {"mode": "ordinary"}
    manifest["runtime"] = {"runner_hint_id": "fast"}
    _write_json(tmp_path / "manifests" / "legacy.json", manifest)

    with pytest.raises(ScenePrepareError, match="unsupported fields"):
        prepare_scene(_request(tmp_path, "legacy"))


def test_legacy_model_field_names_fail_fast(tmp_path: Path) -> None:
    """旧 model.default_name 与 model.temperature_profile 字段必须失败。"""

    _write_json(
        tmp_path / "manifests" / "legacy_model.json",
        _manifest(
            "legacy_model",
            model={
                "default_name": "analyst-model",
                "temperature_profile": "audit",
            },
        ),
    )

    with pytest.raises(ScenePrepareError, match="unsupported fields"):
        prepare_scene(_request(tmp_path, "legacy_model"))


def test_agent_policy_override_outputs_typed_view(tmp_path: Path) -> None:
    """agent_policy override 应输出白名单内 typed view。"""

    _write_json(
        tmp_path / "manifests" / "agent_policy_scene.json",
        _manifest(
            "agent_policy_scene",
            agent_policy={
                "max_iterations": 6,
                "continuation_max_attempts": 1,
                "allow_tool_calls": False,
                "tool_execution_timeout_seconds": 12.5,
                "fallback_mode": "raise_error",
                "fallback_prompt": "请停止工具调用并直接回答。",
                "continuation_prompt": "继续完成上一段回答。",
                "max_consecutive_failed_tool_batches": 3,
            },
        ),
    )

    result = prepare_scene(_request(tmp_path, "agent_policy_scene"))

    assert result.agent_policy_override is not None
    override = result.agent_policy_override
    assert override.max_iterations == 6
    assert override.continuation_max_attempts == 1
    assert override.allow_tool_calls is False
    assert override.tool_execution_timeout_seconds == 12.5
    assert override.fallback_mode == "raise_error"
    assert override.fallback_prompt == "请停止工具调用并直接回答。"
    assert override.continuation_prompt == "继续完成上一段回答。"
    assert override.max_consecutive_failed_tool_batches == 3


def test_agent_policy_unknown_field_fails_fast(tmp_path: Path) -> None:
    """agent_policy 出现白名单外字段必须失败。"""

    _write_json(
        tmp_path / "manifests" / "bad_agent_policy.json",
        _manifest(
            "bad_agent_policy",
            agent_policy={
                "allow_tool_calls": True,
                "worker_backend": "local",
            },
        ),
    )

    with pytest.raises(ScenePrepareError, match="unsupported fields"):
        prepare_scene(_request(tmp_path, "bad_agent_policy"))


def test_agent_policy_fallback_mode_is_closed_enum(tmp_path: Path) -> None:
    """agent_policy fallback_mode 只允许 force_answer / raise_error。"""

    _write_json(
        tmp_path / "manifests" / "bad_fallback.json",
        _manifest(
            "bad_fallback",
            agent_policy={"fallback_mode": "finalize"},
        ),
    )

    with pytest.raises(ScenePrepareError, match="fallback_mode is unsupported"):
        prepare_scene(_request(tmp_path, "bad_fallback"))


def test_request_scene_id_invalid_format_raises_scene_prepare_error(
    tmp_path: Path,
) -> None:
    """request scene id 格式非法时必须抛 ScenePrepareError。"""

    with pytest.raises(
        ScenePrepareError,
        match="ScenePrepareRequest.scene_id must be ASCII scene identifier",
    ):
        _request(tmp_path, "bad/scene")


def test_manifest_scene_id_invalid_format_raises_scene_prepare_error(
    tmp_path: Path,
) -> None:
    """manifest scene 字段格式非法时必须抛 ScenePrepareError。"""

    _write_json(
        tmp_path / "manifests" / "bad_manifest.json",
        _manifest("bad/scene"),
    )

    with pytest.raises(
        ScenePrepareError,
        match=r"bad_manifest\.json\.scene must be ASCII scene identifier",
    ):
        prepare_scene(_request(tmp_path, "bad_manifest"))


def test_extends_parent_id_invalid_format_raises_scene_prepare_error(
    tmp_path: Path,
) -> None:
    """extends parent id 格式非法时必须抛 ScenePrepareError。"""

    _write_json(
        tmp_path / "manifests" / "child.json",
        _manifest("child", extends=["bad/parent"]),
    )

    with pytest.raises(
        ScenePrepareError,
        match=r"child\.json\.extends\[0\] must be ASCII scene identifier",
    ):
        prepare_scene(_request(tmp_path, "child"))


def test_multiple_inheritance_fails(tmp_path: Path) -> None:
    """extends 多父项必须失败。"""

    _write_json(
        tmp_path / "manifests" / "child.json",
        _manifest("child", extends=["left", "right"]),
    )

    with pytest.raises(ScenePrepareError, match="allows only one parent"):
        prepare_scene(_request(tmp_path, "child"))


def test_manifest_file_scene_id_mismatch_fails(tmp_path: Path) -> None:
    """manifest 文件名和内部 scene id 不一致必须失败。"""

    _write_json(
        tmp_path / "manifests" / "requested.json",
        _manifest("declared"),
    )

    with pytest.raises(ScenePrepareError, match="declares different scene"):
        prepare_scene(_request(tmp_path, "requested"))


def test_cycle_inheritance_fails(tmp_path: Path) -> None:
    """scene 继承循环必须失败。"""

    _write_json(
        tmp_path / "manifests" / "a.json",
        _manifest("a", extends=["b"]),
    )
    _write_json(
        tmp_path / "manifests" / "b.json",
        _manifest("b", extends=["a"]),
    )

    with pytest.raises(ScenePrepareError, match="cycle"):
        prepare_scene(_request(tmp_path, "a"))


def test_duplicate_fragment_id_and_order_fail(tmp_path: Path) -> None:
    """fragment id 与 order 重复都必须失败。"""

    _write_json(
        tmp_path / "manifests" / "dup_id.json",
        _manifest(
            "dup_id",
            fragments=[
                _fragment("same", "a.md", 1),
                _fragment("same", "b.md", 2),
            ],
        ),
    )
    with pytest.raises(ScenePrepareError, match="duplicate fragment id"):
        prepare_scene(_request(tmp_path, "dup_id"))

    _write_json(
        tmp_path / "manifests" / "dup_order.json",
        _manifest(
            "dup_order",
            fragments=[
                _fragment("a", "a.md", 1),
                _fragment("b", "b.md", 1),
            ],
        ),
    )
    with pytest.raises(ScenePrepareError, match="duplicate fragment order"):
        prepare_scene(_request(tmp_path, "dup_order"))


def test_fragment_path_escape_prompt_asset_root_fails(tmp_path: Path) -> None:
    """fragment 路径解析后逃逸 prompt_asset_root 必须失败。"""

    _write_json(
        tmp_path / "manifests" / "escape.json",
        _manifest(
            "escape",
            fragments=[_fragment("escape", "../outside.md", 1)],
        ),
    )

    with pytest.raises(ScenePrepareError, match="escapes root"):
        prepare_scene(_request(tmp_path, "escape"))


def test_fragment_symlink_escape_prompt_asset_root_fails(tmp_path: Path) -> None:
    """fragment 路径指向逃逸 root 的符号链接时必须失败。"""

    outside_root = tmp_path / "outside"
    _write_text(outside_root / "secret.md", "外部 fragment")
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir(parents=True, exist_ok=True)
    (prompt_root / "linked.md").symlink_to(outside_root / "secret.md")
    _write_json(
        tmp_path / "manifests" / "symlink_escape.json",
        _manifest(
            "symlink_escape",
            fragments=[_fragment("linked", "linked.md", 1)],
        ),
    )

    with pytest.raises(ScenePrepareError, match="escapes root"):
        prepare_scene(_request(tmp_path, "symlink_escape"))


def test_required_fragment_missing_fails_closed(tmp_path: Path) -> None:
    """required fragment 缺失时必须按 fail-closed 失败。"""

    _write_json(
        tmp_path / "manifests" / "missing_fragment.json",
        _manifest(
            "missing_fragment",
            fragments=[_fragment("missing", "missing.md", 1)],
        ),
    )

    with pytest.raises(ScenePrepareError, match="required fragment missing"):
        prepare_scene(_request(tmp_path, "missing_fragment"))


def test_optional_missing_fragment_is_skipped(tmp_path: Path) -> None:
    """optional fragment 缺失时应跳过且不进入 messages 与 fragment refs。"""

    _write_text(tmp_path / "prompts" / "base.md", "基础提示")
    _write_json(
        tmp_path / "manifests" / "optional_missing.json",
        _manifest(
            "optional_missing",
            fragments=[
                _fragment("base", "base.md", 1),
                _fragment("optional_note", "optional_note.md", 2, required=False),
            ],
        ),
    )

    result = prepare_scene(_request(tmp_path, "optional_missing"))

    assert result.system_messages == ("基础提示",)
    assert tuple(ref.fragment_id for ref in result.fragment_refs) == ("base",)


def test_inherited_duplicate_context_slot_keeps_parent_required_flag(
    tmp_path: Path,
) -> None:
    """父子重复声明同名 slot 时必须保留父声明的 required 语义。"""

    _write_text(tmp_path / "prompts" / "parent.md", "父提示")
    _write_text(tmp_path / "prompts" / "child.md", "子提示")
    _write_json(
        tmp_path / "manifests" / "parent_required.json",
        _manifest(
            "parent_required",
            fragments=[_fragment("parent", "parent.md", 1)],
            context_slots=[_slot("company", required=True)],
        ),
    )
    _write_json(
        tmp_path / "manifests" / "child_optional.json",
        _manifest(
            "child_optional",
            extends=["parent_required"],
            fragments=[_fragment("child", "child.md", 2)],
            context_slots=[_slot("company", required=False)],
        ),
    )

    with pytest.raises(ScenePrepareError, match="required context slot missing: company"):
        prepare_scene(_request(tmp_path, "child_optional"))
