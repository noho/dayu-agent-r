"""``dayu-cli`` Fins direct commands 测试。"""

from __future__ import annotations

import ast
import asyncio
import errno
import hashlib
import io
import logging
import subprocess
import sys
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import partial
from pathlib import Path
from typing import NoReturn, TextIO, cast

import pytest

import dayu.cli.commands.fins as fins_command
import dayu.cli.main as cli_main
import dayu.cli.output as cli_output
import dayu.fins.download_contract as download_contract
import dayu.fins.ingestion_runtime as ingestion_runtime
from dayu.cli.agent_entrypoint import CliSigintMonitor
from dayu.cli.arg_parsing import parse_cli_args
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.fins.direct_events import (
    FinsDirectStreamProtocolError,
    FinsDirectStreamProtocolErrorKind,
    FinsErrorKind,
    FinsEvent,
    FinsEventDetail,
    FinsEventType,
    FinsOperationKind,
    FinsProgress,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.fins.direct_events import ValidatedFinsEventStream
from dayu.fins.download_contract import (
    FinsDownloadEffectiveFilters,
    FinsDownloadRequest,
    build_fins_download_request,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.document_models import SourceDocumentUpsertRequest, SourceHandle
from dayu.fins.ingestion_runtime import (
    FinsJobCancellationChecker,
    FinsIngestionOperationKind,
    FinsUploadFilingRequest,
    FinsUploadResultSummary,
    validate_fins_upload_filing_request,
)
from dayu.fins.pipelines.docling_upload_service import build_sec_filing_ids
from dayu.fins.storage import (
    FilingUploadPublishedState,
    FsBatchingRepository,
    FsDocumentBlobRepository,
    FsFilingUploadStateRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.upload_failure import fins_upload_failure_from_exception
from dayu.service.fins_direct import (
    FINS_DIRECT_EXIT_FAILURE,
    FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT,
    FINS_DIRECT_EXIT_SUCCESS,
)

_NOW: datetime = datetime(2026, 6, 16, tzinfo=timezone.utc)
_UNPARSABLE_PDF_BYTES = b"not a PDF"
_UNPARSABLE_DOCX_BYTES = b"not a DOCX"
_TYPED_CONTENT_FAILURE_REASON = "文件无法解析或已损坏，请检查文件后重试"
_MAX_PUBLIC_CONTENT_FAILURE_STDERR_CHARS = 1024
_UNKNOWN_DIRECT_FAILURE_MARKER = "private /absolute/path traceback marker"
_UNKNOWN_DIRECT_FAILURE_STDERR = "dayu-cli download: 命令执行失败，请使用 --log-file PATH 重试并查看日志\n"


class _NeverCancelledJobChecker(FinsJobCancellationChecker):
    """CLI terminal projection 测试用未取消 checker。"""

    def __call__(self) -> bool:
        """返回未取消状态。

        Args:
            无。

        Returns:
            恒为 ``False``。

        Raises:
            无。
        """

        return False

    def is_cancelled(self) -> bool:
        """返回未取消状态。

        Args:
            无。

        Returns:
            恒为 ``False``。

        Raises:
            无。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Args:
            无。

        Returns:
            未取消，恒为 ``None``。

        Raises:
            无。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Args:
            无。

        Returns:
            未取消，恒为 ``None``。

        Raises:
            无。
        """

        return None


_NEVER_CANCELLED_JOB_CHECKER = _NeverCancelledJobChecker()


def _raise_cli_consumer_error(
    _event: FinsEvent,
    *,
    error: RuntimeError,
) -> NoReturn:
    """在 CLI log/render consumer 边界抛出指定主异常。

    :param _event: 已由 validator 产出的当前事件。
    :param error: 应保持身份向上传播的主异常。
    :returns: 不返回。
    :raises RuntimeError: 始终抛出传入的同一异常对象。
    """

    raise error


async def _raise_unknown_fins_direct_error(_args: fins_command.ParsedCliArgs) -> int:
    """注入携带内部路径 marker 的未知 direct 异常。

    Args:
        _args: 已解析命令参数。

    Returns:
        不返回。

    Raises:
        RuntimeError: 始终抛出包含内部 marker 的异常。
    """

    raise RuntimeError(_UNKNOWN_DIRECT_FAILURE_MARKER)


class _FakeFinsDirectService:
    """CLI 测试用 FinsDirectCommandService 替身。"""

    download_requests: list[FinsDownloadRequest]
    process_requests: list[_ProcessCall]
    process_filing_requests: list[_ProcessSpecificCall]
    process_material_requests: list[_ProcessSpecificCall]
    upload_filing_requests: list[_UploadFilingCall]
    upload_material_requests: list[_UploadMaterialCall]
    events: tuple[FinsEvent, ...]
    stream_error: Exception | None
    close_error: BaseException | None
    stream_calls: list[FinsOperationKind]
    cancellation_tokens: list[fins_command._CliFinsCancellationToken | None]
    first_event_yielded: asyncio.Event
    release_stream: asyncio.Event
    pause_after_first_event: bool
    closed_streams: int
    opened_streams: list[ValidatedFinsEventStream]

    def __init__(
        self,
        *,
        events: tuple[FinsEvent, ...] | None = None,
        stream_error: Exception | None = None,
        close_error: BaseException | None = None,
        pause_after_first_event: bool = False,
    ) -> None:
        """初始化 fake service。

        :param events: stream 需要产出的事件；为空时使用 progress + success。
        :param stream_error: 可选 stream 末尾异常。
        :param close_error: raw generator 关闭失败；取消时作为 cause，其余关闭时原样抛出。
        :param pause_after_first_event: 是否在首个事件后暂停，供取消测试使用。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.download_requests = []
        self.process_requests = []
        self.process_filing_requests = []
        self.process_material_requests = []
        self.upload_filing_requests = []
        self.upload_material_requests = []
        self.events = (_progress_event(FinsOperationKind.DOWNLOAD), _result_event()) if events is None else events
        self.stream_error = stream_error
        self.close_error = close_error
        self.stream_calls = []
        self.cancellation_tokens = []
        self.first_event_yielded = asyncio.Event()
        self.release_stream = asyncio.Event()
        self.pause_after_first_event = pause_after_first_event
        self.closed_streams = 0
        self.opened_streams = []

    def download(
        self,
        request: FinsDownloadRequest,
        *,
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录 download 参数并返回 fake stream。

        :param request: 已完成静态校验的下载请求。
        :param cancellation_token: CLI operation 取消 token。
        :returns: Fins direct event stream。
        :raises Exception: 不主动抛出异常。
        """

        self.download_requests.append(request)
        return self._stream(
            FinsOperationKind.DOWNLOAD,
            cancellation_token,
            validator_operation_kind=FinsOperationKind.DOWNLOAD,
        )

    def process(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录 process 参数并返回 fake stream。

        :param ticker: canonical ticker。
        :param source_kind: 源文档类型。
        :param document_ids: 源文档 ID。
        :param form_types: 表单过滤。
        :param rebuild_processed: 是否重建 processed 产物。
        :param cancellation_token: CLI operation 取消 token。
        :returns: Fins direct event stream。
        :raises Exception: 不主动抛出异常。
        """

        self.process_requests.append(
            _ProcessCall(
                ticker=ticker,
                source_kind=source_kind,
                document_ids=document_ids,
                form_types=form_types,
                rebuild_processed=rebuild_processed,
            )
        )
        return self._stream(
            FinsOperationKind.PREPROCESS,
            cancellation_token,
            validator_operation_kind=FinsOperationKind.PREPROCESS,
        )

    def process_filing(
        self,
        *,
        ticker: str,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录 process_filing 参数并返回 fake stream。

        :param ticker: canonical ticker。
        :param document_ids: filing 源文档 ID。
        :param form_types: 表单过滤。
        :param rebuild_processed: 是否重建 processed 产物。
        :param cancellation_token: CLI operation 取消 token。
        :returns: Fins direct event stream。
        :raises Exception: 不主动抛出异常。
        """

        self.process_filing_requests.append(
            _ProcessSpecificCall(
                ticker=ticker,
                document_ids=document_ids,
                form_types=form_types,
                rebuild_processed=rebuild_processed,
            )
        )
        return self._stream(
            FinsOperationKind.PROCESS_FILING,
            cancellation_token,
            validator_operation_kind=FinsOperationKind.PREPROCESS,
        )

    def process_material(
        self,
        *,
        ticker: str,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录 process_material 参数并返回 fake stream。

        :param ticker: canonical ticker。
        :param document_ids: material 源文档 ID。
        :param form_types: 表单过滤。
        :param rebuild_processed: 是否重建 processed 产物。
        :param cancellation_token: CLI operation 取消 token。
        :returns: Fins direct event stream。
        :raises Exception: 不主动抛出异常。
        """

        self.process_material_requests.append(
            _ProcessSpecificCall(
                ticker=ticker,
                document_ids=document_ids,
                form_types=form_types,
                rebuild_processed=rebuild_processed,
            )
        )
        return self._stream(
            FinsOperationKind.PROCESS_MATERIAL,
            cancellation_token,
            validator_operation_kind=FinsOperationKind.PREPROCESS,
        )

    def upload_filing(
        self,
        request: fins_command.ValidatedFinsUploadFilingRequest,
        *,
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录 upload_filing 参数并返回 fake stream。

        :param request: Fins owner 已验证的 filing request。
        :param cancellation_token: CLI operation 取消 token。
        :returns: Fins direct event stream。
        :raises Exception: 不主动抛出异常。
        """

        raw_request = request.request
        self.upload_filing_requests.append(
            _UploadFilingCall(
                ticker=request.normalized_ticker.canonical,
                action=raw_request.action,
                files=raw_request.files,
                fiscal_year=raw_request.fiscal_year,
                fiscal_period=request.normalized_fiscal_period,
                amended=raw_request.amended,
                filing_date=raw_request.filing_date,
                report_date=raw_request.report_date,
                company_name=raw_request.company_name,
                ticker_aliases=raw_request.ticker_aliases,
                overwrite=raw_request.overwrite,
            )
        )
        return self._stream(
            FinsOperationKind.UPLOAD_FILING,
            cancellation_token,
            validator_operation_kind=FinsOperationKind.UPLOAD_FILING,
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
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录 upload_material 参数并返回 fake stream。

        :param ticker: canonical ticker。
        :param action: 上传动作。
        :param files: 上传文件路径。
        :param form_type: 可选表单类型。
        :param material_name: 可选材料名称。
        :param document_id: 可选业务文档 ID。
        :param internal_document_id: 可选内部文档 ID。
        :param fiscal_year: 可选会计年度。
        :param fiscal_period: 可选会计期间。
        :param amended: 是否为修订材料。
        :param filing_date: 可选披露日期。
        :param report_date: 可选报告期日期。
        :param company_name: 可选公司名称。
        :param ticker_aliases: ticker aliases。
        :param overwrite: 是否覆盖已有文档。
        :param cancellation_token: CLI operation 取消 token。
        :returns: Fins direct event stream。
        :raises Exception: 不主动抛出异常。
        """

        self.upload_material_requests.append(
            _UploadMaterialCall(
                ticker=ticker,
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
        )
        return self._stream(
            FinsOperationKind.UPLOAD_MATERIAL,
            cancellation_token,
            validator_operation_kind=FinsOperationKind.UPLOAD_MATERIAL,
        )

    def _stream(
        self,
        command_operation_kind: FinsOperationKind,
        cancellation_token: fins_command._CliFinsCancellationToken | None,
        *,
        validator_operation_kind: FinsOperationKind,
    ) -> ValidatedFinsEventStream:
        """返回使用 production owner 的 fake validated stream。

        :param command_operation_kind: CLI 入口操作类型，仅用于 fake 调用记录。
        :param cancellation_token: CLI operation 取消 token。
        :param validator_operation_kind: Fins runtime 拥有的 error 来源。
        :returns: production validator stream。
        :raises Exception: 不主动抛出异常。
        """

        self.stream_calls.append(command_operation_kind)
        self.cancellation_tokens.append(cancellation_token)
        stream = ValidatedFinsEventStream(
            self._raw_stream(),
            operation_kind=validator_operation_kind,
        )
        self.opened_streams.append(stream)
        return stream

    async def _raw_stream(self) -> AsyncGenerator[FinsEvent, None]:
        """产出 fake raw events 并保留关闭观测。

        :returns: 未校验的 Fins raw event async generator。
        :raises BaseException: stream_error 原样抛出；关闭失败保留为取消 cause 或原样抛出。
        """

        cancellation_observed = False
        try:
            for index, event in enumerate(self.events):
                yield event
                if index == 0:
                    self.first_event_yielded.set()
                    if self.pause_after_first_event:
                        await self.release_stream.wait()
            if self.stream_error is not None:
                raise self.stream_error
        except asyncio.CancelledError as cancellation_error:
            cancellation_observed = True
            if self.close_error is not None:
                raise cancellation_error from self.close_error
            raise
        finally:
            self.closed_streams += 1
            if not cancellation_observed and self.close_error is not None:
                raise self.close_error


class _ObservedCliCancellationToken(fins_command._CliFinsCancellationToken):
    """使用 async barrier 观察 CLI 取消请求的测试 token。"""

    def __init__(self) -> None:
        """初始化请求计数与 barrier。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.request_count = 0
        self.requested = asyncio.Event()

    def request_cancel(self, reason: str) -> None:
        """记录请求并调用 production token 的幂等真源。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.request_count += 1
        super().request_cancel(reason)
        self.requested.set()


class _ObservedCliSigintMonitor(CliSigintMonitor):
    """暴露每次 ``wait_next`` 已被 owner 消费的测试 monitor。"""

    def __init__(self) -> None:
        """初始化已消费计数队列。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.observed_counts: asyncio.Queue[int] = asyncio.Queue()

    async def wait_next(self, observed_count: int) -> int:
        """等待下一次 SIGINT 并记录 owner 已消费计数。

        :param observed_count: 调用方已观察计数。
        :returns: 新的 SIGINT 计数。
        :raises asyncio.CancelledError: 等待 task 被取消时透传。
        """

        next_count = await super().wait_next(observed_count)
        await self.observed_counts.put(next_count)
        return next_count


@pytest.fixture()
def fake_service(monkeypatch: pytest.MonkeyPatch) -> _FakeFinsDirectService:
    """安装 fake Fins direct service factory。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: fake service。
    :raises Exception: 不主动抛出异常。
    """

    service = _FakeFinsDirectService()

    def factory(_workspace_root: Path) -> fins_command.FinsDirectCommandService:
        """返回 fake service。

        :param _workspace_root: CLI 解析出的 workspace root。
        :returns: cast 后的 fake service。
        :raises Exception: 不主动抛出异常。
        """

        return cast(fins_command.FinsDirectCommandService, service)

    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", factory)
    return service


def _recording_direct_service_factory(
    workspace_root: Path,
    *,
    service: _FakeFinsDirectService,
    factory_calls: list[Path],
) -> fins_command.FinsDirectCommandService:
    """记录不应发生的 factory 调用并返回指定测试 Service。

    Args:
        workspace_root: CLI 传入的 workspace root。
        service: 发生调用时应返回的测试 Service。
        factory_calls: 记录调用路径的列表。

    Returns:
        转换为 production 接口类型的测试 Service。

    Raises:
        无。
    """

    factory_calls.append(workspace_root)
    return cast(fins_command.FinsDirectCommandService, service)


def _snapshot_cli_workspace_tree(workspace_root: Path) -> tuple[tuple[str, str], ...]:
    """读取 CLI workspace 的相对业务树与文件内容摘要。

    Args:
        workspace_root: 待观测 workspace 根目录。

    Returns:
        按相对路径排序的目录标记或文件 SHA-256 元组。

    Raises:
        OSError: 遍历或读取 workspace 失败时抛出。
    """

    if not workspace_root.exists():
        return ()
    entries: list[tuple[str, str]] = []
    for path in sorted(workspace_root.rglob("*")):
        relative_path = path.relative_to(workspace_root).as_posix()
        if path.is_dir():
            entries.append((relative_path, "directory"))
        elif path.is_file():
            entries.append((relative_path, hashlib.sha256(path.read_bytes()).hexdigest()))
    return tuple(entries)


def _seed_cli_filing_source(workspace_root: Path) -> None:
    """通过真实 storage owner 发布 CLI create-existing 测试目标。

    Args:
        workspace_root: 待发布 filing 的 workspace 根目录。

    Returns:
        无。

    Raises:
        OSError: batch、blob 或 source publication 失败时抛出。
        ValueError: storage owner 拒绝测试 filing 元数据时抛出。
    """

    document_id, internal_document_id = build_sec_filing_ids(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    batch = batching_repository.begin_batch("AAPL")
    handle = SourceHandle(
        ticker="AAPL",
        document_id=document_id,
        source_kind=SourceKind.FILING.value,
    )
    file_meta = blob_repository.store_file(
        handle,
        "published.txt",
        io.BytesIO(b"published"),
        batch=batch,
        content_type="text/plain",
    )
    source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type="10-K",
            primary_document="published.txt",
            meta={"ingest_method": "upload", "source_provider": "user_upload"},
            files=[file_meta],
        ),
        SourceKind.FILING,
        batch=batch,
    )
    batching_repository.commit_batch(batch)


@pytest.mark.parametrize(
    "command_name",
    (
        "download",
        "process",
        "upload_filing",
        "upload_material",
        "process_filing",
        "process_material",
    ),
)
def test_live_fins_commands_render_progress_and_terminal_summary(
    command_name: str,
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """六个 Fins direct commands 都必须消费 direct event stream 并输出摘要。"""

    exit_code = cli_main.main(_live_command_argv(command_name, tmp_path))

    captured = capsys.readouterr()
    assert exit_code == EXIT_SUCCESS
    assert fake_service.stream_calls
    assert "Fins progress" in captured.out
    assert 'message="download live progress"' in captured.out
    assert "Fins succeeded" in captured.out
    assert 'processed_count="1"' in captured.out
    assert "Fins direct event received" not in captured.out
    assert "Fins direct event detail" not in captured.out
    assert captured.err == ""
    assert fake_service.closed_streams == 1


def test_fins_direct_default_log_does_not_pollute_progress_output(
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """默认 INFO 日志不得把 progress 诊断写进用户 UI 输出。"""

    exit_code = cli_main.main(("download", "--ticker", "AAPL"))

    captured = capsys.readouterr()
    assert exit_code == EXIT_SUCCESS
    assert "Fins progress" in captured.out
    assert "Fins direct command start" not in captured.out
    assert "Fins direct event received" not in captured.out
    assert captured.err == ""


def test_fins_direct_verbose_log_outputs_execution_skeleton(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--verbose`` 应把执行骨架诊断写到默认日志文件，progress 仍走 stdout。"""

    log_file = _redirect_default_log_file(monkeypatch=monkeypatch, tmp_path=tmp_path)
    exit_code = cli_main.main(("download", "--ticker", "AAPL", "--verbose"))

    captured = capsys.readouterr()
    log_text = log_file.read_text(encoding="utf-8")
    assert exit_code == EXIT_SUCCESS
    assert "Fins progress" in captured.out
    assert "Fins direct command start" not in captured.out
    assert "Fins direct event received" not in captured.out
    assert "[VERBOSE]" not in captured.out
    assert "Fins direct command start" not in captured.err
    assert "Fins direct event received" not in captured.err
    assert "Fins direct command start" in log_text
    assert "Fins direct event received" in log_text
    assert "message='download live progress'" in log_text
    assert "document='AAPL 10-K FY2024'" in log_text
    assert "stage=download" in log_text
    assert "Fins direct event detail" not in log_text


def test_fins_direct_verbose_log_file_keeps_user_ui_on_stdout(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--log-file`` 只接收 Fins direct 诊断，不接收用户 UI 输出。

    :param tmp_path: pytest 临时目录夹具。
    :param fake_service: fake Fins direct service。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 诊断日志与用户 UI 通道混淆时抛出。
    """

    log_file = tmp_path / "dayu.log"

    exit_code = cli_main.main(
        (
            "download",
            "--ticker",
            "AAPL",
            "--verbose",
            "--log-file",
            str(log_file),
        )
    )

    captured = capsys.readouterr()
    log_text = log_file.read_text(encoding="utf-8")
    assert exit_code == EXIT_SUCCESS
    assert "Fins progress" in captured.out
    assert "Fins succeeded" in captured.out
    assert "Fins direct command start" not in captured.out
    assert "Fins direct command start" not in captured.err
    assert "Fins direct event received" not in captured.err
    assert "Fins direct command start" in log_text
    assert "Fins direct event received" in log_text
    assert "message='download live progress'" in log_text
    assert "Fins progress" not in log_text
    assert "Fins succeeded" not in log_text


def test_fins_direct_default_log_file_keeps_verbose_diagnostics_suppressed(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """默认 INFO level 下 ``--log-file`` 不提升 Fins direct 诊断级别。

    :param tmp_path: pytest 临时目录夹具。
    :param fake_service: fake Fins direct service。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: ``--log-file`` 改变日志级别时抛出。
    """

    log_file = tmp_path / "dayu.log"

    exit_code = cli_main.main(("download", "--ticker", "AAPL", "--log-file", str(log_file)))

    captured = capsys.readouterr()
    log_text = log_file.read_text(encoding="utf-8")
    assert exit_code == EXIT_SUCCESS
    assert "Fins progress" in captured.out
    assert "Fins direct command start" not in captured.err
    assert "Fins direct command start" not in log_text
    assert "Fins direct event received" not in log_text


def test_fins_direct_debug_log_omits_empty_event_detail(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--debug`` 不记录只有 operation/event_type 的空泛 event detail。"""

    fake_service.events = (_empty_progress_event(), _result_event())
    log_file = _redirect_default_log_file(monkeypatch=monkeypatch, tmp_path=tmp_path)

    exit_code = cli_main.main(("download", "--ticker", "AAPL", "--debug"))

    captured = capsys.readouterr()
    log_text = log_file.read_text(encoding="utf-8")
    assert exit_code == EXIT_SUCCESS
    assert "Fins direct event received" not in captured.err
    assert "Fins direct event received" in log_text
    assert "Fins direct event detail; operation=download event_type=progress" not in log_text
    assert "Fins direct event detail; operation=download event_type=result" in log_text


def test_fins_direct_debug_log_outputs_event_details(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--debug`` 应把有界 event 详情写到默认日志文件，不输出内部治理标识。"""

    log_file = _redirect_default_log_file(monkeypatch=monkeypatch, tmp_path=tmp_path)
    exit_code = cli_main.main(("download", "--ticker", "AAPL", "--debug"))

    captured = capsys.readouterr()
    log_text = log_file.read_text(encoding="utf-8")
    assert exit_code == EXIT_SUCCESS
    assert "Fins progress" in captured.out
    assert "Fins direct event detail" not in captured.out
    assert "[DEBUG]" not in captured.out
    assert "Fins direct event detail" not in captured.err
    assert "Fins direct event detail" in log_text
    assert "event_type=progress" in log_text
    assert "filing_kind=10-K" in log_text
    assert "completed_units=1" in log_text
    assert "total_units=2" in log_text
    assert "status=success" in log_text
    assert "title='Download finished'" in log_text
    assert "exit_code=0" in log_text
    assert "details=processed_count=1" in log_text
    assert "sequence=" not in log_text
    assert "job_id=" not in log_text
    assert "cursor" not in log_text
    assert "artifact" not in log_text


def test_fins_direct_debug_diagnostic_details_are_bounded() -> None:
    """DEBUG 诊断 details 必须限制条目数，避免日志体量失控。

    :returns: ``None``。
    :raises AssertionError: detail 条目未被限制时抛出。
    """

    event = FinsEvent(
        event_type=FinsEventType.RESULT,
        operation_kind=FinsOperationKind.DOWNLOAD,
        message="download finished",
        emitted_at=_NOW,
        ticker="AAPL",
        filing_kind="10-K",
        document_label="AAPL 10-K FY2024",
        progress=None,
        result=FinsResultSummary(
            status=FinsResultStatus.SUCCESS,
            exit_code=FINS_DIRECT_EXIT_SUCCESS,
            title="Download finished",
            details=(
                FinsEventDetail(label="d0", value="v0"),
                FinsEventDetail(label="d1", value="v1"),
                FinsEventDetail(label="d2", value="v2"),
                FinsEventDetail(label="d3", value="v3"),
                FinsEventDetail(label="d4", value="v4"),
            ),
            error_kind=None,
            error_message=None,
        ),
    )

    diagnostic = " ".join(fins_command._fins_event_debug_diagnostic_parts(event))

    assert "details=d0=v0,d1=v1,d2=v2,d3=v3" in diagnostic
    assert "d4=v4" not in diagnostic


def test_output_keeps_absolute_paths_visible_and_bounded() -> None:
    """CLI output 层不把路径当 secret，但仍限制展示长度。"""

    long_value = "/Users/example/" + ("nested/" * 40)

    assert cli_output._safe_text_value("/tmp/a") == "/tmp/a"
    assert cli_output._safe_text_value("path=/Users/a/b") == "path=/Users/a/b"
    assert cli_output._safe_text_value(r"error=C:\tmp\a") == r"error=C:\tmp\a"
    rendered = cli_output._safe_text_value(long_value)
    assert rendered.startswith("/Users/example/nested/")
    assert rendered.endswith("...")
    assert len(rendered) == 120


def test_download_help_explains_mutually_exclusive_mutation_modes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """download help 应分别说明 overwrite 与 rebuild 不可组合。

    Args:
        capsys: pytest 标准输出捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: 任一 option、互斥说明或退出码不符合契约时抛出。
    """

    exit_code = cli_main.main(("download", "--help"))

    captured = capsys.readouterr()
    assert exit_code == EXIT_SUCCESS
    assert "--overwrite" in captured.out
    assert "覆盖已有原始文档；不可与 --rebuild 同时使用。" in captured.out
    assert "--rebuild" in captured.out
    assert "不访问远端来源；不可与 --overwrite 同时使用。" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    ("mutation_flag", "expected_overwrite", "expected_rebuild"),
    (
        ("--overwrite", True, False),
        ("--rebuild", False, True),
    ),
)
def test_download_command_maps_single_mutation_mode_to_service(
    fake_service: _FakeFinsDirectService,
    mutation_flag: str,
    expected_overwrite: bool,
    expected_rebuild: bool,
) -> None:
    """download CLI 应分别把合法单一变更模式映射到 Service。

    Args:
        fake_service: direct service 测试替身。
        mutation_flag: 当前用例传入的变更模式 flag。
        expected_overwrite: request 中预期的 overwrite 值。
        expected_rebuild: request 中预期的 rebuild 值。

    Returns:
        无。

    Raises:
        AssertionError: CLI 参数映射或退出码不符合契约时抛出。
    """

    exit_code = cli_main.main(
        (
            "download",
            "--ticker",
            "aapl.us",
            "--forms",
            "10-k",
            "10-Q",
            "--start",
            "2024-01-01",
            "--end",
            "2024-12-31",
            mutation_flag,
        )
    )

    assert exit_code == EXIT_SUCCESS
    assert fake_service.download_requests == [
        build_fins_download_request(
            ticker="aapl.us",
            form_types=("10-K", "10-Q"),
            start="2024-01-01",
            end="2024-12-31",
            overwrite_existing=expected_overwrite,
            rebuild_local_artifacts=expected_rebuild,
        )
    ]


@pytest.mark.parametrize(
    ("start", "end", "expected_start", "expected_end"),
    (
        ("1000", "9999", "1000-01-01", "9999-12-31"),
        ("2024-2", "2024-2", "2024-02-01", "2024-02-29"),
        ("0001-1-1", "0999-12-31", "0001-01-01", "0999-12-31"),
        (" 2024-2-9 ", " 2024-2-9 ", "2024-02-09", "2024-02-09"),
    ),
)
def test_download_date_bounds_preserve_shape_canonicalization_and_inclusive_expansion(
    start: str,
    end: str,
    expected_start: str,
    expected_end: str,
) -> None:
    """下载日期应保留三种 shape、外围空白与 inclusive 展开契约。

    Args:
        start: 原始起始边界。
        end: 原始结束边界。
        expected_start: 预期 canonical inclusive 起始日期。
        expected_end: 预期 canonical inclusive 结束日期。

    Returns:
        无。

    Raises:
        AssertionError: canonicalization 或 inclusive 展开不符合契约时抛出。
    """

    request = build_fins_download_request(ticker="AAPL", start=start, end=end)

    assert request.date_range.start_text == expected_start
    assert request.date_range.end_text == expected_end


@pytest.mark.parametrize(
    "partial_bound",
    ("0999", "0000", "0999-12", "0000-1"),
)
def test_download_partial_year_rejects_values_outside_shared_year_domain(
    partial_bound: str,
) -> None:
    """year 与 year-month 应共同拒绝 ``1000..9999`` 之外的 partial year。

    Args:
        partial_bound: 当前非法 year 或 year-month 边界。

    Returns:
        无。

    Raises:
        AssertionError: 非法 partial year 未按 download usage contract 拒绝时抛出。
    """

    with pytest.raises(download_contract.FinsDownloadUsageError) as exc_info:
        build_fins_download_request(ticker="AAPL", start=partial_bound)

    assert str(exc_info.value) == ("--start 不是有效日期，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD")


@pytest.mark.parametrize(
    "full_date_bound",
    ("0000-12-31", "2023-2-29", "2024-13-1", "2024-4-31"),
)
def test_download_full_date_rejects_nonexistent_calendar_dates(
    full_date_bound: str,
) -> None:
    """full-date 应拒绝公历年零、非闰日和非法月日。

    Args:
        full_date_bound: 当前不存在的 full-date 边界。

    Returns:
        无。

    Raises:
        AssertionError: 不存在的公历日期未被拒绝时抛出。
    """

    with pytest.raises(download_contract.FinsDownloadUsageError) as exc_info:
        build_fins_download_request(ticker="AAPL", start=full_date_bound)

    assert str(exc_info.value) == ("--start 不是有效日期，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD")


def test_download_date_bound_delegates_shared_year_and_full_date_owners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """download wrapper 应只把共同年份与 full-date 合法性委托 domain owner。

    Args:
        monkeypatch: owner 调用记录替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: wrapper 未调用 shared owner 或错误耦合两类年份时抛出。
    """

    year_calls: list[tuple[int, str]] = []
    date_calls: list[tuple[str, str]] = []
    real_parse_calendar_year = download_contract.parse_calendar_year
    real_parse_iso_calendar_date = download_contract.parse_iso_calendar_date

    def record_year(value: int, *, field_name: str = "year") -> int:
        """记录并调用真实 partial-year owner。

        Args:
            value: 待校验年份。
            field_name: download wrapper 字段名。

        Returns:
            真实 owner 返回的年份。

        Raises:
            ValueError: 真实 owner 拒绝年份时抛出。
        """

        year_calls.append((value, field_name))
        return real_parse_calendar_year(value, field_name=field_name)

    def record_date(value: str, *, field_name: str = "date") -> date:
        """记录并调用真实 canonical full-date owner。

        Args:
            value: 已由 download wrapper 补零的 full-date 文本。
            field_name: download wrapper 字段名。

        Returns:
            真实 owner 返回的公历日期。

        Raises:
            ValueError: 真实 owner 拒绝日期时抛出。
        """

        date_calls.append((value, field_name))
        return real_parse_iso_calendar_date(value, field_name=field_name)

    monkeypatch.setattr(download_contract, "parse_calendar_year", record_year)
    monkeypatch.setattr(download_contract, "parse_iso_calendar_date", record_date)

    partial_request = build_fins_download_request(
        ticker="AAPL",
        start="1000",
        end="2024-2",
    )
    assert partial_request.date_range.start_text == "1000-01-01"
    assert partial_request.date_range.end_text == "2024-02-29"
    assert year_calls == [(1000, "--start"), (2024, "--end")]
    assert date_calls == []

    full_date_request = build_fins_download_request(
        ticker="AAPL",
        start="0001-1-1",
        end="0999-12-31",
    )
    assert full_date_request.date_range.start_text == "0001-01-01"
    assert full_date_request.date_range.end_text == "0999-12-31"
    assert year_calls == [(1000, "--start"), (2024, "--end")]
    assert date_calls == [
        ("0001-01-01", "--start"),
        ("0999-12-31", "--end"),
    ]


def test_download_public_iso_dates_delegate_shared_full_date_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """download public DTO 的 calendar validity 应委托 shared full-date owner。

    Args:
        monkeypatch: owner 调用记录替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: public DTO 未委托 owner 或接受非法日期时抛出。
    """

    date_calls: list[tuple[str, str]] = []
    real_parse_iso_calendar_date = download_contract.parse_iso_calendar_date

    def record_date(value: str, *, field_name: str = "date") -> date:
        """记录并调用真实 canonical full-date owner。

        Args:
            value: public DTO 日期文本。
            field_name: public DTO 字段名。

        Returns:
            真实 owner 返回的公历日期。

        Raises:
            ValueError: 真实 owner 拒绝日期时抛出。
        """

        date_calls.append((value, field_name))
        return real_parse_iso_calendar_date(value, field_name=field_name)

    monkeypatch.setattr(download_contract, "parse_iso_calendar_date", record_date)

    filters = FinsDownloadEffectiveFilters(
        form_types=(),
        start_date="0001-01-01",
        end_date="2024-02-29",
        overwrite_existing=False,
        rebuild_local_artifacts=False,
    )
    assert filters.start_date == "0001-01-01"
    assert filters.end_date == "2024-02-29"
    assert date_calls == [
        ("0001-01-01", "start_date"),
        ("2024-02-29", "end_date"),
    ]

    with pytest.raises(ValueError, match="start_date must be an ISO date"):
        FinsDownloadEffectiveFilters(
            form_types=(),
            start_date="2023-02-29",
            end_date=None,
            overwrite_existing=False,
            rebuild_local_artifacts=False,
        )

    with pytest.raises(ValueError) as basic_format_exc:
        FinsDownloadEffectiveFilters(
            form_types=(),
            start_date="20240229",
            end_date=None,
            overwrite_existing=False,
            rebuild_local_artifacts=False,
        )
    assert str(basic_format_exc.value) == "start_date must be an ISO date"


def test_download_date_range_ordering_remains_owned_by_range_contract() -> None:
    """展开后的 start/end ordering 应继续由 ``FinsDownloadDateRange`` 拒绝。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: ordering error 类型或 message 发生漂移时抛出。
    """

    with pytest.raises(download_contract.FinsDownloadUsageError) as exc_info:
        build_fins_download_request(ticker="AAPL", start="2025", end="2024-12")

    assert str(exc_info.value) == "--start 不能晚于 --end，请检查下载日期范围"


@pytest.mark.parametrize(
    ("download_args", "expected_message"),
    (
        ((), "--ticker 不能为空，请提供一个公司代码"),
        (("--ticker", "AAPL,MSFT"), "只接受一个公司代码"),
        (("--ticker", "AAPL", "--forms", "UNKNOWN"), "--forms 不支持"),
        (("--ticker", "AAPL", "--start", "2024/01/01"), "--start 格式错误"),
        (
            ("--ticker", "AAPL", "--start", "2025", "--end", "2024"),
            "--start 不能晚于 --end",
        ),
    ),
)
def test_download_static_usage_error_precedes_workspace_and_service_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    download_args: tuple[str, ...],
    expected_message: str,
) -> None:
    """静态 download usage error 应 exit 2 且不解析出任何 workspace 副作用。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: factory 替换夹具。
        capsys: 标准流捕获夹具。
        download_args: 当前非法 download 参数。
        expected_message: 预期中文错误片段。

    Returns:
        无。

    Raises:
        AssertionError: factory 被调用、workspace 被创建或退出语义错误时抛出。
    """

    workspace_root = tmp_path / "must-not-exist"
    factory_calls: list[Path] = []

    def forbidden_factory(path: Path) -> fins_command.FinsDirectCommandService:
        """记录不应发生的 Service factory 调用。

        Args:
            path: CLI 传入的 workspace root。

        Returns:
            不返回。

        Raises:
            AssertionError: factory 一旦被调用即抛出。
        """

        factory_calls.append(path)
        raise AssertionError("usage error 不得构造 Service")

    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", forbidden_factory)

    exit_code = cli_main.main(("download", "--base", str(workspace_root), *download_args))

    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert expected_message in captured.err
    if download_args == ():
        assert captured.err == ("dayu-cli download: --ticker 不能为空，请提供一个公司代码\n")
    assert factory_calls == []
    assert not workspace_root.exists()


@pytest.mark.parametrize(
    ("case_id", "argv_suffix", "expected_reason"),
    (
        ("UF-003", ("--ticker", ""), "--ticker 不能为空，请提供公司代码"),
        ("UF-004", ("--ticker", "../../etc/passwd"), "--ticker 无法识别，请提供有效公司代码"),
        ("UF-005", ("--ticker", "ABCDEFGHI"), "--ticker 无法识别，请提供有效公司代码"),
        ("UF-006", ("--ticker", "AAPL,"), "--ticker 不能为空，请提供公司代码"),
        ("UF-015", ("--ticker", "AAPL", "--fiscal-period", "FY"), "--fiscal-year 不能为空"),
        ("UF-016", ("--ticker", "AAPL", "--fiscal-year", "2024"), "--fiscal-period 不能为空"),
        (
            "UF-017",
            (
                "--ticker",
                "AAPL",
                "--fiscal-year",
                "2024",
                "--fiscal-period",
                "FY",
                "--company-name",
                "Apple Inc.",
            ),
            "create/update 上传必须提供 --files",
        ),
        (
            "UF-018",
            (
                "--ticker",
                "AAPL",
                "--files",
                "{input}/probe.txt",
                "--fiscal-year",
                "2024",
                "--fiscal-period",
                "FY",
            ),
            "当前公司缺少有效元数据；create/update 必须提供 --company-name",
        ),
        (
            "UF-019",
            (
                "--ticker",
                "AAPL",
                "--fiscal-year",
                "2024",
                "--fiscal-period",
                "FY",
                "--company-name",
                "",
            ),
            "create/update 上传必须提供 --files",
        ),
        (
            "UF-021",
            ("--ticker", "AAPL", "--fiscal-year", "-1", "--fiscal-period", "FY"),
            "财年（fiscal_year）必须是 1000..9999 的整数",
        ),
        *tuple(
            (
                f"UF-S2-year-{raw_year}",
                ("--ticker", "AAPL", "--fiscal-year", raw_year, "--fiscal-period", "FY"),
                "财年（fiscal_year）必须是 1000..9999 的整数",
            )
            for raw_year in ("0", "999", "10000")
        ),
        *tuple(
            (
                f"UF-S2-filing-date-{case_id}",
                (
                    "--ticker",
                    "AAPL",
                    "--action",
                    "delete",
                    "--fiscal-year",
                    "2024",
                    "--fiscal-period",
                    "FY",
                    "--filing-date",
                    raw_date,
                ),
                "披露日期（filing_date）必须是实际存在的 YYYY-MM-DD 日期",
            )
            for case_id, raw_date in (
                ("empty", ""),
                ("blank", " "),
                ("padded", " 2024-02-29 "),
                ("non-padded", "2024-2-29"),
                ("non-leap", "2023-02-29"),
                ("month", "2024-13-01"),
                ("separator", "2024/02/29"),
            )
        ),
        *tuple(
            (
                f"UF-S2-report-date-{case_id}",
                (
                    "--ticker",
                    "AAPL",
                    "--action",
                    "delete",
                    "--fiscal-year",
                    "2024",
                    "--fiscal-period",
                    "FY",
                    "--report-date",
                    raw_date,
                ),
                "报告期日期（report_date）必须是实际存在的 YYYY-MM-DD 日期",
            )
            for case_id, raw_date in (
                ("empty", ""),
                ("blank", "\t"),
                ("padded", "2024-02-29 "),
                ("non-padded", "2024-2-29"),
                ("non-leap", "2023-02-29"),
                ("month", "2024-00-01"),
                ("separator", "2024.02.29"),
            )
        ),
        (
            "UF-S2-seeded-invalid-report-date",
            (
                "--ticker",
                "AAPL",
                "--action",
                "delete",
                "--fiscal-year",
                "2024",
                "--fiscal-period",
                "FY",
                "--report-date",
                "2024-04-31",
            ),
            "报告期日期（report_date）必须是实际存在的 YYYY-MM-DD 日期",
        ),
        (
            "UF-022",
            ("--ticker", "AAPL", "--fiscal-year", "2024", "--fiscal-period", ""),
            "--fiscal-period 不能为空",
        ),
        (
            "UF-023",
            ("--ticker", "AAPL", "--fiscal-year", "2024", "--fiscal-period", "X" * 300),
            "--fiscal-period 长度不能超过 240 个字符",
        ),
        (
            "UF-024",
            ("--ticker", "600519", "--fiscal-year", "2024", "--fiscal-period", "9M"),
            "CN/HK --fiscal-period 仅支持 Q1、Q2、Q3、Q4、H1、FY",
        ),
        (
            "UF-026",
            (
                "--ticker",
                "AAPL",
                "--fiscal-year",
                "2024",
                "--fiscal-period",
                "FY",
                "--company-name",
                "Apple Inc.",
                "--files",
                "{input}/missing.pdf",
            ),
            "上传文件不存在：missing.pdf",
        ),
        (
            "UF-027",
            (
                "--ticker",
                "AAPL",
                "--fiscal-year",
                "2024",
                "--fiscal-period",
                "FY",
                "--company-name",
                "Apple Inc.",
                "--files",
                "{input}",
            ),
            "上传路径不是普通文件：input",
        ),
        *tuple(
            (
                case_id,
                (
                    "--ticker",
                    "AAPL",
                    "--fiscal-year",
                    "2024",
                    "--fiscal-period",
                    "FY",
                    "--company-name",
                    "Apple Inc.",
                    "--files",
                    f"{{input}}/probe.{suffix}",
                ),
                expected_reason,
            )
            for case_id, suffix, expected_reason in (
                ("UF-028", "bin", "财报主文件格式不受支持：probe.bin"),
                ("UF-030", "doc", "财报主文件格式不受支持：probe.doc"),
                ("UF-031", "ppt", "财报主文件格式不受支持：probe.ppt"),
                ("UF-FIX06-XLS", "xls", "财报主文件格式不受支持：probe.xls"),
                ("UF-038", "zip", "财报主文件格式不受支持：probe.zip"),
                ("UF-FIX06-XSD", "xsd", "财报主文件格式不受支持：probe.xsd"),
            )
        ),
    ),
)
def test_upload_filing_usage_matrix_precedes_service_factory_and_workspace_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case_id: str,
    argv_suffix: tuple[str, ...],
    expected_reason: str,
) -> None:
    """冻结 filing usage case 必须在 Service factory 前 exact 映射为 exit 2。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: factory 替换夹具。
        capsys: 标准流捕获夹具。
        case_id: frozen usage case 标识。
        argv_suffix: ``upload_filing --base`` 后的冻结参数。
        expected_reason: usage owner 的精确可行动文案。

    Returns:
        无。

    Raises:
        AssertionError: factory/service 被调用、workspace 变化或标准流不精确时抛出。
    """

    workspace_root = tmp_path / f"workspace-{case_id}"
    seed_workspace = case_id == "UF-S2-seeded-invalid-report-date"
    if seed_workspace:
        workspace_root.mkdir(parents=True)
        (workspace_root / "sentinel.txt").write_text("unchanged", encoding="utf-8")
    before_tree = _snapshot_cli_workspace_tree(workspace_root)
    input_root = tmp_path / "input"
    input_root.mkdir()
    for suffix in ("txt", "bin", "doc", "ppt", "xls", "zip", "xsd"):
        (input_root / f"probe.{suffix}").write_text("fixture", encoding="utf-8")
    resolved_argv = tuple(token.format(input=str(input_root)) for token in argv_suffix)
    service = _FakeFinsDirectService()
    factory_calls: list[Path] = []
    recording_factory = partial(
        _recording_direct_service_factory,
        service=service,
        factory_calls=factory_calls,
    )
    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", recording_factory)

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--base",
            str(workspace_root),
            *resolved_argv,
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert captured.out == ""
    assert captured.err == f"dayu-cli upload_filing: {expected_reason}\n"
    assert factory_calls == []
    assert service.upload_filing_requests == []
    assert service.stream_calls == []
    assert _snapshot_cli_workspace_tree(workspace_root) == before_tree
    assert workspace_root.exists() is seed_workspace


@pytest.mark.parametrize(
    ("case_id", "action", "overwrite", "seed_existing", "expected_reason"),
    (
        (
            "update-missing",
            "update",
            False,
            False,
            "update 目标不存在；请改用 create",
        ),
        (
            "update-missing-overwrite",
            "update",
            True,
            False,
            "update 目标不存在；请改用 create",
        ),
        (
            "create-existing",
            "create",
            False,
            True,
            "create 目标已存在；请改用 update 或允许覆盖",
        ),
    ),
)
def test_upload_filing_state_conflict_exits_before_service_factory_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case_id: str,
    action: str,
    overwrite: bool,
    seed_existing: bool,
    expected_reason: str,
) -> None:
    """真实 published state 冲突必须在 Service factory 前精确失败且零 mutation。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: factory 替换夹具。
        capsys: 标准流捕获夹具。
        case_id: 当前 admission 场景标识。
        action: 显式上传动作。
        overwrite: 是否传入 ``--overwrite``。
        seed_existing: 是否先通过真实 storage 发布目标。
        expected_reason: 精确单行 stderr 原因。

    Returns:
        无。

    Raises:
        AssertionError: exit、标准流、factory 或 workspace contract 漂移时抛出。
    """

    workspace_root = tmp_path / f"workspace-{case_id}"
    if seed_existing:
        _seed_cli_filing_source(workspace_root)
    before_tree = _snapshot_cli_workspace_tree(workspace_root)
    input_file = tmp_path / f"{case_id}.txt"
    input_file.write_text("input", encoding="utf-8")
    service = _FakeFinsDirectService()
    factory_calls: list[Path] = []
    recording_factory = partial(
        _recording_direct_service_factory,
        service=service,
        factory_calls=factory_calls,
    )
    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", recording_factory)
    overwrite_args = ("--overwrite",) if overwrite else ()

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--base",
            str(workspace_root),
            "--ticker",
            "AAPL",
            "--action",
            action,
            "--files",
            str(input_file),
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            "FY",
            "--company-name",
            "Apple Inc.",
            *overwrite_args,
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert captured.out == ""
    assert captured.err == f"dayu-cli upload_filing: {expected_reason}\n"
    assert captured.err.count("\n") == 1
    assert len(captured.err) <= _MAX_PUBLIC_CONTENT_FAILURE_STDERR_CHARS
    assert factory_calls == []
    assert service.upload_filing_requests == []
    assert service.stream_calls == []
    assert _snapshot_cli_workspace_tree(workspace_root) == before_tree
    assert workspace_root.exists() is seed_existing


@pytest.mark.parametrize("overwrite", (False, True))
def test_upload_filing_existing_update_projects_typed_request_to_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overwrite: bool,
) -> None:
    """existing filing 的 update 必须把 action/overwrite 精确投影给 Service。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: factory 替换夹具。
        overwrite: 是否传入 ``--overwrite``。

    Returns:
        无。

    Raises:
        AssertionError: CLI admission 或 typed Service handoff 漂移时抛出。
    """

    workspace_root = tmp_path / f"workspace-update-{overwrite}"
    _seed_cli_filing_source(workspace_root)
    input_file = tmp_path / f"update-{overwrite}.txt"
    input_file.write_text("updated input", encoding="utf-8")
    service = _FakeFinsDirectService()
    factory_calls: list[Path] = []
    recording_factory = partial(
        _recording_direct_service_factory,
        service=service,
        factory_calls=factory_calls,
    )
    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", recording_factory)
    overwrite_args = ("--overwrite",) if overwrite else ()

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--base",
            str(workspace_root),
            "--ticker",
            "AAPL",
            "--action",
            "update",
            "--files",
            str(input_file),
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            "FY",
            "--company-name",
            "Apple Inc.",
            *overwrite_args,
        )
    )

    assert exit_code == EXIT_SUCCESS
    assert factory_calls == [workspace_root]
    assert service.upload_filing_requests == [
        _UploadFilingCall(
            ticker="AAPL",
            action="update",
            files=(input_file.resolve(),),
            fiscal_year=2024,
            fiscal_period="FY",
            amended=False,
            filing_date=None,
            report_date=None,
            company_name="Apple Inc.",
            ticker_aliases=(),
            overwrite=overwrite,
        )
    ]
    assert service.stream_calls == [FinsOperationKind.UPLOAD_FILING]


def test_upload_filing_prevalidation_io_failure_is_typed_bounded_and_path_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """prevalidation I/O failure 必须 exit 1 且 public stderr 不泄漏路径。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: storage read failure 注入夹具。
        capsys: 标准流捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: failure 未经 typed owner 投影或泄漏内部路径时抛出。
    """

    workspace_root = tmp_path / "workspace"
    input_file = tmp_path / "filing.pdf"
    input_file.write_text("filing", encoding="utf-8")

    def fail_read(
        _repository: FsFilingUploadStateRepository,
        ticker: str,
        document_id: str,
    ) -> NoReturn:
        """注入包含绝对路径的 permission failure。

        Args:
            _repository: production state repository。
            ticker: canonical ticker。
            document_id: filing document identity。

        Returns:
            不返回。

        Raises:
            PermissionError: 始终抛出包含内部路径的异常。
        """

        del ticker, document_id
        raise PermissionError(f"permission denied: {workspace_root / 'portfolio' / 'AAPL'}")

    monkeypatch.setattr(FsFilingUploadStateRepository, "read_filing_upload_state", fail_read)

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--base",
            str(workspace_root),
            "--ticker",
            "AAPL",
            "--files",
            str(input_file),
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            "FY",
            "--company-name",
            "Apple Inc.",
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_FAILURE
    assert captured.out == ""
    assert captured.err == ("dayu-cli upload_filing: 上传状态读取失败，请检查工作区存储状态\n")
    assert str(tmp_path) not in captured.err
    assert "Traceback" not in captured.err
    assert "PermissionError" not in captured.err


def test_upload_filing_repository_resolve_failure_preserves_cli_boundary_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """构造期 resolve failure 必须 exit 1、stderr 脱敏、日志留因且零 mutation。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: 第二次 workspace resolve failure 注入夹具。
        capsys: 标准流捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: CLI public/operator boundary 或零 mutation contract 漂移时抛出。
    """

    workspace_root = tmp_path / "workspace"
    input_file = tmp_path / "filing.pdf"
    input_file.write_text("filing", encoding="utf-8")
    operator_log = tmp_path / "operator.log"
    real_resolve = Path.resolve
    workspace_resolve_count = 0

    def fail_repository_workspace_resolve(path: Path, strict: bool = False) -> Path:
        """允许 CLI 解析 workspace，但在 repository 再次 resolve 时注入失败。

        Args:
            path: 当前待解析路径。
            strict: 是否要求路径已经存在。

        Returns:
            CLI 首次 workspace resolve 与其它路径的真实解析结果。

        Raises:
            PermissionError: repository 构造期再次解析 workspace 时抛出。
        """

        nonlocal workspace_resolve_count
        if path == workspace_root:
            workspace_resolve_count += 1
            if workspace_resolve_count == 2:
                raise PermissionError(errno.EACCES, "resolve denied", str(workspace_root))
        return real_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_repository_workspace_resolve)

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--base",
            str(workspace_root),
            "--log-file",
            str(operator_log),
            "--ticker",
            "AAPL",
            "--files",
            str(input_file),
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            "FY",
            "--company-name",
            "Apple Inc.",
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_FAILURE
    assert captured.out == ""
    assert captured.err == "dayu-cli upload_filing: 上传状态读取失败，请检查工作区存储状态\n"
    assert str(tmp_path) not in captured.err
    operator_diagnostic = operator_log.read_text(encoding="utf-8")
    assert "upload_filing prevalidation operational failure" in operator_diagnostic
    assert "PermissionError" in operator_diagnostic
    assert "解析 storage workspace底层文件系统失败" in operator_diagnostic
    assert workspace_resolve_count == 2
    assert not workspace_root.exists()


@pytest.mark.parametrize(
    "corruption",
    (
        "descriptor_malformed",
        "meta_malformed",
        "meta_symlink",
        "meta_directory",
        "target_symlink",
        "target_regular_file",
    ),
)
def test_upload_filing_prevalidation_identity_corruption_is_typed_and_path_free(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    corruption: str,
) -> None:
    """真实 descriptor/meta/target corruption 必须只输出 closed bounded reason。

    Args:
        tmp_path: pytest 临时目录。
        capsys: 标准流捕获夹具。
        corruption: 待注入的 durable corruption 形态。

    Returns:
        无。

    Raises:
        AssertionError: corruption 被当 usage/generic pathful failure 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    portfolio_root = workspace_root / "portfolio"
    portfolio_root.mkdir(parents=True)
    ticker_root = portfolio_root / "AAPL"
    if corruption == "target_symlink":
        outside_root = tmp_path / "outside-company"
        outside_root.mkdir()
        ticker_root.symlink_to(outside_root, target_is_directory=True)
    elif corruption == "target_regular_file":
        ticker_root.write_bytes(b"foreign locator")
    else:
        ticker_root.mkdir()
        descriptor_path = ticker_root / ".identity.json"
        if corruption == "descriptor_malformed":
            descriptor_path.write_text("{}", encoding="utf-8")
        else:
            descriptor_path.write_text(
                '{"namespace":"ticker","external_identity":"AAPL"}',
                encoding="utf-8",
            )
            meta_path = ticker_root / "meta.json"
            if corruption == "meta_malformed":
                meta_path.write_text("{}", encoding="utf-8")
            elif corruption == "meta_symlink":
                outside_meta = tmp_path / "outside-meta.json"
                outside_meta.write_text("{}", encoding="utf-8")
                meta_path.symlink_to(outside_meta)
            else:
                meta_path.mkdir()
    input_file = tmp_path / "filing.pdf"
    input_file.write_text("filing", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--base",
            str(workspace_root),
            "--ticker",
            "AAPL",
            "--files",
            str(input_file),
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            "FY",
            "--company-name",
            "Apple Inc.",
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_FAILURE
    assert captured.out == ""
    assert captured.err == ("dayu-cli upload_filing: 上传状态已损坏，请检查工作区存储状态\n")
    assert str(tmp_path) not in captured.err
    assert "Traceback" not in captured.err
    assert "ValueError" not in captured.err


@pytest.mark.parametrize(
    "mutation_flags",
    (
        ("--overwrite", "--rebuild"),
        ("--rebuild", "--overwrite"),
    ),
)
def test_download_mutation_mode_conflict_precedes_all_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutation_flags: tuple[str, str],
) -> None:
    """两种冲突 argv 顺序都应在 workspace、factory 与 operation 前 exit 2。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: factory 替换夹具。
        capsys: 标准流捕获夹具。
        mutation_flags: 当前用例的冲突 flag 顺序。

    Returns:
        无。

    Raises:
        AssertionError: 冲突未前置拒绝或产生任一副作用时抛出。
    """

    workspace_root = tmp_path / "must-not-exist"
    service = _FakeFinsDirectService()
    factory_calls: list[Path] = []
    recording_factory = partial(
        _recording_direct_service_factory,
        service=service,
        factory_calls=factory_calls,
    )

    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", recording_factory)

    exit_code = cli_main.main(
        (
            "download",
            "--base",
            str(workspace_root),
            "--ticker",
            "AAPL",
            *mutation_flags,
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert captured.err == ("dayu-cli download: --overwrite 与 --rebuild 不能同时使用；请只选择一种下载变更模式\n")
    assert factory_calls == []
    assert service.download_requests == []
    assert service.stream_calls == []
    assert not workspace_root.exists()


@pytest.mark.parametrize(
    ("file_name", "payload", "expected_reason", "expected_failure_code"),
    (
        ("empty.pdf", b"", "文件为空，无法上传", "empty_input_file"),
        (
            "corrupt.pdf",
            _UNPARSABLE_PDF_BYTES,
            _TYPED_CONTENT_FAILURE_REASON,
            "docling_converter_execution",
        ),
        (
            "corrupt.docx",
            _UNPARSABLE_DOCX_BYTES,
            _TYPED_CONTENT_FAILURE_REASON,
            "docling_converter_execution",
        ),
    ),
)
def test_real_cli_content_failure_has_bounded_stderr_and_zero_fresh_workspace_mutation(
    tmp_path: Path,
    file_name: str,
    payload: bytes,
    expected_reason: str,
    expected_failure_code: str,
) -> None:
    """真实 CLI empty/corrupt PDF/DOCX failure 必须安全投影且零 mutation。

    Args:
        tmp_path: pytest 临时目录。
        file_name: 当前失败输入的安全 basename。
        payload: 当前失败输入 bytes。
        expected_reason: 当前 closed content reason。
        expected_failure_code: 当前 closed content failure code。

    Returns:
        无。

    Raises:
        AssertionError: CLI contract 漂移、stderr 泄漏或 workspace 变化时抛出。
        subprocess.TimeoutExpired: 真实 conversion 未在期限内结束时抛出。
    """

    corrupt_file = tmp_path / file_name
    corrupt_file.write_bytes(payload)
    workspace_root = tmp_path / "fresh-workspace"
    cli_executable = Path(sys.executable).with_name("dayu-cli")
    repository_root = Path(__file__).resolve().parents[2]

    completed = subprocess.run(
        (
            str(cli_executable),
            "upload_filing",
            "--base",
            str(workspace_root),
            "--ticker",
            "ICPD",
            "--files",
            str(corrupt_file),
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            "FY",
            "--company-name",
            "ICPD Corp.",
        ),
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )

    assert completed.returncode == EXIT_FAILURE
    assert expected_reason in completed.stderr
    assert 'failure_kind="content"' in completed.stderr
    assert f'failure_code="{expected_failure_code}"' in completed.stderr
    assert 'requested_files="1"' in completed.stderr
    assert 'stored_files="0"' in completed.stderr
    assert f'file="{file_name}"' in completed.stderr
    assert len(completed.stderr) <= _MAX_PUBLIC_CONTENT_FAILURE_STDERR_CHARS
    assert "Traceback" not in completed.stderr
    assert str(repository_root) not in completed.stderr
    assert str(corrupt_file) not in completed.stderr
    assert not workspace_root.exists()


def test_download_repeated_ticker_is_last_wins(
    fake_service: _FakeFinsDirectService,
) -> None:
    """重复 ``--ticker`` 应由 argparse 保持 last-wins 并传递最终 canonical ticker。

    Args:
        fake_service: direct service 测试替身。

    Returns:
        无。

    Raises:
        AssertionError: 未使用最后一个 ticker 或 canonicalization 失败时抛出。
    """

    exit_code = cli_main.main(("download", "--ticker", "MSFT", "--ticker", "aapl.us"))

    assert exit_code == EXIT_SUCCESS
    assert len(fake_service.download_requests) == 1
    assert fake_service.download_requests[0].normalized_ticker.canonical == "AAPL"


def test_download_path_does_not_reuse_upload_ticker_csv_parser() -> None:
    """download 专用 builder 不得调用保留 alias 语义的 ``_parse_ticker_csv``。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: download 与 upload/preprocess ticker ownership 混用时抛出。
    """

    source = Path(fins_command.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls_by_function: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls_by_function[node.name] = {
            child.func.id
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }

    assert "_parse_ticker_csv" not in calls_by_function["_prevalidate_download_request"]
    assert "_parse_ticker_csv" not in calls_by_function["_download_stream"]
    assert "_parse_ticker_csv" not in calls_by_function["_upload_filing_stream"]
    assert (
        "prevalidate_fins_upload_filing_request_for_workspace"
        in calls_by_function["_prevalidate_upload_filing_request"]
    )
    assert "_parse_ticker_csv" in calls_by_function["_run_upload_filings_from"]


def test_upload_commands_map_args_and_validate_files(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
) -> None:
    """upload_filing/material CLI 必须调用 Service direct stream 方法。

    Args:
        tmp_path: pytest 临时目录。
        fake_service: 记录 CLI 参数投影的 direct Service 替身。

    Returns:
        无。

    Raises:
        AssertionError: 参数校验、动作映射或 Service 调用漂移时抛出。
    """

    filing_file = tmp_path / "filing.pdf"
    material_file = tmp_path / "material.html"
    filing_file.write_text("filing", encoding="utf-8")
    material_file.write_text("<html></html>", encoding="utf-8")

    assert (
        cli_main.main(
            (
                "upload_filing",
                "--ticker",
                "AAPL,MSFT",
                "--action",
                "create",
                "--files",
                str(filing_file),
                "--fiscal-year",
                "2024",
                "--fiscal-period",
                "FY",
                "--amended",
                "--filing-date",
                "2025-01-30",
                "--report-date",
                "2024-12-31",
                "--company-name",
                "Apple",
                "--overwrite",
            )
        )
        == EXIT_SUCCESS
    )
    assert (
        cli_main.main(
            (
                "upload_material",
                "--ticker",
                "DELTA,MSFT",
                "--forms",
                "8-K",
                "--material-name",
                "Investor Day",
                "--files",
                str(material_file),
                "--document-id",
                "doc-1",
                "--internal-document-id",
                "internal-1",
            )
        )
        == EXIT_SUCCESS
    )

    assert fake_service.upload_filing_requests == [
        _UploadFilingCall(
            ticker="AAPL",
            action="create",
            files=(filing_file.resolve(),),
            fiscal_year=2024,
            fiscal_period="FY",
            amended=True,
            filing_date="2025-01-30",
            report_date="2024-12-31",
            company_name="Apple",
            ticker_aliases=("MSFT",),
            overwrite=True,
        )
    ]
    assert fake_service.upload_material_requests == [
        _UploadMaterialCall(
            ticker="DELTA",
            action="auto",
            files=(material_file.resolve(),),
            form_type="8-K",
            material_name="Investor Day",
            document_id="doc-1",
            internal_document_id="internal-1",
            fiscal_year=None,
            fiscal_period=None,
            amended=False,
            filing_date=None,
            report_date=None,
            company_name=None,
            ticker_aliases=("MSFT",),
            overwrite=False,
        )
    ]


@pytest.mark.parametrize(
    ("basename", "expected_message"),
    (
        ("schema.xsd", "补充材料文件格式不受支持：schema.xsd"),
        (f"{'a' * 226}.doc", "补充材料文件格式不受支持"),
    ),
)
def test_upload_material_cli_uses_bounded_converter_required_format_owner(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
    basename: str,
    expected_message: str,
) -> None:
    """material CLI 必须用 Fins owner 把普通及长文件名投影为 bounded usage error。

    Args:
        tmp_path: 用于创建非法 material 文件的临时目录。
        fake_service: 记录 direct Service 调用的替身。
        capsys: 标准输出与错误输出捕获夹具。
        basename: 当前非法 material 文件的 canonical basename。
        expected_message: 预期有界格式错误文案。

    Returns:
        无。

    Raises:
        AssertionError: failure kind 的 CLI 投影或零调用边界漂移时抛出。
    """

    material_file = tmp_path / basename
    material_file.write_text("<schema></schema>", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_material",
            "--ticker",
            "AAPL",
            "--forms",
            "MATERIAL_OTHER",
            "--material-name",
            "Schema",
            "--files",
            str(material_file),
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert captured.out == ""
    assert captured.err == f"dayu-cli upload_material: {expected_message}\n"
    assert fake_service.upload_material_requests == []
    assert fake_service.stream_calls == []


def test_upload_material_alias_count_uses_typed_upload_admission(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """material 超量 aliases 必须由共享 upload usage owner 有界拒绝。

    Args:
        tmp_path: pytest 临时目录。
        capsys: 标准流捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: material 绕过数量准入、错误命令名前缀或启动 stream 时抛出。
    """

    ticker_csv = ",".join(("AAPL", *(f"A-{index}" for index in range(101))))
    exit_code = cli_main.main(
        (
            "upload_material",
            "--base",
            str(tmp_path / "workspace"),
            "--ticker",
            ticker_csv,
            "--action",
            "delete",
            "--forms",
            "MATERIAL_OTHER",
            "--material-name",
            "Deck",
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert captured.out == ""
    assert captured.err == ("dayu-cli upload_material: --ticker 别名数量不能超过 100 个\n")


def test_process_commands_map_to_service(
    fake_service: _FakeFinsDirectService,
) -> None:
    """process / process_filing / process_material 必须映射到 direct stream 方法。"""

    assert (
        cli_main.main(
            (
                "process",
                "--ticker",
                "AAPL,MSFT",
                "--document-id",
                "doc-1,doc-2",
                "--document-id",
                "doc-3",
                "--overwrite",
            )
        )
        == EXIT_SUCCESS
    )
    assert cli_main.main(("process_filing", "--ticker", "AAPL", "--document-id", "filing-1")) == EXIT_SUCCESS
    assert cli_main.main(("process_material", "--ticker", "AAPL", "--document-id", "material-1")) == EXIT_SUCCESS

    assert fake_service.process_requests == [
        _ProcessCall(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            document_ids=("doc-1", "doc-2", "doc-3"),
            form_types=(),
            rebuild_processed=True,
        )
    ]
    assert fake_service.process_filing_requests == [
        _ProcessSpecificCall(
            ticker="AAPL",
            document_ids=("filing-1",),
            form_types=(),
            rebuild_processed=False,
        )
    ]
    assert fake_service.process_material_requests == [
        _ProcessSpecificCall(
            ticker="AAPL",
            document_ids=("material-1",),
            form_types=(),
            rebuild_processed=False,
        )
    ]


@pytest.mark.parametrize(
    "argv",
    (
        ("download", "--ticker", "AAPL", "--infer"),
        ("process", "--ticker", "AAPL", "--ci"),
    ),
)
def test_removed_flags_are_argparse_unknown(
    argv: tuple[str, ...],
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """已无 public contract 的 ``--infer`` / ``--ci`` 不应出现在 parser。

    :param argv: 含已删除 flag 的命令参数。
    :param fake_service: direct service 测试替身。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: flag 未按未知参数拒绝或启动了 direct stream 时抛出。
    """

    exit_code = cli_main.main(argv)
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "unrecognized arguments" in captured.err
    assert fake_service.stream_calls == []


def test_terminal_failed_and_cancelled_status_exit_mapping(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI 必须使用 FinsResultSummary 的退出码映射。"""

    failed_service = _FakeFinsDirectService(events=(_result_event(status=FinsResultStatus.FAILURE),))
    cancelled_service = _FakeFinsDirectService(events=(_result_event(status=FinsResultStatus.CANCELLED),))

    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            failed_service,
        ),
    )
    assert cli_main.main(("download", "--ticker", "AAPL")) == EXIT_FAILURE
    failed_output = capsys.readouterr()
    assert "Fins failure" in failed_output.err
    assert "failed" in failed_output.err

    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            cancelled_service,
        ),
    )
    assert cli_main.main(("download", "--ticker", "AAPL")) == EXIT_KEYBOARD_INTERRUPT
    cancelled_output = capsys.readouterr()
    assert "Fins cancelled" in cancelled_output.err


