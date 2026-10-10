"""``dayu-cli`` Fins direct commands 测试。"""

from __future__ import annotations

from tests.fins.test_download_failure_diagnostics import _download_summary, _terminal
from tests.fins.test_fins_ingestion_runtime import (
    _build_ingestion_runtime, _HoldingExecutor, _PersistedSummaryDownloadAdapter,
)

from dayu.fins.storage import FsMaterialUploadStateRepository

from dayu.fins.pipelines.docling_upload_service import build_material_ids
from dayu.fins.storage import FsCompanyMetaRepository

import ast
import asyncio
import errno
import hashlib
import io
import logging
import os
import signal
import select
import time
import json
import subprocess
import sys
from collections.abc import AsyncGenerator
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from functools import partial
from pathlib import Path
from unittest.mock import Mock
from typing import NoReturn, TextIO, cast
from dayu.runtime.interruptible_process import InterruptibleProcessHandle, InterruptibleProcessTarget

import pytest

import dayu.cli.commands.fins as fins_command
import dayu.cli.main as cli_main
import dayu.cli.output as cli_output
import dayu.fins.download_contract as download_contract
import dayu.fins.ingestion_runtime as ingestion_runtime
import dayu.fins.direct_events as direct_events
from dayu.cli.agent_entrypoint import CliSigintMonitor
from dayu.cli.arg_parsing import parse_cli_args
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.fins.company_metadata_warning import (
    COMPANY_NAME_IGNORED_WARNING_MESSAGE,
    CompanyMetadataWarning,
    CompanyMetadataWarningKind,
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
    FinsUploadMaterialRequest,
    ValidatedFinsUploadMaterialRequest,
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
    SourceIntegrityClassification,
    SourceIntegrityStatus,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.upload_failure import fins_upload_failure_from_exception
from dayu.service.fins_direct import (
    FinsDirectCommandService,
    FINS_DIRECT_EXIT_FAILURE,
    FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT,
    FINS_DIRECT_EXIT_SUCCESS,
)
from tests.fins.test_fins_ingestion_runtime import _build_real_sec_integrity_runtime
from tests.fins.test_material_upload_publication import seed_material_upload_target

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
    events: tuple[FinsEvent, ...] | None
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
        self.events = events
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
                primary_selectors=raw_request.primary_selectors,
                selected_primary=request.file_selection.primary,
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
        request: ValidatedFinsUploadMaterialRequest,
        *,
        cancellation_token: fins_command._CliFinsCancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录 CLI 传入的同一次 material 准入 handoff。

        Args:
            request: 已准入的 material 请求、选择与资产计划。
            cancellation_token: CLI operation 取消 token。

        Returns:
            Fins direct event stream。

        Raises:
            无。
        """

        raw = request.request
        self.upload_material_requests.append(
            _UploadMaterialCall(
                ticker=raw.ticker,
                action=raw.action,
                files=raw.files,
                form_type=raw.form_type,
                material_name=raw.material_name,
                document_id=raw.document_id,
                internal_document_id=request.identity.internal_document_id,
                fiscal_year=raw.fiscal_year,
                fiscal_period=raw.fiscal_period,
                amended=raw.amended,
                filing_date=raw.filing_date,
                report_date=raw.report_date,
                company_name=raw.company_name,
                ticker_aliases=raw.ticker_aliases,
                overwrite=raw.overwrite,
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
            self._raw_stream(validator_operation_kind),
            operation_kind=validator_operation_kind,
        )
        self.opened_streams.append(stream)
        return stream

    async def _raw_stream(self, operation_kind: FinsOperationKind) -> AsyncGenerator[FinsEvent, None]:
        """产出 fake raw events 并保留关闭观测。

        :param operation_kind: 默认事件的真实操作类型。
        :returns: 未校验的 Fins raw event async generator。
        :raises BaseException: stream_error 原样抛出；关闭失败保留为取消 cause 或原样抛出。
        """

        cancellation_observed = False
        try:
            events = (_progress_event(operation_kind), _result_event(operation_kind=operation_kind)) if self.events is None else self.events
            for index, event in enumerate(events):
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


def test_upload_material_file_base_rejected_before_factory_and_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 parser/main 在装配和读取缺失上传输入前拒绝普通文件 base。

    Args:
        tmp_path: 隔离路径根目录。
        capsys: 标准流捕获夹具。
        monkeypatch: 替换 Service factory 的夹具。

    Returns:
        无。

    Raises:
        AssertionError: factory 被调用或路径用法语义错误时抛出。
    """

    base = tmp_path / "base"
    base.write_bytes(b"original base")
    calls: list[Path] = []

    def forbidden_factory(path: Path) -> fins_command.FinsDirectCommandService:
        """记录不应发生的 Service 装配。

        Args:
            path: 请求的 workspace 路径。

        Returns:
            不返回。

        Raises:
            AssertionError: 一旦装配 Service 即抛出。
        """

        calls.append(path)
        raise AssertionError("base 类型错误必须先于 Service 装配")

    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", forbidden_factory)
    result = cli_main.main(
        (
            "upload_material", "--base", str(base), "--ticker", "AAPL",
            "--forms", "10-K", "--material-name", "sample", "--files",
            str(tmp_path / "missing-input.pdf"),
        )
    )
    output = capsys.readouterr()
    assert result == EXIT_USAGE_ERROR
    assert output.err == (
        "dayu-cli upload_material: --base must point to a directory; "
        "choose a directory path\n"
    )
    assert "missing-input" not in output.err
    assert calls == []
    assert base.read_bytes() == b"original base"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["base"]


@pytest.mark.parametrize("option", ("--base", "-b", "--workspace"))
def test_fins_workspace_aliases_use_one_resolved_target(
    option: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三个工作区参数别名都将同一规范化目录交给 Service。

    Args:
        option: 待验证的工作区参数别名。
        tmp_path: 隔离路径根目录。
        capsys: 标准流捕获夹具。
        monkeypatch: 替换 Service factory 的夹具。

    Returns:
        无。

    Raises:
        AssertionError: 解析结果或 CLI 退出码错误时抛出。
    """

    base = tmp_path / "workspace"
    base.mkdir()
    calls: list[Path] = []
    service = _FakeFinsDirectService()
    monkeypatch.setattr(
        fins_command, "FINS_DIRECT_SERVICE_FACTORY",
        partial(_recording_direct_service_factory, service=service, factory_calls=calls),
    )
    assert cli_main.main(("download", option, str(base), "--ticker", "AAPL")) == EXIT_SUCCESS
    capsys.readouterr()
    assert calls == [base]


def test_fins_repeated_base_uses_last_value(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重复 scalar base 的最终值决定唯一装配路径。

    Args:
        tmp_path: 隔离路径根目录。
        capsys: 标准流捕获夹具。
        monkeypatch: 替换 Service factory 的夹具。

    Returns:
        无。

    Raises:
        AssertionError: 首值被使用或装配路径错误时抛出。
    """

    invalid = tmp_path / "file"
    invalid.write_bytes(b"first")
    valid = tmp_path / "directory"
    valid.mkdir()
    calls: list[Path] = []
    monkeypatch.setattr(
        fins_command, "FINS_DIRECT_SERVICE_FACTORY",
        partial(
            _recording_direct_service_factory,
            service=_FakeFinsDirectService(),
            factory_calls=calls,
        ),
    )
    assert cli_main.main(
        ("download", "--base", str(invalid), "--base", str(valid), "--ticker", "AAPL")
    ) == EXIT_SUCCESS
    capsys.readouterr()
    assert calls == [valid]
    assert invalid.read_bytes() == b"first"


def test_fins_default_base_resolves_against_current_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """省略 base 参数时按当前 cwd 解析默认 workspace。

    Args:
        tmp_path: 隔离路径根目录。
        capsys: 标准流捕获夹具。
        monkeypatch: 切换 cwd 并替换 factory 的夹具。

    Returns:
        无。

    Raises:
        AssertionError: 默认路径或退出码错误时抛出。
    """

    monkeypatch.chdir(tmp_path)
    calls: list[Path] = []
    monkeypatch.setattr(
        fins_command, "FINS_DIRECT_SERVICE_FACTORY",
        partial(
            _recording_direct_service_factory,
            service=_FakeFinsDirectService(),
            factory_calls=calls,
        ),
    )
    assert cli_main.main(("download", "--ticker", "AAPL")) == EXIT_SUCCESS
    capsys.readouterr()
    assert calls == [tmp_path / "workspace"]


def test_real_upload_material_cli_rejects_file_base_from_this_checkout(tmp_path: Path) -> None:
    """真实子进程先证明 checkout 身份，再复验普通文件 base 的无副作用拒绝。

    Args:
        tmp_path: 子进程临时 cwd。

    Returns:
        无。

    Raises:
        AssertionError: 解释器、导入树、错误或文件快照不符合契约时抛出。
    """

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    expected_import = Path(__file__).resolve().parents[2] / "dayu" / "__init__.py"
    identity = subprocess.run(
        (
            sys.executable, "-c",
            "import dayu,pathlib,sys; print(pathlib.Path(dayu.__file__).resolve()); "
            "print(pathlib.Path(sys.executable).resolve()); print(pathlib.Path(sys.prefix).resolve())",
        ),
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert identity.returncode == 0, identity.stderr
    assert identity.stdout.splitlines() == [
        str(expected_import.resolve()),
        str(Path(sys.executable).resolve()),
        str(Path(sys.prefix).resolve()),
    ]

    base = tmp_path / "base"
    original = b"ordinary file base"
    base.write_bytes(original)
    before = sorted(path.name for path in tmp_path.iterdir())
    command = (
        sys.executable, "-m", "dayu.cli", "upload_material", "--base", str(base),
        "--ticker", "AAPL", "--forms", "10-K", "--material-name", "sample",
        "--files", str(tmp_path / "missing-input.pdf"),
    )
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == EXIT_USAGE_ERROR
    assert result.stderr == (
        "dayu-cli upload_material: --base must point to a directory; "
        "choose a directory path\n"
    )
    assert str(tmp_path) not in result.stderr
    assert result.stdout == ""
    assert base.read_bytes() == original
    assert sorted(path.name for path in tmp_path.iterdir()) == before

    directory = tmp_path / "directory"
    directory.mkdir()
    directory_link = tmp_path / "directory-link"
    directory_link.symlink_to(directory, target_is_directory=True)
    symlink_command = tuple(
        str(directory_link) if part == str(base) else part for part in command
    )
    symlink_result = subprocess.run(
        symlink_command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "--base must point to a directory" not in symlink_result.stderr


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
    original_name = "published.txt"
    docling_name = "published_docling.json"
    original_meta = blob_repository.store_file(
        handle,
        original_name,
        io.BytesIO(b"published"),
        batch=batch,
        content_type="text/plain",
    )
    docling_meta = blob_repository.store_file(
        handle,
        docling_name,
        io.BytesIO(b'{"schema_name":"DoclingDocument"}'),
        batch=batch,
        content_type="application/json",
    )
    source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type="10-K",
            primary_document=docling_name,
            meta={"ingest_method": "upload", "source_provider": "user_upload"},
            file_entries=[
                {
                    "name": original_name,
                    "uri": original_meta.uri,
                    "etag": original_meta.etag,
                    "last_modified": original_meta.last_modified,
                    "size": original_meta.size,
                    "content_type": original_meta.content_type,
                    "sha256": original_meta.sha256,
                    "source": "original",
                    "original_filename": original_name,
                },
                {
                    "name": docling_name,
                    "uri": docling_meta.uri,
                    "etag": docling_meta.etag,
                    "last_modified": docling_meta.last_modified,
                    "size": docling_meta.size,
                    "content_type": docling_meta.content_type,
                    "sha256": docling_meta.sha256,
                    "source": "docling",
                    "original_filename": original_name,
                    "derived_from": original_name,
                },
            ],
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
    """六个 Fins direct commands 都必须消费 direct event stream 并输出摘要。

    参数：command_name 为被测 direct 命令名；tmp_path 为隔离测试工作区；fake_service 为记录事件与请求的 Service 替身；capsys 为标准输出与错误输出捕获夹具。
    返回：无（None）。
    异常：AssertionError，既定断言或测试前提不满足时抛出。
    """

    exit_code = cli_main.main(_live_command_argv(command_name, tmp_path))

    captured = capsys.readouterr()
    assert exit_code == EXIT_SUCCESS
    assert fake_service.stream_calls
    assert "Fins progress" in captured.out
    assert 'message="download live progress"' in captured.out
    assert "Fins succeeded" in captured.out
    if command_name == "download":
        assert "downloaded=0 skipped=0 rejected=0 failed=0" in captured.out
        assert captured.out.count("Fins download diagnostics: ") == 1
    else:
        assert 'processed_count="1"' in captured.out
        assert "Fins download diagnostics: " not in captured.out
    assert "Fins direct event received" not in captured.out
    assert "Fins direct event detail" not in captured.out
    assert captured.err == ""
    assert fake_service.closed_streams == 1


@pytest.mark.parametrize(
    ("upload_status", "stored_file_count"),
    (("ok", 1), ("skipped", 0)),
)
def test_upload_filing_command_loop_preserves_summary_and_routes_warning(
    upload_status: str,
    stored_file_count: int,
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """mocked upload_filing 必须经过命令循环并保持摘要、warning 与退出码。

    Args:
        upload_status: mocked upload 终态，覆盖 uploaded 与 skipped。
        stored_file_count: 原摘要中的已发布文件数。
        tmp_path: CLI 上传文件使用的临时目录。
        fake_service: 复用 production command seam 的 direct Service 替身。
        capsys: 标准流捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: 命令循环改写退出码、stdout 摘要或 canonical warning 时抛出。
    """

    warning = CompanyMetadataWarning(
        kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
        message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
    )
    fake_service.events = (
        FinsEvent(
            event_type=FinsEventType.RESULT,
            operation_kind=FinsOperationKind.UPLOAD_FILING,
            message="操作完成",
            emitted_at=_NOW,
            ticker="AAPL",
            filing_kind=SourceKind.FILING.value,
            document_label=None,
            progress=None,
            result=FinsResultSummary(
                status=FinsResultStatus.SUCCESS,
                exit_code=FINS_DIRECT_EXIT_SUCCESS,
                title="操作完成",
                details=(
                    FinsEventDetail(label="source kind", value=SourceKind.FILING.value),
                    FinsEventDetail(label="status", value=upload_status),
                    FinsEventDetail(label="requested files", value="1"),
                    FinsEventDetail(label="stored files", value=str(stored_file_count)),
                ),
                error_kind=None,
                error_message=None,
                warnings=(warning,),
            ),
        ),
    )

    exit_code = cli_main.main(_live_command_argv("upload_filing", tmp_path))

    captured = capsys.readouterr()
    assert exit_code == EXIT_SUCCESS
    assert captured.out == (
        'Fins succeeded: operation="upload_filing" ticker="AAPL" '
        'filing_kind="filing" status="success" message="操作完成"\n'
        f'Fins summary: source_kind="filing" status="{upload_status}" '
        f'requested_files="1" stored_files="{stored_file_count}"\n'
    )
    assert captured.err == f"{COMPANY_NAME_IGNORED_WARNING_MESSAGE}\n"
    assert fake_service.stream_calls == [FinsOperationKind.UPLOAD_FILING]
    assert len(fake_service.upload_filing_requests) == 1
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

    参数：无。
    返回：无（None）。
    异常：AssertionError，既定断言或测试前提不满足时抛出。
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
            download_result=_download_summary(source=download_contract.FinsDownloadSource.SEC),
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
            "UF-FIX01-US-invalid-period-fresh",
            ("--ticker", "AAPL", "--fiscal-year", "2024", "--fiscal-period", "BANANA"),
            "--fiscal-period 仅支持 FY、H1、Q1、Q2、Q3、Q4",
        ),
        (
            "UF-024",
            ("--ticker", "600519", "--fiscal-year", "2024", "--fiscal-period", "9M"),
            "--fiscal-period 仅支持 FY、H1、Q1、Q2、Q3、Q4",
        ),
        (
            "UF-FIX01-HK-invalid-period-fresh",
            ("--ticker", "0700.HK", "--fiscal-year", "2024", "--fiscal-period", "BANANA"),
            "--fiscal-period 仅支持 FY、H1、Q1、Q2、Q3、Q4",
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
        (
            "UF-FIX07-repeated-primary",
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
                "{input}/probe.txt",
                "--primary",
                "{input}/probe.txt",
                "--primary",
                "{input}/probe.xsd",
            ),
            "--primary 只能指定一次",
        ),
        (
            "UF-FIX07-missing-multi-primary",
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
                "{input}/probe.txt",
                "{input}/probe.xsd",
            ),
            "多文件 filing 必须使用 --primary 明确指定主文件",
        ),
        (
            "UF-FIX07-primary-outside-files",
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
                "{input}/probe.txt",
                "--primary",
                "{input}/outside.txt",
            ),
            "--primary 必须精确匹配 --files 中的一个文件",
        ),
        (
            "UF-FIX07-duplicate-files",
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
                "{input}/probe.txt",
                "{input}/probe.txt",
                "--primary",
                "{input}/probe.txt",
            ),
            "--files 不能包含解析后相同的重复路径",
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
    seed_workspace = case_id in {
        "UF-S2-seeded-invalid-report-date",
        "UF-024",
    }
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
    assert "Traceback" not in captured.err
    assert factory_calls == []
    assert service.upload_filing_requests == []
    assert service.stream_calls == []
    assert _snapshot_cli_workspace_tree(workspace_root) == before_tree
    assert workspace_root.exists() is seed_workspace


@pytest.mark.parametrize(
    ("ticker", "raw_period", "expected_period"),
    (
        ("AAPL", " fy ", "FY"),
        ("600519", " q2 ", "Q2"),
        ("0700.HK", " h1 ", "H1"),
    ),
)
def test_upload_filing_canonicalizes_period_before_validated_service_handoff(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    ticker: str,
    raw_period: str,
    expected_period: str,
) -> None:
    """CLI 合法财期应由共享 owner 规范化后交给 Service。

    Args:
        tmp_path: pytest 临时目录。
        fake_service: 记录 validated request 的 direct Service 替身。
        ticker: 覆盖 US、CN 与 HK 的公司代码。
        raw_period: 携带小写与首尾空白的原始财期。
        expected_period: 期望的 canonical 财期。

    Returns:
        无。

    Raises:
        AssertionError: CLI 入口未把 owner 产出的 canonical 财期交给 Service 时抛出。
    """

    workspace_root = tmp_path / f"workspace-{ticker.replace('.', '-')}"

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--base",
            str(workspace_root),
            "--ticker",
            ticker,
            "--action",
            "delete",
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            raw_period,
        )
    )

    assert exit_code == EXIT_SUCCESS
    assert len(fake_service.upload_filing_requests) == 1
    assert fake_service.upload_filing_requests[0].fiscal_period == expected_period
    assert fake_service.stream_calls == [FinsOperationKind.UPLOAD_FILING]


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
            primary_selectors=(),
            selected_primary=input_file.resolve(),
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


