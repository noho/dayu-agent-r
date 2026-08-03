"""Host-owned LLM context compactor。

本模块把 Host ``CompactionRequest`` 映射为一次禁用工具的 Engine public
runner 调用，并把 LLM final answer 的 strict JSON proposal 转换为
``CompactCandidateV2``。它不写 EventLog、不写 artifact、不做
semantic repair loop，也不向 Service 暴露 prompt、candidate builder 或
policy seam。
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from json import JSONDecodeError
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
from dayu.engine.contracts.runner_identity import SuccessfulRunnerResponseIdentity
from dayu.host.compaction import (
    CompactAnswerAnchorV2,
    CompactCandidateDiagnosticV2,
    COMPACT_OUTPUT_SCHEMA_V2,
    CompactDropReasonV2,
    CompactExplicitDropV2,
    CompactionRequest,
    CompactorProposal,
    CompactorProposalError,
    CompactInputV2,
    CompactCandidateV2,
    ContextCompactor,
    CompactEvidenceFactV2,
    CompactForwardIntentV2,
    CompactForwardIntentStatusV2,
    CompactRepairFeedbackV2,
    CompactReferenceContinuityV2,
    CompactSessionSummaryV2,
    CompactValidationIssueCodeV2,
    CompactValidationIssueV2,
    CompactValidationReportV2,
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
_REPAIR_FEEDBACK_BEGIN = "REPAIR_FEEDBACK_JSON_BEGIN"
_REPAIR_FEEDBACK_END = "REPAIR_FEEDBACK_JSON_END"
_COMPACTOR_PROPOSAL_TIMEOUT_MESSAGE = "compactor proposal timed out"
_COMPACTOR_PROPOSAL_TIMEOUT_CANCEL_REASON = "compactor_proposal_timeout"
_COMPACTOR_PROJECTION_SCHEMA_VERSION = "compactor_input_projection.v1"
_SCHEMA_VERSION_FIELD = "schema"
_SESSION_SUMMARY_FIELD = "session_summary"
_EVIDENCE_BACKED_FACTS_FIELD = "evidence_facts"
_ANSWER_ANCHORS_FIELD = "answer_anchors"
_FORWARD_INTENTS_FIELD = "forward_intents"
_REFERENCE_CONTINUITY_ITEMS_FIELD = "reference_continuity"
_DIAGNOSTICS_FIELD = "diagnostics"
_EXPLICITLY_DROPPED_SOURCES_FIELD = "explicitly_dropped_sources"
_SUMMARY_TEXT_FIELD = "text"
_SOURCE_LABELS_FIELD = "source_labels"
_CLAIM_TEXT_FIELD = "claim"
_EVIDENCE_LABELS_FIELD = "support_labels"
_CONTEXT_LABELS_FIELD = "context_labels"
_ANCHOR_TITLE_FIELD = "title"
_ANCHOR_DETAIL_FIELD = "detail"
_INTENT_TYPE_FIELD = "intent_type"
_TEXT_FIELD = "text"
_STATUS_FIELD = "status"
_REASON_FIELD = "reason"
_CODE_FIELD = "code"
_MESSAGE_FIELD = "message"
_SOURCE_LABEL_FIELD = "source_label"
_FORWARD_INTENT_STATUS_VALUES = frozenset(item.value for item in CompactForwardIntentStatusV2)
_TOP_LEVEL_FIELDS = frozenset(
    (
        _SCHEMA_VERSION_FIELD,
        _SESSION_SUMMARY_FIELD,
        _EVIDENCE_BACKED_FACTS_FIELD,
        _ANSWER_ANCHORS_FIELD,
        _FORWARD_INTENTS_FIELD,
        _REFERENCE_CONTINUITY_ITEMS_FIELD,
        _DIAGNOSTICS_FIELD,
        _EXPLICITLY_DROPPED_SOURCES_FIELD,
    )
)
_SUMMARY_FIELDS = frozenset((_SUMMARY_TEXT_FIELD, _SOURCE_LABELS_FIELD))
_FACT_FIELDS = frozenset((_CLAIM_TEXT_FIELD, _EVIDENCE_LABELS_FIELD, _CONTEXT_LABELS_FIELD))
_ANCHOR_FIELDS = frozenset((_ANCHOR_TITLE_FIELD, _ANCHOR_DETAIL_FIELD, _SOURCE_LABELS_FIELD))
_INTENT_FIELDS = frozenset((_INTENT_TYPE_FIELD, _TEXT_FIELD, _STATUS_FIELD, _SOURCE_LABELS_FIELD))
_REFERENCE_FIELDS = frozenset((_TEXT_FIELD, _REASON_FIELD, _SOURCE_LABELS_FIELD))
_DIAGNOSTIC_FIELDS = frozenset((_CODE_FIELD, _MESSAGE_FIELD, _SOURCE_LABELS_FIELD))
_DROP_FIELDS = frozenset((_SOURCE_LABEL_FIELD, _REASON_FIELD))


@runtime_checkable
class _CancellationSignalToken(CancellationToken, Protocol):
    """Host 内部可写取消 token 协议。"""

    def request_cancel(self, reason: str) -> None:
        """请求取消底层 Engine runner。

        :param reason: 结构化取消原因。
        :returns: ``None``。
        """

        ...


class LLMCompactionProposalError(CompactorProposalError):
    """LLM compaction 单次 proposal 失败。

    :param message: 中性失败描述。
    :param successful_response_identity: 本次失败发生在成功 Engine final 之后
        时对应的响应身份；尚未取得成功 final 时为 ``None``。
    """


class LLMCompactionValidationError(LLMCompactionProposalError):
    """raw LLM JSON 未通过 strict v2 contract。

    :param report: 可直接进入 semantic repair 的脱敏 validation report。
    :param successful_response_identity: 已取得成功 Engine final 时的响应身份；
        直接调用 parser 时为 ``None``。
    """

    def __init__(
        self,
        report: CompactValidationReportV2,
        *,
        successful_response_identity: SuccessfulRunnerResponseIdentity | None,
    ) -> None:
        """初始化 strict parser validation error。

        :param report: strict parser 产生的 validation report。
        :param successful_response_identity: 成功 Engine final 的响应身份。
        :returns: ``None``。
        :raises TypeError: report 类型非法时抛出。
        """

        if not isinstance(report, CompactValidationReportV2):
            raise TypeError("report must be CompactValidationReportV2")
        self.report = report
        super().__init__(
            report.issues[0].message,
            successful_response_identity=successful_response_identity,
            validation_report=report,
        )


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
            raise ValueError("user_prompt_template must contain exactly one <<compaction_request>> placeholder")
        self._runner_spec = runner_spec
        self._runner_options = runner_options
        self._agent_policy = agent_policy
        self._system_prompt = system_prompt
        self._user_prompt_template = user_prompt_template

    async def compact(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        repair_feedback: CompactRepairFeedbackV2 | None,
    ) -> CompactorProposal:
        """执行一次 vNext LLM compaction proposal。

        :param request: Host 构造的 immutable compaction request。
        :param cancellation_token: Host run lifecycle 注入的真实取消 token。
        :param repair_feedback: 前次 semantic validation feedback。
        :returns: 与实际成功 Runner call 身份配对的 vNext proposal。
        :raises TypeError: request 类型非法时抛出。
        :raises LLMCompactionProposalError: LLM 没有返回可用 structured proposal 时抛出。
        :raises Exception: Engine runner / provider 调用失败时透传。
        """

        prepared_input = self.prepare_compactor_proposal_run_input(
            request,
            cancellation_token,
            compaction_operation_id=None,
            compaction_attempt_number=1,
            repair_feedback=repair_feedback,
        )
        return await self.run_prepared_compactor_proposal(prepared_input)

    def prepare_compactor_proposal_run_input(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        compaction_operation_id: str | None,
        compaction_attempt_number: int,
        repair_feedback: CompactRepairFeedbackV2 | None,
    ) -> CompactorProposalRunInput:
        """构造一次 compactor proposal 的真实 Engine runner call 输入。

        :param request: Host 构造的 immutable compaction request。
        :param cancellation_token: Host run lifecycle 注入的真实取消 token。
        :param compaction_operation_id: Host compaction operation id；直接
            ``compact`` 调用时为 ``None``。
        :param compaction_attempt_number: operation 内 proposal attempt 序号。
        :param repair_feedback: 前次 semantic validation feedback。
        :returns: 可执行且可写 manifest 的同源 proposal 输入。
        :raises TypeError: request 类型非法时抛出。
        :raises ValueError: attempt 序号非法时抛出。
        """

        if not isinstance(request, CompactionRequest):
            raise TypeError("request must be CompactionRequest")
        if compaction_attempt_number <= 0:
            raise ValueError("compaction_attempt_number must be positive")
        compact_input = request.compact_input
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
            repair_feedback=repair_feedback,
        )
        roles = tuple(message.role.value for message in agent_request.messages)
        projection = _compactor_input_projection_json(
            request=request,
            compact_input=compact_input,
            repair_feedback=repair_feedback,
        )
        return CompactorProposalRunInput(
            compact_input=compact_input,
            agent_request=agent_request,
            compaction_request_digest=request.digest(),
            compactor_engine_run_id=compactor_engine_run_id,
            message_count=len(agent_request.messages),
            role_sequence_digest=runner_role_sequence_digest(roles),
            system_prompt_asset_digest=sha256_digest_json({"compactor_system_prompt": self._system_prompt}),
            user_prompt_template_digest=sha256_digest_json(
                {"compactor_user_prompt_template": self._user_prompt_template}
            ),
            user_prompt_digest=sha256_digest_json({"compactor_user_prompt": agent_request.messages[1].content}),
            compactor_input_projection=projection,
            compactor_input_projection_digest=sha256_digest_json(projection),
            repair_feedback=repair_feedback,
        )

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """执行已准备的 compactor proposal runner call。

        :param prepared_input: 由 ``prepare_compactor_proposal_run_input``
            返回的同源 proposal input。
        :returns: 与实际成功 Runner call 身份配对的 vNext proposal。
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
            _signal_timeout_cancellation(prepared_input.agent_request.cancellation_token)
            raise LLMCompactionProposalError(
                _COMPACTOR_PROPOSAL_TIMEOUT_MESSAGE,
                successful_response_identity=None,
            ) from exc
        if not isinstance(outcome, EngineRunOutcomeFinalAnswer):
            raise LLMCompactionProposalError(
                _non_final_outcome_message(outcome),
                successful_response_identity=None,
            )
        response_identity = _validated_prepared_response_identity(
            prepared_input=prepared_input,
            outcome=outcome,
        )
        if outcome.finish_reason is FinishReason.LENGTH:
            raise LLMCompactionProposalError(
                "compactor proposal was truncated finish_reason=length",
                successful_response_identity=response_identity,
            )
        try:
            candidate = parse_conversation_compact_output_vnext(
                prepared_input.compact_input,
                outcome.content,
            )
        except LLMCompactionValidationError as exc:
            raise LLMCompactionValidationError(
                exc.report,
                successful_response_identity=response_identity,
            ) from exc
        except LLMCompactionProposalError as exc:
            raise LLMCompactionProposalError(
                str(exc),
                successful_response_identity=response_identity,
            ) from exc
        return CompactorProposal(
            candidate=candidate,
            successful_response_identity=response_identity,
        )


