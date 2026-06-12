"""Host Conversation Memory vNext projection 与 durable primitive 测试。"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.context_events import CONTEXT_COMPACTED, CONTEXT_COMPACTION_FAILED
from dayu.host.durable import memory as durable_memory_module
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.connection import HostDurableStore
from dayu.host.durable.codec import canonical_json_dumps
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    append_event,
)
from dayu.host.durable.memory import (
    ConversationMemoryProjectionConsumer,
    MemorySnapshotIntegrityFailureKind,
    inspect_memory_snapshot_integrity,
    read_latest_memory_snapshot,
    read_memory_snapshot,
    write_memory_snapshot_with_checkpoint,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.projection import read_projection_checkpoint
from dayu.host.durable.schema import (
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_SNAPSHOTS,
)
from dayu.host.durable.transaction import HostRow, HostTransaction
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationMemorySnapshotVNext,
    MemoryDiagnosticReason,
    MemoryIncludedReason,
    MemoryProjectionEvent,
    MemoryProjectionPolicy,
    SelectedRecentWindowRole,
    build_conversation_memory_snapshot_from_events,
    build_empty_conversation_memory_snapshot,
    calculate_memory_snapshot_digest,
    conversation_memory_snapshot_from_json_value,
    conversation_memory_snapshot_to_json_value,
    default_memory_projection_policy,
    digest_memory_projection_policy,
    project_conversation_memory_event,
    stable_memory_snapshot_id,
)
from dayu.host.projection import ProjectionRunner

_SESSION_ID = "session-1"
_RUN_ID = "run-1"
_ATTEMPT_ID = "attempt-1"
_EXECUTION_ID = "execution-1"
_NOW = "2026-05-16T00:00:00.000000Z"
_OCCURRED_AT = datetime(2026, 5, 16, tzinfo=UTC)

_POLICY_FIELDS = (
    "context_window_size",
    "selected_recent_window_item_cap",
    "selected_recent_window_char_cap",
    "selected_recent_window_turn_floor",
    "fallback_selected_recent_window_item_cap",
    "fallback_selected_recent_window_char_cap",
    "evidence_fact_item_cap",
    "evidence_fact_char_cap",
    "evidence_fact_floor",
    "session_summary_char_cap",
    "answer_anchor_item_cap",
    "answer_anchor_char_cap",
    "forward_intent_item_cap",
    "forward_intent_char_cap",
    "reference_continuity_item_cap",
    "reference_continuity_char_cap",
    "reference_continuity_item_floor",
    "max_lag_events_for_inline_delta",
    "max_delta_repair_events",
    "policy_ref",
)

_SNAPSHOT_FIELDS = (
    "schema_version",
    "snapshot_id",
    "session_id",
    "cursor",
    "policy_digest",
    "latest_compaction_event_ref",
    "trace_memory",
    "evidence_fact_memory",
    "session_summary_memory",
    "answer_anchor_memory",
    "forward_intent_memory",
    "diagnostics",
    "built_at",
    "snapshot_digest",
)


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )


def _policy() -> MemoryProjectionPolicy:
    """构造 vNext memory projection policy。

    :returns: memory projection policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        selected_recent_window_item_cap=8,
        selected_recent_window_char_cap=2048,
        selected_recent_window_turn_floor=2,
        fallback_selected_recent_window_item_cap=4,
        fallback_selected_recent_window_char_cap=1024,
        evidence_fact_item_cap=4,
        evidence_fact_char_cap=2048,
        evidence_fact_floor=1,
        session_summary_char_cap=1024,
        answer_anchor_item_cap=4,
        answer_anchor_char_cap=1024,
        forward_intent_item_cap=4,
        forward_intent_char_cap=1024,
        reference_continuity_item_cap=4,
        reference_continuity_char_cap=1024,
        reference_continuity_item_floor=0,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
        policy_ref="test-memory-vnext",
    )


