"""为 CLI init/provider matrix 提供确定性 contract 与真实 provider 取证。

本模块只编排真实 ``dayu-cli init``、production Service assembly 和 Host durable
read owner，不实现 provider、配置或 trace 语义。报告只保存白名单身份、脱敏
endpoint、bounded 文本摘要及 digest，绝不保存 runner input 或原始 durable payload。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Sequence, TypeAlias, cast
from urllib.parse import urlsplit

from dayu.cli.commands.prompt import build_prompt_context_slot_values
from dayu.cli.init_catalog import (
    INIT_MODEL_CHOICES,
    InitModelChoice,
    InitModelChoiceKind,
    OllamaModelSettings,
)
from dayu.cli.init_environment import OPTIONAL_ENVIRONMENT_NAMES
from dayu.contracts import JsonValue as DurableJsonValue
from dayu.host._runner_call_manifest import (
    RunnerCallSizingStatus,
    parse_runner_call_manifest,
    parse_runner_call_hot_payload,
)
from dayu.host.durable.connection import open_host_durable_read_store
from dayu.host.durable.options import HostSQLiteStoragePolicy
from dayu.host.durable.tool_trace import (
    TOOL_TRACE_QUERY_MAX_LIMIT,
    RunnerCallReconstructionStatus,
    read_runner_call_reconstruction_signals_by_run,
    read_tool_trace_page,
    resolve_runner_call_projection_from_signal,
    resolve_tool_trace_hot_row_payloads,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.runtime.assembly import model_family_identity
from dayu.runtime.config_loader import ConfigLoader
from dayu.service.entrypoint_runtime import (
    EntrypointRuntimeRequest,
    prepare_entrypoint_runtime,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides


ORACLE_ID = "cli.init.workspace-initialization"
ORACLE_VERSION = 1
PUBLICATION_ROOT = "workspace"
INIT_LOCK_PATH = ".dayu-init.lock"
EXPECTED_DIRECTORY_COUNT = 5
EXPECTED_FILE_COUNT = 43
EXPECTED_MODEL_POINTER_COUNT = 16
DEFAULT_PREVIEW_LIMIT = 256
INIT_TIMEOUT_SECONDS = 60.0
PROMPT_TIMEOUT_SECONDS = 180.0
PERSISTED_SCAN_MAX_NODES = 8_192
PERSISTED_SCAN_MAX_FILES = 4_096
PERSISTED_SCAN_MAX_FILE_BYTES = 64 * 1024 * 1024
PERSISTED_SCAN_MAX_TOTAL_BYTES = 512 * 1024 * 1024
PERSISTED_SCAN_READ_CHUNK_BYTES = 1024 * 1024
# 这两个 getattr 只做标准库平台能力探测；缺少 no-follow/dir-fd 时扫描必须
# fail closed，不能用会跟随 symlink 的兼容路径降级。
PERSISTED_SCAN_NOFOLLOW_FLAG = cast(int, getattr(os, "O_NOFOLLOW", 0))
PERSISTED_SCAN_DIRECTORY_FLAG = cast(int, getattr(os, "O_DIRECTORY", 0))
PERSISTED_SCAN_NOFOLLOW_SUPPORTED = (
    PERSISTED_SCAN_NOFOLLOW_FLAG != 0
    and PERSISTED_SCAN_DIRECTORY_FLAG != 0
    and os.open in os.supports_dir_fd
    and os.scandir in os.supports_fd
)
PROMPT_TEXT = "不要调用任何工具。只回复：S5B_OK"
MATRIX_ROW_COUNT = 15
ROLE_COVERAGE = ("ordinary", "compactor")
DYNAMIC_CHOICE_KINDS = frozenset(
    {
        InitModelChoiceKind.OLLAMA,
        InitModelChoiceKind.CUSTOM_OPENAI,
    }
)
REPORT_ROOT = Path("workspace/tmp/wu-cli-init-01")
FROZEN_MANIFEST_PATH = Path("docs/cli_init_workspace_manifest_v1.json")
PACKAGE_CONFIG_ROOT = Path("dayu/config")
HOST_DB_RELATIVE_PATH = Path(".dayu/host/dayu_host.sqlite3")
HOST_ARTIFACT_RELATIVE_PATH = Path(".dayu/artifacts")
PROFILE_FILE_NAMES = frozenset(
    {".zshrc", ".bashrc", ".bash_profile", ".profile"}
)
TRANSPORT_ERROR_CODES = frozenset({"network_error", "timeout"})
RATE_LIMIT_ERROR_CODES = frozenset({"rate_limit_exceeded"})
PROVIDER_REJECTION_ERROR_CODES = frozenset(
    {"client_error", "server_error", "unknown_http_status", "provider_error"}
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
AUTHORIZATION_PATTERN = re.compile(
    r"(?i)\bauthorization\b\s*[:=]\s*[\"']?\S+"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
REQUEST_ID_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:client_correlation_id|provider_request_id)\s*=\s*\S+"
)
CREDENTIAL_VALUE_PATTERN = re.compile(
    r"""(?ix)
    ["']?
    (?:api[_-]?key|access[_-]?token|secret|password|credential)
    ["']?
    \s*[:=]\s*
    ["'](?![A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)["'])[^"']+["']
    """
)
SECRET_CANARY_PREFIX = "s5b-canary-"
REPORT_JSON_KEYS = frozenset(
    {
        "oracle_id",
        "oracle_version",
        "matrix_run_id",
        "started_at",
        "completed_at",
        "overall_exit_code",
        "rows",
        "secret_scan",
    }
)
ROW_JSON_KEYS = frozenset(
    {
        "scenario_id",
        "choice_id",
        "role_coverage",
        "expected_ordinary_model_id",
        "expected_compactor_model_id",
        "required_credential_ref",
        "credential_present",
        "preflight_class",
        "availability_class",
        "init_exit_code",
        "prompt_exit_code",
        "publication_valid",
        "publication_issues",
        "publication_absent_after_rejection",
        "profile_publication_observed",
        "config_tree_digest_before",
        "config_tree_digest_after_init",
        "config_tree_digest_after_prompt",
        "request_attempted",
        "successful_response_received",
        "provider_request_id_present",
        "client_correlation_id_present",
        "host_run_id",
        "ordinary_identity",
        "compactor_identity",
        "runner_calls",
        "terminal_status",
        "terminal_summary",
        "no_fallback",
        "secret_scan",
        "persisted_secret_scan",
        "internal_contract_valid",
    }
)
LEGACY_ROW_JSON_KEYS = ROW_JSON_KEYS - {"persisted_secret_scan"}
TERMINAL_SUMMARY_JSON_KEYS = frozenset(
    {"length", "sha256", "preview", "marker_present"}
)

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class ManifestValidationError(ValueError):
    """表示冻结清单本身不满足严格 schema，不能作为可信 oracle。"""


class ModelRole(str, Enum):
    """模型投影 owner 的业务角色。"""

    ORDINARY = "ordinary"
    THINKING = "thinking"


class PreflightClass(str, Enum):
    """真实 provider 调用前的外部前置条件分类。"""

    REQUESTABLE = "requestable"
    CREDENTIAL_MISSING = "credential_missing"
    ENDPOINT_UNCONFIGURED = "endpoint_unconfigured"
    SERVICE_UNREACHABLE = "service_unreachable"


class AvailabilityClass(str, Enum):
    """provider matrix row 的最终可用性分类。"""

    AVAILABLE = "available"
    CREDENTIAL_MISSING = "credential_missing"
    ENDPOINT_UNCONFIGURED = "endpoint_unconfigured"
    SERVICE_UNREACHABLE = "service_unreachable"
    PROVIDER_REJECTED = "provider_rejected"
    RATE_LIMITED = "rate_limited"
    INTERNAL_PRODUCT_BUG = "internal_product_bug"


class FailureKind(str, Enum):
    """一次真实调用观测到的失败种类。"""

    NONE = "none"
    TRANSPORT = "transport"
    PROVIDER_REJECTED = "provider_rejected"
    RATE_LIMITED = "rate_limited"
    INTERNAL_PRODUCT_BUG = "internal_product_bug"


class TerminalStatus(str, Enum):
    """matrix row 的终态。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_RUN = "not_run"


class PersistedArtifactClass(str, Enum):
    """row root 内持久化文件的稳定相对类别。"""

    CONFIG = "workspace/config"
    HOST_SQLITE = "workspace/host_sqlite"
    HOST_SQLITE_WAL = "workspace/host_sqlite_wal"
    TRACE_LOG_ARTIFACT = "workspace/trace_log_artifact"
    ROW_OTHER = "row/other"


@dataclass(frozen=True, slots=True)
class ManifestFile:
    """冻结清单中的一个 workspace publication 文件事实。"""

    path: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ModelProjectionOwner:
    """冻结清单中的一个模型投影 owner。"""

    path: str
    json_pointer: str
    role: ModelRole


@dataclass(frozen=True, slots=True)
class FrozenPublicationManifest:
    """经严格校验后可作为 oracle 的冻结 publication manifest。"""

    oracle_id: str
    oracle_version: int
    publication_root: str
    directories: tuple[str, ...]
    files: tuple[ManifestFile, ...]
    model_projection_owner_paths: tuple[ModelProjectionOwner, ...]


@dataclass(frozen=True, slots=True)
class PublicationValidationReport:
    """实际 publication tree 与冻结清单的比较报告。"""

    valid: bool
    issues: tuple[str, ...]
    actual_directories: tuple[str, ...]
    actual_files: tuple[str, ...]
    actual_model_owner_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AvailabilityEvidence:
    """最终可用性分类所需的最小观测集合。"""

    preflight_class: PreflightClass
    internal_contract_valid: bool
    request_attempted: bool
    response_received: bool
    exit_code: int
    failure_kind: FailureKind


@dataclass(frozen=True, slots=True)
class RedactedEndpoint:
    """不含 userinfo、query 和 fragment 的 endpoint 身份。"""

    scheme: str
    hostname: str
    port: int | None
    path_sha256: str


@dataclass(frozen=True, slots=True)
class BoundedTextSummary:
    """不保存完整正文的 bounded 文本摘要。"""

    length: int
    sha256: str
    preview: str
    marker_present: bool


@dataclass(frozen=True, slots=True)
class SecretScanReport:
    """对最终 report 文本执行 secret 扫描后的结果。"""

    passed: bool
    finding_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PersistedCredentialObservation:
    """Host SQLite 中允许存在的 credential 明文观测聚合。"""

    observation_code: str
    artifact_class: PersistedArtifactClass
    count: int


@dataclass(frozen=True, slots=True)
class PersistedSecretViolation:
    """持久化 policy violation 的稳定、无敏感值聚合。"""

    violation_code: str
    artifact_class: PersistedArtifactClass
    count: int


@dataclass(frozen=True, slots=True)
class PersistedSecretScanReport:
    """CI-owned row root 的 bounded、no-follow 持久化扫描结果。"""

    passed: bool
    scanned_file_count: int
    scanned_byte_count: int
    accepted_observations: tuple[PersistedCredentialObservation, ...]
    violations: tuple[PersistedSecretViolation, ...]


@dataclass(slots=True)
class _PersistedScanAccumulator:
    """持久化扫描过程的有界内部累加状态。"""

    node_count: int
    scanned_file_count: int
    scanned_byte_count: int
    accepted_observation_counts: dict[
        tuple[str, PersistedArtifactClass],
        int,
    ]
    violation_counts: dict[tuple[str, PersistedArtifactClass], int]
    stopped: bool


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    """no-fallback 判定使用的 provider/model 业务身份。"""

    family_id: str
    provider: str
    provider_model: str


@dataclass(frozen=True, slots=True)
class EffectiveModelIdentity:
    """production assembly 产生的完整 effective model identity。"""

    config_model_id: str
    provider: str
    provider_model: str
    endpoint: RedactedEndpoint
    credential_ref: str | None


@dataclass(frozen=True, slots=True)
class RunnerCallIdentity:
    """Host runner-call resolver 证明的一次调用身份。"""

    event_id: str
    manifest_ref: str
    manifest_digest: str
    input_projection_digest: str
    provider: str
    provider_model: str


@dataclass(frozen=True, slots=True)
class NoFallbackEvidence:
    """no-fallback 判定所需的独立 expected/effective 身份与 trace 证据。"""

    expected_identity: ProviderIdentity | None
    effective_identity: ProviderIdentity | None
    request_attempted: bool
    host_run_id: str | None
    trace_run_id: str | None
    observed_identities: tuple[ProviderIdentity, ...]
    alternate_success_observed: bool


@dataclass(frozen=True, slots=True)
class NoFallbackVerdict:
    """no-fallback 纯函数的可审计裁决。"""

    passed: bool
    fallback_observed: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProviderMatrixRowReport:
    """单个 provider matrix row 的 typed report schema。"""

    scenario_id: str
    choice_id: str
    role_coverage: tuple[str, str]
    expected_ordinary_model_id: str
    expected_compactor_model_id: str
    required_credential_ref: str | None
    credential_present: bool
    preflight_class: PreflightClass
    availability_class: AvailabilityClass
    init_exit_code: int
    prompt_exit_code: int | None
    publication_valid: bool
    publication_issues: tuple[str, ...]
    publication_absent_after_rejection: bool
    profile_publication_observed: bool
    config_tree_digest_before: str
    config_tree_digest_after_init: str
    config_tree_digest_after_prompt: str
    request_attempted: bool
    successful_response_received: bool
    provider_request_id_present: bool
    client_correlation_id_present: bool
    host_run_id: str | None
    ordinary_identity: EffectiveModelIdentity | None
    compactor_identity: EffectiveModelIdentity | None
    runner_calls: tuple[RunnerCallIdentity, ...]
    terminal_status: TerminalStatus
    terminal_summary: BoundedTextSummary
    no_fallback: NoFallbackVerdict
    secret_scan: SecretScanReport
    persisted_secret_scan: PersistedSecretScanReport
    internal_contract_valid: bool


@dataclass(frozen=True, slots=True)
class ProviderMatrixReport:
    """完整 provider matrix 的 typed report schema。"""

    oracle_id: str
    oracle_version: int
    matrix_run_id: str
    started_at: str
    completed_at: str
    overall_exit_code: int
    rows: tuple[ProviderMatrixRowReport, ...]
    secret_scan: SecretScanReport


@dataclass(frozen=True, slots=True)
class SubprocessResult:
    """受时限约束的真实 CLI 子进程结果。"""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


@dataclass(frozen=True, slots=True)
class HostObservation:
    """从 Host canonical truth 与 Tool Trace owner 读取的白名单证据。"""

    internal_contract_valid: bool
    host_run_id: str | None
    terminal_status: TerminalStatus
    terminal_error_code: str | None
    terminal_text: str
    request_attempted: bool
    successful_response_received: bool
    provider_request_id_present: bool
    client_correlation_id_present: bool
    runner_calls: tuple[RunnerCallIdentity, ...]


@dataclass(frozen=True, slots=True)
class MatrixExecutionResult:
    """live matrix 执行结果与已安全写入的报告路径。"""

    report_path: Path
    report: ProviderMatrixReport


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """既有 run 原位重签后的稳定结果。"""

    report_path: Path
    overall_exit_code: int
    accepted_host_credential_observation_row_count: int
    persistence_violation_row_count: int


class CliArguments(argparse.Namespace):
    """命令行骨架解析后的严格类型参数。"""

    oracle_version: int


def _sha256_bytes(content: bytes) -> str:
    """计算 bytes 的 SHA-256。

    参数：
        content：待计算摘要的原始 bytes。

    返回：
        小写十六进制 SHA-256。

    异常：
        本函数不主动抛出异常。
    """

    return hashlib.sha256(content).hexdigest()


def _expect_mapping(value: JsonValue, context: str) -> dict[str, JsonValue]:
    """要求 JSON 值为字符串键映射。

    参数：
        value：待校验 JSON 值。
        context：错误消息中的字段位置。

    返回：
        严格类型的 JSON 映射。

    异常：
        ManifestValidationError：值不是 JSON object。
    """

    if not isinstance(value, dict):
        raise ManifestValidationError(f"{context} 必须是 JSON object")
    return cast(dict[str, JsonValue], value)


def _expect_list(value: JsonValue, context: str) -> list[JsonValue]:
    """要求 JSON 值为数组。

    参数：
        value：待校验 JSON 值。
        context：错误消息中的字段位置。

    返回：
        严格类型的 JSON 数组。

    异常：
        ManifestValidationError：值不是 JSON array。
    """

    if not isinstance(value, list):
        raise ManifestValidationError(f"{context} 必须是 JSON array")
    return cast(list[JsonValue], value)


def _expect_string(value: JsonValue, context: str) -> str:
    """要求 JSON 值为非空字符串。

    参数：
        value：待校验 JSON 值。
        context：错误消息中的字段位置。

    返回：
        非空字符串。

    异常：
        ManifestValidationError：值不是非空字符串。
    """

    if not isinstance(value, str) or not value:
        raise ManifestValidationError(f"{context} 必须是非空字符串")
    return value


def _expect_text(value: JsonValue, context: str) -> str:
    """要求 JSON value 是允许为空的字符串。

    参数：
        value：待检查 JSON value。
        context：错误消息使用的字段上下文。

    返回：
        字符串原值。

    异常：
        ManifestValidationError：value 不是字符串。
    """

    if not isinstance(value, str):
        raise ManifestValidationError(f"{context} 必须是字符串")
    return value


def _expect_bool(value: JsonValue, context: str) -> bool:
    """要求 JSON value 是严格布尔值。

    参数：
        value：待检查 JSON value。
        context：错误消息使用的字段上下文。

    返回：
        严格 bool。

    异常：
        ManifestValidationError：value 不是 bool。
    """

    if type(value) is not bool:
        raise ManifestValidationError(f"{context} 必须是 bool")
    return value


def _expect_int(value: JsonValue, context: str) -> int:
    """要求 JSON value 是严格整数。

    参数：
        value：待检查 JSON value。
        context：错误消息使用的字段上下文。

    返回：
        不接受 bool 的 int。

    异常：
        ManifestValidationError：value 不是严格 int。
    """

    if type(value) is not int:
        raise ManifestValidationError(f"{context} 必须是 int")
    return value


def _require_exact_keys(
    mapping: dict[str, JsonValue],
    expected_keys: frozenset[str],
    context: str,
) -> None:
    """要求 JSON object 只含指定键。

    参数：
        mapping：待校验映射。
        expected_keys：完整且唯一允许的键集合。
        context：错误消息中的字段位置。

    返回：
        无返回值。

    异常：
        ManifestValidationError：存在缺失键或未知键。
    """

    actual_keys = frozenset(mapping)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        raise ManifestValidationError(
            f"{context} 字段不匹配：missing={missing}, extra={extra}"
        )


def _validate_relative_path(
    path: str,
    context: str,
    *,
    allow_init_lock: bool,
) -> None:
    """校验路径为规范的 workspace publication 相对 POSIX 路径。

    参数：
        path：待校验路径。
        context：错误消息中的字段位置。
        allow_init_lock：当前位置是否允许根级 init lock。

    返回：
        无返回值。

    异常：
        ManifestValidationError：路径绝对、越界、含反斜杠或不属于受管集合。
    """

    pure_path = PurePosixPath(path)
    if (
        pure_path.is_absolute()
        or "\\" in path
        or ".." in pure_path.parts
        or "." in pure_path.parts
        or not pure_path.parts
        or pure_path.as_posix() != path
    ):
        raise ManifestValidationError(
            f"{context} 不是规范的 workspace publication 相对路径：{path}"
        )
    is_config_path = pure_path.parts[0] == "config"
    is_init_lock = allow_init_lock and path == INIT_LOCK_PATH
    if not is_config_path and not is_init_lock:
        raise ManifestValidationError(f"{context} 不属于 init 受管 publication：{path}")


def _parse_manifest_file(value: JsonValue, index: int) -> ManifestFile:
    """解析一个严格的 manifest 文件条目。

    参数：
        value：原始 JSON 条目。
        index：条目索引。

    返回：
        typed manifest 文件条目。

    异常：
        ManifestValidationError：条目字段、路径或摘要不合法。
    """

    context = f"files[{index}]"
    mapping = _expect_mapping(value, context)
    _require_exact_keys(
        mapping,
        frozenset({"path", "content_sha256"}),
        context,
    )
    path = _expect_string(mapping["path"], f"{context}.path")
    digest = _expect_string(
        mapping["content_sha256"],
        f"{context}.content_sha256",
    )
    _validate_relative_path(path, f"{context}.path", allow_init_lock=True)
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise ManifestValidationError(f"{context}.content_sha256 不是合法 SHA-256")
    return ManifestFile(path=path, content_sha256=digest)


def _parse_model_owner(value: JsonValue, index: int) -> ModelProjectionOwner:
    """解析一个严格的模型投影 owner 条目。

    参数：
        value：原始 JSON 条目。
        index：条目索引。

    返回：
        typed 模型投影 owner。

    异常：
        ManifestValidationError：字段、路径、pointer 或 role 不合法。
    """

    context = f"model_projection_owner_paths[{index}]"
    mapping = _expect_mapping(value, context)
    _require_exact_keys(
        mapping,
        frozenset({"path", "json_pointer", "role"}),
        context,
    )
    path = _expect_string(mapping["path"], f"{context}.path")
    pointer = _expect_string(mapping["json_pointer"], f"{context}.json_pointer")
    role_text = _expect_string(mapping["role"], f"{context}.role")
    _validate_relative_path(path, f"{context}.path", allow_init_lock=False)
    if pointer != "/model/default_model_id":
        raise ManifestValidationError(
            f"{context}.json_pointer 必须是 /model/default_model_id"
        )
    try:
        role = ModelRole(role_text)
    except ValueError as error:
        raise ManifestValidationError(f"{context}.role 非法：{role_text}") from error
    return ModelProjectionOwner(path=path, json_pointer=pointer, role=role)


def load_manifest(path: Path) -> FrozenPublicationManifest:
    """加载并严格校验 checked-in frozen manifest。

    参数：
        path：冻结 manifest 的文件路径。

    返回：
        不可变、严格类型的 publication manifest。

    异常：
        OSError：文件不存在、不可读或读取失败。
        ManifestValidationError：JSON 或 manifest contract 不合法。
    """

    try:
        raw_value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise ManifestValidationError(f"manifest 不是合法 JSON：{error.msg}") from error
    root = _expect_mapping(raw_value, "manifest")
    _require_exact_keys(
        root,
        frozenset(
            {
                "oracle_id",
                "oracle_version",
                "publication_root",
                "directories",
                "files",
                "model_projection_owner_paths",
            }
        ),
        "manifest",
    )

    oracle_id = _expect_string(root["oracle_id"], "oracle_id")
    version_value = root["oracle_version"]
    publication_root = _expect_string(root["publication_root"], "publication_root")
    if oracle_id != ORACLE_ID:
        raise ManifestValidationError(f"oracle_id 非法：{oracle_id}")
    if (
        not isinstance(version_value, int)
        or isinstance(version_value, bool)
        or version_value != ORACLE_VERSION
    ):
        raise ManifestValidationError(f"oracle_version 必须是 {ORACLE_VERSION}")
    if publication_root != PUBLICATION_ROOT:
        raise ManifestValidationError(
            f"publication_root 必须是 {PUBLICATION_ROOT}"
        )

    directory_values = _expect_list(root["directories"], "directories")
    directories = tuple(
        _expect_string(value, f"directories[{index}]")
        for index, value in enumerate(directory_values)
    )
    for index, directory in enumerate(directories):
        _validate_relative_path(
            directory,
            f"directories[{index}]",
            allow_init_lock=False,
        )
    if len(directories) != EXPECTED_DIRECTORY_COUNT:
        raise ManifestValidationError(
            f"directories 必须固定为 {EXPECTED_DIRECTORY_COUNT} 项"
        )
    if len(set(directories)) != len(directories):
        raise ManifestValidationError("directories 不得包含重复路径")
    if tuple(sorted(directories)) != directories:
        raise ManifestValidationError("directories 必须按路径排序")

    files = tuple(
        _parse_manifest_file(value, index)
        for index, value in enumerate(_expect_list(root["files"], "files"))
    )
    if len(files) != EXPECTED_FILE_COUNT:
        raise ManifestValidationError(f"files 必须固定为 {EXPECTED_FILE_COUNT} 项")
    file_paths = tuple(item.path for item in files)
    if len(set(file_paths)) != len(file_paths):
        raise ManifestValidationError("files 不得包含重复路径")
    if tuple(sorted(file_paths)) != file_paths:
        raise ManifestValidationError("files 必须按路径排序")
    if file_paths.count(INIT_LOCK_PATH) != 1:
        raise ManifestValidationError(
            f"files 必须且只能包含一个根级 {INIT_LOCK_PATH}"
        )

    owners = tuple(
        _parse_model_owner(value, index)
        for index, value in enumerate(
            _expect_list(
                root["model_projection_owner_paths"],
                "model_projection_owner_paths",
            )
        )
    )
    if len(owners) != EXPECTED_MODEL_POINTER_COUNT:
        raise ManifestValidationError(
            "model_projection_owner_paths "
            f"必须固定为 {EXPECTED_MODEL_POINTER_COUNT} 项"
        )
    owner_paths = tuple(owner.path for owner in owners)
    if len(set(owner_paths)) != len(owner_paths):
        raise ManifestValidationError(
            "model_projection_owner_paths 不得包含重复 owner"
        )
    if tuple(sorted(owner_paths)) != owner_paths:
        raise ManifestValidationError(
            "model_projection_owner_paths 必须按路径排序"
        )
    unknown_owner_paths = sorted(set(owner_paths) - set(file_paths))
    if unknown_owner_paths:
        raise ManifestValidationError(
            f"模型 owner 不在冻结文件列表中：{unknown_owner_paths}"
        )
    role_counts = {
        ModelRole.ORDINARY: sum(
            owner.role is ModelRole.ORDINARY for owner in owners
        ),
        ModelRole.THINKING: sum(
            owner.role is ModelRole.THINKING for owner in owners
        ),
    }
    if role_counts != {ModelRole.ORDINARY: 8, ModelRole.THINKING: 8}:
        raise ManifestValidationError(f"模型 owner role 数量非法：{role_counts}")

    return FrozenPublicationManifest(
        oracle_id=oracle_id,
        oracle_version=version_value,
        publication_root=publication_root,
        directories=directories,
        files=files,
        model_projection_owner_paths=owners,
    )


def _publication_relative_path(workspace_root: Path, path: Path) -> str:
    """把 workspace 内路径投影为 publication 相对路径。

    参数：
        workspace_root：实际 workspace 根目录。
        path：位于该 workspace 内的实际路径。

    返回：
        workspace-root-relative POSIX 路径。

    异常：
        ValueError：path 不在 workspace_root 下。
    """

    return path.relative_to(workspace_root).as_posix()


def _discover_model_owner_paths(
    manifest_root: Path,
    workspace_root: Path,
) -> tuple[str, ...]:
    """独立发现实际 manifest tree 中存在目标 JSON pointer 的文件。

    参数：
        manifest_root：实际 ``config/prompts/manifests`` 目录。
        workspace_root：实际 workspace 根目录。

    返回：
        含 ``/model/default_model_id`` 非空字符串的排序 publication 路径。

    异常：
        OSError：manifest 文件不可读。
        json.JSONDecodeError：manifest 文件不是合法 JSON。
        ValueError：manifest_root 不位于 workspace_root 下。
    """

    owner_paths: list[str] = []
    for path in sorted(manifest_root.glob("*.json")):
        raw_value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
        if not isinstance(raw_value, dict):
            continue
        root = cast(dict[str, JsonValue], raw_value)
        model_value = root.get("model")
        if not isinstance(model_value, dict):
            continue
        model = cast(dict[str, JsonValue], model_value)
        default_model_id = model.get("default_model_id")
        if isinstance(default_model_id, str) and default_model_id:
            owner_paths.append(_publication_relative_path(workspace_root, path))
    return tuple(owner_paths)


def validate_publication_tree(
    manifest: FrozenPublicationManifest,
    workspace_root: Path,
) -> PublicationValidationReport:
    """独立枚举实际 publication tree 并与冻结清单逐项比较。

    实际 publication 由根级 ``.dayu-init.lock`` 与 ``config`` 完整受管子树组成。
    该规则不读取冻结文件列表来构造 actual，因此新增、删除和篡改都会形成独立
    差异；workspace 中 portfolio 等非 init-owned sibling 不参与比较。

    参数：
        manifest：已由 ``load_manifest`` 严格加载的冻结 oracle。
        workspace_root：由 production init owner 生成的实际 workspace 根目录。

    返回：
        包含路径、摘要和 16 个 model pointer 比较结果的 typed report。

    异常：
        本函数把实际树的读取、JSON 和形状错误归入 report，不主动向外抛出。
    """

    issues: list[str] = []
    actual_directories: tuple[str, ...] = ()
    actual_files: tuple[str, ...] = ()
    actual_owner_paths: tuple[str, ...] = ()
    actual_digests: dict[str, str] = {}

    try:
        if not workspace_root.is_dir() or workspace_root.is_symlink():
            raise ValueError("workspace_root 必须是非 symlink 目录")
        config_root = workspace_root / "config"
        if not config_root.is_dir() or config_root.is_symlink():
            raise ValueError("config 必须是非 symlink 目录")
        lock_path = workspace_root / INIT_LOCK_PATH
        if not lock_path.is_file() or lock_path.is_symlink():
            raise ValueError(f"{INIT_LOCK_PATH} 必须是普通非 symlink 文件")
        prompts_root = config_root / "prompts"
        if not prompts_root.is_dir() or prompts_root.is_symlink():
            raise ValueError("config/prompts 必须是非 symlink 目录")

        directory_paths = [config_root]
        directory_paths.extend(
            path
            for path in config_root.rglob("*")
            if path.is_dir() and not path.is_symlink()
        )
        actual_directories = tuple(
            sorted(
                _publication_relative_path(workspace_root, path)
                for path in directory_paths
            )
        )

        file_paths = [lock_path]
        file_paths.extend(
            path
            for path in config_root.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        for path in sorted(file_paths):
            relative_path = _publication_relative_path(workspace_root, path)
            actual_digests[relative_path] = _sha256_bytes(path.read_bytes())
        actual_files = tuple(sorted(actual_digests))
        actual_owner_paths = _discover_model_owner_paths(
            prompts_root / "manifests",
            workspace_root,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        issues.append(f"actual_tree_unreadable:{type(error).__name__}")
        return PublicationValidationReport(
            valid=False,
            issues=tuple(issues),
            actual_directories=actual_directories,
            actual_files=actual_files,
            actual_model_owner_paths=actual_owner_paths,
        )

    expected_directories = manifest.directories
    if actual_directories != expected_directories:
        issues.append(
            "directory_mismatch:"
            f"expected_count={len(expected_directories)},"
            f"actual_count={len(actual_directories)}"
        )

    expected_digest_by_path = {
        item.path: item.content_sha256 for item in manifest.files
    }
    expected_files = tuple(sorted(expected_digest_by_path))
    if actual_files != expected_files:
        missing = sorted(set(expected_files) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected_files))
        issues.append(f"file_path_mismatch:missing={missing},extra={extra}")
    for path in sorted(set(expected_files) & set(actual_files)):
        if actual_digests[path] != expected_digest_by_path[path]:
            issues.append(f"file_digest_mismatch:{path}")

    expected_owner_paths = tuple(
        owner.path for owner in manifest.model_projection_owner_paths
    )
    if actual_owner_paths != expected_owner_paths:
        missing = sorted(set(expected_owner_paths) - set(actual_owner_paths))
        extra = sorted(set(actual_owner_paths) - set(expected_owner_paths))
        issues.append(f"model_pointer_mismatch:missing={missing},extra={extra}")
    if len(actual_owner_paths) != EXPECTED_MODEL_POINTER_COUNT:
        issues.append(
            "model_pointer_count_mismatch:"
            f"expected={EXPECTED_MODEL_POINTER_COUNT},"
            f"actual={len(actual_owner_paths)}"
        )

    return PublicationValidationReport(
        valid=not issues,
        issues=tuple(issues),
        actual_directories=actual_directories,
        actual_files=actual_files,
        actual_model_owner_paths=actual_owner_paths,
    )


def _owner_document_with_default(
    value: JsonValue,
    *,
    default_model_id: str,
    context: str,
) -> JsonValue:
    """只替换 manifest owner 声明的模型 pointer。

    参数：
        value：待投影的 manifest JSON。
        default_model_id：写入 ``/model/default_model_id`` 的模型 id。
        context：结构错误的诊断上下文。

    返回：
        只改变 owner pointer 的新 JSON object。

    异常：
        ManifestValidationError：文档或 model 不是 object。
    """

    root = dict(_expect_mapping(value, context))
    model = dict(_expect_mapping(root.get("model"), f"{context}.model"))
    model["default_model_id"] = default_model_id
    root["model"] = cast(JsonValue, model)
    return cast(JsonValue, root)


def validate_projected_publication_tree(
    manifest: FrozenPublicationManifest,
    workspace_root: Path,
    package_config_root: Path,
    *,
    ordinary_model_id: str,
    thinking_model_id: str,
    allow_ollama_dynamic: bool = False,
) -> PublicationValidationReport:
    """校验允许按角色投影模型 id 的真实 publication tree。

    目录、文件集合、非 owner 文件及 package source 必须仍与冻结 oracle 完全
    一致。owner 文件只允许 production init 改变声明的单一 JSON pointer。

    参数：
        manifest：严格加载的冻结 oracle。
        workspace_root：真实 init publication 根目录。
        package_config_root：production package 配置根目录。
        ordinary_model_id：普通角色期望模型 id。
        thinking_model_id：思考角色期望模型 id。
        allow_ollama_dynamic：是否允许 production Ollama 动态记录的三字段投影。

    返回：
        路径、摘要和 owner pointer 的完整校验报告。

    异常：
        本函数把实际与 package 文档读取错误归入报告，不向外抛出。
    """

    strict_report = validate_publication_tree(manifest, workspace_root)
    if any(
        issue.startswith("actual_tree_unreadable:")
        for issue in strict_report.issues
    ):
        return strict_report
    owner_by_path = {
        owner.path: owner for owner in manifest.model_projection_owner_paths
    }
    issues = [
        issue
        for issue in strict_report.issues
        if not (
            issue.startswith("file_digest_mismatch:")
            and (
                issue.removeprefix("file_digest_mismatch:") in owner_by_path
                or (
                    allow_ollama_dynamic
                    and issue
                    == "file_digest_mismatch:config/models.json"
                )
            )
        )
    ]
    digest_by_path = {
        item.path: item.content_sha256 for item in manifest.files
    }
    for path, owner in sorted(owner_by_path.items()):
        expected_model_id = (
            ordinary_model_id
            if owner.role is ModelRole.ORDINARY
            else thinking_model_id
        )
        workspace_path = workspace_root / path
        package_path = package_config_root / Path(path).relative_to("config")
        try:
            package_bytes = package_path.read_bytes()
            if _sha256_bytes(package_bytes) != digest_by_path[path]:
                issues.append(f"package_source_digest_mismatch:{path}")
                continue
            package_value = cast(
                JsonValue,
                json.loads(package_bytes.decode("utf-8")),
            )
            actual_value = cast(
                JsonValue,
                json.loads(workspace_path.read_text(encoding="utf-8")),
            )
            expected_value = _owner_document_with_default(
                package_value,
                default_model_id=expected_model_id,
                context=f"package:{path}",
            )
            if actual_value != expected_value:
                issues.append(f"model_projection_mismatch:{path}")
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ManifestValidationError,
            ValueError,
        ) as error:
            issues.append(
                f"model_projection_unreadable:{path}:{type(error).__name__}"
            )
    if allow_ollama_dynamic:
        try:
            package_models_bytes = (
                package_config_root / "models.json"
            ).read_bytes()
            if _sha256_bytes(package_models_bytes) != digest_by_path[
                "config/models.json"
            ]:
                raise ManifestValidationError(
                    "package models.json 与冻结 digest 不一致"
                )
            package_models_value = cast(
                JsonValue,
                json.loads(package_models_bytes.decode("utf-8")),
            )
            actual_models_value = cast(
                JsonValue,
                json.loads(
                    (workspace_root / "config/models.json").read_text(
                        encoding="utf-8"
                    )
                ),
            )
            package_root = _expect_mapping(
                package_models_value,
                "package:models.json",
            )
            actual_root = dict(
                _expect_mapping(actual_models_value, "actual:models.json")
            )
            package_models = _expect_mapping(
                package_root.get("models"),
                "package:models.json.models",
            )
            actual_models = dict(
                _expect_mapping(
                    actual_root.get("models"),
                    "actual:models.json.models",
                )
            )
            package_ollama = _expect_mapping(
                package_models.get("ollama"),
                "package:models.json.models.ollama",
            )
            actual_ollama = dict(
                _expect_mapping(
                    actual_models.get("ollama"),
                    "actual:models.json.models.ollama",
                )
            )
            model_name = _expect_string(
                actual_ollama.get("model"),
                "actual:models.json.models.ollama.model",
            )
            endpoint = _expect_string(
                actual_ollama.get("endpoint"),
                "actual:models.json.models.ollama.endpoint",
            )
            context_window = actual_ollama.get("context_window_tokens")
            if (
                not isinstance(context_window, int)
                or isinstance(context_window, bool)
            ):
                raise ManifestValidationError(
                    "Ollama context_window_tokens 必须是整数"
                )
            OllamaModelSettings(
                model_name=model_name,
                endpoint=endpoint,
                context_window_tokens=context_window,
            )
            for field_name in (
                "model",
                "endpoint",
                "context_window_tokens",
            ):
                actual_ollama[field_name] = package_ollama[field_name]
            actual_models["ollama"] = cast(JsonValue, actual_ollama)
            actual_root["models"] = cast(JsonValue, actual_models)
            if actual_root != package_root:
                issues.append("ollama_dynamic_projection_mismatch")
        except (
            OSError,
            json.JSONDecodeError,
            ManifestValidationError,
            ValueError,
        ) as error:
            issues.append(
                f"ollama_dynamic_projection_unreadable:{type(error).__name__}"
            )
    unique_issues = tuple(dict.fromkeys(issues))
    return PublicationValidationReport(
        valid=not unique_issues,
        issues=unique_issues,
        actual_directories=strict_report.actual_directories,
        actual_files=strict_report.actual_files,
        actual_model_owner_paths=strict_report.actual_model_owner_paths,
    )


def classify_preflight(
    *,
    credential_required: bool,
    credential_present: bool,
    endpoint_required: bool,
    endpoint_configured: bool,
    service_reachable: bool | None,
) -> PreflightClass:
    """按外部前置条件对 provider row 做纯函数分类。

    参数：
        credential_required：该 provider 是否要求 credential。
        credential_present：所需 credential ref 是否已有值。
        endpoint_required：该选择是否要求用户显式配置 endpoint。
        endpoint_configured：所需 endpoint 是否已配置。
        service_reachable：服务探测结果；不适用或未探测时为 ``None``。

    返回：
        按 credential、endpoint、service 顺序得到的唯一 preflight class。

    异常：
        本函数不主动抛出异常。
    """

    if credential_required and not credential_present:
        return PreflightClass.CREDENTIAL_MISSING
    if endpoint_required and not endpoint_configured:
        return PreflightClass.ENDPOINT_UNCONFIGURED
    if service_reachable is False:
        return PreflightClass.SERVICE_UNREACHABLE
    return PreflightClass.REQUESTABLE


def classify_availability(evidence: AvailabilityEvidence) -> AvailabilityClass:
    """根据 typed 观测值裁决最终 provider availability。

    参数：
        evidence：preflight、请求、响应、退出码与失败类别的同源观测。

    返回：
        唯一最终 availability class；矛盾或无法证明的状态 fail closed 为
        ``internal_product_bug``。

    异常：
        本函数不主动抛出异常。
    """

    if (
        not evidence.internal_contract_valid
        or evidence.failure_kind is FailureKind.INTERNAL_PRODUCT_BUG
    ):
        return AvailabilityClass.INTERNAL_PRODUCT_BUG

    if evidence.preflight_class is PreflightClass.CREDENTIAL_MISSING:
        if (
            evidence.exit_code != 0
            and not evidence.request_attempted
            and not evidence.response_received
        ):
            return AvailabilityClass.CREDENTIAL_MISSING
        return AvailabilityClass.INTERNAL_PRODUCT_BUG

    if evidence.preflight_class is PreflightClass.ENDPOINT_UNCONFIGURED:
        if (
            evidence.exit_code != 0
            and not evidence.request_attempted
            and not evidence.response_received
        ):
            return AvailabilityClass.ENDPOINT_UNCONFIGURED
        return AvailabilityClass.INTERNAL_PRODUCT_BUG

    if evidence.preflight_class is PreflightClass.SERVICE_UNREACHABLE:
        if evidence.exit_code != 0 and not evidence.response_received:
            return AvailabilityClass.SERVICE_UNREACHABLE
        return AvailabilityClass.INTERNAL_PRODUCT_BUG

    if (
        evidence.failure_kind is FailureKind.NONE
        and evidence.exit_code == 0
        and evidence.request_attempted
        and evidence.response_received
    ):
        return AvailabilityClass.AVAILABLE
    if (
        evidence.failure_kind is FailureKind.TRANSPORT
        and evidence.exit_code != 0
        and evidence.request_attempted
        and not evidence.response_received
    ):
        return AvailabilityClass.SERVICE_UNREACHABLE
    if (
        evidence.failure_kind is FailureKind.PROVIDER_REJECTED
        and evidence.exit_code != 0
        and evidence.request_attempted
        and not evidence.response_received
    ):
        return AvailabilityClass.PROVIDER_REJECTED
    if (
        evidence.failure_kind is FailureKind.RATE_LIMITED
        and evidence.exit_code != 0
        and evidence.request_attempted
        and not evidence.response_received
    ):
        return AvailabilityClass.RATE_LIMITED
    return AvailabilityClass.INTERNAL_PRODUCT_BUG


def redact_endpoint(endpoint: str) -> RedactedEndpoint:
    """将 endpoint 投影为不含 secret-bearing 组件的稳定身份。

    参数：
        endpoint：待脱敏的绝对 HTTP(S) endpoint。

    返回：
        仅含 scheme、hostname、port 与 path digest 的身份。

    异常：
        ValueError：endpoint 缺少合法 scheme/hostname，或 port 非法。
    """

    parsed = urlsplit(endpoint)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname
    if scheme not in {"http", "https"} or hostname is None:
        raise ValueError("endpoint 必须是含 hostname 的绝对 HTTP(S) URL")
    return RedactedEndpoint(
        scheme=scheme,
        hostname=hostname.lower(),
        port=parsed.port,
        path_sha256=_sha256_bytes(parsed.path.encode("utf-8")),
    )


def summarize_bounded_text(
    text: str,
    *,
    preview_limit: int = DEFAULT_PREVIEW_LIMIT,
) -> BoundedTextSummary:
    """生成长度有界且可复核的文本摘要。

    参数：
        text：response 或 diagnostic 原文。
        preview_limit：允许保留的最大字符数。

    返回：
        原文字符长度、UTF-8 SHA-256 与 bounded preview。

    异常：
        ValueError：preview_limit 小于零。
    """

    if preview_limit < 0:
        raise ValueError("preview_limit 不得小于零")
    return BoundedTextSummary(
        length=len(text),
        sha256=_sha256_bytes(text.encode("utf-8")),
        preview=text[:preview_limit],
        marker_present="S5B_OK" in text,
    )


def scan_secrets(
    report_text: str,
    *,
    canaries: Sequence[str] = (),
    credential_values: Sequence[str] = (),
    forbidden_path_prefixes: Sequence[Path] = (),
) -> SecretScanReport:
    """扫描最终 report，且不在 finding 中回显 secret 或绝对路径。

    参数：
        report_text：待发布或持久化的完整 report 文本。
        canaries：专用于验证泄漏检测的 secret canary。
        credential_values：当前进程已知的真实 credential 值。
        forbidden_path_prefixes：正式报告中禁止出现的已知绝对根路径。

    返回：
        是否通过以及不含 secret 本身的稳定 finding code。

    异常：
        ValueError：探针为空，或 forbidden path 不是绝对路径。
    """

    if any(not value for value in canaries):
        raise ValueError("canaries 不得包含空字符串")
    if any(not value for value in credential_values):
        raise ValueError("credential_values 不得包含空字符串")
    if any(not path.is_absolute() for path in forbidden_path_prefixes):
        raise ValueError("forbidden_path_prefixes 必须全部是绝对路径")

    findings: list[str] = []
    if AUTHORIZATION_PATTERN.search(report_text) is not None:
        findings.append("authorization_value")
    if BEARER_PATTERN.search(report_text) is not None:
        findings.append("bearer_token")
    if CREDENTIAL_VALUE_PATTERN.search(report_text) is not None:
        findings.append("credential_field_value")
    if any(canary in report_text for canary in canaries):
        findings.append("secret_canary")
    if any(value in report_text for value in credential_values):
        findings.append("credential_value")
    if any(str(path) in report_text for path in forbidden_path_prefixes):
        findings.append("absolute_path")
    finding_codes = tuple(sorted(set(findings)))
    return SecretScanReport(
        passed=not finding_codes,
        finding_codes=finding_codes,
    )


def _persisted_artifact_class(
    relative_path: PurePosixPath,
) -> PersistedArtifactClass:
    """把 row-relative 文件路径归入不暴露具体文件名的稳定类别。

    参数：
        relative_path：相对 CI-owned row root 的 POSIX 路径。

    返回：
        config、Host SQLite/WAL、trace/log/artifact 或其它类别。

    异常：
        本函数不主动抛出异常。
    """

    parts = relative_path.parts
    if parts[:2] == ("workspace", "config"):
        return PersistedArtifactClass.CONFIG
    if parts[:4] == ("workspace", ".dayu", "host", "dayu_host.sqlite3"):
        return PersistedArtifactClass.HOST_SQLITE
    if parts[:4] == (
        "workspace",
        ".dayu",
        "host",
        "dayu_host.sqlite3-wal",
    ):
        return PersistedArtifactClass.HOST_SQLITE_WAL
    if (
        parts[:3] == ("workspace", ".dayu", "artifacts")
        or "trace" in relative_path.name.lower()
        or "log" in relative_path.name.lower()
        or "artifact" in relative_path.name.lower()
    ):
        return PersistedArtifactClass.TRACE_LOG_ARTIFACT
    return PersistedArtifactClass.ROW_OTHER


def _record_persisted_violation(
    accumulator: _PersistedScanAccumulator,
    *,
    violation_code: str,
    artifact_class: PersistedArtifactClass,
    count: int = 1,
) -> None:
    """向内部 accumulator 聚合一个不含敏感值的 policy violation。

    参数：
        accumulator：当前 row 扫描状态。
        violation_code：稳定 violation code。
        artifact_class：稳定相对 artifact 类别。
        count：本次新增命中数。

    返回：
        无返回值。

    异常：
        ValueError：count 非正数。
    """

    if count <= 0:
        raise ValueError("persisted violation count 必须为正数")
    key = (violation_code, artifact_class)
    accumulator.violation_counts[key] = (
        accumulator.violation_counts.get(key, 0) + count
    )


def _record_accepted_persistence_observation(
    accumulator: _PersistedScanAccumulator,
    *,
    observation_code: str,
    artifact_class: PersistedArtifactClass,
    count: int = 1,
) -> None:
    """聚合 Host SQLite 中允许存在的 credential 明文观测。

    参数：
        accumulator：当前 row 扫描状态。
        observation_code：稳定 observation code。
        artifact_class：Host SQLite 或其 WAL 类别。
        count：本次新增命中数。

    返回：
        无返回值。

    异常：
        ValueError：类别不是 Host SQLite/WAL，或 count 非正数。
    """

    if artifact_class not in {
        PersistedArtifactClass.HOST_SQLITE,
        PersistedArtifactClass.HOST_SQLITE_WAL,
    }:
        raise ValueError("accepted credential observation 只属于 Host SQLite/WAL")
    if count <= 0:
        raise ValueError("persisted observation count 必须为正数")
    key = (observation_code, artifact_class)
    accumulator.accepted_observation_counts[key] = (
        accumulator.accepted_observation_counts.get(key, 0) + count
    )


def _read_persisted_regular_file(
    *,
    parent_fd: int,
    name: str,
    expected_stat: os.stat_result,
    artifact_class: PersistedArtifactClass,
    credential_probes: Sequence[bytes],
    canary_probes: Sequence[bytes],
    accumulator: _PersistedScanAccumulator,
) -> None:
    """no-follow 打开并有界扫描一个已枚举的普通文件。

    参数：
        parent_fd：文件父目录描述符。
        name：相对父目录的单段文件名。
        expected_stat：枚举阶段的 no-follow stat。
        artifact_class：报告使用的稳定相对类别。
        credential_probes：已知 credential 的精确 bytes 探针。
        canary_probes：canary 的精确或稳定前缀 bytes 探针。
        accumulator：当前 row 扫描状态。

    返回：
        无返回值。

    异常：
        本函数把 OSError 与竞态转为 fail-closed violation，不向外传播。
    """

    if expected_stat.st_size > PERSISTED_SCAN_MAX_FILE_BYTES:
        _record_persisted_violation(
            accumulator,
            violation_code="persisted_scan_file_bytes_limit",
            artifact_class=artifact_class,
        )
        return
    if (
        accumulator.scanned_byte_count + expected_stat.st_size
        > PERSISTED_SCAN_MAX_TOTAL_BYTES
    ):
        _record_persisted_violation(
            accumulator,
            violation_code="persisted_scan_total_bytes_limit",
            artifact_class=artifact_class,
        )
        accumulator.stopped = True
        return

    file_fd = -1
    try:
        file_fd = os.open(
            name,
            os.O_RDONLY | PERSISTED_SCAN_NOFOLLOW_FLAG,
            dir_fd=parent_fd,
        )
        opened_stat = os.fstat(file_fd)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or opened_stat.st_dev != expected_stat.st_dev
            or opened_stat.st_ino != expected_stat.st_ino
        ):
            _record_persisted_violation(
                accumulator,
                violation_code="persisted_scan_node_race",
                artifact_class=artifact_class,
            )
            return
        chunks: list[bytes] = []
        bytes_read = 0
        while True:
            chunk = os.read(file_fd, PERSISTED_SCAN_READ_CHUNK_BYTES)
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > PERSISTED_SCAN_MAX_FILE_BYTES:
                _record_persisted_violation(
                    accumulator,
                    violation_code="persisted_scan_file_bytes_limit",
                    artifact_class=artifact_class,
                )
                return
            if (
                accumulator.scanned_byte_count + bytes_read
                > PERSISTED_SCAN_MAX_TOTAL_BYTES
            ):
                _record_persisted_violation(
                    accumulator,
                    violation_code="persisted_scan_total_bytes_limit",
                    artifact_class=artifact_class,
                )
                accumulator.stopped = True
                return
            chunks.append(chunk)
        content = b"".join(chunks)
    except OSError:
        _record_persisted_violation(
            accumulator,
            violation_code="persisted_scan_io_error",
            artifact_class=artifact_class,
        )
        return
    finally:
        if file_fd >= 0:
            os.close(file_fd)

    accumulator.scanned_file_count += 1
    accumulator.scanned_byte_count += len(content)
    credential_count = sum(content.count(probe) for probe in credential_probes)
    if credential_count:
        if artifact_class in {
            PersistedArtifactClass.HOST_SQLITE,
            PersistedArtifactClass.HOST_SQLITE_WAL,
        }:
            _record_accepted_persistence_observation(
                accumulator,
                observation_code="host_sqlite_credential_value",
                artifact_class=artifact_class,
                count=credential_count,
            )
        else:
            _record_persisted_violation(
                accumulator,
                violation_code="persisted_credential_value",
                artifact_class=artifact_class,
                count=credential_count,
            )
    canary_count = sum(content.count(probe) for probe in canary_probes)
    if canary_count:
        _record_persisted_violation(
            accumulator,
            violation_code="persisted_secret_canary",
            artifact_class=artifact_class,
            count=canary_count,
        )


def _scan_persisted_directory(
    *,
    root_fd: int,
    credential_probes: Sequence[bytes],
    canary_probes: Sequence[bytes],
    accumulator: _PersistedScanAccumulator,
) -> None:
    """用目录描述符迭代遍历 row tree，禁止跟随 symlink。

    参数：
        root_fd：已 no-follow 打开的 row root 目录描述符。
        credential_probes：已知 credential bytes 探针。
        canary_probes：canary bytes 探针。
        accumulator：当前 row 扫描状态。

    返回：
        无返回值。

    异常：
        本函数把 OSError 与边界错误转为 fail-closed violation。
    """

    stack: list[tuple[int, PurePosixPath]] = [
        (os.dup(root_fd), PurePosixPath())
    ]
    try:
        while stack and not accumulator.stopped:
            directory_fd, relative_directory = stack.pop()
            try:
                with os.scandir(directory_fd) as entries:
                    ordered_entries = sorted(entries, key=lambda entry: entry.name)
                for entry in ordered_entries:
                    accumulator.node_count += 1
                    relative_path = relative_directory / entry.name
                    artifact_class = _persisted_artifact_class(relative_path)
                    if accumulator.node_count > PERSISTED_SCAN_MAX_NODES:
                        _record_persisted_violation(
                            accumulator,
                            violation_code="persisted_scan_node_limit",
                            artifact_class=artifact_class,
                        )
                        accumulator.stopped = True
                        break
                    try:
                        entry_stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        _record_persisted_violation(
                            accumulator,
                            violation_code="persisted_scan_io_error",
                            artifact_class=artifact_class,
                        )
                        continue
                    mode = entry_stat.st_mode
                    if stat.S_ISLNK(mode):
                        _record_persisted_violation(
                            accumulator,
                            violation_code="persisted_symlink",
                            artifact_class=artifact_class,
                        )
                    elif stat.S_ISDIR(mode):
                        try:
                            child_fd = os.open(
                                entry.name,
                                os.O_RDONLY
                                | PERSISTED_SCAN_DIRECTORY_FLAG
                                | PERSISTED_SCAN_NOFOLLOW_FLAG,
                                dir_fd=directory_fd,
                            )
                            opened_stat = os.fstat(child_fd)
                            if (
                                opened_stat.st_dev != entry_stat.st_dev
                                or opened_stat.st_ino != entry_stat.st_ino
                            ):
                                os.close(child_fd)
                                _record_persisted_violation(
                                    accumulator,
                                    violation_code="persisted_scan_node_race",
                                    artifact_class=artifact_class,
                                )
                            else:
                                stack.append((child_fd, relative_path))
                        except OSError:
                            _record_persisted_violation(
                                accumulator,
                                violation_code="persisted_scan_io_error",
                                artifact_class=artifact_class,
                            )
                    elif stat.S_ISREG(mode):
                        if (
                            accumulator.scanned_file_count
                            >= PERSISTED_SCAN_MAX_FILES
                        ):
                            _record_persisted_violation(
                                accumulator,
                                violation_code="persisted_scan_file_limit",
                                artifact_class=artifact_class,
                            )
                            accumulator.stopped = True
                            break
                        _read_persisted_regular_file(
                            parent_fd=directory_fd,
                            name=entry.name,
                            expected_stat=entry_stat,
                            artifact_class=artifact_class,
                            credential_probes=credential_probes,
                            canary_probes=canary_probes,
                            accumulator=accumulator,
                        )
                    else:
                        _record_persisted_violation(
                            accumulator,
                            violation_code="persisted_special_file",
                            artifact_class=artifact_class,
                        )
            except OSError:
                _record_persisted_violation(
                    accumulator,
                    violation_code="persisted_scan_io_error",
                    artifact_class=PersistedArtifactClass.ROW_OTHER,
                )
            finally:
                os.close(directory_fd)
    finally:
        for directory_fd, _ in stack:
            os.close(directory_fd)


def scan_persisted_secrets(
    row_root: Path,
    *,
    credential_values: Sequence[str],
    canaries: Sequence[str],
) -> PersistedSecretScanReport:
    """扫描 CI-owned row root 的全部普通文件且绝不跟随 symlink。

    参数：
        row_root：一个完成执行的 CI-owned row 根目录。
        credential_values：当前进程已知 credential 的精确值。
        canaries：当前 run 的精确 canary；legacy reconciliation 可为空，
            稳定 canary 前缀仍始终扫描。

    返回：
        有界扫描计数，以及仅含稳定 code、相对 artifact class、count 的 accepted
        observation / violation 报告。

    异常：
        ValueError：row_root 不是绝对路径，或探针包含空字符串。
    """

    if not row_root.is_absolute():
        raise ValueError("row_root 必须是绝对路径")
    if any(not value for value in credential_values):
        raise ValueError("credential_values 不得包含空字符串")
    if any(not value for value in canaries):
        raise ValueError("canaries 不得包含空字符串")

    accumulator = _PersistedScanAccumulator(
        node_count=0,
        scanned_file_count=0,
        scanned_byte_count=0,
        accepted_observation_counts={},
        violation_counts={},
        stopped=False,
    )
    if not PERSISTED_SCAN_NOFOLLOW_SUPPORTED:
        return PersistedSecretScanReport(
            passed=False,
            scanned_file_count=0,
            scanned_byte_count=0,
            accepted_observations=(),
            violations=(
                PersistedSecretViolation(
                    violation_code="persisted_scan_no_follow_unsupported",
                    artifact_class=PersistedArtifactClass.ROW_OTHER,
                    count=1,
                ),
            ),
        )
    credential_probes = tuple(
        value.encode("utf-8")
        for value in sorted(set(credential_values), key=lambda item: (-len(item), item))
    )
    canary_probes = tuple(
        value.encode("utf-8")
        for value in sorted(
            set(canaries) if canaries else {SECRET_CANARY_PREFIX},
            key=lambda item: (-len(item), item),
        )
    )
    root_fd = -1
    try:
        root_stat = os.lstat(row_root)
        if stat.S_ISLNK(root_stat.st_mode):
            _record_persisted_violation(
                accumulator,
                violation_code="persisted_symlink",
                artifact_class=PersistedArtifactClass.ROW_OTHER,
            )
        elif not stat.S_ISDIR(root_stat.st_mode):
            _record_persisted_violation(
                accumulator,
                violation_code="persisted_special_file",
                artifact_class=PersistedArtifactClass.ROW_OTHER,
            )
        else:
            root_fd = os.open(
                row_root,
                os.O_RDONLY
                | PERSISTED_SCAN_DIRECTORY_FLAG
                | PERSISTED_SCAN_NOFOLLOW_FLAG,
            )
            opened_stat = os.fstat(root_fd)
            if (
                opened_stat.st_dev != root_stat.st_dev
                or opened_stat.st_ino != root_stat.st_ino
            ):
                _record_persisted_violation(
                    accumulator,
                    violation_code="persisted_scan_node_race",
                    artifact_class=PersistedArtifactClass.ROW_OTHER,
                )
            else:
                _scan_persisted_directory(
                    root_fd=root_fd,
                    credential_probes=credential_probes,
                    canary_probes=canary_probes,
                    accumulator=accumulator,
                )
    except OSError:
        _record_persisted_violation(
            accumulator,
            violation_code="persisted_scan_io_error",
            artifact_class=PersistedArtifactClass.ROW_OTHER,
        )
    finally:
        if root_fd >= 0:
            os.close(root_fd)

    accepted_observations = tuple(
        PersistedCredentialObservation(
            observation_code=observation_code,
            artifact_class=artifact_class,
            count=count,
        )
        for (observation_code, artifact_class), count in sorted(
            accumulator.accepted_observation_counts.items(),
            key=lambda item: (item[0][0], item[0][1].value),
        )
    )
    violations = tuple(
        PersistedSecretViolation(
            violation_code=violation_code,
            artifact_class=artifact_class,
            count=count,
        )
        for (violation_code, artifact_class), count in sorted(
            accumulator.violation_counts.items(),
            key=lambda item: (item[0][0], item[0][1].value),
        )
    )
    return PersistedSecretScanReport(
        passed=not violations,
        scanned_file_count=accumulator.scanned_file_count,
        scanned_byte_count=accumulator.scanned_byte_count,
        accepted_observations=accepted_observations,
        violations=violations,
    )


def evaluate_no_fallback(evidence: NoFallbackEvidence) -> NoFallbackVerdict:
    """根据 typed identity、run binding 和终态证据裁决是否发生 fallback。

    参数：
        evidence：expected/effective identity、同 run trace、observed set 与替代
            family 成功终态。

    返回：
        可审计的 no-fallback verdict；任一身份漂移都 fail closed。

    异常：
        本函数不主动抛出异常。
    """

    reasons: list[str] = []
    observed_set = frozenset(evidence.observed_identities)
    alternate_identities: frozenset[ProviderIdentity] = frozenset()
    if evidence.alternate_success_observed:
        reasons.append("alternate_success_observed")

    if evidence.request_attempted:
        if evidence.expected_identity is None:
            reasons.append("expected_identity_missing")
        if evidence.effective_identity is None:
            reasons.append("effective_identity_missing")
        elif (
            evidence.expected_identity is not None
            and evidence.effective_identity != evidence.expected_identity
        ):
            reasons.append("effective_identity_mismatch")
        if evidence.expected_identity is not None:
            alternate_identities = observed_set - {evidence.expected_identity}
            if alternate_identities:
                reasons.append("alternate_identity_observed")
        if (
            evidence.host_run_id is None
            or evidence.trace_run_id is None
            or evidence.host_run_id != evidence.trace_run_id
        ):
            reasons.append("run_binding_mismatch")
        if (
            evidence.expected_identity is None
            or evidence.expected_identity not in observed_set
        ):
            reasons.append("expected_identity_not_observed")
    else:
        if (
            evidence.expected_identity is not None
            or evidence.effective_identity is not None
        ):
            reasons.append("identity_present_without_request")
        if evidence.host_run_id is not None or evidence.trace_run_id is not None:
            reasons.append("unexpected_run_binding")
        if observed_set:
            reasons.append("identity_observed_without_request")

    reason_codes = tuple(sorted(set(reasons)))
    fallback_observed = bool(
        alternate_identities or evidence.alternate_success_observed
    )
    return NoFallbackVerdict(
        passed=not reason_codes,
        fallback_observed=fallback_observed,
        reason_codes=reason_codes,
    )


def _run_cli_subprocess(
    argv: Sequence[str],
    *,
    stdin_text: str,
    env: Mapping[str, str],
    cwd: Path,
    timeout_seconds: float,
) -> SubprocessResult:
    """运行一个真实 CLI 子进程并在超时时收口整个进程组。

    参数：
        argv：不含解释器前缀的 CLI 参数。
        stdin_text：完整交互输入；EOF 是 contract 的一部分。
        env：子进程完整环境。
        cwd：子进程工作目录。
        timeout_seconds：正数 wall-clock 时限。

    返回：
        退出码、stdout、stderr 与 timeout 标记。

    异常：
        ValueError：timeout 非正数。
        OSError：子进程无法创建或读取。
    """

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必须为正数")
    process = subprocess.Popen(
        (sys.executable, "-m", "dayu.cli", *argv),
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(
            input=stdin_text,
            timeout=timeout_seconds,
        )
        return SubprocessResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5.0)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return SubprocessResult(
            exit_code=124,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
        )


def _row_environment(
    process_env: Mapping[str, str],
    *,
    home_root: Path,
    canary: str,
) -> dict[str, str]:
    """构造不指向用户 profile 的 fresh row 子进程环境。

    参数：
        process_env：当前进程环境。
        home_root：本 row 的隔离 HOME。
        canary：仅用于最终泄漏扫描的未知环境变量值。

    返回：
        保留真实 credential、但重定向 HOME/XDG 的完整环境。

    异常：
        ValueError：home_root 或 canary 非法。
    """

    if not home_root.is_absolute() or not canary:
        raise ValueError("home_root 必须绝对且 canary 不得为空")
    env = dict(process_env)
    env["HOME"] = str(home_root)
    env["XDG_CONFIG_HOME"] = str(home_root / ".config")
    env["XDG_CACHE_HOME"] = str(home_root / ".cache")
    env["XDG_DATA_HOME"] = str(home_root / ".local/share")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["TERM"] = "dumb"
    env["DAYU_S5B_SECRET_CANARY"] = canary
    return env


def _init_stdin(choice: InitModelChoice, env: Mapping[str, str]) -> str:
    """构造仅使用真实既有 credential 或 EOF 的 init 输入。

    参数：
        choice：当前 catalog 选择。
        env：row 子进程环境。

    返回：
        production init 的完整 stdin 文本。

    异常：
        本函数不主动抛出异常。
    """

    required = choice.required_secret_env_name
    if required is not None and not env.get(required, "").strip():
        if choice.kind is InitModelChoiceKind.CUSTOM_OPENAI:
            return f"{choice.choice_id}\ns5b-custom-model\n\n\n"
        return f"{choice.choice_id}\n"
    if choice.kind is InitModelChoiceKind.CUSTOM_OPENAI:
        return f"{choice.choice_id}\n"
    dynamic_blanks = 3 if choice.kind is InitModelChoiceKind.OLLAMA else 0
    optional_blanks = sum(
        not env.get(name, "").strip() for name in OPTIONAL_ENVIRONMENT_NAMES
    )
    return f"{choice.choice_id}\n" + "\n" * (dynamic_blanks + optional_blanks)


def _config_tree_digest(workspace_root: Path) -> str:
    """计算 init-owned config tree 的路径/内容联合摘要。

    参数：
        workspace_root：row workspace 根目录。

    返回：
        fresh 空树或现有 config tree 的稳定 SHA-256。

    异常：
        OSError：实际树不可读。
        ValueError：config 是 symlink 或含 symlink。
    """

    config_root = workspace_root / "config"
    atoms: list[bytes] = []
    if not config_root.exists():
        return _sha256_bytes(b"absent")
    if not config_root.is_dir() or config_root.is_symlink():
        raise ValueError("config 必须是非 symlink 目录")
    for path in sorted(config_root.rglob("*")):
        if path.is_symlink():
            raise ValueError("config tree 不得包含 symlink")
        relative = path.relative_to(workspace_root).as_posix().encode("utf-8")
        if path.is_dir():
            atoms.append(b"D\0" + relative)
        elif path.is_file():
            atoms.append(
                b"F\0"
                + relative
                + b"\0"
                + _sha256_bytes(path.read_bytes()).encode("ascii")
            )
        else:
            raise ValueError("config tree 含非普通节点")
    return _sha256_bytes(b"\n".join(atoms))


def _profile_publication_observed(home_root: Path) -> bool:
    """检查隔离 HOME 是否出现 shell profile publication。

    参数：
        home_root：本 row 的 fresh HOME。

    返回：
        任一已知 profile 文件存在时为真。

    异常：
        OSError：HOME tree 不可枚举。
    """

    return any(
        path.is_file() and path.name in PROFILE_FILE_NAMES
        for path in home_root.rglob("*")
    )


def _redact_sensitive_text(
    text: str,
    *,
    credential_values: Sequence[str],
    canary: str,
    project_root: Path,
    run_root: Path,
    workspace_root: Path,
) -> str:
    """在生成 bounded 摘要前移除已知 secret 与明确运行根路径。

    参数：
        text：子进程或 Host 诊断文本。
        credential_values：当前进程已知 credential 值。
        canary：本次运行的 secret canary。
        project_root：显式传入的项目绝对根。
        run_root：显式传入的本次 matrix 绝对根。
        workspace_root：显式传入的当前 row workspace 绝对根。

    返回：
        不含已知 secret、request id value 或上述绝对路径前缀的文本。

    异常：
        ValueError：secret 探针为空，或任一路径不是绝对路径。
    """

    if not canary or any(not value for value in credential_values):
        raise ValueError("secret 扫描输入不得为空")
    roots = (
        (workspace_root, "[WORKSPACE_ROOT]"),
        (run_root, "[RUN_ROOT]"),
        (project_root, "[PROJECT_ROOT]"),
    )
    if any(not root.is_absolute() for root, _ in roots):
        raise ValueError("redaction roots 必须全部是绝对路径")
    redacted = text.replace(canary, "[REDACTED]")
    for value in sorted(set(credential_values), key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    redacted = _redact_explicit_path_prefixes(redacted, roots=roots)
    redacted = AUTHORIZATION_PATTERN.sub("[REDACTED]", redacted)
    redacted = BEARER_PATTERN.sub("[REDACTED]", redacted)
    return REQUEST_ID_VALUE_PATTERN.sub("request_id=[REDACTED]", redacted)


def _redact_explicit_path_prefixes(
    text: str,
    *,
    roots: Sequence[tuple[Path, str]],
) -> str:
    """只替换调用者显式给出的绝对路径前缀。

    参数：
        text：待处理文本。
        roots：绝对根路径及其稳定 replacement。

    返回：
        精确 root 字符串已替换、其它业务文本不变的结果。

    异常：
        ValueError：root 非绝对路径或 replacement 为空。
    """

    if any(not root.is_absolute() or not replacement for root, replacement in roots):
        raise ValueError("path redaction roots 必须绝对且 replacement 不得为空")
    redacted = text
    # 最具体的根先替换，防止 project root 提前吞掉 workspace/run 语义。
    for root, replacement in sorted(
        roots,
        key=lambda item: len(str(item[0])),
        reverse=True,
    ):
        redacted = redacted.replace(str(root), replacement)
    return redacted


async def _read_effective_identities(
    workspace_root: Path,
    package_config_root: Path,
    env: Mapping[str, str],
) -> tuple[EffectiveModelIdentity, EffectiveModelIdentity]:
    """通过 production entrypoint assembly 读取 ordinary/compactor identity。

    参数：
        workspace_root：成功 init 的 row workspace。
        package_config_root：production package config 根目录。
        env：与真实 prompt 子进程相同的环境。

    返回：
        ordinary 与 compactor 的完整 typed identity。

    异常：
        Exception：production runtime location、scene、tool 或 assembly 失败。
    """

    context_slots = build_prompt_context_slot_values(
        ticker=None,
        fmp_api_key=env.get("FMP_API_KEY"),
    )
    runtime = await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root,
            explicit_config_dir=None,
            scene_id="prompt",
            context_slot_values=context_slots,
            assembly_overrides=ServiceAssemblyOverrides(),
            env=env,
        )
    )
    ordinary_selection = runtime.host_assembly.ordinary_selection
    compactor_selection = runtime.host_assembly.compactor_selection
    ordinary_family = model_family_identity(ordinary_selection.model)
    compactor_family = model_family_identity(compactor_selection.model)
    return (
        EffectiveModelIdentity(
            config_model_id=ordinary_selection.model_id,
            provider=ordinary_family.provider,
            provider_model=ordinary_family.provider_model,
            endpoint=redact_endpoint(ordinary_family.endpoint),
            credential_ref=ordinary_family.credential_ref,
        ),
        EffectiveModelIdentity(
            config_model_id=compactor_selection.model_id,
            provider=compactor_family.provider,
            provider_model=compactor_family.provider_model,
            endpoint=redact_endpoint(compactor_family.endpoint),
            credential_ref=compactor_family.credential_ref,
        ),
    )


def _optional_payload_text(
    payload: Mapping[str, DurableJsonValue],
    field_name: str,
) -> str | None:
    """严格读取 canonical payload 的可选文本。

    参数：
        payload：Host owner 已解析的 canonical payload。
        field_name：明确白名单字段名。

    返回：
        非空文本或 ``None``。

    异常：
        ValueError：字段存在但不是非空文本。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} 必须是非空文本或 null")
    return value


def _runner_call_identity(
    transaction: HostTransaction,
    signal_index: int,
    run_id: str,
) -> RunnerCallIdentity:
    """解析并白名单投影一条 owner-validated runner-call。

    参数：
        transaction：Host durable read transaction。
        signal_index：目标 runner-call signal 的稳定索引。
        run_id：当前唯一 Host run id。

    返回：
        manifest/ref/digest 与 frozen provider/model identity。

    异常：
        ValueError：signal 或 sizing contract 不完整。
        HostDurableError：durable resolver 校验失败时透传。
    """

    page = read_runner_call_reconstruction_signals_by_run(
        transaction,
        run_id,
        after_event_sequence=0,
        limit=TOOL_TRACE_QUERY_MAX_LIMIT,
    )
    if page.has_more or signal_index >= len(page.signals):
        raise ValueError("runner-call signal 分页或索引不完整")
    signal = page.signals[signal_index]
    if (
        signal.run_id != run_id
        or signal.diagnostic.status is not RunnerCallReconstructionStatus.COMPLETE
        or signal.manifest_ref is None
        or signal.manifest_digest is None
        or signal.input_projection_digest is None
    ):
        raise ValueError("runner-call reconstruction signal 不完整")
    resolved = resolve_runner_call_projection_from_signal(transaction, signal)
    trace_page = read_tool_trace_page(
        transaction,
        after_event_sequence=0,
        limit=TOOL_TRACE_QUERY_MAX_LIMIT,
    )
    matching_rows = tuple(
        row for row in trace_page.rows if row.event_id == signal.event_id
    )
    if trace_page.has_more or len(matching_rows) != 1:
        raise ValueError("runner-call hot row 不唯一")
    resolved_hot = resolve_tool_trace_hot_row_payloads(
        transaction,
        matching_rows[0],
    )
    typed_manifest = parse_runner_call_manifest(
        resolved.manifest.payload,
        hot_payload=parse_runner_call_hot_payload(
            resolved_hot.source_event_payload
        ),
    )
    sizing = typed_manifest.sizing_snapshot
    if (
        sizing.status is not RunnerCallSizingStatus.COMPLETE
        or sizing.provider is None
        or sizing.model is None
    ):
        raise ValueError("runner-call sizing identity 不完整")
    return RunnerCallIdentity(
        event_id=signal.event_id,
        manifest_ref=signal.manifest_ref,
        manifest_digest=signal.manifest_digest,
        input_projection_digest=signal.input_projection_digest,
        provider=sizing.provider,
        provider_model=sizing.model,
    )


def _read_host_observation_transaction(
    transaction: HostTransaction,
) -> HostObservation:
    """从 fresh Host store 读取唯一 run 的真实 terminal 与 runner-call 证据。

    参数：
        transaction：Host durable read transaction。

    返回：
        只含白名单 identity、布尔 truth 与 bounded 前原文的观测。

    异常：
        ValueError：fresh store 不含唯一 run/terminal 或 contract 不完整。
        HostDurableError：durable owner 校验失败时透传。
    """

    page = read_tool_trace_page(
        transaction,
        after_event_sequence=0,
        limit=TOOL_TRACE_QUERY_MAX_LIMIT,
    )
    if page.has_more:
        raise ValueError("fresh Host Tool Trace 超出单页上限")
    run_ids = tuple(
        sorted({row.run_id for row in page.rows if row.run_id is not None})
    )
    if len(run_ids) != 1:
        raise ValueError(f"fresh Host store 必须且只能含一个 run，实际 {len(run_ids)}")
    run_id = run_ids[0]
    run_rows = tuple(row for row in page.rows if row.run_id == run_id)
    terminal_rows = tuple(
        row
        for row in run_rows
        if row.event_type
        in {"RUN_SUCCEEDED", "RUN_FAILED", "RUN_CANCELLED", "RUN_LOST"}
    )
    if len(terminal_rows) != 1:
        raise ValueError(
            f"fresh Host run 必须且只能含一个 terminal，实际 {len(terminal_rows)}"
        )
    terminal_row = terminal_rows[0]
    resolved_terminal = resolve_tool_trace_hot_row_payloads(
        transaction,
        terminal_row,
    )
    payload = resolved_terminal.source_event_payload
    terminal_error_code = _optional_payload_text(payload, "error_code")
    terminal_message = _optional_payload_text(payload, "message") or ""
    terminal_provider_request_id = _optional_payload_text(
        payload,
        "provider_request_id",
    )
    terminal_correlation_id = _optional_payload_text(
        payload,
        "client_correlation_id",
    )
    signal_page = read_runner_call_reconstruction_signals_by_run(
        transaction,
        run_id,
        after_event_sequence=0,
        limit=TOOL_TRACE_QUERY_MAX_LIMIT,
    )
    if signal_page.has_more:
        raise ValueError("runner-call reconstruction signals 超出单页上限")
    runner_calls = tuple(
        _runner_call_identity(transaction, index, run_id)
        for index in range(len(signal_page.signals))
    )
    provider_request_present = terminal_provider_request_id is not None or any(
        row.provider_request_id is not None for row in run_rows
    )
    correlation_present = terminal_correlation_id is not None
    succeeded = terminal_row.event_type == "RUN_SUCCEEDED"
    external_failure = (
        terminal_error_code in TRANSPORT_ERROR_CODES
        or terminal_error_code in RATE_LIMIT_ERROR_CODES
        or terminal_error_code in PROVIDER_REJECTION_ERROR_CODES
    )
    request_attempted = (
        succeeded
        or external_failure
        or provider_request_present
        or correlation_present
    )
    return HostObservation(
        internal_contract_valid=bool(runner_calls),
        host_run_id=run_id,
        terminal_status=(
            TerminalStatus.SUCCEEDED if succeeded else TerminalStatus.FAILED
        ),
        terminal_error_code=terminal_error_code,
        terminal_text=terminal_message,
        request_attempted=request_attempted,
        successful_response_received=succeeded,
        provider_request_id_present=provider_request_present,
        client_correlation_id_present=correlation_present,
        runner_calls=runner_calls,
    )


def _read_host_observation(workspace_root: Path) -> HostObservation:
    """打开 fresh workspace 的 production Host read store。

    参数：
        workspace_root：真实 prompt 使用的 row workspace。

    返回：
        canonical terminal 与 Tool Trace owner 证据。

    异常：
        OSError：Host store 或 artifact root 不可读。
        HostDurableError：durable owner contract 校验失败。
        ValueError：fresh store identity 不唯一或证据不完整。
    """

    observation: HostObservation | None = None
    with open_host_durable_read_store(
        db_path=workspace_root / HOST_DB_RELATIVE_PATH,
        artifact_root=workspace_root / HOST_ARTIFACT_RELATIVE_PATH,
        sqlite_policy=HostSQLiteStoragePolicy(),
    ) as store:
        observation = store.run_read(_read_host_observation_transaction)
    if observation is None:
        raise RuntimeError("Host durable read store 未产生观测")
    return observation


def _failure_kind(
    *,
    preflight: PreflightClass,
    observation: HostObservation | None,
    prompt_result: SubprocessResult | None,
) -> FailureKind:
    """把 owner error code 映射为 matrix failure kind。

    参数：
        preflight：row 的前置分类。
        observation：Host canonical 观测；未运行时为 ``None``。
        prompt_result：真实 prompt 子进程结果；未运行时为 ``None``。

    返回：
        唯一 failure kind；未知、timeout 或缺 owner 证据 fail closed。

    异常：
        本函数不主动抛出异常。
    """

    if preflight is not PreflightClass.REQUESTABLE:
        return FailureKind.NONE
    if observation is None or prompt_result is None or prompt_result.timed_out:
        return FailureKind.INTERNAL_PRODUCT_BUG
    if observation.terminal_status is TerminalStatus.SUCCEEDED:
        return FailureKind.NONE
    error_code = observation.terminal_error_code
    if error_code in TRANSPORT_ERROR_CODES:
        return FailureKind.TRANSPORT
    if error_code in RATE_LIMIT_ERROR_CODES:
        return FailureKind.RATE_LIMITED
    if error_code in PROVIDER_REJECTION_ERROR_CODES:
        return FailureKind.PROVIDER_REJECTED
    return FailureKind.INTERNAL_PRODUCT_BUG


def matrix_exit_code(rows: Sequence[ProviderMatrixRowReport]) -> int:
    """按 S5-B fail-closed 规则计算总体退出码。

    参数：
        rows：全部 provider row report。

    返回：
        完整、无内部错误/泄漏/fallback，且每个 availability class 的证据
        contract 自洽时为零；否则为一。

    异常：
        本函数不主动抛出异常。
    """

    if len(rows) != MATRIX_ROW_COUNT:
        return 1
    for row in rows:
        if (
            not row.internal_contract_valid
            or row.availability_class is AvailabilityClass.INTERNAL_PRODUCT_BUG
            or not row.no_fallback.passed
            or row.no_fallback.fallback_observed
            or not row.secret_scan.passed
            or not row.persisted_secret_scan.passed
            or not _availability_evidence_contract_valid(row)
        ):
            return 1
    return 0


def _availability_evidence_contract_valid(
    row: ProviderMatrixRowReport,
) -> bool:
    """校验 row 最终 availability 与真实 evidence 是否自洽。

    参数：
        row：完整 provider matrix row。

    返回：
        available 或正确 external unavailable 的证据满足封闭 contract 时为真；
        internal、矛盾或不完整 evidence 为假。

    异常：
        本函数不主动抛出异常。
    """

    availability = row.availability_class
    if availability is AvailabilityClass.INTERNAL_PRODUCT_BUG:
        return False
    if availability is AvailabilityClass.AVAILABLE:
        return (
            row.preflight_class is PreflightClass.REQUESTABLE
            and row.init_exit_code == 0
            and row.prompt_exit_code == 0
            and row.publication_valid
            and not row.publication_issues
            and row.ordinary_identity is not None
            and row.compactor_identity is not None
            and row.request_attempted
            and row.successful_response_received
            and row.host_run_id is not None
            and bool(row.runner_calls)
            and row.terminal_status is TerminalStatus.SUCCEEDED
        )
    if availability in {
        AvailabilityClass.CREDENTIAL_MISSING,
        AvailabilityClass.ENDPOINT_UNCONFIGURED,
    }:
        expected_preflight = (
            PreflightClass.CREDENTIAL_MISSING
            if availability is AvailabilityClass.CREDENTIAL_MISSING
            else PreflightClass.ENDPOINT_UNCONFIGURED
        )
        return (
            row.preflight_class is expected_preflight
            and row.init_exit_code != 0
            and row.prompt_exit_code is None
            and row.publication_absent_after_rejection
            and not row.profile_publication_observed
            and not row.request_attempted
            and not row.successful_response_received
            and row.host_run_id is None
            and not row.runner_calls
            and row.terminal_status is TerminalStatus.NOT_RUN
            and row.config_tree_digest_before
            == row.config_tree_digest_after_init
            == row.config_tree_digest_after_prompt
        )
    if availability in {
        AvailabilityClass.SERVICE_UNREACHABLE,
        AvailabilityClass.PROVIDER_REJECTED,
        AvailabilityClass.RATE_LIMITED,
    }:
        preflight_valid = (
            row.preflight_class is PreflightClass.REQUESTABLE
            or (
                availability is AvailabilityClass.SERVICE_UNREACHABLE
                and row.preflight_class is PreflightClass.SERVICE_UNREACHABLE
            )
        )
        return (
            preflight_valid
            and row.init_exit_code == 0
            and row.prompt_exit_code is not None
            and row.prompt_exit_code != 0
            and row.publication_valid
            and not row.publication_issues
            and row.ordinary_identity is not None
            and row.compactor_identity is not None
            and row.request_attempted
            and not row.successful_response_received
            and row.host_run_id is not None
            and bool(row.runner_calls)
            and row.terminal_status is TerminalStatus.FAILED
        )
    return False


def _endpoint_json(endpoint: RedactedEndpoint) -> dict[str, JsonValue]:
    """把脱敏 endpoint 投影为 JSON object。

    参数：
        endpoint：已移除 userinfo/query/fragment 的 endpoint。

    返回：
        可安全写入 report 的 JSON object。

    异常：
        本函数不主动抛出异常。
    """

    return {
        "scheme": endpoint.scheme,
        "hostname": endpoint.hostname,
        "port": endpoint.port,
        "path_sha256": endpoint.path_sha256,
    }


def _effective_identity_json(
    identity: EffectiveModelIdentity | None,
) -> JsonValue:
    """把 effective identity 投影为安全 JSON。

    参数：
        identity：production assembly identity；未装配时为 ``None``。

    返回：
        ``null`` 或不含 credential value/full endpoint 的 object。

    异常：
        本函数不主动抛出异常。
    """

    if identity is None:
        return None
    return {
        "config_model_id": identity.config_model_id,
        "provider": identity.provider,
        "provider_model": identity.provider_model,
        "endpoint": _endpoint_json(identity.endpoint),
        "credential_ref": identity.credential_ref,
    }


def _bounded_summary_json(summary: BoundedTextSummary) -> dict[str, JsonValue]:
    """把 bounded 文本摘要投影为 JSON。

    参数：
        summary：已脱敏 bounded 摘要。

    返回：
        长度、摘要和 preview object。

    异常：
        本函数不主动抛出异常。
    """

    return {
        "length": summary.length,
        "sha256": summary.sha256,
        "preview": summary.preview,
        "marker_present": summary.marker_present,
    }


def _secret_scan_json(scan: SecretScanReport) -> dict[str, JsonValue]:
    """把 secret scan 结果投影为不回显 secret 的 JSON。

    参数：
        scan：扫描结果。

    返回：
        passed 与稳定 finding code object。

    异常：
        本函数不主动抛出异常。
    """

    return {
        "passed": scan.passed,
        "finding_codes": list(scan.finding_codes),
    }


def _no_fallback_json(
    verdict: NoFallbackVerdict,
) -> dict[str, JsonValue]:
    """把 no-fallback verdict 投影为稳定 JSON object。

    参数：
        verdict：由 canonical identity/trace evidence 计算的 typed verdict。

    返回：
        passed、fallback observation 与稳定 reason codes。

    异常：
        本函数不主动抛出异常。
    """

    return {
        "passed": verdict.passed,
        "fallback_observed": verdict.fallback_observed,
        "reason_codes": list(verdict.reason_codes),
    }


def _persisted_secret_scan_json(
    scan: PersistedSecretScanReport,
) -> dict[str, JsonValue]:
    """把持久化扫描投影为不含路径和敏感值的 JSON。

    参数：
        scan：一个 row root 的 typed persisted scan。

    返回：
        扫描计数、允许的 Host observation 与 policy violation。

    异常：
        本函数不主动抛出异常。
    """

    accepted_observations: list[JsonValue] = [
        {
            "observation_code": observation.observation_code,
            "artifact_class": observation.artifact_class.value,
            "count": observation.count,
        }
        for observation in scan.accepted_observations
    ]
    violations: list[JsonValue] = [
        {
            "violation_code": violation.violation_code,
            "artifact_class": violation.artifact_class.value,
            "count": violation.count,
        }
        for violation in scan.violations
    ]
    return {
        "passed": scan.passed,
        "scanned_file_count": scan.scanned_file_count,
        "scanned_byte_count": scan.scanned_byte_count,
        "accepted_observations": accepted_observations,
        "violations": violations,
    }


def _row_json(row: ProviderMatrixRowReport) -> dict[str, JsonValue]:
    """把 typed row 投影为最终报告白名单 JSON。

    参数：
        row：完整 row report。

    返回：
        不含 workspace/home 路径、credential value 或原始 payload 的 object。

    异常：
        本函数不主动抛出异常。
    """

    runner_calls: list[JsonValue] = [
        {
            "event_id": call.event_id,
            "manifest_ref": call.manifest_ref,
            "manifest_digest": call.manifest_digest,
            "input_projection_digest": call.input_projection_digest,
            "provider": call.provider,
            "provider_model": call.provider_model,
        }
        for call in row.runner_calls
    ]
    return {
        "scenario_id": row.scenario_id,
        "choice_id": row.choice_id,
        "role_coverage": list(row.role_coverage),
        "expected_ordinary_model_id": row.expected_ordinary_model_id,
        "expected_compactor_model_id": row.expected_compactor_model_id,
        "required_credential_ref": row.required_credential_ref,
        "credential_present": row.credential_present,
        "preflight_class": row.preflight_class.value,
        "availability_class": row.availability_class.value,
        "init_exit_code": row.init_exit_code,
        "prompt_exit_code": row.prompt_exit_code,
        "publication_valid": row.publication_valid,
        "publication_issues": list(row.publication_issues),
        "publication_absent_after_rejection": (
            row.publication_absent_after_rejection
        ),
        "profile_publication_observed": row.profile_publication_observed,
        "config_tree_digest_before": row.config_tree_digest_before,
        "config_tree_digest_after_init": row.config_tree_digest_after_init,
        "config_tree_digest_after_prompt": row.config_tree_digest_after_prompt,
        "request_attempted": row.request_attempted,
        "successful_response_received": row.successful_response_received,
        "provider_request_id_present": row.provider_request_id_present,
        "client_correlation_id_present": row.client_correlation_id_present,
        "host_run_id": row.host_run_id,
        "ordinary_identity": _effective_identity_json(row.ordinary_identity),
        "compactor_identity": _effective_identity_json(row.compactor_identity),
        "runner_calls": runner_calls,
        "terminal_status": row.terminal_status.value,
        "terminal_summary": _bounded_summary_json(row.terminal_summary),
        "no_fallback": _no_fallback_json(row.no_fallback),
        "secret_scan": _secret_scan_json(row.secret_scan),
        "persisted_secret_scan": _persisted_secret_scan_json(
            row.persisted_secret_scan
        ),
        "internal_contract_valid": row.internal_contract_valid,
    }


def _report_json(report: ProviderMatrixReport) -> dict[str, JsonValue]:
    """把 typed matrix report 投影为最终 JSON contract。

    参数：
        report：完整 typed report。

    返回：
        可供全文 secret scan 与落盘的白名单 object。

    异常：
        本函数不主动抛出异常。
    """

    return {
        "oracle_id": report.oracle_id,
        "oracle_version": report.oracle_version,
        "matrix_run_id": report.matrix_run_id,
        "started_at": report.started_at,
        "completed_at": report.completed_at,
        "overall_exit_code": report.overall_exit_code,
        "rows": [cast(JsonValue, _row_json(row)) for row in report.rows],
        "secret_scan": _secret_scan_json(report.secret_scan),
    }


def _json_text(value: JsonValue) -> str:
    """生成稳定 UTF-8 JSON 文本。

    参数：
        value：严格 JSON value。

    返回：
        末尾含换行的 pretty JSON 文本。

    异常：
        TypeError：value 不可 JSON 序列化。
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _known_credential_values(env: Mapping[str, str]) -> tuple[str, ...]:
    """收集本进程已知且必须从报告排除的 credential 值。

    参数：
        env：执行 live matrix 的 process env。

    返回：
        去重、非空且不回显名称的 credential value tuple。

    异常：
        本函数不主动抛出异常。
    """

    names = {
        choice.required_secret_env_name
        for choice in INIT_MODEL_CHOICES
        if choice.required_secret_env_name is not None
    }
    names.update(OPTIONAL_ENVIRONMENT_NAMES)
    return tuple(
        sorted(
            {
                value
                for name in names
                if (value := env.get(name, "")).strip()
            },
            key=lambda value: (len(value), value),
            reverse=True,
        )
    )


def _preflight_for_choice(
    choice: InitModelChoice,
    env: Mapping[str, str],
) -> PreflightClass:
    """从 catalog credential ref 与动态 endpoint 条件生成 preflight。

    参数：
        choice：当前 catalog choice。
        env：真实 process-derived row env。

    返回：
        credential 优先、custom endpoint 次之的唯一 preflight class。

    异常：
        本函数不主动抛出异常。
    """

    required = choice.required_secret_env_name
    credential_present = (
        required is None or bool(env.get(required, "").strip())
    )
    return classify_preflight(
        credential_required=required is not None,
        credential_present=credential_present,
        endpoint_required=choice.kind is InitModelChoiceKind.CUSTOM_OPENAI,
        endpoint_configured=False,
        service_reachable=None,
    )


def _effective_contract_valid(
    choice: InitModelChoice,
    ordinary: EffectiveModelIdentity | None,
    compactor: EffectiveModelIdentity | None,
) -> bool:
    """校验 init choice 到 production assembly 的角色投影。

    参数：
        choice：init catalog source choice。
        ordinary：prompt scene ordinary selection。
        compactor：compactor selection。

    返回：
        model id、provider 与 credential ref 全部同源一致时为真。

    异常：
        本函数不主动抛出异常。
    """

    if ordinary is None or compactor is None:
        return False
    required = choice.required_secret_env_name
    return (
        ordinary.config_model_id == choice.thinking_model_id
        and compactor.config_model_id == choice.ordinary_model_id
        and ordinary.provider == choice.expected_provider
        and compactor.provider == choice.expected_provider
        and ordinary.credential_ref == required
        and compactor.credential_ref == required
    )


def _expected_provider_identity(
    choice: InitModelChoice,
    package_config_root: Path,
    *,
    workspace_config_root: Path | None = None,
) -> ProviderIdentity:
    """从 init choice 与 package/init-owned model truth 构造 expected identity。

    provider family 只来自静态 init choice。静态 provider model 来自 package
    ``models.json``；动态 Ollama/custom provider model 来自 init-owned workspace
    publication。两者都经层中立 ConfigLoader 解析继承，且不读取 production
    assembly 或 Tool Trace actual identity。

    参数：
        choice：当前 production init catalog choice。
        package_config_root：冻结 oracle 对应的 package config 根目录。
        workspace_config_root：动态 choice 的 init-owned config 根；静态 choice
            必须为 ``None``。

    返回：
        独立于实际 assembly 的 expected provider family/model identity。

    异常：
        ManifestValidationError：路径、dynamic source、thinking model 或 provider
            contract 非法。
        ConfigLoadError：package/workspace models 无法按 production contract 解析。
    """

    if not package_config_root.is_absolute():
        raise ManifestValidationError("package_config_root 必须是绝对路径")
    dynamic_choice = choice.kind in DYNAMIC_CHOICE_KINDS
    if dynamic_choice:
        if (
            workspace_config_root is None
            or not workspace_config_root.is_absolute()
        ):
            raise ManifestValidationError(
                "dynamic choice 必须提供绝对 init-owned config 根"
            )
    elif workspace_config_root is not None:
        raise ManifestValidationError("static choice 不得读取 workspace expected truth")
    models = ConfigLoader(
        package_config_dir=package_config_root,
    ).load_models(workspace_config_dir=workspace_config_root)
    expected_model = models.models.get(choice.thinking_model_id)
    if expected_model is None:
        raise ManifestValidationError(
            f"package thinking model 缺失：{choice.thinking_model_id}"
        )
    expected_family = model_family_identity(expected_model)
    if expected_family.provider != choice.expected_provider:
        raise ManifestValidationError(
            f"package provider 与 init choice 不一致：{choice.choice_id}"
        )
    return ProviderIdentity(
        family_id=choice.expected_provider,
        provider=choice.expected_provider,
        provider_model=expected_family.provider_model,
    )


def _run_matrix_row(
    choice: InitModelChoice,
    *,
    row_index: int,
    run_root: Path,
    project_root: Path,
    manifest: FrozenPublicationManifest,
    process_env: Mapping[str, str],
    credential_values: Sequence[str],
    canary: str,
) -> ProviderMatrixRowReport:
    """执行一个 fresh workspace/home 的真实 provider matrix row。

    参数：
        choice：production init catalog choice。
        row_index：从一开始的稳定 row 序号。
        run_root：本次 matrix 的 fresh run root。
        project_root：仓库根目录。
        manifest：冻结 publication oracle。
        process_env：调用者真实进程环境。
        credential_values：最终报告禁止出现的已知值。
        canary：最终报告禁止出现的 canary。

    返回：
        完成取证、分类、脱敏与 row secret scan 的 typed report。

    异常：
        OSError：fresh workspace/home 或 subprocess 无法安全创建。
    """

    scenario_id = f"P{row_index:02d}-{choice.choice_id}"
    row_root = run_root / "rows" / scenario_id
    workspace_root = row_root / "workspace"
    home_root = row_root / "home"
    workspace_root.mkdir(parents=True)
    home_root.mkdir()
    env = _row_environment(process_env, home_root=home_root, canary=canary)
    required_ref = choice.required_secret_env_name
    credential_present = (
        required_ref is None or bool(env.get(required_ref, "").strip())
    )
    preflight = _preflight_for_choice(choice, env)
    digest_before = _config_tree_digest(workspace_root)
    init_result = _run_cli_subprocess(
        ("init", "--base", str(workspace_root)),
        stdin_text=_init_stdin(choice, env),
        env=env,
        cwd=project_root,
        timeout_seconds=INIT_TIMEOUT_SECONDS,
    )
    digest_after_init = _config_tree_digest(workspace_root)
    publication_absent = (
        not (workspace_root / "config").exists()
        and not (workspace_root / ".dayu").exists()
    )
    publication_report = PublicationValidationReport(
        valid=False,
        issues=(),
        actual_directories=(),
        actual_files=(),
        actual_model_owner_paths=(),
    )
    ordinary: EffectiveModelIdentity | None = None
    compactor: EffectiveModelIdentity | None = None
    prompt_result: SubprocessResult | None = None
    observation: HostObservation | None = None
    extra_issues: list[str] = []

    if init_result.exit_code == 0:
        publication_report = validate_projected_publication_tree(
            manifest,
            workspace_root,
            project_root / PACKAGE_CONFIG_ROOT,
            ordinary_model_id=choice.ordinary_model_id,
            thinking_model_id=choice.thinking_model_id,
            allow_ollama_dynamic=choice.kind is InitModelChoiceKind.OLLAMA,
        )
        try:
            ordinary, compactor = asyncio.run(
                _read_effective_identities(
                    workspace_root,
                    project_root / PACKAGE_CONFIG_ROOT,
                    env,
                )
            )
        except Exception as error:
            extra_issues.append(
                f"production_assembly_unavailable:{type(error).__name__}"
            )
        prompt_result = _run_cli_subprocess(
            (
                "prompt",
                "--base",
                str(workspace_root),
                "--no-detail",
                "--no-thinking",
                "--max-iterations",
                "1",
                PROMPT_TEXT,
            ),
            stdin_text="",
            env=env,
            cwd=project_root,
            timeout_seconds=PROMPT_TIMEOUT_SECONDS,
        )
        try:
            observation = _read_host_observation(workspace_root)
        except Exception as error:
            extra_issues.append(
                f"host_observation_unavailable:{type(error).__name__}"
            )
    digest_after_prompt = _config_tree_digest(workspace_root)
    profile_observed = _profile_publication_observed(home_root)

    failure_kind = _failure_kind(
        preflight=preflight,
        observation=observation,
        prompt_result=prompt_result,
    )
    request_attempted = (
        observation.request_attempted if observation is not None else False
    )
    response_received = (
        observation.successful_response_received
        if observation is not None
        else False
    )
    effective_valid = _effective_contract_valid(choice, ordinary, compactor)
    if preflight is PreflightClass.REQUESTABLE:
        internal_contract_valid = (
            init_result.exit_code == 0
            and not init_result.timed_out
            and publication_report.valid
            and effective_valid
            and prompt_result is not None
            and observation is not None
            and observation.internal_contract_valid
            and not profile_observed
            and digest_after_init == digest_after_prompt
        )
        classification_exit_code = (
            prompt_result.exit_code if prompt_result is not None else 1
        )
    else:
        internal_contract_valid = (
            init_result.exit_code != 0
            and not init_result.timed_out
            and publication_absent
            and not profile_observed
            and observation is None
            and prompt_result is None
            and digest_before == digest_after_init == digest_after_prompt
        )
        classification_exit_code = init_result.exit_code
    internal_contract_valid = internal_contract_valid and not extra_issues
    availability = classify_availability(
        AvailabilityEvidence(
            preflight_class=preflight,
            internal_contract_valid=internal_contract_valid,
            request_attempted=request_attempted,
            response_received=response_received,
            exit_code=classification_exit_code,
            failure_kind=failure_kind,
        )
    )

    expected_identity: ProviderIdentity | None = None
    effective_identity: ProviderIdentity | None = None
    if ordinary is not None:
        expected_identity = _expected_provider_identity(
            choice,
            project_root / PACKAGE_CONFIG_ROOT,
            workspace_config_root=(
                workspace_root / "config"
                if choice.kind in DYNAMIC_CHOICE_KINDS
                else None
            ),
        )
        effective_identity = ProviderIdentity(
            family_id=ordinary.provider,
            provider=ordinary.provider,
            provider_model=ordinary.provider_model,
        )
    observed_identities = tuple(
        ProviderIdentity(
            family_id=call.provider,
            provider=call.provider,
            provider_model=call.provider_model,
        )
        for call in (() if observation is None else observation.runner_calls)
    )
    host_run_id = None if observation is None else observation.host_run_id
    no_fallback = evaluate_no_fallback(
        NoFallbackEvidence(
            expected_identity=expected_identity,
            effective_identity=effective_identity,
            request_attempted=request_attempted,
            host_run_id=host_run_id,
            trace_run_id=host_run_id if observed_identities else None,
            observed_identities=observed_identities,
            alternate_success_observed=(
                response_received
                and expected_identity is not None
                and any(
                    identity != expected_identity
                    for identity in observed_identities
                )
            ),
        )
    )
    if (
        observation is not None
        and observation.terminal_status is TerminalStatus.FAILED
    ):
        raw_terminal_text = observation.terminal_text
    elif prompt_result is not None:
        raw_terminal_text = prompt_result.stdout + prompt_result.stderr
    else:
        raw_terminal_text = init_result.stdout + init_result.stderr
    safe_terminal_text = _redact_sensitive_text(
        raw_terminal_text,
        credential_values=credential_values,
        canary=canary,
        project_root=project_root,
        run_root=run_root,
        workspace_root=workspace_root,
    )
    provisional_scan = SecretScanReport(passed=True, finding_codes=())
    provisional_persisted_scan = PersistedSecretScanReport(
        passed=True,
        scanned_file_count=0,
        scanned_byte_count=0,
        accepted_observations=(),
        violations=(),
    )
    row = ProviderMatrixRowReport(
        scenario_id=scenario_id,
        choice_id=choice.choice_id,
        role_coverage=ROLE_COVERAGE,
        expected_ordinary_model_id=choice.thinking_model_id,
        expected_compactor_model_id=choice.ordinary_model_id,
        required_credential_ref=required_ref,
        credential_present=credential_present,
        preflight_class=preflight,
        availability_class=availability,
        init_exit_code=init_result.exit_code,
        prompt_exit_code=(
            None if prompt_result is None else prompt_result.exit_code
        ),
        publication_valid=publication_report.valid,
        publication_issues=tuple(publication_report.issues) + tuple(extra_issues),
        publication_absent_after_rejection=publication_absent,
        profile_publication_observed=profile_observed,
        config_tree_digest_before=digest_before,
        config_tree_digest_after_init=digest_after_init,
        config_tree_digest_after_prompt=digest_after_prompt,
        request_attempted=request_attempted,
        successful_response_received=response_received,
        provider_request_id_present=(
            observation.provider_request_id_present
            if observation is not None
            else False
        ),
        client_correlation_id_present=(
            observation.client_correlation_id_present
            if observation is not None
            else False
        ),
        host_run_id=host_run_id,
        ordinary_identity=ordinary,
        compactor_identity=compactor,
        runner_calls=(
            () if observation is None else observation.runner_calls
        ),
        terminal_status=(
            observation.terminal_status
            if observation is not None
            else (
                TerminalStatus.NOT_RUN
                if prompt_result is None
                else TerminalStatus.FAILED
            )
        ),
        terminal_summary=summarize_bounded_text(safe_terminal_text),
        no_fallback=no_fallback,
        secret_scan=provisional_scan,
        persisted_secret_scan=provisional_persisted_scan,
        internal_contract_valid=internal_contract_valid,
    )
    persisted_scan = scan_persisted_secrets(
        row_root,
        credential_values=credential_values,
        canaries=(canary,),
    )
    row = replace(
        row,
        availability_class=(
            row.availability_class
            if persisted_scan.passed
            else AvailabilityClass.INTERNAL_PRODUCT_BUG
        ),
        persisted_secret_scan=persisted_scan,
        internal_contract_valid=(
            row.internal_contract_valid and persisted_scan.passed
        ),
    )
    row_text = _json_text(cast(JsonValue, _row_json(row)))
    row_scan = scan_secrets(
        row_text,
        canaries=(canary,),
        credential_values=credential_values,
        forbidden_path_prefixes=(project_root, run_root, workspace_root),
    )
    return replace(row, secret_scan=row_scan)


def run_live_matrix(
    *,
    project_root: Path,
    process_env: Mapping[str, str],
) -> MatrixExecutionResult:
    """执行全部 15 choices 并在全文扫描通过后写唯一报告。

    参数：
        project_root：仓库根目录。
        process_env：含真实既有 credential 的当前进程环境。

    返回：
        已安全写入的绝对报告路径与 typed report。

    异常：
        OSError：run root/report 无法创建或写入。
        ManifestValidationError：冻结 manifest 非法。
        RuntimeError：最终 report secret scan 未通过。
        ValueError：catalog 数量或 project_root 不符合 contract。
    """

    if not project_root.is_absolute() or not project_root.is_dir():
        raise ValueError("project_root 必须是现有绝对目录")
    if len(INIT_MODEL_CHOICES) != MATRIX_ROW_COUNT:
        raise ValueError("production init catalog 必须固定为 15 choices")
    started = datetime.now(UTC)
    matrix_run_id = (
        started.strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:12]
    )
    run_root = project_root / REPORT_ROOT / matrix_run_id
    run_root.mkdir(parents=True)
    manifest = load_manifest(project_root / FROZEN_MANIFEST_PATH)
    canary = "s5b-canary-" + uuid.uuid4().hex
    credential_values = _known_credential_values(process_env)
    rows: list[ProviderMatrixRowReport] = []
    for index, choice in enumerate(INIT_MODEL_CHOICES, start=1):
        print(
            f"[{index:02d}/{MATRIX_ROW_COUNT}] {choice.choice_id}",
            flush=True,
        )
        rows.append(
            _run_matrix_row(
                choice,
                row_index=index,
                run_root=run_root,
                project_root=project_root,
                manifest=manifest,
                process_env=process_env,
                credential_values=credential_values,
                canary=canary,
            )
        )
    overall_exit = matrix_exit_code(rows)
    provisional_scan = SecretScanReport(passed=True, finding_codes=())
    report = ProviderMatrixReport(
        oracle_id=ORACLE_ID,
        oracle_version=ORACLE_VERSION,
        matrix_run_id=matrix_run_id,
        started_at=started.isoformat(),
        completed_at=datetime.now(UTC).isoformat(),
        overall_exit_code=overall_exit,
        rows=tuple(rows),
        secret_scan=provisional_scan,
    )
    provisional_text = _json_text(cast(JsonValue, _report_json(report)))
    report_scan = scan_secrets(
        provisional_text,
        canaries=(canary,),
        credential_values=credential_values,
        forbidden_path_prefixes=(project_root, run_root),
    )
    report = replace(report, secret_scan=report_scan)
    final_text = _json_text(cast(JsonValue, _report_json(report)))
    final_scan = scan_secrets(
        final_text,
        canaries=(canary,),
        credential_values=credential_values,
        forbidden_path_prefixes=(project_root, run_root),
    )
    if not report_scan.passed or not final_scan.passed:
        raise RuntimeError(
            "matrix report secret scan failed; unsafe report was not written"
        )
    report_path = run_root / "matrix-report.json"
    report_path.write_text(final_text, encoding="utf-8")
    return MatrixExecutionResult(
        report_path=report_path,
        report=report,
    )


