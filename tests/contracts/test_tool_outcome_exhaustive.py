"""``ToolExecutionOutcome`` 穷尽匹配测试。

提供一个最小 ``match`` helper 覆盖三分支并以 :func:`typing.assert_never`
收口；新增子类型时 pyright 会在编译期报错。本文件同时确保 helper 在
运行期对每个分支都返回正确判别。
"""

from __future__ import annotations

from datetime import datetime
from typing import assert_never

from dayu.contracts.tool_await import (
    ToolAwaitKind,
    ToolAwaitSnapshot,
    ToolAwaitSpec,
)
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultSuccess,
)


def _classify(outcome: ToolExecutionOutcome) -> str:
    """对 :data:`ToolExecutionOutcome` 三分支做穷尽匹配。

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
            truncation=None,
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


def test_classify_completed() -> None:
    """completed 分支应返回 ``"completed"``。"""

    assert _classify(_make_completed()) == "completed"


def test_classify_failed() -> None:
    """failed 分支应返回 ``"failed"``。"""

    assert _classify(_make_failed()) == "failed"


def test_classify_awaiting() -> None:
    """awaiting 分支应返回 ``"awaiting"``。"""

    assert _classify(_make_awaiting()) == "awaiting"
