"""``dayu-cli`` Fins direct commands 实现。

本模块是 CLI UI adapter：负责把 argparse 结果转换为
``FinsDirectCommandService`` 的显式方法参数，并处理 SIGINT 到 durable
Fins job cancel 的映射。CLI 不直接调用 Fins ingestion runtime，不读取
Fins storage，也不把 direct job 伪装成 Host Run。
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import signal
from collections.abc import Callable
from dataclasses import dataclass
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
    FinsDirectJobEvent,
    FinsDirectJobHandle,
    FinsDirectTerminalResult,
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


class _FinsSigintMonitor:
    """Fins direct job 运行阶段的 SIGINT 观察器。"""

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
    handle = _start_direct_job(args=args, service=service)
    runtime_log.log_verbose(
        _LOGGER,
        "Fins direct job started; command=%s job_id=%s initial_status=%s",
        handle.start_request.command_name,
        handle.job_id,
        handle.initial_status.value,
    )
    terminal = await _wait_for_terminal_handling_sigint(
        service=service,
        handle=handle,
        sigint_monitor=_FinsSigintMonitor(),
    )
    if terminal is None:
        return EXIT_KEYBOARD_INTERRUPT
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


def _start_direct_job(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
) -> FinsDirectJobHandle:
    """按命令名启动 direct job。

    :param args: argparse 已解析的 Fins direct 命令参数。
    :param service: Fins direct Service helper。
    :returns: direct job handle。
    :raises CliFinsUsageError: 命令或用户输入非法时抛出。
    :raises Exception: Service 启动 job 失败时向上抛出。
    """

    if args.command_name == COMMAND_DOWNLOAD:
        return _start_download(args=args, service=service)
    if args.command_name == COMMAND_UPLOAD_FILING:
        return _start_upload_filing(args=args, service=service)
    if args.command_name == COMMAND_UPLOAD_MATERIAL:
        return _start_upload_material(args=args, service=service)
    if args.command_name == COMMAND_PROCESS:
        return _start_process(args=args, service=service)
    if args.command_name == COMMAND_PROCESS_FILING:
        return _start_process_filing(args=args, service=service)
    if args.command_name == COMMAND_PROCESS_MATERIAL:
        return _start_process_material(args=args, service=service)
    raise CliFinsUsageError(f"unsupported fins direct command: {args.command_name}")


def _start_download(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
) -> FinsDirectJobHandle:
    """启动 download direct job。

    :param args: argparse 已解析的 download 参数。
    :param service: Fins direct Service helper。
    :returns: direct job handle。
    :raises CliFinsUsageError: ticker 或 forms 输入非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    return service.start_download(
        ticker=ticker.canonical,
        form_types=_normalized_text_tuple(args.forms, field_name="--forms"),
        filed_after=_optional_stripped_text(args.start),
        filed_before=_optional_stripped_text(args.end),
        overwrite_existing=args.overwrite,
        rebuild_processed=args.rebuild,
    )


def _start_upload_filing(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
) -> FinsDirectJobHandle:
    """启动 upload_filing direct job。

    :param args: argparse 已解析的 upload_filing 参数。
    :param service: Fins direct Service helper。
    :returns: direct job handle。
    :raises CliFinsUsageError: ticker 或文件路径非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    return service.start_upload_filing(
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
    )


def _start_upload_material(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
) -> FinsDirectJobHandle:
    """启动 upload_material direct job。

    :param args: argparse 已解析的 upload_material 参数。
    :param service: Fins direct Service helper。
    :returns: direct job handle。
    :raises CliFinsUsageError: ticker、forms 或文件路径非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    form_type = _single_optional_form(args.forms)
    return service.start_upload_material(
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
    )


def _start_process(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
) -> FinsDirectJobHandle:
    """启动 process direct job。

    :param args: argparse 已解析的 process 参数。
    :param service: Fins direct Service helper。
    :returns: direct job handle。
    :raises CliFinsUsageError: ticker 或 document id 输入非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    return service.start_preprocess(
        command_name=COMMAND_PROCESS,
        ticker=ticker.canonical,
        source_kind=SourceKind.FILING,
        document_ids=_document_ids_from_arg(args.document_id),
        rebuild_processed=args.overwrite,
    )


def _start_process_filing(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
) -> FinsDirectJobHandle:
    """启动 process_filing direct job。

    :param args: argparse 已解析的 process_filing 参数。
    :param service: Fins direct Service helper。
    :returns: direct job handle。
    :raises CliFinsUsageError: ticker 或 document id 输入非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    document_id = _required_single_document_id(args.document_id)
    return service.start_preprocess(
        command_name=COMMAND_PROCESS_FILING,
        ticker=ticker.canonical,
        source_kind=SourceKind.FILING,
        document_ids=(document_id,),
        rebuild_processed=args.overwrite,
    )