def test_fins_owned_missing_result_uses_existing_cli_error_presentation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 Fins missing error 沿用既有 CLI prefix/message 与 exit 1。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        capsys: pytest 标准输出捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: presentation、exit code 或 owner 边界不符合契约时抛出。
    """

    service = _FakeFinsDirectService(events=(_progress_event(FinsOperationKind.DOWNLOAD),))
    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            service,
        ),
    )

    assert cli_main.main(("download", "--ticker", "AAPL")) == EXIT_FAILURE

    captured = capsys.readouterr()
    assert "dayu-cli download: Fins direct stream ended without RESULT" in captured.err
    assert "Fins failure" not in captured.err
    assert service.closed_streams == 1


def test_fins_owned_duplicate_result_uses_existing_cli_error_presentation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 Fins duplicate error 沿用既有 CLI 展示且不伪造业务结果。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        capsys: pytest 标准输出捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: presentation、exit code 或 owner 边界不符合契约时抛出。
    """

    service = _FakeFinsDirectService(
        events=(_result_event(), _result_event()),
    )
    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            service,
        ),
    )

    assert cli_main.main(("download", "--ticker", "AAPL")) == EXIT_FAILURE

    captured = capsys.readouterr()
    assert "dayu-cli download: Fins direct stream produced multiple RESULT events" in captured.err
    assert "Fins failure" not in captured.err
    assert "failed" not in captured.err
    assert service.closed_streams == 1


