"""``dayu-cli`` Fins direct commands 实现。

本模块是 CLI UI adapter：负责把 argparse 结果转换为
``FinsDirectCommandService`` 的显式 direct stream 方法参数，并处理 SIGINT
到当前 async stream cancellation 的映射。CLI 不直接调用 Fins ingestion
runtime，不读取 Fins storage，也不把 direct operation 伪装成 Host Run。
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import signal
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Final, cast

import dayu.runtime.log as runtime_log
from dayu.cli.arg_parsing import (
    COMMAND_DOWNLOAD,
    COMMAND_PROCESS,
    COMMAND_PROCESS_FILING,
    COMMAND_PROCESS_MATERIAL,
    COMMAND_UPLOAD_FILING,
    COMMAND_UPLOAD_FILINGS_FROM,
    COMMAND_UPLOAD_MATERIAL,
    ParsedCliArgs,
)
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.cli.output import (
    render_cli_error,
    render_fins_direct_cancel_requested,
    render_fins_direct_event,
    render_fins_direct_local_exit_after_cancel,
)
from dayu.fins.direct_events import (
    FINS_RESULT_EXIT_CANCELLED,
    FINS_RESULT_EXIT_FAILURE,
    FinsErrorKind,
    FinsEvent,
    FinsEventDetail,
    FinsEventType,
    FinsOperationKind,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.upload_batch import (
    FINS_UPLOAD_FILE_SUFFIXES,
    BatchUploadAction,
    UploadBatchPlanEmptyError,
    UploadBatchPlanEntry,
    UploadBatchPlanRequest,
    UploadBatchPlanUsageError,
    generate_upload_batch_plan,
)
from dayu.service.fins_direct import (
    FinsDirectCommandService,
    FinsDirectUsageError,
)

_BASE_OPTION: Final[str] = "--base"
_TICKER_OPTION: Final[str] = "--ticker"
_INFER_OPTION: Final[str] = "--infer"
_CI_OPTION: Final[str] = "--ci"
_UNSUPPORTED_OPTION_TEMPLATE: Final[str] = "unsupported option {option}: {reason}"
_UNSUPPORTED_INFER_REASON: Final[str] = "当前没有 approved Fins alias inference boundary"
_UNSUPPORTED_CI_REASON: Final[str] = "当前没有 public CI snapshot contract"
_MULTIPLE_MATERIAL_FORMS_MESSAGE: Final[str] = (
    "当前 Fins upload_material request 只支持单个 --forms 值"
)
_EMPTY_TICKER_MESSAGE: Final[str] = "--ticker must not be empty"
_EMPTY_DOCUMENT_ID_MESSAGE: Final[str] = "--document-id must not contain empty item"
_EMPTY_FORM_MESSAGE: Final[str] = "--forms must not contain empty item"
_MISSING_UPLOAD_FILE_TEMPLATE: Final[str] = "upload file does not exist: {path}"
_UPLOAD_PATH_NOT_FILE_TEMPLATE: Final[str] = "upload path is not a file: {path}"
_UPLOAD_SUFFIX_NOT_ALLOWED_TEMPLATE: Final[str] = (
    "upload file suffix is not allowed: {path}"
)
_FINS_DIAGNOSTIC_TEXT_MAX_CHARS: Final[int] = 120
_FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS: Final[int] = 4
_FINS_DIAGNOSTIC_TRUNCATED_SUFFIX: Final[str] = "..."
_FINS_DIRECT_DEBUG_BASE_PART_COUNT: Final[int] = 2
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


class CliFinsUsageError(ValueError):
    """Fins direct CLI 用法错误。"""


@dataclass(frozen=True, slots=True)
class CliTickerInput:
    """CLI ticker CSV 解析结果。

    Attributes:
        canonical: 当前请求使用的 canonical ticker 文本。
        aliases: 用户传入的 ticker 别名。
    """

    canonical: str
    aliases: tuple[str, ...]


class _CliFinsCancellationToken:
    """CLI direct operation 取消 token。"""

    _cancelled: bool
    _reason: str | None
    _requested_at: datetime | None

    def __init__(self) -> None:
        """初始化取消 token。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._cancelled = False
        self._reason = None
        self._requested_at = None

    def request_cancel(self, reason: str) -> None:
        """请求取消当前 direct operation。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._cancelled:
            return
        self._cancelled = True
        self._reason = reason
        self._requested_at = datetime.now(timezone.utc)

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        :returns: 已请求取消返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self._cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 取消原因；未取消时返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return self._reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 请求取消的 UTC 时间；未取消时返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return self._requested_at


class _FinsSigintMonitor:
    """Fins direct operation 运行阶段的 SIGINT 观察器。"""

    count: int
    _event: asyncio.Event
    _loop: asyncio.AbstractEventLoop | None
    _installed: bool

    def __init__(self) -> None:
        """初始化 SIGINT monitor。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.count = 0
        self._event = asyncio.Event()
        self._loop = None
        self._installed = False

    def install(self) -> None:
        """在当前事件循环安装 SIGINT handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常；不支持 signal handler 的平台保留
            默认 KeyboardInterrupt 行为。
        """

        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGINT, self.notify)
        except (NotImplementedError, RuntimeError):
            self._installed = False
            self._loop = None
            return
        self._installed = True
        self._loop = loop

    def close(self) -> None:
        """移除当前 monitor 安装的 SIGINT handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._installed and self._loop is not None:
            self._loop.remove_signal_handler(signal.SIGINT)
        self._installed = False
        self._loop = None

    def notify(self, _signal_number: int | None = None, _frame: FrameType | None = None) -> None:
        """记录一次 SIGINT。

        :param _signal_number: ``signal.signal`` 风格 handler 兼容参数。
        :param _frame: ``signal.signal`` 风格 handler 兼容参数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.count += 1
        self._event.set()

    async def wait_next(self, observed_count: int) -> int:
        """等待下一次 SIGINT。

        :param observed_count: 调用方已经观察到的 SIGINT 计数。
        :returns: 新的 SIGINT 计数。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        while self.count <= observed_count:
            await self._event.wait()
            self._event.clear()
        return self.count


FinsDirectServiceFactory = Callable[[Path], FinsDirectCommandService]
FINS_DIRECT_SERVICE_FACTORY: FinsDirectServiceFactory = (
    FinsDirectCommandService.from_workspace_root
)


def run_fins_direct_command(args: ParsedCliArgs) -> int:
    """执行 Fins direct command。

    :param args: argparse 已解析的 Fins direct 命令参数。
    :returns: CLI 退出码。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    try:
        return asyncio.run(_run_fins_direct_command_async(args))
    except CliFinsUsageError as exc:
        render_cli_error(f"dayu-cli {args.command_name}: {exc}")
        return EXIT_USAGE_ERROR
    except UploadBatchPlanUsageError as exc:
        render_cli_error(f"dayu-cli {args.command_name}: {exc}")
        return EXIT_USAGE_ERROR
    except UploadBatchPlanEmptyError as exc:
        render_cli_error(f"dayu-cli {args.command_name}: {exc}")
        return EXIT_FAILURE
    except FinsDirectUsageError as exc:
        render_cli_error(f"dayu-cli {args.command_name}: {exc}")
        return EXIT_USAGE_ERROR
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
    except Exception as exc:
        render_cli_error(f"dayu-cli {args.command_name}: {exc}")
        return EXIT_FAILURE