def _reconcile_terminal_summary(
    row: dict[str, JsonValue],
    *,
    project_root: Path,
    run_root: Path,
    workspace_root: Path,
    credential_values: Sequence[str],
) -> HostObservation | None:
    """从同 run Host evidence 或既有 preview 重投影安全终端摘要。

    参数：
        row：既有 report 中一个可变 row object。
        project_root：项目绝对根。
        run_root：既有 matrix run 绝对根。
        workspace_root：当前 row workspace 绝对根。
        credential_values：当前进程已知 credential 值。

    返回：
        原位更新 terminal_summary，并返回用于重新裁决 row contract 的只读 Host
        canonical observation；未运行 Host 时返回 ``None``。

    异常：
        ManifestValidationError：既有 terminal_summary 不满足严格 schema。
        ValueError：显式路径根非法。
    """

    summary = _expect_mapping(
        row.get("terminal_summary"),
        "row.terminal_summary",
    )
    _require_exact_keys(
        summary,
        TERMINAL_SUMMARY_JSON_KEYS,
        "row.terminal_summary",
    )
    preview = _expect_text(
        summary.get("preview"),
        "row.terminal_summary.preview",
    )
    host_run_id = row.get("host_run_id")
    if isinstance(host_run_id, str) and host_run_id:
        observation = _read_host_observation(workspace_root)
        if observation.host_run_id != host_run_id:
            raise ManifestValidationError(
                "terminal reconciliation Host run identity 不一致"
            )
        safe_terminal_text = _redact_sensitive_text(
            observation.terminal_text,
            credential_values=credential_values,
            canary="legacy-canary-value-unavailable",
            project_root=project_root,
            run_root=run_root,
            workspace_root=workspace_root,
        )
        row["terminal_summary"] = _bounded_summary_json(
            summarize_bounded_text(safe_terminal_text)
        )
        return observation
    safe_preview = _redact_sensitive_text(
        preview,
        credential_values=credential_values,
        canary="legacy-canary-value-unavailable",
        project_root=project_root,
        run_root=run_root,
        workspace_root=workspace_root,
    )
    row["terminal_summary"] = _bounded_summary_json(
        summarize_bounded_text(safe_preview)
    )
    return None


