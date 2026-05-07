"""人工验证 Host P4 context overflow compact retry。

当前 smoke 使用 fake Engine overflow，不代表真实 provider 覆盖。它稳定
展示同一 Run 下只接纳一次用户输入、Host 追加 compact 事实、随后用
compacted RunInput 启动第二次 internal Engine attempt。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, cast

from dayu.contracts import CancellationToken
from dayu.engine import (
    AgentMessageRole,
    AgentPolicy,
    ContextBudgetSnapshot,
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventData,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    RunFailedData,
    RunnerCallOptions,
    RunnerSpec,
    UserMessage,
)
from dayu.host._conversation_memory import (
    AssumptionRegister,
    ConversationMemoryPatch,
    ConversationMemorySnapshot,
    ConversationMemoryStore,
    ConversationPinnedState,
    ConversationRawTurn,
    MemoryIngestionPolicy,
    MemoryProducerKind,
    MemoryProvenance,
    MemoryScope,
    MemoryTrustLevel,
    TaskFrame,
    UserPreferenceProfileRef,
)
from dayu.host._run_harness import LocalRunHarness
from dayu.host.contracts import (
    HostContextAttemptRetryData,
    HostContextCompactCompletedData,
    HostContextCompactFailedData,
    HostContextCompactRequestedData,
    HostContextOverflowObservedData,
    RunEvent,
    RunEventCursor,
    RunInput,
    RunOptions,
    RunFailedResult,
    RunResult,
    RunSucceededResult,
    StartRunRequest,
    UserInputAcceptedData,
)

_SMOKE_PREFIX: str = "[host-context-compaction]"
_CASE_FAKE_OVERFLOW: str = "fake-overflow"
_CASE_INTERNAL_ECHO_FILTER: str = "internal-echo-filter"
_INTERNAL_ECHO_FINAL_CONTENT: str = (
    "## Host Memory\n## Tool Facts\n"
    "tool_fact_id=tool_fact:run:1; "
    "cursor_fingerprint=fp; source_event_cursor=1; scope_token=secret"
)
_SENSITIVE_OUTPUT_MARKERS: tuple[str, ...] = (
    "scope_token",
    "secret",
    _INTERNAL_ECHO_FINAL_CONTENT,
)
_CaseName = Literal["fake-overflow", "internal-echo-filter"]


@dataclass(frozen=True, slots=True)
class _Args:
    """smoke 命令行参数。"""

    case: _CaseName
    log_level: str


def _utc_now() -> datetime:
    """返回当前 UTC 时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _SmokeMemoryStore:
    """固定 snapshot 的 smoke memory store。"""

    snapshot: ConversationMemorySnapshot

    async def project_run_events(self, events: tuple[RunEvent, ...]) -> None:
        """接收终态后 memory projection。

        :param events: RunEvent 元组。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        logging.getLogger(__name__).debug(
            "smoke.memory_projected event_count=%d", len(events)
        )

    async def get_snapshot(self, session_id: str) -> ConversationMemorySnapshot:
        """读取固定 snapshot。

        :param session_id: 会话 id。
        :returns: ConversationMemorySnapshot。
        :raises Exception: 不主动抛出异常。
        """

        return self.snapshot

    async def apply_patch(self, patch: ConversationMemoryPatch) -> None:
        """smoke 不支持 patch。

        :param patch: memory patch。
        :returns: 无返回值。
        :raises NotImplementedError: 始终抛出。
        """

        raise NotImplementedError(type(patch).__name__)


@dataclass(slots=True)
class _FakeOverflowProxy:
    """第一次 overflow、第二次成功的 fake proxy。"""

    request_message_counts: list[int] = field(default_factory=list)
    final_content: str = "fake overflow compact retry succeeded"

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回 fake EngineEvent 流。

        :param request: Host StartRunRequest。
        :param cancellation_token: 取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.request_message_counts.append(len(request.input.messages))
        if len(self.request_message_counts) == 1:
            return _iter_events(
                (
                    _engine_event(
                        sequence=0,
                        event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
                        data=ContextCompactionRequestedData(
                            iteration_id="iter-0",
                            budget_state=ContextBudgetSnapshot(
                                prompt_tokens=0,
                                completion_tokens=0,
                                total_tokens=0,
                            ),
                            reason="context_compaction_required",
                        ),
                    ),
                    _engine_event(
                        sequence=1,
                        event_type=EngineEventType.RUN_FAILED,
                        data=RunFailedData(
                            error_code="context_compaction_required",
                            message="provider context overflow",
                            recoverable=True,
                        ),
                    ),
                )
            )
        return _iter_events(
            (
                _engine_event(
                    sequence=2,
                    event_type=EngineEventType.FINAL_ANSWER,
                    data=FinalAnswerData(
                        content=self.final_content,
                        filtered=False,
                        degraded=False,
                        finish_reason=FinishReason.STOP,
                    ),
                ),
            )
        )


def _snapshot() -> ConversationMemorySnapshot:
    """构造 smoke memory snapshot。

    :returns: ConversationMemorySnapshot。
    :raises Exception: 不主动抛出异常。
    """

    provenance = MemoryProvenance(
        source_run_id="smoke-old-run",
        source_event_cursor=RunEventCursor(sequence=1),
        producer_kind=MemoryProducerKind.HOST_USER_INPUT,
        ingestion_policy=MemoryIngestionPolicy.PRIMARY_SESSION_CANONICAL,
        scope=MemoryScope.SESSION,
        trust_level=MemoryTrustLevel.USER_PROVIDED,
    )
    old_turn = ConversationRawTurn(
        turn_id="smoke-old-turn",
        user_text="旧财报问题摘要。" * 300,
        assistant_final="旧回答摘要。" * 300,
        user_provenance=provenance,
        assistant_provenance=provenance,
    )
    return ConversationMemorySnapshot(
        session_id="smoke-context-session",
        pinned_state=ConversationPinnedState(current_goal="分析财报"),
        task_frame=TaskFrame(topic_ref="revenue"),
        verified_claims=(),
        assumptions=AssumptionRegister(),
        evidence_anchors=(),
        recent_raw_turns=(old_turn,),
        older_raw_turns=(),
        tool_facts=(),
        user_preference_ref=UserPreferenceProfileRef(),
    )


def _request() -> StartRunRequest:
    """构造 smoke StartRunRequest。

    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id="smoke-context-session",
        run_id="smoke-context-run",
        input=RunInput(
            messages=(
                UserMessage(
                    role=AgentMessageRole.USER,
                    content="请继续分析 A 公司收入增长原因。",
                ),
            )
        ),
        options=RunOptions(
            runner_spec=RunnerSpec(
                provider="openai",
                model="fake-model",
                endpoint="https://example.test/v1/chat/completions",
                api_key_ref="TEST_KEY",
                headers={},
                supports_tool_calling=True,
                supports_streaming=True,
                supports_stream_usage=False,
                default_timeout_seconds=30.0,
                max_retries=0,
                provider_request=None,
            ),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=True,
            ),
            agent_policy=AgentPolicy(
                max_iterations=3,
                continuation_max_attempts=1,
                allow_tool_calls=True,
            ),
            stream=True,
            disable_tools=True,
            tool_schemas=(),
        ),
    )