@pytest.mark.asyncio
async def test_fins_owned_protocol_error_object_reaches_cli_consumer_unchanged() -> None:
    """验证 CLI consumer 不重建 Fins owner typed error。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: error identity 或 typed fields 发生变化时抛出。
    """

    owner_error = FinsDirectStreamProtocolError(
        FinsDirectStreamProtocolErrorKind.EVENT_AFTER_RESULT,
        FinsOperationKind.DOWNLOAD,
        "Fins direct stream produced an event after RESULT",
    )
    service = _FakeFinsDirectService(
        events=(_progress_event(FinsOperationKind.DOWNLOAD),),
        stream_error=owner_error,
    )
    stream = service.download(build_fins_download_request(ticker="AAPL"))

    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await fins_command._consume_fins_direct_events(stream)

    assert captured.value is owner_error
    assert captured.value.reason is FinsDirectStreamProtocolErrorKind.EVENT_AFTER_RESULT
    assert captured.value.operation_kind is FinsOperationKind.DOWNLOAD
    assert captured.value.message == "Fins direct stream produced an event after RESULT"


@pytest.mark.asyncio
async def test_process_filing_keeps_runtime_preprocess_protocol_error_provenance_through_cli() -> None:
    """验证 CLI consumer 保留 process_filing 的 runtime PREPROCESS 来源。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: error identity 或 operation provenance 改变时抛出。
    """

    owner_error = FinsDirectStreamProtocolError(
        FinsDirectStreamProtocolErrorKind.DUPLICATE_RESULT,
        FinsOperationKind.PREPROCESS,
        "Fins direct stream produced multiple RESULT events",
    )
    service = _FakeFinsDirectService(events=(), stream_error=owner_error)
    stream = service.process_filing(ticker="AAPL", document_ids=("filing-1",))

    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await fins_command._consume_fins_direct_events(stream)

    assert captured.value is owner_error
    assert captured.value.reason is FinsDirectStreamProtocolErrorKind.DUPLICATE_RESULT
    assert captured.value.operation_kind is FinsOperationKind.PREPROCESS


