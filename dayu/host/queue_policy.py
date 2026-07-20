"""Host Run queue policy 契约真源。

本模块只拥有 Host 接受新 Run 时的排队策略闭集、解析、序列化与 DDL
取值投影。Admission、public request validation 与 durable row codec 都应
复用这里的 owner helper，不自行维护 queue policy 文本集合。
"""

from __future__ import annotations

from enum import StrEnum


class RunQueuePolicy(StrEnum):
    """Run admission queue policy 闭集。"""

    QUEUE = "queue"
    REJECT = "reject"
    ATTACH_ACTIVE = "attach_active"


def parse_run_queue_policy(value: str) -> RunQueuePolicy:
    """解析 Run queue policy 文本。

    :param value: public 或 SQLite 边界传入的 queue policy 文本。
    :returns: 对应的 ``RunQueuePolicy`` 成员。
    :raises ValueError: ``value`` 为空或不属于合法 queue policy 闭集时抛出。
    """

    if value.strip() == "":
        raise ValueError("queue_policy must be queue, reject or attach_active")
    try:
        return RunQueuePolicy(value)
    except ValueError as exc:
        raise ValueError("queue_policy must be queue, reject or attach_active") from exc


def serialize_run_queue_policy(policy: RunQueuePolicy) -> str:
    """序列化 Run queue policy。

    :param policy: 已解析的 Run queue policy。
    :returns: public 或 SQLite 边界使用的稳定文本。
    :raises ValueError: ``policy`` 不是 ``RunQueuePolicy`` 成员时抛出。
    """

    if not isinstance(policy, RunQueuePolicy):
        raise ValueError("queue_policy must be RunQueuePolicy")
    return policy.value


def run_queue_policy_values() -> tuple[str, ...]:
    """返回 Run queue policy 的稳定合法文本集合。

    :returns: 按 enum 定义顺序排列的 queue policy 文本元组。
    :raises RuntimeError: 当前实现不抛出。
    """

    return tuple(policy.value for policy in RunQueuePolicy)