def _write_existing_report_no_follow(
    report_path: Path,
    *,
    expected_stat: os.stat_result,
    content: str,
) -> None:
    """no-follow 原位覆盖既有 report，不创建 raw backup。

    参数：
        report_path：既有正式 report 路径。
        expected_stat：读取前对 report 执行的 no-follow stat。
        content：已完成全文扫描的安全 JSON 文本。

    返回：
        无返回值。

    异常：
        OSError：report 无法安全打开、写入或 fsync。
        RuntimeError：写入前检测到 inode 竞态。
    """

    if not PERSISTED_SCAN_NOFOLLOW_SUPPORTED:
        raise RuntimeError("当前平台不支持 no-follow report 重签")
    report_fd = os.open(
        report_path,
        os.O_WRONLY | PERSISTED_SCAN_NOFOLLOW_FLAG,
    )
    try:
        opened_stat = os.fstat(report_fd)
        if (
            opened_stat.st_dev != expected_stat.st_dev
            or opened_stat.st_ino != expected_stat.st_ino
            or not stat.S_ISREG(opened_stat.st_mode)
        ):
            raise RuntimeError("matrix report 在重签前发生节点竞态")
        payload = content.encode("utf-8")
        os.ftruncate(report_fd, 0)
        offset = 0
        while offset < len(payload):
            offset += os.write(report_fd, payload[offset:])
        os.fsync(report_fd)
    finally:
        os.close(report_fd)


