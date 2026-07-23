"""P10.5 Slice 5 public resolve_wait resume 测试。"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from contextlib import AsyncExitStack
from dataclasses import replace
from typing import cast

import pytest

import dayu.host.waiting as waiting_module
from dayu.contracts.json_value import JsonValue
from dayu.host import RunStatus, open_host
from dayu.host.context_anchor import (
    CompatibleContextAnchor,
    ContextAnchorResolution,
)
from dayu.host.context_budget import ContextEstimateMethod
from dayu.host.context_events import (
    CONTEXT_BUDGET_EVALUATED,
    parse_context_budget_evaluated_payload,
)
from dayu.host.context_policy import (
    context_budget_policy_from_threshold_tokens,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.event_log import EventLogStore
from dayu.host.durable.transaction import HostTransaction
from dayu.host.run_input import PreparedRunnerCallCandidate
from tests.host.public_smoke_support import (
    AwaitingThenFinalWorkerFactory,
    awaiting_tooling_options,
    close_attachment_shielded,
    completed_wait_request,
    deterministic_runner_spec,
    open_host_options,
    wait_for_public_waiting_run,
)
from tests.host.test_public_retry_replay import (
    _ensure_request,
    _followup_request,
    _wait_for_run_status,
)


@pytest.mark.asyncio
async def test_resolve_wait_resumes_through_open_host_and_terminal_event(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """completed wait resume在同事务解析anchor并恢复执行。

    :param tmp_path: pytest临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    """

    def resolve_anchor(
        transaction: HostTransaction,
        event_log_store: EventLogStore,
        *,
        candidate: PreparedRunnerCallCandidate,
        context_window_size: int,
        candidate_input_cursor: int | None = None,
    ) -> ContextAnchorResolution:
        """为wait resume candidate注入compatible anchor。

        :param transaction: wait resolution transaction。
        :param event_log_store: EventLog primitive。
        :param candidate: complete resume candidate。
        :param context_window_size: frozen source context window。
        :param candidate_input_cursor: 可选scan cursor。
        :returns: compatible anchor。
        """

        del transaction, event_log_store, candidate, candidate_input_cursor
        assert context_window_size > 0
        return ContextAnchorResolution(
            anchor=CompatibleContextAnchor(
                manifest_event_id="event-anchor",
                manifest_payload_ref="payload-anchor",
                manifest_digest=sha256_digest_json({"anchor": "manifest"}),
                iteration_link_event_id="event-anchor-link",
                usage_event_id="event-anchor-usage",
                usage_observation_digest=sha256_digest_json(
                    {"anchor": "usage"}
                ),
                iteration_completed_event_id="event-anchor-completed",
                usage_anchor_tokens=100,
                conservative_anchor_tokens=100,
            ),
            fallback_reason=None,
        )

    monkeypatch.setattr(
        waiting_module,
        "resolve_prepared_runner_call_context_anchor_in_transaction",
        resolve_anchor,
    )

    factory = AwaitingThenFinalWorkerFactory()
    options = replace(
        open_host_options(
            tmp_path,
            runner_spec=deterministic_runner_spec("resolve-wait-model"),
            worker_factory=factory,
            allow_tool_calls=True,
            tooling_options=awaiting_tooling_options(),
        ),
        context_budget_policy=context_budget_policy_from_threshold_tokens(
            context_window_size=32_768,
            soft_threshold_tokens=28_000,
            hard_threshold_tokens=30_000,
        ),
    )
    async with (
        open_host(options) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(_ensure_request("resolve-wait-public"))
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        first = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "resolve-wait-source"),
        )
        waiting = await wait_for_public_waiting_run(
            host, options, first.accepted_run_id
        )

        resolved = await host.resolve_wait(
            waiting.wait_id, completed_wait_request("public-resolve")
        )
        assert resolved.status is RunStatus.RUNNING
        assert resolved.current_attempt_id != waiting.attempt_id
        await _wait_for_run_status(host, waiting.run_id, RunStatus.SUCCEEDED)
    with sqlite3.connect(tmp_path / "host.sqlite3") as connection:
        row = connection.execute(
            """
            SELECT payload_json
            FROM event_log
            WHERE run_id = ? AND event_type = ?
            ORDER BY event_sequence DESC
            LIMIT 1
            """,
            (waiting.run_id, CONTEXT_BUDGET_EVALUATED),
        ).fetchone()
    assert row is not None
    payload = parse_context_budget_evaluated_payload(
        cast(dict[str, JsonValue], json.loads(str(row[0])))
    )
    assert payload.estimate_method is ContextEstimateMethod.USAGE_ANCHORED
    assert payload.anchor_diagnostic is not None
