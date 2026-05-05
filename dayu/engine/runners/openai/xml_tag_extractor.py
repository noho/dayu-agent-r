"""流式 XML 单标签内容提取状态机。

本模块提供 :class:`StreamingXMLTagExtractor`，从 LLM 文本流中实时把
特定 XML 标签（如 ``<thought>...</thought>``）剥离出来，分别向调用
方暴露「标签外」与「标签内」两路文本增量。

实现要点：

- 单一目标 ``tag_name``；未声明 ``tag_name`` 时直接放行所有文本。
- 状态机基于「字符级匹配 + 残缓冲」：当输入流恰好截断在
  ``<thoug`` 这种半个起始标签上时，残缓必须保留到下一次 ``feed``
  才决定是否真的命中标签。
- ``start_only`` 安全锁（默认开启）：只识别**出现在响应开头**（允许
  前置空白）的标签；一旦在标签外出现非空白正文（含字面量
  ``<thought>``-like 文本），提取器**永久失活**，后续输入整体走正文
  通道。该语义对齐 OLD ``xml_extractor.py`` ，避免把内容里出现的
  ``<thought>`` 误剥离成 reasoning。
- 流结束时调用 :meth:`flush`，把所有未决残缓作为标签外正文吐出，
  避免「半个标签」永久卡在内部缓冲。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto


class _State(StrEnum):
    """提取器内部状态。"""

    OUTSIDE = auto()
    """当前光标位于标签外，文本走「正文」通道。"""

    INSIDE = auto()
    """当前光标位于标签内，文本走「reasoning」通道。"""


@dataclass(frozen=True, slots=True)
class XMLExtractionDelta:
    """一次 ``feed`` / ``flush`` 调用的增量结果。

    :param outside_text: 本次新增的标签外文本。
    :param inside_text: 本次新增的标签内文本。
    """

    outside_text: str
    inside_text: str


class StreamingXMLTagExtractor:
    """流式 XML 单标签内容提取状态机。

    :param tag_name: 目标标签名（不含尖括号）；为 ``None`` 表示禁用
        提取，所有 ``feed`` 文本均归入 ``outside_text``。
    :param start_only: 安全锁；默认为 ``True``，只识别出现在文本开头
        （允许前置空白）的目标标签。一旦在标签外检测到非空白正文，
        提取器永久失活，后续输入整体走 ``outside_text``。

    使用流程：

    1. 多次调用 :meth:`feed` 投喂增量文本，逐次拿到
       :class:`XMLExtractionDelta`。
    2. 流结束时调用一次 :meth:`flush`，把残缓收口。
    """

    def __init__(
        self, *, tag_name: str | None, start_only: bool = True
    ) -> None:
        self._tag_name: str | None = tag_name
        self._state: _State = _State.OUTSIDE
        self._buffer: str = ""
        self._start_only: bool = start_only
        self._is_active: bool = True
        self._has_seen_non_whitespace: bool = False

    @property
    def tag_name(self) -> str | None:
        """返回目标标签名。"""

        return self._tag_name

    def _open_pattern(self) -> str:
        """构造起始标签。"""

        return f"<{self._tag_name}>"

    def _close_pattern(self) -> str:
        """构造结束标签。"""

        return f"</{self._tag_name}>"

    def feed(self, chunk: str) -> XMLExtractionDelta:
        """投喂一段流式增量文本。

        :param chunk: 增量字符串。
        :returns: 本次新增的标签外 / 标签内文本切分。

        当目标标签名未配置或 ``start_only`` 安全锁已失活时，
        ``chunk`` 整体落到 ``outside_text``。
        """

        if self._tag_name is None or not chunk:
            return XMLExtractionDelta(outside_text=chunk, inside_text="")
        if not self._is_active:
            return XMLExtractionDelta(outside_text=chunk, inside_text="")
        outside_pieces: list[str] = []
        inside_pieces: list[str] = []
        self._buffer += chunk
        while self._buffer:
            if (
                self._start_only
                and self._state is _State.OUTSIDE
                and self._is_active
            ):
                if self._should_deactivate():
                    self._is_active = False
                    outside_pieces.append(self._buffer)
                    self._buffer = ""
                    break
            if self._state is _State.OUTSIDE:
                pattern = self._open_pattern()
                index = self._buffer.find(pattern)
                if index == -1:
                    safe_len = self._safe_emit_length(self._buffer, pattern)
                    if safe_len > 0:
                        emitted = self._buffer[:safe_len]
                        outside_pieces.append(emitted)
                        if emitted.strip():
                            self._has_seen_non_whitespace = True
                        self._buffer = self._buffer[safe_len:]
                    break
                if index > 0:
                    emitted = self._buffer[:index]
                    outside_pieces.append(emitted)
                    if emitted.strip():
                        self._has_seen_non_whitespace = True
                self._buffer = self._buffer[index + len(pattern) :]
                self._state = _State.INSIDE
                continue
            pattern = self._close_pattern()
            index = self._buffer.find(pattern)
            if index == -1:
                safe_len = self._safe_emit_length(self._buffer, pattern)
                if safe_len > 0:
                    inside_pieces.append(self._buffer[:safe_len])
                    self._buffer = self._buffer[safe_len:]
                break
            if index > 0:
                inside_pieces.append(self._buffer[:index])
            self._buffer = self._buffer[index + len(pattern) :]
            self._state = _State.OUTSIDE
        return XMLExtractionDelta(
            outside_text="".join(outside_pieces),
            inside_text="".join(inside_pieces),
        )

    def _should_deactivate(self) -> bool:
        """判断当前是否需要触发 ``start_only`` 安全锁失活。

        当 ``OUTSIDE`` 状态下，若已经看到过非空白正文，或当前
        buffer 中起始标签 ``<`` 之前已经出现非空白字符，则视为
        标签未出现在响应开头，永久失活。
        """

        if self._has_seen_non_whitespace:
            return True
        first_lt = self._buffer.find("<")
        if first_lt == -1:
            return bool(self._buffer.strip())
        if first_lt > 0:
            return bool(self._buffer[:first_lt].strip())
        return False

    def flush(self) -> XMLExtractionDelta:
        """流结束时收口残缓。

        :returns: 残缓划分后的 outside / inside 文本。

        若残缓位于 ``OUTSIDE``，作为正文吐出；位于 ``INSIDE``，作为
        reasoning 吐出（视作未闭合的 thought 段）。``start_only``
        失活分支上残缓也作为正文吐出。
        """

        if not self._buffer:
            return XMLExtractionDelta(outside_text="", inside_text="")
        if self._state is _State.OUTSIDE or not self._is_active:
            outside = self._buffer
            self._buffer = ""
            return XMLExtractionDelta(outside_text=outside, inside_text="")
        inside = self._buffer
        self._buffer = ""
        return XMLExtractionDelta(outside_text="", inside_text=inside)

    @staticmethod
    def _safe_emit_length(buffer: str, pattern: str) -> int:
        """计算可安全输出的前缀长度。

        当 ``buffer`` 末尾可能是 ``pattern`` 的前缀时（半个标签），
        必须保留这部分残缓等待下一次 ``feed``。
        """

        if not buffer:
            return 0
        max_overlap = min(len(buffer), len(pattern) - 1)
        for overlap in range(max_overlap, 0, -1):
            if buffer.endswith(pattern[:overlap]):
                return len(buffer) - overlap
        return len(buffer)


__all__ = ["StreamingXMLTagExtractor", "XMLExtractionDelta"]

