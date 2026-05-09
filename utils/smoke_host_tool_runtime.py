"""Host P2 ToolRuntime smoke。

该脚本在单进程内演示 schema-driven truncate、canonical RunEvent 事实、
非 EventLog handle 补读与 single-use 失效。日志只输出中性摘要，不输出
scope token 明文或完整大结果。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from dayu.contracts import JsonValue, ToolTruncateSpec
from dayu.contracts.tool_call import (
    ToolCallRequest,
    ToolExecutionContext,
    ToolExecutionRequest,
)
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host import (
    ToolFetchMoreHandleRequest,
    ToolFetchMoreHandleSucceededResult,
    ToolFetchMoreRequest,
    ToolFetchMoreSucceededResult,
)
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._proxy import LocalProxy
from dayu.host._run_harness import LocalRunHarness
from dayu.host._tool_runtime import InMemoryToolRuntime, ToolRuntimeToolExecutor
from dayu.host._worker import EngineWorker
from dayu.host.contracts import (
    ToolCursorIssuedData,
    ToolFetchMoreCompletedData,
    ToolFetchMoreFailedData,
    ToolFetchMoreRequestedData,
    ToolResultTruncatedData,
)

_LOGGER: logging.Logger = logging.getLogger("smoke.host.tool_runtime")
_RUN_ID: str = "smoke_run_tool_runtime"
_SESSION_ID: str = "smoke_session"
_TOOL_CALL_ID: str = "smoke_tc_1"


@dataclass(frozen=True, slots=True)
class _Token:
    """smoke 用永不取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否取消。

        :returns: 始终为 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


@dataclass(slots=True)
class _LargeListExecutor:
    """返回较大列表的 fake 业务工具。"""

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """执行 fake 工具。

        :param request: 工具执行请求。
        :returns: 成功 outcome。
        :raises Exception: 不主动抛出异常。
        """

        values: list[JsonValue] = [f"row-{index:03d}" for index in range(12)]
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=values,
                truncation=None,
                meta=None,
            )
        )


def _request() -> ToolExecutionRequest:
    """构造 smoke 工具执行请求。

    :returns: ToolExecutionRequest。
    :raises Exception: 不主动抛出异常。
    """

    return ToolExecutionRequest(
        call=ToolCallRequest(
            tool_call_id=_TOOL_CALL_ID,
            name="smoke_list",
            arguments={"query": "demo"},
            index_in_iteration=0,
            provider_state=None,
        ),
        context=ToolExecutionContext(
            run_id=_RUN_ID,
            session_id=_SESSION_ID,
            iteration_id="smoke_iter_1",
            tool_call_id=_TOOL_CALL_ID,
            index_in_iteration=0,
            timeout_seconds=None,
            cancellation_token=_Token(),
            correlation_id="smoke-correlation",
        ),
    )