def _event(
    sequence: int,
    event_id: str,
    event_type: str,
    payload: dict[str, JsonValue],
) -> MemoryProjectionEvent:
    """构造 memory projection event。

    :param sequence: EventLog sequence。
    :param event_id: event id。
    :param event_type: event type。
    :param payload: canonical payload。
    :returns: memory projection event。
    """

    return MemoryProjectionEvent(
        event_sequence=sequence,
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT.value,
        event_type=event_type,
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        attempt_id=_ATTEMPT_ID,
        execution_id=_EXECUTION_ID,
        occurred_at=_NOW,
        payload_ref=None,
        payload_digest=None,
        payload=payload,
    )


def _accepted_compact_payload(
    *,
    facts: list[dict[str, JsonValue]] | None = None,
) -> dict[str, JsonValue]:
    """构造 accepted vNext compact payload。

    :param facts: 可选 evidence-backed fact candidates。
    :returns: CONTEXT_COMPACTED payload。
    """

    accepted_candidate = cast(dict[str, JsonValue], {
        "schema_version": "conversation_compact_output_v1",
        "session_summary": {
            "summary_text": "用户关注收入增速和毛利率变化。",
            "source_labels": ["u1"],
        },
        "evidence_backed_facts": [] if facts is None else facts,
        "answer_anchors": [
            {
                "anchor_title": "收入口径",
                "anchor_items": [
                    {"display_text": "同比收入增速来自已接受证据。", "ordinal": 1}
                ],
                "answer_source_labels": ["e1"],
            }
        ],
        "forward_intents": [
            {
                "intent_type": "follow_up",
                "text": "下一轮继续核对费用率。",
                "status": "open",
                "source_labels": ["u1"],
            }
        ],
        "reference_continuity_items": [
            {
                "text": "“该公司”继续指向当前分析主体。",
                "reason": "pronoun_resolution",
                "source_labels": ["u1"],
            }
        ],
        "diagnostics": [],
    })
    return {
        "accepted_candidate": accepted_candidate,
        "accepted_evidence_mapping_refs": ["event:tool-1"],
        "compact_artifact_ref": "artifact:compact-1",
    }


def _fact(claim_text: str) -> dict[str, JsonValue]:
    """构造 fact candidate。

    :param claim_text: fact claim 文本。
    :returns: fact candidate JSON object。
    """

    return {
        "claim_text": claim_text,
        "evidence_labels": ["e1"],
    }


def _memory_item_count(transaction: HostTransaction) -> int:
    """读取 memory item durable row 数。

    :param transaction: Host transaction。
    :returns: memory item row 数。
    """

    row = transaction.fetchone(
        f"SELECT COUNT(*) AS count FROM {TABLE_HOST_MEMORY_ITEMS}"
    )
    assert row is not None
    count = row.get("count")
    assert isinstance(count, int)
    return count


def test_memory_projection_policy_contract_uses_design_source_fields() -> None:
    """MemoryProjectionPolicy 字段集合只包含设计真源字段。"""

    assert tuple(field.name for field in fields(MemoryProjectionPolicy)) == _POLICY_FIELDS


def test_conversation_memory_snapshot_vnext_contract_fields_are_fixed() -> None:
    """ConversationMemorySnapshotVNext 字段集合固定为 vNext contract。"""

    assert (
        tuple(field.name for field in fields(ConversationMemorySnapshotVNext))
        == _SNAPSHOT_FIELDS
    )


