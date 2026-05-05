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
from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timezone

import aiohttp

from dayu.contracts.cancellation import CancellationToken
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
from dayu.engine.runners.openai.cancellation_helpers import (
    _RunnerInterrupted,
    await_or_cancel,
)
from dayu.engine.runners.openai.error_classifier import (
    classify_exception,
    classify_http_status,
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

_SSE_CONTENT_TYPE_FRAGMENT: str = "text/event-stream"


class _AttemptFailedRetriable(Exception):
    """单次尝试失败且**可能**重试。

    :param error_code: 中性错误码。
    :param http_status: HTTP 状态码；网络层错误为 ``None``。
    :param message_text: 人类可读消息。
    :param retry_after_seconds: 解析后的 ``Retry-After`` 秒数。
    """

    def __init__(
        self,
        *,
        error_code: RunnerHTTPErrorCode,
        http_status: int | None,
        message_text: str,
        retry_after_seconds: float | None,
    ) -> None:
        super().__init__(message_text)
        self.error_code: RunnerHTTPErrorCode = error_code
        self.http_status: int | None = http_status
        self.message_text: str = message_text
        self.retry_after_seconds: float | None = retry_after_seconds


class _AttemptFailedTerminal(Exception):
    """单次尝试失败且不可重试。"""

    def __init__(
        self,
        *,
        error_code: RunnerHTTPErrorCode,
        http_status: int | None,
        message_text: str,
    ) -> None:
        super().__init__(message_text)
        self.error_code: RunnerHTTPErrorCode = error_code
        self.http_status: int | None = http_status
        self.message_text: str = message_text


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

        payload = build_request_payload(
            messages=messages, options=options, tools=tools, spec=self._spec
        )
        attempt = 0
        try:
            while True:
                attempt += 1
                try:
                    async for event in self._do_attempt(payload, options):
                        yield event
                    return
                except _AttemptFailedTerminal as failure:
                    yield self._make_http_error_event(
                        error_code=failure.error_code,
                        http_status=failure.http_status,
                        message_text=failure.message_text,
                        attempt=attempt,
                    )
                    yield self._make_done_event(FinishReason.ERROR)
                    return
                except _AttemptFailedRetriable as failure:
                    decision = compute_retry_decision(
                        error_code=failure.error_code,
                        attempt=attempt,
                        max_retries=self._spec.max_retries,
                        retry_after_seconds=failure.retry_after_seconds,
                    )
                    if not decision.should_retry:
                        yield self._make_http_error_event(
                            error_code=failure.error_code,
                            http_status=failure.http_status,
                            message_text=failure.message_text,
                            attempt=attempt,
                        )
                        yield self._make_done_event(FinishReason.ERROR)
                        return
                    await await_or_cancel(
                        asyncio.sleep(decision.sleep_seconds),
                        token=self._token,
                    )
        except _RunnerInterrupted:
            # 取消例外：直接退出生成器，不补 RunnerDoneData。
            return

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
                retry_after_seconds=None,
            ) from exc
        try:
            if response.status != 200:
                error_code = classify_http_status(response.status)
                retry_after = parse_retry_after(
                    response.headers.get("Retry-After")
                )
                body_preview = await self._safe_read_text(response)
                if error_code in {
                    RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED,
                    RunnerHTTPErrorCode.SERVER_ERROR,
                }:
                    raise _AttemptFailedRetriable(
                        error_code=error_code,
                        http_status=response.status,
                        message_text=body_preview
                        or f"HTTP {response.status}",
                        retry_after_seconds=retry_after,
                    )
                raise _AttemptFailedTerminal(
                    error_code=error_code,
                    http_status=response.status,
                    message_text=body_preview
                    or f"HTTP {response.status}",
                )
            content_type = (
                response.headers.get("Content-Type") or ""
            ).lower()
            hook = detect_reasoning_protocol_hook(
                self._spec.provider_request
            )
            if options.stream and _SSE_CONTENT_TYPE_FRAGMENT in content_type:
                parser = SSEParser(hook=hook)
                async for event in parser.parse(
                    self._iter_response_bytes(response)
                ):
                    yield event
            else:
                body = await await_or_cancel(
                    response.read(), token=self._token
                )
                for event in parse_non_stream_response(body, hook=hook):
                    yield event
        finally:
            response.release()

    async def _iter_response_bytes(
        self, response: aiohttp.ClientResponse
    ) -> AsyncIterator[bytes]:
        """把响应 body 包装为带取消观察的字节迭代器。

        :param response: aiohttp 响应。
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
                    retry_after_seconds=None,
                ) from exc
            if not chunk:
                return
            yield chunk

    async def _safe_read_text(
        self, response: aiohttp.ClientResponse
    ) -> str:
        """尽力读取错误响应的文本，失败时返回空串。"""

        try:
            return await await_or_cancel(
                response.text(), token=self._token
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError):
            return ""

    def _make_http_error_event(
        self,
        *,
        error_code: RunnerHTTPErrorCode,
        http_status: int | None,
        message_text: str,
        attempt: int,
    ) -> RunnerEvent:
        """构造 HTTP 错误事件。"""

        data = RunnerHTTPErrorData(
            error_code=error_code,
            http_status=http_status,
            message=message_text,
            provider_request_id=None,
            raw_payload=None,
            attempt=attempt,
            retried=attempt > 1,
        )
        return RunnerEvent(
            type=RunnerEventType.RUNNER_HTTP_ERROR,
            data=data,
            occurred_at=datetime.now(tz=timezone.utc),
        )

    def _make_done_event(self, finish_reason: FinishReason) -> RunnerEvent:
        """构造 Done 事件。"""

        return RunnerEvent(
            type=RunnerEventType.RUNNER_DONE,
            data=RunnerDoneData(finish_reason=finish_reason),
            occurred_at=datetime.now(tz=timezone.utc),
        )


__all__ = ["AsyncOpenAIRunner"]
