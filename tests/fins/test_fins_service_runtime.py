"""Fins service runtime owner boundary 测试。"""

from __future__ import annotations

import ast
import errno
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

import dayu.fins.service_runtime as service_runtime
from dayu.contracts.cancellation import CancellationToken
from dayu.fins.company_metadata_warning import (
    COMPANY_NAME_IGNORED_WARNING_MESSAGE,
    CompanyMetadataWarning,
    CompanyMetadataWarningKind,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    FinsJobCancellationChecker,
    FinsUploadFilingRequest,
    FinsUploadMaterialRequest,
    FinsUploadPipelineResult,
    FinsUploadResultSummary,
    FinsUploadUsageCode,
    FinsUploadUsageError,
    ValidatedFinsUploadFilingRequest,
)
from dayu.fins.pipelines.cn_pipeline import CnPipeline
from dayu.fins.pipelines.sec_pipeline import SecPipeline, SecPipelineUploadResult
from dayu.fins.service_runtime import (
    DefaultFinsRuntime,
    ProductionFinsUploadRunner,
    _upload_summary_from_result,
    prevalidate_fins_upload_filing_request_for_workspace,
)
from dayu.fins.upload_failure import (
    FinsUploadPrevalidationError,
    fins_upload_prevalidation_io_failure,
    fins_upload_source_integrity_unsafe_failure,
)
from dayu.fins.storage import (
    FilingUploadPublishedState,
    SourceIntegrityClassification,
    SourceIntegrityReason,
    SourceIntegrityStatus,
)