@pytest.mark.asyncio
async def test_process_material_keeps_runtime_preprocess_protocol_error_provenance_through_cli() -> None:
    """验证 CLI consumer 保留 process_material 的 runtime PREPROCESS 来源。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: error identity 或 operation provenance 改变时抛出。
    """

    owner_error = FinsDirectStreamProtocolError(
        FinsDirectStreamProtocolErrorKind.EVENT_AFTER_RESULT,
        FinsOperationKind.PREPROCESS,
        "Fins direct stream produced an event after RESULT",
    )
    service = _FakeFinsDirectService(events=(), stream_error=owner_error)
    stream = service.process_material(ticker="AAPL", document_ids=("material-1",))

    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await fins_command._consume_fins_direct_events(stream)

    assert captured.value is owner_error
    assert captured.value.reason is FinsDirectStreamProtocolErrorKind.EVENT_AFTER_RESULT
    assert captured.value.operation_kind is FinsOperationKind.PREPROCESS


def test_stream_failure_propagates_to_cli_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """stream 异常必须转为 CLI failure，不伪造成 terminal fallback。"""

    service = _FakeFinsDirectService(
        events=(_progress_event(FinsOperationKind.DOWNLOAD),),
        stream_error=RuntimeError("stream boom"),
    )
    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            service,
        ),
    )

    assert cli_main.main(("download", "--ticker", "AAPL")) == EXIT_FAILURE

    captured = capsys.readouterr()
    assert captured.err == _UNKNOWN_DIRECT_FAILURE_STDERR
    assert "stream boom" not in captured.err
    assert "job_id" not in captured.err
    assert service.closed_streams == 1


