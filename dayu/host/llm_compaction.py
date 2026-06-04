"""Host-owned LLM context compactor。

本模块把 Host ``CompactionRequest`` 映射为一次禁用工具的 Engine public
runner 调用，并把 LLM final answer 的 strict JSON proposal 转换为
Host-owned ``CompactionCandidate``。它不写 EventLog、不写 artifact、不做
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
from dayu.host.compact_material import validate_material_label
from dayu.host.compact_material import conversation_compact_input_vnext_from_material_pack
from dayu.host.compaction import (
    AnswerAnchorCandidateVNext,
    AnswerAnchorChildVNext,
    CONVERSATION_COMPACT_ANSWER_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_DIAGNOSTIC_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_FORWARD_SOURCE_SECTIONS_VNEXT,
    CompactInputRange,
    CompactMaterialSection,
    CompactCandidateDiagnosticVNext,
    CONVERSATION_COMPACT_REFERENCE_SOURCE_SECTIONS_VNEXT,
    CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
    CONVERSATION_COMPACT_SUMMARY_SOURCE_SECTIONS_VNEXT,
    CompactionCandidate,
    CompactionRequest,
    ConversationCompactInputVNext,
    ConversationCompactLabelSectionVNext,
    ConversationCompactOutputVNext,
    ContextCompactor,
    EpisodeSummaryCandidate,
    EvidenceBackedFactCandidate,
    EvidenceBackedFactKind,
    EvidenceBackedFactCandidateVNext,
    FactEvidenceKindVNext,
    ForwardIntentCandidateVNext,
    ForwardIntentStatusVNext,
    ForwardIntentTypeVNext,
    MAX_EVIDENCE_BACKED_FACT_CANDIDATES,
    MAX_VNEXT_ANSWER_ANCHOR_ITEMS,
    MAX_VNEXT_DIAGNOSTIC_ITEMS,
    MAX_VNEXT_FACT_ITEMS,
    MAX_VNEXT_FORWARD_INTENT_ITEMS,
    MAX_VNEXT_REFERENCE_CONTINUITY_ITEMS,
    MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES,
    MinimumPreserveItemCandidate,
    MinimumPreserveReason,
    PinnedPatchOperation,
    PinnedStatePatchCandidate,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
    PromptLocalProvenanceEntry,
    PreservationEvidence,
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
from dayu.host.opaque_ref import validate_host_neutral_opaque_ref_text
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
    "Host post-compact run context includes compact summary, pinned state, "
    "current input, preserved refs, evidence-backed facts, and continuity items."
)
_POST_COMPACT_BASE_MESSAGE_COUNT = 2
_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT = 1
_REQUIRED_PROPOSAL_KEYS = (
    "episode_summary_candidate",
    "pinned_state_patch_candidate",
    "evidence_backed_fact_candidates",
    "minimum_preserve_item_candidates",
    "preservation_evidence",
    "retained_current_input_label",
    "preserved_material_labels",
    "preserved_evidence_labels",
    "preserved_evidence_backed_fact_refs",
    "dropped_ranges",
    "summarized_ranges",
)
_MATERIAL_LABEL_SECTIONS = (
    CompactMaterialSection.STABLE_INPUT,
    CompactMaterialSection.HISTORY_INPUT,
    CompactMaterialSection.EVIDENCE_INPUT,
    CompactMaterialSection.CURRENT_INPUT_ANCHOR,
)
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

    async def compact(self, request: CompactionRequest, cancellation_token: CancellationToken) -> CompactionCandidate:
        """执行一次 LLM compaction proposal。

        :param request: Host 构造的 immutable compaction request。
        :param cancellation_token: Host run lifecycle 注入的真实取消 token。
        :returns: Host-owned candidate。
        :raises TypeError: request 类型非法时抛出。
        :raises LLMCompactionProposalError: LLM 没有返回可用 structured proposal 时抛出。
        :raises Exception: Engine runner / provider 调用失败时透传。
        """

        if not isinstance(request, CompactionRequest):
            raise TypeError("request must be CompactionRequest")
        try:
            outcome = await _run_agent_request(
                _agent_request(
                    request,
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
        return _candidate_from_final_answer(request, outcome.content)

    async def compact_vnext(
        self,
        request: ConversationCompactInputVNext,
        cancellation_token: CancellationToken,
    ) -> ConversationCompactOutputVNext:
        """执行一次 vNext LLM compaction proposal。

        该方法是 Slice A 的局部 contract 入口，不替换旧 production
        ``compact`` operation，也不把 vNext output 桥接回旧 candidate。

        :param request: vNext compactor 输入。
        :param cancellation_token: Host run lifecycle 注入的真实取消 token。
        :returns: vNext compact output candidate。
        :raises TypeError: request 类型非法时抛出。
        :raises LLMCompactionProposalError: LLM 没有返回可用 structured proposal 时抛出。
        :raises Exception: Engine runner / provider 调用失败时透传。
        """

        if not isinstance(request, ConversationCompactInputVNext):
            raise TypeError("request must be ConversationCompactInputVNext")
        try:
            outcome = await _run_agent_request(
                _agent_request_vnext(
                    request,
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
        return parse_conversation_compact_output_vnext(request, outcome.content)

    async def compact_request_vnext(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
    ) -> ConversationCompactOutputVNext:
        """执行一次 operation-level vNext LLM compaction proposal。

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
        return await self.compact_vnext(compact_input, cancellation_token)


