"""Host context compaction typed contracts。

本模块定义 Phase 10 Context Governance 使用的 compactor 输入、候选输出、
preservation evidence 与 quality check 结果。它只表达 Host-owned typed
boundary，不调用 LLM、不写 EventLog、不更新 memory projection。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from dayu.contracts.json_value import JsonValue
from dayu.host._public_validation import (
    require_non_empty as _require_non_empty,
)
from dayu.host._public_validation import (
    require_non_negative_int as _require_non_negative_int,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.codec import sha256_digest_json


class PinnedPatchOperation(StrEnum):
    """Pinned state 字段 patch 操作。"""

    MISSING = "missing"
    CLEAR = "clear"
    REPLACE = "replace"


class CompactQualityIssue(StrEnum):
    """Compact quality check 拒绝原因。"""

    CURRENT_USER_INPUT_MISSING = "current_user_input_missing"
    TOOL_FACT_REFS_MISSING = "tool_fact_refs_missing"
    SUMMARY_PRETENDS_VERIFIED_FACT = "summary_pretends_verified_fact"
    PRESERVATION_EVIDENCE_MISSING = "preservation_evidence_missing"
    EVIDENCE_ANCHOR_NOT_RETAINED = "evidence_anchor_not_retained"
    PINNED_PATCH_TRI_STATE_INVALID = "pinned_patch_tri_state_invalid"
    PINNED_PATCH_EVIDENCE_REF_MISSING = "pinned_patch_evidence_ref_missing"


def _empty_string_tuple() -> tuple[str, ...]:
    """返回空字符串 tuple。

    :returns: 空 tuple。
    """

    return ()


@dataclass(frozen=True, slots=True)
class CurrentMessageSummary:
    """当前用户输入摘要。

    :param current_user_input_ref: 当前 ``USER_INPUT_ACCEPTED`` event ref。
    :param summary_text: 当前用户输入的短摘要。
    :param source_event_refs: 摘要覆盖的输入 event refs。
    """

    current_user_input_ref: str
    summary_text: str
    source_event_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验当前消息摘要字段。

        :returns: ``None``。
        :raises TypeError: tuple 字段类型非法时抛出。
        :raises ValueError: 文本字段为空时抛出。
        """

        _require_non_empty(
            self.current_user_input_ref,
            field_name="CurrentMessageSummary.current_user_input_ref",
        )
        _require_non_empty(
            self.summary_text, field_name="CurrentMessageSummary.summary_text"
        )
        _require_string_tuple(
            self.source_event_refs,
            field_name="CurrentMessageSummary.source_event_refs",
        )
        if self.current_user_input_ref not in self.source_event_refs:
            raise ValueError(
                "CurrentMessageSummary.source_event_refs must include current user input"
            )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "current_user_input_ref": self.current_user_input_ref,
            "summary_text": self.summary_text,
            "source_event_refs": _string_list_json(self.source_event_refs),
        }


@dataclass(frozen=True, slots=True)
class CompactInputRange:
    """Compact 输入范围引用。

    :param range_ref: 输入范围引用。
    :param start_input_ref: 范围起点输入 ref。
    :param end_input_ref: 范围终点输入 ref。
    """

    range_ref: str
    start_input_ref: str
    end_input_ref: str

    def __post_init__(self) -> None:
        """校验输入范围字段。

        :returns: ``None``。
        :raises ValueError: 文本字段为空时抛出。
        """

        _require_non_empty(self.range_ref, field_name="CompactInputRange.range_ref")
        _require_non_empty(
            self.start_input_ref, field_name="CompactInputRange.start_input_ref"
        )
        _require_non_empty(
            self.end_input_ref, field_name="CompactInputRange.end_input_ref"
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "range_ref": self.range_ref,
            "start_input_ref": self.start_input_ref,
            "end_input_ref": self.end_input_ref,
        }