def _start_process_material(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
) -> FinsDirectJobHandle:
    """启动 process_material direct job。

    :param args: argparse 已解析的 process_material 参数。
    :param service: Fins direct Service helper。
    :returns: direct job handle。
    :raises CliFinsUsageError: ticker 或 document id 输入非法时抛出。
    """

    ticker = _parse_ticker_csv(args.ticker)
    document_id = _required_single_document_id(args.document_id)
    return service.start_preprocess(
        command_name=COMMAND_PROCESS_MATERIAL,
        ticker=ticker.canonical,
        source_kind=SourceKind.MATERIAL,
        document_ids=(document_id,),
        rebuild_processed=args.overwrite,
    )


async def _wait_for_terminal_handling_sigint(
    *,
    service: FinsDirectCommandService,
    handle: FinsDirectJobHandle,
    sigint_monitor: _FinsSigintMonitor,
) -> FinsDirectTerminalResult | None:
    """等待 direct job 终态并处理运行中 SIGINT。

    :param service: Fins direct Service helper。
    :param handle: 已启动 direct job handle。
    :param sigint_monitor: SIGINT 观察器。
    :returns: terminal result；第二次 SIGINT 本地退出时返回 ``None``。
    :raises Exception: wait 或 cancel runtime 失败时向上抛出。
    """

    sigint_monitor.install()
    event_task = asyncio.create_task(
        _consume_fins_direct_events(service=service, handle=handle)
    )
    observed_count = sigint_monitor.count
    sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_count))
    cancel_requested = False
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
                if cancel_requested:
                    event_task.cancel()
                    render_fins_direct_local_exit_after_cancel(handle.job_id)
                    return None
                runtime_log.log_verbose(
                    _LOGGER,
                    "Fins direct cancel requested; job_id=%s sigint_count=%s",
                    handle.job_id,
                    observed_count,
                )
                service.request_cancel(handle.job_id)
                cancel_requested = True
                render_fins_direct_cancel_requested(handle.job_id)
                sigint_task = asyncio.create_task(
                    sigint_monitor.wait_next(observed_count)
                )
    finally:
        sigint_monitor.close()
        sigint_task.cancel()
        if not event_task.done():
            event_task.cancel()


async def _consume_fins_direct_events(
    *,
    service: FinsDirectCommandService,
    handle: FinsDirectJobHandle,
) -> FinsDirectTerminalResult:
    """消费 Service event stream 并输出 Fins direct job 事件。

    :param service: Fins direct Service helper。
    :param handle: 已启动 direct job handle。
    :returns: event stream 产出的 terminal result。
    :raises RuntimeError: event stream 结束但没有 terminal result 时抛出。
    :raises Exception: Service stream 或输出失败时向上抛出。
    """

    async for event in service.stream_job_events_until_terminal(handle):
        _log_fins_direct_event_received(event)
        render_fins_direct_event(event)
        if event.terminal_result is not None:
            runtime_log.log_verbose(
                _LOGGER,
                "Fins direct terminal closeout; command=%s job_id=%s status=%s exit_code=%s",
                event.command_name,
                event.job_id,
                event.terminal_result.status.value,
                event.terminal_result.exit_code,
            )
            return event.terminal_result
    raise RuntimeError(
        f"Fins direct event stream ended without terminal result: {handle.job_id}"
    )


def _log_fins_direct_event_received(event: FinsDirectJobEvent) -> None:
    """记录 Fins direct event 的有界诊断信息。

    :param event: Service event stream 投影出的 Fins direct job event。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    runtime_log.log_verbose(
        _LOGGER,
        "Fins direct event received; command=%s job_id=%s event=%s",
        event.command_name,
        event.job_id,
        event.event_label,
    )
    _LOGGER.debug(
        "Fins direct event detail; job_id=%s sequence=%s event=%s status=%s "
        "payload_key_count=%s payload_keys=%s",
        event.job_id,
        event.sequence,
        event.event_label,
        None if event.status is None else event.status.value,
        len(event.payload),
        runtime_log.bounded_payload_keys(event.payload),
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