class _UnsafeFilingUploadStateRepository:
    """显式返回 exact UNSAFE classification 的 Service 边界 fixture。"""

    def __init__(self, workspace_root: Path, *, create_directories: bool) -> None:
        """接受 production constructor 参数但不读取或创建 workspace。

        Args:
            workspace_root: 本测试禁止读取的 workspace 根。
            create_directories: production prevalidation 固定传入的目录创建开关。

        Returns:
            无。

        Raises:
            AssertionError: Service 错误请求创建 workspace 目录时抛出。
        """

        if create_directories:
            raise AssertionError("prevalidation repository 不得创建 workspace")
        self.workspace_root = workspace_root

    def read_filing_upload_state(
        self,
        ticker: str,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """返回调用参数 exact target 的 typed UNSAFE state。

        Args:
            ticker: canonical filing ticker。
            document_id: exact filing document ID。

        Returns:
            显式 status/reasons 且不含 source meta 的 published state。

        Raises:
            无。
        """

        return FilingUploadPublishedState(
            company_meta=None,
            source_integrity=SourceIntegrityClassification(
                ticker=ticker,
                source_kind=SourceKind.FILING,
                document_id=document_id,
                revision=None,
                status=SourceIntegrityStatus.UNSAFE,
                reasons=(SourceIntegrityReason.META_UNTRUSTED,),
            ),
            source_meta=None,
            publication_identity=None,
        )


class _AlwaysCancelledChecker(FinsJobCancellationChecker):
    """始终报告已取消的 production runner 测试 checker。"""

    def __call__(self) -> bool:
        """返回 callable cancellation checkpoint 状态。

        Args:
            无。

        Returns:
            始终返回 ``True``。

        Raises:
            无。
        """

        return True

    def is_cancelled(self) -> bool:
        """返回 token cancellation 状态。

        Args:
            无。

        Returns:
            始终返回 ``True``。

        Raises:
            无。
        """

        return True

    def cancel_reason(self) -> str | None:
        """返回测试取消原因。

        Args:
            无。

        Returns:
            固定测试取消原因。

        Raises:
            无。
        """

        return "test-cancelled"

    def requested_at(self) -> datetime | None:
        """返回测试取消时间。

        Args:
            无。

        Returns:
            本测试不依赖取消时间，因此返回 ``None``。

        Raises:
            无。
        """

        return None


class _NeverCancelledChecker(FinsJobCancellationChecker):
    """始终保持开放的 production runner 测试 checker。"""

    def __call__(self) -> bool:
        """返回 callable cancellation checkpoint 状态。

        Args:
            无。

        Returns:
            始终返回 ``False``。

        Raises:
            无。
        """

        return False

    def is_cancelled(self) -> bool:
        """返回 token cancellation 状态。

        Args:
            无。

        Returns:
            始终返回 ``False``。

        Raises:
            无。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回测试取消原因。

        Args:
            无。

        Returns:
            未取消，返回 ``None``。

        Raises:
            无。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回测试取消时间。

        Args:
            无。

        Returns:
            未取消，返回 ``None``。

        Raises:
            无。
        """

        return None


class _WarningFilingPipelineFacade:
    """为 production runner 返回 canonical warning JSON 的最小 pipeline facade。"""

    def __init__(self, warning: CompanyMetadataWarning) -> None:
        """初始化 warning 与调用记录。

        Args:
            warning: pipeline terminal result 应投影的 typed warning。

        Returns:
            无。

        Raises:
            无。
        """

        self.warning = warning
        self.requests: list[ValidatedFinsUploadFilingRequest] = []
        self.cancellation_checkers: list[CancellationToken | None] = []

    def upload_filing(
        self,
        request: ValidatedFinsUploadFilingRequest,
        *,
        cancellation_checker: CancellationToken | None = None,
    ) -> SecPipelineUploadResult:
        """返回 skipped filing 的 canonical pipeline terminal JSON。

        Args:
            request: runner 传入的 validated filing request。
            cancellation_checker: runner 原样传入的取消观察器。

        Returns:
            含一个 canonical company metadata warning 的合法 skipped result。

        Raises:
            无。
        """

        self.requests.append(request)
        self.cancellation_checkers.append(cancellation_checker)
        return {
            "status": "skipped",
            "stored_file_count": 0,
            "warnings": [self.warning.to_json()],
        }


def test_production_runner_parser_callsites_use_explicit_source_kind() -> None:
    """四个 parser callsite 必须按所属 runner 方法绑定正确 SourceKind。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: callsite 数量、所属方法、关键字或 SourceKind 漂移时抛出。
        OSError: production 模块源码读取失败时抛出。
        SyntaxError: production 模块源码无法解析时抛出。
    """

    source_path = Path(service_runtime.__file__)
    syntax_tree = ast.parse(
        source_path.read_text(encoding="utf-8"),
        filename=str(source_path),
    )
    runner_classes = [
        node
        for node in syntax_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ProductionFinsUploadRunner"
    ]
    assert len(runner_classes) == 1
    runner_class = runner_classes[0]
    source_kinds_by_method: dict[str, list[str]] = {}
    for method in runner_class.body:
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls = [
            node
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "from_pipeline_json"
        ]
        if not calls:
            continue
        method_source_kinds: list[str] = []
        for call in calls:
            keyword = next(
                (item for item in call.keywords if item.arg == "source_kind"),
                None,
            )
            assert keyword is not None
            assert isinstance(keyword.value, ast.Attribute)
            assert isinstance(keyword.value.value, ast.Name)
            assert keyword.value.value.id == "SourceKind"
            method_source_kinds.append(keyword.value.attr)
        source_kinds_by_method[method.name] = method_source_kinds

    assert set(source_kinds_by_method) == {
        "_run_filing_upload",
        "_run_material_upload",
    }
    assert len(source_kinds_by_method["_run_filing_upload"]) == 2
    assert set(source_kinds_by_method["_run_filing_upload"]) == {"FILING"}
    assert len(source_kinds_by_method["_run_material_upload"]) == 2
    assert set(source_kinds_by_method["_run_material_upload"]) == {"MATERIAL"}
    assert sum(len(kinds) for kinds in source_kinds_by_method.values()) == 4


def test_delete_contract_rejects_before_workspace_repository_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """delete 携带 files/primary 必须在 Service repository bootstrap 前拒绝。

    Args:
        tmp_path: 用于声明不得创建的 workspace。
        monkeypatch: 用于禁止 workspace resolve 的 pytest 夹具。

    Returns:
        无。

    Raises:
        AssertionError: static admission 越界进入 repository bootstrap 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    raw_file = tmp_path / "never-read.pdf"
    real_resolve = Path.resolve

    def forbid_workspace_resolve(path: Path, strict: bool = False) -> Path:
        """禁止非法 delete 请求进入 workspace repository 路径解析。

        Args:
            path: 当前待解析路径。
            strict: 是否要求路径已存在。

        Returns:
            非 workspace 路径的真实解析结果。

        Raises:
            AssertionError: workspace repository 被提前构造时抛出。
            OSError: 非目标路径解析失败时由真实实现抛出。
            RuntimeError: 非目标路径存在 symlink loop 时由真实实现抛出。
        """

        if path == workspace_root:
            raise AssertionError("delete static rejection 前禁止构造 workspace repository")
        return real_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", forbid_workspace_resolve)
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="delete",
        files=(raw_file,),
        primary_selectors=(raw_file,),
        fiscal_year=2024,
        fiscal_period="FY",
    )

    with pytest.raises(FinsUploadUsageError) as exc_info:
        prevalidate_fins_upload_filing_request_for_workspace(
            request,
            workspace_root=workspace_root,
        )

    assert exc_info.value.failure.code is FinsUploadUsageCode.FILES_NOT_ALLOWED_FOR_DELETE
    assert exc_info.value.failure.message == "delete 不得提供 --files"
    assert not workspace_root.exists()


def test_prevalidation_maps_repository_resolve_failure_to_typed_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """repository 构造期 resolve failure 必须由 prevalidation owner typed 投影。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: workspace resolve failure 注入夹具。

    Returns:
        无。

    Raises:
        AssertionError: typed reason、cause chain 或零 mutation contract 漂移时抛出。
    """

    workspace_root = tmp_path / "workspace"
    input_file = tmp_path / "filing.pdf"
    input_file.write_text("filing", encoding="utf-8")
    real_resolve = Path.resolve

    def fail_workspace_resolve(path: Path, strict: bool = False) -> Path:
        """只在 production repository 解析目标 workspace 时注入 OSError。

        Args:
            path: 当前待解析路径。
            strict: 是否要求路径已经存在。

        Returns:
            非目标路径的真实解析结果。

        Raises:
            PermissionError: 目标 workspace 进入 resolve 时始终抛出。
        """

        if path == workspace_root:
            raise PermissionError(errno.EACCES, "resolve denied", str(workspace_root))
        return real_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_workspace_resolve)
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(input_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )

    with pytest.raises(FinsUploadPrevalidationError) as exc_info:
        prevalidate_fins_upload_filing_request_for_workspace(
            request,
            workspace_root=workspace_root,
        )

    assert exc_info.value.failure == fins_upload_prevalidation_io_failure()
    projected_error = exc_info.value.__cause__
    assert isinstance(projected_error, PermissionError)
    assert "解析 storage workspace失败" in str(projected_error)
    projected_root_cause = projected_error.__cause__
    assert isinstance(projected_root_cause, PermissionError)
    assert "解析 storage workspace底层文件系统失败" in str(projected_root_cause)
    assert not workspace_root.exists()


def test_service_prevalidation_propagates_typed_unsafe_without_workspace_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service prevalidation 必须原样传播 validator 的 path-free UNSAFE failure。

    Args:
        tmp_path: 用于创建输入文件与禁止创建的 workspace。
        monkeypatch: 用于注入只返回 typed state 的 repository fixture。

    Returns:
        无。

    Raises:
        AssertionError: Service 从 raw meta 重判、改写 failure 或创建 workspace 时抛出。
    """

    input_file = tmp_path / "filing.pdf"
    input_file.write_bytes(b"filing")
    workspace_root = tmp_path / "workspace"
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="auto",
        files=(input_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    monkeypatch.setattr(
        service_runtime,
        "FsFilingUploadStateRepository",
        _UnsafeFilingUploadStateRepository,
    )

    with pytest.raises(FinsUploadPrevalidationError) as exc_info:
        prevalidate_fins_upload_filing_request_for_workspace(
            request,
            workspace_root=workspace_root,
        )

    assert exc_info.value.failure == fins_upload_source_integrity_unsafe_failure()
    assert str(workspace_root) not in repr(exc_info.value.failure)
    assert not workspace_root.exists()


@pytest.mark.parametrize(
    ("status", "stored_file_count", "requested_file_count"),
    (
        ("ok", 2, 2),
        ("skipped", 0, 2),
        ("deleted", 0, 2),
        ("cancelled", 0, 2),
    ),
)
def test_upload_summary_joins_validated_request_and_pipeline_counts(
    status: str,
    stored_file_count: int,
    requested_file_count: int,
) -> None:
    """runtime 汇合点必须分别消费 request count 与 pipeline stored count。

    Args:
        status: pipeline 终态。
        stored_file_count: pipeline publication owner 交付的 original 数。
        requested_file_count: validated request 文件数。

    Returns:
        无。

    Raises:
        AssertionError: summary 重建 stored count 或保留 basename 时抛出。
    """

    request = FinsUploadMaterialRequest(
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        files=(Path("first.pdf"), Path("second.pdf")),
    )
    summary = _upload_summary_from_result(
        request=request,
        result=FinsUploadPipelineResult(
            status=status,
            stored_file_count=stored_file_count,
        ),
    )

    assert summary.requested_file_count == requested_file_count
    assert summary.stored_file_count == stored_file_count


def test_upload_summary_from_result_explicitly_copies_typed_warnings() -> None:
    """service 汇合点必须机械复制 pipeline typed warning tuple。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: service 丢失、重建或依赖 summary 默认值时抛出。
    """

    warnings = (
        CompanyMetadataWarning(
            kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
            message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
        ),
    )
    result = FinsUploadPipelineResult(
        status="skipped",
        stored_file_count=0,
        warnings=warnings,
    )

    summary = _upload_summary_from_result(
        request=FinsUploadFilingRequest(
            ticker="AAPL",
            files=(Path("filing.pdf"),),
            fiscal_year=2024,
            fiscal_period="FY",
            company_name="Apple Inc.",
        ),
        result=result,
    )

    assert summary.warnings is result.warnings
    assert summary.warnings == warnings


def test_production_upload_runner_preserves_pipeline_warning_in_summary_and_json(
    tmp_path: Path,
) -> None:
    """真实 production runner 必须保留 pipeline warning 到 summary 与 durable JSON。

    Args:
        tmp_path: validated filing request 与只读 workspace 使用的临时目录。

    Returns:
        无。

    Raises:
        AssertionError: runner handoff、typed warning 或 durable 投影发生丢失时抛出。
        OSError: 临时输入或只读 workspace 状态读取失败时抛出。
    """

    input_file = tmp_path / "filing.pdf"
    input_file.write_bytes(b"typed filing")
    request = prevalidate_fins_upload_filing_request_for_workspace(
        FinsUploadFilingRequest(
            ticker="AAPL",
            action="create",
            files=(input_file,),
            fiscal_year=2024,
            fiscal_period="FY",
            company_name="Apple Inc.",
        ),
        workspace_root=tmp_path / "workspace",
    )
    warning = CompanyMetadataWarning(
        kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
        message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
    )
    pipeline = _WarningFilingPipelineFacade(warning)
    cancellation_checker = _NeverCancelledChecker()
    runner = ProductionFinsUploadRunner(
        sec_pipeline=cast(SecPipeline, pipeline),
        cn_pipeline=cast(CnPipeline, pipeline),
    )

    summary = runner.run_upload(
        request,
        cancellation_checker=cancellation_checker,
    )

    assert isinstance(summary, FinsUploadResultSummary)
    assert pipeline.requests == [request]
    assert pipeline.cancellation_checkers == [cancellation_checker]
    assert summary.status == "skipped"
    assert summary.warnings == (warning,)
    assert summary.to_json_summary()["warnings"] == [warning.to_json()]


def test_production_upload_runner_early_cancel_uses_request_count(
    tmp_path: Path,
) -> None:
    """production runner 入口取消必须保留 requested，并保持 stored 为零。

    Args:
        tmp_path: pytest 临时目录夹具。

    Returns:
        无。

    Raises:
        AssertionError: production 装配或 early-cancel count 语义漂移时抛出。
        OSError: production runtime 仓储装配失败时抛出。
    """

    runtime = DefaultFinsRuntime.create(
        workspace_root=tmp_path / "workspace",
    ).get_ingestion_runtime()
    runner = runtime.upload_runner
    assert isinstance(runner, ProductionFinsUploadRunner)
    request = FinsUploadMaterialRequest(
        ticker="AAPL",
        files=(Path("first.pdf"), Path("second.pdf")),
    )

    summary = runner.run_upload(
        request,
        cancellation_checker=_AlwaysCancelledChecker(),
    )

    assert summary.status == "cancelled"
    assert summary.requested_file_count == len(request.files)
    assert summary.stored_file_count == 0
