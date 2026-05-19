"""测试 / 本地开发专用 deterministic context compactor。

本模块存在于 production 包中只是为了让 tests 和本地 composition 可以显式
注入一个稳定 compactor。生产默认路径不得隐式导入或默认使用
``FakeContextCompactor``；真实生产装配必须显式提供 ``ContextCompactor``。
"""

from __future__ import annotations

from dayu.host.compaction import (
    CompactInputRange,
    CompactionCandidate,
    CompactionRequest,
    ContextCompactor,
    EpisodeSummaryCandidate,
    PinnedPatchOperation,
    PinnedStatePatchCandidate,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
    PreservationEvidence,
)


class FakeContextCompactor(ContextCompactor):
    """Deterministic context compactor。

    该实现只根据 typed request 构造稳定 candidate，不调用 LLM，不访问外部
    状态，不应作为生产默认 compactor。
    """

    async def compact(self, request: CompactionRequest) -> CompactionCandidate:
        """生成 deterministic compaction candidate。

        :param request: Host 构造的 compaction 请求。
        :returns: deterministic compaction candidate。
        :raises TypeError: ``request`` 类型非法时抛出。
        """

        if not isinstance(request, CompactionRequest):
            raise TypeError("request must be CompactionRequest")
        evidence = _preservation_evidence(request)
        evidence_refs = tuple(evidence_item.evidence_id for evidence_item in evidence)
        summarized_ranges = _summarized_ranges(request)
        return CompactionCandidate(
            candidate_id=f"fake-compact:{request.run_id}",
            episode_summary_candidate=EpisodeSummaryCandidate(
                candidate_id=f"fake-summary:{request.run_id}",
                episode_title=f"Session {request.session_id} compact summary",
                goal=request.current_message_summary.summary_text,
                completed_actions=_completed_actions(request),
                confirmed_fact_refs=request.verified_fact_refs,
                confirmed_fact_summaries=_confirmed_fact_summaries(request),
                user_constraints=_user_constraints(request),
                open_questions=("continue-current-run",),
                next_step="preserve current input and accepted tool facts",
                tool_finding_refs=request.tool_fact_refs,
                source_event_refs=request.input_event_refs,
                evidence_refs=evidence_refs,
            ),
            pinned_state_patch_candidate=PinnedStatePatchCandidate(
                candidate_id=f"fake-pinned-patch:{request.run_id}",
                current_goal=PinnedTextFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=request.current_message_summary.summary_text,
                    evidence_refs=evidence_refs,
                ),
                confirmed_subjects=PinnedStringTupleFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=_confirmed_subjects(request),
                    evidence_refs=evidence_refs,
                ),
                user_constraints=PinnedStringTupleFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=_user_constraints(request),
                    evidence_refs=evidence_refs,
                ),
                open_questions=PinnedStringTupleFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=("continue-current-run",),
                    evidence_refs=evidence_refs,
                ),
            ),
            preservation_evidence=evidence,
            retained_current_user_input_ref=(
                request.current_message_summary.current_user_input_ref
            ),
            preserved_input_event_refs=request.input_event_refs,
            preserved_tool_fact_refs=request.tool_fact_refs,
            preserved_verified_fact_refs=request.verified_fact_refs,
            dropped_ranges=(),
            summarized_ranges=summarized_ranges,
            budget_after_compact=max(
                0, request.budget_before_compact.estimated_input_tokens // 2
            ),
        )


def _preservation_evidence(
    request: CompactionRequest,
) -> tuple[PreservationEvidence, ...]:
    """构造 deterministic preservation evidence。

    :param request: compaction 请求。
    :returns: preservation evidence tuple。
    """

    return (
        PreservationEvidence(
            evidence_id=f"fake-evidence:{request.run_id}:primary",
            input_event_refs=request.input_event_refs,
            tool_fact_refs=request.tool_fact_refs,
            memory_snapshot_cursor=request.memory_snapshot_cursor,
            compact_input_range=_range_for_request(request),
        ),
    )


def _range_for_request(request: CompactionRequest) -> CompactInputRange | None:
    """根据请求构造输入范围。

    :param request: compaction 请求。
    :returns: 输入范围；输入为空时为 ``None``。
    """

    if len(request.input_event_refs) == 0:
        return None
    return CompactInputRange(
        range_ref=f"fake-range:{request.run_id}:all-inputs",
        start_input_ref=request.input_event_refs[0],
        end_input_ref=request.input_event_refs[-1],
    )


def _summarized_ranges(request: CompactionRequest) -> tuple[CompactInputRange, ...]:
    """构造被摘要输入范围。

    :param request: compaction 请求。
    :returns: summarized ranges。
    """

    if len(request.older_raw_turn_refs) == 0:
        return ()
    return (
        CompactInputRange(
            range_ref=f"fake-range:{request.run_id}:older-raw-turns",
            start_input_ref=request.older_raw_turn_refs[0],
            end_input_ref=request.older_raw_turn_refs[-1],
        ),
    )


def _completed_actions(request: CompactionRequest) -> tuple[str, ...]:
    """构造 completed actions 摘要。

    :param request: compaction 请求。
    :returns: completed actions。
    """

    if len(request.older_raw_turn_refs) == 0:
        return ("preserved current turn",)
    return (f"summarized {len(request.older_raw_turn_refs)} older raw turns",)


def _confirmed_fact_summaries(request: CompactionRequest) -> tuple[str, ...]:
    """构造 confirmed fact summaries。

    :param request: compaction 请求。
    :returns: confirmed fact summaries。
    """

    if len(request.verified_fact_refs) == 0:
        return ("no verified facts in input",)
    return tuple(f"verified:{fact_ref}" for fact_ref in request.verified_fact_refs)


def _confirmed_subjects(request: CompactionRequest) -> tuple[str, ...]:
    """构造 pinned confirmed subjects。

    :param request: compaction 请求。
    :returns: confirmed subjects。
    """

    if len(request.verified_fact_refs) > 0:
        return tuple(f"subject:{fact_ref}" for fact_ref in request.verified_fact_refs)
    return (f"subject:{request.current_message_summary.current_user_input_ref}",)


def _user_constraints(request: CompactionRequest) -> tuple[str, ...]:
    """构造用户约束摘要。

    :param request: compaction 请求。
    :returns: 用户约束摘要。
    """

    return (f"keep-current-input:{request.current_message_summary.current_user_input_ref}",)


__all__ = ["FakeContextCompactor"]
