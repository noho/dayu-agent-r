"""Host ToolRuntimeExecutor P6-S3 测试。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import signal
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSnapshot, ToolAwaitSpec
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolCallable, ToolDefinition
from dayu.contracts.tool_execution import (
    AsyncDirectToolExecutionCapability,
    ProcessBackedToolContext,
    ProcessBackedToolExecutionCapability,
    ThreadBackedToolExecutionCapability,
    ToolExecutionCapability,
    process_tool_completed_envelope,
    process_tool_failed_envelope,
)
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)
from dayu.host.api import WaitAdapterKey
from dayu.host.durable.state import WaitResumePolicy
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    FetchMoreRequest,
    HostEventRef,
    HostPayloadRef,
    HostToolFactAcceptPort,
    HostToolAwaitingAcceptPort,
    InMemoryToolTraceDiagnosticEmitter,
    ToolAcceptRejectReason,
    ToolAcceptRetryPolicy,
    ToolAcceptCall,
    ToolAcceptDiagnostics,
    ToolAcceptGovernance,
    ToolAcceptIdentity,
    ToolAcceptIdempotency,
    ToolAcceptResult,
    ToolFactAcceptCandidate,
    ToolFactAcceptResult,
    ToolFactAcceptTimedOut,
    ToolFactAcceptedAck,
    ToolFactKind,
    ToolFactRejectedAck,
    ToolAwaitingAcceptRejectReason,
    ToolAwaitingAcceptCandidate,
    ToolAwaitingAcceptResult,
    ToolAwaitingAcceptedAck,
    ToolAwaitingAcceptTimedOut,
    ToolAwaitingEventRef,
    ToolAwaitingRejectedAck,
    ToolPolicyDecision,
    ToolPolicyDecisionKind,
    ProcessBackedToolExecutionCapsule,
    ThreadBackedToolExecutionCapsule,
    ToolDispatcher,
    ToolExecutionCapsule,
    ToolExecutionCapsuleFactory,
    ToolExecutionMode,
    ToolInterruptStepResult,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
    ToolRuntimePolicyView,
    ToolRuntimeToolPolicy,
    ToolSideEffectKind,
    TruncationManager,
)
from dayu.host.wait_adapter import (
    WaitActivationAdapterRegistration,
    WaitActivationRegistry,
    WaitActivationRequest,
    WaitAdapterBinding,
    WaitAdapterRegistry,
    WaitExternalJobRefSource,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.errors import HostTransactionRetryExhaustedError
from dayu.host.tool_duplicate_governance import (
    DuplicateAwaitingAcceptedEntry,
    DuplicateDurableMissingReason,
    DuplicateGovernanceRequest,
    InMemoryAttemptDuplicateGovernance,
)
from dayu.host.tooling import (
    ProcessCapsuleInterruptPolicy,
    default_framework_tool_policy_view,
)
from dayu.runtime.interruptible_process import InterruptibleProcessHandle
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef

_SESSION_ID = "session-toolruntime"
_RUN_ID = "run-toolruntime"
_ATTEMPT_ID = "attempt-toolruntime"
_EXECUTION_ID = "execution-toolruntime"
_ITERATION_ID = "iteration-toolruntime"
_POLICY_DIGEST = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
_DEFAULT_TOOL_TIMEOUT_SECONDS = 10.0
_FAST_TOOL_TIMEOUT_SECONDS = 0.001
_OVERSIZED_INLINE_TEXT_LENGTH = 70010
_OVERSIZED_TRUNCATED_TEXT_LIMIT = 70000
_TEST_PROCESS_CLOSE_DEFAULT_GRACE_SECONDS = 1.0
_CUSTOM_PROCESS_CLOSE_GRACE_SECONDS = 0.73
_RECORDED_PROCESS_HANDLE_CLOSE_KILL_GRACES: list[float] = []
_ORIGINAL_INTERRUPTIBLE_PROCESS_HANDLE_CLOSE = InterruptibleProcessHandle.close


async def _recording_interruptible_process_handle_close(
    handle: InterruptibleProcessHandle,
    *,
    kill_grace_seconds: float = _TEST_PROCESS_CLOSE_DEFAULT_GRACE_SECONDS,
) -> None:
    """记录 InterruptibleProcessHandle.close 收到的 kill grace 后继续真实关闭。

    :param handle: 当前 process handle。
    :param kill_grace_seconds: close best-effort kill 等待秒数。
    :returns: ``None``。
    """

    _RECORDED_PROCESS_HANDLE_CLOSE_KILL_GRACES.append(kill_grace_seconds)
    await _ORIGINAL_INTERRUPTIBLE_PROCESS_HANDLE_CLOSE(
        handle,
        kill_grace_seconds=kill_grace_seconds,
    )


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终为 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        """

        return None


class _AlreadyCancelledToken:
    """测试用已取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终为 ``True``。
        """

        return True

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 测试取消原因。
        """

        return "test_cancel"

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 本测试不关心请求时间，返回 ``None``。
        """

        return None


class _MutableCancellationToken:
    """测试用可翻转取消 token。"""

    def __init__(self) -> None:
        """初始化未取消 token。

        :returns: ``None``。
        """

        self._cancel_reason: str | None = None

    def cancel(self, reason: str) -> None:
        """请求取消。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self._cancel_reason = reason

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已调用 ``cancel`` 时返回 ``True``。
        """

        return self._cancel_reason is not None

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 已取消时返回取消原因，否则返回 ``None``。
        """

        return self._cancel_reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 本测试不关心请求时间，返回 ``None``。
        """

        return None


class _CountingCallable:
    """返回固定成功结果并记录调用次数的 fake 工具。"""

    def __init__(self, value: JsonValue) -> None:
        """初始化 fake callable。

        :param value: 工具成功载荷。
        :returns: ``None``。
        """

        self._value = value
        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回固定成功结果。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 工具成功 outcome。
        """

        del call, context
        self.call_count += 1
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value=self._value, meta=None)
        )


class _OutcomeCallable:
    """返回指定工具 outcome 并记录调用次数的 fake 工具。"""

    def __init__(self, outcome: ToolExecutionOutcome) -> None:
        """初始化 fake callable。

        :param outcome: 预设工具 outcome。
        :returns: ``None``。
        """

        self._outcome = outcome
        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回预设 outcome。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 预设工具 outcome。
        """

        del call, context
        self.call_count += 1
        return self._outcome


class _BlockingCallable:
    """挂起直到被取消的 fake 工具。"""

    def __init__(self) -> None:
        """初始化 fake callable。

        :returns: ``None``。
        """

        self.call_count = 0
        self.cancelled = False
        self._ready = asyncio.Event()

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """等待一个不会主动完成的事件。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 本测试不会正常返回。
        :raises asyncio.CancelledError: ToolRuntime timeout 取消等待时抛出。
        """

        del call, context
        self.call_count += 1
        try:
            await self._ready.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value={"unexpected": True}, meta=None)
        )


