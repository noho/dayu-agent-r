"""Host P8-S7 测试用 multiprocessing 平台 helper。

本模块是 ``tests/host`` 私有 helper, 不进入生产路径。它把 P8-S7 真实多
进程压力测试需要的样板集中在一处, 让 :mod:`test_phase8_multiprocess_stress`
里的每个场景只关心"哪几个 spawn-safe worker 并发做什么", 不再各自重写
启动 / join / 超时 / 终止 / 退出码 / 子进程异常回传等机制。

设计要点:

- **Spawn-only**: 一律使用 ``multiprocessing.get_context("spawn")`` 启
  动子进程, 不依赖 fork。fork 在测试主进程内已加载 asyncio loop /
  SQLite handle, 子进程会继承一个不可用的进程内状态; spawn 则强制每
  个子进程从干净状态启动, 与生产 host 进程行为一致。
- **Module-level worker**: 子进程执行的 callable 必须可被 pickle, 因此
  调用方必须把 worker 写成模块级函数; 本模块只负责把 ``WorkerSpec``
  里的 callable + args 交给 ``Process``, 不允许 closures。
- **结果回收**: 通过 spawn-context 的 :class:`multiprocessing.Queue`
  在子进程里报告"成功 + 结果"或"失败 + traceback 文本"; 主进程不依赖
  exit code 的具体数字含义猜测原因, 而是把 typed traceback 文本回传到
  测试断言里。
- **Join + 超时 + 强杀**: 主进程等待每个子进程, 超时未退则
  ``terminate()``、再不行 ``kill()`` 并最终抛出 ``RuntimeError``;
  这是为了避免单个测试 hang 整个 pytest 运行。
- **临时 SQLite 路径**: SQLite WAL 多进程必须用真实文件路径, 不允许
  ``:memory:``。本 helper 提供 :func:`temp_database_path` 统一生成。

本 helper 不引入 host 生产代码, 也不暴露任何观察者 / 锁 / 事件总线 API,
仅满足 P8-S7 测试所需。multiprocess launcher / process supervision 的
生产化归未来阶段, 不在 P8-S7 scope 内。
"""

from __future__ import annotations

import multiprocessing as _mp
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.context import SpawnContext
from multiprocessing.process import BaseProcess
from multiprocessing.queues import Queue as _MpQueue
from multiprocessing.synchronize import Barrier as _MpBarrier
from pathlib import Path
from typing import Any

SPAWN_CONTEXT_NAME: str = "spawn"
"""强制使用的 multiprocessing context 名。"""

DEFAULT_JOIN_TIMEOUT_SECONDS: float = 30.0
"""单个 worker 默认 join 超时时间; 触发后会先 terminate 再 kill。"""

_TERMINATE_GRACE_SECONDS: float = 5.0
"""``terminate()`` 后等待进程退出的宽限时间。"""

_KILL_GRACE_SECONDS: float = 5.0
"""``kill()`` 后等待进程退出的最终宽限时间。"""

_RESULT_KIND_OK: str = "ok"
"""worker 正常返回时 Queue 内的标识符。"""

_RESULT_KIND_ERROR: str = "error"
"""worker 抛异常时 Queue 内的标识符。"""

_DATABASE_FILE_NAME: str = "host.db"
"""默认 SQLite 文件名。"""


@dataclass(frozen=True, slots=True)
class WorkerSpec:
    """单个子进程的描述。

    :param name: 进程名, 同时作为 Queue 内结果回传的 key, 必须在一组
        ``WorkerSpec`` 内唯一。
    :param target: 模块级可被 pickle 的 callable。其签名第一个参数固
        定为 :class:`WorkerContext`, 其余参数从 ``args`` 透传。
    :param args: 透传给 ``target`` 的位置参数 (在 ``WorkerContext``
        之后)。所有元素必须可 pickle (基础类型 / 数据类等)。
    """

    name: str
    target: Callable[..., None]
    args: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkerContext:
    """子进程入口收到的执行上下文。

    本结构是 worker 与主进程之间唯一的通信通道, 所有 IPC 都收敛于此:

    - ``result_queue``: worker 通过 :func:`report_success` /
      :func:`report_error` 把结果回传主进程; 主进程靠 ``name`` 查找。
    - ``barrier``: 可选同步屏障, 让若干 worker "同时" 进入 race 区段。
      未提供时为 ``None`` (例如纯并发追加场景, 不强制同步起跑)。
    - ``name``: 当前 worker 名, 用于结果消息 key。

    :param name: 当前 worker 名。
    :param result_queue: spawn-context Queue。
    :param barrier: spawn-context Barrier 或 ``None``。
    """

    name: str
    result_queue: "_MpQueue[tuple[str, str, Any]]"
    barrier: "_MpBarrier | None"


