"""Host public opener。

本模块定义普通 Service 使用的 ``open_host(options)`` 入口。Slice 1 只冻结
public contract surface，不装配 durable store、scheduler、fanout、memory catch-up
或 ToolRuntime；生产 runtime 接线由后续 slice 完成。
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from types import TracebackType

from dayu.host.api import Host, OpenHostOptions


class _OpenHostContextManager(AbstractAsyncContextManager[Host]):
    """Slice 1 的 public opener context manager 骨架。

    :param options: Host public opener 构造期选项。
    """

    _options: OpenHostOptions

    def __init__(self, options: OpenHostOptions) -> None:
        """保存已校验的 opener options。

        :param options: Host public opener 构造期选项。
        :returns: 无返回值。
        :raises TypeError: ``options`` 不是 ``OpenHostOptions`` 时抛出。
        """

        if not isinstance(options, OpenHostOptions):
            raise TypeError("open_host options must be OpenHostOptions")
        self._options = options

    async def __aenter__(self) -> Host:
        """进入 Host opener runtime。

        :returns: public async Host handle。
        :raises NotImplementedError: Slice 1 尚未实现生产 runtime 接线时抛出。
        """

        raise NotImplementedError(
            "open_host runtime composition is owned by a later P10.5 slice"
        )

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """退出 Host opener runtime。

        :param exc_type: context body 抛出的异常类型；无异常时为 ``None``。
        :param exc_value: context body 抛出的异常；无异常时为 ``None``。
        :param traceback: context body 异常 traceback；无异常时为 ``None``。
        :returns: ``None`` 表示不吞掉异常。
        :raises RuntimeError: Slice 1 骨架不会在退出阶段抛出。
        """

        return None


def open_host(options: OpenHostOptions) -> AbstractAsyncContextManager[Host]:
    """打开普通本地多轮 Host public handle。

    Slice 1 仅提供可导入、可类型检查的 async context manager 入口，并在进入
    runtime body 前校验 ``options`` 是冻结的 public typed contract。后续 slice
    会在同一入口下装配 durable store、scheduler、live fanout、memory catch-up
    与 compactor wiring。

    :param options: Host public opener 构造期选项。
    :returns: public async Host handle context manager。
    :raises TypeError: ``options`` 不是 ``OpenHostOptions`` 时抛出。
    :raises NotImplementedError: 进入 context 时 Slice 1 尚未实现生产 runtime
        接线则抛出。
    """

    return _OpenHostContextManager(options)


__all__ = ["open_host"]