@dataclass(frozen=True, slots=True)
class CompactionRequest:
    """Context compaction 请求。

    :param trigger_source: compact 触发来源。
    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: reactive compact 对应 Attempt id；proactive 时为 ``None``。
    :param execution_id: reactive compact 对应 execution id；proactive 时为 ``None``。
    :param input_event_refs: compact 输入 event refs。
    :param memory_snapshot_cursor: memory snapshot cursor；无 snapshot 时为 ``None``。
    :param current_message_summary: 当前用户输入摘要。
    :param tool_fact_refs: accepted tool fact refs。
    :param verified_fact_refs: 已验证事实 refs。
    :param recent_raw_turn_refs: 必须保留的近期 raw turn refs。
    :param older_raw_turn_refs: 可摘要的较旧 raw turn refs。
    :param existing_episode_summary_refs: 已存在 episode summary refs。
    :param budget_before_compact: compact 前预算估算。
    """

    trigger_source: ContextCompactionTriggerSource
    session_id: str
    run_id: str
    attempt_id: str | None
    execution_id: str | None
    input_event_refs: tuple[str, ...]
    memory_snapshot_cursor: int | None
    current_message_summary: CurrentMessageSummary
    tool_fact_refs: tuple[str, ...]
    verified_fact_refs: tuple[str, ...]
    recent_raw_turn_refs: tuple[str, ...]
    older_raw_turn_refs: tuple[str, ...]
    existing_episode_summary_refs: tuple[str, ...]
    budget_before_compact: BudgetEstimate

    def __post_init__(self) -> None:
        """校验 compaction 请求。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        if not isinstance(self.trigger_source, ContextCompactionTriggerSource):
            raise TypeError("CompactionRequest.trigger_source is invalid")
        _require_non_empty(self.session_id, field_name="CompactionRequest.session_id")
        _require_non_empty(self.run_id, field_name="CompactionRequest.run_id")
        _require_optional_non_empty(
            self.attempt_id, field_name="CompactionRequest.attempt_id"
        )
        _require_optional_non_empty(
            self.execution_id, field_name="CompactionRequest.execution_id"
        )
        if self.trigger_source is ContextCompactionTriggerSource.REACTIVE:
            if self.attempt_id is None:
                raise ValueError(
                    "CompactionRequest.attempt_id is required for reactive compaction"
                )
            if self.execution_id is None:
                raise ValueError(
                    "CompactionRequest.execution_id is required for reactive compaction"
                )
        _require_string_tuple(
            self.input_event_refs, field_name="CompactionRequest.input_event_refs"
        )
        if not isinstance(self.current_message_summary, CurrentMessageSummary):
            raise TypeError(
                "CompactionRequest.current_message_summary must be CurrentMessageSummary"
            )
        if (
            self.current_message_summary.current_user_input_ref
            not in self.input_event_refs
        ):
            raise ValueError(
                "CompactionRequest.input_event_refs must include current input"
            )
        if self.memory_snapshot_cursor is not None:
            _require_non_negative_int(
                self.memory_snapshot_cursor,
                field_name="CompactionRequest.memory_snapshot_cursor",
            )
        _require_string_tuple(
            self.tool_fact_refs, field_name="CompactionRequest.tool_fact_refs"
        )
        _require_string_tuple(
            self.verified_fact_refs, field_name="CompactionRequest.verified_fact_refs"
        )
        _require_string_tuple(
            self.recent_raw_turn_refs,
            field_name="CompactionRequest.recent_raw_turn_refs",
        )
        _require_string_tuple(
            self.older_raw_turn_refs,
            field_name="CompactionRequest.older_raw_turn_refs",
        )
        _require_string_tuple(
            self.existing_episode_summary_refs,
            field_name="CompactionRequest.existing_episode_summary_refs",
        )
        if not isinstance(self.budget_before_compact, BudgetEstimate):
            raise TypeError(
                "CompactionRequest.budget_before_compact must be BudgetEstimate"
            )

    def digest(self) -> str:
        """计算 compaction request digest。

        :returns: 请求 canonical JSON 的 sha256 digest。
        """

        return sha256_digest_json(self.to_json())

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "trigger_source": self.trigger_source.value,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "execution_id": self.execution_id,
            "input_event_refs": _string_list_json(self.input_event_refs),
            "memory_snapshot_cursor": self.memory_snapshot_cursor,
            "current_message_summary": self.current_message_summary.to_json(),
            "tool_fact_refs": _string_list_json(self.tool_fact_refs),
            "verified_fact_refs": _string_list_json(self.verified_fact_refs),
            "recent_raw_turn_refs": _string_list_json(self.recent_raw_turn_refs),
            "older_raw_turn_refs": _string_list_json(self.older_raw_turn_refs),
            "existing_episode_summary_refs": _string_list_json(
                self.existing_episode_summary_refs
            ),
            "budget_before_compact": _budget_estimate_json(
                self.budget_before_compact
            ),
        }


@dataclass(frozen=True, slots=True)
class EpisodeSummaryCandidate:
    """Episode summary 候选。

    :param candidate_id: summary candidate id。
    :param episode_title: episode 标题。
    :param goal: 用户目标摘要。
    :param completed_actions: 已完成动作摘要。
    :param confirmed_fact_refs: 输入中已有 confirmed / verified fact refs。
    :param confirmed_fact_summaries: confirmed facts 的可读摘要。
    :param user_constraints: 用户约束摘要。
    :param open_questions: 未决问题。
    :param next_step: 下一步摘要；无时为 ``None``。
    :param tool_finding_refs: 工具发现 refs。
    :param source_event_refs: summary 覆盖的输入 event refs。
    :param evidence_refs: preservation evidence refs。
    :param proposed_verified_fact_refs: compactor 试图新建的 verified fact refs；正常应为空。
    """

    candidate_id: str
    episode_title: str
    goal: str
    completed_actions: tuple[str, ...]
    confirmed_fact_refs: tuple[str, ...]
    confirmed_fact_summaries: tuple[str, ...]
    user_constraints: tuple[str, ...]
    open_questions: tuple[str, ...]
    next_step: str | None
    tool_finding_refs: tuple[str, ...]
    source_event_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    proposed_verified_fact_refs: tuple[str, ...] = field(
        default_factory=_empty_string_tuple
    )

    def __post_init__(self) -> None:
        """校验 episode summary 候选。

        :returns: ``None``。
        :raises TypeError: tuple 字段类型非法时抛出。
        :raises ValueError: 文本字段为空时抛出。
        """

        _require_non_empty(
            self.candidate_id, field_name="EpisodeSummaryCandidate.candidate_id"
        )
        _require_non_empty(
            self.episode_title,
            field_name="EpisodeSummaryCandidate.episode_title",
        )
        _require_non_empty(self.goal, field_name="EpisodeSummaryCandidate.goal")
        _require_string_tuple(
            self.completed_actions,
            field_name="EpisodeSummaryCandidate.completed_actions",
        )
        _require_string_tuple(
            self.confirmed_fact_refs,
            field_name="EpisodeSummaryCandidate.confirmed_fact_refs",
        )
        _require_string_tuple(
            self.confirmed_fact_summaries,
            field_name="EpisodeSummaryCandidate.confirmed_fact_summaries",
        )
        _require_string_tuple(
            self.user_constraints,
            field_name="EpisodeSummaryCandidate.user_constraints",
        )
        _require_string_tuple(
            self.open_questions,
            field_name="EpisodeSummaryCandidate.open_questions",
        )
        _require_optional_non_empty(
            self.next_step, field_name="EpisodeSummaryCandidate.next_step"
        )
        _require_string_tuple(
            self.tool_finding_refs,
            field_name="EpisodeSummaryCandidate.tool_finding_refs",
        )
        _require_string_tuple(
            self.source_event_refs,
            field_name="EpisodeSummaryCandidate.source_event_refs",
        )
        _require_string_tuple(
            self.evidence_refs,
            field_name="EpisodeSummaryCandidate.evidence_refs",
        )
        _require_string_tuple(
            self.proposed_verified_fact_refs,
            field_name="EpisodeSummaryCandidate.proposed_verified_fact_refs",
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "candidate_id": self.candidate_id,
            "episode_title": self.episode_title,
            "goal": self.goal,
            "completed_actions": _string_list_json(self.completed_actions),
            "confirmed_fact_refs": _string_list_json(self.confirmed_fact_refs),
            "confirmed_fact_summaries": _string_list_json(
                self.confirmed_fact_summaries
            ),
            "user_constraints": _string_list_json(self.user_constraints),
            "open_questions": _string_list_json(self.open_questions),
            "next_step": self.next_step,
            "tool_finding_refs": _string_list_json(self.tool_finding_refs),
            "source_event_refs": _string_list_json(self.source_event_refs),
            "evidence_refs": _string_list_json(self.evidence_refs),
            "proposed_verified_fact_refs": _string_list_json(
                self.proposed_verified_fact_refs
            ),
        }


@dataclass(frozen=True, slots=True)
class PinnedTextFieldPatch:
    """Pinned state 文本字段三态 patch。

    :param operation: missing / clear / replace 操作。
    :param value: replace 时的新值；其它操作为 ``None``。
    :param evidence_refs: clear / replace 操作引用的 preservation evidence refs。
    """

    operation: PinnedPatchOperation
    value: str | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=_empty_string_tuple)

    def __post_init__(self) -> None:
        """校验文本 patch 基础类型。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: evidence ref 为空时抛出。
        """

        if not isinstance(self.operation, PinnedPatchOperation):
            raise TypeError("PinnedTextFieldPatch.operation is invalid")
        if self.value is not None:
            _require_non_empty(self.value, field_name="PinnedTextFieldPatch.value")
        _require_string_tuple(
            self.evidence_refs, field_name="PinnedTextFieldPatch.evidence_refs"
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "operation": self.operation.value,
            "value": self.value,
            "evidence_refs": _string_list_json(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class PinnedStringTupleFieldPatch:
    """Pinned state 字符串 tuple 字段三态 patch。

    :param operation: missing / clear / replace 操作。
    :param value: replace 时的新 tuple；其它操作为 ``None``。
    :param evidence_refs: clear / replace 操作引用的 preservation evidence refs。
    """

    operation: PinnedPatchOperation
    value: tuple[str, ...] | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=_empty_string_tuple)

    def __post_init__(self) -> None:
        """校验 tuple patch 基础类型。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: evidence ref 为空时抛出。
        """

        if not isinstance(self.operation, PinnedPatchOperation):
            raise TypeError("PinnedStringTupleFieldPatch.operation is invalid")
        if self.value is not None:
            _require_string_tuple(
                self.value, field_name="PinnedStringTupleFieldPatch.value"
            )
        _require_string_tuple(
            self.evidence_refs,
            field_name="PinnedStringTupleFieldPatch.evidence_refs",
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "operation": self.operation.value,
            "value": (
                None if self.value is None else _string_list_json(self.value)
            ),
            "evidence_refs": _string_list_json(self.evidence_refs),
        }


def missing_text_patch() -> PinnedTextFieldPatch:
    """构造文本字段 missing patch。

    :returns: missing patch。
    """

    return PinnedTextFieldPatch(operation=PinnedPatchOperation.MISSING)


def missing_string_tuple_patch() -> PinnedStringTupleFieldPatch:
    """构造字符串 tuple 字段 missing patch。

    :returns: missing patch。
    """

    return PinnedStringTupleFieldPatch(operation=PinnedPatchOperation.MISSING)


@dataclass(frozen=True, slots=True)
class PinnedStatePatchCandidate:
    """Pinned state 字段级三态 patch 候选。

    :param candidate_id: patch candidate id。
    :param current_goal: current goal patch。
    :param confirmed_subjects: confirmed subjects patch。
    :param user_constraints: user constraints patch。
    :param open_questions: open questions patch。
    """

    candidate_id: str
    current_goal: PinnedTextFieldPatch = field(default_factory=missing_text_patch)
    confirmed_subjects: PinnedStringTupleFieldPatch = field(
        default_factory=missing_string_tuple_patch
    )
    user_constraints: PinnedStringTupleFieldPatch = field(
        default_factory=missing_string_tuple_patch
    )
    open_questions: PinnedStringTupleFieldPatch = field(
        default_factory=missing_string_tuple_patch
    )

    def __post_init__(self) -> None:
        """校验 pinned state patch 候选基础类型。

        :returns: ``None``。
        :raises TypeError: patch 字段类型非法时抛出。
        :raises ValueError: candidate id 为空时抛出。
        """

        _require_non_empty(
            self.candidate_id, field_name="PinnedStatePatchCandidate.candidate_id"
        )
        if not isinstance(self.current_goal, PinnedTextFieldPatch):
            raise TypeError(
                "PinnedStatePatchCandidate.current_goal must be PinnedTextFieldPatch"
            )
        _require_tuple_patch_field(
            self.confirmed_subjects,
            field_name="PinnedStatePatchCandidate.confirmed_subjects",
        )
        _require_tuple_patch_field(
            self.user_constraints,
            field_name="PinnedStatePatchCandidate.user_constraints",
        )
        _require_tuple_patch_field(
            self.open_questions,
            field_name="PinnedStatePatchCandidate.open_questions",
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "candidate_id": self.candidate_id,
            "current_goal": self.current_goal.to_json(),
            "confirmed_subjects": self.confirmed_subjects.to_json(),
            "user_constraints": self.user_constraints.to_json(),
            "open_questions": self.open_questions.to_json(),
        }


@dataclass(frozen=True, slots=True)
class PreservationEvidence:
    """Compact preservation evidence。

    :param evidence_id: evidence id。
    :param input_event_refs: evidence 覆盖的输入 event refs。
    :param tool_fact_refs: evidence 覆盖的 tool fact refs。
    :param memory_snapshot_cursor: evidence 对应 memory cursor；无时为 ``None``。
    :param compact_input_range: evidence 对应 compact 输入范围；无时为 ``None``。
    """

    evidence_id: str
    input_event_refs: tuple[str, ...]
    tool_fact_refs: tuple[str, ...]
    memory_snapshot_cursor: int | None
    compact_input_range: CompactInputRange | None

    def __post_init__(self) -> None:
        """校验 preservation evidence。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty(
            self.evidence_id, field_name="PreservationEvidence.evidence_id"
        )
        _require_string_tuple(
            self.input_event_refs, field_name="PreservationEvidence.input_event_refs"
        )
        _require_string_tuple(
            self.tool_fact_refs, field_name="PreservationEvidence.tool_fact_refs"
        )
        if self.memory_snapshot_cursor is not None:
            _require_non_negative_int(
                self.memory_snapshot_cursor,
                field_name="PreservationEvidence.memory_snapshot_cursor",
            )
        if self.compact_input_range is not None and not isinstance(
            self.compact_input_range, CompactInputRange
        ):
            raise TypeError(
                "PreservationEvidence.compact_input_range must be CompactInputRange"
            )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "evidence_id": self.evidence_id,
            "input_event_refs": _string_list_json(self.input_event_refs),
            "tool_fact_refs": _string_list_json(self.tool_fact_refs),
            "memory_snapshot_cursor": self.memory_snapshot_cursor,
            "compact_input_range": (
                None
                if self.compact_input_range is None
                else self.compact_input_range.to_json()
            ),
        }


