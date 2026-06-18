"""``dayu-cli`` Fins direct commands 测试。"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO, cast

import pytest

import dayu.cli.commands.fins as fins_command
import dayu.cli.main as cli_main
import dayu.cli.output as cli_output
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.fins.direct_events import (
    FinsErrorKind,
    FinsEvent,
    FinsEventDetail,
    FinsEventType,
    FinsOperationKind,
    FinsProgress,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.fins.domain.enums import SourceKind
from dayu.service.fins_direct import (
    FINS_DIRECT_EXIT_FAILURE,
    FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT,
    FINS_DIRECT_EXIT_SUCCESS,
)

_NOW: datetime = datetime(2026, 6, 16, tzinfo=timezone.utc)


class _FakeFinsDirectService:
    """CLI 测试用 FinsDirectCommandService 替身。"""

    download_requests: list[_DownloadCall]
    process_requests: list[_ProcessCall]
    process_filing_requests: list[_ProcessSpecificCall]
    process_material_requests: list[_ProcessSpecificCall]
    upload_filing_requests: list[_UploadFilingCall]
    upload_material_requests: list[_UploadMaterialCall]
    events: tuple[FinsEvent, ...]
    stream_error: Exception | None
    stream_calls: list[FinsOperationKind]
    cancellation_tokens: list[fins_command._CliFinsCancellationToken | None]
    first_event_yielded: asyncio.Event
    release_stream: asyncio.Event
    pause_after_first_event: bool
    closed_streams: int

    def __init__(
        self,
        *,
        events: tuple[FinsEvent, ...] | None = None,
        stream_error: Exception | None = None,
        pause_after_first_event: bool = False,
    ) -> None:
        """初始化 fake service。

        :param events: stream 需要产出的事件；为空时使用 progress + success。
        :param stream_error: 可选 stream 末尾异常。
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
        self.events = (
            (_progress_event(FinsOperationKind.DOWNLOAD), _result_event())
            if events is None
            else events
        )
        self.stream_error = stream_error
        self.stream_calls = []
        self.cancellation_tokens = []
        self.first_event_yielded = asyncio.Event()
        self.release_stream = asyncio.Event()
        self.pause_after_first_event = pause_after_first_event
        self.closed_streams = 0

    def download(
        self,
        *,
        ticker: str,
        form_types: tuple[str, ...] = (),
        filed_after: str | None = None,
        filed_before: str | None = None,
        overwrite_existing: bool = False,
        rebuild_processed: bool = False,
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> AsyncIterator[FinsEvent]:
        """记录 download 参数并返回 fake stream。

        :param ticker: canonical ticker。
        :param form_types: 表单过滤条件。
        :param filed_after: 最早 filing 日期。
        :param filed_before: 最晚 filing 日期。
        :param overwrite_existing: 是否覆盖已有文档。
        :param rebuild_processed: 是否重建 processed 产物。
        :param cancellation_token: CLI operation 取消 token。
        :returns: Fins direct event stream。
        :raises Exception: 不主动抛出异常。
        """

        self.download_requests.append(
            _DownloadCall(
                ticker=ticker,
                form_types=form_types,
                filed_after=filed_after,
                filed_before=filed_before,
                overwrite_existing=overwrite_existing,
                rebuild_processed=rebuild_processed,
            )
        )
        return self._stream(FinsOperationKind.DOWNLOAD, cancellation_token)

    def process(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> AsyncIterator[FinsEvent]:
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
        return self._stream(FinsOperationKind.PREPROCESS, cancellation_token)

    def process_filing(
        self,
        *,
        ticker: str,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> AsyncIterator[FinsEvent]:
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
        return self._stream(FinsOperationKind.PROCESS_FILING, cancellation_token)

    def process_material(
        self,
        *,
        ticker: str,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> AsyncIterator[FinsEvent]:
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
        return self._stream(FinsOperationKind.PROCESS_MATERIAL, cancellation_token)

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
    ) -> AsyncIterator[FinsEvent]:
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
        return self._stream(FinsOperationKind.UPLOAD_FILING, cancellation_token)

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
    ) -> AsyncIterator[FinsEvent]:
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
        return self._stream(FinsOperationKind.UPLOAD_MATERIAL, cancellation_token)

    async def _stream(
        self,
        operation_kind: FinsOperationKind,
        cancellation_token: fins_command._CliFinsCancellationToken | None,
    ) -> AsyncIterator[FinsEvent]:
        """产出 fake stream。

        :param operation_kind: 当前操作类型。
        :param cancellation_token: CLI operation 取消 token。
        :returns: Fins direct event stream。
        :raises Exception: stream_error 不为空时在事件后抛出。
        """

        self.stream_calls.append(operation_kind)
        self.cancellation_tokens.append(cancellation_token)
        try:
            for index, event in enumerate(self.events):
                yield event
                if index == 0:
                    self.first_event_yielded.set()
                    if self.pause_after_first_event:
                        await self.release_stream.wait()
            if self.stream_error is not None:
                raise self.stream_error
        finally:
            self.closed_streams += 1


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
    assert "message=\"download live progress\"" in captured.out
    assert "Fins succeeded" in captured.out
    assert "processed_count=\"1\"" in captured.out
    assert "Fins direct event received" not in captured.out
    assert "Fins direct event detail" not in captured.out
    assert captured.err == ""


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

    exit_code = cli_main.main(
        ("download", "--ticker", "AAPL", "--log-file", str(log_file))
    )

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
            "AAPL,Apple Inc.",
            "--forms",
            "10-K,10-Q",
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
        _DownloadCall(
            ticker="AAPL",
            form_types=("10-K", "10-Q"),
            filed_after="2024-01-01",
            filed_before="2024-12-31",
            overwrite_existing=True,
            rebuild_processed=True,
        )
    ]


def test_upload_commands_map_args_and_validate_files(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
) -> None:
    """upload_filing/material CLI 必须调用 Service direct stream 方法。"""

    filing_file = tmp_path / "filing.pdf"
    material_file = tmp_path / "material.html"
    filing_file.write_text("filing", encoding="utf-8")
    material_file.write_text("<html></html>", encoding="utf-8")

    assert cli_main.main(
        (
            "upload_filing",
            "--ticker",
            "AAPL,Apple Inc.",
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
    ) == EXIT_SUCCESS
    assert cli_main.main(
        (
            "upload_material",
            "--ticker",
            "MSFT,Microsoft",
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
    ) == EXIT_SUCCESS

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
            ticker_aliases=("Apple Inc.",),
            overwrite=True,
        )
    ]
    assert fake_service.upload_material_requests == [
        _UploadMaterialCall(
            ticker="MSFT",
            action="create",
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
            ticker_aliases=("Microsoft",),
            overwrite=False,
        )
    ]


def test_process_commands_map_to_service(
    fake_service: _FakeFinsDirectService,
) -> None:
    """process / process_filing / process_material 必须映射到 direct stream 方法。"""

    assert cli_main.main(
        (
            "process",
            "--ticker",
            "AAPL,Apple",
            "--document-id",
            "doc-1,doc-2",
            "--document-id",
            "doc-3",
            "--overwrite",
        )
    ) == EXIT_SUCCESS
    assert cli_main.main(
        ("process_filing", "--ticker", "AAPL", "--document-id", "filing-1")
    ) == EXIT_SUCCESS
    assert cli_main.main(
        ("process_material", "--ticker", "AAPL", "--document-id", "material-1")
    ) == EXIT_SUCCESS

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
def test_unsupported_flags_fail_fast(
    argv: tuple[str, ...],
    fake_service: _FakeFinsDirectService,
) -> None:
    """--infer 和 --ci 必须 fail fast。"""

    exit_code = cli_main.main(argv)

    assert exit_code == EXIT_USAGE_ERROR
    assert fake_service.stream_calls == []


def test_terminal_failed_and_cancelled_status_exit_mapping(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI 必须使用 FinsResultSummary 的退出码映射。"""

    failed_service = _FakeFinsDirectService(
        events=(_result_event(status=FinsResultStatus.FAILURE),)
    )
    cancelled_service = _FakeFinsDirectService(
        events=(_result_event(status=FinsResultStatus.CANCELLED),)
    )

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


def test_stream_without_result_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """direct stream 无 RESULT 时 CLI 必须失败收口。"""

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
    assert "Fins failure" in captured.err
    assert "ended without result" in captured.err


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


@pytest.mark.asyncio
async def test_sigint_cancels_stream_task_without_job_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """第一次 SIGINT 必须取消当前 stream task，不调用 job cancel 语义。"""

    service = _FakeFinsDirectService(
        events=(_progress_event(FinsOperationKind.DOWNLOAD), _result_event()),
        pause_after_first_event=True,
    )
    token = fins_command._CliFinsCancellationToken()
    monitor = fins_command._FinsSigintMonitor()

    wait_task = asyncio.create_task(
        fins_command._wait_for_terminal_handling_sigint(
            events=service.download(ticker="AAPL", cancellation_token=token),
            cancellation_token=token,
            sigint_monitor=monitor,
            command_name="download",
        )
    )
    await service.first_event_yielded.wait()
    monitor.notify()

    result = await wait_task

    assert result.status is FinsResultStatus.CANCELLED
    assert result.exit_code == FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT
    assert token.is_cancelled()
    assert service.closed_streams == 1
    captured = capsys.readouterr()
    assert "Fins operation cancel requested" in captured.err
    assert "job_id" not in captured.err


@pytest.mark.asyncio
async def test_cancel_race_does_not_override_terminal_result() -> None:
    """取消注入后 stream 返回 terminal RESULT 时不得覆盖最终结果。"""

    async def terminal_stream_after_cancel() -> AsyncIterator[FinsEvent]:
        """取消注入后仍返回已经形成的 terminal result。

        :returns: Fins direct event stream。
        :raises asyncio.CancelledError: 测试失败路径中透传取消。
        """

        yield _progress_event(FinsOperationKind.DOWNLOAD)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            yield _result_event(status=FinsResultStatus.SUCCESS)
            return

        yield _result_event(status=FinsResultStatus.SUCCESS)

    token = fins_command._CliFinsCancellationToken()
    monitor = fins_command._FinsSigintMonitor()

    wait_task = asyncio.create_task(
        fins_command._wait_for_terminal_handling_sigint(
            events=terminal_stream_after_cancel(),
            cancellation_token=token,
            sigint_monitor=monitor,
            command_name="download",
        )
    )
    await asyncio.sleep(0)
    monitor.notify()

    result = await wait_task

    assert result.status is FinsResultStatus.SUCCESS
    assert token.is_cancelled()


def test_keyboard_interrupt_before_stream_exits_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stream 打开前 KeyboardInterrupt 必须返回 130。"""

    class _InterruptingService(_FakeFinsDirectService):
        def download(
            self,
            *,
            ticker: str,
            form_types: tuple[str, ...] = (),
            filed_after: str | None = None,
            filed_before: str | None = None,
            overwrite_existing: bool = False,
            rebuild_processed: bool = False,
            cancellation_token: fins_command._CliFinsCancellationToken | None = None,
        ) -> AsyncIterator[FinsEvent]:
            """模拟打开 stream 前中断。

            :param ticker: canonical ticker。
            :param form_types: 表单过滤条件。
            :param filed_after: 最早 filing 日期。
            :param filed_before: 最晚 filing 日期。
            :param overwrite_existing: 是否覆盖已有文档。
            :param rebuild_processed: 是否重建 processed 产物。
            :param cancellation_token: CLI operation 取消 token。
            :returns: 正常路径不会返回。
            :raises KeyboardInterrupt: 始终抛出。
            """

            del ticker, form_types, filed_after, filed_before
            del overwrite_existing, rebuild_processed, cancellation_token
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
    """upload_filings_from 只生成脚本，不启动 Fins direct stream。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "AAPL 10-K 2024.pdf").write_text("filing", encoding="utf-8")

    assert cli_main.main(
        ("upload_filings_from", "--ticker", "AAPL", "--from", str(source_dir))
    ) == EXIT_SUCCESS

    captured = capsys.readouterr()
    assert "dayu-cli upload_filing" in captured.out
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
                    if alias.name == "dayu.fins.storage" or alias.name.startswith(
                        "dayu.fins.storage."
                    ):
                        violations.append((str(file_path), alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None and (
                    node.module == "dayu.fins.storage"
                    or node.module.startswith("dayu.fins.storage.")
                ):
                    violations.append((str(file_path), node.module))

    assert violations == []


@dataclass(frozen=True, slots=True)
class _DownloadCall:
    """download service call 记录。"""

    ticker: str
    form_types: tuple[str, ...]
    filed_after: str | None
    filed_before: str | None
    overwrite_existing: bool
    rebuild_processed: bool


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
