"""OpenAI 兼容 :class:`AsyncRunner` 实现。

:class:`AsyncOpenAIRunner` 把
:class:`~dayu.engine.runners.openai.payload.build_request_payload` 构建的
请求发送给 provider，按 ``Content-Type`` 自动选择 SSE 解析或非流式
JSON 解析，并按 :class:`RunnerSpec.max_retries` 与 ``Retry-After``
应用重试退避。

终态规则（见 phase1-plan.md §6.4 / §7）：

- 成功 / 协议错误：以 :class:`RunnerDoneData` 收口（必要时
  ``finish_reason=ERROR``）。
- HTTP / 网络 / 超时终态错误：发出
  :class:`RunnerHTTPErrorData` + :class:`RunnerDoneData(ERROR)` 收口。
- 取消例外：``token.is_cancelled() == True`` 时生成器**自然终止**，
  不再 yield 任何事件，**不**补 :class:`RunnerDoneData`。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeVar

import aiohttp

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_schema import ToolSchema
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessage
from dayu.engine.contracts.runner_events import (
    RunnerDoneData,
    RunnerEvent,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
)
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.engine.runners.openai.cancellation_helpers import _RunnerInterrupted
from dayu.engine.runners.openai.error_classifier import (
    classify_exception,
    classify_http_status,
    detect_context_overflow,
    is_retriable,
)
from dayu.engine.runners.openai.http_client import HTTPClient
from dayu.engine.runners.openai.non_stream_parser import (
    parse_non_stream_response,
)
from dayu.engine.runners.openai.payload import build_request_payload
from dayu.engine.runners.openai._types import _OpenAIRequestPayload
from dayu.engine.runners.openai.reasoning_protocol import (
    detect_reasoning_protocol_hook,
)
from dayu.engine.runners.openai.retry_policy import (
    compute_retry_decision,
    parse_retry_after,
)
from dayu.engine.runners.openai.sse_parser import SSEParser
from dayu.runtime.cancellation import (
    WaitCancelled,
    WaitCompleted,
    WaitTimedOut,
    await_or_cancel as _runtime_await_or_cancel,
    wait_for_or_cancel as _runtime_wait_for_or_cancel,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)

_SSE_CONTENT_TYPE_FRAGMENT: str = "text/event-stream"
_JSON_CONTENT_TYPE_FRAGMENT: str = "json"
_PROVIDER_REQUEST_ID_HEADER_NAMES: tuple[str, ...] = ("x-request-id",)

_AwaitableResult = TypeVar("_AwaitableResult")


@dataclass(frozen=True, slots=True)
class _HTTPErrorBody:
    """HTTP 错误响应体读取结果。

    :param message_text: 尽力读取到的人类可读 body 文本。
    :param raw_payload: 当 body 是 JSON object 时保留的原始载荷。
    """

    message_text: str
    raw_payload: JsonValue | None


def _extract_provider_request_id(headers: Iterable[tuple[str, str]]) -> str | None:
    """从 provider response headers 提取 request id。

    :param headers: response header 键值序列。
    :returns: ``x-request-id`` 去除首尾空白后的值；缺失或空白时返回
        ``None``。
    :raises Exception: 不主动抛出异常。
    """

    wanted = frozenset(_PROVIDER_REQUEST_ID_HEADER_NAMES)
    for name, value in headers:
        if name.lower() in wanted:
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _is_sse_response(*, content_type: str, stream: bool) -> bool:
    """判断 HTTP 200 response 是否应按 SSE 解析。

    :param content_type: 小写后的 ``Content-Type``。
    :param stream: 本次 effective options 是否请求流式。
    :returns: 应按 SSE parser 尝试时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    if not stream:
        return False
    if _SSE_CONTENT_TYPE_FRAGMENT in content_type:
        return True
    return _JSON_CONTENT_TYPE_FRAGMENT not in content_type


