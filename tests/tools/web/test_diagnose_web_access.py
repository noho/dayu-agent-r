"""Web access diagnostics utility 的确定性测试。"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolCallable, ToolDefinition
from dayu.contracts.tool_execution import AsyncDirectToolExecutionCapability
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.contracts.tool_schema import ToolFunctionSchema, ToolParametersSchema, ToolSchema
from dayu.documents.docling_runtime import DoclingRuntimeInitializationError
from dayu.tools.web import web_http_session
from dayu.tools.web import web_tools as web_tools_module
from dayu.tools.web.web_egress_policy import WebEgressPolicy
from dayu.tools.web.web_resource_budget import (
    DEFAULT_BROWSER_RESOURCE_BUDGET,
    DEFAULT_HTTP_RESOURCE_BUDGET,
    HttpResourceBudget,
)
JsonObject = dict[str, JsonValue]

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from utils import diagnose_web_access as diag

_DIAGNOSE_SCRIPT = _REPO_ROOT / "utils" / "diagnose_web_access.py"
_FORBIDDEN_IMPORTS = (
    "dayu.engine.tool_registry",
    "dayu.engine.truncation_manager",
    "dayu.engine.tools",
    "dayu.engine.tools.fetch_more",
    "dayu.web",
    "dayu.ui",
)


class _SessionCloseSpy(diag.requests.Session):
    """记录 diagnostic requests profile 是否关闭局部 Session。"""

    instances: list["_SessionCloseSpy"] = []

    def __init__(self) -> None:
        """初始化 close 计数。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self.close_count = 0
        _SessionCloseSpy.instances.append(self)

    def close(self) -> None:
        """记录 close 调用并执行父类关闭。

        Args:
            无。

        Returns:
            无。

        Raises:
            Exception: 父类关闭失败时透出。
        """

        self.close_count += 1
        super().close()


class _StorageStateContext:
    """storage-state atomic lifecycle 测试用最小 context。"""

    def __init__(self, payload: JsonValue) -> None:
        """保存待序列化 payload。"""

        self.payload = payload
        self.call_count = 0

    def storage_state(self, *, path: str | None = None) -> JsonValue:
        """返回内存 payload，并拒绝 Playwright 直接写路径。"""

        assert path is None
        self.call_count += 1
        return self.payload


class _BodyResponse:
    """bounded Playwright response-body helper 测试替身。"""

    def __init__(self, *, body: bytes, headers: Mapping[str, str]) -> None:
        """保存 response bytes 与 headers。"""

        self._body = body
        self.headers = headers

    def body(self) -> bytes:
        """返回确定性 response bytes。"""

        return self._body


def _raise_diagnostic_request_exception(
    session: diag.requests.Session,
    *,
    method: str,
    url: str,
    timeout: float,
    headers: dict[str, str],
    normalize_url_for_http: Callable[[str], str],
    egress_policy: WebEgressPolicy,
    stream: bool,
    cancellation_token: CancellationToken | None,
) -> tuple[web_http_session.AuthorizedResponseLease, int, tuple[str, ...]]:
    """模拟 diagnostic requests 路径的请求异常。

    Args:
        session: 当前 diagnostic 局部 Session。
        method: HTTP 方法。
        url: 请求 URL。
        timeout: 超时秒数。
        headers: 请求头。
        normalize_url_for_http: URL 规范化函数。
        egress_policy: 当前 Web 出站策略。
        stream: 是否流式读取。
        cancellation_token: 取消令牌。

    Returns:
        不返回；始终抛出请求异常。

    Raises:
        requests.Timeout: 始终抛出，用于验证异常路径 cleanup。
    """

    del session, method, url, timeout, headers, normalize_url_for_http, egress_policy, stream, cancellation_token
    raise diag.requests.Timeout("synthetic diagnostic timeout")


def _preserve_materialized_response_body(
    response_value: diag.requests.Response,
    *,
    http_resource_budget: HttpResourceBudget,
) -> None:
    """保留测试已预置的 response body，不执行二次 materialize。

    Args:
        response_value: 已预置 body 的 diagnostic response。
        http_resource_budget: 本次 HTTP child 资源预算。

    Returns:
        无。

    Raises:
        无。
    """

    del response_value, http_resource_budget


def test_jsonl_and_txt_corpus_parsing_retains_metadata_and_deduplicates(tmp_path: Path) -> None:
    """JSONL/TXT corpus 解析应保留首个样本元数据并按 URL 去重。"""

    jsonl_path = tmp_path / "urls.jsonl"
    jsonl_path.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "url": "https://example.com/a",
                        "label": "Example",
                        "region": "US",
                        "category": "news",
                        "notes": "first",
                    }
                ),
                json.dumps("https://example.com/b"),
                json.dumps({"url": "https://example.com/a", "label": "Duplicate"}),
            )
        ),
        encoding="utf-8",
    )
    txt_path = tmp_path / "urls.txt"
    txt_path.write_text(
        "\n".join(("", "# comment", "https://example.com/c", "https://example.com/c")),
        encoding="utf-8",
    )

    jsonl_entries = diag._read_url_entries(jsonl_path)
    txt_entries = diag._read_url_entries(txt_path)

    assert jsonl_entries == [
        diag.DiagnosticUrlEntry(
            url="https://example.com/a",
            label="Example",
            region="US",
            category="news",
            notes="first",
        ),
        diag.DiagnosticUrlEntry(url="https://example.com/b"),
    ]
    assert txt_entries == [diag.DiagnosticUrlEntry(url="https://example.com/c")]


def test_invalid_jsonl_reports_line_number(tmp_path: Path) -> None:
    """非法 JSONL 应带行号失败，避免批量诊断静默吞样本。"""

    path = tmp_path / "bad.jsonl"
    path.write_text('{"url": "https://example.com"}\n{"url": ', encoding="utf-8")

    with pytest.raises(ValueError, match="JSONL 第 2 行不是合法 JSON"):
        diag._read_url_entries(path)


def test_storage_state_dir_resolves_existing_host_input_without_default_output(tmp_path: Path) -> None:
    """storage-state 目录只允许解析 owner 输入，默认必须零写入。"""

    storage_dir = tmp_path / "state"
    storage_dir.mkdir()
    host_state = storage_dir / "dayu-web-diagnostic-storage-state-example.com.json"
    host_state.write_text('{"cookies":[]}', encoding="utf-8")
    options = _options(storage_state_dir=str(storage_dir))

    storage_state_in, storage_state_out = diag._resolve_storage_state_paths(
        options,
        "https://example.com/report",
    )

    assert storage_state_in == str(host_state)
    assert storage_state_out == ""


def test_storage_state_default_publish_is_zero_write(tmp_path: Path) -> None:
    """未显式 opt-in 时不得创建目录、temp 或 final。"""

    context = _StorageStateContext({"cookies": [{"value": "secret"}]})
    lifecycle = diag._prepare_storage_state_lifecycle(
        _options(storage_state_dir=str(tmp_path / "missing")),
        "https://example.com/report",
    )

    lifecycle.publish(cast(diag._BrowserContextProtocol, context))

    assert lifecycle.output_enabled is False
    assert context.call_count == 0
    assert not (tmp_path / "missing").exists()