@dataclass(frozen=True, slots=True)
class WorkerOutcome:
    """单个 worker 的最终结果。

    :param name: ``WorkerSpec.name``。
    :param exitcode: 进程退出码; ``None`` 表示主进程在 join 中超时强杀。
    :param ok: ``True`` 表示 worker 正常调用了 :func:`report_success`。
    :param result: ``ok=True`` 时的 worker 返回值 (必须可 pickle); 否
        则为 ``None``。
    :param traceback_text: ``ok=False`` 时的 traceback 文本; 否则
        ``None``。
    """

    name: str
    exitcode: int | None
    ok: bool
    result: Any
    traceback_text: str | None


def temp_database_path(tmp_path: Path, *, name: str = _DATABASE_FILE_NAME) -> str:
    """生成测试专属 SQLite 文件路径。

    P8-S7 多进程必须使用真实文件路径, 不允许 ``:memory:``; 本函数对
    pytest ``tmp_path`` fixture 做最小封装, 不创建文件本身, 由
    :class:`HostStorage` 在 ``open()`` 时落库。

    :param tmp_path: pytest 提供的临时目录。
    :param name: SQLite 文件名, 同一测试可多次调用以隔离不同库。
    :returns: 子进程可访问的绝对路径字符串。
    :raises Exception: 不主动抛出异常。
    """

    return str(tmp_path / name)


def get_spawn_context() -> SpawnContext:
    """返回固定 ``spawn`` 模式的 multiprocessing context。

    :returns: spawn context 实例。
    :raises Exception: 不主动抛出异常。
    """

    ctx = _mp.get_context(SPAWN_CONTEXT_NAME)
    assert isinstance(ctx, SpawnContext)
    return ctx


def make_result_queue(
    ctx: SpawnContext,
) -> "_MpQueue[tuple[str, str, Any]]":
    """构造一个结果回传 Queue。

    :param ctx: spawn context, 必须由 :func:`get_spawn_context` 提供以
        保证跨进程序列化兼容。
    :returns: spawn-context Queue。
    :raises Exception: 不主动抛出异常。
    """

    return ctx.Queue()


def make_barrier(ctx: SpawnContext, *, parties: int) -> "_MpBarrier":
    """构造同步屏障, 用于让多个 worker "同时" 进入 race 区段。

    :param ctx: spawn context。
    :param parties: 屏障 parties 数量, 必须为正。
    :returns: spawn-context Barrier。
    :raises ValueError: ``parties`` 非正时抛出。
    """

    if parties <= 0:
        raise ValueError("parties must be positive")
    return ctx.Barrier(parties)


def report_success(context: WorkerContext, *, payload: Any) -> None:
    """worker 内部成功回报。

    payload 必须是可 pickle 的简单类型 (基础类型 / dataclass / dict 等)。
    禁止把 ``HostStorage`` / 文件句柄等不可序列化对象写入。

    :param context: 当前 worker 上下文。
    :param payload: 成功结果。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常 (Queue.put 失败由调用方负责)。
    """

    context.result_queue.put((context.name, _RESULT_KIND_OK, payload))


