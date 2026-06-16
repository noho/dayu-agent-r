"""``dayu-cli session`` helper 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

from dayu.cli.output import render_session_list, render_session_purge_result
from dayu.cli.session_identity import (
    CliSessionDisplayKind,
    CliSessionLabelKind,
    display_identity_from_slot,
    slot_ref_for_cli_label,
)
from dayu.host.api import (
    HostStreamCursor,
    ListSessionsResult,
    PurgeSessionResult,
    SessionListItem,
    SessionSlotRef,
    SessionStatus,
)


def test_cli_label_kind_maps_to_host_slot_ref() -> None:
    """CLI label kind 必须映射到对应 Host slot namespace。

    :returns: ``None``。
    :raises AssertionError: slot ref 映射不符合 CLI label namespace 时抛出。
    """

    prompt_slot = slot_ref_for_cli_label(CliSessionLabelKind.PROMPT, " proj.v1 ")
    interactive_slot = slot_ref_for_cli_label(
        CliSessionLabelKind.INTERACTIVE,
        "earnings",
    )

    assert prompt_slot == SessionSlotRef(
        scope="cli.prompt",
        slot_key="cli.prompt.proj.v1",
    )
    assert interactive_slot == SessionSlotRef(
        scope="cli.interactive",
        slot_key="cli.interactive.earnings",
    )


def test_display_identity_from_slot_covers_cli_and_other_slots() -> None:
    """Session list slot 反解必须覆盖 anonymous、prompt、interactive、other。

    :returns: ``None``。
    :raises AssertionError: 任一 slot 展示身份反解不符合固定规则时抛出。
    """

    anonymous = display_identity_from_slot(None)
    prompt = display_identity_from_slot(
        SessionSlotRef(scope="cli.prompt", slot_key="cli.prompt.proj.v1")
    )
    interactive = display_identity_from_slot(
        SessionSlotRef(
            scope="cli.interactive",
            slot_key="cli.interactive.earnings",
        )
    )
    other_scope = display_identity_from_slot(
        SessionSlotRef(scope="service.workflow", slot_key="workflow.alpha")
    )
    prompt_bad_prefix = display_identity_from_slot(
        SessionSlotRef(scope="cli.prompt", slot_key="not-cli.prompt.alpha")
    )
    prompt_empty_suffix = display_identity_from_slot(
        SessionSlotRef(scope="cli.prompt", slot_key="cli.prompt.")
    )

    assert anonymous.kind is CliSessionDisplayKind.ANONYMOUS
    assert anonymous.label == "-"
    assert prompt.kind is CliSessionDisplayKind.PROMPT
    assert prompt.label == "proj.v1"
    assert interactive.kind is CliSessionDisplayKind.INTERACTIVE
    assert interactive.label == "earnings"
    assert other_scope.kind is CliSessionDisplayKind.OTHER
    assert other_scope.label == "workflow.alpha"
    assert prompt_bad_prefix.kind is CliSessionDisplayKind.OTHER
    assert prompt_bad_prefix.label == "not-cli.prompt.alpha"
    assert prompt_empty_suffix.kind is CliSessionDisplayKind.OTHER
    assert prompt_empty_suffix.label == "cli.prompt."


def test_render_session_list_uses_public_summary_without_internal_fields() -> None:
    """Session list 输出只展示 public summary，不泄漏内部治理字段。

    :returns: ``None``。
    :raises AssertionError: 输出格式或内部字段隐藏行为不符合预期时抛出。
    """

    output = StringIO()
    render_session_list(
        ListSessionsResult(
            sessions=(
                _session_list_item(
                    session_id="session-anonymous",
                    slot=None,
                    queued_run_ids=(
                        "attempt-hidden",
                        "execution-hidden",
                        "payload-ref-hidden",
                        "digest-hidden",
                    ),
                ),
                _session_list_item(
                    session_id="session-prompt",
                    slot=SessionSlotRef(
                        scope="cli.prompt",
                        slot_key="cli.prompt.proj.v1",
                    ),
                ),
                _session_list_item(
                    session_id="session-other",
                    slot=SessionSlotRef(
                        scope="service.workflow",
                        slot_key="workflow.alpha",
                    ),
                ),
            )
        ),
        stdout=output,
    )

    rendered = output.getvalue()

    assert "SESSION_ID\tSTATUS\tKIND\tLABEL\tACTIVE_RUN\tQUEUED\tCREATED_AT\tCLOSED_AT" in rendered
    assert "session-anonymous\topen\tanonymous\t-\t-\t4\t2026-06-16T01:02:03Z\t-" in rendered
    assert "session-prompt\topen\tprompt\tproj.v1\t-\t0\t2026-06-16T01:02:03Z\t-" in rendered
    assert "session-other\topen\tother\tworkflow.alpha\t-\t0\t2026-06-16T01:02:03Z\t-" in rendered
    assert "attempt-hidden" not in rendered
    assert "execution-hidden" not in rendered
    assert "payload-ref-hidden" not in rendered
    assert "digest-hidden" not in rendered
    assert "HostStreamCursor" not in rendered


def test_render_session_list_empty_result() -> None:
    """空 Session 列表输出稳定可读空状态。

    :returns: ``None``。
    :raises AssertionError: 空列表输出不符合预期时抛出。
    """

    output = StringIO()

    render_session_list(ListSessionsResult(sessions=()), stdout=output)

    assert output.getvalue() == "No sessions.\n"


def test_render_session_purge_result_hides_digest() -> None:
    """purge 输出只展示 tombstone 前缀，不展示删除计数 digest。

    :returns: ``None``。
    :raises AssertionError: purge 输出格式或 digest 隐藏行为不符合预期时抛出。
    """

    output = StringIO()
    render_session_purge_result(
        PurgeSessionResult(
            session_id="session-purged",
            purged=True,
            purge_tombstone_ref="tombstone-ref-abcdef",
            deleted_counts_digest="sha256:digest-hidden",
        ),
        stdout=output,
    )

    rendered = output.getvalue()

    assert rendered == "Purged session session-purged (tombstone: tombstone-re...)\n"
    assert "sha256" not in rendered
    assert "digest-hidden" not in rendered
    assert "payload" not in rendered
    assert "attempt" not in rendered
    assert "execution" not in rendered


def _session_list_item(
    *,
    session_id: str,
    slot: SessionSlotRef | None,
    queued_run_ids: tuple[str, ...] = (),
) -> SessionListItem:
    """构造测试用 Session list item。

    :param session_id: Session id。
    :param slot: Host public slot ref。
    :param queued_run_ids: queued Run id 元组。
    :returns: Session list item。
    :raises ValueError: 构造出的 public DTO 字段非法时抛出。
    :raises TypeError: 构造出的 public DTO 类型非法时抛出。
    """

    return SessionListItem(
        session_id=session_id,
        status=SessionStatus.OPEN,
        slot=slot,
        active_run_id=None,
        queued_run_ids=queued_run_ids,
        timeline_cursor=HostStreamCursor(event_sequence=123),
        created_at=datetime(2026, 6, 16, 1, 2, 3, tzinfo=UTC),
        closed_at=None,
    )
