"""验证 CLI init/provider matrix 的 S5-A 确定性 contract。"""

from __future__ import annotations

import hashlib
import platform
import shutil
from pathlib import Path

import pytest

from dayu.cli.init_catalog import InitModelSelection, find_init_model_choice
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
    FailureKind,
    ManifestValidationError,
    NoFallbackEvidence,
    PreflightClass,
    ProviderIdentity,
    classify_availability,
    classify_preflight,
    evaluate_no_fallback,
    load_manifest,
    main,
    redact_endpoint,
    scan_secrets,
    summarize_bounded_text,
    validate_publication_tree,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_CONFIG_ROOT = PROJECT_ROOT / "dayu" / "config"
FROZEN_MANIFEST_PATH = PROJECT_ROOT / "docs" / "cli_init_workspace_manifest_v1.json"
FROZEN_MANIFEST_SHA256 = (
    "a4865273f11ce059aaabaf9d91ee1154a7f5c1f26794828c343a20e0e73cea88"
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

    identity = ProviderIdentity(
        family_id="openai",
        provider="openai",
        provider_model="gpt",
    )
    verdict = evaluate_no_fallback(
        NoFallbackEvidence(
            expected_identity=identity,
            effective_identity=identity,
            request_attempted=False,
            host_run_id=None,
            trace_run_id=None,
            observed_identities=(),
            alternate_success_observed=False,
        )
    )

    assert verdict.passed
    assert not verdict.fallback_observed


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

    identity = ProviderIdentity(
        family_id="mimo",
        provider="mimo",
        provider_model="mimo-v2",
    )
    verdict = evaluate_no_fallback(
        NoFallbackEvidence(
            expected_identity=identity,
            effective_identity=identity,
            request_attempted=False,
            host_run_id="run-1",
            trace_run_id=None,
            observed_identities=(identity,),
            alternate_success_observed=False,
        )
    )

    assert not verdict.passed
    assert not verdict.fallback_observed
    assert set(verdict.reason_codes) == {
        "identity_observed_without_request",
        "unexpected_run_binding",
    }


def test_main_is_explicitly_not_implemented_for_live_execution() -> None:
    """验证当前 argparse 入口明确拒绝尚未实现的 live 路径。

    参数：
        无。

    返回：
        无返回值。

    异常：
        AssertionError：入口未抛出预期 NotImplementedError。
    """

    with pytest.raises(NotImplementedError, match="live provider matrix"):
        main(["--oracle-version", "1"])
