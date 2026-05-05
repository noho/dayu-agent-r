"""Engine README Phase 2 当前事实测试。"""

from __future__ import annotations

from pathlib import Path


def _readme_text() -> str:
    """读取 Engine README。

    :returns: README 文本。
    :raises FileNotFoundError: README 不存在时抛出。
    """

    return Path("dayu/engine/README.md").read_text(encoding="utf-8")


def test_engine_readme_covers_phase2_facts() -> None:
    """Engine README 必须覆盖 Phase 2 已落地事实。"""

    text = _readme_text()
    required_fragments = (
        "UI -> Service -> Host -> Engine",
        "run_agent_messages",
        "run_agent_and_wait",
        "run-scoped",
        "RunnerEvent",
        "EngineEvent",
        "final_answer",
        "run_failed",
        "run_cancelled",
        "取消优先",
        "Runner close",
        "OpenAI-compatible Runner",
        "SSE idle",
    )

    for fragment in required_fragments:
        assert fragment in text


def test_engine_readme_does_not_claim_phase3_plus_as_available() -> None:
    """Engine README 不得把 Phase 3+ 能力写成当前可用能力。"""

    text = _readme_text()
    forbidden_available_claims = (
        "当前支持 ToolExecutor tool calling 闭环",
        "当前支持 awaiting",
        "当前支持 Host ToolRegistry",
        "当前支持 trace store",
        "当前支持 transcript 持久化",
        "当前支持 conversation memory",
        "当前支持 context budget",
        "当前支持 continuation",
    )

    for fragment in forbidden_available_claims:
        assert fragment not in text