async def _run_fins_direct_command_async(args: ParsedCliArgs) -> int:
    """异步执行 Fins direct command 主流程。

    :param args: argparse 已解析的 Fins direct 命令参数。
    :returns: CLI 退出码。
    :raises CliFinsUsageError: 用户输入参数非法或命令未支持时抛出。
    :raises Exception: Service 或 runtime 执行失败时向上抛出。
    """

    runtime_log.log_verbose(
        _LOGGER,
        "Fins direct command start; command=%s",
        args.command_name,
    )
    if args.command_name == COMMAND_UPLOAD_FILINGS_FROM:
        return _run_upload_filings_from(args)
    _raise_for_unsupported_flags(args)
    workspace_root = _resolve_workspace_root(args.workspace_root)
    service = FINS_DIRECT_SERVICE_FACTORY(workspace_root)
    cancellation_token = _CliFinsCancellationToken()
    stream = _open_direct_stream(
        args=args,
        service=service,
        cancellation_token=cancellation_token,
    )
    runtime_log.log_verbose(
        _LOGGER,
        "Fins direct stream opened; command=%s",
        args.command_name,
    )
    terminal = await _wait_for_terminal_handling_sigint(
        events=stream,
        cancellation_token=cancellation_token,
        sigint_monitor=_FinsSigintMonitor(),
        command_name=args.command_name,
    )
    return terminal.exit_code