def test_upload_filing_non_first_primary_is_preserved_into_validated_service_request(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
) -> None:
    """CLI 必须保留非首位 primary，并由 Fins owner 产生 authoritative selection。

    Args:
        tmp_path: 用于创建两个 filing 输入文件。
        fake_service: 记录 validated request 的 direct Service 替身。

    Returns:
        无。

    Raises:
        AssertionError: raw selector 或 validated primary 被改成首文件时抛出。
    """

    companion = tmp_path / "schema.xsd"
    primary = tmp_path / "report.pdf"
    companion.write_text("schema", encoding="utf-8")
    primary.write_text("filing", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_filing",
            "--ticker",
            "AAPL",
            "--action",
            "create",
            "--files",
            str(companion),
            str(primary),
            "--primary",
            str(primary),
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            "FY",
            "--company-name",
            "Apple Inc.",
        )
    )

    assert exit_code == EXIT_SUCCESS
    assert len(fake_service.upload_filing_requests) == 1
    call = fake_service.upload_filing_requests[0]
    assert call.files == (companion.resolve(), primary.resolve())
    assert call.primary_selectors == (primary.resolve(),)
    assert call.selected_primary == primary.resolve()


@pytest.mark.parametrize("damage", ("bad_meta", "missing_original", "missing_docling", "missing_manifest"))
@pytest.mark.parametrize("action", ("auto", "update", "delete"))
def test_upload_material_real_corruption_prevalidation_keeps_cli_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    damage: str,
    action: str,
) -> None:
    """真实损坏材料经 CLI 主入口拒绝，命令归属正确且零生命周期写入。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: factory 与生命周期零调用观测夹具。
        capsys: 标准流捕获夹具。
        damage: 已发布材料的实际损坏形态。
        action: 待执行的上传动作。

    Returns:
        无。

    Raises:
        AssertionError: 错误归属、安全投影、准入顺序或业务字节保持漂移时抛出。
    """

    workspace_root = tmp_path / "workspace"
    seed_material_upload_target(
        FinsUploadMaterialRequest(
            ticker="AAPL", action="delete", form_type="OTHER", material_name="Deck",
            company_name="Apple Inc.",
        ),
        workspace_root,
    )
    material_root = workspace_root / "portfolio" / "AAPL" / "materials"
    if damage == "bad_meta":
        paths = tuple(material_root.rglob("meta.json"))
        assert len(paths) == 1
        paths[0].write_text("{}", encoding="utf-8")
    else:
        name = (
            "seed-target.txt" if damage == "missing_original"
            else "seed-target.txt_docling.json" if damage == "missing_docling"
            else "material_manifest.json"
        )
        next(material_root.rglob(name)).unlink()
    identity = build_material_ids(
        form_type="OTHER", material_name="Deck", fiscal_year=None, fiscal_period=None, document_id=None,
    )
    state = FsMaterialUploadStateRepository(workspace_root).read_material_upload_state(
        "AAPL", identity.document_id,
    )
    assert state.source_integrity.status in {SourceIntegrityStatus.UNSAFE, SourceIntegrityStatus.REPAIR_REQUIRED}
    before_tree = _snapshot_cli_workspace_tree(workspace_root)
    input_file = tmp_path / "deck.txt"
    input_file.write_text("candidate", encoding="utf-8")
    operator_log = tmp_path / "operator.log"
    service = _FakeFinsDirectService()
    factory_calls: list[Path] = []
    monkeypatch.setattr(
        fins_command, "FINS_DIRECT_SERVICE_FACTORY",
        partial(_recording_direct_service_factory, service=service, factory_calls=factory_calls),
    )
    lifecycle_calls: list[Mock] = []
    for owner, method in (
        (ingestion_runtime.FinsIngestionRuntime, "upload"),
        (ingestion_runtime.FinsIngestionRuntime, "prepare_observed_upload"),
        (ingestion_runtime.FinsIngestionRuntime, "start_upload"),
        (FsBatchingRepository, "begin_batch"),
    ):
        spy = Mock(side_effect=AssertionError("材料损坏必须在生命周期之前拒绝"))
        monkeypatch.setattr(owner, method, spy)
        lifecycle_calls.append(spy)

    exit_code = cli_main.main(
        (
            "upload_material", "--base", str(workspace_root), "--log-file", str(operator_log),
            "--ticker", "AAPL", "--action", action, "--forms", "OTHER", "--material-name", "Deck",
            *(("--files", str(input_file)) if action != "delete" else ()),
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_FAILURE
    assert captured.out == ""
    assert captured.err == "dayu-cli upload_material: 工作区中的目标材料状态不完整，无法安全上传\n"
    assert str(tmp_path) not in captured.err
    assert "Traceback" not in captured.err and "FinsUploadPrevalidationError" not in captured.err
    operator_diagnostic = operator_log.read_text(encoding="utf-8")
    assert "upload_material prevalidation operational failure" in operator_diagnostic
    assert "upload_filing prevalidation operational failure" not in operator_diagnostic
    assert "FinsUploadPrevalidationError" in operator_diagnostic
    assert factory_calls == []
    assert service.upload_material_requests == [] and service.stream_calls == []
    for spy in lifecycle_calls:
        spy.assert_not_called()
    assert _snapshot_cli_workspace_tree(workspace_root) == before_tree


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


@pytest.mark.parametrize("command_name", ("upload_filing", "upload_material"))
@pytest.mark.parametrize("ticker", ("ICPD", "600519", "0700"))
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
    command_name: str,
    ticker: str,
) -> None:
    """两类真实 CLI 在 US/CN/HK 的 empty/corrupt PDF/DOCX 保持五字段、安全路径与零文档发布，material 保留合法公司。

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
    repository_root = Path(__file__).resolve().parents[2]

    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "dayu.cli",
            command_name,
            "--base",
            str(workspace_root),
            "--ticker",
            ticker,
            "--files",
            str(corrupt_file),
            "--fiscal-year",
            "2024",
            "--fiscal-period",
            "FY",
            "--company-name",
            "ICPD Corp.",
            *(("--forms", "MATERIAL_OTHER", "--material-name", "CLI Content") if command_name == "upload_material" else ()),
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
    (tmp_path / "cli.stdout").write_text(completed.stdout, encoding="utf-8")
    (tmp_path / "cli.stderr").write_text(completed.stderr, encoding="utf-8")
    (tmp_path / "cli.exit").write_text(str(completed.returncode) + "\n", encoding="utf-8")
    (tmp_path / "cli.command.json").write_text(json.dumps(completed.args, ensure_ascii=False), encoding="utf-8")
    if command_name == "upload_filing":
        assert not workspace_root.exists()
    else:
        repository = FsSourceDocumentRepository(workspace_root)
        assert repository.list_source_document_ids(ticker, SourceKind.MATERIAL) == []
        assert FsCompanyMetaRepository(workspace_root).get_company_meta(ticker).company_name == "ICPD Corp."
        assert not tuple((workspace_root / ".dayu" / "fins_ingestion" / "jobs").glob("*.json"))
        assert not (workspace_root / "sessions").exists()
        assert not (workspace_root / "artifacts").exists()


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
                "--base", str(tmp_path / "workspace"),
                "--company-name", "Apple Inc.",
                "--ticker",
                "AAPL,MSFT",
                "--forms",
                "8-K",
                "--material-name",
                "Investor Day",
                "--files",
                str(material_file),


            )
        )
        == EXIT_SUCCESS
    )

    assert fake_service.upload_filing_requests == [
        _UploadFilingCall(
            ticker="AAPL",
            action="create",
            files=(filing_file.resolve(),),
            primary_selectors=(),
            selected_primary=filing_file.resolve(),
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
            ticker="AAPL",
            action="auto",
            files=(material_file.resolve(),),
            form_type="8-K",
            material_name="Investor Day",
            document_id=None,
            internal_document_id=build_material_ids(form_type="8-K", material_name="Investor Day", fiscal_year=None, fiscal_period=None, document_id=None).internal_document_id,
            fiscal_year=None,
            fiscal_period=None,
            amended=False,
            filing_date=None,
            report_date=None,
            company_name="Apple Inc.",
            ticker_aliases=("MSFT",),
            overwrite=False,
        )
    ]


@pytest.mark.parametrize(
    ("option", "raw_value", "expected_reason"),
    (
        ("--filing-date", "", None),
        ("--filing-date", " 2024-02-29 ", "披露日期（filing_date）必须是实际存在的 YYYY-MM-DD 日期"),
        ("--report-date", "2024-02-29 ", "报告期日期（report_date）必须是实际存在的 YYYY-MM-DD 日期"),
    ),
)
def test_upload_material_cli_rejects_padded_dates_before_service(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
    option: str,
    raw_value: str,
    expected_reason: str | None,
) -> None:
    """CLI 仅折叠空日期，非空非法原文在启动 Service 前被 owner 拒绝。

    Args:
        tmp_path: 测试材料文件所在临时目录。
        fake_service: 记录 Service 参数的替身。
        capsys: 捕获公开 usage 文案。
        option: 当前日期命令参数。
        raw_value: CLI 收到的原始文本。
        expected_reason: 非空非法日期的公开拒绝原因；空值为 None。

    Returns:
        无。

    Raises:
        AssertionError: CLI 空值例外或非空日期前置拒绝漂移时抛出。
    """

    material_file = tmp_path / "material.html"
    material_file.write_text("<html></html>", encoding="utf-8")
    exit_code = cli_main.main(
        (
            "upload_material",
                "--base", str(tmp_path / "workspace"),
                "--company-name", "Apple Inc.",
            "--ticker",
            "AAPL",
            "--forms",
            "MATERIAL_OTHER",
            "--material-name",
            "Deck",
            "--files",
            str(material_file),
            option,
            raw_value,
        )
    )

    if expected_reason is None:
        assert exit_code == EXIT_SUCCESS
        assert len(fake_service.upload_material_requests) == 1
        assert fake_service.upload_material_requests[0].filing_date is None
    else:
        assert exit_code == EXIT_USAGE_ERROR
        assert fake_service.upload_material_requests == []
        assert expected_reason in capsys.readouterr().err


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


def test_upload_material_cli_names_conflicting_basename_without_path(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI 将 planner 的安全冲突标签投影为可定位的 usage 文案。

    Args:
        tmp_path: 两个同名原件所在的隔离目录。
        fake_service: 记录未被调用的 direct Service。
        capsys: 捕获 CLI 输出。

    Returns:
        无。

    Raises:
        AssertionError: 冲突文件标签、路径安全或零调用边界漂移时抛出。
    """

    first = tmp_path / "one" / "deck.pdf"
    second = tmp_path / "two" / "deck.pdf"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    exit_code = cli_main.main(
        (
            "upload_material", "--ticker", "AAPL", "--forms", "MATERIAL_OTHER",
            "--material-name", "Deck", "--files", str(first), str(second),
        )
    )
    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR, captured.err
    assert captured.out == ""
    assert "deck.pdf" in captured.err
    assert str(tmp_path) not in captured.err
    assert fake_service.upload_material_requests == []


@pytest.mark.parametrize(
    ("names", "expected_code", "expected_message"),
    (
        (("META.JSON", "deck.zip"), "reserved_control_name",
         "文件名与仓储控制文件冲突：META.JSON；请重命名后重试"),
        (("same.txt", "same.txt", "deck.zip"), "duplicate_original_basename",
         "原件文件名重复：same.txt；请重命名后重试"),
    ),
)
def test_upload_material_cli_mixed_name_and_format_uses_plan_reason(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
    names: tuple[str, ...],
    expected_code: str,
    expected_message: str,
) -> None:
    """CLI 对混合名称及格式错误使用计划 owner 的原因和完整安全文案。

    Args:
        tmp_path: 隔离输入路径。
        fake_service: 记录不应发生的 Service 调用。
        capsys: CLI 输出捕获。
        names: 原件名的保序组合。
        expected_code: owner 用法错误码。
        expected_message: 完整安全文案。

    Returns:
        无。

    Raises:
        AssertionError: 公开错误与 owner 分裂或启动 Service 时抛出。
    """

    from dayu.fins.ingestion_runtime import FinsUploadMaterialRequest, admit_fins_upload_material_request
    from dayu.fins.upload_usage_contract import FinsUploadUsageError

    paths = tuple(tmp_path / str(index) / name for index, name in enumerate(names))
    for path in paths:
        path.parent.mkdir()
        path.write_bytes(b"input")
    with pytest.raises(FinsUploadUsageError) as raised:
        admit_fins_upload_material_request(FinsUploadMaterialRequest(form_type="MATERIAL_OTHER", material_name="Deck", ticker="AAPL", files=paths,  company_name="Apple Inc.",),  state_repository=FsMaterialUploadStateRepository(tmp_path),)
    assert raised.value.failure.code.value == expected_code
    assert raised.value.failure.message == expected_message
    exit_code = cli_main.main((
        "upload_material", "--ticker", "AAPL", "--forms", "MATERIAL_OTHER",
        "--material-name", "Deck", "--files", *(str(path) for path in paths),
    ))
    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert captured.out == ""
    assert captured.err == f"dayu-cli upload_material: {expected_message}\n"
    assert str(tmp_path) not in captured.err
    assert fake_service.upload_material_requests == []


def test_real_cli_long_duplicate_basename_is_typed_usage_without_publication(
    tmp_path: Path,
) -> None:
    """真实 CLI 对合法长同名原件返回有界用法错误且不发布。

    Args:
        tmp_path: 隔离输入目录与尚未建立的工作区。

    Returns:
        无。

    Raises:
        AssertionError: closed reason、退出码、路径安全或零发布漂移时抛出。
        subprocess.TimeoutExpired: 真实 CLI 在期限内没有完成时抛出。
    """

    from dayu.fins.ingestion_runtime import (
        FinsUploadMaterialRequest,
        admit_fins_upload_material_request,
    )
    from dayu.fins.upload_usage_contract import FinsUploadUsageCode, FinsUploadUsageError

    basename = "a" * 222 + ".txt"
    first = tmp_path / "one" / basename
    second = tmp_path / "two" / basename
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    with pytest.raises(FinsUploadUsageError) as raised:
        admit_fins_upload_material_request(
            FinsUploadMaterialRequest(form_type="MATERIAL_OTHER", material_name="Deck", primary_selectors=(first,), ticker="AAPL", files=(first, second),  company_name="Apple Inc.",)
        ,  state_repository=FsMaterialUploadStateRepository(tmp_path),)
    assert raised.value.failure.code is FinsUploadUsageCode.DUPLICATE_ORIGINAL_BASENAME

    workspace_root = tmp_path / "fresh-workspace"
    repository_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        (
            sys.executable, "-m", "dayu.cli", "upload_material",
            "--base", str(workspace_root), "--ticker", "AAPL", "--action", "create",
            "--forms", "MATERIAL_OTHER", "--material-name", "Deck",
            "--company-name", "Apple Inc.", "--files", str(first), str(second),
        ),
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )

    assert completed.returncode == EXIT_USAGE_ERROR
    assert completed.stdout == ""
    assert completed.stderr == (
        f"dayu-cli upload_material: {raised.value.failure.message}\n"
    )
    assert len(raised.value.failure.message) <= 240
    assert "…" in completed.stderr
    assert ".txt" in completed.stderr
    assert str(tmp_path) not in completed.stderr
    assert str(repository_root) not in completed.stderr
    assert "Traceback" not in completed.stderr
    assert not workspace_root.exists()


