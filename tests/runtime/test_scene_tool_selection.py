"""``ScenePrepare`` 工具选择语义测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dayu.contracts import JsonValue
from dayu.runtime.scene_prepare import (
    ScenePrepareError,
    ScenePrepareRequest,
    SceneToolCatalog,
    SceneToolInfo,
    prepare_scene,
)


def _write_json(path: Path, value: JsonValue) -> None:
    """写入 JSON fixture。

    :param path: 目标路径。
    :param value: JSON 值。
    :returns: ``None``。
    :raises OSError: 写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _manifest(scene_id: str, tool_selection: JsonValue) -> dict[str, JsonValue]:
    """构造只有工具选择差异的 scene manifest。

    :param scene_id: scene id。
    :param tool_selection: tool selection JSON object。
    :returns: manifest JSON object。
    """

    return {
        "schema_version": 1,
        "scene": scene_id,
        "version": "v1",
        "description": f"{scene_id} tool selection",
        "capability_tags": ["tool-selection"],
        "extends": [],
        "model": {"default_model_id": "analyst-model"},
        "tool_selection": tool_selection,
        "defaults": {"missing_required_fragment": "fail_closed"},
        "fragments": [],
        "context_slots": [],
    }


def _request(tmp_path: Path, scene_id: str) -> ScenePrepareRequest:
    """构造工具选择测试请求。

    :param tmp_path: pytest 临时目录。
    :param scene_id: scene id。
    :returns: ScenePrepare 请求。
    """

    return ScenePrepareRequest(
        scene_id=scene_id,
        scene_manifest_root=tmp_path / "manifests",
        prompt_asset_root=tmp_path / "prompts",
        context_slot_values={},
        available_tools=SceneToolCatalog(
            tools=(
                SceneToolInfo(name="lookup_filing", tags=frozenset({"filing", "read"})),
                SceneToolInfo(name="quote_metric", tags=frozenset({"metric"})),
                SceneToolInfo(name="news_search", tags=frozenset({"news", "read"})),
            )
        ),
    )


def test_tool_selection_all_maps_to_none(tmp_path: Path) -> None:
    """mode=all 应映射为 ``tool_names=None``。"""

    _write_json(
        tmp_path / "manifests" / "all_tools.json",
        _manifest(
            "all_tools",
            {"mode": "all", "tool_names": [], "tool_tags_any": []},
        ),
    )

    result = prepare_scene(_request(tmp_path, "all_tools"))

    assert result.tool_selection.tool_names is None


def test_tool_selection_none_maps_to_empty_set(tmp_path: Path) -> None:
    """mode=none 应映射为空集合。"""

    _write_json(
        tmp_path / "manifests" / "no_tools.json",
        _manifest(
            "no_tools",
            {"mode": "none", "tool_names": [], "tool_tags_any": []},
        ),
    )

    result = prepare_scene(_request(tmp_path, "no_tools"))

    assert result.tool_selection.tool_names == frozenset()


def test_tool_selection_select_explicit_names(tmp_path: Path) -> None:
    """mode=select 支持显式 tool_names。"""

    _write_json(
        tmp_path / "manifests" / "names.json",
        _manifest(
            "names",
            {
                "mode": "select",
                "tool_names": ["lookup_filing", "quote_metric"],
                "tool_tags_any": [],
            },
        ),
    )

    result = prepare_scene(_request(tmp_path, "names"))

    assert result.tool_selection.tool_names == frozenset(
        {"lookup_filing", "quote_metric"}
    )


def test_tool_selection_select_tags(tmp_path: Path) -> None:
    """mode=select 支持 tool_tags_any 任一标签命中。"""

    _write_json(
        tmp_path / "manifests" / "tags.json",
        _manifest(
            "tags",
            {
                "mode": "select",
                "tool_names": [],
                "tool_tags_any": ["read"],
            },
        ),
    )

    result = prepare_scene(_request(tmp_path, "tags"))

    assert result.tool_selection.tool_names == frozenset(
        {"lookup_filing", "news_search"}
    )


def test_tool_selection_select_names_and_tags_are_union(tmp_path: Path) -> None:
    """显式 tool_names 与 tag 命中结果必须取并集。"""

    _write_json(
        tmp_path / "manifests" / "union.json",
        _manifest(
            "union",
            {
                "mode": "select",
                "tool_names": ["quote_metric"],
                "tool_tags_any": ["read"],
            },
        ),
    )

    result = prepare_scene(_request(tmp_path, "union"))

    assert result.tool_selection.tool_names == frozenset(
        {"lookup_filing", "quote_metric", "news_search"}
    )


def test_tool_selection_unknown_tool_name_fails(tmp_path: Path) -> None:
    """未知 tool_names 必须失败。"""

    _write_json(
        tmp_path / "manifests" / "unknown_name.json",
        _manifest(
            "unknown_name",
            {
                "mode": "select",
                "tool_names": ["missing_tool"],
                "tool_tags_any": [],
            },
        ),
    )

    with pytest.raises(ScenePrepareError, match="unknown tool_names"):
        prepare_scene(_request(tmp_path, "unknown_name"))


def test_tool_selection_tag_without_match_fails_by_default(tmp_path: Path) -> None:
    """tag 无匹配时默认必须失败。"""

    _write_json(
        tmp_path / "manifests" / "missing_tag.json",
        _manifest(
            "missing_tag",
            {
                "mode": "select",
                "tool_names": [],
                "tool_tags_any": ["missing"],
            },
        ),
    )

    with pytest.raises(ScenePrepareError, match="matched no tools"):
        prepare_scene(_request(tmp_path, "missing_tag"))


def test_tool_selection_allow_empty_allows_empty_select(tmp_path: Path) -> None:
    """allow_empty=true 时允许空选择结果。"""

    _write_json(
        tmp_path / "manifests" / "allow_empty.json",
        _manifest(
            "allow_empty",
            {
                "mode": "select",
                "tool_names": [],
                "tool_tags_any": ["missing"],
                "allow_empty": True,
            },
        ),
    )

    result = prepare_scene(_request(tmp_path, "allow_empty"))

    assert result.tool_selection.tool_names == frozenset()