def test_ensure_private_storage_directory_creates_private_leaf(tmp_path: Path) -> None:
    """新 storage owner 目录必须创建为 0700。"""

    storage_directory = tmp_path / "private-state"

    diag._ensure_private_storage_directory(storage_directory)

    assert storage_directory.is_dir()
    assert storage_directory.stat().st_mode & 0o777 == 0o700


def test_ensure_private_storage_directory_accepts_existing_private_leaf(
    tmp_path: Path,
) -> None:
    """已存在且为 0700 的 owner 目录必须原样接受。"""

    storage_directory = tmp_path / "private-state"
    storage_directory.mkdir(mode=0o700)

    diag._ensure_private_storage_directory(storage_directory)

    assert storage_directory.stat().st_mode & 0o777 == 0o700


def test_ensure_private_storage_directory_rejects_non_private_leaf(
    tmp_path: Path,
) -> None:
    """已存在但权限不是 0700 的 owner 目录必须 fail closed。"""

    storage_directory = tmp_path / "shared-state"
    storage_directory.mkdir(mode=0o755)
    os.chmod(storage_directory, 0o755)

    with pytest.raises(ValueError, match="必须预先设置为 0700"):
        diag._ensure_private_storage_directory(storage_directory)


def test_ensure_private_storage_directory_rejects_non_directory_path(
    tmp_path: Path,
) -> None:
    """owner 路径已被普通文件占用时必须拒绝。"""

    storage_directory = tmp_path / "state-file"
    storage_directory.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="不是目录"):
        diag._ensure_private_storage_directory(storage_directory)


def test_ensure_private_storage_directory_does_not_harden_intermediate_parents(
    tmp_path: Path,
) -> None:
    """嵌套路径只收紧最终 storage dir，不把中间父目录强制改成 0700。"""

    storage_directory = tmp_path / "shared" / "nested" / "private-state"
    previous_umask = os.umask(0o022)
    try:
        diag._ensure_private_storage_directory(storage_directory)
    finally:
        os.umask(previous_umask)

    assert (tmp_path / "shared").stat().st_mode & 0o777 == 0o755
    assert (tmp_path / "shared" / "nested").stat().st_mode & 0o777 == 0o755
    assert storage_directory.stat().st_mode & 0o777 == 0o700


