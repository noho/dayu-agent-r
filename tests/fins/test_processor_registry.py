"""Fins processor registry 的 focused contract tests。"""

from __future__ import annotations

from dayu.fins.processors.registry import build_fins_processor_registry


def test_fins_processor_registry_overlays_documents_defaults() -> None:
    """Fins 注册表应覆盖 documents 默认处理器并保留 SEC 处理器优先级。"""

    registry = build_fins_processor_registry()
    processors_by_name: dict[str, tuple[str, int]] = {}
    priorities_by_name: dict[str, int] = {}

    for record in registry.list_processors():
        name = record["name"]
        class_name = record["class"]
        priority = record["priority"]
        assert isinstance(name, str)
        assert isinstance(class_name, str)
        assert isinstance(priority, int)
        processors_by_name[name] = (class_name, priority)
        priorities_by_name[name] = priority

    assert processors_by_name["docling_processor"] == ("FinsDoclingProcessor", 100)
    assert processors_by_name["markdown_processor"] == ("FinsMarkdownProcessor", 100)
    assert processors_by_name["bs_processor"] == ("FinsBSProcessor", 80)
    assert processors_by_name["sec_processor"] == ("SecProcessor", 120)

    assert processors_by_name["docling_processor"][0] != "DoclingProcessor"
    assert processors_by_name["markdown_processor"][0] != "MarkdownProcessor"
    assert processors_by_name["bs_processor"][0] != "BSProcessor"

    assert "sc13_section_processor" in priorities_by_name
    assert "six_k_section_processor" in priorities_by_name
    assert "def14a_section_processor" in priorities_by_name
    assert "eight_k_section_processor" in priorities_by_name
    assert "ten_k_section_processor" in priorities_by_name
    assert "ten_q_section_processor" in priorities_by_name
    assert "twenty_f_section_processor" in priorities_by_name
    assert "sc13_section_processor_fallback" in priorities_by_name
    assert "def14a_section_processor_fallback" in priorities_by_name
    assert "eight_k_section_processor_fallback" in priorities_by_name
    assert "ten_k_section_processor_fallback" in priorities_by_name
    assert "ten_q_section_processor_fallback" in priorities_by_name
    assert "twenty_f_section_processor_fallback" in priorities_by_name

    priority_bucket_200 = {
        name for name, priority in priorities_by_name.items() if priority == 200
    }
    priority_bucket_190 = {
        name for name, priority in priorities_by_name.items() if priority == 190
    }

    assert priority_bucket_200 == {
        "sc13_section_processor",
        "six_k_section_processor",
        "def14a_section_processor",
        "eight_k_section_processor",
        "ten_k_section_processor",
        "ten_q_section_processor",
        "twenty_f_section_processor",
    }
    assert priority_bucket_190 == {
        "sc13_section_processor_fallback",
        "def14a_section_processor_fallback",
        "eight_k_section_processor_fallback",
        "ten_k_section_processor_fallback",
        "ten_q_section_processor_fallback",
        "twenty_f_section_processor_fallback",
    }
