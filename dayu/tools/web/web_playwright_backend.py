"""网页抓取的 Playwright backend 基础设施。

本模块只承载浏览器单例、同步 worker、storage state 解析与
Playwright 回退执行逻辑，不包含 requests 主路径编排或工具注册。
"""

from __future__ import annotations

import atexit
import asyncio
import logging
import math
import multiprocessing
import os
import pickle
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from multiprocessing.process import BaseProcess
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Final, Protocol, TypeAlias, TypedDict, cast
from urllib.parse import urlparse

import requests
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.runtime.interruptible_process import (
    ProcessCleanupSignal,
    ProcessInterruptResult,
    enter_new_process_session_if_supported,
    interrupt_multiprocessing_process,
)

from .web_fetch_orchestrator import _FetchUrlSafetyError
from .web_challenge_detection import BotChallengeDecision
from .web_egress_policy import WebEgressPolicy, WebEgressPolicyError
from .web_resource_budget import BrowserResourceBudget, DiagnosticResourceBudget
from .web_diagnostics import (
    WebDiagnosticBackend,
    failed_projection,
    project_safe_url_or_empty,
)

MODULE = "ENGINE.WEB_PLAYWRIGHT"
_LOGGER = logging.getLogger(__name__)

_DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
_DEFAULT_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,en;q=0.8"
_DEFAULT_SEC_CH_UA = '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"'
_DEFAULT_SEC_CH_UA_MOBILE = "?0"
_DEFAULT_SEC_CH_UA_PLATFORM = '"macOS"'

WebPayload: TypeAlias = dict[str, JsonValue]
_ProcessInterruptBridgeMessage: TypeAlias = ProcessInterruptResult | BaseException


class _ResultQueueProtocol(Protocol):
    """Playwright worker 结果队列的最小协议。"""

    def put(self, obj: WebPayload, block: bool = True, timeout: float | None = None) -> None:
        """写入 worker 结果。"""
        ...

    def get(self, block: bool = True, timeout: float | None = None) -> WebPayload:
        """读取 worker 结果。"""
        ...

    def get_nowait(self) -> WebPayload:
        """非阻塞读取 worker 结果。"""
        ...

    def close(self) -> None:
        """关闭队列句柄。"""
        ...

    def join_thread(self) -> None:
        """等待队列后台线程结束。"""
        ...


class _RouteRequestProtocol(Protocol):
    """Playwright Route.request 的最小协议。"""

    resource_type: str
    url: str


class _RouteProtocol(Protocol):
    """Playwright Route 的最小协议。"""

    request: _RouteRequestProtocol

    def abort(self) -> None:
        """中止当前请求。"""
        ...

    def continue_(self) -> None:
        """放行当前请求。"""
        ...


class _PlaywrightResponseProtocol(Protocol):
    """Playwright Response 的最小协议。"""

    status: int
    headers: Mapping[str, str]


class _PageProtocol(Protocol):
    """Playwright Page 的最小协议。"""

    url: str

    def goto(self, url: str, *, wait_until: str, timeout: int) -> _PlaywrightResponseProtocol | None:
        """导航到指定 URL。"""
        ...

    def route(self, pattern: str, handler: Callable[[_RouteProtocol], None]) -> None:
        """注册路由处理器。"""
        ...

    def content(self) -> str:
        """读取页面 HTML。"""
        ...

    def evaluate(
        self,
        expression: str,
        arg: Mapping[str, int] | None = None,
    ) -> JsonValue:
        """执行页面脚本并返回 JSON 值。"""
        ...

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        """等待页面加载状态。"""
        ...

    def wait_for_timeout(self, timeout: int) -> None:
        """等待指定毫秒。"""
        ...


class _BrowserContextProtocol(Protocol):
    """Playwright BrowserContext 的最小协议。"""

    def new_page(self) -> _PageProtocol:
        """创建新页面。"""
        ...

    def close(self) -> None:
        """关闭上下文。"""
        ...


class _BrowserProtocol(Protocol):
    """Playwright Browser 的最小协议。"""

    def new_context(self, **kwargs: JsonValue) -> _BrowserContextProtocol:
        """创建浏览器上下文。"""
        ...

    def close(self) -> None:
        """关闭浏览器。"""
        ...


class _ChromiumProtocol(Protocol):
    """Playwright chromium launcher 的最小协议。"""

    def launch(self, **kwargs: JsonValue) -> _BrowserProtocol:
        """启动 Chromium 浏览器。"""
        ...


class _PlaywrightInstanceProtocol(Protocol):
    """Playwright 运行时实例的最小协议。"""

    chromium: _ChromiumProtocol

    def stop(self) -> None:
        """停止 Playwright 运行时。"""
        ...


class _WorkerKwargs(TypedDict):
    """Playwright worker 关键字参数。"""

    url: str
    timeout_seconds: float
    headers: Mapping[str, str] | None
    playwright_channel: str | None
    playwright_storage_state_path: str
    egress_policy: WebEgressPolicy
    browser_resource_budget: BrowserResourceBudget


class _BudgetedDomMetrics(TypedDict):
    """浏览器 bounded TreeWalker 预检结果。"""

    dom_chars: int
    text_chars: int
    dom_exceeded: bool
    text_exceeded: bool


@dataclass(frozen=True, slots=True)
class _BrowserPageProjection:
    """预算预检通过后的完整浏览器页面投影。"""

    html: str
    page_text: str


_BROWSER_DOM_TOO_LARGE_REASON: Final[str] = "browser_dom_too_large"
_BROWSER_TEXT_TOO_LARGE_REASON: Final[str] = "browser_text_too_large"
_BROWSER_RESOURCE_BUDGET_FAILURE_REASONS: Final[frozenset[str]] = frozenset(
    {
        _BROWSER_DOM_TOO_LARGE_REASON,
        _BROWSER_TEXT_TOO_LARGE_REASON,
    }
)


class _BrowserResourceBudgetExceeded(RuntimeError):
    """浏览器页面在完整投影前后超过资源预算。"""

    def __init__(self, reason: str) -> None:
        """初始化浏览器资源超限异常。

        Args:
            reason: 封闭的 browser DOM/text 超限码。

        Returns:
            无。

        Raises:
            ValueError: reason 不是封闭超限码时抛出。
        """

        if reason not in _BROWSER_RESOURCE_BUDGET_FAILURE_REASONS:
            raise ValueError(f"unsupported browser budget failure: {reason}")
        super().__init__(reason)
        self.reason = reason


