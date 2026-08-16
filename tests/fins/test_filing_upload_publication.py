"""Filing upload publication identity 与纯裁决 owner 测试。"""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from dayu.fins.domain.document_models import CompanyMeta, SourceDocumentRevision
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    FinsUploadFilingRequest,
    ValidatedFinsUploadFilingRequest,
    validate_fins_upload_filing_request,
)
from dayu.fins.pipelines.docling_upload_service import (
    FilingInitialSkipDisposition,
    build_sec_filing_ids,
)
from dayu.fins.pipelines.filing_upload_publication import (
    FilingUploadPublicationDisposition,
    FilingUploadPublishMode,
    arbitrate_filing_upload_publication,
)
from dayu.fins.storage import (
    FILING_UPLOAD_ASSET_SOURCE_DOCLING,
    FILING_UPLOAD_ASSET_SOURCE_ORIGINAL,
    FilingUploadAssetDescriptor,
    FilingUploadPublicationIdentity,
    FilingUploadPublishedState,
    SourceIntegrityClassification,
    SourceIntegrityReason,
    SourceIntegrityStatus,
)
from dayu.fins.ticker_normalization import build_company_ticker_identity
from dayu.fins.upload_failure import FinsUploadFailureCode

_FINGERPRINT_A = "a" * 64
_FINGERPRINT_B = "b" * 64
_ORIGINAL_PRIMARY_SHA = "c" * 64
_ORIGINAL_COMPANION_SHA = "d" * 64
_DOCLING_SHA = "e" * 64
_RESOLVER_VERSION = "market_resolver_v1.0.0"


