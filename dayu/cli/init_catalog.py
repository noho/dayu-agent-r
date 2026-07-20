"""``dayu-cli init`` 的模型选择与 manifest 投影 owner。

本模块只拥有初始化流程可展示的模型组合、动态模型记录构造规则，以及
已知 scene manifest 的普通/思考模型角色。当前配置 schema 的解析与继承
仍由 :class:`dayu.runtime.config_loader.ConfigLoader` 唯一负责。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeAlias, cast
from urllib.parse import urlsplit

from dayu.contracts import JsonValue
from dayu.runtime.config_loader import ConfigLoader, ModelConfig, ModelsConfig

_EXPECTED_CHOICE_COUNT: Final[int] = 15
_MODELS_FILE_NAME: Final[str] = "models.json"
_MODELS_FIELD: Final[str] = "models"
_MODEL_FIELD: Final[str] = "model"
_DEFAULT_MODEL_ID_FIELD: Final[str] = "default_model_id"
_JSON_SUFFIX: Final[str] = ".json"
_CUSTOM_MODEL_ID: Final[str] = "custom-openai"
_OLLAMA_MODEL_ID: Final[str] = "ollama"
_CUSTOM_API_KEY_REF: Final[str] = "CUSTOM_OPENAI_API_KEY"

JsonObject: TypeAlias = Mapping[str, JsonValue]
"""JSON object 的只读映射类型。"""


class InitCatalogError(ValueError):
    """初始化模型目录、动态记录或 manifest 投影不符合 contract 时抛出的错误。"""


class InitModelChoiceKind(StrEnum):
    """初始化模型组合所属 provider 类别。"""

    MIMO = "mimo"
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    QWEN = "qwen"
    OLLAMA = "ollama"
    CUSTOM_OPENAI = "custom-openai"


@dataclass(frozen=True, slots=True)
class InitModelChoice:
    """单个可展示的初始化模型组合。

    :param choice_id: 初始化流程内部稳定选择 id。
    :param display_name: 面向用户的展示名。
    :param ordinary_model_id: 普通 scene 使用的模型目录 id。
    :param thinking_model_id: 思考 scene 使用的模型目录 id。
    :param required_secret_env_name: 该组合需要的 secret 环境变量名。
    :param kind: provider 类别，同时承诺 resolved model 的 provider。
    """

    choice_id: str
    display_name: str
    ordinary_model_id: str
    thinking_model_id: str
    required_secret_env_name: str | None
    kind: InitModelChoiceKind

    def __post_init__(self) -> None:
        """校验选择记录的最小形态。

        :returns: ``None``。
        :raises ValueError: 任一必需文本为空，或 Ollama 错误声明 secret 时抛出。
        """

        for field_name, value in (
            ("choice_id", self.choice_id),
            ("display_name", self.display_name),
            ("ordinary_model_id", self.ordinary_model_id),
            ("thinking_model_id", self.thinking_model_id),
        ):
            if not value.strip():
                raise ValueError(f"InitModelChoice.{field_name} must be non-empty")
        if self.required_secret_env_name is not None and not self.required_secret_env_name.strip():
            raise ValueError("InitModelChoice.required_secret_env_name must be non-empty or None")
        if self.kind is InitModelChoiceKind.OLLAMA and self.required_secret_env_name is not None:
            raise ValueError("Ollama choice must not require a secret environment variable")

    @property
    def expected_provider(self) -> str:
        """返回 resolved model 必须匹配的 provider。

        :returns: provider 字符串。
        :raises Exception: 不主动抛出异常。
        """

        return self.kind.value


INIT_MODEL_CHOICES: Final[tuple[InitModelChoice, ...]] = (
    InitModelChoice(
        choice_id="mimo-token-plan",
        display_name="Mimo Token Plan",
        ordinary_model_id="mimo-v2.5-pro-plan",
        thinking_model_id="mimo-v2.5-pro-thinking-plan",
        required_secret_env_name="MIMO_PLAN_API_KEY",
        kind=InitModelChoiceKind.MIMO,
    ),
    InitModelChoice(
        choice_id="mimo-sg",
        display_name="Mimo SG",
        ordinary_model_id="mimo-v2.5-pro-plan-sg",
        thinking_model_id="mimo-v2.5-pro-thinking-plan-sg",
        required_secret_env_name="MIMO_PLAN_SG_API_KEY",
        kind=InitModelChoiceKind.MIMO,
    ),
    InitModelChoice(
        choice_id="mimo-pro",
        display_name="Mimo Pro",
        ordinary_model_id="mimo-v2.5-pro",
        thinking_model_id="mimo-v2.5-pro-thinking",
        required_secret_env_name="MIMO_API_KEY",
        kind=InitModelChoiceKind.MIMO,
    ),
    InitModelChoice(
        choice_id="deepseek-pro",
        display_name="DeepSeek Pro",
        ordinary_model_id="deepseek-v4-pro",
        thinking_model_id="deepseek-v4-pro-thinking",
        required_secret_env_name="DEEPSEEK_API_KEY",
        kind=InitModelChoiceKind.DEEPSEEK,
    ),
    InitModelChoice(
        choice_id="deepseek-flash",
        display_name="DeepSeek Flash",
        ordinary_model_id="deepseek-v4-flash",
        thinking_model_id="deepseek-v4-flash-thinking",
        required_secret_env_name="DEEPSEEK_API_KEY",
        kind=InitModelChoiceKind.DEEPSEEK,
    ),
    InitModelChoice(
        choice_id="openai",
        display_name="OpenAI",
        ordinary_model_id="gpt-5.4",
        thinking_model_id="gpt-5.4-thinking",
        required_secret_env_name="OPENAI_API_KEY",
        kind=InitModelChoiceKind.OPENAI,
    ),
    InitModelChoice(
        choice_id="anthropic",
        display_name="Anthropic",
        ordinary_model_id="claude-sonnet-4-6",
        thinking_model_id="claude-sonnet-4-6-thinking",
        required_secret_env_name="ANTHROPIC_API_KEY",
        kind=InitModelChoiceKind.ANTHROPIC,
    ),
    InitModelChoice(
        choice_id="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        ordinary_model_id="gemini-2.5-flash",
        thinking_model_id="gemini-2.5-flash-thinking",
        required_secret_env_name="GEMINI_API_KEY",
        kind=InitModelChoiceKind.GEMINI,
    ),
    InitModelChoice(
        choice_id="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        ordinary_model_id="gemini-2.5-pro",
        thinking_model_id="gemini-2.5-pro-thinking",
        required_secret_env_name="GEMINI_API_KEY",
        kind=InitModelChoiceKind.GEMINI,
    ),
    InitModelChoice(
        choice_id="gemini-2.5-flash-lite",
        display_name="Gemini 2.5 Flash-Lite",
        ordinary_model_id="gemini-2.5-flash-lite",
        thinking_model_id="gemini-2.5-flash-lite-thinking",
        required_secret_env_name="GEMINI_API_KEY",
        kind=InitModelChoiceKind.GEMINI,
    ),
    InitModelChoice(
        choice_id="gemini-3.1-pro-preview",
        display_name="Gemini 3.1 Pro Preview",
        ordinary_model_id="gemini-3.1-pro-preview",
        thinking_model_id="gemini-3.1-pro-preview-thinking",
        required_secret_env_name="GEMINI_API_KEY",
        kind=InitModelChoiceKind.GEMINI,
    ),
    InitModelChoice(
        choice_id="gemini-3.1-flash-lite-preview",
        display_name="Gemini 3.1 Flash-Lite Preview",
        ordinary_model_id="gemini-3.1-flash-lite-preview",
        thinking_model_id="gemini-3.1-flash-lite-preview-thinking",
        required_secret_env_name="GEMINI_API_KEY",
        kind=InitModelChoiceKind.GEMINI,
    ),
    InitModelChoice(
        choice_id="qwen-plus",
        display_name="Qwen Plus",
        ordinary_model_id="qwen-plus",
        thinking_model_id="qwen-plus-thinking",
        required_secret_env_name="QWEN_API_KEY",
        kind=InitModelChoiceKind.QWEN,
    ),
    InitModelChoice(
        choice_id="ollama",
        display_name="Ollama",
        ordinary_model_id=_OLLAMA_MODEL_ID,
        thinking_model_id=_OLLAMA_MODEL_ID,
        required_secret_env_name=None,
        kind=InitModelChoiceKind.OLLAMA,
    ),
    InitModelChoice(
        choice_id="custom-openai",
        display_name="Custom OpenAI-compatible",
        ordinary_model_id=_CUSTOM_MODEL_ID,
        thinking_model_id=_CUSTOM_MODEL_ID,
        required_secret_env_name=_CUSTOM_API_KEY_REF,
        kind=InitModelChoiceKind.CUSTOM_OPENAI,
    ),
)

ORDINARY_MANIFEST_BASENAMES: Final[frozenset[str]] = frozenset(
    {
        "conversation_compaction",
        "fix",
        "overview",
        "regenerate",
        "repair",
        "smoke_host_public_conversation_memory",
        "smoke_host_public_conversation_memory_scenarios",
        "write",
    }
)
"""普通模型角色的 8 个已知 manifest basename。"""

THINKING_MANIFEST_BASENAMES: Final[frozenset[str]] = frozenset(
    {
        "audit",
        "confirm",
        "decision",
        "infer",
        "interactive",
        "prompt",
        "smoke_host_public_multiturn",
        "wechat",
    }
)
"""思考模型角色的 8 个已知 manifest basename。"""

PRODUCTION_RUNTIME_MANIFEST_BASENAMES: Final[frozenset[str]] = frozenset(
    {
        "audit",
        "confirm",
        "conversation_compaction",
        "decision",
        "fix",
        "infer",
        "interactive",
        "overview",
        "prompt",
        "regenerate",
        "repair",
        "wechat",
        "write",
    }
)
"""使用真实 production tool discovery 校验的 13 个 manifest basename。"""

TEST_OWNED_MANUAL_SMOKE_MANIFEST_BASENAMES: Final[frozenset[str]] = frozenset(
    {
        "smoke_host_public_conversation_memory",
        "smoke_host_public_conversation_memory_scenarios",
        "smoke_host_public_multiturn",
    }
)
"""只能由测试提供显式 ``manual-smoke`` tool catalog 的 3 个 manifest basename。"""


@dataclass(frozen=True, slots=True)
class OllamaModelSettings:
    """用户明确输入的 Ollama 模型设置。

    :param model_name: Ollama provider 模型名。
    :param endpoint: 完整 HTTP(S) endpoint URL。
    :param context_window_tokens: 正整数上下文窗口 token 数。
    """

    model_name: str
    endpoint: str
    context_window_tokens: int

    def __post_init__(self) -> None:
        """在任何 models.json mutation 前校验显式输入。

        :returns: ``None``。
        :raises InitCatalogError: 模型名、URL 或上下文窗口非法时抛出。
        """

        _validate_dynamic_model_inputs(
            model_name=self.model_name,
            endpoint=self.endpoint,
            context_window_tokens=self.context_window_tokens,
        )


@dataclass(frozen=True, slots=True)
class CustomOpenAIModelSettings:
    """用户明确输入的 OpenAI-compatible 模型设置。

    :param model_name: provider 模型名。
    :param endpoint: 按用户输入原样保存的完整 HTTP(S) endpoint URL。
    :param context_window_tokens: 正整数上下文窗口 token 数。
    """

    model_name: str
    endpoint: str
    context_window_tokens: int

    def __post_init__(self) -> None:
        """在任何 models.json mutation 前校验显式输入。

        :returns: ``None``。
        :raises InitCatalogError: 模型名、URL 或上下文窗口非法时抛出。
        """

        _validate_dynamic_model_inputs(
            model_name=self.model_name,
            endpoint=self.endpoint,
            context_window_tokens=self.context_window_tokens,
        )


DynamicModelSettings: TypeAlias = OllamaModelSettings | CustomOpenAIModelSettings
"""两类动态模型显式输入的联合类型。"""


@dataclass(frozen=True, slots=True)
class InitModelSelection:
    """已完成类型校验的初始化模型选择。

    :param choice: 15 项目录中的选项。
    :param dynamic_settings: Ollama/custom 的显式动态设置；静态选项必须为 ``None``。
    """

    choice: InitModelChoice
    dynamic_settings: DynamicModelSettings | None = None

    def __post_init__(self) -> None:
        """校验选项与动态设置类型严格对应。

        :returns: ``None``。
        :raises InitCatalogError: 静态/动态选择与输入类型不匹配时抛出。
        """

        if self.choice not in INIT_MODEL_CHOICES:
            raise InitCatalogError("model selection must use an entry from INIT_MODEL_CHOICES")
        if self.choice.kind is InitModelChoiceKind.OLLAMA:
            if not isinstance(self.dynamic_settings, OllamaModelSettings):
                raise InitCatalogError("Ollama choice requires OllamaModelSettings")
            return
        if self.choice.kind is InitModelChoiceKind.CUSTOM_OPENAI:
            if not isinstance(self.dynamic_settings, CustomOpenAIModelSettings):
                raise InitCatalogError("custom OpenAI choice requires CustomOpenAIModelSettings")
            return
        if self.dynamic_settings is not None:
            raise InitCatalogError("static model choice must not include dynamic settings")


@dataclass(frozen=True, slots=True)
class OllamaTemplateDefaults:
    """由已验证 package Ollama template 投影的交互默认值。

    :param endpoint: package template endpoint。
    :param context_window_tokens: package template context window。
    """

    endpoint: str
    context_window_tokens: int


def find_init_model_choice(choice_id: str) -> InitModelChoice:
    """按稳定 id 查找初始化模型选项。

    :param choice_id: 要查找的稳定选择 id。
    :returns: 对应的不可变模型选项。
    :raises InitCatalogError: id 不在 15 项目录中时抛出。
    """

    for choice in INIT_MODEL_CHOICES:
        if choice.choice_id == choice_id:
            return choice
    raise InitCatalogError(f"unknown init model choice: {choice_id}")


def validate_init_catalog(package_config_dir: Path, package_manifest_dir: Path) -> ModelsConfig:
    """用当前 ConfigLoader 与 package manifest 集合校验初始化目录。

    :param package_config_dir: 包含当前 ``models.json`` 的 package 配置目录。
    :param package_manifest_dir: 当前 package scene manifest 目录。
    :returns: 已由当前 extends resolver 解析的 ``ModelsConfig``。
    :raises ConfigLoadError: 当前 models schema 或 extends 解析失败时抛出。
    :raises InitCatalogError: 选择映射、Ollama template 或 manifest 集合漂移时抛出。
    :raises OSError: manifest 目录无法读取时抛出。
    """

    _validate_choice_tuple_shape()
    models = ConfigLoader(package_config_dir=package_config_dir).load_models()
    for choice in INIT_MODEL_CHOICES:
        if choice.kind in (InitModelChoiceKind.OLLAMA, InitModelChoiceKind.CUSTOM_OPENAI):
            continue
        _validate_resolved_choice(models=models, choice=choice)
    _validate_ollama_template(models)
    _validate_package_manifest_names(package_manifest_dir)
    return models


def ollama_template_defaults(models: ModelsConfig) -> OllamaTemplateDefaults:
    """从已解析的 package Ollama template 返回交互默认值。

    :param models: 当前 ConfigLoader 产生的模型目录。
    :returns: endpoint 与 context window 默认值。
    :raises InitCatalogError: Ollama template 缺失或 provider/API key contract 漂移时抛出。
    """

    model = _validate_ollama_template(models)
    return OllamaTemplateDefaults(
        endpoint=model.endpoint,
        context_window_tokens=model.context_window_tokens,
    )


def apply_model_selection(config_dir: Path, selection: InitModelSelection) -> ModelsConfig:
    """在 staging ``models.json`` 应用动态记录并用真实 ConfigLoader 重载。

    静态选择不会重写文件，只验证 resolved pair。Ollama 复制 staging 中的
    当前完整 template 并只替换显式字段；custom 生成计划锁定的完整当前-schema
    记录。

    :param config_dir: 私有 staging 配置目录。
    :param selection: 类型化模型选择。
    :returns: mutation 后由当前 ConfigLoader 解析的模型目录。
    :raises ConfigLoadError: staging models schema 或 extends 解析失败时抛出。
    :raises InitCatalogError: 选择 contract、JSON shape 或动态记录验证失败时抛出。
    :raises OSError: ``models.json`` 读写失败时抛出。
    """

    models_before = ConfigLoader(package_config_dir=config_dir).load_models()
    if selection.dynamic_settings is None:
        _validate_resolved_choice(models=models_before, choice=selection.choice)
        return models_before

    models_path = config_dir / _MODELS_FILE_NAME
    root = _read_json_object(models_path)
    raw_models = _require_json_object(
        root.get(_MODELS_FIELD),
        context=f"{models_path}.{_MODELS_FIELD}",
    )
    updated_models: dict[str, JsonValue] = dict(raw_models)
    if isinstance(selection.dynamic_settings, OllamaModelSettings):
        _validate_ollama_template(models_before)
        raw_template = _require_json_object(
            raw_models.get(_OLLAMA_MODEL_ID),
            context=f"{models_path}.{_MODELS_FIELD}.{_OLLAMA_MODEL_ID}",
        )
        updated_models[_OLLAMA_MODEL_ID] = _build_ollama_record(
            template=raw_template,
            settings=selection.dynamic_settings,
        )
    else:
        updated_models[_CUSTOM_MODEL_ID] = _build_custom_openai_record(selection.dynamic_settings)
    updated_root: dict[str, JsonValue] = dict(root)
    updated_root[_MODELS_FIELD] = updated_models
    _write_json(models_path, updated_root)

    models_after = ConfigLoader(package_config_dir=config_dir).load_models()
    _validate_dynamic_selection(models=models_after, selection=selection)
    return models_after


def project_known_manifest_models(manifest_dir: Path, selection: InitModelSelection) -> tuple[Path, ...]:
    """只改写 16 个已知 manifest 的 ``model.default_model_id``。

    helper 会先读取并校验全部已知文件的最小投影路径，再开始写入；目录中的
    用户自建 manifest 不被枚举或改写。完整 scene schema 的解析仍由
    ``prepare_scene`` owner 负责。

    :param manifest_dir: 私有 staging scene manifest 目录。
    :param selection: 已完成类型校验的模型选择。
    :returns: 按 basename 排序的 16 个已改写路径。
    :raises InitCatalogError: 角色集合、已知文件或最小 JSON 投影路径非法时抛出。
    :raises OSError: manifest 文件读写失败时抛出。
    """

    _validate_manifest_role_sets()
    loaded: list[tuple[Path, JsonObject]] = []
    for basename in sorted(_known_manifest_basenames()):
        manifest_path = manifest_dir / f"{basename}{_JSON_SUFFIX}"
        manifest = _read_json_object(manifest_path)
        _require_manifest_model_object(manifest=manifest, manifest_path=manifest_path)
        loaded.append((manifest_path, manifest))

    changed_paths: list[Path] = []
    for manifest_path, manifest in loaded:
        model_id = (
            selection.choice.ordinary_model_id
            if manifest_path.stem in ORDINARY_MANIFEST_BASENAMES
            else selection.choice.thinking_model_id
        )
        projected = _project_manifest_model(
            manifest=manifest,
            manifest_path=manifest_path,
            model_id=model_id,
        )
        _write_json(manifest_path, projected)
        changed_paths.append(manifest_path)
    return tuple(changed_paths)


def _validate_choice_tuple_shape() -> None:
    """校验 15 项选择目录的稳定 id 与动态选项 contract。

    :returns: ``None``。
    :raises InitCatalogError: 选项数量、id 唯一性或 dynamic model id 漂移时抛出。
    """

    if len(INIT_MODEL_CHOICES) != _EXPECTED_CHOICE_COUNT:
        raise InitCatalogError(f"init model catalog must contain {_EXPECTED_CHOICE_COUNT} choices")
    choice_ids = tuple(choice.choice_id for choice in INIT_MODEL_CHOICES)
    if len(set(choice_ids)) != len(choice_ids):
        raise InitCatalogError("init model catalog choice ids must be unique")
    ollama = find_init_model_choice("ollama")
    if (ollama.ordinary_model_id, ollama.thinking_model_id) != (_OLLAMA_MODEL_ID, _OLLAMA_MODEL_ID):
        raise InitCatalogError("Ollama choice must use the single ollama runtime model id")
    custom = find_init_model_choice("custom-openai")
    if (custom.ordinary_model_id, custom.thinking_model_id) != (_CUSTOM_MODEL_ID, _CUSTOM_MODEL_ID):
        raise InitCatalogError("custom choice must use the single custom-openai runtime model id")
    if custom.required_secret_env_name != _CUSTOM_API_KEY_REF:
        raise InitCatalogError("custom choice API key ref does not match the current contract")


def _validate_resolved_choice(*, models: ModelsConfig, choice: InitModelChoice) -> None:
    """依据 resolved ``ModelsConfig`` 校验一对普通/思考模型。

    :param models: 当前 ConfigLoader 的 resolved 模型目录。
    :param choice: 需要校验的静态选择。
    :returns: ``None``。
    :raises InitCatalogError: 任一 id 缺失或 resolved provider/API key ref 不匹配时抛出。
    """

    for role, model_id in (
        ("ordinary", choice.ordinary_model_id),
        ("thinking", choice.thinking_model_id),
    ):
        model = models.models.get(model_id)
        if model is None:
            raise InitCatalogError(f"{choice.choice_id} {role} model is missing: {model_id}")
        if model.provider != choice.expected_provider:
            raise InitCatalogError(f"{choice.choice_id} {role} model provider mismatch: {model_id}")
        if model.api_key_ref != choice.required_secret_env_name:
            raise InitCatalogError(f"{choice.choice_id} {role} model API key ref mismatch: {model_id}")


def _validate_ollama_template(models: ModelsConfig) -> ModelConfig:
    """校验并返回唯一 Ollama current-schema template。

    :param models: 当前 ConfigLoader 产生的 resolved 模型目录。
    :returns: 已校验的 Ollama 模型记录。
    :raises InitCatalogError: template 缺失、provider 或 API key ref 漂移时抛出。
    """

    model = models.models.get(_OLLAMA_MODEL_ID)
    if model is None:
        raise InitCatalogError("package Ollama template is missing")
    if model.provider != InitModelChoiceKind.OLLAMA.value:
        raise InitCatalogError("package Ollama template provider mismatch")
    if model.api_key_ref is not None:
        raise InitCatalogError("package Ollama template must not require an API key")
    return model


def _validate_package_manifest_names(manifest_dir: Path) -> None:
    """校验 package manifest basename 精确等于锁定的 16 项。

    :param manifest_dir: package manifest 目录。
    :returns: ``None``。
    :raises InitCatalogError: 目录不存在或 JSON basename 集合漂移时抛出。
    :raises OSError: 目录无法读取时抛出。
    """

    _validate_manifest_role_sets()
    if not manifest_dir.is_dir():
        raise InitCatalogError(f"package manifest directory is missing: {manifest_dir}")
    actual = frozenset(path.stem for path in manifest_dir.iterdir() if path.is_file() and path.suffix == _JSON_SUFFIX)
    expected = _known_manifest_basenames()
    if actual != expected:
        missing = ",".join(sorted(expected - actual))
        extra = ",".join(sorted(actual - expected))
        raise InitCatalogError(f"package manifest set mismatch; missing=[{missing}] extra=[{extra}]")


def _validate_manifest_role_sets() -> None:
    """校验模型角色集合与 13/3 validation 集合彼此正交且同源。

    :returns: ``None``。
    :raises InitCatalogError: 任一集合有交集或两个并集不一致时抛出。
    """

    if ORDINARY_MANIFEST_BASENAMES & THINKING_MANIFEST_BASENAMES:
        raise InitCatalogError("ordinary and thinking manifest roles must be disjoint")
    if PRODUCTION_RUNTIME_MANIFEST_BASENAMES & TEST_OWNED_MANUAL_SMOKE_MANIFEST_BASENAMES:
        raise InitCatalogError("production and test-owned manifest validation sets must be disjoint")
    if _known_manifest_basenames() != (
        PRODUCTION_RUNTIME_MANIFEST_BASENAMES | TEST_OWNED_MANUAL_SMOKE_MANIFEST_BASENAMES
    ):
        raise InitCatalogError("manifest role and validation sets must describe the same 16 basenames")


def _known_manifest_basenames() -> frozenset[str]:
    """返回普通/思考角色并集。

    :returns: 精确 16 个 package known manifest basename。
    :raises Exception: 不主动抛出异常。
    """

    return ORDINARY_MANIFEST_BASENAMES | THINKING_MANIFEST_BASENAMES


def _validate_dynamic_model_inputs(*, model_name: str, endpoint: str, context_window_tokens: int) -> None:
    """校验两类动态模型共享的显式输入。

    :param model_name: provider 模型名。
    :param endpoint: 完整 HTTP(S) endpoint URL。
    :param context_window_tokens: 上下文窗口 token 数。
    :returns: ``None``。
    :raises InitCatalogError: 文本、URL 或正整数约束不满足时抛出。
    """

    if not model_name.strip() or model_name != model_name.strip() or _contains_control_character(model_name):
        raise InitCatalogError("dynamic model name must be non-empty and contain no surrounding/control whitespace")
    _validate_endpoint(endpoint)
    if isinstance(context_window_tokens, bool) or not isinstance(context_window_tokens, int) or context_window_tokens <= 0:
        raise InitCatalogError("dynamic model context_window_tokens must be a positive integer")


def _validate_endpoint(endpoint: str) -> None:
    """执行不联网的完整 HTTP(S) endpoint 语法校验。

    :param endpoint: 用户输入的 endpoint 原文。
    :returns: ``None``。
    :raises InitCatalogError: endpoint 为空、含空白/控制字符或缺少 HTTP(S) scheme/netloc 时抛出。
    """

    if not endpoint or endpoint != endpoint.strip() or any(character.isspace() for character in endpoint):
        raise InitCatalogError("dynamic model endpoint must not be empty or contain whitespace")
    if _contains_control_character(endpoint):
        raise InitCatalogError("dynamic model endpoint must not contain control characters")
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        raise InitCatalogError("dynamic model endpoint is not a valid URL") from None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname is None:
        raise InitCatalogError("dynamic model endpoint must be a complete HTTP(S) URL")
    if port is not None and port <= 0:
        raise InitCatalogError("dynamic model endpoint port must be positive")


def _contains_control_character(value: str) -> bool:
    """判断文本是否包含 Unicode 控制字符。

    :param value: 待检查文本。
    :returns: 包含控制字符时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _build_ollama_record(*, template: JsonObject, settings: OllamaModelSettings) -> dict[str, JsonValue]:
    """复制完整 Ollama template 并只替换三个显式字段。

    :param template: staging ``models.ollama`` 的完整当前-schema record。
    :param settings: 用户确认的 Ollama 设置。
    :returns: 可写回 staging 的新记录。
    :raises Exception: 不主动抛出异常。
    """

    record: dict[str, JsonValue] = dict(template)
    record["model"] = settings.model_name
    record["endpoint"] = settings.endpoint
    record["context_window_tokens"] = settings.context_window_tokens
    return record


