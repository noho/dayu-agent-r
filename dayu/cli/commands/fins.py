"""``dayu-cli`` Fins direct commands 实现。

本模块是 CLI UI adapter：负责把 argparse 结果转换为
``FinsDirectCommandService`` 的显式 direct stream 方法参数，并处理 SIGINT
到当前 async stream cancellation 的映射。CLI 不直接调用 Fins ingestion
runtime，不读取 Fins storage，也不把 direct operation 伪装成 Host Run。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, NoReturn, cast

import dayu.runtime.log as runtime_log
from dayu.cli.agent_entrypoint import CliSigintMonitor
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
from dayu.cli.upload_script import (
    current_upload_script_platform,
    publish_upload_script,
    render_upload_script,
)
from dayu.fins.direct_events import (
    FinsDirectStreamProtocolError,
    FinsEvent,
    FinsEventDetail,
    FinsResultSummary,
)
from dayu.fins.direct_events import ValidatedFinsEventStream
from dayu.fins.download_contract import FinsDownloadRequest, FinsDownloadUsageError
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.filing_semantics import FiscalPeriod
from dayu.fins.resolver import FmpCompanyInfoResolver
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.fins.upload_batch import (
    FINS_UPLOAD_FILE_SUFFIXES,
    BatchUploadAction,
    UploadBatchFilingEntry,
    UploadBatchMaterialEntry,
    UploadBatchPlanEmptyError,
    UploadBatchPlanRequest,
    UploadBatchPlanUsageError,
    UploadBatchSkippedEntry,
    generate_upload_batch_plan,
)
from dayu.service.fins_direct import (
    FinsDirectCommandService,
    build_direct_download_request,
)

_BASE_OPTION: Final[str] = "--base"
_TICKER_OPTION: Final[str] = "--ticker"
_MULTIPLE_MATERIAL_FORMS_MESSAGE: Final[str] = "当前 Fins upload_material request 只支持单个 --forms 值"
_MULTIPLE_BATCH_MATERIAL_FORMS_MESSAGE: Final[str] = (
    "upload_filings_from 的 --material-forms 最多接受一个值"
)
_FMP_API_KEY_ENV: Final[str] = "FMP_API_KEY"
_EMPTY_TICKER_MESSAGE: Final[str] = "--ticker must not be empty"
_EMPTY_DOCUMENT_ID_MESSAGE: Final[str] = "--document-id must not contain empty item"
_EMPTY_FORM_MESSAGE: Final[str] = "--forms must not contain empty item"
_MISSING_UPLOAD_FILE_TEMPLATE: Final[str] = "upload file does not exist: {path}"
_UPLOAD_PATH_NOT_FILE_TEMPLATE: Final[str] = "upload path is not a file: {path}"
_UPLOAD_SUFFIX_NOT_ALLOWED_TEMPLATE: Final[str] = "upload file suffix is not allowed: {path}"
_FINS_DIAGNOSTIC_TEXT_MAX_CHARS: Final[int] = 120
_FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS: Final[int] = 4
_FINS_DIAGNOSTIC_TRUNCATED_SUFFIX: Final[str] = "..."
_FINS_DIRECT_DEBUG_BASE_PART_COUNT: Final[int] = 2
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


class CliFinsUsageError(ValueError):
    """Fins direct CLI 用法错误。"""


@dataclass(frozen=True, slots=True)
class _CliDirectLocalExit:
    """CLI 本地 direct command 退出状态。

    :param exit_code: 当前 CLI command 应返回的进程退出码。
    """

    exit_code: int


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


FinsDirectServiceFactory = Callable[[Path], FinsDirectCommandService]
FINS_DIRECT_SERVICE_FACTORY: FinsDirectServiceFactory = FinsDirectCommandService.from_workspace_root


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
    except FinsDownloadUsageError as exc:
        render_cli_error(f"dayu-cli {args.command_name}: {exc}")
        return EXIT_USAGE_ERROR
    except FinsDirectStreamProtocolError as exc:
        render_cli_error(f"dayu-cli {args.command_name}: {exc.message}")
        return EXIT_FAILURE
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
    :raises BaseException: stream 消费或确定性关闭失败时保持原异常向上抛出。
    """

    runtime_log.log_verbose(
        _LOGGER,
        "Fins direct command start; command=%s",
        args.command_name,
    )
    if args.command_name == COMMAND_UPLOAD_FILINGS_FROM:
        return _run_upload_filings_from(args)
    download_request = _prevalidate_download_request(args)
    workspace_root = _resolve_workspace_root(args.workspace_root)
    service = FINS_DIRECT_SERVICE_FACTORY(workspace_root)
    cancellation_token = _CliFinsCancellationToken()
    stream = _open_direct_stream(
        args=args,
        service=service,
        cancellation_token=cancellation_token,
        download_request=download_request,
    )
    try:
        runtime_log.log_verbose(
            _LOGGER,
            "Fins direct stream opened; command=%s",
            args.command_name,
        )
        terminal = await _wait_for_terminal_handling_sigint(
            events=stream,
            cancellation_token=cancellation_token,
            sigint_monitor=CliSigintMonitor(),
            command_name=args.command_name,
        )
    except BaseException as primary_error:
        await _raise_primary_after_fins_stream_close(
            stream=stream,
            primary_error=primary_error,
        )
    await stream.aclose()
    return terminal.exit_code


