"""P10.5 Slice 6 public mock-tool wiring smoke。"""

from __future__ import annotations

import pathlib
import asyncio

import pytest

from dayu.engine.contracts.messages import ToolMessage
from dayu.host import HostEventKind, open_host
from tests.host.public_smoke_support import (
    FinalAnswerWorkerFactory,
    ToolCallingWorkerFactory,
    deterministic_runner_spec,
    ensure_request,
    followup_request,
    mock_tooling_options,
    next_terminal_for_run,
    open_host_options,
)


@pytest.mark.asyncio
async def test_mock_tool_fact_enters_memory_and_next_run_input(
    tmp_path: pathlib.Path,
) -> None:
    """mock 工具事实经 Host accept barrier 进入后续 RunInputBuilder 输入。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 工具事实未出现在 continuation 或后续 Run input 时抛出。
    """

    factory = ToolCallingWorkerFactory()
    async with open_host(
        open_host_options(
            tmp_path,
            runner_spec=deterministic_runner_spec("tool-model"),
            worker_factory=factory,
            allow_tool_calls=True,
            tooling_options=mock_tooling_options(),
        )
    ) as host:
        session = await host.ensure_session(ensure_request("tool-memory"))
        watcher = host.watch_session_events(session.session_id)
        first = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "tool-first",
                "调用 lookup_mock_fact 查询 DAYU。",
            ),
        )
        first_terminal = await next_terminal_for_run(watcher, first.accepted_run_id)
        second = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "tool-second",
                "根据已接受工具事实继续回答。",
            ),
        )
        second_terminal = await next_terminal_for_run(watcher, second.accepted_run_id)

    assert first_terminal.kind is HostEventKind.SUCCEEDED
    assert second_terminal.kind is HostEventKind.SUCCEEDED
    continuation_messages = factory.messages_seen[1]
    assert isinstance(continuation_messages[-1], ToolMessage)
    assert "mock-tool-fact-enters-memory" in continuation_messages[-1].content
    second_run_initial_messages = factory.messages_seen[2]
    joined = "\n".join(
        message.content if message.content is not None else ""
        for message in second_run_initial_messages
    )
    assert "event_ref=event-engine-" in joined


@pytest.mark.asyncio
async def test_tool_names_subset_and_empty_freeze(tmp_path: pathlib.Path) -> None:
    """tool_names subset 与 empty 语义冻结到 Engine request。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: subset / empty 工具 schema 不符合预期时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    async with open_host(
        open_host_options(
            tmp_path,
            runner_spec=deterministic_runner_spec("tool-select-model"),
            worker_factory=factory,
            allow_tool_calls=True,
            tooling_options=mock_tooling_options(),
        )
    ) as host:
        session = await host.ensure_session(ensure_request("tool-select"))
        await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "tool-subset",
                "use selected tool",
                tool_names=frozenset({"lookup_mock_fact"}),
            ),
        )
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)
        factory.accepted.clear()
        await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "tool-empty",
                "do not use tools",
                tool_names=frozenset(),
            ),
        )
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)

    subset_names = tuple(
        schema.function.name for schema in factory.requests[0].tool_schemas
    )
    empty_names = tuple(
        schema.function.name for schema in factory.requests[1].tool_schemas
    )
    assert subset_names == ("lookup_mock_fact",)
    assert empty_names == ()