def _build_publication_identity(
    *,
    primary_original_name: str = "original-main.pdf",
    source_fingerprint: str = _FINGERPRINT_A,
    companion_sha256: str = _ORIGINAL_COMPANION_SHA,
    docling_sha256: str = _DOCLING_SHA,
    docling_content_type: str = "application/json",
) -> FilingUploadPublicationIdentity:
    """构造满足 exact equality contract 的多文件 publication identity。

    Args:
        primary_original_name: 当前 authoritative primary 的 storage name。
        source_fingerprint: publication source fingerprint。
        companion_sha256: companion original 摘要。
        docling_sha256: primary Docling 派生内容摘要。
        docling_content_type: primary Docling 内容类型。

    Returns:
        稳定排序且无路径字段的 publication identity。

    Raises:
        ValueError: primary storage name 不属于 fixture originals 时抛出。
    """

    original_names = ("original-appendix.xlsx", "original-main.pdf")
    if primary_original_name not in original_names:
        raise ValueError("primary fixture 必须命中 original storage name")
    original_assets = (
        FilingUploadAssetDescriptor(
            name="original-appendix.xlsx",
            original_filename="appendix.xlsx",
            derived_from=None,
            sha256=companion_sha256,
            size=13,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            source=FILING_UPLOAD_ASSET_SOURCE_ORIGINAL,
        ),
        FilingUploadAssetDescriptor(
            name="original-main.pdf",
            original_filename="main.pdf",
            derived_from=None,
            sha256=_ORIGINAL_PRIMARY_SHA,
            size=11,
            content_type="application/pdf",
            source=FILING_UPLOAD_ASSET_SOURCE_ORIGINAL,
        ),
    )
    primary_basename = "main.pdf" if primary_original_name.endswith("main.pdf") else "appendix.xlsx"
    docling_name = f"{primary_original_name}_docling.json"
    docling_asset = FilingUploadAssetDescriptor(
        name=docling_name,
        original_filename=primary_basename,
        derived_from=primary_original_name,
        sha256=docling_sha256,
        size=17,
        content_type=docling_content_type,
        source=FILING_UPLOAD_ASSET_SOURCE_DOCLING,
    )
    document_id, internal_document_id = build_sec_filing_ids(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    return FilingUploadPublicationIdentity(
        ticker="AAPL",
        document_id=document_id,
        internal_document_id=internal_document_id,
        form_type="10-K",
        company_id="company-aapl",
        ingest_method="upload",
        fiscal_year=2024,
        fiscal_period="FY",
        report_kind="annual",
        filing_date="2025-01-31",
        report_date="2024-12-31",
        amended=False,
        source_provider="user_upload",
        is_deleted=False,
        document_version="v1",
        source_fingerprint=source_fingerprint,
        primary_document=docling_name,
        primary_original_asset_name=primary_original_name,
        companion_original_asset_names=tuple(
            sorted(name for name in original_names if name != primary_original_name)
        ),
        assets=tuple(sorted((*original_assets, docling_asset), key=lambda asset: asset.name)),
    )


def _fresh_company_meta() -> CompanyMeta:
    """构造能令 company resolver 精确返回 keep 的 durable company meta。

    Args:
        无。

    Returns:
        当前 resolver version 下的 AAPL company meta。

    Raises:
        ValueError: ticker identity fixture 非法时抛出。
    """

    return CompanyMeta(
        company_id="company-aapl",
        company_name="Apple Inc.",
        ticker_identity=build_company_ticker_identity("AAPL", ()),
        resolver_version=_RESOLVER_VERSION,
        updated_at="2025-01-01T00:00:00+00:00",
    )


def _build_request(
    file_path: Path,
    *,
    action: str = "auto",
    overwrite: bool = False,
) -> FinsUploadFilingRequest:
    """构造同一 arbitration 前后可重复验证的 filing raw request。

    Args:
        file_path: 已存在的 authoritative primary 文件。
        action: raw upload action。
        overwrite: raw overwrite 开关。

    Returns:
        AAPL FY2024 filing request。

    Raises:
        无。
    """

    return FinsUploadFilingRequest(
        ticker="AAPL",
        action=action,
        files=(file_path,),
        primary_selectors=(file_path,),
        fiscal_year=2024,
        fiscal_period="FY",
        filing_date="2025-01-31",
        report_date="2024-12-31",
        company_name="Apple Inc.",
        overwrite=overwrite,
    )


def _build_validated_request(
    request: FinsUploadFilingRequest,
    *,
    status: SourceIntegrityStatus,
    revision: str | None = None,
    publication_identity: FilingUploadPublicationIdentity | None = None,
    company_meta: CompanyMeta | None = None,
) -> ValidatedFinsUploadFilingRequest:
    """按指定 storage observation 运行真实 filing validator。

    Args:
        request: 两次 arbitration 共用的不可变 raw request。
        status: 当前 exact target integrity status。
        revision: COMPLETE/REPAIR_REQUIRED 的 opaque revision。
        publication_identity: COMPLETE user-upload target 的可选 exact identity。
        company_meta: 当前同版 company meta。

    Returns:
        真实 validator 产生的 typed request。

    Raises:
        ValueError: status/revision 或 request/state contract 不一致时抛出。
    """

    document_id, _internal_document_id = build_sec_filing_ids(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    if status is SourceIntegrityStatus.MISSING:
        source_revision = None
        reasons: tuple[SourceIntegrityReason, ...] = ()
        source_meta = None
    elif status is SourceIntegrityStatus.COMPLETE:
        if revision is None:
            raise ValueError("COMPLETE fixture 必须携带 revision")
        source_revision = SourceDocumentRevision(revision)
        reasons = ()
        source_meta = {"is_deleted": False}
    elif status is SourceIntegrityStatus.REPAIR_REQUIRED:
        if revision is None:
            raise ValueError("REPAIR_REQUIRED fixture 必须携带 revision")
        source_revision = SourceDocumentRevision(revision)
        reasons = (SourceIntegrityReason.ORIGINAL_FILE_MISSING,)
        source_meta = {"is_deleted": False}
    else:
        raise ValueError("pure arbitration fixture 不构造 UNSAFE validated request")
    state = FilingUploadPublishedState(
        company_meta=company_meta,
        source_integrity=SourceIntegrityClassification(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            document_id=document_id,
            revision=source_revision,
            status=status,
            reasons=reasons,
        ),
        source_meta=source_meta,
        publication_identity=(
            publication_identity if status is SourceIntegrityStatus.COMPLETE else None
        ),
    )
    return validate_fins_upload_filing_request(request, published_state=state)


def test_publication_identity_is_exact_sorted_path_free_business_fact() -> None:
    """identity 必须跟踪角色/全部资产事实并拒绝路径语义。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: exact equality、排序、角色或无路径 contract 漂移时抛出。
    """

    identity = _build_publication_identity()
    primary_flipped = _build_publication_identity(
        primary_original_name="original-appendix.xlsx"
    )
    companion_changed = _build_publication_identity(companion_sha256="f" * 64)
    derived_bytes_changed = _build_publication_identity(docling_sha256="1" * 64)
    derived_content_type_changed = _build_publication_identity(
        docling_content_type="application/octet-stream"
    )

    assert tuple(asset.name for asset in identity.assets) == tuple(
        sorted(asset.name for asset in identity.assets)
    )
    assert identity.companion_original_asset_names == ("original-appendix.xlsx",)
    assert identity.primary_original_asset_name == "original-main.pdf"
    assert all(asset.source in {"original", "docling"} for asset in identity.assets)
    assert identity != primary_flipped
    assert identity != companion_changed
    assert identity != derived_bytes_changed
    assert identity != derived_content_type_changed
    assert "/private/" not in repr(identity)
    assert not {"path", "uri", "etag", "last_modified", "revision"}.intersection(
        field.name for field in fields(identity)
    )
    with pytest.raises(ValueError, match="无路径 basename"):
        replace(identity.assets[0], name="/private/report.pdf")


def test_publication_identity_rejects_non_string_business_text() -> None:
    """identity owner 必须在运行时拒绝 required text 与 content type 的错误类型。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非字符串业务文本被 closed contract 接受时抛出。
    """

    identity = _build_publication_identity()
    with pytest.raises(TypeError, match="fiscal_period 必须是字符串"):
        replace(identity, fiscal_period=2024)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="name 与 original_filename 必须是字符串"):
        replace(identity.assets[0], name=7)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="content_type 必须是字符串或 None"):
        replace(identity.assets[0], content_type=5)  # type: ignore[arg-type]


