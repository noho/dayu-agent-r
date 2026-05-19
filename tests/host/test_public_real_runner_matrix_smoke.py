"""P10.5 Slice 6 真实 runner provider matrix smoke。"""

from __future__ import annotations

import pathlib

import pytest

from dayu.host import HostEventKind, HostTerminalStatus, open_host
from tests.host.public_smoke_support import (
    PROVIDER_CASES,
    ProviderSmokeCase,
    api_key_or_skip,
    ensure_request,
    followup_request,
    next_terminal_for_run,
    open_host_options,
    runner_spec_for_case,
    skip_if_provider_terminal_failed,
)


@pytest.mark.asyncio
async def test_mimo_public_real_runner_two_turn_path(
    tmp_path: pathlib.Path,
) -> None:
    """mimo 真实 runner 走 public open_host / watch terminal 路径。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: terminal event 不是成功 final answer 时抛出。
    """

    await _run_provider_case(tmp_path, PROVIDER_CASES[0])


@pytest.mark.asyncio
async def test_deepseek_public_real_runner_two_turn_path(
    tmp_path: pathlib.Path,
) -> None:
    """deepseek 真实 runner 走 public open_host / watch terminal 路径。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: terminal event 不是成功 final answer 时抛出。
    """

    await _run_provider_case(tmp_path, PROVIDER_CASES[1])


@pytest.mark.asyncio
async def test_gemini_public_real_runner_two_turn_path(
    tmp_path: pathlib.Path,
) -> None:
    """gemini 真实 runner 走 public open_host / watch terminal 路径。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: terminal event 不是成功 final answer 时抛出。
    """

    await _run_provider_case(tmp_path, PROVIDER_CASES[2])


@pytest.mark.asyncio
async def test_qwen_public_real_runner_two_turn_path(
    tmp_path: pathlib.Path,
) -> None:
    """qwen 真实 runner 走 public open_host / watch terminal 路径。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: terminal event 不是成功 final answer 时抛出。
    """

    await _run_provider_case(tmp_path, PROVIDER_CASES[3])


async def _run_provider_case(
    tmp_path: pathlib.Path, case: ProviderSmokeCase
) -> None:
    """运行单个 provider two-turn public smoke。

    :param tmp_path: pytest 临时目录。
    :param case: provider case。
    :returns: ``None``。
    :raises AssertionError: provider 返回失败或空 final answer 时抛出。
    """

    api_key = api_key_or_skip(case)
    options = open_host_options(
        tmp_path,
        runner_spec=runner_spec_for_case(case, api_key),
        worker_factory=None,
        allow_tool_calls=False,
        max_tokens=2048,
    )
    async with open_host(options) as host:
        session = await host.ensure_session(ensure_request(f"matrix-{case.name}"))
        watcher = host.watch_session_events(session.session_id)
        first = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                f"{case.name}-first",
                "只回答：4。",
            ),
        )
        first_terminal = await next_terminal_for_run(
            watcher, first.accepted_run_id
        )
        skip_if_provider_terminal_failed(case, first_terminal)
        assert first_terminal.kind is HostEventKind.SUCCEEDED

        second = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                f"{case.name}-second",
                "只输出稳定标记：DAYU_MATRIX_OK。",
            ),
        )
        second_terminal = await next_terminal_for_run(
            watcher, second.accepted_run_id
        )

    skip_if_provider_terminal_failed(case, second_terminal)
    assert second_terminal.terminal_status is HostTerminalStatus.SUCCEEDED
    assert second_terminal.final_answer is not None
    assert second_terminal.final_answer.content.strip() != ""