def _run_upload_filings_from(args: ParsedCliArgs) -> int:
    """执行 ``upload_filings_from`` 本地计划生成。

    :param args: argparse 已解析的 upload_filings_from 参数。
    :returns: CLI 退出码。
    :raises CliFinsUsageError: ticker 或 source dir 参数非法时抛出。
    :raises UploadBatchPlanUsageError: Fins batch helper 判断输入非法时抛出。
    :raises UploadBatchPlanEmptyError: 源目录无可识别文件时抛出。
    :raises OSError: 输出文件写入失败时由底层抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    if args.source_dir is None or args.source_dir.strip() == "":
        raise CliFinsUsageError("--from must not be empty")
    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(
            ticker=ticker.canonical,
            source_dir=Path(args.source_dir),
            action=cast(BatchUploadAction, args.action),
            recursive=args.recursive,
            fiscal_year=args.fiscal_year,
            fiscal_period=_optional_stripped_text(args.fiscal_period),
            amended=args.amended,
            filing_date=_optional_stripped_text(args.filing_date),
            report_date=_optional_stripped_text(args.report_date),
            company_name=_optional_stripped_text(args.company_name),
            material_forms=_normalized_text_tuple(
                args.material_forms,
                field_name="--material-forms",
            ),
        )
    )
    script = _render_upload_batch_script(plan.entries)
    if args.output is None:
        print(script, end="")
        return EXIT_SUCCESS
    output_path = Path(args.output).expanduser().resolve(strict=False)
    output_path.write_text(script, encoding="utf-8")
    return EXIT_SUCCESS


def _render_upload_batch_script(entries: tuple[UploadBatchPlanEntry, ...]) -> str:
    """把结构化上传计划渲染为 ``dayu-cli`` 命令脚本。

    :param entries: Fins batch helper 返回的结构化计划条目。
    :returns: shell 可执行的命令脚本文本。
    :raises Exception: 不主动抛出异常。
    """

    lines = tuple(_render_upload_batch_command(entry) for entry in entries)
    return "\n".join(lines) + "\n"


def _render_upload_batch_command(entry: UploadBatchPlanEntry) -> str:
    """渲染单条上传命令。

    :param entry: 结构化上传计划条目。
    :returns: shell quoted 命令行。
    :raises Exception: 不主动抛出异常。
    """

    parts = [
        "dayu-cli",
        entry.command_name,
        "--ticker",
        entry.ticker,
        "--action",
        entry.action,
    ]
    if entry.command_name == COMMAND_UPLOAD_MATERIAL:
        if entry.form_type is not None:
            parts.extend(("--forms", entry.form_type))
        if entry.material_name is not None:
            parts.extend(("--material-name", entry.material_name))
    parts.append("--files")
    parts.extend(str(path) for path in entry.files)
    _append_optional_entry_metadata(parts, entry)
    return shlex.join(parts)


def _append_optional_entry_metadata(
    parts: list[str],
    entry: UploadBatchPlanEntry,
) -> None:
    """向命令参数列表追加可选 metadata flags。

    :param parts: 正在构造的命令参数列表。
    :param entry: 结构化上传计划条目。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if entry.fiscal_year is not None:
        parts.extend(("--fiscal-year", str(entry.fiscal_year)))
    if entry.fiscal_period is not None:
        parts.extend(("--fiscal-period", entry.fiscal_period))
    if entry.amended:
        parts.append("--amended")
    if entry.filing_date is not None:
        parts.extend(("--filing-date", entry.filing_date))
    if entry.report_date is not None:
        parts.extend(("--report-date", entry.report_date))
    if entry.company_name is not None:
        parts.extend(("--company-name", entry.company_name))