def _build_custom_openai_record(settings: CustomOpenAIModelSettings) -> dict[str, JsonValue]:
    """构造计划锁定的完整 custom OpenAI-compatible current-schema record。

    :param settings: 用户确认的 custom provider 设置。
    :returns: 可由当前 ConfigLoader 读取的完整模型记录。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "runner_kind": "openai_compatible",
        "provider": InitModelChoiceKind.CUSTOM_OPENAI.value,
        "model": settings.model_name,
        "endpoint": settings.endpoint,
        "api_key_ref": _CUSTOM_API_KEY_REF,
        "headers": {
            "Authorization": "Bearer {{CUSTOM_OPENAI_API_KEY}}",
            "Content-Type": "application/json",
        },
        "supports_tool_calling": True,
        "supports_stream": True,
        "supports_stream_usage": True,
        "default_timeout_seconds": 3600.0,
        "max_retries": 3,
        "sse_idle_timeout_seconds": 120.0,
        "sse_heartbeat_seconds": 10.0,
        "provider_request_extension": None,
        "context_window_tokens": settings.context_window_tokens,
        "runtime_hints": {"runner_option_hints": _custom_runner_option_hints()},
    }


def _custom_runner_option_hints() -> dict[str, JsonValue]:
    """返回 OLD 直接证据到当前 schema 的唯一八项 custom hint 投影。

    :returns: 八个自足的 ``temperature/top_p/stream`` hint。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "write": {"temperature": 1.0, "top_p": 1.0, "stream": True},
        "overview": {"temperature": 1.0, "top_p": 1.0, "stream": True},
        "audit": {"temperature": 0.8, "top_p": 1.0, "stream": True},
        "decision": {"temperature": 1.0, "top_p": 1.0, "stream": True},
        "interactive": {"temperature": 1.0, "top_p": 1.0, "stream": True},
        "prompt": {"temperature": 1.0, "top_p": 1.0, "stream": True},
        "infer": {"temperature": 0.5, "top_p": 1.0, "stream": True},
        "conversation_compaction": {"temperature": 0.4, "top_p": 1.0, "stream": False},
    }


