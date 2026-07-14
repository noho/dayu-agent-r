"""Web access diagnostics utility 的确定性测试。"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
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
from dayu.tools.web import provider as web_provider
from dayu.tools.web import web_http_session
from dayu.tools.web import web_tools as web_tools_module
from dayu.tools.web.web_egress_policy import WebEgressPolicy
from dayu.tools.web.web_resource_budget import (
    DEFAULT_BROWSER_RESOURCE_BUDGET,
    DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
    DEFAULT_HTTP_RESOURCE_BUDGET,
    DiagnosticResourceBudget,
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
    transport_policy: web_http_session.WebHttpTransportPolicy,
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
        transport_policy: provider parser 产生的 HTTP transport 策略快照。
        stream: 是否流式读取。
        cancellation_token: 取消令牌。

    Returns:
        不返回；始终抛出请求异常。

    Raises:
        requests.Timeout: 始终抛出，用于验证异常路径 cleanup。
    """

    del session, method, url, timeout, headers, normalize_url_for_http, egress_policy
    del transport_policy, stream, cancellation_token
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


def test_storage_state_dir_only_flows_to_provider_config(tmp_path: Path) -> None:
    """storage state 目录只进入 production resolver 配置，不派生 raw 输入。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: utility 重新从目录推导 host 文件名时抛出。
    """

    storage_dir = tmp_path / "state"
    storage_dir.mkdir()
    host_state = storage_dir / "dayu-web-diagnostic-storage-state-example.com.json"
    host_state.write_text('{"cookies":[]}', encoding="utf-8")
    options = _options(storage_state_dir=str(storage_dir))

    provider_config = diag._provider_config(options)
    storage_state_input = diag._resolve_explicit_storage_state_input(
        options.storage_state_in
    )

    assert provider_config["playwright_storage_state_dir"] == str(
        storage_dir.resolve()
    )
    assert storage_state_input is None


def test_explicit_storage_state_input_reads_valid_json_object(tmp_path: Path) -> None:
    """显式 storage state 输入必须读取合法 JSON object 常规文件。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 合法输入未解析为同一绝对文件路径时抛出。
    """

    input_path = tmp_path / "storage-state.json"
    input_path.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    resolved = diag._resolve_explicit_storage_state_input(str(input_path))

    assert resolved == input_path.resolve()


@pytest.mark.parametrize("path_kind", ("missing", "directory"))
def test_explicit_storage_state_input_rejects_missing_or_non_file(
    tmp_path: Path,
    path_kind: str,
) -> None:
    """显式 storage state 输入缺失或不是常规文件时必须 fail fast。

    Args:
        tmp_path: pytest 临时目录。
        path_kind: 待构造的非法路径类别。

    Returns:
        无。

    Raises:
        AssertionError: 非常规文件未触发 ValueError 时抛出。
    """

    input_path = tmp_path / path_kind
    if path_kind == "directory":
        input_path.mkdir()

    with pytest.raises(ValueError, match="存在的常规文件"):
        diag._resolve_explicit_storage_state_input(str(input_path))


@pytest.mark.parametrize("payload_text", ("{", "[]", "null"))
def test_explicit_storage_state_input_rejects_invalid_json_shape(
    tmp_path: Path,
    payload_text: str,
) -> None:
    """显式 storage state 输入必须拒绝非法 JSON 或非 object 根值。

    Args:
        tmp_path: pytest 临时目录。
        payload_text: 待写入的非法 JSON 或错误根值。

    Returns:
        无。

    Raises:
        AssertionError: 非法输入未触发 ValueError 时抛出。
    """

    input_path = tmp_path / "storage-state.json"
    input_path.write_text(payload_text, encoding="utf-8")

    with pytest.raises(ValueError, match="JSON"):
        diag._resolve_explicit_storage_state_input(str(input_path))


def test_diagnostic_artifact_only_projects_storage_state_input_fact(
    tmp_path: Path,
) -> None:
    """诊断 artifact 只投影显式输入事实，不得残留 lifecycle 字段。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: artifact 出现 lifecycle authority 字段时抛出。
    """

    input_path = tmp_path / "storage-state.json"
    input_path.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    payload = diag._build_single_diagnostic_payload(
        _options(
            storage_state_in=str(input_path),
            skip_requests=True,
            skip_tool_fetch=True,
            skip_playwright=True,
        )
    )
    playwright_profile = _object_field(payload, "playwright_profile")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert playwright_profile["storage_state"] == {"input_used": True}
    for forbidden in (
        "output_enabled",
        "output_label",
        "ttl_seconds",
        "published",
        "reconcile",
        "cleanup",
    ):
        assert forbidden not in serialized


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