def _reconciled_effective_identity_contract_valid(
    row: dict[str, JsonValue],
    choice: InitModelChoice,
) -> bool:
    """校验既有 report 中 ordinary/compactor identity 的 owner 投影。

    参数：
        row：严格 row JSON object。
        choice：production init catalog choice。

    返回：
        两个角色的 model/provider/credential ref 均与 choice 同源时为真。

    异常：
        ManifestValidationError：identity 不是预期 JSON object 或字段类型非法。
    """

    ordinary = _expect_mapping(row.get("ordinary_identity"), "row.ordinary_identity")
    compactor = _expect_mapping(
        row.get("compactor_identity"),
        "row.compactor_identity",
    )
    ordinary_ref = ordinary.get("credential_ref")
    compactor_ref = compactor.get("credential_ref")
    required_ref = choice.required_secret_env_name
    if ordinary_ref is not None and not isinstance(ordinary_ref, str):
        raise ManifestValidationError("row.ordinary_identity.credential_ref 非法")
    if compactor_ref is not None and not isinstance(compactor_ref, str):
        raise ManifestValidationError("row.compactor_identity.credential_ref 非法")
    return (
        _expect_string(
            ordinary.get("config_model_id"),
            "row.ordinary_identity.config_model_id",
        )
        == choice.thinking_model_id
        and _expect_string(
            compactor.get("config_model_id"),
            "row.compactor_identity.config_model_id",
        )
        == choice.ordinary_model_id
        and _expect_string(
            ordinary.get("provider"),
            "row.ordinary_identity.provider",
        )
        == choice.expected_provider
        and _expect_string(
            compactor.get("provider"),
            "row.compactor_identity.provider",
        )
        == choice.expected_provider
        and ordinary_ref == required_ref
        and compactor_ref == required_ref
    )


