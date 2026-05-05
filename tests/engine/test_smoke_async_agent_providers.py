"""手动 provider smoke 脚本的轻量无网络测试。"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

import pytest

from dayu.engine import EngineEvent, EngineEventType, FinalAnswerData
from dayu.engine.contracts.finish_reason import FinishReason
from utils import smoke_async_agent_providers as smoke


def test_parse_args_and_case_selection() -> None:
    """smoke 脚本支持 case / all / stream / timeout 参数。"""

    args = smoke.parse_args(
        (
            "--case",
            "mimo-v2.5-pro-plan",
            "--stream",
            "false",
            "--timeout-seconds",
            "12",
        )
    )

    selected = smoke.select_cases(args)
    assert args.stream is False
    assert args.timeout_seconds == 12
    assert len(selected) == 1
    assert selected[0].name == "mimo-v2.5-pro-plan"


@pytest.mark.asyncio
async def test_missing_key_skips_without_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """缺少 API key 时友好跳过且退出码为 0。"""

    args = smoke.parse_args(("--case", "mimo-v2.5-pro-plan"))
    exit_code = await smoke.run_selected_cases(args=args, env={})
    captured = capsys.readouterr()

    assert exit_code == 0
    assert (
        "SKIP mimo-v2.5-pro-plan missing_env=MIMO_PLAN_API_KEY"
        in captured.out
    )


def test_build_request_uses_env_key_without_printing_it() -> None:
    """API key 只进入 headers，不进入安全事件摘要。"""

    case = smoke.CASES[0]
    request = smoke.build_request(
        case=case,
        api_key="SECRET_SENTINEL_KEY",
        stream=True,
        timeout_seconds=30.0,
    )
    event = EngineEvent(
        event_id="run:0",
        sequence=0,
        occurred_at=datetime.now(tz=timezone.utc),
        session_id=request.session_id,
        run_id=request.run_id,
        type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content="ANSWER_SENTINEL",
            filtered=False,
            finish_reason=FinishReason.STOP,
        ),
        metadata=None,
    )
    summary = smoke.safe_event_summary(event)

    assert request.runner_spec.headers["Authorization"] == (
        "Bearer SECRET_SENTINEL_KEY"
    )
    assert "SECRET_SENTINEL_KEY" not in summary
    assert "ANSWER_SENTINEL" not in summary
    assert "用一句话回答" not in summary


def test_smoke_script_does_not_reference_old_runtime_files() -> None:
    """脚本运行时不得读取 OLD 仓库文件。"""

    source = Path(smoke.__file__).read_text(encoding="utf-8")
    assert "workspace/dayu-agent" not in source
    assert "llm_models.json" not in source
