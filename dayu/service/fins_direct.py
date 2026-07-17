"""Fins direct command 的 Service 流式边界。

本模块为 CLI、未来 GUI 或内部 product entrypoint 提供共享的 Fins direct
执行语义：构造 typed Fins ingestion request，并把 runtime 返回的同一个
``ValidatedFinsEventStream`` 暴露给调用方。它不解析 CLI 参数，不处理
stdout/stderr，不读取 Fins storage，也不暴露后台 job id、sidecar cursor 或
durable cancel API。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

import dayu.runtime.log as runtime_log
from dayu.contracts.cancellation import CancellationToken
from dayu.fins.direct_events import (
    FINS_RESULT_EXIT_CANCELLED,
    FINS_RESULT_EXIT_FAILURE,
    FINS_RESULT_EXIT_SUCCESS,
    FinsOperationKind,
)
from dayu.fins.direct_stream import ValidatedFinsEventStream
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    FinsDownloadRequest,
    FinsPreprocessRequest,
    FinsUploadFilingRequest,
    FinsUploadMaterialRequest,
    FinsUploadRequest,
)
from dayu.fins.service_runtime import DefaultFinsRuntime

FINS_DIRECT_EXIT_SUCCESS: Final[int] = FINS_RESULT_EXIT_SUCCESS
FINS_DIRECT_EXIT_FAILURE: Final[int] = FINS_RESULT_EXIT_FAILURE
FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT: Final[int] = FINS_RESULT_EXIT_CANCELLED

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


class FinsDirectUsageError(ValueError):
    """Fins direct Service 参数错误。"""


class FinsDirectIngestionRuntime(Protocol):
    """Fins direct command 需要的 ingestion runtime 协议。"""

    def download(
        self,
        request: FinsDownloadRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行下载 direct stream。

        :param request: 下载请求。
        :param cancellation_token: 可选 operation-scoped 取消 token。
        :returns: Fins owner 已验证的 direct 事件流。
        :raises Exception: runtime 执行失败时由具体实现抛出。
        """

        ...

    def preprocess(
        self,
        request: FinsPreprocessRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行预处理 direct stream。

        :param request: 预处理请求。
        :param cancellation_token: 可选 operation-scoped 取消 token。
        :returns: Fins owner 已验证的 direct 事件流。
        :raises Exception: runtime 执行失败时由具体实现抛出。
        """

        ...

    def upload(
        self,
        request: FinsUploadRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行上传 direct stream。

        :param request: filing 或 material 上传请求。
        :param cancellation_token: 可选 operation-scoped 取消 token。
        :returns: Fins owner 已验证的 direct 事件流。
        :raises Exception: runtime 执行失败时由具体实现抛出。
        """

        ...


@dataclass(frozen=True, slots=True)
class FinsDirectRuntimeRequest:
    """Fins direct Service runtime 装配请求。

    Attributes:
        workspace_root: Fins 工作区根目录。
        runtime: 测试或上层显式注入的 runtime；为空时从 workspace 创建默认 runtime。
    """

    workspace_root: Path
    runtime: DefaultFinsRuntime | FinsDirectIngestionRuntime | None = None


class FinsDirectCommandService:
    """Fins direct command 的共享 Service helper。"""

    _runtime: FinsDirectIngestionRuntime

    def __init__(
        self,
        runtime: DefaultFinsRuntime | FinsDirectIngestionRuntime,
    ) -> None:
        """初始化 Fins direct command service。

        :param runtime: 默认 Fins runtime 或已取得的 ingestion runtime。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if isinstance(runtime, DefaultFinsRuntime):
            self._runtime = runtime.get_ingestion_runtime()
        else:
            self._runtime = runtime

    @classmethod
    def from_runtime_request(
        cls,
        request: FinsDirectRuntimeRequest,
    ) -> "FinsDirectCommandService":
        """按 runtime request 创建 service。

        :param request: Fins direct runtime 装配请求。
        :returns: Fins direct command service。
        :raises OSError: 默认 runtime 创建失败时由底层仓储实现抛出。
        """

        runtime = request.runtime
        if runtime is None:
            runtime = DefaultFinsRuntime.create(workspace_root=request.workspace_root)
        return cls(runtime)

    @classmethod
    def from_workspace_root(cls, workspace_root: Path) -> "FinsDirectCommandService":
        """按 workspace root 创建默认 service。

        :param workspace_root: Fins 工作区根目录。
        :returns: Fins direct command service。
        :raises OSError: 默认 runtime 创建失败时由底层仓储实现抛出。
        """

        return cls.from_runtime_request(
            FinsDirectRuntimeRequest(workspace_root=workspace_root),
        )

    def download(
        self,
        *,
        ticker: str,
        form_types: tuple[str, ...] = (),
        filed_after: str | None = None,
        filed_before: str | None = None,
        overwrite_existing: bool = False,
        rebuild_processed: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行 Fins 下载 direct stream。

        :param ticker: canonical ticker 文本。
        :param form_types: 表单过滤条件。
        :param filed_after: 可选最早 filing 日期。
        :param filed_before: 可选最晚 filing 日期。
        :param overwrite_existing: 是否覆盖已有 source document。
        :param rebuild_processed: 是否请求重建 processed 产物。
        :param cancellation_token: 可选 operation-scoped 取消 token。
        :returns: runtime 返回的同一个 Fins owner 已验证事件流。
        :raises Exception: request 构造或 runtime 执行失败时由底层抛出。
        """

        runtime_log.log_verbose(
            _LOGGER,
            "Fins direct command stream opened; command=%s ticker=%s",
            FinsOperationKind.DOWNLOAD.value,
            ticker,
        )
        request = FinsDownloadRequest(
            ticker=ticker,
            form_types=form_types,
            filed_after=filed_after,
            filed_before=filed_before,
            overwrite_existing=overwrite_existing,
            rebuild_processed=rebuild_processed,
        )
        return self._runtime.download(
            request,
            cancellation_token=cancellation_token,
        )

    def process(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行通用 Fins 预处理 direct stream。

        :param ticker: canonical ticker 文本。
        :param source_kind: 预处理源文档类别。
        :param document_ids: 可选源文档 ID。
        :param form_types: 可选表单过滤。
        :param rebuild_processed: 是否允许重建 processed 产物。
        :param cancellation_token: 可选 operation-scoped 取消 token。
        :returns: runtime 返回的同一个 Fins owner 已验证事件流。
        :raises Exception: request 构造或 runtime 执行失败时由底层抛出。
        """

        return self._preprocess(
            operation_kind=FinsOperationKind.PREPROCESS,
            ticker=ticker,
            source_kind=source_kind,
            document_ids=document_ids,
            form_types=form_types,
            rebuild_processed=rebuild_processed,
            cancellation_token=cancellation_token,
        )

    def process_filing(
        self,
        *,
        ticker: str,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行 filing 预处理 direct stream。

        :param ticker: canonical ticker 文本。
        :param document_ids: 可选 filing 源文档 ID。
        :param form_types: 可选表单过滤。
        :param rebuild_processed: 是否允许重建 processed 产物。
        :param cancellation_token: 可选 operation-scoped 取消 token。
        :returns: runtime 返回的同一个 Fins owner 已验证事件流。
        :raises Exception: request 构造或 runtime 执行失败时由底层抛出。
        """

        return self._preprocess(
            operation_kind=FinsOperationKind.PROCESS_FILING,
            ticker=ticker,
            source_kind=SourceKind.FILING,
            document_ids=document_ids,
            form_types=form_types,
            rebuild_processed=rebuild_processed,
            cancellation_token=cancellation_token,
        )

    def process_material(
        self,
        *,
        ticker: str,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行 material 预处理 direct stream。

        :param ticker: canonical ticker 文本。
        :param document_ids: 可选 material 源文档 ID。
        :param form_types: 可选表单过滤。
        :param rebuild_processed: 是否允许重建 processed 产物。
        :param cancellation_token: 可选 operation-scoped 取消 token。
        :returns: runtime 返回的同一个 Fins owner 已验证事件流。
        :raises Exception: request 构造或 runtime 执行失败时由底层抛出。
        """

        return self._preprocess(
            operation_kind=FinsOperationKind.PROCESS_MATERIAL,
            ticker=ticker,
            source_kind=SourceKind.MATERIAL,
            document_ids=document_ids,
            form_types=form_types,
            rebuild_processed=rebuild_processed,
            cancellation_token=cancellation_token,
        )

    def upload_filing(
        self,
        *,
        ticker: str,
        action: str,
        files: tuple[Path, ...],
        fiscal_year: int | None = None,
        fiscal_period: str | None = None,
        amended: bool = False,
        filing_date: str | None = None,
        report_date: str | None = None,
        company_name: str | None = None,
        ticker_aliases: tuple[str, ...] = (),
        overwrite: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行 filing 上传 direct stream。

        :param ticker: canonical ticker 文本。
        :param action: 上传动作。
        :param files: 用户提供且已通过入口前置校验的文件路径。
        :param fiscal_year: 可选会计年度。
        :param fiscal_period: 可选会计期间。
        :param amended: 是否为修订 filing。
        :param filing_date: 可选披露日期。
        :param report_date: 可选报告期日期。
        :param company_name: 可选公司名称。
        :param ticker_aliases: ticker 别名，仅传给支持该字段的 upload request。
        :param overwrite: 是否允许覆盖已有文档。
        :param cancellation_token: 可选 operation-scoped 取消 token。
        :returns: runtime 返回的同一个 Fins owner 已验证事件流。
        :raises Exception: request 构造或 runtime 执行失败时由底层抛出。
        """

        request = FinsUploadFilingRequest(
            ticker=ticker,
            source_kind=SourceKind.FILING,
            action=action,
            files=files,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            amended=amended,
            filing_date=filing_date,
            report_date=report_date,
            company_name=company_name,
            ticker_aliases=ticker_aliases,
            overwrite=overwrite,
        )
        return self._runtime.upload(
            request,
            cancellation_token=cancellation_token,
        )

    def upload_material(
        self,
        *,
        ticker: str,
        action: str,
        files: tuple[Path, ...],
        form_type: str | None = None,
        material_name: str | None = None,
        document_id: str | None = None,
        internal_document_id: str | None = None,
        fiscal_year: int | None = None,
        fiscal_period: str | None = None,
        amended: bool = False,
        filing_date: str | None = None,
        report_date: str | None = None,
        company_name: str | None = None,
        ticker_aliases: tuple[str, ...] = (),
        overwrite: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行 material 上传 direct stream。

        :param ticker: canonical ticker 文本。
        :param action: 上传动作。
        :param files: 用户提供且已通过入口前置校验的文件路径。
        :param form_type: 可选关联表单类型。
        :param material_name: 可选材料名称。
        :param document_id: 可选业务文档 ID。
        :param internal_document_id: 可选内部文档 ID。
        :param fiscal_year: 可选会计年度。
        :param fiscal_period: 可选会计期间。
        :param amended: 是否为修订材料。
        :param filing_date: 可选披露日期。
        :param report_date: 可选报告期日期。
        :param company_name: 可选公司名称。
        :param ticker_aliases: ticker 别名，仅传给支持该字段的 upload request。
        :param overwrite: 是否允许覆盖已有文档。
        :param cancellation_token: 可选 operation-scoped 取消 token。
        :returns: runtime 返回的同一个 Fins owner 已验证事件流。
        :raises Exception: request 构造或 runtime 执行失败时由底层抛出。
        """

        request = FinsUploadMaterialRequest(
            ticker=ticker,
            source_kind=SourceKind.MATERIAL,
            action=action,
            files=files,
            form_type=form_type,
            material_name=material_name,
            document_id=document_id,
            internal_document_id=internal_document_id,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            amended=amended,
            filing_date=filing_date,
            report_date=report_date,
            company_name=company_name,
            ticker_aliases=ticker_aliases,
            overwrite=overwrite,
        )
        return self._runtime.upload(
            request,
            cancellation_token=cancellation_token,
        )

    def _preprocess(
        self,
        *,
        operation_kind: FinsOperationKind,
        ticker: str,
        source_kind: SourceKind,
        document_ids: tuple[str, ...],
        form_types: tuple[str, ...],
        rebuild_processed: bool,
        cancellation_token: CancellationToken | None,
    ) -> ValidatedFinsEventStream:
        """构造预处理请求并返回 direct stream。

        :param operation_kind: Service direct command 对应的业务操作类型。
        :param ticker: canonical ticker 文本。
        :param source_kind: 预处理源文档类别。
        :param document_ids: 可选源文档 ID。
        :param form_types: 可选表单过滤。
        :param rebuild_processed: 是否允许重建 processed 产物。
        :param cancellation_token: 可选 operation-scoped 取消 token。
        :returns: runtime 返回的同一个 Fins owner 已验证事件流。
        :raises Exception: request 构造或 runtime 执行失败时由底层抛出。
        """

        runtime_log.log_verbose(
            _LOGGER,
            "Fins direct command stream opened; command=%s ticker=%s",
            operation_kind.value,
            ticker,
        )
        request = FinsPreprocessRequest(
            ticker=ticker,
            source_kind=source_kind,
            document_ids=document_ids,
            form_types=form_types,
            rebuild_processed=rebuild_processed,
        )
        return self._runtime.preprocess(
            request,
            cancellation_token=cancellation_token,
        )


__all__: tuple[str, ...] = (
    "FINS_DIRECT_EXIT_FAILURE",
    "FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT",
    "FINS_DIRECT_EXIT_SUCCESS",
    "FinsDirectCommandService",
    "FinsDirectIngestionRuntime",
    "FinsDirectRuntimeRequest",
    "FinsDirectUsageError",
)
