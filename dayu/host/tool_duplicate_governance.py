"""Host 工具重复治理的 attempt-scoped typed contracts。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_outcome import ToolAwaitingOutcome, ToolExecutionOutcome
from dayu.host.durable.codec import is_sha256_digest, sha256_digest_json

if TYPE_CHECKING:
    from dayu.host.tool_runtime import HostEventRef


class DuplicateDecisionKind(StrEnum):
    """同一 Attempt 内语义级重复工具调用决策类别。"""

    ALLOW = "allow"
    REUSE = "reuse"
    HINT = "hint"
    REQUIRE_JUSTIFICATION = "require_justification"
    HARD_STOP = "hard_stop"
    DURABLE_MISSING = "durable_missing"
    AWAITING_FANOUT = "awaiting_fanout"


class DuplicateDurableMissingReason(StrEnum):
    """in-flight owner 未产生可复用 accepted fact 的原因。"""

    OWNER_CANCELLED = "owner_cancelled"
    TOOL_EXCEPTION = "tool_exception"
    HOST_ACCEPT_REJECTED = "host_accept_rejected"
    HOST_ACCEPT_TIMEOUT = "host_accept_timeout"
    GOVERNED_BEFORE_ACCEPT = "governed_before_accept"


class _InFlightDuplicateState(StrEnum):
    """attempt-local in-flight duplicate 记录状态。"""

    OWNER_RUNNING = "owner_running"
    ACCEPTED = "accepted"
    AWAITING_ACCEPTED = "awaiting_accepted"
    DURABLE_MISSING = "durable_missing"


@dataclass(frozen=True, slots=True)
class DuplicateGovernanceScope:
    """重复治理作用域。

    :param kind: 作用域类别；当前固定为 ``attempt``。
    :param attempt_id: 当前 ToolRuntime execution scope 的 Attempt id。
    """

    kind: Literal["attempt"]
    attempt_id: str

    def __post_init__(self) -> None:
        """校验作用域字段。

        :returns: ``None``。
        :raises ValueError: 作用域类别或 Attempt id 非法时抛出。
        """

        if self.kind != "attempt":
            raise ValueError("duplicate governance scope kind must be attempt")
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")


@dataclass(frozen=True, slots=True)
class DuplicateGovernanceMessages:
    """重复治理面向模型和诊断的消息配置。

    :param allow: allow 决策说明。
    :param reuse: reuse 决策说明。
    :param hint: hint 决策说明。
    :param require_justification: require_justification 决策说明。
    :param hard_stop: hard_stop 决策说明。
    :param attempt_scope_diagnostic: attempt-scoped duplicate 诊断说明。
    :param prior_accept_missing: owner 未产生 accepted fact 时的等待者说明。
    :param awaiting_fanout: owner 已进入 Host waiting 后的防御性 fanout 说明。
    """

    allow: str = "本次重复工具调用已允许执行。"
    reuse: str = "请直接使用上一次工具结果继续推理，不要重复请求相同证据。"
    hint: str = (
        "请优先使用上一次工具结果继续推理；只有当需要不同主体、期间、"
        "指标或证据范围时，才重新调用工具并修改参数。"
    )
    require_justification: str = (
        "重复调用同一工具前，必须在参数中说明为什么上一次工具结果不足，"
        "以及本次需要补充的不同证据范围。"
    )
    hard_stop: str = (
        "本次重复工具调用已被拒绝。请使用上一次工具结果继续推理；"
        "如果信息不足，请说明不确定性，不要编造。"
    )
    attempt_scope_diagnostic: str = (
        "检测到当前推理步骤中重复请求相同工具证据。"
    )
    prior_accept_missing: str = (
        "上一次相同工具请求没有产生可用结果。请说明信息不足，"
        "或在改变证据范围后再调用工具。"
    )
    awaiting_fanout: str = (
        "相同工具请求已经进入等待状态；当前重复请求共享同一个等待结果。"
    )

    def __post_init__(self) -> None:
        """校验所有消息均为非空文本。

        :returns: ``None``。
        :raises ValueError: 任一消息为空或纯空白时抛出。
        """

        for field_name, value in (
            ("allow", self.allow),
            ("reuse", self.reuse),
            ("hint", self.hint),
            ("require_justification", self.require_justification),
            ("hard_stop", self.hard_stop),
            ("attempt_scope_diagnostic", self.attempt_scope_diagnostic),
            ("prior_accept_missing", self.prior_accept_missing),
            ("awaiting_fanout", self.awaiting_fanout),
        ):
            _require_non_empty_text(value, field_name=field_name)

    def message_for(self, kind: DuplicateDecisionKind) -> str:
        """返回指定 duplicate 决策对应的消息。

        :param kind: duplicate 决策类别。
        :returns: 已配置的人类可读消息。
        """

        if kind is DuplicateDecisionKind.ALLOW:
            return self.allow
        if kind is DuplicateDecisionKind.REUSE:
            return self.reuse
        if kind is DuplicateDecisionKind.HINT:
            return self.hint
        if kind is DuplicateDecisionKind.REQUIRE_JUSTIFICATION:
            return self.require_justification
        if kind is DuplicateDecisionKind.HARD_STOP:
            return self.hard_stop
        if kind is DuplicateDecisionKind.DURABLE_MISSING:
            return self.prior_accept_missing
        if kind is DuplicateDecisionKind.AWAITING_FANOUT:
            return self.awaiting_fanout
        raise ValueError(f"unsupported duplicate decision kind: {kind}")


@dataclass(frozen=True, slots=True)
class DuplicateGovernancePolicy:
    """attempt-scoped duplicate governance 策略。

    :param default_duplicate_decision: 已命中既有 accepted 记录时的默认治理动作。
    :param decisions_by_tool_name: 按工具名覆盖的 duplicate 动作。
    :param justification_argument_names_by_tool_name: 结构化 justification 参数名映射。
    :param messages: duplicate governance 消息配置。
    """

    default_duplicate_decision: DuplicateDecisionKind = DuplicateDecisionKind.HINT
    decisions_by_tool_name: Mapping[str, DuplicateDecisionKind] = field(
        default_factory=dict
    )
    justification_argument_names_by_tool_name: Mapping[str, str] = field(
        default_factory=dict
    )
    messages: DuplicateGovernanceMessages = field(
        default_factory=DuplicateGovernanceMessages
    )

    def __post_init__(self) -> None:
        """校验 duplicate governance 策略字段。

        :returns: ``None``。
        :raises ValueError: 工具名、决策类别或 justification 参数名非法时抛出。
        """

        if not isinstance(self.default_duplicate_decision, DuplicateDecisionKind):
            raise ValueError(
                "default_duplicate_decision must be DuplicateDecisionKind"
            )
        for tool_name, decision in self.decisions_by_tool_name.items():
            _require_non_empty_text(tool_name, field_name="duplicate policy tool_name")
            if not isinstance(decision, DuplicateDecisionKind):
                raise ValueError(
                    "duplicate policy decision must be DuplicateDecisionKind"
                )
        for tool_name, argument_name in (
            self.justification_argument_names_by_tool_name.items()
        ):
            _require_non_empty_text(
                tool_name, field_name="duplicate justification tool_name"
            )
            _require_non_empty_text(
                argument_name, field_name="duplicate justification argument_name"
            )


@dataclass(frozen=True, slots=True)
class DuplicateGovernanceRequest:
    """重复治理查询输入。

    :param scope: 当前 duplicate governance 作用域。
    :param tool_name: 工具名。
    :param tool_identity_digest: 工具身份 digest。
    :param normalized_arguments_digest: canonical 参数 digest。
    :param arguments: 当前工具参数，用于读取 semantic key 或 justification。
    :param semantic_duplicate_key: 工具可选提供的 attempt-local 语义重复 key。
    """

    scope: DuplicateGovernanceScope
    tool_name: str
    tool_identity_digest: str
    normalized_arguments_digest: str
    arguments: Mapping[str, JsonValue]
    semantic_duplicate_key: str | None

    def __post_init__(self) -> None:
        """校验重复治理查询输入。

        :returns: ``None``。
        :raises ValueError: 工具名、digest 或 semantic key 非法时抛出。
        """

        if not isinstance(self.scope, DuplicateGovernanceScope):
            raise ValueError("scope must be DuplicateGovernanceScope")
        _require_non_empty_text(self.tool_name, field_name="tool_name")
        _require_sha256_digest(
            self.tool_identity_digest, field_name="tool_identity_digest"
        )
        _require_sha256_digest(
            self.normalized_arguments_digest,
            field_name="normalized_arguments_digest",
        )
        _require_optional_non_empty_text(
            self.semantic_duplicate_key, field_name="semantic_duplicate_key"
        )


@dataclass(frozen=True, slots=True)
class DuplicateAcceptedEntry:
    """重复治理 accepted 索引写入条目。

    :param accepted_event_refs: Host accept ack 返回的 accepted refs。
    :param accepted_outcome: 已 durable accepted 且可复用的工具 outcome。
    :param result_digest: accepted ack 中的结果 digest。
    """

    accepted_event_refs: tuple["HostEventRef", ...]
    accepted_outcome: ToolExecutionOutcome
    result_digest: str

    def __post_init__(self) -> None:
        """校验 accepted 索引写入条目。

        :returns: ``None``。
        :raises ValueError: 缺少 accepted refs 或 result digest 非法时抛出。
        """

        if not self.accepted_event_refs:
            raise ValueError("duplicate accepted entry requires event refs")
        _require_sha256_digest(self.result_digest, field_name="result_digest")


@dataclass(frozen=True, slots=True)
class DuplicateAwaitingAcceptedEntry:
    """重复治理 awaiting accepted marker 写入条目。

    :param accepted_event_refs: Host awaiting accept ack 返回的 accepted refs。
    :param wait_id: Host 已接受的 owner wait id。
    :param awaiting_outcome: 已被 Host 接受的 awaiting outcome。
    :param result_digest: awaiting accept ack 中的语义结果 digest。
    """

    accepted_event_refs: tuple["HostEventRef", ...]
    wait_id: str
    awaiting_outcome: ToolAwaitingOutcome
    result_digest: str

    def __post_init__(self) -> None:
        """校验 awaiting accepted marker 写入条目。

        :returns: ``None``。
        :raises ValueError: refs、wait id、awaiting outcome 或 digest 非法时抛出。
        """

        if not self.accepted_event_refs:
            raise ValueError("duplicate awaiting accepted entry requires event refs")
        _require_non_empty_text(self.wait_id, field_name="wait_id")
        if not isinstance(self.awaiting_outcome, ToolAwaitingOutcome):
            raise ValueError("awaiting_outcome must be ToolAwaitingOutcome")
        _require_sha256_digest(self.result_digest, field_name="result_digest")


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    """重复工具调用治理决策。

    :param kind: 重复治理类别。
    :param duplicate_key: 当前调用的重复键；未产生时为 ``None``。
    :param prior_event_refs: 可复用的既有事件引用；无复用时为空元组。
    :param prior_outcome: 可返回给 Engine 的既有 accepted outcome；无复用时为 ``None``。
    :param prior_awaiting_outcome: 可返回给 Engine 的既有 awaiting outcome；无 fanout 时为 ``None``。
    :param prior_wait_id: 既有 owner wait id；无 awaiting fanout 时为 ``None``。
    :param scope: 当前 duplicate governance 作用域。
    :param reason_code: 机器可读治理原因；无原因时为 ``None``。
    :param message: 面向模型或诊断的人类可读消息；无消息时为 ``None``。
    :param diagnostic_message: attempt-scope 诊断消息；无消息时为 ``None``。
    :param durable_missing_reason: owner 未产生 accepted fact 的原因；非该场景为 ``None``。
    """

    kind: DuplicateDecisionKind
    duplicate_key: str | None
    prior_event_refs: tuple["HostEventRef", ...]
    prior_outcome: ToolExecutionOutcome | None
    prior_awaiting_outcome: ToolAwaitingOutcome | None
    prior_wait_id: str | None
    scope: DuplicateGovernanceScope
    reason_code: str | None
    message: str | None
    diagnostic_message: str | None
    durable_missing_reason: DuplicateDurableMissingReason | None = None


class DuplicateGovernancePort(Protocol):
    """重复工具调用治理端口协议。

    该端口只表达 attempt-scoped duplicate governance 能力，不依赖
    ToolRuntime 的执行、accept barrier 或 dispatch 生命周期。
    """

    async def decide_duplicate(
        self, request: DuplicateGovernanceRequest
    ) -> DuplicateDecision:
        """判断当前工具调用是否与同 Attempt 既有调用重复。

        :param request: duplicate governance 查询输入。
        :returns: 重复治理决策。
        :raises ValueError: 实现可在 request 字段非法时抛出。
        """
        ...

    async def record_accepted(
        self,
        request: DuplicateGovernanceRequest,
        accepted_entry: DuplicateAcceptedEntry,
    ) -> None:
        """记录已 accepted 工具事实供同 Attempt 后续治理复用。

        :param request: duplicate governance 查询输入。
        :param accepted_entry: accepted 索引写入条目。
        :returns: ``None``。
        :raises ValueError: 实现可在记录字段非法时抛出。
        """
        ...

    async def record_awaiting_accepted(
        self,
        request: DuplicateGovernanceRequest,
        awaiting_entry: DuplicateAwaitingAcceptedEntry,
    ) -> None:
        """记录 owner 已 accepted awaiting marker 供同 Attempt 后续治理。

        :param request: duplicate governance 查询输入。
        :param awaiting_entry: awaiting accepted marker 写入条目。
        :returns: ``None``。
        :raises ValueError: 实现可在记录字段非法时抛出。
        """
        ...

    async def record_durable_missing(
        self,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """记录 owner 未产生可复用 accepted fact。

        :param request: duplicate governance 查询输入。
        :param reason: durable missing 原因。
        :returns: ``None``。
        :raises ValueError: 实现可在请求或原因非法时抛出。
        """
        ...


@dataclass(slots=True)
class _InFlightDuplicateRecord:
    """attempt-local in-flight duplicate 记录。

    :param duplicate_key: 当前 in-flight 窗口的 duplicate key。
    :param state: in-flight 当前状态。
    :param accepted_entry: owner accepted 后写入的条目。
    :param awaiting_entry: owner awaiting accepted 后写入的 marker。
    :param durable_missing_reason: owner 未产生 accepted fact 的原因。
    """

    duplicate_key: str
    state: _InFlightDuplicateState
    accepted_entry: DuplicateAcceptedEntry | None = None
    awaiting_entry: DuplicateAwaitingAcceptedEntry | None = None
    durable_missing_reason: DuplicateDurableMissingReason | None = None


@dataclass(slots=True)
class _AttemptDuplicateGovernanceState:
    """单个 ToolRuntime Attempt 的 duplicate 内存状态。"""

    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    entries_by_key: dict[str, DuplicateAcceptedEntry] = field(default_factory=dict)
    in_flight_by_key: dict[str, _InFlightDuplicateRecord] = field(
        default_factory=dict
    )


class InMemoryAttemptDuplicateGovernance:
    """单 Attempt 内存 duplicate governance 实现。

    该实现不落 durable duplicate table，不跨 Attempt、Run、进程或重启复用状态。
    """

    def __init__(
        self,
        policy: DuplicateGovernancePolicy | None = None,
        *,
        state: _AttemptDuplicateGovernanceState | None = None,
    ) -> None:
        """初始化 attempt-local duplicate governance。

        :param policy: duplicate governance 策略；无则默认 duplicate 命中也继续 ``allow``。
        :param state: 可选状态对象；测试或组合场景可显式传入。
        :returns: ``None``。
        """

        self._policy = policy if policy is not None else DuplicateGovernancePolicy()
        self._state = state if state is not None else _AttemptDuplicateGovernanceState()

    async def decide_duplicate(
        self, request: DuplicateGovernanceRequest
    ) -> DuplicateDecision:
        """按 attempt-local accepted index 和 in-flight 状态生成 duplicate 决策。

        :param request: duplicate governance 查询输入。
        :returns: duplicate 决策；duplicate key 不包含 ``index_in_iteration``。
        :raises ValueError: request 字段非法时由 dataclass 校验抛出。
        """

        duplicate_key = duplicate_governance_key(request)
        async with self._state.condition:
            while True:
                accepted_entry = self._state.entries_by_key.get(duplicate_key)
                if accepted_entry is not None:
                    return self._decision_for_accepted_entry(
                        request=request,
                        duplicate_key=duplicate_key,
                        accepted_entry=accepted_entry,
                    )
                in_flight = self._state.in_flight_by_key.get(duplicate_key)
                if in_flight is None:
                    self._state.in_flight_by_key[duplicate_key] = (
                        _InFlightDuplicateRecord(
                            duplicate_key=duplicate_key,
                            state=_InFlightDuplicateState.OWNER_RUNNING,
                        )
                    )
                    return self._allow_decision(request, duplicate_key, prior_refs=())
                while in_flight.state is _InFlightDuplicateState.OWNER_RUNNING:
                    await self._state.condition.wait()
                if in_flight.state is _InFlightDuplicateState.ACCEPTED:
                    if in_flight.accepted_entry is None:
                        raise RuntimeError(
                            "accepted duplicate in-flight entry is missing"
                        )
                    return self._decision_for_accepted_entry(
                        request=request,
                        duplicate_key=duplicate_key,
                        accepted_entry=in_flight.accepted_entry,
                    )
                if in_flight.state is _InFlightDuplicateState.AWAITING_ACCEPTED:
                    if in_flight.awaiting_entry is None:
                        raise RuntimeError(
                            "awaiting accepted duplicate entry is missing"
                        )
                    return self._decision_for_awaiting_entry(
                        request=request,
                        duplicate_key=duplicate_key,
                        awaiting_entry=in_flight.awaiting_entry,
                    )
                if in_flight.durable_missing_reason is None:
                    raise RuntimeError("durable-missing duplicate reason is missing")
                # durable-missing 只说明上一任 owner 没有可复用 fact；等待者需要
                # 回到循环重新竞争 owner，而不是把旧失败永久传播给所有等待者。
                continue

    async def record_accepted(
        self,
        request: DuplicateGovernanceRequest,
        accepted_entry: DuplicateAcceptedEntry,
    ) -> None:
        """记录 owner 已 accepted 的工具事实并唤醒等待者。

        :param request: 原始 duplicate governance 查询。
        :param accepted_entry: accepted 索引写入条目。
        :returns: ``None``。
        """

        duplicate_key = duplicate_governance_key(request)
        async with self._state.condition:
            self._state.entries_by_key[duplicate_key] = accepted_entry
            in_flight = self._state.in_flight_by_key.pop(duplicate_key, None)
            if in_flight is not None:
                in_flight.state = _InFlightDuplicateState.ACCEPTED
                in_flight.accepted_entry = accepted_entry
            self._state.condition.notify_all()

    async def record_awaiting_accepted(
        self,
        request: DuplicateGovernanceRequest,
        awaiting_entry: DuplicateAwaitingAcceptedEntry,
    ) -> None:
        """记录 owner 已 accepted awaiting marker 并唤醒等待者。

        :param request: 原始 duplicate governance 查询。
        :param awaiting_entry: awaiting accepted marker 写入条目。
        :returns: ``None``。
        """

        duplicate_key = duplicate_governance_key(request)
        async with self._state.condition:
            in_flight = self._state.in_flight_by_key.get(duplicate_key)
            if in_flight is None:
                in_flight = _InFlightDuplicateRecord(
                    duplicate_key=duplicate_key,
                    state=_InFlightDuplicateState.AWAITING_ACCEPTED,
                )
                self._state.in_flight_by_key[duplicate_key] = in_flight
            in_flight.state = _InFlightDuplicateState.AWAITING_ACCEPTED
            in_flight.awaiting_entry = awaiting_entry
            self._state.condition.notify_all()

    async def record_durable_missing(
        self,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """记录 owner 未产生 accepted fact 并唤醒等待者。

        :param request: 原始 duplicate governance 查询。
        :param reason: durable missing 原因。
        :returns: ``None``。
        """

        duplicate_key = duplicate_governance_key(request)
        async with self._state.condition:
            in_flight = self._state.in_flight_by_key.pop(duplicate_key, None)
            if in_flight is not None:
                if in_flight.state is _InFlightDuplicateState.AWAITING_ACCEPTED:
                    self._state.in_flight_by_key[duplicate_key] = in_flight
                    self._state.condition.notify_all()
                    return
                in_flight.state = _InFlightDuplicateState.DURABLE_MISSING
                in_flight.durable_missing_reason = reason
            self._state.condition.notify_all()

    def _decision_for_accepted_entry(
        self,
        *,
        request: DuplicateGovernanceRequest,
        duplicate_key: str,
        accepted_entry: DuplicateAcceptedEntry,
    ) -> DuplicateDecision:
        """根据已 accepted 条目生成 policy 驱动的 duplicate 决策。

        :param request: duplicate governance 查询输入。
        :param duplicate_key: 当前 duplicate key。
        :param accepted_entry: 命中的 accepted 条目。
        :returns: duplicate 决策。
        """

        decision = self._decision_for_request(request)
        if decision is DuplicateDecisionKind.ALLOW:
            return self._allow_decision(
                request,
                duplicate_key,
                prior_refs=accepted_entry.accepted_event_refs,
            )
        return DuplicateDecision(
            kind=decision,
            duplicate_key=duplicate_key,
            prior_event_refs=accepted_entry.accepted_event_refs,
            prior_outcome=accepted_entry.accepted_outcome,
            prior_awaiting_outcome=None,
            prior_wait_id=None,
            scope=request.scope,
            reason_code=None,
            message=self._policy.messages.message_for(decision),
            diagnostic_message=self._policy.messages.attempt_scope_diagnostic,
        )

    def _decision_for_awaiting_entry(
        self,
        *,
        request: DuplicateGovernanceRequest,
        duplicate_key: str,
        awaiting_entry: DuplicateAwaitingAcceptedEntry,
    ) -> DuplicateDecision:
        """根据 awaiting accepted marker 生成防御性 fanout 决策。

        :param request: duplicate governance 查询输入。
        :param duplicate_key: 当前 duplicate key。
        :param awaiting_entry: 命中的 awaiting accepted marker。
        :returns: awaiting fanout 决策。
        """

        return DuplicateDecision(
            kind=DuplicateDecisionKind.AWAITING_FANOUT,
            duplicate_key=duplicate_key,
            prior_event_refs=awaiting_entry.accepted_event_refs,
            prior_outcome=None,
            prior_awaiting_outcome=awaiting_entry.awaiting_outcome,
            prior_wait_id=awaiting_entry.wait_id,
            scope=request.scope,
            reason_code="duplicate_awaiting_fanout",
            message=self._policy.messages.message_for(
                DuplicateDecisionKind.AWAITING_FANOUT
            ),
            diagnostic_message=self._policy.messages.attempt_scope_diagnostic,
        )

    def _decision_for_request(
        self, request: DuplicateGovernanceRequest
    ) -> DuplicateDecisionKind:
        """返回命中 duplicate index 后的治理动作。

        :param request: duplicate governance 查询输入。
        :returns: 当前工具对应的 duplicate 决策。
        """

        decision = self._policy.decisions_by_tool_name.get(
            request.tool_name, self._policy.default_duplicate_decision
        )
        if decision is DuplicateDecisionKind.REQUIRE_JUSTIFICATION:
            argument_name = (
                self._policy.justification_argument_names_by_tool_name.get(
                    request.tool_name
                )
            )
            if argument_name is None:
                return DuplicateDecisionKind.HINT
            value = request.arguments.get(argument_name)
            if isinstance(value, str) and value.strip() != "":
                return DuplicateDecisionKind.ALLOW
            return DuplicateDecisionKind.REQUIRE_JUSTIFICATION
        return decision

    def _allow_decision(
        self,
        request: DuplicateGovernanceRequest,
        duplicate_key: str,
        *,
        prior_refs: tuple["HostEventRef", ...],
    ) -> DuplicateDecision:
        """构造 allow duplicate 决策。

        :param request: duplicate governance 查询输入。
        :param duplicate_key: 当前 duplicate key。
        :param prior_refs: 已命中的同 scope prior refs；无则为空。
        :returns: allow duplicate 决策。
        """

        return DuplicateDecision(
            kind=DuplicateDecisionKind.ALLOW,
            duplicate_key=duplicate_key,
            prior_event_refs=prior_refs,
            prior_outcome=None,
            prior_awaiting_outcome=None,
            prior_wait_id=None,
            scope=request.scope,
            reason_code=None,
            message=self._policy.messages.allow,
            diagnostic_message=None,
        )


def duplicate_governance_key(request: DuplicateGovernanceRequest) -> str:
    """计算 attempt-scoped duplicate key。

    :param request: duplicate governance 查询输入。
    :returns: 稳定 sha256 duplicate key；包含 Attempt id，不包含 ``index_in_iteration``。
    """

    return sha256_digest_json(
        {
            "scope": {
                "kind": request.scope.kind,
                "attempt_id": request.scope.attempt_id,
            },
            "tool_name": request.tool_name,
            "tool_identity_digest": request.tool_identity_digest,
            "normalized_arguments_digest": request.normalized_arguments_digest,
            "semantic_duplicate_key": request.semantic_duplicate_key,
        }
    )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验文本非空。

    :param value: 待校验文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty_text(
    value: str | None, *, field_name: str
) -> None:
    """校验 optional 文本不为空白。

    :param value: 待校验文本；无值时为 ``None``。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空白时抛出。
    """

    if value is not None and value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty when provided")


def _require_sha256_digest(value: str | None, *, field_name: str) -> None:
    """校验必填 sha256 digest。

    :param value: digest 文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: digest 缺失或非法时抛出。
    """

    if value is None or not is_sha256_digest(value):
        raise ValueError(f"{field_name} must be a sha256 digest")


__all__ = [
    "DuplicateAcceptedEntry",
    "DuplicateAwaitingAcceptedEntry",
    "DuplicateDecision",
    "DuplicateDecisionKind",
    "DuplicateDurableMissingReason",
    "DuplicateGovernanceMessages",
    "DuplicateGovernancePolicy",
    "DuplicateGovernancePort",
    "DuplicateGovernanceRequest",
    "DuplicateGovernanceScope",
    "InMemoryAttemptDuplicateGovernance",
    "duplicate_governance_key",
]
