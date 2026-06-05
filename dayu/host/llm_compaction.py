"""Host-owned LLM context compactor。

本模块把 Host ``CompactionRequest`` 映射为一次禁用工具的 Engine public
runner 调用，并把 LLM final answer 的 strict JSON proposal 转换为
``ConversationCompactOutputVNext``。它不写 EventLog、不写 artifact、不做
semantic repair loop，也不向 Service 暴露 prompt、candidate builder 或
policy seam。
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from json import JSONDecodeError
from math import ceil
from typing import Protocol, cast, runtime_checkable
from uuid import uuid4

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import BatchToolExecutionOutcome
from dayu.engine import run_agent_and_wait
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    EngineRunOutcomeCancelled,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
    EngineRunOutcomeSuspended,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import (
    AgentMessageRole,
    SystemMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host.compact_material import conversation_compact_input_vnext_from_material_pack
from dayu.host.compaction import (
    AnswerAnchorCandidateVNext,
    AnswerAnchorChildVNext,
    CONVERSATION_COMPACT_ANSWER_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_DIAGNOSTIC_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_FORWARD_SOURCE_SECTIONS_VNEXT,
    CompactCandidateDiagnosticVNext,
    CONVERSATION_COMPACT_REFERENCE_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
    CONVERSATION_COMPACT_SUMMARY_SOURCE_SECTIONS_VNEXT,
    CompactionRequest,
    ConversationCompactInputVNext,
    ConversationCompactLabelSectionVNext,
    ConversationCompactOutputVNext,
    ContextCompactor,
    EvidenceBackedFactCandidateVNext,
    FactEvidenceKindVNext,
    ForwardIntentCandidateVNext,
    ForwardIntentStatusVNext,
    ForwardIntentTypeVNext,
    MAX_VNEXT_ANSWER_ANCHOR_ITEMS,
    MAX_VNEXT_DIAGNOSTIC_ITEMS,
    MAX_VNEXT_FACT_ITEMS,
    MAX_VNEXT_FORWARD_INTENT_ITEMS,
    MAX_VNEXT_REFERENCE_CONTINUITY_ITEMS,
    ReferenceContinuityCandidateVNext,
    ReferenceContinuityReasonVNext,
    SessionSummaryCandidateVNext,
    conversation_compact_label_looks_stale_vnext,
)
from dayu.host.context_budget import (
    DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS,
    DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS,
    estimate_budget_text_tokens,
)
from dayu.runtime.diagnostic_text import (
    redact_sensitive_diagnostic_values,
    truncate_diagnostic_text,
)

_COMPACTOR_RUN_ID_PREFIX = "context-compactor"
_MIN_PROPOSAL_LENGTH = 1
_MAX_SAFE_OUTCOME_MESSAGE_CHARS = 240
_TRUNCATED_SUFFIX = "..."
_REDACTED_SECRET = "<redacted>"
_SAFE_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_COMPACTION_REQUEST_PLACEHOLDER = "<<compaction_request>>"
_UNTRUSTED_COMPACTION_MATERIAL_BEGIN = "UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN"
_UNTRUSTED_COMPACTION_MATERIAL_END = "UNTRUSTED_COMPACTION_MATERIAL_JSON_END"
_COMPACTOR_PROPOSAL_TIMEOUT_MESSAGE = "compactor proposal timed out"
_COMPACTOR_PROPOSAL_TIMEOUT_CANCEL_REASON = "compactor_proposal_timeout"
_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE = (
    "Host post-compact run context includes session summary, current input, "
    "evidence-backed facts, answer anchors, forward intents, and continuity items."
)
_POST_COMPACT_BASE_MESSAGE_COUNT = 2
_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT = 1
@runtime_checkable
class _CancellationSignalToken(CancellationToken, Protocol):
    """Host 内部可写取消 token 协议。"""

    def request_cancel(self, reason: str) -> None:
        """请求取消底层 Engine runner。

        :param reason: 结构化取消原因。
        :returns: ``None``。
        """

        ...


class LLMCompactionProposalError(RuntimeError):
    """LLM compaction 单次 proposal 失败。

    :param message: 中性失败描述。
    """


class _RejectingToolExecutor(ToolExecutor):
    """禁用工具 compactor 的 rejecting executor。

    Engine request 同时设置 ``disable_tools=True`` 与空 tool schema；若未来
    上游错误地发起工具握手，本 executor 返回空批次，让 Engine 的双射校验
    将其收口为协议失败。
    """

    async def execute(self, request: BatchToolExecutionRequest) -> BatchToolExecutionOutcome:
        """拒绝 compactor 工具握手。

        :param request: Engine 发起的工具批式请求。
        :returns: 空批次 outcome。
        """

        del request
        return BatchToolExecutionOutcome(records=())


class LLMContextCompactor(ContextCompactor):
    """Host-owned LLM context compactor。

    :param runner_spec: compactor 独立 Runner 规约。
    :param runner_options: compactor 独立 Runner 调用参数。
    :param agent_policy: compactor 独立 Agent policy。
    :param system_prompt: Service 从 compactor scene 装配的 system prompt。
    :param user_prompt_template: Service 从 compactor baseline prompt asset
        装配的 user prompt template；必须包含
        ``<<compaction_request>>`` 占位符。
    """

    def __init__(
        self,
        *,
        runner_spec: RunnerSpec,
        runner_options: RunnerCallOptions,
        agent_policy: AgentPolicy,
        system_prompt: str,
        user_prompt_template: str,
    ) -> None:
        """初始化 Host-owned compactor。

        :param runner_spec: compactor 独立 Runner 规约。
        :param runner_options: compactor 独立 Runner 调用参数。
        :param agent_policy: compactor 独立 Agent policy。
        :param system_prompt: compactor system prompt。
        :param user_prompt_template: compactor user prompt template。
        :returns: ``None``。
        :raises TypeError: runner 或 prompt 参数类型非法时抛出。
        :raises ValueError: prompt 为空或 template 缺少占位符时抛出。
        """

        if not isinstance(runner_spec, RunnerSpec):
            raise TypeError("runner_spec must be RunnerSpec")
        if not isinstance(runner_options, RunnerCallOptions):
            raise TypeError("runner_options must be RunnerCallOptions")
        if not isinstance(agent_policy, AgentPolicy):
            raise TypeError("agent_policy must be AgentPolicy")
        if not isinstance(system_prompt, str):
            raise TypeError("system_prompt must be str")
        if system_prompt.strip() == "":
            raise ValueError("system_prompt must be non-empty")
        if not isinstance(user_prompt_template, str):
            raise TypeError("user_prompt_template must be str")
        if user_prompt_template.strip() == "":
            raise ValueError("user_prompt_template must be non-empty")
        if user_prompt_template.count(_COMPACTION_REQUEST_PLACEHOLDER) != 1:
            raise ValueError("user_prompt_template must contain exactly one " "<<compaction_request>> placeholder")
        self._runner_spec = runner_spec
        self._runner_options = runner_options
        self._agent_policy = agent_policy
        self._system_prompt = system_prompt
        self._user_prompt_template = user_prompt_template

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """执行一次 vNext LLM compaction proposal。

        :param request: Host 构造的 immutable compaction request。
        :param cancellation_token: Host run lifecycle 注入的真实取消 token。
        :returns: vNext compact output candidate。
        :raises TypeError: request 类型非法时抛出。
        :raises LLMCompactionProposalError: LLM 没有返回可用 structured proposal 时抛出。
        :raises Exception: Engine runner / provider 调用失败时透传。
        """

        if not isinstance(request, CompactionRequest):
            raise TypeError("request must be CompactionRequest")
        compact_input = conversation_compact_input_vnext_from_material_pack(
            request.material_pack
        )
        try:
            outcome = await _run_agent_request(
                _agent_request_vnext(
                    compact_input,
                    self._runner_spec,
                    self._runner_options,
                    self._agent_policy,
                    self._system_prompt,
                    self._user_prompt_template,
                    cancellation_token,
                ),
                timeout_seconds=self._runner_spec.default_timeout_seconds,
            )
        except TimeoutError as exc:
            _signal_timeout_cancellation(cancellation_token)
            raise LLMCompactionProposalError(_COMPACTOR_PROPOSAL_TIMEOUT_MESSAGE) from exc
        if not isinstance(outcome, EngineRunOutcomeFinalAnswer):
            raise LLMCompactionProposalError(_non_final_outcome_message(outcome))
        if outcome.finish_reason is FinishReason.LENGTH:
            raise LLMCompactionProposalError("compactor proposal was truncated finish_reason=length")
        return parse_conversation_compact_output_vnext(compact_input, outcome.content)



async def _run_agent_request(request: AgentRunRequest, *, timeout_seconds: float) -> AgentRunResult:
    """运行 Engine async public runner。

    :param request: Engine AgentRunRequest。
    :param timeout_seconds: compactor 单次 proposal 的总耗时上限。
    :returns: AgentRunResult。
    :raises BaseException: Engine async 调用抛出的异常会原样透传。
    """

    return await asyncio.wait_for(run_agent_and_wait(request), timeout=timeout_seconds)


def _signal_timeout_cancellation(cancellation_token: CancellationToken) -> None:
    """在 compactor timeout 时尽量通知 Host 可写取消 token。

    :param cancellation_token: Host 注入 Engine 的取消 token。
    :returns: ``None``。
    """

    if isinstance(cancellation_token, _CancellationSignalToken):
        cancellation_token.request_cancel(_COMPACTOR_PROPOSAL_TIMEOUT_CANCEL_REASON)


def _non_final_outcome_message(outcome: AgentRunResult) -> str:
    """构造非 final outcome 的脱敏 proposal 失败描述。

    :param outcome: Engine public runner 返回的非 final outcome。
    :returns: 不含密钥、headers 与完整 provider payload 的中性错误描述。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(outcome, EngineRunOutcomeFailed):
        return (
            "compactor runner failed "
            f"error_code={_safe_error_code(outcome.error_code)} "
            f"recoverable={outcome.recoverable} "
            f"message={_safe_outcome_text(outcome.message)}"
        )
    if isinstance(outcome, EngineRunOutcomeCancelled):
        return "compactor runner was cancelled"
    if isinstance(outcome, EngineRunOutcomeSuspended):
        return f"compactor runner suspended reason={_safe_outcome_text(outcome.reason)}"
    return "compactor runner did not return final answer"