def test_pre_compact_projection_only_builds_selected_recent_window() -> None:
    """compact 前 projection 只形成 selected recent window 可读材料。"""

    policy = _policy()
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(1, "user-1", "USER_INPUT_ACCEPTED", {"display_text": "请分析收入。"}),
            _event(2, "run-1", "RUN_SUCCEEDED", {"final_answer": "收入同比增长。"}),
            _event(
                3,
                "tool-1",
                "TOOL_RESULT_ACCEPTED",
                {"display_text": "10-K revenue table"},
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert tuple(
        item.role for item in snapshot.trace_memory.selected_recent_window
    ) == (
        SelectedRecentWindowRole.USER,
        SelectedRecentWindowRole.ASSISTANT,
        SelectedRecentWindowRole.EVIDENCE,
    )
    assistant_item = snapshot.trace_memory.selected_recent_window[1]
    assert assistant_item.included_reason is MemoryIncludedReason.SELECTED_RECENT_WINDOW
    assert snapshot.session_summary_memory.summary_text is None
    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()
    assert snapshot.answer_anchor_memory.anchors == ()
    assert snapshot.forward_intent_memory.intents == ()


def test_accepted_compact_materializes_vnext_memory_sections() -> None:
    """accepted CONTEXT_COMPACTED 物化 vNext memory sections。"""

    policy = _policy()
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(1, "user-1", "USER_INPUT_ACCEPTED", {"display_text": "请分析收入。"}),
            _event(
                2,
                "compact-1",
                CONTEXT_COMPACTED,
                _accepted_compact_payload(facts=[_fact("收入同比增长 12%。")]),
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert snapshot.latest_compaction_event_ref == "compact-1"
    assert snapshot.session_summary_memory.summary_text == "用户关注收入增速和毛利率变化。"
    assert snapshot.evidence_fact_memory.evidence_backed_facts[0].claim_text == (
        "收入同比增长 12%。"
    )
    assert snapshot.answer_anchor_memory.anchors[0].anchor_title == "收入口径"
    assert snapshot.forward_intent_memory.intents[0].text == "下一轮继续核对费用率。"
    assert snapshot.trace_memory.reference_continuity_items[0].reason == (
        "pronoun_resolution"
    )


def test_run_succeeded_summary_only_does_not_materialize_assistant_window() -> None:
    """只有 summary_text 或 nested summary 时不生成 assistant selected recent item。"""

    policy = _policy()
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "run-summary-only",
                "RUN_SUCCEEDED",
                {
                    "summary_text": "摘要不应进入 assistant final answer",
                    "summary": {"summary_text": "nested 摘要也不应进入"},
                },
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert snapshot.trace_memory.selected_recent_window == ()
    assert snapshot.session_summary_memory.summary_text is None


def test_run_succeeded_payload_refs_do_not_materialize_assistant_window() -> None:
    """缺失 final answer 时不把 ref / digest / event id 投影给 assistant window。"""

    policy = _policy()
    event = _event(1, "run-ref-only", "RUN_SUCCEEDED", {})
    event = replace(event, payload_ref="payload-run", payload_digest="sha256:digest")

    snapshot = build_conversation_memory_snapshot_from_events(
        events=(event,),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert snapshot.trace_memory.selected_recent_window == ()


def test_durable_projection_hydrates_terminal_content_as_selected_recent_window(
    tmp_path: Path,
) -> None:
    """durable projection adapter hydrate terminal content 后进入 continuity。"""

    policy = _policy()
    with open_host_durable_store(_options(tmp_path)) as store:

        def append_run_succeeded(transaction: HostTransaction) -> None:
            """写入 terminal artifact 与仅含 descriptor 的 RUN_SUCCEEDED。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-terminal-final-answer",
                    payload_id="sqlite-terminal-final-answer",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={
                        "content": "artifact final answer",
                        "summary_text": "artifact summary",
                    },
                ),
            )
            append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="run-terminal-content",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    event_type="RUN_SUCCEEDED",
                    occurred_at=_OCCURRED_AT,
                    actor="pytest",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json={
                        "final_answer": " ",
                        "content": "裸 content 不应进入 assistant window",
                        "summary_text": "run summary 不应进入 assistant window",
                        "terminal_summary_ref": descriptor.payload_ref,
                        "terminal_summary_digest": descriptor.payload_digest,
                    },
                    payload_ref=None,
                    payload_digest=None,
                ),
            )

        store.transaction_runner.run_write(append_run_succeeded)
        consumer = ConversationMemoryProjectionConsumer(policy)
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        policy_digest = digest_memory_projection_policy(policy)
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=policy_digest,
            )
        )

        assert latest is not None
        selected = latest.snapshot.trace_memory.selected_recent_window
        assert len(selected) == 1
        assert selected[0].text == "artifact final answer"
        assert selected[0].included_reason is MemoryIncludedReason.SELECTED_RECENT_WINDOW
        assert latest.snapshot.evidence_fact_memory.evidence_backed_facts == ()


def test_memory_direct_consumer_does_not_follow_terminal_descriptor() -> None:
    """直接 memory consumer 不跟随 terminal summary descriptor。

    Durable projection / run-input adapter 负责把 digest-checked terminal content
    合并成 transient ``final_answer``；纯 consumer 只读取 inline final_answer。

    :returns: ``None``。
    :raises AssertionError: direct consumer 错误跟随 descriptor 时抛出。
    """

    policy = _policy()
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "run-descriptor-only",
                "RUN_SUCCEEDED",
                {
                    "terminal_summary_ref": "payload-terminal-final-answer",
                    "terminal_summary_digest": "sha256:terminal-final-answer",
                    "content": "裸 content 不应进入 assistant window",
                    "summary_text": "summary 不应进入 assistant window",
                },
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert snapshot.trace_memory.selected_recent_window == ()
    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()


def test_accepted_compact_limits_evidence_facts_and_records_budget_diagnostic() -> None:
    """Evidence facts 超过 section cap 时截断并记录 budget diagnostic。"""

    policy = replace(_policy(), evidence_fact_item_cap=1, evidence_fact_floor=0)
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "compact-1",
                CONTEXT_COMPACTED,
                _accepted_compact_payload(
                    facts=[
                        _fact("旧 fact 应被截断。"),
                        _fact("新 fact 应被保留。"),
                    ],
                ),
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert tuple(
        fact.claim_text
        for fact in snapshot.evidence_fact_memory.evidence_backed_facts
    ) == ("新 fact 应被保留。",)
    assert MemoryDiagnosticReason.BUDGET_LIMIT_REACHED in tuple(
        diagnostic.reason for diagnostic in snapshot.diagnostics
    )


def test_accepted_evidence_without_fact_candidate_records_diagnostic_only() -> None:
    """accepted evidence 存在但无 fact candidate 时不合成 fallback fact。"""

    policy = _policy()
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=_event(1, "compact-1", CONTEXT_COMPACTED, _accepted_compact_payload()),
        policy=policy,
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )

    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()
    assert tuple(diagnostic.reason for diagnostic in snapshot.diagnostics) == (
        MemoryDiagnosticReason.ACCEPTED_EVIDENCE_WITHOUT_FACT_CANDIDATE,
    )


def test_failed_compaction_event_does_not_materialize_memory_sections() -> None:
    """failed compaction event 不物化 summary、fact、anchor 或 intent。"""

    policy = _policy()
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=_event(1, "failed-1", "CONTEXT_COMPACTION_FAILED", {"reason": "over"}),
        policy=policy,
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )

    assert snapshot.session_summary_memory.summary_text is None
    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()
    assert snapshot.answer_anchor_memory.anchors == ()
    assert snapshot.forward_intent_memory.intents == ()
    assert snapshot.trace_memory.reference_continuity_items == ()
    assert snapshot.diagnostics[0].reason is MemoryDiagnosticReason.UNSUPPORTED_EVENT_TYPE


def test_snapshot_json_roundtrip_preserves_vnext_sections() -> None:
    """snapshot JSON codec 保留 vNext sections 与 digest。"""

    policy = _policy()
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=_event(
            1,
            "compact-1",
            CONTEXT_COMPACTED,
            _accepted_compact_payload(facts=[_fact("毛利率提升。")]),
        ),
        policy=policy,
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )

    value = conversation_memory_snapshot_to_json_value(snapshot)
    restored = conversation_memory_snapshot_from_json_value(value)

    assert restored == snapshot
    assert restored.snapshot_digest == calculate_memory_snapshot_digest(restored)


def test_write_snapshot_with_checkpoint_commits_snapshot_before_checkpoint(
    tmp_path: Path,
) -> None:
    """snapshot 与 projection checkpoint 在同一 durable transaction 提交。"""

    policy = _policy()
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=_event(
            1,
            "compact-1",
            CONTEXT_COMPACTED,
            _accepted_compact_payload(facts=[_fact("收入增长。")]),
        ),
        policy=policy,
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="compact-1",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    event_type=CONTEXT_COMPACTED,
                    occurred_at=_OCCURRED_AT,
                    actor="pytest",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json=_accepted_compact_payload(facts=[_fact("收入增长。")]),
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
        )
        written = store.transaction_runner.run_write(
            lambda transaction: write_memory_snapshot_with_checkpoint(
                transaction,
                snapshot,
                now=_NOW,
            )
        )
        read_back = store.transaction_runner.run_read(
            lambda transaction: read_memory_snapshot(transaction, snapshot.snapshot_id)
        )
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction,
                CONVERSATION_MEMORY_CONSUMER_ID,
            )
        )

        assert read_back is not None
        assert written.snapshot.snapshot_id == read_back.snapshot.snapshot_id
        assert checkpoint is not None
        assert (
            checkpoint.checkpoint_event_sequence
            == snapshot.cursor.checkpoint_event_sequence
        )
        assert checkpoint.checkpoint_event_id == snapshot.cursor.checkpoint_event_id


def test_projection_consumer_applies_event_and_writes_durable_vnext_snapshot(
    tmp_path: Path,
) -> None:
    """accepted compact 经 ProjectionRunner 物化五类 memory section 与 checkpoint。"""

    policy = _policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="compact-1",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    event_type=CONTEXT_COMPACTED,
                    occurred_at=_OCCURRED_AT,
                    actor="pytest",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json=_accepted_compact_payload(facts=[_fact("收入增长。")]),
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        policy_digest = digest_memory_projection_policy(policy)
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=policy_digest,
            )
        )
        item_kinds = store.transaction_runner.run_read(
            lambda transaction: tuple(
                cast(
                    str,
                    row.get("item_kind"),
                )
                for row in transaction.fetchall(
                    f"""
                    SELECT item_kind
                    FROM {TABLE_HOST_MEMORY_ITEMS}
                    ORDER BY item_kind
                    """
                )
            )
        )
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction,
                CONVERSATION_MEMORY_CONSUMER_ID,
            )
        )

        assert latest is not None
        assert latest.snapshot.latest_compaction_event_ref == "compact-1"
        assert latest.snapshot.session_summary_memory.summary_text == (
            "用户关注收入增速和毛利率变化。"
        )
        assert (
            latest.snapshot.evidence_fact_memory.evidence_backed_facts[0].claim_text
            == "收入增长。"
        )
        assert latest.snapshot.answer_anchor_memory.anchors[0].anchor_title == (
            "收入口径"
        )
        assert latest.snapshot.forward_intent_memory.intents[0].text == (
            "下一轮继续核对费用率。"
        )
        assert latest.snapshot.trace_memory.reference_continuity_items[0].text == (
            "“该公司”继续指向当前分析主体。"
        )
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 1
        assert checkpoint.checkpoint_event_id == "compact-1"
        assert (
            latest.snapshot.cursor.checkpoint_event_sequence
            == checkpoint.checkpoint_event_sequence
        )
        assert latest.snapshot.cursor.checkpoint_event_id == checkpoint.checkpoint_event_id
        assert set(item_kinds) == {
            "answer_anchor",
            "evidence_backed_fact",
            "forward_intent",
            "reference_continuity",
            "session_summary",
        }


def test_projection_consumer_skips_failed_compact_without_memory_snapshot(
    tmp_path: Path,
) -> None:
    """failed compact 不进入 Conversation Memory snapshot 或 compact sections。"""

    policy = _policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="compact-failed-1",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    event_type=CONTEXT_COMPACTION_FAILED,
                    occurred_at=_OCCURRED_AT,
                    actor="pytest",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json={"failure_reason": "compactor_unavailable"},
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        policy_digest = digest_memory_projection_policy(policy)
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=policy_digest,
            )
        )
        item_count = store.transaction_runner.run_read(_memory_item_count)
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction,
                CONVERSATION_MEMORY_CONSUMER_ID,
            )
        )

        assert result.events_scanned == 1
        assert result.events_matched == 0
        assert result.events_applied == 0
        assert latest is None
        assert item_count == 0
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 1
        assert checkpoint.checkpoint_event_id == "compact-failed-1"


def test_policy_digest_changes_when_design_field_changes() -> None:
    """policy digest 覆盖 vNext 字段变化。"""

    policy = _policy()
    changed = replace(policy, forward_intent_item_cap=policy.forward_intent_item_cap + 1)

    assert digest_memory_projection_policy(policy) != digest_memory_projection_policy(changed)


def test_empty_snapshot_uses_stable_id_and_vnext_empty_views() -> None:
    """空 snapshot 使用稳定 id 并初始化 vNext 空 view。"""

    policy = default_memory_projection_policy()
    policy_digest = digest_memory_projection_policy(policy)
    snapshot_id = stable_memory_snapshot_id(
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy_digest=policy_digest,
    )

    snapshot = build_empty_conversation_memory_snapshot(
        snapshot_id=snapshot_id,
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy_digest=policy_digest,
        built_at=_NOW,
    )

    assert snapshot.snapshot_id == snapshot_id
    assert snapshot.trace_memory.selected_recent_window == ()
    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()
    assert snapshot.snapshot_digest == calculate_memory_snapshot_digest(snapshot)


def test_memory_snapshot_integrity_empty_and_valid_rows_return_no_issues(
    tmp_path: Path,
) -> None:
    """Memory snapshot integrity classifier 对空库和有效 row 返回空诊断。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        empty_issues = store.transaction_runner.run_read(
            inspect_memory_snapshot_integrity
        )
        snapshot = _write_integrity_compact_snapshot(store)
        valid_issues = store.transaction_runner.run_read(
            inspect_memory_snapshot_integrity
        )
        read_back = store.transaction_runner.run_read(
            lambda transaction: read_memory_snapshot(
                transaction,
                snapshot.snapshot_id,
            )
        )

        assert empty_issues == ()
        assert valid_issues == ()
        assert read_back is not None


def test_memory_snapshot_integrity_classifies_invalid_json(tmp_path: Path) -> None:
    """Memory snapshot integrity classifier 识别非法 JSON。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        _replace_snapshot_json(store, snapshot.snapshot_id, "{not-json")

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert issues[0].failure_kind is MemorySnapshotIntegrityFailureKind.INVALID_JSON
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_classifies_schema_mismatch(tmp_path: Path) -> None:
    """Memory snapshot integrity classifier 识别 schema-mismatched JSON。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        _replace_snapshot_json(
            store,
            snapshot.snapshot_id,
            canonical_json_dumps({"schema_version": "conversation_memory_snapshot_v1"}),
        )

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.SCHEMA_MISMATCH
        )
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_classifies_manual_digest_mismatch(
    tmp_path: Path,
) -> None:
    """手动 SQL 篡改合法 JSON 内容时归类为 digest mismatch。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        corrupted_json = _snapshot_json_with_changed_built_at(snapshot)
        _replace_snapshot_json(store, snapshot.snapshot_id, corrupted_json)

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.DIGEST_MISMATCH
        )
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_classifies_row_digest_column_mismatch(
    tmp_path: Path,
) -> None:
    """手动 SQL 篡改 snapshot_digest 列时归类为 digest mismatch。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        _replace_snapshot_digest(store, snapshot.snapshot_id, "sha256:manual-corrupt")

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.DIGEST_MISMATCH
        )
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_classifies_unsupported_old_item_kind(
    tmp_path: Path,
) -> None:
    """旧 durable verified_fact item kind 被分类并继续使普通读路径 fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        _insert_old_verified_fact_item(store, snapshot)

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        with pytest.raises(HostDurableError, match="verified_fact"):
            store.transaction_runner.run_read(
                lambda transaction: read_memory_snapshot(
                    transaction,
                    snapshot.snapshot_id,
                )
            )

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.UNSUPPORTED_ITEM_KIND
        )
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_classifies_unknown_item_kind(tmp_path: Path) -> None:
    """未知 durable memory item kind 被分类为 unsupported item kind。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        _insert_unsupported_memory_item_kind(store, snapshot, "mystery_memory_kind")

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.UNSUPPORTED_ITEM_KIND
        )
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_reports_mixed_damaged_rows(
    tmp_path: Path,
) -> None:
    """Memory snapshot integrity classifier 对多个 damaged rows 返回全部诊断。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        first_snapshot = _write_integrity_compact_snapshot(
            store,
            event_id="compact-1",
            claim_text="收入增长。",
        )
        second_snapshot = _write_integrity_compact_snapshot(
            store,
            event_id="compact-2",
            claim_text="利润提升。",
            session_id="session-2",
            event_sequence=2,
        )
        _replace_snapshot_json(store, first_snapshot.snapshot_id, "{not-json")
        _replace_snapshot_json(
            store,
            second_snapshot.snapshot_id,
            _snapshot_json_with_changed_built_at(second_snapshot),
        )

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert {issue.failure_kind for issue in issues} == {
            MemorySnapshotIntegrityFailureKind.INVALID_JSON,
            MemorySnapshotIntegrityFailureKind.DIGEST_MISMATCH,
        }


def test_memory_snapshot_integrity_classifies_storage_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memory snapshot integrity scan 读取失败时返回 storage_read_failed。"""

    def _raise_storage_read_failed(
        transaction: HostTransaction,
    ) -> tuple[HostRow, ...]:
        """模拟 SQLite scan failure。

        :param transaction: Host durable transaction。
        :returns: 不返回；始终抛出 SQLite 错误。
        :raises sqlite3.OperationalError: 始终抛出。
        """

        del transaction
        raise sqlite3.OperationalError("forced snapshot scan failure")

    monkeypatch.setattr(
        durable_memory_module,
        "_memory_snapshot_integrity_rows",
        _raise_storage_read_failed,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.STORAGE_READ_FAILED
        )
        assert issues[0].snapshot_id is None