def test_single_diagnostic_packaged_defaults_allow_private_custom_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """diagnostic 必须消费 packaged typed private/custom-port true 默认值。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: utility 未从唯一 parser 取得完整 typed 默认值时抛出。
    """

    authorized_ports: list[int] = []

    def fake_build_requests_profile(
        url: str,
        *,
        timeout_seconds: float,
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        diagnostic_resource_budget: DiagnosticResourceBudget,
    ) -> JsonObject:
        """在 utility policy construction boundary 验证 custom-port 授权。

        Args:
            url: 待诊断 URL。
            timeout_seconds: 当前请求超时秒数。
            egress_policy: utility 构造的 Web 出站策略。
            transport_policy: provider parser 产生的 HTTP transport 策略快照。
            diagnostic_resource_budget: provider parser 产生的诊断预算。

        Returns:
            完成授权后的确定性 skipped profile。

        Raises:
            WebEgressPolicyError: URL 未被当前出站策略授权时抛出。
        """

        del timeout_seconds, transport_policy
        assert diagnostic_resource_budget == DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET
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
            skip_tool_fetch=True,
            skip_playwright=True,
        )
    )

    assert authorized_ports == [43117]
    assert payload["safe_url"] == "http://127.0.0.1:43117/fixture.pdf"


@pytest.mark.parametrize(
    ("raw_provider_config", "expected_error"),
    (
        ({"allow_private_network_url": False, "allow_custom_port_url": True}, "not allowed"),
        ({"allow_private_network_url": True, "allow_custom_port_url": False}, "port"),
    ),
)
def test_single_diagnostic_private_and_custom_port_denies_are_independent(
    monkeypatch: pytest.MonkeyPatch,
    raw_provider_config: JsonObject,
    expected_error: str,
) -> None:
    """显式 private/custom-port deny 必须经 typed provider parser 独立生效。

    Args:
        monkeypatch: pytest 属性替换夹具。
        raw_provider_config: 仅关闭一个出站维度的 provider overlay。
        expected_error: 期望错误消息包含的维度文本。

    Returns:
        无。

    Raises:
        AssertionError: 两个独立 typed 开关被重新耦合时抛出。
    """

    def fake_provider_config(options: diag.CliOptions) -> JsonObject:
        """返回显式 typed deny overlay。

        Args:
            options: 当前 CLI 选项。

        Returns:
            测试提供的 raw provider 配置。

        Raises:
            无。
        """

        del options
        return raw_provider_config

    def authorize_in_requests_profile(
        url: str,
        *,
        timeout_seconds: float,
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        diagnostic_resource_budget: DiagnosticResourceBudget,
    ) -> JsonObject:
        """在 raw requests 边界触发本次 typed 出站裁决。

        Args:
            url: 待诊断 URL。
            timeout_seconds: 当前请求超时。
            egress_policy: 唯一 parser 配置产生的出站策略。
            transport_policy: 唯一 parser 配置产生的 transport 策略。
            diagnostic_resource_budget: 唯一 parser 配置产生的诊断预算。

        Returns:
            授权成功时的 synthetic profile；本测试预期不返回。

        Raises:
            ValueError: 当前独立 deny 拒绝本地 custom-port URL 时抛出。
        """

        del timeout_seconds, transport_policy, diagnostic_resource_budget
        egress_policy.authorize_http_target(url, stage="diagnostic_test")
        return diag._skipped_profile(
            "unexpected_authorization",
            url=url,
            backend=diag.WebDiagnosticBackend.REQUESTS,
        )

    monkeypatch.setattr(diag, "_provider_config", fake_provider_config)
    monkeypatch.setattr(diag, "_build_requests_profile", authorize_in_requests_profile)

    with pytest.raises(ValueError, match=expected_error):
        diag._build_single_diagnostic_payload(
            _options(
                url="http://127.0.0.1:43117/fixture.pdf",
                skip_tool_fetch=True,
                skip_playwright=True,
            )
        )


