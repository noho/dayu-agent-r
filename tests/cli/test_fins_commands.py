"""``dayu-cli`` Fins direct commands 测试。"""

from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

import dayu.cli.commands.fins as fins_command
import dayu.cli.main as cli_main
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import FinsIngestionJobStatus
from dayu.service.fins_direct import (
    FINS_DIRECT_EXIT_FAILURE,
    FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT,
    FINS_DIRECT_EXIT_SUCCESS,
    FinsDirectJobHandle,
    FinsDirectStartRequest,
    FinsDirectTerminalResult,
)


class _FakeFinsDirectService:
    """CLI 测试用 FinsDirectCommandService 替身。"""

    download_requests: list[_DownloadCall]
    preprocess_requests: list[_PreprocessCall]
    upload_filing_requests: list[_UploadFilingCall]
    upload_material_requests: list[_UploadMaterialCall]
    cancel_requests: list[str]
    wait_started: asyncio.Event
    cancel_seen: asyncio.Event
    terminal_status: FinsIngestionJobStatus
    wait_for_cancel_before_terminal: bool

    def __init__(
        self,
        *,
        terminal_status: FinsIngestionJobStatus = FinsIngestionJobStatus.SUCCEEDED,
        wait_for_cancel_before_terminal: bool = False,
    ) -> None:
        """初始化 fake service。

        :param terminal_status: wait_for_terminal 返回的终态。
        :param wait_for_cancel_before_terminal: 是否等待 request_cancel 后才返回终态。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.download_requests = []
        self.preprocess_requests = []
        self.upload_filing_requests = []
        self.upload_material_requests = []
        self.cancel_requests = []
        self.wait_started = asyncio.Event()
        self.cancel_seen = asyncio.Event()
        self.terminal_status = terminal_status
        self.wait_for_cancel_before_terminal = wait_for_cancel_before_terminal

    def start_download(
        self,
        *,
        ticker: str,
        form_types: tuple[str, ...] = (),
        filed_after: str | None = None,
        filed_before: str | None = None,
        overwrite_existing: bool = False,
        rebuild_processed: bool = False,
    ) -> FinsDirectJobHandle:
        """记录 download start 参数。

        :param ticker: canonical ticker。
        :param form_types: 表单过滤条件。
        :param filed_after: 最早 filing 日期。
        :param filed_before: 最晚 filing 日期。
        :param overwrite_existing: 是否覆盖已有文档。
        :param rebuild_processed: 是否重建 processed 产物。
        :returns: fake job handle。
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
        return _handle(command_name="download", ticker=ticker)

    def start_preprocess(
        self,
        *,
        command_name: str,
        ticker: str,
        source_kind: SourceKind,
        document_ids: tuple[str, ...] = (),
        form_types: tuple[str, ...] = (),
        rebuild_processed: bool = False,
    ) -> FinsDirectJobHandle:
        """记录 preprocess start 参数。

        :param command_name: 用户可见命令名。
        :param ticker: canonical ticker。
        :param source_kind: 源文档类型。
        :param document_ids: 源文档 ID。
        :param form_types: 表单过滤。
        :param rebuild_processed: 是否重建 processed 产物。
        :returns: fake job handle。
        :raises Exception: 不主动抛出异常。
        """

        self.preprocess_requests.append(
            _PreprocessCall(
                command_name=command_name,
                ticker=ticker,
                source_kind=source_kind,
                document_ids=document_ids,
                form_types=form_types,
                rebuild_processed=rebuild_processed,
            )
        )
        return _handle(command_name=command_name, ticker=ticker)

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
    ) -> FinsDirectJobHandle:
        """记录 upload_filing start 参数。

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
        :returns: fake job handle。
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
        return _handle(command_name="upload_filing", ticker=ticker)

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
    ) -> FinsDirectJobHandle:
        """记录 upload_material start 参数。

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
        :returns: fake job handle。
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
        return _handle(command_name="upload_material", ticker=ticker)

    async def wait_for_terminal(self, job_id: str) -> FinsDirectTerminalResult:
        """返回 fake terminal result。

        :param job_id: Fins ingestion job id。
        :returns: fake terminal result。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        self.wait_started.set()
        if (
            self.terminal_status is FinsIngestionJobStatus.CANCELLED
            and self.wait_for_cancel_before_terminal
        ):
            await self.cancel_seen.wait()
        return _terminal(job_id=job_id, status=self.terminal_status)

    def request_cancel(self, job_id: str) -> None:
        """记录 cancel 请求。

        :param job_id: Fins ingestion job id。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.cancel_requests.append(job_id)
        self.cancel_seen.set()