def test_storage_state_atomic_publish_permissions_and_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式 opt-in 必须执行 0700/0600、flush/fsync、replace 与 failure cleanup。"""

    parent = tmp_path / "private-state"
    final_path = parent / "dayu-web-diagnostic-storage-state-example.com.json"
    options = _options(
        storage_state_out=str(final_path),
        storage_state_ttl_seconds=60,
    )
    lifecycle = diag._prepare_storage_state_lifecycle(
        options,
        "https://example.com/report",
    )
    context = _StorageStateContext({"cookies": [{"name": "sid", "value": "secret"}]})
    fsync_calls: list[int] = []
    replace_calls: list[tuple[Path, Path]] = []
    original_fsync = os.fsync
    original_replace = os.replace

    def fsync_spy(descriptor: int) -> None:
        """记录并执行真实 fsync。"""

        fsync_calls.append(descriptor)
        original_fsync(descriptor)

    def replace_spy(source: Path, destination: Path) -> None:
        """记录并执行真实 atomic replace。"""

        replace_calls.append((source, destination))
        original_replace(source, destination)

    monkeypatch.setattr(diag.os, "fsync", fsync_spy)
    monkeypatch.setattr(diag.os, "replace", replace_spy)

    lifecycle.publish(cast(diag._BrowserContextProtocol, context))

    assert parent.stat().st_mode & 0o777 == 0o700
    assert final_path.stat().st_mode & 0o777 == 0o600
    assert fsync_calls
    assert len(replace_calls) == 1
    assert replace_calls[0][1] == final_path
    assert not tuple(parent.glob(".dayu-web-diagnostic-storage-state-*.tmp"))
    assert lifecycle.artifact_projection() == {
        "input_used": False,
        "output_enabled": True,
        "output_label": final_path.name,
        "ttl_seconds": 60,
        "published": True,
    }

    lifecycle.cleanup_failure()
    assert not final_path.exists()
    assert lifecycle.published is False


def test_storage_state_replace_failure_removes_run_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通 publish failure 必须删除本 run temp，且不得留下 final。"""

    parent = tmp_path / "state"
    final_path = parent / "dayu-web-diagnostic-storage-state-example.com.json"
    lifecycle = diag._prepare_storage_state_lifecycle(
        _options(
            storage_state_out=str(final_path),
            storage_state_ttl_seconds=30,
        ),
        "https://example.com/report",
    )

    def fail_replace(source: Path, destination: Path) -> None:
        """模拟 ordinary replace failure。"""

        del source, destination
        raise OSError("replace failed")

    monkeypatch.setattr(diag.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        lifecycle.publish(
            cast(diag._BrowserContextProtocol, _StorageStateContext({"cookies": []}))
        )

    assert not final_path.exists()
    assert not tuple(parent.glob(".dayu-web-diagnostic-storage-state-*.tmp"))


def test_storage_state_post_replace_failure_marks_and_cleans_published_final(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """replace 后 chmod 失败时必须保留 published 事实供 cleanup 删除 final。"""

    parent = tmp_path / "state"
    final_path = parent / "dayu-web-diagnostic-storage-state-example.com.json"
    lifecycle = diag._prepare_storage_state_lifecycle(
        _options(
            storage_state_out=str(final_path),
            storage_state_ttl_seconds=30,
        ),
        "https://example.com/report",
    )
    original_chmod = os.chmod

    def fail_final_chmod(path: Path, mode: int) -> None:
        """只在 final 已由 replace 发布后模拟 chmod failure。"""

        if Path(path) == final_path:
            raise OSError("final chmod failed")
        original_chmod(path, mode)

    monkeypatch.setattr(diag.os, "chmod", fail_final_chmod)

    with pytest.raises(OSError, match="final chmod failed"):
        lifecycle.publish(
            cast(diag._BrowserContextProtocol, _StorageStateContext({"cookies": []}))
        )

    assert final_path.exists()
    assert lifecycle.published is True
    lifecycle.cleanup_failure()
    assert not final_path.exists()
    assert lifecycle.published is False


def test_storage_state_cancel_path_cleans_temp_and_published_final(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BaseException/cancel 路径必须调用同一 lifecycle cleanup，不承诺 SIGKILL。"""

    import playwright.sync_api as playwright_sync_api

    parent = tmp_path / "state"
    parent.mkdir(mode=0o700)
    final_path = parent / "dayu-web-diagnostic-storage-state-127.0.0.1.json"
    temp_path = parent / ".dayu-web-diagnostic-storage-state-cancel.tmp"
    final_path.write_text("{}", encoding="utf-8")
    temp_path.write_text("{}", encoding="utf-8")
    lifecycle = diag._StorageStateLifecycle(
        input_path=None,
        final_path=final_path,
        ttl_seconds=60,
        temp_path=temp_path,
        published=True,
    )

    class _CancelledManager:
        """在 browser manager enter 阶段模拟协作取消。"""

        def __enter__(self) -> diag._PlaywrightProtocol:
            """模拟取消异常。"""

            raise KeyboardInterrupt("cancelled")

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            """保持 context manager 协议。"""

            del exc_type, exc_value, traceback

    def fake_prepare(
        options: diag.CliOptions,
        url: str,
    ) -> diag._StorageStateLifecycle:
        """返回预置 cancellation lifecycle。"""

        del options, url
        return lifecycle

    def fake_sync_playwright() -> _CancelledManager:
        """返回会在 enter 抛取消的 manager。"""

        return _CancelledManager()

    monkeypatch.setattr(diag, "_prepare_storage_state_lifecycle", fake_prepare)
    monkeypatch.setattr(playwright_sync_api, "sync_playwright", fake_sync_playwright)

    with pytest.raises(KeyboardInterrupt, match="cancelled"):
        diag._build_playwright_profile(
            "http://127.0.0.1/report",
            _options(
                url="http://127.0.0.1/report",
                allow_private_network_url=True,
            ),
            egress_policy=WebEgressPolicy(allow_private_network=True),
        )

    assert not temp_path.exists()
    assert not final_path.exists()
    assert lifecycle.published is False


def test_storage_state_startup_reconciliation_is_owner_scoped_and_ttl_bounded(
    tmp_path: Path,
) -> None:
    """startup 只删除 owner orphan temp 与过期 final，保留 fresh/unrelated 文件。"""

    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    orphan = directory / ".dayu-web-diagnostic-storage-state-orphan.tmp"
    expired = directory / "dayu-web-diagnostic-storage-state-expired.example.json"
    fresh = directory / "dayu-web-diagnostic-storage-state-fresh.example.json"
    unrelated = directory / "customer-storage.json"
    for path in (orphan, expired, fresh, unrelated):
        path.write_text("{}", encoding="utf-8")
    os.utime(expired, (100.0, 100.0))
    os.utime(fresh, (180.0, 180.0))

    diag._reconcile_storage_state_directory(
        directory,
        ttl_seconds=60,
        now_epoch_seconds=200.0,
    )

    assert not orphan.exists()
    assert not expired.exists()
    assert fresh.exists()
    assert unrelated.exists()


def test_url_normalization_requires_http_url() -> None:
    """URL 规范化应补全 HTTPS，并拒绝空值、非 HTTP scheme 与缺失 host 的输入。"""

    assert diag._normalize_url_for_http(" example.com/report ") == "https://example.com/report"
    assert diag._normalize_url_for_http("http://example.com/report") == "http://example.com/report"

    with pytest.raises(ValueError, match="URL 不能为空"):
        diag._normalize_url_for_http(" ")
    with pytest.raises(ValueError, match="只支持 http/https URL"):
        diag._normalize_url_for_http("ftp://example.com/report")
    with pytest.raises(ValueError, match="只支持 http/https URL"):
        diag._normalize_url_for_http("https:///missing-host")


def _resolve_example_public_address(hostname: str, port: int) -> tuple[str, ...]:
    """把测试域名固定解析到公开示例地址。

    Args:
        hostname: 待解析 hostname。
        port: 目标端口。

    Returns:
        单一公开 IPv4 地址。

    Raises:
        无。
    """

    del hostname, port
    return ("93.184.216.34",)


def test_url_safety_rejects_private_and_local_hosts_by_default() -> None:
    """默认 URL 安全策略应阻止内网、本地与 IPv4-mapped IPv6 目标。"""

    blocked_urls = (
        "http://localhost/report",
        "http://service.localhost/report",
        "http://printer.local/report",
        "http://0.0.0.0/report",
        "http://127.0.0.1/report",
        "http://10.0.0.1/report",
        "http://172.16.0.1/report",
        "http://192.168.1.1/report",
        "http://[::1]/report",
        "http://[fe80::1]/report",
        "http://[::ffff:10.0.0.1]/report",
    )

    public_policy = WebEgressPolicy(resolver=_resolve_example_public_address)
    for url in blocked_urls:
        with pytest.raises(ValueError, match="Web egress policy rejected"):
            public_policy.authorize_http_target(url, stage="diagnostic_test")

    local_policy = WebEgressPolicy(allow_private_network=True)
    with pytest.raises(ValueError, match="IPv4-mapped"):
        local_policy.authorize_http_target(
            "http://[::ffff:10.0.0.1]/report",
            stage="diagnostic_test",
        )
    target = public_policy.authorize_http_target(
        diag._normalize_url_for_http("example.com/report"),
        stage="diagnostic_test",
    )
    assert target.normalized_url == "https://example.com/report"


def test_single_diagnostic_private_mode_preserves_local_custom_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既有 private diagnostic 模式必须继续允许本地 custom-port URL。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: utility policy construction 未保留 custom-port 行为时抛出。
    """

    authorized_ports: list[int] = []

    def fake_build_requests_profile(
        url: str,
        *,
        timeout_seconds: float,
        egress_policy: WebEgressPolicy,
    ) -> JsonObject:
        """在 utility policy construction boundary 验证 custom-port 授权。

        Args:
            url: 待诊断 URL。
            timeout_seconds: 当前请求超时秒数。
            egress_policy: utility 构造的 Web 出站策略。

        Returns:
            完成授权后的确定性 skipped profile。

        Raises:
            WebEgressPolicyError: URL 未被当前出站策略授权时抛出。
        """

        del timeout_seconds
        target = egress_policy.authorize_http_target(
            url,
            stage="diagnostic_test",
        )
        authorized_ports.append(target.port)
        return diag._skipped_profile(
            "synthetic_after_authorization",
            url=url,
            backend=diag.WebDiagnosticBackend.REQUESTS,
        )

    monkeypatch.setattr(diag, "_build_requests_profile", fake_build_requests_profile)
    payload = diag._build_single_diagnostic_payload(
        _options(
            url="http://127.0.0.1:43117/fixture.pdf",
            allow_private_network_url=True,
            skip_tool_fetch=True,
            skip_playwright=True,
        )
    )

    assert authorized_ports == [43117]
    assert payload["safe_url"] == "http://127.0.0.1:43117/fixture.pdf"


def test_header_projection_never_persists_raw_values() -> None:
    """header 投影只能保留存在性与受限 media-type 语义。"""

    redacted = diag._redact_headers(
        {
            "Authorization": "Bearer secret-token",
            "Cookie": "sid=abc",
            "X-Api-Key": "api-key",
            "X-Access-Token": "token",
            "Client-Secret": "secret",
            "User-Agent": "diagnostic-agent",
            "Cache-Control": "no-cache",
        }
    )

    assert redacted["sensitive_names"] == [
        "authorization",
        "client-secret",
        "cookie",
        "x-access-token",
        "x-api-key",
    ]
    assert redacted["present_names"] == ["cache-control"]
    assert "secret-token" not in json.dumps(redacted)
    assert "diagnostic-agent" not in json.dumps(redacted)


def test_requests_profile_records_raw_response_byte_length(monkeypatch: pytest.MonkeyPatch) -> None:
    """requests profile 应记录 response.content 的原始字节长度。"""

    response = diag.requests.Response()
    response.status_code = 200
    response.url = "http://127.0.0.1:43117/fixture.pdf"
    response.headers.update({"Content-Type": "application/pdf"})
    response._content = b"%PDF fixture bytes"
    response.encoding = "utf-8"

    def fake_request_with_safe_redirects(
        session: diag.requests.Session,
        *,
        method: str,
        url: str,
        timeout: float,
        headers: dict[str, str],
        normalize_url_for_http: Callable[[str], str],
        egress_policy: WebEgressPolicy,
        stream: bool,
        cancellation_token: CancellationToken | None,
    ) -> tuple[web_http_session.AuthorizedResponseLease, int, tuple[str, ...]]:
        """返回确定性 diagnostic response lease。"""

        del session, headers, normalize_url_for_http, egress_policy, cancellation_token
        assert method == "GET"
        assert url == "http://127.0.0.1:43117/fixture.pdf"
        assert timeout == 1.0
        assert stream is True
        return (
            web_http_session.AuthorizedResponseLease(
                response=response,
                session=diag.requests.Session(),
            ),
            0,
            (url,),
        )

    monkeypatch.setattr(
        diag._web_fetch_orchestrator,
        "_request_with_safe_redirects",
        fake_request_with_safe_redirects,
    )

    monkeypatch.setattr(
        diag._web_fetch_orchestrator,
        "_materialize_response_body",
        _preserve_materialized_response_body,
    )

    profile = diag._build_requests_profile(
        "http://127.0.0.1:43117/fixture.pdf",
        timeout_seconds=1.0,
        egress_policy=WebEgressPolicy(allow_private_network=True),
    )
    response_headers = _object_value(profile["response_headers"])
    assert profile["outcome"] == "completed"
    assert response_headers["content_type"] == "application/pdf"
    assert profile["content_length"] == len(b"%PDF fixture bytes")
    assert str(profile["content_digest"]).startswith("sha256:")


def test_requests_profile_closes_session_on_request_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """requests profile 请求异常路径必须关闭局部 Session。"""

    _SessionCloseSpy.instances = []
    monkeypatch.setattr(diag.requests, "Session", _SessionCloseSpy)
    monkeypatch.setattr(
        diag._web_fetch_orchestrator,
        "_request_with_safe_redirects",
        _raise_diagnostic_request_exception,
    )

    profile = diag._build_requests_profile(
        "https://example.com/report",
        timeout_seconds=1.0,
        egress_policy=WebEgressPolicy(resolver=_resolve_example_public_address),
    )

    assert profile["outcome"] == "failed"
    assert profile["error_code"] == "request_exception"
    assert len(_SessionCloseSpy.instances) == 1
    assert _SessionCloseSpy.instances[0].close_count == 1


def test_diagnostic_requests_egress_rejection_uses_shared_policy() -> None:
    """raw requests 诊断路径必须由共享 egress owner 在发送前拒绝私网。"""

    profile = diag._build_requests_profile(
        "http://127.0.0.1/internal",
        timeout_seconds=1.0,
        egress_policy=WebEgressPolicy(),
    )

    assert profile["sampled"] is False
    assert profile["outcome"] == "failed"
    assert profile["error_code"] == "blocked_by_web_egress_policy"


def test_diagnostic_playwright_public_egress_is_typed_unavailable() -> None:
    """diagnostic 公网 browser direct 不得绕过 production safe-profile gate。"""

    profile = diag._build_playwright_profile(
        "https://example.com/report",
        _options(),
        egress_policy=WebEgressPolicy(resolver=_resolve_example_public_address),
    )

    assert profile["sampled"] is False
    assert profile["outcome"] == "skipped"
    assert profile["error_code"] == "browser_egress_policy_unavailable"


def test_playwright_response_body_projection_uses_exact_bytes_and_budget() -> None:
    """browser origin-content oracle 必须使用 exact bytes，并拒绝 declared/actual 超限。"""

    assert diag._DIAGNOSTIC_HTTP_RESOURCE_BUDGET is DEFAULT_HTTP_RESOURCE_BUDGET
    assert diag._DIAGNOSTIC_BROWSER_RESOURCE_BUDGET is DEFAULT_BROWSER_RESOURCE_BUDGET
    budget = HttpResourceBudget(wire_body_bytes=4, decoded_body_bytes=4)
    exact_response = _BodyResponse(
        body=b"pdf!",
        headers={"Content-Length": "4"},
    )
    declared_too_large = _BodyResponse(
        body=b"ok",
        headers={"Content-Length": "5"},
    )
    actual_too_large = _BodyResponse(
        body=b"large",
        headers={},
    )

    assert diag._read_bounded_playwright_response_body(
        cast(diag._ResponseProtocol, exact_response),
        http_resource_budget=budget,
    ) == b"pdf!"
    with pytest.raises(diag._DiagnosticBrowserBodyLimitExceeded):
        diag._read_bounded_playwright_response_body(
            cast(diag._ResponseProtocol, declared_too_large),
            http_resource_budget=budget,
        )
    with pytest.raises(diag._DiagnosticBrowserBodyLimitExceeded):
        diag._read_bounded_playwright_response_body(
            cast(diag._ResponseProtocol, actual_too_large),
            http_resource_budget=budget,
        )


def test_comparison_bucket_matrix() -> None:
    """synthetic profile payload 应进入稳定 comparison bucket。"""

    cases: list[tuple[str, Mapping[str, JsonValue], str]] = [
        (
            "requests_only_sampled",
            _payload(
                requests_sampled=True,
                requests_ok=True,
                fetch_sampled=False,
                fetch_ok=False,
                playwright_sampled=False,
                playwright_ok=False,
            ),
            "requests_only_sampled",
        ),
        (
            "mixed_zero_sample",
            _payload(
                requests_sampled=False,
                requests_ok=False,
                fetch_sampled=False,
                fetch_ok=False,
                playwright_sampled=False,
                playwright_ok=False,
            ),
            "mixed",
        ),
        (
            "all_success_before_challenge",
            _payload(
                requests_sampled=True,
                requests_ok=True,
                fetch_sampled=True,
                fetch_ok=True,
                playwright_sampled=True,
                playwright_ok=True,
                challenge_detected=True,
            ),
            "playwright_challenge_detected",
        ),
        (
            "playwright_challenge_detected",
            _payload(
                requests_sampled=True,
                requests_ok=True,
                fetch_sampled=True,
                fetch_ok=True,
                playwright_sampled=True,
                playwright_ok=False,
                challenge_detected=True,
            ),
            "playwright_challenge_detected",
        ),
        (
            "fetch_outperforms_requests_playwright_skipped",
            _payload(
                requests_sampled=True,
                requests_ok=False,
                fetch_sampled=True,
                fetch_ok=True,
                playwright_sampled=False,
                playwright_ok=False,
            ),
            "fetch_outperforms_requests",
        ),
        (
            "fetch_only_success_narrowed_to_sampled_failures",
            _payload(
                requests_sampled=True,
                requests_ok=False,
                fetch_sampled=True,
                fetch_ok=True,
                playwright_sampled=True,
                playwright_ok=False,
            ),
            "fetch_only_success",
        ),
        (
            "requests_only_success",
            _payload(
                requests_sampled=True,
                requests_ok=True,
                fetch_sampled=True,
                fetch_ok=False,
                playwright_sampled=False,
                playwright_ok=False,
            ),
            "requests_only_success",
        ),
        (
            "browser_only_success",
            _payload(
                requests_sampled=True,
                requests_ok=False,
                fetch_sampled=True,
                fetch_ok=False,
                playwright_sampled=True,
                playwright_ok=True,
            ),
            "browser_only_success",
        ),
        (
            "requests_and_fetch_success_playwright_failed",
            _payload(
                requests_sampled=True,
                requests_ok=True,
                fetch_sampled=True,
                fetch_ok=True,
                playwright_sampled=True,
                playwright_ok=False,
            ),
            "requests_and_fetch_success_playwright_failed",
        ),
        (
            "fetch_only_failure",
            _payload(
                requests_sampled=True,
                requests_ok=True,
                fetch_sampled=True,
                fetch_ok=False,
                playwright_sampled=True,
                playwright_ok=True,
            ),
            "fetch_only_failure",
        ),
        (
            "all_failed",
            _payload(
                requests_sampled=True,
                requests_ok=False,
                fetch_sampled=True,
                fetch_ok=False,
                playwright_sampled=True,
                playwright_ok=False,
            ),
            "all_failed",
        ),
        (
            "partial_sample",
            _payload(
                requests_sampled=False,
                requests_ok=False,
                fetch_sampled=False,
                fetch_ok=False,
                playwright_sampled=True,
                playwright_ok=True,
            ),
            "partial_sample",
        ),
        (
            "child_process_error",
            {"status": "child_process_error"},
            "child_process_error",
        ),
    ]

    for case_name, payload, expected_bucket in cases:
        assert diag._classify_diagnostic_bucket(payload) == expected_bucket, case_name


def test_batch_rows_and_summary_counts(tmp_path: Path) -> None:
    """synthetic rows 应汇总路径采样、成功、challenge 与子进程异常计数。"""

    success_payload = _payload(
        requests_sampled=True,
        requests_ok=True,
        fetch_sampled=True,
        fetch_ok=True,
        playwright_sampled=True,
        playwright_ok=True,
        challenge_detected=True,
    )
    child_payload: JsonObject = {
        "status": "child_process_error",
        "comparison_bucket": "child_process_error",
        "returncode": 7,
        "stdout_length": 3,
        "stdout_digest": "sha256:" + "0" * 64,
        "stderr_length": 3,
        "stderr_digest": "sha256:" + "1" * 64,
    }
    rows = [
        diag._build_batch_result_row(
            entry=diag.DiagnosticUrlEntry(url="https://example.com/a", label="A"),
            diagnostic_path=tmp_path / "a.json",
            payload=success_payload,
            index=1,
        ),
        diag._build_batch_result_row(
            entry=diag.DiagnosticUrlEntry(url="https://example.com/b", label="B"),
            diagnostic_path=None,
            payload=child_payload,
            index=2,
        ),
    ]

    summary = diag._build_batch_summary(run_label="run", input_path=tmp_path / "urls.jsonl", rows=rows)

    assert summary["input_url_count"] == 2
    assert summary["child_process_error_count"] == 1
    assert summary["playwright_sampled_count"] == 1
    assert summary["playwright_ok_count"] == 1
    assert summary["requests_sampled_count"] == 1
    assert summary["requests_ok_count"] == 1
    assert summary["fetch_sampled_count"] == 1
    assert summary["fetch_ok_count"] == 1
    assert summary["challenge_detected_count"] == 1
    assert summary["comparison_buckets"] == {"playwright_challenge_detected": 1, "child_process_error": 1}
    assert summary["observed_buckets"] == {"playwright_challenge_detected": 1, "child_process_error": 1}
    assert summary["child_returncodes"] == {"7": 1}
    assert rows[0]["observed_bucket"] == "playwright_challenge_detected"
    assert rows[0]["evidence_path"] == str(tmp_path / "a.json")
    assert rows[0]["failure_safe_url"] == "https://example.com/a"
    assert rows[0]["diagnostic_schema_version"] == "web-diagnostics-v2"
    assert rows[1]["observed_bucket"] == "child_process_error"
    assert rows[1]["observed_failing_path"] == "diagnostic_child_process"
    assert rows[1]["evidence_path"] is None
    assert rows[1]["failure_safe_url"] == "https://example.com/b"
    assert "重新运行单 URL 诊断子进程" in str(rows[1]["diagnostic_action_hint"])
    assert summary["diagnostic_schema_version"] == "web-diagnostics-v2"
    observed_items = summary["observed_items"]
    assert isinstance(observed_items, list)
    assert len(observed_items) == 2
    action_hints = summary["diagnostic_action_hints"]
    assert isinstance(action_hints, list)
    assert len(action_hints) == 2


def test_current_fetch_adapter_completed_outcome_generates_ok_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """current ToolDefinition.callable 成功 outcome 应投影为 ok=true profile。"""

    async def fake_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolCompletedOutcome:
        """返回确定性成功 outcome。"""

        assert call.name == "fetch_web_page"
        assert context.run_id == "diagnose-web"
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "title": "Report",
                    "final_url": "https://example.com/final",
                    "fetch_backend": "requests",
                    "content": "abcdef",
                    "response_content_length": 6,
                    "response_content_digest": "sha256:" + "b" * 64,
                },
                meta=None,
            )
        )

    def fake_definition(options: diag.CliOptions) -> ToolDefinition:
        """返回 current contract 形状的工具定义。"""

        assert options.request_timeout == 1.0
        return _tool_definition(fake_callable)

    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    profile = diag._build_tool_fetch_profile("https://example.com", _options(request_timeout=1.0))

    assert profile["sampled"] is True
    assert profile["ok"] is True
    assert profile["outcome"] == "completed"
    assert profile["safe_url"] == "https://example.com/final"
    assert profile["backend"] == "requests"
    assert profile["content_length"] == 6
    assert profile["content_digest"] == "sha256:" + "b" * 64
    assert profile["projected_content_length"] == 6
    assert "abcdef" not in json.dumps(profile)