def report_error(context: WorkerContext, *, exc: BaseException) -> None:
    """worker 内部异常回报。

    把 traceback 文本而不是异常对象自身放进 Queue, 避免子进程内部异常
    类型在父进程不可重建时产生反序列化错误。

    :param context: 当前 worker 上下文。
    :param exc: 当前捕获到的异常。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    text = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    context.result_queue.put((context.name, _RESULT_KIND_ERROR, text))


def run_workers(
    specs: tuple[WorkerSpec, ...],
    *,
    barrier: "_MpBarrier | None" = None,
    timeout_seconds: float = DEFAULT_JOIN_TIMEOUT_SECONDS,
) -> tuple[WorkerOutcome, ...]:
    """启动一组 spawn-safe worker, 收集 typed 结果。

    流程:

    1. 用 spawn context 创建 result Queue 与各 worker Process;
    2. 全部 ``start()`` 后, 按顺序在 ``timeout_seconds`` 内 ``join``;
    3. 任意 worker 超时未退则 ``terminate()`` -> 等 ``_TERMINATE_GRACE_SECONDS``
       -> 仍存活则 ``kill()`` -> 等 ``_KILL_GRACE_SECONDS``, 最终抛
       ``RuntimeError``;
    4. 从 Queue 收集每个 worker 的结果消息, 按 ``name`` 配对到
       :class:`WorkerOutcome`; 没有消息的 worker 标记为 ``ok=False`` +
       ``traceback_text=None``。

    :param specs: 待启动的 worker 描述, ``name`` 必须在组内唯一。
    :param barrier: 可选 :class:`_MpBarrier`, 若提供则与每个 worker 共享
        同一 barrier; 不提供时 :class:`WorkerContext.barrier` 为 ``None``。
    :param timeout_seconds: 单个 worker join 超时时间; 超时进入强杀路径。
    :returns: 与 ``specs`` 顺序对齐的 :class:`WorkerOutcome` 元组。
    :raises ValueError: ``specs`` 为空或 ``name`` 出现重复。
    :raises RuntimeError: 任意 worker 超时未退。
    """

    if not specs:
        raise ValueError("specs must not be empty")
    names = [spec.name for spec in specs]
    if len(set(names)) != len(names):
        raise ValueError("worker names must be unique within a run")

    ctx = get_spawn_context()
    queue = make_result_queue(ctx)
    processes: list[BaseProcess] = []
    for spec in specs:
        worker_context = WorkerContext(
            name=spec.name,
            result_queue=queue,
            barrier=barrier,
        )
        process = ctx.Process(
            target=spec.target,
            args=(worker_context, *spec.args),
            name=spec.name,
        )
        processes.append(process)

    for process in processes:
        process.start()

    deadline = time.monotonic() + timeout_seconds
    timed_out_names: list[str] = []
    for process in processes:
        remaining = max(0.0, deadline - time.monotonic())
        process.join(timeout=remaining)
        if process.is_alive():
            timed_out_names.append(process.name)
            process.terminate()
            process.join(timeout=_TERMINATE_GRACE_SECONDS)
            if process.is_alive():
                process.kill()
                process.join(timeout=_KILL_GRACE_SECONDS)

    # 在 join 全部结束之后再消费 Queue, 避免 Queue 内部 buffer flush 与
    # 进程退出之间的竞态。
    pending: dict[str, tuple[str, Any]] = {}
    while True:
        try:
            name, kind, payload = queue.get_nowait()
        except Exception:  # noqa: BLE001 — Queue.Empty 在不同 Python 版本下类型不一致, 用宽泛 catch 守住边界。
            break
        pending[name] = (kind, payload)

    outcomes: list[WorkerOutcome] = []
    for spec, process in zip(specs, processes, strict=True):
        record = pending.get(spec.name)
        if record is None:
            outcomes.append(
                WorkerOutcome(
                    name=spec.name,
                    exitcode=process.exitcode,
                    ok=False,
                    result=None,
                    traceback_text=None,
                )
            )
            continue
        kind, payload = record
        if kind == _RESULT_KIND_OK:
            outcomes.append(
                WorkerOutcome(
                    name=spec.name,
                    exitcode=process.exitcode,
                    ok=True,
                    result=payload,
                    traceback_text=None,
                )
            )
        else:
            outcomes.append(
                WorkerOutcome(
                    name=spec.name,
                    exitcode=process.exitcode,
                    ok=False,
                    result=None,
                    traceback_text=str(payload),
                )
            )

    if timed_out_names:
        raise RuntimeError(
            "multiprocess workers timed out: "
            + ", ".join(timed_out_names)
        )
    return tuple(outcomes)


def assert_clean_exit(outcomes: tuple[WorkerOutcome, ...]) -> None:
    """断言全部 worker 退出码为 0 且没有未回报的异常。

    本 helper 把"worker 全部 OK"这一最常见的断言收敛在一处, 避免在每个
    测试里复述同样的 ``assert outcome.exitcode == 0`` + traceback 透传
    逻辑。仅当全部 worker ``ok=True`` 且 ``exitcode=0`` 时返回, 否则抛
    :class:`AssertionError`, 并把首个失败 worker 的 traceback 文本作为
    错误消息以便诊断。

    :param outcomes: :func:`run_workers` 返回的元组。
    :returns: 无返回值。
    :raises AssertionError: 任一 worker 异常或退出码非 0。
    """

    for outcome in outcomes:
        assert outcome.exitcode == 0, (
            f"worker {outcome.name} exited with {outcome.exitcode}; "
            f"traceback={outcome.traceback_text}"
        )
        assert outcome.ok, (
            f"worker {outcome.name} reported failure; "
            f"traceback={outcome.traceback_text}"
        )


__all__ = [
    "DEFAULT_JOIN_TIMEOUT_SECONDS",
    "SPAWN_CONTEXT_NAME",
    "WorkerContext",
    "WorkerOutcome",
    "WorkerSpec",
    "assert_clean_exit",
    "get_spawn_context",
    "make_barrier",
    "make_result_queue",
    "report_error",
    "report_success",
    "run_workers",
    "temp_database_path",
]
