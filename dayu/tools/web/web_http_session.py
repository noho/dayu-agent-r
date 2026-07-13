"""网页抓取的 Session、已授权 transport 与 timeout 基础设施。

本模块消费 :class:`AuthorizedHttpTarget`，为每个 HTTP hop 创建私有的
target-bound adapter/pool/connection，并管理 response lease。它不拥有 URL
安全语义，也不包含内容转换或浏览器回退逻辑。
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Mapping
from threading import Lock
from types import TracebackType
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import InvalidURL
from requests.models import PreparedRequest
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.exceptions import NewConnectionError
from urllib3.util import connection as urllib3_connection
from urllib3.util.retry import Retry

from .web_egress_policy import AuthorizedHttpTarget

if TYPE_CHECKING:
    from urllib3._base_connection import BaseHTTPConnection, BaseHTTPSConnection

_RETRY_TOTAL = 3
_RETRY_CONNECT = 3
_RETRY_READ = 3
_RETRY_BACKOFF_FACTOR = 0.8
_RETRY_STATUS_FORCELIST = (429, 500, 502, 503, 504)
_MAX_REDIRECTS = 8
_MIN_TIMEOUT_BUDGET_SECONDS = 0.05

_WEB_SESSION: requests.Session | None = None
_WEB_NO_RETRY_SESSION: requests.Session | None = None
_WEB_SESSION_LOCK = Lock()


class _PinnedHTTPConnection(HTTPConnection):
    """只连接当前 pool 绑定 numeric address 的 HTTPConnection。"""

    _approved_addresses: tuple[str, ...] = ()

    def bind_approved_addresses(self, approved_addresses: tuple[str, ...]) -> None:
        """绑定本连接可使用的不可变 numeric address 集合。

        Args:
            approved_addresses: 当前 HTTP hop 的授权地址。

        Returns:
            无。

        Raises:
            ValueError: 地址集合为空时抛出。
        """

        if not approved_addresses:
            raise ValueError("approved address set must not be empty")
        self._approved_addresses = approved_addresses

    def _new_conn(self) -> socket.socket:
        """建立并验证只指向 approved address 的 socket。

        Args:
            无。

        Returns:
            peer 已验证的 TCP socket。

        Raises:
            NewConnectionError: 所有 approved address 均连接失败或 peer 不匹配时抛出。
        """

        return _connect_to_approved_addresses(self, self._approved_addresses)


class _PinnedHTTPSConnection(HTTPSConnection):
    """只连接当前 pool 绑定 numeric address 的 HTTPSConnection。"""

    _approved_addresses: tuple[str, ...] = ()

    def bind_approved_addresses(self, approved_addresses: tuple[str, ...]) -> None:
        """绑定本连接可使用的不可变 numeric address 集合。

        Args:
            approved_addresses: 当前 HTTPS hop 的授权地址。

        Returns:
            无。

        Raises:
            ValueError: 地址集合为空时抛出。
        """

        if not approved_addresses:
            raise ValueError("approved address set must not be empty")
        self._approved_addresses = approved_addresses

    def _new_conn(self) -> socket.socket:
        """建立并验证只指向 approved address 的 socket。

        Args:
            无。

        Returns:
            peer 已验证的 TCP socket；TLS 包装仍由父类以原 hostname 执行。

        Raises:
            NewConnectionError: 所有 approved address 均连接失败或 peer 不匹配时抛出。
        """

        return _connect_to_approved_addresses(self, self._approved_addresses)


def _connect_to_approved_addresses(
    connection: _PinnedHTTPConnection | _PinnedHTTPSConnection,
    approved_addresses: tuple[str, ...],
) -> socket.socket:
    """按确定顺序连接 approved numeric address 并验证实际 peer。

    Args:
        connection: 当前 urllib3 connection。
        approved_addresses: 当前 hop 冻结的授权地址。

    Returns:
        peer 属于授权集合的 socket。

    Raises:
        NewConnectionError: 未绑定地址、连接失败或 peer 不属于授权集合时抛出。
    """

    if not approved_addresses:
        raise NewConnectionError(connection, "No approved numeric address is bound")
    approved_values = {ipaddress.ip_address(address) for address in approved_addresses}
    failures: list[str] = []
    for address in approved_addresses:
        sock: socket.socket | None = None
        try:
            sock = urllib3_connection.create_connection(
                (address, connection.port),
                connection.timeout,
                source_address=connection.source_address,
                socket_options=connection.socket_options,
            )
            peer_text = str(sock.getpeername()[0]).split("%", 1)[0]
            peer = ipaddress.ip_address(peer_text)
            if isinstance(peer, ipaddress.IPv6Address) and peer.ipv4_mapped is not None:
                peer = peer.ipv4_mapped
            if peer not in approved_values:
                failures.append(f"peer mismatch: {peer}")
                sock.close()
                sock = None
                continue
            return sock
        except OSError as exc:
            failures.append(f"{address}: {exc}")
            if sock is not None:
                sock.close()
    detail = "; ".join(failures) or "no connection attempt completed"
    raise NewConnectionError(connection, f"Failed to connect to approved addresses: {detail}")


class _PinnedHTTPConnectionPool(HTTPConnectionPool):
    """把 approved address 集合注入每个新 HTTPConnection 的私有 pool。"""

    ConnectionCls = cast("type[BaseHTTPConnection]", _PinnedHTTPConnection)
    _approved_addresses: tuple[str, ...] = ()

    def bind_approved_addresses(self, approved_addresses: tuple[str, ...]) -> None:
        """绑定 pool 后续所有连接使用的地址集合。

        Args:
            approved_addresses: 当前 target 的不可变授权地址。

        Returns:
            无。

        Raises:
            ValueError: 地址集合为空时抛出。
        """

        if not approved_addresses:
            raise ValueError("approved address set must not be empty")
        self._approved_addresses = approved_addresses

    def _new_conn(self) -> BaseHTTPConnection:
        """创建已绑定 approved address 的 HTTP connection。

        Args:
            无。

        Returns:
            已绑定地址的 connection。

        Raises:
            RuntimeError: urllib3 未使用预期 connection class 时抛出。
        """

        connection = super()._new_conn()
        if not isinstance(connection, _PinnedHTTPConnection):
            raise RuntimeError("urllib3 returned an unexpected HTTP connection class")
        connection.bind_approved_addresses(self._approved_addresses)
        return connection


class _PinnedHTTPSConnectionPool(HTTPSConnectionPool):
    """把 approved address 集合注入每个新 HTTPSConnection 的私有 pool。"""

    ConnectionCls = cast("type[BaseHTTPSConnection]", _PinnedHTTPSConnection)
    _approved_addresses: tuple[str, ...] = ()

    def bind_approved_addresses(self, approved_addresses: tuple[str, ...]) -> None:
        """绑定 pool 后续所有连接使用的地址集合。

        Args:
            approved_addresses: 当前 target 的不可变授权地址。

        Returns:
            无。

        Raises:
            ValueError: 地址集合为空时抛出。
        """

        if not approved_addresses:
            raise ValueError("approved address set must not be empty")
        self._approved_addresses = approved_addresses

    def _new_conn(self) -> BaseHTTPSConnection:
        """创建已绑定 approved address 的 HTTPS connection。

        Args:
            无。

        Returns:
            已绑定地址的 connection。

        Raises:
            RuntimeError: urllib3 未使用预期 connection class 时抛出。
        """

        connection = super()._new_conn()
        if not isinstance(connection, _PinnedHTTPSConnection):
            raise RuntimeError("urllib3 returned an unexpected HTTPS connection class")
        connection.bind_approved_addresses(self._approved_addresses)
        return connection


class _TargetBoundHTTPAdapter(HTTPAdapter):
    """只服务单个 :class:`AuthorizedHttpTarget` 的 requests adapter。"""

    def __init__(self, *, target: AuthorizedHttpTarget, max_retries: Retry) -> None:
        """初始化 target-bound adapter。

        Args:
            target: 当前 HTTP hop 的授权目标。
            max_retries: 沿用 source session 的 urllib3 retry policy。

        Returns:
            无。

        Raises:
            无。
        """

        self._target = target
        super().__init__(max_retries=max_retries, pool_connections=1, pool_maxsize=1, pool_block=True)
        self.poolmanager.pool_classes_by_scheme = {
            "http": _PinnedHTTPConnectionPool,
            "https": _PinnedHTTPSConnectionPool,
        }

    def get_connection_with_tls_context(
        self,
        request: PreparedRequest,
        verify: bool | str | None,
        proxies: Mapping[str, str] | None = None,
        cert: str | tuple[str, str] | None = None,
    ) -> HTTPConnectionPool | HTTPSConnectionPool:
        """获取并绑定当前 target 的私有 pool。

        Args:
            request: requests 已准备请求。
            verify: TLS CA 校验配置。
            proxies: proxy 配置；本 owner 不支持 proxy。
            cert: 可选客户端证书配置。

        Returns:
            host 仍为原 IDNA hostname、destination 已绑定 numeric address 的 pool。

        Raises:
            requests.InvalidURL: 请求 origin 与 target 不一致或配置了 proxy 时抛出。
            RuntimeError: requests/urllib3 未返回预期 pool class 时抛出。
        """

        if proxies:
            raise InvalidURL("Target-bound Web egress transport does not support proxies")
        _validate_prepared_request_target(request, target=self._target)
        pool = super().get_connection_with_tls_context(request, verify, proxies={}, cert=cert)
        if isinstance(pool, _PinnedHTTPConnectionPool | _PinnedHTTPSConnectionPool):
            if pool.host != self._target.hostname or int(pool.port or 0) != self._target.port:
                raise InvalidURL("Connection pool origin does not match authorized target")
            pool.bind_approved_addresses(self._target.approved_addresses)
            return pool
        raise RuntimeError("requests/urllib3 returned an unexpected connection pool class")


def _validate_prepared_request_target(
    request: PreparedRequest,
    *,
    target: AuthorizedHttpTarget,
) -> None:
    """验证 PreparedRequest 未离开 adapter 绑定 target。

    Args:
        request: requests 已准备请求。
        target: adapter 唯一允许的目标。

    Returns:
        无。

    Raises:
        requests.InvalidURL: 请求缺少 URL、userinfo/端口非法或 origin 不匹配时抛出。
    """

    request_url = request.url or ""
    try:
        parsed = urlsplit(request_url)
        hostname = (parsed.hostname or "").encode("idna").decode("ascii").lower()
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme.lower() == "https" else 80)
    except (UnicodeError, ValueError) as exc:
        raise InvalidURL("Prepared request target is invalid") from exc
    if parsed.username is not None or parsed.password is not None:
        raise InvalidURL("Prepared request userinfo is not allowed")
    if (parsed.scheme.lower(), hostname, port) != (target.scheme, target.hostname, target.port):
        raise InvalidURL("Prepared request origin does not match authorized target")


class AuthorizedResponseLease:
    """持有一个 response 及其 target-bound transport 的唯一关闭权。"""

    def __init__(self, *, response: requests.Response, session: requests.Session) -> None:
        """初始化 response lease。

        Args:
            response: 已创建的 response。
            session: 持有 target-bound adapter/pool 的私有 session。

        Returns:
            无。

        Raises:
            无。
        """

        self.response = response
        self._session = session
        self._closed = False

    @property
    def closed(self) -> bool:
        """返回 lease 是否已关闭。

        Args:
            无。

        Returns:
            已关闭返回 ``True``。

        Raises:
            无。
        """

        return self._closed

    def close(self) -> None:
        """幂等关闭 response 与其私有 transport。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。关闭异常不会覆盖当前业务异常。
        """

        if self._closed:
            return
        self._closed = True
        try:
            self.response.close()
        except Exception:
            pass
        try:
            self._session.close()
        except Exception:
            pass

    def __enter__(self) -> AuthorizedResponseLease:
        """进入 lease context。

        Args:
            无。

        Returns:
            当前 lease。

        Raises:
            无。
        """

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出 context 并关闭 lease。

        Args:
            exc_type: 当前异常类型。
            exc: 当前异常。
            traceback: 当前 traceback；不读取。

        Returns:
            无。

        Raises:
            无。
        """

        del exc_type, exc, traceback
        self.close()