class _PlaywrightWorkerProtocol(Protocol):
    """Playwright 同步 worker 的最小可调用协议。"""

    def __call__(
        self,
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        browser_resource_budget: BrowserResourceBudget,
    ) -> WebPayload:
        """执行一次 Playwright 抓取。

        Args:
            url: 已通过调用入口校验的 URL。
            timeout_seconds: 单次浏览器抓取超时秒数。
            headers: 可选请求头。
            playwright_channel: 可选浏览器 channel。
            playwright_storage_state_path: 可选 storage state 路径。
            egress_policy: 浏览器导航和子请求出站策略。
            browser_resource_budget: 浏览器 DOM/text/Markdown 资源预算。

        Returns:
            浏览器抓取与转换后的 payload。

        Raises:
            Exception: 浏览器抓取或转换失败时透出。
        """
        ...


class _GetPlaywrightBrowserProtocol(Protocol):
    """Playwright Browser 获取函数的最小协议。"""

    def __call__(
        self,
        *,
        playwright_channel: str | None = None,
        headless: bool = True,
    ) -> _BrowserProtocol | None:
        """获取可用浏览器。"""
        ...


class _ResolveTimeoutBudgetProtocol(Protocol):
    """timeout 预算解析函数的最小协议。"""

    def __call__(
        self,
        timeout_seconds: float,
        *,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        reserve_seconds: float = 0.0,
    ) -> float:
        """解析当前阶段可用 timeout。"""
        ...


class _HtmlPipelineResultProtocol(Protocol):
    """HTML pipeline 返回值的最小协议。"""

    @property
    def title(self) -> str:
        """页面标题。"""
        ...

    @property
    def markdown(self) -> str:
        """Markdown 正文。"""
        ...

    @property
    def extractor_source(self) -> str:
        """抽取器来源。"""
        ...

    @property
    def renderer_source(self) -> str:
        """渲染器来源。"""
        ...

    @property
    def normalization_applied(self) -> bool:
        """是否执行过规范化。"""
        ...

    @property
    def quality_flags(self) -> tuple[str, ...]:
        """质量标记。"""
        ...

    @property
    def content_stats(self) -> Mapping[str, JsonValue]:
        """内容统计。"""
        ...


class _HtmlConverterProtocol(Protocol):
    """HTML 到 Markdown 转换函数的最小协议。"""

    def __call__(self, html: str, *, url: str = "") -> _HtmlPipelineResultProtocol:
        """转换 HTML。"""
        ...


class _ChallengeResultProtocol(Protocol):
    """Challenge 检测结果的最小协议。"""

    @property
    def decision(self) -> BotChallengeDecision:
        """返回挑战页证据强度判定。"""
        ...

    @property
    def challenge_signals(self) -> tuple[str, ...]:
        """挑战页信号。"""
        ...


class _DetectBotChallengeProtocol(Protocol):
    """挑战页检测函数的最小协议。"""

    def __call__(
        self,
        *,
        response: requests.Response | None,
        response_headers: Mapping[str, str] | None = None,
        http_status: int | None = None,
        content_text: str,
    ) -> _ChallengeResultProtocol:
        """检测挑战页。"""
        ...


_PW_INSTANCE: _PlaywrightInstanceProtocol | None = None
_PW_BROWSER: _BrowserProtocol | None = None
_PW_BROWSER_KEY: tuple[str | None, bool] | None = None
_PW_LOCK = Lock()
_PW_RESULT_EXTRA_TIMEOUT_SECONDS = 10
_PW_NAVIGATION_WAIT_UNTIL = "domcontentloaded"
_PW_POST_NAVIGATION_SETTLE_MS = 1000
_PW_HOME_WARMUP_TIMEOUT_MS = 2500
_PW_LOAD_STATE_TIMEOUT_MS = 2500
_PW_NETWORK_IDLE_TIMEOUT_MS = 1500
_PW_RESULT_POLL_INTERVAL_SECONDS = 0.05
_PW_RESULT_DRAIN_GRACE_SECONDS = 0.5
_PW_PROCESS_TERMINATE_GRACE_SECONDS = 1.0
_BUDGETED_DOM_METRICS_SCRIPT = """
({domLimit, textLimit}) => {
  let domChars = 0;
  let textChars = 0;
  let domExceeded = false;
  let textExceeded = false;
  const addDom = (value) => {
    domChars = Math.min(domLimit + 1, domChars + value);
    domExceeded = domChars > domLimit;
  };
  const addText = (value) => {
    textChars = Math.min(textLimit + 1, textChars + value);
    textExceeded = textChars > textLimit;
  };
  const walker = document.createTreeWalker(document, NodeFilter.SHOW_ALL);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.nodeType === Node.ELEMENT_NODE) {
      const localName = node.localName || '';
      addDom(2 * localName.length + 5);
      for (const attribute of node.attributes) {
        addDom(attribute.name.length + 6 * attribute.value.length + 4);
        if (domExceeded) break;
      }
    } else if (node.nodeType === Node.TEXT_NODE) {
      const length = (node.nodeValue || '').length;
      addDom(5 * length);
      addText(length);
    } else if (node.nodeType === Node.COMMENT_NODE) {
      addDom((node.nodeValue || '').length + 7);
    } else if (node.nodeType === Node.DOCUMENT_TYPE_NODE) {
      addDom(
        (node.name || '').length +
        (node.publicId || '').length +
        (node.systemId || '').length +
        32
      );
    }
    if (domExceeded || textExceeded) break;
  }
  return {domChars, textChars, domExceeded, textExceeded};
}
""".strip()
_FULL_PAGE_TEXT_SCRIPT = "() => document.body ? document.body.innerText : ''"


class _PlaywrightProcessCleanup(TypedDict):
    """Playwright raw worker cleanup 诊断。"""

    terminate: ProcessInterruptResult | None
    kill: ProcessInterruptResult | None


class CancelledError(RuntimeError):
    """迁移 Playwright backend 内部取消错误。

    Args:
        message: 错误说明。

    Returns:
        无。

    Raises:
        无。
    """


