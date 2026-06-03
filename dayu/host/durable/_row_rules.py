"""Host durable row 终态形状规则。

本模块只承载 durable row 的终态状态常量、终态引用 SQL 片段和终态形状校验。
它不负责 scalar 类型校验、row decode、schema bootstrap、transaction 或 public
API validation。
"""

from __future__ import annotations

from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.durable.errors import HostDurableError

TERMINAL_RUN_STATUS_VALUES: tuple[str, ...] = (
    RunStatus.SUCCEEDED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
    RunStatus.LOST.value,
)
"""Run 终态 status 文本集合。"""

TERMINAL_ATTEMPT_STATUS_VALUES: tuple[str, ...] = (
    AttemptStatus.SUCCEEDED.value,
    AttemptStatus.FAILED.value,
    AttemptStatus.CANCELLED.value,
    AttemptStatus.SUSPENDED.value,
    AttemptStatus.STEERED.value,
    AttemptStatus.LOST.value,
)
"""Attempt 终态 status 文本集合。"""

WAIT_RECORD_WAITING_STATUS_VALUE = "waiting"
"""WaitRecord waiting status 文本。"""

WAIT_RECORD_RESOLVED_STATUS_VALUE = "resolved"
"""WaitRecord resolved status 文本。"""

WAIT_RECORD_FAILED_STATUS_VALUE = "failed"
"""WaitRecord failed status 文本。"""

WAIT_RECORD_CANCELLED_STATUS_VALUE = "cancelled"
"""WaitRecord cancelled status 文本。"""

WAIT_RECORD_LOST_STATUS_VALUE = "lost"
"""WaitRecord lost status 文本。"""

WAIT_RECORD_TERMINAL_STATUS_VALUES: tuple[str, ...] = (
    WAIT_RECORD_RESOLVED_STATUS_VALUE,
    WAIT_RECORD_FAILED_STATUS_VALUE,
    WAIT_RECORD_CANCELLED_STATUS_VALUE,
    WAIT_RECORD_LOST_STATUS_VALUE,
)
"""WaitRecord 终态 status 文本集合。"""

_TERMINAL_EVENT_ID_COLUMN = "terminal_event_id"
"""终态 EventLog id 引用列名。"""

_TERMINAL_EVENT_SEQUENCE_COLUMN = "terminal_event_sequence"
"""终态 EventLog sequence 引用列名。"""

_TERMINAL_AT_COLUMN = "terminal_at"
"""终态时间列名。"""


def sql_string_list(values: tuple[str, ...]) -> str:
    """生成 SQLite 单引号字符串列表。

    :param values: 待写入 SQL ``IN`` / ``NOT IN`` 的文本值。
    :returns: 逗号分隔的 SQLite 字符串字面量列表。
    :raises HostDurableError: 值集合为空或任一值为空时抛出。
    """

    if not values:
        raise HostDurableError("SQL string list values must not be empty")
    escaped_values: list[str] = []
    for value in values:
        if value == "":
            raise HostDurableError("SQL string list value must not be empty")
        escaped_values.append("'" + value.replace("'", "''") + "'")
    return ", ".join(escaped_values)


def terminal_event_refs_required_check_sql(
    *,
    status_column: str,
    terminal_status_values: tuple[str, ...],
) -> str:
    """生成终态 row 必须携带 terminal refs 的 CHECK 表达式。

    :param status_column: status 列名。
    :param terminal_status_values: 终态 status 文本集合。
    :returns: SQLite CHECK 表达式片段，不包含外层 ``CHECK``。
    :raises HostDurableError: status 列名为空或终态集合非法时抛出。
    """

    _validate_sql_identifier(status_column, field_name="status_column")
    return (
        f"{status_column} NOT IN ({sql_string_list(terminal_status_values)})\n"
        "    OR\n"
        f"    ({_TERMINAL_EVENT_ID_COLUMN} IS NOT NULL\n"
        f"      AND {_TERMINAL_EVENT_SEQUENCE_COLUMN} IS NOT NULL\n"
        f"      AND {_TERMINAL_AT_COLUMN} IS NOT NULL)"
    )


def terminal_event_refs_unset_check_sql(
    *,
    status_column: str,
    terminal_status_values: tuple[str, ...],
) -> str:
    """生成非终态 row 必须清空 terminal refs 的 CHECK 表达式。

    :param status_column: status 列名。
    :param terminal_status_values: 终态 status 文本集合。
    :returns: SQLite CHECK 表达式片段，不包含外层 ``CHECK``。
    :raises HostDurableError: status 列名为空或终态集合非法时抛出。
    """

    _validate_sql_identifier(status_column, field_name="status_column")
    return (
        f"{status_column} IN ({sql_string_list(terminal_status_values)})\n"
        "    OR\n"
        f"    ({_TERMINAL_EVENT_ID_COLUMN} IS NULL\n"
        f"      AND {_TERMINAL_EVENT_SEQUENCE_COLUMN} IS NULL\n"
        f"      AND {_TERMINAL_AT_COLUMN} IS NULL)"
    )


