"""Runner 请求身份契约。

本模块定义 Engine 在每次逻辑 Runner 调用边界传入的强类型请求身份。
该身份只用于本地诊断关联与 provider adapter 的显式 per-call 映射，
不表达 Host 生命周期治理，也不伪装为 provider end-user 字段。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

_CLIENT_CORRELATION_PREFIX: str = "dayu-"
_SHA256_HEX_LENGTH: int = 64
_CLIENT_CORRELATION_LENGTH: int = (
    len(_CLIENT_CORRELATION_PREFIX) + _SHA256_HEX_LENGTH
)
_STRING_PART_PREFIX: str = "s"
_INTEGER_PART_PREFIX: str = "i"
_NONE_PART_TOKEN: str = "n"
_PART_SEPARATOR: str = "|"
_PART_FIELD_SEPARATOR: str = ":"
_RUNNER_REQUEST_IDENTITY_OWNER: str = "RunnerRequestIdentity"
_SUCCESSFUL_RUNNER_RESPONSE_IDENTITY_OWNER: str = (
    "SuccessfulRunnerResponseIdentity"
)

_CanonicalIdentityParts = tuple[str, str | None, str | None, str, int, int]


class ProviderRequestIdAvailability(StrEnum):
    """成功响应中的 provider request id 可用性。"""

    PRESENT = "present"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RunnerRequestIdentity:
    """单次逻辑 Runner 调用的请求身份。

    :param run_id: Engine run id。
    :param attempt_id: Host attempt id；非 Host attempt 路径为 ``None``。
    :param execution_id: Host execution id；非 Host attempt 路径为 ``None``。
    :param iteration_id: 当前 Engine iteration id。
    :param iteration_index: 当前 Engine iteration 序号，从 0 起。
    :param runner_call_index: 当前 run 内逻辑 Runner 调用序号，从 1 起。
    :param client_correlation_id: ``dayu-`` 加完整 64 位 lowercase SHA-256
        hex 的客户端关联 id。
    """

    run_id: str
    attempt_id: str | None
    execution_id: str | None
    iteration_id: str
    iteration_index: int
    runner_call_index: int
    client_correlation_id: str

    def __post_init__(self) -> None:
        """校验请求身份字段与派生关联 id。

        :returns: 无返回值。
        :raises ValueError: 文本字段为空、序号越界、attempt/execution 未成对
            出现、或 ``client_correlation_id`` 与规范 SHA-256 派生值不一致
            时抛出。
        """

        _validate_identity_inputs(
            run_id=self.run_id,
            attempt_id=self.attempt_id,
            execution_id=self.execution_id,
            iteration_id=self.iteration_id,
            iteration_index=self.iteration_index,
            runner_call_index=self.runner_call_index,
        )
        _validate_client_correlation_id(self.client_correlation_id)
        expected = _build_client_correlation_id(
            _canonical_identity_parts(
                run_id=self.run_id,
                attempt_id=self.attempt_id,
                execution_id=self.execution_id,
                iteration_id=self.iteration_id,
                iteration_index=self.iteration_index,
                runner_call_index=self.runner_call_index,
            )
        )
        if self.client_correlation_id != expected:
            raise ValueError(
                "RunnerRequestIdentity.client_correlation_id must match "
                "the canonical identity tuple"
            )


@dataclass(frozen=True, slots=True)
class SuccessfulRunnerResponseIdentity:
    """实际终结成功 Runner 调用的安全响应身份。

    :param effective_provider: 实际调用的 provider 标识。
    :param effective_model: 实际调用的 provider model 标识。
    :param runner_request_identity: 同一次逻辑 Runner 调用的请求身份。
    :param provider_request_id_availability: provider request id 是否可用。
    :param provider_request_id: provider 返回的 request id；不可用时为
        ``None``。
    """

    effective_provider: str
    effective_model: str
    runner_request_identity: RunnerRequestIdentity
    provider_request_id_availability: ProviderRequestIdAvailability
    provider_request_id: str | None

    def __post_init__(self) -> None:
        """校验成功响应身份的严格字段不变量。

        :returns: 无返回值。
        :raises TypeError: 请求身份或 availability 不是对应强类型时抛出。
        :raises ValueError: provider/model 为空，或 availability 与 provider
            request id 未严格成对时抛出。
        """

        _validate_non_empty_text(
            _SUCCESSFUL_RUNNER_RESPONSE_IDENTITY_OWNER,
            "effective_provider",
            self.effective_provider,
        )
        _validate_non_empty_text(
            _SUCCESSFUL_RUNNER_RESPONSE_IDENTITY_OWNER,
            "effective_model",
            self.effective_model,
        )
        if not isinstance(self.runner_request_identity, RunnerRequestIdentity):
            raise TypeError(
                "SuccessfulRunnerResponseIdentity.runner_request_identity "
                "must be RunnerRequestIdentity"
            )
        if not isinstance(
            self.provider_request_id_availability,
            ProviderRequestIdAvailability,
        ):
            raise TypeError(
                "SuccessfulRunnerResponseIdentity."
                "provider_request_id_availability must be "
                "ProviderRequestIdAvailability"
            )
        if (
            self.provider_request_id_availability
            is ProviderRequestIdAvailability.PRESENT
        ):
            if self.provider_request_id is None:
                raise ValueError(
                    "SuccessfulRunnerResponseIdentity.provider_request_id "
                    "must be present when availability is present"
                )
            _validate_non_empty_text(
                _SUCCESSFUL_RUNNER_RESPONSE_IDENTITY_OWNER,
                "provider_request_id",
                self.provider_request_id,
            )
            return
        if self.provider_request_id is not None:
            raise ValueError(
                "SuccessfulRunnerResponseIdentity.provider_request_id must be "
                "None when availability is unavailable"
            )


def build_runner_request_identity(
    *,
    run_id: str,
    attempt_id: str | None,
    execution_id: str | None,
    iteration_id: str,
    iteration_index: int,
    runner_call_index: int,
) -> RunnerRequestIdentity:
    """构造单次逻辑 Runner 调用的请求身份。

    :param run_id: Engine run id。
    :param attempt_id: Host attempt id；非 Host attempt 路径为 ``None``。
    :param execution_id: Host execution id；非 Host attempt 路径为 ``None``。
    :param iteration_id: 当前 Engine iteration id。
    :param iteration_index: 当前 Engine iteration 序号，从 0 起。
    :param runner_call_index: 当前 run 内逻辑 Runner 调用序号，从 1 起。
    :returns: 已校验且带规范 ``client_correlation_id`` 的请求身份。
    :raises ValueError: 输入字段不满足请求身份不变量时抛出。
    """

    _validate_identity_inputs(
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        iteration_id=iteration_id,
        iteration_index=iteration_index,
        runner_call_index=runner_call_index,
    )
    parts = _canonical_identity_parts(
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        iteration_id=iteration_id,
        iteration_index=iteration_index,
        runner_call_index=runner_call_index,
    )
    return RunnerRequestIdentity(
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        iteration_id=iteration_id,
        iteration_index=iteration_index,
        runner_call_index=runner_call_index,
        client_correlation_id=_build_client_correlation_id(parts),
    )


def _validate_identity_inputs(
    *,
    run_id: str,
    attempt_id: str | None,
    execution_id: str | None,
    iteration_id: str,
    iteration_index: int,
    runner_call_index: int,
) -> None:
    """校验请求身份构造输入。

    :param run_id: Engine run id。
    :param attempt_id: Host attempt id 或 ``None``。
    :param execution_id: Host execution id 或 ``None``。
    :param iteration_id: 当前 Engine iteration id。
    :param iteration_index: 当前 Engine iteration 序号。
    :param runner_call_index: 当前 run 内逻辑 Runner 调用序号。
    :returns: 无返回值。
    :raises ValueError: 任一输入违反请求身份不变量时抛出。
    """

    _validate_non_empty_text(
        _RUNNER_REQUEST_IDENTITY_OWNER,
        "run_id",
        run_id,
    )
    _validate_optional_non_empty_text(
        _RUNNER_REQUEST_IDENTITY_OWNER,
        "attempt_id",
        attempt_id,
    )
    _validate_optional_non_empty_text(
        _RUNNER_REQUEST_IDENTITY_OWNER,
        "execution_id",
        execution_id,
    )
    _validate_non_empty_text(
        _RUNNER_REQUEST_IDENTITY_OWNER,
        "iteration_id",
        iteration_id,
    )
    if iteration_index < 0:
        raise ValueError("RunnerRequestIdentity.iteration_index must be >= 0")
    if runner_call_index < 1:
        raise ValueError("RunnerRequestIdentity.runner_call_index must be >= 1")
    if (attempt_id is None) != (execution_id is None):
        raise ValueError(
            "RunnerRequestIdentity.attempt_id and execution_id must both be "
            "None or both be non-None"
        )


def _validate_non_empty_text(
    owner_name: str,
    field_name: str,
    value: str,
) -> None:
    """校验必填文本字段非空。

    :param owner_name: 字段所属 contract 名称。
    :param field_name: 字段名，用于错误消息。
    :param value: 需要校验的文本值。
    :returns: 无返回值。
    :raises ValueError: 文本为空或仅包含空白时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{owner_name}.{field_name} must be non-empty")