async def _raise_primary_after_fins_stream_close(
    *,
    stream: ValidatedFinsEventStream,
    primary_error: BaseException,
) -> NoReturn:
    """确定性关闭 CLI 创建的 stream，并保持既存 primary 异常身份。

    :param stream: 当前 CLI 创建并拥有的 Fins direct stream。
    :param primary_error: stream 消费或下游处理已经产生的主异常。
    :returns: 不返回。
    :raises BaseException: 始终重抛同一 primary；关闭失败时将其挂为显式 cause。
    """

    try:
        await stream.aclose()
    except BaseException as close_error:
        raise primary_error from close_error
    raise primary_error


def _run_upload_filings_from(args: ParsedCliArgs) -> int:
    """生成并安全发布 ``upload_filings_from`` 可执行脚本。

    :param args: argparse 已解析的 upload_filings_from 参数。
    :returns: CLI 退出码。
    :raises CliFinsUsageError: ticker、source、material form 或 FMP 输入非法时抛出。
    :raises UploadBatchPlanUsageError: Fins batch helper 判断输入非法时抛出。
    :raises UploadBatchPlanEmptyError: 源目录无可识别文件时抛出。
    :raises RuntimeError: FMP 结果与用户 canonical ticker 冲突时抛出。
    :raises OSError: 脚本发布失败时由底层抛出。
    """

    if args.source_dir is None or args.source_dir.strip() == "":
        raise CliFinsUsageError("--from must not be empty")
    ticker = _parse_ticker_csv(args.ticker)
    explicit_company_name = _optional_stripped_text(args.company_name)
    aliases = ticker.aliases
    company_name = explicit_company_name
    if args.infer:
        api_key = os.environ.get(_FMP_API_KEY_ENV)
        if api_key is None or api_key.strip() == "":
            raise CliFinsUsageError("--infer requires non-empty FMP_API_KEY")
        resolved_info = FmpCompanyInfoResolver(api_key=api_key).resolve_company_info(
            ticker.canonical
        )
        if resolved_info.canonical_ticker != ticker.canonical:
            raise RuntimeError(
                "FMP resolved canonical ticker does not match the requested ticker"
            )
        aliases = _merge_ticker_aliases(
            canonical=ticker.canonical,
            explicit_aliases=ticker.aliases,
            resolved_aliases=resolved_info.ticker_aliases,
        )
        if company_name is None:
            company_name = resolved_info.company_name
    material_form = _single_batch_material_form(args.material_forms)
    workspace_root = _resolve_workspace_root(args.workspace_root)
    source_dir = Path(args.source_dir)
    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(
            ticker=ticker.canonical,
            aliases=aliases,
            source_dir=source_dir,
            action=cast(BatchUploadAction, args.action),
            recursive=args.recursive,
            fiscal_year=args.fiscal_year,
            fiscal_period=cast(
                FiscalPeriod | None,
                _optional_stripped_text(args.fiscal_period),
            ),
            amended=args.amended,
            filing_date=_optional_stripped_text(args.filing_date),
            report_date=_optional_stripped_text(args.report_date),
            company_name=company_name,
            overwrite=args.overwrite,
            material_form=material_form,
        )
    )
    commands = tuple(
        _upload_batch_command_argv(entry, workspace_root=workspace_root)
        for entry in (*plan.recognized_entries, *plan.material_entries)
    )
    platform = current_upload_script_platform()
    content = render_upload_script(
        commands,
        regeneration_argv=_upload_batch_regeneration_argv(
            args=args,
            ticker=ticker,
            source_dir=source_dir,
            explicit_company_name=explicit_company_name,
            material_form=material_form,
        ),
        platform=platform,
    )
    script_path = publish_upload_script(
        workspace_root=workspace_root,
        output=Path(args.output) if args.output is not None else None,
        canonical_ticker=ticker.canonical,
        platform=platform,
        content=content,
    )
    _render_upload_batch_summary(
        script_path=script_path,
        recognized_count=len(plan.recognized_entries),
        material_count=len(plan.material_entries),
        skipped_entries=plan.skipped_entries,
    )
    return EXIT_SUCCESS