def test_requests_profile_forwards_provider_owned_transport_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """single diagnostic 必须传播 provider parser 产生的 transport 快照。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: raw mapping 未同源传播或 transport 值被重建时抛出。
    """

    raw_provider_config: JsonObject = {
        "dns_peer_proof_enabled": True,
        "allow_environment_proxy": False,
    }
    observed_transport_policies: list[web_http_session.WebHttpTransportPolicy] = []
    observed_diagnostic_budgets: list[DiagnosticResourceBudget] = []
    observed_discovery_configs: list[Mapping[str, JsonValue]] = []
    provider_config_calls = 0

    def fake_provider_config(options: diag.CliOptions) -> JsonObject:
        """返回含非默认 transport 组合的 raw provider 配置。

        Args:
            options: single diagnostic CLI 选项。

        Returns:
            由测试固定的 raw provider 配置对象。

        Raises:
            无。
        """

        nonlocal provider_config_calls
        del options
        provider_config_calls += 1
        return raw_provider_config

    def fake_build_requests_profile(
        url: str,
        *,
        timeout_seconds: float,
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        diagnostic_resource_budget: DiagnosticResourceBudget,
    ) -> JsonObject:
        """记录 raw requests caller 收到的 typed transport 快照。

        Args:
            url: 待诊断 URL。
            timeout_seconds: requests 超时秒数。
            egress_policy: utility 构造的 Web 出站策略。
            transport_policy: provider parser 产生的 transport 策略快照。
            diagnostic_resource_budget: provider parser 产生的 diagnostic 快照。

        Returns:
            确定性 skipped profile。

        Raises:
            无。
        """

        del timeout_seconds, egress_policy
        observed_transport_policies.append(transport_policy)
        observed_diagnostic_budgets.append(diagnostic_resource_budget)
        return diag._skipped_profile(
            "synthetic_requests",
            url=url,
            backend=diag.WebDiagnosticBackend.REQUESTS,
        )

    def fake_build_tool_fetch_profile(
        url: str,
        options: diag.CliOptions,
        *,
        provider_config: Mapping[str, JsonValue],
        diagnostic_resource_budget: DiagnosticResourceBudget,
    ) -> JsonObject:
        """记录 provider discovery 将继续消费的同一 raw mapping。

        Args:
            url: 待诊断 URL。
            options: single diagnostic CLI 选项。
            provider_config: orchestration 传给 discovery 的 raw provider 配置。
            diagnostic_resource_budget: provider parser 产生的 diagnostic 快照。

        Returns:
            确定性 skipped profile。

        Raises:
            无。
        """

        del options
        observed_diagnostic_budgets.append(diagnostic_resource_budget)
        observed_discovery_configs.append(provider_config)
        return diag._skipped_profile(
            "synthetic_tool_fetch",
            url=url,
            backend=diag.WebDiagnosticBackend.TOOL,
        )

    monkeypatch.setattr(diag, "_provider_config", fake_provider_config)
    monkeypatch.setattr(diag, "_build_requests_profile", fake_build_requests_profile)
    monkeypatch.setattr(diag, "_build_tool_fetch_profile", fake_build_tool_fetch_profile)

    diag._build_single_diagnostic_payload(
        _options(
            url="https://example.com/report",
            skip_playwright=True,
        )
    )

    assert provider_config_calls == 1
    expected_transport_policy = web_provider._parse_config(
        raw_provider_config
    ).transport_policy
    assert expected_transport_policy.dns_peer_proof_enabled is True
    assert expected_transport_policy.allow_environment_proxy is False
    assert observed_transport_policies == [expected_transport_policy]
    assert observed_diagnostic_budgets == [
        DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
        DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
    ]
    assert observed_discovery_configs == [raw_provider_config]
    assert observed_discovery_configs[0] is raw_provider_config