class _AwaitingCallable:
    """返回 awaiting outcome 的 fake 工具。"""

    def __init__(self, *, snapshot: ToolAwaitSnapshot | None = None) -> None:
        """初始化 fake callable。

        :param snapshot: 可选等待时点快照引用。
        :returns: ``None``。
        """

        self._snapshot = snapshot
        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回 P6-S3 不支持的 awaiting outcome。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: awaiting outcome。
        """

        del call, context
        self.call_count += 1
        return ToolAwaitingOutcome(
            await_spec=ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token="resume-token",
            ),
            snapshot=self._snapshot,
        )


class _BlockingAwaitingCallable:
    """等待测试事件释放后返回 awaiting outcome 的 fake 工具。"""

    def __init__(self, *, entered: asyncio.Event, release: asyncio.Event) -> None:
        """初始化阻塞 awaiting fake callable。

        :param entered: callable 进入时置位的事件。
        :param release: 允许返回 awaiting outcome 的事件。
        :returns: ``None``。
        """

        self._entered = entered
        self._release = release
        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """等待 release 事件后返回 awaiting outcome。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: awaiting outcome。
        """

        del call, context
        self.call_count += 1
        self._entered.set()
        await self._release.wait()
        return ToolAwaitingOutcome(
            await_spec=ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token="resume-token",
            ),
            snapshot=None,
        )


@dataclass(frozen=True, slots=True)
class _SleepingProcessTarget:
    """测试用非协作子进程目标。"""

    sleep_seconds: float

    def __call__(self) -> JsonValue:
        """阻塞到自然结束后返回结果。

        :returns: JSON-like 结果。
        """

        time.sleep(self.sleep_seconds)
        return {"late": True}


@dataclass(frozen=True, slots=True)
class _IgnoreTerminateProcessTarget:
    """测试用忽略 SIGTERM 的非协作子进程目标。"""

    sleep_seconds: float

    def __call__(self) -> JsonValue:
        """忽略 SIGTERM 并阻塞到自然结束。

        :returns: JSON-like 结果。
        """

        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(self.sleep_seconds)
        return {"late": True}


@dataclass(frozen=True, slots=True)
class _EnvelopeProcessTarget:
    """测试用 process-backed JSON 信封目标。"""

    envelope: JsonValue

    def __call__(self) -> JsonValue:
        """返回预置 JSON 信封。

        :returns: 预置 JSON 信封。
        """

        return self.envelope


_ProcessTargetForTest = _SleepingProcessTarget | _IgnoreTerminateProcessTarget


class _ProcessCapsuleFactory:
    """测试用 process-backed capsule factory。"""

    def __init__(self, target: _ProcessTargetForTest) -> None:
        """初始化 factory。

        :param target: 子进程目标。
        :returns: ``None``。
        """

        self._target = target

    def create_capsule(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        dispatcher: ToolDispatcher,
    ) -> ToolExecutionCapsule:
        """创建 process-backed capsule。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param dispatcher: 默认 dispatcher，本测试不使用。
        :returns: process-backed capsule。
        """

        del call, context, dispatcher
        return ProcessBackedToolExecutionCapsule(self._target)


class _RecordingProcessTargetFactory:
    """记录 process-backed target 构造输入的测试 factory。"""

    def __init__(self, envelope: JsonValue) -> None:
        """初始化测试 factory。

        :param envelope: 子进程目标返回的 JSON 信封。
        :returns: ``None``。
        """

        self._envelope = envelope
        self.calls: list[ToolCallRequest] = []
        self.contexts: list[ProcessBackedToolContext] = []

    def build_process_target(
        self,
        call: ToolCallRequest,
        context: ProcessBackedToolContext,
    ) -> _EnvelopeProcessTarget:
        """构造测试 process target 并记录投影上下文。

        :param call: 单次工具调用请求。
        :param context: process-backed 投影上下文。
        :returns: 可序列化测试目标。
        """

        self.calls.append(call)
        self.contexts.append(context)
        return _EnvelopeProcessTarget(self._envelope)


class _ObservedProcessBackedToolExecutionCapsule(ProcessBackedToolExecutionCapsule):
    """记录 interrupt 步骤的 process-backed 测试 capsule。"""

    def __init__(self, target: _ProcessTargetForTest) -> None:
        """初始化观测型 process capsule。

        :param target: 子进程目标。
        :returns: ``None``。
        """

        super().__init__(target)
        self.run_entered = asyncio.Event()
        self.terminate_result: ToolInterruptStepResult | None = None
        self.kill_result: ToolInterruptStepResult | None = None
        self.close_calls = 0

    async def run(self) -> ToolExecutionOutcome:
        """记录 run 已进入并运行真实 process-backed capsule。

        :returns: 工具执行 outcome。
        """

        self.run_entered.set()
        return await super().run()

    async def terminate(self, reason: str) -> ToolInterruptStepResult:
        """记录 terminate 结果。

        :param reason: interrupt 原因。
        :returns: terminate 结果。
        """

        result = await super().terminate(reason)
        self.terminate_result = result
        return result

    async def kill(self, reason: str) -> ToolInterruptStepResult:
        """记录 kill 结果。

        :param reason: interrupt 原因。
        :returns: kill 结果。
        """

        result = await super().kill(reason)
        self.kill_result = result
        return result

    async def close(self) -> None:
        """记录 close 调用并释放真实 process 资源。

        :returns: ``None``。
        """

        self.close_calls += 1
        await super().close()


class _ObservedProcessCapsuleFactory:
    """创建可观测 process-backed capsule 的测试 factory。"""

    def __init__(self, target: _ProcessTargetForTest) -> None:
        """初始化 factory。

        :param target: 子进程目标。
        :returns: ``None``。
        """

        self._target = target
        self._capsule: _ObservedProcessBackedToolExecutionCapsule | None = None

    def create_capsule(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        dispatcher: ToolDispatcher,
    ) -> ToolExecutionCapsule:
        """创建可观测 process-backed capsule。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param dispatcher: 默认 dispatcher，本测试不使用。
        :returns: process-backed capsule。
        """

        del call, context, dispatcher
        capsule = _ObservedProcessBackedToolExecutionCapsule(self._target)
        self._capsule = capsule
        return capsule

    def created_capsule(self) -> _ObservedProcessBackedToolExecutionCapsule:
        """返回已经创建的 capsule。

        :returns: 可观测 process-backed capsule。
        :raises AssertionError: 尚未创建 capsule 时抛出。
        """

        if self._capsule is None:
            raise AssertionError("process capsule was not created")
        return self._capsule


class _RecordingInterruptibleProcessHandle:
    """记录 close grace 参数的测试 process handle。"""

    def __init__(self) -> None:
        """初始化记录型 handle。

        :returns: ``None``。
        """

        self.close_kill_grace_seconds: float | None = None

    async def close(
        self,
        *,
        kill_grace_seconds: float = _TEST_PROCESS_CLOSE_DEFAULT_GRACE_SECONDS,
    ) -> None:
        """记录 close 使用的 kill grace。

        :param kill_grace_seconds: close best-effort kill 等待秒数。
        :returns: ``None``。
        """

        self.close_kill_grace_seconds = kill_grace_seconds


class _RaisingCapsuleFactory:
    """创建 capsule 时抛出异常的测试 factory。"""

    def __init__(self, failure: Exception) -> None:
        """初始化测试 factory。

        :param failure: create_capsule 时要抛出的异常。
        :returns: ``None``。
        """

        self._failure = failure
        self.create_calls = 0

    def create_capsule(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        dispatcher: ToolDispatcher,
    ) -> ToolExecutionCapsule:
        """抛出预置异常以模拟 capsule 构造失败。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param dispatcher: 默认 dispatcher，本测试不使用。
        :returns: 不会返回。
        :raises Exception: 始终抛出初始化传入的异常。
        """

        del call, context, dispatcher
        self.create_calls += 1
        raise self._failure


class _CloseFailingInterruptCapsule:
    """close 会失败的 interrupt 测试 capsule。"""

    def __init__(self) -> None:
        """初始化测试 capsule。

        :returns: ``None``。
        """

        self.run_entered = asyncio.Event()
        self.close_calls = 0

    @property
    def mode(self) -> ToolExecutionMode:
        """返回执行模式。

        :returns: ``async_direct``。
        """

        return ToolExecutionMode.ASYNC_DIRECT

    async def run(self) -> ToolExecutionOutcome:
        """保持运行直到外部 cancel。

        :returns: 本测试不会正常返回。
        :raises AssertionError: 若阻塞意外结束则抛出。
        """

        self.run_entered.set()
        await asyncio.Event().wait()
        raise AssertionError("close failing capsule should not complete")

    def request_interrupt(self, reason: str) -> None:
        """接收 interrupt 请求。

        :param reason: interrupt 原因。
        :returns: ``None``。
        """

        del reason

    async def terminate(self, reason: str) -> ToolInterruptStepResult:
        """返回 terminate 已完成。

        :param reason: interrupt 原因。
        :returns: terminate 结果。
        """

        del reason
        return ToolInterruptStepResult(
            supported=True,
            completed=True,
            message="test terminate completed",
        )

    async def kill(self, reason: str) -> ToolInterruptStepResult:
        """返回无需 hard kill。

        :param reason: interrupt 原因。
        :returns: kill 结果。
        """

        del reason
        return ToolInterruptStepResult(
            supported=False,
            completed=False,
            message="test kill unsupported",
        )

    async def close(self) -> None:
        """模拟 close 失败。

        :returns: 不会正常返回。
        :raises RuntimeError: 始终抛出 close 失败。
        """

        self.close_calls += 1
        raise RuntimeError("test capsule close failed")


class _CloseFailingCapsuleFactory:
    """创建 close 失败 capsule 的测试 factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self._capsule: _CloseFailingInterruptCapsule | None = None

    def create_capsule(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        dispatcher: ToolDispatcher,
    ) -> ToolExecutionCapsule:
        """创建 close 失败 capsule。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param dispatcher: 默认 dispatcher，本测试不使用。
        :returns: close 失败 capsule。
        """

        del call, context, dispatcher
        capsule = _CloseFailingInterruptCapsule()
        self._capsule = capsule
        return capsule

    def created_capsule(self) -> _CloseFailingInterruptCapsule:
        """返回已经创建的 capsule。

        :returns: close 失败 capsule。
        :raises AssertionError: 尚未创建 capsule 时抛出。
        """

        if self._capsule is None:
            raise AssertionError("close failing capsule was not created")
        return self._capsule


class _ThreadBlockingTarget:
    """测试用 thread-backed 非协作目标。"""

    def __init__(self) -> None:
        """初始化目标。

        :returns: ``None``。
        """

        self.started = False

    def __call__(self) -> ToolExecutionOutcome:
        """阻塞一段时间后返回结果。

        :returns: 工具成功 outcome。
        """

        self.started = True
        time.sleep(0.5)
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value={"thread": "late"}, meta=None)
        )


class _SequencedAcceptPort(HostToolFactAcceptPort):
    """按序返回 accept 结果的 fake accept port。"""

    def __init__(self, results: tuple[ToolFactAcceptResult, ...]) -> None:
        """初始化 fake accept port。

        :param results: 每次 accept 调用返回的结果序列。
        :returns: ``None``。
        """

        self._results = results
        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """记录 candidate 并返回脚本化结果。

        :param candidate: 工具事实候选。
        :returns: 脚本化 accept 结果。
        """

        self.candidates.append(candidate)
        index = len(self.candidates) - 1
        if index >= len(self._results):
            return _accepted_ack(candidate)
        return self._results[index]


