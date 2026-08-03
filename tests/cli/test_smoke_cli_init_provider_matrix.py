"""验证 CLI init/provider matrix 的 S5-A/S5-B 确定性 contract。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import get_type_hints

import pytest

from dayu.cli.init_catalog import (
    INIT_MODEL_CHOICES,
    InitModelSelection,
    OllamaModelSettings,
    find_init_model_choice,
)
from dayu.cli.init_workspace import (
    InitMode,
    WorkspaceTransactionRequest,
    prepare_workspace_transaction,
    publish_workspace_transaction,
    snapshot_managed_roots,
)
from dayu.runtime.filelock import file_lock
from utils.smoke_cli_init_provider_matrix import (
    AvailabilityClass,
    AvailabilityEvidence,
    BoundedTextSummary,
    EffectiveModelIdentity,
    FailureKind,
    HostObservation,
    ManifestValidationError,
    NoFallbackEvidence,
    NoFallbackVerdict,
    PersistedArtifactClass,
    PersistedCredentialObservation,
    PersistedSecretScanReport,
    PersistedSecretViolation,
    PreflightClass,
    ProviderMatrixReport,
    ProviderMatrixRowReport,
    ProviderIdentity,
    RedactedEndpoint,
    RunnerCallIdentity,
    SecretScanReport,
    SubprocessResult,
    TerminalStatus,
    _config_tree_digest,
    _effective_contract_valid,
    _expected_provider_identity,
    _failure_kind,
    _init_stdin,
    _json_text,
    _known_credential_values,
    _preflight_for_choice,
    _profile_publication_observed,
    _read_effective_identities,
    _reconciled_availability_class,
    _reconciled_no_fallback_verdict,
    _reconciled_row_internal_contract_valid,
    _redact_sensitive_text,
    _report_json,
    _row_environment,
    _row_json,
    _run_cli_subprocess,
    _run_matrix_row,
    _optional_payload_text,
    classify_availability,
    classify_preflight,
    evaluate_no_fallback,
    load_manifest,
    main,
    matrix_exit_code,
    redact_endpoint,
    reconcile_existing_report,
    run_live_matrix,
    scan_persisted_secrets,
    scan_secrets,
    summarize_bounded_text,
    validate_projected_publication_tree,
    validate_publication_tree,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_CONFIG_ROOT = PROJECT_ROOT / "dayu" / "config"
FROZEN_MANIFEST_PATH = PROJECT_ROOT / "docs" / "cli_init_workspace_manifest_v1.json"
FROZEN_MANIFEST_SHA256 = (
    "d63fb2ca415e914c9aaa3959b0b88be2072d1997b70799c9a2ac7de91fce2408"
)


@pytest.fixture(scope="module")
def production_publication_tree(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    """通过 production lock 与 transaction owner 构造 FIRST publication。

    参数：
        tmp_path_factory：pytest 提供的 module-scope 临时目录工厂。

    返回：
        含根级空 lock 与已发布 config 的真实 workspace。

    异常：
        OSError：workspace、lock 或 publication I/O 失败。
        AssertionError：production FIRST 未满足冻结 publication 前提。
    """

    workspace_root = tmp_path_factory.mktemp("s5-a-production") / "workspace"
    workspace_root.mkdir()
    platform_system = platform.system()
    selection = InitModelSelection(
        choice=find_init_model_choice("mimo-token-plan"),
        dynamic_settings=None,
    )
    snapshot = snapshot_managed_roots(
        workspace_root,
        platform_system=platform_system,
    )
    request = WorkspaceTransactionRequest(
        workspace_root=workspace_root.resolve(strict=True),
        package_config_root=PACKAGE_CONFIG_ROOT,
        mode=InitMode.FIRST,
        selection=selection,
        expected_snapshot=snapshot,
        platform_system=platform_system,
    )

    lock_path = workspace_root / ".dayu-init.lock"
    with file_lock(
        lock_path,
        timeout_seconds=None,
        create_parent_dirs=False,
    ):
        result = publish_workspace_transaction(
            prepare_workspace_transaction(request)
        )

    assert result.mode is InitMode.FIRST
    assert result.warnings == ()
    assert lock_path.is_file()
    assert lock_path.read_bytes() == b""
    assert not (workspace_root / "config" / "README.md").exists()
    assert not (workspace_root / "config" / ".DS_Store").exists()
    return workspace_root


@pytest.fixture(scope="module")
def openai_publication_tree(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    """通过 production owner 构造非冻结默认模型的 FIRST publication。

    参数：
        tmp_path_factory：pytest module-scope 临时目录工厂。

    返回：
        模型 pointer 已按 OpenAI choice 投影的真实 workspace。

    异常：
        OSError：workspace、lock 或 publication I/O 失败。
        AssertionError：production FIRST transaction 未成功。
    """

    workspace_root = tmp_path_factory.mktemp("s5-b-openai") / "workspace"
    workspace_root.mkdir()
    selection = InitModelSelection(
        choice=find_init_model_choice("openai"),
        dynamic_settings=None,
    )
    snapshot = snapshot_managed_roots(
        workspace_root,
        platform_system=platform.system(),
    )
    request = WorkspaceTransactionRequest(
        workspace_root=workspace_root.resolve(strict=True),
        package_config_root=PACKAGE_CONFIG_ROOT,
        mode=InitMode.FIRST,
        selection=selection,
        expected_snapshot=snapshot,
        platform_system=platform.system(),
    )
    with file_lock(
        workspace_root / ".dayu-init.lock",
        timeout_seconds=None,
        create_parent_dirs=False,
    ):
        result = publish_workspace_transaction(
            prepare_workspace_transaction(request)
        )
    assert result.mode is InitMode.FIRST
    return workspace_root


@pytest.fixture(scope="module")
def ollama_publication_tree(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    """通过 production owner 构造 Ollama 动态模型 FIRST publication。

    参数：
        tmp_path_factory：pytest module-scope 临时目录工厂。

    返回：
        models.json 与 manifest 均由 production owner 投影的 workspace。

    异常：
        OSError：workspace、lock 或 publication I/O 失败。
        AssertionError：production FIRST transaction 未成功。
    """

    workspace_root = tmp_path_factory.mktemp("s5-b-ollama") / "workspace"
    workspace_root.mkdir()
    selection = InitModelSelection(
        choice=find_init_model_choice("ollama"),
        dynamic_settings=OllamaModelSettings(
            model_name="qwen3:8b",
            endpoint="http://localhost:11434/v1/chat/completions",
            context_window_tokens=262144,
        ),
    )
    snapshot = snapshot_managed_roots(
        workspace_root,
        platform_system=platform.system(),
    )
    request = WorkspaceTransactionRequest(
        workspace_root=workspace_root.resolve(strict=True),
        package_config_root=PACKAGE_CONFIG_ROOT,
        mode=InitMode.FIRST,
        selection=selection,
        expected_snapshot=snapshot,
        platform_system=platform.system(),
    )
    with file_lock(
        workspace_root / ".dayu-init.lock",
        timeout_seconds=None,
        create_parent_dirs=False,
    ):
        result = publish_workspace_transaction(
            prepare_workspace_transaction(request)
        )
    assert result.mode is InitMode.FIRST
    return workspace_root


@pytest.fixture
def fresh_publication_tree(
    tmp_path: Path,
    production_publication_tree: Path,
) -> Path:
    """复制真实 FIRST workspace，形成可独立破坏的 fresh publication tree。

    参数：
        tmp_path：pytest 提供的当前测试临时目录。
        production_publication_tree：由 production owner 构造的基准 workspace。

    返回：
        完整复制后的临时 workspace 根目录。

    异常：
        OSError：真实 publication 不可读或复制失败。
    """

    workspace_root = tmp_path / "workspace"
    shutil.copytree(production_publication_tree, workspace_root)
    return workspace_root


def _sha256_path(path: Path) -> str:
    """计算文件内容的 SHA-256。

    参数：
        path：待读取文件。

    返回：
        小写十六进制 SHA-256。

    异常：
        OSError：文件不可读。
    """

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest_variant(
    tmp_path: Path,
    *,
    old: str,
    new: str,
) -> Path:
    """通过精确文本替换写出一个非法 manifest 变体。

    参数：
        tmp_path：pytest 临时目录。
        old：冻结 manifest 中必须存在的原文本。
        new：替换后的非法文本。

    返回：
        非法 manifest 变体路径。

    异常：
        OSError：manifest 不可读或临时文件不可写。
        AssertionError：old 在冻结 manifest 中不唯一。
    """

    original = FROZEN_MANIFEST_PATH.read_text(encoding="utf-8")
    assert original.count(old) == 1
    variant_path = tmp_path / "manifest.json"
    variant_path.write_text(original.replace(old, new), encoding="utf-8")
    return variant_path


def _passing_non_requestable_row(index: int) -> ProviderMatrixRowReport:
    """构造不签发 real pass 的纯函数 matrix row。

    参数：
        index：row 的稳定测试序号。

    返回：
        credential missing、零请求且 contract 完整的 typed row。

    异常：
        ValueError：index 非正数。
    """

    if index <= 0:
        raise ValueError("index 必须为正数")
    return ProviderMatrixRowReport(
        scenario_id=f"P{index:02d}-test",
        choice_id=f"test-{index}",
        role_coverage=("ordinary", "compactor"),
        expected_ordinary_model_id="model-thinking",
        expected_compactor_model_id="model",
        required_credential_ref="TEST_API_KEY",
        credential_present=False,
        preflight_class=PreflightClass.CREDENTIAL_MISSING,
        availability_class=AvailabilityClass.CREDENTIAL_MISSING,
        init_exit_code=1,
        prompt_exit_code=None,
        publication_valid=False,
        publication_issues=(),
        publication_absent_after_rejection=True,
        profile_publication_observed=False,
        config_tree_digest_before="a" * 64,
        config_tree_digest_after_init="a" * 64,
        config_tree_digest_after_prompt="a" * 64,
        request_attempted=False,
        successful_response_received=False,
        provider_request_id_present=False,
        client_correlation_id_present=False,
        host_run_id=None,
        ordinary_identity=None,
        compactor_identity=None,
        runner_calls=(),
        terminal_status=TerminalStatus.NOT_RUN,
        terminal_summary=BoundedTextSummary(
            length=0,
            sha256=hashlib.sha256(b"").hexdigest(),
            preview="",
            marker_present=False,
        ),
        no_fallback=NoFallbackVerdict(
            passed=True,
            fallback_observed=False,
            reason_codes=(),
        ),
        secret_scan=SecretScanReport(passed=True, finding_codes=()),
        persisted_secret_scan=PersistedSecretScanReport(
            passed=True,
            scanned_file_count=0,
            scanned_byte_count=0,
            accepted_observations=(),
            violations=(),
        ),
        internal_contract_valid=True,
    )


def test_frozen_manifest_matches_fresh_real_publication_tree(
    fresh_publication_tree: Path,
) -> None:
    """验证冻结 manifest 与真实 package 副本完全匹配。

    参数：
        fresh_publication_tree：fresh 真实 publication tree。

    返回：
        无返回值。

    异常：
        AssertionError：路径、摘要或模型 pointer 不匹配。
    """

    manifest = load_manifest(FROZEN_MANIFEST_PATH)
    report = validate_publication_tree(manifest, fresh_publication_tree)

    assert report.valid
    assert report.issues == ()
    assert len(report.actual_directories) == 5
    assert len(report.actual_files) == 43
    assert ".dayu-init.lock" in report.actual_files
    assert len(report.actual_model_owner_paths) == 16


def test_actual_tree_root_error_short_circuits_to_one_diagnostic(
    tmp_path: Path,
) -> None:
    """验证不可读 actual 根只产生一个根因诊断。

    参数：
        tmp_path：pytest 临时目录。

    返回：
        无返回值。

    异常：
        AssertionError：下游差异噪声掩盖根因。
    """

    report = validate_publication_tree(
        load_manifest(FROZEN_MANIFEST_PATH),
        tmp_path / "missing-workspace",
    )

    assert not report.valid
    assert report.issues == ("actual_tree_unreadable:ValueError",)
    assert report.actual_directories == ()
    assert report.actual_files == ()
    assert report.actual_model_owner_paths == ()


def test_projected_publication_accepts_only_role_model_pointer_changes(
    openai_publication_tree: Path,
) -> None:
    """验证非默认 choice 的 16 个角色 owner 投影可通过冻结 oracle。

    参数：
        openai_publication_tree：production owner 生成的 OpenAI publication。

    返回：
        无返回值。

    异常：
        AssertionError：合法角色投影被误判为 frozen digest 漂移。
    """

    report = validate_projected_publication_tree(
        load_manifest(FROZEN_MANIFEST_PATH),
        openai_publication_tree,
        PACKAGE_CONFIG_ROOT,
        ordinary_model_id="gpt-5.4",
        thinking_model_id="gpt-5.4-thinking",
    )

    assert report.valid
    assert report.issues == ()


def test_projected_publication_validates_ollama_dynamic_owner_fields(
    ollama_publication_tree: Path,
) -> None:
    """验证 Ollama 只获准投影 owner 定义的三个动态字段。

    参数：
        ollama_publication_tree：production owner 生成的 Ollama publication。

    返回：
        无返回值。

    异常：
        AssertionError：动态 models.json 未被严格模式拒绝或 owner 模式误拒。
    """

    manifest = load_manifest(FROZEN_MANIFEST_PATH)
    strict_report = validate_projected_publication_tree(
        manifest,
        ollama_publication_tree,
        PACKAGE_CONFIG_ROOT,
        ordinary_model_id="ollama",
        thinking_model_id="ollama",
    )
    owner_report = validate_projected_publication_tree(
        manifest,
        ollama_publication_tree,
        PACKAGE_CONFIG_ROOT,
        ordinary_model_id="ollama",
        thinking_model_id="ollama",
        allow_ollama_dynamic=True,
    )

    assert not strict_report.valid
    assert "file_digest_mismatch:config/models.json" in strict_report.issues
    assert owner_report.valid
    assert owner_report.issues == ()


def test_ollama_expected_identity_uses_init_owned_dynamic_truth(
    ollama_publication_tree: Path,
) -> None:
    """验证动态 expected model 来自 init publication 而非 package placeholder。

    参数：
        ollama_publication_tree：production owner 生成的 Ollama publication。

    返回：
        无返回值。

    异常：
        ConfigLoadError：package/workspace models 无法解析。
        AssertionError：expected identity 回退到 package template 或 assembly actual。
    """

    expected = _expected_provider_identity(
        find_init_model_choice("ollama"),
        PACKAGE_CONFIG_ROOT,
        workspace_config_root=ollama_publication_tree / "config",
    )

    assert expected == ProviderIdentity(
        family_id="ollama",
        provider="ollama",
        provider_model="qwen3:8b",
    )


def test_projected_publication_rejects_non_owner_field_change(
    tmp_path: Path,
    openai_publication_tree: Path,
) -> None:
    """验证 owner 文件的其它字段不能借模型投影获得豁免。

    参数：
        tmp_path：pytest 临时目录。
        openai_publication_tree：production OpenAI publication。

    返回：
        无返回值。

    异常：
        OSError：临时 tree 无法复制或篡改。
        AssertionError：非 owner 字段漂移未被拒绝。
    """

    workspace_root = tmp_path / "workspace"
    shutil.copytree(openai_publication_tree, workspace_root)
    target = (
        workspace_root
        / "config"
        / "prompts"
        / "manifests"
        / "prompt.json"
    )
    content = target.read_text(encoding="utf-8")
    assert content.count('"description": "单轮财报问答场景"') == 1
    target.write_text(
        content.replace(
            '"description": "单轮财报问答场景"',
            '"description": "changed"',
        ),
        encoding="utf-8",
    )

    report = validate_projected_publication_tree(
        load_manifest(FROZEN_MANIFEST_PATH),
        workspace_root,
        PACKAGE_CONFIG_ROOT,
        ordinary_model_id="gpt-5.4",
        thinking_model_id="gpt-5.4-thinking",
    )

    assert not report.valid
    assert "model_projection_mismatch:config/prompts/manifests/prompt.json" in (
        report.issues
    )


def test_added_actual_file_fails_manifest_validation(
    fresh_publication_tree: Path,
) -> None:
    """验证 actual tree 新增 managed file 时 fail closed。

    参数：
        fresh_publication_tree：fresh 真实 publication tree。

    返回：
        无返回值。

    异常：
        OSError：测试文件无法写入。
        AssertionError：新增路径未被识别。
    """

    added_path = (
        fresh_publication_tree
        / "config"
        / "prompts"
        / "scenes"
        / "unexpected.md"
    )
    added_path.write_text("unexpected", encoding="utf-8")

    report = validate_publication_tree(
        load_manifest(FROZEN_MANIFEST_PATH),
        fresh_publication_tree,
    )

    assert not report.valid
    assert any(issue.startswith("file_path_mismatch:") for issue in report.issues)


def test_deleted_actual_file_fails_manifest_validation(
    fresh_publication_tree: Path,
) -> None:
    """验证 actual tree 删除 managed file 时 fail closed。

    参数：
        fresh_publication_tree：fresh 真实 publication tree。

    返回：
        无返回值。

    异常：
        OSError：测试文件无法删除。
        AssertionError：缺失路径未被识别。
    """

    (
        fresh_publication_tree
        / "config"
        / "prompts"
        / "scenes"
        / "audit.md"
    ).unlink()

    report = validate_publication_tree(
        load_manifest(FROZEN_MANIFEST_PATH),
        fresh_publication_tree,
    )

    assert not report.valid
    assert any(issue.startswith("file_path_mismatch:") for issue in report.issues)


def test_tampered_actual_file_fails_digest_validation(
    fresh_publication_tree: Path,
) -> None:
    """验证 actual tree 内容篡改时由 digest owner 拒绝。

    参数：
        fresh_publication_tree：fresh 真实 publication tree。

    返回：
        无返回值。

    异常：
        OSError：测试文件无法写入。
        AssertionError：摘要漂移未被识别。
    """

    target = fresh_publication_tree / "config" / "host_runtime.json"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    report = validate_publication_tree(
        load_manifest(FROZEN_MANIFEST_PATH),
        fresh_publication_tree,
    )

    assert not report.valid
    assert "file_digest_mismatch:config/host_runtime.json" in report.issues


def test_actual_model_pointer_mismatch_fails_validation(
    fresh_publication_tree: Path,
) -> None:
    """验证模型 owner JSON pointer 漂移时 fail closed。

    参数：
        fresh_publication_tree：fresh 真实 publication tree。

    返回：
        无返回值。

    异常：
        OSError：manifest 副本不可读写。
        AssertionError：目标 pointer 不唯一或漂移未被识别。
    """

    target = (
        fresh_publication_tree
        / "config"
        / "prompts"
        / "manifests"
        / "conversation_compaction.json"
    )
    content = target.read_text(encoding="utf-8")
    assert content.count('"default_model_id"') == 1
    target.write_text(
        content.replace('"default_model_id"', '"unexpected_model_id"'),
        encoding="utf-8",
    )

    report = validate_publication_tree(
        load_manifest(FROZEN_MANIFEST_PATH),
        fresh_publication_tree,
    )

    assert not report.valid
    assert any(
        issue.startswith("model_pointer_mismatch:") for issue in report.issues
    )
    assert any(
        issue.startswith("model_pointer_count_mismatch:")
        for issue in report.issues
    )


def test_checked_in_manifest_digest_is_stable_across_validation(
    fresh_publication_tree: Path,
) -> None:
    """验证正常加载与校验不会改写 checked-in frozen manifest。

    参数：
        fresh_publication_tree：fresh 真实 publication tree。

    返回：
        无返回值。

    异常：
        OSError：manifest 不可读。
        AssertionError：manifest digest 漂移或 tree 校验失败。
    """

    digest_before = _sha256_path(FROZEN_MANIFEST_PATH)
    manifest = load_manifest(FROZEN_MANIFEST_PATH)
    report = validate_publication_tree(manifest, fresh_publication_tree)
    digest_after = _sha256_path(FROZEN_MANIFEST_PATH)

    assert digest_before == FROZEN_MANIFEST_SHA256
    assert report.valid
    assert digest_after == digest_before


def test_loader_rejects_invalid_json(tmp_path: Path) -> None:
    """验证 loader 拒绝非法 JSON。

    参数：
        tmp_path：pytest 临时目录。

    返回：
        无返回值。

    异常：
        OSError：测试文件不可写。
        AssertionError：loader 未抛出严格 schema 错误。
    """

    path = tmp_path / "invalid.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="不是合法 JSON"):
        load_manifest(path)


def test_loader_rejects_unknown_root_key(tmp_path: Path) -> None:
    """验证 loader 拒绝未知根字段。

    参数：
        tmp_path：pytest 临时目录。

    返回：
        无返回值。

    异常：
        OSError：manifest 变体不可写。
        AssertionError：loader 接受未知字段。
    """

    path = _write_manifest_variant(
        tmp_path,
        old='  "oracle_id":',
        new='  "unexpected": true,\n  "oracle_id":',
    )

    with pytest.raises(ManifestValidationError, match="字段不匹配"):
        load_manifest(path)


def test_loader_rejects_wrong_oracle_version(tmp_path: Path) -> None:
    """验证 loader 拒绝错误 oracle version。

    参数：
        tmp_path：pytest 临时目录。

    返回：
        无返回值。

    异常：
        OSError：manifest 变体不可写。
        AssertionError：loader 接受错误版本。
    """

    path = _write_manifest_variant(
        tmp_path,
        old='"oracle_version": 1',
        new='"oracle_version": 2',
    )

    with pytest.raises(ManifestValidationError, match="oracle_version"):
        load_manifest(path)


def test_loader_rejects_invalid_package_digest(tmp_path: Path) -> None:
    """验证 loader 拒绝非法 package SHA-256。

    参数：
        tmp_path：pytest 临时目录。

    返回：
        无返回值。

    异常：
        OSError：manifest 变体不可写。
        AssertionError：loader 接受非法摘要。
    """

    path = _write_manifest_variant(
        tmp_path,
        old="3fd7e6940e337f0668bbac315f6b99254e3eb3309473a2161efc91cfc1b2e1f5",
        new="not-a-digest",
    )

    with pytest.raises(ManifestValidationError, match="SHA-256"):
        load_manifest(path)


def test_loader_rejects_wrong_model_json_pointer(tmp_path: Path) -> None:
    """验证 loader 拒绝冻结 owner pointer 自身漂移。

    参数：
        tmp_path：pytest 临时目录。

    返回：
        无返回值。

    异常：
        OSError：manifest 变体不可写。
        AssertionError：loader 接受错误 pointer。
    """

    path = _write_manifest_variant(
        tmp_path,
        old='{"path": "config/prompts/manifests/audit.json", '
        '"json_pointer": "/model/default_model_id", "role": "thinking"}',
        new='{"path": "config/prompts/manifests/audit.json", '
        '"json_pointer": "/model/wrong", "role": "thinking"}',
    )

    with pytest.raises(ManifestValidationError, match="json_pointer"):
        load_manifest(path)


@pytest.mark.parametrize(
    ("credential_required", "credential_present", "endpoint_required",
     "endpoint_configured", "service_reachable", "expected"),
    [
        (True, False, False, False, None, PreflightClass.CREDENTIAL_MISSING),
        (False, False, True, False, None, PreflightClass.ENDPOINT_UNCONFIGURED),
        (False, False, False, False, False, PreflightClass.SERVICE_UNREACHABLE),
        (True, True, True, True, True, PreflightClass.REQUESTABLE),
        (False, False, False, False, None, PreflightClass.REQUESTABLE),
    ],
)
def test_classify_preflight_covers_every_branch(
    credential_required: bool,
    credential_present: bool,
    endpoint_required: bool,
    endpoint_configured: bool,
    service_reachable: bool | None,
    expected: PreflightClass,
) -> None:
    """验证 preflight classifier 的全部 enum 分支及不适用状态。

    参数：
        credential_required：是否要求 credential。
        credential_present：credential 是否存在。
        endpoint_required：是否要求 endpoint。
        endpoint_configured：endpoint 是否已配置。
        service_reachable：服务探测结果。
        expected：预期 preflight class。

    返回：
        无返回值。

    异常：
        AssertionError：分类结果不符合优先级 contract。
    """

    assert (
        classify_preflight(
            credential_required=credential_required,
            credential_present=credential_present,
            endpoint_required=endpoint_required,
            endpoint_configured=endpoint_configured,
            service_reachable=service_reachable,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        (
            AvailabilityEvidence(
                preflight_class=PreflightClass.REQUESTABLE,
                internal_contract_valid=True,
                request_attempted=True,
                response_received=True,
                exit_code=0,
                failure_kind=FailureKind.NONE,
            ),
            AvailabilityClass.AVAILABLE,
        ),
        (
            AvailabilityEvidence(
                preflight_class=PreflightClass.CREDENTIAL_MISSING,
                internal_contract_valid=True,
                request_attempted=False,
                response_received=False,
                exit_code=1,
                failure_kind=FailureKind.NONE,
            ),
            AvailabilityClass.CREDENTIAL_MISSING,
        ),
        (
            AvailabilityEvidence(
                preflight_class=PreflightClass.ENDPOINT_UNCONFIGURED,
                internal_contract_valid=True,
                request_attempted=False,
                response_received=False,
                exit_code=1,
                failure_kind=FailureKind.NONE,
            ),
            AvailabilityClass.ENDPOINT_UNCONFIGURED,
        ),
        (
            AvailabilityEvidence(
                preflight_class=PreflightClass.SERVICE_UNREACHABLE,
                internal_contract_valid=True,
                request_attempted=False,
                response_received=False,
                exit_code=1,
                failure_kind=FailureKind.NONE,
            ),
            AvailabilityClass.SERVICE_UNREACHABLE,
        ),
        (
            AvailabilityEvidence(
                preflight_class=PreflightClass.REQUESTABLE,
                internal_contract_valid=True,
                request_attempted=True,
                response_received=False,
                exit_code=1,
                failure_kind=FailureKind.TRANSPORT,
            ),
            AvailabilityClass.SERVICE_UNREACHABLE,
        ),
        (
            AvailabilityEvidence(
                preflight_class=PreflightClass.REQUESTABLE,
                internal_contract_valid=True,
                request_attempted=True,
                response_received=False,
                exit_code=1,
                failure_kind=FailureKind.PROVIDER_REJECTED,
            ),
            AvailabilityClass.PROVIDER_REJECTED,
        ),
        (
            AvailabilityEvidence(
                preflight_class=PreflightClass.REQUESTABLE,
                internal_contract_valid=True,
                request_attempted=True,
                response_received=False,
                exit_code=1,
                failure_kind=FailureKind.RATE_LIMITED,
            ),
            AvailabilityClass.RATE_LIMITED,
        ),
        (
            AvailabilityEvidence(
                preflight_class=PreflightClass.REQUESTABLE,
                internal_contract_valid=False,
                request_attempted=False,
                response_received=False,
                exit_code=1,
                failure_kind=FailureKind.NONE,
            ),
            AvailabilityClass.INTERNAL_PRODUCT_BUG,
        ),
        (
            AvailabilityEvidence(
                preflight_class=PreflightClass.REQUESTABLE,
                internal_contract_valid=True,
                request_attempted=False,
                response_received=False,
                exit_code=0,
                failure_kind=FailureKind.NONE,
            ),
            AvailabilityClass.INTERNAL_PRODUCT_BUG,
        ),
    ],
)
def test_classify_availability_covers_every_enum_branch(
    evidence: AvailabilityEvidence,
    expected: AvailabilityClass,
) -> None:
    """验证 availability classifier 的全部 enum 分支与 fail-closed 分支。

    参数：
        evidence：typed availability 观测。
        expected：预期最终分类。

    返回：
        无返回值。

    异常：
        AssertionError：分类结果不符合证据 contract。
    """

    assert classify_availability(evidence) is expected


def test_classify_availability_rejects_inconsistent_external_preflight() -> None:
    """验证 external preflight 与请求事实矛盾时归类为内部错误。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：矛盾状态未 fail closed。
    """

    evidence = AvailabilityEvidence(
        preflight_class=PreflightClass.CREDENTIAL_MISSING,
        internal_contract_valid=True,
        request_attempted=True,
        response_received=False,
        exit_code=1,
        failure_kind=FailureKind.NONE,
    )

    assert (
        classify_availability(evidence)
        is AvailabilityClass.INTERNAL_PRODUCT_BUG
    )


def test_redact_endpoint_removes_secret_bearing_components() -> None:
    """验证 endpoint identity 去除 userinfo、query 与 fragment。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：输出保留 secret-bearing 组件或路径摘要错误。
    """

    endpoint = redact_endpoint(
        "https://user:password@Example.COM:8443/v1/chat"
        "?api_key=secret#fragment"
    )

    assert endpoint.scheme == "https"
    assert endpoint.hostname == "example.com"
    assert endpoint.port == 8443
    assert endpoint.path_sha256 == hashlib.sha256(b"/v1/chat").hexdigest()
    assert "user" not in repr(endpoint)
    assert "password" not in repr(endpoint)
    assert "secret" not in repr(endpoint)
    assert "fragment" not in repr(endpoint)


def test_redact_endpoint_rejects_non_absolute_url() -> None:
    """验证 endpoint redaction 拒绝缺少 hostname 的输入。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：非法 endpoint 未抛出 ValueError。
    """

    with pytest.raises(ValueError, match="绝对 HTTP"):
        redact_endpoint("/v1/chat?secret=value")


def test_summarize_bounded_text_preserves_only_bounded_preview() -> None:
    """验证 bounded summary 保存完整长度和摘要但截断 preview。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：长度、摘要或 preview 不符合 contract。
    """

    text = "财报分析-response"
    summary = summarize_bounded_text(text, preview_limit=4)

    assert summary.length == len(text)
    assert summary.sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert summary.preview == text[:4]
    assert len(summary.preview) == 4


def test_summarize_bounded_text_rejects_negative_limit() -> None:
    """验证 bounded summary 拒绝负数限制。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：负数限制未抛出 ValueError。
    """

    with pytest.raises(ValueError, match="不得小于零"):
        summarize_bounded_text("text", preview_limit=-1)


def test_scan_secrets_accepts_redacted_reference_names() -> None:
    """验证 secret scan 允许 credential ref 名但不允许其值。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：纯 ref 名被误判为 secret。
    """

    report = scan_secrets(
        '{"credential_ref":"OPENAI_API_KEY","endpoint":"redacted"}',
        canaries=("canary-value",),
        credential_values=("real-credential-value",),
    )

    assert report.passed
    assert report.finding_codes == ()


@pytest.mark.parametrize(
    ("report_text", "expected_code"),
    [
        ("Authorization: Basic abc123", "authorization_value"),
        ("message Bearer abc.def.ghi", "bearer_token"),
        ('{"api_key":"plaintext-secret"}', "credential_field_value"),
        ("prefix canary-value suffix", "secret_canary"),
        ("prefix real-credential-value suffix", "credential_value"),
    ],
)
def test_scan_secrets_detects_each_leak_category(
    report_text: str,
    expected_code: str,
) -> None:
    """验证 secret、authorization 与 canary 的每类泄漏均被识别。

    参数：
        report_text：含一种泄漏的 report 文本。
        expected_code：不得包含 secret 本身的预期 finding code。

    返回：
        无返回值。

    异常：
        AssertionError：泄漏未检出或 finding 回显 secret。
    """

    report = scan_secrets(
        report_text,
        canaries=("canary-value",),
        credential_values=("real-credential-value",),
    )

    assert not report.passed
    assert expected_code in report.finding_codes
    assert "canary-value" not in repr(report.finding_codes)
    assert "real-credential-value" not in repr(report.finding_codes)


def test_scan_secrets_rejects_empty_secret_probe() -> None:
    """验证 secret scan 拒绝会匹配所有文本的空探针。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：空探针未抛出 ValueError。
    """

    with pytest.raises(ValueError, match="canaries"):
        scan_secrets("report", canaries=("",))
    with pytest.raises(ValueError, match="credential_values"):
        scan_secrets("report", credential_values=("",))


def test_redaction_replaces_only_explicit_root_prefixes(
    tmp_path: Path,
) -> None:
    """验证路径脱敏只替换显式 roots，不泛化删除业务路径文本。

    参数：
        tmp_path：pytest 临时项目根。

    返回：
        无返回值。

    异常：
        AssertionError：绝对 root 残留或业务 URL path 被误删。
    """

    project_root = tmp_path.resolve()
    run_root = project_root / "workspace/tmp/wu-cli-init-01/run-1"
    workspace_root = run_root / "rows/P01-test/workspace"
    text = (
        f"workspace={workspace_root} run={run_root} project={project_root} "
        "business_path=/v1/financial-statements"
    )

    redacted = _redact_sensitive_text(
        text,
        credential_values=(),
        canary="exact-canary",
        project_root=project_root,
        run_root=run_root,
        workspace_root=workspace_root,
    )

    assert str(project_root) not in redacted
    assert "workspace=[WORKSPACE_ROOT]" in redacted
    assert "run=[RUN_ROOT]" in redacted
    assert "project=[PROJECT_ROOT]" in redacted
    assert "business_path=/v1/financial-statements" in redacted
    assert scan_secrets(
        redacted,
        forbidden_path_prefixes=(project_root, run_root, workspace_root),
    ).passed


def test_persisted_scan_detects_real_sqlite_and_ordinary_file(
    tmp_path: Path,
) -> None:
    """验证 Host credential 是 observation、任意位置 canary 是 violation。

    参数：
        tmp_path：pytest 临时 row root。

    返回：
        无返回值。

    异常：
        sqlite3.Error：临时 SQLite 无法建立。
        AssertionError：Host observation/canary policy 分类错误或回显敏感值。
    """

    row_root = (tmp_path / "row").resolve()
    host_root = row_root / "workspace/.dayu/host"
    artifact_root = row_root / "workspace/.dayu/artifacts/audit"
    config_root = row_root / "workspace/config"
    host_root.mkdir(parents=True)
    artifact_root.mkdir(parents=True)
    config_root.mkdir(parents=True)
    credential = "deterministic-persisted-credential"
    canary = "deterministic-persisted-canary"
    database_path = host_root / "dayu_host.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE event_log(payload_json TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO event_log(payload_json) VALUES (?)",
            (f'{{"Authorization":"Bearer {credential}"}}',),
        )
        connection.commit()
    (host_root / "dayu_host.sqlite3-wal").write_text(
        f"{credential}\n{canary}\n",
        encoding="utf-8",
    )
    (artifact_root / "host-audit.jsonl").write_text(
        f'{{"probe":"{canary}"}}\n',
        encoding="utf-8",
    )
    (config_root / "models.json").write_text("{}\n", encoding="utf-8")

    report = scan_persisted_secrets(
        row_root,
        credential_values=(credential,),
        canaries=(canary,),
    )

    assert not report.passed
    assert report.scanned_file_count == 4
    assert report.scanned_byte_count > 0
    observation_keys = {
        (observation.observation_code, observation.artifact_class)
        for observation in report.accepted_observations
    }
    assert (
        "host_sqlite_credential_value",
        PersistedArtifactClass.HOST_SQLITE,
    ) in observation_keys
    assert (
        "host_sqlite_credential_value",
        PersistedArtifactClass.HOST_SQLITE_WAL,
    ) in observation_keys
    violation_keys = {
        (violation.violation_code, violation.artifact_class)
        for violation in report.violations
    }
    assert (
        "persisted_secret_canary",
        PersistedArtifactClass.HOST_SQLITE_WAL,
    ) in violation_keys
    assert (
        "persisted_secret_canary",
        PersistedArtifactClass.TRACE_LOG_ARTIFACT,
    ) in violation_keys
    assert credential not in repr(report)
    assert canary not in repr(report)


@pytest.mark.parametrize(
    ("relative_path", "expected_class"),
    [
        (
            Path("workspace/config/models.json"),
            PersistedArtifactClass.CONFIG,
        ),
        (
            Path("workspace/.dayu/artifacts/trace.jsonl"),
            PersistedArtifactClass.TRACE_LOG_ARTIFACT,
        ),
        (
            Path("matrix-report.json"),
            PersistedArtifactClass.ROW_OTHER,
        ),
        (
            Path("home/provider-cache.bin"),
            PersistedArtifactClass.ROW_OTHER,
        ),
    ],
)
def test_persisted_scan_rejects_credential_outside_host_sqlite(
    tmp_path: Path,
    relative_path: Path,
    expected_class: PersistedArtifactClass,
) -> None:
    """验证 config/report/log/trace/其它 durable artifact 的明文均失败。

    参数：
        tmp_path：pytest 临时 row root。
        relative_path：待写入 exact credential 的 row-relative 文件。
        expected_class：policy owner 应投影的稳定 artifact 类别。

    返回：
        无返回值。

    异常：
        OSError：临时 artifact 无法创建。
        AssertionError：非 Host SQLite credential 被接受。
    """

    row_root = (tmp_path / "row").resolve()
    target = row_root / relative_path
    target.parent.mkdir(parents=True)
    credential = "credential-outside-host-sqlite"
    target.write_text(credential, encoding="utf-8")

    report = scan_persisted_secrets(
        row_root,
        credential_values=(credential,),
        canaries=(),
    )

    assert not report.passed
    assert report.accepted_observations == ()
    assert report.violations == (
        PersistedSecretViolation(
            violation_code="persisted_credential_value",
            artifact_class=expected_class,
            count=1,
        ),
    )


def test_persisted_scan_accepts_host_sqlite_credential_only(
    tmp_path: Path,
) -> None:
    """验证 Host SQLite/WAL exact credential 只形成 accepted observation。

    参数：
        tmp_path：pytest 临时 row root。

    返回：
        无返回值。

    异常：
        OSError：临时 Host artifacts 无法创建。
        AssertionError：允许观测被计入 violation。
    """

    row_root = (tmp_path / "row").resolve()
    host_root = row_root / "workspace/.dayu/host"
    host_root.mkdir(parents=True)
    credential = "accepted-host-credential"
    (host_root / "dayu_host.sqlite3").write_text(
        credential,
        encoding="utf-8",
    )
    (host_root / "dayu_host.sqlite3-wal").write_text(
        credential,
        encoding="utf-8",
    )

    report = scan_persisted_secrets(
        row_root,
        credential_values=(credential,),
        canaries=(),
    )

    assert report.passed
    assert report.violations == ()
    assert report.accepted_observations == (
        PersistedCredentialObservation(
            observation_code="host_sqlite_credential_value",
            artifact_class=PersistedArtifactClass.HOST_SQLITE,
            count=1,
        ),
        PersistedCredentialObservation(
            observation_code="host_sqlite_credential_value",
            artifact_class=PersistedArtifactClass.HOST_SQLITE_WAL,
            count=1,
        ),
    )


def test_persisted_scan_legacy_canary_prefix_fails_closed(
    tmp_path: Path,
) -> None:
    """验证不知道旧 exact canary 时仍按稳定前缀 fail closed。

    参数：
        tmp_path：pytest 临时 row root。

    返回：
        无返回值。

    异常：
        OSError：临时 artifact 无法创建。
        AssertionError：空 canaries 被错误解释为禁用 canary 检测。
    """

    row_root = (tmp_path / "row").resolve()
    artifact = row_root / "workspace/config/models.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        '{"probe":"s5b-canary-legacy-value"}',
        encoding="utf-8",
    )

    report = scan_persisted_secrets(
        row_root,
        credential_values=(),
        canaries=(),
    )

    assert not report.passed
    assert report.violations == (
        PersistedSecretViolation(
            violation_code="persisted_secret_canary",
            artifact_class=PersistedArtifactClass.CONFIG,
            count=1,
        ),
    )


def test_persisted_scan_fails_closed_on_symlink(tmp_path: Path) -> None:
    """验证 row tree 中 symlink 不被跟随且稳定 fail closed。

    参数：
        tmp_path：pytest 临时 row root。

    返回：
        无返回值。

    异常：
        OSError：当前平台无法创建测试 symlink。
        AssertionError：symlink 被跟随或未形成稳定 finding。
    """

    row_root = (tmp_path / "row").resolve()
    config_root = row_root / "workspace/config"
    config_root.mkdir(parents=True)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("credential-outside-scope", encoding="utf-8")
    (config_root / "linked.json").symlink_to(outside)

    report = scan_persisted_secrets(
        row_root,
        credential_values=("credential-outside-scope",),
        canaries=(),
    )

    assert not report.passed
    assert report.scanned_file_count == 0
    assert report.accepted_observations == ()
    assert report.violations == (
        PersistedSecretViolation(
            violation_code="persisted_symlink",
            artifact_class=PersistedArtifactClass.CONFIG,
            count=1,
        ),
    )


def test_persisted_scan_fails_closed_on_special_file(tmp_path: Path) -> None:
    """验证 row tree 中 FIFO 等特殊文件形成稳定 fail-closed finding。

    参数：
        tmp_path：pytest 临时 row root。

    返回：
        无返回值。

    异常：
        OSError：当前 POSIX 平台无法创建测试 FIFO。
        AssertionError：特殊文件被读取或未形成稳定 finding。
    """

    row_root = (tmp_path / "row").resolve()
    artifact_root = row_root / "workspace/.dayu/artifacts"
    artifact_root.mkdir(parents=True)
    os.mkfifo(artifact_root / "diagnostic.pipe")

    report = scan_persisted_secrets(
        row_root,
        credential_values=(),
        canaries=(),
    )

    assert not report.passed
    assert report.scanned_file_count == 0
    assert report.accepted_observations == ()
    assert report.violations == (
        PersistedSecretViolation(
            violation_code="persisted_special_file",
            artifact_class=PersistedArtifactClass.TRACE_LOG_ARTIFACT,
            count=1,
        ),
    )


def test_evaluate_no_fallback_accepts_same_run_same_identity() -> None:
    """验证同一 run、同一 provider/model 身份通过 no-fallback。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：完整同源证据未通过。
    """

    identity = ProviderIdentity(
        family_id="mimo",
        provider="mimo",
        provider_model="mimo-v2",
    )
    verdict = evaluate_no_fallback(
        NoFallbackEvidence(
            expected_identity=identity,
            effective_identity=identity,
            request_attempted=True,
            host_run_id="run-1",
            trace_run_id="run-1",
            observed_identities=(identity,),
            alternate_success_observed=False,
        )
    )

    assert verdict.passed
    assert not verdict.fallback_observed
    assert verdict.reason_codes == ()


def test_evaluate_no_fallback_accepts_clean_preflight_failure() -> None:
    """验证未发请求且无 observed identity 的前置失败仍可证明无 fallback。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：干净 preflight failure 被误判。
    """

    verdict = evaluate_no_fallback(
        NoFallbackEvidence(
            expected_identity=None,
            effective_identity=None,
            request_attempted=False,
            host_run_id=None,
            trace_run_id=None,
            observed_identities=(),
            alternate_success_observed=False,
        )
    )

    assert verdict.passed
    assert not verdict.fallback_observed


def test_evaluate_no_fallback_requires_independent_identities_for_request() -> None:
    """验证已请求 row 缺 expected/effective identity 时 fail closed。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：请求路径接受了缺失或伪造的 identity。
    """

    verdict = evaluate_no_fallback(
        NoFallbackEvidence(
            expected_identity=None,
            effective_identity=None,
            request_attempted=True,
            host_run_id="run-1",
            trace_run_id="run-1",
            observed_identities=(),
            alternate_success_observed=False,
        )
    )

    assert not verdict.passed
    assert not verdict.fallback_observed
    assert set(verdict.reason_codes) == {
        "effective_identity_missing",
        "expected_identity_missing",
        "expected_identity_not_observed",
    }


def test_evaluate_no_fallback_rejects_identity_and_trace_drift() -> None:
    """验证 effective、observed、trace 和 alternate terminal 漂移均失败。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：任一 fallback 证据未进入裁决原因。
    """

    expected = ProviderIdentity(
        family_id="mimo",
        provider="mimo",
        provider_model="mimo-v2",
    )
    alternate = ProviderIdentity(
        family_id="deepseek",
        provider="deepseek",
        provider_model="deepseek-v4",
    )
    verdict = evaluate_no_fallback(
        NoFallbackEvidence(
            expected_identity=expected,
            effective_identity=alternate,
            request_attempted=True,
            host_run_id="run-1",
            trace_run_id="run-2",
            observed_identities=(alternate,),
            alternate_success_observed=True,
        )
    )

    assert not verdict.passed
    assert verdict.fallback_observed
    assert set(verdict.reason_codes) == {
        "alternate_identity_observed",
        "alternate_success_observed",
        "effective_identity_mismatch",
        "expected_identity_not_observed",
        "run_binding_mismatch",
    }


def test_evaluate_no_fallback_rejects_observation_without_request() -> None:
    """验证未声明请求却出现 run/identity 时 fail closed。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：矛盾证据未被拒绝。
    """

    verdict = evaluate_no_fallback(
        NoFallbackEvidence(
            expected_identity=None,
            effective_identity=None,
            request_attempted=False,
            host_run_id="run-1",
            trace_run_id=None,
            observed_identities=(
                ProviderIdentity(
                    family_id="mimo",
                    provider="mimo",
                    provider_model="mimo-v2",
                ),
            ),
            alternate_success_observed=False,
        )
    )

    assert not verdict.passed
    assert not verdict.fallback_observed
    assert set(verdict.reason_codes) == {
        "identity_observed_without_request",
        "unexpected_run_binding",
    }


def test_live_input_uses_existing_env_or_real_eof() -> None:
    """验证 init stdin 不生成 credential，缺失时以 EOF 结束。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：static/custom/Ollama 输入违反真实交互 contract。
    """

    mimo = find_init_model_choice("mimo-token-plan")
    custom = find_init_model_choice("custom-openai")
    ollama = find_init_model_choice("ollama")

    assert _init_stdin(mimo, {}) == "mimo-token-plan\n"
    assert _init_stdin(mimo, {"MIMO_PLAN_API_KEY": "present"}) == (
        "mimo-token-plan\n\n\n\n\n\n"
    )
    assert _init_stdin(custom, {}) == (
        "custom-openai\ns5b-custom-model\n\n\n"
    )
    assert _init_stdin(
        custom,
        {"CUSTOM_OPENAI_API_KEY": "present"},
    ) == "custom-openai\n"
    assert _init_stdin(ollama, {}) == "ollama\n\n\n\n\n\n\n\n\n"


def test_missing_credential_row_uses_real_init_eof_without_publication(
    tmp_path: Path,
) -> None:
    """验证 deterministic row 真实执行 secret EOF 且不触发 provider。

    参数：
        tmp_path：pytest fresh run root。

    返回：
        无返回值。

    异常：
        OSError：真实 init 子进程或 fresh tree 无法创建。
        AssertionError：缺 credential 分支发生 publication/request 或误分类。
    """

    run_root = tmp_path / "run"
    run_root.mkdir()
    process_env = dict(os.environ)
    process_env.pop("OPENAI_API_KEY", None)
    row = _run_matrix_row(
        find_init_model_choice("openai"),
        row_index=6,
        run_root=run_root,
        project_root=PROJECT_ROOT,
        manifest=load_manifest(FROZEN_MANIFEST_PATH),
        process_env=process_env,
        credential_values=(),
        canary="deterministic-row-canary",
    )

    assert row.preflight_class is PreflightClass.CREDENTIAL_MISSING
    assert row.availability_class is AvailabilityClass.CREDENTIAL_MISSING
    assert row.init_exit_code != 0
    assert row.prompt_exit_code is None
    assert row.publication_absent_after_rejection
    assert not row.request_attempted
    assert row.runner_calls == ()
    assert row.internal_contract_valid
    assert row.secret_scan.passed


def test_row_environment_and_managed_tree_are_isolated(
    tmp_path: Path,
) -> None:
    """验证 row HOME/XDG 隔离与 config tree digest 稳定。

    参数：
        tmp_path：pytest fresh 临时目录。

    返回：
        无返回值。

    异常：
        OSError：临时 tree 无法创建或读取。
        AssertionError：环境仍指向用户 HOME 或 digest/profile 判断错误。
    """

    home_root = (tmp_path / "home").resolve()
    home_root.mkdir()
    env = _row_environment(
        {"PATH": "/bin"},
        home_root=home_root,
        canary="canary-value",
    )
    assert env["HOME"] == str(home_root)
    assert env["XDG_CONFIG_HOME"].startswith(str(home_root))
    assert env["DAYU_S5B_SECRET_CANARY"] == "canary-value"

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    absent_digest = _config_tree_digest(workspace_root)
    config_root = workspace_root / "config"
    config_root.mkdir()
    (config_root / "value.json").write_text("{}\n", encoding="utf-8")
    assert _config_tree_digest(workspace_root) != absent_digest
    assert not _profile_publication_observed(home_root)
    (home_root / ".zshrc").write_text("export SAFE=1\n", encoding="utf-8")
    assert _profile_publication_observed(home_root)


def test_real_cli_subprocess_helper_runs_bounded_help(
    tmp_path: Path,
) -> None:
    """验证 subprocess helper 真实运行当前 CLI 且返回 typed 退出值。

    参数：
        tmp_path：pytest 临时 HOME 根。

    返回：
        无返回值。

    异常：
        OSError：真实 CLI 无法启动。
        AssertionError：help 进程未正常收口。
    """

    env = _row_environment(
        dict(os.environ),
        home_root=tmp_path.resolve(),
        canary="subprocess-canary",
    )
    result = _run_cli_subprocess(
        ("--help",),
        stdin_text="",
        env=env,
        cwd=PROJECT_ROOT,
        timeout_seconds=30.0,
    )

    assert result.exit_code == 0
    assert not result.timed_out
    assert "dayu-cli" in result.stdout


def test_redaction_preflight_and_credential_inventory_are_value_safe() -> None:
    """验证 process credential 只用于布尔分类与全文泄漏扫描。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：known value、Bearer 或 Authorization 未被移除。
    """

    env = {
        "MIMO_PLAN_API_KEY": "real-secret-value",
        "FMP_API_KEY": "fmp-secret-value",
    }
    values = _known_credential_values(env)
    assert set(values) == {"real-secret-value", "fmp-secret-value"}
    redacted = _redact_sensitive_text(
        (
            "Authorization: Bearer real-secret-value canary "
            "client_correlation_id=correlation-secret"
        ),
        credential_values=values,
        canary="canary",
        project_root=PROJECT_ROOT,
        run_root=PROJECT_ROOT / "workspace/tmp/wu-cli-init-01/run",
        workspace_root=(
            PROJECT_ROOT / "workspace/tmp/wu-cli-init-01/run/rows/P01/workspace"
        ),
    )
    assert "real-secret-value" not in redacted
    assert "canary" not in redacted
    assert "correlation-secret" not in redacted
    assert _preflight_for_choice(
        find_init_model_choice("mimo-token-plan"),
        env,
    ) is PreflightClass.REQUESTABLE
    assert _preflight_for_choice(
        find_init_model_choice("openai"),
        env,
    ) is PreflightClass.CREDENTIAL_MISSING
    assert _preflight_for_choice(
        find_init_model_choice("custom-openai"),
        {"CUSTOM_OPENAI_API_KEY": "present"},
    ) is PreflightClass.ENDPOINT_UNCONFIGURED


def test_effective_contract_and_failure_kind_fail_closed() -> None:
    """验证 assembly role identity 与 terminal error code 使用闭集映射。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：角色漂移或未知 terminal 未 fail closed。
    """

    choice = find_init_model_choice("openai")
    endpoint = RedactedEndpoint(
        scheme="https",
        hostname="api.example.com",
        port=None,
        path_sha256="a" * 64,
    )
    ordinary = EffectiveModelIdentity(
        config_model_id=choice.thinking_model_id,
        provider=choice.expected_provider,
        provider_model="gpt-5.4",
        endpoint=endpoint,
        credential_ref=choice.required_secret_env_name,
    )
    compactor = EffectiveModelIdentity(
        config_model_id=choice.ordinary_model_id,
        provider=choice.expected_provider,
        provider_model="gpt-5.4",
        endpoint=endpoint,
        credential_ref=choice.required_secret_env_name,
    )
    assert _effective_contract_valid(choice, ordinary, compactor)
    assert not _effective_contract_valid(
        choice,
        replace(ordinary, config_model_id="wrong"),
        compactor,
    )

    observation = HostObservation(
        internal_contract_valid=True,
        host_run_id="run-1",
        terminal_status=TerminalStatus.FAILED,
        terminal_error_code="network_error",
        terminal_text="network unavailable",
        request_attempted=True,
        successful_response_received=False,
        provider_request_id_present=False,
        client_correlation_id_present=True,
        runner_calls=(),
    )
    prompt_result = SubprocessResult(
        exit_code=1,
        stdout="",
        stderr="",
        timed_out=False,
    )
    assert _failure_kind(
        preflight=PreflightClass.REQUESTABLE,
        observation=observation,
        prompt_result=prompt_result,
    ) is FailureKind.TRANSPORT
    assert _failure_kind(
        preflight=PreflightClass.REQUESTABLE,
        observation=replace(observation, terminal_error_code="unknown"),
        prompt_result=prompt_result,
    ) is FailureKind.INTERNAL_PRODUCT_BUG
    assert _failure_kind(
        preflight=PreflightClass.REQUESTABLE,
        observation=observation,
        prompt_result=replace(prompt_result, timed_out=True),
    ) is FailureKind.INTERNAL_PRODUCT_BUG
    assert _failure_kind(
        preflight=PreflightClass.CREDENTIAL_MISSING,
        observation=None,
        prompt_result=None,
    ) is FailureKind.NONE
    assert _failure_kind(
        preflight=PreflightClass.REQUESTABLE,
        observation=replace(
            observation,
            terminal_status=TerminalStatus.SUCCEEDED,
            terminal_error_code=None,
        ),
        prompt_result=prompt_result,
    ) is FailureKind.NONE
    assert _failure_kind(
        preflight=PreflightClass.REQUESTABLE,
        observation=replace(
            observation,
            terminal_error_code="rate_limit_exceeded",
        ),
        prompt_result=prompt_result,
    ) is FailureKind.RATE_LIMITED
    assert _failure_kind(
        preflight=PreflightClass.REQUESTABLE,
        observation=replace(
            observation,
            terminal_error_code="server_error",
        ),
        prompt_result=prompt_result,
    ) is FailureKind.PROVIDER_REJECTED


def test_production_assembly_projects_full_effective_identities(
    openai_publication_tree: Path,
) -> None:
    """验证 expected package truth 与 effective assembly identity 独立同值。

    参数：
        openai_publication_tree：production owner 生成的 OpenAI publication。

    返回：
        无返回值。

    异常：
        Exception：production runtime/scene/tool/assembly contract 失败。
        AssertionError：ordinary/compactor role identity 漂移。
    """

    ordinary, compactor = asyncio.run(
        _read_effective_identities(
            openai_publication_tree,
            PACKAGE_CONFIG_ROOT,
            {"OPENAI_API_KEY": "deterministic-assembly-only"},
        )
    )
    choice = find_init_model_choice("openai")
    expected = _expected_provider_identity(choice, PACKAGE_CONFIG_ROOT)

    assert ordinary.config_model_id == "gpt-5.4-thinking"
    assert compactor.config_model_id == "gpt-5.4"
    assert ordinary.provider == compactor.provider == "openai"
    assert ordinary.provider_model == compactor.provider_model == "gpt-5.4"
    assert ordinary.credential_ref == compactor.credential_ref == (
        "OPENAI_API_KEY"
    )
    assert choice.thinking_model_id != expected.provider_model
    assert expected == ProviderIdentity(
        family_id="openai",
        provider="openai",
        provider_model="gpt-5.4",
    )
    assert expected == ProviderIdentity(
        family_id=ordinary.provider,
        provider=ordinary.provider,
        provider_model=ordinary.provider_model,
    )


def test_payload_text_reader_and_full_row_projection_are_strict() -> None:
    """验证 canonical payload 白名单读取与完整 identity JSON 投影。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：非法 payload 未拒绝或完整 endpoint 被写入。
    """

    assert _optional_payload_text({"error_code": "network_error"}, "error_code") == (
        "network_error"
    )
    assert _optional_payload_text({}, "error_code") is None
    with pytest.raises(ValueError, match="error_code"):
        _optional_payload_text({"error_code": 7}, "error_code")

    endpoint = RedactedEndpoint(
        scheme="https",
        hostname="api.example.com",
        port=443,
        path_sha256="b" * 64,
    )
    identity = EffectiveModelIdentity(
        config_model_id="model-thinking",
        provider="provider",
        provider_model="provider-model",
        endpoint=endpoint,
        credential_ref="PROVIDER_API_KEY",
    )
    call = RunnerCallIdentity(
        event_id="event-1",
        manifest_ref="manifest-ref",
        manifest_digest="c" * 64,
        input_projection_digest="d" * 64,
        provider="provider",
        provider_model="provider-model",
    )
    row = replace(
        _passing_non_requestable_row(1),
        ordinary_identity=identity,
        compactor_identity=replace(
            identity,
            config_model_id="model",
        ),
        runner_calls=(call,),
    )
    text = _json_text(_row_json(row))

    assert '"hostname": "api.example.com"' in text
    assert '"path_sha256"' in text
    assert "manifest-ref" in text
    assert "https://api.example.com" not in text


def test_matrix_exit_and_json_projection_are_fail_closed() -> None:
    """验证 15-row completeness、availability evidence 与安全 JSON 投影。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：缺 row、内部失败或证据矛盾未导致非零。
    """

    rows = tuple(_passing_non_requestable_row(index) for index in range(1, 16))
    assert matrix_exit_code(rows) == 0
    assert matrix_exit_code(rows[:-1]) == 1
    requestable_failure = replace(
        rows[0],
        preflight_class=PreflightClass.REQUESTABLE,
        availability_class=AvailabilityClass.PROVIDER_REJECTED,
        request_attempted=True,
        prompt_exit_code=1,
        terminal_status=TerminalStatus.FAILED,
    )
    assert matrix_exit_code((requestable_failure, *rows[1:])) == 1
    endpoint = RedactedEndpoint(
        scheme="https",
        hostname="api.example.com",
        port=None,
        path_sha256="b" * 64,
    )
    ordinary = EffectiveModelIdentity(
        config_model_id="model-thinking",
        provider="provider",
        provider_model="provider-model",
        endpoint=endpoint,
        credential_ref="PROVIDER_API_KEY",
    )
    call = RunnerCallIdentity(
        event_id="event-1",
        manifest_ref="manifest-ref",
        manifest_digest="c" * 64,
        input_projection_digest="d" * 64,
        provider="provider",
        provider_model="provider-model",
    )
    valid_external_unavailable = replace(
        rows[0],
        required_credential_ref="PROVIDER_API_KEY",
        credential_present=True,
        preflight_class=PreflightClass.REQUESTABLE,
        availability_class=AvailabilityClass.PROVIDER_REJECTED,
        init_exit_code=0,
        prompt_exit_code=1,
        publication_valid=True,
        publication_absent_after_rejection=False,
        config_tree_digest_after_init="b" * 64,
        config_tree_digest_after_prompt="b" * 64,
        request_attempted=True,
        successful_response_received=False,
        client_correlation_id_present=True,
        host_run_id="run-1",
        ordinary_identity=ordinary,
        compactor_identity=replace(
            ordinary,
            config_model_id="model",
        ),
        runner_calls=(call,),
        terminal_status=TerminalStatus.FAILED,
    )
    assert matrix_exit_code(
        (valid_external_unavailable, *rows[1:])
    ) == 0
    assert matrix_exit_code(
        (
            replace(
                valid_external_unavailable,
                availability_class=AvailabilityClass.RATE_LIMITED,
            ),
            *rows[1:],
        )
    ) == 0
    valid_available = replace(
        valid_external_unavailable,
        availability_class=AvailabilityClass.AVAILABLE,
        prompt_exit_code=0,
        successful_response_received=True,
        terminal_status=TerminalStatus.SUCCEEDED,
    )
    assert matrix_exit_code((valid_available, *rows[1:])) == 0
    assert matrix_exit_code(
        (
            replace(valid_available, successful_response_received=False),
            *rows[1:],
        )
    ) == 1
    internal_failure = replace(rows[0], internal_contract_valid=False)
    assert matrix_exit_code((internal_failure, *rows[1:])) == 1
    accepted_host_observation = replace(
        rows[0],
        persisted_secret_scan=PersistedSecretScanReport(
            passed=True,
            scanned_file_count=1,
            scanned_byte_count=128,
            accepted_observations=(
                PersistedCredentialObservation(
                    observation_code="host_sqlite_credential_value",
                    artifact_class=PersistedArtifactClass.HOST_SQLITE,
                    count=1,
                ),
            ),
            violations=(),
        ),
    )
    assert matrix_exit_code((accepted_host_observation, *rows[1:])) == 0
    persisted_failure = replace(
        rows[0],
        persisted_secret_scan=PersistedSecretScanReport(
            passed=False,
            scanned_file_count=1,
            scanned_byte_count=128,
            accepted_observations=(),
            violations=(
                PersistedSecretViolation(
                    violation_code="persisted_credential_value",
                    artifact_class=PersistedArtifactClass.CONFIG,
                    count=1,
                ),
            ),
        ),
    )
    assert matrix_exit_code((persisted_failure, *rows[1:])) == 1

    projected = _row_json(rows[0])
    text = _json_text(projected)
    assert '"role_coverage"' in text
    assert '"credential_present": false' in text
    assert "TEST_API_KEY" in text
    assert "S5B_OK" not in text


def test_reconciliation_recomputes_contract_from_owner_evidence() -> None:
    """验证 reconciliation 不沿用旧 persistence 派生值。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：owner evidence 未恢复 internal/availability contract。
    """

    choice = find_init_model_choice("mimo-token-plan")
    expected_provider = _expected_provider_identity(
        choice,
        PACKAGE_CONFIG_ROOT,
    )
    endpoint = RedactedEndpoint(
        scheme="https",
        hostname="api.example.com",
        port=None,
        path_sha256="b" * 64,
    )
    ordinary = EffectiveModelIdentity(
        config_model_id=choice.thinking_model_id,
        provider=choice.expected_provider,
        provider_model=expected_provider.provider_model,
        endpoint=endpoint,
        credential_ref=choice.required_secret_env_name,
    )
    call = RunnerCallIdentity(
        event_id="event-1",
        manifest_ref="manifest-ref",
        manifest_digest="c" * 64,
        input_projection_digest="d" * 64,
        provider=choice.expected_provider,
        provider_model=expected_provider.provider_model,
    )
    old_misclassified_row = replace(
        _passing_non_requestable_row(1),
        scenario_id="P01-mimo-token-plan",
        choice_id=choice.choice_id,
        expected_ordinary_model_id=choice.thinking_model_id,
        expected_compactor_model_id=choice.ordinary_model_id,
        required_credential_ref=choice.required_secret_env_name,
        credential_present=True,
        preflight_class=PreflightClass.REQUESTABLE,
        availability_class=AvailabilityClass.INTERNAL_PRODUCT_BUG,
        init_exit_code=0,
        prompt_exit_code=1,
        publication_valid=True,
        publication_absent_after_rejection=False,
        config_tree_digest_after_init="b" * 64,
        config_tree_digest_after_prompt="b" * 64,
        request_attempted=True,
        successful_response_received=False,
        client_correlation_id_present=True,
        host_run_id="run-1",
        ordinary_identity=ordinary,
        compactor_identity=replace(
            ordinary,
            config_model_id=choice.ordinary_model_id,
        ),
        runner_calls=(call,),
        terminal_status=TerminalStatus.FAILED,
        no_fallback=NoFallbackVerdict(
            passed=False,
            fallback_observed=True,
            reason_codes=("stale_old_live_verdict",),
        ),
        internal_contract_valid=False,
    )
    row_json = _row_json(old_misclassified_row)
    observation = HostObservation(
        internal_contract_valid=True,
        host_run_id="run-1",
        terminal_status=TerminalStatus.FAILED,
        terminal_error_code="rate_limit_exceeded",
        terminal_text="rate limited",
        request_attempted=True,
        successful_response_received=False,
        provider_request_id_present=True,
        client_correlation_id_present=True,
        runner_calls=(call,),
    )

    internal_valid = _reconciled_row_internal_contract_valid(
        row_json,
        choice=choice,
        observation=observation,
    )

    assert internal_valid
    canonical_no_fallback = _reconciled_no_fallback_verdict(
        row_json,
        choice=choice,
        package_config_root=PACKAGE_CONFIG_ROOT,
        workspace_config_root=None,
        observation=observation,
    )
    assert canonical_no_fallback.passed
    assert not canonical_no_fallback.fallback_observed
    assert canonical_no_fallback.reason_codes == ()
    assert (
        _reconciled_availability_class(
            row_json,
            internal_contract_valid=internal_valid,
            observation=observation,
        )
        is AvailabilityClass.RATE_LIMITED
    )
    assert (
        _reconciled_availability_class(
            row_json,
            internal_contract_valid=internal_valid,
            observation=replace(
                observation,
                terminal_error_code="provider_error",
            ),
        )
        is AvailabilityClass.PROVIDER_REJECTED
    )
    assert (
        _reconciled_availability_class(
            row_json,
            internal_contract_valid=internal_valid,
            observation=replace(
                observation,
                terminal_error_code="network_error",
            ),
        )
        is AvailabilityClass.SERVICE_UNREACHABLE
    )
    assert (
        _reconciled_availability_class(
            row_json,
            internal_contract_valid=internal_valid,
            observation=replace(
                observation,
                terminal_error_code="unclassified_error",
            ),
        )
        is AvailabilityClass.INTERNAL_PRODUCT_BUG
    )


def test_reconcile_existing_report_scans_same_run_without_raw_backup(
    tmp_path: Path,
) -> None:
    """验证既有 run 原位接受 Host observation 且不创建 raw backup。

    参数：
        tmp_path：pytest 临时 project/run root。

    返回：
        无返回值。

    异常：
        sqlite3.Error：真实临时 Host SQLite 无法建立。
        AssertionError：reconciliation 误判、泄漏或留下 raw backup。
    """

    project_root = tmp_path.resolve()
    run_root = (
        project_root
        / "workspace/tmp/wu-cli-init-01/20260730T000000Z-test"
    )
    rows_root = run_root / "rows"
    rows_root.mkdir(parents=True)
    credential = "same-run-persisted-credential"
    typed_rows: list[ProviderMatrixRowReport] = []
    for index, choice in enumerate(INIT_MODEL_CHOICES, start=1):
        scenario_id = f"P{index:02d}-{choice.choice_id}"
        row_root = rows_root / scenario_id
        workspace_root = row_root / "workspace"
        workspace_root.mkdir(parents=True)
        (row_root / "home").mkdir()
        (workspace_root / ".dayu-init.lock").write_bytes(b"")
        row = replace(
            _passing_non_requestable_row(index),
            scenario_id=scenario_id,
            choice_id=choice.choice_id,
            no_fallback=NoFallbackVerdict(
                passed=False,
                fallback_observed=True,
                reason_codes=("stale_old_live_verdict",),
            ),
        )
        if index == 1:
            unsafe_preview = (
                f"workspace={workspace_root} "
                f"Authorization: Bearer {credential} "
                "legacy-canary-value-unavailable "
                "provider_request_id=provider-request-raw "
                "client_correlation_id=client-request-raw"
            )
            row = replace(
                row,
                terminal_summary=summarize_bounded_text(unsafe_preview),
            )
            host_root = workspace_root / ".dayu/host"
            host_root.mkdir(parents=True)
            with sqlite3.connect(
                host_root / "dayu_host.sqlite3"
            ) as connection:
                connection.execute(
                    "CREATE TABLE event_log(payload_json TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO event_log(payload_json) VALUES (?)",
                    (f'{{"Authorization":"Bearer {credential}"}}',),
                )
                connection.commit()
        typed_rows.append(row)
    report = ProviderMatrixReport(
        oracle_id="cli.init.workspace-initialization",
        oracle_version=1,
        matrix_run_id=run_root.name,
        started_at="2026-07-30T00:00:00+00:00",
        completed_at="2026-07-30T00:01:00+00:00",
        overall_exit_code=0,
        rows=tuple(typed_rows),
        secret_scan=SecretScanReport(passed=True, finding_codes=()),
    )
    report_path = run_root / "matrix-report.json"
    report_path.write_text(
        _json_text(_report_json(report)),
        encoding="utf-8",
    )

    result = reconcile_existing_report(
        report_path=report_path,
        project_root=project_root,
        process_env={"MIMO_PLAN_API_KEY": credential},
    )

    final_text = report_path.read_text(encoding="utf-8")
    final_document = json.loads(final_text)
    assert isinstance(final_document, dict)
    final_rows = final_document["rows"]
    assert isinstance(final_rows, list)
    first_row = final_rows[0]
    assert isinstance(first_row, dict)
    assert result.overall_exit_code == 0
    assert result.accepted_host_credential_observation_row_count == 1
    assert result.persistence_violation_row_count == 0
    assert final_document["overall_exit_code"] == 0
    assert first_row["availability_class"] == "credential_missing"
    assert first_row["internal_contract_valid"] is True
    assert first_row["no_fallback"] == {
        "fallback_observed": False,
        "passed": True,
        "reason_codes": [],
    }
    assert all(
        isinstance(row, dict) and row["no_fallback"]["passed"] is True
        for row in final_rows
    )
    persisted_scan = first_row["persisted_secret_scan"]
    assert isinstance(persisted_scan, dict)
    assert persisted_scan["accepted_observations"] == [
        {
            "artifact_class": "workspace/host_sqlite",
            "count": 1,
            "observation_code": "host_sqlite_credential_value",
        }
    ]
    assert persisted_scan["violations"] == []
    assert persisted_scan["passed"] is True
    assert persisted_scan["scanned_file_count"] == 2
    assert isinstance(persisted_scan["scanned_byte_count"], int)
    assert persisted_scan["scanned_byte_count"] > 0
    assert credential not in final_text
    assert "legacy-canary-value-unavailable" not in final_text
    assert "provider-request-raw" not in final_text
    assert "client-request-raw" not in final_text
    assert str(project_root) not in final_text
    assert "[WORKSPACE_ROOT]" in final_text
    assert sorted(path.name for path in run_root.iterdir()) == [
        "matrix-report.json",
        "rows",
    ]


def test_live_matrix_rejects_invalid_project_root_without_side_effect(
    tmp_path: Path,
) -> None:
    """验证 live orchestrator 在无效 project root 上明确拒绝。

    参数：
        tmp_path：pytest 临时目录。

    返回：
        无返回值。

    异常：
        AssertionError：无效根未在任何 row 创建前拒绝。
    """

    missing = (tmp_path / "missing").resolve()
    with pytest.raises(ValueError, match="project_root"):
        run_live_matrix(project_root=missing, process_env={})
    assert not missing.exists()


def test_main_declares_explicit_integer_return_without_not_implemented() -> None:
    """验证 live main 保持明确整数返回 contract。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：入口返回注解漂移或残留 NotImplementedError。
    """

    assert get_type_hints(main)["return"] is int
    assert main.__doc__ is not None
    assert "NotImplementedError" not in main.__doc__


def test_main_rejects_unknown_oracle_before_live_execution() -> None:
    """验证非法 oracle 参数在任何 live 副作用前由 argparse 拒绝。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：未知 oracle 未得到稳定非零 SystemExit。
    """

    with pytest.raises(SystemExit) as caught:
        main(["--oracle-version", "999"])

    assert caught.value.code == 2
