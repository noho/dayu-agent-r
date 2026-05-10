"""Host P2 ToolRuntime smoke。

该脚本在单进程内演示 schema-driven truncate、canonical RunEvent 事实、
非 EventLog handle 补读与 single-use 失效。日志只输出中性摘要，不输出
scope token 明文或完整大结果。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_REPO_ROOT_PARENT_INDEX: int = 1


def _ensure_repo_root_on_path() -> None:
    """确保按文件路径运行脚本时也能导入仓库顶层包。

    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if __package__ not in (None, ""):
        return
    repo_root = Path(__file__).resolve().parents[_REPO_ROOT_PARENT_INDEX]
    repo_root_text = str(repo_root)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)


_ensure_repo_root_on_path()

from dayu.contracts import (
    FRAMEWORK_FETCH_MORE_TOOL_NAME,
    JsonValue,
    ToolTruncateSpec,
)
from dayu.contracts.tool_call import (
    ToolCallRequest,
    ToolExecutionContext,
    ToolExecutionRequest,
)
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._proxy import LocalProxy
from dayu.host._run_harness import LocalRunHarness
from dayu.host._tool_runtime import InMemoryToolRuntime, ToolRuntimeToolExecutor
from utils._smoke_memory_store import SmokeInMemoryConversationMemoryStore
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
        is_durable=False,
        executor=_LargeListExecutor(),
        event_store=event_store,
        truncate_specs={"smoke_list": _spec()},
    )
    adapter = ToolRuntimeToolExecutor(runtime)
    # harness 在 P8-S2 之前用于演示 LocalRunHarness 的公开 fetch_more 入口；
    # S2 之后 framework fetch_more 仅作普通 tool call 经
    # ToolRuntimeToolExecutor -> InMemoryToolRuntime.execute_tool_call。
    # 保留 harness 装配仅为验证 LocalRunHarness 仍能持有 tool_runtime。
    harness = LocalRunHarness(
        is_durable=False,
        proxy=LocalProxy(worker=EngineWorker(adapter)),
        event_store=event_store,
        tool_runtime=runtime,
        memory_store=SmokeInMemoryConversationMemoryStore(),
    )
    assert harness.tool_runtime is runtime

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

    truncation = outcome.result.truncation
    if truncation is None:
        raise RuntimeError("truncation info missing")

    fetch_outcome = await runtime.execute_tool_call(
        ToolExecutionRequest(
            call=ToolCallRequest(
                tool_call_id="smoke_fetch_call_1",
                name=FRAMEWORK_FETCH_MORE_TOOL_NAME,
                arguments={
                    "cursor": truncation.cursor,
                    "scope_token": truncation.scope_token,
                    "limit": 99,
                },
                index_in_iteration=0,
                provider_state=None,
            ),
            context=ToolExecutionContext(
                run_id=_RUN_ID,
                session_id=_SESSION_ID,
                iteration_id="smoke_iter_1",
                tool_call_id="smoke_fetch_call_1",
                index_in_iteration=0,
                timeout_seconds=None,
                cancellation_token=_Token(),
                correlation_id="smoke-correlation",
            ),
        )
    )
    if not isinstance(fetch_outcome, ToolCompletedOutcome):
        raise RuntimeError("framework fetch_more did not complete")
    if not isinstance(fetch_outcome.result.value, list):
        raise RuntimeError("fetch_more value is not a list")
    _LOGGER.info(
        "fetch_more completed items=%s has_more=%s",
        len(fetch_outcome.result.value),
        fetch_outcome.result.truncation is not None,
    )

    reused = await runtime.execute_tool_call(
        ToolExecutionRequest(
            call=ToolCallRequest(
                tool_call_id="smoke_fetch_call_2",
                name=FRAMEWORK_FETCH_MORE_TOOL_NAME,
                arguments={
                    "cursor": truncation.cursor,
                    "scope_token": truncation.scope_token,
                },
                index_in_iteration=0,
                provider_state=None,
            ),
            context=ToolExecutionContext(
                run_id=_RUN_ID,
                session_id=_SESSION_ID,
                iteration_id="smoke_iter_1",
                tool_call_id="smoke_fetch_call_2",
                index_in_iteration=0,
                timeout_seconds=None,
                cancellation_token=_Token(),
                correlation_id="smoke-correlation",
            ),
        )
    )
    if not isinstance(reused, ToolFailedOutcome):
        raise RuntimeError("single-use cursor unexpectedly succeeded")
    _LOGGER.info("old cursor rejected error=%s", reused.result.error)

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
