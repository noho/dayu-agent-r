"""``ToolResultEnvelope`` 判别字段与字段集合测试。

断言 :class:`ToolResultSuccess` / :class:`ToolResultFailure` 的 ``ok``
判别字段固定，并且字段集合**不**包含 ``await_spec`` / ``await`` /
``awaiting`` 等指向 :class:`ToolAwaitSpec` 的字段。
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from dayu.contracts.tool_result import (
    ToolResultMeta,
    ToolResultFailure,
    ToolResultSuccess,
)


def test_success_envelope_has_ok_true_and_value() -> None:
    """:class:`ToolResultSuccess` 应固定 ``ok=True`` 并承载 ``value``。"""

    s = ToolResultSuccess(ok=True, value={"a": 1}, meta=None)
    assert s.ok is True
    assert isinstance(s, ToolResultSuccess)
    assert not isinstance(s, ToolResultFailure)


def test_failure_envelope_has_ok_false_and_error() -> None:
    """:class:`ToolResultFailure` 应固定 ``ok=False`` 并承载错误字段。"""

    f = ToolResultFailure(
        ok=False, error="E_X", message="x", hint=None, meta=None
    )
    assert f.ok is False
    assert isinstance(f, ToolResultFailure)
    assert not isinstance(f, ToolResultSuccess)


def test_failure_envelope_rejects_empty_error_or_message() -> None:
    """失败结果必须携带非空错误码与说明。"""

    with pytest.raises(ValueError, match="error"):
        ToolResultFailure(
            ok=False, error="", message="x", hint=None, meta=None
        )
    with pytest.raises(ValueError, match="message"):
        ToolResultFailure(
            ok=False, error="E_X", message="  ", hint=None, meta=None
        )
    with pytest.raises(ValueError, match="hint"):
        ToolResultFailure(
            ok=False, error="E_X", message="x", hint=" \n", meta=None
        )


def test_tool_result_meta_rejects_empty_tool_name_and_reversed_time() -> None:
    """工具结果元信息必须拒绝空工具名与倒序时间。"""

    started_at = datetime(2026, 5, 19, 1, 2, 3, tzinfo=UTC)
    with pytest.raises(ValueError, match="tool_name"):
        ToolResultMeta(
            tool_name=" ",
            started_at=started_at,
            finished_at=started_at,
        )
    with pytest.raises(ValueError, match="finished_at"):
        ToolResultMeta(
            tool_name="lookup",
            started_at=started_at,
            finished_at=started_at - timedelta(seconds=1),
        )


def test_tool_result_meta_rejects_mixed_naive_and_aware_times() -> None:
    """工具结果元信息不得混合 naive 与 aware datetime。"""

    aware = datetime(2026, 5, 19, 1, 2, 3, tzinfo=UTC)
    naive = datetime(2026, 5, 19, 1, 2, 3)

    with pytest.raises(ValueError, match="timezone-aware"):
        ToolResultMeta(
            tool_name="lookup",
            started_at=aware,
            finished_at=naive,
        )


def test_envelope_field_sets_do_not_contain_await_spec() -> None:
    """``ToolResultSuccess`` / ``ToolResultFailure`` 字段不得包含
    ``await_spec`` 或任何指向 ``ToolAwaitSpec`` 的字段。"""

    success_fields = {f.name for f in dataclasses.fields(ToolResultSuccess)}
    failure_fields = {f.name for f in dataclasses.fields(ToolResultFailure)}
    forbidden = {"await_spec", "await", "awaiting"}
    assert success_fields == {"ok", "value", "meta"}
    assert failure_fields == {"ok", "error", "message", "hint", "meta"}
    assert success_fields.isdisjoint(forbidden)
    assert failure_fields.isdisjoint(forbidden)