def _agent_request(
    request: CompactionRequest,
    runner_spec: RunnerSpec,
    runner_options: RunnerCallOptions,
    agent_policy: AgentPolicy,
    system_prompt: str,
    user_prompt_template: str,
    cancellation_token: CancellationToken,
) -> AgentRunRequest:
    """构造禁用工具的 Engine public run request。

    :param request: Host compaction request。
    :param runner_spec: compactor Runner 规约。
    :param runner_options: compactor Runner 调用参数。
    :param agent_policy: compactor Agent policy。
    :param system_prompt: compactor system prompt。
    :param user_prompt_template: compactor user prompt template。
    :param cancellation_token: Host 注入 Engine 的真实取消 token。
    :returns: Engine AgentRunRequest。
    """

    return AgentRunRequest(
        run_id=f"{_COMPACTOR_RUN_ID_PREFIX}-{request.run_id}-{uuid4().hex}",
        session_id=request.session_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        messages=(
            SystemMessage(role=AgentMessageRole.SYSTEM, content=system_prompt),
            UserMessage(
                role=AgentMessageRole.USER,
                content=_user_prompt(request, user_prompt_template),
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


def _user_prompt(request: CompactionRequest, template: str) -> str:
    """用 baseline template 构造 Host-owned compactor user prompt。

    :param request: Host compaction request。
    :param template: Service 从 compactor baseline prompt asset 读取的 user
        prompt template。
    :returns: 用户消息文本。
    """

    return template.replace(
        _COMPACTION_REQUEST_PLACEHOLDER,
        _compaction_request_prompt_block(request),
    )


def _user_prompt_vnext(request: ConversationCompactInputVNext, template: str) -> str:
    """用 baseline template 构造 vNext compactor user prompt。

    :param request: vNext compactor input。
    :param template: Service 从 compactor baseline prompt asset 读取的 user prompt template。
    :returns: 用户消息文本。
    """

    return template.replace(
        _COMPACTION_REQUEST_PLACEHOLDER,
        _compaction_request_prompt_block_vnext(request),
    )


def _compaction_request_prompt_block(request: CompactionRequest) -> str:
    """构造 compactor request 数据块。

    该函数只渲染 material pack 的四个 LLM-facing section，不读取
    EventLog、accepted evidence envelope 或 Host ledger helper；任务指令与
    schema 由 compactor scene prompt template 提供。

    :param request: Host compaction request。
    :returns: compaction request prompt 数据块。
    """

    material_json = json.dumps(
        request.llm_material_json(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (
        f"{_UNTRUSTED_COMPACTION_MATERIAL_BEGIN}\n"
        f"{material_json}\n"
        f"{_UNTRUSTED_COMPACTION_MATERIAL_END}"
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


def _candidate_from_final_answer(request: CompactionRequest, final_answer: str) -> CompactionCandidate:
    """把 LLM strict JSON final answer 映射为 Host-owned candidate。

    :param request: Host compaction request。
    :param final_answer: LLM 返回的 strict JSON 文本。
    :returns: CompactionCandidate。
    :raises LLMCompactionProposalError: JSON 解析、schema 或值校验失败时抛出。
    """

    proposal = _parse_proposal(final_answer)
    try:
        evidence = _preservation_evidence(request, proposal)
        evidence_refs = tuple(item.evidence_id for item in evidence)
        episode = _episode_summary_candidate(request, proposal, evidence_refs)
        pinned_patch = _pinned_state_patch_candidate(proposal, evidence_refs, run_id=request.run_id)
        fact_candidates = _evidence_backed_fact_candidates(request, proposal)
        preserve_items = _minimum_preserve_item_candidates(request, proposal)
        retained_current_input = _retained_current_user_input_ref(request, proposal)
        preserved_material_refs = _canonical_refs_for_labels(
            request,
            _required_string_tuple(proposal, "preserved_material_labels"),
            field_name="preserved_material_labels",
        )
        preserved_evidence_refs = _canonical_evidence_refs_for_labels(
            request,
            _required_string_tuple(proposal, "preserved_evidence_labels"),
            field_name="preserved_evidence_labels",
        )
        preserved_fact_refs = _bounded_known_refs(
            _required_string_tuple(proposal, "preserved_evidence_backed_fact_refs"),
            allowed_refs=request.evidence_backed_fact_refs,
            field_name="preserved_evidence_backed_fact_refs",
        )
        dropped_ranges = _range_tuple(
            proposal,
            "dropped_ranges",
            request=request,
        )
        summarized_ranges = _range_tuple(
            proposal,
            "summarized_ranges",
            request=request,
        )
        return CompactionCandidate(
            candidate_id=f"llm-compact:{request.run_id}",
            episode_summary_candidate=episode,
            pinned_state_patch_candidate=pinned_patch,
            preservation_evidence=evidence,
            evidence_backed_fact_candidates=fact_candidates,
            minimum_preserve_item_candidates=preserve_items,
            retained_current_user_input_ref=retained_current_input,
            preserved_material_source_refs=preserved_material_refs,
            preserved_canonical_evidence_refs=preserved_evidence_refs,
            preserved_evidence_backed_fact_refs=preserved_fact_refs,
            dropped_ranges=dropped_ranges,
            summarized_ranges=summarized_ranges,
            budget_after_compact=_budget_after_compact(
                request,
                episode,
                pinned_patch,
                fact_candidates,
                preserve_items,
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMCompactionProposalError(f"compactor proposal schema invalid: {exc}") from exc


def _parse_proposal(final_answer: str) -> Mapping[str, JsonValue]:
    """解析 LLM strict JSON proposal。

    :param final_answer: LLM final answer 原文。
    :returns: top-level JSON object。
    :raises LLMCompactionProposalError: 空文本、非 JSON 或缺少必需字段时抛出。
    """

    raw = final_answer.strip()
    if len(raw) < _MIN_PROPOSAL_LENGTH:
        raise LLMCompactionProposalError("compactor proposal is empty")
    try:
        parsed = json.loads(raw)
    except JSONDecodeError as exc:
        raise LLMCompactionProposalError(f"compactor proposal is not valid JSON: {exc.msg}") from exc
    if not isinstance(parsed, Mapping):
        raise LLMCompactionProposalError("compactor proposal top-level value must be object")
    proposal = cast(Mapping[str, JsonValue], parsed)
    for key in _REQUIRED_PROPOSAL_KEYS:
        if key not in proposal:
            raise LLMCompactionProposalError(f"compactor proposal missing required key: {key}")
    return proposal


def _episode_summary_candidate(
    request: CompactionRequest,
    proposal: Mapping[str, JsonValue],
    evidence_refs: tuple[str, ...],
) -> EpisodeSummaryCandidate:
    """从 proposal 构造 episode summary candidate。

    :param request: Host compaction request。
    :param proposal: 已解析 proposal。
    :param evidence_refs: Host-owned preservation evidence refs。
    :returns: episode summary candidate。
    """

    data = _required_mapping(proposal, "episode_summary_candidate")
    tool_finding_refs = _bounded_known_refs(
        _canonical_evidence_refs_for_labels(
            request,
            _optional_string_tuple(data, "tool_finding_labels"),
            field_name="episode_summary_candidate.tool_finding_labels",
        ),
        allowed_refs=request.canonical_evidence_refs,
        field_name="episode_summary_candidate.tool_finding_refs",
    )
    confirmed_fact_refs = _bounded_known_refs(
        _optional_string_tuple(data, "confirmed_fact_refs"),
        allowed_refs=request.evidence_backed_fact_refs,
        field_name="episode_summary_candidate.confirmed_fact_refs",
    )
    return EpisodeSummaryCandidate(
        candidate_id=f"llm-summary:{request.run_id}",
        episode_title=_required_string(data, "episode_title"),
        goal=_required_string(data, "goal"),
        completed_actions=_optional_string_tuple(data, "completed_actions"),
        confirmed_fact_refs=confirmed_fact_refs,
        confirmed_fact_summaries=_optional_string_tuple(data, "confirmed_fact_summaries"),
        user_constraints=_optional_string_tuple(data, "user_constraints"),
        open_questions=_optional_string_tuple(data, "open_questions"),
        next_step=_optional_string_or_none(data, "next_step"),
        tool_finding_refs=tool_finding_refs,
        source_event_refs=request.material_source_refs,
        evidence_refs=evidence_refs,
    )


def _pinned_state_patch_candidate(
    proposal: Mapping[str, JsonValue],
    evidence_refs: tuple[str, ...],
    *,
    run_id: str,
) -> PinnedStatePatchCandidate:
    """从 proposal 构造 pinned state patch candidate。

    :param proposal: 已解析 proposal。
    :param evidence_refs: Host-owned preservation evidence refs。
    :param run_id: Host run id，用于生成 Host-owned candidate id。
    :returns: pinned state patch candidate。
    """

    data = _required_mapping(proposal, "pinned_state_patch_candidate")
    return PinnedStatePatchCandidate(
        candidate_id=f"llm-pinned-patch:{run_id}",
        current_goal=_text_patch(data, "current_goal", evidence_refs),
        confirmed_subjects=_confirmed_subjects_patch(data, "confirmed_subjects", evidence_refs),
        user_constraints=_string_tuple_patch(data, "user_constraints", evidence_refs),
        open_questions=_string_tuple_patch(data, "open_questions", evidence_refs),
    )


def _evidence_backed_fact_candidates(
    request: CompactionRequest, proposal: Mapping[str, JsonValue]
) -> tuple[EvidenceBackedFactCandidate, ...]:
    """从 proposal 构造 evidence-backed fact candidates。

    :param request: Host compaction request。
    :param proposal: 已解析 proposal。
    :returns: fact candidate tuple。
    :raises ValueError: evidence_refs 不在 request canonical evidence refs 内时抛出。
    """

    values = _required_sequence(
        proposal,
        "evidence_backed_fact_candidates",
        max_items=MAX_EVIDENCE_BACKED_FACT_CANDIDATES,
    )
    candidates: list[EvidenceBackedFactCandidate] = []
    for index, item in enumerate(values):
        data = _json_mapping(item, f"evidence_backed_fact_candidates[{index}]")
        evidence_refs = _canonical_evidence_refs_for_labels(
            request,
            _required_string_tuple(data, "evidence_labels"),
            field_name=f"evidence_backed_fact_candidates[{index}].evidence_refs",
            require_non_empty=True,
        )
        candidates.append(
            EvidenceBackedFactCandidate(
                candidate_id=_required_string(data, "candidate_id"),
                claim_text=_required_string(data, "claim_text"),
                evidence_kind=EvidenceBackedFactKind(_required_string(data, "evidence_kind")),
                evidence_refs=evidence_refs,
                attributes=_required_mapping(data, "attributes"),
            )
        )
    return tuple(candidates)


def _minimum_preserve_item_candidates(
    request: CompactionRequest, proposal: Mapping[str, JsonValue]
) -> tuple[MinimumPreserveItemCandidate, ...]:
    """从 proposal 构造 minimum preserve item candidates。

    :param request: Host compaction request。
    :param proposal: 已解析 proposal。
    :returns: minimum preserve item candidate tuple。
    """

    values = _required_sequence(
        proposal,
        "minimum_preserve_item_candidates",
        max_items=MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES,
    )
    candidates: list[MinimumPreserveItemCandidate] = []
    for index, item in enumerate(values):
        data = _json_mapping(item, f"minimum_preserve_item_candidates[{index}]")
        source_refs = _canonical_refs_for_labels(
            request,
            _required_string_tuple(data, "source_labels"),
            field_name=f"minimum_preserve_item_candidates[{index}].source_labels",
        )
        candidates.append(
            MinimumPreserveItemCandidate(
                item_id=_required_string(data, "item_id"),
                label=_required_string(data, "label"),
                text=_required_string(data, "text"),
                source_refs=source_refs,
                preserve_reason=MinimumPreserveReason(_required_string(data, "preserve_reason")),
            )
        )
    return tuple(candidates)


def _retained_current_user_input_ref(request: CompactionRequest, proposal: Mapping[str, JsonValue]) -> str | None:
    """读取并校验 retained current user input ref。

    :param request: Host compaction request。
    :param proposal: 已解析 proposal。
    :returns: retained current user input ref；JSON null 时为 ``None``。
    :raises ValueError: ref 不属于当前用户输入时抛出。
    """

    value = proposal["retained_current_input_label"]
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("retained_current_input_label must be string or null")
    if value != request.material_pack.current_input_anchor.anchor_label:
        raise ValueError("retained_current_input_label must match request current input")
    return request.current_input_ref


def _text_patch(
    source: Mapping[str, JsonValue],
    key: str,
    evidence_refs: tuple[str, ...],
) -> PinnedTextFieldPatch:
    """解析 pinned 文本 patch。

    :param source: JSON object。
    :param key: patch 字段名。
    :param evidence_refs: Host-owned evidence refs。
    :returns: 文本 patch。
    """

    data = _required_mapping(source, key)
    operation = PinnedPatchOperation(_required_string(data, "operation"))
    value = _optional_string_or_none(data, "value")
    _validate_patch_value(operation, value, field_name=key)
    return PinnedTextFieldPatch(
        operation=operation,
        value=value,
        evidence_refs=_evidence_refs_for_patch(operation, evidence_refs),
    )


def _string_tuple_patch(
    source: Mapping[str, JsonValue],
    key: str,
    evidence_refs: tuple[str, ...],
) -> PinnedStringTupleFieldPatch:
    """解析 pinned 字符串 tuple patch。

    :param source: JSON object。
    :param key: patch 字段名。
    :param evidence_refs: Host-owned evidence refs。
    :returns: 字符串 tuple patch。
    """

    data = _required_mapping(source, key)
    operation = PinnedPatchOperation(_required_string(data, "operation"))
    value = _optional_string_tuple_or_none(data, "value")
    _validate_patch_value(operation, value, field_name=key)
    return PinnedStringTupleFieldPatch(
        operation=operation,
        value=value,
        evidence_refs=_evidence_refs_for_patch(operation, evidence_refs),
    )


def _confirmed_subjects_patch(
    source: Mapping[str, JsonValue],
    key: str,
    evidence_refs: tuple[str, ...],
) -> PinnedStringTupleFieldPatch:
    """解析并校验 confirmed subjects patch。

    ``confirmed_subjects`` 是 Host 中立 opaque ref 集合，不接受自由业务文本；
    非法值必须在 LLM proposal accept 前 fail closed，避免写 canonical event
    transaction 时才暴露校验异常。

    :param source: JSON object。
    :param key: patch 字段名。
    :param evidence_refs: Host-owned evidence refs。
    :returns: confirmed subjects patch。
    :raises ValueError: replace 值不是 Host 中立 opaque ref 时抛出。
    """

    patch = _string_tuple_patch(source, key, evidence_refs)
    if patch.operation is not PinnedPatchOperation.REPLACE:
        return patch
    if patch.value is None:
        return patch
    for item in patch.value:
        validate_host_neutral_opaque_ref_text(item)
    return patch


def _validate_patch_value(
    operation: PinnedPatchOperation,
    value: str | tuple[str, ...] | None,
    *,
    field_name: str,
) -> None:
    """校验 pinned patch 三态 value 约束。

    :param operation: patch 操作。
    :param value: patch 值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises ValueError: operation 与 value 不匹配时抛出。
    """

    if operation is PinnedPatchOperation.REPLACE:
        if value is None:
            raise ValueError(f"{field_name}.value is required for replace")
        return
    if value is not None:
        raise ValueError(f"{field_name}.value must be null unless replace")


def _evidence_refs_for_patch(operation: PinnedPatchOperation, evidence_refs: tuple[str, ...]) -> tuple[str, ...]:
    """根据 patch 操作返回 Host-owned evidence refs。

    :param operation: patch 操作。
    :param evidence_refs: Host-owned preservation evidence refs。
    :returns: clear / replace 操作使用 evidence refs，missing 使用空 tuple。
    """

    if operation is PinnedPatchOperation.MISSING:
        return ()
    return evidence_refs


def _range_tuple(
    proposal: Mapping[str, JsonValue],
    key: str,
    *,
    request: CompactionRequest,
) -> tuple[CompactInputRange, ...]:
    """解析 compact input range tuple。

    :param proposal: 已解析 proposal。
    :param key: range 字段名。
    :param request: Host compaction request。
    :returns: compact input range tuple。
    :raises ValueError: range endpoint label 不在 request material pack 内时抛出。
    """

    values = _required_sequence(proposal, key, max_items=len(request.material_source_refs))
    ranges: list[CompactInputRange] = []
    for index, item in enumerate(values):
        data = _json_mapping(item, f"{key}[{index}]")
        start_refs = _canonical_refs_for_labels(
            request,
            (_required_string(data, "start_material_label"),),
            field_name=f"{key}[{index}].start_material_label",
        )
        end_refs = _canonical_refs_for_labels(
            request,
            (_required_string(data, "end_material_label"),),
            field_name=f"{key}[{index}].end_material_label",
        )
        start_ref = _single_range_endpoint_ref(
            start_refs,
            field_name=f"{key}[{index}].start_material_label",
        )
        end_ref = _single_range_endpoint_ref(
            end_refs,
            field_name=f"{key}[{index}].end_material_label",
        )
        ranges.append(
            CompactInputRange(
                range_ref=_required_string(data, "range_ref"),
                start_input_ref=start_ref,
                end_input_ref=end_ref,
            )
        )
    return tuple(ranges)


def _canonical_refs_for_labels(
    request: CompactionRequest,
    labels: tuple[str, ...],
    *,
    field_name: str,
) -> tuple[str, ...]:
    """把 prompt-local material labels 映射为 canonical source refs。

    :param request: Host compaction request。
    :param labels: prompt-local labels。
    :param field_name: 错误字段名。
    :returns: canonical source refs。
    :raises ValueError: label 未知、格式非法或 section 不匹配时抛出。
    """

    refs: list[str] = []
    for label in labels:
        entry = _provenance_entry_for_label(
            request,
            label,
            allowed_sections=_MATERIAL_LABEL_SECTIONS,
            field_name=field_name,
        )
        if len(entry.canonical_source_refs) == 0:
            raise ValueError(f"{field_name} label has no canonical source refs: {label}")
        refs.extend(entry.canonical_source_refs)
    return tuple(dict.fromkeys(refs))


def _single_range_endpoint_ref(refs: tuple[str, ...], *, field_name: str) -> str:
    """校验 range endpoint label 精确解析到一个 canonical source ref。

    :param refs: label 解析得到的 canonical refs。
    :param field_name: 错误字段名。
    :returns: 唯一 canonical source ref。
    :raises ValueError: endpoint 无 ref 或对应多个 refs 时抛出。
    """

    if len(refs) != 1:
        raise ValueError(f"{field_name} must resolve to exactly one canonical source ref")
    return refs[0]


def _canonical_evidence_refs_for_labels(
    request: CompactionRequest,
    labels: tuple[str, ...],
    *,
    field_name: str,
    require_non_empty: bool = False,
) -> tuple[str, ...]:
    """把 prompt-local evidence labels 映射为 canonical canonical evidence refs。

    :param request: Host compaction request。
    :param labels: prompt-local evidence labels。
    :param field_name: 错误字段名。
    :param require_non_empty: 是否要求至少一个 evidence label。
    :returns: canonical canonical evidence refs。
    :raises ValueError: label 未知、格式非法或不是 evidence label 时抛出。
    """

    if require_non_empty and len(labels) == 0:
        raise ValueError(f"{field_name} must reference at least one evidence label")
    refs: list[str] = []
    for label in labels:
        entry = _provenance_entry_for_label(
            request,
            label,
            allowed_sections=(CompactMaterialSection.EVIDENCE_INPUT,),
            field_name=field_name,
        )
        if entry.accepted_evidence_id is None:
            raise ValueError(f"{field_name} evidence label has no canonical ref")
        refs.append(entry.accepted_evidence_id)
    return tuple(dict.fromkeys(refs))


def _provenance_entry_for_label(
    request: CompactionRequest,
    label: str,
    *,
    allowed_sections: tuple[CompactMaterialSection, ...],
    field_name: str,
) -> PromptLocalProvenanceEntry:
    """读取并校验 prompt-local label 对应 provenance entry。

    :param request: Host compaction request。
    :param label: prompt-local label。
    :param allowed_sections: 允许引用的 material section 集合。
    :param field_name: 错误字段名。
    :returns: provenance entry。
    :raises ValueError: label 未知、格式非法或 section 不匹配时抛出。
    """

    entry = request.material_pack.provenance_map.get(label)
    if entry is None:
        entry = _evidence_parent_entry_for_label(
            request,
            label,
            allowed_sections=allowed_sections,
        )
    if entry is None:
        raise ValueError(f"{field_name} contains unknown label: {label}")
    if entry.section not in allowed_sections:
        raise ValueError(f"{field_name} label section mismatch: {label}")
    validate_material_label(label, entry.section)
    return entry


def _evidence_parent_entry_for_label(
    request: CompactionRequest,
    label: str,
    *,
    allowed_sections: tuple[CompactMaterialSection, ...],
) -> PromptLocalProvenanceEntry | None:
    """按 chunk parent label 解析 evidence provenance entry。

    大 accepted tool evidence 会渲染为 ``E1.1`` / ``E1.2`` 等 chunk label；
    compactor 可用父标签 ``E1`` 表达同一个 canonical evidence。该 helper 只在
    调用方允许 evidence section 时启用，并返回父标签下第一个 chunk 的
    provenance，因为同一父标签下所有 chunk 共享 canonical evidence id。

    :param request: Host compaction request。
    :param label: prompt-local evidence 父标签。
    :param allowed_sections: 允许引用的 material section 集合。
    :returns: 解析到的 provenance entry；无法解析时返回 ``None``。
    """

    if CompactMaterialSection.EVIDENCE_INPUT not in allowed_sections:
        return None
    try:
        validate_material_label(label, CompactMaterialSection.EVIDENCE_INPUT)
    except (TypeError, ValueError):
        return None
    matches = tuple(
        entry
        for entry in request.material_pack.provenance_map.values()
        if entry.section is CompactMaterialSection.EVIDENCE_INPUT and entry.chunk_parent_label == label
    )
    if len(matches) == 0:
        return None
    return matches[0]


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


def _preservation_evidence(
    request: CompactionRequest,
    proposal: Mapping[str, JsonValue],
) -> tuple[PreservationEvidence, ...]:
    """从 proposal 构造 Host-owned preservation evidence。

    LLM 只能输出 prompt-local labels；本函数先把 labels 映射为 canonical
    refs，再生成 Host-owned evidence id。

    :param request: Host compaction request。
    :param proposal: 已解析 proposal。
    :returns: preservation evidence tuple。
    :raises TypeError: preservation evidence shape 非法时抛出。
    :raises ValueError: label 未知或 section 不匹配时抛出。
    """

    values = _required_sequence(
        proposal,
        "preservation_evidence",
        max_items=max(1, len(request.material_pack.all_labels)),
    )
    evidence_items: list[PreservationEvidence] = []
    for index, item in enumerate(values):
        data = _json_mapping(item, f"preservation_evidence[{index}]")
        evidence_items.append(
            PreservationEvidence(
                evidence_id=f"llm-evidence:{request.run_id}:{index + 1}",
                material_source_refs=_canonical_refs_for_labels(
                    request,
                    _required_string_tuple(data, "material_labels"),
                    field_name=f"preservation_evidence[{index}].material_labels",
                ),
                canonical_evidence_refs=_canonical_evidence_refs_for_labels(
                    request,
                    _optional_string_tuple(data, "evidence_labels"),
                    field_name=f"preservation_evidence[{index}].evidence_labels",
                ),
                memory_snapshot_cursor=None,
                compact_input_range=_optional_input_range(
                    request,
                    data,
                    "compact_range",
                    field_name=f"preservation_evidence[{index}].compact_range",
                ),
            )
        )
    return tuple(evidence_items)


def _optional_input_range(
    request: CompactionRequest,
    source: Mapping[str, JsonValue],
    key: str,
    *,
    field_name: str,
) -> CompactInputRange | None:
    """读取可选 prompt-local compact range。

    :param request: Host compaction request。
    :param source: JSON object。
    :param key: range 字段名。
    :param field_name: 错误字段名。
    :returns: compact input range；字段缺省或为 ``null`` 时返回 ``None``。
    :raises TypeError: range shape 非法时抛出。
    :raises ValueError: range label 未知或 section 不匹配时抛出。
    """

    if key not in source or source[key] is None:
        return None
    data = _json_mapping(source[key], field_name)
    start_refs = _canonical_refs_for_labels(
        request,
        (_required_string(data, "start_material_label"),),
        field_name=f"{field_name}.start_material_label",
    )
    end_refs = _canonical_refs_for_labels(
        request,
        (_required_string(data, "end_material_label"),),
        field_name=f"{field_name}.end_material_label",
    )
    start_ref = _single_range_endpoint_ref(
        start_refs,
        field_name=f"{field_name}.start_material_label",
    )
    end_ref = _single_range_endpoint_ref(
        end_refs,
        field_name=f"{field_name}.end_material_label",
    )
    return CompactInputRange(
        range_ref=_required_string(data, "range_ref"),
        start_input_ref=start_ref,
        end_input_ref=end_ref,
    )


def _budget_after_compact(
    request: CompactionRequest,
    episode: EpisodeSummaryCandidate,
    pinned_patch: PinnedStatePatchCandidate,
    fact_candidates: tuple[EvidenceBackedFactCandidate, ...],
    preserve_items: tuple[MinimumPreserveItemCandidate, ...],
) -> int:
    """保守估算 compact 后预算。

    :param request: Host compaction request。
    :param episode: compactor 产出的 episode summary candidate。
    :param pinned_patch: compactor 产出的 pinned state patch candidate。
    :param fact_candidates: compactor 产出的 fact candidate 集合。
    :param preserve_items: compactor 产出的 minimum preserve item 集合。
    :returns: 非负 token 估算。
    """

    structured_fragments = _structured_output_texts(
        episode,
        pinned_patch,
        fact_candidates,
        preserve_items,
    )
    structured_output_tokens = sum(
        _estimate_text_tokens(fragment) + DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS for fragment in structured_fragments
    )
    preserved_tokens = _estimate_preserved_context_tokens(request)
    tool_schema_overhead = DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS * _POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT
    return structured_output_tokens + preserved_tokens + tool_schema_overhead


def _structured_output_texts(
    episode: EpisodeSummaryCandidate,
    pinned_patch: PinnedStatePatchCandidate,
    fact_candidates: tuple[EvidenceBackedFactCandidate, ...],
    preserve_items: tuple[MinimumPreserveItemCandidate, ...],
) -> tuple[str, ...]:
    """收集 structured proposal 中会被保留或物化的 Host-neutral 文本。

    :param episode: episode summary candidate。
    :param pinned_patch: pinned state patch candidate。
    :param fact_candidates: fact candidate 集合。
    :param preserve_items: minimum preserve item 集合。
    :returns: 待估算 token 的文本片段 tuple。
    """

    fragments: list[str] = [
        episode.episode_title,
        episode.goal,
        *episode.completed_actions,
        *episode.confirmed_fact_summaries,
        *episode.user_constraints,
        *episode.open_questions,
        *_optional_text(episode.next_step),
        *_pinned_patch_texts(pinned_patch),
    ]
    for fact_candidate in fact_candidates:
        fragments.append(fact_candidate.claim_text)
    for preserve_item in preserve_items:
        fragments.append(preserve_item.label)
        fragments.append(preserve_item.text)
    return tuple(fragments)


def _pinned_patch_texts(pinned_patch: PinnedStatePatchCandidate) -> tuple[str, ...]:
    """收集 pinned patch replace 值中的文本。

    :param pinned_patch: pinned state patch candidate。
    :returns: pinned patch 文本片段 tuple。
    """

    fragments: list[str] = []
    fragments.extend(_optional_text(pinned_patch.current_goal.value))
    fragments.extend(_optional_string_tuple_texts(pinned_patch.confirmed_subjects.value))
    fragments.extend(_optional_string_tuple_texts(pinned_patch.user_constraints.value))
    fragments.extend(_optional_string_tuple_texts(pinned_patch.open_questions.value))
    return tuple(fragments)


def _optional_text(value: str | None) -> tuple[str, ...]:
    """把可选文本转换为 token 估算片段。

    :param value: 可选文本。
    :returns: 文本存在时返回单元素 tuple，否则返回空 tuple。
    """

    if value is None:
        return ()
    return (value,)


def _optional_string_tuple_texts(value: tuple[str, ...] | None) -> tuple[str, ...]:
    """把可选字符串 tuple 转换为 token 估算片段。

    :param value: 可选字符串 tuple。
    :returns: 字符串 tuple；值为 ``None`` 时返回空 tuple。
    """

    if value is None:
        return ()
    return value


def _estimate_preserved_context_tokens(request: CompactionRequest) -> int:
    """估算 compact 后仍保留的 Host-neutral context token。

    该估算只依赖 Slice 3 冻结后的 ``CompactionRequest`` 字段，基于保留
    引用占比、当前输入和 post-compact 系统提示保守估算 compact 后预算。

    :param request: Host compaction request。
    :returns: 保留上下文的保守 token 估算。
    """

    typed_fragments = (
        _POST_COMPACT_SYSTEM_PROMPT_ESTIMATE,
        request.current_input_text,
        request.current_input_ref,
        *_preserved_ref_texts(request),
    )
    typed_fragment_tokens = sum(
        _estimate_text_tokens(fragment) + DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS for fragment in typed_fragments
    ) + (DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS * _POST_COMPACT_BASE_MESSAGE_COUNT)
    return max(
        typed_fragment_tokens,
        _estimate_preserved_share_from_budget(request),
    )


def _preserved_ref_texts(request: CompactionRequest) -> tuple[str, ...]:
    """返回 compact 后必须保留的引用文本集合。

    :param request: Host compaction request。
    :returns: 去重后的 ref tuple。
    """

    preserved_refs = {
        request.current_input_ref,
        *request.recent_raw_turn_refs,
        *request.canonical_evidence_refs,
        *request.evidence_backed_fact_refs,
        *request.existing_episode_summary_refs,
    }
    return tuple(sorted(preserved_refs))


def _estimate_preserved_share_from_budget(request: CompactionRequest) -> int:
    """按保留引用占比从 compact 前预算中估算保留 token。

    :param request: Host compaction request。
    :returns: 保留部分 token 估算。
    """

    source_refs = {
        *request.material_source_refs,
        *request.canonical_evidence_refs,
        *request.evidence_backed_fact_refs,
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


def _estimate_text_tokens(text: str) -> int:
    """按 Host context budget 统一字符/token 常数估算文本。

    :param text: 文本内容。
    :returns: 至少为 1 的 token 估算。
    """

    return max(1, estimate_budget_text_tokens(text))


__all__ = ["LLMCompactionProposalError", "LLMContextCompactor"]