def _validated_prepared_response_identity(
    *,
    prepared_input: CompactorProposalRunInput,
    outcome: EngineRunOutcomeFinalAnswer,
) -> SuccessfulRunnerResponseIdentity:
    """校验成功 Engine final 与 prepared compactor call 完全同源。

    :param prepared_input: 当前 Host attempt 已冻结的真实 Engine request。
    :param outcome: Engine 返回的成功 final outcome。
    :returns: 校验通过的成功响应身份。
    :raises LLMCompactionProposalError: Engine run、ordinary attempt/execution
        或 effective provider/model 与 prepared request 不一致时抛出。
    """

    response_identity = outcome.response_identity
    request_identity = response_identity.runner_request_identity
    if request_identity.run_id != prepared_input.compactor_engine_run_id:
        raise LLMCompactionProposalError(
            "compactor successful response Engine run identity mismatch",
            successful_response_identity=response_identity,
        )
    if request_identity.attempt_id is not None or request_identity.execution_id is not None:
        raise LLMCompactionProposalError(
            "compactor successful response must not use ordinary attempt identity",
            successful_response_identity=response_identity,
        )
    runner_spec = prepared_input.agent_request.runner_spec
    if response_identity.effective_provider != runner_spec.provider:
        raise LLMCompactionProposalError(
            "compactor successful response effective provider mismatch",
            successful_response_identity=response_identity,
        )
    if response_identity.effective_model != runner_spec.model:
        raise LLMCompactionProposalError(
            "compactor successful response effective model mismatch",
            successful_response_identity=response_identity,
        )
    return response_identity


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
    request: CompactInputV2,
    runner_spec: RunnerSpec,
    runner_options: RunnerCallOptions,
    agent_policy: AgentPolicy,
    system_prompt: str,
    user_prompt_template: str,
    cancellation_token: CancellationToken,
    *,
    compactor_engine_run_id: str,
    repair_feedback: CompactRepairFeedbackV2 | None,
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
    :param repair_feedback: 前次 semantic validation feedback。
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
                content=_user_prompt_vnext(
                    request,
                    user_prompt_template,
                    repair_feedback=repair_feedback,
                ),
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
    compact_input: CompactInputV2,
    repair_feedback: CompactRepairFeedbackV2 | None,
) -> Mapping[str, JsonValue]:
    """构造 compactor input projection artifact body。

    :param request: Host compaction request。
    :param compact_input: 已冻结的 vNext compactor input。
    :param repair_feedback: 本次 attempt 的 semantic repair feedback。
    :returns: 可作为 artifact 写入的 projection JSON。
    """

    return {
        "projection_kind": "compactor_input_projection",
        "schema_version": _COMPACTOR_PROJECTION_SCHEMA_VERSION,
        "compaction_request_digest": request.digest(),
        "source_boundary_refs": list(_compactor_source_boundary_refs(request)),
        "compact_input": compact_input.to_json(),
        "repair_feedback": (None if repair_feedback is None else repair_feedback.to_json()),
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
    request: CompactInputV2,
    user_prompt_template: str,
    *,
    repair_feedback: CompactRepairFeedbackV2 | None,
) -> str:
    """渲染 vNext compactor user prompt。

    :param request: vNext compactor input。
    :param user_prompt_template: 包含唯一 compaction request 占位符的模板。
    :param repair_feedback: 前次 semantic validation feedback。
    :returns: 已嵌入 vNext compaction request 数据块的 user prompt。
    """

    rendered = user_prompt_template.replace(
        _COMPACTION_REQUEST_PLACEHOLDER,
        _compaction_request_prompt_block_vnext(request),
    )
    if repair_feedback is None:
        return rendered
    repair_feedback_json = _repair_feedback_prompt_json_vnext(repair_feedback)
    return (
        rendered
        + f"\n\n{_REPAIR_FEEDBACK_BEGIN}\n"
        + json.dumps(
            repair_feedback_json,
            ensure_ascii=False,
            sort_keys=True,
        )
        + f"\n{_REPAIR_FEEDBACK_END}"
    )


