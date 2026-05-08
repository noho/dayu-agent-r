"""人工验证 Host P6 durable EventLog 路径的 smoke 脚本。

本脚本不依赖 Engine Worker，只直接 append 一组手工构造的 RunEvent，
然后驱动 :class:`ProjectionCoordinator` 把事件 drain 到 memory / timeline /
audit 三个 read model，最后打印 checkpoint 与 read model 内容。用于人工
观察：

- DurableRunEventStore 写入路径 + global position 顺序。
- ProjectionCoordinator drain + checkpoint 推进。
- memory required projection 写入用户输入 + assistant final。
- timeline / audit observer 累积情况。

运行示例：

    source .venv/bin/activate
    python utils/smoke_host_p6_durable_eventlog.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT_PARENT_INDEX: int = 1


def _ensure_repo_root_on_path() -> None:
    """确保按文件路径运行脚本时也能导入仓库顶层包。

    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if __package__ not in (None, ""):
        return
    repo_root = Path(__file__).resolve().parents[_REPO_ROOT_PARENT_INDEX]
    repo_root_text = str(repo_root)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)


_ensure_repo_root_on_path()

from dayu.engine import FinalAnswerData, FinishReason  # noqa: E402
from dayu.host._durable_harness import build_durable_harness  # noqa: E402
from dayu.host.contracts import (  # noqa: E402
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    UserInputAcceptedData,
    UserInputScope,
)


def _utc() -> datetime:
    """返回当前 UTC 时间。

    :returns: 时区感知的 UTC datetime。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


async def _run_smoke() -> None:
    """驱动一遍 append + drain，并打印 read model 状态。

    :returns: 无返回值。
    :raises Exception: 子组件异常时透传。
    """

    bundle = build_durable_harness(database_path=":memory:")
    try:
        run_id = "smoke_run_1"
        session_id = "smoke_session"
        # 1. 用户输入。
        await bundle.event_store.append(
            RunEventDraft(
                run_id=run_id,
                session_id=session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.USER_INPUT_ACCEPTED,
                occurred_at=_utc(),
                data=UserInputAcceptedData(
                    turn_id=run_id,
                    content="问题1",
                    scope=UserInputScope.SESSION,
                ),
                source_engine_event_id=None,
            )
        )
        # 2. assistant final。
        await bundle.event_store.append(
            RunEventDraft(
                run_id=run_id,
                session_id=session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.ENGINE,
                type=RunEventType.FINAL_ANSWER,
                occurred_at=_utc(),
                data=FinalAnswerData(
                    content="答案1",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                source_engine_event_id="engine_smoke_final",
            )
        )

        snapshots = await bundle.coordinator.drain()
        for cp in snapshots:
            last = (
                cp.last_success_position.value
                if cp.last_success_position is not None
                else None
            )
            print(
                f"[checkpoint] observer={cp.observer_id} "
                f"status={cp.status.value} "
                f"last_success_position={last} "
                f"lag={cp.lag_events}"
            )

        memory_snapshot = await bundle.memory_store.get_snapshot(session_id)
        print("[memory] recent_raw_turns:")
        for turn in memory_snapshot.recent_raw_turns:
            print(
                f"  user_text={turn.user_text!r} "
                f"assistant_final={turn.assistant_final!r} "
                f"terminal_summary={turn.terminal_summary!r}"
            )

        timeline = bundle.timeline_observer.get_timeline(run_id)
        print(f"[timeline] {len(timeline)} canonical events:")
        for evt in timeline:
            print(f"  seq={evt.cursor.sequence} type={evt.type.value}")

        audit = bundle.audit_observer.list_records()
        print(f"[audit] {len(audit)} records:")
        for record in audit:
            print(
                f"  position={record.position.value} "
                f"run={record.run_id} type={record.event_type.value}"
            )
    finally:
        bundle.close()


def main() -> None:
    """脚本入口。

    :returns: 无返回值。
    :raises Exception: 子组件异常时透传。
    """

    asyncio.run(_run_smoke())


if __name__ == "__main__":
    main()