def test_docling_wrapper_records_invoked_true_and_restores_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docling wrapper 应记录实际调用证据并在诊断后恢复原 callable。"""

    def fake_docling(raw_bytes: bytes, stream_name: str) -> tuple[str, str, str]:
        """模拟原始 Docling 转换成功。"""

        assert raw_bytes == b"%PDF fixture"
        assert stream_name == "page.pdf"
        return "Fixture", "fixture markdown", "docling"

    async def fake_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolCompletedOutcome:
        """模拟 current fetch callable 进入非 HTML Docling 路径。"""

        assert call.name == "fetch_web_page"
        assert context.run_id == "diagnose-web"
        title, markdown, backend = web_tools_module._docling_convert_to_markdown(b"%PDF fixture", "page.pdf")
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "title": title,
                    "final_url": "https://example.com/report.pdf",
                    "fetch_backend": backend,
                    "content": markdown,
                },
                meta=None,
            )
        )

    def fake_definition(options: diag.CliOptions) -> ToolDefinition:
        """返回会触发 Docling callable 的工具定义。"""

        assert options.url == "https://example.com/report.pdf"
        return _tool_definition(fake_callable)

    monkeypatch.setattr(web_tools_module, "_docling_convert_to_markdown", fake_docling)
    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    profile = diag._build_tool_fetch_profile(
        "https://example.com/report.pdf",
        _options(url="https://example.com/report.pdf"),
    )

    evidence = _object_field(profile, "docling_conversion_invocation_evidence")
    assert profile["ok"] is True
    assert evidence["invoked"] is True
    assert evidence["stream_name"] == "page.pdf"
    assert evidence["raw_bytes_length"] == len(b"%PDF fixture")
    assert evidence["target_module"] == "dayu.tools.web.web_tools"
    assert evidence["target_function"] == "_docling_convert_to_markdown"
    assert evidence["original_completed"] is True
    assert evidence["original_exception_type"] == ""
    assert evidence["docling_runtime_initialization_error"] is False
    assert evidence["safe_url"] == "https://example.com/report.pdf"
    assert web_tools_module._docling_convert_to_markdown is fake_docling


def test_html_fetch_profile_records_docling_invoked_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTML 成功路径未触发 Docling 时应显式记录 invoked=false。"""

    async def fake_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolCompletedOutcome:
        """模拟 HTML fetch 成功且不调用 Docling。"""

        assert call.name == "fetch_web_page"
        assert context.timeout_seconds == 2.0
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "title": "HTML",
                    "final_url": "https://example.com/page",
                    "fetch_backend": "requests",
                    "content": "html markdown",
                },
                meta=None,
            )
        )

    def fake_definition(options: diag.CliOptions) -> ToolDefinition:
        """返回不触发 Docling 的工具定义。"""

        assert options.url == "https://example.com/page"
        return _tool_definition(fake_callable)

    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    profile = diag._build_tool_fetch_profile(
        "https://example.com/page",
        _options(url="https://example.com/page"),
    )

    evidence = _object_field(profile, "docling_conversion_invocation_evidence")
    assert profile["ok"] is True
    assert evidence["invoked"] is False
    assert evidence["stream_name"] == ""
    assert evidence["raw_bytes_length"] is None
    assert evidence["original_completed"] is False
    assert evidence["docling_runtime_initialization_error"] is False