def test_arbitration_closed_table_for_stable_and_changed_observations(
    tmp_path: Path,
) -> None:
    """pure owner 必须覆盖 stable、convergence、rebase 与 conflict 封闭分支。

    Args:
        tmp_path: authoritative primary fixture 目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一 frozen arbitration 决策或 typed reason 漂移时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    identity = _build_publication_identity()
    durable_company = _fresh_company_meta()

    auto_request = _build_request(primary)
    missing_initial = _build_validated_request(
        auto_request,
        status=SourceIntegrityStatus.MISSING,
    )
    missing_fresh = _build_validated_request(
        auto_request,
        status=SourceIntegrityStatus.MISSING,
    )
    stable_missing = arbitrate_filing_upload_publication(
        initial_request=missing_initial,
        fresh_request=missing_fresh,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert stable_missing.disposition is FilingUploadPublicationDisposition.PUBLISH
    assert stable_missing.publish_mode is FilingUploadPublishMode.PREPARED

    complete_winner = _build_validated_request(
        auto_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="winner",
        publication_identity=identity,
        company_meta=durable_company,
    )
    converged = arbitrate_filing_upload_publication(
        initial_request=missing_initial,
        fresh_request=complete_winner,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert converged.disposition is FilingUploadPublicationDisposition.SKIP

    company_not_durable = _build_validated_request(
        auto_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="winner",
        publication_identity=identity,
        company_meta=None,
    )
    company_conflict = arbitrate_filing_upload_publication(
        initial_request=missing_initial,
        fresh_request=company_not_durable,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert company_conflict.failure_reason is not None
    assert company_conflict.failure_reason.code is FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT

    identity_conflict = arbitrate_filing_upload_publication(
        initial_request=missing_initial,
        fresh_request=complete_winner,
        prepared_identity=_build_publication_identity(source_fingerprint=_FINGERPRINT_B),
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert identity_conflict.failure_reason is not None
    assert identity_conflict.failure_reason.code is FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT

    overwrite_request = _build_request(primary, action="create", overwrite=True)
    overwrite_initial = _build_validated_request(
        overwrite_request,
        status=SourceIntegrityStatus.MISSING,
    )
    overwrite_fresh = _build_validated_request(
        overwrite_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="winner",
        publication_identity=identity,
        company_meta=durable_company,
    )
    rebased = arbitrate_filing_upload_publication(
        initial_request=overwrite_initial,
        fresh_request=overwrite_fresh,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert rebased.disposition is FilingUploadPublicationDisposition.PUBLISH
    assert rebased.publish_mode is FilingUploadPublishMode.REBASE_CREATE_OVERWRITE


def test_arbitration_preserves_retransmission_and_repair_ownership(
    tmp_path: Path,
) -> None:
    """stable retransmission 与 repair revision 漂移必须由各自 typed owner 裁决。

    Args:
        tmp_path: authoritative primary fixture 目录。

    Returns:
        无。

    Raises:
        AssertionError: stable skip/publish 或 repair stale code 漂移时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    identity = _build_publication_identity()
    durable_company = _fresh_company_meta()
    update_request = _build_request(primary, action="update")
    complete_initial = _build_validated_request(
        update_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="stable",
        publication_identity=identity,
        company_meta=durable_company,
    )
    complete_fresh = _build_validated_request(
        update_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="stable",
        publication_identity=identity,
        company_meta=durable_company,
    )
    retransmission = arbitrate_filing_upload_publication(
        initial_request=complete_initial,
        fresh_request=complete_fresh,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.IDENTICAL_PUBLICATION,
    )
    assert retransmission.disposition is FilingUploadPublicationDisposition.SKIP

    ordinary_stable_update = arbitrate_filing_upload_publication(
        initial_request=complete_initial,
        fresh_request=complete_fresh,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert ordinary_stable_update.disposition is FilingUploadPublicationDisposition.PUBLISH
    assert ordinary_stable_update.publish_mode is FilingUploadPublishMode.PREPARED

    complete_changed = _build_validated_request(
        update_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="changed",
        publication_identity=identity,
        company_meta=durable_company,
    )
    changed_complete = arbitrate_filing_upload_publication(
        initial_request=complete_initial,
        fresh_request=complete_changed,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.IDENTICAL_PUBLICATION,
    )
    assert changed_complete.failure_reason is not None
    assert changed_complete.failure_reason.code is FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT

    repair_request = _build_request(primary)
    repair_initial = _build_validated_request(
        repair_request,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        revision="repair-a",
        company_meta=durable_company,
    )
    repair_stable = _build_validated_request(
        repair_request,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        revision="repair-a",
        company_meta=durable_company,
    )
    stable_repair = arbitrate_filing_upload_publication(
        initial_request=repair_initial,
        fresh_request=repair_stable,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert stable_repair.disposition is FilingUploadPublicationDisposition.PUBLISH

    repair_changed = _build_validated_request(
        repair_request,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        revision="repair-b",
        company_meta=durable_company,
    )
    stale_repair = arbitrate_filing_upload_publication(
        initial_request=repair_initial,
        fresh_request=repair_changed,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert stale_repair.failure_reason is not None
    assert stale_repair.failure_reason.code is FinsUploadFailureCode.SOURCE_REVISION_STALE


@pytest.mark.parametrize(
    (
        "initial_status",
        "fresh_status",
        "action",
        "overwrite",
        "manual_explicit_create_fresh",
    ),
    (
        (
            SourceIntegrityStatus.MISSING,
            SourceIntegrityStatus.REPAIR_REQUIRED,
            "auto",
            False,
            False,
        ),
        (
            SourceIntegrityStatus.COMPLETE,
            SourceIntegrityStatus.MISSING,
            "auto",
            False,
            False,
        ),
        (
            SourceIntegrityStatus.COMPLETE,
            SourceIntegrityStatus.REPAIR_REQUIRED,
            "auto",
            False,
            False,
        ),
        (
            SourceIntegrityStatus.MISSING,
            SourceIntegrityStatus.COMPLETE,
            "auto",
            True,
            False,
        ),
        (
            SourceIntegrityStatus.MISSING,
            SourceIntegrityStatus.COMPLETE,
            "create",
            False,
            True,
        ),
    ),
)
def test_arbitration_conflict_grid_is_closed_and_typed(
    tmp_path: Path,
    initial_status: SourceIntegrityStatus,
    fresh_status: SourceIntegrityStatus,
    action: str,
    overwrite: bool,
    manual_explicit_create_fresh: bool,
) -> None:
    """§7.4 changed-observation conflict 格必须统一 fail closed 且绝不 skip。

    Args:
        tmp_path: authoritative primary fixture 目录。
        initial_status: preparation observation 状态。
        fresh_status: batch staging fresh observation 状态。
        action: raw upload action。
        overwrite: raw overwrite 开关。
        manual_explicit_create_fresh: 是否直接构造 validator 不会产生的 fresh create 观察。

    Returns:
        无。

    Raises:
        AssertionError: conflict 格产生 publish/skip 或错误 failure code 时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    request = _build_request(primary, action=action, overwrite=overwrite)
    identity = _build_publication_identity()
    durable_company = _fresh_company_meta()
    initial = _build_validated_request(
        request,
        status=initial_status,
        revision=("initial" if initial_status is not SourceIntegrityStatus.MISSING else None),
        publication_identity=(
            identity if initial_status is SourceIntegrityStatus.COMPLETE else None
        ),
        company_meta=(
            durable_company if initial_status is not SourceIntegrityStatus.MISSING else None
        ),
    )
    if manual_explicit_create_fresh:
        donor_request = _build_request(primary, action="update")
        donor = _build_validated_request(
            donor_request,
            status=SourceIntegrityStatus.COMPLETE,
            revision="fresh",
            publication_identity=identity,
            company_meta=durable_company,
        )
        fresh = replace(
            initial,
            published_state=donor.published_state,
            company_meta_decision=donor.company_meta_decision,
        )
    else:
        fresh = _build_validated_request(
            request,
            status=fresh_status,
            revision=("fresh" if fresh_status is not SourceIntegrityStatus.MISSING else None),
            publication_identity=(
                identity if fresh_status is SourceIntegrityStatus.COMPLETE else None
            ),
            company_meta=(
                durable_company if fresh_status is not SourceIntegrityStatus.MISSING else None
            ),
        )

    decision = arbitrate_filing_upload_publication(
        initial_request=initial,
        fresh_request=fresh,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )

    assert decision.disposition is FilingUploadPublicationDisposition.CONFLICT
    assert decision.disposition is not FilingUploadPublicationDisposition.SKIP
    assert decision.publish_mode is None
    assert decision.failure_reason is not None
    assert decision.failure_reason.code is FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT


@pytest.mark.parametrize("unsafe_side", ("initial", "fresh"))
def test_arbitration_rejects_unsafe_observation_at_either_entry(
    tmp_path: Path,
    unsafe_side: str,
) -> None:
    """UNSAFE initial/fresh observation 即使由 adversarial caller 伪造也必须 raise。

    Args:
        tmp_path: authoritative primary fixture 目录。
        unsafe_side: 需要伪造为 UNSAFE 的输入侧。

    Returns:
        无。

    Raises:
        AssertionError: UNSAFE 被转换为普通 decision 时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    request = _build_request(primary)
    initial = _build_validated_request(request, status=SourceIntegrityStatus.MISSING)
    fresh = _build_validated_request(request, status=SourceIntegrityStatus.MISSING)
    unsafe_state = FilingUploadPublishedState(
        company_meta=None,
        source_integrity=SourceIntegrityClassification(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            document_id=initial.document_id,
            revision=None,
            status=SourceIntegrityStatus.UNSAFE,
            reasons=(SourceIntegrityReason.IDENTITY_UNTRUSTED,),
        ),
        source_meta=None,
        publication_identity=None,
    )
    # Validated request 自身拒绝 UNSAFE；这里刻意越过 frozen dataclass，测试纯 owner 的防线。
    object.__setattr__(
        initial if unsafe_side == "initial" else fresh,
        "published_state",
        unsafe_state,
    )

    with pytest.raises(ValueError, match="UNSAFE source observation"):
        arbitrate_filing_upload_publication(
            initial_request=initial,
            fresh_request=fresh,
            prepared_identity=_build_publication_identity(),
            initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
        )


def test_arbitration_rejects_stable_repair_action_invariant_drift(tmp_path: Path) -> None:
    """stable REPAIR_REQUIRED 必须分别检查 initial/fresh 的 update action。

    Args:
        tmp_path: authoritative primary fixture 目录。

    Returns:
        无。

    Raises:
        AssertionError: 两侧同样漂移的 action 绕过 stable owner invariant 时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    request = _build_request(primary)
    initial = _build_validated_request(
        request,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        revision="stable",
        company_meta=_fresh_company_meta(),
    )
    fresh = _build_validated_request(
        request,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        revision="stable",
        company_meta=_fresh_company_meta(),
    )
    # 伪造两侧相等但非法的 action，确保测试命中 REPAIR_REQUIRED 分支自身的 fresh 检查。
    object.__setattr__(initial, "resolved_action", "create")
    object.__setattr__(fresh, "resolved_action", "create")

    with pytest.raises(ValueError, match="stable REPAIR_REQUIRED observation"):
        arbitrate_filing_upload_publication(
            initial_request=initial,
            fresh_request=fresh,
            prepared_identity=_build_publication_identity(),
            initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
        )


def test_arbitration_rejects_target_and_closed_input_contract_drift(tmp_path: Path) -> None:
    """pure owner 必须拒绝不同 raw request、target identity 与 open disposition。

    Args:
        tmp_path: authoritative primary fixture 目录。

    Returns:
        无。

    Raises:
        AssertionError: invariant drift 被静默降级为 publish/skip/conflict 时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    request = _build_request(primary)
    initial = _build_validated_request(request, status=SourceIntegrityStatus.MISSING)
    fresh = _build_validated_request(request, status=SourceIntegrityStatus.MISSING)
    identity = _build_publication_identity()

    with pytest.raises(TypeError, match="FilingInitialSkipDisposition"):
        arbitrate_filing_upload_publication(
            initial_request=initial,
            fresh_request=fresh,
            prepared_identity=identity,
            initial_skip_disposition="not_eligible",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="prepared target identity"):
        arbitrate_filing_upload_publication(
            initial_request=initial,
            fresh_request=fresh,
            prepared_identity=replace(identity, internal_document_id="foreign-internal"),
            initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
        )
    different_request = _build_request(primary, overwrite=True)
    different_fresh = _build_validated_request(
        different_request,
        status=SourceIntegrityStatus.MISSING,
    )
    with pytest.raises(ValueError, match="同一不可变 raw request"):
        arbitrate_filing_upload_publication(
            initial_request=initial,
            fresh_request=different_fresh,
            prepared_identity=identity,
            initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
        )