def _open_direct_stream(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
) -> AsyncIterator[FinsEvent]:
    """按命令名打开 direct event stream。

    :param args: argparse 已解析的 Fins direct 命令参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins direct 事件异步迭代器。
    :raises CliFinsUsageError: 命令或用户输入非法时抛出。
    :raises Exception: Service 打开 stream 失败时向上抛出。
    """

    if args.command_name == COMMAND_DOWNLOAD:
        return _download_stream(args=args, service=service, cancellation_token=cancellation_token)
    if args.command_name == COMMAND_UPLOAD_FILING:
        return _upload_filing_stream(
            args=args,
            service=service,
            cancellation_token=cancellation_token,
        )
    if args.command_name == COMMAND_UPLOAD_MATERIAL:
        return _upload_material_stream(
            args=args,
            service=service,
            cancellation_token=cancellation_token,
        )
    if args.command_name == COMMAND_PROCESS:
        return _process_stream(args=args, service=service, cancellation_token=cancellation_token)
    if args.command_name == COMMAND_PROCESS_FILING:
        return _process_filing_stream(
            args=args,
            service=service,
            cancellation_token=cancellation_token,
        )
    if args.command_name == COMMAND_PROCESS_MATERIAL:
        return _process_material_stream(
            args=args,
            service=service,
            cancellation_token=cancellation_token,
        )
    raise CliFinsUsageError(f"unsupported fins direct command: {args.command_name}")


def _download_stream(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
) -> AsyncIterator[FinsEvent]:
    """打开 download direct stream。

    :param args: argparse 已解析的 download 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins direct 事件异步迭代器。
    :raises CliFinsUsageError: ticker 或 forms 输入非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    return service.download(
        ticker=ticker.canonical,
        form_types=_normalized_text_tuple(args.forms, field_name="--forms"),
        filed_after=_optional_stripped_text(args.start),
        filed_before=_optional_stripped_text(args.end),
        overwrite_existing=args.overwrite,
        rebuild_processed=args.rebuild,
        cancellation_token=cancellation_token,
    )


def _upload_filing_stream(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
) -> AsyncIterator[FinsEvent]:
    """打开 upload_filing direct stream。

    :param args: argparse 已解析的 upload_filing 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins direct 事件异步迭代器。
    :raises CliFinsUsageError: ticker 或文件路径非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    return service.upload_filing(
        ticker=ticker.canonical,
        action=args.action,
        files=_validated_upload_files(args.files),
        fiscal_year=args.fiscal_year,
        fiscal_period=_optional_stripped_text(args.fiscal_period),
        amended=args.amended,
        filing_date=_optional_stripped_text(args.filing_date),
        report_date=_optional_stripped_text(args.report_date),
        company_name=_optional_stripped_text(args.company_name),
        ticker_aliases=ticker.aliases,
        overwrite=args.overwrite,
        cancellation_token=cancellation_token,
    )


def _upload_material_stream(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
) -> AsyncIterator[FinsEvent]:
    """打开 upload_material direct stream。

    :param args: argparse 已解析的 upload_material 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins direct 事件异步迭代器。
    :raises CliFinsUsageError: ticker、forms 或文件路径非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    form_type = _single_optional_form(args.forms)
    return service.upload_material(
        ticker=ticker.canonical,
        action=args.action,
        files=_validated_upload_files(args.files),
        form_type=form_type,
        material_name=_optional_stripped_text(args.material_name),
        document_id=_optional_stripped_text(_single_document_id(args.document_id)),
        internal_document_id=_optional_stripped_text(args.internal_document_id),
        fiscal_year=args.fiscal_year,
        fiscal_period=_optional_stripped_text(args.fiscal_period),
        amended=args.amended,
        filing_date=_optional_stripped_text(args.filing_date),
        report_date=_optional_stripped_text(args.report_date),
        company_name=_optional_stripped_text(args.company_name),
        ticker_aliases=ticker.aliases,
        overwrite=args.overwrite,
        cancellation_token=cancellation_token,
    )


def _process_stream(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
) -> AsyncIterator[FinsEvent]:
    """打开 process direct stream。

    :param args: argparse 已解析的 process 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins direct 事件异步迭代器。
    :raises CliFinsUsageError: ticker 或 document id 输入非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    return service.process(
        ticker=ticker.canonical,
        source_kind=SourceKind.FILING,
        document_ids=_document_ids_from_arg(args.document_id),
        rebuild_processed=args.overwrite,
        cancellation_token=cancellation_token,
    )


