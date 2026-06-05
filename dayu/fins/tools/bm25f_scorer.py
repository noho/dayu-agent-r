"""BM25F 风格的 section 检索打分模块。

该模块为 ``search_document`` 提供低侵入的多字段词法排序能力：
- 基于 section 摘要字段构建文档级词法索引。
- 对单条搜索命中计算 BM25F 风格分数。
- 仅增强排序，不负责召回。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Mapping

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

_FIELD_WEIGHTS: dict[str, float] = {
    "title": 3.0,
    "item": 2.0,
    "topic": 2.0,
    "path": 2.0,
    "preview": 1.0,
    "content": 1.0,
}

_FIELD_B: dict[str, float] = {
    "title": 0.35,
    "item": 0.2,
    "topic": 0.2,
    "path": 0.35,
    "preview": 0.75,
    "content": 0.75,
}

_K1 = 1.2


@dataclass(frozen=True)
class BM25FSectionProfile:
    """单个 section 的词法字段画像。

    Args:
        section_ref: section 唯一标识。
        field_tokens: 各字段对应的 token 序列。

    Returns:
        无。

    Raises:
        无。
    """

    section_ref: str
    field_tokens: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class BM25FSectionIndex:
    """BM25F 风格的 section 索引。

    Args:
        profiles: ``section_ref -> BM25FSectionProfile`` 映射。
        document_frequency: token 的 section 级文档频次。
        avg_field_lengths: 各字段平均长度。
        avg_content_length: content 字段平均长度。
        document_count: section 总数。

    Returns:
        无。

    Raises:
        无。
    """

    profiles: dict[str, BM25FSectionProfile]
    document_frequency: dict[str, int]
    avg_field_lengths: dict[str, float]
    avg_content_length: float
    document_count: int


def build_section_bm25f_index(sections: Sequence[Mapping[str, Any]]) -> BM25FSectionIndex:
    """基于增强后的 section 摘要构建 BM25F 索引。

    Args:
        sections: 已包含 ``title/item/topic/path/preview`` 等字段的章节摘要。

    Returns:
        BM25FSectionIndex 实例。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    profiles: dict[str, BM25FSectionProfile] = {}
    document_frequency: Counter[str] = Counter()
    total_field_lengths: Counter[str] = Counter()

    for section in sections:
        section_ref = str(section.get("ref") or "").strip()
        if not section_ref:
            continue
        field_texts = {
            "title": _normalize_text(section.get("title")),
            "item": _normalize_text(section.get("item")),
            "topic": _normalize_text(section.get("topic")),
            "path": _normalize_text(section.get("path")),
            "preview": _normalize_text(section.get("preview")),
        }
        field_tokens = {
            field_name: tuple(_tokenize(text))
            for field_name, text in field_texts.items()
        }
        profiles[section_ref] = BM25FSectionProfile(
            section_ref=section_ref,
            field_tokens=field_tokens,
        )
        seen_terms: set[str] = set()
        for field_name, tokens in field_tokens.items():
            total_field_lengths[field_name] += len(tokens)
            seen_terms.update(tokens)
        document_frequency.update(seen_terms)

    document_count = len(profiles)
    avg_field_lengths: dict[str, float] = {}
    for field_name in ("title", "item", "topic", "path", "preview"):
        avg_field_lengths[field_name] = (
            total_field_lengths[field_name] / document_count if document_count > 0 else 0.0
        )

    return BM25FSectionIndex(
        profiles=profiles,
        document_frequency=dict(document_frequency),
        avg_field_lengths=avg_field_lengths,
        avg_content_length=avg_field_lengths.get("preview", 0.0),
        document_count=document_count,
    )


def score_search_entry_bm25f(
    *,
    entry: Mapping[str, Any],
    query: str,
    index: BM25FSectionIndex,
) -> float:
    """计算单条搜索命中的 BM25F 风格分数。

    Args:
        entry: 搜索命中条目。
        query: 原始查询词。
        index: 预构建的 BM25F 索引。

    Returns:
        BM25F 风格得分；无法计算时返回 ``0.0``。

    Raises:
        RuntimeError: 计算失败时抛出。
    """

    query_terms = _tokenize(query)
    if not query_terms or index.document_count <= 0:
        return 0.0

    section_ref = str(entry.get("section_ref") or "").strip()
    if not section_ref:
        return 0.0
    profile = index.profiles.get(section_ref)
    if profile is None:
        return 0.0

    content_tokens = tuple(_tokenize(_extract_entry_content_text(entry)))
    field_counters: dict[str, Counter[str]] = {
        field_name: Counter(tokens)
        for field_name, tokens in profile.field_tokens.items()
    }
    field_counters["content"] = Counter(content_tokens)

    avg_field_lengths = dict(index.avg_field_lengths)
    avg_field_lengths["content"] = index.avg_content_length

    score = 0.0
    for term in query_terms:
        term_df = index.document_frequency.get(term, 0)
        if term_df <= 0:
            continue
        idf = math.log(1.0 + ((index.document_count - term_df + 0.5) / (term_df + 0.5)))
        weighted_tf = 0.0
        for field_name, weight in _FIELD_WEIGHTS.items():
            counter = field_counters.get(field_name)
            if counter is None:
                continue
            tf = counter.get(term, 0)
            if tf <= 0:
                continue
            field_length = sum(counter.values())
            avg_length = avg_field_lengths.get(field_name, 0.0)
            normalized_tf = _normalize_tf(
                tf=tf,
                field_length=field_length,
                avg_field_length=avg_length,
                b=_FIELD_B[field_name],
            )
            weighted_tf += weight * normalized_tf
        if weighted_tf <= 0:
            continue
        score += idf * (((_K1 + 1.0) * weighted_tf) / (_K1 + weighted_tf))
    return round(score, 6)


def _normalize_tf(*, tf: int, field_length: int, avg_field_length: float, b: float) -> float:
    """按 BM25F 公式标准化字段内词频。

    Args:
        tf: 字段内原始词频。
        field_length: 字段 token 长度。
        avg_field_length: 字段平均长度。
        b: 长度归一化参数。

    Returns:
        标准化后的 tf。

    Raises:
        RuntimeError: 计算失败时抛出。
    """

    if tf <= 0:
        return 0.0
    if field_length <= 0 or avg_field_length <= 0:
        return float(tf)
    denominator = 1.0 - b + b * (field_length / avg_field_length)
    if denominator <= 0:
        return float(tf)
    return float(tf) / denominator


def _extract_entry_content_text(entry: Mapping[str, Any]) -> str:
    """提取搜索命中的正文语料字段。

    Args:
        entry: 搜索命中条目。

    Returns:
        优先返回 evidence.context，其次 matched_text/snippet。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    evidence = entry.get("evidence")
    if isinstance(evidence, Mapping):
        context = _normalize_text(evidence.get("context"))
        if context:
            return context
        matched_text = _normalize_text(evidence.get("matched_text"))
        if matched_text:
            return matched_text
    return _normalize_text(entry.get("snippet"))


def _normalize_text(value: Any) -> str:
    """将任意输入规整为可分词文本。

    Args:
        value: 原始值。

    Returns:
        规整后的字符串。

    Raises:
        RuntimeError: 转换失败时抛出。
    """

    text = str(value or "").strip().lower()
    return " ".join(text.split())


def _tokenize(text: str) -> list[str]:
    """提取 ASCII token。

    Args:
        text: 输入文本。

    Returns:
        token 列表。

    Raises:
        RuntimeError: 分词失败时抛出。
    """

    return _TOKEN_PATTERN.findall(text)