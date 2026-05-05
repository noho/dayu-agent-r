"""Runner 内部 cancellation 信号 :class:`_RunnerInterrupted` 私有性守卫。

按 ``docs/engine/phase1-plan.md`` §7：``_RunnerInterrupted`` 仅在
:mod:`dayu.engine.runners.openai` 内部传递，必须满足：

- 不出现在 :data:`dayu.engine.runners.openai.cancellation_helpers.__all__`。
- 不出现在 :data:`dayu.engine.__all__` 或 :data:`dayu.engine.contracts.__all__`。
- 名称以单下划线开头（按 PEP 8 私有约定）。
- 不是 :class:`asyncio.CancelledError` 的子类——避免被外部
  ``except asyncio.CancelledError`` 误吞。
"""

from __future__ import annotations

import asyncio

import dayu.engine as engine
import dayu.engine.contracts as engine_contracts
from dayu.engine.runners.openai import cancellation_helpers


def test_runner_interrupted_not_in_module_all() -> None:
    """``_RunnerInterrupted`` 不得出现在 ``cancellation_helpers.__all__``。"""

    public_names = getattr(cancellation_helpers, "__all__", [])
    assert "_RunnerInterrupted" not in public_names


def test_runner_interrupted_not_in_engine_all() -> None:
    """``_RunnerInterrupted`` 不得在 :data:`dayu.engine.__all__`。"""

    assert "_RunnerInterrupted" not in engine.__all__


def test_runner_interrupted_not_in_engine_contracts_all() -> None:
    """``_RunnerInterrupted`` 不得在 :data:`dayu.engine.contracts.__all__`。"""

    public_names = getattr(engine_contracts, "__all__", [])
    assert "_RunnerInterrupted" not in public_names


def test_runner_interrupted_naming_is_private() -> None:
    """名字必须以单下划线开头，PEP 8 私有约定。"""

    name = cancellation_helpers._RunnerInterrupted.__name__
    assert name.startswith("_"), name


def test_runner_interrupted_not_subclass_of_cancelled_error() -> None:
    """``_RunnerInterrupted`` 不得继承 :class:`asyncio.CancelledError`。

    避免外层 ``except asyncio.CancelledError`` 误吞 Runner 协作式取消信号，
    或导致协程被错误地置为 cancelled 终态。
    """

    assert not issubclass(
        cancellation_helpers._RunnerInterrupted, asyncio.CancelledError
    )


def test_runner_interrupted_is_exception_subclass() -> None:
    """``_RunnerInterrupted`` 必须是 :class:`Exception` 子类。"""

    assert issubclass(
        cancellation_helpers._RunnerInterrupted, Exception
    )
