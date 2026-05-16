"""Host 等待适配器 registry 的层内契约。

本模块只定义 Host 内部如何为 ``ToolAwaitingOutcome`` 选择等待适配器
binding。它不实现 poller、callback endpoint 或外部系统协议，也不让
Engine 选择 adapter。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.host.api import WaitAdapterKey
from dayu.host.durable.state import ExternalJobRef, WaitResumePolicy


class WaitExternalJobRefSource(StrEnum):
    """外部 job id 的 Host 派生来源。"""

    NONE = "none"
    RESUME_TOKEN = "resume_token"


@dataclass(frozen=True, slots=True)
class WaitAdapterBinding:
    """单个工具等待适配器 binding。

    :param tool_name: 适用工具名。
    :param await_kind: 适用等待类型。
    :param adapter_key: Host registry 中的稳定 adapter key。
    :param resume_policy: 等待恢复策略。
    :param external_job_ref_source: 外部 job id 的派生来源。
    """

    tool_name: str
    await_kind: ToolAwaitKind
    adapter_key: WaitAdapterKey
    resume_policy: WaitResumePolicy
    external_job_ref_source: WaitExternalJobRefSource

    def __post_init__(self) -> None:
        """校验 binding 字段。

        :returns: ``None``。
        :raises ValueError: 工具名为空或 enum 类型非法时抛出。
        """

        if self.tool_name.strip() == "":
            raise ValueError("tool_name must be non-empty")
        if not isinstance(self.await_kind, ToolAwaitKind):
            raise ValueError("await_kind must be ToolAwaitKind")
        if not isinstance(self.adapter_key, WaitAdapterKey):
            raise ValueError("adapter_key must be WaitAdapterKey")
        if not isinstance(self.resume_policy, WaitResumePolicy):
            raise ValueError("resume_policy must be WaitResumePolicy")
        if not isinstance(self.external_job_ref_source, WaitExternalJobRefSource):
            raise ValueError(
                "external_job_ref_source must be WaitExternalJobRefSource"
            )

    def external_job_ref(self, await_spec: ToolAwaitSpec) -> ExternalJobRef | None:
        """根据 Host binding 从等待规约派生外部 job 引用。

        :param await_spec: 工具等待规约。
        :returns: 外部 job 引用；当前 binding 不需要时为 ``None``。
        """

        if self.external_job_ref_source is WaitExternalJobRefSource.NONE:
            return None
        if self.external_job_ref_source is WaitExternalJobRefSource.RESUME_TOKEN:
            return ExternalJobRef(
                adapter_key=self.adapter_key,
                external_job_id=await_spec.resume_token,
            )
        raise ValueError("unsupported external job ref source")


class WaitAdapterRegistry:
    """Host 等待适配器 registry。

    registry 只按 Host 配置过的 tool name 与 await kind 选择 binding，不读取
    Engine event，也不反序列化业务 payload。
    """

    def __init__(self, bindings: tuple[WaitAdapterBinding, ...]) -> None:
        """初始化 registry。

        :param bindings: 可用 binding 列表。
        :returns: ``None``。
        :raises ValueError: 出现重复 binding key 时抛出。
        """

        self._bindings: dict[tuple[str, ToolAwaitKind], WaitAdapterBinding] = {}
        for binding in bindings:
            key = (binding.tool_name, binding.await_kind)
            if key in self._bindings:
                raise ValueError("duplicate wait adapter binding")
            self._bindings[key] = binding

    def resolve_binding(
        self, *, tool_name: str, await_kind: ToolAwaitKind
    ) -> WaitAdapterBinding | None:
        """解析工具等待 binding。

        :param tool_name: 工具名。
        :param await_kind: 等待类型。
        :returns: 匹配 binding；未配置时为 ``None``。
        :raises ValueError: 工具名为空或等待类型非法时抛出。
        """

        if tool_name.strip() == "":
            raise ValueError("tool_name must be non-empty")
        if not isinstance(await_kind, ToolAwaitKind):
            raise ValueError("await_kind must be ToolAwaitKind")
        return self._bindings.get((tool_name, await_kind))


__all__ = [
    "WaitAdapterBinding",
    "WaitAdapterRegistry",
    "WaitExternalJobRefSource",
]
