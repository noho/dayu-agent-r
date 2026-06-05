"""Host 内部 deterministic recent-window fallback helper。

本模块只服务 Host Context Governance 内部 fallback：从 ordinary material
blocks 中确定性选择有界 recent window，使用既有 conservative estimator
重估预算，并为 ``CONTEXT_COMPACTION_FAILED`` 构造结构化诊断。它不定义
public policy 字段，不写 compact artifact，不物化 memory projection。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.host.compact_material import RunInputMaterialBlock
from dayu.host.compaction import CompactMaterialBlockKind, CompactMaterialSection
from dayu.host.context_budget import (
    BudgetEstimate,
    BudgetEstimateInput,
    BudgetTextFragment,
    ContextBudgetDecision,
    decide_context_budget,
    estimate_context_budget,
)
from dayu.host.context_events import CONTEXT_COMPACTION_FAILED
from dayu.host.context_policy import ContextBudgetPolicy, ContextCompactionTriggerSource
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.event_log import EventLogStore
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.payload_resolution import event_payload_object

FALLBACK_ACTION_DISPATCH = "dispatch"
FALLBACK_ACTION_FAIL_CLOSED = "fail_closed"
FALLBACK_ACTION_NOT_APPLICABLE = "not_applicable"
FALLBACK_POLICY_DECISION_RECENT_WINDOW = "deterministic_recent_window"
FALLBACK_POLICY_DECISION_SELECTION_FAILED = "deterministic_recent_window_selection_failed"
FALLBACK_BUDGET_STATUS_WITHIN_BUDGET = "within_hard_budget"
FALLBACK_BUDGET_STATUS_OVER_BUDGET = "over_hard_budget"
FALLBACK_BUDGET_STATUS_SELECTION_FAILED = "selection_failed"
_NO_EVENT_SEQUENCE = -1
_FIELD_FALLBACK_ACTION = "fallback_action"
_FIELD_FALLBACK_INPUT_WINDOW = "fallback_input_window"
_FIELD_FALLBACK_INPUT_DIGEST = "fallback_input_digest"
_FIELD_SELECTED_BLOCK_IDS = "selected_block_ids"
_FIELD_CURRENT_INPUT_REF = "current_input_ref"
_FIELD_SELECTED_RECENT_WINDOW_TURN_FLOOR = "selected_recent_window_turn_floor"


class RecentWindowFallbackAction(StrEnum):
    """recent-window fallback 的内部动作。"""

    DISPATCH = FALLBACK_ACTION_DISPATCH
    FAIL_CLOSED = FALLBACK_ACTION_FAIL_CLOSED


@dataclass(frozen=True, slots=True)
class RecentWindowFallbackBudgetResult:
    """recent-window fallback 的预算重估结果。

    :param status: 预算状态。
    :param decision: 既有 context budget decision。
    :param estimate: 既有 conservative estimator 输出。
    :param policy_ref: context budget policy ref。
    """

    status: str
    decision: ContextBudgetDecision
    estimate: BudgetEstimate
    policy_ref: str

    def __post_init__(self) -> None:
        """校验预算结果字段。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 文本字段为空时抛出。
        """

        if self.status.strip() == "":
            raise ValueError("RecentWindowFallbackBudgetResult.status must be non-empty")
        if not isinstance(self.decision, ContextBudgetDecision):
            raise TypeError("RecentWindowFallbackBudgetResult.decision is invalid")
        if not isinstance(self.estimate, BudgetEstimate):
            raise TypeError("RecentWindowFallbackBudgetResult.estimate is invalid")
        if self.policy_ref.strip() == "":
            raise ValueError("RecentWindowFallbackBudgetResult.policy_ref must be non-empty")

    @property
    def hard_budget_passed(self) -> bool:
        """返回 fallback view 是否低于 hard threshold。

        :returns: 未触发 hard threshold 时返回 ``True``。
        """

        return self.decision is not ContextBudgetDecision.BLOCK_HARD_THRESHOLD

    def to_payload(self) -> Mapping[str, JsonValue]:
        """转换为 failed payload 中的结构化预算诊断。

        :returns: JSON object。
        """

        return {
            "status": self.status,
            "decision": self.decision.value,
            "estimated_input_tokens": self.estimate.estimated_input_tokens,
            "soft_threshold_tokens": self.estimate.soft_threshold_tokens,
            "hard_threshold_tokens": self.estimate.hard_threshold_tokens,
            "estimator_digest": self.estimate.estimator_digest,
            "policy_ref": self.policy_ref,
        }


@dataclass(frozen=True, slots=True)
class RecentWindowFallbackSelection:
    """deterministic recent-window fallback 选择结果。

    :param selected_blocks: 按原 material 顺序保留的 blocks。
    :param dropped_blocks: 未进入 fallback view 的 blocks。
    :param current_input_ref: 当前输入 canonical ref。
    :param source_refs: selected blocks 的 canonical source refs。
    :param selected_recent_window_turn_floor: selected recent window turn floor。
    :param trigger_source: compact trigger source。
    :param policy_ref: context budget policy ref。
    :param input_cursor: material input cursor。
    :param blocked_next_block_id: 因 hard budget 被拒绝的下一 block id。
    """

    selected_blocks: tuple[RunInputMaterialBlock, ...]
    dropped_blocks: tuple[RunInputMaterialBlock, ...]
    current_input_ref: str
    source_refs: tuple[str, ...]
    selected_recent_window_turn_floor: int
    trigger_source: ContextCompactionTriggerSource
    policy_ref: str
    input_cursor: int
    blocked_next_block_id: str | None = None

    def __post_init__(self) -> None:
        """校验选择结果字段。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_block_tuple(self.selected_blocks, "selected_blocks")
        _require_block_tuple(self.dropped_blocks, "dropped_blocks")
        _require_non_empty_text(self.current_input_ref, "current_input_ref")
        _require_text_tuple(self.source_refs, "source_refs")
        if self.selected_recent_window_turn_floor < 0:
            raise ValueError("selected_recent_window_turn_floor must be non-negative")
        if not isinstance(self.trigger_source, ContextCompactionTriggerSource):
            raise TypeError("trigger_source must be ContextCompactionTriggerSource")
        _require_non_empty_text(self.policy_ref, "policy_ref")
        if self.input_cursor < 0:
            raise ValueError("input_cursor must be non-negative")
        if self.blocked_next_block_id is not None:
            _require_non_empty_text(self.blocked_next_block_id, "blocked_next_block_id")

    @property
    def selected_block_ids(self) -> tuple[str, ...]:
        """返回 selected block ids。

        :returns: selected block id 元组。
        """

        return tuple(block.block_id for block in self.selected_blocks)

    @property
    def dropped_block_ids(self) -> tuple[str, ...]:
        """返回 dropped block ids。

        :returns: dropped block id 元组。
        """

        return tuple(block.block_id for block in self.dropped_blocks)

    @property
    def digest(self) -> str:
        """返回 fallback input window 的稳定 digest。

        :returns: sha256 digest。
        """

        return sha256_digest_json(self.to_window_payload())

    def to_window_payload(self) -> Mapping[str, JsonValue]:
        """转换为 failed payload 中的结构化 input window 诊断。

        :returns: JSON object，不包含 raw prompt 或 provider payload。
        """

        payload: dict[str, JsonValue] = {
            _FIELD_SELECTED_BLOCK_IDS: list(self.selected_block_ids),
            "dropped_block_ids": list(self.dropped_block_ids),
            _FIELD_CURRENT_INPUT_REF: self.current_input_ref,
            "source_refs": list(self.source_refs),
            _FIELD_SELECTED_RECENT_WINDOW_TURN_FLOOR: self.selected_recent_window_turn_floor,
            "trigger_source": self.trigger_source.value,
            "policy_ref": self.policy_ref,
            "input_cursor": self.input_cursor,
            "selected_raw_turn_count": _raw_turn_count(self.selected_blocks),
        }
        if self.blocked_next_block_id is not None:
            payload["blocked_next_block_id"] = self.blocked_next_block_id
        return payload