def _repair_feedback_prompt_json_vnext(
    feedback: CompactRepairFeedbackV2,
) -> dict[str, JsonValue]:
    """把 typed internal feedback 投影为最小 LLM-facing repair JSON。

    :param feedback: 已脱敏且有界的 typed repair feedback。
    :returns: 只含完整重产动作与逐项问题的 JSON object。
    :raises TypeError: ``feedback`` 类型非法时抛出。
    """

    if not isinstance(feedback, CompactRepairFeedbackV2):
        raise TypeError("feedback must be CompactRepairFeedbackV2")
    return {
        "required_action": feedback.required_action,
        "issues": [
            {
                "code": issue.code.value,
                "json_path": issue.json_path,
                "message": issue.message,
                "source_labels": list(issue.source_labels),
            }
            for issue in feedback.issues
        ],
    }


def _compaction_request_prompt_block_vnext(request: CompactInputV2) -> str:
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
    return f"{_UNTRUSTED_COMPACTION_MATERIAL_BEGIN}\n{material_json}\n{_UNTRUSTED_COMPACTION_MATERIAL_END}"


def parse_conversation_compact_output_vnext(
    request: CompactInputV2,
    final_answer: str,
) -> CompactCandidateV2:
    """解析并校验 vNext strict JSON compact output。

    :param request: vNext compactor input。
    :param final_answer: LLM 返回的 strict JSON 文本。
    :returns: vNext compact output candidate。
    :raises TypeError: request 类型非法时抛出。
    :raises LLMCompactionProposalError: JSON 解析、schema 或 label contract 非法时抛出。
    """

    if not isinstance(request, CompactInputV2):
        raise TypeError("request must be CompactInputV2")
    try:
        candidate = _parse_vnext_proposal(final_answer)
    except LLMCompactionValidationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMCompactionValidationError(
            _parser_validation_report(exc),
            successful_response_identity=None,
        ) from exc
    return candidate