def _validate_dynamic_selection(*, models: ModelsConfig, selection: InitModelSelection) -> None:
    """校验真实 ConfigLoader 重载后的动态记录精确匹配显式输入。

    :param models: mutation 后的 resolved 模型目录。
    :param selection: 动态模型选择。
    :returns: ``None``。
    :raises InitCatalogError: 重载记录缺失或关键字段与显式 contract 不一致时抛出。
    """

    settings = selection.dynamic_settings
    if settings is None:
        raise InitCatalogError("dynamic validation requires dynamic settings")
    model_id = selection.choice.ordinary_model_id
    model = models.models.get(model_id)
    if model is None:
        raise InitCatalogError(f"dynamic model record is missing: {model_id}")
    if model.provider != selection.choice.expected_provider:
        raise InitCatalogError(f"dynamic model provider mismatch: {model_id}")
    if model.model != settings.model_name or model.endpoint != settings.endpoint:
        raise InitCatalogError(f"dynamic model explicit field mismatch: {model_id}")
    if model.context_window_tokens != settings.context_window_tokens:
        raise InitCatalogError(f"dynamic model context window mismatch: {model_id}")
    if model.api_key_ref != selection.choice.required_secret_env_name:
        raise InitCatalogError(f"dynamic model API key ref mismatch: {model_id}")


