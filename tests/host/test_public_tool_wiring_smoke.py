"""P10.5 Slice 6 public mock-tool wiring smoke。"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sqlite3
from contextlib import AsyncExitStack
from dataclasses import replace
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.messages import ToolMessage
from dayu.host import HostEventKind, open_host
from dayu.host.context_budget import (
    ContextEstimateMethod,
    ContextSizingFallbackReason,
)
from dayu.host.context_events import (
    CONTEXT_BUDGET_EVALUATED,
    parse_context_budget_evaluated_payload,
)
from dayu.host.context_policy import default_context_budget_policy
from tests.host.public_smoke_support import (
    FinalAnswerWorkerFactory,
    ToolCallingWorkerFactory,
    assert_at_most_one_system_message,
    close_attachment_shielded,
    deterministic_runner_spec,
    ensure_request,
    followup_request,
    mock_tooling_options,
    next_terminal_for_run,
    open_host_options,
)


@pytest.mark.asyncio
async def test_scripted_runner_without_usage_emits_conservative_fact_and_succeeds(
    tmp_path: pathlib.Path,
) -> None:
    """合法scripted runner不发usage时仍以保守预算事实完成Run。

    :param tmp_path: pytest临时目录。
    :returns: ``None``。
    :raises AssertionError: Host因缺usage失败或未持久化保守事实时抛出。
    """

    factory = ToolCallingWorkerFactory()
    options = replace(
        open_host_options(
            tmp_path,
            runner_spec=deterministic_runner_spec("no-usage-model"),
            worker_factory=factory,
            allow_tool_calls=True,
            tooling_options=mock_tooling_options(),
        ),
        context_budget_policy=default_context_budget_policy(
            context_window_size=100_000
        ),
    )
    async with (
        open_host(options) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(ensure_request("no-usage"))
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        watcher = await host.watch_session_events(session.session_id)
        submitted = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "no-usage-followup",
                "调用 lookup_mock_fact 查询无 usage 路径。",
            ),
        )
        terminal = await next_terminal_for_run(
            watcher,
            submitted.accepted_run_id,
        )

    with sqlite3.connect(tmp_path / "host.sqlite3") as connection:
        rows = connection.execute(
            """
            SELECT event_type, payload_json
            FROM event_log
            WHERE run_id = ?
            ORDER BY event_sequence ASC
            """,
            (submitted.accepted_run_id,),
        ).fetchall()

    assert terminal.kind is HostEventKind.SUCCEEDED
    event_types = tuple(str(row[0]) for row in rows)
    assert "USAGE_REPORTED" not in event_types
    budget_payloads = tuple(
        parse_context_budget_evaluated_payload(
            cast(dict[str, JsonValue], json.loads(str(payload_json)))
        )
        for event_type, payload_json in rows
        if str(event_type) == CONTEXT_BUDGET_EVALUATED
    )
    assert budget_payloads
    assert all(
        payload.estimate_method is ContextEstimateMethod.CONSERVATIVE_FALLBACK
        and payload.fallback_reason is ContextSizingFallbackReason.USAGE_MISSING
        for payload in budget_payloads
    )


@pytest.mark.asyncio
async def test_mock_tool_result_feeds_same_run_and_later_run_continuity(
    tmp_path: pathlib.Path,
) -> None:
    """mock 工具结果经 Host accept barrier 进入同轮 continuation。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 工具结果未进入同轮 continuation，或后续 Run 未保留
        对话连续性时抛出。
    """

    factory = ToolCallingWorkerFactory()
    async with (
        open_host(
            open_host_options(
                tmp_path,
                runner_spec=deterministic_runner_spec("tool-model"),
                worker_factory=factory,
                allow_tool_calls=True,
                tooling_options=mock_tooling_options(),
            )
        ) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(ensure_request("tool-memory"))
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        watcher = await host.watch_session_events(session.session_id)
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
    for index, messages in enumerate(factory.messages_seen):
        assert_at_most_one_system_message(
            messages, label=f"tool wiring runner call {index}"
        )
    assert isinstance(continuation_messages[-1], ToolMessage)
    assert "mock-tool-fact-enters-memory" in continuation_messages[-1].content
    second_run_initial_messages = factory.messages_seen[2]
    joined = "\n".join(
        message.content if message.content is not None else ""
        for message in second_run_initial_messages
    )
    assert "tool fact accepted" in joined
    assert "调用 lookup_mock_fact 查询 DAYU。" in joined
    assert "event_id=event-tool-result-accepted-" not in joined
    assert "event_ref=" not in joined
    assert "payload_ref=" not in joined
    assert "payload_digest=" not in joined
    assert "result_preview" not in joined


@pytest.mark.asyncio
async def test_tool_names_subset_and_empty_freeze(tmp_path: pathlib.Path) -> None:
    """tool_names subset 与 empty 语义冻结到 Engine request。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: subset / empty 工具 schema 不符合预期时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    async with (
        open_host(
            open_host_options(
                tmp_path,
                runner_spec=deterministic_runner_spec("tool-select-model"),
                worker_factory=factory,
                allow_tool_calls=True,
                tooling_options=mock_tooling_options(),
            )
        ) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(ensure_request("tool-select"))
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
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
    for index, request in enumerate(factory.requests):
        assert_at_most_one_system_message(
            request.messages, label=f"tool selection request {index}"
        )
    assert subset_names == ("lookup_mock_fact",)
    assert empty_names == ()