def test_pdf_fetch_success_without_docling_invocation_keeps_failure_evidence_for_smoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF fetch 成功但 wrapper 未被调用时，应留下 invoked=false 供 smoke 判失败。"""

    async def fake_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolCompletedOutcome:
        """模拟 PDF URL 成功返回但没有进入 Docling callable。"""

        assert call.arguments == {"url": "https://example.com/report.pdf"}
        assert context.cancellation_token.is_cancelled() is False
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "title": "PDF",
                    "final_url": "https://example.com/report.pdf",
                    "fetch_backend": "requests",
                    "content": "pdf markdown",
                },
                meta=None,
            )
        )

    def fake_definition(options: diag.CliOptions) -> ToolDefinition:
        """返回未触发 Docling 的 PDF 工具定义。"""

        assert options.url == "https://example.com/report.pdf"
        return _tool_definition(fake_callable)

    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    profile = diag._build_tool_fetch_profile(
        "https://example.com/report.pdf",
        _options(url="https://example.com/report.pdf"),
    )
    evidence = _object_field(profile, "docling_conversion_invocation_evidence")

    assert profile["ok"] is True
    assert profile["content_length"] == len("pdf markdown")
    assert evidence["invoked"] is False
    assert evidence["safe_url"] == "https://example.com/report.pdf"


def test_docling_runtime_initialization_exception_becomes_skip_observed_item(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Docling 初始化异常应进入 skip observed items，并保留 wrapper 异常证据。"""

    def fake_docling(raw_bytes: bytes, stream_name: str) -> tuple[str, str, str]:
        """模拟 Docling 初始化失败。"""

        assert raw_bytes == b"%PDF fixture"
        assert stream_name == "page.pdf"
        raise DoclingRuntimeInitializationError("docling runtime missing")

    async def fake_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolCompletedOutcome:
        """调用 Docling 后让初始化异常透传到诊断边界。"""

        assert call.name == "fetch_web_page"
        assert context.run_id == "diagnose-web"
        web_tools_module._docling_convert_to_markdown(b"%PDF fixture", "page.pdf")
        raise AssertionError("Docling 初始化异常应在上一行透传。")

    def fake_definition(options: diag.CliOptions) -> ToolDefinition:
        """返回会触发 Docling 初始化异常的工具定义。"""

        assert options.url == "https://example.com/report.pdf"
        return _tool_definition(fake_callable)

    monkeypatch.setattr(web_tools_module, "_docling_convert_to_markdown", fake_docling)
    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    profile = diag._build_tool_fetch_profile(
        "https://example.com/report.pdf",
        _options(url="https://example.com/report.pdf"),
    )
    evidence = _object_field(profile, "docling_conversion_invocation_evidence")
    payload = _payload(
        requests_sampled=True,
        requests_ok=True,
        fetch_sampled=True,
        fetch_ok=False,
        playwright_sampled=False,
        playwright_ok=False,
    )
    payload["fetch_web_page_profile"] = profile
    payload["docling_conversion_invocation_evidence"] = evidence
    row = diag._build_batch_result_row(
        entry=diag.DiagnosticUrlEntry(url="https://example.com/report.pdf", label="PDF"),
        diagnostic_path=tmp_path / "pdf.json",
        payload=payload,
        index=1,
    )
    summary = diag._build_batch_summary(run_label="run", input_path=tmp_path / "urls.jsonl", rows=[row])

    assert profile["outcome"] == "failed"
    assert profile["error_code"] == "callable_exception"
    assert evidence["invoked"] is True
    assert evidence["original_completed"] is False
    assert evidence["original_exception_type"] == "DoclingRuntimeInitializationError"
    assert evidence["docling_runtime_initialization_error"] is True
    assert row["observed_bucket"] == "docling_runtime_initialization_error"
    assert row["observed_failing_path"] == "docling_conversion"
    skip_items = summary["skip_observed_items"]
    assert isinstance(skip_items, list)
    assert len(skip_items) == 1
    assert summary["observed_buckets"] == {"docling_runtime_initialization_error": 1}
    assert web_tools_module._docling_convert_to_markdown is fake_docling


