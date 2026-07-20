"""CLI thinking renderer 测试。"""

from __future__ import annotations

import io

from dayu.cli.thinking import CliThinkingRenderer, CliThinkingRendererOptions
from dayu.service.entrypoint_runtime import EntrypointThinking


def test_thinking_renderer_outputs_delta_to_stderr() -> None:
    """enabled renderer 应输出 thinking 增量。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=True),
    )

    renderer.record(_thinking(dedupe_key="thinking-1", runtime_sequence=1))

    assert stderr.getvalue() == "Thinking: 正在分析收入变化"


def test_thinking_renderer_appends_later_deltas_to_same_line() -> None:
    """后续 thinking delta 应追加到第一条 thinking 行。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=True),
    )

    renderer.record(
        _thinking(
            dedupe_key="thinking-1",
            runtime_sequence=1,
            text_delta="正在分析",
        )
    )
    renderer.record(
        _thinking(
            dedupe_key="thinking-2",
            runtime_sequence=2,
            text_delta="收入变化",
        )
    )

    assert stderr.getvalue() == "Thinking: 正在分析收入变化"


def test_thinking_renderer_preserves_delta_boundary_spaces() -> None:
    """后续 delta 的前导空格必须保留，换行只转为单行空格。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=True),
    )

    renderer.record(
        _thinking(
            dedupe_key="thinking-1",
            runtime_sequence=1,
            text_delta="The user is asking",
        )
    )
    renderer.record(
        _thinking(
            dedupe_key="thinking-2",
            runtime_sequence=2,
            text_delta=" two",
        )
    )
    renderer.record(
        _thinking(
            dedupe_key="thinking-3",
            runtime_sequence=3,
            text_delta=" things:\n1.",
        )
    )

    assert stderr.getvalue() == "Thinking: The user is asking two things: 1."


def test_thinking_renderer_finishes_non_tty_with_readable_newline() -> None:
    """非 TTY 收尾应补换行且不输出 ANSI 控制符。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=True),
    )

    renderer.record(_thinking(dedupe_key="thinking-1", runtime_sequence=1))
    renderer.finish_runtime_display()

    assert stderr.getvalue() == "Thinking: 正在分析收入变化\n"
    assert "\x1b[" not in stderr.getvalue()


def test_thinking_renderer_clears_tty_line_before_terminal_result() -> None:
    """TTY 收尾应清除当前 thinking 行。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(
            enabled=True,
            terminal_control=True,
            terminal_columns=80,
        ),
    )

    renderer.record(_thinking(dedupe_key="thinking-1", runtime_sequence=1))
    renderer.finish_runtime_display()

    assert stderr.getvalue() == "Thinking: 正在分析收入变化\r\x1b[2K"


def test_thinking_renderer_suppresses_records_after_close() -> None:
    """renderer 关闭后不应再向 stderr 输出 thinking。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=True),
    )
    renderer.record(_thinking(dedupe_key="thinking-1", runtime_sequence=1))
    output_before_close = stderr.getvalue()
    assert output_before_close == "Thinking: 正在分析收入变化"

    renderer.close()
    renderer.record(
        _thinking(
            dedupe_key="thinking-2",
            runtime_sequence=2,
            text_delta="关闭后不应输出",
        )
    )

    assert stderr.getvalue() == output_before_close


def test_thinking_renderer_deduplicates_and_ignores_older_sequences() -> None:
    """renderer 应过滤重复 dedupe key 和乱序 thinking。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=True),
    )

    renderer.record(_thinking(dedupe_key="thinking-1", runtime_sequence=2))
    renderer.record(_thinking(dedupe_key="thinking-1", runtime_sequence=3))
    renderer.record(_thinking(dedupe_key="thinking-old", runtime_sequence=1))
    renderer.record(_thinking(dedupe_key="thinking-equal", runtime_sequence=2))
    renderer.record(_thinking(dedupe_key="thinking-3", runtime_sequence=3))

    output = stderr.getvalue()
    assert output.count("Thinking:") == 1
    assert output == "Thinking: 正在分析收入变化正在分析收入变化"
    assert "thinking-old" not in output


def test_thinking_renderer_resets_sequence_baseline_for_new_runtime() -> None:
    """runtime identity 改变后允许新的序列从 1 开始。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=True),
    )

    renderer.record(_thinking(dedupe_key="runtime-1-2", runtime_sequence=2))
    renderer.record(
        _thinking(
            dedupe_key="runtime-2-1",
            runtime_id="runtime-2",
            runtime_sequence=1,
            text_delta="新运行期",
        )
    )

    assert stderr.getvalue() == "Thinking: 正在分析收入变化新运行期"


def test_thinking_renderer_suppresses_when_disabled() -> None:
    """disabled renderer 不应输出 thinking。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=False),
    )

    renderer.record(_thinking(dedupe_key="thinking-1", runtime_sequence=1))

    assert stderr.getvalue() == ""


def _thinking(
    *,
    dedupe_key: str,
    runtime_sequence: int,
    runtime_id: str = "runtime-1",
    text_delta: str = "正在分析收入变化",
) -> EntrypointThinking:
    """构造测试 thinking。

    :param dedupe_key: thinking dedupe key。
    :param runtime_sequence: 当前 Host runtime 瞬态序列。
    :param runtime_id: 当前 Host runtime opaque identity。
    :param text_delta: thinking 文本增量。
    :returns: Service entrypoint thinking。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointThinking(
        run_id="run-1",
        runtime_id=runtime_id,
        runtime_sequence=runtime_sequence,
        dedupe_key=dedupe_key,
        text_delta=text_delta,
    )
