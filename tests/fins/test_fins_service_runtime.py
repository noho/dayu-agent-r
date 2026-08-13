"""Fins service runtime owner boundary 测试。"""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from dayu.fins.ingestion_runtime import FinsUploadFilingRequest
from dayu.fins.service_runtime import prevalidate_fins_upload_filing_request_for_workspace
from dayu.fins.upload_failure import (
    FinsUploadPrevalidationError,
    fins_upload_prevalidation_io_failure,
)


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