def _write_integrity_compact_snapshot(
    store: HostDurableStore,
    *,
    event_id: str = "compact-1",
    claim_text: str = "收入增长。",
    session_id: str = _SESSION_ID,
    event_sequence: int = 1,
) -> ConversationMemorySnapshotVNext:
    """写入测试用 compact event 与 memory snapshot。

    :param store: Host durable store。
    :param event_id: compact event id。
    :param claim_text: compact fact claim 文本。
    :param session_id: snapshot 所属 session id。
    :param event_sequence: compact event sequence。
    :returns: 已写入的 memory snapshot。
    """

    payload = _accepted_compact_payload(facts=[_fact(claim_text)])
    store.transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=_RUN_ID,
                attempt_id=_ATTEMPT_ID,
                execution_id=_EXECUTION_ID,
                event_type=CONTEXT_COMPACTED,
                occurred_at=_OCCURRED_AT,
                actor="pytest",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=payload,
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
    )
    projection_event = MemoryProjectionEvent(
        event_sequence=event_sequence,
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT.value,
        event_type=CONTEXT_COMPACTED,
        session_id=session_id,
        run_id=_RUN_ID,
        attempt_id=_ATTEMPT_ID,
        execution_id=_EXECUTION_ID,
        occurred_at=_NOW,
        payload_ref=None,
        payload_digest=None,
        payload=payload,
    )
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=projection_event,
        policy=_policy(),
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )
    store.transaction_runner.run_write(
        lambda transaction: write_memory_snapshot_with_checkpoint(
            transaction,
            snapshot,
            now=_NOW,
        )
    )
    return snapshot