class _RetryExhaustedAcceptPort(HostToolFactAcceptPort):
    """始终模拟 durable transaction busy retry exhausted 的 accept port。"""

    def __init__(self) -> None:
        """初始化 fake accept port。

        :returns: ``None``。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """记录 candidate 并抛出 transaction retry exhausted。

        :param candidate: 工具事实候选。
        :returns: 本实现不会正常返回。
        :raises HostTransactionRetryExhaustedError: 始终抛出以模拟 SQLite busy。
        """

        self.candidates.append(candidate)
        raise HostTransactionRetryExhaustedError(
            "busy retry exhausted in fake accept port",
            attempts=len(self.candidates),
        )


class _TimeoutAcceptPort(HostToolFactAcceptPort):
    """始终抛出同步 TimeoutError 的 accept port。"""

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """模拟同步 accept port 抛出 TimeoutError。

        :param candidate: 工具事实候选。
        :returns: 不会正常返回。
        :raises TimeoutError: 始终抛出。
        """

        del candidate
        raise TimeoutError("sync timeout should not be caught")


class _AwaitingAcceptPort(HostToolAwaitingAcceptPort):
    """记录 awaiting candidate 并返回 accepted ack 的 fake port。"""

    def __init__(self) -> None:
        """初始化 fake awaiting accept port。

        :returns: ``None``。
        """

        self.candidates: list[ToolAwaitingAcceptCandidate] = []

    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """记录 candidate 并返回 accepted ack。

        :param candidate: awaiting candidate。
        :returns: accepted ack。
        """

        self.candidates.append(candidate)
        return ToolAwaitingAcceptedAck(
            accepted_event_refs=(
                ToolAwaitingEventRef(
                    event_id=f"event-tool-awaiting-{candidate.tool_call_id}",
                    event_sequence=1,
                ),
                ToolAwaitingEventRef(
                    event_id=f"event-run-waiting-{candidate.tool_call_id}",
                    event_sequence=2,
                ),
                ToolAwaitingEventRef(
                    event_id=f"event-attempt-suspended-{candidate.tool_call_id}",
                    event_sequence=3,
                ),
            ),
            wait_id=candidate.wait_id,
            tool_awaiting_event_ref=ToolAwaitingEventRef(
                event_id=f"event-tool-awaiting-{candidate.tool_call_id}",
                event_sequence=1,
            ),
            run_waiting_event_ref=ToolAwaitingEventRef(
                event_id=f"event-run-waiting-{candidate.tool_call_id}",
                event_sequence=2,
            ),
            attempt_suspended_event_ref=ToolAwaitingEventRef(
                event_id=f"event-attempt-suspended-{candidate.tool_call_id}",
                event_sequence=3,
            ),
            result_digest=candidate.semantic_input_digest,
            idempotency_record_ref=f"awaiting:{candidate.wait_id}",
        )


class _CancellingAwaitingAcceptPort(HostToolAwaitingAcceptPort):
    """返回 accepted ack 后立即翻转取消 token 的 fake port。"""

    def __init__(self, cancellation_token: _MutableCancellationToken) -> None:
        """初始化 fake awaiting accept port。

        :param cancellation_token: accepted ack 后需要翻转的取消 token。
        :returns: ``None``。
        """

        self._cancellation_token = cancellation_token
        self.candidates: list[ToolAwaitingAcceptCandidate] = []

    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """记录 candidate、返回 accepted ack，并模拟随后发生的取消。

        :param candidate: awaiting candidate。
        :returns: accepted ack。
        """

        self.candidates.append(candidate)
        ack = _awaiting_accepted_ack(candidate.wait_id)
        self._cancellation_token.cancel("cancel-after-awaiting-accept")
        return ack


class _SequencedAwaitingAcceptPort(HostToolAwaitingAcceptPort):
    """按序返回 awaiting accept 结果的 fake port。"""

    def __init__(self, results: tuple[ToolAwaitingAcceptResult, ...]) -> None:
        """初始化 fake awaiting accept port。

        :param results: 每次 awaiting accept 调用返回的结果序列。
        :returns: ``None``。
        """

        self._results = results
        self.candidates: list[ToolAwaitingAcceptCandidate] = []

    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """记录 candidate 并返回脚本化结果。

        :param candidate: awaiting candidate。
        :returns: 脚本化 awaiting accept 结果。
        """

        self.candidates.append(candidate)
        index = len(self.candidates) - 1
        if index >= len(self._results):
            return _AwaitingAcceptPort().accept_tool_awaiting(candidate)
        return self._results[index]


class _RetryExhaustedAwaitingAcceptPort(HostToolAwaitingAcceptPort):
    """始终模拟 awaiting accept 事务重试耗尽的 fake port。"""

    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """抛出 Host 事务重试耗尽异常。

        :param candidate: awaiting candidate。
        :returns: 不会正常返回。
        :raises HostTransactionRetryExhaustedError: 始终抛出。
        """

        del candidate
        raise HostTransactionRetryExhaustedError("busy", attempts=1)


class _TimeoutAwaitingAcceptPort(HostToolAwaitingAcceptPort):
    """始终抛出同步 TimeoutError 的 awaiting accept port。"""

    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """模拟同步 awaiting accept port 抛出 TimeoutError。

        :param candidate: awaiting candidate。
        :returns: 不会正常返回。
        :raises TimeoutError: 始终抛出。
        """

        del candidate
        raise TimeoutError("sync awaiting timeout should not be caught")


class _SpyWaitActivationAdapter:
    """记录 accepted wait activation 请求的测试 adapter。"""

    def __init__(self, failure: Exception | None = None) -> None:
        """初始化 spy adapter。

        :param failure: 可选的 activation 异常。
        :returns: ``None``。
        """

        self._failure = failure
        self.requests: list[WaitActivationRequest] = []

    def activate_accepted_wait(self, request: WaitActivationRequest) -> None:
        """记录 activation 请求，并按需抛出脚本化异常。

        :param request: accepted wait activation 请求。
        :returns: ``None``。
        :raises Exception: 初始化传入 failure 时抛出该异常。
        """

        self.requests.append(request)
        if self._failure is not None:
            raise self._failure


@pytest.mark.asyncio
async def test_fake_tool_result_returns_only_after_accepted_ack() -> None:
    """fake tool 原始结果只有 accepted ack 后才返回给 Engine。"""

    callable_ = _CountingCallable({"secret": "visible-after-accept"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port)

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolCompletedOutcome)
    assert record.outcome.result.value == {"secret": "visible-after-accept"}


@pytest.mark.asyncio
async def test_declared_async_direct_default_factory_calls_tool() -> None:
    """默认 declaration-backed factory 会按 async_direct 声明调用工具。"""

    callable_ = _CountingCallable({"declared": "async-direct"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port)

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolCompletedOutcome)
    assert record.outcome.result.value == {"declared": "async-direct"}


@pytest.mark.asyncio
async def test_declared_thread_backed_default_factory_calls_tool() -> None:
    """默认 declaration-backed factory 会按 thread_backed 声明调用工具。"""

    callable_ = _CountingCallable({"declared": "thread-backed"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(
        callable_,
        accept_port,
        execution=ThreadBackedToolExecutionCapability(),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolCompletedOutcome)
    assert record.outcome.result.value == {"declared": "thread-backed"}


@pytest.mark.asyncio
async def test_capsule_build_failure_bypasses_accept_barrier() -> None:
    """capsule 构造失败应返回工具失败并跳过 accept barrier。"""

    callable_ = _CountingCallable({"secret": "must-not-run"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    capsule_factory = _RaisingCapsuleFactory(ValueError("capsule boom"))
    executor = _executor(
        callable_,
        accept_port,
        capsule_factory=capsule_factory,
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert capsule_factory.create_calls == 1
    assert callable_.call_count == 0
    assert accept_port.candidates == []
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_capsule_build_failed"
    assert "ValueError: capsule boom" in record.outcome.result.message


@pytest.mark.asyncio
async def test_oversized_tool_result_returns_completed_outcome_without_default_governance() -> None:
    """无显式截断时超大工具结果原样返回给 Engine。"""

    oversized_value = {"content": "x" * 70000}
    callable_ = _CountingCallable(oversized_value)
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(
        callable_,
        accept_port,
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(accept_port.candidates) == 1
    candidate = accept_port.candidates[0]
    assert candidate.tool_fact_kind is ToolFactKind.COMPLETED
    assert candidate.governance.policy_decision.kind is ToolPolicyDecisionKind.ALLOW
    assert _required_result(candidate).raw_tool_outcome == {
        "kind": "completed",
        "result": {
            "ok": True,
            "value": oversized_value,
            "meta": None,
        },
    }
    assert isinstance(record.outcome, ToolCompletedOutcome)
    assert record.outcome.result.value == oversized_value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repair_hint", "expected_truncated"),
    (
        (None, False),
        ("r" * 512, False),
        ("r" * 513, True),
    ),
)
async def test_tool_runtime_produces_tool_failed_failure_metadata(
    repair_hint: str | None, expected_truncated: bool
) -> None:
    """failed outcome 生产 tool_failed failure_metadata 且 repair_hint 有界。"""

    outcome = ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error="lookup_failed",
            message="tool failed body must not become analyzer fact",
            hint=repair_hint,
            meta=None,
        )
    )
    callable_ = _OutcomeCallable(outcome)
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port)

    result = await executor.execute(_request(_call("tool-call-1")))

    assert result.records[0].outcome == outcome
    metadata = _required_failure_metadata(accept_port.candidates[0])
    assert metadata["failure_kind"] == "tool_failed"
    assert metadata["error_code"] == "lookup_failed"
    assert "message" not in metadata
    _assert_bounded_text(metadata, "repair_hint", repair_hint, expected_truncated)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cancel_message", "cancel_hint", "message_truncated", "hint_truncated"),
    (
        ("m" * 512, None, False, False),
        ("m" * 513, "h" * 512, True, False),
        ("short message", "h" * 513, False, True),
    ),
)
async def test_tool_runtime_produces_tool_cancelled_failure_metadata(
    cancel_message: str,
    cancel_hint: str | None,
    message_truncated: bool,
    hint_truncated: bool,
) -> None:
    """cancelled outcome 生产 tool_cancelled，且不会混入 tool_failed。"""

    outcome = ToolCancelledOutcome(
        reason="host_cancelled",
        message=cancel_message,
        hint=cancel_hint,
        meta=None,
    )
    callable_ = _OutcomeCallable(outcome)
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port)

    result = await executor.execute(_request(_call("tool-call-1")))

    assert result.records[0].outcome == outcome
    metadata = _required_failure_metadata(accept_port.candidates[0])
    assert metadata["failure_kind"] == "tool_cancelled"
    assert metadata["failure_kind"] != "tool_failed"
    assert metadata["cancel_reason"] == "host_cancelled"
    _assert_bounded_text(
        metadata, "cancel_message", cancel_message, message_truncated
    )
    _assert_bounded_text(metadata, "cancel_hint", cancel_hint, hint_truncated)


@pytest.mark.asyncio
async def test_tool_runtime_produces_policy_blocked_failure_metadata() -> None:
    """治理拒绝生产 policy_blocked，原因只来自 reason_code。"""

    callable_ = _CountingCallable({"secret": "side-effect"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    policy_view = ToolRuntimePolicyView(
        rules_by_tool_name={
            "fake_tool": ToolRuntimeToolPolicy(
                side_effect_kind=ToolSideEffectKind.SIDE_EFFECT,
                idempotency_key_argument_name="tool_idempotency_key",
            )
        }
    )
    executor = _executor(callable_, accept_port, policy_view=policy_view)

    await executor.execute(_request(_call("tool-call-1")))

    metadata = _required_failure_metadata(accept_port.candidates[0])
    assert metadata == {
        "schema_version": 1,
        "signal_source": "TOOL_RESULT_ACCEPTED",
        "failure_kind": "policy_blocked",
        "policy_decision_kind": "governed_error",
        "policy_block_reason": "tool_idempotency_key_required",
        "diagnostic_refs": [],
    }


def test_fetch_more_returns_oversized_continuation_without_default_inline_limit() -> None:
    """fetch_more 不再复用 durable payload inline 阈值拒绝 continuation。"""

    spec = ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": 1},
        target_field=None,
        field_path=None,
        ttl_seconds=None,
    )
    manager = TruncationManager(
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        attempt_id=_ATTEMPT_ID,
        truncate_specs_by_name={"fake_tool": spec},
    )
    applied = manager.apply_truncation(
        "fake_tool",
        "tool-call-1",
        ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value="x" * _OVERSIZED_INLINE_TEXT_LENGTH,
                meta=None,
            )
        ),
        spec,
    )
    assert applied.cursor_hint is not None
    assert isinstance(applied.outcome, ToolCompletedOutcome)
    truncated_value = applied.outcome.result.value
    assert isinstance(truncated_value, dict)
    fetch_more = truncated_value["fetch_more"]
    assert isinstance(fetch_more, dict)
    scope_token = fetch_more["scope_token"]
    assert isinstance(scope_token, str)

    fetched = manager.fetch_more(
        FetchMoreRequest(
            cursor=applied.cursor_hint,
            scope_token=scope_token,
            limit=None,
        ),
        _request(_call("tool-call-1")).context,
    )

    assert isinstance(fetched, ToolCompletedOutcome)
    assert fetched.result.value == "x" * (_OVERSIZED_INLINE_TEXT_LENGTH - 1)


def test_truncation_keeps_cursor_when_visible_result_is_large_by_explicit_spec() -> None:
    """显式截断 spec 的大可见结果不再被默认 inline 阈值二次拒绝。"""

    spec = ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": _OVERSIZED_TRUNCATED_TEXT_LIMIT},
        target_field=None,
        field_path=None,
        ttl_seconds=None,
    )
    manager = TruncationManager(
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        attempt_id=_ATTEMPT_ID,
        truncate_specs_by_name={"fake_tool": spec},
    )

    applied = manager.apply_truncation(
        "fake_tool",
        "tool-call-1",
        ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value="x" * _OVERSIZED_INLINE_TEXT_LENGTH,
                meta=None,
            )
        ),
        spec,
    )

    assert isinstance(applied.outcome, ToolCompletedOutcome)
    assert applied.cursor_hint is not None
    assert applied.cursor_hint in manager._cursors


@pytest.mark.asyncio
async def test_accept_rejected_does_not_expose_raw_fake_result() -> None:
    """accepted ack 被拒绝时不向 Engine 暴露原始 fake result。"""

    callable_ = _CountingCallable({"secret": "must-not-leak"})
    accept_port = _SequencedAcceptPort(
        (
            ToolFactRejectedAck(
                reason_code=ToolAcceptRejectReason.IDEMPOTENCY_CONFLICT,
                message="reject fake result",
                diagnostic_refs=(),
                retryable=False,
            ),
        )
    )
    executor = _executor(callable_, accept_port)

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_accept_rejected"
    assert "must-not-leak" not in record.outcome.result.message


@pytest.mark.asyncio
async def test_accept_timeout_bounded_retry_returns_governed_error() -> None:
    """accept timeout 只有限重试，耗尽后返回 governed error。"""

    callable_ = _CountingCallable({"secret": "timeout-raw"})
    accept_port = _SequencedAcceptPort(
        (
            ToolFactAcceptTimedOut(
                attempt_count=1,
                last_error_code="ack_lost",
                diagnostic_refs=(),
            ),
            ToolFactAcceptTimedOut(
                attempt_count=2,
                last_error_code="ack_lost",
                diagnostic_refs=(),
            ),
        )
    )
    executor = _executor(
        callable_,
        accept_port,
        retry_policy=ToolAcceptRetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(accept_port.candidates) == 2
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_accept_timeout"
    assert "timeout-raw" not in record.outcome.result.message


@pytest.mark.asyncio
async def test_accept_retry_exhausted_returns_governed_timeout() -> None:
    """durable transaction retry exhausted 被治理成 accept timeout。"""

    callable_ = _CountingCallable({"secret": "retry-exhausted-raw"})
    accept_port = _RetryExhaustedAcceptPort()
    executor = _executor(
        callable_,
        accept_port,
        retry_policy=ToolAcceptRetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(accept_port.candidates) == 2
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_accept_timeout"
    assert "retry-exhausted-raw" not in record.outcome.result.message


@pytest.mark.asyncio
async def test_sync_timeout_error_from_accept_port_is_not_caught() -> None:
    """同步 accept port 的 TimeoutError 不应被误分类为 retry timeout。"""

    callable_ = _CountingCallable({"secret": "timeout-error"})
    executor = _executor(callable_, _TimeoutAcceptPort())

    with pytest.raises(TimeoutError, match="sync timeout"):
        await executor.execute(_request(_call("tool-call-1")))


@pytest.mark.asyncio
async def test_duplicate_cleanup_failure_does_not_replace_tool_timeout_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """duplicate cleanup 失败不覆盖工具 timeout 返回结果。"""

    async def _raise_cleanup_failure(
        self: InMemoryAttemptDuplicateGovernance,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """模拟 duplicate cleanup 失败。

        :param self: duplicate governance 实例。
        :param request: cleanup 请求。
        :param reason: durable missing 原因。
        :returns: ``None``。
        :raises RuntimeError: 始终抛出 cleanup 失败。
        """

        del self, request, reason
        raise RuntimeError("duplicate cleanup failed")

    monkeypatch.setattr(
        InMemoryAttemptDuplicateGovernance,
        "record_durable_missing",
        _raise_cleanup_failure,
    )
    callable_ = _BlockingCallable()
    diagnostics = InMemoryToolTraceDiagnosticEmitter()
    executor = _executor(
        callable_,
        _SequencedAcceptPort(()),
        diagnostic_emitter=diagnostics,
    )

    outcome = await executor.execute(
        _request(_call("tool-call-1"), timeout_seconds=_FAST_TOOL_TIMEOUT_SECONDS)
    )

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_call_governed"
    assert record.outcome.result.hint == "tool_runtime_timeout"
    assert diagnostics.records[-1].reason_code == "duplicate_cleanup_failed"


@pytest.mark.asyncio
async def test_duplicate_cleanup_failure_does_not_replace_original_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """duplicate cleanup 失败不覆盖 try 块原始异常。"""

    async def _raise_cleanup_failure(
        self: InMemoryAttemptDuplicateGovernance,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """模拟 duplicate cleanup 失败。

        :param self: duplicate governance 实例。
        :param request: cleanup 请求。
        :param reason: durable missing 原因。
        :returns: ``None``。
        :raises RuntimeError: 始终抛出 cleanup 失败。
        """

        del self, request, reason
        raise RuntimeError("duplicate cleanup failed")

    monkeypatch.setattr(
        InMemoryAttemptDuplicateGovernance,
        "record_durable_missing",
        _raise_cleanup_failure,
    )
    callable_ = _CountingCallable({"secret": "timeout-error"})
    executor = _executor(callable_, _TimeoutAcceptPort())

    with pytest.raises(TimeoutError, match="sync timeout"):
        await executor.execute(_request(_call("tool-call-1")))


@pytest.mark.asyncio
async def test_side_effect_tool_missing_idempotency_key_never_calls_callable() -> None:
    """side-effect 工具缺少必需幂等 key 时不得调用 callable。"""

    callable_ = _CountingCallable({"secret": "side-effect"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    policy_view = ToolRuntimePolicyView(
        rules_by_tool_name={
            "fake_tool": ToolRuntimeToolPolicy(
                side_effect_kind=ToolSideEffectKind.SIDE_EFFECT,
                idempotency_key_argument_name="tool_idempotency_key",
            )
        }
    )
    executor = _executor(callable_, accept_port, policy_view=policy_view)

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert accept_port.candidates[0].tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_idempotency_key_required"
    )
    assert isinstance(record.outcome, ToolFailedOutcome)


@pytest.mark.asyncio
async def test_tool_runtime_timeout_returns_governed_failure() -> None:
    """业务工具超过批级 timeout 时返回受治理失败且取消底层 task。"""

    callable_ = _BlockingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port)

    outcome = await executor.execute(
        _request(_call("tool-call-1"), timeout_seconds=_FAST_TOOL_TIMEOUT_SECONDS)
    )

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert callable_.cancelled
    assert len(accept_port.candidates) == 1
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_runtime_timeout"
    )
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_call_governed"
    assert record.outcome.result.hint == "tool_runtime_timeout"


@pytest.mark.asyncio
async def test_tool_runtime_process_backed_cancel_does_not_wait_for_natural_completion() -> None:
    """process-backed 非协作工具取消后不等待自然 sleep 结束。"""

    callable_ = _CountingCallable({"secret": "unused"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    token = _MutableCancellationToken()
    executor = _executor(
        callable_,
        accept_port,
        capsule_factory=_ProcessCapsuleFactory(
            _SleepingProcessTarget(sleep_seconds=5.0)
        ),
    )

    started_at = time.monotonic()
    task = asyncio.create_task(
        executor.execute(_request(_call("tool-call-1"), cancellation_token=token))
    )
    await asyncio.sleep(0.3)
    token.cancel("test_process_cancel")
    outcome = await asyncio.wait_for(task, timeout=2.0)
    elapsed = time.monotonic() - started_at

    record = outcome.records[0]
    assert elapsed < 2.0
    assert callable_.call_count == 0
    assert len(accept_port.candidates) == 1
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_runtime_cancelled"
    )
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "tool_runtime_cancelled"


@pytest.mark.asyncio
async def test_tool_runtime_default_factory_uses_declared_process_backed_execution() -> None:
    """生产默认 factory 会按 ToolDefinition.execution 选择 process-backed。"""

    callable_ = _CountingCallable({"secret": "must-not-run"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    target_factory = _RecordingProcessTargetFactory(
        process_tool_completed_envelope({"from_process": True})
    )
    executor = _executor(
        callable_,
        accept_port,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=target_factory
        ),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert len(target_factory.calls) == 1
    assert target_factory.calls[0].tool_call_id == "tool-call-1"
    assert target_factory.contexts == [
        ProcessBackedToolContext(
            run_id=_RUN_ID,
            session_id=_SESSION_ID,
            iteration_id=_ITERATION_ID,
            timeout_seconds=_DEFAULT_TOOL_TIMEOUT_SECONDS,
            correlation_id="correlation-toolruntime",
        )
    ]
    assert len(accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolCompletedOutcome)
    assert record.outcome.result.value == {"from_process": True}


@pytest.mark.asyncio
async def test_tool_runtime_default_factory_wires_process_capsule_interrupt_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认 factory 必须把 HostToolingOptions 的 process policy 传到 capsule。"""

    _RECORDED_PROCESS_HANDLE_CLOSE_KILL_GRACES.clear()
    monkeypatch.setattr(
        InterruptibleProcessHandle,
        "close",
        _recording_interruptible_process_handle_close,
    )
    callable_ = _CountingCallable({"secret": "must-not-run"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    target_factory = _RecordingProcessTargetFactory(
        process_tool_completed_envelope({"from_process": True})
    )
    policy = ProcessCapsuleInterruptPolicy(
        kill_grace_seconds=_CUSTOM_PROCESS_CLOSE_GRACE_SECONDS
    )
    definition = _definition(
        "fake_tool",
        callable_,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=target_factory
        ),
    )
    handle = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(definitions=(definition,)),
                source_refs=(_source_ref(),),
                framework_tool_policy=default_framework_tool_policy_view(),
                policy_snapshot_digest=_POLICY_DIGEST,
            ),
            execution_scope=ToolRuntimeExecutionScope(
                session_id=_SESSION_ID,
                run_id=_RUN_ID,
                attempt_id=_ATTEMPT_ID,
                execution_id=_EXECUTION_ID,
                allow_tool_calls=True,
            ),
            accept_port=accept_port,
            retry_policy=ToolAcceptRetryPolicy(
                max_attempts=1,
                backoff_seconds=0.0,
            ),
            process_capsule_interrupt_policy=policy,
        )
    )

    outcome = await handle.tool_executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert len(target_factory.calls) == 1
    assert len(accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolCompletedOutcome)
    assert record.outcome.result.value == {"from_process": True}
    assert _RECORDED_PROCESS_HANDLE_CLOSE_KILL_GRACES == [
        _CUSTOM_PROCESS_CLOSE_GRACE_SECONDS
    ]