def _project_manifest_model(*, manifest: JsonObject, manifest_path: Path, model_id: str) -> dict[str, JsonValue]:
    """复制 manifest object 并只替换 model 内的默认模型 id。

    :param manifest: 已读取的 manifest JSON object。
    :param manifest_path: 错误上下文路径。
    :param model_id: 角色对应的目标模型 id。
    :returns: 保留其它字段的新 manifest object。
    :raises InitCatalogError: ``model`` 不是 JSON object 时抛出。
    """

    model = _require_manifest_model_object(manifest=manifest, manifest_path=manifest_path)
    projected_model: dict[str, JsonValue] = dict(model)
    projected_model[_DEFAULT_MODEL_ID_FIELD] = model_id
    projected_manifest: dict[str, JsonValue] = dict(manifest)
    projected_manifest[_MODEL_FIELD] = projected_model
    return projected_manifest


def _require_manifest_model_object(*, manifest: JsonObject, manifest_path: Path) -> JsonObject:
    """读取 projection 所需的最小 manifest model object。

    :param manifest: manifest JSON object。
    :param manifest_path: 错误上下文路径。
    :returns: model JSON object。
    :raises InitCatalogError: model/default_model_id 缺失或 shape 非法时抛出。
    """

    model = _require_json_object(manifest.get(_MODEL_FIELD), context=f"{manifest_path}.{_MODEL_FIELD}")
    default_model_id = model.get(_DEFAULT_MODEL_ID_FIELD)
    if not isinstance(default_model_id, str) or not default_model_id.strip():
        raise InitCatalogError(f"{manifest_path}.model.default_model_id must be a non-empty string")
    return model