def _reconciled_row_internal_contract_valid(
    row: dict[str, JsonValue],
    *,
    choice: InitModelChoice,
    observation: HostObservation | None,
) -> bool:
    """从非 persistence 证据重新计算既有 row 的 internal contract。

    旧错误 oracle 已把允许的 Host SQLite credential observation 写回
    ``internal_contract_valid=false``，所以 reconciliation 不能沿用该派生值。
    本函数只使用 publication、effective identity、Host canonical observation、
    profile 与 config digest 等原始 contract 证据重算。

    参数：
        row：既有 report 的严格 row JSON object。
        choice：production init catalog choice。
        observation：只读 Host canonical observation；未运行 Host 时为 ``None``。

    返回：
        排除 persistence policy 后的 internal contract verdict。

    异常：
        ManifestValidationError：必要字段类型或 enum 值非法。
    """

    try:
        preflight = PreflightClass(
            _expect_string(row.get("preflight_class"), "row.preflight_class")
        )
    except ValueError as error:
        raise ManifestValidationError("row.preflight_class 非法") from error
    init_exit_code = _expect_int(row.get("init_exit_code"), "row.init_exit_code")
    prompt_exit_value = row.get("prompt_exit_code")
    profile_observed = _expect_bool(
        row.get("profile_publication_observed"),
        "row.profile_publication_observed",
    )
    digest_before = _expect_string(
        row.get("config_tree_digest_before"),
        "row.config_tree_digest_before",
    )
    digest_after_init = _expect_string(
        row.get("config_tree_digest_after_init"),
        "row.config_tree_digest_after_init",
    )
    digest_after_prompt = _expect_string(
        row.get("config_tree_digest_after_prompt"),
        "row.config_tree_digest_after_prompt",
    )
    publication_issues = _expect_list(
        row.get("publication_issues"),
        "row.publication_issues",
    )
    if preflight is PreflightClass.REQUESTABLE:
        if type(prompt_exit_value) is not int:
            raise ManifestValidationError("requestable row.prompt_exit_code 必须是 int")
        host_run_id = _expect_string(row.get("host_run_id"), "row.host_run_id")
        return (
            init_exit_code == 0
            and _expect_bool(
                row.get("publication_valid"),
                "row.publication_valid",
            )
            and not publication_issues
            and _reconciled_effective_identity_contract_valid(row, choice)
            and observation is not None
            and observation.host_run_id == host_run_id
            and observation.internal_contract_valid
            and not profile_observed
            and digest_after_init == digest_after_prompt
        )
    if prompt_exit_value is not None:
        raise ManifestValidationError("non-requestable row.prompt_exit_code 必须为 null")
    return (
        init_exit_code != 0
        and _expect_bool(
            row.get("publication_absent_after_rejection"),
            "row.publication_absent_after_rejection",
        )
        and not profile_observed
        and observation is None
        and digest_before == digest_after_init == digest_after_prompt
    )


