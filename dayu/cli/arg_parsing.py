"""Dayu CLI 参数解析器工厂。

本模块定义当前 CLI-01-S1 允许暴露的命令、全局参数和各命令帮助文本。它只处理
用户可见命令面，不启动 Host、Service 或 Fins 业务流程。
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Protocol, cast

CLI_PROGRAM_NAME: str = "dayu-cli"
DEFAULT_WORKSPACE: str = "./workspace"
DEFAULT_LOG_LEVEL: str = "info"

LOG_LEVEL_CHOICES: tuple[str, ...] = (
    "debug",
    "verbose",
    "info",
    "warn",
    "error",
)
COMMAND_INIT: str = "init"
COMMAND_PROMPT: str = "prompt"
COMMAND_INTERACTIVE: str = "interactive"
COMMAND_DOWNLOAD: str = "download"
COMMAND_UPLOAD_FILING: str = "upload_filing"
COMMAND_UPLOAD_MATERIAL: str = "upload_material"
COMMAND_UPLOAD_FILINGS_FROM: str = "upload_filings_from"
COMMAND_PROCESS: str = "process"
COMMAND_PROCESS_FILING: str = "process_filing"
COMMAND_PROCESS_MATERIAL: str = "process_material"

CLI_COMMAND_NAMES: tuple[str, ...] = (
    COMMAND_INIT,
    COMMAND_PROMPT,
    COMMAND_INTERACTIVE,
    COMMAND_DOWNLOAD,
    COMMAND_UPLOAD_FILING,
    COMMAND_UPLOAD_MATERIAL,
    COMMAND_UPLOAD_FILINGS_FROM,
    COMMAND_PROCESS,
    COMMAND_PROCESS_FILING,
    COMMAND_PROCESS_MATERIAL,
)
EXCLUDED_COMMAND_NAMES: tuple[str, ...] = (
    "write",
    "host",
    "sessions",
    "runs",
    "cancel",
    "conv",
)
FILING_ACTION_CHOICES: tuple[str, ...] = ("create", "update", "delete")
BATCH_UPLOAD_ACTION_CHOICES: tuple[str, ...] = ("create", "update")


class CommandSubparserRegistry(Protocol):
    """命令子解析器注册器协议。

    本协议只描述当前模块需要的 ``add_parser`` 能力，避免把 argparse 内部实现
    类型扩散到各个命令注册函数签名中。
    """

    def add_parser(
        self,
        name: str,
        *,
        help: str,
        description: str,
        parents: Sequence[argparse.ArgumentParser],
    ) -> argparse.ArgumentParser:
        """注册并返回命令子解析器。

        :param name: 命令名。
        :param help: 顶层 help 中展示的命令摘要。
        :param description: 子命令 help 中展示的说明文本。
        :param parents: 子解析器需要复用的父解析器集合。
        :returns: 新增命令对应的子解析器。
        :raises ValueError: argparse 参数注册失败时透传底层异常。
        """

        ...


class ParsedCliArgs(argparse.Namespace):
    """Dayu CLI 解析结果命名空间。

    argparse 会在运行时写入各命令参数；命令 runner 只读取自身命令注册过的
    字段。
    """

    command_name: str
    workspace_root: str
    config_dir: str | None
    log_level: str
    prompt: str
    ticker: str | None
    label: str | None
    new_session: bool
    model_name: str | None
    thinking: bool | None
    web_provider: str | None
    temperature: float | None
    debug_sse: bool
    debug_tool_delta: bool
    debug_sse_sample_rate: float | None
    debug_sse_throttle_sec: float | None
    tool_timeout_seconds: float | None
    enable_tool_trace: bool
    tool_trace_dir: str | None
    max_iterations: int | None
    fallback_mode: str | None
    fallback_prompt: str | None
    max_consecutive_failed_tool_batches: int | None
    max_duplicate_tool_calls: int | None
    duplicate_tool_hint_prompt: str | None
    doc_limits_json: str | None
    fins_limits_json: str | None
    forms: list[str] | None
    start: str | None
    end: str | None
    reset: bool
    overwrite: bool
    rebuild: bool
    infer: bool
    action: str
    files: list[str] | None
    fiscal_year: int | None
    fiscal_period: str | None
    amended: bool
    filing_date: str | None
    report_date: str | None
    company_name: str | None
    material_name: str | None
    document_id: str | list[str] | None
    internal_document_id: str | None
    ci: bool
    source_dir: str | None
    output: str | None
    recursive: bool
    material_forms: list[str] | None


def build_parser(prog: str = CLI_PROGRAM_NAME) -> argparse.ArgumentParser:
    """构建 Dayu CLI 顶层参数解析器。

    :param prog: 帮助文本中显示的程序名。
    :returns: 已注册 S1 scoped commands 的 argparse 解析器。
    :raises ValueError: argparse 初始化或参数注册失败时透传底层异常。
    """

    global_parent = _build_global_arguments_parent()
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Dayu 财报分析命令行入口。",
        parents=[global_parent],
    )
    subparsers = cast(
        CommandSubparserRegistry,
        parser.add_subparsers(
            dest="command_name",
            metavar="COMMAND",
            required=True,
        ),
    )
    _register_init_command(subparsers, global_parent)
    _register_prompt_command(subparsers, global_parent)
    _register_interactive_command(subparsers, global_parent)
    _register_download_command(subparsers, global_parent)
    _register_upload_filing_command(subparsers, global_parent)
    _register_upload_material_command(subparsers, global_parent)
    _register_upload_filings_from_command(subparsers, global_parent)
    _register_process_command(subparsers, global_parent)
    _register_process_filing_command(subparsers, global_parent)
    _register_process_material_command(subparsers, global_parent)
    return parser


def parse_cli_args(argv: Sequence[str] | None = None) -> ParsedCliArgs:
    """解析 Dayu CLI 参数。

    :param argv: 不含程序名的命令行参数；为 ``None`` 时使用进程参数。
    :returns: 类型化的 CLI 解析结果。
    :raises SystemExit: ``--help``、用法错误或未知命令由 argparse 触发。
    """

    parser = build_parser()
    namespace = parser.parse_args(argv, namespace=_new_default_namespace())
    return cast(ParsedCliArgs, namespace)


def _new_default_namespace() -> ParsedCliArgs:
    """创建带全局默认值的解析结果命名空间。

    :returns: 已填充全局默认值的解析命名空间。
    :raises ValueError: 本函数不主动抛出异常。
    """

    namespace = ParsedCliArgs()
    namespace.workspace_root = DEFAULT_WORKSPACE
    namespace.config_dir = None
    namespace.log_level = DEFAULT_LOG_LEVEL
    namespace.ticker = None
    namespace.label = None
    namespace.new_session = False
    namespace.model_name = None
    namespace.thinking = None
    namespace.web_provider = None
    namespace.temperature = None
    namespace.debug_sse = False
    namespace.debug_tool_delta = False
    namespace.debug_sse_sample_rate = None
    namespace.debug_sse_throttle_sec = None
    namespace.tool_timeout_seconds = None
    namespace.enable_tool_trace = False
    namespace.tool_trace_dir = None
    namespace.max_iterations = None
    namespace.fallback_mode = None
    namespace.fallback_prompt = None
    namespace.max_consecutive_failed_tool_batches = None
    namespace.max_duplicate_tool_calls = None
    namespace.duplicate_tool_hint_prompt = None
    namespace.doc_limits_json = None
    namespace.fins_limits_json = None
    namespace.forms = None
    namespace.start = None
    namespace.end = None
    namespace.reset = False
    namespace.overwrite = False
    namespace.rebuild = False
    namespace.infer = False
    namespace.action = "create"
    namespace.files = None
    namespace.fiscal_year = None
    namespace.fiscal_period = None
    namespace.amended = False
    namespace.filing_date = None
    namespace.report_date = None
    namespace.company_name = None
    namespace.material_name = None
    namespace.document_id = None
    namespace.internal_document_id = None
    namespace.ci = False
    namespace.source_dir = None
    namespace.output = None
    namespace.recursive = False
    namespace.material_forms = None
    return namespace


def _build_global_arguments_parent() -> argparse.ArgumentParser:
    """创建可复用的全局参数父解析器。

    :returns: 不含 help 的全局参数解析器。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--base",
        "-b",
        "--workspace",
        dest="workspace_root",
        default=argparse.SUPPRESS,
        help="工作区根目录，默认 ./workspace。",
    )
    parser.add_argument(
        "--config",
        dest="config_dir",
        default=argparse.SUPPRESS,
        help="显式配置目录；未提供时使用 workspace/config 或随包默认配置。",
    )
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVEL_CHOICES,
        default=argparse.SUPPRESS,
        help="日志等级。",
    )
    parser.add_argument(
        "--debug",
        action="store_const",
        const="debug",
        dest="log_level",
        default=argparse.SUPPRESS,
        help="等价于 --log-level debug。",
    )
    parser.add_argument(
        "--verbose",
        action="store_const",
        const="verbose",
        dest="log_level",
        default=argparse.SUPPRESS,
        help="等价于 --log-level verbose。",
    )
    parser.add_argument(
        "--info",
        action="store_const",
        const="info",
        dest="log_level",
        default=argparse.SUPPRESS,
        help="等价于 --log-level info。",
    )
    parser.add_argument(
        "--quiet",
        action="store_const",
        const="error",
        dest="log_level",
        default=argparse.SUPPRESS,
        help="只输出错误级别日志。",
    )
    return parser