@pytest.mark.asyncio
async def test_tool_runtime_process_backed_failed_envelope_returns_tool_failure() -> None:
    """process-backed failed 信封缺省 hint 时映射为工具失败 outcome。"""

    callable_ = _CountingCallable({"secret": "must-not-run"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    target_factory = _RecordingProcessTargetFactory(
        {
            "status": "failed",
            "error_type": "business_failed",
            "message": "business failure",
        }
    )
    executor = _executor(
        callable_,
        accept_port,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=target_factory
        ),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert len(accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "business_failed"
    assert record.outcome.result.message == "business failure"
    assert record.outcome.result.hint is None


@pytest.mark.asyncio
async def test_tool_runtime_process_backed_failed_envelope_maps_hint() -> None:
    """process-backed failed 信封的结构化 hint 必须映射为工具失败 hint。"""

    callable_ = _CountingCallable({"secret": "must-not-run"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    target_factory = _RecordingProcessTargetFactory(
        process_tool_failed_envelope(
            error_type="business_failed",
            message="business failure",
            hint="retry with a narrower filing range",
        )
    )
    executor = _executor(
        callable_,
        accept_port,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=target_factory
        ),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert len(accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "business_failed"
    assert record.outcome.result.message == "business failure"
    assert record.outcome.result.hint == "retry with a narrower filing range"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("envelope", "expected_error"),
    (
        ({"value": {"missing": "status"}}, "process_backed_tool_malformed_envelope"),
        ({"status": "awaiting"}, "process_backed_tool_unsupported_envelope"),
        ({"status": "cancelled"}, "process_backed_tool_unsupported_envelope"),
        ({"status": "timeout"}, "process_backed_tool_unsupported_envelope"),
        ({"status": "host_cancelled"}, "process_backed_tool_unsupported_envelope"),
        ({"status": "unknown"}, "process_backed_tool_unsupported_envelope"),
        (
            {"status": "failed", "error_type": "", "message": "missing"},
            "process_backed_tool_malformed_envelope",
        ),
        (
            {
                "status": "failed",
                "error_type": "err",
                "message": "msg",
                "hint": 123,
            },
            "process_backed_tool_malformed_envelope",
        ),
    ),
)
async def test_process_backed_capsule_fail_closes_unsupported_envelopes(
    envelope: JsonValue,
    expected_error: str,
) -> None:
    """process-backed capsule 对非法或 Host-governed 信封 fail closed。"""

    capsule = ProcessBackedToolExecutionCapsule(_EnvelopeProcessTarget(envelope))

    outcome = await capsule.run()
    await capsule.close()

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == expected_error


@pytest.mark.asyncio
async def test_process_backed_capsule_close_uses_interrupt_policy_kill_grace() -> None:
    """process-backed capsule close 必须使用 Host policy 中的 kill grace。"""

    capsule = ProcessBackedToolExecutionCapsule(
        _EnvelopeProcessTarget(process_tool_completed_envelope({"ok": True})),
        interrupt_policy=ProcessCapsuleInterruptPolicy(
            kill_grace_seconds=_CUSTOM_PROCESS_CLOSE_GRACE_SECONDS,
        ),
    )
    handle = _RecordingInterruptibleProcessHandle()
    capsule._handle = cast(InterruptibleProcessHandle, handle)

    await capsule.close()

    assert handle.close_kill_grace_seconds == _CUSTOM_PROCESS_CLOSE_GRACE_SECONDS


def test_engine_facing_tool_schema_projection_excludes_execution_capability() -> None:
    """Engine-facing ToolSchema 投影不携带 execution capability。"""

    callable_ = _CountingCallable({"unused": True})
    target_factory = _RecordingProcessTargetFactory(
        {"status": "completed", "value": {"unused": True}}
    )
    definition = _definition(
        "fake_tool",
        callable_,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=target_factory
        ),
    )
    handle = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(definitions=(definition,)),
                source_refs=(_source_ref(),),
                framework_tool_policy=default_framework_tool_policy_view(),
                policy_snapshot_digest=_POLICY_DIGEST,
            ),
        )
    )

    schema = handle.tool_schemas[0]
    schema_json: JsonValue = {
        "type": schema.type,
        "function": {
            "name": schema.function.name,
            "description": schema.function.description,
            "parameters": {
                "type": schema.function.parameters.type,
                "properties": schema.function.parameters.properties,
                "required": list(schema.function.parameters.required),
                "additionalProperties": (
                    schema.function.parameters.additional_properties
                ),
            },
        },
    }
    assert definition.execution == ProcessBackedToolExecutionCapability(
        target_factory=target_factory
    )
    assert isinstance(schema_json, dict)
    assert "execution" not in schema_json
    function_json = schema_json["function"]
    assert isinstance(function_json, dict)
    assert "execution" not in function_json


def test_active_toolruntime_path_has_no_process_capsule_grace_constants() -> None:
    """active ToolRuntime 路径不得保留旧 process capsule grace 常量。"""

    source = (
        Path(__file__).resolve().parents[2] / "dayu" / "host" / "tool_runtime.py"
    ).read_text(encoding="utf-8")

    assert "_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS" not in source
    assert "_PROCESS_CAPSULE_KILL_GRACE_SECONDS" not in source


@pytest.mark.asyncio
async def test_tool_runtime_outer_task_cancel_closes_process_capsule() -> None:
    """外层 execute task 被取消时会 interrupt 并 close process capsule。"""

    callable_ = _CountingCallable({"secret": "unused"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    factory = _ObservedProcessCapsuleFactory(
        _IgnoreTerminateProcessTarget(sleep_seconds=5.0)
    )
    executor = _executor(
        callable_,
        accept_port,
        capsule_factory=factory,
    )

    task = asyncio.create_task(executor.execute(_request(_call("tool-call-1"))))
    await asyncio.sleep(0)
    capsule = factory.created_capsule()
    await asyncio.wait_for(capsule.run_entered.wait(), timeout=1.0)
    await asyncio.sleep(0.8)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2.0)

    assert callable_.call_count == 0
    assert capsule.close_calls == 1
    assert capsule.terminate_result is not None
    assert capsule.terminate_result.supported
    assert not capsule.terminate_result.completed
    assert capsule.kill_result is not None
    assert capsule.kill_result.supported
    assert capsule.kill_result.completed


@pytest.mark.asyncio
async def test_tool_runtime_process_backed_cancel_kills_when_terminate_is_ignored() -> None:
    """executor 层 process-backed cancel 会从 terminate 升级到 kill。"""

    callable_ = _CountingCallable({"secret": "unused"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    token = _MutableCancellationToken()
    factory = _ObservedProcessCapsuleFactory(
        _IgnoreTerminateProcessTarget(sleep_seconds=5.0)
    )
    executor = _executor(
        callable_,
        accept_port,
        capsule_factory=factory,
    )

    task = asyncio.create_task(
        executor.execute(_request(_call("tool-call-1"), cancellation_token=token))
    )
    await asyncio.sleep(0)
    capsule = factory.created_capsule()
    await asyncio.wait_for(capsule.run_entered.wait(), timeout=1.0)
    await asyncio.sleep(0.8)
    token.cancel("test_process_cancel_ignored_terminate")
    outcome = await asyncio.wait_for(task, timeout=2.0)

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert capsule.close_calls == 1
    assert capsule.terminate_result is not None
    assert capsule.terminate_result.supported
    assert not capsule.terminate_result.completed
    assert capsule.kill_result is not None
    assert capsule.kill_result.supported
    assert capsule.kill_result.completed
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "tool_runtime_cancelled"


@pytest.mark.asyncio
async def test_tool_runtime_interrupt_close_failure_keeps_governed_cancel_outcome(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """interrupt cleanup 的 close 失败不会遮蔽 governed cancel outcome。"""

    callable_ = _CountingCallable({"secret": "unused"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    token = _MutableCancellationToken()
    factory = _CloseFailingCapsuleFactory()
    executor = _executor(
        callable_,
        accept_port,
        capsule_factory=factory,
    )

    task = asyncio.create_task(
        executor.execute(_request(_call("tool-call-1"), cancellation_token=token))
    )
    await asyncio.sleep(0)
    capsule = factory.created_capsule()
    await asyncio.wait_for(capsule.run_entered.wait(), timeout=1.0)
    with caplog.at_level(logging.WARNING, logger="dayu.host.tool_runtime"):
        token.cancel("test_close_failure")
        outcome = await asyncio.wait_for(task, timeout=1.0)

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert capsule.close_calls == 1
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "tool_runtime_cancelled"
    assert "host.tool_runtime.capsule_close_failed" in caplog.text
    assert "error_type=RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_thread_backed_capsule_does_not_claim_thread_termination() -> None:
    """thread-backed capsule 的 terminate / kill 明确不支持 OS thread 中止。"""

    capability = ThreadBackedToolExecutionCapability()
    target = _ThreadBlockingTarget()
    capsule = ThreadBackedToolExecutionCapsule(target)
    task = asyncio.create_task(capsule.run())
    await asyncio.sleep(0.05)

    assert capability.production_safe_non_cooperative_cancel is False
    assert capsule.mode is ToolExecutionMode.THREAD_BACKED
    terminate = await capsule.terminate("test")
    kill = await capsule.kill("test")
    await capsule.close()

    assert target.started
    assert isinstance(terminate, ToolInterruptStepResult)
    assert not terminate.supported
    assert not terminate.completed
    assert isinstance(kill, ToolInterruptStepResult)
    assert not kill.supported
    assert not kill.completed
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_tool_runtime_pre_cancelled_context_returns_governed_failure() -> None:
    """context token 已取消时不得调用业务工具，并返回受治理失败。"""

    callable_ = _CountingCallable({"secret": "must-not-run"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    activation_adapter = _SpyWaitActivationAdapter()
    executor = _executor(
        callable_,
        accept_port,
        wait_activation_registry=_wait_activation_registry(activation_adapter),
    )

    outcome = await executor.execute(
        _request(_call("tool-call-1"), cancellation_token=_AlreadyCancelledToken())
    )

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert len(accept_port.candidates) == 1
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_runtime_cancelled"
    )
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_call_governed"
    assert record.outcome.result.hint == "tool_runtime_cancelled"
    assert "must-not-run" not in record.outcome.result.message
    assert activation_adapter.requests == []


@pytest.mark.asyncio
async def test_awaiting_outcome_returns_only_after_awaiting_accepted_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """awaiting outcome accepted 后不执行 durable-missing cleanup。"""

    recorded_reasons: list[DuplicateDurableMissingReason] = []

    async def _record_durable_missing(
        self: InMemoryAttemptDuplicateGovernance,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """记录测试观察到的 durable-missing cleanup。

        :param self: duplicate governance 实例。
        :param request: duplicate governance 查询。
        :param reason: durable missing 原因。
        :returns: ``None``。
        """

        del self, request
        recorded_reasons.append(reason)

    monkeypatch.setattr(
        InMemoryAttemptDuplicateGovernance,
        "record_durable_missing",
        _record_durable_missing,
    )

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _AwaitingAcceptPort()
    activation_adapter = _SpyWaitActivationAdapter()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert accept_port.candidates == []
    assert len(awaiting_accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolAwaitingOutcome)
    assert awaiting_accept_port.candidates[0].external_job_ref is not None
    assert awaiting_accept_port.candidates[0].external_job_ref.external_job_id == (
        "resume-token"
    )
    assert len(activation_adapter.requests) == 1
    assert activation_adapter.requests[0].tool_name == "fake_tool"
    assert activation_adapter.requests[0].await_spec.resume_token == "resume-token"
    assert activation_adapter.requests[0].accepted_ack.wait_id == (
        awaiting_accept_port.candidates[0].wait_id
    )
    assert recorded_reasons == []


@pytest.mark.asyncio
async def test_awaiting_outcome_with_snapshot_builds_complete_wait_snapshot_ref() -> None:
    """awaiting outcome 携带 snapshot 时生成可落库的完整 wait snapshot ref。

    :returns: ``None``。
    """

    snapshot = ToolAwaitSnapshot(
        snapshot_id="fins-observation-start-test",
        captured_at=datetime(2026, 5, 16, 1, 2, 3, 456789, tzinfo=UTC),
    )
    callable_ = _AwaitingCallable(snapshot=snapshot)
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _AwaitingAcceptPort()
    activation_adapter = _SpyWaitActivationAdapter()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolAwaitingOutcome)
    assert len(awaiting_accept_port.candidates) == 1
    snapshot_ref = awaiting_accept_port.candidates[0].snapshot_ref
    assert snapshot_ref is not None
    assert snapshot_ref.snapshot_id == snapshot.snapshot_id
    assert snapshot_ref.captured_at == snapshot.captured_at
    assert snapshot_ref.snapshot_digest == sha256_digest_json(
        {
            "captured_at": "2026-05-16T01:02:03.456789Z",
            "snapshot_id": "fins-observation-start-test",
        }
    )


@pytest.mark.asyncio
async def test_cancel_after_awaiting_accept_skips_activation() -> None:
    """awaiting accept 返回 accepted 后若取消，不能再触发 activation。"""

    cancellation_token = _MutableCancellationToken()
    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _CancellingAwaitingAcceptPort(cancellation_token)
    activation_adapter = _SpyWaitActivationAdapter()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
    )

    outcome = await executor.execute(
        _request(_call("tool-call-1"), cancellation_token=cancellation_token)
    )

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(awaiting_accept_port.candidates) == 1
    assert cancellation_token.is_cancelled()
    assert isinstance(record.outcome, ToolAwaitingOutcome)
    assert activation_adapter.requests == []


@pytest.mark.asyncio
async def test_awaiting_activation_failure_keeps_accepted_awaiting_outcome(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """activation adapter 异常只产生有界诊断，不覆盖 accepted awaiting。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _AwaitingAcceptPort()
    diagnostics = InMemoryToolTraceDiagnosticEmitter()
    activation_adapter = _SpyWaitActivationAdapter(
        RuntimeError("raw-provider-job-secret")
    )
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
        diagnostic_emitter=diagnostics,
    )

    with caplog.at_level(logging.WARNING, logger="dayu.host.tool_runtime"):
        outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolAwaitingOutcome)
    assert len(activation_adapter.requests) == 1
    assert len(diagnostics.records) == 1
    assert diagnostics.records[0].reason_code == "wait_activation_failed"
    assert "RuntimeError" in diagnostics.records[0].message
    assert "raw-provider-job-secret" not in diagnostics.records[0].message
    assert "RuntimeError" in caplog.text
    assert _SESSION_ID in caplog.text
    assert _RUN_ID in caplog.text
    assert _ATTEMPT_ID in caplog.text
    assert "fake_tool" in caplog.text
    assert "poll:fake-tool" in caplog.text
    assert "raw-provider-job-secret" not in caplog.text


def test_wait_activation_request_rejects_empty_tool_name() -> None:
    """WaitActivationRequest 拒绝空工具名。"""

    with pytest.raises(ValueError, match="tool_name"):
        WaitActivationRequest(
            tool_name=" ",
            await_spec=_external_job_await_spec(),
            accepted_ack=_awaiting_accepted_ack("wait-validation"),
        )


def test_wait_activation_request_rejects_invalid_await_spec() -> None:
    """WaitActivationRequest 拒绝非法等待规约对象。"""

    with pytest.raises(ValueError, match="await_spec"):
        WaitActivationRequest(
            tool_name="fake_tool",
            await_spec=cast(ToolAwaitSpec, "invalid-await-spec"),
            accepted_ack=_awaiting_accepted_ack("wait-validation"),
        )


@pytest.mark.asyncio
async def test_awaiting_marker_failure_keeps_owner_outcome_and_suppresses_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """awaiting marker 写入失败不得覆盖 owner awaiting 返回或误记 cleanup。"""

    marker_wait_ids: list[str] = []
    recorded_reasons: list[DuplicateDurableMissingReason] = []

    async def _record_awaiting_accepted(
        self: InMemoryAttemptDuplicateGovernance,
        request: DuplicateGovernanceRequest,
        awaiting_entry: DuplicateAwaitingAcceptedEntry,
    ) -> None:
        """模拟 accepted awaiting marker 写入失败。

        :param self: duplicate governance 实例。
        :param request: duplicate governance 查询。
        :param awaiting_entry: awaiting accepted marker 条目。
        :returns: 不会正常返回。
        :raises RuntimeError: 始终模拟 marker 写入失败。
        """

        del self, request
        marker_wait_ids.append(awaiting_entry.wait_id)
        raise RuntimeError("marker write failed")

    async def _record_durable_missing(
        self: InMemoryAttemptDuplicateGovernance,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """记录测试观察到的 durable-missing cleanup。

        :param self: duplicate governance 实例。
        :param request: duplicate governance 查询。
        :param reason: durable missing 原因。
        :returns: ``None``。
        """

        del self, request
        recorded_reasons.append(reason)

    monkeypatch.setattr(
        InMemoryAttemptDuplicateGovernance,
        "record_awaiting_accepted",
        _record_awaiting_accepted,
    )
    monkeypatch.setattr(
        InMemoryAttemptDuplicateGovernance,
        "record_durable_missing",
        _record_durable_missing,
    )
    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _AwaitingAcceptPort()
    diagnostics = InMemoryToolTraceDiagnosticEmitter()
    activation_adapter = _SpyWaitActivationAdapter()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
        diagnostic_emitter=diagnostics,
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert accept_port.candidates == []
    assert len(awaiting_accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolAwaitingOutcome)
    assert marker_wait_ids == [awaiting_accept_port.candidates[0].wait_id]
    assert recorded_reasons == []
    assert len(diagnostics.records) == 1
    assert diagnostics.records[0].reason_code == "duplicate_awaiting_marker_failed"
    assert "marker write failed" not in diagnostics.records[0].message
    assert awaiting_accept_port.candidates[0].wait_id not in diagnostics.records[0].message
    assert len(activation_adapter.requests) == 1


@pytest.mark.asyncio
async def test_awaiting_outcome_without_adapter_binding_is_governed_error() -> None:
    """缺少 Host adapter binding 时 awaiting outcome 不进入普通 accept。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    activation_adapter = _SpyWaitActivationAdapter()
    executor = _executor(
        callable_,
        accept_port,
        wait_activation_registry=_wait_activation_registry(activation_adapter),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert accept_port.candidates == []
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "awaiting_adapter_not_configured"
    assert activation_adapter.requests == []


@pytest.mark.asyncio
async def test_awaiting_accept_rejected_returns_governed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """awaiting accept rejected ack 不向 Engine 暴露 awaiting outcome。"""

    recorded_reasons: list[DuplicateDurableMissingReason] = []

    async def _record_durable_missing(
        self: InMemoryAttemptDuplicateGovernance,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """记录测试观察到的 durable-missing cleanup。

        :param self: duplicate governance 实例。
        :param request: duplicate governance 查询。
        :param reason: durable missing 原因。
        :returns: ``None``。
        """

        del self, request
        recorded_reasons.append(reason)

    monkeypatch.setattr(
        InMemoryAttemptDuplicateGovernance,
        "record_durable_missing",
        _record_durable_missing,
    )
    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    activation_adapter = _SpyWaitActivationAdapter()
    awaiting_accept_port = _SequencedAwaitingAcceptPort(
        (
            ToolAwaitingRejectedAck(
                reason_code=ToolAwaitingAcceptRejectReason.IDEMPOTENCY_CONFLICT,
                message="awaiting conflict",
                retryable=False,
            ),
        )
    )
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_awaiting_accept_rejected"
    assert record.outcome.result.hint == "accept_rejected:idempotency_conflict"
    assert recorded_reasons == [DuplicateDurableMissingReason.HOST_ACCEPT_REJECTED]
    assert activation_adapter.requests == []


@pytest.mark.asyncio
async def test_stale_execution_awaiting_rejection_does_not_activate_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host stale execution 拒绝 awaiting accept 时不得执行 activation。"""

    recorded_reasons: list[DuplicateDurableMissingReason] = []

    async def _record_durable_missing(
        self: InMemoryAttemptDuplicateGovernance,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """记录测试观察到的 durable-missing cleanup。

        :param self: duplicate governance 实例。
        :param request: duplicate governance 查询。
        :param reason: durable missing 原因。
        :returns: ``None``。
        """

        del self, request
        recorded_reasons.append(reason)

    monkeypatch.setattr(
        InMemoryAttemptDuplicateGovernance,
        "record_durable_missing",
        _record_durable_missing,
    )
    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    activation_adapter = _SpyWaitActivationAdapter()
    awaiting_accept_port = _SequencedAwaitingAcceptPort(
        (
            ToolAwaitingRejectedAck(
                reason_code=ToolAwaitingAcceptRejectReason.STALE_EXECUTION,
                message="stale execution",
                retryable=False,
            ),
        )
    )
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_awaiting_accept_rejected"
    assert record.outcome.result.hint == "accept_rejected:stale_execution"
    assert recorded_reasons == [DuplicateDurableMissingReason.HOST_ACCEPT_REJECTED]
    assert activation_adapter.requests == []


@pytest.mark.asyncio
async def test_awaiting_accept_timeout_returns_governed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """awaiting accept timeout 不向 Engine 暴露 awaiting outcome。"""

    recorded_reasons: list[DuplicateDurableMissingReason] = []

    async def _record_durable_missing(
        self: InMemoryAttemptDuplicateGovernance,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """记录测试观察到的 durable-missing cleanup。

        :param self: duplicate governance 实例。
        :param request: duplicate governance 查询。
        :param reason: durable missing 原因。
        :returns: ``None``。
        """

        del self, request
        recorded_reasons.append(reason)

    monkeypatch.setattr(
        InMemoryAttemptDuplicateGovernance,
        "record_durable_missing",
        _record_durable_missing,
    )
    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    activation_adapter = _SpyWaitActivationAdapter()
    awaiting_accept_port = _SequencedAwaitingAcceptPort(
        (
            ToolAwaitingAcceptTimedOut(
                attempt_count=1,
                last_error_code="accept_ack_lost",
            ),
        )
    )
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_awaiting_accept_timeout"
    assert record.outcome.result.hint is not None
    assert record.outcome.result.hint.startswith("accept_ack_lost;diagnostic_refs=")
    assert "tool-diagnostic-" in record.outcome.result.hint
    assert recorded_reasons == [DuplicateDurableMissingReason.HOST_ACCEPT_TIMEOUT]
    assert activation_adapter.requests == []


@pytest.mark.asyncio
async def test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref() -> None:
    """awaiting accept retry 耗尽时最终失败 outcome 携带诊断引用。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _RetryExhaustedAwaitingAcceptPort()
    diagnostics = InMemoryToolTraceDiagnosticEmitter()
    activation_adapter = _SpyWaitActivationAdapter()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
        diagnostic_emitter=diagnostics,
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_awaiting_accept_timeout"
    assert (
        record.outcome.result.hint
        == "accept_ack_lost;diagnostic_refs=tool-diagnostic-memory-1"
    )
    assert len(diagnostics.records) == 1
    assert diagnostics.records[0].reason_code == "accept_timeout"
    assert activation_adapter.requests == []


@pytest.mark.asyncio
async def test_sync_timeout_error_from_awaiting_accept_port_is_not_caught() -> None:
    """同步 awaiting accept port 的 TimeoutError 不应被误分类为 retry timeout。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=_TimeoutAwaitingAcceptPort(),
        wait_adapter_registry=_wait_adapter_registry(),
    )

    with pytest.raises(TimeoutError, match="sync awaiting timeout"):
        await executor.execute(_request(_call("tool-call-1")))


@pytest.mark.asyncio
async def test_poll_awaiting_without_external_job_ref_is_governed_error() -> None:
    """POLL binding 未派生 external_job_ref 时返回受治理错误。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _AwaitingAcceptPort()
    activation_adapter = _SpyWaitActivationAdapter()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry_without_external_job_ref(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert awaiting_accept_port.candidates == []
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "awaiting_external_job_missing"
    assert activation_adapter.requests == []


@pytest.mark.asyncio
async def test_concurrent_duplicate_awaiting_fanout_does_not_start_second_job() -> None:
    """防御性 awaiting fanout 不启动第二个业务 callable 或 accept candidate。"""

    entered = asyncio.Event()
    release = asyncio.Event()
    callable_ = _BlockingAwaitingCallable(entered=entered, release=release)
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _AwaitingAcceptPort()
    activation_adapter = _SpyWaitActivationAdapter()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        wait_activation_registry=_wait_activation_registry(activation_adapter),
    )

    owner = asyncio.create_task(executor.execute(_request(_call("tool-call-1"))))
    await entered.wait()
    waiter = asyncio.create_task(executor.execute(_request(_call("tool-call-2"))))
    await asyncio.sleep(0)
    assert callable_.call_count == 1
    assert not waiter.done()

    release.set()
    owner_outcome, waiter_outcome = await asyncio.gather(owner, waiter)

    owner_record = owner_outcome.records[0]
    waiter_record = waiter_outcome.records[0]
    assert callable_.call_count == 1
    assert accept_port.candidates == []
    assert len(awaiting_accept_port.candidates) == 1
    assert isinstance(owner_record.outcome, ToolAwaitingOutcome)
    assert isinstance(waiter_record.outcome, ToolAwaitingOutcome)
    assert waiter_record.tool_call_id == "tool-call-2"
    assert len(activation_adapter.requests) == 1


@pytest.mark.asyncio
async def test_awaiting_outcome_stops_remaining_batch_calls() -> None:
    """批内首个 awaiting accepted 后不得继续调用后续业务工具。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _AwaitingAcceptPort()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
    )

    outcome = await executor.execute(
        _request(_call("tool-call-1"), _call("tool-call-2"))
    )

    first, second = (record.outcome for record in outcome.records)
    assert callable_.call_count == 1
    assert len(awaiting_accept_port.candidates) == 1
    assert isinstance(first, ToolAwaitingOutcome)
    assert isinstance(second, ToolFailedOutcome)
    assert second.result.hint == "run_suspended_by_tool_awaiting"


@pytest.mark.asyncio
async def test_no_tool_scope_rejects_model_tool_call() -> None:
    """replay/no-tool scope 下即使模型发起工具调用也必须拒绝。"""

    callable_ = _CountingCallable({"secret": "no-tool"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port, allow_tool_calls=False)

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert accept_port.candidates[0].tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_call_not_allowed_in_scope"
    )
    assert isinstance(record.outcome, ToolFailedOutcome)


@pytest.mark.asyncio
async def test_batch_mixed_accept_outcomes_keep_accepted_visible() -> None:
    """批内 accepted call 可见，rejected / timeout call 只返回 governed error。"""

    callable_ = _CountingCallable({"accepted": True})
    accept_port = _SequencedAcceptPort(
        (
            _accepted_ack_for_call("tool-call-1"),
            ToolFactRejectedAck(
                reason_code=ToolAcceptRejectReason.EXPLICIT_POLICY_REJECT,
                message="reject second",
                diagnostic_refs=(),
                retryable=False,
            ),
            ToolFactAcceptTimedOut(
                attempt_count=1,
                last_error_code="ack_lost",
                diagnostic_refs=(),
            ),
        )
    )
    executor = _executor(
        callable_,
        accept_port,
        retry_policy=ToolAcceptRetryPolicy(max_attempts=1, backoff_seconds=0.0),
    )

    outcome = await executor.execute(
        _request(
            _call("tool-call-1", ticker="DAYU-1"),
            _call("tool-call-2", ticker="DAYU-2"),
            _call("tool-call-3", ticker="DAYU-3"),
        )
    )

    first, second, third = (record.outcome for record in outcome.records)
    assert callable_.call_count == 3
    assert isinstance(first, ToolCompletedOutcome)
    assert first.result.value == {"accepted": True}
    assert isinstance(second, ToolFailedOutcome)
    assert second.result.error == "tool_accept_rejected"
    assert isinstance(third, ToolFailedOutcome)
    assert third.result.error == "tool_accept_timeout"


def _executor(
    callable_: (
        _CountingCallable
        | _OutcomeCallable
        | _AwaitingCallable
        | _BlockingAwaitingCallable
        | _BlockingCallable
    ),
    accept_port: HostToolFactAcceptPort,
    *,
    awaiting_accept_port: HostToolAwaitingAcceptPort | None = None,
    wait_adapter_registry: WaitAdapterRegistry | None = None,
    wait_activation_registry: WaitActivationRegistry | None = None,
    retry_policy: ToolAcceptRetryPolicy | None = None,
    policy_view: ToolRuntimePolicyView | None = None,
    allow_tool_calls: bool = True,
    diagnostic_emitter: InMemoryToolTraceDiagnosticEmitter | None = None,
    capsule_factory: ToolExecutionCapsuleFactory | None = None,
    execution: ToolExecutionCapability | None = None,
) -> ToolExecutor:
    """构造测试用 ToolRuntime executor。

    :param callable_: fake 工具 callable。
    :param accept_port: fake accept port。
    :param awaiting_accept_port: fake awaiting accept port。
    :param wait_adapter_registry: wait adapter registry。
    :param wait_activation_registry: wait activation registry。
    :param retry_policy: accept retry policy。
    :param policy_view: Host 内部工具 policy view。
    :param allow_tool_calls: ToolRuntime scope 是否允许工具调用。
    :param diagnostic_emitter: 可选内存诊断发射器。
    :param capsule_factory: 可选内部 execution capsule factory。
    :param execution: 可选工具 execution capability；``None`` 表示默认
        ``async_direct``。
    :returns: ToolExecutor protocol 实现。
    """

    handle = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(
                    definitions=(
                        _definition(
                            "fake_tool",
                            callable_,
                            execution=execution,
                        ),
                    )
                ),
                source_refs=(_source_ref(),),
                framework_tool_policy=default_framework_tool_policy_view(),
                policy_snapshot_digest=_POLICY_DIGEST,
            ),
            execution_scope=ToolRuntimeExecutionScope(
                session_id=_SESSION_ID,
                run_id=_RUN_ID,
                attempt_id=_ATTEMPT_ID,
                execution_id=_EXECUTION_ID,
                allow_tool_calls=allow_tool_calls,
            ),
            accept_port=accept_port,
            awaiting_accept_port=awaiting_accept_port,
            wait_adapter_registry=wait_adapter_registry,
            wait_activation_registry=wait_activation_registry,
            retry_policy=(
                retry_policy
                if retry_policy is not None
                else ToolAcceptRetryPolicy(max_attempts=1, backoff_seconds=0.0)
            ),
            policy_view=policy_view if policy_view is not None else ToolRuntimePolicyView(),
            diagnostic_emitter=diagnostic_emitter,
            execution_capsule_factory=capsule_factory,
        )
    )
    return handle.tool_executor


def _request(
    *calls: ToolCallRequest,
    timeout_seconds: float | None = _DEFAULT_TOOL_TIMEOUT_SECONDS,
    cancellation_token: CancellationToken | None = None,
) -> BatchToolExecutionRequest:
    """构造批式工具执行请求。

    :param calls: 单次工具调用请求。
    :param timeout_seconds: 批式工具执行 timeout。
    :param cancellation_token: 批式工具执行 cancellation token。
    :returns: 批式工具执行请求。
    """

    return BatchToolExecutionRequest(
        calls=calls,
        context=BatchToolExecutionContext(
            run_id=_RUN_ID,
            session_id=_SESSION_ID,
            iteration_id=_ITERATION_ID,
            timeout_seconds=timeout_seconds,
            cancellation_token=(
                cancellation_token
                if cancellation_token is not None
                else _OpenCancellationToken()
            ),
            correlation_id="correlation-toolruntime",
        ),
    )


def _call(tool_call_id: str, *, ticker: str = "DAYU") -> ToolCallRequest:
    """构造 fake 工具调用。

    :param tool_call_id: 工具调用 id。
    :param ticker: fake ticker 参数。
    :returns: 工具调用请求。
    """

    return ToolCallRequest(
        tool_call_id=tool_call_id,
        name="fake_tool",
        arguments={"ticker": ticker},
        index_in_iteration=0,
        provider_state=None,
    )


def _definition(
    name: str,
    callable_: ToolCallable,
    *,
    execution: ToolExecutionCapability | None = None,
) -> ToolDefinition:
    """构造工具声明。

    :param name: 工具名。
    :param callable_: 工具 callable。
    :param execution: 可选工具 execution capability；``None`` 表示默认
        ``async_direct``。
    :returns: 工具声明。
    """

    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description="fake tool",
                parameters=_parameters(),
            ),
        ),
        callable=callable_,
        execution=(
            execution
            if execution is not None
            else AsyncDirectToolExecutionCapability()
        ),
        truncate=None,
        display=None,
        tags=("test",),
    )


def _parameters() -> ToolParametersSchema:
    """构造工具参数 schema。

    :returns: 参数 schema。
    """

    properties: dict[str, JsonValue] = {
        "ticker": {"type": "string"},
        "tool_idempotency_key": {"type": "string"},
    }
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker",),
        additional_properties=False,
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造工具来源引用。

    :returns: ToolBundleSourceRef。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="toolruntime-test",
    )


def _wait_adapter_registry() -> WaitAdapterRegistry:
    """构造测试用 wait adapter registry。

    :returns: wait adapter registry。
    """

    return WaitAdapterRegistry(
        (
            WaitAdapterBinding(
                tool_name="fake_tool",
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                adapter_key=WaitAdapterKey("poll:fake-tool"),
                resume_policy=WaitResumePolicy.POLL,
                external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
            ),
        )
    )


def _wait_adapter_registry_without_external_job_ref() -> WaitAdapterRegistry:
    """构造不会派生 external job ref 的 poll registry。

    :returns: wait adapter registry。
    """

    return WaitAdapterRegistry(
        (
            WaitAdapterBinding(
                tool_name="fake_tool",
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                adapter_key=WaitAdapterKey("poll:fake-tool"),
                resume_policy=WaitResumePolicy.POLL,
                external_job_ref_source=WaitExternalJobRefSource.NONE,
            ),
        )
    )


def _wait_activation_registry(
    adapter: _SpyWaitActivationAdapter,
) -> WaitActivationRegistry:
    """构造测试用 wait activation registry。

    :param adapter: spy activation adapter。
    :returns: wait activation registry。
    """

    return WaitActivationRegistry(
        (
            WaitActivationAdapterRegistration(
                adapter_key=WaitAdapterKey("poll:fake-tool"),
                adapter=adapter,
            ),
        )
    )


def _external_job_await_spec() -> ToolAwaitSpec:
    """构造测试用 external job 等待规约。

    :returns: external job 等待规约。
    """

    return ToolAwaitSpec(
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        deadline=None,
        resume_token="resume-token",
    )


def _awaiting_accepted_ack(wait_id: str) -> ToolAwaitingAcceptedAck:
    """构造测试用 awaiting accepted ack。

    :param wait_id: Host wait id。
    :returns: awaiting accepted ack。
    """

    tool_awaiting_ref = ToolAwaitingEventRef(
        event_id=f"event-tool-awaiting-{wait_id}",
        event_sequence=1,
    )
    run_waiting_ref = ToolAwaitingEventRef(
        event_id=f"event-run-waiting-{wait_id}",
        event_sequence=2,
    )
    attempt_suspended_ref = ToolAwaitingEventRef(
        event_id=f"event-attempt-suspended-{wait_id}",
        event_sequence=3,
    )
    return ToolAwaitingAcceptedAck(
        accepted_event_refs=(
            tool_awaiting_ref,
            run_waiting_ref,
            attempt_suspended_ref,
        ),
        wait_id=wait_id,
        tool_awaiting_event_ref=tool_awaiting_ref,
        run_waiting_event_ref=run_waiting_ref,
        attempt_suspended_event_ref=attempt_suspended_ref,
        result_digest=sha256_digest_json({"wait_id": wait_id}),
        idempotency_record_ref=f"awaiting:{wait_id}",
    )


def _accepted_ack_for_call(tool_call_id: str) -> ToolFactAcceptedAck:
    """构造 accepted ack。

    :param tool_call_id: 工具调用 id。
    :returns: accepted ack。
    """

    candidate = ToolFactAcceptCandidate(
        identity=ToolAcceptIdentity(
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            attempt_id=_ATTEMPT_ID,
            execution_id=_EXECUTION_ID,
        ),
        call=ToolAcceptCall(
            iteration_id=_ITERATION_ID,
            tool_call_id=tool_call_id,
            tool_name="fake_tool",
            tool_schema_digest=sha256_digest_json({"schema": tool_call_id}),
            tool_identity_digest=sha256_digest_json({"identity": tool_call_id}),
            normalized_arguments_digest=sha256_digest_json(
                {"arguments": tool_call_id}
            ),
        ),
        tool_fact_kind=ToolFactKind.COMPLETED,
        result=ToolAcceptResult(
            outcome_digest=sha256_digest_json({"outcome": tool_call_id}),
            payload_digest=sha256_digest_json({"payload": tool_call_id}),
            payload_ref=None,
            truncation=None,
            raw_tool_outcome={
                "kind": "completed",
                "result": {
                    "ok": True,
                    "value": {"tool_call_id": tool_call_id},
                    "meta": None,
                },
            },
            tool_timing={
                "schema_version": 1,
                "status": "missing_tool_result_meta",
                "started_at": None,
                "finished_at": None,
                "duration_ms": None,
                "duration_source": None,
            },
        ),
        governance=ToolAcceptGovernance(
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.ALLOW,
                reason_code=None,
                message=None,
            ),
            tool_idempotency_key=None,
            duplicate=None,
        ),
        idempotency=ToolAcceptIdempotency(
            accept_idempotency_key=f"accept-{tool_call_id}",
            semantic_input_digest=sha256_digest_json({"semantic": tool_call_id}),
        ),
        diagnostics=ToolAcceptDiagnostics(diagnostic_refs=()),
    )
    return _accepted_ack(candidate)


def _accepted_ack(candidate: ToolFactAcceptCandidate) -> ToolFactAcceptedAck:
    """按 candidate 构造 accepted ack。

    :param candidate: 工具事实候选。
    :returns: accepted ack。
    """

    requested_ref = HostEventRef(
        event_id=f"event-requested-{candidate.call.tool_call_id}",
        event_sequence=1,
    )
    result_ref = HostEventRef(
        event_id=f"event-result-{candidate.call.tool_call_id}",
        event_sequence=2,
    )
    result = candidate.result
    result_digest = (
        result.outcome_digest
        if result is not None
        else candidate.idempotency.semantic_input_digest
    )
    result_payload_ref = (
        HostPayloadRef("payload-ref", result.payload_digest)
        if result is not None and result.payload_digest is not None
        else None
    )
    return ToolFactAcceptedAck(
        accepted_event_refs=(requested_ref, result_ref),
        tool_fact_id=f"tool-fact-{candidate.call.tool_call_id}",
        tool_call_requested_event_ref=requested_ref,
        tool_call_governed_event_ref=None,
        tool_result_event_ref=result_ref,
        result_payload_ref=result_payload_ref,
        result_digest=result_digest,
        reuse_prior_event_refs=(),
        diagnostic_refs=(),
        idempotency_record_ref=f"idempotency-{candidate.call.tool_call_id}",
    )


def _required_result(candidate: ToolFactAcceptCandidate) -> ToolAcceptResult:
    """读取必须存在的 result 子结构。

    :param candidate: 工具事实候选。
    :returns: result 子结构。
    :raises AssertionError: candidate 未携带 result 时抛出。
    """

    assert candidate.result is not None
    return candidate.result


def _required_failure_metadata(
    candidate: ToolFactAcceptCandidate,
) -> Mapping[str, JsonValue]:
    """读取必须存在的 failure metadata。

    :param candidate: 工具事实候选。
    :returns: failure metadata JSON object。
    :raises AssertionError: candidate 未携带 result 或 failure metadata 时抛出。
    """

    metadata = _required_result(candidate).failure_metadata
    assert metadata is not None
    return metadata


def _assert_bounded_text(
    metadata: Mapping[str, JsonValue],
    field_name: str,
    original: str | None,
    expected_truncated: bool,
) -> None:
    """断言 bounded text 字段值、截断标志和 full original digest。

    :param metadata: failure metadata JSON object。
    :param field_name: bounded text 字段名前缀。
    :param original: 原始文本。
    :param expected_truncated: 预期截断标志。
    :returns: ``None``。
    """

    if original is None:
        assert metadata[field_name] is None
        assert metadata[f"{field_name}_sha256"] is None
        assert metadata[f"{field_name}_truncated"] is False
        return
    assert metadata[field_name] == original[:512]
    assert metadata[f"{field_name}_sha256"] == _text_sha256(original)
    assert metadata[f"{field_name}_truncated"] is expected_truncated


def _text_sha256(value: str) -> str:
    """计算文本 UTF-8 sha256 digest。

    :param value: 原始文本。
    :returns: ``sha256:`` 前缀 digest。
    """

    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