def test_real_cli_backslash_basename_is_typed_usage_without_publication(
    tmp_path: Path,
) -> None:
    """真实 CLI 对可创建的反斜杠文件名给出封闭用法错误且不发布。

    Args:
        tmp_path: 隔离输入文件与尚未建立的工作区。

    Returns:
        无。

    Raises:
        AssertionError: 退出码、公开标签或零发布边界漂移时抛出。
        subprocess.TimeoutExpired: 真实 CLI 在期限内没有完成时抛出。
    """

    from dayu.fins.ingestion_runtime import (
        FinsUploadMaterialRequest,
        admit_fins_upload_material_request,
    )
    from dayu.fins.upload_usage_contract import FinsUploadUsageCode, FinsUploadUsageError

    upload_file = tmp_path / "a\\b.txt"
    upload_file.write_bytes(b"content")
    with pytest.raises(FinsUploadUsageError) as raised:
        admit_fins_upload_material_request(
            FinsUploadMaterialRequest(form_type="MATERIAL_OTHER", material_name="Deck", ticker="AAPL", files=(upload_file,),  company_name="Apple Inc.",)
        ,  state_repository=FsMaterialUploadStateRepository(tmp_path),)
    assert raised.value.failure.code is FinsUploadUsageCode.INVALID_ASSET_NAME

    workspace_root = tmp_path / "fresh-workspace"
    repository_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        (
            sys.executable, "-m", "dayu.cli", "upload_material",
            "--base", str(workspace_root), "--ticker", "AAPL", "--action", "create",
            "--forms", "MATERIAL_OTHER", "--material-name", "Deck",
            "--company-name", "Apple Inc.", "--files", str(upload_file),
        ),
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )

    assert completed.returncode == EXIT_USAGE_ERROR
    assert completed.stdout == ""
    assert completed.stderr == f"dayu-cli upload_material: {raised.value.failure.message}\n"
    assert "输入文件（文件名已隐藏）" in completed.stderr
    assert str(tmp_path) not in completed.stderr
    assert "Traceback" not in completed.stderr
    assert not workspace_root.exists()


