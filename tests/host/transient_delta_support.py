"""Host 瞬态发布端口的强类型测试 fixture。"""

from __future__ import annotations

from dayu.host.transient_delta import ValidatedTransientDeltaCandidate


class NoopTransientDeltaPublisher:
    """显式忽略候选、用于不关注 live fanout 的既有 owner tests。"""

    def publish(self, candidate: ValidatedTransientDeltaCandidate) -> None:
        """接受一个已验证候选但不记录。

        :param candidate: 已通过 Host ingest 校验的候选。
        :returns: ``None``。
        :raises Exception: 本实现不抛出异常。
        """


class RecordingTransientDeltaPublisher:
    """按调用顺序记录已验证候选的测试发布端口。"""

    def __init__(self) -> None:
        """创建空记录器。

        :returns: 无返回值。
        :raises Exception: 本构造函数不抛出异常。
        """

        self.candidates: list[ValidatedTransientDeltaCandidate] = []

    def publish(self, candidate: ValidatedTransientDeltaCandidate) -> None:
        """记录一次发布调用。

        :param candidate: 已通过 Host ingest 校验的候选。
        :returns: ``None``。
        :raises Exception: 本实现不抛出异常。
        """

        self.candidates.append(candidate)


class FailingTransientDeltaPublisher:
    """模拟发布端口意外的测试实现。"""

    def publish(self, candidate: ValidatedTransientDeltaCandidate) -> None:
        """对每次发布抛出带敏感哨兵的异常。

        :param candidate: 已通过 Host ingest 校验的候选。
        :returns: 本实现始终抛出，不返回。
        :raises RuntimeError: 固定抛出，用于验证 ingestor 异常隔离与脱敏。
        """

        raise RuntimeError("sensitive-delta-publisher-message")


NOOP_TRANSIENT_DELTA_PUBLISHER = NoopTransientDeltaPublisher()
"""既有非 transient owner tests 显式注入的无状态发布端口。"""


__all__ = [
    "NOOP_TRANSIENT_DELTA_PUBLISHER",
    "FailingTransientDeltaPublisher",
    "NoopTransientDeltaPublisher",
    "RecordingTransientDeltaPublisher",
]
