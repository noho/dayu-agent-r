"""财报工具限制配置。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FinsToolLimits:
    """财报工具限制配置。

    Attributes:
        processor_cache_max_entries: Processor 缓存最大条目数（仅 LRU，无 TTL）。
        list_documents_max_items: `list_documents` 返回最大文档条目数。
        get_document_sections_max_items: `get_document_sections` 返回最大章节条目数。
        search_document_max_items: `search_document` 返回最大命中条目数。
        list_tables_max_items: `list_tables` 返回最大表格条目数。
        read_section_max_chars: `read_section` 文本最大字符数（超出由当前 ToolRuntime 截断）。
        get_page_content_max_chars: `get_page_content` 文本最大字符数（超出由当前 ToolRuntime 截断）。
        get_table_max_items: `get_table` 中列表数据最大条目数。
        get_financial_statement_max_items: `get_financial_statement` 列表数据最大条目数。
        query_xbrl_facts_max_items: `query_xbrl_facts` 列表数据最大条目数。
    """

    processor_cache_max_entries: int = 128
    list_documents_max_items: int = 300
    get_document_sections_max_items: int = 1200
    search_document_max_items: int = 20
    list_tables_max_items: int = 50
    read_section_max_chars: int = 80000
    get_page_content_max_chars: int = 80000
    get_table_max_items: int = 800
    get_financial_statement_max_items: int = 1200
    query_xbrl_facts_max_items: int = 1200