def _reconciled_availability_class(
    row: dict[str, JsonValue],
    *,
    internal_contract_valid: bool,
    observation: HostObservation | None,
) -> AvailabilityClass:
    """用 preflight 与 Host canonical error 重新裁决 availability。

    参数：
        row：既有 report 的严格 row JSON object。
        internal_contract_valid：排除 persistence policy 后的 internal verdict。
        observation：只读 Host canonical observation。

    返回：
        可用、外部不可用或内部错误的唯一 availability class。

    异常：
        ManifestValidationError：row 的必要 typed evidence 非法。
    """

    try:
        preflight = PreflightClass(
            _expect_string(row.get("preflight_class"), "row.preflight_class")
        )
    except ValueError as error:
        raise ManifestValidationError("row.preflight_class 非法") from error
    prompt_exit_value = row.get("prompt_exit_code")
    if preflight is PreflightClass.REQUESTABLE:
        if type(prompt_exit_value) is not int:
            raise ManifestValidationError("requestable row.prompt_exit_code 必须是 int")
        if observation is None:
            failure_kind = FailureKind.INTERNAL_PRODUCT_BUG
        elif observation.terminal_status is TerminalStatus.SUCCEEDED:
            failure_kind = FailureKind.NONE
        elif observation.terminal_error_code in TRANSPORT_ERROR_CODES:
            failure_kind = FailureKind.TRANSPORT
        elif observation.terminal_error_code in RATE_LIMIT_ERROR_CODES:
            failure_kind = FailureKind.RATE_LIMITED
        elif observation.terminal_error_code in PROVIDER_REJECTION_ERROR_CODES:
            failure_kind = FailureKind.PROVIDER_REJECTED
        else:
            failure_kind = FailureKind.INTERNAL_PRODUCT_BUG
        classification_exit_code = prompt_exit_value
    else:
        failure_kind = FailureKind.NONE
        classification_exit_code = _expect_int(
            row.get("init_exit_code"),
            "row.init_exit_code",
        )
    return classify_availability(
        AvailabilityEvidence(
            preflight_class=preflight,
            internal_contract_valid=internal_contract_valid,
            request_attempted=_expect_bool(
                row.get("request_attempted"),
                "row.request_attempted",
            ),
            response_received=_expect_bool(
                row.get("successful_response_received"),
                "row.successful_response_received",
            ),
            exit_code=classification_exit_code,
            failure_kind=failure_kind,
        )
    )