def test_real_cli_unknown_home_uses_planner_usage_without_publication(
    tmp_path: Path,
) -> None:
    """可经 argv 传入的未知用户目录在真实 CLI 返回封闭用法错误。

    Args:
        tmp_path: 尚未建立的隔离工作区根。

    Returns:
        无。

    Raises:
        AssertionError: 退出码、安全文案或零发布漂移时抛出。
        subprocess.TimeoutExpired: CLI 未在期限内结束时抛出。
    """

    from dayu.fins.ingestion_runtime import FinsUploadMaterialRequest, admit_fins_upload_material_request
    from dayu.fins.upload_usage_contract import FinsUploadUsageCode, FinsUploadUsageError

    raw_name = "~dayu_assets_nonexistent_user_20260929/report.txt"
    with pytest.raises(FinsUploadUsageError) as raised:
        admit_fins_upload_material_request(
            FinsUploadMaterialRequest(form_type="MATERIAL_OTHER", material_name="Deck", ticker="AAPL", files=(Path(raw_name),),  company_name="Apple Inc.",)
        ,  state_repository=FsMaterialUploadStateRepository(tmp_path),)
    assert raised.value.failure.code is FinsUploadUsageCode.INVALID_ASSET_NAME
    workspace_root = tmp_path / "fresh-workspace"
    repository_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        (
            sys.executable, "-m", "dayu.cli", "upload_material",
            "--base", str(workspace_root), "--ticker", "AAPL", "--action", "create",
            "--forms", "MATERIAL_OTHER", "--material-name", "Deck",
            "--company-name", "Apple Inc.", "--files", raw_name,
        ),
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    assert completed.returncode == EXIT_USAGE_ERROR
    assert completed.stdout == ""
    assert completed.stderr == f"dayu-cli upload_material: {raised.value.failure.message}\n"
    assert "Could not determine home directory" not in completed.stderr
    assert str(tmp_path) not in completed.stderr
    assert not workspace_root.exists()


