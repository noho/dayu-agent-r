"""``dayu-cli tool_trace`` operator 命令。

本模块只把 CLI 参数映射到 Service public Tool Trace analysis boundary，并把
成功路径或 typed publication failure 投影到 stdout/stderr。它不读取 Host
durable internals，也不解释 structured report 的业务语义。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from dayu.cli.arg_parsing import (
    TOOL_TRACE_ACTION_ANALYZE,
    ParsedCliArgs,
)
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.service.tool_trace_analysis import (
    ServiceToolTraceAnalysisPublishError,
    ServiceToolTraceAnalysisUsageError,
    analyze_and_publish_tool_trace,
)


def run_tool_trace_command(args: ParsedCliArgs) -> int:
    """执行 ``dayu-cli tool_trace`` 命令。

    :param args: argparse 已解析的 Tool Trace 参数。
    :returns: 成功为 0，分析/发布失败为 1，用法错误为 2。
    :raises OSError: stdout/stderr 写入失败时透传。
    """

    if args.tool_trace_action != TOOL_TRACE_ACTION_ANALYZE:
        print(
            f"dayu-cli tool_trace: 不支持的 action：{args.tool_trace_action}",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR
    try:
        result = analyze_and_publish_tool_trace(
            Path(args.tool_trace_input),
            Path(args.output_dir),
        )
    except ServiceToolTraceAnalysisUsageError as exc:
        print(f"dayu-cli tool_trace analyze: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except ServiceToolTraceAnalysisPublishError as exc:
        _render_publish_failure(exc, stderr=sys.stderr)
        return EXIT_FAILURE
    except Exception as exc:
        print(f"dayu-cli tool_trace analyze: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    print(f"JSON report: {result.json_path}", file=sys.stdout)
    print(f"Markdown report: {result.markdown_path}", file=sys.stdout)
    return EXIT_SUCCESS


def _render_publish_failure(
    error: ServiceToolTraceAnalysisPublishError,
    *,
    stderr: TextIO,
) -> None:
    """输出 primary publication failure 与独立 cleanup secondary detail。

    :param error: Service typed publication failure。
    :param stderr: CLI 标准错误流。
    :returns: ``None``。
    :raises OSError: 标准错误流写入失败时透传。
    """

    published_text = (
        "无"
        if not error.published_paths
        else ", ".join(str(path) for path in error.published_paths)
    )
    print("dayu-cli tool_trace analyze: 报告发布失败。", file=stderr)
    print(f"已发布路径：{published_text}", file=stderr)
    print(f"发布失败路径：{error.failed_path}", file=stderr)
    print(
        f"主发布错误：{error.primary_publish_error.error_summary}",
        file=stderr,
    )
    if error.cleanup_error is not None:
        cleanup_paths = ", ".join(
            str(path) for path in error.cleanup_error.failed_paths
        )
        print(f"临时文件清理失败路径：{cleanup_paths}", file=stderr)
        print(
            f"清理错误：{error.cleanup_error.error_summary}",
            file=stderr,
        )


__all__ = ("run_tool_trace_command",)