def _safe_error_code(error_code: str) -> str:
    """返回可进入异常消息的中性错误码。

    :param error_code: Engine failed outcome 的错误码。
    :returns: 安全机器码；不符合机器码格式时返回 ``unknown_error``。
    :raises Exception: 不主动抛出异常。
    """

    if _SAFE_ERROR_CODE_PATTERN.fullmatch(error_code) is None:
        return "unknown_error"
    return error_code


def _safe_outcome_text(text: str) -> str:
    """脱敏并截断 provider / runner 错误摘要。

    :param text: 原始错误摘要。
    :returns: 可进入异常消息的短文本。
    :raises Exception: 不主动抛出异常。
    """

    redacted = redact_sensitive_diagnostic_values(text, redaction_marker=_REDACTED_SECRET)
    return truncate_diagnostic_text(
        redacted,
        max_chars=_MAX_SAFE_OUTCOME_MESSAGE_CHARS,
        truncated_suffix=_TRUNCATED_SUFFIX,
    )


def _agent_request_vnext(
    request: ConversationCompactInputVNext,
    runner_spec: RunnerSpec,
    runner_options: RunnerCallOptions,
    agent_policy: AgentPolicy,
    system_prompt: str,
    user_prompt_template: str,
    cancellation_token: CancellationToken,
) -> AgentRunRequest:
    """构造 vNext 禁用工具的 Engine public run request。

    :param request: vNext compaction input。
    :param runner_spec: compactor Runner 规约。
    :param runner_options: compactor Runner 调用参数。
    :param agent_policy: compactor Agent policy。
    :param system_prompt: compactor system prompt。
    :param user_prompt_template: compactor user prompt template。
    :param cancellation_token: Host cancellation token。
    :returns: Engine run request。
    """

    return AgentRunRequest(
        run_id=f"{_COMPACTOR_RUN_ID_PREFIX}-vnext-{uuid4().hex}",
        session_id=f"{_COMPACTOR_RUN_ID_PREFIX}:vnext",
        attempt_id=None,
        execution_id=None,
        messages=(
            SystemMessage(role=AgentMessageRole.SYSTEM, content=system_prompt),
            UserMessage(
                role=AgentMessageRole.USER,
                content=_user_prompt_vnext(request, user_prompt_template),
            ),
        ),
        disable_tools=True,
        runner_spec=runner_spec,
        runner_options=runner_options,
        agent_policy=agent_policy,
        tool_schemas=(),
        tool_executor=_RejectingToolExecutor(),
        cancellation_token=cancellation_token,
    )