def _parse_vnext_proposal(final_answer: str) -> CompactCandidateV2:
    """解析 vNext LLM strict JSON proposal。

    :param final_answer: LLM final answer 原文。
    :returns: vNext compact output candidate。
    :raises LLMCompactionProposalError: 空文本、非 JSON 或缺少必需字段时抛出。
    """

    raw = final_answer.strip()
    if len(raw) < _MIN_PROPOSAL_LENGTH:
        raise LLMCompactionValidationError(
            _single_parser_issue_report(
                code=CompactValidationIssueCodeV2.BLANK_REQUIRED_TEXT,
                json_path="$",
                message="candidate 必须是非空 strict JSON object。",
            ),
            successful_response_identity=None,
        )
    try:
        parsed: JsonValue = json.loads(raw, object_pairs_hook=_strict_object_pairs)
    except JSONDecodeError as exc:
        raise LLMCompactionValidationError(
            _single_parser_issue_report(
                code=CompactValidationIssueCodeV2.INVALID_JSON,
                json_path="$",
                message=f"candidate 不是有效 JSON：{exc.msg}。",
            ),
            successful_response_identity=None,
        ) from exc
    proposal = _json_object(parsed, "proposal")
    _require_exact_keys(proposal, _TOP_LEVEL_FIELDS, path="$")
    schema_version = _required_string(
        proposal,
        _SCHEMA_VERSION_FIELD,
        parent_path="",
    )
    if schema_version != COMPACT_OUTPUT_SCHEMA_V2:
        raise ValueError(f"{_SCHEMA_VERSION_FIELD} is invalid")
    return CompactCandidateV2(
        schema=schema_version,
        session_summary=_session_summary_candidate_vnext(proposal),
        evidence_facts=_fact_candidates_vnext(proposal),
        answer_anchors=_answer_anchor_candidates_vnext(proposal),
        forward_intents=_forward_intent_candidates_vnext(proposal),
        reference_continuity=_reference_candidates_vnext(proposal),
        diagnostics=_diagnostics_vnext(proposal),
        explicitly_dropped_sources=_explicit_drops_v2(proposal),
    )


