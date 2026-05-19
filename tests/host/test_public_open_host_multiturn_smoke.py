"""P10.5 Slice 6 public open_host 多轮 smoke 测试。"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.runner_spec import RunnerCallOptions
from dayu.host import Host, HostEventKind, HostTerminalStatus, RunStatus, open_host
from tests.host.public_smoke_support import (
    FinalAnswerWorkerFactory,
    deterministic_runner_spec,
    ensure_request,
    first_available_provider_case,
    followup_request,
    next_terminal_for_run,
    open_host_options,
    runner_spec_for_case,
    skip_if_provider_terminal_failed,
)


@pytest.mark.asyncio
async def test_real_runner_no_tool_two_turn_public_path(
    tmp_path: pathlib.Path,
) -> None:
    """真实 runner 两轮 no-tool 多轮路径只经 public API 与 watch 验证。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 终态事件或 final answer 不符合预期时抛出。
    """

    case, api_key = first_available_provider_case()
    options = open_host_options(
        tmp_path,
        runner_spec=runner_spec_for_case(case, api_key),
        worker_factory=None,
        allow_tool_calls=False,
        max_tokens=2048,
    )
    async with open_host(options) as host:
        session = await host.ensure_session(ensure_request("real-two-turn"))
        watcher = host.watch_session_events(session.session_id)
        first = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "real-first",
                "请只回答这个标记：DAYU_ALPHA。",
            ),
        )
        first_terminal = await next_terminal_for_run(
            watcher, first.accepted_run_id
        )
        skip_if_provider_terminal_failed(case, first_terminal)
        assert first_terminal.kind is HostEventKind.SUCCEEDED
        assert first_terminal.final_answer is not None
        assert first_terminal.final_answer.content.strip() != ""

        second = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "real-second",
                "结合上一轮上下文，只输出这个标记：DAYU_BETA。",
            ),
        )
        second_terminal = await next_terminal_for_run(
            watcher, second.accepted_run_id
        )

    skip_if_provider_terminal_failed(case, second_terminal)
    assert second_terminal.kind is HostEventKind.SUCCEEDED
    assert second_terminal.terminal_status is HostTerminalStatus.SUCCEEDED
    assert second_terminal.final_answer is not None
    assert second_terminal.final_answer.content.strip() != ""


@pytest.mark.asyncio
async def test_two_watchers_observe_same_terminal_event(
    tmp_path: pathlib.Path,
) -> None:
    """两个 public watcher 观察同一个 terminal HostEvent。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 两个 watcher 看到的 terminal identity 不一致时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    async with open_host(
        open_host_options(
            tmp_path,
            runner_spec=deterministic_runner_spec(),
            worker_factory=factory,
            allow_tool_calls=False,
        )
    ) as host:
        session = await host.ensure_session(ensure_request("two-watchers"))
        first_watcher = host.watch_session_events(session.session_id)
        second_watcher = host.watch_session_events(session.session_id)
        followup = await host.submit_followup(
            session.session_id,
            followup_request(session.session_id, "watch-run", "hello"),
        )
        first_terminal, second_terminal = await asyncio.gather(
            next_terminal_for_run(first_watcher, followup.accepted_run_id),
            next_terminal_for_run(second_watcher, followup.accepted_run_id),
        )

    assert first_terminal.event_id == second_terminal.event_id
    assert first_terminal.event_sequence == second_terminal.event_sequence
    assert first_terminal.dedupe_key == second_terminal.dedupe_key
    assert first_terminal.kind is HostEventKind.SUCCEEDED
    assert first_terminal.final_answer is not None


