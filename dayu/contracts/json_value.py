"""严格 JSON 值类型别名。

本模块定义 :data:`JsonValue` 类型别名，用于在 Engine 公共契约中标注
任意可序列化为 JSON 的强类型值。Phase 0 仅落地类型别名本身，
**不**实现 runtime validator、不实现序列化 helper；运行时的 JSON
合法性校验由后续消费 Phase 的具体 adapter 负责。

- 不可变结构使用 :class:`collections.abc.Mapping`，构造侧用 ``dict`` 即可；
  类型层面禁止以裸 ``dict`` / ``list`` 形式承诺协变可变契约。
- ``int`` 与 ``bool`` 在 Python 类型系统中是子类关系；本 Phase 不做
  bool/int 区分守护，留给后续 Phase 在真正消费 ``JsonValue`` 时处理。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias

JsonValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | list["JsonValue"]
    | Mapping[str, "JsonValue"]
)
"""严格 JSON 值联合类型。

成员：

- ``None``：JSON ``null``。
- ``bool``：JSON ``true`` / ``false``。
- ``int`` / ``float``：JSON 数值。
- ``str``：JSON 字符串。
- ``list[JsonValue]``：JSON 数组。
- ``Mapping[str, JsonValue]``：JSON 对象。
"""

__all__ = ["JsonValue"]