def _session_summary_candidate_vnext(
    proposal: Mapping[str, JsonValue],
) -> CompactSessionSummaryV2 | None:
    """解析 vNext session summary candidate。

    :param proposal: 已解析 proposal。
    :returns: session summary candidate；JSON null 时为 ``None``。
    """

    value = _required_value(proposal, _SESSION_SUMMARY_FIELD, parent_path="")
    if value is None:
        return None
    data = _json_object(value, _SESSION_SUMMARY_FIELD)
    _require_exact_keys(data, _SUMMARY_FIELDS, path=f"$.{_SESSION_SUMMARY_FIELD}")
    return CompactSessionSummaryV2(
        text=_required_string(data, _SUMMARY_TEXT_FIELD, parent_path=_SESSION_SUMMARY_FIELD),
        source_labels=_required_string_tuple(data, _SOURCE_LABELS_FIELD, parent_path=_SESSION_SUMMARY_FIELD),
    )


def _fact_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[CompactEvidenceFactV2, ...]:
    """解析 vNext evidence-backed fact candidates。

    :param proposal: 已解析 proposal。
    :returns: fact candidate tuple。
    """

    values = _required_array(
        proposal,
        _EVIDENCE_BACKED_FACTS_FIELD,
        parent_path="",
    )
    candidates: list[CompactEvidenceFactV2] = []
    for index, item in enumerate(values):
        item_path = _item_path(_EVIDENCE_BACKED_FACTS_FIELD, index)
        data = _json_object(item, item_path)
        _require_exact_keys(data, _FACT_FIELDS, path=f"$.{item_path}")
        candidates.append(
            CompactEvidenceFactV2(
                claim=_required_string(data, _CLAIM_TEXT_FIELD, parent_path=item_path),
                support_labels=_required_string_tuple(data, _EVIDENCE_LABELS_FIELD, parent_path=item_path),
                context_labels=_required_string_tuple(data, _CONTEXT_LABELS_FIELD, parent_path=item_path),
            )
        )
    return tuple(candidates)