def test_generic_docling_conversion_exception_is_not_skip_observed_item(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """普通 Docling 转换异常只能作为失败事实，不能归为环境 skip。"""

    def fake_docling(raw_bytes: bytes, stream_name: str) -> tuple[str, str, str]:
        """模拟普通转换失败。"""

        assert raw_bytes == b"%PDF fixture"
        assert stream_name == "page.pdf"
        raise RuntimeError("conversion failed")

    async def fake_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolCompletedOutcome:
        """调用 Docling 后让普通转换异常透传到诊断边界。"""

        assert call.name == "fetch_web_page"
        assert context.timeout_seconds == 2.0
        web_tools_module._docling_convert_to_markdown(b"%PDF fixture", "page.pdf")
        raise AssertionError("普通转换异常应在上一行透传。")

    def fake_definition(options: diag.CliOptions) -> ToolDefinition:
        """返回会触发普通 Docling 转换异常的工具定义。"""

        assert options.url == "https://example.com/report.pdf"
        return _tool_definition(fake_callable)

    monkeypatch.setattr(web_tools_module, "_docling_convert_to_markdown", fake_docling)
    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    profile = diag._build_tool_fetch_profile(
        "https://example.com/report.pdf",
        _options(url="https://example.com/report.pdf"),
    )
    evidence = _object_field(profile, "docling_conversion_invocation_evidence")
    payload = _payload(
        requests_sampled=True,
        requests_ok=True,
        fetch_sampled=True,
        fetch_ok=False,
        playwright_sampled=False,
        playwright_ok=False,
    )
    payload["fetch_web_page_profile"] = profile
    payload["docling_conversion_invocation_evidence"] = evidence
    row = diag._build_batch_result_row(
        entry=diag.DiagnosticUrlEntry(url="https://example.com/report.pdf", label="PDF"),
        diagnostic_path=tmp_path / "pdf.json",
        payload=payload,
        index=1,
    )
    summary = diag._build_batch_summary(run_label="run", input_path=tmp_path / "urls.jsonl", rows=[row])

    assert evidence["invoked"] is True
    assert evidence["original_exception_type"] == "RuntimeError"
    assert evidence["docling_runtime_initialization_error"] is False
    assert row["observed_bucket"] == "requests_only_success"
    assert row["observed_failing_path"] == "fetch_web_page"
    skip_items = summary["skip_observed_items"]
    assert isinstance(skip_items, list)
    assert skip_items == []


def test_current_fetch_adapter_failed_outcome_generates_business_readable_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """current ToolDefinition.callable 失败 outcome 应保留错误、hint 和诊断来源。"""

    async def fake_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolFailedOutcome:
        """返回确定性失败 outcome。"""

        assert call.name == "fetch_web_page"
        assert context.cancellation_token.is_cancelled() is False
        return ToolFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error="blocked_by_site_policy",
                message="Target site blocked automated access.",
                hint="[change_source] Use another source.",
                meta=None,
            )
        )

    def fake_definition(options: diag.CliOptions) -> ToolDefinition:
        """返回 current contract 形状的工具定义。"""

        assert options.tool_timeout_budget == 3.0
        return _tool_definition(fake_callable)

    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    profile = diag._build_tool_fetch_profile("https://example.com", _options(tool_timeout_budget=3.0))

    assert profile["sampled"] is True
    assert profile["ok"] is False
    assert profile["outcome"] == "failed"
    assert profile["error_code"] == "blocked_by_site_policy"
    assert profile["error_message"] == "Target site blocked automated access."
    assert profile["next_action"] == "change_source"
    diagnostics = _object_field(profile, "diagnostics")
    assert diagnostics["diagnostic_source"] == "current_tool_failed_outcome"
    assert diagnostics["error_code"] == "blocked_by_site_policy"