def _user_prompt_vnext(
    request: ConversationCompactInputVNext, user_prompt_template: str
) -> str:
    """渲染 vNext compactor user prompt。

    :param request: vNext compactor input。
    :param user_prompt_template: 包含唯一 compaction request 占位符的模板。
    :returns: 已嵌入 vNext compaction request 数据块的 user prompt。
    """

    return user_prompt_template.replace(
        _COMPACTION_REQUEST_PLACEHOLDER,
        _compaction_request_prompt_block_vnext(request),
    )



def _compaction_request_prompt_block_vnext(request: ConversationCompactInputVNext) -> str:
    """构造 vNext compactor request 数据块。

    :param request: vNext compactor input。
    :returns: compaction request prompt 数据块。
    """

    material_json = json.dumps(
        request.to_json(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (
        f"{_UNTRUSTED_COMPACTION_MATERIAL_BEGIN}\n"
        f"{material_json}\n"
        f"{_UNTRUSTED_COMPACTION_MATERIAL_END}"
    )


def parse_conversation_compact_output_vnext(
    request: ConversationCompactInputVNext,
    final_answer: str,
) -> ConversationCompactOutputVNext:
    """解析并校验 vNext strict JSON compact output。

    :param request: vNext compactor input。
    :param final_answer: LLM 返回的 strict JSON 文本。
    :returns: vNext compact output candidate。
    :raises TypeError: request 类型非法时抛出。
    :raises LLMCompactionProposalError: JSON 解析、schema 或 label contract 非法时抛出。
    """

    if not isinstance(request, ConversationCompactInputVNext):
        raise TypeError("request must be ConversationCompactInputVNext")
    proposal = _parse_vnext_proposal(final_answer)
    try:
        candidate = ConversationCompactOutputVNext(
            schema_version=_required_string(proposal, "schema_version"),
            session_summary=_session_summary_candidate_vnext(proposal),
            evidence_backed_facts=_fact_candidates_vnext(proposal),
            answer_anchors=_answer_anchor_candidates_vnext(proposal),
            forward_intents=_forward_intent_candidates_vnext(proposal),
            reference_continuity_items=_reference_candidates_vnext(proposal),
            diagnostics=_diagnostics_vnext(proposal),
        )
        _validate_vnext_candidate_source_labels(request, candidate)
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMCompactionProposalError(f"compactor vNext proposal schema invalid: {exc}") from exc
    return candidate


def _parse_vnext_proposal(final_answer: str) -> Mapping[str, JsonValue]:
    """解析 vNext LLM strict JSON proposal。

    :param final_answer: LLM final answer 原文。
    :returns: top-level JSON object。
    :raises LLMCompactionProposalError: 空文本、非 JSON 或缺少必需字段时抛出。
    """

    raw = final_answer.strip()
    if len(raw) < _MIN_PROPOSAL_LENGTH:
        raise LLMCompactionProposalError("compactor vNext proposal is empty")
    try:
        parsed = json.loads(raw)
    except JSONDecodeError as exc:
        raise LLMCompactionProposalError(f"compactor vNext proposal is not valid JSON: {exc.msg}") from exc
    if not isinstance(parsed, Mapping):
        raise LLMCompactionProposalError("compactor vNext proposal top-level value must be object")
    proposal = cast(Mapping[str, JsonValue], parsed)
    required_keys = (
        "schema_version",
        "session_summary",
        "evidence_backed_facts",
        "answer_anchors",
        "forward_intents",
        "reference_continuity_items",
        "diagnostics",
    )
    for key in required_keys:
        if key not in proposal:
            raise LLMCompactionProposalError(f"compactor vNext proposal missing required key: {key}")
    return proposal


def _session_summary_candidate_vnext(
    proposal: Mapping[str, JsonValue],
) -> SessionSummaryCandidateVNext | None:
    """解析 vNext session summary candidate。

    :param proposal: 已解析 proposal。
    :returns: session summary candidate；JSON null 时为 ``None``。
    """

    value = proposal["session_summary"]
    if value is None:
        return None
    data = _json_mapping(value, "session_summary")
    return SessionSummaryCandidateVNext(
        summary_text=_required_string(data, "summary_text"),
        source_labels=_required_string_tuple(data, "source_labels"),
    )


def _fact_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[EvidenceBackedFactCandidateVNext, ...]:
    """解析 vNext evidence-backed fact candidates。

    :param proposal: 已解析 proposal。
    :returns: fact candidate tuple。
    """

    values = _required_sequence(proposal, "evidence_backed_facts", max_items=MAX_VNEXT_FACT_ITEMS)
    candidates: list[EvidenceBackedFactCandidateVNext] = []
    for index, item in enumerate(values):
        data = _json_mapping(item, f"evidence_backed_facts[{index}]")
        candidates.append(
            EvidenceBackedFactCandidateVNext(
                claim_text=_required_string(data, "claim_text"),
                evidence_labels=_required_string_tuple(data, "evidence_labels"),
                evidence_kind=FactEvidenceKindVNext(_required_string(data, "evidence_kind")),
                source_labels=_optional_string_tuple(data, "source_labels"),
            )
        )
    return tuple(candidates)


def _answer_anchor_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[AnswerAnchorCandidateVNext, ...]:
    """解析 vNext answer anchor candidates。

    :param proposal: 已解析 proposal。
    :returns: answer anchor candidate tuple。
    """

    values = _required_sequence(proposal, "answer_anchors", max_items=MAX_VNEXT_ANSWER_ANCHOR_ITEMS)
    candidates: list[AnswerAnchorCandidateVNext] = []
    for index, item in enumerate(values):
        data = _json_mapping(item, f"answer_anchors[{index}]")
        candidates.append(
            AnswerAnchorCandidateVNext(
                anchor_title=_required_string(data, "anchor_title"),
                anchor_items=_answer_anchor_children_vnext(data, f"answer_anchors[{index}].anchor_items"),
                answer_source_labels=_required_string_tuple(data, "answer_source_labels"),
            )
        )
    return tuple(candidates)


def _answer_anchor_children_vnext(
    source: Mapping[str, JsonValue],
    field_name: str,
) -> tuple[AnswerAnchorChildVNext, ...]:
    """解析 vNext answer anchor children。

    :param source: answer anchor JSON object。
    :param field_name: 错误字段名。
    :returns: answer anchor child tuple。
    """

    values = _required_sequence(source, "anchor_items", max_items=MAX_VNEXT_ANSWER_ANCHOR_ITEMS)
    children: list[AnswerAnchorChildVNext] = []
    for index, item in enumerate(values):
        data = _json_mapping(item, f"{field_name}[{index}]")
        children.append(
            AnswerAnchorChildVNext(
                display_text=_required_string(data, "display_text"),
                ordinal=_optional_int_or_none(data, "ordinal"),
            )
        )
    return tuple(children)


def _forward_intent_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[ForwardIntentCandidateVNext, ...]:
    """解析 vNext forward intent candidates。

    :param proposal: 已解析 proposal。
    :returns: forward intent candidate tuple。
    """

    values = _required_sequence(proposal, "forward_intents", max_items=MAX_VNEXT_FORWARD_INTENT_ITEMS)
    candidates: list[ForwardIntentCandidateVNext] = []
    for index, item in enumerate(values):
        data = _json_mapping(item, f"forward_intents[{index}]")
        candidates.append(
            ForwardIntentCandidateVNext(
                intent_type=ForwardIntentTypeVNext(_required_string(data, "intent_type")),
                text=_required_string(data, "text"),
                status=ForwardIntentStatusVNext(_required_string(data, "status")),
                source_labels=_required_string_tuple(data, "source_labels"),
            )
        )
    return tuple(candidates)


def _reference_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[ReferenceContinuityCandidateVNext, ...]:
    """解析 vNext reference continuity candidates。

    :param proposal: 已解析 proposal。
    :returns: reference continuity candidate tuple。
    """

    values = _required_sequence(
        proposal,
        "reference_continuity_items",
        max_items=MAX_VNEXT_REFERENCE_CONTINUITY_ITEMS,
    )
    candidates: list[ReferenceContinuityCandidateVNext] = []
    for index, item in enumerate(values):
        data = _json_mapping(item, f"reference_continuity_items[{index}]")
        candidates.append(
            ReferenceContinuityCandidateVNext(
                text=_required_string(data, "text"),
                reason=ReferenceContinuityReasonVNext(_required_string(data, "reason")),
                source_labels=_required_string_tuple(data, "source_labels"),
            )
        )
    return tuple(candidates)


def _diagnostics_vnext(proposal: Mapping[str, JsonValue]) -> tuple[CompactCandidateDiagnosticVNext, ...]:
    """解析 vNext compact diagnostics。

    :param proposal: 已解析 proposal。
    :returns: diagnostic tuple。
    """

    values = _required_sequence(proposal, "diagnostics", max_items=MAX_VNEXT_DIAGNOSTIC_ITEMS)
    diagnostics: list[CompactCandidateDiagnosticVNext] = []
    for index, item in enumerate(values):
        data = _json_mapping(item, f"diagnostics[{index}]")
        diagnostics.append(
            CompactCandidateDiagnosticVNext(
                code=_required_string(data, "code"),
                text=_required_string(data, "text"),
                source_labels=_optional_string_tuple(data, "source_labels"),
            )
        )
    return tuple(diagnostics)


def _validate_vnext_candidate_source_labels(
    request: ConversationCompactInputVNext,
    candidate: ConversationCompactOutputVNext,
) -> None:
    """校验 vNext candidate source labels 的 section allowlist。

    :param request: vNext compactor input。
    :param candidate: vNext compact output。
    :returns: ``None``。
    :raises ValueError: label 未知、stale、跨 section 或 current anchor 被引用时抛出。
    """

    if candidate.session_summary is not None:
        _validate_vnext_labels(
            request,
            candidate.session_summary.source_labels,
            field_name="session_summary.source_labels",
            allowed_sections=CONVERSATION_COMPACT_SUMMARY_SOURCE_SECTIONS_VNEXT,
        )
    for index, fact in enumerate(candidate.evidence_backed_facts):
        _validate_vnext_labels(
            request,
            fact.evidence_labels,
            field_name=f"evidence_backed_facts[{index}].evidence_labels",
            allowed_sections=CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT,
        )
        _validate_vnext_labels(
            request,
            fact.source_labels,
            field_name=f"evidence_backed_facts[{index}].source_labels",
            allowed_sections=CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT,
            allow_empty=True,
        )
    for index, anchor in enumerate(candidate.answer_anchors):
        _validate_vnext_labels(
            request,
            anchor.answer_source_labels,
            field_name=f"answer_anchors[{index}].answer_source_labels",
            allowed_sections=CONVERSATION_COMPACT_ANSWER_SOURCE_SECTIONS_VNEXT,
        )
    for index, intent in enumerate(candidate.forward_intents):
        _validate_vnext_labels(
            request,
            intent.source_labels,
            field_name=f"forward_intents[{index}].source_labels",
            allowed_sections=CONVERSATION_COMPACT_FORWARD_SOURCE_SECTIONS_VNEXT,
        )
    for index, item in enumerate(candidate.reference_continuity_items):
        _validate_vnext_labels(
            request,
            item.source_labels,
            field_name=f"reference_continuity_items[{index}].source_labels",
            allowed_sections=CONVERSATION_COMPACT_REFERENCE_SOURCE_SECTIONS_VNEXT,
        )
    for index, diagnostic in enumerate(candidate.diagnostics):
        _validate_vnext_labels(
            request,
            diagnostic.source_labels,
            field_name=f"diagnostics[{index}].source_labels",
            allowed_sections=CONVERSATION_COMPACT_DIAGNOSTIC_SOURCE_SECTIONS_VNEXT,
            allow_empty=True,
        )


def _validate_vnext_labels(
    request: ConversationCompactInputVNext,
    labels: tuple[str, ...],
    *,
    field_name: str,
    allowed_sections: tuple[ConversationCompactLabelSectionVNext, ...],
    allow_empty: bool = False,
) -> None:
    """校验 vNext prompt-local labels。

    :param request: vNext compactor input。
    :param labels: 待校验 labels。
    :param field_name: 错误字段名。
    :param allowed_sections: 允许引用的 section。
    :param allow_empty: 是否允许空 labels。
    :returns: ``None``。
    :raises ValueError: label 缺失、未知、stale、跨 section 或 current anchor 被引用时抛出。
    """

    if not allow_empty and len(labels) == 0:
        raise ValueError(f"{field_name} missing source label")
    for label in labels:
        section = request.source_section(label)
        if section is ConversationCompactLabelSectionVNext.CURRENT_INPUT_ANCHOR:
            raise ValueError(f"{field_name} cites current input anchor: {label}")
        if section is None:
            if conversation_compact_label_looks_stale_vnext(label):
                raise ValueError(f"{field_name} contains stale source label: {label}")
            raise ValueError(f"{field_name} contains unknown source label: {label}")
        if section not in allowed_sections:
            raise ValueError(f"{field_name} contains cross-section label: {label}")



def _required_mapping(source: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue]:
    """读取必需 JSON object 字段。

    :param source: JSON object。
    :param key: 字段名。
    :returns: JSON object 字段值。
    :raises KeyError: 字段缺失时抛出。
    :raises TypeError: 字段不是 object 时抛出。
    """

    if key not in source:
        raise KeyError(f"{key} is required")
    return _json_mapping(source[key], key)


def _json_mapping(value: JsonValue, field_name: str) -> Mapping[str, JsonValue]:
    """校验 JSON 值为 object。

    :param value: JSON 值。
    :param field_name: 错误字段名。
    :returns: JSON object。
    :raises TypeError: 值不是 object 时抛出。
    """

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be object")
    return value


def _required_sequence(
    source: Mapping[str, JsonValue],
    key: str,
    *,
    max_items: int,
) -> tuple[JsonValue, ...]:
    """读取必需 JSON array 字段。

    :param source: JSON object。
    :param key: 字段名。
    :param max_items: 数组元素上限。
    :returns: JSON 值 tuple。
    :raises KeyError: 字段缺失时抛出。
    :raises TypeError: 字段不是 array 时抛出。
    :raises ValueError: 数组超过上限时抛出。
    """

    if key not in source:
        raise KeyError(f"{key} is required")
    value = source[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} must be array")
    if len(value) > max_items:
        raise ValueError(f"{key} exceeds maximum item count")
    return tuple(value)


def _required_string(source: Mapping[str, JsonValue], key: str) -> str:
    """读取必需字符串字段。

    :param source: JSON object。
    :param key: 字段名。
    :returns: 字符串值。
    :raises KeyError: 字段缺失时抛出。
    :raises TypeError: 字段不是字符串时抛出。
    """

    if key not in source:
        raise KeyError(f"{key} is required")
    value = source[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be string")
    return value


def _optional_string_or_none(source: Mapping[str, JsonValue], key: str) -> str | None:
    """读取可选字符串或 null 字段。

    :param source: JSON object。
    :param key: 字段名。
    :returns: 字符串、``None`` 或缺省时的 ``None``。
    :raises TypeError: 字段既不是字符串也不是 null 时抛出。
    """

    if key not in source:
        return None
    value = source[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be string or null")
    return value


def _optional_int_or_none(source: Mapping[str, JsonValue], key: str) -> int | None:
    """读取可选整数或 null 字段。

    :param source: JSON object。
    :param key: 字段名。
    :returns: 整数、``None`` 或缺省时的 ``None``。
    :raises TypeError: 字段既不是整数也不是 null 时抛出。
    """

    if key not in source:
        return None
    value = source[key]
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be integer or null")
    return value


def _optional_string_tuple(source: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    """读取可选字符串数组字段。

    :param source: JSON object。
    :param key: 字段名。
    :returns: 字符串 tuple；缺省时为空 tuple。
    :raises TypeError: 字段不是字符串数组时抛出。
    """

    if key not in source:
        return ()
    return _string_tuple(source[key], key)


def _required_string_tuple(source: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    """读取必需字符串数组字段。

    :param source: JSON object。
    :param key: 字段名。
    :returns: 字符串 tuple。
    :raises KeyError: 字段缺失时抛出。
    :raises TypeError: 字段不是字符串数组时抛出。
    """

    if key not in source:
        raise KeyError(f"{key} is required")
    return _string_tuple(source[key], key)


def _optional_string_tuple_or_none(source: Mapping[str, JsonValue], key: str) -> tuple[str, ...] | None:
    """读取字符串数组或 null 字段。

    :param source: JSON object。
    :param key: 字段名。
    :returns: 字符串 tuple、``None`` 或缺省时的 ``None``。
    :raises TypeError: 字段既不是字符串数组也不是 null 时抛出。
    """

    if key not in source:
        return None
    value = source[key]
    if value is None:
        return None
    return _string_tuple(value, key)


def _string_tuple(value: JsonValue, field_name: str) -> tuple[str, ...]:
    """校验 JSON 值为字符串数组。

    :param value: JSON 值。
    :param field_name: 错误字段名。
    :returns: 字符串 tuple。
    :raises TypeError: 值不是字符串数组时抛出。
    """

    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be array")
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"{field_name}[{index}] must be string")
        strings.append(item)
    return tuple(strings)


def _bounded_known_refs(
    refs: tuple[str, ...],
    *,
    allowed_refs: tuple[str, ...],
    field_name: str,
) -> tuple[str, ...]:
    """校验 refs 只引用 Host request 中已知 refs。

    :param refs: 待校验 refs。
    :param allowed_refs: 允许引用的 refs。
    :param field_name: 错误字段名。
    :returns: 原 refs。
    :raises ValueError: 出现未知 ref 时抛出。
    """

    allowed = frozenset(allowed_refs)
    for ref in refs:
        if ref not in allowed:
            raise ValueError(f"{field_name} contains unknown ref: {ref}")
    return refs



__all__ = ["LLMCompactionProposalError", "LLMContextCompactor"]