def test_real_cli_filing_unknown_home_uses_typed_usage_before_workspace(
    tmp_path: Path,
) -> None:
    """真实 filing CLI 不在参数层自行解析路径并遮蔽封闭失败。

    Args:
        tmp_path: 尚未建立的隔离工作区根。

    Returns:
        无。

    Raises:
        AssertionError: CLI 退出码、文案或工作区副作用漂移时抛出。
        subprocess.TimeoutExpired: CLI 未在期限内结束时抛出。
    """

    workspace_root = tmp_path / "fresh-workspace"
    raw_name = "~dayu_nonexistent_user_zz/report.pdf"
    completed = subprocess.run(
        (sys.executable, "-m", "dayu.cli", "upload_filing", "--base", str(workspace_root),
         "--ticker", "AAPL", "--action", "create", "--fiscal-year", "2024",
         "--fiscal-period", "FY", "--company-name", "Apple Inc.", "--files", raw_name),
        cwd=Path(__file__).resolve().parents[2], check=False,
        capture_output=True, text=True, timeout=60.0,
    )
    assert completed.returncode == EXIT_USAGE_ERROR
    assert "上传文件不存在：report.pdf" in completed.stderr
    assert "Could not determine home directory" not in completed.stderr
    assert not workspace_root.exists()


def test_real_cli_material_delete_rejects_files_before_path_access(tmp_path: Path) -> None:
    """参数：隔离根；返回：无；异常：断言/超时；delete 所有 files 在解析路径前同源拒绝。"""
    workspace_root = tmp_path / "fresh-workspace"
    valid = tmp_path / "valid.pdf"
    valid.write_bytes(b"valid")
    prefix = (sys.executable, "-m", "dayu.cli", "upload_material", "--base", str(workspace_root),
              "--ticker", "AAPL", "--action", "delete", "--forms", "MATERIAL_OTHER",
              "--material-name", "Deck", "--company-name", "Apple Inc.", "--files")
    for paths in ((str(valid),), (str(tmp_path / "missing.pdf"),), (str(tmp_path),), (str(valid),) * 101):
        completed = subprocess.run((*prefix, *paths), cwd=Path(__file__).resolve().parents[2],
                                   check=False, capture_output=True, text=True, timeout=60.0)
        assert completed.returncode == EXIT_USAGE_ERROR
        assert completed.stdout == ""
        assert "delete 不得提供 --files" in completed.stderr
        assert not workspace_root.exists()


def test_real_cli_material_delete_unknown_home_is_closed_usage(tmp_path: Path) -> None:
    """真实 delete CLI 将未知用户目录归入可修正的资产规划失败。

    Args:
        tmp_path: 隔离且未创建的工作区根。

    Returns:
        无。

    Raises:
        AssertionError: 退出分类、公开标签或零副作用漂移时抛出。
        subprocess.TimeoutExpired: CLI 未在期限内结束时抛出。
    """

    workspace_root = tmp_path / "fresh-workspace"
    completed = subprocess.run(
        (
            sys.executable, "-m", "dayu.cli", "upload_material",
            "--base", str(workspace_root), "--ticker", "AAPL", "--action", "delete",
            "--forms", "MATERIAL_OTHER", "--material-name", "Deck",
            "--company-name", "Apple Inc.", "--files",
            "~dayu_assets_nonexistent_user_20260930/report.pdf",
        ),
        cwd=Path(__file__).resolve().parents[2],
        check=False, capture_output=True, text=True, timeout=60.0,
    )
    assert completed.returncode == EXIT_USAGE_ERROR
    assert completed.stdout == ""
    assert "delete 不得提供 --files" in completed.stderr
    assert "dayu_assets_nonexistent_user_20260930" not in completed.stderr
    assert not workspace_root.exists()


@pytest.mark.parametrize("action", ("create", "delete"))
def test_real_cli_material_symlink_loop_is_operational_without_publication(
    tmp_path: Path, action: str,
) -> None:
    """真实 CLI 将路径循环作为操作失败处理，不创建工作区资产。

    Args:
        tmp_path: 隔离链接和工作区。
        action: 待验证的上传动作。

    Returns:
        无。

    Raises:
        AssertionError: 退出分类、公开文案或零发布漂移时抛出。
        subprocess.TimeoutExpired: CLI 未在期限内结束时抛出。
    """

    loop = tmp_path / "loop.pdf"
    loop.symlink_to(loop.name)
    workspace_root = tmp_path / "fresh-workspace"
    repository_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        (
            sys.executable, "-m", "dayu.cli", "upload_material",
            "--base", str(workspace_root), "--ticker", "AAPL", "--action", action,
            "--forms", "MATERIAL_OTHER", "--material-name", "Deck",
            "--company-name", "Apple Inc.", "--files", str(loop),
        ),
        cwd=repository_root, check=False, capture_output=True, text=True, timeout=60.0,
    )
    assert completed.returncode == (EXIT_USAGE_ERROR if action == "delete" else EXIT_FAILURE)
    assert completed.stdout == ""
    assert "文件名无法安全保存" not in completed.stderr
    assert str(loop) not in completed.stderr
    assert not workspace_root.exists()