def terminal_event_refs_unset_where_sql(*, indent: str) -> str:
    """生成 CAS ``WHERE`` 中 terminal refs 全空谓词。

    :param indent: 每个 ``AND`` 行前的缩进文本。
    :returns: 带前导 ``AND`` 的多行 SQL 片段。
    :raises HostDurableError: 本函数不主动抛出。
    """

    return (
        f"{indent}AND {_TERMINAL_EVENT_ID_COLUMN} IS NULL\n"
        f"{indent}AND {_TERMINAL_EVENT_SEQUENCE_COLUMN} IS NULL\n"
        f"{indent}AND {_TERMINAL_AT_COLUMN} IS NULL"
    )


def wait_terminal_at_check_sql(*, status_column: str) -> str:
    """生成 WaitRecord status 与 terminal_at 形状 CHECK 表达式。

    :param status_column: WaitRecord status 列名。
    :returns: SQLite CHECK 表达式片段，不包含外层 ``CHECK``。
    :raises HostDurableError: status 列名为空时抛出。
    """

    _validate_sql_identifier(status_column, field_name="status_column")
    return (
        f"({status_column} = '{WAIT_RECORD_WAITING_STATUS_VALUE}' AND {_TERMINAL_AT_COLUMN} IS NULL)\n"
        "    OR\n"
        f"    ({status_column} IN ({sql_string_list(WAIT_RECORD_TERMINAL_STATUS_VALUES)})\n"
        f"      AND {_TERMINAL_AT_COLUMN} IS NOT NULL)"
    )


def wait_terminal_at_unset_where_sql(*, indent: str) -> str:
    """生成 WaitRecord terminal CAS 的 waiting terminal_at 空值谓词。

    :param indent: ``AND`` 行前的缩进文本。
    :returns: 带前导 ``AND`` 的 SQL 片段。
    :raises HostDurableError: 本函数不主动抛出。
    """

    return f"{indent}AND {_TERMINAL_AT_COLUMN} IS NULL"


def validate_terminal_event_refs_shape(
    *,
    terminal_event_id: str | None,
    terminal_event_sequence: int | None,
    terminal_at: str | None,
    is_terminal: bool,
    owner_label: str,
) -> None:
    """校验 Run / Attempt terminal refs 与状态终态性一致。

    :param terminal_event_id: terminal EventLog id，非终态应为 ``None``。
    :param terminal_event_sequence: terminal EventLog sequence，非终态应为 ``None``。
    :param terminal_at: terminal timestamp，非终态应为 ``None``。
    :param is_terminal: 当前 row 状态是否为终态。
    :param owner_label: 错误消息中的 row owner 名称，如 ``Run``。
    :returns: ``None``。
    :raises HostDurableError: 终态缺少任一 terminal ref，或非终态携带任一
        terminal ref 时抛出。
    """

    if is_terminal:
        if (
            terminal_event_id is None
            or terminal_event_sequence is None
            or terminal_at is None
        ):
            raise HostDurableError(f"terminal {owner_label} requires terminal refs")
        return
    if (
        terminal_event_id is not None
        or terminal_event_sequence is not None
        or terminal_at is not None
    ):
        raise HostDurableError(f"non-terminal {owner_label} terminal refs must be unset")


def validate_wait_terminal_at_shape(
    *,
    status_value: str,
    terminal_at: str | None,
) -> None:
    """校验 WaitRecord status 与 terminal_at 形状一致。

    :param status_value: WaitRecord status 文本。
    :param terminal_at: terminal timestamp；waiting 应为空，终态应非空。
    :returns: ``None``。
    :raises HostDurableError: waiting 携带 terminal_at，或终态缺少
        terminal_at 时抛出。
    """

    if status_value == WAIT_RECORD_WAITING_STATUS_VALUE and terminal_at is not None:
        raise HostDurableError("waiting wait record terminal_at must be unset")
    if status_value in WAIT_RECORD_TERMINAL_STATUS_VALUES and terminal_at is None:
        raise HostDurableError("terminal wait record requires terminal_at")


def _validate_sql_identifier(value: str, *, field_name: str) -> None:
    """校验内部 SQL identifier 非空。

    :param value: SQL identifier。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises HostDurableError: identifier 为空时抛出。
    """

    if value == "":
        raise HostDurableError(f"{field_name} must not be empty")
