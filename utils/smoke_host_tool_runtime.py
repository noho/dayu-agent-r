"""Host P2 ToolRuntime smoke。

该脚本在单进程内演示 schema-driven truncate、普通 framework
``fetch_more`` tool call 与 single-use 失效。ToolRuntime 不追加截断或
cursor 专属 RunEvent。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Mapping
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

from dayu.contracts import JsonValue, ToolTruncateSpec
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
from dayu.host._framework_tools import FRAMEWORK_FETCH_MORE_NAME
from dayu.host._proxy import LocalProxy
from dayu.host._run_harness import LocalRunHarness
from dayu.host._tool_result_truncation import extract_truncation_hint
from dayu.host._tool_runtime import HostToolRuntime, ToolRuntimeToolExecutor
from utils._smoke_memory_store import SmokeInMemoryConversationMemoryStore
from dayu.host._worker import EngineWorker

_LOGGER: logging.Logger = logging.getLogger("smoke.host.tool_runtime")
_RUN_ID: str = "smoke_run_tool_runtime"
_SESSION_ID: str = "smoke_session"
_TOOL_CALL_ID: str = "smoke_tc_1"


def _content_value(value: JsonValue) -> JsonValue:
    """读取非 object 工具值被截断后的 ``content`` 包装。

    :param value: 工具成功结果值。
    :returns: ``content`` 字段或原值。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, Mapping) and "content" in value:
        return value["content"]
    return value


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
    runtime = HostToolRuntime(
        is_durable=False,
        executor=_LargeListExecutor(),
        event_store=event_store,
        truncate_specs={"smoke_list": _spec()},
    )
    adapter = ToolRuntimeToolExecutor(runtime)
    harness = LocalRunHarness(
        is_durable=False,
        proxy=LocalProxy(
            worker=EngineWorker(tool_executor=adapter)
        ),
        event_store=event_store,
        tool_runtime=runtime,
        memory_store=SmokeInMemoryConversationMemoryStore(),
    )
    assert harness.tool_runtime is runtime

    outcome = await adapter.execute(_request())
    if not isinstance(outcome, ToolCompletedOutcome):
        raise RuntimeError("tool execution did not complete")
    value = outcome.result.value
    content = _content_value(value)
    if not isinstance(content, list):
        raise RuntimeError("truncated value is not a list")
    _LOGGER.info(
        "execute completed truncated_items=%s truncation_present %s",
        len(content),
        extract_truncation_hint(outcome.result.value) is not None,
    )

    if await event_store.list_events(_RUN_ID, after=None) != ():
        raise RuntimeError("ToolRuntime appended unexpected special events")

    truncation = extract_truncation_hint(outcome.result.value)
    if truncation is None:
        raise RuntimeError("truncation info missing")

    fetch_outcome = await runtime.execute_tool_call(
        ToolExecutionRequest(
            call=ToolCallRequest(
                tool_call_id="smoke_fetch_call_1",
                name=FRAMEWORK_FETCH_MORE_NAME,
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
    fetch_content = _content_value(fetch_outcome.result.value)
    if not isinstance(fetch_content, list):
        raise RuntimeError("fetch_more value is not a list")
    _LOGGER.info(
        "fetch_more completed items=%s has_more=%s",
        len(fetch_content),
        extract_truncation_hint(fetch_outcome.result.value) is not None,
    )

    reused = await runtime.execute_tool_call(
        ToolExecutionRequest(
            call=ToolCallRequest(
                tool_call_id="smoke_fetch_call_2",
                name=FRAMEWORK_FETCH_MORE_NAME,
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

    if await event_store.list_events(_RUN_ID, after=None) != ():
        raise RuntimeError("fetch_more appended unexpected special events")


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
