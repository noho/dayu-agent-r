"""``StreamingXMLTagExtractor`` 的 ``start_only`` 安全锁测试。

关键语义对齐 OLD ``xml_extractor.py``：

- 标签出现在文本开头（允许前置空白）→ 正常剥离。
- 标签**之前**已出现非空白正文 → 提取器永久失活，标签字面量
  作为 outside_text 透传，避免误剥离。
- 失活后即使再次出现 ``<thought>...</thought>`` 也不再剥离。
"""

from __future__ import annotations

from dayu.engine.runners.openai.xml_tag_extractor import (
    StreamingXMLTagExtractor,
)


def test_thought_at_start_extracted() -> None:
    """以 ``<thought>`` 开头的文本应被剥离。"""

    extractor = StreamingXMLTagExtractor(tag_name="thought")
    delta = extractor.feed("<thought>secret</thought>visible")
    assert delta.outside_text == "visible"
    assert delta.inside_text == "secret"


def test_thought_with_leading_whitespace_extracted() -> None:
    """前置空白不阻断 start_only 识别。"""

    extractor = StreamingXMLTagExtractor(tag_name="thought")
    delta = extractor.feed("\n  <thought>x</thought>y")
    assert delta.outside_text == "\n  y"
    assert delta.inside_text == "x"


def test_thought_after_content_treated_as_text() -> None:
    """正文里出现 ``<thought>`` 字面量应**不**被剥离。"""

    extractor = StreamingXMLTagExtractor(tag_name="thought")
    delta = extractor.feed("hi <thought>noise</thought>tail")
    # start_only 失活：整段作为 outside 输出。
    assert delta.outside_text == "hi <thought>noise</thought>tail"
    assert delta.inside_text == ""


def test_deactivation_persists_across_feeds() -> None:
    """一旦失活，后续 feed 即使含完整标签也透传。"""

    extractor = StreamingXMLTagExtractor(tag_name="thought")
    first = extractor.feed("hi ")
    assert first.outside_text == "hi "
    assert first.inside_text == ""
    second = extractor.feed("<thought>noise</thought>tail")
    assert second.outside_text == "<thought>noise</thought>tail"
    assert second.inside_text == ""


def test_start_only_off_allows_mid_text_thought() -> None:
    """``start_only=False`` 不触发失活，仍按状态机剥离。"""

    extractor = StreamingXMLTagExtractor(
        tag_name="thought", start_only=False
    )
    delta = extractor.feed("hi <thought>noise</thought>tail")
    assert delta.outside_text == "hi tail"
    assert delta.inside_text == "noise"