def _validate_optional_non_empty_text(
    owner_name: str,
    field_name: str,
    value: str | None,
) -> None:
    """校验可选文本字段在出现时非空。

    :param owner_name: 字段所属 contract 名称。
    :param field_name: 字段名，用于错误消息。
    :param value: 需要校验的文本值或 ``None``。
    :returns: 无返回值。
    :raises ValueError: 文本出现但为空或仅包含空白时抛出。
    """

    if value is None:
        return
    _validate_non_empty_text(owner_name, field_name, value)


def _canonical_identity_parts(
    *,
    run_id: str,
    attempt_id: str | None,
    execution_id: str | None,
    iteration_id: str,
    iteration_index: int,
    runner_call_index: int,
) -> _CanonicalIdentityParts:
    """返回用于派生关联 id 的规范身份元组。

    :param run_id: Engine run id。
    :param attempt_id: Host attempt id 或 ``None``。
    :param execution_id: Host execution id 或 ``None``。
    :param iteration_id: 当前 Engine iteration id。
    :param iteration_index: 当前 Engine iteration 序号。
    :param runner_call_index: 当前 run 内逻辑 Runner 调用序号。
    :returns: 按契约顺序排列的规范身份元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        run_id,
        attempt_id,
        execution_id,
        iteration_id,
        iteration_index,
        runner_call_index,
    )


def _build_client_correlation_id(parts: _CanonicalIdentityParts) -> str:
    """根据规范身份元组派生客户端关联 id。

    :param parts: 规范身份元组。
    :returns: ``dayu-`` 加 64 位 lowercase SHA-256 hex。
    :raises Exception: 不主动抛出异常。
    """

    digest = hashlib.sha256(_encode_canonical_parts(parts)).hexdigest()
    return f"{_CLIENT_CORRELATION_PREFIX}{digest}"


def _encode_canonical_parts(parts: _CanonicalIdentityParts) -> bytes:
    """将规范身份元组编码为稳定字节串。

    编码使用类型前缀和字符串长度，避免 ``None``、整数与文本之间发生
    歧义；输入顺序即契约中的 canonical tuple 顺序。

    :param parts: 规范身份元组。
    :returns: UTF-8 字节串。
    :raises UnicodeEncodeError: 文本无法编码为 UTF-8 时抛出。
    """

    encoded_parts = tuple(_encode_canonical_part(part) for part in parts)
    return _PART_SEPARATOR.join(encoded_parts).encode("utf-8")


def _encode_canonical_part(value: str | int | None) -> str:
    """编码规范身份元组中的单个值。

    :param value: 文本、整数或 ``None``。
    :returns: 带类型前缀的稳定文本片段。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return _NONE_PART_TOKEN
    if isinstance(value, int):
        return (
            f"{_INTEGER_PART_PREFIX}{_PART_FIELD_SEPARATOR}"
            f"{value}"
        )
    return (
        f"{_STRING_PART_PREFIX}{_PART_FIELD_SEPARATOR}"
        f"{len(value)}{_PART_FIELD_SEPARATOR}{value}"
    )


