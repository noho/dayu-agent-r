"""Host-owned LLM context compactor。

本模块把 Host ``CompactionRequest`` 映射为一次禁用工具的 Engine public
runner 调用，并把 LLM final answer 的 strict JSON proposal 转换为
``CompactCandidateV3``。它不写 EventLog、不写 artifact、不做
semantic repair loop，也不向 Service 暴露 prompt、candidate builder 或
policy seam。
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
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
from dayu.engine.contracts.structured_output import (
    JsonObjectStructuredOutputRequest,
    JsonSchemaStructuredOutputRequest,
    StructuredOutputCapability,
    StructuredOutputRequest,
)
from dayu.host.compact_structure import (
    COMPACT_OUTPUT_JSON_SCHEMA_NAME_V3,
    compact_output_json_schema_v3,
    compact_output_prompt_rules_v3,
    compact_output_template_v3,
    parse_compact_candidate_v3,
)
from dayu.host.compaction import (
    CompactionRequest,
    CompactorProposal,
    CompactorProposalError,
    CompactInputV3,
    CompactCandidateV3,
    ContextCompactor,
    CompactRepairFeedbackV3,
    CompactValidationIssueCodeV3,
    CompactValidationIssueV3,
    CompactValidationReportV3,
    compact_policy_usage_measurement_rules_v3,
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
_COMPACT_OUTPUT_TEMPLATE_PLACEHOLDER = "<<compact_output_template>>"
_COMPACT_OUTPUT_RULES_PLACEHOLDER = "<<compact_output_rules>>"
_UNTRUSTED_COMPACTION_MATERIAL_BEGIN = "UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN"
_UNTRUSTED_COMPACTION_MATERIAL_END = "UNTRUSTED_COMPACTION_MATERIAL_JSON_END"
_REPAIR_FEEDBACK_BEGIN = "REPAIR_FEEDBACK_JSON_BEGIN"
_REPAIR_FEEDBACK_END = "REPAIR_FEEDBACK_JSON_END"
_COMPACTOR_PROPOSAL_TIMEOUT_MESSAGE = "compactor proposal timed out"
_COMPACTOR_PROPOSAL_TIMEOUT_CANCEL_REASON = "compactor_proposal_timeout"
_COMPACTOR_PROJECTION_SCHEMA_VERSION = "compactor_input_projection.v2"


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
    """raw LLM JSON 未通过 strict v3 contract。

    :param report: 可直接进入 semantic repair 的脱敏 validation report。
    :param successful_response_identity: 已取得成功 Engine final 时的响应身份；
        直接调用 parser 时为 ``None``。
    """

    def __init__(
        self,
        report: CompactValidationReportV3,
        *,
        successful_response_identity: SuccessfulRunnerResponseIdentity | None,
    ) -> None:
        """初始化 strict parser validation error。

        :param report: strict parser 产生的 validation report。
        :param successful_response_identity: 成功 Engine final 的响应身份。
        :returns: ``None``。
        :raises TypeError: report 类型非法时抛出。
        """

        if not isinstance(report, CompactValidationReportV3):
            raise TypeError("report must be CompactValidationReportV3")
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
        if user_prompt_template.count(_COMPACT_OUTPUT_TEMPLATE_PLACEHOLDER) != 1:
            raise ValueError(
                "user_prompt_template must contain exactly one "
                "<<compact_output_template>> placeholder"
            )
        if user_prompt_template.count(_COMPACT_OUTPUT_RULES_PLACEHOLDER) != 1:
            raise ValueError(
                "user_prompt_template must contain exactly one "
                "<<compact_output_rules>> placeholder"
            )
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
        repair_feedback: CompactRepairFeedbackV3 | None,
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
        repair_feedback: CompactRepairFeedbackV3 | None,
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
        output_schema = compact_output_json_schema_v3()
        structured_output = _structured_output_request_v3(
            capability=self._runner_spec.structured_output_capability,
            output_schema=output_schema,
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
            repair_feedback=repair_feedback,
            structured_output=structured_output,
        )
        roles = tuple(message.role.value for message in agent_request.messages)
        projection = _compactor_input_projection_json(
            request=request,
            compact_input=compact_input,
            repair_feedback=repair_feedback,
            output_schema=output_schema,
            structured_output=structured_output,
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
    request: CompactInputV3,
    runner_spec: RunnerSpec,
    runner_options: RunnerCallOptions,
    agent_policy: AgentPolicy,
    system_prompt: str,
    user_prompt_template: str,
    cancellation_token: CancellationToken,
    *,
    compactor_engine_run_id: str,
    repair_feedback: CompactRepairFeedbackV3 | None,
    structured_output: StructuredOutputRequest | None,
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
    :param structured_output: 由 Runner capability 唯一选择的显式 request。
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
        structured_output=structured_output,
        tool_schemas=(),
        tool_executor=_RejectingToolExecutor(),
        cancellation_token=cancellation_token,
    )


def _structured_output_request_v3(
    *,
    capability: StructuredOutputCapability,
    output_schema: Mapping[str, JsonValue],
) -> StructuredOutputRequest | None:
    """只按 typed Runner capability 选择 compactor structured output request。

    :param capability: Runner 声明的 provider-neutral capability。
    :param output_schema: 本次 structure owner 生成的 concrete schema instance。
    :returns: ``None``、JSON object request 或绑定同一 schema instance 的 JSON
        Schema request。
    :raises TypeError: capability 不属于封闭 enum 时抛出。
    """

    if capability is StructuredOutputCapability.NONE:
        return None
    if capability is StructuredOutputCapability.JSON_OBJECT:
        return JsonObjectStructuredOutputRequest()
    if capability is StructuredOutputCapability.JSON_SCHEMA:
        return JsonSchemaStructuredOutputRequest(
            name=COMPACT_OUTPUT_JSON_SCHEMA_NAME_V3,
            schema=output_schema,
            strict=True,
        )
    raise TypeError("capability must be StructuredOutputCapability")


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
    compact_input: CompactInputV3,
    repair_feedback: CompactRepairFeedbackV3 | None,
    output_schema: Mapping[str, JsonValue],
    structured_output: StructuredOutputRequest | None,
) -> Mapping[str, JsonValue]:
    """构造 compactor input projection artifact body。

    :param request: Host compaction request。
    :param compact_input: 已冻结的 vNext compactor input。
    :param repair_feedback: 本次 attempt 的 semantic repair feedback。
    :param output_schema: 本次 prompt/transport 共用的 concrete schema instance。
    :param structured_output: 本次显式 Engine structured-output request。
    :returns: 可作为 artifact 写入的 projection JSON。
    """

    return {
        "projection_kind": "compactor_input_projection",
        "schema_version": _COMPACTOR_PROJECTION_SCHEMA_VERSION,
        "compaction_request_digest": request.digest(),
        "source_boundary_refs": list(_compactor_source_boundary_refs(request)),
        "compact_input": compact_input.to_json(),
        "repair_feedback": (None if repair_feedback is None else repair_feedback.to_json()),
        "structured_output_mode": _structured_output_mode(structured_output),
        "structured_output_schema_name": COMPACT_OUTPUT_JSON_SCHEMA_NAME_V3,
        "structured_output_schema_digest": sha256_digest_json(output_schema),
    }


def _structured_output_mode(request: StructuredOutputRequest | None) -> str:
    """返回 durable projection 使用的显式 structured-output mode。

    :param request: 本次 typed request。
    :returns: ``none``、``json_object`` 或 ``json_schema``。
    """

    if request is None:
        return StructuredOutputCapability.NONE.value
    if isinstance(request, JsonObjectStructuredOutputRequest):
        return StructuredOutputCapability.JSON_OBJECT.value
    return StructuredOutputCapability.JSON_SCHEMA.value


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
    request: CompactInputV3,
    user_prompt_template: str,
    *,
    repair_feedback: CompactRepairFeedbackV3 | None,
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
    rendered = rendered.replace(
        _COMPACT_OUTPUT_TEMPLATE_PLACEHOLDER,
        json.dumps(
            compact_output_template_v3(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
    )
    rendered = rendered.replace(
        _COMPACT_OUTPUT_RULES_PLACEHOLDER,
        _compact_output_rules_prompt_block_vnext(),
    )
    if repair_feedback is None:
        return rendered
    repair_feedback_json = _repair_feedback_prompt_json_vnext(repair_feedback)
    return (
        rendered
        + "\n\n修复动作：前一次完整输出未通过校验。反馈中的 code 只是问题类别；"
        "json_path 是需修正的字段位置；message 是具体错误与修复动作；source_labels "
        "是相关输入引用标签，不是业务事实。issues 是有界、已脱敏的问题摘要；必须结合"
        "本消息中的同一完整输入、完整字段规则与 concrete template 重新生成整个 JSON "
        "object，不得输出 patch，不得依赖或复用前一次输出。前次输出编号："
        + str(repair_feedback.previous_attempt_number)
        + f"。\n{_REPAIR_FEEDBACK_BEGIN}\n"
        + json.dumps(
            repair_feedback_json,
            ensure_ascii=False,
            sort_keys=True,
        )
        + f"\n{_REPAIR_FEEDBACK_END}"
    )


def _compact_output_rules_prompt_block_vnext() -> str:
    """渲染 structure 与 policy usage 两个 owner 的 LLM-facing 规则块。

    :returns: 精简字段结构规则与 exact 字符计量规则。
    """

    structure_rules = json.dumps(
        compact_output_prompt_rules_v3(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    measurement_rules = json.dumps(
        dict(compact_policy_usage_measurement_rules_v3()),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (
        structure_rules
        + "\n\n字符计量规则（对应 output_caps 中各字符 cap）：\n"
        + measurement_rules
    )


def _repair_feedback_prompt_json_vnext(
    feedback: CompactRepairFeedbackV3,
) -> dict[str, JsonValue]:
    """把 typed internal feedback 投影为最小 LLM-facing repair JSON。

    :param feedback: 已脱敏且有界的 typed repair feedback。
    :returns: 只含完整重产动作与逐项问题的 JSON object。
    :raises TypeError: ``feedback`` 类型非法时抛出。
    """

    if not isinstance(feedback, CompactRepairFeedbackV3):
        raise TypeError("feedback must be CompactRepairFeedbackV3")
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


def _compaction_request_prompt_block_vnext(request: CompactInputV3) -> str:
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
    request: CompactInputV3,
    final_answer: str,
) -> CompactCandidateV3:
    """解析并校验 vNext strict JSON compact output。

    :param request: vNext compactor input。
    :param final_answer: LLM 返回的 strict JSON 文本。
    :returns: vNext compact output candidate。
    :raises TypeError: request 类型非法时抛出。
    :raises LLMCompactionProposalError: JSON 解析、schema 或 label contract 非法时抛出。
    """

    if not isinstance(request, CompactInputV3):
        raise TypeError("request must be CompactInputV3")
    try:
        return parse_compact_candidate_v3(final_answer)
    except (TypeError, ValueError) as exc:
        raise LLMCompactionValidationError(
            _structure_validation_report(exc),
            successful_response_identity=None,
        ) from exc


def _structure_validation_report(error: TypeError | ValueError) -> CompactValidationReportV3:
    """把 structure owner 的 strict error 投影为 bounded repair report。

    :param error: structure parser 抛出的类型或值错误。
    :returns: 单一、脱敏且稳定排序的 validation report。
    """

    message = _safe_outcome_text(str(error))
    prefix = message.partition(":")[0]
    code_by_prefix = {
        "blank_required_text": CompactValidationIssueCodeV3.BLANK_REQUIRED_TEXT,
        "duplicate_json_key": CompactValidationIssueCodeV3.DUPLICATE_JSON_KEY,
        "duplicate_source_label": CompactValidationIssueCodeV3.DUPLICATE_SOURCE_LABEL,
        "invalid_enum_value": CompactValidationIssueCodeV3.INVALID_ENUM_VALUE,
        "invalid_field_type": CompactValidationIssueCodeV3.INVALID_FIELD_TYPE,
        "invalid_json": CompactValidationIssueCodeV3.INVALID_JSON,
        "missing_required_key": CompactValidationIssueCodeV3.MISSING_REQUIRED_KEY,
        "unknown_json_key": CompactValidationIssueCodeV3.UNKNOWN_JSON_KEY,
    }
    code = code_by_prefix.get(
        prefix,
        CompactValidationIssueCodeV3.INVALID_FIELD_TYPE,
    )
    path = _structure_error_path(message)
    issue = CompactValidationIssueV3(
        code=code,
        json_path=path,
        message=message,
        source_labels=(),
    )
    return CompactValidationReportV3(issues=(issue,))


def _structure_error_path(message: str) -> str:
    """从 structure error 中提取安全 JSON path。

    :param message: 已脱敏、截断的 structure error 文本。
    :returns: 以 ``$`` 开头的 path；无法提取时返回 root。
    """

    suffix = message.partition(":")[2].strip()
    return suffix if suffix.startswith("$") else "$"
