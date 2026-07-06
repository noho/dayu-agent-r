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

    renderer.record(_thinking(dedupe_key="thinking-1", event_sequence=1))

    assert stderr.getvalue() == "Thinking: 正在分析收入变化\n"


def test_thinking_renderer_deduplicates_and_ignores_older_sequences() -> None:
    """renderer 应过滤重复 dedupe key 和乱序 thinking。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=True),
    )

    renderer.record(_thinking(dedupe_key="thinking-1", event_sequence=2))
    renderer.record(_thinking(dedupe_key="thinking-1", event_sequence=3))
    renderer.record(_thinking(dedupe_key="thinking-old", event_sequence=1))
    renderer.record(_thinking(dedupe_key="thinking-3", event_sequence=3))

    output = stderr.getvalue()
    assert output.count("Thinking:") == 2
    assert "thinking-old" not in output


def test_thinking_renderer_suppresses_when_disabled() -> None:
    """disabled renderer 不应输出 thinking。"""

    stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=False),
    )

    renderer.record(_thinking(dedupe_key="thinking-1", event_sequence=1))

    assert stderr.getvalue() == ""


def _thinking(*, dedupe_key: str, event_sequence: int) -> EntrypointThinking:
    """构造测试 thinking。

    :param dedupe_key: thinking dedupe key。
    :param event_sequence: Host event sequence。
    :returns: Service entrypoint thinking。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointThinking(
        run_id="run-1",
        event_sequence=event_sequence,
        dedupe_key=dedupe_key,
        text_delta="正在分析收入变化",
    )
