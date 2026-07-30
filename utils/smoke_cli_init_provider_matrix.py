"""为 CLI init/provider matrix 提供确定性证据模型与冻结清单校验。

本模块只拥有 S5-A 的纯函数、严格类型 schema 和命令行骨架。真实 subprocess、
Host trace 与公网 provider 调用属于后续 live 实现；当前入口会明确拒绝执行。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Sequence, TypeAlias, cast
from urllib.parse import urlsplit


ORACLE_ID = "cli.init.workspace-initialization"
ORACLE_VERSION = 1
PUBLICATION_ROOT = "workspace"
INIT_LOCK_PATH = ".dayu-init.lock"
EXPECTED_DIRECTORY_COUNT = 5
EXPECTED_FILE_COUNT = 43
EXPECTED_MODEL_POINTER_COUNT = 16
DEFAULT_PREVIEW_LIMIT = 256
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
AUTHORIZATION_PATTERN = re.compile(
    r"(?i)\bauthorization\b\s*[:=]\s*[\"']?\S+"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
CREDENTIAL_VALUE_PATTERN = re.compile(
    r"""(?ix)
    ["']?
    (?:api[_-]?key|access[_-]?token|secret|password|credential)
    ["']?
    \s*[:=]\s*
    ["'](?![A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)["'])[^"']+["']
    """
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


@dataclass(frozen=True, slots=True)
class SecretScanReport:
    """对最终 report 文本执行 secret 扫描后的结果。"""

    passed: bool
    finding_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    """no-fallback 判定使用的 provider/model 业务身份。"""

    family_id: str
    provider: str
    provider_model: str


@dataclass(frozen=True, slots=True)
class NoFallbackEvidence:
    """no-fallback 判定所需的同源身份与 trace 证据。"""

    expected_identity: ProviderIdentity
    effective_identity: ProviderIdentity
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
    preflight_class: PreflightClass
    availability_class: AvailabilityClass
    request_attempted: bool
    effective_identity: ProviderIdentity | None
    terminal_status: TerminalStatus
    terminal_summary: BoundedTextSummary
    endpoint: RedactedEndpoint | None
    no_fallback: NoFallbackVerdict
    secret_scan: SecretScanReport


@dataclass(frozen=True, slots=True)
class ProviderMatrixReport:
    """完整 provider matrix 的 typed report schema。"""

    oracle_id: str
    oracle_version: int
    rows: tuple[ProviderMatrixRowReport, ...]


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
    )


def scan_secrets(
    report_text: str,
    *,
    canaries: Sequence[str] = (),
    credential_values: Sequence[str] = (),
) -> SecretScanReport:
    """扫描最终 report，且不在 finding 中回显 secret 值。

    参数：
        report_text：待发布或持久化的完整 report 文本。
        canaries：专用于验证泄漏检测的 secret canary。
        credential_values：当前进程已知的真实 credential 值。

    返回：
        是否通过以及不含 secret 本身的稳定 finding code。

    异常：
        ValueError：canaries 或 credential_values 含空字符串。
    """

    if any(not value for value in canaries):
        raise ValueError("canaries 不得包含空字符串")
    if any(not value for value in credential_values):
        raise ValueError("credential_values 不得包含空字符串")

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
    finding_codes = tuple(sorted(set(findings)))
    return SecretScanReport(
        passed=not finding_codes,
        finding_codes=finding_codes,
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
    if evidence.effective_identity != evidence.expected_identity:
        reasons.append("effective_identity_mismatch")

    observed_set = frozenset(evidence.observed_identities)
    alternate_identities = observed_set - {evidence.expected_identity}
    if alternate_identities:
        reasons.append("alternate_identity_observed")
    if evidence.alternate_success_observed:
        reasons.append("alternate_success_observed")

    if evidence.request_attempted:
        if (
            evidence.host_run_id is None
            or evidence.trace_run_id is None
            or evidence.host_run_id != evidence.trace_run_id
        ):
            reasons.append("run_binding_mismatch")
        if evidence.expected_identity not in observed_set:
            reasons.append("expected_identity_not_observed")
    else:
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
    """解析 live 命令行参数并明确拒绝尚未实现的执行路径。

    参数：
        argv：不含程序名的命令行参数；``None`` 表示读取进程参数。

    返回：
        当前版本不会正常返回。

    异常：
        SystemExit：argparse 参数非法。
        NotImplementedError：S5-A 不实现 live subprocess/Host trace。
    """

    parser = build_argument_parser()
    cast(CliArguments, parser.parse_args(argv, namespace=CliArguments()))
    raise NotImplementedError(
        "S5-A 仅实现 deterministic contract；live provider matrix 尚未实现"
    )


if __name__ == "__main__":
    raise SystemExit(main())
