"""手动 tool-call smoke 脚本的轻量无网络测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    ToolCallRequest,
    ToolExecutionContext,
    ToolExecutionRequest,
)
from dayu.engine import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    ToolCallRequestedData,
)
from utils import smoke_async_agent_providers as provider_smoke
from utils import smoke_async_agent_tool_call as smoke


class _Token:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终返回 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


def test_parse_args_and_case_selection() -> None:
    """tool-call smoke 脚本支持 case / stream / timeout 参数。"""

    args = smoke.parse_args(
        (
            "--case",
            "deepseek-v4-flash",
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
    assert selected[0].name == "deepseek-v4-flash"


def test_provider_cases_align_with_provider_smoke() -> None:
    """tool-call smoke 覆盖的 provider 与 provider smoke 对齐。"""

    provider_cases = tuple(case.name for case in provider_smoke.CASES)
    tool_cases = tuple(case.name for case in smoke.CASES)

    assert tool_cases == provider_cases
    assert len(tool_cases) == 4


@pytest.mark.asyncio
async def test_missing_key_skips_without_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """缺少 API key 时友好跳过且退出码为 0。"""

    args = smoke.parse_args(("--case", "deepseek-v4-flash"))
    exit_code = await smoke.run_selected_cases(args=args, env={})
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "SKIP deepseek-v4-flash missing_env=DEEPSEEK_API_KEY" in captured.out
    assert captured.out.endswith("\n\n")


def test_build_request_uses_key_and_fake_tool_schema_safely() -> None:
    """API key 只进入 headers，schema 来自 fake add_numbers。"""

    executor = smoke.AddNumbersToolExecutor()
    request = smoke.build_request(
        case=smoke.CASES[0],
        api_key="SECRET_SENTINEL_KEY",
        stream=True,
        timeout_seconds=30.0,
        tool_executor=executor,
    )

    assert request.runner_spec.headers["Authorization"] == (
        "Bearer SECRET_SENTINEL_KEY"
    )
    assert request.tool_executor is executor
    assert request.tool_schemas[0].function.name == "add_numbers"
    assert request.disable_tools is False
    assert request.agent_policy.allow_tool_calls is True


@pytest.mark.asyncio
async def test_fake_add_numbers_completed_and_failed() -> None:
    """fake add_numbers 能完成安全加法，也能对非法参数返回 failed。"""

    executor = smoke.AddNumbersToolExecutor()
    completed = await executor.execute(
        _tool_request({"a": 2, "b": 3})
    )
    failed = await executor.execute(_tool_request({"a": True, "b": 3}))

    assert type(completed).__name__ == "ToolCompletedOutcome"
    assert type(failed).__name__ == "ToolFailedOutcome"
    assert len(executor.requests) == 2


def test_safe_event_summary_excludes_key_prompt_and_arguments() -> None:
    """摘要不得输出 key、完整 prompt 或工具参数，但应输出 final answer。"""

    event = EngineEvent(
        event_id="run:0",
        sequence=0,
        occurred_at=datetime.now(tz=timezone.utc),
        session_id="session",
        run_id="run",
        type=EngineEventType.TOOL_CALL_REQUESTED,
        data=ToolCallRequestedData(
            iteration_id="iter",
            tool_call_id="tc_1",
            name="add_numbers",
            arguments={"a": 2, "b": 3},
            index_in_iteration=0,
            provider_state=None,
        ),
        metadata=None,
    )
    final = EngineEvent(
        event_id="run:1",
        sequence=1,
        occurred_at=datetime.now(tz=timezone.utc),
        session_id="session",
        run_id="run",
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
    final_summary = smoke.safe_event_summary(final)
    assert "add_numbers" in summary
    assert '"a"' not in summary
    assert "2+3" not in summary
    assert "SECRET_SENTINEL_KEY" not in final_summary
    assert "ANSWER_SENTINEL" in final_summary
    assert "content_len=15" in final_summary
    assert "degraded=False" in final_summary
    assert "filtered=False" in final_summary
    assert "finish_reason=stop" in final_summary


@pytest.mark.asyncio
async def test_run_selected_cases_prints_blank_lines_and_final_summary(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """每个 case 结束后输出空行，并在最后输出 final summary。"""

    async def fake_run_case(
        *,
        case: smoke.ProviderCase,
        api_key: str,
        stream: bool,
        timeout_seconds: float,
    ) -> str:
        """返回 fake final answer。

        :param case: provider case。
        :param api_key: API key。
        :param stream: 是否启用流式。
        :param timeout_seconds: 超时秒数。
        :returns: fake final answer。
        :raises Exception: 不主动抛出异常。
        """

        print(f"CASE {case.name} start stream={stream}")
        return f"final-{case.provider}-{len(api_key)}-{int(timeout_seconds)}"

    monkeypatch.setattr(smoke, "run_case", fake_run_case)

    args = smoke.parse_args(("--all", "--timeout-seconds", "9"))
    env = {case.env_var: "KEY" for case in smoke.CASES}
    exit_code = await smoke.run_selected_cases(args=args, env=env)
    captured = capsys.readouterr()

    assert exit_code == 0
    for case in smoke.CASES:
        assert f"CASE {case.name} start stream=True\n\n" in captured.out
        assert f"FINAL_SUMMARY provider={case.provider}" in captured.out
    assert "FINAL_SUMMARY begin" in captured.out
    assert "FINAL_SUMMARY end" in captured.out


def test_smoke_script_does_not_reference_old_runtime_files() -> None:
    """脚本运行时不得读取 OLD 仓库文件。"""

    source = Path(smoke.__file__).read_text(encoding="utf-8")
    assert "workspace/dayu-agent" not in source
    assert "llm_models.json" not in source


def _tool_request(arguments: dict[str, JsonValue]) -> ToolExecutionRequest:
    """构造 fake 工具请求。

    :param arguments: 工具参数。
    :returns: ToolExecutionRequest。
    :raises Exception: 不主动抛出异常。
    """

    return ToolExecutionRequest(
        call=ToolCallRequest(
            tool_call_id="tc",
            name="add_numbers",
            arguments=arguments,
            index_in_iteration=0,
            provider_state=None,
        ),
        context=ToolExecutionContext(
            run_id="run",
            session_id="session",
            iteration_id="iter",
            tool_call_id="tc",
            index_in_iteration=0,
            timeout_seconds=None,
            cancellation_token=_Token(),
            correlation_id="corr",
        ),
    )
