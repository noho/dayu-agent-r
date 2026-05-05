"""``ToolResultEnvelope`` 判别字段与字段集合测试。

断言 :class:`ToolResultSuccess` / :class:`ToolResultFailure` 的 ``ok``
判别字段固定，并且字段集合**不**包含 ``await_spec`` / ``await`` /
``awaiting`` 等指向 :class:`ToolAwaitSpec` 的字段。
"""

from __future__ import annotations

import dataclasses

from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultSuccess,
)


def test_success_envelope_has_ok_true_and_value() -> None:
    """:class:`ToolResultSuccess` 应固定 ``ok=True`` 并承载 ``value``。"""

    s = ToolResultSuccess(ok=True, value={"a": 1}, truncation=None, meta=None)
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


def test_envelope_field_sets_do_not_contain_await_spec() -> None:
    """``ToolResultSuccess`` / ``ToolResultFailure`` 字段不得包含
    ``await_spec`` 或任何指向 ``ToolAwaitSpec`` 的字段。"""

    success_fields = {f.name for f in dataclasses.fields(ToolResultSuccess)}
    failure_fields = {f.name for f in dataclasses.fields(ToolResultFailure)}
    forbidden = {"await_spec", "await", "awaiting"}
    assert success_fields == {"ok", "value", "truncation", "meta"}
    assert failure_fields == {"ok", "error", "message", "hint", "meta"}
    assert success_fields.isdisjoint(forbidden)
    assert failure_fields.isdisjoint(forbidden)