@pytest.mark.parametrize("action", ("create", "delete"))
def test_cli_nul_path_uses_planner_usage_before_service_factory(
    tmp_path: Path,
    fake_service: _FakeFinsDirectService,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    """无法经 argv 传入的 NUL 在 CLI 参数边界仍安全退出。

    Args:
        tmp_path: 尚未建立的隔离工作区根。
        fake_service: 记录意外的 Service 调用。
        capsys: 捕获公开标准输出和错误输出。
        action: 待验证的上传动作。

    Returns:
        无。

    Raises:
        AssertionError: usage 退出、安全文案或零发布漂移时抛出。
    """

    workspace_root = tmp_path / "fresh-workspace"
    exit_code = cli_main.main(
        (
            "upload_material", "--base", str(workspace_root), "--ticker", "AAPL",
            "--action", action, "--forms", "MATERIAL_OTHER", "--material-name", "Deck",
            "--company-name", "Apple Inc.", "--files", "a\x00b.txt",
        )
    )
    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert captured.out == ""
    if action == "delete":
        assert "delete 不得提供 --files" in captured.err
    else:
        assert "文件名无法安全保存" in captured.err
        assert "输入文件（文件名已隐藏）" in captured.err
    assert "embedded null byte" not in captured.err
    assert str(tmp_path) not in captured.err
    assert fake_service.upload_material_requests == []
    assert not workspace_root.exists()


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


def test_unknown_download_command_logs_safe_trace_and_hides_exception_from_stderr(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """未知 download 外层异常只记录安全诊断，普通 stderr 使用固定文案。

    Args:
        monkeypatch: direct async 主流程异常注入夹具。
        caplog: operator 日志捕获夹具。
        capsys: 标准流捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: stderr 或日志泄漏原文、安全诊断缺失时抛出。
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
    assert "fins.download.command_unexpected_failure" in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert _UNKNOWN_DIRECT_FAILURE_MARKER not in caplog.text
    assert "/absolute/path" not in caplog.text
    assert "Traceback" not in caplog.text
    records = [record for record in caplog.records if "fins.download.command_unexpected_failure" in record.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].exc_info is None


def test_unknown_download_command_log_file_is_readable_and_helper_failure_is_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """显式日志文件可读取安全诊断；共享 helper 内部故障不改变 CLI 终态。

    :param tmp_path: 临时日志目录。
    :param monkeypatch: 外层异常和 helper 内部故障注入。
    :param capsys: 用户输出捕获。
    :returns: 无。
    :raises AssertionError: 文件不可读、泄密或退出码漂移时抛出。
    """

    monkeypatch.setattr(fins_command, "_run_fins_direct_command_async", _raise_unknown_fins_direct_error)
    log_file = tmp_path / "download.log"
    assert cli_main.main(("download", "--ticker", "AAPL", "--log-file", str(log_file))) == EXIT_FAILURE
    first_output = capsys.readouterr()
    assert first_output.err == _UNKNOWN_DIRECT_FAILURE_STDERR
    log_text = log_file.read_text(encoding="utf-8")
    assert "fins.download.command_unexpected_failure" in log_text
    assert "exception_type=RuntimeError" in log_text
    assert _UNKNOWN_DIRECT_FAILURE_MARKER not in log_text
    assert "Traceback" not in log_text

    def fail_type(_exc: Exception) -> tuple[str, str]:
        """模拟共用 helper 内部类型判断失败。

        :param _exc: 原始异常。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出。
        """

        raise RuntimeError("token=helper-secret")

    monkeypatch.setattr(fins_command.runtime_log, "_safe_exception_type", fail_type)
    assert cli_main.main(("download", "--ticker", "AAPL", "--log-file", str(log_file))) == EXIT_FAILURE
    second_output = capsys.readouterr()
    assert second_output.err == _UNKNOWN_DIRECT_FAILURE_STDERR
    log_text = log_file.read_text(encoding="utf-8")
    assert "exception_type=redacted custom_type=redacted stack=[unavailable]" in log_text
    assert "helper-secret" not in log_text
    assert _UNKNOWN_DIRECT_FAILURE_MARKER not in log_text


def test_non_download_unknown_command_keeps_original_traceback(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """非 download direct 外层异常保留既有 raw 日志与固定用户文案。

    :param monkeypatch: 外层异常注入。
    :param caplog: operator 日志捕获。
    :param capsys: 用户输出捕获。
    :returns: 无。
    :raises AssertionError: 原有日志行为或固定文案漂移时抛出。
    """

    monkeypatch.setattr(fins_command, "_run_fins_direct_command_async", _raise_unknown_fins_direct_error)
    caplog.set_level(logging.ERROR, logger=fins_command.__name__)
    args = parse_cli_args(("process", "--ticker", "AAPL", "--document-id", "doc-1"))
    assert fins_command.run_fins_direct_command(args) == EXIT_FAILURE
    assert capsys.readouterr().err == (
        "dayu-cli process: 命令执行失败，请使用 --log-file PATH 重试并查看日志\n"
    )
    assert "Fins direct command failed; command=process" in caplog.text
    assert _UNKNOWN_DIRECT_FAILURE_MARKER in caplog.text
    assert "Traceback" in caplog.text


@pytest.mark.parametrize(
    ("summary", "expected_stream", "expected_other_stream"),
    (
        (
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status="ok",
                requested_file_count=2,
                stored_file_count=2,
             published_amended=None,),
            "stdout",
            "",
        ),
        (
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status="deleted",
                requested_file_count=0,
                stored_file_count=0,
             published_amended=None,),
            "stdout",
            "",
        ),
        (
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status="skipped",
                requested_file_count=2,
                stored_file_count=0,
             published_amended=None,),
            "stdout",
            "",
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
             published_amended=None,),
            "stderr",
            "",
        ),
        (
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status="ok",
                requested_file_count=1,
                stored_file_count=1,
                warnings=(
                    CompanyMetadataWarning(
                        kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
                        message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
                    ),
                ),
             published_amended=None,),
            "stdout",
            f"{COMPANY_NAME_IGNORED_WARNING_MESSAGE}\n",
        ),
        (
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status="skipped",
                requested_file_count=1,
                stored_file_count=0,
                warnings=(
                    CompanyMetadataWarning(
                        kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
                        message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
                    ),
                ),
             published_amended=None,),
            "stdout",
            f"{COMPANY_NAME_IGNORED_WARNING_MESSAGE}\n",
        ),
    ),
)
def test_upload_terminal_summary_renderer_uses_typed_requested_and_stored_counts(
    summary: FinsUploadResultSummary,
    expected_stream: str,
    expected_other_stream: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI renderer 必须展示 typed upload summary 的 requested/stored 真源。

    Args:
        summary: production upload summary owner 构造的当前终态。
        expected_stream: 当前终态应写入的标准流名称。
        expected_other_stream: 另一标准流应包含的 exact warning 文本。
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
        primary_selectors=(input_files[0],) if len(input_files) > 1 else (),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name=None if summary.status == "deleted" else "Apple Inc.",
    )
    document_id, _internal_document_id = build_sec_filing_ids(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    published_state = FilingUploadPublishedState(
        company_meta=None,
        source_integrity=SourceIntegrityClassification(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            document_id=document_id,
            revision=None,
            status=SourceIntegrityStatus.MISSING,
            reasons=(),
        ),
        source_meta=None,
        publication_identity=None,
    )
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
    assert result_event.result is not None
    if expected_stream == "stdout":
        assert result_event.result.exit_code == EXIT_SUCCESS
    rendered = captured.out if expected_stream == "stdout" else captured.err
    other_stream = captured.err if expected_stream == "stdout" else captured.out
    assert f'requested_files="{summary.requested_file_count}"' in rendered
    assert f'stored_files="{summary.stored_file_count}"' in rendered
    assert "uploaded_files" not in rendered
    assert other_stream == expected_other_stream


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
    primary_selectors: tuple[Path, ...]
    selected_primary: Path | None
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
        return ("upload_material", "--base", str(tmp_path / "workspace"), "--company-name", "Apple Inc.", "--forms", "MATERIAL_OTHER", "--material-name", "Deck", "--ticker", "AAPL", "--files", str(upload_file))
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
    operation_kind: FinsOperationKind = FinsOperationKind.DOWNLOAD,
) -> FinsEvent:
    """构造真实操作类型对应的合法测试终态事件。

    :param status: result status。
    :param operation_kind: 真实操作类型。
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
        operation_kind=operation_kind,
        message="download finished",
        emitted_at=_NOW,
        ticker="AAPL",
        filing_kind="10-K",
        document_label="AAPL 10-K FY2024",
        progress=None,
        result=(
            replace(_terminal(_download_summary(source=download_contract.FinsDownloadSource.SEC), status), title="Download finished", details=(FinsEventDetail(label="processed_count", value="1"),))
            if operation_kind is FinsOperationKind.DOWNLOAD
            else FinsResultSummary(status=status, exit_code=exit_code, title="Operation finished",
                details=(FinsEventDetail(label="processed_count", value="1"),),
                error_kind=error_kind, error_message=error_message)
        ),
    )


@pytest.mark.parametrize("path_kind", ("missing", "directory"))
def test_material_cli_path_precheck_keeps_existing_usage_before_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    path_kind: str,
) -> None:
    """material 准入后对缺失路径与目录沿用原有文案且不打开 Service。

    Args:
        tmp_path: 隔离输入与 workspace 根。
        monkeypatch: Service 构造观察点。
        capsys: 双流捕获。
        path_kind: 缺失路径或目录。

    Returns:
        无。

    Raises:
        AssertionError: CLI 预检、exit 或旧英文文案漂移时抛出。
    """

    bad_path = tmp_path / ("missing.pdf" if path_kind == "missing" else "directory.pdf")
    if path_kind == "directory":
        bad_path.mkdir()
    service_factory = Mock(side_effect=AssertionError("Service 不应启动"))
    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", service_factory)
    exit_code = cli_main.main(
        (
            "upload_material",
            "--company-name", "Apple Inc.",
            "--base",
            str(tmp_path / "workspace"),
            "--ticker",
            "AAPL",
            "--forms",
            "MATERIAL_OTHER",
            "--material-name",
            "Deck",
            "--files",
            str(bad_path),
        )
    )
    captured = capsys.readouterr()
    expected = (
        f"upload file does not exist: {bad_path.resolve(strict=False)}"
        if path_kind == "missing"
        else f"upload path is not a file: {bad_path.resolve(strict=False)}"
    )
    assert exit_code == EXIT_USAGE_ERROR
    assert captured.out == ""
    assert captured.err == f"dayu-cli upload_material: {expected}\n"
    service_factory.assert_not_called()


