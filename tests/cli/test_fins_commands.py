"""``dayu-cli`` Fins direct commands 测试。"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import NoReturn, TextIO, cast

import pytest

import dayu.cli.commands.fins as fins_command
import dayu.cli.main as cli_main
import dayu.cli.output as cli_output
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
    FinsDownloadRequest,
    build_fins_download_request,
)
from dayu.fins.domain.enums import SourceKind
from dayu.service.fins_direct import (
    FINS_DIRECT_EXIT_FAILURE,
    FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT,
    FINS_DIRECT_EXIT_SUCCESS,
)

_NOW: datetime = datetime(2026, 6, 16, tzinfo=timezone.utc)


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
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录 upload_filing 参数并返回 fake stream。

        :param ticker: canonical ticker。
        :param action: 上传动作。
        :param files: 上传文件路径。
        :param fiscal_year: 可选会计年度。
        :param fiscal_period: 可选会计期间。
        :param amended: 是否为修订 filing。
        :param filing_date: 可选披露日期。
        :param report_date: 可选报告期日期。
        :param company_name: 可选公司名称。
        :param ticker_aliases: ticker aliases。
        :param overwrite: 是否覆盖已有文档。
        :param cancellation_token: CLI operation 取消 token。
        :returns: Fins direct event stream。
        :raises Exception: 不主动抛出异常。
        """

        self.upload_filing_requests.append(
            _UploadFilingCall(
                ticker=ticker,
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


def test_download_command_maps_args_to_service(
    fake_service: _FakeFinsDirectService,
) -> None:
    """download CLI 参数必须转换为 Service direct stream 方法参数。"""

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
            "--overwrite",
            "--rebuild",
        )
    )

    assert exit_code == EXIT_SUCCESS
    assert fake_service.download_requests == [
        build_fins_download_request(
            ticker="aapl.us",
            form_types=("10-K", "10-Q"),
            start="2024-01-01",
            end="2024-12-31",
            overwrite_existing=True,
            rebuild_local_artifacts=True,
        )
    ]


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
    assert "_parse_ticker_csv" in calls_by_function["_upload_filing_stream"]
    assert "_parse_ticker_csv" in calls_by_function["_run_upload_filings_from"]


def test_upload_commands_map_args_and_validate_files(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
) -> None:
    """upload_filing/material CLI 必须调用 Service direct stream 方法。"""

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
                "update",
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
                "MSFT,GOOG",
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
            action="update",
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
            ticker="MSFT",
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
            ticker_aliases=("GOOG",),
            overwrite=False,
        )
    ]


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
    assert "stream boom" in captured.err
    assert "job_id" not in captured.err
    assert service.closed_streams == 1


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
) -> None:
    """SIGINT 只请求 token，退出码必须来自 canonical cancelled terminal。

    :param monkeypatch: pytest monkeypatch 夹具。
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
    await asyncio.wait_for(token.requested.wait(), timeout=1.0)
    service.release_stream.set()
    exit_code = await command_task

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert service.cancellation_tokens[0] is not None
    assert service.cancellation_tokens[0].is_cancelled()
    assert service.closed_streams == 1


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
) -> None:
    """upload 文件路径只做存在性与 allowlist 前置校验。"""

    disallowed = tmp_path / "filing.exe"
    disallowed.write_text("bad", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--ticker",
            "AAPL",
            "--files",
            str(disallowed),
        )
    )

    assert exit_code == EXIT_USAGE_ERROR
    assert fake_service.upload_filing_requests == []


def test_upload_filings_from_does_not_start_live_stream(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """upload_filings_from 只生成可执行脚本，不启动 direct stream。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "2024FY AAPL Annual Report.pdf").write_text("filing", encoding="utf-8")

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
    assert "upload_filing" in script.read_text(encoding="utf-8")
    assert "schema_version" not in script.read_text(encoding="utf-8")
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
        return ("upload_filing", "--ticker", "AAPL", "--files", str(upload_file))
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