def _upload_batch_command_argv(
    entry: UploadBatchFilingEntry | UploadBatchMaterialEntry,
    *,
    workspace_root: Path,
) -> tuple[str, ...]:
    """把单条 Fins typed entry 机械投影为 current CLI argv。

    :param entry: Fins owner 产生的 filing 或 material entry。
    :param workspace_root: 每条 direct upload 使用的 workspace root。
    :returns: 不经过 shell quoting 的 argv 元组。
    :raises Exception: 不主动抛出异常。
    """

    command_name = (
        COMMAND_UPLOAD_FILING
        if isinstance(entry, UploadBatchFilingEntry)
        else COMMAND_UPLOAD_MATERIAL
    )
    parts = [
        "python",
        "-m",
        "dayu.cli",
        command_name,
        _BASE_OPTION,
        str(workspace_root),
        "--ticker",
        ",".join((entry.ticker, *entry.aliases)),
    ]
    if entry.action != "auto":
        parts.extend(("--action", entry.action))
    if isinstance(entry, UploadBatchMaterialEntry):
        parts.extend(("--forms", entry.form_type))
        parts.extend(("--material-name", entry.material_name))
    parts.extend(("--files", str(entry.file)))
    _append_optional_entry_metadata(parts, entry)
    return tuple(parts)