def _engine_event(
    *,
    sequence: int,
    event_type: EngineEventType,
    data: EngineEventData,
) -> EngineEvent:
    """构造 fake EngineEvent。

    :param sequence: 事件序号。
    :param event_type: 事件类型。
    :param data: 事件 data。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id=f"smoke-engine-{sequence}",
        sequence=sequence,
        occurred_at=_utc_now(),
        session_id="smoke-context-session",
        run_id="smoke-context-run",
        type=event_type,
        data=data,
        metadata=None,
    )


async def _iter_events(
    events: tuple[EngineEvent, ...],
) -> AsyncIterator[EngineEvent]:
    """按顺序产出 EngineEvent。

    :param events: EngineEvent 元组。
    :returns: EngineEvent 异步迭代器。
    :raises Exception: 不主动抛出异常。
    """

    for event in events:
        yield event


async def _run_fake_overflow() -> None:
    """运行 fake overflow smoke。

    :returns: 无返回值。
    :raises Exception: 运行失败时透传。
    """

    await _run_smoke(proxy=_FakeOverflowProxy())


async def _run_internal_echo_filter() -> None:
    """运行 final answer internal echo gate smoke。

    :returns: 无返回值。
    :raises Exception: 运行失败时透传。
    """

    await _run_smoke(
        proxy=_FakeOverflowProxy(final_content=_INTERNAL_ECHO_FINAL_CONTENT)
    )


async def _run_smoke(*, proxy: _FakeOverflowProxy) -> None:
    """运行 Host context compaction smoke 并打印人工观察摘要。

    :param proxy: fake overflow proxy。
    :returns: 无返回值。
    :raises RuntimeError: smoke 关键不变量不满足时抛出。
    """

    memory_store: ConversationMemoryStore = _SmokeMemoryStore(_snapshot())
    harness = LocalRunHarness(proxy=proxy, memory_store=memory_store)
    stream = await harness.start_run(_request())
    events: list[RunEvent] = []
    async for event in stream.events:
        events.append(event)
        _safe_print(_event_summary(event))
    result = await harness.get_run_result("smoke-context-run")
    _safe_print(_event_counts_summary(tuple(events)))
    for index, message_count in enumerate(proxy.request_message_counts):
        _safe_print(
            f"{_SMOKE_PREFIX} attempt index={index} "
            f"message_count={message_count}"
        )
    _safe_print(f"{_SMOKE_PREFIX} proxy.attempts {len(proxy.request_message_counts)}")
    _safe_print(_result_summary(result))
    _assert_observation(events=tuple(events), proxy=proxy, result=result)


def _event_summary(event: RunEvent) -> str:
    """生成不含大结果和 token 的事件摘要。

    :param event: RunEvent。
    :returns: 单行摘要。
    :raises Exception: 不主动抛出异常。
    """

    data = event.data
    suffix = ""
    if isinstance(data, UserInputAcceptedData):
        suffix = f" turn_id={data.turn_id} scope={data.scope.value}"
    elif isinstance(data, HostContextOverflowObservedData):
        suffix = (
            f" attempt={data.attempt_index} "
            f"engine_error_code={data.engine_error_code} "
            f"recoverable={data.recoverable}"
        )
    elif isinstance(data, HostContextCompactRequestedData):
        suffix = (
            f" attempt={data.attempt_index} "
            f"before={data.before_token_estimate} "
            f"before_chars={data.before_char_size}"
        )
    elif isinstance(data, HostContextCompactCompletedData):
        suffix = (
            f" attempt={data.attempt_index} "
            f"before={data.before_token_estimate} "
            f"after={data.after_token_estimate} "
            f"before_chars={data.before_char_size} "
            f"after_chars={data.after_char_size} "
            f"reduced={data.reduced}"
        )
    elif isinstance(data, HostContextCompactFailedData):
        suffix = f" reason={data.reason.value}"
    elif isinstance(data, HostContextAttemptRetryData):
        suffix = (
            f" from_attempt={data.from_attempt_index} "
            f"next_attempt={data.next_attempt_index}"
        )
    return (
        f"{_SMOKE_PREFIX} event cursor={event.cursor.sequence} "
        f"type={event.type.value} source={event.source.value}{suffix}"
    )


def _event_counts_summary(events: tuple[RunEvent, ...]) -> str:
    """生成关键事件计数摘要。

    :param events: 已观察到的 RunEvent。
    :returns: 事件计数摘要。
    :raises Exception: 不主动抛出异常。
    """

    user_input_count = sum(
        isinstance(event.data, UserInputAcceptedData) for event in events
    )
    overflow_count = sum(
        isinstance(event.data, HostContextOverflowObservedData)
        for event in events
    )
    requested_count = sum(
        isinstance(event.data, HostContextCompactRequestedData)
        for event in events
    )
    completed_count = sum(
        isinstance(event.data, HostContextCompactCompletedData)
        for event in events
    )
    retry_count = sum(
        isinstance(event.data, HostContextAttemptRetryData) for event in events
    )
    return (
        f"{_SMOKE_PREFIX} counts "
        f"user_input_accepted={user_input_count} "
        f"context_overflow_observed={overflow_count} "
        f"context_compact_requested={requested_count} "
        f"context_compact_completed={completed_count} "
        f"context_attempt_retrying={retry_count}"
    )


def _result_summary(result: RunResult | None) -> str:
    """生成终态结果摘要，避免输出 final answer 正文。

    :param result: Host run result；无终态时为 ``None``。
    :returns: 终态结果摘要。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(result, RunSucceededResult):
        return (
            f"{_SMOKE_PREFIX} result RunSucceededResult "
            f"filtered={result.filtered} degraded={result.degraded} "
            f"terminal_cursor={result.terminal_event_cursor.sequence}"
        )
    if isinstance(result, RunFailedResult):
        return (
            f"{_SMOKE_PREFIX} result RunFailedResult "
            f"error_code={result.error_code} recoverable={result.recoverable} "
            f"terminal_cursor={result.terminal_event_cursor.sequence}"
        )
    if result is None:
        return f"{_SMOKE_PREFIX} result None"
    return f"{_SMOKE_PREFIX} result {type(result).__name__}"