@dataclass(frozen=True, slots=True)
class ActiveRecentWindowFallback:
    """RunInputBuilder 可消费的 active fallback view 摘要。

    :param selected_block_ids: 应从 ordinary material blocks 中保留的 block ids。
    :param current_input_ref: fallback 绑定的当前输入 ref。
    :param fallback_input_digest: failed payload 中记录的 fallback input digest。
    """

    selected_block_ids: tuple[str, ...]
    current_input_ref: str
    fallback_input_digest: str

    def __post_init__(self) -> None:
        """校验 active fallback view。

        :returns: ``None``。
        :raises ValueError: 字段为空时抛出。
        """

        _require_text_tuple(self.selected_block_ids, "selected_block_ids")
        _require_non_empty_text(self.current_input_ref, "current_input_ref")
        _require_non_empty_text(self.fallback_input_digest, "fallback_input_digest")


class EventLogContextFallbackProvider:
    """从 EventLog failed payload 读取当前 Run active fallback view。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 provider。

        :param transaction_runner: Host transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = EventLogStore()

    def load_context_fallback(
        self,
        *,
        run_id: str,
        run_started_event_sequence: int,
        current_input_ref: str,
    ) -> ActiveRecentWindowFallback | None:
        """读取当前 Run started 之前最近的 dispatch fallback view。

        :param run_id: 当前 Run id。
        :param run_started_event_sequence: 当前 ``RUN_STARTED`` event sequence。
        :param current_input_ref: 当前用户输入 event id。
        :returns: active fallback view；不存在时返回 ``None``。
        """

        return self._transaction_runner.run_read(
            lambda transaction: self._load_context_fallback_tx(
                transaction,
                run_id=run_id,
                run_started_event_sequence=run_started_event_sequence,
                current_input_ref=current_input_ref,
            )
        )

    def _load_context_fallback_tx(
        self,
        transaction: HostTransaction,
        *,
        run_id: str,
        run_started_event_sequence: int,
        current_input_ref: str,
    ) -> ActiveRecentWindowFallback | None:
        """在 read transaction 内读取 active fallback view。

        :param transaction: Host transaction。
        :param run_id: 当前 Run id。
        :param run_started_event_sequence: 当前 ``RUN_STARTED`` event sequence。
        :param current_input_ref: 当前用户输入 event id。
        :returns: active fallback view；不存在时返回 ``None``。
        """

        row = transaction.fetchone(
            f"""
            SELECT event_id
            FROM {TABLE_EVENT_LOG}
            WHERE run_id = ?
              AND event_type = ?
              AND event_sequence < ?
            ORDER BY event_sequence DESC
            LIMIT 1
            """,
            (run_id, CONTEXT_COMPACTION_FAILED, run_started_event_sequence),
        )
        if row is None:
            return None
        event_id = _required_row_text(row, "event_id")
        event = self._event_log_store.read_event_by_id(transaction, event_id)
        if event is None:
            return None
        payload = event_payload_object(
            transaction,
            event,
            payload_label=CONTEXT_COMPACTION_FAILED,
        )
        if payload.get(_FIELD_FALLBACK_ACTION) != FALLBACK_ACTION_DISPATCH:
            return None
        window = _optional_mapping(payload, _FIELD_FALLBACK_INPUT_WINDOW)
        digest = _optional_text(payload, _FIELD_FALLBACK_INPUT_DIGEST)
        if window is None or digest is None:
            return None
        window_current_ref = _optional_text(window, _FIELD_CURRENT_INPUT_REF)
        if window_current_ref != current_input_ref:
            return None
        actual_current_input_ref = window_current_ref
        if actual_current_input_ref is None:
            return None
        return ActiveRecentWindowFallback(
            selected_block_ids=_required_text_tuple(window, _FIELD_SELECTED_BLOCK_IDS),
            current_input_ref=actual_current_input_ref,
            fallback_input_digest=digest,
        )


def build_recent_window_fallback_selection(
    *,
    policy: ContextBudgetPolicy,
    session_id: str,
    run_id: str,
    material_blocks: tuple[RunInputMaterialBlock, ...],
    current_input_ref: str,
    input_cursor: int,
    selected_recent_window_turn_floor: int,
    trigger_source: ContextCompactionTriggerSource,
) -> RecentWindowFallbackSelection:
    """按 deterministic recent-window policy 选择 fallback input view。

    选择顺序为：固定 current input anchor、stable / compact represented
    context、recent raw turn floor；若必保留集合未超过 hard budget，再按
    reverse chronological raw turn block order 追加最近 raw turn，直到下一
    block 会触发 hard threshold 或 material 耗尽。

    :param policy: context budget policy。
    :param session_id: Session id。
    :param run_id: Run id。
    :param material_blocks: ordinary material blocks。
    :param current_input_ref: 当前输入 event id。
    :param input_cursor: material input cursor。
    :param selected_recent_window_turn_floor: selected recent window turn floor。
    :param trigger_source: compact trigger source。
    :returns: fallback selection。
    :raises ValueError: 缺少 current input anchor 或 floor 非法时抛出。
    """

    if selected_recent_window_turn_floor < 0:
        raise ValueError("selected_recent_window_turn_floor must be non-negative")
    current = _current_input_block(material_blocks, current_input_ref=current_input_ref)
    raw_blocks = _reverse_chronological_raw_blocks(material_blocks)
    floor_ids = frozenset(
        block.block_id for block in raw_blocks[:selected_recent_window_turn_floor]
    )
    selected_ids = _required_block_ids(
        material_blocks,
        current_block_id=current.block_id,
        floor_ids=floor_ids,
    )
    required_blocks = _blocks_by_material_order(material_blocks, selected_ids)
    required_budget = estimate_recent_window_fallback_budget(
        policy=policy,
        session_id=session_id,
        run_id=run_id,
        selection_blocks=required_blocks,
        current_input_ref=current_input_ref,
    )
    blocked_next_block_id: str | None = None
    if required_budget.hard_budget_passed:
        for block in raw_blocks:
            if block.block_id in selected_ids:
                continue
            candidate_ids = frozenset((*selected_ids, block.block_id))
            candidate_blocks = _blocks_by_material_order(material_blocks, candidate_ids)
            candidate_budget = estimate_recent_window_fallback_budget(
                policy=policy,
                session_id=session_id,
                run_id=run_id,
                selection_blocks=candidate_blocks,
                current_input_ref=current_input_ref,
            )
            if not candidate_budget.hard_budget_passed:
                blocked_next_block_id = block.block_id
                break
            selected_ids = candidate_ids
    selected_blocks = _blocks_by_material_order(material_blocks, selected_ids)
    selected_block_ids = frozenset(block.block_id for block in selected_blocks)
    dropped_blocks = tuple(block for block in material_blocks if block.block_id not in selected_block_ids)
    return RecentWindowFallbackSelection(
        selected_blocks=selected_blocks,
        dropped_blocks=dropped_blocks,
        current_input_ref=current_input_ref,
        source_refs=_selected_source_refs(selected_blocks),
        selected_recent_window_turn_floor=selected_recent_window_turn_floor,
        trigger_source=trigger_source,
        policy_ref=policy.policy_ref,
        input_cursor=input_cursor,
        blocked_next_block_id=blocked_next_block_id,
    )


def estimate_recent_window_fallback_budget(
    *,
    policy: ContextBudgetPolicy,
    session_id: str,
    run_id: str,
    selection_blocks: tuple[RunInputMaterialBlock, ...],
    current_input_ref: str,
) -> RecentWindowFallbackBudgetResult:
    """对 fallback-selected message fragments 执行既有保守预算重估。

    :param policy: context budget policy。
    :param session_id: Session id。
    :param run_id: Run id。
    :param selection_blocks: 已选择的 fallback material blocks。
    :param current_input_ref: 当前用户输入 ref。
    :returns: fallback budget result。
    """

    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id=session_id,
            run_id=run_id,
            message_fragments=tuple(
                BudgetTextFragment(fragment_ref=block.block_id, text=block.text)
                for block in selection_blocks
            ),
            current_prompt_ref=current_input_ref,
        ),
    )
    decision = decide_context_budget(estimate)
    status = (
        FALLBACK_BUDGET_STATUS_OVER_BUDGET
        if decision is ContextBudgetDecision.BLOCK_HARD_THRESHOLD
        else FALLBACK_BUDGET_STATUS_WITHIN_BUDGET
    )
    return RecentWindowFallbackBudgetResult(
        status=status,
        decision=decision,
        estimate=estimate,
        policy_ref=policy.policy_ref,
    )


def build_selection_failure_window_payload(
    *,
    current_input_ref: str,
    trigger_source: ContextCompactionTriggerSource,
    policy_ref: str,
    input_cursor: int,
    failure_reason: str,
) -> Mapping[str, JsonValue]:
    """构造 selection failure 的有界 fallback window 诊断。

    :param current_input_ref: 当前输入 ref。
    :param trigger_source: compact trigger source。
    :param policy_ref: context budget policy ref。
    :param input_cursor: input cursor。
    :param failure_reason: selection failure reason。
    :returns: JSON object。
    """

    return {
        _FIELD_SELECTED_BLOCK_IDS: [],
        "dropped_block_ids": [],
        _FIELD_CURRENT_INPUT_REF: current_input_ref,
        "source_refs": [current_input_ref],
        _FIELD_SELECTED_RECENT_WINDOW_TURN_FLOOR: 0,
        "trigger_source": trigger_source.value,
        "policy_ref": policy_ref,
        "input_cursor": input_cursor,
        "selection_failure_reason": failure_reason,
    }


def build_selection_failure_budget_payload(*, policy_ref: str) -> Mapping[str, JsonValue]:
    """构造 selection failure 的 fallback budget 诊断。

    :param policy_ref: context budget policy ref。
    :returns: JSON object。
    """

    return {
        "status": FALLBACK_BUDGET_STATUS_SELECTION_FAILED,
        "decision": RecentWindowFallbackAction.FAIL_CLOSED.value,
        "estimated_input_tokens": None,
        "soft_threshold_tokens": None,
        "hard_threshold_tokens": None,
        "estimator_digest": None,
        "policy_ref": policy_ref,
    }


def fallback_window_digest(window_payload: Mapping[str, JsonValue]) -> str:
    """计算 fallback input window payload 的 digest。

    :param window_payload: fallback window payload。
    :returns: sha256 digest。
    """

    return sha256_digest_json(window_payload)


def _current_input_block(
    blocks: tuple[RunInputMaterialBlock, ...], *, current_input_ref: str
) -> RunInputMaterialBlock:
    """读取当前输入 anchor block。

    :param blocks: material blocks。
    :param current_input_ref: 当前输入 ref。
    :returns: 当前输入 block。
    :raises ValueError: 找不到唯一 current input anchor 时抛出。
    """

    matches = tuple(
        block
        for block in blocks
        if block.section is CompactMaterialSection.CURRENT_INPUT_ANCHOR
        and current_input_ref in block.canonical_source_refs
    )
    if len(matches) != 1:
        raise ValueError("fallback selection requires exactly one current input anchor")
    return matches[0]


def _required_block_ids(
    blocks: tuple[RunInputMaterialBlock, ...],
    *,
    current_block_id: str,
    floor_ids: frozenset[str],
) -> frozenset[str]:
    """计算 fallback 必保留 block ids。

    :param blocks: material blocks。
    :param current_block_id: current input block id。
    :param floor_ids: recent raw floor block ids。
    :returns: 必保留 block ids。
    """

    selected: set[str] = {current_block_id}
    selected.update(floor_ids)
    for block in blocks:
        if block.section is CompactMaterialSection.PREVIOUS_COMPACTED_VIEW or block.already_represented:
            selected.add(block.block_id)
    return frozenset(selected)


def _reverse_chronological_raw_blocks(
    blocks: tuple[RunInputMaterialBlock, ...],
) -> tuple[RunInputMaterialBlock, ...]:
    """按 reverse chronological material order 返回 raw turn blocks。

    :param blocks: material blocks。
    :returns: raw turn blocks。
    """

    return tuple(
        sorted(
            (block for block in blocks if _is_raw_turn_block(block)),
            key=lambda block: (
                _NO_EVENT_SEQUENCE if block.event_sequence is None else block.event_sequence,
                block.event_sub_index,
                block.block_id,
            ),
            reverse=True,
        )
    )


def _blocks_by_material_order(
    blocks: tuple[RunInputMaterialBlock, ...], selected_ids: frozenset[str]
) -> tuple[RunInputMaterialBlock, ...]:
    """按原 material 顺序返回 selected blocks。

    :param blocks: material blocks。
    :param selected_ids: selected block id 集合。
    :returns: selected blocks。
    """

    return tuple(block for block in blocks if block.block_id in selected_ids)


def _selected_source_refs(blocks: tuple[RunInputMaterialBlock, ...]) -> tuple[str, ...]:
    """收集 selected blocks 的 canonical source refs。

    :param blocks: selected blocks。
    :returns: 去重 source refs。
    """

    refs: list[str] = []
    for block in blocks:
        refs.extend(block.canonical_source_refs)
    return tuple(dict.fromkeys(refs))


def _raw_turn_count(blocks: tuple[RunInputMaterialBlock, ...]) -> int:
    """统计 selected raw turn block 数量。

    :param blocks: selected blocks。
    :returns: raw turn 数量。
    """

    return sum(1 for block in blocks if _is_raw_turn_block(block))


def _is_raw_turn_block(block: RunInputMaterialBlock) -> bool:
    """判断 block 是否为 raw user / assistant turn。

    :param block: material block。
    :returns: raw turn 返回 ``True``。
    """

    return block.kind in (
        CompactMaterialBlockKind.USER_INPUT,
        CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
    )


def _optional_mapping(
    payload: Mapping[str, JsonValue], field_name: str
) -> Mapping[str, JsonValue] | None:
    """读取可选 JSON object 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: mapping 或 ``None``。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    return value