def _row_effective_provider_identity(
    row: dict[str, JsonValue],
) -> ProviderIdentity | None:
    """从 row 的 assembly projection 读取 effective ordinary identity。

    参数：
        row：既有 report 的严格 row JSON object。

    返回：
        assembly 未发生时为 ``None``；否则为 provider family/model identity。

    异常：
        ManifestValidationError：ordinary identity 字段类型非法。
    """

    ordinary_value = row.get("ordinary_identity")
    if ordinary_value is None:
        return None
    ordinary = _expect_mapping(ordinary_value, "row.ordinary_identity")
    provider = _expect_string(
        ordinary.get("provider"),
        "row.ordinary_identity.provider",
    )
    return ProviderIdentity(
        family_id=provider,
        provider=provider,
        provider_model=_expect_string(
            ordinary.get("provider_model"),
            "row.ordinary_identity.provider_model",
        ),
    )


def _row_runner_call_identities(
    row: dict[str, JsonValue],
) -> tuple[ProviderIdentity, ...]:
    """严格读取 retained row 中的 runner-call identities。

    该投影只用于无 Host observation 的 non-requestable contradiction 检查；
    requestable reconciliation 必须使用 Host canonical runner calls。

    参数：
        row：既有 report 的严格 row JSON object。

    返回：
        retained runner-call provider family/model identities。

    异常：
        ManifestValidationError：runner_calls 或 identity 字段类型非法。
    """

    calls = _expect_list(row.get("runner_calls"), "row.runner_calls")
    identities: list[ProviderIdentity] = []
    for index, value in enumerate(calls):
        call = _expect_mapping(value, f"row.runner_calls[{index}]")
        provider = _expect_string(
            call.get("provider"),
            f"row.runner_calls[{index}].provider",
        )
        identities.append(
            ProviderIdentity(
                family_id=provider,
                provider=provider,
                provider_model=_expect_string(
                    call.get("provider_model"),
                    f"row.runner_calls[{index}].provider_model",
                ),
            )
        )
    return tuple(identities)