def _assert_observation(
    *,
    events: tuple[RunEvent, ...],
    proxy: _FakeOverflowProxy,
    result: RunResult | None,
) -> None:
    """校验 smoke 关键观察目标，避免脚本静默退化。

    :param events: 已观察到的 RunEvent。
    :param proxy: fake overflow proxy。
    :param result: Host run result。
    :returns: 无返回值。
    :raises RuntimeError: 任一关键观察目标不满足时抛出。
    """

    user_input_count = sum(
        isinstance(event.data, UserInputAcceptedData) for event in events
    )
    if user_input_count != 1:
        raise RuntimeError("USER_INPUT_ACCEPTED count is not 1")
    if not any(
        isinstance(event.data, HostContextOverflowObservedData)
        for event in events
    ):
        raise RuntimeError("context_overflow_observed is missing")
    if not any(
        isinstance(event.data, HostContextCompactRequestedData)
        for event in events
    ):
        raise RuntimeError("context_compact_requested is missing")
    if not any(
        isinstance(event.data, HostContextCompactCompletedData)
        and event.data.after_token_estimate < event.data.before_token_estimate
        for event in events
    ):
        raise RuntimeError("context_compact_completed reduction is missing")
    if not any(
        isinstance(event.data, HostContextAttemptRetryData)
        and event.data.next_attempt_index == 1
        for event in events
    ):
        raise RuntimeError("context_attempt_retrying next attempt is missing")
    if len(proxy.request_message_counts) != 2:
        raise RuntimeError("second internal attempt did not start")
    if not isinstance(result, RunSucceededResult):
        raise RuntimeError("smoke did not finish with RunSucceededResult")