class _RealSecIntegrityServiceFactory:
    """给真实 CLI 装配真实 runtime，仅下载器资产为离线合成。"""

    def __init__(self, runtime: ingestion_runtime.FinsIngestionRuntime) -> None:
        """保存授权工作区的真实 runtime。

        参数：runtime 为真实运行时。返回：无。异常：无。
        """
        self.runtime = runtime

    def __call__(self, workspace_root: Path) -> FinsDirectCommandService:
        """提供真实 Service 消费入口。

        参数：workspace_root 为 CLI 规范化工作区。返回：真实 direct Service。异常：无。
        """
        del workspace_root
        return FinsDirectCommandService(self.runtime)


@pytest.mark.parametrize("scenario", ("postrepair", "churn"))
def test_fins_download_sec_integrity_failure_preserves_summary(
    tmp_path: Path, scenario: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI 主入口执行真实 SEC adapter 后返回失败并保全文档摘要和安全原因。

    参数：tmp_path 为隔离根；scenario 为真实状态；monkeypatch 为 Service 装配；capsys 为输出观察器。
    返回：无。异常：断言失败抛出 AssertionError。
    """
    runtime, _executor, pipeline = _build_real_sec_integrity_runtime(tmp_path, scenario)
    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", _RealSecIntegrityServiceFactory(runtime))
    args = ["download", "--base", str(tmp_path), "--ticker", "AAPL", "--forms", "10-K", "6-K",
        "--start", "2025-01-01", "--end", "2025-12-31"]
    if scenario == "churn":
        args.append("--overwrite")
    code = cli_main.main(tuple(args))
    captured = capsys.readouterr()
    assert code == EXIT_FAILURE, captured.err
    reason = "source_repair_required" if scenario == "postrepair" else "source_revision_conflict"
    message = "本地来源仍需修复，本次下载已停止" if scenario == "postrepair" else "本地来源版本持续变化，本次下载已停止"
    assert f'reason_code="{reason}"' in captured.err and message in captured.err
    assert "downloaded=1" in captured.err
    assert ("failed=0" if scenario == "postrepair" else "failed=1") in captured.err
    assert str(tmp_path) not in captured.err and "://" not in captured.err
    assert pipeline.source_repository.classify_source_integrity("AAPL", "fil_0000000000-25-000001", SourceKind.FILING).status is SourceIntegrityStatus.COMPLETE
    print(captured.err)


@pytest.mark.skipif(os.name != "posix", reason="真实 SIGINT 验证需要 POSIX 信号")
def test_real_material_cli_sigint_waits_for_cancelled_terminal(tmp_path: Path) -> None:
    """参数：独占真实输入与根；返回：无；异常：断言/超时；首个真实进度后 SIGINT 请求协作取消，exit=130且无材料/job/Agent产物。"""
    workspace_root = tmp_path / "workspace"
    path = tmp_path / "cancel.txt"
    path.write_text("Public cancellation probe text.\n" * 2000, encoding="utf-8")
    argv = (sys.executable, "-m", "dayu.cli", "upload_material", "--base", str(workspace_root),
            "--ticker", "AAPL", "--forms", "MATERIAL_OTHER", "--material-name", "Cancel Text",
            "--company-name", "Apple Inc.", "--files", str(path))
    started = time.monotonic()
    process = subprocess.Popen(argv, cwd=Path(__file__).resolve().parents[2], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    first_line = ""
    try:
        assert process.stdout is not None
        readable, _, _ = select.select((process.stdout,), (), (), 30.0)
        assert readable, "CLI 未产生首个进度"
        first_line = process.stdout.readline()
        assert "Fins progress" in first_line
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=30.0)
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=10.0)
    (tmp_path / "sigint.stdout").write_text(first_line + stdout, encoding="utf-8")
    (tmp_path / "sigint.stderr").write_text(stderr, encoding="utf-8")
    (tmp_path / "sigint.exit").write_text(str(process.returncode) + "\n", encoding="utf-8")
    (tmp_path / "sigint.command.json").write_text(json.dumps({"argv": argv, "pid": process.pid,
        "monotonic_start": started, "monotonic_end": time.monotonic(), "signal": "SIGINT"}), encoding="utf-8")
    assert process.returncode == EXIT_KEYBOARD_INTERRUPT
    assert "Fins cancelled" in stderr and "Traceback" not in stderr
    assert not tuple((workspace_root / ".dayu" / "fins_ingestion" / "jobs").glob("*.json"))
    assert FsSourceDocumentRepository(workspace_root).list_source_document_ids("AAPL", SourceKind.MATERIAL) == []
    assert not (workspace_root / "sessions").exists()
    assert not (workspace_root / "artifacts").exists()


class _DiagnosticsSpawnHandle:
    """复用真实 process 生命周期，仅在 worker 替换转换内容结果。"""
    def __new__(cls, target: 'InterruptibleProcessTarget') -> 'InterruptibleProcessHandle':
        """参数：真实 production target；返回：真实 handle；异常：worker 装配错误传播。"""
        from dayu.runtime.interruptible_process import InterruptibleProcessHandle
        from dayu.fins.pipelines.docling_process_converter import _DoclingProcessTarget
        from tests.fins.test_docling_process_converter import _TargetSpawnProbe
        return InterruptibleProcessHandle(_TargetSpawnProbe(cast(_DoclingProcessTarget, target), 'leak'))


@pytest.mark.parametrize('selector', ['default', 'quiet', 'info', 'error'])
def test_upload_material_converter_diagnostics_cli_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str], selector: str) -> None:
    """参数：真实 CLI/Service/Fs/worker 与 selector；返回：无；异常：双流泄漏/日志准入/业务终态漂移失败。"""
    from dayu.fins.pipelines import docling_process_converter
    monkeypatch.setattr(docling_process_converter, 'InterruptibleProcessHandle', _DiagnosticsSpawnHandle)
    source = tmp_path / 'annual-report.pdf'; source.write_bytes(b'immutable-filing-input')
    logfile = _redirect_default_log_file(tmp_path=tmp_path, monkeypatch=monkeypatch) if selector == 'default' else tmp_path / 'explicit.log'
    args = ['upload_material', '--base', str(tmp_path / 'store'), '--ticker', 'MSFT', '--forms', 'MATERIAL_OTHER',
            '--material-name', 'Diagnostic owner', '--company-name', 'Microsoft Corporation', '--files', str(source)]
    if selector != 'default': args += ['--' + selector, '--log-file', str(logfile)]
    if selector == 'info': logfile.write_text('append-prefix\n')
    assert cli_main.main(tuple(args)) == EXIT_SUCCESS
    public = capfd.readouterr()
    assert public.err == '' and 'stored_files="1"' in public.out
    assert 'installed late-created warning' not in public.out and 'native stdout WARNING' not in public.out
    text = logfile.read_text()
    if selector in ('default', 'info'):
        assert '[WARNING] [MatchingPostProcessor] installed late-created warning' in text
        assert 'source_level=unknown' in text and '转换诊断捕获异常' in text
    else: assert 'installed late-created warning' not in text and 'native stdout WARNING' not in text
    if selector == 'info': assert text.startswith('append-prefix\n')


def test_fixed_cli_download_diagnostics_on_empty_rebuild(tmp_path: Path) -> None:
    """通过固定绝对 CLI 与仓库外 cwd 验证空来源离线 rebuild 新协议。

    Args:
        tmp_path: 本轮独占临时根，隔离来源工作区与进程 cwd。

    Returns:
        无。

    Raises:
        AssertionError: 实际退出码、唯一诊断行或新协议字段不满足预期时抛出。
        subprocess.TimeoutExpired: 固定入口未在六十秒内退出时抛出。
    """

    binary = Path(__file__).resolve().parents[2] / ".venv/bin/dayu-cli"
    outside_cwd = tmp_path / "outside-cwd"
    outside_cwd.mkdir()
    fixture_root = tmp_path / "empty-workspace"
    completed = subprocess.run(
        [str(binary), "download", "--base", str(fixture_root), "--ticker", "0700", "--start", "2018-01-01", "--end", "2026-10-10", "--rebuild"],
        cwd=outside_cwd, capture_output=True, text=True, timeout=60, check=False,
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    prefix = "Fins download diagnostics: "
    lines = [line for line in completed.stdout.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1
    assert not [line for line in completed.stderr.splitlines() if line.startswith(prefix)]
    diagnostics = json.loads(lines[0][len(prefix):])
    assert diagnostics["status"] == "success" and diagnostics["exit_code"] == 0
    assert diagnostics["summary"]["ticker"] == "0700"
    assert diagnostics["summary"]["filters"] == {"forms": ["FY", "H1"], "start_date": "2018-01-01", "end_date": "2026-10-10", "overwrite": False, "rebuild": True}
    assert set(diagnostics["summary"]["counts"].values()) == {0}
    assert diagnostics["summary"]["terminal_disposition"] == "succeeded"
    assert diagnostics["failed_documents"] == [] and diagnostics["failure"] is None


@pytest.mark.parametrize("quiet", (False, True))
@pytest.mark.parametrize("status", tuple(FinsResultStatus))
def test_cli_main_default_temporary_log_delivers_twelve_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], quiet: bool, status: FinsResultStatus) -> None:
    """验证主入口默认临时日志及 quiet 都交付同一 owner 完整诊断。

    参数：tmp_path 为隔离来源根；monkeypatch 为 Service 装配替换夹具；
        capsys 为标准输出与错误输出捕获夹具；quiet 控制是否使用静默日志选项；
        status 为成功、失败或取消的下载终态。
    返回：无（None）。
    异常：AssertionError，完整性、原通道、退出码或流生命周期不满足断言时抛出。
    """

    summary = _download_summary(source=download_contract.FinsDownloadSource.SEC, failed=12, skipped=11, downloaded=1 if status is not FinsResultStatus.FAILURE else 0)
    terminal = _terminal(summary, status)
    event = FinsEvent(event_type=FinsEventType.RESULT, operation_kind=FinsOperationKind.DOWNLOAD,
        message="下载终态", emitted_at=_NOW, ticker="AAPL", filing_kind=None, document_label=None,
        progress=None, result=terminal)
    service = _FakeFinsDirectService(events=(_progress_event(FinsOperationKind.DOWNLOAD), event))
    factory = Mock(return_value=service)
    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", factory)
    args = ["download", "--base", str(tmp_path / "fresh"), "--ticker", "AAPL"]
    if quiet:
        args.append("--quiet")
    exit_code = cli_main.main(args)
    captured = capsys.readouterr()
    assert exit_code == terminal.exit_code
    expected_stream = captured.out if status is FinsResultStatus.SUCCESS else captured.err
    other_stream = captured.err if status is FinsResultStatus.SUCCESS else captured.out
    prefix = "Fins download diagnostics: "
    lines = [line.removeprefix(prefix) for line in expected_stream.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1 and prefix not in other_stream
    diagnostics = json.loads(lines[0])
    assert diagnostics == terminal.to_download_diagnostics_json_value()
    assert len(diagnostics["failed_documents"]) == 12
    assert diagnostics["summary"]["counts"]["failed"] == 12
    assert len(diagnostics["summary"]["documents"]) == 10
    assert terminal.download_result is not None
    assert f'terminal_disposition="{terminal.download_result.terminal_disposition.value}"' in expected_stream
    assert service.opened_streams[-1].terminal_result is terminal
    assert service.closed_streams == 1 and factory.call_count == 1


@pytest.mark.parametrize("index", (0, 10))
@pytest.mark.parametrize("typed_abort", (False, True))
@pytest.mark.parametrize("race", ("none", "before_claim", "after_claim"))
def test_real_runtime_public_rejection_delivers_unique_safe_cli_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    index: int, typed_abort: bool, race: str,
) -> None:
    """真实 runtime 公共拒绝必须经唯一 RESULT 交付默认 CLI 安全诊断。

    参数：tmp_path 为隔离根；monkeypatch 替外部 adapter、装配和 claim 观察；
        capsys 观察标准流；index 为第一或第十一条 FAILED；typed_abort 控制快照中止；
        race 为取消竞争时点。
    返回：无。
    异常：终态丢失、错误通道、泄漏、非法事实或 claim 后投影时抛出 AssertionError。
    """

    summary = _download_summary(source=download_contract.FinsDownloadSource.SEC, failed=11)
    rows = list(summary.document_rows)
    rows[index] = replace(rows[index], document_id="note /Users/private/file")
    supplied = replace(summary, document_rows=tuple(rows))
    assert supplied.failed_count == 11
    adapter = _PersistedSummaryDownloadAdapter(supplied)
    if typed_abort:
        monkeypatch.setattr(adapter, "download", Mock(side_effect=ingestion_runtime.FinsSourceDownloadAdapterFailure(
            ingestion_runtime.SourceIntegrityRepairRequiredError(), supplied,
        )))
    runtime = _build_ingestion_runtime(tmp_path, executor=_HoldingExecutor(), download_adapters={("sec", "US"): adapter})
    service = FinsDirectCommandService(runtime)
    monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", Mock(return_value=service))
    put = Mock(wraps=ingestion_runtime._put_direct_queue)
    monkeypatch.setattr(ingestion_runtime, "_put_direct_queue", put)
    claims: list[FinsResultStatus | None] = []
    original_claim = ingestion_runtime._DirectStreamCancellationState.claim_terminal
    late_projection = Mock(side_effect=AssertionError("claim 后不得构造下载公共行"))

    # 闭包仅绑定本次竞争观察，仍调用真实 owner 的锁与原子裁决。
    def controlled_claim(state: ingestion_runtime._DirectStreamCancellationState, status: FinsResultStatus) -> FinsResultStatus | None:
        """观察真实 claim 前后竞争，不替换终态算法。

        参数：state 为真实取消 owner；status 为受理终态。
        返回：原 owner 的终态或 None。
        异常：取消时点或请求终态错误时抛出 AssertionError。
        """

        assert status is FinsResultStatus.FAILURE
        if race == "before_claim":
            assert state.request_cancel()
        resolved = original_claim(state, status)
        claims.append(resolved)
        if race == "after_claim":
            assert not state.request_cancel()
            monkeypatch.setattr(direct_events, "_download_public_document", late_projection)
        return resolved

    monkeypatch.setattr(ingestion_runtime._DirectStreamCancellationState, "claim_terminal", controlled_claim)
    exit_code = cli_main.main(("download", "--base", str(tmp_path), "--ticker", "AAPL"))
    captured = capsys.readouterr()
    expected_status = FinsResultStatus.CANCELLED if race == "before_claim" else FinsResultStatus.FAILURE
    assert exit_code == (130 if race == "before_claim" else 1)
    assert claims == [expected_status]
    results = [call.args[1] for call in put.call_args_list if isinstance(call.args[1], FinsEvent) and call.args[1].event_type is FinsEventType.RESULT]
    assert len(results) == 1
    event = results[0]
    assert isinstance(event, FinsEvent) and event.result is not None
    terminal = event.result
    assert terminal.status is expected_status and terminal.download_result is not None
    assert terminal.download_result is not supplied
    assert terminal.download_result.document_rows == ()
    assert terminal.download_result.terminal_disposition is (
        download_contract.FinsDownloadTerminalDisposition.CANCELLED if race == "before_claim"
        else download_contract.FinsDownloadTerminalDisposition.FAILED
    )
    prefix = "Fins download diagnostics: "
    lines = [line.removeprefix(prefix) for line in captured.err.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1 and prefix not in captured.out
    diagnostics = json.loads(lines[0])
    assert diagnostics == terminal.to_download_diagnostics_json_value()
    assert diagnostics["failed_documents"] == [] and diagnostics["summary"]["documents"] == []
    assert set(diagnostics["summary"]["counts"].values()) == {0}
    assert diagnostics["summary"]["ticker"] == "AAPL"
    assert diagnostics["summary"]["filters"] == {"forms": [], "start_date": None, "end_date": None, "overwrite": False, "rebuild": False}
    if race == "before_claim":
        assert diagnostics["failure"] is None and terminal.failure is None
    else:
        assert terminal.failure is not None
        assert terminal.failure.kind is direct_events.FinsPublicFailureKind.EXECUTION
        assert terminal.error_kind is FinsErrorKind.EXECUTION
        assert diagnostics["failure"] == {"classification": "execution", "source": "sec", "transport_category": None,
            "message": "下载执行失败", "retry_hint": "请保存脱敏诊断并排查失败原因后重试。", "reason_code": None}
    assert "MISSING_RESULT" not in captured.out + captured.err
    assert "ended without RESULT" not in captured.out + captured.err
    assert "命令执行失败" not in captured.out + captured.err
    assert "/Users/private/file" not in captured.out + captured.err
    late_projection.assert_not_called()