def _add_command_parser(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
    *,
    command_name: str,
    help_text: str,
) -> argparse.ArgumentParser:
    """注册一个 scoped command 的子解析器。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :param command_name: 命令名。
    :param help_text: 命令摘要。
    :returns: 新增命令对应的子解析器。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = subparsers.add_parser(
        command_name,
        help=help_text,
        description=help_text,
        parents=[global_parent],
    )
    parser.set_defaults(command_name=command_name)
    return parser


def _register_init_command(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
) -> None:
    """注册 ``init`` 命令参数。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = _add_command_parser(
        subparsers,
        global_parent,
        command_name=COMMAND_INIT,
        help_text="初始化当前工作区配置骨架。",
    )
    parser.add_argument("--reset", action="store_true", help="重置已有工作区配置。")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有配置文件。")


def _register_prompt_command(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
) -> None:
    """注册 ``prompt`` 命令参数。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = _add_command_parser(
        subparsers,
        global_parent,
        command_name=COMMAND_PROMPT,
        help_text="提交一次性财报分析问题。",
    )
    parser.add_argument("prompt", type=_non_empty_prompt, help="本轮用户问题。")
    parser.add_argument("--ticker", help="可选公司代码或财报主体。")
    parser.add_argument("--label", help="复用或绑定的本地会话标签。")
    _add_agent_execution_arguments(parser)


def _register_interactive_command(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
) -> None:
    """注册 ``interactive`` 命令参数。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = _add_command_parser(
        subparsers,
        global_parent,
        command_name=COMMAND_INTERACTIVE,
        help_text="进入多轮财报分析交互模式。",
    )
    parser.add_argument("--ticker", help="可选公司代码或财报主体。")
    label_group = parser.add_mutually_exclusive_group()
    label_group.add_argument("--label", help="复用或绑定的本地会话标签。")
    label_group.add_argument(
        "--new-session",
        action="store_true",
        help="为指定标签创建新会话。",
    )
    _add_agent_execution_arguments(parser)


