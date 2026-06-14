"""Fins direct job 的 Service 边界。

本模块为 CLI、未来 GUI 或内部任务入口提供共享的 Fins direct job 语义：
构造 typed Fins ingestion request、启动 job、轮询终态、请求 durable cancel，
并把终态映射为 product entrypoint 可消费的退出码。它不解析 CLI 参数，
不处理 stdout/stderr，也不读取 Fins storage。
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    FinsDownloadRequest,
    FinsIngestionJobRecord,
    FinsIngestionJobStart,
    FinsIngestionJobStatus,
    FinsPreprocessRequest,
    FinsUploadFilingRequest,
    FinsUploadMaterialRequest,
)
from dayu.fins.service_runtime import DefaultFinsRuntime

DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS: Final[float] = 1.0
MAX_FINS_DIRECT_POLL_INTERVAL_SECONDS: Final[float] = 60.0
FINS_DIRECT_EXIT_SUCCESS: Final[int] = 0
FINS_DIRECT_EXIT_FAILURE: Final[int] = 1
FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT: Final[int] = 130


class FinsDirectUsageError(ValueError):
    """Fins direct Service 参数错误。"""


class FinsDirectIngestionRuntime(Protocol):
    """Fins direct command 需要的 ingestion runtime 协议。"""

    def start_download(
        self,
        request: FinsDownloadRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsIngestionJobStart:
        """启动下载 job。

        :param request: 下载请求。
        :param cancellation_token: 可选启动边界取消 token。
        :returns: job 启动结果。
        :raises Exception: runtime 启动失败时由具体实现抛出。
        """

        ...

    def start_preprocess(
        self,
        request: FinsPreprocessRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsIngestionJobStart:
        """启动预处理 job。

        :param request: 预处理请求。
        :param cancellation_token: 可选启动边界取消 token。
        :returns: job 启动结果。
        :raises Exception: runtime 启动失败时由具体实现抛出。
        """

        ...

    def start_upload(
        self,
        request: FinsUploadFilingRequest | FinsUploadMaterialRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsIngestionJobStart:
        """启动上传 job。

        :param request: filing 或 material 上传请求。
        :param cancellation_token: 可选启动边界取消 token。
        :returns: job 启动结果。
        :raises Exception: runtime 启动失败时由具体实现抛出。
        """

        ...

    def read_job(self, job_id: str) -> FinsIngestionJobRecord:
        """读取 job record。

        :param job_id: Fins ingestion job id。
        :returns: 当前持久化 job record。
        :raises Exception: job 不存在或读取失败时由具体实现抛出。
        """

        ...

    def request_cancel(self, job_id: str) -> FinsIngestionJobRecord:
        """请求取消 job。

        :param job_id: Fins ingestion job id。
        :returns: 更新后的 job record。
        :raises Exception: job 不存在或取消请求落盘失败时由具体实现抛出。
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


@dataclass(frozen=True, slots=True)
class FinsDirectStartRequest:
    """Fins direct job 启动诊断信息。

    Attributes:
        command_name: 用户可见 direct command 名称。
        ticker: 当前请求使用的 canonical ticker 文本。
    """

    command_name: str
    ticker: str


@dataclass(frozen=True, slots=True)
class FinsDirectJobHandle:
    """Fins direct job 启动后的 Service handle。

    Attributes:
        job_id: Fins ingestion job id。
        initial_status: 启动后 job 初始状态。
        start_request: 启动该 job 的 direct command 诊断信息。
    """

    job_id: str
    initial_status: FinsIngestionJobStatus
    start_request: FinsDirectStartRequest


@dataclass(frozen=True, slots=True)
class FinsDirectTerminalResult:
    """Fins direct job 终态结果。

    Attributes:
        job_id: Fins ingestion job id。
        status: Fins ingestion job 终态。
        exit_code: direct command 应映射的 CLI 退出码。
        result_summary: job 业务结果摘要。
        failure_summary: job 失败摘要。
    """

    job_id: str
    status: FinsIngestionJobStatus
    exit_code: int
    result_summary: Mapping[str, JsonValue]
    failure_summary: Mapping[str, JsonValue]