def _append_optional_entry_metadata(
    parts: list[str],
    entry: UploadBatchFilingEntry | UploadBatchMaterialEntry,
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
    if entry.overwrite:
        parts.append("--overwrite")


def _upload_batch_regeneration_argv(
    *,
    args: ParsedCliArgs,
    ticker: CliTickerInput,
    source_dir: Path,
    explicit_company_name: str | None,
    material_form: str | None,
) -> tuple[str, ...]:
    """从用户显式生成参数构造无 secret 的再生成 argv。

    :param args: argparse 解析结果。
    :param ticker: 已规范化的用户 ticker CSV。
    :param source_dir: 用户 source directory。
    :param explicit_company_name: 用户显式 company name，不含 FMP 推断值。
    :param material_form: 已规范化单一 material form 候选。
    :returns: 可安全写入注释的 argv。
    :raises Exception: 不主动抛出异常。
    """

    parts = [
        "python",
        "-m",
        "dayu.cli",
        COMMAND_UPLOAD_FILINGS_FROM,
        _BASE_OPTION,
        args.workspace_root,
        "--ticker",
        ",".join((ticker.canonical, *ticker.aliases)),
        "--from",
        str(source_dir),
    ]
    if args.action != "auto":
        parts.extend(("--action", args.action))
    if args.output is not None:
        parts.extend(("--output", args.output))
    if args.recursive:
        parts.append("--recursive")
    if args.fiscal_year is not None:
        parts.extend(("--fiscal-year", str(args.fiscal_year)))
    fiscal_period = _optional_stripped_text(args.fiscal_period)
    if fiscal_period is not None:
        parts.extend(("--fiscal-period", fiscal_period))
    if args.amended:
        parts.append("--amended")
    if args.filing_date is not None:
        parts.extend(("--filing-date", args.filing_date))
    if args.report_date is not None:
        parts.extend(("--report-date", args.report_date))
    if explicit_company_name is not None:
        parts.extend(("--company-name", explicit_company_name))
    if material_form is not None:
        parts.extend(("--material-forms", material_form))
    if args.infer:
        parts.append("--infer")
    if args.overwrite:
        parts.append("--overwrite")
    return tuple(parts)


def _render_upload_batch_summary(
    *,
    script_path: Path,
    recognized_count: int,
    material_count: int,
    skipped_entries: tuple[UploadBatchSkippedEntry, ...],
) -> None:
    """输出用户可读的脚本生成摘要。

    :param script_path: 已发布脚本绝对路径。
    :param recognized_count: filing 数量。
    :param material_count: material 数量。
    :param skipped_entries: Fins owner 跳过事实。
    :returns: ``None``。
    :raises OSError: stdout 写入失败时由 ``print`` 透传。
    """

    print(f"Generated upload script: {script_path}")
    print(f"Recognized filings: {recognized_count}")
    print(f"Material files: {material_count}")
    print(f"Skipped files: {len(skipped_entries)}")
    for skipped in skipped_entries:
        print(
            f"Skipped [{skipped.reason_code}] {skipped.path}: {skipped.reason}"
        )


def _open_direct_stream(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
    download_request: FinsDownloadRequest | None,
) -> ValidatedFinsEventStream:
    """按命令名打开 direct event stream。

    :param args: argparse 已解析的 Fins direct 命令参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :param download_request: download 命令预先校验完成的请求；其它命令为 ``None``。
    :returns: Fins owner 已验证的 direct 事件流。
    :raises CliFinsUsageError: 命令或用户输入非法时抛出。
    :raises Exception: Service 打开 stream 失败时向上抛出。
    """

    if args.command_name == COMMAND_DOWNLOAD:
        if download_request is None:
            raise AssertionError("download command 缺少预校验请求")
        return _download_stream(
            request=download_request,
            service=service,
            cancellation_token=cancellation_token,
        )
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
    request: FinsDownloadRequest,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
) -> ValidatedFinsEventStream:
    """打开 download direct stream。

    :param request: workspace resolution 前完成校验的下载请求。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins owner 已验证的 direct 事件流。
    :raises Exception: Service 打开 stream 失败时由底层抛出。
    """

    return service.download(
        request,
        cancellation_token=cancellation_token,
    )


def _prevalidate_download_request(args: ParsedCliArgs) -> FinsDownloadRequest | None:
    """在 workspace resolution 前校验 download 静态输入。

    Args:
        args: argparse 已解析的 direct command 参数。

    Returns:
        download 命令返回 typed request；其它 direct command 返回 ``None``。

    Raises:
        FinsDownloadUsageError: download 参数违反公开调用契约时抛出。
    """

    if args.command_name != COMMAND_DOWNLOAD:
        return None
    if args.ticker is None:
        raise FinsDownloadUsageError("--ticker 不能为空，请提供一个公司代码")
    return build_direct_download_request(
        ticker=args.ticker,
        form_types=tuple(args.forms or ()),
        start=args.start,
        end=args.end,
        overwrite_existing=args.overwrite,
        rebuild_local_artifacts=args.rebuild,
    )


