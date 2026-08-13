"""Fins service runtime owner boundary 测试。"""

from __future__ import annotations

import errno
from datetime import datetime
from pathlib import Path

import pytest

from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    FinsJobCancellationChecker,
    FinsUploadFilingRequest,
    FinsUploadMaterialRequest,
    FinsUploadPipelineResult,
)
from dayu.fins.service_runtime import (
    DefaultFinsRuntime,
    ProductionFinsUploadRunner,
    _upload_summary_from_result,
    prevalidate_fins_upload_filing_request_for_workspace,
)
from dayu.fins.upload_failure import (
    FinsUploadPrevalidationError,
    fins_upload_prevalidation_io_failure,
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