def test_unknown_fins_direct_failure_logs_traceback_and_hides_exception_from_stderr(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """未知 direct 异常只进入 operator traceback，普通 stderr 使用固定文案。

    Args:
        monkeypatch: direct async 主流程异常注入夹具。
        caplog: operator 日志捕获夹具。
        capsys: 标准流捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: stderr 泄漏异常或 operator 日志缺少 traceback 时抛出。
    """

    monkeypatch.setattr(
        fins_command,
        "_run_fins_direct_command_async",
        _raise_unknown_fins_direct_error,
    )
    caplog.set_level(logging.ERROR, logger=fins_command.__name__)

    exit_code = fins_command.run_fins_direct_command(parse_cli_args(("download", "--ticker", "AAPL")))

    captured = capsys.readouterr()
    assert exit_code == EXIT_FAILURE
    assert captured.out == ""
    assert captured.err == _UNKNOWN_DIRECT_FAILURE_STDERR
    assert _UNKNOWN_DIRECT_FAILURE_MARKER not in captured.err
    assert "/absolute/path" not in captured.err
    assert "Traceback" not in captured.err
    assert "RuntimeError" not in captured.err
    assert "Fins direct command failed; command=download" in caplog.text
    assert _UNKNOWN_DIRECT_FAILURE_MARKER in caplog.text
    assert "Traceback" in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.parametrize(
    ("summary", "expected_stream"),
    (
        (
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status="ok",
                requested_file_count=2,
                stored_file_count=2,
            ),
            "stdout",
        ),
        (
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status="deleted",
                requested_file_count=0,
                stored_file_count=0,
            ),
            "stdout",
        ),
        (
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status="skipped",
                requested_file_count=2,
                stored_file_count=0,
            ),
            "stdout",
        ),
        (
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status="failed",
                requested_file_count=2,
                stored_file_count=0,
                failure_reason=fins_upload_failure_from_exception(
                    RuntimeError(),
                    file_label=None,
                ),
            ),
            "stderr",
        ),
    ),
)
def test_upload_terminal_summary_renderer_uses_typed_requested_and_stored_counts(
    summary: FinsUploadResultSummary,
    expected_stream: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI renderer 必须展示 typed upload summary 的 requested/stored 真源。

    Args:
        summary: production upload summary owner 构造的当前终态。
        expected_stream: 当前终态应写入的标准流名称。
        tmp_path: filing validator 使用的临时输入目录。
        capsys: 标准流捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: typed RESULT 到 CLI 摘要的计数或字段名投影漂移时抛出。
    """

    input_files = tuple(tmp_path / f"input-{index}.pdf" for index in range(summary.requested_file_count))
    for input_file in input_files:
        input_file.write_bytes(b"typed filing input")
    raw_request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="delete" if summary.status == "deleted" else "create",
        files=input_files,
        fiscal_year=2024,
        fiscal_period="FY",
        company_name=None if summary.status == "deleted" else "Apple Inc.",
    )
    published_state = FilingUploadPublishedState(company_meta=None, source_meta=None)
    request = validate_fins_upload_filing_request(
        raw_request,
        published_state=published_state,
    )
    context = ingestion_runtime._FinsIngestionExecutionContext(
        operation_kind=FinsIngestionOperationKind.UPLOAD,
        direct_operation_kind=FinsOperationKind.UPLOAD_FILING,
        normalized_ticker=request.normalized_ticker.canonical,
        market=request.normalized_ticker.market,
        exchange=request.normalized_ticker.exchange,
        source=None,
        source_kind=request.request.source_kind,
        download_request=None,
        cancellation_checker=_NEVER_CANCELLED_JOB_CHECKER,
        job_record=None,
        direct_queue=None,
        cancellation_state=None,
    )
    _progress_event_value, result_event = ingestion_runtime._direct_upload_terminal_events(
        context=context,
        request=request,
        summary=summary,
        disposition=summary.terminal_disposition(),
        emitted_at=_NOW,
    )

    cli_output.render_fins_direct_event(result_event)

    captured = capsys.readouterr()
    rendered = captured.out if expected_stream == "stdout" else captured.err
    other_stream = captured.err if expected_stream == "stdout" else captured.out
    assert f'requested_files="{summary.requested_file_count}"' in rendered
    assert f'stored_files="{summary.stored_file_count}"' in rendered
    assert "uploaded_files" not in rendered
    assert other_stream == ""


@pytest.mark.parametrize(
    "consumer_name",
    ("_log_fins_direct_event_received", "render_fins_direct_event"),
)
@pytest.mark.asyncio
async def test_cli_stream_owner_preserves_consumer_error_and_cleanup_cause(
    consumer_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """log/render 失败时 CLI owner 必须确定性关闭并保持 primary/cause。

    :param consumer_name: 本次注入失败的 CLI consumer 函数名。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 异常身份、cleanup cause 或关闭次数不符合契约时抛出。
    """

    primary_error = RuntimeError(f"{consumer_name} failed")
    close_error = OSError("raw generator close failed")
    service = _FakeFinsDirectService(close_error=close_error)
    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            service,
        ),
    )
    monkeypatch.setattr(
        fins_command,
        consumer_name,
        partial(_raise_cli_consumer_error, error=primary_error),
    )

    with pytest.raises(RuntimeError) as captured:
        await fins_command._run_fins_direct_command_async(parse_cli_args(("download", "--ticker", "AAPL")))

    assert captured.value is primary_error
    assert captured.value.__cause__ is close_error
    assert service.closed_streams == 1
    assert len(service.opened_streams) == 1
    with pytest.raises(StopAsyncIteration):
        await anext(service.opened_streams[0])


@pytest.mark.asyncio
async def test_cli_stream_owner_external_cancellation_closes_once_with_cleanup_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """外部 task cancellation 必须等待 consumer 清理并关闭 raw generator 一次。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 取消、cleanup cause 或关闭次数不符合契约时抛出。
    """

    close_error = OSError("raw generator close failed")
    service = _FakeFinsDirectService(
        close_error=close_error,
        pause_after_first_event=True,
    )
    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            service,
        ),
    )
    command_task = asyncio.create_task(
        fins_command._run_fins_direct_command_async(parse_cli_args(("download", "--ticker", "AAPL")))
    )
    await service.first_event_yielded.wait()

    command_task.cancel("external cancellation")
    with pytest.raises(asyncio.CancelledError) as captured:
        await command_task

    assert captured.value.__cause__ is close_error
    assert service.closed_streams == 1


@pytest.mark.asyncio
async def test_cli_event_task_drain_keeps_close_cause_when_child_already_done() -> None:
    """child 已完成的取消竞态仍必须把 raw close failure 交给 creator owner。

    :returns: ``None``。
    :raises AssertionError: completed task 的 cleanup cause 或关闭次数丢失时抛出。
    """

    close_error = OSError("raw generator close failed")
    primary_error = asyncio.CancelledError("external cancellation")
    service = _FakeFinsDirectService(
        close_error=close_error,
        pause_after_first_event=True,
    )
    event_task = asyncio.create_task(
        fins_command._consume_fins_direct_events(service.download(build_fins_download_request(ticker="AAPL")))
    )
    await service.first_event_yielded.wait()
    event_task.cancel()
    await asyncio.sleep(0)
    assert event_task.done()

    cleanup_error = await fins_command._cancel_and_drain_fins_event_task(
        event_task,
        primary_error=primary_error,
    )

    assert cleanup_error is close_error
    assert service.closed_streams == 1


@pytest.mark.asyncio
async def test_cli_event_task_drain_deduplicates_same_primary_close_cause() -> None:
    """child cleanup cause 已是 primary 时不得返回同一对象形成 self-cause。

    :returns: ``None``。
    :raises AssertionError: completed task 的同一 cleanup cause 未去重时抛出。
    """

    close_error = OSError("raw generator close failed")
    service = _FakeFinsDirectService(
        close_error=close_error,
        pause_after_first_event=True,
    )
    event_task = asyncio.create_task(
        fins_command._consume_fins_direct_events(service.download(build_fins_download_request(ticker="AAPL")))
    )
    await service.first_event_yielded.wait()
    event_task.cancel()
    await asyncio.sleep(0)
    assert event_task.done()

    cleanup_error = await fins_command._cancel_and_drain_fins_event_task(
        event_task,
        primary_error=close_error,
    )

    assert cleanup_error is None
    assert close_error.__cause__ is None
    assert close_error.__context__ is None
    assert service.closed_streams == 1


@pytest.mark.asyncio
async def test_cli_stream_owner_sigint_waits_for_canonical_cancelled_terminal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SIGINT 只请求 token，退出码必须来自 canonical cancelled terminal。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: canonical 退出码、取消或关闭次数不符合契约时抛出。
    """

    service = _FakeFinsDirectService(
        events=(
            _progress_event(FinsOperationKind.DOWNLOAD),
            _result_event(status=FinsResultStatus.CANCELLED),
        ),
        pause_after_first_event=True,
    )
    monitor = _ObservedCliSigintMonitor()
    token = _ObservedCliCancellationToken()
    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            service,
        ),
    )
    monkeypatch.setattr(fins_command, "CliSigintMonitor", lambda: monitor)
    monkeypatch.setattr(fins_command, "_CliFinsCancellationToken", lambda: token)
    command_task = asyncio.create_task(
        fins_command._run_fins_direct_command_async(parse_cli_args(("download", "--ticker", "AAPL")))
    )
    await service.first_event_yielded.wait()

    monitor.notify()
    assert await asyncio.wait_for(monitor.observed_counts.get(), timeout=1.0) == 1
    await asyncio.wait_for(token.requested.wait(), timeout=1.0)
    assert token.request_count == 1
    assert not command_task.done()
    monitor.notify()
    assert await asyncio.wait_for(monitor.observed_counts.get(), timeout=1.0) == 2
    assert token.request_count == 1
    service.release_stream.set()
    exit_code = await command_task
    captured = capsys.readouterr()

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert service.cancellation_tokens[0] is not None
    assert service.cancellation_tokens[0].is_cancelled()
    assert service.closed_streams == 1
    assert "download live progress" in captured.out
    assert "Fins cancelled" in captured.err