async def await_or_cancel(
    awaitable: Awaitable[_AwaitableResult],
    *,
    token: CancellationToken,
) -> _AwaitableResult:
    """Runner 内部 await + cancel 适配器。

    把 :func:`dayu.runtime.cancellation.await_or_cancel` 的封闭联合返回
    翻译为 Runner 内部协作式取消信号 :class:`_RunnerInterrupted`：

    - :class:`WaitCompleted` 分支返回结果值。
    - :class:`WaitCancelled` 分支抛出 :class:`_RunnerInterrupted`，由
      生成器顶层捕获后直接退出生成器。

    :param awaitable: 需要等待的 awaitable / coroutine。
    :param token: 取消观察 token。
    :returns: ``awaitable`` 的返回结果。

    :raises _RunnerInterrupted: 当 ``token.is_cancelled()`` 在 awaitable
        完成前先成立时抛出。
    :raises Exception: 透传 ``awaitable`` 自身的异常。
    """

    outcome = await _runtime_await_or_cancel(awaitable, token=token)
    if isinstance(outcome, WaitCancelled):
        raise _RunnerInterrupted(outcome.reason or "cancelled during await")
    assert isinstance(outcome, WaitCompleted)
    return outcome.value


class _AttemptFailedRetriable(Exception):
    """单次尝试失败且**可能**重试。

    :param error_code: 中性错误码。
    :param http_status: HTTP 状态码；网络层错误为 ``None``。
    :param message_text: 人类可读消息。
    :param provider_request_id: provider response request id。
    :param raw_payload: provider JSON object 错误载荷。
    :param retry_after_seconds: 解析后的 ``Retry-After`` 秒数。
    """

    def __init__(
        self,
        *,
        error_code: RunnerHTTPErrorCode,
        http_status: int | None,
        message_text: str,
        provider_request_id: str | None,
        raw_payload: JsonValue | None,
        retry_after_seconds: float | None,
    ) -> None:
        super().__init__(message_text)
        self.error_code: RunnerHTTPErrorCode = error_code
        self.http_status: int | None = http_status
        self.message_text: str = message_text
        self.provider_request_id: str | None = provider_request_id
        self.raw_payload: JsonValue | None = raw_payload
        self.retry_after_seconds: float | None = retry_after_seconds


class _AttemptFailedTerminal(Exception):
    """单次尝试失败且不可重试。"""

    def __init__(
        self,
        *,
        error_code: RunnerHTTPErrorCode,
        http_status: int | None,
        message_text: str,
        provider_request_id: str | None,
        raw_payload: JsonValue | None,
    ) -> None:
        super().__init__(message_text)
        self.error_code: RunnerHTTPErrorCode = error_code
        self.http_status: int | None = http_status
        self.message_text: str = message_text
        self.provider_request_id: str | None = provider_request_id
        self.raw_payload: JsonValue | None = raw_payload