def _spec() -> ToolTruncateSpec:
    """构造 smoke 截断声明。

    :returns: ToolTruncateSpec。
    :raises Exception: 不主动抛出异常。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy="list_items",
        limits={"max_items": 4},
        target_field=None,
        field_path=None,
        ttl_seconds=120,
    )


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。

    :returns: argparse Namespace。
    :raises SystemExit: 参数非法时由 argparse 抛出。
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


async def _main() -> None:
    """执行 smoke 主流程。

    :returns: 无返回值。
    :raises RuntimeError: smoke 关键断言失败时抛出。
    """

    event_store = InMemoryRunEventStore()
    runtime = InMemoryToolRuntime(
        executor=_LargeListExecutor(),
        event_store=event_store,
        truncate_specs={"smoke_list": _spec()},
    )
    adapter = ToolRuntimeToolExecutor(runtime)
    harness = LocalRunHarness(
        proxy=LocalProxy(worker=EngineWorker(adapter)),
        event_store=event_store,
        tool_runtime=runtime,
    )

    outcome = await adapter.execute(_request())
    if not isinstance(outcome, ToolCompletedOutcome):
        raise RuntimeError("tool execution did not complete")
    value = outcome.result.value
    if not isinstance(value, list):
        raise RuntimeError("truncated value is not a list")
    _LOGGER.info(
        "execute completed truncated_items=%s has_truncation=%s",
        len(value),
        outcome.result.truncation is not None,
    )

    events = await event_store.list_events(_RUN_ID, after=None)
    cursor_fingerprint = ""
    for event in events:
        data = event.data
        if isinstance(data, ToolResultTruncatedData):
            cursor_fingerprint = data.cursor_fingerprint
            _LOGGER.info(
                "event cursor=%s type=%s fingerprint=%s size=%s total=%s",
                event.cursor.sequence,
                event.type.value,
                data.cursor_fingerprint,
                data.value_summary.size,
                data.total_estimate,
            )
        elif isinstance(data, ToolCursorIssuedData):
            _LOGGER.info(
                "event cursor=%s type=%s fingerprint=%s parent=%s offset=%s",
                event.cursor.sequence,
                event.type.value,
                data.cursor_fingerprint,
                data.parent_cursor_fingerprint,
                data.offset,
            )
    if not cursor_fingerprint:
        raise RuntimeError("cursor fingerprint was not issued")

    handle_result = await harness.get_tool_fetch_more_handle(
        ToolFetchMoreHandleRequest(
            iteration_id="smoke_iter_1",
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            tool_call_id=_TOOL_CALL_ID,
            cursor_fingerprint=cursor_fingerprint,
        )
    )
    if not isinstance(handle_result, ToolFetchMoreHandleSucceededResult):
        raise RuntimeError(handle_result.error_code)
    _LOGGER.info(
        "handle acquired fingerprint=%s expires_at=%.3f",
        handle_result.handle.cursor.fingerprint,
        handle_result.expires_at_monotonic,
    )

    fetch_result = await harness.fetch_more_tool_result(
        ToolFetchMoreRequest(
            iteration_id="smoke_iter_1",
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            tool_call_id=_TOOL_CALL_ID,
            cursor=handle_result.handle.cursor,
            scope_token=handle_result.handle.scope_token,
            limit=99,
        )
    )
    if not isinstance(fetch_result, ToolFetchMoreSucceededResult):
        raise RuntimeError(fetch_result.error_code)
    if not isinstance(fetch_result.value, list):
        raise RuntimeError("fetch_more value is not a list")
    _LOGGER.info(
        "fetch_more completed items=%s has_more=%s event_cursor=%s",
        len(fetch_result.value),
        fetch_result.truncation is not None,
        fetch_result.event_cursor.sequence,
    )

    reused = await harness.fetch_more_tool_result(
        ToolFetchMoreRequest(
            iteration_id="smoke_iter_1",
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            tool_call_id=_TOOL_CALL_ID,
            cursor=handle_result.handle.cursor,
            scope_token=handle_result.handle.scope_token,
            limit=None,
        )
    )
    if isinstance(reused, ToolFetchMoreSucceededResult):
        raise RuntimeError("single-use cursor unexpectedly succeeded")
    _LOGGER.info(
        "old cursor rejected error=%s event_cursor=%s",
        reused.error_code,
        reused.event_cursor.sequence if reused.event_cursor is not None else None,
    )

    for event in await event_store.list_events(_RUN_ID, after=None):
        data = event.data
        if isinstance(data, ToolFetchMoreRequestedData):
            _LOGGER.debug(
                "event cursor=%s type=%s fingerprint=%s requested_limit=%s",
                event.cursor.sequence,
                event.type.value,
                data.cursor_fingerprint,
                data.requested_limit,
            )
        elif isinstance(data, ToolFetchMoreCompletedData):
            _LOGGER.debug(
                "event cursor=%s type=%s consumed=%s next=%s chunk_size=%s",
                event.cursor.sequence,
                event.type.value,
                data.consumed_cursor_fingerprint,
                data.next_cursor_fingerprint,
                data.chunk_size,
            )
        elif isinstance(data, ToolFetchMoreFailedData):
            _LOGGER.debug(
                "event cursor=%s type=%s fingerprint=%s error=%s",
                event.cursor.sequence,
                event.type.value,
                data.cursor_fingerprint,
                data.error_code,
            )


def main() -> None:
    """脚本入口。

    :returns: 无返回值。
    :raises SystemExit: argparse 或 asyncio 运行失败时抛出。
    """

    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper()),
        format="%(levelname)s %(name)s %(message)s",
    )
    asyncio.run(_main())


if __name__ == "__main__":
    main()
