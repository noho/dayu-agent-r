"""Host durable foundation codec 与 digest helper。

本模块提供 canonical JSON、固定 UTC timestamp 格式与 sha256 digest helper。
这些 helper 是 SQLite durable facts 的编码真源；后续 EventLog、payload 与
idempotency 逻辑应复用这里的格式，不在各模块重新定义。
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256

from dayu.contracts.json_value import JsonValue

_DIGEST_PREFIX = "sha256:"
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
)


def canonical_json_dumps(value: JsonValue) -> str:
    """把 JSON 值序列化为 canonical JSON 文本。

    :param value: 待序列化的 JSON 值。
    :returns: key 排序、紧凑分隔符、禁止非有限浮点数的 JSON 文本。
    :raises ValueError: ``value`` 含有 ``NaN``、``Infinity`` 或不可序列化值时抛出。
    :raises TypeError: ``value`` 含有 JSON 不支持的 Python 值时抛出。
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def format_utc_timestamp(value: datetime) -> str:
    """格式化固定微秒精度 UTC ``Z`` timestamp。

    :param value: timezone-aware ``datetime``。
    :returns: ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` 格式的 UTC timestamp。
    :raises ValueError: ``value`` 是 naive datetime 时抛出。
    """

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    utc_value = value.astimezone(UTC)
    return utc_value.strftime(_UTC_TIMESTAMP_FORMAT)


def parse_utc_timestamp(value: str) -> datetime:
    """解析固定微秒精度 UTC ``Z`` timestamp。

    :param value: ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` 格式 timestamp。
    :returns: timezone-aware UTC ``datetime``。
    :raises ValueError: 字符串不符合固定格式或日期值无效时抛出。
    """

    if _UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise ValueError("timestamp must use fixed UTC microsecond Z format")
    parsed = datetime.strptime(value, _UTC_TIMESTAMP_FORMAT)
    return parsed.replace(tzinfo=UTC)


def sha256_digest_bytes(content: bytes) -> str:
    """计算 bytes 的标准 Host durable sha256 digest。

    :param content: 待计算 digest 的原始 bytes。
    :returns: ``sha256:<64 lowercase hex>`` 格式 digest。
    """

    return _DIGEST_PREFIX + sha256(content).hexdigest()


def sha256_digest_json(value: JsonValue) -> str:
    """计算 JSON 值 canonical encoding 的 sha256 digest。

    :param value: 待计算 digest 的 JSON 值。
    :returns: ``sha256:<64 lowercase hex>`` 格式 digest。
    :raises ValueError: ``value`` 含有 ``NaN``、``Infinity`` 或不可序列化值时抛出。
    :raises TypeError: ``value`` 含有 JSON 不支持的 Python 值时抛出。
    """

    return sha256_digest_bytes(canonical_json_dumps(value).encode("utf-8"))
