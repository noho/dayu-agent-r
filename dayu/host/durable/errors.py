"""Host durable foundation 结构化错误类型。

本模块只定义 Host durable store 内部错误分类。错误类型用于区分配置、
schema、SQLite 事务、digest、idempotency、EventLog identity、payload、
artifact 与 host instance liveness 失败；具体业务行为由后续 durable 子模块
实现。
"""

from __future__ import annotations


class HostDurableError(Exception):
    """Host durable foundation 基础异常。

    :param message: 面向诊断的中文错误消息。
    :raises TypeError: ``Exception`` 初始化失败时由父类抛出。
    """

    def __init__(self, message: str) -> None:
        """初始化 Host durable 基础异常。

        :param message: 面向诊断的中文错误消息。
        :returns: ``None``。
        :raises TypeError: ``Exception`` 初始化失败时由父类抛出。
        """

        super().__init__(message)


class HostDurableConfigError(HostDurableError):
    """Host durable store 配置无效。"""


class HostSchemaMismatchError(HostDurableError):
    """Host durable store schema version 与当前代码不匹配。"""


class HostTransactionBusyError(HostDurableError):
    """SQLite write transaction 遇到 busy 或 locked。"""


class HostTransactionRetryExhaustedError(HostDurableError):
    """SQLite write transaction busy / locked 重试耗尽。

    :param message: 面向诊断的中文错误消息。
    :param attempts: 已执行的 transaction 尝试次数。
    :raises TypeError: ``Exception`` 初始化失败时由父类抛出。
    """

    attempts: int

    def __init__(self, message: str, *, attempts: int) -> None:
        """初始化重试耗尽错误。

        :param message: 面向诊断的中文错误消息。
        :param attempts: 已执行的 transaction 尝试次数。
        :returns: ``None``。
        :raises TypeError: ``Exception`` 初始化失败时由父类抛出。
        """

        self.attempts = attempts
        super().__init__(message)


class HostUniqueConstraintError(HostDurableError):
    """SQLite unique / primary-key constraint 失败。"""


class HostForeignKeyError(HostDurableError):
    """SQLite foreign-key constraint 失败。"""


class HostDigestMismatchError(HostDurableError):
    """digest 校验失败。"""


class HostIdempotencyConflictError(HostDurableError):
    """同一 idempotency key 对应了不同语义输入。"""


class HostEventIdentityConflictError(HostDurableError):
    """同一 EventLog ``event_id`` 对应了不同事件事实。"""


class HostInstanceIdentityConflictError(HostDurableError):
    """host instance identity 与既有 durable row 冲突。"""


class HostInstanceLifecycleConflictError(HostDurableError):
    """host instance lifecycle 状态转移与既有 durable row 冲突。"""


class HostInstanceNotRegisteredError(HostDurableError):
    """当前 host instance 尚未注册。"""


class HostPayloadReferenceError(HostDurableError):
    """payload descriptor 或 payload 引用无效。"""


class HostArtifactWriteError(HostDurableError):
    """本地 artifact 写入、校验或发布失败。"""


class HostAfterCommitError(HostDurableError):
    """after-commit callback 在 durable commit 完成后失败。

    :param message: 面向诊断的中文错误消息。
    :param callback_index: 失败 callback 在本次回调元组中的位置。
    :raises TypeError: ``Exception`` 初始化失败时由父类抛出。
    """

    callback_index: int

    def __init__(self, message: str, *, callback_index: int) -> None:
        """初始化 after-commit callback 错误。

        :param message: 面向诊断的中文错误消息。
        :param callback_index: 失败 callback 在本次回调元组中的位置。
        :returns: ``None``。
        :raises TypeError: ``Exception`` 初始化失败时由父类抛出。
        """

        self.callback_index = callback_index
        super().__init__(message)