def _send_authorized_request(
    source_session: requests.Session,
    *,
    target: AuthorizedHttpTarget,
    method: str,
    timeout: float,
    headers: Mapping[str, str],
    stream: bool,
) -> AuthorizedResponseLease:
    """通过 target-bound transport 发送单个已授权 HTTP hop。

    Args:
        source_session: 仅提供 retry、headers、cookies 与 TLS 配置的 source session。
        target: 当前 hop 的不可变授权目标。
        method: HTTP 方法。
        timeout: 当前 hop 超时秒数。
        headers: 请求头。
        stream: 是否流式读取响应。

    Returns:
        唯一拥有 response 与 pool 的 lease。

    Raises:
        requests.RequestException: prepare、connect、TLS 或请求失败时抛出。
    """

    source_adapter = source_session.get_adapter(target.normalized_url)
    if not isinstance(source_adapter, HTTPAdapter):
        raise RuntimeError("source session adapter must be requests.HTTPAdapter")
    retry = source_adapter.max_retries
    adapter = _TargetBoundHTTPAdapter(target=target, max_retries=retry)
    call_session = requests.Session()
    call_session.trust_env = False
    call_session.headers.clear()
    call_session.headers.update(source_session.headers)
    call_session.cookies.update(source_session.cookies)
    call_session.auth = source_session.auth
    call_session.verify = source_session.verify
    call_session.cert = source_session.cert
    call_session.max_redirects = source_session.max_redirects
    replaced_adapter = call_session.get_adapter(target.normalized_url)
    call_session.mount(f"{target.scheme}://", adapter)
    replaced_adapter.close()
    response: requests.Response | None = None
    try:
        response = call_session.request(
            method,
            target.normalized_url,
            timeout=timeout,
            headers=dict(headers),
            allow_redirects=False,
            stream=stream,
            proxies={},
        )
        source_session.cookies.update(call_session.cookies)
        return AuthorizedResponseLease(response=response, session=call_session)
    except Exception:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        call_session.close()
        raise


