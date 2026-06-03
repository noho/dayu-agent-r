"""Runner 请求身份契约测试。"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.runner_identity import (
    RunnerRequestIdentity,
    build_runner_request_identity,
)

_CLIENT_CORRELATION_LENGTH: int = 69
_CLIENT_CORRELATION_PREFIX: str = "dayu-"


def test_runner_request_identity_builds_stable_lowercase_digest() -> None:
    """请求身份构造器必须生成稳定的 lowercase SHA-256 关联 id。"""

    identity = _identity()
    same_identity = _identity()

    assert identity.client_correlation_id == same_identity.client_correlation_id
    assert len(identity.client_correlation_id) == _CLIENT_CORRELATION_LENGTH
    assert identity.client_correlation_id.startswith(
        _CLIENT_CORRELATION_PREFIX
    )
    digest = identity.client_correlation_id.removeprefix(
        _CLIENT_CORRELATION_PREFIX
    )
    assert digest == digest.lower()
    assert all(("0" <= char <= "9") or ("a" <= char <= "f") for char in digest)
    identity.client_correlation_id.encode("ascii")


def test_runner_request_identity_changes_across_iteration_and_call() -> None:
    """不同 iteration 或 logical Runner call 必须派生不同关联 id。"""

    base = _identity()
    next_iteration = _identity(iteration_id="run_identity_iteration_2", iteration_index=1)
    next_call = _identity(runner_call_index=2)

    assert base.client_correlation_id != next_iteration.client_correlation_id
    assert base.client_correlation_id != next_call.client_correlation_id


def test_runner_request_identity_accepts_direct_engine_without_attempt() -> None:
    """直接 Engine 路径允许 attempt / execution 同时为 None。"""

    identity = _identity(attempt_id=None, execution_id=None)

    assert identity.attempt_id is None
    assert identity.execution_id is None
    assert identity.runner_call_index == 1
    assert identity.iteration_index == 0


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("run_id", ""),
        ("attempt_id", " "),
        ("execution_id", ""),
        ("iteration_id", " "),
    ),
)
def test_runner_request_identity_rejects_empty_text_fields(
    field_name: str,
    invalid_value: str,
) -> None:
    """请求身份必须拒绝空文本字段。

    :param field_name: 期望命中的字段名。
    :param invalid_value: 覆盖到构造器的非法字段值。
    :returns: 无返回值。
    :raises AssertionError: 校验未按预期失败时由 pytest 抛出。
    """

    with pytest.raises(ValueError, match=field_name):
        if field_name == "run_id":
            _identity(run_id=invalid_value)
        elif field_name == "attempt_id":
            _identity(attempt_id=invalid_value)
        elif field_name == "execution_id":
            _identity(execution_id=invalid_value)
        elif field_name == "iteration_id":
            _identity(iteration_id=invalid_value)
        else:
            raise AssertionError(f"unexpected field name: {field_name}")


@pytest.mark.parametrize("iteration_index", (-1, -2))
def test_runner_request_identity_rejects_negative_iteration_index(
    iteration_index: int,
) -> None:
    """请求身份必须拒绝负数 iteration_index。"""

    with pytest.raises(ValueError, match="iteration_index"):
        _identity(iteration_index=iteration_index)


@pytest.mark.parametrize("runner_call_index", (0, -1))
def test_runner_request_identity_rejects_non_positive_runner_call_index(
    runner_call_index: int,
) -> None:
    """请求身份必须拒绝非正 runner_call_index。"""

    with pytest.raises(ValueError, match="runner_call_index"):
        _identity(runner_call_index=runner_call_index)


def test_runner_request_identity_requires_attempt_execution_pair() -> None:
    """请求身份必须要求 attempt_id / execution_id 同时出现或同时缺失。"""

    with pytest.raises(ValueError, match="attempt_id"):
        _identity(attempt_id="attempt", execution_id=None)
    with pytest.raises(ValueError, match="attempt_id"):
        _identity(attempt_id=None, execution_id="execution")


def test_runner_request_identity_rejects_non_canonical_client_id() -> None:
    """直接构造请求身份时必须拒绝与规范元组不匹配的关联 id。"""

    identity = _identity()
    with pytest.raises(ValueError, match="canonical"):
        RunnerRequestIdentity(
            run_id=identity.run_id,
            attempt_id=identity.attempt_id,
            execution_id=identity.execution_id,
            iteration_id=identity.iteration_id,
            iteration_index=identity.iteration_index,
            runner_call_index=identity.runner_call_index + 1,
            client_correlation_id=identity.client_correlation_id,
        )


def _identity(
    *,
    run_id: str = "run_identity",
    attempt_id: str | None = "attempt_identity",
    execution_id: str | None = "execution_identity",
    iteration_id: str = "run_identity_iteration_1",
    iteration_index: int = 0,
    runner_call_index: int = 1,
) -> RunnerRequestIdentity:
    """构造测试用 RunnerRequestIdentity。

    :param run_id: Engine run id。
    :param attempt_id: Host attempt id 或 ``None``。
    :param execution_id: Host execution id 或 ``None``。
    :param iteration_id: Engine iteration id。
    :param iteration_index: Engine iteration 序号。
    :param runner_call_index: 逻辑 Runner 调用序号。
    :returns: RunnerRequestIdentity。
    :raises ValueError: 输入非法时由构造器抛出。
    """

    return build_runner_request_identity(
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        iteration_id=iteration_id,
        iteration_index=iteration_index,
        runner_call_index=runner_call_index,
    )