def _optional_row_host_run_id(
    row: dict[str, JsonValue],
) -> str | None:
    """严格读取 retained row 的可选 Host run id。

    参数：
        row：既有 report 的严格 row JSON object。

    返回：
        ``None`` 或非空 Host run id。

    异常：
        ManifestValidationError：host_run_id 不是 null/非空字符串。
    """

    value = row.get("host_run_id")
    if value is None:
        return None
    return _expect_string(value, "row.host_run_id")


def _reconciled_no_fallback_verdict(
    row: dict[str, JsonValue],
    *,
    choice: InitModelChoice,
    package_config_root: Path,
    workspace_config_root: Path | None,
    observation: HostObservation | None,
) -> NoFallbackVerdict:
    """从 canonical evidence 重算 no-fallback，绝不读取旧 verdict。

    requestable row 的 expected identity 来自 choice/package frozen truth，
    effective identity 来自 retained assembly projection，runner calls、run binding
    与 request/response facts 来自只读 Host observation。non-requestable row 只在
    retained facts 同时证明无 request、无 identity、无 trace/run binding 时通过。

    参数：
        row：既有 report 的严格 row JSON object。
        choice：当前 init catalog choice。
        package_config_root：冻结 package config 根。
        workspace_config_root：动态 choice 的 init-owned config 根；静态为
            ``None``。
        observation：只读 Host canonical observation；non-requestable 为 ``None``。

    返回：
        重新执行 ``evaluate_no_fallback`` 得到的 canonical verdict。

    异常：
        ManifestValidationError：retained typed evidence 非法。
        ConfigLoadError：package expected model truth 无法解析。
    """

    effective_identity = _row_effective_provider_identity(row)
    if observation is not None:
        expected_identity = _expected_provider_identity(
            choice,
            package_config_root,
            workspace_config_root=workspace_config_root,
        )
        observed_identities = tuple(
            ProviderIdentity(
                family_id=call.provider,
                provider=call.provider,
                provider_model=call.provider_model,
            )
            for call in observation.runner_calls
        )
        return evaluate_no_fallback(
            NoFallbackEvidence(
                expected_identity=expected_identity,
                effective_identity=effective_identity,
                request_attempted=observation.request_attempted,
                host_run_id=observation.host_run_id,
                trace_run_id=(
                    observation.host_run_id if observed_identities else None
                ),
                observed_identities=observed_identities,
                alternate_success_observed=(
                    observation.successful_response_received
                    and any(
                        identity != expected_identity
                        for identity in observed_identities
                    )
                ),
            )
        )

    request_attempted = _expect_bool(
        row.get("request_attempted"),
        "row.request_attempted",
    )
    response_received = _expect_bool(
        row.get("successful_response_received"),
        "row.successful_response_received",
    )
    if request_attempted:
        expected_identity = _expected_provider_identity(
            choice,
            package_config_root,
            workspace_config_root=workspace_config_root,
        )
        return evaluate_no_fallback(
            NoFallbackEvidence(
                expected_identity=expected_identity,
                effective_identity=effective_identity,
                request_attempted=True,
                host_run_id=None,
                trace_run_id=None,
                observed_identities=(),
                alternate_success_observed=response_received,
            )
        )

    observed_identities = _row_runner_call_identities(row)
    host_run_id = _optional_row_host_run_id(row)
    expected_identity: ProviderIdentity | None = None
    if effective_identity is not None:
        expected_identity = _expected_provider_identity(
            choice,
            package_config_root,
            workspace_config_root=workspace_config_root,
        )
    return evaluate_no_fallback(
        NoFallbackEvidence(
            expected_identity=expected_identity,
            effective_identity=effective_identity,
            request_attempted=False,
            host_run_id=host_run_id,
            trace_run_id=host_run_id if observed_identities else None,
            observed_identities=observed_identities,
            alternate_success_observed=response_received,
        )
    )


def reconcile_existing_report(
    *,
    report_path: Path,
    project_root: Path,
    process_env: Mapping[str, str],
) -> ReconciliationResult:
    """只读既有 row artifacts，原位重签唯一 matrix report。

    本函数绝不执行 init、prompt 或 provider；它只扫描同一 run 已持久化的
    CI-owned row roots，并重建安全的 report projection。

    参数：
        report_path：既有 run 的唯一 ``matrix-report.json`` 绝对路径。
        project_root：仓库绝对根。
        process_env：当前进程环境，仅从已知 credential refs 提取精确值。

    返回：
        report 路径、overall exit、Host accepted observation row 数与
        persistence violation row 数。

    异常：
        ValueError：路径不属于本 WU 的单一既有 run。
        ManifestValidationError：既有 report schema 或 row identity 非法。
        RuntimeError：安全扫描失败、report 含敏感值/绝对路径或节点竞态。
        OSError：既有 artifacts/report 无法安全读取或写入。
    """

    if not project_root.is_absolute() or not project_root.is_dir():
        raise ValueError("project_root 必须是现有绝对目录")
    if not report_path.is_absolute() or report_path.name != "matrix-report.json":
        raise ValueError("report_path 必须是 matrix-report.json 的绝对路径")
    run_root = report_path.parent
    expected_report_root = project_root / REPORT_ROOT
    if run_root.parent != expected_report_root:
        raise ValueError("report_path 不属于 S5-B CI-owned report root")
    report_stat = os.lstat(report_path)
    if not stat.S_ISREG(report_stat.st_mode):
        raise ValueError("matrix report 必须是非 symlink 普通文件")

    document = cast(
        JsonValue,
        json.loads(report_path.read_text(encoding="utf-8")),
    )
    report = _expect_mapping(document, "matrix report")
    _require_exact_keys(report, REPORT_JSON_KEYS, "matrix report")
    matrix_run_id = _expect_string(
        report.get("matrix_run_id"),
        "matrix report.matrix_run_id",
    )
    if matrix_run_id != run_root.name:
        raise ManifestValidationError("matrix_run_id 与 report run root 不一致")
    _expect_int(
        report.get("overall_exit_code"),
        "matrix report.overall_exit_code",
    )
    rows = _expect_list(report.get("rows"), "matrix report.rows")
    if len(rows) != MATRIX_ROW_COUNT:
        raise ManifestValidationError("matrix report 必须恰好包含 15 rows")

    credential_values = _known_credential_values(process_env)
    reconciled_rows: list[JsonValue] = []
    accepted_host_observation_row_count = 0
    persistence_violation_row_count = 0
    all_rows_safe = True
    for index, (choice, row_value) in enumerate(
        zip(INIT_MODEL_CHOICES, rows, strict=True),
        start=1,
    ):
        row = _expect_mapping(row_value, f"matrix report.rows[{index - 1}]")
        row_keys = frozenset(row)
        if row_keys not in {ROW_JSON_KEYS, LEGACY_ROW_JSON_KEYS}:
            raise ManifestValidationError(
                f"matrix report.rows[{index - 1}] keys 非法"
            )
        scenario_id = f"P{index:02d}-{choice.choice_id}"
        if (
            _expect_string(row.get("scenario_id"), "row.scenario_id")
            != scenario_id
            or _expect_string(row.get("choice_id"), "row.choice_id")
            != choice.choice_id
        ):
            raise ManifestValidationError("matrix row identity 与 catalog 不一致")
        row_root = run_root / "rows" / scenario_id
        workspace_root = row_root / "workspace"
        observation = _reconcile_terminal_summary(
            row,
            project_root=project_root,
            run_root=run_root,
            workspace_root=workspace_root,
            credential_values=credential_values,
        )
        persisted_scan = scan_persisted_secrets(
            row_root,
            credential_values=credential_values,
            canaries=(),
        )
        row["persisted_secret_scan"] = _persisted_secret_scan_json(
            persisted_scan
        )
        internal_contract_valid = _reconciled_row_internal_contract_valid(
            row,
            choice=choice,
            observation=observation,
        )
        reconciled_internal_contract_valid = (
            internal_contract_valid and persisted_scan.passed
        )
        row["internal_contract_valid"] = reconciled_internal_contract_valid
        row["availability_class"] = _reconciled_availability_class(
            row,
            internal_contract_valid=reconciled_internal_contract_valid,
            observation=observation,
        ).value
        no_fallback = _reconciled_no_fallback_verdict(
            row,
            choice=choice,
            package_config_root=project_root / PACKAGE_CONFIG_ROOT,
            workspace_config_root=(
                workspace_root / "config"
                if choice.kind in DYNAMIC_CHOICE_KINDS
                else None
            ),
            observation=observation,
        )
        row["no_fallback"] = _no_fallback_json(no_fallback)
        if any(
            observation_item.observation_code
            == "host_sqlite_credential_value"
            for observation_item in persisted_scan.accepted_observations
        ):
            accepted_host_observation_row_count += 1
        if persisted_scan.violations:
            persistence_violation_row_count += 1

        row["secret_scan"] = _secret_scan_json(
            SecretScanReport(passed=True, finding_codes=())
        )
        row_text = _json_text(cast(JsonValue, row))
        row_scan = scan_secrets(
            row_text,
            canaries=(SECRET_CANARY_PREFIX,),
            credential_values=credential_values,
            forbidden_path_prefixes=(
                project_root,
                run_root,
                workspace_root,
            ),
        )
        row["secret_scan"] = _secret_scan_json(row_scan)
        all_rows_safe = (
            all_rows_safe
            and row_scan.passed
            and persisted_scan.passed
            and no_fallback.passed
            and not no_fallback.fallback_observed
            and _expect_bool(
                row.get("internal_contract_valid"),
                "row.internal_contract_valid",
            )
        )
        reconciled_rows.append(cast(JsonValue, row))

    report["rows"] = reconciled_rows
    report["overall_exit_code"] = 0 if all_rows_safe else 1
    report["secret_scan"] = _secret_scan_json(
        SecretScanReport(passed=True, finding_codes=())
    )
    provisional_text = _json_text(cast(JsonValue, report))
    report_scan = scan_secrets(
        provisional_text,
        canaries=(SECRET_CANARY_PREFIX,),
        credential_values=credential_values,
        forbidden_path_prefixes=(project_root, run_root),
    )
    report["secret_scan"] = _secret_scan_json(report_scan)
    final_text = _json_text(cast(JsonValue, report))
    final_scan = scan_secrets(
        final_text,
        canaries=(SECRET_CANARY_PREFIX,),
        credential_values=credential_values,
        forbidden_path_prefixes=(project_root, run_root),
    )
    if not report_scan.passed or not final_scan.passed:
        raise RuntimeError(
            "reconciled matrix report secret/path scan failed; report 未写入"
        )
    _write_existing_report_no_follow(
        report_path,
        expected_stat=report_stat,
        content=final_text,
    )
    return ReconciliationResult(
        report_path=report_path,
        overall_exit_code=_expect_int(
            report.get("overall_exit_code"),
            "matrix report.overall_exit_code",
        ),
        accepted_host_credential_observation_row_count=(
            accepted_host_observation_row_count
        ),
        persistence_violation_row_count=persistence_violation_row_count,
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """构造 real provider matrix 的 argparse 骨架。

    参数：
        无。

    返回：
        只接受冻结 oracle version 的命令行 parser。

    异常：
        本函数不主动抛出异常。
    """

    parser = argparse.ArgumentParser(
        description="验证 CLI init publication 并运行真实 provider matrix。"
    )
    parser.add_argument(
        "--oracle-version",
        type=int,
        required=True,
        choices=(ORACLE_VERSION,),
        help="冻结 publication oracle 的版本。",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """解析参数、执行真实 matrix，并返回明确整数退出码。

    参数：
        argv：不含程序名的命令行参数；``None`` 表示读取进程参数。

    返回：
        matrix verdict；安全执行错误返回二。

    异常：
        SystemExit：argparse 参数非法。
    """

    parser = build_argument_parser()
    cast(CliArguments, parser.parse_args(argv, namespace=CliArguments()))
    try:
        execution = run_live_matrix(
            project_root=Path(__file__).resolve().parents[1],
            process_env=os.environ,
        )
    except Exception as error:
        print(
            "provider matrix execution failed safely: "
            f"{type(error).__name__}",
            file=sys.stderr,
        )
        return 2
    print(f"matrix-report={execution.report_path}")
    print(f"overall-exit={execution.report.overall_exit_code}")
    return execution.report.overall_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