def _replace_snapshot_json(
    store: HostDurableStore,
    snapshot_id: str,
    snapshot_json: str,
) -> None:
    """直接替换 snapshot JSON 以模拟手动 durable corruption。

    :param store: Host durable store。
    :param snapshot_id: snapshot id。
    :param snapshot_json: 替换后的 JSON 文本。
    :returns: ``None``。
    """

    store.transaction_runner.run_write(
        lambda transaction: transaction.execute(
            f"""
            UPDATE {TABLE_HOST_MEMORY_SNAPSHOTS}
            SET snapshot_json = ?
            WHERE snapshot_id = ?
            """,
            (snapshot_json, snapshot_id),
        )
    )


def _replace_snapshot_digest(
    store: HostDurableStore,
    snapshot_id: str,
    snapshot_digest: str,
) -> None:
    """直接替换 snapshot digest 列以模拟手动 durable corruption。

    :param store: Host durable store。
    :param snapshot_id: snapshot id。
    :param snapshot_digest: 替换后的 digest 文本。
    :returns: ``None``。
    """

    store.transaction_runner.run_write(
        lambda transaction: transaction.execute(
            f"""
            UPDATE {TABLE_HOST_MEMORY_SNAPSHOTS}
            SET snapshot_digest = ?
            WHERE snapshot_id = ?
            """,
            (snapshot_digest, snapshot_id),
        )
    )