def _upload_filing_stream(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
) -> ValidatedFinsEventStream:
    """打开 upload_filing direct stream。

    :param args: argparse 已解析的 upload_filing 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins owner 已验证的 direct 事件流。
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
) -> ValidatedFinsEventStream:
    """打开 upload_material direct stream。

    :param args: argparse 已解析的 upload_material 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins owner 已验证的 direct 事件流。
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
) -> ValidatedFinsEventStream:
    """打开 process direct stream。

    :param args: argparse 已解析的 process 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins owner 已验证的 direct 事件流。
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
) -> ValidatedFinsEventStream:
    """打开 process_filing direct stream。

    :param args: argparse 已解析的 process_filing 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins owner 已验证的 direct 事件流。
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
) -> ValidatedFinsEventStream:
    """打开 process_material direct stream。

    :param args: argparse 已解析的 process_material 参数。
    :param service: Fins direct Service helper。
    :param cancellation_token: 当前 operation 的取消 token。
    :returns: Fins owner 已验证的 direct 事件流。
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
    events: ValidatedFinsEventStream,
    cancellation_token: _CliFinsCancellationToken,
    sigint_monitor: CliSigintMonitor,
    command_name: str,
) -> FinsResultSummary | _CliDirectLocalExit:
    """等待 direct stream 终态并处理运行中 SIGINT。

    :param events: Fins direct event stream。
    :param cancellation_token: 当前 operation 的取消 token。
    :param sigint_monitor: SIGINT 观察器。
    :param command_name: 用户可见命令名，用于诊断。
    :returns: direct stream 终态摘要，或 CLI 本地退出状态。
    :raises BaseException: stream 消费或 consumer task 清理失败时保持原异常向上抛出。
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
                close_error: BaseException | None = None
                try:
                    terminal_result = await event_task
                except asyncio.CancelledError as cancellation_error:
                    close_error = cancellation_error.__cause__
                else:
                    return terminal_result
                if close_error is not None:
                    # 离开 child cancellation handler 后再传播 cleanup error，
                    # 避免 Python 把 child cancellation 写入其隐式 context。
                    raise close_error
                render_fins_direct_local_exit_after_cancel()
                return _CliDirectLocalExit(exit_code=EXIT_KEYBOARD_INTERRUPT)
    except BaseException as primary_error:
        cleanup_error = await _cancel_and_drain_fins_event_task(
            event_task,
            primary_error=primary_error,
        )
        if cleanup_error is not None:
            raise primary_error from cleanup_error
        raise primary_error
    finally:
        sigint_monitor.close()
        sigint_task.cancel()


async def _cancel_and_drain_fins_event_task(
    event_task: asyncio.Task[FinsResultSummary],
    *,
    primary_error: BaseException,
) -> BaseException | None:
    """取消并等待仍在运行的 CLI event consumer task。

    :param event_task: 当前 direct stream consumer task。
    :param primary_error: 当前 owner 已捕获且必须保持身份的主异常。
    :returns: task 取消期间发生的显式 cleanup cause；正常取消或已结束时返回 ``None``。
    :raises Exception: 不主动抛出异常；task cleanup error 作为返回值交给 owner 裁决。
    """

    if not event_task.done():
        event_task.cancel()
    try:
        await event_task
    except asyncio.CancelledError as cancellation_error:
        if cancellation_error is primary_error:
            return None
        cleanup_error = cancellation_error.__cause__
        if cleanup_error is primary_error:
            return None
        return cleanup_error
    except BaseException as cleanup_error:
        if cleanup_error is primary_error:
            return None
        return cleanup_error
    return None