@dataclass(frozen=True, slots=True)
class CompactionCandidate:
    """Compactor 输出候选。

    :param candidate_id: compact candidate id。
    :param episode_summary_candidate: episode summary 候选。
    :param pinned_state_patch_candidate: pinned state patch 候选。
    :param preservation_evidence: preservation evidence 集合。
    :param retained_current_user_input_ref: 被保留的当前用户输入 ref。
    :param preserved_input_event_refs: 被保留的输入 event refs。
    :param preserved_tool_fact_refs: 被保留的 accepted tool fact refs。
    :param preserved_verified_fact_refs: 被保留的 verified fact refs。
    :param dropped_ranges: 被丢弃的输入范围。
    :param summarized_ranges: 被摘要的输入范围。
    :param budget_after_compact: compact 后预算 token 估算。
    """

    candidate_id: str
    episode_summary_candidate: EpisodeSummaryCandidate
    pinned_state_patch_candidate: PinnedStatePatchCandidate
    preservation_evidence: tuple[PreservationEvidence, ...]
    retained_current_user_input_ref: str | None
    preserved_input_event_refs: tuple[str, ...]
    preserved_tool_fact_refs: tuple[str, ...]
    preserved_verified_fact_refs: tuple[str, ...]
    dropped_ranges: tuple[CompactInputRange, ...]
    summarized_ranges: tuple[CompactInputRange, ...]
    budget_after_compact: int

    def __post_init__(self) -> None:
        """校验 compaction candidate 基础类型。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty(
            self.candidate_id, field_name="CompactionCandidate.candidate_id"
        )
        if not isinstance(self.episode_summary_candidate, EpisodeSummaryCandidate):
            raise TypeError(
                "CompactionCandidate.episode_summary_candidate must be "
                "EpisodeSummaryCandidate"
            )
        if not isinstance(self.pinned_state_patch_candidate, PinnedStatePatchCandidate):
            raise TypeError(
                "CompactionCandidate.pinned_state_patch_candidate must be "
                "PinnedStatePatchCandidate"
            )
        _require_evidence_tuple(
            self.preservation_evidence,
            field_name="CompactionCandidate.preservation_evidence",
        )
        _require_optional_non_empty(
            self.retained_current_user_input_ref,
            field_name="CompactionCandidate.retained_current_user_input_ref",
        )
        _require_string_tuple(
            self.preserved_input_event_refs,
            field_name="CompactionCandidate.preserved_input_event_refs",
        )
        _require_string_tuple(
            self.preserved_tool_fact_refs,
            field_name="CompactionCandidate.preserved_tool_fact_refs",
        )
        _require_string_tuple(
            self.preserved_verified_fact_refs,
            field_name="CompactionCandidate.preserved_verified_fact_refs",
        )
        _require_range_tuple(
            self.dropped_ranges, field_name="CompactionCandidate.dropped_ranges"
        )
        _require_range_tuple(
            self.summarized_ranges, field_name="CompactionCandidate.summarized_ranges"
        )
        _require_non_negative_int(
            self.budget_after_compact,
            field_name="CompactionCandidate.budget_after_compact",
        )

    def digest(self) -> str:
        """计算 candidate digest。

        :returns: candidate canonical JSON 的 sha256 digest。
        """

        return sha256_digest_json(self.to_json())

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "candidate_id": self.candidate_id,
            "episode_summary_candidate": self.episode_summary_candidate.to_json(),
            "pinned_state_patch_candidate": (
                self.pinned_state_patch_candidate.to_json()
            ),
            "preservation_evidence": _evidence_list_json(
                self.preservation_evidence
            ),
            "retained_current_user_input_ref": self.retained_current_user_input_ref,
            "preserved_input_event_refs": _string_list_json(
                self.preserved_input_event_refs
            ),
            "preserved_tool_fact_refs": _string_list_json(
                self.preserved_tool_fact_refs
            ),
            "preserved_verified_fact_refs": _string_list_json(
                self.preserved_verified_fact_refs
            ),
            "dropped_ranges": _range_list_json(self.dropped_ranges),
            "summarized_ranges": _range_list_json(self.summarized_ranges),
            "budget_after_compact": self.budget_after_compact,
        }


@dataclass(frozen=True, slots=True)
class CompactQualityCheckResult:
    """Compact quality check 结果。

    :param accepted: 候选是否通过 quality check。
    :param rejection_reasons: 拒绝原因集合。
    :param current_user_input_retained: 当前用户输入是否保留。
    :param accepted_tool_fact_refs_retained: accepted tool fact refs 是否全部保留。
    :param evidence_anchors_retained: evidence anchors 是否保留。
    :param open_questions_retained: open questions / assumptions 是否保留。
    :param retained_evidence_refs: 被接受的 evidence refs。
    :param dropped_ranges: 被丢弃的输入范围。
    :param summarized_ranges: 被摘要的输入范围。
    """

    accepted: bool
    rejection_reasons: tuple[CompactQualityIssue, ...]
    current_user_input_retained: bool
    accepted_tool_fact_refs_retained: bool
    evidence_anchors_retained: bool
    open_questions_retained: bool
    retained_evidence_refs: tuple[str, ...]
    dropped_ranges: tuple[CompactInputRange, ...]
    summarized_ranges: tuple[CompactInputRange, ...]

    def __post_init__(self) -> None:
        """校验 quality check 结果字段。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        if not isinstance(self.accepted, bool):
            raise TypeError("CompactQualityCheckResult.accepted must be bool")
        _require_quality_issue_tuple(
            self.rejection_reasons,
            field_name="CompactQualityCheckResult.rejection_reasons",
        )
        _require_bool(
            self.current_user_input_retained,
            field_name="CompactQualityCheckResult.current_user_input_retained",
        )
        _require_bool(
            self.accepted_tool_fact_refs_retained,
            field_name="CompactQualityCheckResult.accepted_tool_fact_refs_retained",
        )
        _require_bool(
            self.evidence_anchors_retained,
            field_name="CompactQualityCheckResult.evidence_anchors_retained",
        )
        _require_bool(
            self.open_questions_retained,
            field_name="CompactQualityCheckResult.open_questions_retained",
        )
        _require_string_tuple(
            self.retained_evidence_refs,
            field_name="CompactQualityCheckResult.retained_evidence_refs",
        )
        _require_range_tuple(
            self.dropped_ranges,
            field_name="CompactQualityCheckResult.dropped_ranges",
        )
        _require_range_tuple(
            self.summarized_ranges,
            field_name="CompactQualityCheckResult.summarized_ranges",
        )
        if self.accepted and len(self.rejection_reasons) > 0:
            raise ValueError(
                "Accepted quality result must not include rejection reasons"
            )
        if not self.accepted and len(self.rejection_reasons) == 0:
            raise ValueError("Rejected quality result must include rejection reasons")

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "accepted": self.accepted,
            "rejection_reasons": [
                _enum_value for _enum_value in self._rejection_reason_values()
            ],
            "current_user_input_retained": self.current_user_input_retained,
            "accepted_tool_fact_refs_retained": (
                self.accepted_tool_fact_refs_retained
            ),
            "evidence_anchors_retained": self.evidence_anchors_retained,
            "open_questions_retained": self.open_questions_retained,
            "retained_evidence_refs": _string_list_json(self.retained_evidence_refs),
            "dropped_ranges": _range_list_json(self.dropped_ranges),
            "summarized_ranges": _range_list_json(self.summarized_ranges),
        }

    def _rejection_reason_values(self) -> list[JsonValue]:
        """返回拒绝原因字符串列表。

        :returns: JSON 字符串列表。
        """

        values: list[JsonValue] = []
        for reason in self.rejection_reasons:
            values.append(reason.value)
        return values


