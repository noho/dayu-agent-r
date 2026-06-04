"""Host context governance vNext compact quality checker。

本模块实现 Context Governance 的 vNext compact output accept barrier。它不
append canonical compact events，不写 memory projection，也不执行 proactive /
reactive orchestration。
"""

from __future__ import annotations

from dayu.host.compaction import (
    CONVERSATION_COMPACT_ANSWER_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_DIAGNOSTIC_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_FORWARD_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_REFERENCE_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_SUMMARY_SOURCE_SECTIONS_VNEXT,
    CompactQualityCheckResultVNext,
    CompactQualityIssueVNext,
    ConversationCompactInputVNext,
    ConversationCompactLabelSectionVNext,
    ConversationCompactOutputVNext,
    conversation_compact_label_looks_stale_vnext,
)


def check_conversation_compact_output_vnext(
    request: ConversationCompactInputVNext,
    candidate: ConversationCompactOutputVNext,
) -> CompactQualityCheckResultVNext:
    """检查 vNext compact output 是否满足 Host accept barrier。

    :param request: vNext compact input。
    :param candidate: vNext compact output candidate。
    :returns: vNext quality check 结果。
    :raises TypeError: ``request`` 或 ``candidate`` 类型非法时抛出。
    """

    if not isinstance(request, ConversationCompactInputVNext):
        raise TypeError("request must be ConversationCompactInputVNext")
    if not isinstance(candidate, ConversationCompactOutputVNext):
        raise TypeError("candidate must be ConversationCompactOutputVNext")
    collector = _VNextQualityIssueCollector()
    if candidate.session_summary is not None:
        _collect_vnext_label_issues(
            request,
            candidate.session_summary.source_labels,
            allowed_sections=CONVERSATION_COMPACT_SUMMARY_SOURCE_SECTIONS_VNEXT,
            collector=collector,
            require_non_empty=True,
        )
    for fact in candidate.evidence_backed_facts:
        _collect_vnext_label_issues(
            request,
            fact.evidence_labels,
            allowed_sections=CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT,
            collector=collector,
            require_non_empty=True,
        )
        _collect_vnext_label_issues(
            request,
            fact.source_labels,
            allowed_sections=CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT,
            collector=collector,
            require_non_empty=False,
        )
    for anchor in candidate.answer_anchors:
        _collect_vnext_label_issues(
            request,
            anchor.answer_source_labels,
            allowed_sections=CONVERSATION_COMPACT_ANSWER_SOURCE_SECTIONS_VNEXT,
            collector=collector,
            require_non_empty=True,
        )
    for intent in candidate.forward_intents:
        _collect_vnext_label_issues(
            request,
            intent.source_labels,
            allowed_sections=CONVERSATION_COMPACT_FORWARD_SOURCE_SECTIONS_VNEXT,
            collector=collector,
            require_non_empty=True,
        )
    for item in candidate.reference_continuity_items:
        _collect_vnext_label_issues(
            request,
            item.source_labels,
            allowed_sections=CONVERSATION_COMPACT_REFERENCE_SOURCE_SECTIONS_VNEXT,
            collector=collector,
            require_non_empty=True,
        )
    for diagnostic in candidate.diagnostics:
        _collect_vnext_label_issues(
            request,
            diagnostic.source_labels,
            allowed_sections=CONVERSATION_COMPACT_DIAGNOSTIC_SOURCE_SECTIONS_VNEXT,
            collector=collector,
            require_non_empty=False,
        )
    reasons = collector.reasons()
    return CompactQualityCheckResultVNext(
        accepted=len(reasons) == 0,
        rejection_reasons=reasons,
    )


class _VNextQualityIssueCollector:
    """vNext quality issue 去重收集器。"""

    def __init__(self) -> None:
        """初始化收集器。

        :returns: ``None``。
        """

        self._issues: list[CompactQualityIssueVNext] = []

    def add(self, issue: CompactQualityIssueVNext) -> None:
        """追加 vNext 拒绝原因。

        :param issue: 拒绝原因。
        :returns: ``None``。
        """

        if issue not in self._issues:
            self._issues.append(issue)

    def reasons(self) -> tuple[CompactQualityIssueVNext, ...]:
        """返回已收集 vNext 拒绝原因。

        :returns: 拒绝原因 tuple。
        """

        return tuple(self._issues)


def _collect_vnext_label_issues(
    request: ConversationCompactInputVNext,
    labels: tuple[str, ...],
    *,
    allowed_sections: tuple[ConversationCompactLabelSectionVNext, ...],
    collector: _VNextQualityIssueCollector,
    require_non_empty: bool,
) -> None:
    """收集 vNext label contract issue。

    :param request: vNext compact input。
    :param labels: 待校验 labels。
    :param allowed_sections: 允许引用的 section。
    :param collector: issue 收集器。
    :param require_non_empty: 是否要求至少一个 label。
    :returns: ``None``。
    """

    if require_non_empty and len(labels) == 0:
        collector.add(CompactQualityIssueVNext.MISSING_SOURCE_LABEL)
    for label in labels:
        section = request.source_section(label)
        if section is ConversationCompactLabelSectionVNext.CURRENT_INPUT_ANCHOR:
            collector.add(CompactQualityIssueVNext.CURRENT_INPUT_ANCHOR_CITED)
            continue
        if section is None:
            if conversation_compact_label_looks_stale_vnext(label):
                collector.add(CompactQualityIssueVNext.STALE_SOURCE_LABEL)
            else:
                collector.add(CompactQualityIssueVNext.UNKNOWN_SOURCE_LABEL)
            continue
        if section not in allowed_sections:
            collector.add(CompactQualityIssueVNext.CROSS_SECTION_LABEL)


__all__ = ["check_conversation_compact_output_vnext"]