@pytest.mark.asyncio
async def test_cli_stream_owner_sigint_close_failure_propagates_without_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SIGINT request-and-wait 期间的 raw close 失败应原样传播。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: close error 身份或关闭次数不符合契约时抛出。
    """

    close_error = OSError("raw generator close failed")
    service = _FakeFinsDirectService(
        events=(
            _progress_event(FinsOperationKind.DOWNLOAD),
            _result_event(status=FinsResultStatus.CANCELLED),
        ),
        close_error=close_error,
        pause_after_first_event=True,
    )
    monitor = CliSigintMonitor()
    token = _ObservedCliCancellationToken()
    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            service,
        ),
    )
    monkeypatch.setattr(fins_command, "CliSigintMonitor", lambda: monitor)
    monkeypatch.setattr(fins_command, "_CliFinsCancellationToken", lambda: token)
    command_task = asyncio.create_task(
        fins_command._run_fins_direct_command_async(parse_cli_args(("download", "--ticker", "AAPL")))
    )
    await service.first_event_yielded.wait()

    monitor.notify()
    await asyncio.wait_for(token.requested.wait(), timeout=1.0)
    service.release_stream.set()
    with pytest.raises(OSError) as captured:
        await command_task

    assert captured.value is close_error
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert service.closed_streams == 1


@pytest.mark.asyncio
async def test_sigint_requests_token_and_waits_without_job_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """第一次 SIGINT 只请求 token 并等待 Fins owner 终态。"""

    service = _FakeFinsDirectService(
        events=(
            _progress_event(FinsOperationKind.DOWNLOAD),
            _result_event(status=FinsResultStatus.CANCELLED),
        ),
        pause_after_first_event=True,
    )
    token = _ObservedCliCancellationToken()
    monitor = _ObservedCliSigintMonitor()

    wait_task = asyncio.create_task(
        fins_command._wait_for_terminal_handling_sigint(
            events=service.download(
                build_fins_download_request(ticker="AAPL"),
                cancellation_token=token,
            ),
            cancellation_token=token,
            sigint_monitor=monitor,
            command_name="download",
        )
    )
    await service.first_event_yielded.wait()
    monitor.notify()
    assert await asyncio.wait_for(monitor.observed_counts.get(), timeout=1.0) == 1
    await asyncio.wait_for(token.requested.wait(), timeout=1.0)
    assert not wait_task.done()
    monitor.notify()
    assert await asyncio.wait_for(monitor.observed_counts.get(), timeout=1.0) == 2
    assert token.request_count == 1
    service.release_stream.set()

    result = await wait_task

    assert result.status is FinsResultStatus.CANCELLED
    assert result.exit_code == FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT
    assert token.is_cancelled()
    assert service.closed_streams == 1
    captured = capsys.readouterr()
    assert "Fins operation cancel requested" in captured.err
    assert "Fins cancelled" in captured.err
    assert "local process exiting" not in captured.err
    assert "job_id" not in captured.err


@pytest.mark.asyncio
async def test_cancel_race_does_not_override_terminal_result() -> None:
    """取消注入后 stream 返回 terminal RESULT 时不得覆盖最终结果。"""

    progress_delivered = asyncio.Event()
    release_terminal = asyncio.Event()

    async def terminal_stream_after_cancel() -> AsyncGenerator[FinsEvent, None]:
        """取消注入后仍返回已经形成的 terminal result。

        :returns: Fins direct event stream。
        :raises Exception: 不主动抛出异常。
        """

        progress_delivered.set()
        yield _progress_event(FinsOperationKind.DOWNLOAD)
        await release_terminal.wait()
        yield _result_event(status=FinsResultStatus.SUCCESS)

    token = _ObservedCliCancellationToken()
    monitor = CliSigintMonitor()
    stream = ValidatedFinsEventStream(
        terminal_stream_after_cancel(),
        operation_kind=FinsOperationKind.DOWNLOAD,
    )

    wait_task = asyncio.create_task(
        fins_command._wait_for_terminal_handling_sigint(
            events=stream,
            cancellation_token=token,
            sigint_monitor=monitor,
            command_name="download",
        )
    )
    await asyncio.wait_for(progress_delivered.wait(), timeout=1.0)
    monitor.notify()
    await asyncio.wait_for(token.requested.wait(), timeout=1.0)
    assert not wait_task.done()
    release_terminal.set()

    result = await wait_task

    assert isinstance(result, FinsResultSummary)
    assert result.status is FinsResultStatus.SUCCESS
    assert token.is_cancelled()


def test_keyboard_interrupt_before_stream_exits_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stream 打开前 KeyboardInterrupt 必须返回 130。"""

    class _InterruptingService(_FakeFinsDirectService):
        def download(
            self,
            request: FinsDownloadRequest,
            *,
            cancellation_token: fins_command._CliFinsCancellationToken | None = None,
        ) -> ValidatedFinsEventStream:
            """模拟打开 stream 前中断。

            :param request: 已完成静态校验的下载请求。
            :param cancellation_token: CLI operation 取消 token。
            :returns: 正常路径不会返回。
            :raises KeyboardInterrupt: 始终抛出。
            """

            del request, cancellation_token
            raise KeyboardInterrupt

    service = _InterruptingService()
    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            service,
        ),
    )

    assert cli_main.main(("download", "--ticker", "AAPL")) == EXIT_KEYBOARD_INTERRUPT
    assert service.stream_calls == []