def test_cli_single_mode_writes_deterministic_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """CLI 单 URL 模式应在 monkeypatch 采样路径后写出确定性 JSON。"""

    output_path = tmp_path / "single.json"
    monkeypatch.setattr(diag, "_utc_now_iso", _fixed_now)
    monkeypatch.setattr(diag, "_build_requests_profile", _fake_requests_profile)
    monkeypatch.setattr(diag, "_build_tool_fetch_profile", _fake_fetch_profile)
    monkeypatch.setattr(diag, "_build_playwright_profile", _fake_playwright_profile)

    exit_code = diag.main(
        [
            "--url",
            "https://example.com",
            "--output",
            str(output_path),
        ]
    )

    payload = _load_json_object(output_path)
    assert exit_code == 0
    assert payload["schema_version"] == "web-diagnostics-v2"
    assert payload["diagnostic_schema_version"] == "web-diagnostics-v2"
    assert payload["diagnostic_schema_revision"] == 2
    assert payload["generated_at"] == "2026-06-09T00:00:00+00:00"
    assert payload["comparison_bucket"] == "all_success"
    evidence = _object_field(payload, "docling_conversion_invocation_evidence")
    assert evidence["invoked"] is False
    assert evidence["safe_url"] == "https://example.com/"


def test_cli_requires_exactly_one_url_mode(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """CLI 应在 --url 与 --url-file 同时提供或同时缺失时清晰失败。"""

    url_file = tmp_path / "urls.txt"
    url_file.write_text("https://example.com\n", encoding="utf-8")

    conflict_exit_code = diag.main(["--url", "https://example.com", "--url-file", str(url_file)])
    conflict_output = capsys.readouterr()
    missing_exit_code = diag.main([])
    missing_output = capsys.readouterr()

    assert conflict_exit_code == 2
    assert "--url 与 --url-file 不能同时提供" in conflict_output.err
    assert missing_exit_code == 2
    assert "必须提供 --url 或 --url-file 其中一个" in missing_output.err


def test_cli_batch_mode_uses_monkeypatched_child_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """CLI 批量模式应允许替换子进程执行，避免真实网络和浏览器。"""

    url_file = tmp_path / "urls.jsonl"
    url_file.write_text(
        "\n".join(
            (
                json.dumps({"url": "https://example.com/a", "label": "A"}),
                json.dumps({"url": "https://example.com/b", "label": "B"}),
            )
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "batch"

    def fake_run(
        command: Sequence[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        """模拟批量子进程，首条成功写 JSON，第二条返回错误。"""

        assert capture_output is True
        assert text is True
        assert check is False
        command_parts = list(command)
        output_index = command_parts.index("--output") + 1
        url_index = command_parts.index("--url") + 1
        diagnostic_path = Path(command_parts[output_index])
        url = command_parts[url_index]
        if url.endswith("/b"):
            return subprocess.CompletedProcess(command_parts, 9, stdout="child out", stderr="child err")
        diag._write_json(
            diagnostic_path,
            _payload(
                requests_sampled=True,
                requests_ok=True,
                fetch_sampled=True,
                fetch_ok=True,
                playwright_sampled=False,
                playwright_ok=False,
            ),
        )
        return subprocess.CompletedProcess(command_parts, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(diag, "_utc_now_iso", _fixed_now)

    exit_code = diag.main(
        [
            "--url-file",
            str(url_file),
            "--batch-output-dir",
            str(output_dir),
            "--run-label",
            "deterministic",
            "--skip-playwright",
        ]
    )

    results = [
        _load_json_object_from_text(line)
        for line in (output_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    summary = _load_json_object(output_dir / "summary.json")
    assert exit_code == 0
    assert len(results) == 2
    assert results[0]["comparison_bucket"] == "partial_sample"
    assert results[1]["comparison_bucket"] == "child_process_error"
    assert summary["input_url_count"] == 2
    assert summary["child_process_error_count"] == 1
    assert summary["child_returncodes"] == {"9": 1}


def test_diagnose_web_access_does_not_import_old_web_or_ui_paths() -> None:
    """诊断脚本不得恢复 OLD registry、truncation、fetch_more、dayu.web 或 UI 路径。"""

    tree = ast.parse(_DIAGNOSE_SCRIPT.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)

    for forbidden in _FORBIDDEN_IMPORTS:
        assert forbidden not in imports


def _options(
    *,
    url: str = "https://example.com",
    url_file: str = "",
    output: str = "",
    batch_output_dir: str = "",
    run_label: str = "",
    request_timeout: float = 1.0,
    tool_timeout_budget: float = 2.0,
    playwright_timeout: float = 1.0,
    playwright_channel: str = "chrome",
    headed: bool = False,
    manual_wait_seconds: float = 0.0,
    pause_before_snapshot: bool = False,
    storage_state_in: str = "",
    storage_state_out: str = "",
    storage_state_dir: str = "",
    storage_state_ttl_seconds: int = 0,
    skip_playwright: bool = False,
    skip_requests: bool = False,
    skip_tool_fetch: bool = False,
    max_network: int = 3,
    fetch_truncate_chars: int = 1000,
    allow_private_network_url: bool = False,
) -> diag.CliOptions:
    """构造测试用 CLI 选项。"""

    return diag.CliOptions(
        url=url,
        url_file=url_file,
        output=output,
        batch_output_dir=batch_output_dir,
        run_label=run_label,
        request_timeout=request_timeout,
        tool_timeout_budget=tool_timeout_budget,
        playwright_timeout=playwright_timeout,
        playwright_channel=playwright_channel,
        headed=headed,
        manual_wait_seconds=manual_wait_seconds,
        pause_before_snapshot=pause_before_snapshot,
        storage_state_in=storage_state_in,
        storage_state_out=storage_state_out,
        storage_state_dir=storage_state_dir,
        storage_state_ttl_seconds=storage_state_ttl_seconds,
        skip_playwright=skip_playwright,
        skip_requests=skip_requests,
        skip_tool_fetch=skip_tool_fetch,
        max_network=max_network,
        fetch_truncate_chars=fetch_truncate_chars,
        allow_private_network_url=allow_private_network_url,
    )


def _payload(
    *,
    requests_sampled: bool,
    requests_ok: bool,
    fetch_sampled: bool,
    fetch_ok: bool,
    playwright_sampled: bool,
    playwright_ok: bool,
    challenge_detected: bool = False,
) -> JsonObject:
    """构造 synthetic 单 URL 诊断 payload。"""

    def profile(
        *,
        sampled: bool,
        completed: bool,
        backend: str,
        safe_url: str,
    ) -> JsonObject:
        """构造 schema v2 path profile。"""

        outcome = "completed" if completed else "failed" if sampled else "skipped"
        result: JsonObject = {
            "stage": backend,
            "sampled": sampled,
            "outcome": outcome,
            "ok": completed,
            "safe_url": safe_url,
            "elapsed_seconds": 0.1,
            "backend": backend,
        }
        if completed:
            result.update(
                {
                    "content_length": 8,
                    "content_digest": "sha256:" + "a" * 64,
                    "http_status": 200,
                }
            )
        elif sampled:
            result["error_code"] = f"{backend}_failed"
        return result

    payload: JsonObject = {
        "schema_version": "web-diagnostics-v2",
        "diagnostic_schema_version": "web-diagnostics-v2",
        "diagnostic_schema_revision": 2,
        "safe_url": "https://example.com/",
        "requests_profile": profile(
            sampled=requests_sampled,
            completed=requests_ok,
            backend="requests",
            safe_url="https://example.com/requests",
        ),
        "fetch_web_page_profile": profile(
            sampled=fetch_sampled,
            completed=fetch_ok,
            backend="tool",
            safe_url="https://example.com/fetch",
        ),
        "playwright_profile": profile(
            sampled=playwright_sampled,
            completed=playwright_ok,
            backend="playwright",
            safe_url="https://example.com/browser",
        ),
    }
    playwright_profile = cast(JsonObject, payload["playwright_profile"])
    playwright_profile["challenge_decision"] = "confirmed" if challenge_detected else "none"
    playwright_profile["challenge_signals"] = ["challenge"] if challenge_detected else []
    payload["comparison_bucket"] = diag._classify_diagnostic_bucket(payload)
    return payload


def _tool_definition(callable_value: ToolCallable) -> ToolDefinition:
    """构造 fetch_web_page ToolDefinition。"""

    schema = ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="fetch_web_page",
            description="Fetch a page.",
            parameters=ToolParametersSchema(
                type="object",
                properties={"url": {"type": "string"}},
                required=("url",),
                additional_properties=False,
            ),
        ),
    )
    return ToolDefinition(
        name="fetch_web_page",
        schema=schema,
        callable=callable_value,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=None,
        tags=("web",),
    )


def _fixed_now() -> str:
    """返回固定诊断时间。"""

    return "2026-06-09T00:00:00+00:00"


def _fake_requests_profile(
    url: str,
    *,
    timeout_seconds: float,
    egress_policy: WebEgressPolicy,
) -> JsonObject:
    """返回确定性 requests profile。"""

    assert url == "https://example.com"
    assert timeout_seconds > 0
    assert egress_policy.allows_private_network is False
    return cast(JsonObject, _payload(
        requests_sampled=True,
        requests_ok=True,
        fetch_sampled=False,
        fetch_ok=False,
        playwright_sampled=False,
        playwright_ok=False,
    )["requests_profile"])


def _fake_fetch_profile(url: str, options: diag.CliOptions) -> JsonObject:
    """返回确定性 fetch profile。"""

    assert url == "https://example.com"
    assert options.url == "https://example.com"
    return cast(JsonObject, _payload(
        requests_sampled=False,
        requests_ok=False,
        fetch_sampled=True,
        fetch_ok=True,
        playwright_sampled=False,
        playwright_ok=False,
    )["fetch_web_page_profile"])


def _object_value(value: JsonValue) -> JsonObject:
    """把 JSON 值收窄为 JSON 对象。"""

    assert isinstance(value, Mapping)
    return {str(key): item for key, item in value.items()}


def _fake_playwright_profile(
    url: str,
    options: diag.CliOptions,
    *,
    egress_policy: WebEgressPolicy,
) -> JsonObject:
    """返回确定性 Playwright profile。"""

    assert url == "https://example.com"
    assert options.url == "https://example.com"
    assert egress_policy.allows_private_network is False
    return cast(JsonObject, _payload(
        requests_sampled=False,
        requests_ok=False,
        fetch_sampled=False,
        fetch_ok=False,
        playwright_sampled=True,
        playwright_ok=True,
    )["playwright_profile"])


def _load_json_object(path: Path) -> JsonObject:
    """读取 JSON 对象文件。"""

    return _load_json_object_from_text(path.read_text(encoding="utf-8"))


def _load_json_object_from_text(text: str) -> JsonObject:
    """从文本读取 JSON 对象。"""

    payload = cast(JsonValue, json.loads(text))
    assert isinstance(payload, Mapping)
    return {str(key): value for key, value in payload.items()}


def _object_field(payload: Mapping[str, JsonValue], key: str) -> JsonObject:
    """读取 JSON 对象字段。"""

    value = payload.get(key)
    assert isinstance(value, Mapping)
    return {str(nested_key): nested_value for nested_key, nested_value in value.items()}