def _safe_print(line: str) -> None:
    """打印经过敏感标记检查的单行 smoke 输出。

    :param line: 待输出文本。
    :returns: 无返回值。
    :raises RuntimeError: 文本包含禁止输出的敏感标记时抛出。
    """

    if any(marker in line for marker in _SENSITIVE_OUTPUT_MARKERS):
        raise RuntimeError("smoke output contains sensitive marker")
    print(line)


def _parse_args() -> _Args:
    """解析命令行参数。

    :returns: 解析后的参数。
    :raises SystemExit: 参数非法时由 argparse 抛出。
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=(_CASE_FAKE_OVERFLOW, _CASE_INTERNAL_ECHO_FILTER),
        required=True,
    )
    parser.add_argument("--log-level", default="INFO")
    namespace = parser.parse_args()
    return _Args(
        case=cast(_CaseName, namespace.case),
        log_level=str(namespace.log_level),
    )


async def _amain() -> None:
    """异步主入口。

    :returns: 无返回值。
    :raises Exception: smoke 失败时透传。
    """

    args = _parse_args()
    logging.basicConfig(level=args.log_level.upper())
    if args.case == _CASE_FAKE_OVERFLOW:
        await _run_fake_overflow()
    elif args.case == _CASE_INTERNAL_ECHO_FILTER:
        await _run_internal_echo_filter()


if __name__ == "__main__":
    asyncio.run(_amain())
