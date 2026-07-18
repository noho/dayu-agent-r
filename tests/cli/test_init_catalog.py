"""``dayu.cli.init_catalog`` owner contract 测试。"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

import pytest

from dayu.cli.init_catalog import (
    INIT_MODEL_CHOICES,
    ORDINARY_MANIFEST_BASENAMES,
    PRODUCTION_RUNTIME_MANIFEST_BASENAMES,
    TEST_OWNED_MANUAL_SMOKE_MANIFEST_BASENAMES,
    THINKING_MANIFEST_BASENAMES,
    CustomOpenAIModelSettings,
    InitCatalogError,
    InitModelChoice,
    InitModelChoiceKind,
    InitModelSelection,
    OllamaModelSettings,
    apply_model_selection,
    find_init_model_choice,
    ollama_template_defaults,
    project_known_manifest_models,
    validate_init_catalog,
)
from dayu.contracts import JsonValue
from dayu.runtime.scene_prepare import (
    ScenePrepareRequest,
    SceneToolCatalog,
    SceneToolInfo,
    prepare_scene,
)

_MODELS_FILE: Final[str] = "models.json"
_MANIFEST_RELATIVE_PATH: Final[Path] = Path("prompts/manifests")
_PROMPT_RELATIVE_PATH: Final[Path] = Path("prompts")
_CUSTOM_ENDPOINT: Final[str] = "https://models.example.test/openai/v1"
_CUSTOM_MODEL_NAME: Final[str] = "research-model"
_CUSTOM_CONTEXT_WINDOW: Final[int] = 131_072


def _repo_root() -> Path:
    """返回仓库根目录。

    :returns: 当前测试仓库根路径。
    :raises Exception: 不主动抛出异常。
    """

    return Path(__file__).resolve().parents[2]


def _package_config_dir() -> Path:
    """返回只读 package 配置目录。

    :returns: ``dayu/config`` 路径。
    :raises Exception: 不主动抛出异常。
    """

    return _repo_root() / "dayu" / "config"


def _copy_package_config(tmp_path: Path) -> Path:
    """复制当前 package 配置供 mutation 测试使用。

    :param tmp_path: pytest 临时目录。
    :returns: 私有 staging config 目录。
    :raises OSError: 配置复制失败时抛出。
    """

    destination = tmp_path / "config"
    shutil.copytree(_package_config_dir(), destination)
    return destination


def _read_json_object(path: Path) -> Mapping[str, JsonValue]:
    """读取测试 JSON object。

    :param path: JSON 文件路径。
    :returns: string-keyed JSON object。
    :raises AssertionError: 顶层不是 mapping 时抛出。
    :raises OSError: 文件读取失败时抛出。
    """

    value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(value, Mapping)
    return value


def _write_json(path: Path, value: JsonValue) -> None:
    """写入测试 JSON 值。

    :param path: 目标路径。
    :param value: 严格 JSON 值。
    :returns: ``None``。
    :raises OSError: 写入失败时抛出。
    """

    path.write_text(f"{json.dumps(value, ensure_ascii=False, indent=2)}\n", encoding="utf-8")


def _models_map(config_dir: Path) -> dict[str, JsonValue]:
    """返回可修改的 raw models map。

    :param config_dir: staging config 目录。
    :returns: ``models.json.models`` 的浅复制。
    :raises AssertionError: 当前 fixture shape 非法时抛出。
    """

    root = _read_json_object(config_dir / _MODELS_FILE)
    models = root["models"]
    assert isinstance(models, Mapping)
    return dict(models)


def _replace_models_map(config_dir: Path, models: Mapping[str, JsonValue]) -> None:
    """替换测试 ``models.json.models`` map。

    :param config_dir: staging config 目录。
    :param models: 新 raw models map。
    :returns: ``None``。
    :raises OSError: 写入失败时抛出。
    """

    _write_json(config_dir / _MODELS_FILE, {"models": dict(models)})


def _static_selection(choice_id: str) -> InitModelSelection:
    """构造静态模型选择。

    :param choice_id: 15 项目录中的静态选择 id。
    :returns: 无动态设置的 typed selection。
    :raises InitCatalogError: id 不存在或属于动态选项时抛出。
    """

    choice = find_init_model_choice(choice_id)
    if choice.kind in (InitModelChoiceKind.OLLAMA, InitModelChoiceKind.CUSTOM_OPENAI):
        raise InitCatalogError("test helper requires a static choice")
    return InitModelSelection(choice=choice)


def _custom_selection() -> InitModelSelection:
    """构造合法 custom OpenAI-compatible 选择。

    :returns: 带完整动态设置的 typed selection。
    :raises InitCatalogError: 固定测试输入不符合动态 contract 时抛出。
    """

    return InitModelSelection(
        choice=find_init_model_choice("custom-openai"),
        dynamic_settings=CustomOpenAIModelSettings(
            model_name=_CUSTOM_MODEL_NAME,
            endpoint=_CUSTOM_ENDPOINT,
            context_window_tokens=_CUSTOM_CONTEXT_WINDOW,
        ),
    )


def _required_context_values(manifest: Mapping[str, JsonValue]) -> dict[str, str]:
    """从 manifest fixture 构造 current parser 所需 context values。

    :param manifest: scene manifest JSON object。
    :returns: 仅包含 required slot 的测试字符串 map。
    :raises AssertionError: fixture context slot shape 非法时抛出。
    """

    raw_slots = manifest["context_slots"]
    assert isinstance(raw_slots, list)
    values: dict[str, str] = {}
    for raw_slot in raw_slots:
        assert isinstance(raw_slot, Mapping)
        name = raw_slot["name"]
        assert isinstance(name, str)
        required = raw_slot.get("required", True)
        assert isinstance(required, bool)
        if required:
            values[name] = ""
    return values


def _production_test_catalog() -> SceneToolCatalog:
    """构造覆盖 production manifests tag selection 的测试目录。

    :returns: 不含 ``manual-smoke`` tag 的显式测试工具目录。
    :raises ValueError: 固定测试工具定义非法时抛出。
    """

    return SceneToolCatalog(
        tools=(
            SceneToolInfo(
                name="production-catalog-fixture",
                tags=frozenset(
                    {
                        "fins-read",
                        "fins-download",
                        "fins-preprocess",
                        "web",
                        "utils",
                    }
                ),
            ),
        )
    )


def _manual_smoke_test_catalog() -> SceneToolCatalog:
    """构造仅归测试所有的 ``manual-smoke`` 显式目录。

    :returns: 单工具测试目录。
    :raises ValueError: 固定测试工具定义非法时抛出。
    """

    return SceneToolCatalog(
        tools=(
            SceneToolInfo(
                name="manual-smoke-catalog-fixture",
                tags=frozenset({"manual-smoke"}),
            ),
        )
    )


def test_choice_catalog_order_and_exact_mapping() -> None:
    """15 项展示顺序与 ordinary/thinking/env 映射必须稳定。

    :returns: None。
    :raises AssertionError: 目录顺序、字段映射或选择 id 唯一性不符合 contract 时抛出。
    """

    expected = (
        ("Mimo Token Plan", "mimo-v2.5-pro-plan", "mimo-v2.5-pro-thinking-plan", "MIMO_PLAN_API_KEY"),
        ("Mimo SG", "mimo-v2.5-pro-plan-sg", "mimo-v2.5-pro-thinking-plan-sg", "MIMO_PLAN_SG_API_KEY"),
        ("Mimo Pro", "mimo-v2.5-pro", "mimo-v2.5-pro-thinking", "MIMO_API_KEY"),
        ("DeepSeek Pro", "deepseek-v4-pro", "deepseek-v4-pro-thinking", "DEEPSEEK_API_KEY"),
        ("DeepSeek Flash", "deepseek-v4-flash", "deepseek-v4-flash-thinking", "DEEPSEEK_API_KEY"),
        ("OpenAI", "gpt-5.4", "gpt-5.4-thinking", "OPENAI_API_KEY"),
        ("Anthropic", "claude-sonnet-4-6", "claude-sonnet-4-6-thinking", "ANTHROPIC_API_KEY"),
        ("Gemini 2.5 Flash", "gemini-2.5-flash", "gemini-2.5-flash-thinking", "GEMINI_API_KEY"),
        ("Gemini 2.5 Pro", "gemini-2.5-pro", "gemini-2.5-pro-thinking", "GEMINI_API_KEY"),
        (
            "Gemini 2.5 Flash-Lite",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash-lite-thinking",
            "GEMINI_API_KEY",
        ),
        (
            "Gemini 3.1 Pro Preview",
            "gemini-3.1-pro-preview",
            "gemini-3.1-pro-preview-thinking",
            "GEMINI_API_KEY",
        ),
        (
            "Gemini 3.1 Flash-Lite Preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-3.1-flash-lite-preview-thinking",
            "GEMINI_API_KEY",
        ),
        ("Qwen Plus", "qwen-plus", "qwen-plus-thinking", "QWEN_API_KEY"),
        ("Ollama", "ollama", "ollama", None),
        ("Custom OpenAI-compatible", "custom-openai", "custom-openai", "CUSTOM_OPENAI_API_KEY"),
    )

    assert tuple(
        (
            choice.display_name,
            choice.ordinary_model_id,
            choice.thinking_model_id,
            choice.required_secret_env_name,
        )
        for choice in INIT_MODEL_CHOICES
    ) == expected
    assert len({choice.choice_id for choice in INIT_MODEL_CHOICES}) == 15


def test_current_package_catalog_uses_resolved_models_and_ollama_template() -> None:
    """当前 package 的 13 pair 与 Ollama template 应通过真实 loader。

    :returns: None。
    :raises AssertionError: resolved model 数量或 Ollama 默认值不符合 contract 时抛出。
    :raises InitCatalogError: 当前 package catalog 或 manifest 集合校验失败时传播。
    :raises OSError: package 配置文件无法读取时传播。
    """

    config_dir = _package_config_dir()
    models = validate_init_catalog(config_dir, config_dir / _MANIFEST_RELATIVE_PATH)
    defaults = ollama_template_defaults(models)

    assert len(models.models) == 27
    assert defaults.endpoint == "http://localhost:11434/v1/chat/completions"
    assert defaults.context_window_tokens == 262_144


def test_raw_thinking_child_with_only_extends_uses_current_resolver(tmp_path: Path) -> None:
    """thinking child 只写 extends 时必须按 resolved provider/ref 成功。

    :param tmp_path: pytest 提供的临时 staging 根目录。
    :returns: None。
    :raises AssertionError: resolved provider 或 API key ref 不符合继承 contract 时抛出。
    :raises InitCatalogError: 真实 catalog resolver 拒绝合法 extends 配置时传播。
    :raises OSError: package 配置复制或测试 JSON 写入失败时传播。
    """

    config_dir = _copy_package_config(tmp_path)
    models = _models_map(config_dir)
    models["mimo-v2.5-pro-thinking-plan"] = {"extends": "mimo-v2.5-pro-plan"}
    _replace_models_map(config_dir, models)

    resolved = validate_init_catalog(config_dir, config_dir / _MANIFEST_RELATIVE_PATH)

    child = resolved.models["mimo-v2.5-pro-thinking-plan"]
    assert child.provider == "mimo"
    assert child.api_key_ref == "MIMO_PLAN_API_KEY"


@pytest.mark.parametrize("mismatch_field", ["missing", "provider", "api_key_ref"])
def test_static_pair_missing_or_resolved_mismatch_fails_closed(tmp_path: Path, mismatch_field: str) -> None:
    """静态 pair 的缺失、provider 或 API ref mismatch 均必须拒绝。

    :param tmp_path: pytest 提供的临时 staging 根目录。
    :param mismatch_field: 要删除或改写的静态模型字段场景。
    :returns: None。
    :raises AssertionError: fixture shape 非法或被测边界未按预期 fail closed 时抛出。
    :raises OSError: package 配置复制或测试 JSON 写入失败时传播。
    """

    config_dir = _copy_package_config(tmp_path)
    models = _models_map(config_dir)
    child_id = "mimo-v2.5-pro-thinking-plan"
    if mismatch_field == "missing":
        del models[child_id]
    else:
        raw_child = models[child_id]
        assert isinstance(raw_child, Mapping)
        changed_child: dict[str, JsonValue] = dict(raw_child)
        changed_child[mismatch_field] = "unexpected"
        models[child_id] = changed_child
    _replace_models_map(config_dir, models)

    with pytest.raises(InitCatalogError, match="mimo-token-plan"):
        validate_init_catalog(config_dir, config_dir / _MANIFEST_RELATIVE_PATH)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [("provider", "unexpected"), ("api_key_ref", "OPENAI_API_KEY")],
)
def test_ollama_template_provider_and_secret_ref_fail_closed(
    tmp_path: Path,
    field_name: str,
    field_value: str,
) -> None:
    """Ollama template 必须精确保持 provider=ollama/api_key_ref=null。

    :param tmp_path: pytest 提供的临时 staging 根目录。
    :param field_name: 要破坏的 Ollama template 字段名。
    :param field_value: 写入目标字段的非法测试值。
    :returns: None。
    :raises AssertionError: fixture shape 非法或 template 漂移未被拒绝时抛出。
    :raises OSError: package 配置复制或测试 JSON 写入失败时传播。
    """

    config_dir = _copy_package_config(tmp_path)
    models = _models_map(config_dir)
    raw_ollama = models["ollama"]
    assert isinstance(raw_ollama, Mapping)
    changed_ollama: dict[str, JsonValue] = dict(raw_ollama)
    changed_ollama[field_name] = field_value
    models["ollama"] = changed_ollama
    _replace_models_map(config_dir, models)

    with pytest.raises(InitCatalogError, match="Ollama template"):
        validate_init_catalog(config_dir, config_dir / _MANIFEST_RELATIVE_PATH)


def test_static_validation_does_not_require_package_custom_record() -> None:
    """package 缺少 custom-openai 是预期事实，不得成为静态校验错误。

    :returns: None。
    :raises AssertionError: package fixture 意外包含 custom record 时抛出。
    :raises InitCatalogError: 静态校验错误要求 package custom record 时传播。
    :raises OSError: package models 或 manifest 文件无法读取时传播。
    """

    config_dir = _package_config_dir()
    raw_models = _models_map(config_dir)
    assert "custom-openai" not in raw_models

    validate_init_catalog(config_dir, config_dir / _MANIFEST_RELATIVE_PATH)


@pytest.mark.parametrize("manifest_change", ["missing", "extra"])
def test_package_manifest_set_must_equal_exact_known_sixteen(tmp_path: Path, manifest_change: str) -> None:
    """package known manifest 缺失或多余都必须 fail closed。

    :param tmp_path: pytest 提供的临时 staging 根目录。
    :param manifest_change: 要构造的 manifest 缺失或多余场景。
    :returns: None。
    :raises AssertionError: manifest 集合漂移未被被测边界拒绝时抛出。
    :raises OSError: package 配置复制、删除或写入 manifest 失败时传播。
    """

    config_dir = _copy_package_config(tmp_path)
    manifest_dir = config_dir / _MANIFEST_RELATIVE_PATH
    if manifest_change == "missing":
        (manifest_dir / "audit.json").unlink()
    else:
        (manifest_dir / "unexpected.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(InitCatalogError, match="package manifest set mismatch"):
        validate_init_catalog(config_dir, manifest_dir)


def test_ollama_record_copies_template_and_replaces_only_explicit_fields(tmp_path: Path) -> None:
    """Ollama 动态记录必须复制 template 且只换 model/endpoint/context。

    :param tmp_path: pytest 提供的临时 staging 根目录。
    :returns: None。
    :raises AssertionError: 动态记录改写了非显式字段或 resolved 结果不一致时抛出。
    :raises InitCatalogError: 合法 Ollama selection 应用或重载校验失败时传播。
    :raises OSError: package 配置复制或 staging models 读写失败时传播。
    """

    config_dir = _copy_package_config(tmp_path)
    before_models = _models_map(config_dir)
    before_ollama = before_models["ollama"]
    assert isinstance(before_ollama, Mapping)
    settings = OllamaModelSettings(
        model_name="qwen-local:latest",
        endpoint="http://127.0.0.1:11434/v1/chat/completions",
        context_window_tokens=524_288,
    )
    selection = InitModelSelection(
        choice=find_init_model_choice("ollama"),
        dynamic_settings=settings,
    )

    resolved = apply_model_selection(config_dir, selection)
    after_ollama = _models_map(config_dir)["ollama"]
    assert isinstance(after_ollama, Mapping)
    expected: dict[str, JsonValue] = dict(before_ollama)
    expected.update(
        {
            "model": settings.model_name,
            "endpoint": settings.endpoint,
            "context_window_tokens": settings.context_window_tokens,
        }
    )

    assert after_ollama == expected
    assert resolved.models["ollama"].model == settings.model_name
    assert resolved.models["ollama"].api_key_ref is None


def test_custom_record_is_complete_current_schema_with_exact_eight_hints(tmp_path: Path) -> None:
    """Custom record 必须由真实 loader 读取并精确承诺八项 runtime hints。

    :param tmp_path: pytest 提供的临时 staging 根目录。
    :returns: None。
    :raises AssertionError: custom record 字段、capability 或八项 hint 不符合 contract 时抛出。
    :raises InitCatalogError: 合法 custom selection 应用或真实 loader 重载失败时传播。
    :raises OSError: package 配置复制或 staging models 读写失败时传播。
    """

    config_dir = _copy_package_config(tmp_path)
    selection = _custom_selection()

    resolved = apply_model_selection(config_dir, selection)
    raw_custom = _models_map(config_dir)["custom-openai"]
    assert isinstance(raw_custom, Mapping)
    custom = resolved.models["custom-openai"]
    hints = custom.runtime_hints.runner_option_hints

    assert custom.provider == "custom-openai"
    assert custom.model == _CUSTOM_MODEL_NAME
    assert custom.endpoint == _CUSTOM_ENDPOINT
    assert custom.api_key_ref == "CUSTOM_OPENAI_API_KEY"
    assert custom.headers == {
        "Authorization": "Bearer {{CUSTOM_OPENAI_API_KEY}}",
        "Content-Type": "application/json",
    }
    assert custom.supports_tool_calling is True
    assert custom.supports_stream is True
    assert custom.supports_stream_usage is True
    assert custom.default_timeout_seconds == 3600.0
    assert custom.max_retries == 3
    assert custom.sse_idle_timeout_seconds == 120.0
    assert custom.sse_heartbeat_seconds == 10.0
    assert custom.provider_request_extension is None
    assert custom.context_window_tokens == _CUSTOM_CONTEXT_WINDOW
    assert {
        hint_id: (hint.temperature, hint.top_p, hint.stream)
        for hint_id, hint in hints.items()
    } == {
        "write": (1.0, 1.0, True),
        "overview": (1.0, 1.0, True),
        "audit": (0.8, 1.0, True),
        "decision": (1.0, 1.0, True),
        "interactive": (1.0, 1.0, True),
        "prompt": (1.0, 1.0, True),
        "infer": (0.5, 1.0, True),
        "conversation_compaction": (0.4, 1.0, False),
    }
    assert "extends" not in raw_custom
    assert "default_name" not in raw_custom
    assert "_init_model_role" not in raw_custom


@pytest.mark.parametrize(
    "endpoint",
    ["", " endpoint", "https://bad host/path", "ftp://models.example.test/v1", "https:///missing-host", "https://x\n/v1"],
)
def test_dynamic_endpoint_boundary_rejects_invalid_values(endpoint: str) -> None:
    """动态 endpoint 的空白、控制字符与非完整 HTTP(S) URL 必须拒绝。

    :param endpoint: 应在 mutation 前被拒绝的动态 endpoint。
    :returns: None。
    :raises AssertionError: 非法 endpoint 未触发预期校验失败时抛出。
    """

    with pytest.raises(InitCatalogError, match="endpoint"):
        CustomOpenAIModelSettings(
            model_name=_CUSTOM_MODEL_NAME,
            endpoint=endpoint,
            context_window_tokens=_CUSTOM_CONTEXT_WINDOW,
        )


@pytest.mark.parametrize("model_name", ["", "   ", " model", "model\tname"])
def test_dynamic_model_name_boundary_rejects_blank_or_control_text(model_name: str) -> None:
    """动态模型名的空白、外围空格与控制字符必须在 mutation 前拒绝。

    :param model_name: 应在 mutation 前被拒绝的动态模型名。
    :returns: None。
    :raises AssertionError: 非法模型名未触发预期校验失败时抛出。
    """

    with pytest.raises(InitCatalogError, match="model name"):
        OllamaModelSettings(
            model_name=model_name,
            endpoint="http://localhost:11434/v1/chat/completions",
            context_window_tokens=1,
        )


@pytest.mark.parametrize("context_window", [0, -1, cast(int, True)])
def test_dynamic_context_window_rejects_non_positive_and_bool(context_window: int) -> None:
    """动态 context window 必须是大于零且非 bool 的整数。

    :param context_window: 应被拒绝的非正整数或 bool 测试值。
    :returns: None。
    :raises AssertionError: 非法 context window 未触发预期校验失败时抛出。
    """

    with pytest.raises(InitCatalogError, match="positive integer"):
        OllamaModelSettings(
            model_name="local-model",
            endpoint="http://localhost:11434/v1/chat/completions",
            context_window_tokens=context_window,
        )


def test_selection_rejects_static_dynamic_and_dynamic_kind_mismatch() -> None:
    """Typed selection 必须拒绝静态额外设置和两类 dynamic settings 互换。

    :returns: None。
    :raises AssertionError: 非法 selection、未知 id 或伪造 choice 未被拒绝时抛出。
    """

    custom_settings = CustomOpenAIModelSettings(
        model_name=_CUSTOM_MODEL_NAME,
        endpoint=_CUSTOM_ENDPOINT,
        context_window_tokens=_CUSTOM_CONTEXT_WINDOW,
    )

    with pytest.raises(InitCatalogError, match="static model choice"):
        InitModelSelection(choice=find_init_model_choice("openai"), dynamic_settings=custom_settings)
    with pytest.raises(InitCatalogError, match="OllamaModelSettings"):
        InitModelSelection(choice=find_init_model_choice("ollama"), dynamic_settings=custom_settings)
    with pytest.raises(InitCatalogError, match="unknown init model choice"):
        find_init_model_choice("unknown")

    forged_choice = InitModelChoice(
        choice_id="forged",
        display_name="Forged",
        ordinary_model_id="gpt-5.4",
        thinking_model_id="gpt-5.4-thinking",
        required_secret_env_name="OPENAI_API_KEY",
        kind=InitModelChoiceKind.OPENAI,
    )
    with pytest.raises(InitCatalogError, match="INIT_MODEL_CHOICES"):
        InitModelSelection(choice=forged_choice)


def test_static_selection_does_not_rewrite_models_file(tmp_path: Path) -> None:
    """静态选择只消费 resolved pair，不得重写 staging models.json。

    :param tmp_path: pytest 提供的临时 staging 根目录。
    :returns: None。
    :raises AssertionError: models 文件发生改写或 resolved provider 不符合 contract 时抛出。
    :raises InitCatalogError: 合法静态 selection 应用或重载校验失败时传播。
    :raises OSError: package 配置复制或 models 文件读取失败时传播。
    """

    config_dir = _copy_package_config(tmp_path)
    models_path = config_dir / _MODELS_FILE
    before = models_path.read_bytes()

    resolved = apply_model_selection(config_dir, _static_selection("openai"))

    assert models_path.read_bytes() == before
    assert resolved.models["gpt-5.4"].provider == "openai"


def test_projection_changes_only_default_model_id_and_current_parser_reads_all_sixteen(tmp_path: Path) -> None:
    """16 个 manifest 只改模型 id，用户文件逐字节保留，并由 current parser 读取。

    :param tmp_path: pytest 提供的临时 staging 根目录。
    :returns: None。
    :raises AssertionError: projection、用户文件保留或 13/3 manifest 边界不符合 contract 时抛出。
    :raises InitCatalogError: known manifest projection 或 selection 校验失败时传播。
    :raises OSError: package 配置复制或 manifest 文件读写失败时传播。
    :raises ValueError: current scene parser 无法装配投影后的合法 manifest 时传播。
    """

    config_dir = _copy_package_config(tmp_path)
    prompt_root = config_dir / _PROMPT_RELATIVE_PATH
    manifest_dir = config_dir / _MANIFEST_RELATIVE_PATH
    known_names = ORDINARY_MANIFEST_BASENAMES | THINKING_MANIFEST_BASENAMES
    before = {
        basename: _read_json_object(manifest_dir / f"{basename}.json")
        for basename in known_names
    }
    user_manifest = manifest_dir / "user-owned.json"
    user_bytes = b'{"user-owned": true, "format": "unchanged"}\n'
    user_manifest.write_bytes(user_bytes)
    selection = _custom_selection()

    changed_paths = project_known_manifest_models(manifest_dir, selection)

    assert {path.stem for path in changed_paths} == known_names
    assert user_manifest.read_bytes() == user_bytes
    production_catalog = _production_test_catalog()
    manual_catalog = _manual_smoke_test_catalog()
    for basename in known_names:
        before_manifest = before[basename]
        before_model = before_manifest["model"]
        assert isinstance(before_model, Mapping)
        target_model_id = (
            selection.choice.ordinary_model_id
            if basename in ORDINARY_MANIFEST_BASENAMES
            else selection.choice.thinking_model_id
        )
        expected_model: dict[str, JsonValue] = dict(before_model)
        expected_model["default_model_id"] = target_model_id
        expected_manifest: dict[str, JsonValue] = dict(before_manifest)
        expected_manifest["model"] = expected_model
        after_manifest = _read_json_object(manifest_dir / f"{basename}.json")
        assert after_manifest == expected_manifest

        available_tools = (
            manual_catalog
            if basename in TEST_OWNED_MANUAL_SMOKE_MANIFEST_BASENAMES
            else production_catalog
        )
        prepared = prepare_scene(
            ScenePrepareRequest(
                scene_id=basename,
                scene_manifest_root=manifest_dir,
                prompt_asset_root=prompt_root,
                context_slot_values=_required_context_values(after_manifest),
                available_tools=available_tools,
            )
        )
        assert prepared.model_hints is not None
        assert prepared.model_hints.default_model_id == target_model_id

    assert len(PRODUCTION_RUNTIME_MANIFEST_BASENAMES) == 13
    assert len(TEST_OWNED_MANUAL_SMOKE_MANIFEST_BASENAMES) == 3
    assert not (PRODUCTION_RUNTIME_MANIFEST_BASENAMES & TEST_OWNED_MANUAL_SMOKE_MANIFEST_BASENAMES)


@pytest.mark.parametrize("failure_kind", ["missing", "invalid-model"])
def test_projection_validates_all_known_files_before_any_write(tmp_path: Path, failure_kind: str) -> None:
    """任一 known manifest 缺失或 model 非法时不得部分改写其它文件。

    :param tmp_path: pytest 提供的临时 staging 根目录。
    :param failure_kind: 要构造的 known manifest 缺失或非法 model 场景。
    :returns: None。
    :raises AssertionError: 预校验未拒绝故障或其它 manifest 被部分改写时抛出。
    :raises OSError: package 配置复制或 fixture 文件读写失败时传播。
    """

    config_dir = _copy_package_config(tmp_path)
    manifest_dir = config_dir / _MANIFEST_RELATIVE_PATH
    audit_path = manifest_dir / "audit.json"
    overview_path = manifest_dir / "overview.json"
    audit_before = audit_path.read_bytes()
    if failure_kind == "missing":
        overview_path.unlink()
    else:
        _write_json(overview_path, {"model": {"runner_option_hint_id": "overview"}})

    with pytest.raises((InitCatalogError, OSError)):
        project_known_manifest_models(manifest_dir, _custom_selection())

    assert audit_path.read_bytes() == audit_before
