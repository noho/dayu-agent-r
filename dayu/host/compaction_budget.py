"""Host compaction 后上下文预算估算 helper。

本模块只根据 ``CompactionRequest`` 中的 typed 引用、当前输入摘要与
compactor 摘要文本估算 compact 后仍会进入上下文的 token。它不读取
EventLog、memory projection 或 artifact 内容，也不调用 compactor。
"""

from __future__ import annotations

from math import ceil

from dayu.host.compaction import CompactionRequest
from dayu.host.context_budget import DEFAULT_ESTIMATOR_CHARS_PER_TOKEN


def estimate_compacted_context_budget(
    request: CompactionRequest, *, summary: str, system_prompt: str
) -> int:
    """估算 compact 后上下文预算。

    :param request: Host compaction request。
    :param summary: compact 产出的摘要文本。
    :param system_prompt: compact 后运行仍需携带的系统提示估算文本。
    :returns: summary 加保留上下文的保守 token 估算。
    :raises TypeError: request 类型非法时抛出。
    """

    if not isinstance(request, CompactionRequest):
        raise TypeError("request must be CompactionRequest")
    summary_tokens = estimate_text_tokens(summary)
    preserved_tokens = _estimate_preserved_context_tokens(
        request,
        system_prompt=system_prompt,
    )
    return summary_tokens + preserved_tokens


def estimate_text_tokens(text: str) -> int:
    """按 Host context budget 统一常数估算文本 token。

    :param text: 文本内容。
    :returns: 至少为 1 的 token 估算。
    :raises Exception: 不主动抛出异常。
    """

    return max(1, ceil(len(text) / DEFAULT_ESTIMATOR_CHARS_PER_TOKEN))


def _estimate_preserved_context_tokens(
    request: CompactionRequest, *, system_prompt: str
) -> int:
    """估算 compact 后仍会保留的上下文 token。

    :param request: Host compaction request。
    :param system_prompt: compact 后运行仍需携带的系统提示估算文本。
    :returns: 保留上下文的保守 token 估算。
    :raises Exception: 不主动抛出异常。
    """

    typed_fragment_tokens = sum(
        estimate_text_tokens(fragment)
        for fragment in (
            system_prompt,
            request.current_message_summary.summary_text,
            request.current_message_summary.current_user_input_ref,
            *_preserved_ref_texts(request),
        )
    )
    return max(
        typed_fragment_tokens,
        _estimate_preserved_share_from_budget(request),
    )


def _preserved_ref_texts(request: CompactionRequest) -> tuple[str, ...]:
    """返回 compact 后必须保留的引用文本集合。

    :param request: Host compaction request。
    :returns: 去重后的 ref tuple。
    :raises Exception: 不主动抛出异常。
    """

    preserved_refs = {
        request.current_message_summary.current_user_input_ref,
        *request.recent_raw_turn_refs,
        *request.tool_fact_refs,
        *request.verified_fact_refs,
        *request.existing_episode_summary_refs,
    }
    return tuple(sorted(preserved_refs))


def _estimate_preserved_share_from_budget(request: CompactionRequest) -> int:
    """按保留引用占比从 compact 前预算中估算保留部分。

    :param request: Host compaction request。
    :returns: 保留部分 token 估算。
    :raises Exception: 不主动抛出异常。
    """

    source_refs = {
        *request.input_event_refs,
        *request.tool_fact_refs,
        *request.verified_fact_refs,
        *request.existing_episode_summary_refs,
    }
    preserved_refs = set(_preserved_ref_texts(request))
    if len(source_refs) == 0:
        return 0
    retained_count = len(preserved_refs.intersection(source_refs))
    if retained_count == 0:
        return 0
    estimated_tokens = request.budget_before_compact.estimated_input_tokens
    return ceil(estimated_tokens * retained_count / len(source_refs))


__all__ = ["estimate_compacted_context_budget", "estimate_text_tokens"]