class AsyncOpenAIRunner:
    """OpenAI 兼容协议异步 Runner。"""

    def __init__(
        self,
        *,
        spec: RunnerSpec,
        cancellation_token: CancellationToken,
    ) -> None:
        """构造 Runner。

        :param spec: Runner 规约。
        :param cancellation_token: 取消观察 token。
        """

        self._spec: RunnerSpec = spec
        self._token: CancellationToken = cancellation_token
        self._http_client: HTTPClient = HTTPClient(
            timeout_seconds=spec.default_timeout_seconds
        )

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
    ) -> AsyncIterator[RunnerEvent]:
        """发起一次 LLM 调用并返回 :class:`RunnerEvent` 异步流。

        :param messages: 消息序列。
        :param options: 单次调用参数。
        :param tools: 工具 schema 序列。
        :returns: :class:`RunnerEvent` 异步迭代器。
        """

        return self._call_impl(messages, options, tools)

    def is_supports_tool_calling(self) -> bool:
        """返回 Runner 是否支持工具调用。

        :returns: ``RunnerSpec.supports_tool_calling`` 字段值。
        """

        return self._spec.supports_tool_calling

    async def close(self) -> None:
        """幂等关闭底层 HTTP 资源。

        :returns: 无返回值。
        """

        await self._http_client.close()

    async def _call_impl(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
    ) -> AsyncIterator[RunnerEvent]:
        """``call`` 的真实异步生成器实现。"""

        effective_options = self._effective_options(options)
        payload = build_request_payload(
            messages=messages,
            options=effective_options,
            tools=tools,
            spec=self._spec,
        )
        attempt = 0
        try:
            while True:
                attempt += 1
                _LOGGER.debug(
                    "runner.attempt.start provider=%s model=%s attempt=%d "
                    "stream=%s",
                    self._spec.provider,
                    self._spec.model,
                    attempt,
                    effective_options.stream,
                )
                try:
                    async for event in self._do_attempt(
                        payload, effective_options
                    ):
                        yield event
                    return
                except _AttemptFailedTerminal as failure:
                    _LOGGER.warning(
                        "runner.attempt.terminal provider=%s model=%s "
                        "attempt=%d error_code=%s http_status=%s "
                        "provider_request_id=%s",
                        self._spec.provider,
                        self._spec.model,
                        attempt,
                        failure.error_code.value,
                        failure.http_status,
                        failure.provider_request_id,
                    )
                    yield self._make_http_error_event(
                        error_code=failure.error_code,
                        http_status=failure.http_status,
                        message_text=failure.message_text,
                        provider_request_id=failure.provider_request_id,
                        raw_payload=failure.raw_payload,
                        attempt=attempt,
                    )
                    yield self._make_done_event(
                        FinishReason.ERROR,
                        provider_request_id=failure.provider_request_id,
                    )
                    return
                except _AttemptFailedRetriable as failure:
                    decision = compute_retry_decision(
                        error_code=failure.error_code,
                        attempt=attempt,
                        max_retries=self._spec.max_retries,
                        retry_after_seconds=failure.retry_after_seconds,
                    )
                    if not decision.should_retry:
                        _LOGGER.warning(
                            "runner.attempt.exhausted provider=%s model=%s "
                            "attempt=%d error_code=%s http_status=%s "
                            "provider_request_id=%s",
                            self._spec.provider,
                            self._spec.model,
                            attempt,
                            failure.error_code.value,
                            failure.http_status,
                            failure.provider_request_id,
                        )
                        yield self._make_http_error_event(
                            error_code=failure.error_code,
                            http_status=failure.http_status,
                            message_text=failure.message_text,
                            provider_request_id=failure.provider_request_id,
                            raw_payload=failure.raw_payload,
                            attempt=attempt,
                        )
                        yield self._make_done_event(
                            FinishReason.ERROR,
                            provider_request_id=failure.provider_request_id,
                        )
                        return
                    _LOGGER.info(
                        "runner.attempt.retry provider=%s model=%s "
                        "attempt=%d error_code=%s sleep=%.3fs",
                        self._spec.provider,
                        self._spec.model,
                        attempt,
                        failure.error_code.value,
                        decision.sleep_seconds,
                    )
                    await await_or_cancel(
                        asyncio.sleep(decision.sleep_seconds),
                        token=self._token,
                    )
        except _RunnerInterrupted:
            # 取消例外：直接退出生成器，不补 RunnerDoneData。
            _LOGGER.debug(
                "runner.cancelled provider=%s model=%s attempt=%d",
                self._spec.provider,
                self._spec.model,
                attempt,
            )
            return

    def _effective_options(self, options: RunnerCallOptions) -> RunnerCallOptions:
        """根据 Runner capability 计算本次实际调用选项。

        :param options: 调用方传入的 Runner 调用选项。
        :returns: 若当前 Runner 不支持流式且调用方请求流式，则返回
            ``stream=False`` 的新选项；否则返回原选项。
        :raises Exception: 不主动抛出异常。
        """

        if not options.stream or self._spec.supports_streaming:
            return options
        return RunnerCallOptions(
            temperature=options.temperature,
            max_tokens=options.max_tokens,
            top_p=options.top_p,
            stream=False,
        )

    async def _do_attempt(
        self,
        payload: _OpenAIRequestPayload,
        options: RunnerCallOptions,
    ) -> AsyncIterator[RunnerEvent]:
        """执行 HTTP 请求并归一为事件。

        :param payload: 已构建的请求 payload（投影后的强类型 TypedDict
            视图，本路径仅做 JSON 序列化）。
        :param options: 调用参数。
        :returns: :class:`RunnerEvent` 异步迭代器。

        :raises _AttemptFailedRetriable: 当本次尝试失败且属于可重试
            类目时。
        :raises _AttemptFailedTerminal: 当本次尝试失败且不可重试时。
        :raises _RunnerInterrupted: 当 cancellation token 命中时。
        """

        session = self._http_client.session()
        body_bytes = json.dumps(dict(payload)).encode("utf-8")
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            **dict(self._spec.headers),
        }
        _LOGGER.debug(
            "runner.http.post endpoint=%s body_bytes=%d stream=%s",
            self._spec.endpoint,
            len(body_bytes),
            options.stream,
        )
        try:
            response_ctx = session.post(
                self._spec.endpoint, data=body_bytes, headers=headers
            )
            response = await await_or_cancel(
                response_ctx.__aenter__(), token=self._token
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise _AttemptFailedRetriable(
                error_code=classify_exception(exc),
                http_status=None,
                message_text=str(exc) or type(exc).__name__,
                provider_request_id=None,
                raw_payload=None,
                retry_after_seconds=None,
            ) from exc
        try:
            provider_request_id = _extract_provider_request_id(
                response.headers.items()
            )
            _LOGGER.debug(
                "runner.http.response status=%d content_type=%s "
                "provider_request_id=%s",
                response.status,
                response.headers.get("Content-Type") or "",
                provider_request_id,
            )
            if response.status != 200:
                error_code = classify_http_status(response.status)
                retry_after = parse_retry_after(
                    response.headers.get("Retry-After")
                )
                error_body = await self._safe_read_error_body(response)
                if detect_context_overflow(
                    http_status=response.status,
                    response_text=error_body.message_text,
                ):
                    raise _AttemptFailedTerminal(
                        error_code=RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED,
                        http_status=response.status,
                        message_text=error_body.message_text
                        or f"HTTP {response.status}",
                        provider_request_id=provider_request_id,
                        raw_payload=error_body.raw_payload,
                    )
                if is_retriable(error_code):
                    raise _AttemptFailedRetriable(
                        error_code=error_code,
                        http_status=response.status,
                        message_text=error_body.message_text
                        or f"HTTP {response.status}",
                        provider_request_id=provider_request_id,
                        raw_payload=error_body.raw_payload,
                        retry_after_seconds=retry_after,
                    )
                raise _AttemptFailedTerminal(
                    error_code=error_code,
                    http_status=response.status,
                    message_text=error_body.message_text
                    or f"HTTP {response.status}",
                    provider_request_id=provider_request_id,
                    raw_payload=error_body.raw_payload,
                )
            content_type = (
                response.headers.get("Content-Type") or ""
            ).lower()
            hook = detect_reasoning_protocol_hook(
                self._spec.provider_request
            )
            if _is_sse_response(
                content_type=content_type, stream=options.stream
            ):
                parser = SSEParser(
                    hook=hook, provider_request_id=provider_request_id
                )
                async for event in parser.parse(
                    self._iter_response_bytes(
                        response,
                        provider_request_id=provider_request_id,
                    )
                ):
                    yield event
            else:
                body = await await_or_cancel(
                    response.read(), token=self._token
                )
                for event in parse_non_stream_response(
                    body, hook=hook, provider_request_id=provider_request_id
                ):
                    yield event
        finally:
            response.release()

    async def _iter_response_bytes(
        self,
        response: aiohttp.ClientResponse,
        *,
        provider_request_id: str | None,
    ) -> AsyncIterator[bytes]:
        """把响应 body 包装为带取消观察的字节迭代器。

        根据 :class:`RunnerSpec.stream_idle_timeout_seconds` 是否启用，
        分派到 :meth:`_iter_response_bytes_no_idle` 或
        :meth:`_iter_response_bytes_with_idle`。

        :param response: aiohttp 响应。
        :param provider_request_id: 当前 response header 提供的 request id。
        :returns: 字节迭代器。

        :raises _AttemptFailedRetriable: 网络读取失败时。
        :raises _RunnerInterrupted: token 命中时。
        """

        if self._spec.stream_idle_timeout_seconds is None:
            async for chunk in self._iter_response_bytes_no_idle(
                response, provider_request_id=provider_request_id
            ):
                yield chunk
            return
        async for chunk in self._iter_response_bytes_with_idle(
            response, provider_request_id=provider_request_id
        ):
            yield chunk

    async def _iter_response_bytes_no_idle(
        self,
        response: aiohttp.ClientResponse,
        *,
        provider_request_id: str | None,
    ) -> AsyncIterator[bytes]:
        """无空闲检测的字节迭代器。

        :param response: aiohttp 响应。
        :param provider_request_id: 当前 response header 提供的 request id。
        :returns: 字节迭代器。

        :raises _AttemptFailedRetriable: 网络读取失败时。
        :raises _RunnerInterrupted: token 命中时。
        """

        while True:
            try:
                chunk = await await_or_cancel(
                    response.content.readany(), token=self._token
                )
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                raise _AttemptFailedRetriable(
                    error_code=classify_exception(exc),
                    http_status=None,
                    message_text=str(exc) or type(exc).__name__,
                    provider_request_id=provider_request_id,
                    raw_payload=None,
                    retry_after_seconds=None,
                ) from exc
            if not chunk:
                return
            yield chunk

    async def _iter_response_bytes_with_idle(
        self,
        response: aiohttp.ClientResponse,
        *,
        provider_request_id: str | None,
    ) -> AsyncIterator[bytes]:
        """带空闲心跳 / timeout 的字节迭代器。

        在 ``readany()`` 上做「pending vs cancellation vs heartbeat /
        timeout」三方 race：

        - 单次等待时长不超过
          ``stream_idle_heartbeat_seconds``（若设置且小于剩余 timeout）
          或剩余 timeout 时长。
        - 心跳到点：发出一条 DEBUG 日志，继续等待，复用同一 readany
          pending task（不取消、不丢弃已收到的字节）。
        - 累计 idle 超过 ``stream_idle_timeout_seconds``：把 pending
          取消并抛 :class:`_AttemptFailedRetriable`(TIMEOUT)。
        - cancellation：透传 :class:`_RunnerInterrupted`。

        :param response: aiohttp 响应。
        :param provider_request_id: 当前 response header 提供的 request id。
        :returns: 字节迭代器。

        :raises _AttemptFailedRetriable: 网络读取失败 / idle timeout。
        :raises _RunnerInterrupted: token 命中。
        """

        timeout_seconds = self._spec.stream_idle_timeout_seconds
        heartbeat_seconds = self._spec.stream_idle_heartbeat_seconds
        assert timeout_seconds is not None  # post_init 已校验
        while True:
            pending: asyncio.Task[bytes] = asyncio.ensure_future(
                response.content.readany()
            )
            idle_started = time.monotonic()
            # try/finally 确保 pending 在任何退出路径（外层 cancel /
            # aclose / 心跳 timeout 终结 / 网络异常 / 正常完成）都会被
            # 取消并 await 到收口；正常完成时 _cancel_pending_readany
            # 会因 pending.done() 直接 no-op。
            try:
                try:
                    while True:
                        elapsed = time.monotonic() - idle_started
                        remaining = timeout_seconds - elapsed
                        if remaining <= 0:
                            _LOGGER.warning(
                                "runner.stream_idle.timeout "
                                "elapsed=%.3fs timeout=%.3fs",
                                elapsed,
                                timeout_seconds,
                            )
                            raise _AttemptFailedRetriable(
                                error_code=RunnerHTTPErrorCode.TIMEOUT,
                                http_status=None,
                                message_text=(
                                    "stream idle timeout: no bytes "
                                    f"received in {timeout_seconds:.3f}s"
                                ),
                                provider_request_id=provider_request_id,
                                raw_payload=None,
                                retry_after_seconds=None,
                            )
                        if (
                            heartbeat_seconds is not None
                            and heartbeat_seconds <= remaining
                        ):
                            wait_seconds = heartbeat_seconds
                        else:
                            wait_seconds = remaining

                        outcome = await _runtime_wait_for_or_cancel(
                            pending,
                            token=self._token,
                            timeout_seconds=wait_seconds,
                        )
                        if isinstance(outcome, WaitCancelled):
                            raise _RunnerInterrupted(
                                outcome.reason
                                or "cancelled during stream"
                            )
                        if isinstance(outcome, WaitTimedOut):
                            # heartbeat 命中：发心跳日志后继续等。
                            if heartbeat_seconds is not None:
                                _LOGGER.debug(
                                    "runner.stream_idle.heartbeat "
                                    "elapsed=%.3fs timeout=%.3fs",
                                    time.monotonic() - idle_started,
                                    timeout_seconds,
                                )
                            continue
                        assert isinstance(outcome, WaitCompleted)
                        chunk = outcome.value
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    # readany() 自身网络层异常：包成 retriable。
                    raise _AttemptFailedRetriable(
                        error_code=classify_exception(exc),
                        http_status=None,
                        message_text=str(exc) or type(exc).__name__,
                        provider_request_id=provider_request_id,
                        raw_payload=None,
                        retry_after_seconds=None,
                    ) from exc
            finally:
                await self._cancel_pending_readany(pending)
            if not chunk:
                return
            yield chunk

    @staticmethod
    async def _cancel_pending_readany(
        pending: asyncio.Task[bytes],
    ) -> None:
        """取消并等待 ``readany`` pending task 收口。

        :param pending: 需要取消的 readany task。
        :returns: 无返回值；吞掉 ``CancelledError`` 与读取异常。
        """

        if pending.done():
            return
        pending.cancel()
        try:
            await pending
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    async def _safe_read_error_body(
        self, response: aiohttp.ClientResponse
    ) -> _HTTPErrorBody:
        """尽力读取错误响应 body，并保留 JSON object 载荷。

        :param response: HTTP 错误响应。
        :returns: body 文本与可选 JSON object 载荷。
        :raises Exception: 不主动抛出异常。
        """

        try:
            message_text = await await_or_cancel(
                response.text(), token=self._token
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError):
            return _HTTPErrorBody(message_text="", raw_payload=None)
        try:
            decoded: JsonValue = json.loads(message_text)
        except json.JSONDecodeError:
            return _HTTPErrorBody(message_text=message_text, raw_payload=None)
        if isinstance(decoded, dict):
            return _HTTPErrorBody(
                message_text=message_text,
                raw_payload=decoded,
            )
        return _HTTPErrorBody(message_text=message_text, raw_payload=None)

    def _make_http_error_event(
        self,
        *,
        error_code: RunnerHTTPErrorCode,
        http_status: int | None,
        message_text: str,
        provider_request_id: str | None,
        raw_payload: JsonValue | None,
        attempt: int,
    ) -> RunnerEvent:
        """构造 HTTP 错误事件。"""

        data = RunnerHTTPErrorData(
            error_code=error_code,
            http_status=http_status,
            message=message_text,
            provider_request_id=provider_request_id,
            raw_payload=raw_payload,
            attempt=attempt,
            retried=attempt > 1,
        )
        return RunnerEvent(
            type=RunnerEventType.RUNNER_HTTP_ERROR,
            data=data,
            occurred_at=datetime.now(tz=timezone.utc),
        )

    def _make_done_event(
        self,
        finish_reason: FinishReason,
        *,
        provider_request_id: str | None,
    ) -> RunnerEvent:
        """构造 Done 事件。

        :param finish_reason: 完成原因。
        :param provider_request_id: 本次 Runner 调用最终采用的 provider
            response request id。
        :returns: Runner done event。
        :raises Exception: 不主动抛出异常。
        """

        return RunnerEvent(
            type=RunnerEventType.RUNNER_DONE,
            data=RunnerDoneData(
                finish_reason=finish_reason,
                provider_request_id=provider_request_id,
            ),
            occurred_at=datetime.now(tz=timezone.utc),
        )


__all__ = ["AsyncOpenAIRunner"]