def _add_agent_execution_arguments(parser: argparse.ArgumentParser) -> None:
    """为 Agent 类命令追加旧 CLI 用户可见执行参数。

    :param parser: 目标命令解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser.add_argument("--model-name", "-m", dest="model_name", help="模型配置标识。")
    thinking_group = parser.add_mutually_exclusive_group()
    thinking_group.add_argument(
        "--thinking",
        dest="thinking",
        action="store_true",
        default=None,
        help="请求启用模型思考能力；执行期按当前配置裁决。",
    )
    thinking_group.add_argument(
        "--no-thinking",
        dest="thinking",
        action="store_false",
        default=None,
        help="请求关闭模型思考能力；执行期按当前配置裁决。",
    )
    parser.add_argument("--web-provider", help="Web 工具 provider 覆盖标识。")
    parser.add_argument("--temperature", type=float, help="本轮模型采样温度覆盖值。")
    parser.add_argument("--debug-sse", action="store_true", help="保留的 SSE 调试开关。")
    parser.add_argument(
        "--debug-tool-delta",
        action="store_true",
        help="保留的工具增量调试开关。",
    )
    parser.add_argument(
        "--debug-sse-sample-rate",
        type=float,
        help="保留的 SSE 调试采样率。",
    )
    parser.add_argument(
        "--debug-sse-throttle-sec",
        type=float,
        help="保留的 SSE 调试节流秒数。",
    )
    parser.add_argument(
        "--tool-timeout-seconds",
        type=float,
        help="本轮工具执行超时秒数覆盖值。",
    )
    parser.add_argument(
        "--enable-tool-trace",
        action="store_true",
        help="保留的工具追踪开关。",
    )
    parser.add_argument("--tool-trace-dir", help="保留的工具追踪输出目录。")
    parser.add_argument("--max-iterations", type=int, help="本轮最大推理迭代次数。")
    parser.add_argument("--fallback-mode", help="本轮 fallback 策略。")
    parser.add_argument("--fallback-prompt", help="本轮 fallback 提示文本。")
    parser.add_argument(
        "--max-consecutive-failed-tool-batches",
        type=int,
        help="连续失败工具批次上限。",
    )
    parser.add_argument(
        "--max-duplicate-tool-calls",
        type=int,
        help="保留的重复工具调用治理上限。",
    )
    parser.add_argument(
        "--duplicate-tool-hint-prompt",
        help="保留的重复工具调用提示文本。",
    )
    parser.add_argument("--doc-limits-json", help="保留的文档工具限制 JSON。")
    parser.add_argument("--fins-limits-json", help="保留的财报工具限制 JSON。")


def _non_empty_prompt(value: str) -> str:
    """校验 positional prompt 不是空白文本。

    :param value: argparse 收到的原始 prompt 参数。
    :returns: 原始 prompt 文本。
    :raises argparse.ArgumentTypeError: prompt 为空或仅包含空白时抛出。
    """

    if value.strip() == "":
        raise argparse.ArgumentTypeError("prompt must not be empty")
    return value


def _register_download_command(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
) -> None:
    """注册 ``download`` 命令参数。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = _add_command_parser(
        subparsers,
        global_parent,
        command_name=COMMAND_DOWNLOAD,
        help_text="下载指定主体的财报文档。",
    )
    _add_required_ticker_argument(parser)
    parser.add_argument("--forms", nargs="+", help="需要下载的报表类型。")
    parser.add_argument("--start", help="最早 filing 日期。")
    parser.add_argument("--end", help="最晚 filing 日期。")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有原始文档。")
    parser.add_argument("--rebuild", action="store_true", help="重建已处理结果。")
    parser.add_argument("--infer", action="store_true", help="保留的主体别名推断开关。")