class Log:
    """迁移 Playwright backend 的窄日志适配器。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    @staticmethod
    def debug(message: str, *, module: str | None = None) -> None:
        """记录 debug 日志。

        Args:
            message: 日志正文。
            module: OLD 模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _LOGGER.debug("[%s] %s", module or MODULE, message)

    @staticmethod
    def warning(message: str, *, module: str | None = None) -> None:
        """记录 warning 日志。

        Args:
            message: 日志正文。
            module: OLD 模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _LOGGER.warning("[%s] %s", module or MODULE, message)


def _playwright_process_entry(
    result_queue: _ResultQueueProtocol,
    worker_callable: _PlaywrightWorkerProtocol,
    worker_kwargs: _WorkerKwargs,
    diagnostic_resource_budget: DiagnosticResourceBudget,
) -> None:
    """子进程入口：执行同步 Playwright worker 并回传结果。

    Args:
        result_queue: 结果队列。
        worker_callable: 同步 worker 函数。
        worker_kwargs: worker 关键字参数。
        diagnostic_resource_budget: process/failure 诊断投影预算。

    Returns:
        无。

    Raises:
        无。
    """

    enter_new_process_session_if_supported()
    diagnostic_url = worker_kwargs["url"]
    max_error_chars = diagnostic_resource_budget.error_chars
    try:
        result_queue.put({
            "kind": "result",
            "payload": worker_callable(**worker_kwargs),
        })
    except _FetchUrlSafetyError as exc:
        result_queue.put(
            {
                "kind": "error",
                "error_type": type(exc).__name__,
                "message": failed_projection(
                    stage="playwright_worker",
                    url=diagnostic_url,
                    elapsed_seconds=0.0,
                    error_code="permission_denied",
                    error_message=str(exc),
                    max_error_chars=max_error_chars,
                    backend=WebDiagnosticBackend.PLAYWRIGHT,
                ).error_message,
                "blocked_by_safety_policy": True,
                "blocked_url": project_safe_url_or_empty(exc.url),
                "blocked_stage": exc.reason,
            }
        )
    except BaseException as exc:
        result_queue.put(
            {
                "kind": "error",
                "error_type": type(exc).__name__,
                "message": failed_projection(
                    stage="playwright_worker",
                    url=diagnostic_url,
                    elapsed_seconds=0.0,
                    error_code="playwright_error",
                    error_message=str(exc),
                    max_error_chars=max_error_chars,
                    backend=WebDiagnosticBackend.PLAYWRIGHT,
                ).error_message,
            }
        )


def _is_picklable_worker(worker_callable: _PlaywrightWorkerProtocol) -> bool:
    """判断给定 worker 是否可安全发送到子进程。"""

    try:
        pickle.dumps(worker_callable)
    except Exception:
        return False
    return True


def _thread_has_running_asyncio_loop() -> bool:
    """判断当前线程是否已经运行 asyncio event loop。

    :returns: 当前线程已有 running loop 时返回 ``True``。
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _run_process_interrupt_in_helper_thread(
    process: BaseProcess,
    signal_kind: ProcessCleanupSignal,
    grace_seconds: float,
    result_queue: Queue[_ProcessInterruptBridgeMessage],
) -> None:
    """在短生命周期线程中运行 async process interrupt primitive。

    :param process: 待 cleanup 的 raw multiprocessing process。
    :param signal_kind: cleanup 信号类型。
    :param grace_seconds: signal 后等待退出的秒数。
    :param result_queue: 回传结果或异常的线程内队列。
    :returns: 无返回值。
    """

    try:
        result_queue.put(
            asyncio.run(
                interrupt_multiprocessing_process(
                    process,
                    signal_kind=signal_kind,
                    grace_seconds=grace_seconds,
                )
            )
        )
    except BaseException as exc:
        result_queue.put(exc)


def _interrupt_playwright_process_sync(
    process: BaseProcess,
    *,
    signal_kind: ProcessCleanupSignal,
    grace_seconds: float,
) -> ProcessInterruptResult:
    """从同步 Playwright cleanup 路径调用 async runtime primitive。

    当前线程没有 running loop 时直接使用 ``asyncio.run``。当前线程已经有
    running loop 时，在短生命周期 helper thread 中运行 ``asyncio.run``，
    避免 cleanup 路径因调用上下文变化触发 ``asyncio.run`` 的运行时限制。

    :param process: 待 cleanup 的 raw multiprocessing process。
    :param signal_kind: cleanup 信号类型。
    :param grace_seconds: signal 后等待退出的秒数。
    :returns: runtime primitive 返回的 interrupt 结果。
    :raises BaseException: helper thread 中 runtime primitive 抛出的异常会原样传播。
    """

    if not _thread_has_running_asyncio_loop():
        return asyncio.run(
            interrupt_multiprocessing_process(
                process,
                signal_kind=signal_kind,
                grace_seconds=grace_seconds,
            )
        )
    result_queue: Queue[_ProcessInterruptBridgeMessage] = Queue(maxsize=1)
    helper_thread = Thread(
        target=_run_process_interrupt_in_helper_thread,
        args=(process, signal_kind, grace_seconds, result_queue),
        name="dayu-web-playwright-cleanup",
        daemon=True,
    )
    helper_thread.start()
    helper_thread.join()
    try:
        message = result_queue.get_nowait()
    except Empty as exc:
        raise RuntimeError("playwright process cleanup helper returned no result") from exc
    if isinstance(message, BaseException):
        raise message
    return message


def _log_playwright_process_cleanup_stage(
    *,
    stage: str,
    result: ProcessInterruptResult | None,
) -> None:
    """记录 Playwright worker cleanup 诊断。

    日志只包含 cleanup 诊断字段，不包含 URL、内容或 headers。

    :param stage: cleanup 阶段标签。
    :param result: runtime primitive 返回的 interrupt 结果；未执行时为 ``None``。
    :returns: 无返回值。
    """

    if result is None:
        return
    diagnostic = result.cleanup
    Log.debug(
        "Playwright worker cleanup "
        f"stage={stage} "
        f"reason={diagnostic.reason.value} "
        f"direct_signal_sent={diagnostic.direct_signal_sent} "
        f"group_signal_sent={diagnostic.group_signal_sent} "
        f"exited={result.exited} "
        f"exitcode={result.exitcode} "
        f"elapsed_seconds={result.elapsed_seconds:.6f}",
        module=MODULE,
    )


