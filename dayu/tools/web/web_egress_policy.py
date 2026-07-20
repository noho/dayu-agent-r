"""Web HTTP 出站目标授权策略。

本模块是 Web 工具对 URL 语法、DNS 解析结果与私网边界的唯一语义 owner。
它只产生不可变的已授权目标，不负责发送请求或解释响应内容。
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, TypeAlias, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

_DEFAULT_PORTS: Final[dict[str, int]] = {"http": 80, "https": 443}
_LOCAL_HOST_SUFFIXES: Final[tuple[str, ...]] = (".localhost", ".local", ".localdomain")
_BENCHMARK_NETWORK: Final[ipaddress.IPv4Network] = cast(
    ipaddress.IPv4Network,
    ipaddress.ip_network("198.18.0.0/15"),
)
_METADATA_ADDRESSES: Final[frozenset[ipaddress.IPv4Address]] = frozenset(
    {
        ipaddress.IPv4Address("169.254.169.254"),
        ipaddress.IPv4Address("100.100.100.200"),
    }
)

ResolvedAddresses: TypeAlias = tuple[str, ...]
WebAddressResolver: TypeAlias = Callable[[str, int], ResolvedAddresses]


class WebEgressPolicyError(ValueError):
    """表示 URL 或解析结果未通过 Web 出站策略。"""

    def __init__(self, *, url: str, stage: str, reason: str) -> None:
        """初始化拒绝异常。

        Args:
            url: 被拒绝的 URL。
            stage: 授权发生的网络阶段。
            reason: 稳定的拒绝原因。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(f"Web egress policy rejected URL during {stage}: {reason}: {url}")
        self.url = url
        self.stage = stage
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AuthorizedHttpTarget:
    """一次 HTTP hop 的不可变授权结果。

    Args:
        normalized_url: 已完成 IDNA 与传输规范化的 URL。
        scheme: ``http`` 或 ``https``。
        hostname: 保留给 HTTP Host、TLS SNI 与证书校验的 IDNA hostname。
        port: 已授权目标端口。
        approved_addresses: 本 hop 唯一允许连接的 numeric address 集合。

    Returns:
        无。

    Raises:
        无。
    """

    normalized_url: str
    scheme: str
    hostname: str
    port: int
    approved_addresses: ResolvedAddresses