def _validate_client_correlation_id(client_correlation_id: str) -> None:
    """校验客户端关联 id 的公开格式。

    :param client_correlation_id: 待校验的客户端关联 id。
    :returns: 无返回值。
    :raises ValueError: 关联 id 不是 ``dayu-`` 加 64 位 lowercase SHA-256 hex
        时抛出。
    """

    if len(client_correlation_id) != _CLIENT_CORRELATION_LENGTH:
        raise ValueError(
            "RunnerRequestIdentity.client_correlation_id must be 69 characters"
        )
    if not client_correlation_id.startswith(_CLIENT_CORRELATION_PREFIX):
        raise ValueError(
            "RunnerRequestIdentity.client_correlation_id must start with dayu-"
        )
    digest = client_correlation_id[len(_CLIENT_CORRELATION_PREFIX):]
    if not all(_is_lowercase_hex_char(char) for char in digest):
        raise ValueError(
            "RunnerRequestIdentity.client_correlation_id must contain "
            "lowercase SHA-256 hex"
        )


def _is_lowercase_hex_char(char: str) -> bool:
    """判断字符是否为 lowercase hex 字符。

    :param char: 单个字符。
    :returns: 是 ``0-9`` 或 ``a-f`` 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return ("0" <= char <= "9") or ("a" <= char <= "f")


__all__ = [
    "ProviderRequestIdAvailability",
    "RunnerRequestIdentity",
    "SuccessfulRunnerResponseIdentity",
    "build_runner_request_identity",
]