def _terminate_playwright_process(process: BaseProcess) -> _PlaywrightProcessCleanup:
    """尽力终止 Playwright worker 进程并返回 cleanup 诊断。

    :param process: Playwright raw ``multiprocessing.Process`` worker。
    :returns: terminate / kill 两阶段 cleanup 诊断；未执行的阶段为 ``None``。
    :raises TypeError: cleanup grace 配置非法时由 runtime primitive 抛出。
    :raises ValueError: cleanup grace 配置非法时由 runtime primitive 抛出。
    """

    cleanup: _PlaywrightProcessCleanup = {"terminate": None, "kill": None}
    if not process.is_alive():
        process.join(timeout=0)
        return cleanup
    cleanup["terminate"] = _interrupt_playwright_process_sync(
        process,
        signal_kind=ProcessCleanupSignal.TERMINATE,
        grace_seconds=_PW_PROCESS_TERMINATE_GRACE_SECONDS,
    )
    _log_playwright_process_cleanup_stage(
        stage=ProcessCleanupSignal.TERMINATE.value,
        result=cleanup["terminate"],
    )
    if process.is_alive():
        cleanup["kill"] = _interrupt_playwright_process_sync(
            process,
            signal_kind=ProcessCleanupSignal.KILL,
            grace_seconds=_PW_PROCESS_TERMINATE_GRACE_SECONDS,
        )
        _log_playwright_process_cleanup_stage(
            stage=ProcessCleanupSignal.KILL.value,
            result=cleanup["kill"],
        )
    return cleanup


def _poll_playwright_result_queue(
    *,
    result_queue: _ResultQueueProtocol,
    timeout: float,
) -> WebPayload | None:
    """在限定时间内轮询 Playwright worker 结果队列。

    Args:
        result_queue: 子进程结果队列。
        timeout: 本次轮询允许等待的秒数。

    Returns:
        读到结果时返回结果字典；本轮无结果时返回 ``None``。

    Raises:
        无。
    """

    try:
        if timeout <= 0:
            return result_queue.get_nowait()
        return result_queue.get(timeout=timeout)
    except Empty:
        return None


def _close_playwright_result_queue(result_queue: _ResultQueueProtocol) -> None:
    """关闭父进程侧结果队列句柄。

    Args:
        result_queue: 子进程结果队列。

    Returns:
        无。

    Raises:
        无。
    """

    try:
        result_queue.close()
    except Exception:
        pass
    try:
        result_queue.join_thread()
    except Exception:
        pass


def _run_playwright_worker_process(
    *,
    playwright_sync_worker: _PlaywrightWorkerProtocol,
    worker_kwargs: _WorkerKwargs,
    diagnostic_resource_budget: DiagnosticResourceBudget,
    total_timeout: float,
    cancellation_token: CancellationToken | None,
) -> WebPayload:
    """在子进程边界执行 Playwright worker，并在超时或取消时硬终止。

    Args:
        playwright_sync_worker: 同步 worker 函数。
        worker_kwargs: worker 关键字参数。
        diagnostic_resource_budget: process/failure 诊断投影预算。
        total_timeout: 父进程等待总时长。
        cancellation_token: 当前工具调用的取消令牌。

    Returns:
        worker 返回的抓取结果。

    Raises:
        TimeoutError: worker 超时未返回时抛出。
        CancelledError: 当前调用已被取消时抛出。
        RuntimeError: worker 异常退出或未回传结果时抛出。
    """

    ctx = multiprocessing.get_context("spawn")
    result_queue = cast(_ResultQueueProtocol, ctx.Queue(maxsize=1))
    process = ctx.Process(
        target=_playwright_process_entry,
        args=(
            result_queue,
            playwright_sync_worker,
            worker_kwargs,
            diagnostic_resource_budget,
        ),
    )
    process.daemon = True
    process.start()
    deadline = time.monotonic() + max(total_timeout, 0.0)
    result_drain_deadline: float | None = None
    try:
        while True:
            if cancellation_token is not None and cancellation_token.is_cancelled():
                _terminate_playwright_process(process)
                raise CancelledError(cancellation_token.cancel_reason() or "工具调用已取消")
            current_time = time.monotonic()
            active_deadline = result_drain_deadline if result_drain_deadline is not None else deadline
            if current_time >= active_deadline:
                if result_drain_deadline is not None:
                    raise RuntimeError("playwright worker exited without result")
                _terminate_playwright_process(process)
                raise TimeoutError("playwright worker timeout")

            payload = _poll_playwright_result_queue(
                result_queue=result_queue,
                timeout=min(_PW_RESULT_POLL_INTERVAL_SECONDS, max(0.0, active_deadline - current_time)),
            )
            if payload is not None:
                process.join(timeout=0)
                break

            if not process.is_alive() and result_drain_deadline is None:
                process.join(timeout=0)
                result_drain_deadline = min(
                    deadline,
                    time.monotonic() + _PW_RESULT_DRAIN_GRACE_SECONDS,
                )
                continue

        if payload.get("kind") == "error":
            if payload.get("blocked_by_safety_policy") is True:
                blocked_url = payload.get("blocked_url")
                blocked_stage = payload.get("blocked_stage")
                if isinstance(blocked_url, str) and isinstance(blocked_stage, str):
                    raise _FetchUrlSafetyError(url=blocked_url, reason=blocked_stage)
            raise RuntimeError(
                f"{payload.get('error_type')}: {payload.get('message')}"
            )
        return cast(WebPayload, payload["payload"])
    finally:
        if process.is_alive():
            _terminate_playwright_process(process)
        _close_playwright_result_queue(result_queue)


