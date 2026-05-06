"""Host 内部最小 RunEventStore。

本模块实现 P1.5 的内存态 append-only 事件事实层。它只保证单进程内
RunEvent append、exclusive replay 与 replay-then-follow 订阅语义，不宣称
多进程恢复或持久化正确性。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

from dayu.host.contracts import (
    TERMINAL_RUN_EVENT_TYPES,
    RunEvent,
    RunEventCursor,
    RunEventDraft,
    RunEventSource,
)

_FIRST_EVENT_SEQUENCE: int = 0
_ERROR_ENGINE_EVENT_ID_REQUIRED: str = (
    "engine sourced RunEventDraft requires source_engine_event_id"
)
_ERROR_HOST_EVENT_ID_FORBIDDEN: str = (
    "host sourced RunEventDraft must not set source_engine_event_id"
)
_ERROR_APPEND_AFTER_TERMINAL: str = (
    "cannot append RunEventDraft after terminal event"
)
_LOGGER: logging.Logger = logging.getLogger(__name__)


class RunEventStore(Protocol):
    """Host 内部 RunEventStore 协议。"""

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """追加 RunEvent 草稿并返回带 cursor 的已落库事件。

        :param draft: 待追加的 RunEvent 草稿。
        :returns: 已分配 Host cursor 的 RunEvent。
        :raises Exception: 具体实现追加失败时抛出。
        """
        ...

    async def list_events(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> tuple[RunEvent, ...]:
        """按 exclusive cursor 补读某个 run 的事件。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时返回全部事件。
        :returns: cursor 大于 ``after`` 的 RunEvent 元组。
        :raises Exception: 具体实现读取失败时抛出。
        """
        ...

    def subscribe(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> AsyncIterator[RunEvent]:
        """订阅某个 run 的 replay-then-follow 事件流。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时从头订阅。
        :returns: RunEvent 异步流。
        :raises Exception: 具体实现订阅失败时抛出。
        """
        ...


@dataclass(slots=True)
class InMemoryRunEventStore:
    """单进程内存态 RunEventStore 实现。"""

    _condition: asyncio.Condition = field(
        default_factory=asyncio.Condition,
        init=False,
    )
    _events_by_run: dict[str, list[RunEvent]] = field(
        default_factory=dict,
        init=False,
    )
    _next_sequence_by_run: dict[str, int] = field(
        default_factory=dict,
        init=False,
    )
    _terminal_cursor_by_run: dict[str, RunEventCursor] = field(
        default_factory=dict,
        init=False,
    )

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """追加 RunEvent 草稿并返回带 cursor 的已落库事件。

        append 在同一 condition 锁内完成 cursor 分配、事件保存与订阅通知，
        因此订阅者只能在事件已经进入 store 后观察到通知。

        :param draft: 待追加的 RunEvent 草稿。
        :returns: 已分配 Host cursor 的 RunEvent。
        :raises ValueError: draft 来源与 source_engine_event_id 不一致，或 run
            已经进入终态后仍尝试追加事件时抛出。
        """

        async with self._condition:
            _validate_draft_provenance(draft)
            _validate_run_is_not_terminal(
                run_id=draft.run_id,
                terminal_cursor_by_run=self._terminal_cursor_by_run,
            )
            sequence = self._next_sequence_by_run.get(
                draft.run_id, _FIRST_EVENT_SEQUENCE
            )
            self._next_sequence_by_run[draft.run_id] = sequence + 1
            event = RunEvent(
                run_id=draft.run_id,
                session_id=draft.session_id,
                cursor=RunEventCursor(sequence=sequence),
                kind=draft.kind,
                source=draft.source,
                type=draft.type,
                occurred_at=draft.occurred_at,
                data=draft.data,
                source_engine_event_id=draft.source_engine_event_id,
            )
            events = self._events_by_run.setdefault(draft.run_id, [])
            events.append(event)
            if (
                event.type in TERMINAL_RUN_EVENT_TYPES
                and draft.run_id not in self._terminal_cursor_by_run
            ):
                self._terminal_cursor_by_run[draft.run_id] = event.cursor
            self._condition.notify_all()
            _LOGGER.debug(
                "host.event_store.appended run_id=%s cursor=%s type=%s "
                "kind=%s source=%s terminal=%s",
                event.run_id,
                event.cursor.sequence,
                event.type.value,
                event.kind.value,
                event.source.value,
                event.type in TERMINAL_RUN_EVENT_TYPES,
            )
            return event

    async def list_events(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> tuple[RunEvent, ...]:
        """按 exclusive cursor 补读某个 run 的事件。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时返回全部事件。
        :returns: cursor 大于 ``after`` 的 RunEvent 元组。
        :raises Exception: 不主动抛出异常。
        """

        async with self._condition:
            events = self._events_after_locked(run_id=run_id, after=after)
            _LOGGER.debug(
                "host.event_store.list run_id=%s after=%s count=%s",
                run_id,
                _cursor_sequence(after),
                len(events),
            )
            return events

    def subscribe(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> AsyncIterator[RunEvent]:
        """订阅某个 run 的 replay-then-follow 事件流。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时从头订阅。
        :returns: RunEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        return self._subscribe(run_id=run_id, after=after)

    async def _subscribe(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> AsyncGenerator[RunEvent, None]:
        """在同一 condition 保护下补读并等待新事件。

        循环先检查 ``last_seen`` 之后是否已有事件，只有确认没有新事件且
        run 未终态时才等待 condition，避免 replay 与 follow 之间的 lost
        wakeup 窗口。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时从头订阅。
        :returns: RunEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        last_seen = after
        _LOGGER.debug(
            "host.event_store.subscribe_start run_id=%s after=%s",
            run_id,
            _cursor_sequence(after),
        )
        while True:
            async with self._condition:
                while True:
                    events = self._events_after_locked(
                        run_id=run_id,
                        after=last_seen,
                    )
                    if events:
                        _LOGGER.debug(
                            "host.event_store.subscribe_batch run_id=%s "
                            "after=%s count=%s first_cursor=%s "
                            "last_cursor=%s",
                            run_id,
                            _cursor_sequence(last_seen),
                            len(events),
                            events[0].cursor.sequence,
                            events[-1].cursor.sequence,
                        )
                        break
                    if self._terminal_reached_locked(
                        run_id=run_id,
                        after=last_seen,
                    ):
                        _LOGGER.debug(
                            "host.event_store.subscribe_complete run_id=%s "
                            "after=%s reason=terminal_seen",
                            run_id,
                            _cursor_sequence(last_seen),
                        )
                        return
                    _LOGGER.debug(
                        "host.event_store.subscribe_wait run_id=%s after=%s",
                        run_id,
                        _cursor_sequence(last_seen),
                    )
                    await self._condition.wait()
                last_seen = events[-1].cursor

            for event in events:
                yield event
                if event.type in TERMINAL_RUN_EVENT_TYPES:
                    _LOGGER.debug(
                        "host.event_store.subscribe_complete run_id=%s "
                        "after=%s reason=terminal_yielded",
                        run_id,
                        event.cursor.sequence,
                    )
                    return

    def _events_after_locked(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> tuple[RunEvent, ...]:
        """返回指定 cursor 之后的事件。

        调用方必须已经持有 ``_condition`` 锁。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时返回全部事件。
        :returns: cursor 大于 ``after`` 的 RunEvent 元组。
        :raises Exception: 不主动抛出异常。
        """

        events = self._events_by_run.get(run_id, [])
        if after is None:
            return tuple(events)
        return tuple(
            event
            for event in events
            if event.cursor.sequence > after.sequence
        )

    def _terminal_reached_locked(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> bool:
        """判断订阅起点是否已经越过 run 终态。

        调用方必须已经持有 ``_condition`` 锁。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时表示尚未看过事件。
        :returns: 已经看过终态或起点在终态之后时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        terminal_cursor = self._terminal_cursor_by_run.get(run_id)
        if terminal_cursor is None or after is None:
            return False
        return after.sequence >= terminal_cursor.sequence


def _validate_draft_provenance(draft: RunEventDraft) -> None:
    """校验 RunEventDraft 的来源字段。

    :param draft: 待追加的 RunEvent 草稿。
    :returns: 无返回值。
    :raises ValueError: 来源与 ``source_engine_event_id`` 不一致时抛出。
    """

    if (
        draft.source is RunEventSource.ENGINE
        and draft.source_engine_event_id is None
    ):
        raise ValueError(_ERROR_ENGINE_EVENT_ID_REQUIRED)
    if (
        draft.source is RunEventSource.HOST
        and draft.source_engine_event_id is not None
    ):
        raise ValueError(_ERROR_HOST_EVENT_ID_FORBIDDEN)


def _validate_run_is_not_terminal(
    *,
    run_id: str,
    terminal_cursor_by_run: dict[str, RunEventCursor],
) -> None:
    """校验同一 run 尚未写入终态事件。

    :param run_id: Run id。
    :param terminal_cursor_by_run: 已记录的 run 终态 cursor 映射。
    :returns: 无返回值。
    :raises ValueError: run 已经写入终态事件时抛出。
    """

    if run_id in terminal_cursor_by_run:
        raise ValueError(_ERROR_APPEND_AFTER_TERMINAL)


def _cursor_sequence(cursor: RunEventCursor | None) -> int | None:
    """返回 cursor 序号，便于日志输出。

    :param cursor: 可选 RunEventCursor。
    :returns: cursor 为 ``None`` 时返回 ``None``，否则返回序号。
    :raises Exception: 不主动抛出异常。
    """

    if cursor is None:
        return None
    return cursor.sequence


__all__ = ["InMemoryRunEventStore", "RunEventStore"]