@pytest.mark.asyncio
async def test_deterministic_two_turn_request_contains_prior_final_answer(
    tmp_path: pathlib.Path,
) -> None:
    """两轮 public followup 后第二轮 Engine request 包含第一轮 final_answer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: deterministic worker 未收到连续上下文时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    async with open_host(
        open_host_options(
            tmp_path,
            runner_spec=deterministic_runner_spec(),
            worker_factory=factory,
            allow_tool_calls=False,
        )
    ) as host:
        session = await host.ensure_session(ensure_request("two-turn-continuity"))
        first = await host.submit_followup(
            session.session_id,
            followup_request(session.session_id, "continuity-first", "first prompt"),
        )
        await _wait_for_public_run_status(host, first.accepted_run_id, RunStatus.SUCCEEDED)
        factory.accepted.clear()

        second = await host.submit_followup(
            session.session_id,
            followup_request(session.session_id, "continuity-second", "second prompt"),
        )
        await _wait_for_public_run_status(host, second.accepted_run_id, RunStatus.SUCCEEDED)

    second_contents = tuple(
        message.content for message in factory.requests[1].messages
    )
    assert any(
        content is not None and f"final:1:{first.accepted_run_id}" in content
        for content in second_contents
    )
    assert second_contents[-1] == "second prompt"


@pytest.mark.asyncio
async def test_concurrent_queue_uses_client_request_id_idempotency(
    tmp_path: pathlib.Path,
) -> None:
    """同一 client_request_id 并发重放不重复创建 queued Run。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: queue 顺序或幂等结果不符合预期时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    async with open_host(
        open_host_options(
            tmp_path,
            runner_spec=deterministic_runner_spec(),
            worker_factory=factory,
            allow_tool_calls=False,
        )
    ) as host:
        session = await host.ensure_session(ensure_request("queue-idempotency"))
        request = followup_request(
            session.session_id,
            "concurrent-same",
            "same request",
        )
        first, second = await asyncio.gather(
            host.submit_followup(session.session_id, request),
            host.submit_followup(session.session_id, request),
        )
        distinct = await host.submit_followup(
            session.session_id,
            followup_request(session.session_id, "concurrent-other", "other"),
        )

    assert first.accepted_run_id == second.accepted_run_id
    assert distinct.accepted_run_id != first.accepted_run_id


@pytest.mark.asyncio
async def test_submit_followup_field_level_execution_override_freezes_effective_config(
    tmp_path: pathlib.Path,
) -> None:
    """per-run execution override 按字段 merge 并冻结到 worker request。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: effective config 未按字段冻结时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    baseline_spec = deterministic_runner_spec("baseline-model")
    override_spec = deterministic_runner_spec("override-model")
    override_options = RunnerCallOptions(
        temperature=0.2,
        max_tokens=17,
        top_p=0.9,
        stream=False,
    )
    async with open_host(
        open_host_options(
            tmp_path,
            runner_spec=baseline_spec,
            worker_factory=factory,
            allow_tool_calls=False,
        )
    ) as host:
        session = await host.ensure_session(ensure_request("override"))
        await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "override-options",
                "override options",
                runner_options=override_options,
            ),
        )
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)
        factory.accepted.clear()
        await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "override-spec",
                "override spec",
                runner_spec=override_spec,
            ),
        )
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)

    first_request = factory.requests[0]
    second_request = factory.requests[1]
    assert first_request.runner_spec.model == "baseline-model"
    assert first_request.runner_options == override_options
    assert first_request.agent_policy == AgentPolicy(
        max_iterations=1,
        continuation_max_attempts=0,
        allow_tool_calls=False,
        tool_execution_timeout_seconds=5.0,
    )
    assert second_request.runner_spec.model == "override-model"
    assert second_request.runner_options.max_tokens == 96


async def _wait_for_public_run_status(
    host: Host, run_id: str, expected_status: RunStatus
) -> None:
    """等待 public Run 到达目标状态。

    :param host: public Host handle。
    :param run_id: Run id。
    :param expected_status: 期望状态。
    :returns: ``None``。
    :raises TimeoutError: 超时未达到目标状态时抛出。
    """

    for _index in range(200):
        snapshot = await host.get_run(run_id)
        if snapshot.status == expected_status:
            return
        await asyncio.sleep(0.01)
    raise TimeoutError(f"Run {run_id} did not reach {expected_status.value}")
