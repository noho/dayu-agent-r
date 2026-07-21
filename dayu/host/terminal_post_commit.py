"""Host opener 内 terminal commit 后的本地协调契约。

本模块只定义不可持久化、不可跨进程传播的 notice 与同步端口。durable
terminal fact 仍由 EventLog 与 Run state 拥有；notice 只把同一事务返回的精确
terminal sequence 交给当前 opener 的 delivery/promotion coordinator。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TerminalPostCommitNotice:
    """一次已提交 Run terminal fact 的 opener-local 通知。

    :param session_id: terminal Run 所属 Session 标识，必须非空。
    :param terminal_event_sequence: 同一事务返回的 terminal Run EventLog 正整数序号。
    :param wake_queue_promotion: 本次提交是否首次释放 active slot。
    :raises TypeError: 字段类型不符合严格契约时抛出。
    :raises ValueError: Session 标识为空或序号不是正数时抛出。
    """

    session_id: str
    terminal_event_sequence: int
    wake_queue_promotion: bool

    def __post_init__(self) -> None:
        """校验 notice 的严格本地契约。

        :returns: ``None``。
        :raises TypeError: 字段类型不符合严格契约时抛出。
        :raises ValueError: Session 标识为空或序号不是正数时抛出。
        """

        if not isinstance(self.session_id, str):
            raise TypeError("session_id must be str")
        if self.session_id.strip() == "":
            raise ValueError("session_id must be non-empty")
        if isinstance(self.terminal_event_sequence, bool) or not isinstance(
            self.terminal_event_sequence,
            int,
        ):
            raise TypeError("terminal_event_sequence must be int")
        if self.terminal_event_sequence <= 0:
            raise ValueError("terminal_event_sequence must be positive")
        if not isinstance(self.wake_queue_promotion, bool):
            raise TypeError("wake_queue_promotion must be bool")


class TerminalPostCommitPort(Protocol):
    """消费当前 opener 本地 terminal post-commit notice 的同步端口。"""

    def notify_terminal_post_commit(
        self,
        notice: TerminalPostCommitNotice,
    ) -> None:
        """消费一次已经成功提交的精确 terminal notice。

        :param notice: 同一 transaction result 派生的精确 notice。
        :returns: ``None``。
        :raises Exception: 实现无法完成本地协调时原样传播。
        """

        ...