async def _consume_fins_direct_events(
    events: ValidatedFinsEventStream,
) -> FinsResultSummary:
    """消费 Service event stream 并输出 Fins direct 事件。

    :param events: Fins direct event stream。
    :returns: clean exhaustion 后由 Fins owner 提供的 terminal result summary。
    :raises FinsDirectStreamProtocolError: Fins owner 判定 terminal 协议非法时抛出。
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
    return events.terminal_result


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
        rendered.append(f"{_bounded_diagnostic_text(detail.label)}=" f"{_quoted_diagnostic_text(detail.value)}")
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
    return (
        value[: _FINS_DIAGNOSTIC_TEXT_MAX_CHARS - len(_FINS_DIAGNOSTIC_TRUNCATED_SUFFIX)]
        + _FINS_DIAGNOSTIC_TRUNCATED_SUFFIX
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
    :raises CliFinsUsageError: ticker 缺失、空项或任一 token 无法规范化时抛出。
    """

    if raw_value is None:
        raise CliFinsUsageError(_EMPTY_TICKER_MESSAGE)
    parts = tuple(part.strip() for part in raw_value.split(","))
    if not parts or any(part == "" for part in parts):
        raise CliFinsUsageError(_EMPTY_TICKER_MESSAGE)
    try:
        canonical = normalize_ticker(parts[0]).canonical
        normalized_aliases = tuple(
            normalize_ticker(alias).canonical for alias in parts[1:]
        )
    except ValueError as exc:
        raise CliFinsUsageError(str(exc)) from exc
    aliases = _merge_ticker_aliases(
        canonical=canonical,
        explicit_aliases=normalized_aliases,
        resolved_aliases=(),
    )
    return CliTickerInput(canonical=canonical, aliases=aliases)


def _merge_ticker_aliases(
    *,
    canonical: str,
    explicit_aliases: tuple[str, ...],
    resolved_aliases: tuple[str, ...],
) -> tuple[str, ...]:
    """按显式优先顺序合并已由各自 owner 规范化的 ticker aliases。

    :param canonical: 用户 canonical ticker。
    :param explicit_aliases: CLI strict normalizer 产生的显式 aliases。
    :param resolved_aliases: FMP resolver public contract 产生的 aliases。
    :returns: 排除 canonical 后的稳定去重 aliases。
    :raises RuntimeError: resolver 返回空 alias 时抛出。
    """

    aliases: list[str] = []
    seen = {canonical}
    for raw_alias in (*explicit_aliases, *resolved_aliases):
        alias = raw_alias.strip()
        if alias == "":
            raise RuntimeError("FMP resolver returned an empty ticker alias")
        if alias in seen:
            continue
        seen.add(alias)
        aliases.append(alias)
    return tuple(aliases)


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
            raise CliFinsUsageError(_MISSING_UPLOAD_FILE_TEMPLATE.format(path=path))
        if not path.is_file():
            raise CliFinsUsageError(_UPLOAD_PATH_NOT_FILE_TEMPLATE.format(path=path))
        if path.suffix.lower() not in FINS_UPLOAD_FILE_SUFFIXES:
            raise CliFinsUsageError(_UPLOAD_SUFFIX_NOT_ALLOWED_TEMPLATE.format(path=path))
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


def _single_batch_material_form(
    values: list[str] | None,
) -> str | None:
    """读取 batch 可选单一 material form override。

    :param values: ``--material-forms`` 输入。
    :returns: 规范化的单一 material form 候选；未传入时返回 ``None``。
    :raises CliFinsUsageError: 传入多个 form 时抛出。
    """

    normalized = _normalized_text_tuple(values, field_name="--material-forms")
    if len(normalized) > 1:
        raise CliFinsUsageError(_MULTIPLE_BATCH_MATERIAL_FORMS_MESSAGE)
    if not normalized:
        return None
    return normalized[0].upper()


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
