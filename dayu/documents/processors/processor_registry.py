"""处理器注册表实现。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .source import Source

from .base import DocumentProcessor


@dataclass(frozen=True)
class ProcessorRegistration:
    """处理器注册记录。"""

    name: str
    processor_cls: type[DocumentProcessor]
    priority: int


class ProcessorRegistry:
    """处理器注册表。

    按 supports 选择处理器，避免在 Pipeline 层硬编码 if/else。
    """

    def __init__(self) -> None:
        """初始化注册表。

        Args:
            无。

        Returns:
            None。

        Raises:
            RuntimeError: 初始化失败时抛出。
        """

        self._items: list[ProcessorRegistration] = []

    def register(
        self,
        processor_cls: type[DocumentProcessor],
        *,
        name: Optional[str] = None,
        priority: int = 0,
        overwrite: bool = False,
    ) -> None:
        """注册处理器。

        Args:
            processor_cls: 处理器类。
            name: 注册名（默认使用类名）。
            priority: 优先级，越大越优先。
            overwrite: 是否覆盖同名注册。

        Returns:
            None。

        Raises:
            ValueError: 注册名冲突且不允许覆盖时抛出。
        """

        reg_name = name or processor_cls.__name__
        existing = self._find(reg_name)
        if existing and not overwrite:
            raise ValueError(f"处理器已注册: {reg_name}")

        if existing:
            self._items = [item for item in self._items if item.name != reg_name]

        self._items.append(
            ProcessorRegistration(
                name=reg_name,
                processor_cls=processor_cls,
                priority=priority,
            )
        )
        self._items.sort(key=lambda item: item.priority, reverse=True)

    def unregister(self, name: str) -> None:
        """移除处理器注册。

        Args:
            name: 注册名。

        Returns:
            None。

        Raises:
            KeyError: 注册名不存在时抛出。
        """

        if not self._find(name):
            raise KeyError(f"处理器未注册: {name}")
        self._items = [item for item in self._items if item.name != name]

    def list_processors(self) -> list[dict[str, object]]:
        """列出已注册处理器。

        Args:
            无。

        Returns:
            注册处理器列表。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        return [
            {
                "name": item.name,
                "class": item.processor_cls.__name__,
                "priority": item.priority,
            }
            for item in self._items
        ]

    def resolve(
        self,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> Optional[type[DocumentProcessor]]:
        """选择合适的处理器类。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            处理器类或 None。

        Raises:
            RuntimeError: 选择失败时抛出。
        """

        candidates = self.resolve_candidates(
            source,
            form_type=form_type,
            media_type=media_type,
        )
        if not candidates:
            return None
        return candidates[0]

    def resolve_candidates(
        self,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> list[type[DocumentProcessor]]:
        """按优先级返回全部可用处理器类。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            按优先级降序排列的处理器类列表。

        Raises:
            RuntimeError: 选择失败时抛出。
        """

        candidates: list[type[DocumentProcessor]] = []
        # 复杂逻辑说明：`resolve_candidates` 需要遍历全部注册项并逐一判定 supports。
        for item in self._items:
            try:
                if item.processor_cls.supports(
                    source,
                    form_type=form_type,
                    media_type=media_type,
                ):
                    candidates.append(item.processor_cls)
            except OSError:
                continue
        return candidates

    def create(
        self,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> DocumentProcessor:
        """创建处理器实例。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            处理器实例。

        Raises:
            ValueError: 没有可用处理器时抛出。
        """

        processor_cls = self.resolve(
            source,
            form_type=form_type,
            media_type=media_type,
        )
        if not processor_cls:
            raise ValueError(f"未找到可用处理器: {source}")
        return processor_cls(
            source=source,
            form_type=form_type,
            media_type=media_type,
        )

    def create_with_fallback(
        self,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
        on_fallback: Optional[Callable[[type[DocumentProcessor], Exception, int, int], None]] = None,
    ) -> DocumentProcessor:
        """创建处理器实例，实例化失败时回退到下一候选。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。
            on_fallback: 候选创建失败且存在下一候选时的回调。

        Returns:
            成功创建的处理器实例。

        Raises:
            ValueError: 没有可用处理器时抛出。
            RuntimeError: 候选处理器全部创建失败时抛出。
        """

        candidates = self.resolve_candidates(
            source,
            form_type=form_type,
            media_type=media_type,
        )
        if not candidates:
            raise ValueError(f"未找到可用处理器: {source}")

        errors: list[str] = []
        total_candidates = len(candidates)
        # 复杂逻辑说明：候选按优先级有序，创建失败时继续尝试后续候选以实现统一回退策略。
        for index, processor_cls in enumerate(candidates):
            try:
                return processor_cls(
                    source=source,
                    form_type=form_type,
                    media_type=media_type,
                )
            except Exception as exc:
                errors.append(f"{processor_cls.__name__}: {exc}")
                if on_fallback is not None and index + 1 < total_candidates:
                    on_fallback(processor_cls, exc, index + 1, total_candidates)
                continue

        error_text = "; ".join(errors)
        raise RuntimeError(f"处理器创建失败且无可用回退: source={source} errors={error_text}")

    def _find(self, name: str) -> Optional[ProcessorRegistration]:
        """查找注册记录。

        Args:
            name: 注册名。

        Returns:
            注册记录或 None。

        Raises:
            RuntimeError: 查找失败时抛出。
        """

        for item in self._items:
            if item.name == name:
                return item
        return None