def _close_playwright_browser() -> None:
    """关闭 Playwright Browser 和运行时单例。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    global _PW_BROWSER, _PW_INSTANCE, _PW_BROWSER_KEY
    try:
        if _PW_BROWSER is not None:
            _PW_BROWSER.close()
    except Exception:
        pass
    try:
        if _PW_INSTANCE is not None:
            _PW_INSTANCE.stop()
    except Exception:
        pass
    _PW_BROWSER = None
    _PW_INSTANCE = None
    _PW_BROWSER_KEY = None


atexit.register(_close_playwright_browser)


def _normalize_playwright_channel(playwright_channel: str | None) -> str | None:
    """标准化 Playwright channel 配置。

    Args:
        playwright_channel: 原始 channel 配置。

    Returns:
        规整后的 channel；空字符串时返回 `None`。

    Raises:
        无。
    """

    if playwright_channel is None:
        return None
    normalized = str(playwright_channel).strip()
    return normalized or None


def _normalize_playwright_storage_state_dir(path_value: str | None) -> str | None:
    """标准化 Playwright storage state 目录路径。

    Args:
        path_value: 原始路径配置。

    Returns:
        目录路径字符串；未配置时返回 `None`。

    Raises:
        无。
    """

    if path_value is None:
        return None
    normalized = str(path_value).strip()
    if not normalized:
        return None
    return os.path.expanduser(normalized)


def _resolve_playwright_storage_state_path(
    *,
    url: str,
    playwright_storage_state_dir: str | None,
) -> str:
    """按 host 解析 Playwright storage state 文件路径。

    Args:
        url: 当前抓取 URL。
        playwright_storage_state_dir: storage state 目录配置。

    Returns:
        命中的 storage state 文件绝对路径；未命中时返回空字符串。

    Raises:
        无。
    """

    normalized_dir = _normalize_playwright_storage_state_dir(playwright_storage_state_dir)
    if normalized_dir is None:
        return ""
    host = (urlparse(url).hostname or "").strip().lower()
    if not host:
        return ""
    host_candidates = [host]
    if host.startswith("www."):
        stripped_host = host[4:]
        if stripped_host:
            host_candidates.append(stripped_host)
    else:
        host_candidates.append(f"www.{host}")

    for candidate_host in dict.fromkeys(host_candidates):
        candidate = os.path.join(normalized_dir, f"{candidate_host}.json")
        if os.path.isfile(candidate):
            return candidate
    return ""


def _get_playwright_browser(
    *,
    playwright_channel: str | None = None,
    headless: bool = True,
) -> _BrowserProtocol | None:
    """获取或懒初始化全局 Playwright Browser 单例。

    Args:
        playwright_channel: 浏览器 channel 配置。
        headless: 是否以 headless 方式启动。

    Returns:
        Playwright Browser 单例；不可用时返回 `None`。

    Raises:
        无。
    """

    global _PW_INSTANCE, _PW_BROWSER, _PW_BROWSER_KEY
    browser_key = (_normalize_playwright_channel(playwright_channel), bool(headless))
    if _PW_BROWSER is not None and _PW_BROWSER_KEY == browser_key:
        return _PW_BROWSER
    with _PW_LOCK:
        if _PW_BROWSER is not None and _PW_BROWSER_KEY == browser_key:
            return _PW_BROWSER
        if _PW_BROWSER is not None or _PW_INSTANCE is not None:
            _close_playwright_browser()
        try:
            from playwright.sync_api import sync_playwright

            pw = cast(_PlaywrightInstanceProtocol, sync_playwright().start())
            launch_kwargs: WebPayload = {"headless": bool(headless)}
            if browser_key[0] is not None:
                launch_kwargs["channel"] = browser_key[0]
            launch_kwargs["args"] = ["--disable-blink-features=AutomationControlled"]
            browser = pw.chromium.launch(**launch_kwargs)
            _PW_INSTANCE = pw
            _PW_BROWSER = browser
            _PW_BROWSER_KEY = browser_key
        except Exception as exc:
            Log.warning(f"Playwright 浏览器初始化失败，回退不可用: {exc}", module=MODULE)
            return None
    return _PW_BROWSER


def _raise_if_playwright_url_blocked(
    *, url: str, egress_policy: WebEgressPolicy, reason: str
) -> None:
    """在 Playwright 导航/request 边界复用 Web URL 安全谓词。

    Args:
        url: 待校验 URL。
        egress_policy: 当前 Web 调用唯一的出站策略。
        reason: 诊断用阶段标识。

    Returns:
        无。

    Raises:
        _FetchUrlSafetyError: URL 被安全策略拒绝时抛出。
    """

    try:
        egress_policy.authorize_http_target(url, stage=reason)
    except WebEgressPolicyError as exc:
        raise _FetchUrlSafetyError(url=exc.url, reason=reason) from exc


def _route_handler_abort_resources(
    route: _RouteProtocol,
    *,
    egress_policy: WebEgressPolicy,
) -> None:
    """中止图片、字体、媒体请求，并拒绝不安全的浏览器 request。

    Args:
        route: Playwright Route 对象。
        egress_policy: 当前 local/dev 浏览器 profile 的统一出站策略。

    Returns:
        无。

    Raises:
        无。
    """

    abort_resource_types = {"image", "font", "media"}
    if route.request.resource_type in abort_resource_types:
        route.abort()
    elif not egress_policy.is_url_allowed(route.request.url):
        route.abort()
    else:
        route.continue_()


def _get_remaining_playwright_timeout_ms(
    deadline_monotonic: float,
    *,
    time_monotonic: Callable[[], float] = time.monotonic,
) -> int:
    """计算 Playwright 当前阶段剩余超时。

    Args:
        deadline_monotonic: 本次浏览器抓取总预算 deadline。
        time_monotonic: 可注入的单调时钟函数。

    Returns:
        剩余可用毫秒数；预算已耗尽时返回 0。

    Raises:
        无。
    """

    remaining_seconds = max(0.0, deadline_monotonic - time_monotonic())
    return max(0, math.ceil(remaining_seconds * 1000))


def _require_playwright_timeout_ms(
    deadline_monotonic: float,
    *,
    time_monotonic: Callable[[], float] = time.monotonic,
) -> int:
    """为必需的 Playwright 阶段解析剩余超时。

    Args:
        deadline_monotonic: 本次浏览器抓取总预算 deadline。
        time_monotonic: 可注入的单调时钟函数。

    Returns:
        当前阶段可用的毫秒超时。

    Raises:
        RuntimeError: 当浏览器总预算已耗尽时抛出。
    """

    remaining_timeout_ms = _get_remaining_playwright_timeout_ms(
        deadline_monotonic,
        time_monotonic=time_monotonic,
    )
    if remaining_timeout_ms <= 0:
        raise RuntimeError("Playwright 页面加载超时: browser deadline exceeded")
    return remaining_timeout_ms


def _maybe_warmup_playwright_page(
    *,
    page: _PageProtocol,
    url: str,
    deadline_monotonic: float,
    build_domain_home_url: Callable[[str], str],
    normalize_url_for_http: Callable[[str], str],
    egress_policy: WebEgressPolicy,
    time_monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """在浏览器回退前先做一次同域首页预热。

    Args:
        page: Playwright Page。
        url: 目标 URL。
        deadline_monotonic: 本次浏览器抓取总预算 deadline。
        build_domain_home_url: 同域首页构造函数。
        normalize_url_for_http: URL 规范化函数。
        egress_policy: 当前 Web 调用唯一的出站策略。
        time_monotonic: 可注入的单调时钟函数。

    Returns:
        无。

    Raises:
        无。
    """

    try:
        home_url = build_domain_home_url(url)
        normalized_url = normalize_url_for_http(url)
    except ValueError:
        return

    if home_url == normalized_url:
        return
    try:
        _raise_if_playwright_url_blocked(
            url=home_url,
            egress_policy=egress_policy,
            reason="playwright_warmup",
        )
    except RuntimeError:
        return

    remaining_timeout_ms = _get_remaining_playwright_timeout_ms(
        deadline_monotonic,
        time_monotonic=time_monotonic,
    )
    warmup_timeout_ms = min(remaining_timeout_ms, _PW_HOME_WARMUP_TIMEOUT_MS)
    if warmup_timeout_ms <= 0:
        return

    try:
        page.goto(home_url, wait_until="domcontentloaded", timeout=warmup_timeout_ms)
        _raise_if_playwright_url_blocked(
            url=page.url,
            egress_policy=egress_policy,
            reason="playwright_warmup_response",
        )
    except Exception:
        return


def _settle_playwright_page(
    *,
    page: _PageProtocol,
    deadline_monotonic: float,
    time_monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """在浏览器导航后做有上限的页面稳定化等待。

    Args:
        page: Playwright Page。
        deadline_monotonic: 本次浏览器抓取总预算 deadline。
        time_monotonic: 可注入的单调时钟函数。

    Returns:
        无。

    Raises:
        无。
    """

    for state, budget_ms in (
        ("load", _PW_LOAD_STATE_TIMEOUT_MS),
        ("networkidle", _PW_NETWORK_IDLE_TIMEOUT_MS),
    ):
        remaining_timeout_ms = _get_remaining_playwright_timeout_ms(
            deadline_monotonic,
            time_monotonic=time_monotonic,
        )
        step_timeout_ms = min(remaining_timeout_ms, budget_ms)
        if step_timeout_ms <= 0:
            return
        try:
            page.wait_for_load_state(state, timeout=step_timeout_ms)
        except Exception:
            continue

    remaining_timeout_ms = _get_remaining_playwright_timeout_ms(
        deadline_monotonic,
        time_monotonic=time_monotonic,
    )
    step_timeout_ms = min(remaining_timeout_ms, _PW_POST_NAVIGATION_SETTLE_MS)
    if step_timeout_ms <= 0:
        return
    page.wait_for_timeout(step_timeout_ms)


def _read_budgeted_dom_metrics(
    page: _PageProtocol,
    *,
    browser_resource_budget: BrowserResourceBudget,
) -> _BudgetedDomMetrics:
    """执行不生成完整 DOM/text 的 bounded TreeWalker 预检。

    Args:
        page: 当前 Playwright Page。
        browser_resource_budget: 浏览器 DOM/text 资源预算。

    Returns:
        有界 DOM/text counters 与超限标记。

    Raises:
        RuntimeError: 浏览器返回的 metrics shape 或字段类型非法时抛出。
    """

    raw_metrics = page.evaluate(
        _BUDGETED_DOM_METRICS_SCRIPT,
        {
            "domLimit": browser_resource_budget.dom_chars,
            "textLimit": browser_resource_budget.text_chars,
        },
    )
    if not isinstance(raw_metrics, Mapping):
        raise RuntimeError("Playwright DOM budget preflight returned invalid shape")
    dom_chars = raw_metrics.get("domChars")
    text_chars = raw_metrics.get("textChars")
    dom_exceeded = raw_metrics.get("domExceeded")
    text_exceeded = raw_metrics.get("textExceeded")
    if (
        isinstance(dom_chars, bool)
        or not isinstance(dom_chars, int)
        or dom_chars < 0
        or isinstance(text_chars, bool)
        or not isinstance(text_chars, int)
        or text_chars < 0
        or not isinstance(dom_exceeded, bool)
        or not isinstance(text_exceeded, bool)
    ):
        raise RuntimeError("Playwright DOM budget preflight returned invalid fields")
    return {
        "dom_chars": dom_chars,
        "text_chars": text_chars,
        "dom_exceeded": dom_exceeded,
        "text_exceeded": text_exceeded,
    }


def _materialize_bounded_page_projection(
    page: _PageProtocol,
    *,
    browser_resource_budget: BrowserResourceBudget,
) -> _BrowserPageProjection:
    """先 bounded preflight，再生成并复核完整 HTML/text 投影。

    Args:
        page: 当前 Playwright Page。
        browser_resource_budget: 浏览器 DOM/text 资源预算。

    Returns:
        实际长度复核通过的完整 HTML 与页面文本。

    Raises:
        _BrowserResourceBudgetExceeded: DOM/text 预检或实际投影超限时抛出。
        RuntimeError: 浏览器返回的 metrics shape 非法时抛出。
    """

    metrics = _read_budgeted_dom_metrics(
        page,
        browser_resource_budget=browser_resource_budget,
    )
    if (
        metrics["dom_exceeded"]
        or metrics["dom_chars"] > browser_resource_budget.dom_chars
    ):
        raise _BrowserResourceBudgetExceeded(_BROWSER_DOM_TOO_LARGE_REASON)
    if (
        metrics["text_exceeded"]
        or metrics["text_chars"] > browser_resource_budget.text_chars
    ):
        raise _BrowserResourceBudgetExceeded(_BROWSER_TEXT_TOO_LARGE_REASON)

    html = page.content()
    if len(html) > browser_resource_budget.dom_chars:
        raise _BrowserResourceBudgetExceeded(_BROWSER_DOM_TOO_LARGE_REASON)
    try:
        raw_page_text = page.evaluate(_FULL_PAGE_TEXT_SCRIPT)
        page_text = raw_page_text if isinstance(raw_page_text, str) else html
    except Exception:
        Log.debug(
            "Playwright 页面全文本提取失败，回退到 HTML。",
            module=MODULE,
        )
        page_text = html
    if len(page_text) > browser_resource_budget.text_chars:
        raise _BrowserResourceBudgetExceeded(_BROWSER_TEXT_TOO_LARGE_REASON)
    return _BrowserPageProjection(html=html, page_text=page_text)


def _browser_budget_failure(reason: str) -> WebPayload:
    """构造浏览器资源超限的稳定失败事实。

    Args:
        reason: 封闭的 browser DOM/text 超限码。

    Returns:
        可跨进程投影的失败 payload。

    Raises:
        ValueError: reason 不是封闭资源失败码时抛出。
    """

    if reason not in _BROWSER_RESOURCE_BUDGET_FAILURE_REASONS:
        raise ValueError(f"unsupported browser budget failure: {reason}")
    return {
        "ok": False,
        "availability": "unprocessable",
        "reason": reason,
    }


def _playwright_sync_worker(
    *,
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None = None,
    playwright_channel: str | None = None,
    playwright_storage_state_path: str = "",
    get_playwright_browser: _GetPlaywrightBrowserProtocol,
    build_domain_home_url: Callable[[str], str],
    normalize_url_for_http: Callable[[str], str],
    sanitize_response_headers: Callable[[Mapping[str, str]], dict[str, str]],
    convert_html_to_markdown: _HtmlConverterProtocol,
    egress_policy: WebEgressPolicy,
    browser_resource_budget: BrowserResourceBudget,
    time_monotonic: Callable[[], float] = time.monotonic,
) -> WebPayload:
    """在独立线程中执行完整的 Playwright 同步抓取流程。

    Args:
        url: 已通过安全校验的网页链接。
        timeout_seconds: 本次浏览器回退总预算秒数。
        headers: 可选额外请求头；当前保留作未来扩展。
        playwright_channel: 浏览器回退使用的 Chromium channel。
        playwright_storage_state_path: 浏览器回退可选 storage state 文件路径。
        get_playwright_browser: Browser 单例获取函数。
        build_domain_home_url: 同域首页构造函数。
        normalize_url_for_http: URL 规范化函数。
        sanitize_response_headers: 响应头裁剪函数。
        convert_html_to_markdown: HTML 四段式转换函数。
        egress_policy: 当前 Web 调用唯一的出站策略。
        browser_resource_budget: 浏览器 DOM/text/Markdown 资源预算。
        time_monotonic: 可注入的单调时钟函数。

    Returns:
        成功时返回含 `ok=True` 的结果字典；失败时抛出异常由调用方处理。

    Raises:
        RuntimeError: Playwright 不可用、页面加载失败、内容转换失败等。
    """

    _ = headers
    if not egress_policy.allows_private_network:
        return {
            "ok": False,
            "availability": "unprocessable",
            "reason": "browser_egress_policy_unavailable",
        }
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    except ImportError as exc:
        raise RuntimeError(f"Playwright 未安装，无法执行浏览器回退抓取: {exc}") from exc

    stealth_class: type | None = None
    has_stealth = False
    try:
        from playwright_stealth import Stealth

        stealth_class = Stealth
        has_stealth = True
    except ImportError:
        Log.warning("未安装 playwright-stealth，将跳过指纹隐蔽步骤，反爬绕过率可能降低", module=MODULE)

    browser = get_playwright_browser(playwright_channel=playwright_channel, headless=True)
    if browser is None:
        raise RuntimeError("Playwright Browser 单例不可用，无法执行浏览器回退抓取。")

    context_kwargs: WebPayload = {
        "viewport": {"width": 1280, "height": 800},
        "user_agent": _DEFAULT_BROWSER_USER_AGENT,
        "locale": "zh-CN",
        "accept_downloads": False,
        "ignore_https_errors": True,
        "extra_http_headers": {
            "Accept": _DEFAULT_ACCEPT,
            "Accept-Language": _DEFAULT_ACCEPT_LANGUAGE,
            "Sec-Ch-Ua": _DEFAULT_SEC_CH_UA,
            "Sec-Ch-Ua-Mobile": _DEFAULT_SEC_CH_UA_MOBILE,
            "Sec-Ch-Ua-Platform": _DEFAULT_SEC_CH_UA_PLATFORM,
            "Upgrade-Insecure-Requests": "1",
        },
    }
    storage_state_path = str(playwright_storage_state_path).strip()
    if storage_state_path:
        context_kwargs["storage_state"] = storage_state_path
    context = browser.new_context(**context_kwargs)
    try:
        page = context.new_page()
        if has_stealth and stealth_class is not None:
            stealth_class().apply_stealth_sync(page)
        page.route(
            "**/*",
            partial(_route_handler_abort_resources, egress_policy=egress_policy),
        )

        deadline_monotonic = time_monotonic() + max(float(timeout_seconds), 0.0)
        _raise_if_playwright_url_blocked(
            url=url,
            egress_policy=egress_policy,
            reason="playwright_goto",
        )
        _maybe_warmup_playwright_page(
            page=page,
            url=url,
            deadline_monotonic=deadline_monotonic,
            build_domain_home_url=build_domain_home_url,
            normalize_url_for_http=normalize_url_for_http,
            egress_policy=egress_policy,
            time_monotonic=time_monotonic,
        )
        try:
            response = page.goto(
                url,
                wait_until=_PW_NAVIGATION_WAIT_UNTIL,
                timeout=_require_playwright_timeout_ms(
                    deadline_monotonic,
                    time_monotonic=time_monotonic,
                ),
            )
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Playwright 页面加载超时: {exc}") from exc

        if response is None:
            raise RuntimeError("Playwright page.goto 未返回 response 对象。")
        _raise_if_playwright_url_blocked(
            url=page.url,
            egress_policy=egress_policy,
            reason="playwright_response",
        )

        content_type_value = (response.headers.get("content-type") or "").lower()
        if "text/html" not in content_type_value and content_type_value:
            context.close()
            return {
                "ok": False,
                "availability": "unprocessable",
                "reason": "non_html_content_type",
                "http_status": response.status,
                "response_headers": sanitize_response_headers(response.headers),
                "content_type": content_type_value,
            }

        _settle_playwright_page(
            page=page,
            deadline_monotonic=deadline_monotonic,
            time_monotonic=time_monotonic,
        )
        _raise_if_playwright_url_blocked(
            url=page.url,
            egress_policy=egress_policy,
            reason="playwright_settled_page",
        )
        try:
            page_projection = _materialize_bounded_page_projection(
                page,
                browser_resource_budget=browser_resource_budget,
            )
        except _BrowserResourceBudgetExceeded as exc:
            context.close()
            return _browser_budget_failure(exc.reason)
        html = page_projection.html
        final_url = page.url
        page_text = page_projection.page_text
    except Exception:
        context.close()
        raise
    else:
        context.close()

    pipeline_result = convert_html_to_markdown(html, url=final_url)
    if len(pipeline_result.markdown) > browser_resource_budget.text_chars:
        return _browser_budget_failure(_BROWSER_TEXT_TOO_LARGE_REASON)
    return {
        "ok": True,
        "title": pipeline_result.title,
        "content": pipeline_result.markdown,
        "final_url": final_url,
        "extraction_source": pipeline_result.extractor_source,
        "renderer_source": pipeline_result.renderer_source,
        "normalization_applied": pipeline_result.normalization_applied,
        "quality_flags": list(pipeline_result.quality_flags),
        "content_stats": dict(pipeline_result.content_stats),
        "http_status": response.status,
        "response_headers": sanitize_response_headers(response.headers),
    }


def _fetch_and_convert_with_playwright(
    *,
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None = None,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    playwright_channel: str | None = None,
    playwright_storage_state_path: str = "",
    egress_policy: WebEgressPolicy,
    browser_resource_budget: BrowserResourceBudget,
    diagnostic_resource_budget: DiagnosticResourceBudget,
    cancellation_token: CancellationToken | None = None,
    resolve_timeout_budget: _ResolveTimeoutBudgetProtocol,
    playwright_sync_worker: _PlaywrightWorkerProtocol,
    detect_bot_challenge: _DetectBotChallengeProtocol,
) -> WebPayload:
    """使用 Playwright 执行浏览器抓取并转换为 Markdown。

    Args:
        url: 已通过安全校验的网页链接。
        timeout_seconds: 浏览器回退总预算秒数。
        headers: 可选请求头。
        timeout_budget: Runner 注入的单次 tool call 总预算。
        deadline_monotonic: 当前工具调用的单调时钟 deadline。
        playwright_channel: 浏览器回退使用的 Chromium channel。
        playwright_storage_state_path: 浏览器回退可选 storage state 文件路径。
        egress_policy: 当前 Web 调用唯一的出站策略。
        browser_resource_budget: 浏览器 DOM/text/Markdown 资源预算。
        diagnostic_resource_budget: process/failure 诊断投影预算。
        cancellation_token: 当前工具调用的可选取消令牌。
        resolve_timeout_budget: timeout 预算解析函数。
        playwright_sync_worker: 同步 worker 函数。
        detect_bot_challenge: challenge 检测函数。

    Returns:
        成功时返回 `ok=True` 结果；失败时返回标准化失败字典。

    Raises:
        _FetchUrlSafetyError: Playwright 导航或最终页面 URL 被安全策略拒绝时抛出。
    """

    if not egress_policy.allows_private_network:
        return {
            "ok": False,
            "availability": "unprocessable",
            "reason": "browser_egress_policy_unavailable",
        }

    try:
        import playwright  # noqa: F401
    except ImportError:
        Log.warning("playwright 未安装，浏览器回退不可用。", module=MODULE)
        return {
            "ok": False,
            "availability": "unprocessable",
            "reason": "playwright_not_installed",
        }

    try:
        effective_timeout = resolve_timeout_budget(
            timeout_seconds,
            timeout_budget=timeout_budget,
            deadline_monotonic=deadline_monotonic,
            reserve_seconds=_PW_RESULT_EXTRA_TIMEOUT_SECONDS,
        )
    except requests.Timeout:
        return {
            "ok": False,
            "availability": "timeout",
            "reason": "playwright_timeout",
        }

    total_timeout = effective_timeout + _PW_RESULT_EXTRA_TIMEOUT_SECONDS
    try:
        if cancellation_token is not None and cancellation_token.is_cancelled():
            raise CancelledError(cancellation_token.cancel_reason() or "工具调用已取消")
        if _is_picklable_worker(playwright_sync_worker):
            result = _run_playwright_worker_process(
                playwright_sync_worker=playwright_sync_worker,
                worker_kwargs={
                    "url": url,
                    "timeout_seconds": effective_timeout,
                    "headers": headers,
                    "playwright_channel": playwright_channel,
                    "playwright_storage_state_path": playwright_storage_state_path,
                    "egress_policy": egress_policy,
                    "browser_resource_budget": browser_resource_budget,
                },
                diagnostic_resource_budget=diagnostic_resource_budget,
                total_timeout=total_timeout,
                cancellation_token=cancellation_token,
            )
        else:
            Log.warning(
                "Playwright worker 不可序列化，已拒绝同进程 fallback。", module=MODULE
            )
            return {
                "ok": False,
                "availability": "unprocessable",
                "reason": "playwright_worker_not_picklable",
            }
    except TimeoutError:
        timeout_projection = failed_projection(
            stage="playwright_fallback",
            url=url,
            elapsed_seconds=total_timeout,
            error_code="playwright_timeout",
            error_message="Playwright 浏览器回退在预算内未返回结果。",
            max_error_chars=diagnostic_resource_budget.error_chars,
            backend=WebDiagnosticBackend.PLAYWRIGHT,
        )
        Log.debug(
            f"Playwright 浏览器回退失败: {timeout_projection.to_json()}",
            module=MODULE,
        )
        return {
            "ok": False,
            "availability": "timeout",
            "reason": "playwright_timeout",
        }
    except CancelledError:
        raise
    except _FetchUrlSafetyError:
        raise
    except Exception as exc:
        error_projection = failed_projection(
            stage="playwright_fallback",
            url=url,
            elapsed_seconds=0.0,
            error_code="playwright_error",
            error_message=str(exc),
            max_error_chars=diagnostic_resource_budget.error_chars,
            backend=WebDiagnosticBackend.PLAYWRIGHT,
        )
        Log.debug(
            f"Playwright 浏览器回退失败: {error_projection.to_json()}",
            module=MODULE,
        )
        return {
            "ok": False,
            "availability": "unprocessable",
            "reason": "playwright_error",
        }

    if result.get("ok"):
        result_headers = result.get("response_headers")
        response_headers = cast(Mapping[str, str], result_headers) if isinstance(result_headers, Mapping) else None
        result_status = result.get("http_status")
        http_status = result_status if isinstance(result_status, int) and not isinstance(result_status, bool) else None
        content_value = result.get("content")
        content_text = content_value if isinstance(content_value, str) else ""
        challenge = detect_bot_challenge(
            response=None,
            response_headers=response_headers,
            http_status=http_status,
            content_text=content_text,
        )
        if challenge.decision is BotChallengeDecision.CONFIRMED:
            return {
                "ok": False,
                "availability": "blocked",
                "reason": "bot_challenge",
                "http_status": result.get("http_status"),
                "response_headers": result.get("response_headers", {}),
                "challenge_signals": list(challenge.challenge_signals),
            }
    return result
