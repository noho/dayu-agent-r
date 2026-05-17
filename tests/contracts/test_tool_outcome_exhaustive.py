"""``ToolExecutionOutcome`` 穷尽匹配测试。

提供一个最小 ``match`` helper 覆盖四分支并以 :func:`typing.assert_never`
收口；新增子类型时 pyright 会在编译期报错。本文件同时确保 helper 在
运行期对每个分支都返回正确判别。
"""

from __future__ import annotations

from datetime import datetime
from typing import assert_never, cast

import pytest

from dayu.contracts.tool_await import (
    ToolAwaitKind,
    ToolAwaitSnapshot,
    ToolAwaitSpec,
)
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_APPROVAL_DENIED,
    ToolCancelledReason,
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolAwaitingOutcome,
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultSuccess,
)


def _classify(outcome: ToolExecutionOutcome) -> str:
    """对 :data:`ToolExecutionOutcome` 四分支做穷尽匹配。

    :param outcome: 工具执行 outcome 联合。
    :returns: 分支判别字符串。
    """

    match outcome:
        case ToolCompletedOutcome():
            return "completed"
        case ToolFailedOutcome():
            return "failed"
        case ToolAwaitingOutcome():
            return "awaiting"
        case ToolCancelledOutcome():
            return "cancelled"
        case _:  # pragma: no cover - guarded by pyright
            assert_never(outcome)


def _make_completed() -> ToolCompletedOutcome:
    """构造一个最小的 completed outcome。

    :returns: 最小可构造的 :class:`ToolCompletedOutcome`。
    """

    return ToolCompletedOutcome(
        result=ToolResultSuccess(
            ok=True,
            value=None,
            meta=None,
        )
    )


def _make_failed() -> ToolFailedOutcome:
    """构造一个最小的 failed outcome。

    :returns: 最小可构造的 :class:`ToolFailedOutcome`。
    """

    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error="E_X",
            message="x",
            hint=None,
            meta=None,
        )
    )


def _make_awaiting() -> ToolAwaitingOutcome:
    """构造一个最小的 awaiting outcome。

    :returns: 最小可构造的 :class:`ToolAwaitingOutcome`。
    """

    return ToolAwaitingOutcome(
        await_spec=ToolAwaitSpec(
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
            deadline=None,
            resume_token="rt",
        ),
        snapshot=ToolAwaitSnapshot(
            snapshot_id="s",
            captured_at=datetime(2026, 1, 1),
        ),
    )


def _make_cancelled() -> ToolCancelledOutcome:
    """构造一个最小的 cancelled outcome。

    :returns: 最小可构造的 :class:`ToolCancelledOutcome`。
    """

    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_APPROVAL_DENIED,
        message="approval denied",
        hint=None,
        meta=None,
    )


def test_classify_completed() -> None:
    """completed 分支应返回 ``"completed"``。"""

    assert _classify(_make_completed()) == "completed"


def test_classify_failed() -> None:
    """failed 分支应返回 ``"failed"``。"""

    assert _classify(_make_failed()) == "failed"


def test_classify_awaiting() -> None:
    """awaiting 分支应返回 ``"awaiting"``。"""

    assert _classify(_make_awaiting()) == "awaiting"


def test_classify_cancelled() -> None:
    """cancelled 分支应返回 ``"cancelled"``。"""

    assert _classify(_make_cancelled()) == "cancelled"


def test_cancelled_rejects_invalid_reason() -> None:
    """非白名单 ``reason`` 必须在构造期抛出 :class:`ValueError`。

    校验 :class:`ToolCancelledOutcome.__post_init__` 防御受限 reason 集合，
    避免 Host 误传任意 reason 字面量绕过取消语义。
    """

    with pytest.raises(ValueError):
        ToolCancelledOutcome(
            reason=cast(ToolCancelledReason, "not_a_real_reason"),
            message="x",
            hint=None,
            meta=None,
        )


def test_cancelled_rejects_empty_message() -> None:
    """``message`` 为空必须在构造期抛出 :class:`ValueError`。

    取消语义必须携带可解释的人类可读 message；空 message 视为无效输入。
    """

    with pytest.raises(ValueError):
        ToolCancelledOutcome(
            reason=TOOL_CANCELLED_REASON_APPROVAL_DENIED,
            message="",
            hint=None,
            meta=None,
        )


def test_cancelled_rejects_whitespace_message() -> None:
    """``message`` 为纯空白必须在构造期抛出 :class:`ValueError`。

    取消语义需要可解释 message；纯空白与空字符串等价无效。
    """

    for invalid_message in ("   ", "\t", "\n", "  \t  \n"):
        with pytest.raises(ValueError):
            ToolCancelledOutcome(
                reason=TOOL_CANCELLED_REASON_APPROVAL_DENIED,
                message=invalid_message,
                hint=None,
                meta=None,
            )


def test_cancelled_rejects_empty_or_whitespace_hint() -> None:
    """``hint`` 存在时必须是非空文本。"""

    for invalid_hint in ("", "   ", "\t", "\n", "  \t  \n"):
        with pytest.raises(ValueError):
            ToolCancelledOutcome(
                reason=TOOL_CANCELLED_REASON_APPROVAL_DENIED,
                message="approval denied",
                hint=invalid_hint,
                meta=None,
            )


def test_batch_outcome_rejects_blank_tool_call_id() -> None:
    """批式 outcome record 的 ``tool_call_id`` 不能为空或纯空白。"""

    for invalid_id in ("", "   ", "\t", "\n", "  \t  \n"):
        with pytest.raises(ValueError, match="tool_call_id must be non-empty"):
            BatchToolExecutionOutcome(
                records=(
                    BatchToolExecutionRecord(
                        tool_call_id=invalid_id,
                        outcome=_make_completed(),
                    ),
                )
            )


def test_batch_outcome_rejects_duplicate_tool_call_id() -> None:
    """批式 outcome record 的 ``tool_call_id`` 不得重复。"""

    with pytest.raises(ValueError, match="tool_call_id must be unique"):
        BatchToolExecutionOutcome(
            records=(
                BatchToolExecutionRecord(
                    tool_call_id="call-1",
                    outcome=_make_completed(),
                ),
                BatchToolExecutionRecord(
                    tool_call_id="call-1",
                    outcome=_make_failed(),
                ),
            )
        )