def _create_retry_session() -> requests.Session:
    """创建带重试策略的会话对象。

    Args:
        无。

    Returns:
        复用连接池和 Cookie 的 `requests.Session` 实例。

    Raises:
        无。
    """

    session = requests.Session()
    retry = Retry(
        total=_RETRY_TOTAL,
        connect=_RETRY_CONNECT,
        read=_RETRY_READ,
        status_forcelist=_RETRY_STATUS_FORCELIST,
        allowed_methods=frozenset({"GET", "HEAD"}),
        backoff_factor=_RETRY_BACKOFF_FACTOR,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.max_redirects = _MAX_REDIRECTS
    return session


def _create_no_retry_session(*, source_session: requests.Session | None = None) -> requests.Session:
    """创建禁用自动重试的会话对象。

    Args:
        source_session: 可选源会话；若提供则复用其 headers/cookies/max_redirects。

    Returns:
        不带 urllib3 自动重试的 `requests.Session`。

    Raises:
        无。
    """

    session = requests.Session()
    if isinstance(source_session, requests.Session):
        session.headers.update(source_session.headers)
        session.cookies.update(source_session.cookies)
        session.max_redirects = source_session.max_redirects
    else:
        session.max_redirects = _MAX_REDIRECTS

    retry = Retry(
        total=0,
        connect=0,
        read=0,
        redirect=0,
        status=0,
        allowed_methods=frozenset({"GET", "HEAD"}),
        backoff_factor=0.0,
        respect_retry_after_header=False,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _get_web_session() -> requests.Session:
    """获取全局复用 Session。

    Args:
        无。

    Returns:
        全局共享的 `requests.Session`。

    Raises:
        无。
    """

    global _WEB_SESSION
    if _WEB_SESSION is not None:
        return _WEB_SESSION
    with _WEB_SESSION_LOCK:
        if _WEB_SESSION is None:
            _WEB_SESSION = _create_retry_session()
    return _WEB_SESSION


def _get_no_retry_web_session() -> requests.Session:
    """获取全局复用的无重试 Session。

    Args:
        无。

    Returns:
        共享的无自动重试 `requests.Session`。

    Raises:
        无。
    """

    global _WEB_NO_RETRY_SESSION
    if _WEB_NO_RETRY_SESSION is not None:
        return _WEB_NO_RETRY_SESSION
    with _WEB_SESSION_LOCK:
        if _WEB_NO_RETRY_SESSION is None:
            _WEB_NO_RETRY_SESSION = _create_no_retry_session()
    return _WEB_NO_RETRY_SESSION


def _safe_timeout(timeout_seconds: float) -> float:
    """规范化超时参数。

    Args:
        timeout_seconds: 原始超时秒数。

    Returns:
        有效的超时值。

    Raises:
        无。
    """

    return max(1.0, float(timeout_seconds))


def _normalize_timeout_budget(timeout_budget: float | None) -> float | None:
    """规范化工具总预算秒数。

    Args:
        timeout_budget: Runner 注入的单次 tool call 总预算。

    Returns:
        规范化后的预算秒数；若未配置则返回 `None`。

    Raises:
        无。
    """

    if timeout_budget is None:
        return None
    return max(0.0, float(timeout_budget))


def _compute_deadline_monotonic(timeout_budget: float | None) -> float | None:
    """基于工具总预算计算当前调用的单调时钟 deadline。

    Args:
        timeout_budget: Runner 注入的单次 tool call 总预算。

    Returns:
        当前调用的 deadline；若未配置预算则返回 `None`。

    Raises:
        无。
    """

    normalized_budget = _normalize_timeout_budget(timeout_budget)
    if normalized_budget is None:
        return None
    return time.monotonic() + normalized_budget


def _resolve_timeout_budget(
    timeout_seconds: float,
    *,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    reserve_seconds: float = 0.0,
) -> float:
    """结合工具总预算与当前剩余时间，解析本阶段允许使用的 timeout。

    Args:
        timeout_seconds: 配置层或调用方声明的基础超时。
        timeout_budget: Runner 注入的单次 tool call 总预算。
        deadline_monotonic: 当前工具调用的单调时钟 deadline。
        reserve_seconds: 需要为后续阶段预留的秒数。

    Returns:
        当前阶段可用的 timeout 秒数。

    Raises:
        requests.Timeout: 当当前工具剩余预算已耗尽时抛出。
    """

    configured_timeout = _safe_timeout(timeout_seconds)
    normalized_budget = _normalize_timeout_budget(timeout_budget)
    if deadline_monotonic is None:
        if normalized_budget is None:
            return configured_timeout
        remaining_timeout = normalized_budget
    else:
        remaining_timeout = max(0.0, deadline_monotonic - time.monotonic())

    if normalized_budget is None and deadline_monotonic is None:
        return configured_timeout

    effective_timeout = min(configured_timeout, max(remaining_timeout - reserve_seconds, 0.0))
    if effective_timeout < _MIN_TIMEOUT_BUDGET_SECONDS:
        raise requests.Timeout("Tool execution deadline exceeded before web request started")
    return effective_timeout


def _prepare_call_session(
    session: requests.Session,
    *,
    timeout_budget: float | None = None,
) -> tuple[requests.Session, bool]:
    """按工具总预算选择当前调用应使用的 Session。

    当工具处于 Runner 的总预算约束内时，返回共享的无自动重试 Session，
    防止单次 HTTP 调用因 urllib3 retry/backoff 放大总耗时，同时保留跨次
    抓取的 Cookie / warmup 状态。

    Args:
        session: 默认复用 Session。
        timeout_budget: Runner 注入的单次 tool call 总预算。

    Returns:
        `(resolved_session, should_close)` 二元组。

    Raises:
        无。
    """

    if timeout_budget is None or not isinstance(session, requests.Session):
        return session, False
    return _get_no_retry_web_session(), False