class ContextCompactor(Protocol):
    """Context compactor typed port。

    真实实现可以是 LLM scene adapter；Host 只能接受 typed candidate，并且
    必须由 quality checker 通过后才可写 compact artifact / canonical event。
    """

    def compact(self, request: CompactionRequest) -> CompactionCandidate:
        """生成 compaction candidate。

        :param request: Host 构造的 compaction 请求。
        :returns: compaction candidate。
        :raises RuntimeError: compactor 后端失败时可抛出运行时错误。
        """

        ...


def _require_optional_non_empty(value: str | None, *, field_name: str) -> None:
    """校验可选非空字符串。

    :param value: 待校验值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises ValueError: 字符串存在但为空时抛出。
    """

    if value is not None:
        _require_non_empty(value, field_name=field_name)


def _require_string_tuple(value: tuple[str, ...], *, field_name: str) -> None:
    """校验字符串 tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 元素为空时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} items must be str")
        _require_non_empty(item, field_name=field_name)


def _require_tuple_patch_field(
    value: PinnedStringTupleFieldPatch, *, field_name: str
) -> None:
    """校验字符串 tuple patch 字段。

    :param value: 待校验 patch。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: patch 字段类型非法时抛出。
    """

    if not isinstance(value, PinnedStringTupleFieldPatch):
        raise TypeError(f"{field_name} must be PinnedStringTupleFieldPatch")


def _require_evidence_tuple(
    value: tuple[PreservationEvidence, ...], *, field_name: str
) -> None:
    """校验 preservation evidence tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, PreservationEvidence):
            raise TypeError(f"{field_name} items must be PreservationEvidence")


