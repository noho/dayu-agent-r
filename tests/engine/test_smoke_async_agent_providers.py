"""手动 provider smoke 脚本的轻量无网络测试。"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

import pytest

from dayu.engine import EngineEvent, EngineEventType, FinalAnswerData
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import (
    DeepSeekThinkingExtension,
    GeminiThinkingExtension,
    MimoThinkingExtension,
    QwenThinkingExtension,
)
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
    """API key 只进入 headers；final answer 可输出人工核验答案。"""

    case = smoke.CASES[0]
    request = smoke.build_request(
        case=case,
        api_key="SECRET_SENTINEL_KEY",
        stream=True,
        timeout_seconds=30.0,
    )
    event = EngineEvent(
        occurred_at=datetime.now(tz=timezone.utc),
        session_id=request.session_id,
        run_id=request.run_id,
        type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content="ANSWER_SENTINEL",
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        metadata=None,
    )
    summary = smoke.safe_event_summary(event)

    assert request.runner_spec.headers["Authorization"] == (
        "Bearer SECRET_SENTINEL_KEY"
    )
    assert "SECRET_SENTINEL_KEY" not in summary
    assert "ANSWER_SENTINEL" in summary
    assert "用一句话回答" not in summary


def test_print_final_answers_outputs_provider_prompt_and_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """最终汇总应输出 provider、prompt 和 final answer。"""

    smoke.print_final_answers(
        (
            smoke.CaseFinalAnswer(
                provider="mimo",
                prompt="PROMPT_SENTINEL",
                final_answer="ANSWER_SENTINEL",
            ),
        )
    )
    captured = capsys.readouterr()

    assert "FINAL_SUMMARY begin" in captured.out
    assert (
        "FINAL_SUMMARY provider=mimo prompt='PROMPT_SENTINEL' "
        "final_answer='ANSWER_SENTINEL'"
    ) in captured.out
    assert "FINAL_SUMMARY end" in captured.out


def test_all_smoke_cases_enable_thinking() -> None:
    """所有 provider case 都必须显式开启 thinking。"""

    requests = [
        smoke.build_request(
            case=case,
            api_key="KEY",
            stream=True,
            timeout_seconds=30.0,
        )
        for case in smoke.CASES
    ]

    provider_requests = [
        request.runner_spec.provider_request for request in requests
    ]
    assert all(item is not None for item in provider_requests)
    assert isinstance(provider_requests[0], MimoThinkingExtension)
    assert provider_requests[0].enabled is True
    assert isinstance(provider_requests[1], DeepSeekThinkingExtension)
    assert provider_requests[1].enabled is True
    assert isinstance(provider_requests[2], GeminiThinkingExtension)
    assert provider_requests[2].include_thoughts is True
    assert isinstance(provider_requests[3], QwenThinkingExtension)
    assert provider_requests[3].enable_thinking is True


@pytest.mark.asyncio
async def test_selected_cases_output_blank_line_between_cases(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """多个 case 的输出之间保留一个空行。"""

    args = smoke.parse_args(("--all",))
    exit_code = await smoke.run_selected_cases(args=args, env={})
    captured = capsys.readouterr()

    assert exit_code == 0
    assert (
        "missing_env=MIMO_PLAN_API_KEY\n\n"
        "SKIP deepseek-v4-flash missing_env=DEEPSEEK_API_KEY"
        in captured.out
    )
    assert "FINAL_SUMMARY" not in captured.out


def test_smoke_script_does_not_reference_old_runtime_files() -> None:
    """脚本运行时不得读取 OLD 仓库文件。"""

    source = Path(smoke.__file__).read_text(encoding="utf-8")
    assert "workspace/dayu-agent" not in source
    assert "llm_models.json" not in source