def _process_filing_stream(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
) -> AsyncIterator[FinsEvent]:
    """打开 process_filing direct stream。

    :param args: argparse 已解析的 process_filing 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins direct 事件异步迭代器。
    :raises CliFinsUsageError: ticker 或 document id 输入非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    document_id = _required_single_document_id(args.document_id)
    return service.process_filing(
        ticker=ticker.canonical,
        document_ids=(document_id,),
        rebuild_processed=args.overwrite,
        cancellation_token=cancellation_token,
    )


def _process_material_stream(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
) -> AsyncIterator[FinsEvent]:
    """打开 process_material direct stream。

    :param args: argparse 已解析的 process_material 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins direct 事件异步迭代器。
    :raises CliFinsUsageError: ticker 或 document id 输入非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    document_id = _required_single_document_id(args.document_id)
    return service.process_material(
        ticker=ticker.canonical,
        document_ids=(document_id,),
        rebuild_processed=args.overwrite,
        cancellation_token=cancellation_token,
    )


async def _wait_for_terminal_handling_sigint(
    *,
    events: AsyncIterator[FinsEvent],
    cancellation_token: _CliFinsCancellationToken,
    sigint_monitor: _FinsSigintMonitor,
    command_name: str,
) -> FinsResultSummary:
    """等待 direct stream 终态并处理运行中 SIGINT。

    :param events: Fins direct event stream。
    :param cancellation_token: 当前 operation 的取消 token。
    :param sigint_monitor: SIGINT 观察器。
    :param command_name: 用户可见命令名，用于诊断。
    :returns: direct stream 终态摘要。
    :raises Exception: stream 消费失败时向上抛出。
    """

    sigint_monitor.install()
    event_task = asyncio.create_task(_consume_fins_direct_events(events))
    observed_count = sigint_monitor.count
    sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_count))
    try:
        while True:
            await asyncio.wait(
                (event_task, sigint_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if event_task.done():
                sigint_task.cancel()
                return await event_task
            if sigint_task.done():
                observed_count = sigint_task.result()
                runtime_log.log_verbose(
                    _LOGGER,
                    "Fins direct stream cancel requested; command=%s sigint_count=%s",
                    command_name,
                    observed_count,
                )
                cancellation_token.request_cancel("keyboard_interrupt")
                event_task.cancel()
                render_fins_direct_cancel_requested()
                try:
                    terminal_result = await event_task
                except asyncio.CancelledError:
                    pass
                else:
                    return terminal_result
                render_fins_direct_local_exit_after_cancel()
                return _cancelled_result_summary()
    finally:
        sigint_monitor.close()
        sigint_task.cancel()
        if not event_task.done():
            event_task.cancel()


async def _consume_fins_direct_events(
    events: AsyncIterator[FinsEvent],
) -> FinsResultSummary:
    """消费 Service event stream 并输出 Fins direct 事件。

    :param events: Fins direct event stream。
    :returns: event stream 产出的 terminal result summary。
    :raises RuntimeError: event stream 结束但没有 terminal result 时抛出。
    :raises Exception: Service stream 或输出失败时向上抛出。
    """

    async for event in events:
        _log_fins_direct_event_received(event)
        render_fins_direct_event(event)
        if event.result is not None:
            runtime_log.log_verbose(
                _LOGGER,
                "Fins direct terminal closeout; operation=%s status=%s exit_code=%s",
                event.operation_kind.value,
                event.result.status.value,
                event.result.exit_code,
            )
            return event.result
    missing_result = _missing_result_event()
    render_fins_direct_event(missing_result)
    result = missing_result.result
    if result is None:
        raise RuntimeError("missing-result event did not contain result")
    return result


def _log_fins_direct_event_received(event: FinsEvent) -> None:
    """记录 Fins direct event 的有界诊断信息。

    :param event: Service direct stream 产出的 Fins direct event。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    runtime_log.log_verbose(
        _LOGGER,
        "Fins direct event received; %s",
        " ".join(_fins_event_verbose_diagnostic_parts(event)),
    )
    debug_parts = _fins_event_debug_diagnostic_parts(event)
    if len(debug_parts) > _FINS_DIRECT_DEBUG_BASE_PART_COUNT:
        _LOGGER.debug(
            "Fins direct event detail; %s",
            " ".join(debug_parts),
        )


def _fins_event_verbose_diagnostic_parts(event: FinsEvent) -> tuple[str, ...]:
    """生成 VERBOSE 级别 Fins event 诊断片段。

    :param event: Service direct stream 产出的 Fins direct event。
    :returns: 有界、业务可读的 ``key=value`` 片段。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = [
        f"operation={event.operation_kind.value}",
        f"event_type={event.event_type.value}",
    ]
    _append_optional_diagnostic_part(parts, "ticker", event.ticker)
    _append_optional_diagnostic_part(parts, "document", event.document_label)
    if event.progress is not None:
        _append_optional_diagnostic_part(parts, "stage", event.progress.stage)
    if event.result is not None:
        parts.append(f"status={event.result.status.value}")
    _append_optional_diagnostic_part(parts, "message", event.message)
    return tuple(parts)


def _fins_event_debug_diagnostic_parts(event: FinsEvent) -> tuple[str, ...]:
    """生成 DEBUG 级别 Fins event 诊断片段。

    :param event: Service direct stream 产出的 Fins direct event。
    :returns: 有界、业务可读的 ``key=value`` 片段。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = [
        f"operation={event.operation_kind.value}",
        f"event_type={event.event_type.value}",
    ]
    _append_optional_diagnostic_part(parts, "filing_kind", event.filing_kind)
    if event.progress is not None:
        _append_optional_int_diagnostic_part(
            parts,
            "completed_units",
            event.progress.completed_units,
        )
        _append_optional_int_diagnostic_part(
            parts,
            "total_units",
            event.progress.total_units,
        )
    if event.result is not None:
        parts.append(f"status={event.result.status.value}")
        _append_optional_diagnostic_part(parts, "title", event.result.title)
        if event.result.error_kind is not None:
            parts.append(f"error_kind={event.result.error_kind.value}")
        parts.append(f"exit_code={event.result.exit_code}")
        _append_result_details_diagnostic_parts(parts, event.result.details)
    return tuple(parts)


def _append_optional_diagnostic_part(
    parts: list[str],
    key: str,
    value: str | None,
) -> None:
    """追加可选文本诊断片段。

    :param parts: 待追加的片段列表。
    :param key: 诊断字段名。
    :param value: 可选字段值。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None or value.strip() == "":
        return
    parts.append(f"{key}={_quoted_diagnostic_text(value)}")


def _append_optional_int_diagnostic_part(
    parts: list[str],
    key: str,
    value: int | None,
) -> None:
    """追加可选整数诊断片段。

    :param parts: 待追加的片段列表。
    :param key: 诊断字段名。
    :param value: 可选整数值。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return
    parts.append(f"{key}={value}")


def _append_result_details_diagnostic_parts(
    parts: list[str],
    details: tuple[FinsEventDetail, ...],
) -> None:
    """追加有界 result details 诊断片段。

    :param parts: 待追加的片段列表。
    :param details: Fins direct result details。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    rendered: list[str] = []
    for detail in details:
        if len(rendered) >= _FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS:
            break
        rendered.append(
            f"{_bounded_diagnostic_text(detail.label)}="
            f"{_quoted_diagnostic_text(detail.value)}"
        )
    if rendered:
        parts.append(f"details={','.join(rendered)}")


def _quoted_diagnostic_text(value: str) -> str:
    """把诊断文本渲染为有界 shell 风格 token。

    :param value: 原始诊断文本。
    :returns: 适合日志中单行展示的有界 token。
    :raises Exception: 不主动抛出异常。
    """

    return shlex.quote(_bounded_diagnostic_text(value))


def _bounded_diagnostic_text(value: str) -> str:
    """截断诊断文本，避免日志输出体积失控。

    :param value: 原始诊断文本。
    :returns: 长度受限的诊断文本。
    :raises Exception: 不主动抛出异常。
    """

    if len(value) <= _FINS_DIAGNOSTIC_TEXT_MAX_CHARS:
        return value
    return value[
        : _FINS_DIAGNOSTIC_TEXT_MAX_CHARS - len(_FINS_DIAGNOSTIC_TRUNCATED_SUFFIX)
    ] + _FINS_DIAGNOSTIC_TRUNCATED_SUFFIX


def _missing_result_event() -> FinsEvent:
    """构造 direct stream 无 RESULT 时的 failure event。

    :returns: failure RESULT 事件。
    :raises ValueError: 构造出的事件违反 direct contract 时抛出。
    """

    return FinsEvent(
        event_type=FinsEventType.RESULT,
        operation_kind=FinsOperationKind.PREPROCESS,
        message="Fins direct stream ended without result",
        emitted_at=datetime.now(timezone.utc),
        ticker=None,
        filing_kind=None,
        document_label=None,
        progress=None,
        result=FinsResultSummary(
            status=FinsResultStatus.FAILURE,
            exit_code=FINS_RESULT_EXIT_FAILURE,
            title="Fins direct operation failed",
            details=(),
            error_kind=FinsErrorKind.EXECUTION,
            error_message="Fins direct stream ended without result",
        ),
    )


def _cancelled_result_summary() -> FinsResultSummary:
    """构造 CLI 本地取消终态摘要。

    :returns: cancelled result summary。
    :raises ValueError: 构造出的摘要违反 direct contract 时抛出。
    """

    return FinsResultSummary(
        status=FinsResultStatus.CANCELLED,
        exit_code=FINS_RESULT_EXIT_CANCELLED,
        title="Fins direct operation cancelled",
        details=(FinsEventDetail(label="reason", value="keyboard_interrupt"),),
        error_kind=FinsErrorKind.CANCELLED,
        error_message="cancelled",
    )


def _raise_for_unsupported_flags(args: ParsedCliArgs) -> None:
    """对当前无 approved boundary 的旧 flag fail fast。

    :param args: argparse 已解析的 Fins direct 命令参数。
    :returns: ``None``。
    :raises CliFinsUsageError: 发现 unsupported flag 时抛出。
    """

    if args.infer:
        raise CliFinsUsageError(
            _UNSUPPORTED_OPTION_TEMPLATE.format(
                option=_INFER_OPTION,
                reason=_UNSUPPORTED_INFER_REASON,
            )
        )
    if args.ci:
        raise CliFinsUsageError(
            _UNSUPPORTED_OPTION_TEMPLATE.format(
                option=_CI_OPTION,
                reason=_UNSUPPORTED_CI_REASON,
            )
        )


def _resolve_workspace_root(raw_value: str) -> Path:
    """解析 CLI workspace root。

    :param raw_value: ``--base`` / ``--workspace`` 原始值。
    :returns: 解析后的绝对路径。
    :raises CliFinsUsageError: 路径为空时抛出。
    """

    if raw_value.strip() == "":
        raise CliFinsUsageError(f"{_BASE_OPTION} must not be empty")
    return Path(raw_value).expanduser().resolve(strict=False)


def _parse_ticker_csv(raw_value: str | None) -> CliTickerInput:
    """解析 ticker CSV 为 canonical ticker 与 aliases。

    :param raw_value: ``--ticker`` 原始值。
    :returns: CLI ticker 输入。
    :raises CliFinsUsageError: ticker 缺失或 canonical 为空时抛出。
    """

    if raw_value is None:
        raise CliFinsUsageError(_EMPTY_TICKER_MESSAGE)
    parts = tuple(part.strip() for part in raw_value.split(","))
    canonical = parts[0] if parts else ""
    if canonical == "":
        raise CliFinsUsageError(_EMPTY_TICKER_MESSAGE)
    aliases = tuple(part for part in parts[1:] if part != "")
    return CliTickerInput(canonical=canonical, aliases=aliases)


def _validated_upload_files(raw_files: list[str] | None) -> tuple[Path, ...]:
    """校验并解析 upload 文件路径。

    :param raw_files: CLI 收到的 ``--files`` 值。
    :returns: 已解析绝对路径元组。
    :raises CliFinsUsageError: 文件不存在、不是普通文件或后缀不在 allowlist 时抛出。
    """

    if raw_files is None:
        return ()
    paths: list[Path] = []
    for raw_file in raw_files:
        path = Path(raw_file).expanduser().resolve(strict=False)
        if not path.exists():
            raise CliFinsUsageError(
                _MISSING_UPLOAD_FILE_TEMPLATE.format(path=path)
            )
        if not path.is_file():
            raise CliFinsUsageError(
                _UPLOAD_PATH_NOT_FILE_TEMPLATE.format(path=path)
            )
        if path.suffix.lower() not in FINS_UPLOAD_FILE_SUFFIXES:
            raise CliFinsUsageError(
                _UPLOAD_SUFFIX_NOT_ALLOWED_TEMPLATE.format(path=path)
            )
        paths.append(path)
    return tuple(paths)


def _normalized_text_tuple(
    values: list[str] | None,
    *,
    field_name: str,
) -> tuple[str, ...]:
    """把 argparse 文本列表规范成非空字符串元组。

    :param values: argparse 文本列表。
    :param field_name: 字段名，用于错误消息。
    :returns: 规范化文本元组。
    :raises CliFinsUsageError: 任一项目为空时抛出。
    """

    if values is None:
        return ()
    normalized: list[str] = []
    for value in values:
        for item in value.split(","):
            stripped = item.strip()
            if stripped == "":
                if field_name == "--forms":
                    raise CliFinsUsageError(_EMPTY_FORM_MESSAGE)
                raise CliFinsUsageError(f"{field_name} must not contain empty item")
            normalized.append(stripped)
    return tuple(normalized)


def _single_optional_form(values: list[str] | None) -> str | None:
    """读取 upload_material 当前支持的单个 form_type。

    :param values: ``--forms`` 输入。
    :returns: 单个 form type；未传入时返回 ``None``。
    :raises CliFinsUsageError: 传入多个 form 时抛出。
    """

    normalized = _normalized_text_tuple(values, field_name="--forms")
    if len(normalized) > 1:
        raise CliFinsUsageError(_MULTIPLE_MATERIAL_FORMS_MESSAGE)
    if not normalized:
        return None
    return normalized[0]


def _document_ids_from_arg(raw_value: str | list[str] | None) -> tuple[str, ...]:
    """解析可重复或逗号分隔的 document id 输入。

    :param raw_value: argparse 中的 document id 字段。
    :returns: document id 元组。
    :raises CliFinsUsageError: 任一 document id 为空时抛出。
    """

    if raw_value is None:
        return ()
    raw_values = (raw_value,) if isinstance(raw_value, str) else tuple(raw_value)
    document_ids: list[str] = []
    for raw_item in raw_values:
        for item in raw_item.split(","):
            stripped = item.strip()
            if stripped == "":
                raise CliFinsUsageError(_EMPTY_DOCUMENT_ID_MESSAGE)
            document_ids.append(stripped)
    return tuple(document_ids)


def _single_document_id(raw_value: str | list[str] | None) -> str | None:
    """读取可选单个 document id。

    :param raw_value: argparse 中的 document id 字段。
    :returns: 单个 document id；未传入时返回 ``None``。
    :raises CliFinsUsageError: 输入多于一个 document id 时抛出。
    """

    document_ids = _document_ids_from_arg(raw_value)
    document_id_count = len(document_ids)
    if document_id_count == 0:
        return None
    if document_id_count == 1:
        return document_ids[0]
    raise CliFinsUsageError("--document-id only accepts one value here")


def _required_single_document_id(raw_value: str | list[str] | None) -> str:
    """读取必填单个 document id。

    :param raw_value: argparse 中的 document id 字段。
    :returns: 单个 document id。
    :raises CliFinsUsageError: 输入为空或多于一个 document id 时抛出。
    """

    document_id = _single_document_id(raw_value)
    if document_id is None:
        raise CliFinsUsageError("--document-id is required")
    return document_id


def _optional_stripped_text(value: str | None) -> str | None:
    """规范化可选文本。

    :param value: 原始文本。
    :returns: 去除首尾空白后的文本；空白或 ``None`` 返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    return stripped


__all__: tuple[str, ...] = (
    "FINS_DIRECT_SERVICE_FACTORY",
    "FinsDirectServiceFactory",
    "run_fins_direct_command",
)