def _require_range_tuple(
    value: tuple[CompactInputRange, ...], *, field_name: str
) -> None:
    """校验 compact input range tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, CompactInputRange):
            raise TypeError(f"{field_name} items must be CompactInputRange")


def _require_quality_issue_tuple(
    value: tuple[CompactQualityIssue, ...], *, field_name: str
) -> None:
    """校验 quality issue tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, CompactQualityIssue):
            raise TypeError(f"{field_name} items must be CompactQualityIssue")


def _require_bool(value: bool, *, field_name: str) -> None:
    """校验 bool 字段。

    :param value: 待校验值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段不是 bool 时抛出。
    """

    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool")


def _string_list_json(values: tuple[str, ...]) -> list[JsonValue]:
    """把字符串 tuple 转换为 JSON 数组。

    :param values: 字符串 tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value)
    return result


def _range_list_json(values: tuple[CompactInputRange, ...]) -> list[JsonValue]:
    """把 compact range tuple 转换为 JSON 数组。

    :param values: range tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _evidence_list_json(values: tuple[PreservationEvidence, ...]) -> list[JsonValue]:
    """把 preservation evidence tuple 转换为 JSON 数组。

    :param values: evidence tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _budget_estimate_json(estimate: BudgetEstimate) -> JsonValue:
    """把 budget estimate 转换为 JSON object。

    :param estimate: budget estimate。
    :returns: JSON object。
    """

    return {
        "estimated_input_tokens": estimate.estimated_input_tokens,
        "input_budget_tokens": estimate.input_budget_tokens,
        "soft_threshold_tokens": estimate.soft_threshold_tokens,
        "hard_threshold_tokens": estimate.hard_threshold_tokens,
        "safety_margin_tokens": estimate.safety_margin_tokens,
        "estimator_digest": estimate.estimator_digest,
        "overage_reason": (
            None if estimate.overage_reason is None else estimate.overage_reason.value
        ),
    }


__all__ = [
    "CompactInputRange",
    "CompactQualityCheckResult",
    "CompactQualityIssue",
    "CompactionCandidate",
    "CompactionRequest",
    "ContextCompactor",
    "CurrentMessageSummary",
    "EpisodeSummaryCandidate",
    "PinnedPatchOperation",
    "PinnedStatePatchCandidate",
    "PinnedStringTupleFieldPatch",
    "PinnedTextFieldPatch",
    "PreservationEvidence",
    "missing_string_tuple_patch",
    "missing_text_patch",
]
