"""Host wait 时间边界判定真源。

本模块只解释 wait record 中 Host 持久化的 ``deadline_at`` / ``expires_at``
边界。callback、poller 和 provider adapter 只能消费这里的 typed 判定结果，
不得自行解析 Host deadline 或把损坏边界转换成业务终态。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from dayu.host.durable.codec import parse_utc_timestamp
from dayu.host.durable.state import WaitRecordRow

_WAIT_BOUNDARY_FIELD_DEADLINE = "deadline_at"
_WAIT_BOUNDARY_FIELD_EXPIRES = "expires_at"


class WaitBoundaryDecisionKind(StrEnum):
    """Host wait 时间边界判定类别。"""

    ACTIVE = "active"
    EXPIRED = "expired"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class WaitBoundaryDecision:
    """Host wait 时间边界判定结果。

    :param kind: 边界状态分类。
    :param boundary_field: 被采用的持久化字段名；无边界时为 ``None``。
    :param boundary_text: 被采用的原始 UTC 文本；无边界时为 ``None``。
    :param boundary_at: 解析后的 UTC 时间；无边界或非法边界时为 ``None``。
    """

    kind: WaitBoundaryDecisionKind
    boundary_field: str | None
    boundary_text: str | None
    boundary_at: datetime | None

    def __post_init__(self) -> None:
        """校验边界判定结果字段。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段组合不符合边界判定语义时抛出。
        """

        if not isinstance(self.kind, WaitBoundaryDecisionKind):
            raise TypeError("kind must be WaitBoundaryDecisionKind")
        if self.boundary_field is not None and self.boundary_field not in (
            _WAIT_BOUNDARY_FIELD_DEADLINE,
            _WAIT_BOUNDARY_FIELD_EXPIRES,
        ):
            raise ValueError("boundary_field is not supported")
        if self.kind is WaitBoundaryDecisionKind.ACTIVE and self.boundary_text is None:
            if self.boundary_field is not None or self.boundary_at is not None:
                raise ValueError("empty active boundary cannot carry parsed fields")
            return
        if self.boundary_text is None or self.boundary_field is None:
            raise ValueError("non-empty boundary decision requires boundary metadata")
        if self.kind in (
            WaitBoundaryDecisionKind.ACTIVE,
            WaitBoundaryDecisionKind.EXPIRED,
        ) and self.boundary_at is None:
            raise ValueError("valid boundary decision requires parsed datetime")
        if self.kind is WaitBoundaryDecisionKind.INVALID and self.boundary_at is not None:
            raise ValueError("invalid boundary cannot carry parsed datetime")


def classify_wait_time_boundary(
    wait_record: WaitRecordRow, *, observed_at: datetime
) -> WaitBoundaryDecision:
    """按 Host 持久化 wait 边界判断当前观察是否仍可处理。

    ``deadline_at`` 优先于 ``expires_at``。边界不存在时表示当前 wait 在时间
    维度仍 active；边界文本非法时返回 ``INVALID``，由调用方 fail closed。

    :param wait_record: Host wait record 快照。
    :param observed_at: 当前观察或 resolve 请求的 UTC 时间。
    :returns: typed 时间边界判定结果。
    :raises TypeError: ``observed_at`` 类型非法时抛出。
    :raises ValueError: ``observed_at`` 不是 timezone-aware datetime 时抛出。
    """

    if not isinstance(observed_at, datetime):
        raise TypeError("observed_at must be datetime")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    boundary_field = (
        _WAIT_BOUNDARY_FIELD_DEADLINE
        if wait_record.deadline_at is not None
        else _WAIT_BOUNDARY_FIELD_EXPIRES
        if wait_record.expires_at is not None
        else None
    )
    boundary_text = (
        wait_record.deadline_at
        if wait_record.deadline_at is not None
        else wait_record.expires_at
    )
    if boundary_text is None or boundary_field is None:
        return WaitBoundaryDecision(
            kind=WaitBoundaryDecisionKind.ACTIVE,
            boundary_field=None,
            boundary_text=None,
            boundary_at=None,
        )
    try:
        boundary_at = parse_utc_timestamp(boundary_text)
    except ValueError:
        return WaitBoundaryDecision(
            kind=WaitBoundaryDecisionKind.INVALID,
            boundary_field=boundary_field,
            boundary_text=boundary_text,
            boundary_at=None,
        )
    if observed_at > boundary_at:
        return WaitBoundaryDecision(
            kind=WaitBoundaryDecisionKind.EXPIRED,
            boundary_field=boundary_field,
            boundary_text=boundary_text,
            boundary_at=boundary_at,
        )
    return WaitBoundaryDecision(
        kind=WaitBoundaryDecisionKind.ACTIVE,
        boundary_field=boundary_field,
        boundary_text=boundary_text,
        boundary_at=boundary_at,
    )
