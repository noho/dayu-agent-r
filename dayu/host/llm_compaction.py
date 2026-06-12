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
from typing import Protocol, runtime_checkable

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import BatchToolExecutionOutcome
from dayu.engine import run_agent_and_wait, runner_role_sequence_digest
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
    MAX_VNEXT_SOURCE_LABELS_PER_ITEM,
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
from dayu.host.compaction_operation import CompactorProposalRunInput
from dayu.host.durable.codec import sha256_digest_json
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
_COMPACTOR_PROJECTION_SCHEMA_VERSION = "compactor_input_projection.v1"
_SCHEMA_VERSION_FIELD = "schema_version"
_SESSION_SUMMARY_FIELD = "session_summary"
_EVIDENCE_BACKED_FACTS_FIELD = "evidence_backed_facts"
_ANSWER_ANCHORS_FIELD = "answer_anchors"
_FORWARD_INTENTS_FIELD = "forward_intents"
_REFERENCE_CONTINUITY_ITEMS_FIELD = "reference_continuity_items"
_DIAGNOSTICS_FIELD = "diagnostics"
_SUMMARY_TEXT_FIELD = "summary_text"
_SOURCE_LABELS_FIELD = "source_labels"
_CLAIM_TEXT_FIELD = "claim_text"
_EVIDENCE_LABELS_FIELD = "evidence_labels"
_EVIDENCE_KIND_FIELD = "evidence_kind"
_ANCHOR_TITLE_FIELD = "anchor_title"
_ANCHOR_ITEMS_FIELD = "anchor_items"
_ANSWER_SOURCE_LABELS_FIELD = "answer_source_labels"
_DISPLAY_TEXT_FIELD = "display_text"
_ORDINAL_FIELD = "ordinal"
_INTENT_TYPE_FIELD = "intent_type"
_TEXT_FIELD = "text"
_STATUS_FIELD = "status"
_REASON_FIELD = "reason"
_CODE_FIELD = "code"
_FACT_EVIDENCE_KIND_VALUES = frozenset(item.value for item in FactEvidenceKindVNext)
_FORWARD_INTENT_TYPE_VALUES = frozenset(item.value for item in ForwardIntentTypeVNext)
_FORWARD_INTENT_STATUS_VALUES = frozenset(item.value for item in ForwardIntentStatusVNext)
_REFERENCE_CONTINUITY_REASON_VALUES = frozenset(item.value for item in ReferenceContinuityReasonVNext)


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

        prepared_input = self.prepare_compactor_proposal_run_input(
            request,
            cancellation_token,
            compaction_operation_id=None,
            compaction_attempt_number=1,
        )
        return await self.run_prepared_compactor_proposal(prepared_input)

    def prepare_compactor_proposal_run_input(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        compaction_operation_id: str | None,
        compaction_attempt_number: int,
    ) -> CompactorProposalRunInput:
        """构造一次 compactor proposal 的真实 Engine runner call 输入。

        :param request: Host 构造的 immutable compaction request。
        :param cancellation_token: Host run lifecycle 注入的真实取消 token。
        :param compaction_operation_id: Host compaction operation id；直接
            ``compact`` 调用时为 ``None``。
        :param compaction_attempt_number: operation 内 proposal attempt 序号。
        :returns: 可执行且可写 manifest 的同源 proposal 输入。
        :raises TypeError: request 类型非法时抛出。
        :raises ValueError: attempt 序号非法时抛出。
        """

        if not isinstance(request, CompactionRequest):
            raise TypeError("request must be CompactionRequest")
        if compaction_attempt_number <= 0:
            raise ValueError("compaction_attempt_number must be positive")
        compact_input = conversation_compact_input_vnext_from_material_pack(
            request.material_pack
        )
        compactor_engine_run_id = _compactor_engine_run_id(
            request=request,
            compaction_operation_id=compaction_operation_id,
            compaction_attempt_number=compaction_attempt_number,
        )
        agent_request = _agent_request_vnext(
            compact_input,
            self._runner_spec,
            self._runner_options,
            self._agent_policy,
            self._system_prompt,
            self._user_prompt_template,
            cancellation_token,
            compactor_engine_run_id=compactor_engine_run_id,
        )
        roles = tuple(message.role.value for message in agent_request.messages)
        projection = _compactor_input_projection_json(
            request=request,
            compact_input=compact_input,
        )
        return CompactorProposalRunInput(
            compact_input=compact_input,
            agent_request=agent_request,
            compaction_request_digest=request.digest(),
            compactor_engine_run_id=compactor_engine_run_id,
            message_count=len(agent_request.messages),
            role_sequence_digest=runner_role_sequence_digest(roles),
            system_prompt_asset_digest=sha256_digest_json(
                {"compactor_system_prompt": self._system_prompt}
            ),
            user_prompt_template_digest=sha256_digest_json(
                {"compactor_user_prompt_template": self._user_prompt_template}
            ),
            user_prompt_digest=sha256_digest_json(
                {"compactor_user_prompt": agent_request.messages[1].content}
            ),
            compactor_input_projection=projection,
            compactor_input_projection_digest=sha256_digest_json(projection),
        )

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> ConversationCompactOutputVNext:
        """执行已准备的 compactor proposal runner call。

        :param prepared_input: 由 ``prepare_compactor_proposal_run_input``
            返回的同源 proposal input。
        :returns: vNext compact output candidate。
        :raises TypeError: prepared_input 类型非法时抛出。
        :raises LLMCompactionProposalError: LLM 没有返回可用 structured proposal 时抛出。
        :raises Exception: Engine runner / provider 调用失败时透传。
        """

        if not isinstance(prepared_input, CompactorProposalRunInput):
            raise TypeError("prepared_input must be CompactorProposalRunInput")
        try:
            outcome = await _run_agent_request(
                prepared_input.agent_request,
                timeout_seconds=self._runner_spec.default_timeout_seconds,
            )
        except TimeoutError as exc:
            _signal_timeout_cancellation(
                prepared_input.agent_request.cancellation_token
            )
            raise LLMCompactionProposalError(_COMPACTOR_PROPOSAL_TIMEOUT_MESSAGE) from exc
        if not isinstance(outcome, EngineRunOutcomeFinalAnswer):
            raise LLMCompactionProposalError(_non_final_outcome_message(outcome))
        if outcome.finish_reason is FinishReason.LENGTH:
            raise LLMCompactionProposalError("compactor proposal was truncated finish_reason=length")
        return parse_conversation_compact_output_vnext(
            prepared_input.compact_input,
            outcome.content,
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
    *,
    compactor_engine_run_id: str,
) -> AgentRunRequest:
    """构造 vNext 禁用工具的 Engine public run request。

    :param request: vNext compaction input。
    :param runner_spec: compactor Runner 规约。
    :param runner_options: compactor Runner 调用参数。
    :param agent_policy: compactor Agent policy。
    :param system_prompt: compactor system prompt。
    :param user_prompt_template: compactor user prompt template。
    :param cancellation_token: Host cancellation token。
    :param compactor_engine_run_id: Host 派生的 compactor Engine run id。
    :returns: Engine run request。
    """

    return AgentRunRequest(
        run_id=compactor_engine_run_id,
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


def _compactor_engine_run_id(
    *,
    request: CompactionRequest,
    compaction_operation_id: str | None,
    compaction_attempt_number: int,
) -> str:
    """派生 compactor internal Engine run id。

    :param request: Host compaction request。
    :param compaction_operation_id: Host compaction operation id；未知时为
        ``None``。
    :param compaction_attempt_number: operation 内 proposal attempt 序号。
    :returns: deterministic compactor Engine run id。
    """

    digest = sha256_digest_json(
        {
            "compaction_operation_id": compaction_operation_id,
            "compaction_request_digest": request.digest(),
            "compaction_attempt_number": compaction_attempt_number,
        }
    )
    return f"{_COMPACTOR_RUN_ID_PREFIX}-vnext-{digest.removeprefix('sha256:')}"


def _compactor_input_projection_json(
    *,
    request: CompactionRequest,
    compact_input: ConversationCompactInputVNext,
) -> Mapping[str, JsonValue]:
    """构造 compactor input projection artifact body。

    :param request: Host compaction request。
    :param compact_input: 已冻结的 vNext compactor input。
    :returns: 可作为 artifact 写入的 projection JSON。
    """

    return {
        "projection_kind": "compactor_input_projection",
        "schema_version": _COMPACTOR_PROJECTION_SCHEMA_VERSION,
        "compaction_request_digest": request.digest(),
        "source_boundary_refs": list(_compactor_source_boundary_refs(request)),
        "compact_input": compact_input.to_json(),
    }


def _compactor_source_boundary_refs(request: CompactionRequest) -> tuple[str, ...]:
    """返回 compactor projection 的 source boundary refs。

    :param request: Host compaction request。
    :returns: 去重后的 source refs。
    """

    return tuple(
        dict.fromkeys(
            (
                request.current_input_ref,
                *request.material_source_refs,
                *request.canonical_evidence_refs,
                *request.evidence_backed_fact_refs,
            )
        )
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
    try:
        candidate = _parse_vnext_proposal(final_answer)
        _validate_vnext_candidate_source_labels(request, candidate)
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMCompactionProposalError(f"compactor vNext proposal schema invalid: {exc}") from exc
    return candidate


def _parse_vnext_proposal(final_answer: str) -> ConversationCompactOutputVNext:
    """解析 vNext LLM strict JSON proposal。

    :param final_answer: LLM final answer 原文。
    :returns: vNext compact output candidate。
    :raises LLMCompactionProposalError: 空文本、非 JSON 或缺少必需字段时抛出。
    """

    raw = final_answer.strip()
    if len(raw) < _MIN_PROPOSAL_LENGTH:
        raise LLMCompactionProposalError("compactor vNext proposal is empty")
    try:
        parsed: JsonValue = json.loads(raw)
    except JSONDecodeError as exc:
        raise LLMCompactionProposalError(f"compactor vNext proposal is not valid JSON: {exc.msg}") from exc
    proposal = _json_object(parsed, "proposal")
    schema_version = _required_string(
        proposal,
        _SCHEMA_VERSION_FIELD,
        parent_path="",
    )
    if schema_version != CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT:
        raise ValueError(f"{_SCHEMA_VERSION_FIELD} is invalid")
    return ConversationCompactOutputVNext(
        schema_version=schema_version,
        session_summary=_session_summary_candidate_vnext(proposal),
        evidence_backed_facts=_fact_candidates_vnext(proposal),
        answer_anchors=_answer_anchor_candidates_vnext(proposal),
        forward_intents=_forward_intent_candidates_vnext(proposal),
        reference_continuity_items=_reference_candidates_vnext(proposal),
        diagnostics=_diagnostics_vnext(proposal),
    )


def _session_summary_candidate_vnext(
    proposal: Mapping[str, JsonValue],
) -> SessionSummaryCandidateVNext | None:
    """解析 vNext session summary candidate。

    :param proposal: 已解析 proposal。
    :returns: session summary candidate；JSON null 时为 ``None``。
    """

    value = _required_value(proposal, _SESSION_SUMMARY_FIELD, parent_path="")
    if value is None:
        return None
    data = _json_object(value, _SESSION_SUMMARY_FIELD)
    return SessionSummaryCandidateVNext(
        summary_text=_required_string(data, _SUMMARY_TEXT_FIELD, parent_path=_SESSION_SUMMARY_FIELD),
        source_labels=_required_string_tuple(data, _SOURCE_LABELS_FIELD, parent_path=_SESSION_SUMMARY_FIELD),
    )


def _fact_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[EvidenceBackedFactCandidateVNext, ...]:
    """解析 vNext evidence-backed fact candidates。

    :param proposal: 已解析 proposal。
    :returns: fact candidate tuple。
    """

    values = _required_array(
        proposal,
        _EVIDENCE_BACKED_FACTS_FIELD,
        parent_path="",
        max_items=MAX_VNEXT_FACT_ITEMS,
    )
    candidates: list[EvidenceBackedFactCandidateVNext] = []
    for index, item in enumerate(values):
        item_path = _item_path(_EVIDENCE_BACKED_FACTS_FIELD, index)
        data = _json_object(item, item_path)
        candidates.append(
            EvidenceBackedFactCandidateVNext(
                claim_text=_required_string(data, _CLAIM_TEXT_FIELD, parent_path=item_path),
                evidence_labels=_required_string_tuple(data, _EVIDENCE_LABELS_FIELD, parent_path=item_path),
                evidence_kind=FactEvidenceKindVNext(
                    _required_enum(
                        data,
                        _EVIDENCE_KIND_FIELD,
                        parent_path=item_path,
                        allowed_values=_FACT_EVIDENCE_KIND_VALUES,
                    )
                ),
                source_labels=_optional_string_tuple(data, _SOURCE_LABELS_FIELD, parent_path=item_path),
            )
        )
    return tuple(candidates)


def _answer_anchor_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[AnswerAnchorCandidateVNext, ...]:
    """解析 vNext answer anchor candidates。

    :param proposal: 已解析 proposal。
    :returns: answer anchor candidate tuple。
    """

    values = _required_array(
        proposal,
        _ANSWER_ANCHORS_FIELD,
        parent_path="",
        max_items=MAX_VNEXT_ANSWER_ANCHOR_ITEMS,
    )
    candidates: list[AnswerAnchorCandidateVNext] = []
    for index, item in enumerate(values):
        item_path = _item_path(_ANSWER_ANCHORS_FIELD, index)
        data = _json_object(item, item_path)
        candidates.append(
            AnswerAnchorCandidateVNext(
                anchor_title=_required_string(data, _ANCHOR_TITLE_FIELD, parent_path=item_path),
                anchor_items=_answer_anchor_children_vnext(data, item_path),
                answer_source_labels=_required_string_tuple(data, _ANSWER_SOURCE_LABELS_FIELD, parent_path=item_path),
            )
        )
    return tuple(candidates)


def _answer_anchor_children_vnext(
    source: Mapping[str, JsonValue],
    parent_path: str,
) -> tuple[AnswerAnchorChildVNext, ...]:
    """解析 vNext answer anchor children。

    :param source: answer anchor JSON object。
    :param parent_path: answer anchor 的完整字段路径。
    :returns: answer anchor child tuple。
    """

    values = _required_array(
        source,
        _ANCHOR_ITEMS_FIELD,
        parent_path=parent_path,
        max_items=MAX_VNEXT_ANSWER_ANCHOR_ITEMS,
    )
    field_path = _field_path(parent_path, _ANCHOR_ITEMS_FIELD)
    children: list[AnswerAnchorChildVNext] = []
    for index, item in enumerate(values):
        item_path = _item_path(field_path, index)
        data = _json_object(item, item_path)
        children.append(
            AnswerAnchorChildVNext(
                display_text=_required_string(data, _DISPLAY_TEXT_FIELD, parent_path=item_path),
                ordinal=_optional_non_negative_int(data, _ORDINAL_FIELD, parent_path=item_path),
            )
        )
    return tuple(children)


def _forward_intent_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[ForwardIntentCandidateVNext, ...]:
    """解析 vNext forward intent candidates。

    :param proposal: 已解析 proposal。
    :returns: forward intent candidate tuple。
    """

    values = _required_array(
        proposal,
        _FORWARD_INTENTS_FIELD,
        parent_path="",
        max_items=MAX_VNEXT_FORWARD_INTENT_ITEMS,
    )
    candidates: list[ForwardIntentCandidateVNext] = []
    for index, item in enumerate(values):
        item_path = _item_path(_FORWARD_INTENTS_FIELD, index)
        data = _json_object(item, item_path)
        candidates.append(
            ForwardIntentCandidateVNext(
                intent_type=ForwardIntentTypeVNext(
                    _required_enum(
                        data,
                        _INTENT_TYPE_FIELD,
                        parent_path=item_path,
                        allowed_values=_FORWARD_INTENT_TYPE_VALUES,
                    )
                ),
                text=_required_string(data, _TEXT_FIELD, parent_path=item_path),
                status=ForwardIntentStatusVNext(
                    _required_enum(
                        data,
                        _STATUS_FIELD,
                        parent_path=item_path,
                        allowed_values=_FORWARD_INTENT_STATUS_VALUES,
                    )
                ),
                source_labels=_required_string_tuple(data, _SOURCE_LABELS_FIELD, parent_path=item_path),
            )
        )
    return tuple(candidates)


def _reference_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[ReferenceContinuityCandidateVNext, ...]:
    """解析 vNext reference continuity candidates。

    :param proposal: 已解析 proposal。
    :returns: reference continuity candidate tuple。
    """

    values = _required_array(
        proposal,
        _REFERENCE_CONTINUITY_ITEMS_FIELD,
        parent_path="",
        max_items=MAX_VNEXT_REFERENCE_CONTINUITY_ITEMS,
    )
    candidates: list[ReferenceContinuityCandidateVNext] = []
    for index, item in enumerate(values):
        item_path = _item_path(_REFERENCE_CONTINUITY_ITEMS_FIELD, index)
        data = _json_object(item, item_path)
        candidates.append(
            ReferenceContinuityCandidateVNext(
                text=_required_string(data, _TEXT_FIELD, parent_path=item_path),
                reason=ReferenceContinuityReasonVNext(
                    _required_enum(
                        data,
                        _REASON_FIELD,
                        parent_path=item_path,
                        allowed_values=_REFERENCE_CONTINUITY_REASON_VALUES,
                    )
                ),
                source_labels=_required_string_tuple(data, _SOURCE_LABELS_FIELD, parent_path=item_path),
            )
        )
    return tuple(candidates)


def _diagnostics_vnext(proposal: Mapping[str, JsonValue]) -> tuple[CompactCandidateDiagnosticVNext, ...]:
    """解析 vNext compact diagnostics。

    :param proposal: 已解析 proposal。
    :returns: diagnostic tuple。
    """

    values = _required_array(
        proposal,
        _DIAGNOSTICS_FIELD,
        parent_path="",
        max_items=MAX_VNEXT_DIAGNOSTIC_ITEMS,
    )
    diagnostics: list[CompactCandidateDiagnosticVNext] = []
    for index, item in enumerate(values):
        item_path = _item_path(_DIAGNOSTICS_FIELD, index)
        data = _json_object(item, item_path)
        diagnostics.append(
            CompactCandidateDiagnosticVNext(
                code=_required_string(data, _CODE_FIELD, parent_path=item_path),
                text=_required_string(data, _TEXT_FIELD, parent_path=item_path),
                source_labels=_optional_string_tuple(data, _SOURCE_LABELS_FIELD, parent_path=item_path),
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



def _field_path(parent: str, key: str) -> str:
    """拼接 JSON object 字段路径。

    :param parent: 父字段路径；顶层字段传空字符串。
    :param key: 当前字段名。
    :returns: 完整字段路径。
    """

    if parent == "":
        return key
    return f"{parent}.{key}"


def _item_path(parent: str, index: int) -> str:
    """拼接 JSON array 元素路径。

    :param parent: 数组字段的完整路径。
    :param index: 元素下标。
    :returns: 完整元素路径。
    """

    return f"{parent}[{index}]"


def _json_object(value: JsonValue, field_path: str) -> Mapping[str, JsonValue]:
    """校验 JSON 值为 object。

    :param value: JSON 值。
    :param field_path: 待校验值的完整字段路径。
    :returns: JSON object。
    :raises TypeError: 值不是 object 或 object key 不是字符串时抛出。
    """

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_path} must be object")
    for key in value:
        if not isinstance(key, str):
            raise TypeError(f"{field_path} object keys must be strings")
    return value


def _required_value(
    source: Mapping[str, JsonValue],
    key: str,
    *,
    parent_path: str,
) -> JsonValue:
    """读取必需 JSON 字段值。

    :param source: JSON object。
    :param key: 字段名。
    :param parent_path: ``source`` 对应的父字段路径。
    :returns: JSON 字段值。
    :raises KeyError: 字段缺失时抛出。
    """

    field_path = _field_path(parent_path, key)
    if key not in source:
        raise KeyError(f"missing required key: {field_path}")
    return source[key]


def _required_array(
    source: Mapping[str, JsonValue],
    key: str,
    *,
    parent_path: str,
    max_items: int,
) -> tuple[JsonValue, ...]:
    """读取必需 JSON array 字段。

    :param source: JSON object。
    :param key: 字段名。
    :param parent_path: ``source`` 对应的父字段路径。
    :param max_items: 数组元素上限。
    :returns: JSON 值 tuple。
    :raises KeyError: 字段缺失时抛出。
    :raises TypeError: 字段不是 array 时抛出。
    :raises ValueError: 数组超过上限时抛出。
    """

    field_path = _field_path(parent_path, key)
    value = _required_value(source, key, parent_path=parent_path)
    if not isinstance(value, list):
        raise TypeError(f"{field_path} must be array")
    if len(value) > max_items:
        raise ValueError(f"{field_path} exceeds maximum item count")
    return tuple(value)


def _required_string(
    source: Mapping[str, JsonValue],
    key: str,
    *,
    parent_path: str,
) -> str:
    """读取必需字符串字段。

    :param source: JSON object。
    :param key: 字段名。
    :param parent_path: ``source`` 对应的父字段路径。
    :returns: 字符串值。
    :raises KeyError: 字段缺失时抛出。
    :raises TypeError: 字段不是字符串时抛出。
    """

    field_path = _field_path(parent_path, key)
    value = _required_value(source, key, parent_path=parent_path)
    if not isinstance(value, str):
        raise TypeError(f"{field_path} must be string")
    return value


def _optional_non_negative_int(
    source: Mapping[str, JsonValue],
    key: str,
    *,
    parent_path: str,
) -> int | None:
    """读取可选非负整数或 null 字段。

    :param source: JSON object。
    :param key: 字段名。
    :param parent_path: ``source`` 对应的父字段路径。
    :returns: 非负整数、``None`` 或缺省时的 ``None``。
    :raises TypeError: 字段既不是整数也不是 null 时抛出。
    :raises ValueError: 字段是负整数时抛出。
    """

    if key not in source:
        return None
    field_path = _field_path(parent_path, key)
    value = source[key]
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_path} must be non-negative integer or null")
    if value < 0:
        raise ValueError(f"{field_path} must be non-negative integer or null")
    return value


def _required_enum(
    source: Mapping[str, JsonValue],
    key: str,
    *,
    parent_path: str,
    allowed_values: frozenset[str],
) -> str:
    """读取必需枚举字符串字段。

    :param source: JSON object。
    :param key: 字段名。
    :param parent_path: ``source`` 对应的父字段路径。
    :param allowed_values: 允许的枚举字符串集合。
    :returns: 枚举字符串值。
    :raises KeyError: 字段缺失时抛出。
    :raises TypeError: 字段不是字符串时抛出。
    :raises ValueError: 字段值不在允许集合中时抛出。
    """

    value = _required_string(source, key, parent_path=parent_path)
    field_path = _field_path(parent_path, key)
    if value not in allowed_values:
        raise ValueError(f"{field_path} has invalid enum value")
    return value


def _optional_string_tuple(
    source: Mapping[str, JsonValue],
    key: str,
    *,
    parent_path: str,
) -> tuple[str, ...]:
    """读取可选字符串数组字段。

    :param source: JSON object。
    :param key: 字段名。
    :param parent_path: ``source`` 对应的父字段路径。
    :returns: 字符串 tuple；缺省时为空 tuple。
    :raises TypeError: 字段不是字符串数组时抛出。
    :raises ValueError: 数组超过上限时抛出。
    """

    if key not in source:
        return ()
    return _string_tuple(
        source[key],
        _field_path(parent_path, key),
        max_items=MAX_VNEXT_SOURCE_LABELS_PER_ITEM,
    )


def _required_string_tuple(
    source: Mapping[str, JsonValue],
    key: str,
    *,
    parent_path: str,
) -> tuple[str, ...]:
    """读取必需字符串数组字段。

    :param source: JSON object。
    :param key: 字段名。
    :param parent_path: ``source`` 对应的父字段路径。
    :returns: 字符串 tuple。
    :raises KeyError: 字段缺失时抛出。
    :raises TypeError: 字段不是字符串数组时抛出。
    :raises ValueError: 数组超过上限时抛出。
    """

    field_path = _field_path(parent_path, key)
    return _string_tuple(
        _required_value(source, key, parent_path=parent_path),
        field_path,
        max_items=MAX_VNEXT_SOURCE_LABELS_PER_ITEM,
    )


def _string_tuple(value: JsonValue, field_path: str, *, max_items: int) -> tuple[str, ...]:
    """校验 JSON 值为字符串数组。

    :param value: JSON 值。
    :param field_path: 待校验值的完整字段路径。
    :param max_items: 字符串数组元素上限。
    :returns: 字符串 tuple。
    :raises TypeError: 值不是字符串数组时抛出。
    :raises ValueError: 数组超过上限时抛出。
    """

    if not isinstance(value, list):
        raise TypeError(f"{field_path} must be array")
    if len(value) > max_items:
        raise ValueError(f"{field_path} exceeds maximum item count")
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"{_item_path(field_path, index)} must be string")
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