class FinsDirectCommandService:
    """Fins direct command 的共享 Service helper。"""

    _runtime: FinsDirectIngestionRuntime
    poll_interval_seconds: float
    _sleep: Callable[[float], Awaitable[None]]

    def __init__(
        self,
        runtime: DefaultFinsRuntime | FinsDirectIngestionRuntime,
        *,
        poll_interval_seconds: float = DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """初始化 Fins direct command service。

        :param runtime: 默认 Fins runtime 或已取得的 ingestion runtime。
        :param poll_interval_seconds: 轮询非终态 job 的等待秒数。
        :param sleep: 可注入的异步 sleep 函数，供测试验证轮询。
        :returns: ``None``。
        :raises FinsDirectUsageError: poll interval 非法时抛出。
        """

        _validate_poll_interval_seconds(poll_interval_seconds)
        if isinstance(runtime, DefaultFinsRuntime):
            self._runtime = runtime.get_ingestion_runtime()
        else:
            self._runtime = runtime
        self.poll_interval_seconds = poll_interval_seconds
        self._sleep = sleep

    @classmethod
    def from_runtime_request(
        cls,
        request: FinsDirectRuntimeRequest,
        *,
        poll_interval_seconds: float = DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> "FinsDirectCommandService":
        """按 runtime request 创建 service。

        :param request: Fins direct runtime 装配请求。
        :param poll_interval_seconds: 轮询非终态 job 的等待秒数。
        :param sleep: 可注入的异步 sleep 函数。
        :returns: Fins direct command service。
        :raises OSError: 默认 runtime 创建失败时由底层仓储实现抛出。
        :raises FinsDirectUsageError: poll interval 非法时抛出。
        """

        runtime = request.runtime
        if runtime is None:
            runtime = DefaultFinsRuntime.create(workspace_root=request.workspace_root)
        return cls(
            runtime,
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
        )

    @classmethod
    def from_workspace_root(
        cls,
        workspace_root: Path,
        *,
        poll_interval_seconds: float = DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> "FinsDirectCommandService":
        """按 workspace root 创建默认 service。

        :param workspace_root: Fins 工作区根目录。
        :param poll_interval_seconds: 轮询非终态 job 的等待秒数。
        :param sleep: 可注入的异步 sleep 函数。
        :returns: Fins direct command service。
        :raises OSError: 默认 runtime 创建失败时由底层仓储实现抛出。
        :raises FinsDirectUsageError: poll interval 非法时抛出。
        """

        return cls.from_runtime_request(
            FinsDirectRuntimeRequest(workspace_root=workspace_root),
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
        )

    def start_download(
        self,
        *,
        ticker: str,
        form_types: tuple[str, ...] = (),
        filed_after: str | None = None,
        filed_before: str | None = None,
        overwrite_existing: bool = False,
        rebuild_processed: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsDirectJobHandle:
        """启动 Fins 下载 direct job。

        :param ticker: canonical ticker 文本。
        :param form_types: 表单过滤条件。
        :param filed_after: 可选最早 filing 日期。
        :param filed_before: 可选最晚 filing 日期。
        :param overwrite_existing: 是否覆盖已有 source document。
        :param rebuild_processed: 是否请求重建 processed 产物。
        :param cancellation_token: 可选启动边界取消 token。
        :returns: direct job handle。
        :raises Exception: request 构造或 runtime 启动失败时由底层抛出。
        """

        start = self._runtime.start_download(
            FinsDownloadRequest(
                ticker=ticker,
                form_types=form_types,
                filed_after=filed_after,
                filed_before=filed_before,
                overwrite_existing=overwrite_existing,
                rebuild_processed=rebuild_processed,
            ),
            cancellation_token=cancellation_token,
        )
        return _job_handle(
            start,
            command_name="download",
            ticker=ticker,
        )

    def start_preprocess(
        self,
        *,
        command_name: str,
        ticker: str,
        source_kind: SourceKind,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsDirectJobHandle:
        """启动 Fins 预处理 direct job。

        :param command_name: 用户可见命令名，用于 handle 诊断。
        :param ticker: canonical ticker 文本。
        :param source_kind: 预处理源文档类别。
        :param document_ids: 可选源文档 ID。
        :param form_types: 可选表单过滤。
        :param rebuild_processed: 是否允许重建 processed 产物。
        :param cancellation_token: 可选启动边界取消 token。
        :returns: direct job handle。
        :raises Exception: request 构造或 runtime 启动失败时由底层抛出。
        """

        start = self._runtime.start_preprocess(
            FinsPreprocessRequest(
                ticker=ticker,
                source_kind=source_kind,
                document_ids=document_ids,
                form_types=form_types,
                rebuild_processed=rebuild_processed,
            ),
            cancellation_token=cancellation_token,
        )
        return _job_handle(start, command_name=command_name, ticker=ticker)

    def start_upload_filing(
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
    ) -> FinsDirectJobHandle:
        """启动 filing 上传 direct job。

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
        :param cancellation_token: 可选启动边界取消 token。
        :returns: direct job handle。
        :raises Exception: request 构造或 runtime 启动失败时由底层抛出。
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
        start = self._runtime.start_upload(request, cancellation_token=cancellation_token)
        return _job_handle(start, command_name="upload_filing", ticker=ticker)

    def start_upload_material(
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
    ) -> FinsDirectJobHandle:
        """启动 material 上传 direct job。

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
        :param cancellation_token: 可选启动边界取消 token。
        :returns: direct job handle。
        :raises Exception: request 构造或 runtime 启动失败时由底层抛出。
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
        start = self._runtime.start_upload(request, cancellation_token=cancellation_token)
        return _job_handle(start, command_name="upload_material", ticker=ticker)

    async def wait_for_terminal(self, job_id: str) -> FinsDirectTerminalResult:
        """等待 job 进入终态。

        :param job_id: Fins ingestion job id。
        :returns: direct terminal result。
        :raises Exception: job 读取失败时由 runtime 抛出。
        """

        while True:
            record = self._runtime.read_job(job_id)
            if _is_terminal_status(record.status):
                return _terminal_result(record)
            await self._sleep(self.poll_interval_seconds)

    def request_cancel(self, job_id: str) -> FinsIngestionJobRecord:
        """请求取消 Fins ingestion job。

        :param job_id: Fins ingestion job id。
        :returns: 更新后的 job record。
        :raises Exception: job 不存在或取消落盘失败时由 runtime 抛出。
        """

        return self._runtime.request_cancel(job_id)


def _validate_poll_interval_seconds(value: float) -> None:
    """校验 poll interval。

    :param value: 轮询间隔秒数。
    :returns: ``None``。
    :raises FinsDirectUsageError: 值不是有限正数或超过上限时抛出。
    """

    if not math.isfinite(value) or value <= 0.0:
        raise FinsDirectUsageError("poll_interval_seconds must be finite and positive")
    if value > MAX_FINS_DIRECT_POLL_INTERVAL_SECONDS:
        raise FinsDirectUsageError("poll_interval_seconds must not exceed 60 seconds")


def _job_handle(
    start: FinsIngestionJobStart,
    *,
    command_name: str,
    ticker: str,
) -> FinsDirectJobHandle:
    """把 runtime start result 转成 direct job handle。

    :param start: runtime 返回的 job start。
    :param command_name: 用户可见命令名。
    :param ticker: direct request 使用的 ticker 文本。
    :returns: direct job handle。
    :raises Exception: 不主动抛出异常。
    """

    return FinsDirectJobHandle(
        job_id=start.job_id,
        initial_status=start.status,
        start_request=FinsDirectStartRequest(
            command_name=command_name,
            ticker=ticker,
        ),
    )


def _is_terminal_status(status: FinsIngestionJobStatus) -> bool:
    """判断 Fins job 状态是否为终态。

    :param status: Fins ingestion job 状态。
    :returns: 终态返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return status in {
        FinsIngestionJobStatus.SUCCEEDED,
        FinsIngestionJobStatus.FAILED,
        FinsIngestionJobStatus.CANCELLED,
    }


def _terminal_result(record: FinsIngestionJobRecord) -> FinsDirectTerminalResult:
    """把 job record 终态映射为 direct terminal result。

    :param record: 已进入终态的 job record。
    :returns: direct terminal result。
    :raises FinsDirectUsageError: 非终态 record 传入时抛出。
    """

    if record.status is FinsIngestionJobStatus.SUCCEEDED:
        exit_code = FINS_DIRECT_EXIT_SUCCESS
    elif record.status is FinsIngestionJobStatus.FAILED:
        exit_code = FINS_DIRECT_EXIT_FAILURE
    elif record.status is FinsIngestionJobStatus.CANCELLED:
        exit_code = FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT
    else:
        raise FinsDirectUsageError(f"job is not terminal: {record.status.value}")
    return FinsDirectTerminalResult(
        job_id=record.job_id,
        status=record.status,
        exit_code=exit_code,
        result_summary=record.result_summary,
        failure_summary=record.failure_summary,
    )


__all__: tuple[str, ...] = (
    "DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS",
    "FINS_DIRECT_EXIT_FAILURE",
    "FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT",
    "FINS_DIRECT_EXIT_SUCCESS",
    "FinsDirectCommandService",
    "FinsDirectIngestionRuntime",
    "FinsDirectJobHandle",
    "FinsDirectRuntimeRequest",
    "FinsDirectStartRequest",
    "FinsDirectTerminalResult",
    "FinsDirectUsageError",
)