@pytest.mark.parametrize(
    ("max_network", "expected_events"),
    ((None, 13), (7, 7)),
)
def test_single_diagnostic_uses_typed_budget_default_and_run_override(
    monkeypatch: pytest.MonkeyPatch,
    max_network: int | None,
    expected_events: int,
) -> None:
    """缺省 events 与显式 override 必须形成同源 typed diagnostic value。

    Args:
        monkeypatch: pytest 属性替换夹具。
        max_network: 可选的本次 CLI override。
        expected_events: raw profile 应收到的 typed events 值。

    Returns:
        无。

    Raises:
        AssertionError: utility 复制默认或丢失 error chars owner 时抛出。
    """

    raw_provider_config: JsonObject = {
        "resource_budget": {
            "diagnostics": {"error_chars": 37, "events": 13}
        }
    }
    observed_budgets: list[DiagnosticResourceBudget] = []

    def fake_provider_config(options: diag.CliOptions) -> JsonObject:
        """返回含非默认 diagnostic child budget 的 raw 配置。

        Args:
            options: 当前 CLI 选项。

        Returns:
            测试固定的 raw provider 配置。

        Raises:
            无。
        """

        del options
        return raw_provider_config

    def capture_requests_profile(
        url: str,
        *,
        timeout_seconds: float,
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        diagnostic_resource_budget: DiagnosticResourceBudget,
    ) -> JsonObject:
        """记录 raw requests 收到的 typed diagnostic child budget。

        Args:
            url: 待诊断 URL。
            timeout_seconds: 当前请求超时。
            egress_policy: 本次 typed 出站策略。
            transport_policy: 本次 typed transport 策略。
            diagnostic_resource_budget: 本次 typed diagnostic child budget。

        Returns:
            synthetic skipped profile。

        Raises:
            无。
        """

        del timeout_seconds, egress_policy, transport_policy
        observed_budgets.append(diagnostic_resource_budget)
        return diag._skipped_profile(
            "synthetic_budget_capture",
            url=url,
            backend=diag.WebDiagnosticBackend.REQUESTS,
        )

    monkeypatch.setattr(diag, "_provider_config", fake_provider_config)
    monkeypatch.setattr(diag, "_build_requests_profile", capture_requests_profile)

    diag._build_single_diagnostic_payload(
        _options(
            max_network=max_network,
            skip_tool_fetch=True,
            skip_playwright=True,
        )
    )

    assert observed_budgets == [
        DiagnosticResourceBudget(error_chars=37, events=expected_events)
    ]


def test_cli_max_network_absent_is_none_and_invalid_override_fails() -> None:
    """CLI 缺省不得复制 events 默认，非正 override 必须由 typed value 拒绝。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: CLI 恢复本地默认或 typed validation 未执行时抛出。
    """

    options = diag._parse_options(["--url", "https://example.com"])

    assert options.max_network is None
    for invalid_value in (0, -1):
        with pytest.raises(ValueError, match="positive integer"):
            diag._build_single_diagnostic_payload(
                _options(
                    max_network=invalid_value,
                    skip_requests=True,
                    skip_tool_fetch=True,
                    skip_playwright=True,
                )
            )


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
        transport_policy: web_http_session.WebHttpTransportPolicy,
        stream: bool,
        cancellation_token: CancellationToken | None,
    ) -> tuple[web_http_session.AuthorizedResponseLease, int, tuple[str, ...]]:
        """返回确定性 diagnostic response lease。

        Args:
            session: 当前 diagnostic 局部 Session。
            method: HTTP 方法。
            url: 请求 URL。
            timeout: 超时秒数。
            headers: 请求头。
            normalize_url_for_http: URL 规范化函数。
            egress_policy: 当前 Web 出站策略。
            transport_policy: provider parser 产生的 HTTP transport 策略快照。
            stream: 是否流式读取。
            cancellation_token: 取消令牌。

        Returns:
            确定性 response lease、redirect 次数与访问 URL 序列。

        Raises:
            无。
        """

        del session, headers, normalize_url_for_http, egress_policy, transport_policy
        del cancellation_token
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
        transport_policy=web_provider._parse_config({}).transport_policy,
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
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
        transport_policy=web_provider._parse_config({}).transport_policy,
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
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
        transport_policy=web_provider._parse_config({}).transport_policy,
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
    )

    assert profile["sampled"] is False
    assert profile["outcome"] == "failed"
    assert profile["error_code"] == "blocked_by_web_egress_policy"