def test_upload_file_allowlist_fail_fast(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """upload_filing 必须按 primary 角色在 Service 前拒绝非法格式。

    Args:
        tmp_path: 用于创建非法 primary 文件的临时目录。
        fake_service: 记录 direct Service 调用的替身。
        capsys: 标准输出与错误输出捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: 角色错误投影或 fail-fast 边界漂移时抛出。
    """

    disallowed = tmp_path / "filing.exe"
    disallowed.write_text("bad", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--ticker",
            "AAPL",
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            "FY",
            "--company-name",
            "Apple Inc.",
            "--files",
            str(disallowed),
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert captured.err == "dayu-cli upload_filing: 财报主文件格式不受支持：filing.exe\n"
    assert fake_service.upload_filing_requests == []


@pytest.mark.parametrize(
    "suffix",
    (
        ".pdf",
        ".docx",
        ".pptx",
        ".htm",
        ".html",
        ".xhtml",
        ".md",
        ".txt",
        ".csv",
        ".xlsx",
        ".xbrl",
        ".xml",
        ".json",
    ),
)
def test_upload_filings_from_does_not_start_live_stream(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
    suffix: str,
) -> None:
    """13 个冻结 primary suffix 必须各自产生 standalone filing 命令。

    Args:
        tmp_path: 用于创建单格式 source 与 workspace 的临时目录。
        fake_service: 记录 direct Service 调用的替身。
        capsys: 标准输出与错误输出捕获夹具。
        suffix: 当前冻结 primary 扩展名。

    Returns:
        无。

    Raises:
        AssertionError: batch admission、命令生成或零 live-stream 边界漂移时抛出。
    """

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_file = source_dir / f"2024FY AAPL Annual Report{suffix}"
    source_file.write_text("filing", encoding="utf-8")

    assert (
        cli_main.main(
            (
                "upload_filings_from",
                "--base",
                str(tmp_path / "workspace"),
                "--ticker",
                "AAPL",
                "--from",
                str(source_dir),
            )
        )
        == EXIT_SUCCESS
    )

    captured = capsys.readouterr()
    script = tmp_path / "workspace" / "upload_filings_AAPL.sh"
    assert "Generated upload script:" in captured.out
    assert "Recognized filings: 1" in captured.out
    script_text = script.read_text(encoding="utf-8")
    assert "upload_filing" in script_text
    assert str(source_file.resolve()) in script_text
    assert "schema_version" not in script_text
    assert "Fins progress" not in captured.out
    assert fake_service.stream_calls == []


def test_cli_does_not_import_fins_storage_directly() -> None:
    """CLI 源码不得直接 import dayu.fins.storage。"""

    violations: list[tuple[str, str]] = []
    cli_root = Path(fins_command.__file__).resolve().parents[1]
    for file_path in sorted(cli_root.rglob("*.py")):
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "dayu.fins.storage" or alias.name.startswith("dayu.fins.storage."):
                        violations.append((str(file_path), alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None and (
                    node.module == "dayu.fins.storage" or node.module.startswith("dayu.fins.storage.")
                ):
                    violations.append((str(file_path), node.module))

    assert violations == []


@dataclass(frozen=True, slots=True)
class _ProcessCall:
    """process service call 记录。"""

    ticker: str
    source_kind: SourceKind
    document_ids: tuple[str, ...]
    form_types: tuple[str, ...]
    rebuild_processed: bool


@dataclass(frozen=True, slots=True)
class _ProcessSpecificCall:
    """process_filing/material service call 记录。"""

    ticker: str
    document_ids: tuple[str, ...]
    form_types: tuple[str, ...]
    rebuild_processed: bool


@dataclass(frozen=True, slots=True)
class _UploadFilingCall:
    """upload_filing service call 记录。"""

    ticker: str
    action: str
    files: tuple[Path, ...]
    fiscal_year: int | None
    fiscal_period: str | None
    amended: bool
    filing_date: str | None
    report_date: str | None
    company_name: str | None
    ticker_aliases: tuple[str, ...]
    overwrite: bool


@dataclass(frozen=True, slots=True)
class _UploadMaterialCall:
    """upload_material service call 记录。"""

    ticker: str
    action: str
    files: tuple[Path, ...]
    form_type: str | None
    material_name: str | None
    document_id: str | None
    internal_document_id: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    amended: bool
    filing_date: str | None
    report_date: str | None
    company_name: str | None
    ticker_aliases: tuple[str, ...]
    overwrite: bool


def _live_command_argv(command_name: str, tmp_path: Path) -> tuple[str, ...]:
    """构造 live command 参数。

    :param command_name: 用户可见命令名。
    :param tmp_path: pytest 临时目录。
    :returns: CLI argv。
    :raises ValueError: 未知命令名时抛出。
    """

    if command_name == "download":
        return ("download", "--ticker", "AAPL", "--forms", "10-K")
    if command_name == "process":
        return ("process", "--ticker", "AAPL", "--document-id", "doc-1")
    if command_name == "process_filing":
        return ("process_filing", "--ticker", "AAPL", "--document-id", "doc-1")
    if command_name == "process_material":
        return ("process_material", "--ticker", "AAPL", "--document-id", "doc-1")
    if command_name == "upload_filing":
        upload_file = tmp_path / "filing.pdf"
        upload_file.write_text("filing", encoding="utf-8")
        return (
            "upload_filing",
            "--ticker",
            "AAPL",
            "--files",
            str(upload_file),
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            "FY",
            "--company-name",
            "Apple Inc.",
        )
    if command_name == "upload_material":
        upload_file = tmp_path / "material.pdf"
        upload_file.write_text("material", encoding="utf-8")
        return ("upload_material", "--ticker", "AAPL", "--files", str(upload_file))
    raise ValueError(f"unknown live command: {command_name}")


def _redirect_default_log_file(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """把 CLI 默认日志文件重定向到 pytest 临时目录。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: pytest 临时目录。
    :returns: 默认日志文件路径。
    :raises Exception: 不主动抛出异常。
    """

    log_file = tmp_path / "dayu-default.log"

    def open_default_log_file() -> TextIO:
        """打开测试用默认日志文件。

        :returns: 已打开的日志文件流。
        :raises OSError: 文件打开失败时由 ``open`` 透传。
        """

        return open(log_file, mode="a", encoding="utf-8")

    monkeypatch.setattr(cli_main, "_open_default_log_file", open_default_log_file)
    return log_file


def _progress_event(operation_kind: FinsOperationKind) -> FinsEvent:
    """构造 fake progress event。

    :param operation_kind: 操作类型。
    :returns: fake progress event。
    :raises ValueError: 事件违反 direct contract 时抛出。
    """

    return FinsEvent(
        event_type=FinsEventType.PROGRESS,
        operation_kind=operation_kind,
        message="download live progress",
        emitted_at=_NOW,
        ticker="AAPL",
        filing_kind="10-K",
        document_label="AAPL 10-K FY2024",
        progress=FinsProgress(stage="download", completed_units=1, total_units=2),
        result=None,
    )


def _empty_progress_event() -> FinsEvent:
    """构造没有额外诊断字段的 fake progress event。

    :returns: fake progress event。
    :raises ValueError: 事件违反 direct contract 时抛出。
    """

    return FinsEvent(
        event_type=FinsEventType.PROGRESS,
        operation_kind=FinsOperationKind.DOWNLOAD,
        message="progress tick",
        emitted_at=_NOW,
        ticker=None,
        filing_kind=None,
        document_label=None,
        progress=FinsProgress(stage="poll", completed_units=None, total_units=None),
        result=None,
    )


def _result_event(
    *,
    status: FinsResultStatus = FinsResultStatus.SUCCESS,
) -> FinsEvent:
    """构造 fake result event。

    :param status: result status。
    :returns: fake result event。
    :raises ValueError: 事件违反 direct contract 时抛出。
    """

    if status is FinsResultStatus.SUCCESS:
        exit_code = FINS_DIRECT_EXIT_SUCCESS
        error_kind = None
        error_message = None
    elif status is FinsResultStatus.CANCELLED:
        exit_code = FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT
        error_kind = FinsErrorKind.CANCELLED
        error_message = "cancelled"
    else:
        exit_code = FINS_DIRECT_EXIT_FAILURE
        error_kind = FinsErrorKind.EXECUTION
        error_message = "failed"
    return FinsEvent(
        event_type=FinsEventType.RESULT,
        operation_kind=FinsOperationKind.DOWNLOAD,
        message="download finished",
        emitted_at=_NOW,
        ticker="AAPL",
        filing_kind="10-K",
        document_label="AAPL 10-K FY2024",
        progress=None,
        result=FinsResultSummary(
            status=status,
            exit_code=exit_code,
            title="Download finished",
            details=(FinsEventDetail(label="processed_count", value="1"),),
            error_kind=error_kind,
            error_message=error_message,
        ),
    )