def _register_upload_filing_command(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
) -> None:
    """注册 ``upload_filing`` 命令参数。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = _add_command_parser(
        subparsers,
        global_parent,
        command_name=COMMAND_UPLOAD_FILING,
        help_text="上传或管理单个财报 filing 文档。",
    )
    _add_required_ticker_argument(parser)
    _add_upload_action_argument(parser, choices=FILING_ACTION_CHOICES)
    parser.add_argument("--files", nargs="+", help="待上传文件路径。")
    _add_filing_metadata_arguments(parser)
    parser.add_argument("--infer", action="store_true", help="保留的元数据推断开关。")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有文档。")


def _register_upload_material_command(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
) -> None:
    """注册 ``upload_material`` 命令参数。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = _add_command_parser(
        subparsers,
        global_parent,
        command_name=COMMAND_UPLOAD_MATERIAL,
        help_text="上传或管理补充材料文档。",
    )
    _add_required_ticker_argument(parser)
    _add_upload_action_argument(parser, choices=FILING_ACTION_CHOICES)
    parser.add_argument("--forms", nargs="+", help="关联的报表类型。")
    parser.add_argument("--material-name", help="材料名称。")
    parser.add_argument("--files", nargs="+", help="待上传文件路径。")
    parser.add_argument("--document-id", help="已有文档标识。")
    parser.add_argument("--internal-document-id", help="内部文档标识。")
    _add_filing_metadata_arguments(parser)
    parser.add_argument("--infer", action="store_true", help="保留的元数据推断开关。")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有文档。")