def _optional_text(payload: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取可选文本字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    """

    value = payload.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _required_text_tuple(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取必填字符串列表字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 字符串 tuple。
    :raises ValueError: 字段不存在或元素非法时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise ValueError(f"{field_name} must contain non-empty strings")
        result.append(item)
    return tuple(result)


def _required_row_text(row: HostRow, field_name: str) -> str:
    """读取 SQLite row 中的必填文本字段。

    :param row: Host row。
    :param field_name: 字段名。
    :returns: 文本。
    :raises ValueError: 字段缺失或非法时抛出。
    """

    value = row.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _require_block_tuple(
    blocks: tuple[RunInputMaterialBlock, ...], field_name: str
) -> None:
    """校验 material block tuple。

    :param blocks: 待校验 blocks。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: tuple 或元素类型非法时抛出。
    """

    if not isinstance(blocks, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for block in blocks:
        if not isinstance(block, RunInputMaterialBlock):
            raise TypeError(f"{field_name} must contain RunInputMaterialBlock")


def _require_text_tuple(values: tuple[str, ...], field_name: str) -> None:
    """校验字符串 tuple。

    :param values: 待校验字符串 tuple。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: tuple 或元素类型非法时抛出。
    :raises ValueError: 元素为空时抛出。
    """

    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for value in values:
        _require_non_empty_text(value, field_name)


def _require_non_empty_text(value: str, field_name: str) -> None:
    """校验非空文本。

    :param value: 待校验文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


__all__ = [
    "FALLBACK_ACTION_DISPATCH",
    "FALLBACK_ACTION_FAIL_CLOSED",
    "FALLBACK_ACTION_NOT_APPLICABLE",
    "FALLBACK_BUDGET_STATUS_OVER_BUDGET",
    "FALLBACK_BUDGET_STATUS_SELECTION_FAILED",
    "FALLBACK_BUDGET_STATUS_WITHIN_BUDGET",
    "FALLBACK_POLICY_DECISION_RECENT_WINDOW",
    "FALLBACK_POLICY_DECISION_SELECTION_FAILED",
    "ActiveRecentWindowFallback",
    "EventLogContextFallbackProvider",
    "RecentWindowFallbackAction",
    "RecentWindowFallbackBudgetResult",
    "RecentWindowFallbackSelection",
    "build_recent_window_fallback_selection",
    "build_selection_failure_budget_payload",
    "build_selection_failure_window_payload",
    "estimate_recent_window_fallback_budget",
    "fallback_window_digest",
]