@pytest.fixture()
def fake_service(
    monkeypatch: pytest.MonkeyPatch,
) -> _FakeFinsDirectService:
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


def test_download_command_maps_args_to_service(
    fake_service: _FakeFinsDirectService,
) -> None:
    """download CLI 参数必须转换为 Service 显式方法参数。"""

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


def test_upload_filing_command_maps_args_and_validates_files(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
) -> None:
    """upload_filing CLI 必须走 Service wrapper 并传入 ticker aliases。"""

    upload_file = tmp_path / "filing.pdf"
    upload_file.write_text("filing", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--ticker",
            "AAPL,Apple Inc.",
            "--action",
            "update",
            "--files",
            str(upload_file),
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

    assert exit_code == EXIT_SUCCESS
    assert fake_service.upload_filing_requests == [
        _UploadFilingCall(
            ticker="AAPL",
            action="update",
            files=(upload_file.resolve(),),
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


def test_upload_material_command_maps_single_form(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
) -> None:
    """upload_material 当前 request 只接收单个 form_type。"""

    upload_file = tmp_path / "material.html"
    upload_file.write_text("<html></html>", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_material",
            "--ticker",
            "MSFT,Microsoft",
            "--forms",
            "8-K",
            "--material-name",
            "Investor Day",
            "--files",
            str(upload_file),
            "--document-id",
            "doc-1",
            "--internal-document-id",
            "internal-1",
        )
    )

    assert exit_code == EXIT_SUCCESS
    assert fake_service.upload_material_requests == [
        _UploadMaterialCall(
            ticker="MSFT",
            action="create",
            files=(upload_file.resolve(),),
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


def test_process_commands_map_to_preprocess_service(
    fake_service: _FakeFinsDirectService,
) -> None:
    """process / process_filing / process_material 必须映射到 preprocess。"""

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

    assert fake_service.preprocess_requests == [
        _PreprocessCall(
            command_name="process",
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            document_ids=("doc-1", "doc-2", "doc-3"),
            form_types=(),
            rebuild_processed=True,
        ),
        _PreprocessCall(
            command_name="process_filing",
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            document_ids=("filing-1",),
            form_types=(),
            rebuild_processed=False,
        ),
        _PreprocessCall(
            command_name="process_material",
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            document_ids=("material-1",),
            form_types=(),
            rebuild_processed=False,
        ),
    ]


@pytest.mark.parametrize(
    "argv",
    (
        ("download", "--ticker", "AAPL", "--infer"),
        ("process", "--ticker", "AAPL", "--ci"),
        ("upload_filings_from", "--ticker", "AAPL", "--from", "input"),
    ),
)
def test_unsupported_flags_and_s6_command_fail_fast(
    argv: tuple[str, ...],
    fake_service: _FakeFinsDirectService,
) -> None:
    """--infer、--ci 和 S6 command 执行必须 fail fast。"""

    exit_code = cli_main.main(argv)

    assert exit_code == EXIT_USAGE_ERROR
    assert fake_service.download_requests == []
    assert fake_service.preprocess_requests == []


def test_terminal_failed_and_cancelled_status_exit_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI 必须使用 Service terminal result 的退出码映射。"""

    failed_service = _FakeFinsDirectService(
        terminal_status=FinsIngestionJobStatus.FAILED
    )
    cancelled_service = _FakeFinsDirectService(
        terminal_status=FinsIngestionJobStatus.CANCELLED
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

    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        lambda _workspace_root: cast(
            fins_command.FinsDirectCommandService,
            cancelled_service,
        ),
    )
    assert cli_main.main(("download", "--ticker", "AAPL")) == EXIT_KEYBOARD_INTERRUPT


@pytest.mark.asyncio
async def test_sigint_after_job_id_requests_cancel_and_waits_terminal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """第一次 SIGINT 必须 request_cancel(job_id) 并继续等待 terminal。"""

    service = _FakeFinsDirectService(
        terminal_status=FinsIngestionJobStatus.CANCELLED,
        wait_for_cancel_before_terminal=True,
    )
    handle = _handle(command_name="download", ticker="AAPL")
    monitor = fins_command._FinsSigintMonitor()

    wait_task = asyncio.create_task(
        fins_command._wait_for_terminal_handling_sigint(
            service=cast(fins_command.FinsDirectCommandService, service),
            handle=handle,
            sigint_monitor=monitor,
        )
    )
    await service.wait_started.wait()
    monitor.notify()

    result = await wait_task

    assert result is not None
    assert result.exit_code == FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT
    assert service.cancel_requests == ["job-1"]
    assert "job-1" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_second_sigint_after_cancel_exits_locally(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """第二次 SIGINT 必须本地 130，并打印 job id。"""

    class _NeverTerminalService(_FakeFinsDirectService):
        async def wait_for_terminal(self, job_id: str) -> FinsDirectTerminalResult:
            """等待直到测试取消 task。

            :param job_id: Fins ingestion job id。
            :returns: 正常路径不会返回。
            :raises asyncio.CancelledError: 测试触发本地退出时透传。
            """

            del job_id
            self.wait_started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    service = _NeverTerminalService()
    handle = _handle(command_name="download", ticker="AAPL")
    monitor = fins_command._FinsSigintMonitor()

    wait_task = asyncio.create_task(
        fins_command._wait_for_terminal_handling_sigint(
            service=cast(fins_command.FinsDirectCommandService, service),
            handle=handle,
            sigint_monitor=monitor,
        )
    )
    await service.wait_started.wait()
    monitor.notify()
    await asyncio.sleep(0)
    monitor.notify()

    result = await wait_task

    assert result is None
    assert service.cancel_requests == ["job-1"]
    assert "job-1" in capsys.readouterr().err


def test_keyboard_interrupt_before_job_id_exits_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """job id 产生前 KeyboardInterrupt 不做 durable cancel。"""

    class _InterruptingService(_FakeFinsDirectService):
        def start_download(
            self,
            *,
            ticker: str,
            form_types: tuple[str, ...] = (),
            filed_after: str | None = None,
            filed_before: str | None = None,
            overwrite_existing: bool = False,
            rebuild_processed: bool = False,
        ) -> FinsDirectJobHandle:
            """模拟启动边界中断。

            :param ticker: canonical ticker。
            :param form_types: 表单过滤条件。
            :param filed_after: 最早 filing 日期。
            :param filed_before: 最晚 filing 日期。
            :param overwrite_existing: 是否覆盖已有文档。
            :param rebuild_processed: 是否重建 processed 产物。
            :returns: 正常路径不会返回。
            :raises KeyboardInterrupt: 始终抛出以模拟 job id 前中断。
            """

            del ticker, form_types, filed_after, filed_before
            del overwrite_existing, rebuild_processed
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
    assert service.cancel_requests == []


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
class _PreprocessCall:
    """preprocess service call 记录。"""

    command_name: str
    ticker: str
    source_kind: SourceKind
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


def _handle(*, command_name: str, ticker: str) -> FinsDirectJobHandle:
    """构造 fake direct job handle。

    :param command_name: 用户可见命令名。
    :param ticker: canonical ticker。
    :returns: fake direct job handle。
    :raises Exception: 不主动抛出异常。
    """

    return FinsDirectJobHandle(
        job_id="job-1",
        initial_status=FinsIngestionJobStatus.QUEUED,
        start_request=FinsDirectStartRequest(
            command_name=command_name,
            ticker=ticker,
        ),
    )


def _terminal(
    *,
    job_id: str,
    status: FinsIngestionJobStatus,
) -> FinsDirectTerminalResult:
    """构造 fake terminal result。

    :param job_id: Fins ingestion job id。
    :param status: Fins ingestion terminal status。
    :returns: fake terminal result。
    :raises Exception: 不主动抛出异常。
    """

    if status is FinsIngestionJobStatus.SUCCEEDED:
        exit_code = FINS_DIRECT_EXIT_SUCCESS
    elif status is FinsIngestionJobStatus.CANCELLED:
        exit_code = FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT
    else:
        exit_code = FINS_DIRECT_EXIT_FAILURE
    return FinsDirectTerminalResult(
        job_id=job_id,
        status=status,
        exit_code=exit_code,
        result_summary={},
        failure_summary={"message": "failed"} if status is FinsIngestionJobStatus.FAILED else {},
    )