def _register_upload_filings_from_command(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
) -> None:
    """注册 ``upload_filings_from`` 命令参数。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = _add_command_parser(
        subparsers,
        global_parent,
        command_name=COMMAND_UPLOAD_FILINGS_FROM,
        help_text="从目录生成批量上传计划。",
    )
    _add_required_ticker_argument(parser)
    parser.add_argument("--from", dest="source_dir", required=True, help="待扫描目录。")
    _add_upload_action_argument(parser, choices=BATCH_UPLOAD_ACTION_CHOICES)
    parser.add_argument("--output", help="输出计划文件路径。")
    parser.add_argument("--recursive", action="store_true", help="递归扫描目录。")
    _add_filing_metadata_arguments(parser)
    parser.add_argument("--material-forms", nargs="+", help="补充材料关联报表类型。")


def _register_process_command(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
) -> None:
    """注册 ``process`` 命令参数。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = _add_command_parser(
        subparsers,
        global_parent,
        command_name=COMMAND_PROCESS,
        help_text="处理指定主体的财报文档。",
    )
    _add_required_ticker_argument(parser)
    parser.add_argument(
        "--document-id",
        action="append",
        help="指定待处理文档，可重复传入或使用逗号分隔。",
    )
    parser.add_argument("--overwrite", action="store_true", help="重建已处理结果。")
    parser.add_argument("--ci", action="store_true", help="保留的 CI 快照开关。")


def _register_process_filing_command(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
) -> None:
    """注册 ``process_filing`` 命令参数。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = _add_command_parser(
        subparsers,
        global_parent,
        command_name=COMMAND_PROCESS_FILING,
        help_text="处理单个 filing 文档。",
    )
    _add_required_ticker_argument(parser)
    parser.add_argument("--document-id", required=True, help="待处理 filing 文档标识。")
    parser.add_argument("--overwrite", action="store_true", help="重建已处理结果。")
    parser.add_argument("--ci", action="store_true", help="保留的 CI 快照开关。")


def _register_process_material_command(
    subparsers: CommandSubparserRegistry,
    global_parent: argparse.ArgumentParser,
) -> None:
    """注册 ``process_material`` 命令参数。

    :param subparsers: 顶层 subparsers 注册器。
    :param global_parent: 包含全局参数的父解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser = _add_command_parser(
        subparsers,
        global_parent,
        command_name=COMMAND_PROCESS_MATERIAL,
        help_text="处理单个补充材料文档。",
    )
    _add_required_ticker_argument(parser)
    parser.add_argument("--document-id", required=True, help="待处理材料文档标识。")
    parser.add_argument("--overwrite", action="store_true", help="重建已处理结果。")
    parser.add_argument("--ci", action="store_true", help="保留的 CI 快照开关。")


def _add_required_ticker_argument(parser: argparse.ArgumentParser) -> None:
    """追加必填 ``--ticker`` 参数。

    :param parser: 目标命令解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser.add_argument("--ticker", required=True, help="公司代码或财报主体。")


def _add_upload_action_argument(
    parser: argparse.ArgumentParser, *, choices: tuple[str, ...]
) -> None:
    """追加上传类命令的 ``--action`` 参数。

    :param parser: 目标命令解析器。
    :param choices: 当前命令允许的动作集合。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser.add_argument(
        "--action",
        choices=choices,
        default="create",
        help="上传动作。",
    )


def _add_filing_metadata_arguments(parser: argparse.ArgumentParser) -> None:
    """追加 filing 与材料上传共用元数据参数。

    :param parser: 目标命令解析器。
    :returns: ``None``。
    :raises ValueError: argparse 参数注册失败时透传底层异常。
    """

    parser.add_argument("--fiscal-year", type=int, help="财政年度。")
    parser.add_argument("--fiscal-period", help="财政期间。")
    parser.add_argument("--amended", action="store_true", help="标记为修订文件。")
    parser.add_argument("--filing-date", help="filing 日期。")
    parser.add_argument("--report-date", help="报告日期。")
    parser.add_argument("--company-name", help="公司名称。")


__all__: tuple[str, ...] = (
    "CLI_COMMAND_NAMES",
    "EXCLUDED_COMMAND_NAMES",
    "CLI_PROGRAM_NAME",
    "ParsedCliArgs",
    "build_parser",
    "parse_cli_args",
)