def _answer_anchor_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[CompactAnswerAnchorV2, ...]:
    """解析 vNext answer anchor candidates。

    :param proposal: 已解析 proposal。
    :returns: answer anchor candidate tuple。
    """

    values = _required_array(
        proposal,
        _ANSWER_ANCHORS_FIELD,
        parent_path="",
    )
    candidates: list[CompactAnswerAnchorV2] = []
    for index, item in enumerate(values):
        item_path = _item_path(_ANSWER_ANCHORS_FIELD, index)
        data = _json_object(item, item_path)
        _require_exact_keys(data, _ANCHOR_FIELDS, path=f"$.{item_path}")
        candidates.append(
            CompactAnswerAnchorV2(
                title=_required_string(data, _ANCHOR_TITLE_FIELD, parent_path=item_path),
                detail=_required_string(data, _ANCHOR_DETAIL_FIELD, parent_path=item_path),
                source_labels=_required_string_tuple(data, _SOURCE_LABELS_FIELD, parent_path=item_path),
            )
        )
    return tuple(candidates)


def _forward_intent_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[CompactForwardIntentV2, ...]:
    """解析 vNext forward intent candidates。

    :param proposal: 已解析 proposal。
    :returns: forward intent candidate tuple。
    """

    values = _required_array(
        proposal,
        _FORWARD_INTENTS_FIELD,
        parent_path="",
    )
    candidates: list[CompactForwardIntentV2] = []
    for index, item in enumerate(values):
        item_path = _item_path(_FORWARD_INTENTS_FIELD, index)
        data = _json_object(item, item_path)
        _require_exact_keys(data, _INTENT_FIELDS, path=f"$.{item_path}")
        candidates.append(
            CompactForwardIntentV2(
                intent_type=_required_string(data, _INTENT_TYPE_FIELD, parent_path=item_path),
                text=_required_string(data, _TEXT_FIELD, parent_path=item_path),
                status=CompactForwardIntentStatusV2(
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


def _reference_candidates_vnext(proposal: Mapping[str, JsonValue]) -> tuple[CompactReferenceContinuityV2, ...]:
    """解析 vNext reference continuity candidates。

    :param proposal: 已解析 proposal。
    :returns: reference continuity candidate tuple。
    """

    values = _required_array(
        proposal,
        _REFERENCE_CONTINUITY_ITEMS_FIELD,
        parent_path="",
    )
    candidates: list[CompactReferenceContinuityV2] = []
    for index, item in enumerate(values):
        item_path = _item_path(_REFERENCE_CONTINUITY_ITEMS_FIELD, index)
        data = _json_object(item, item_path)
        _require_exact_keys(data, _REFERENCE_FIELDS, path=f"$.{item_path}")
        candidates.append(
            CompactReferenceContinuityV2(
                text=_required_string(data, _TEXT_FIELD, parent_path=item_path),
                reason=_required_string(data, _REASON_FIELD, parent_path=item_path),
                source_labels=_required_string_tuple(data, _SOURCE_LABELS_FIELD, parent_path=item_path),
            )
        )
    return tuple(candidates)


def _diagnostics_vnext(proposal: Mapping[str, JsonValue]) -> tuple[CompactCandidateDiagnosticV2, ...]:
    """解析 vNext compact diagnostics。

    :param proposal: 已解析 proposal。
    :returns: diagnostic tuple。
    """

    values = _required_array(
        proposal,
        _DIAGNOSTICS_FIELD,
        parent_path="",
    )
    diagnostics: list[CompactCandidateDiagnosticV2] = []
    for index, item in enumerate(values):
        item_path = _item_path(_DIAGNOSTICS_FIELD, index)
        data = _json_object(item, item_path)
        _require_exact_keys(data, _DIAGNOSTIC_FIELDS, path=f"$.{item_path}")
        diagnostics.append(
            CompactCandidateDiagnosticV2(
                code=_required_string(data, _CODE_FIELD, parent_path=item_path),
                message=_required_string(data, _MESSAGE_FIELD, parent_path=item_path),
                source_labels=_required_string_tuple(data, _SOURCE_LABELS_FIELD, parent_path=item_path),
            )
        )
    return tuple(diagnostics)


def _explicit_drops_v2(
    proposal: Mapping[str, JsonValue],
) -> tuple[CompactExplicitDropV2, ...]:
    """解析 explicit drop declarations。

    :param proposal: 已解析 proposal。
    :returns: typed drop tuple。
    """

    values = _required_array(proposal, _EXPLICITLY_DROPPED_SOURCES_FIELD, parent_path="")
    drops: list[CompactExplicitDropV2] = []
    for index, item in enumerate(values):
        item_path = _item_path(_EXPLICITLY_DROPPED_SOURCES_FIELD, index)
        data = _json_object(item, item_path)
        _require_exact_keys(data, _DROP_FIELDS, path=f"$.{item_path}")
        drops.append(
            CompactExplicitDropV2(
                source_label=_required_string(data, _SOURCE_LABEL_FIELD, parent_path=item_path),
                reason=CompactDropReasonV2(
                    _required_enum(
                        data,
                        _REASON_FIELD,
                        parent_path=item_path,
                        allowed_values=frozenset(item.value for item in CompactDropReasonV2),
                    )
                ),
            )
        )
    return tuple(drops)


def _strict_object_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """把 JSON object pairs 转为 dict，并在覆盖前拒绝 duplicate key。

    :param pairs: json decoder 提供的原始 key/value pairs。
    :returns: 无重复 key 的 JSON object。
    :raises ValueError: 任一 key 重复时抛出。
    """

    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key: {key}")
        result[key] = value
    return result


def _single_parser_issue_report(
    *,
    code: CompactValidationIssueCodeV2,
    json_path: str,
    message: str,
) -> CompactValidationReportV2:
    """构造单问题 strict parser report。

    :param code: 稳定 parser 问题码。
    :param json_path: 出错 JSON path。
    :param message: 脱敏、自解释消息。
    :returns: 单问题 validation report。
    """

    safe_path = truncate_diagnostic_text(
        redact_sensitive_diagnostic_values(
            json_path,
            redaction_marker=_REDACTED_SECRET,
        ),
        max_chars=_MAX_SAFE_OUTCOME_MESSAGE_CHARS,
        truncated_suffix=_TRUNCATED_SUFFIX,
    )
    safe_message = truncate_diagnostic_text(
        redact_sensitive_diagnostic_values(
            message,
            redaction_marker=_REDACTED_SECRET,
        ),
        max_chars=_MAX_SAFE_OUTCOME_MESSAGE_CHARS,
        truncated_suffix=_TRUNCATED_SUFFIX,
    )
    return CompactValidationReportV2(
        issues=(
            CompactValidationIssueV2(
                code=code,
                json_path=safe_path,
                message=safe_message,
            ),
        )
    )


def _parser_validation_report(
    error: KeyError | TypeError | ValueError,
) -> CompactValidationReportV2:
    """把 strict parser 内部异常归一为稳定 validation report。

    :param error: parser helper 抛出的边界错误。
    :returns: 可供 whole-candidate repair 使用的 validation report。
    """

    raw_message = str(error).strip("'")
    code = CompactValidationIssueCodeV2.INVALID_ENUM_VALUE
    json_path = "$"
    if raw_message.startswith("duplicate_json_key:"):
        code = CompactValidationIssueCodeV2.DUPLICATE_JSON_KEY
        # object_pairs_hook 尚不知道 nested object 的父路径；raw key 可能携带
        # secret，不能把它伪装成可回显的 JSON path。
        json_path = "$"
    elif raw_message.startswith("unknown_json_key at "):
        code = CompactValidationIssueCodeV2.UNKNOWN_JSON_KEY
        json_path = raw_message.removeprefix("unknown_json_key at ").partition(":")[0]
    elif raw_message.startswith("missing_required_key at "):
        code = CompactValidationIssueCodeV2.MISSING_REQUIRED_KEY
        json_path = raw_message.removeprefix("missing_required_key at ").partition(":")[0]
    elif raw_message.startswith("missing required key:"):
        code = CompactValidationIssueCodeV2.MISSING_REQUIRED_KEY
        json_path = f"$.{raw_message.partition(':')[2].strip()}"
    elif isinstance(error, TypeError):
        code = CompactValidationIssueCodeV2.INVALID_FIELD_TYPE
        json_path = f"$.{raw_message.partition(' ')[0]}"
    elif "must not be empty" in raw_message or "must be non-empty" in raw_message:
        code = CompactValidationIssueCodeV2.BLANK_REQUIRED_TEXT
    elif "invalid enum value" in raw_message or "schema is invalid" in raw_message:
        code = CompactValidationIssueCodeV2.INVALID_ENUM_VALUE
        json_path = f"$.{raw_message.partition(' ')[0]}"
    return _single_parser_issue_report(
        code=code,
        json_path=json_path,
        message=f"strict candidate contract rejected：{raw_message}",
    )


def _require_exact_keys(
    source: Mapping[str, JsonValue],
    expected: frozenset[str],
    *,
    path: str,
) -> None:
    """拒绝 unknown 与 missing JSON keys。

    :param source: 当前 JSON object。
    :param expected: exact required key set。
    :param path: 当前 object path。
    :returns: ``None``。
    :raises ValueError: key set 不精确时抛出。
    """

    actual = frozenset(source)
    unknown = tuple(sorted(actual - expected))
    missing = tuple(sorted(expected - actual))
    if unknown:
        raise ValueError(f"unknown_json_key at {path}: {','.join(unknown)}")
    if missing:
        raise ValueError(f"missing_required_key at {path}: {','.join(missing)}")


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
) -> tuple[JsonValue, ...]:
    """读取必需 JSON array 字段。

    :param source: JSON object。
    :param key: 字段名。
    :param parent_path: ``source`` 对应的父字段路径。
    :returns: JSON 值 tuple。
    :raises KeyError: 字段缺失时抛出。
    :raises TypeError: 字段不是 array 时抛出。
    """

    field_path = _field_path(parent_path, key)
    value = _required_value(source, key, parent_path=parent_path)
    if not isinstance(value, list):
        raise TypeError(f"{field_path} must be array")
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
        safe_value = truncate_diagnostic_text(
            redact_sensitive_diagnostic_values(value, redaction_marker=_REDACTED_SECRET),
            max_chars=_MAX_SAFE_OUTCOME_MESSAGE_CHARS,
            truncated_suffix=_TRUNCATED_SUFFIX,
        )
        raise ValueError(f"{field_path} has invalid enum value: {safe_value}")
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
    """

    if key not in source:
        return ()
    return _string_tuple(
        source[key],
        _field_path(parent_path, key),
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
    """

    field_path = _field_path(parent_path, key)
    return _string_tuple(
        _required_value(source, key, parent_path=parent_path),
        field_path,
    )


def _string_tuple(value: JsonValue, field_path: str) -> tuple[str, ...]:
    """校验 JSON 值为字符串数组。

    :param value: JSON 值。
    :param field_path: 待校验值的完整字段路径。
    :returns: 字符串 tuple。
    :raises TypeError: 值不是字符串数组时抛出。
    """

    if not isinstance(value, list):
        raise TypeError(f"{field_path} must be array")
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"{_item_path(field_path, index)} must be string")
        strings.append(item)
    return tuple(strings)


__all__ = [
    "LLMCompactionProposalError",
    "LLMCompactionValidationError",
    "LLMContextCompactor",
]