def _default_resolver(hostname: str, port: int) -> ResolvedAddresses:
    """使用系统 resolver 解析一个 hostname。

    Args:
        hostname: 已 IDNA 规范化的 hostname。
        port: 目标端口。

    Returns:
        去重且按 numeric address 排序的解析结果。

    Raises:
        OSError: DNS 解析失败时抛出。
    """

    infos = socket.getaddrinfo(
        hostname,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    addresses = {str(info[4][0]).strip() for info in infos if info[4] and str(info[4][0]).strip()}
    return tuple(sorted(addresses, key=lambda value: (ipaddress.ip_address(value).version, value)))


def _normalized_ip_address(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """解析不带 scope id 的 numeric address。

    Args:
        address: numeric IPv4 或 IPv6 文本。

    Returns:
        标准库 IP address 对象。

    Raises:
        ValueError: 地址非法、带 scope id 或为 IPv4-mapped IPv6 时抛出。
    """

    if "%" in address:
        raise ValueError("scoped IPv6 address is not supported")
    value = ipaddress.ip_address(address)
    if isinstance(value, ipaddress.IPv6Address) and value.ipv4_mapped is not None:
        raise ValueError("IPv4-mapped IPv6 address is not allowed")
    return value


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """判断地址是否满足公网 profile。

    Args:
        address: 已解析 numeric address。

    Returns:
        可由公网 profile 连接时返回 ``True``。

    Raises:
        无。
    """

    if isinstance(address, ipaddress.IPv4Address):
        if address in _BENCHMARK_NETWORK or address in _METADATA_ADDRESSES:
            return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _is_local_profile_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """判断地址是否可由显式 local/dev profile 连接。

    Args:
        address: 已解析 numeric address。

    Returns:
        地址不是 unspecified 或 multicast 时返回 ``True``。

    Raises:
        无。
    """

    return not (address.is_unspecified or address.is_multicast)


def _normalize_hostname(hostname: str) -> str:
    """把 hostname 规范化为 IDNA ASCII。

    Args:
        hostname: URL 中的原始 hostname。

    Returns:
        小写 IDNA hostname。

    Raises:
        ValueError: hostname 为空或 IDNA 编码失败时抛出。
    """

    normalized = hostname.strip().rstrip(".").lower()
    if not normalized:
        raise ValueError("hostname is empty")
    try:
        return normalized.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("hostname is not valid IDNA") from exc


def _normalize_url_parts(url: str) -> tuple[SplitResult, str, str, int]:
    """解析并规范化 HTTP URL 的 owner 字段。

    Args:
        url: 待授权 URL。

    Returns:
        ``(parsed, scheme, hostname, port)``。

    Raises:
        ValueError: URL 语法、scheme、userinfo 或端口非法时抛出。
    """

    raw_url = url.strip()
    if not raw_url:
        raise ValueError("URL is empty")
    parsed = urlsplit(raw_url)
    scheme = parsed.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise ValueError("scheme must be http or https")
    if not parsed.netloc:
        raise ValueError("URL authority is missing")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise ValueError("userinfo is not allowed")
    hostname = _normalize_hostname(parsed.hostname or "")
    try:
        port = parsed.port if parsed.port is not None else _DEFAULT_PORTS[scheme]
    except ValueError as exc:
        raise ValueError("port is invalid") from exc
    if port < 1 or port > 65535:
        raise ValueError("port is invalid")
    return parsed, scheme, hostname, port


def _build_normalized_url(parsed: SplitResult, *, scheme: str, hostname: str, port: int) -> str:
    """用 owner 字段重建规范化 URL。

    Args:
        parsed: 原始拆分结果。
        scheme: 规范化 scheme。
        hostname: IDNA hostname。
        port: 目标端口。

    Returns:
        不含 fragment 的规范化 URL。

    Raises:
        ValueError: hostname 字面量非法时抛出。
    """

    try:
        host_value = f"[{hostname}]" if ipaddress.ip_address(hostname).version == 6 else hostname
    except ValueError:
        host_value = hostname
    default_port = _DEFAULT_PORTS[scheme]
    netloc = host_value if port == default_port else f"{host_value}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


class WebEgressPolicy:
    """冻结一次 Web 调用使用的 URL、DNS 与网络 profile。"""

    def __init__(
        self,
        *,
        allow_private_network: bool = False,
        allow_custom_port: bool = False,
        resolver: WebAddressResolver = _default_resolver,
    ) -> None:
        """初始化 policy。

        Args:
            allow_private_network: 是否启用显式 local/dev profile。
            allow_custom_port: 是否允许非默认 HTTP(S) 端口。
            resolver: 每 hop 唯一的 hostname resolver。

        Returns:
            无。

        Raises:
            无。
        """

        self._allow_private_network = bool(allow_private_network)
        self._allow_custom_port = bool(allow_custom_port)
        self._resolver = resolver

    @property
    def allows_private_network(self) -> bool:
        """返回当前 policy 是否为显式 local/dev profile。

        Args:
            无。

        Returns:
            local/dev profile 返回 ``True``。

        Raises:
            无。
        """

        return self._allow_private_network

    @property
    def allows_custom_port(self) -> bool:
        """返回当前 policy 是否允许非默认 HTTP(S) 端口。

        Args:
            无。

        Returns:
            允许自定义端口时返回 ``True``。

        Raises:
            无。
        """

        return self._allow_custom_port

    def authorize_http_target(self, url: str, *, stage: str) -> AuthorizedHttpTarget:
        """授权一个 HTTP hop 并冻结其 numeric destination。

        Args:
            url: 待授权 URL。
            stage: 当前网络阶段。

        Returns:
            只能由 target-bound transport 消费的不可变目标。

        Raises:
            WebEgressPolicyError: URL、端口、解析结果或地址类别不允许时抛出。
        """

        try:
            parsed, scheme, hostname, port = _normalize_url_parts(url)
        except ValueError as exc:
            raise WebEgressPolicyError(url=url, stage=stage, reason=str(exc)) from exc

        if not self._allow_custom_port and port != _DEFAULT_PORTS[scheme]:
            raise WebEgressPolicyError(url=url, stage=stage, reason="custom port is not allowed")
        if not self._allow_private_network and (
            hostname == "localhost" or hostname.endswith(_LOCAL_HOST_SUFFIXES)
        ):
            raise WebEgressPolicyError(url=url, stage=stage, reason="local hostname is not allowed")

        try:
            literal = _normalized_ip_address(hostname)
        except ValueError as literal_error:
            if "IPv4-mapped" in str(literal_error) or "scoped" in str(literal_error):
                raise WebEgressPolicyError(url=url, stage=stage, reason=str(literal_error)) from literal_error
            try:
                resolved_addresses = self._resolver(hostname, port)
            except OSError as exc:
                raise WebEgressPolicyError(url=url, stage=stage, reason="hostname resolution failed") from exc
        else:
            resolved_addresses = (str(literal),)

        if not resolved_addresses:
            raise WebEgressPolicyError(url=url, stage=stage, reason="hostname resolved to no addresses")

        approved: list[str] = []
        for raw_address in resolved_addresses:
            try:
                address = _normalized_ip_address(raw_address)
            except ValueError as exc:
                raise WebEgressPolicyError(url=url, stage=stage, reason=str(exc)) from exc
            address_allowed = (
                _is_local_profile_address(address)
                if self._allow_private_network
                else _is_public_address(address)
            )
            if not address_allowed:
                raise WebEgressPolicyError(
                    url=url,
                    stage=stage,
                    reason=f"resolved address is not allowed: {address}",
                )
            approved.append(str(address))

        approved_addresses = tuple(
            sorted(set(approved), key=lambda value: (ipaddress.ip_address(value).version, value))
        )
        return AuthorizedHttpTarget(
            normalized_url=_build_normalized_url(
                parsed,
                scheme=scheme,
                hostname=hostname,
                port=port,
            ),
            scheme=scheme,
            hostname=hostname,
            port=port,
            approved_addresses=approved_addresses,
        )

    def validate_response_url(
        self,
        url: str,
        *,
        target: AuthorizedHttpTarget,
        stage: str,
    ) -> str:
        """验证无自动 redirect 响应仍属于已授权 origin。

        本方法不重新解析 DNS；它只防止 transport 或测试替身把 response URL
        偷换到未授权 origin。

        Args:
            url: 响应报告的 URL。
            target: 本次请求使用的已授权目标。
            stage: 当前响应校验阶段。

        Returns:
            规范化后的响应 URL。

        Raises:
            WebEgressPolicyError: URL 非法或 origin 与 target 不一致时抛出。
        """

        try:
            parsed, scheme, hostname, port = _normalize_url_parts(url)
        except ValueError as exc:
            raise WebEgressPolicyError(url=url, stage=stage, reason=str(exc)) from exc
        if (scheme, hostname, port) != (target.scheme, target.hostname, target.port):
            raise WebEgressPolicyError(url=url, stage=stage, reason="response origin changed")
        return _build_normalized_url(parsed, scheme=scheme, hostname=hostname, port=port)

    def is_url_allowed(self, url: str) -> bool:
        """为非连接 consumer 提供同源的 fail-closed 布尔投影。

        Args:
            url: 待检查 URL。

        Returns:
            当前 profile 可授权时返回 ``True``。

        Raises:
            无。
        """

        try:
            self.authorize_http_target(url, stage="policy_projection")
        except WebEgressPolicyError:
            return False
        return True