def _read_json_object(path: Path) -> JsonObject:
    """读取 UTF-8 JSON object，不实现 models/scene schema。

    :param path: JSON 文件路径。
    :returns: JSON object。
    :raises InitCatalogError: JSON 非法或顶层不是 object 时抛出。
    :raises OSError: 文件读取失败时抛出。
    """

    try:
        value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    except ValueError:
        raise InitCatalogError(f"invalid JSON file: {path}") from None
    return _require_json_object(value, context=str(path))


def _require_json_object(value: JsonValue | None, *, context: str) -> JsonObject:
    """要求 JSON 值为 string-keyed object。

    :param value: 待检查 JSON 值。
    :param context: 安全错误上下文。
    :returns: JSON object。
    :raises InitCatalogError: 值不是 mapping 或存在非字符串 key 时抛出。
    """

    if not isinstance(value, Mapping):
        raise InitCatalogError(f"{context} must be a JSON object")
    for key in value:
        if not isinstance(key, str):
            raise InitCatalogError(f"{context} keys must be strings")
    return cast(JsonObject, value)


def _write_json(path: Path, value: JsonValue) -> None:
    """以当前 package 风格写入 staging JSON。

    :param path: 私有 staging 目标路径。
    :param value: 严格 JSON 值。
    :returns: ``None``。
    :raises OSError: 文件写入失败时抛出。
    :raises TypeError: 值不能被标准 JSON serializer 处理时抛出。
    """

    path.write_text(
        f"{json.dumps(value, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