def test_diagnostic_playwright_private_egress_rejection_precedes_browser() -> None:
    """raw Playwright 必须在启动 browser 前保留共享 private egress 拒绝。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: browser 绕过 typed egress owner 时抛出。
    """

    profile = diag._build_playwright_profile(
        "http://127.0.0.1/report",
        _options(),
        egress_policy=WebEgressPolicy(),
        storage_state_input=None,
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
    )

    assert profile["sampled"] is False
    assert profile["outcome"] == "failed"
    assert profile["error_code"] == "blocked_by_web_egress_policy"
    assert profile["storage_state"] == {"input_used": False}


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

    def fake_definition(provider_config: Mapping[str, JsonValue]) -> ToolDefinition:
        """返回 current contract 形状的工具定义。

        Args:
            provider_config: single diagnostic 交给 provider discovery 的 raw 配置。

        Returns:
            确定性 fetch 工具定义。

        Raises:
            无。
        """

        assert provider_config["request_timeout_seconds"] == 1.0
        return _tool_definition(fake_callable)

    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    options = _options(request_timeout=1.0)
    profile = diag._build_tool_fetch_profile(
        "https://example.com",
        options,
        provider_config=diag._provider_config(options),
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
    )

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

    def fake_definition(provider_config: Mapping[str, JsonValue]) -> ToolDefinition:
        """返回会触发 Docling callable 的工具定义。

        Args:
            provider_config: single diagnostic 交给 provider discovery 的 raw 配置。

        Returns:
            确定性 fetch 工具定义。

        Raises:
            无。
        """

        assert provider_config["request_timeout_seconds"] == 1.0
        return _tool_definition(fake_callable)

    monkeypatch.setattr(web_tools_module, "_docling_convert_to_markdown", fake_docling)
    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    options = _options(url="https://example.com/report.pdf")
    profile = diag._build_tool_fetch_profile(
        "https://example.com/report.pdf",
        options,
        provider_config=diag._provider_config(options),
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
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

    def fake_definition(provider_config: Mapping[str, JsonValue]) -> ToolDefinition:
        """返回不触发 Docling 的工具定义。

        Args:
            provider_config: single diagnostic 交给 provider discovery 的 raw 配置。

        Returns:
            确定性 fetch 工具定义。

        Raises:
            无。
        """

        assert provider_config["request_timeout_seconds"] == 1.0
        return _tool_definition(fake_callable)

    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    options = _options(url="https://example.com/page")
    profile = diag._build_tool_fetch_profile(
        "https://example.com/page",
        options,
        provider_config=diag._provider_config(options),
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
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

    def fake_definition(provider_config: Mapping[str, JsonValue]) -> ToolDefinition:
        """返回未触发 Docling 的 PDF 工具定义。

        Args:
            provider_config: single diagnostic 交给 provider discovery 的 raw 配置。

        Returns:
            确定性 fetch 工具定义。

        Raises:
            无。
        """

        assert provider_config["request_timeout_seconds"] == 1.0
        return _tool_definition(fake_callable)

    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    options = _options(url="https://example.com/report.pdf")
    profile = diag._build_tool_fetch_profile(
        "https://example.com/report.pdf",
        options,
        provider_config=diag._provider_config(options),
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
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

    def fake_definition(provider_config: Mapping[str, JsonValue]) -> ToolDefinition:
        """返回会触发 Docling 初始化异常的工具定义。

        Args:
            provider_config: single diagnostic 交给 provider discovery 的 raw 配置。

        Returns:
            确定性 fetch 工具定义。

        Raises:
            无。
        """

        assert provider_config["request_timeout_seconds"] == 1.0
        return _tool_definition(fake_callable)

    monkeypatch.setattr(web_tools_module, "_docling_convert_to_markdown", fake_docling)
    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    options = _options(url="https://example.com/report.pdf")
    profile = diag._build_tool_fetch_profile(
        "https://example.com/report.pdf",
        options,
        provider_config=diag._provider_config(options),
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
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

    def fake_definition(provider_config: Mapping[str, JsonValue]) -> ToolDefinition:
        """返回会触发普通 Docling 转换异常的工具定义。

        Args:
            provider_config: single diagnostic 交给 provider discovery 的 raw 配置。

        Returns:
            确定性 fetch 工具定义。

        Raises:
            无。
        """

        assert provider_config["request_timeout_seconds"] == 1.0
        return _tool_definition(fake_callable)

    monkeypatch.setattr(web_tools_module, "_docling_convert_to_markdown", fake_docling)
    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    options = _options(url="https://example.com/report.pdf")
    profile = diag._build_tool_fetch_profile(
        "https://example.com/report.pdf",
        options,
        provider_config=diag._provider_config(options),
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
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

    def fake_definition(provider_config: Mapping[str, JsonValue]) -> ToolDefinition:
        """返回 current contract 形状的工具定义。

        Args:
            provider_config: single diagnostic 交给 provider discovery 的 raw 配置。

        Returns:
            确定性 fetch 工具定义。

        Raises:
            无。
        """

        assert provider_config["request_timeout_seconds"] == 1.0
        return _tool_definition(fake_callable)

    monkeypatch.setattr(diag, "_fetch_web_page_definition", fake_definition)

    options = _options(tool_timeout_budget=3.0)
    profile = diag._build_tool_fetch_profile(
        "https://example.com",
        options,
        provider_config=diag._provider_config(options),
        diagnostic_resource_budget=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
    )

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
    storage_state_dir: str = "",
    skip_playwright: bool = False,
    skip_requests: bool = False,
    skip_tool_fetch: bool = False,
    max_network: int | None = None,
    fetch_truncate_chars: int = 1000,
) -> diag.CliOptions:
    """构造测试用 CLI 选项。

    Args:
        url: 单 URL 输入。
        url_file: 批量 URL 输入文件。
        output: 单 URL artifact 路径。
        batch_output_dir: 批量 artifact 目录。
        run_label: 批量运行标签。
        request_timeout: HTTP 请求超时。
        tool_timeout_budget: 工具调用超时预算。
        playwright_timeout: 浏览器导航超时。
        playwright_channel: 浏览器 channel。
        headed: 是否使用有界面浏览器。
        manual_wait_seconds: 导航后等待秒数。
        pause_before_snapshot: 是否在页面采样前等待确认。
        storage_state_in: 显式 storage state 输入文件。
        storage_state_dir: production provider storage state 目录。
        skip_playwright: 是否跳过 Playwright。
        skip_requests: 是否跳过 raw requests。
        skip_tool_fetch: 是否跳过工具调用。
        max_network: 可选的本次 diagnostic events override。
        fetch_truncate_chars: 工具内容截断字符数。

    Returns:
        强类型诊断 CLI 选项。

    Raises:
        无。
    """

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
        storage_state_dir=storage_state_dir,
        skip_playwright=skip_playwright,
        skip_requests=skip_requests,
        skip_tool_fetch=skip_tool_fetch,
        max_network=max_network,
        fetch_truncate_chars=fetch_truncate_chars,
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
    transport_policy: web_http_session.WebHttpTransportPolicy,
    diagnostic_resource_budget: DiagnosticResourceBudget,
) -> JsonObject:
    """返回确定性 requests profile。

    Args:
        url: 待诊断 URL。
        timeout_seconds: requests 超时秒数。
        egress_policy: utility 构造的 Web 出站策略。
        transport_policy: provider parser 产生的 transport 策略快照。
        diagnostic_resource_budget: provider parser 产生的 diagnostic 快照。

    Returns:
        确定性 requests profile。

    Raises:
        AssertionError: 调用参数不符合测试约束时抛出。
    """

    assert url == "https://example.com"
    assert timeout_seconds > 0
    assert egress_policy.allows_private_network is True
    assert transport_policy == web_provider._parse_config({}).transport_policy
    assert diagnostic_resource_budget == DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET
    return cast(JsonObject, _payload(
        requests_sampled=True,
        requests_ok=True,
        fetch_sampled=False,
        fetch_ok=False,
        playwright_sampled=False,
        playwright_ok=False,
    )["requests_profile"])


def _fake_fetch_profile(
    url: str,
    options: diag.CliOptions,
    *,
    provider_config: Mapping[str, JsonValue],
    diagnostic_resource_budget: DiagnosticResourceBudget,
) -> JsonObject:
    """返回确定性 fetch profile。

    Args:
        url: 待诊断 URL。
        options: single diagnostic CLI 选项。
        provider_config: orchestration 交给 provider discovery 的 raw 配置。
        diagnostic_resource_budget: provider parser 产生的 diagnostic 快照。

    Returns:
        确定性 fetch profile。

    Raises:
        AssertionError: 调用参数不符合测试约束时抛出。
    """

    assert url == "https://example.com"
    assert options.url == "https://example.com"
    assert provider_config == diag._provider_config(options)
    assert diagnostic_resource_budget == DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET
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
    storage_state_input: Path | None,
    diagnostic_resource_budget: DiagnosticResourceBudget,
) -> JsonObject:
    """返回确定性 Playwright profile。

    Args:
        url: 待诊断 URL。
        options: single diagnostic CLI 选项。
        egress_policy: 唯一 parser 配置产生的出站策略。
        storage_state_input: 已校验的显式 storage state 输入。
        diagnostic_resource_budget: provider parser 产生的 diagnostic 快照。

    Returns:
        确定性 Playwright profile。

    Raises:
        AssertionError: orchestration 未传播 typed owner 值时抛出。
    """

    assert url == "https://example.com"
    assert options.url == "https://example.com"
    assert egress_policy.allows_private_network is True
    assert storage_state_input is None
    assert diagnostic_resource_budget == DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET
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