def _snapshot_json_with_changed_built_at(
    snapshot: ConversationMemorySnapshotVNext,
) -> str:
    """返回保留旧 digest 但内容已变更的 snapshot JSON。

    :param snapshot: 原始 snapshot。
    :returns: digest mismatch JSON 文本。
    """

    snapshot_value = conversation_memory_snapshot_to_json_value(snapshot)
    if not isinstance(snapshot_value, Mapping):
        raise AssertionError("snapshot JSON value must be an object")
    corrupted_value: dict[str, JsonValue] = dict(snapshot_value)
    corrupted_value["built_at"] = "2026-05-17T00:00:00.000000Z"
    return canonical_json_dumps(corrupted_value)


def _insert_old_verified_fact_item(
    store: HostDurableStore,
    snapshot: ConversationMemorySnapshotVNext,
) -> None:
    """插入旧 verified_fact item kind 以模拟旧库或手工损坏。

    :param store: Host durable store。
    :param snapshot: 已存在的 memory snapshot。
    :returns: ``None``。
    """

    _insert_unsupported_memory_item_kind(store, snapshot, "verified_fact")


def _insert_unsupported_memory_item_kind(
    store: HostDurableStore,
    snapshot: ConversationMemorySnapshotVNext,
    item_kind: str,
) -> None:
    """插入不受支持的 item kind 以模拟旧库或手工损坏。

    :param store: Host durable store。
    :param snapshot: 已存在的 memory snapshot。
    :param item_kind: 待插入的 item kind。
    :returns: ``None``。
    """

    store.transaction_runner.run_write(
        lambda transaction: _insert_unsupported_memory_item_kind_in_transaction(
            transaction,
            snapshot,
            item_kind,
        )
    )


def _insert_unsupported_memory_item_kind_in_transaction(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
    item_kind: str,
) -> None:
    """在当前 transaction 中插入不受支持的 item kind。

    :param transaction: Host durable transaction。
    :param snapshot: 已存在的 memory snapshot。
    :param item_kind: 待插入的 item kind。
    :returns: ``None``。
    """

    transaction.execute("PRAGMA ignore_check_constraints = ON")
    try:
        transaction.execute(
            f"""
            INSERT INTO {TABLE_HOST_MEMORY_ITEMS} (
              item_id,
              snapshot_id,
              session_id,
              item_kind,
              claim_status,
              event_id,
              event_sequence,
              producer_kind,
              producer_name,
              payload_ref,
              payload_digest,
              item_json,
              included_reason,
              excluded_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "old-verified-fact-item",
                snapshot.snapshot_id,
                snapshot.session_id,
                item_kind,
                "evidence_backed",
                snapshot.cursor.checkpoint_event_id,
                snapshot.cursor.checkpoint_event_sequence,
                "tool",
                "pytest",
                None,
                None,
                "{}",
                None,
                None,
            ),
        )
    finally:
        transaction.execute("PRAGMA ignore_check_constraints = OFF")
