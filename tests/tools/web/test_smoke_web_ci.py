"""Web CI smoke CLI 与 summary contract 的确定性测试。"""

from __future__ import annotations

import hashlib
import json
import sys
import contextlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Iterator, cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_declaration import ToolCallable, ToolDefinition
from dayu.contracts.tool_execution import AsyncDirectToolExecutionCapability
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from utils import smoke_web_ci as smoke

JsonObject = dict[str, JsonValue]


def test_local_fixture_urls_and_pdf_fixture_are_stable() -> None:
    """本地 fixture URL 与 PDF 文本 fixture 应稳定可测。"""

    urls = smoke._local_fixture_urls(43117)
    pdf_bytes = smoke._pdf_fixture_bytes()

    assert urls.html_url == "http://127.0.0.1:43117/index.html"
    assert urls.pdf_url == "http://127.0.0.1:43117/fixture.pdf"
    assert urls.browser_url == "http://127.0.0.1:43117/client-rendered.html"
    assert b"Dayu Web Smoke Browser Rendered" in smoke._browser_fixture_bytes()
    assert b"Dayu Web Smoke PDF" in pdf_bytes
    assert b"This PDF verifies Docling conversion." in pdf_bytes
    assert smoke.PDF_FETCH_MIN_CHARS >= 20


def test_versioned_filing_fixture_is_regular_and_registered_directly() -> None:
    """版本化 AAPL filing 必须以模块常量和 LocalFixtureCase 直接注册。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: fixture 缺失、不是常规文件或 bytes 未同源注册时抛出。
    """

    assert smoke._VERSIONED_FILING_FIXTURE.is_file()
    expected_bytes = smoke._VERSIONED_FILING_FIXTURE.read_bytes()
    filing_cases = tuple(
        case
        for case in smoke._build_local_fixture_cases(43117)
        if case.case_kind == smoke._CASE_LOCAL_FILING
    )

    assert tuple(case.case_name for case in filing_cases) == (
        "local-filing-http",
        "local-filing-playwright",
    )
    assert all(case.response_body == expected_bytes for case in filing_cases)
    assert filing_cases[0].sample_playwright is False
    assert filing_cases[1].sample_playwright is True


def test_diagnostic_command_has_no_private_cli_and_forwards_explicit_input(
    tmp_path: Path,
) -> None:
    """smoke child 命令不得依赖旧 private CLI，只转发显式只读输入。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 命令残留旧 CLI 或丢失显式输入时抛出。
    """

    storage_input = tmp_path / "explicit-storage-state-input.json"
    options = smoke.SmokeOptions(
        output_dir=tmp_path,
        request_timeout=1.0,
        tool_timeout_budget=2.0,
        include_playwright=True,
        external_url_file=None,
        external_limit=0,
        diagnostic_only_external=True,
        run_label="command-owner",
        log_level=smoke.LogLevel.DEBUG,
    )

    command = smoke._diagnostic_command(
        url="http://127.0.0.1:43117/aapl-20240928.htm",
        artifact_path=tmp_path / "filing.json",
        options=options,
        sample_playwright=True,
        skip_requests=True,
        skip_tool_fetch=True,
        storage_state_input=storage_input,
    )

    assert "--allow-private-network-url" not in command
    assert _command_value(command, "--storage-state-in") == str(storage_input)
    assert "--skip-playwright" not in command


def test_fixture_session_owns_unique_sentinels_negative_controls_and_freeze_order() -> None:
    """父进程 fixture session 必须绑定唯一 sentinel、负控与 shutdown/freeze 顺序。"""

    with smoke._running_local_fixture_server() as session:
        assert len({case.token for case in session.cases}) == len(session.cases)
        assert all(len(case.token) == 64 for case in session.cases)
        assert session.frozen_ledger is None
        for case in session.cases:
            smoke._exercise_pre_child_negative_controls(case)
            response = smoke.requests.get(case.url, timeout=2.0)
            assert response.status_code == 200
            response.close()
            smoke._exercise_post_child_replay_control(case)

    ledger = session.frozen_ledger
    assert ledger is not None
    assert ledger.lifecycle[-2:] == ("server_stopped", "frozen")
    assert ledger.dropped_count == 0
    for case in session.cases:
        assert smoke._fixture_ledger_gap(case=case, ledger=ledger) == ""
    with pytest.raises(RuntimeError, match="frozen"):
        session.ledger.append(ledger.observations[0])


def test_diagnostic_child_log_uses_only_stdio_length_and_digest(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """child stdout/stderr 即使含 sentinel，也不得以 prefix 进入日志。"""

    sentinel = "8e" * 32
    caplog.set_level("DEBUG", logger=smoke.__name__)
    smoke._log_diagnostic_child_result(
        case_name="sentinel-case",
        child_result=smoke.DiagnosticChildResult(
            returncode=1,
            stdout=f"stdout-{sentinel}",
            stderr=f"stderr-{sentinel}",
        ),
    )

    assert sentinel not in caplog.text
    assert sentinel[:16] not in caplog.text
    assert "stdout_length=" in caplog.text
    assert "stdout_digest=sha256:" in caplog.text
    assert "stderr_length=" in caplog.text
    assert "stderr_digest=sha256:" in caplog.text


def test_local_assembly_config_case_writes_overlay_and_truncate_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """local assembly case 必须证明 overlay config 与 truncate spec。"""

    loaded_overlay_dirs: list[Path] = []
    discovered_configs: list[smoke.RuntimeConfig] = []

    async def fake_fetch_callable(
        call: smoke.ToolCallRequest,
        context: smoke.BatchToolExecutionContext,
    ) -> smoke.ToolCompletedOutcome:
        """模拟 fetch_web_page callable 成功返回 fixture 正文。"""

        assert call.name == "fetch_web_page"
        assert context.run_id == "web-smoke-run"
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "content": smoke._HTML_FIXTURE_BODY,
                    "title": "Fixture",
                    "response_content_length": len(smoke._html_fixture_bytes()),
                    "response_content_digest": smoke.content_diagnostic_from_bytes(
                        smoke._html_fixture_bytes()
                    ).digest,
                },
                meta=None,
            )
        )

    def fake_load_runtime_config(workspace_config_dir: Path) -> smoke.RuntimeConfig:
        """记录 ConfigLoader overlay 目录并返回占位 RuntimeConfig。"""

        loaded_overlay_dirs.append(workspace_config_dir)
        return cast(smoke.RuntimeConfig, object())

    def fake_discover_tools(
        config: smoke.RuntimeConfig,
        *,
        workspace_root: Path,
    ) -> Mapping[str, ToolDefinition]:
        """记录 Service discovery 输入并返回 fetch_web_page definition。"""

        discovered_configs.append(config)
        assert workspace_root == tmp_path
        return {
            "search_web": _tool_definition("search_web", fake_fetch_callable),
            "fetch_web_page": _tool_definition(
                "fetch_web_page",
                fake_fetch_callable,
                truncate_max_chars=3210,
            ),
        }

    monkeypatch.setattr(smoke, "_load_runtime_config_for_overlay", fake_load_runtime_config)
    monkeypatch.setattr(smoke, "_discover_tools_by_name", fake_discover_tools)

    result = smoke._run_local_assembly_config_case(
        fixture_urls=smoke.LocalFixtureUrls(
            html_url="http://127.0.0.1:43117/index.html",
            pdf_url="http://127.0.0.1:43117/fixture.pdf",
            browser_url="http://127.0.0.1:43117/client-rendered.html",
        ),
        diagnostics_dir=tmp_path,
    )

    artifact = _load_json_object(Path(result.evidence_path))
    overlay = _load_json_object(tmp_path / "assembly-workspace-config" / "tool_discovery.json")
    providers = _object_value(overlay["providers"])
    web_provider = _object_value(providers["web-tools"])
    provider_config = _object_value(artifact["provider_config"])
    assert result.status == "passed"
    assert loaded_overlay_dirs == [tmp_path / "assembly-workspace-config"]
    assert len(discovered_configs) == 1
    assert "allow_empty" not in web_provider
    assert provider_config["provider"] == "duckduckgo"
    assert provider_config["fetch_truncate_chars"] == 3210
    assert artifact["truncate_max_chars"] == 3210
    assert artifact["content_contains_fixture_text"] is True
    assert artifact["content_length"] == len(smoke._html_fixture_bytes())
    assert (
        artifact["assembly_path"]
        == "ConfigLoader -> assemble_effective_tool_provider_configs -> discover_service_tools -> ToolDefinition.callable"
    )


@pytest.mark.parametrize(
    ("case_name", "case_kind", "provider_config"),
    (
        (
            "local-private-deny",
            "local_private_deny",
            {"allow_private_network_url": False, "allow_custom_port_url": True},
        ),
        (
            "local-custom-port-deny",
            "local_custom_port_deny",
            {"allow_private_network_url": True, "allow_custom_port_url": False},
        ),
    ),
)
def test_typed_egress_deny_cases_use_provider_overlay_and_callable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_name: str,
    case_kind: str,
    provider_config: JsonObject,
) -> None:
    """private/custom-port deny 必须经 overlay、discovery 与正式 callable 证明。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest 属性替换夹具。
        case_name: 稳定 deny case 名称。
        case_kind: deny case 类型。
        provider_config: 仅关闭一个出站维度的 typed provider overlay。

    Returns:
        无。

    Raises:
        AssertionError: smoke 绕过 typed provider 链或错误接受 URL 时抛出。
    """

    async def denied_fetch_callable(
        call: smoke.ToolCallRequest,
        context: smoke.BatchToolExecutionContext,
    ) -> smoke.ToolFailedOutcome:
        """模拟正式 callable 投影 typed egress denial。

        Args:
            call: fetch_web_page 调用。
            context: smoke 批式调用上下文。

        Returns:
            permission_denied 工具失败 outcome。

        Raises:
            无。
        """

        assert call.name == "fetch_web_page"
        assert context.run_id == "web-smoke-run"
        return ToolFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error="permission_denied",
                message="typed egress denied",
                hint=None,
                meta=None,
            )
        )

    def fake_load_runtime_config(workspace_config_dir: Path) -> smoke.RuntimeConfig:
        """确认 overlay 已写入后返回占位 RuntimeConfig。

        Args:
            workspace_config_dir: 当前 deny case 的 workspace config 目录。

        Returns:
            测试占位 RuntimeConfig。

        Raises:
            AssertionError: overlay 未包含本次 provider config 时抛出。
        """

        overlay = _load_json_object(workspace_config_dir / "tool_discovery.json")
        providers = _object_value(overlay["providers"])
        web_tools = _object_value(providers["web-tools"])
        assert _object_value(web_tools["config"]) == provider_config
        return cast(smoke.RuntimeConfig, object())

    def fake_discover_tools(
        config: smoke.RuntimeConfig,
        *,
        workspace_root: Path,
    ) -> Mapping[str, ToolDefinition]:
        """返回会产生 permission_denied 的 fetch_web_page 定义。

        Args:
            config: 占位 runtime config。
            workspace_root: smoke diagnostics workspace root。

        Returns:
            只含 fetch_web_page 的工具定义映射。

        Raises:
            AssertionError: workspace root 不符合调用 contract 时抛出。
        """

        del config
        assert workspace_root == tmp_path
        return {
            "fetch_web_page": _tool_definition(
                "fetch_web_page",
                denied_fetch_callable,
            )
        }

    monkeypatch.setattr(smoke, "_load_runtime_config_for_overlay", fake_load_runtime_config)
    monkeypatch.setattr(smoke, "_discover_tools_by_name", fake_discover_tools)

    result = smoke._run_local_typed_egress_deny_case(
        case_name=case_name,
        case_kind=case_kind,
        fixture_url="http://127.0.0.1:43117/index.html?dayu_smoke_token=test",
        diagnostics_dir=tmp_path,
        provider_config=provider_config,
    )
    artifact = _load_json_object(Path(result.evidence_path))

    assert result.status == "passed"
    assert result.bucket == "passed"
    assert artifact["observed_error_code"] == "permission_denied"
    assert artifact["passed"] is True


def test_search_provider_cases_are_typed_diagnostic_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search provider cases 必须进入 typed search_cases，不混入 external_cases。"""

    async def fake_success_search_callable(
        call: smoke.ToolCallRequest,
        context: smoke.BatchToolExecutionContext,
    ) -> smoke.ToolCompletedOutcome:
        """模拟 search_web 成功返回一个首选结果。"""

        assert call.name == "search_web"
        assert context.run_id == "web-smoke-run"
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "total": 1,
                    "preferred_result": {"url": "https://openai.com/investors"},
                    "results": [],
                },
                meta=None,
            )
        )

    async def fake_failed_search_callable(
        call: smoke.ToolCallRequest,
        context: smoke.BatchToolExecutionContext,
    ) -> smoke.ToolFailedOutcome:
        """模拟 Tavily 缺 key 的 search_web failed outcome。"""

        assert call.name == "search_web"
        assert context.run_id == "web-smoke-run"
        return ToolFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error="execution_error",
                message="TAVILY_API_KEY 未配置",
                hint=None,
                meta=None,
            )
        )

    loaded_overlay_dirs: list[Path] = []

    def fake_load_runtime_config(workspace_config_dir: Path) -> smoke.RuntimeConfig:
        """记录 search provider overlay 目录并返回占位 RuntimeConfig。"""

        loaded_overlay_dirs.append(workspace_config_dir)
        return cast(smoke.RuntimeConfig, object())

    def fake_discover_tools(
        config: smoke.RuntimeConfig,
        *,
        workspace_root: Path,
    ) -> Mapping[str, ToolDefinition]:
        """根据 overlay 路径返回 search_web fake definition。"""

        del config
        assert workspace_root == tmp_path
        overlay_dir = loaded_overlay_dirs[-1]
        if "tavily" in str(overlay_dir):
            return {"search_web": _tool_definition("search_web", fake_failed_search_callable)}
        return {"search_web": _tool_definition("search_web", fake_success_search_callable)}

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(smoke, "_load_runtime_config_for_overlay", fake_load_runtime_config)
    monkeypatch.setattr(smoke, "_discover_tools_by_name", fake_discover_tools)
    options = smoke.SmokeOptions(
        output_dir=tmp_path,
        request_timeout=1.0,
        tool_timeout_budget=1.0,
        include_playwright=False,
        external_url_file=None,
        external_limit=0,
        diagnostic_only_external=True,
        run_label="search-cases",
        log_level=smoke.LogLevel.DEBUG,
    )

    search_cases = smoke._run_search_provider_cases(options=options)
    summary = smoke._summary_from_cases(
        run_label="search-cases",
        output_dir=tmp_path,
        local_cases=(
            smoke.SmokeCaseResult(
                case_name="local-html",
                case_kind="local_html",
                url="http://127.0.0.1/index.html",
                status="passed",
                bucket="passed",
                evidence_path=str(tmp_path / "local.json"),
                suggested_next_step="",
                reason="",
                exit_code=0,
            ),
        ),
        external_cases=(),
        search_cases=search_cases,
    )

    tavily_artifact = _load_json_object(tmp_path / "diagnostics" / "search" / "search-provider-tavily.json")
    assert len(search_cases) == 4
    assert summary.exit_code == 0
    assert summary.external_cases == ()
    assert len(summary.search_cases) == 4
    assert len(summary.diagnostic_only) == 4
    assert search_cases[1].bucket == "provider_key_missing"
    assert tavily_artifact["api_key_env"] == "TAVILY_API_KEY"
    assert tavily_artifact["api_key_present"] is False
    assert "provider_config" in tavily_artifact


@pytest.mark.parametrize(
    ("status_code", "expected_bucket"),
    (
        (401, "provider_auth_failure"),
        (403, "provider_auth_failure"),
        (429, "provider_quota_or_rate_limited"),
        (500, "provider_unavailable"),
    ),
)
def test_search_http_status_classifier(status_code: int, expected_bucket: str) -> None:
    """search provider HTTP 状态分类必须稳定。

    :param status_code: HTTP 状态码。
    :param expected_bucket: 预期分类 bucket。
    :returns: ``None``。
    :raises AssertionError: 分类不符合预期时抛出。
    """

    assert smoke._classify_search_http_status(status_code) == expected_bucket


@pytest.mark.parametrize(
    ("provider", "error_text", "api_key_present", "expected_bucket"),
    (
        ("tavily", "missing credentials", False, "provider_key_missing"),
        ("auto", "api_key 未配置", True, "provider_key_missing"),
        ("duckduckgo", "unauthorized invalid key", True, "provider_auth_failure"),
        ("duckduckgo", "quota exceeded", True, "provider_quota_or_rate_limited"),
        ("duckduckgo", "connection timeout", True, "provider_network_failure"),
        ("duckduckgo", "unexpected json parse error", True, "provider_response_parse_failure"),
        ("auto", "所有 provider 均不可用", True, "provider_unavailable"),
        ("duckduckgo", "unknown failure", True, "search_tool_execution_error"),
    ),
)
def test_search_error_text_classifier(
    provider: str,
    error_text: str,
    api_key_present: bool,
    expected_bucket: str,
) -> None:
    """search provider 错误文本分类必须覆盖关键模式。

    :param provider: provider 名称。
    :param error_text: 错误文本。
    :param api_key_present: API key 是否存在。
    :param expected_bucket: 预期分类 bucket。
    :returns: ``None``。
    :raises AssertionError: 分类不符合预期时抛出。
    """

    assert (
        smoke._classify_search_error_text(
            provider=provider,
            error_text=error_text,
            api_key_present=api_key_present,
        )
        == expected_bucket
    )


def test_single_search_provider_case_reports_loader_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search provider case 的 ConfigLoader 失败必须是 hard failure。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 失败分类不符合预期时抛出。
    """

    def fake_load_runtime_config(workspace_config_dir: Path) -> smoke.RuntimeConfig:
        """模拟 ConfigLoader 失败。"""

        del workspace_config_dir
        raise RuntimeError("loader down")

    monkeypatch.setattr(smoke, "_load_runtime_config_for_overlay", fake_load_runtime_config)

    result = smoke._run_single_search_provider_case(
        case_name="search-provider-duckduckgo",
        provider="duckduckgo",
        provider_config={"provider": "duckduckgo"},
        workspace_config_dir=tmp_path / "config",
        artifact_path=tmp_path / "search-loader.json",
        workspace_root=tmp_path,
    )

    artifact = _load_json_object(Path(result.evidence_path))
    assert result.status == "failed"
    assert result.exit_code == 2
    assert result.bucket == "web_config_loader_failure"
    assert artifact["error_summary"] == "loader down"


def test_single_search_provider_case_reports_discovery_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search provider case 的 discovery 失败必须是 hard failure。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 失败分类不符合预期时抛出。
    """

    def fake_load_runtime_config(workspace_config_dir: Path) -> smoke.RuntimeConfig:
        """返回占位 RuntimeConfig。"""

        del workspace_config_dir
        return cast(smoke.RuntimeConfig, object())

    def fake_discover_tools(
        config: smoke.RuntimeConfig,
        *,
        workspace_root: Path,
    ) -> Mapping[str, ToolDefinition]:
        """模拟 Service discovery 失败。"""

        del config
        del workspace_root
        raise RuntimeError("discovery down")

    monkeypatch.setattr(smoke, "_load_runtime_config_for_overlay", fake_load_runtime_config)
    monkeypatch.setattr(smoke, "_discover_tools_by_name", fake_discover_tools)

    result = smoke._run_single_search_provider_case(
        case_name="search-provider-duckduckgo",
        provider="duckduckgo",
        provider_config={"provider": "duckduckgo"},
        workspace_config_dir=tmp_path / "config",
        artifact_path=tmp_path / "search-discovery.json",
        workspace_root=tmp_path,
    )

    artifact = _load_json_object(Path(result.evidence_path))
    assert result.status == "failed"
    assert result.exit_code == 2
    assert result.bucket == "web_assembly_discovery_failure"
    assert artifact["error_summary"] == "discovery down"


def test_single_search_provider_case_classifies_callable_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web callable timeout 必须降级为 diagnostic-only 网络失败。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 失败分类不符合预期时抛出。
    """

    async def fake_timeout_search_callable(
        call: smoke.ToolCallRequest,
        context: smoke.BatchToolExecutionContext,
    ) -> smoke.ToolCompletedOutcome:
        """模拟 provider timeout。"""

        del call
        del context
        raise smoke.requests.Timeout("search timeout")

    def fake_load_runtime_config(workspace_config_dir: Path) -> smoke.RuntimeConfig:
        """返回占位 RuntimeConfig。"""

        del workspace_config_dir
        return cast(smoke.RuntimeConfig, object())

    def fake_discover_tools(
        config: smoke.RuntimeConfig,
        *,
        workspace_root: Path,
    ) -> Mapping[str, ToolDefinition]:
        """返回会 timeout 的 search_web definition。"""

        del config
        del workspace_root
        return {"search_web": _tool_definition("search_web", fake_timeout_search_callable)}

    monkeypatch.setattr(smoke, "_load_runtime_config_for_overlay", fake_load_runtime_config)
    monkeypatch.setattr(smoke, "_discover_tools_by_name", fake_discover_tools)

    result = smoke._run_single_search_provider_case(
        case_name="search-provider-duckduckgo",
        provider="duckduckgo",
        provider_config={"provider": "duckduckgo"},
        workspace_config_dir=tmp_path / "config",
        artifact_path=tmp_path / "search-timeout.json",
        workspace_root=tmp_path,
    )

    assert result.status == "diagnostic_only"
    assert result.exit_code == 0
    assert result.bucket == "provider_network_failure"


def test_single_search_provider_case_classifies_empty_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web 成功但结果为空时必须记录 provider_no_results。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 分类不符合预期时抛出。
    """

    async def fake_empty_search_callable(
        call: smoke.ToolCallRequest,
        context: smoke.BatchToolExecutionContext,
    ) -> smoke.ToolCompletedOutcome:
        """模拟 provider 成功但无结果。"""

        del call
        del context
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"total": 0, "preferred_result": {}, "results": []},
                meta=None,
            )
        )

    def fake_load_runtime_config(workspace_config_dir: Path) -> smoke.RuntimeConfig:
        """返回占位 RuntimeConfig。"""

        del workspace_config_dir
        return cast(smoke.RuntimeConfig, object())

    def fake_discover_tools(
        config: smoke.RuntimeConfig,
        *,
        workspace_root: Path,
    ) -> Mapping[str, ToolDefinition]:
        """返回 search_web definition。"""

        del config
        del workspace_root
        return {"search_web": _tool_definition("search_web", fake_empty_search_callable)}

    monkeypatch.setattr(smoke, "_load_runtime_config_for_overlay", fake_load_runtime_config)
    monkeypatch.setattr(smoke, "_discover_tools_by_name", fake_discover_tools)

    result = smoke._run_single_search_provider_case(
        case_name="search-provider-duckduckgo",
        provider="duckduckgo",
        provider_config={"provider": "duckduckgo"},
        workspace_config_dir=tmp_path / "config",
        artifact_path=tmp_path / "search-empty.json",
        workspace_root=tmp_path,
    )

    assert result.status == "diagnostic_only"
    assert result.exit_code == 0
    assert result.bucket == "provider_no_results"


def test_synthetic_diagnostics_results_map_to_pass_fail_skip_diagnostic_only_and_schema_gap(
    tmp_path: Path,
) -> None:
    """只有 v2 artifact、exact bytes、frozen ledger 与负控共同满足才可 PASS。"""

    case = _fixture_case("local-html-requests")
    artifact_path = tmp_path / "html-pass.json"
    _write_payload(artifact_path, _diagnostic_payload_for_case(case))
    passed = smoke._classify_child_result(
        case_name=case.case_name,
        case_kind=case.case_kind,
        fallback_url=case.url,
        artifact_path=artifact_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
        fixture_case=case,
        frozen_ledger=_frozen_ledger_for_case(case),
    )
    assert passed.status == "passed"

    synthetic_without_ledger = smoke._classify_child_result(
        case_name=case.case_name,
        case_kind=case.case_kind,
        fallback_url=case.url,
        artifact_path=artifact_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
    )
    assert synthetic_without_ledger.status == "failed"
    assert synthetic_without_ledger.bucket == "fixture_ledger_gap"

    wrong_digest_payload = _diagnostic_payload_for_case(case)
    wrong_profile = _object_value(wrong_digest_payload["requests_profile"])
    wrong_profile["content_digest"] = "sha256:" + "f" * 64
    wrong_digest_payload["requests_profile"] = wrong_profile
    wrong_digest_path = tmp_path / "wrong-digest.json"
    _write_payload(wrong_digest_path, wrong_digest_payload)
    wrong_digest = smoke._classify_child_result(
        case_name=case.case_name,
        case_kind=case.case_kind,
        fallback_url=case.url,
        artifact_path=wrong_digest_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
        fixture_case=case,
        frozen_ledger=_frozen_ledger_for_case(case),
    )
    assert wrong_digest.bucket == "content_oracle_mismatch"

    for ledger_name, ledger in (
        (
            "missing-accepted",
            _frozen_ledger_for_case(case, include_accepted=False),
        ),
        (
            "wrong-response-digest",
            _frozen_ledger_for_case(
                case,
                accepted_response_digest="sha256:" + "e" * 64,
            ),
        ),
        (
            "negative-control-accepted",
            _frozen_ledger_for_case(case, negative_controls_rejected=False),
        ),
        (
            "missing-method-negative-control",
            _frozen_ledger_for_case(case, include_method_negative=False),
        ),
    ):
        rejected = smoke._classify_child_result(
            case_name=f"{case.case_name}-{ledger_name}",
            case_kind=case.case_kind,
            fallback_url=case.url,
            artifact_path=artifact_path,
            child_result=smoke.DiagnosticChildResult(
                returncode=0,
                stdout="",
                stderr="",
            ),
            fixture_case=case,
            frozen_ledger=ledger,
        )
        assert rejected.status == "failed"
        assert rejected.bucket == "fixture_ledger_gap"

    old_schema_payload = _diagnostic_payload_for_case(case)
    old_schema_payload["schema_version"] = "web-diagnostics-v1"
    old_schema_path = tmp_path / "old-schema.json"
    _write_payload(old_schema_path, old_schema_payload)
    old_schema = smoke._classify_child_result(
        case_name=case.case_name,
        case_kind=case.case_kind,
        fallback_url=case.url,
        artifact_path=old_schema_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
        fixture_case=case,
        frozen_ledger=_frozen_ledger_for_case(case),
    )
    assert old_schema.bucket == "diagnostic_schema_gap"

    external_path = tmp_path / "external.json"
    _write_payload(
        external_path,
        _diagnostic_payload(
            url="https://example.com",
            requests_ok=False,
            fetch_ok=False,
            comparison_bucket="all_failed",
        ),
    )
    external = smoke._classify_child_result(
        case_name="external-0001",
        case_kind="external",
        fallback_url="https://example.com",
        artifact_path=external_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
    )
    assert external.status == "diagnostic_only"
    assert external.bucket == "all_failed"
    assert external.exit_code == 0


def test_local_browser_case_without_playwright_execution_is_failure(tmp_path: Path) -> None:
    """browser fixture 缺少实际 Playwright execution evidence 必须失败。"""

    case = _fixture_case("local-browser-playwright")
    browser_path = tmp_path / "browser.json"
    payload = _diagnostic_payload_for_case(case)
    profile = _object_value(payload["playwright_profile"])
    profile["browser_executed"] = False
    payload["playwright_profile"] = profile
    _write_payload(browser_path, payload)

    browser = smoke._classify_child_result(
        case_name=case.case_name,
        case_kind=case.case_kind,
        fallback_url=case.url,
        artifact_path=browser_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
        fixture_case=case,
        frozen_ledger=_frozen_ledger_for_case(case),
    )
    summary = smoke._summary_from_cases(
        run_label="browser-diagnostic",
        output_dir=tmp_path,
        local_cases=(browser,),
        external_cases=(),
    )

    assert browser.status == "failed"
    assert browser.bucket == "browser_backend_not_observed"
    assert browser.exit_code == 1
    assert summary.status == "failed"
    assert summary.exit_code == 1


@pytest.mark.parametrize(
    "case_name",
    ("local-filing-http", "local-filing-playwright"),
)
def test_versioned_filing_http_and_playwright_execution_are_hard_gates(
    tmp_path: Path,
    case_name: str,
) -> None:
    """版本化 filing 的 HTTP 与真实 Playwright artifact 都必须可独立判 PASS。

    Args:
        tmp_path: pytest 临时目录。
        case_name: filing HTTP 或 Playwright case 名称。

    Returns:
        无。

    Raises:
        AssertionError: filing metrics、显式输入或 exact bytes contract 缺失时抛出。
    """

    case = _fixture_case(case_name)
    artifact_path = tmp_path / f"{case_name}.json"
    payload = _diagnostic_payload_for_case(case)
    _write_payload(artifact_path, payload)

    result = smoke._classify_child_result(
        case_name=case.case_name,
        case_kind=case.case_kind,
        fallback_url=case.url,
        artifact_path=artifact_path,
        child_result=smoke.DiagnosticChildResult(
            returncode=0,
            stdout="",
            stderr="",
        ),
        fixture_case=case,
        frozen_ledger=_frozen_ledger_for_case(case),
    )
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert result.status == "passed"
    assert result.exit_code == 0
    for forbidden in (
        "output_enabled",
        "output_label",
        "ttl_seconds",
        "published",
    ):
        assert forbidden not in serialized


def test_browser_package_missing_is_independently_verified_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """browser package 缺失必须由父进程独立确认，并映射 skipped/exit 0。"""

    case = _fixture_case("local-browser-playwright")
    payload = _diagnostic_payload_for_case(case)
    profile = _object_value(payload["playwright_profile"])
    profile["sampled"] = False
    profile["outcome"] = "failed"
    profile["ok"] = False
    profile["error_code"] = "playwright_package_missing"
    profile.pop("content_length", None)
    profile.pop("content_digest", None)
    profile.pop("http_status", None)
    payload["playwright_profile"] = profile
    artifact_path = tmp_path / "browser-missing.json"
    _write_payload(artifact_path, payload)
    monkeypatch.setattr(
        smoke,
        "_playwright_package_missing_independently",
        lambda: True,
    )

    result = smoke._classify_child_result(
        case_name=case.case_name,
        case_kind=case.case_kind,
        fallback_url=case.url,
        artifact_path=artifact_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
        fixture_case=case,
        frozen_ledger=_frozen_ledger_for_case(case, include_accepted=False),
    )

    assert result.status == "skipped"
    assert result.exit_code == 0


def test_pdf_payload_failures_are_not_misclassified_as_pass(tmp_path: Path) -> None:
    """PDF content-type、内容长度与 Docling evidence 缺口必须失败。"""

    cases: list[tuple[str, JsonObject, str]] = [
        (
            "non-pdf-content-type",
            _diagnostic_payload(
                url="http://127.0.0.1/fixture.pdf",
                content_type="text/html",
                raw_length=512,
                fetch_length=smoke.PDF_FETCH_MIN_CHARS,
                docling_invoked=True,
                docling_completed=True,
            ),
            "pdf_content_type_failure",
        ),
        (
            "short-fetch-content",
            _diagnostic_payload(
                url="http://127.0.0.1/fixture.pdf",
                content_type="application/pdf",
                raw_length=512,
                fetch_length=smoke.PDF_FETCH_MIN_CHARS - 1,
                docling_invoked=True,
                docling_completed=True,
            ),
            "pdf_content_length_failure",
        ),
        (
            "empty-raw-response-bytes",
            _diagnostic_payload(
                url="http://127.0.0.1/fixture.pdf",
                content_type="application/pdf",
                raw_length=0,
                fetch_length=smoke.PDF_FETCH_MIN_CHARS,
                docling_invoked=True,
                docling_completed=True,
            ),
            "pdf_content_length_failure",
        ),
        (
            "missing-docling-evidence",
            _payload_without_docling_evidence(
                _diagnostic_payload(
                    url="http://127.0.0.1/fixture.pdf",
                    content_type="application/pdf",
                    raw_length=512,
                    fetch_length=smoke.PDF_FETCH_MIN_CHARS,
                    docling_invoked=True,
                    docling_completed=True,
                )
            ),
            "pdf_docling_invocation_failure",
        ),
        (
            "docling-invocation-not-completed",
            _diagnostic_payload(
                url="http://127.0.0.1/fixture.pdf",
                content_type="application/pdf",
                raw_length=512,
                fetch_length=smoke.PDF_FETCH_MIN_CHARS,
                docling_invoked=True,
                docling_completed=False,
                docling_init_error=False,
                stream_name="page.pdf",
            ),
            "pdf_docling_invocation_failure",
        ),
        (
            "wrong-stream-name",
            _diagnostic_payload(
                url="http://127.0.0.1/fixture.pdf",
                content_type="application/pdf",
                raw_length=512,
                fetch_length=smoke.PDF_FETCH_MIN_CHARS,
                docling_invoked=True,
                docling_completed=True,
                stream_name="fixture.bin",
            ),
            "pdf_docling_invocation_failure",
        ),
    ]

    for case_name, payload, expected_bucket in cases:
        result = smoke._classify_pdf_loaded_artifact(
            case_name=case_name,
            url="http://127.0.0.1/fixture.pdf",
            evidence_path=str(tmp_path / f"{case_name}.json"),
            payload=payload,
        )
        assert result is not None
        assert result.status == "failed"
        assert result.bucket == expected_bucket


def test_docling_skip_only_skips_pdf_and_does_not_hide_html_failure(tmp_path: Path) -> None:
    """Docling init evidence 只能 skip PDF，不能掩盖 HTML failure。"""

    html_failure = smoke.SmokeCaseResult(
        case_name="local-html",
        case_kind="local_html",
        url="http://127.0.0.1/index.html",
        status="failed",
        bucket="local_fetch_failure",
        evidence_path=str(tmp_path / "html.json"),
        suggested_next_step="检查 HTML fetch。",
        reason="",
        exit_code=1,
    )
    pdf_skip = smoke.SmokeCaseResult(
        case_name="local-pdf",
        case_kind="local_pdf",
        url="http://127.0.0.1/fixture.pdf",
        status="skipped",
        bucket="docling_runtime_initialization_error",
        evidence_path=str(tmp_path / "pdf.json"),
        suggested_next_step="安装或修复 Docling runtime 后重跑 smoke。",
        reason="Docling init failure.",
        exit_code=0,
    )

    summary = smoke._summary_from_cases(
        run_label="html-failure-pdf-skip",
        output_dir=tmp_path,
        local_cases=(html_failure, pdf_skip),
        external_cases=(),
    )

    assert summary.status == "failed"
    assert summary.exit_code == 1
    assert len(summary.failures) == 1
    assert len(summary.skips) == 1


def test_confirmed_challenge_cannot_pass_a_normal_local_case(tmp_path: Path) -> None:
    """artifact 即使 completed，confirmed challenge 也不能签发普通 case PASS。"""

    case = _fixture_case("local-html-requests")
    payload = _diagnostic_payload_for_case(case)
    profile = _object_value(payload["requests_profile"])
    profile["challenge_decision"] = "confirmed"
    payload["requests_profile"] = profile
    artifact_path = tmp_path / "challenge.json"
    _write_payload(artifact_path, payload)

    result = smoke._classify_child_result(
        case_name=case.case_name,
        case_kind=case.case_kind,
        fallback_url=case.url,
        artifact_path=artifact_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
        fixture_case=case,
        frozen_ledger=_frozen_ledger_for_case(case),
    )

    assert result.status == "failed"
    assert result.bucket == "challenge_control_failed"


@pytest.mark.parametrize("challenge_decision", [None, "none", "suspected"])
def test_challenge_control_requires_confirmed_decision(
    tmp_path: Path,
    challenge_decision: str | None,
) -> None:
    """challenge-control 缺失或非 confirmed decision 时必须失败。"""

    case = _fixture_case("local-challenge-control")
    payload = _diagnostic_payload_for_case(case)
    profile = _object_value(payload["requests_profile"])
    if challenge_decision is None:
        profile.pop("challenge_decision", None)
    else:
        profile["challenge_decision"] = challenge_decision
    payload["requests_profile"] = profile
    artifact_path = tmp_path / f"challenge-control-{challenge_decision}.json"
    _write_payload(artifact_path, payload)

    result = smoke._classify_child_result(
        case_name=case.case_name,
        case_kind=case.case_kind,
        fallback_url=case.url,
        artifact_path=artifact_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
        fixture_case=case,
        frozen_ledger=_frozen_ledger_for_case(case),
    )

    assert result.status == "failed"
    assert result.bucket == "challenge_control_failed"


def test_summary_exit_code_prefers_schema_gap_over_local_failure(tmp_path: Path) -> None:
    """local failure 应为 exit 1，schema gap 应提升为 exit 2。"""

    local_failure = smoke.SmokeCaseResult(
        case_name="local-html",
        case_kind="local_html",
        url="http://127.0.0.1/index.html",
        status="failed",
        bucket="local_fetch_failure",
        evidence_path=str(tmp_path / "failure.json"),
        suggested_next_step="检查 fetch_web_page。",
        reason="",
        exit_code=1,
    )
    schema_gap = smoke.SmokeCaseResult(
        case_name="local-pdf",
        case_kind="local_pdf",
        url="http://127.0.0.1/fixture.pdf",
        status="failed",
        bucket="diagnostic_schema_gap",
        evidence_path=str(tmp_path / "schema-gap.json"),
        suggested_next_step="补齐 diagnostics schema。",
        reason="",
        exit_code=2,
    )

    failure_summary = smoke._summary_from_cases(
        run_label="local-failure",
        output_dir=tmp_path,
        local_cases=(local_failure,),
        external_cases=(),
    )
    schema_gap_summary = smoke._summary_from_cases(
        run_label="schema-gap",
        output_dir=tmp_path,
        local_cases=(local_failure, schema_gap),
        external_cases=(),
    )

    assert failure_summary.status == "failed"
    assert failure_summary.exit_code == 1
    assert schema_gap_summary.status == "failed"
    assert schema_gap_summary.exit_code == 2


def test_external_failure_is_diagnostic_only_and_does_not_override_local_pass(tmp_path: Path) -> None:
    """外部站点失败只进入 diagnostic-only，不覆盖 local pass exit code。"""

    local_pass = smoke.SmokeCaseResult(
        case_name="local-html",
        case_kind="local_html",
        url="http://127.0.0.1/index.html",
        status="passed",
        bucket="passed",
        evidence_path=str(tmp_path / "local.json"),
        suggested_next_step="",
        reason="",
        exit_code=0,
    )
    external_failure = smoke.SmokeCaseResult(
        case_name="external-0001",
        case_kind="external",
        url="https://example.com",
        status="diagnostic_only",
        bucket="child_process_error",
        evidence_path=str(tmp_path / "external.json"),
        suggested_next_step="检查外部诊断证据。",
        reason="外部 URL diagnostics 失败。",
        exit_code=0,
    )

    summary = smoke._summary_from_cases(
        run_label="external-gap",
        output_dir=tmp_path,
        local_cases=(local_pass,),
        external_cases=(external_failure,),
    )

    assert summary.status == "passed"
    assert summary.exit_code == 0
    assert len(summary.diagnostic_only) == 1
    assert summary.diagnostic_only[0].bucket == "child_process_error"


def test_external_child_returncode_does_not_override_local_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """external child returncode 非 0 只能进入 diagnostic-only，不能覆盖 local pass。"""

    html_url = "http://127.0.0.1:43117/index.html"
    pdf_url = "http://127.0.0.1:43117/fixture.pdf"
    browser_url = "http://127.0.0.1:43117/client-rendered.html"
    url_file = tmp_path / "urls.txt"
    url_file.write_text("https://example.com/child-error\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    @contextlib.contextmanager
    def fake_server() -> Iterator[smoke.LocalFixtureUrls]:
        """提供 deterministic local fixture URL，不启动真实 HTTP server。"""

        yield smoke.LocalFixtureUrls(html_url=html_url, pdf_url=pdf_url, browser_url=browser_url)

    def fake_runner(command: Sequence[str]) -> smoke.DiagnosticChildResult:
        """local case 写入 pass artifact，external case 返回非零退出码。"""

        url = _command_value(command, "--url")
        output = Path(_command_value(command, "--output"))
        if url == html_url:
            _write_payload(output, _diagnostic_payload(url=url))
            return smoke.DiagnosticChildResult(returncode=0, stdout="", stderr="")
        if url == pdf_url:
            _write_payload(
                output,
                _diagnostic_payload(
                    url=url,
                    content_type="application/pdf",
                    raw_length=512,
                    fetch_length=smoke.PDF_FETCH_MIN_CHARS,
                    docling_invoked=True,
                    docling_completed=True,
                ),
            )
            return smoke.DiagnosticChildResult(returncode=0, stdout="", stderr="")
        if url == browser_url:
            _write_payload(
                output,
                _diagnostic_payload(
                    url=url,
                    fetch_backend="playwright",
                    playwright_sampled=True,
                    playwright_ok=True,
                ),
            )
            return smoke.DiagnosticChildResult(returncode=0, stdout="", stderr="")
        return smoke.DiagnosticChildResult(returncode=9, stdout="", stderr="external failed")

    _patch_local_cases_as_pass(monkeypatch, output_dir=output_dir)
    monkeypatch.setattr(smoke, "_run_diagnostic_command", fake_runner)
    _patch_direct_assembly_and_search_cases(monkeypatch)

    exit_code = smoke.main(
        [
            "--output-dir",
            str(output_dir),
            "--run-label",
            "external-child-error",
            "--external-url-file",
            str(url_file),
            "--external-limit",
            "1",
        ]
    )

    summary = _load_json_object(output_dir / "summary.json")
    external_cases = _list_field(summary, "external_cases")
    diagnostic_only = _list_field(summary, "diagnostic_only")
    assert exit_code == 0
    assert summary["status"] == "passed"
    assert summary["exit_code"] == 0
    assert len(external_cases) == 1
    assert _object_value(external_cases[0])["bucket"] == "child_process_error"
    assert _object_value(diagnostic_only[0])["bucket"] == "child_process_error"


def test_external_parse_and_artifact_gap_do_not_override_local_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """external parse failure 与 artifact missing 都只能进入 diagnostic-only。"""

    html_url = "http://127.0.0.1:43117/index.html"
    pdf_url = "http://127.0.0.1:43117/fixture.pdf"
    browser_url = "http://127.0.0.1:43117/client-rendered.html"
    url_file = tmp_path / "urls.txt"
    url_file.write_text(
        "https://example.com/parse-gap\nhttps://example.com/artifact-gap\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    @contextlib.contextmanager
    def fake_server() -> Iterator[smoke.LocalFixtureUrls]:
        """提供 deterministic local fixture URL，不启动真实 HTTP server。"""

        yield smoke.LocalFixtureUrls(html_url=html_url, pdf_url=pdf_url, browser_url=browser_url)

    def fake_runner(command: Sequence[str]) -> smoke.DiagnosticChildResult:
        """local case 写入 pass artifact，external case 制造 parse/missing gap。"""

        url = _command_value(command, "--url")
        output = Path(_command_value(command, "--output"))
        if url == html_url:
            _write_payload(output, _diagnostic_payload(url=url))
        elif url == pdf_url:
            _write_payload(
                output,
                _diagnostic_payload(
                    url=url,
                    content_type="application/pdf",
                    raw_length=512,
                    fetch_length=smoke.PDF_FETCH_MIN_CHARS,
                    docling_invoked=True,
                    docling_completed=True,
                ),
            )
        elif url == browser_url:
            _write_payload(
                output,
                _diagnostic_payload(
                    url=url,
                    fetch_backend="playwright",
                    playwright_sampled=True,
                    playwright_ok=True,
                ),
            )
        elif url.endswith("/parse-gap"):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("{not-json\n", encoding="utf-8")
        elif url.endswith("/artifact-gap"):
            pass
        else:
            raise AssertionError(f"unexpected url: {url}")
        return smoke.DiagnosticChildResult(returncode=0, stdout="", stderr="")

    _patch_local_cases_as_pass(monkeypatch, output_dir=output_dir)
    monkeypatch.setattr(smoke, "_run_diagnostic_command", fake_runner)
    _patch_direct_assembly_and_search_cases(monkeypatch)

    exit_code = smoke.main(
        [
            "--output-dir",
            str(output_dir),
            "--run-label",
            "external-artifact-gaps",
            "--external-url-file",
            str(url_file),
            "--external-limit",
            "2",
        ]
    )

    summary = _load_json_object(output_dir / "summary.json")
    buckets = [
        str(_object_value(item)["bucket"])
        for item in _list_field(summary, "external_cases")
    ]
    assert exit_code == 0
    assert summary["status"] == "passed"
    assert summary["exit_code"] == 0
    assert buckets == ["artifact_parse_failure", "artifact_missing"]


def test_default_browser_case_samples_playwright_and_include_playwright_affects_external(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认 browser case 采样 Playwright，--include-playwright 额外影响 external。"""

    html_url = "http://127.0.0.1:43117/index.html"
    pdf_url = "http://127.0.0.1:43117/fixture.pdf"
    browser_url = "http://127.0.0.1:43117/client-rendered.html"
    external_url = "https://example.com/playwright"
    url_file = tmp_path / "urls.txt"
    url_file.write_text(f"{external_url}\n", encoding="utf-8")
    commands_by_url: dict[str, Sequence[str]] = {}

    @contextlib.contextmanager
    def fake_server() -> Iterator[smoke.LocalFixtureUrls]:
        """提供 deterministic local fixture URL，不启动真实 HTTP server。"""

        yield smoke.LocalFixtureUrls(html_url=html_url, pdf_url=pdf_url, browser_url=browser_url)

    def fake_runner(command: Sequence[str]) -> smoke.DiagnosticChildResult:
        """记录命令并写入 pass/diagnostic-only artifact。"""

        url = _command_value(command, "--url")
        output = Path(_command_value(command, "--output"))
        commands_by_url[url] = tuple(command)
        if url == html_url:
            _write_payload(output, _diagnostic_payload(url=url))
        elif url == pdf_url:
            _write_payload(
                output,
                _diagnostic_payload(
                    url=url,
                    content_type="application/pdf",
                    raw_length=512,
                    fetch_length=smoke.PDF_FETCH_MIN_CHARS,
                    docling_invoked=True,
                    docling_completed=True,
                ),
            )
        elif url == browser_url:
            _write_payload(
                output,
                _diagnostic_payload(
                    url=url,
                    fetch_backend="playwright",
                    playwright_sampled=True,
                    playwright_ok=True,
                ),
            )
        elif url == external_url:
            _write_payload(
                output,
                _diagnostic_payload(
                    url=url,
                    comparison_bucket="playwright_challenge_detected",
                ),
            )
        else:
            raise AssertionError(f"unexpected url: {url}")
        return smoke.DiagnosticChildResult(returncode=0, stdout="", stderr="")

    _patch_local_cases_as_pass(monkeypatch, output_dir=tmp_path / "out")
    monkeypatch.setattr(smoke, "_run_diagnostic_command", fake_runner)
    _patch_direct_assembly_and_search_cases(monkeypatch)

    exit_code = smoke.main(
        [
            "--output-dir",
            str(tmp_path / "out"),
            "--run-label",
            "include-playwright-external-only",
            "--include-playwright",
            "--external-url-file",
            str(url_file),
            "--external-limit",
            "1",
        ]
    )

    summary = _load_json_object(tmp_path / "out" / "summary.json")
    diagnostic_only = _list_field(summary, "diagnostic_only")
    assert exit_code == 0
    assert "--skip-playwright" not in commands_by_url[external_url]
    assert _object_value(diagnostic_only[0])["bucket"] == "playwright_challenge_detected"


def test_missing_external_file_returns_operator_input_error(tmp_path: Path) -> None:
    """显式传入不存在的 external URL 文件时应返回 operator input error。"""

    exit_code = smoke.main(
        [
            "--output-dir",
            str(tmp_path / "out"),
            "--run-label",
            "missing-external-file",
            "--external-url-file",
            str(tmp_path / "missing.jsonl"),
            "--external-limit",
            "1",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "out" / "summary.json").exists()


def test_log_level_cli_accepts_lowercase_verbose() -> None:
    """--log-level 应不区分大小写并投影为 LogLevel。"""

    namespace = smoke._parse_args(["--log-level", "verbose", "--external-limit", "0"])
    options = smoke._options_from_namespace(namespace)

    assert options.log_level == smoke.LogLevel.VERBOSE


@pytest.mark.parametrize(
    ("file_name", "file_content"),
    [
        ("urls.jsonl", "{not-json\n"),
        ("urls.txt", "ftp://example.com/not-http\n"),
    ],
)
def test_invalid_external_file_returns_operator_input_error_before_local_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_name: str,
    file_content: str,
) -> None:
    """非法 external 文件应在 local fixture 和 diagnostics 启动前失败。"""

    url_file = tmp_path / file_name
    url_file.write_text(file_content, encoding="utf-8")
    output_dir = tmp_path / "out"
    fixture_starts: list[str] = []

    @contextlib.contextmanager
    def raising_server() -> Iterator[smoke.LocalFixtureUrls]:
        """非法参数路径不应启动 local fixture server。"""

        fixture_starts.append("started")
        raise AssertionError("local fixture should not start for invalid external URL file")
        yield smoke.LocalFixtureUrls(html_url="", pdf_url="", browser_url="")

    def raising_runner(command: Sequence[str]) -> smoke.DiagnosticChildResult:
        """非法参数路径不应触发 diagnostics runner。"""

        raise AssertionError(f"runner should not be called: {command}")

    monkeypatch.setattr(smoke, "_running_local_fixture_server", raising_server)
    monkeypatch.setattr(smoke, "_run_diagnostic_command", raising_runner)

    exit_code = smoke.main(
        [
            "--output-dir",
            str(output_dir),
            "--run-label",
            "invalid-external-file",
            "--external-url-file",
            str(url_file),
            "--external-limit",
            "1",
        ]
    )

    assert exit_code == 2
    assert fixture_starts == []
    assert not output_dir.exists()


def test_external_limit_and_summary_paths_are_predictable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """external-limit 应限制 runner 调用次数，summary 路径应固定在 output-dir 下。"""

    html_url = "http://127.0.0.1:43117/index.html"
    pdf_url = "http://127.0.0.1:43117/fixture.pdf"
    browser_url = "http://127.0.0.1:43117/client-rendered.html"
    url_file = tmp_path / "urls.jsonl"
    url_file.write_text(
        "\n".join(
            (
                "# comment",
                "",
                json.dumps({"url": "https://example.com/a"}),
                "  # another comment",
                json.dumps({"url": "https://example.com/b"}),
                json.dumps({"url": "https://example.com/c"}),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    called_urls: list[str] = []

    @contextlib.contextmanager
    def fake_server() -> Iterator[smoke.LocalFixtureUrls]:
        """提供 deterministic local fixture URL，不启动真实 HTTP server。"""

        yield smoke.LocalFixtureUrls(html_url=html_url, pdf_url=pdf_url, browser_url=browser_url)

    def fake_runner(command: Sequence[str]) -> smoke.DiagnosticChildResult:
        """写入 synthetic diagnostics artifact 并记录 URL。"""

        url = _command_value(command, "--url")
        output = Path(_command_value(command, "--output"))
        if url == html_url:
            _write_payload(output, _diagnostic_payload(url=url))
        elif url == pdf_url:
            _write_payload(
                output,
                _diagnostic_payload(
                    url=url,
                    content_type="application/pdf",
                    raw_length=512,
                    fetch_length=smoke.PDF_FETCH_MIN_CHARS,
                    docling_invoked=True,
                    docling_completed=True,
                ),
            )
        elif url == browser_url:
            _write_payload(
                output,
                _diagnostic_payload(
                    url=url,
                    fetch_backend="playwright",
                    playwright_sampled=True,
                    playwright_ok=True,
                ),
            )
        else:
            called_urls.append(url)
            _write_payload(output, _diagnostic_payload(url=url, comparison_bucket="all_failed"))
        return smoke.DiagnosticChildResult(returncode=0, stdout="", stderr="")

    _patch_local_cases_as_pass(monkeypatch, output_dir=output_dir)
    monkeypatch.setattr(smoke, "_run_diagnostic_command", fake_runner)
    _patch_direct_assembly_and_search_cases(monkeypatch)

    exit_code = smoke.main(
        [
            "--output-dir",
            str(output_dir),
            "--run-label",
            "external-limit",
            "--external-url-file",
            str(url_file),
            "--external-limit",
            "2",
        ]
    )

    summary = _load_json_object(output_dir / "summary.json")
    assert exit_code == 0
    assert called_urls == ["https://example.com/a", "https://example.com/b"]
    assert summary["status"] == "passed"
    assert summary["output_dir"] == str(output_dir)
    assert len(_list_field(summary, "local_cases")) == 1
    assert len(_list_field(summary, "external_cases")) == 2
    assert len(_list_field(summary, "search_cases")) == 4
    assert _list_field(summary, "skips") == []
    assert (output_dir / "summary.md").is_file()


def _diagnostic_payload(
    *,
    url: str,
    requests_ok: bool = True,
    fetch_ok: bool = True,
    content_type: str = "text/html; charset=utf-8",
    raw_length: int = 128,
    fetch_length: int = 64,
    docling_invoked: bool = False,
    docling_completed: bool = False,
    docling_init_error: bool = False,
    comparison_bucket: str = "all_success",
    stream_name: str = "page.pdf",
    fetch_backend: str = "requests",
    playwright_sampled: bool = False,
    playwright_ok: bool = False,
) -> JsonObject:
    """构造 schema v2 synthetic diagnostics artifact。"""

    evidence: JsonObject = {
        "invoked": docling_invoked,
        "stream_name": stream_name if docling_invoked else "",
        "raw_bytes_length": raw_length if docling_invoked else None,
        "target_module": "dayu.tools.web.web_tools",
        "target_function": "_docling_convert_to_markdown",
        "original_completed": docling_completed,
        "original_exception_type": "DoclingRuntimeInitializationError" if docling_init_error else "",
        "docling_runtime_initialization_error": docling_init_error,
        "safe_url": smoke.project_safe_url_or_empty(url),
    }
    requests_outcome = "completed" if requests_ok else "failed"
    fetch_outcome = "completed" if fetch_ok else "failed"
    playwright_outcome = (
        "completed" if playwright_ok else "failed" if playwright_sampled else "skipped"
    )
    return {
        "schema_version": "web-diagnostics-v2",
        "diagnostic_schema_version": "web-diagnostics-v2",
        "diagnostic_schema_revision": 2,
        "safe_url": smoke.project_safe_url_or_empty(url),
        "comparison_bucket": comparison_bucket,
        "observed_bucket": comparison_bucket,
        "diagnostic_action_hint": "查看诊断证据。",
        "requests_profile": {
            "sampled": True,
            "ok": requests_ok,
            "stage": "requests",
            "outcome": requests_outcome,
            "safe_url": smoke.project_safe_url_or_empty(url),
            "elapsed_seconds": 0.1,
            "backend": "requests",
            "content_length": raw_length,
            "content_digest": "sha256:" + "a" * 64,
            "http_status": 200,
            "content_type": content_type.split(";", 1)[0].lower(),
            "response_headers": {
                "present_names": ["content-type"],
                "sensitive_names": [],
                "content_type": content_type.split(";", 1)[0].lower(),
                "content_length": None,
            },
            "challenge_decision": "none",
        },
        "fetch_web_page_profile": {
            "sampled": True,
            "ok": fetch_ok,
            "stage": "fetch_web_page",
            "outcome": fetch_outcome,
            "safe_url": smoke.project_safe_url_or_empty(url),
            "elapsed_seconds": 0.1,
            "content_length": fetch_length,
            "content_digest": "sha256:" + "b" * 64,
            "http_status": None,
            "backend": fetch_backend,
            "docling_conversion_invocation_evidence": evidence,
        },
        "docling_conversion_invocation_evidence": evidence,
        "playwright_profile": {
            "sampled": playwright_sampled,
            "ok": playwright_ok,
            "stage": "playwright",
            "outcome": playwright_outcome,
            "safe_url": smoke.project_safe_url_or_empty(url),
            "elapsed_seconds": 0.1,
            "backend": "playwright",
            "content_length": raw_length if playwright_ok else None,
            "content_digest": "sha256:" + "c" * 64 if playwright_ok else "",
            "http_status": 200 if playwright_ok else None,
            "browser_executed": playwright_ok,
            "challenge_decision": "none",
        },
    }


def _write_payload(path: Path, payload: Mapping[str, JsonValue]) -> None:
    """写入 JSON payload。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _payload_without_docling_evidence(payload: JsonObject) -> JsonObject:
    """移除 synthetic payload 中的 Docling evidence 字段。"""

    copied = dict(payload)
    copied.pop("docling_conversion_invocation_evidence", None)
    fetch_profile = copied.get("fetch_web_page_profile")
    assert isinstance(fetch_profile, Mapping)
    copied_fetch_profile = {str(key): value for key, value in fetch_profile.items()}
    copied_fetch_profile.pop("docling_conversion_invocation_evidence", None)
    copied["fetch_web_page_profile"] = copied_fetch_profile
    return copied


def _fixture_case(case_name: str) -> smoke.LocalFixtureCase:
    """按名称取得 deterministic 父进程 fixture registration。"""

    return next(
        case for case in smoke._build_local_fixture_cases(43117)
        if case.case_name == case_name
    )


def _frozen_ledger_for_case(
    case: smoke.LocalFixtureCase,
    *,
    include_accepted: bool = True,
    accepted_response_digest: str | None = None,
    negative_controls_rejected: bool = True,
    include_method_negative: bool = True,
) -> smoke.FrozenFixtureLedger:
    """构造只含 typed digest/count 事实的 frozen ledger。

    Args:
        case: 父进程 fixture registration。
        include_accepted: 是否加入当前 case 的 accepted observation。
        accepted_response_digest: 可选替代 accepted response digest。
        negative_controls_rejected: negative observations 是否标记为 rejected。
        include_method_negative: 是否加入 HEAD/NEGATIVE_METHOD observation。

    Returns:
        可直接提供给 classifier 的 frozen ledger。

    Raises:
        无。
    """

    observations: list[smoke.FixtureRequestObservation] = []
    if include_accepted:
        observations.append(
            smoke.FixtureRequestObservation(
                token_digest=case.token_digest,
                method="GET",
                normalized_path=case.path,
                response_kind=case.response_kind,
                response_digest=accepted_response_digest or case.response_digest,
                accepted=True,
            )
        )
    for kind in (
        smoke.FixtureResponseKind.NEGATIVE_MISSING_TOKEN,
        smoke.FixtureResponseKind.NEGATIVE_WRONG_TOKEN,
        smoke.FixtureResponseKind.NEGATIVE_REPLAY_TOKEN,
        smoke.FixtureResponseKind.NEGATIVE_METHOD,
        smoke.FixtureResponseKind.NEGATIVE_UNKNOWN_PATH,
    ):
        if (
            kind is smoke.FixtureResponseKind.NEGATIVE_METHOD
            and not include_method_negative
        ):
            continue
        response = (
            b""
            if kind is smoke.FixtureResponseKind.NEGATIVE_METHOD
            else f"rejected:{kind.value}\n".encode("ascii")
        )
        observations.append(
            smoke.FixtureRequestObservation(
                token_digest=hashlib.sha256(kind.value.encode("ascii")).hexdigest(),
                method=(
                    "HEAD"
                    if kind is smoke.FixtureResponseKind.NEGATIVE_METHOD
                    else "GET"
                ),
                normalized_path=(
                    "/negative-control"
                    if kind is smoke.FixtureResponseKind.NEGATIVE_UNKNOWN_PATH
                    else case.path
                ),
                response_kind=kind,
                response_digest=smoke.content_diagnostic_from_bytes(response).digest,
                accepted=not negative_controls_rejected,
            )
        )
    return smoke.FrozenFixtureLedger(
        observations=tuple(observations),
        dropped_count=0,
        lifecycle=(
            "created",
            "server_started",
            f"child_started:{case.case_name}",
            "server_stopped",
            "frozen",
        ),
    )


def _diagnostic_payload_for_case(case: smoke.LocalFixtureCase) -> JsonObject:
    """按父进程 expected bytes 构造可被独立 oracle 验证的 v2 artifact。"""

    playwright_case = case.case_kind == "local_browser" or (
        case.case_kind == "local_filing"
        and case.case_name == "local-filing-playwright"
    )
    payload = _diagnostic_payload(
        url=case.url,
        content_type=(
            "application/pdf"
            if case.response_kind is smoke.FixtureResponseKind.PDF
            else "text/html; charset=utf-8"
        ),
        raw_length=case.response_length,
        fetch_length=case.response_length,
        docling_invoked=case.case_kind == "local_pdf" and case.case_name.endswith("-tool"),
        docling_completed=case.case_kind == "local_pdf" and case.case_name.endswith("-tool"),
        fetch_backend=case.expected_backend,
        playwright_sampled=playwright_case,
        playwright_ok=playwright_case,
    )
    profile_name = (
        "playwright_profile"
        if playwright_case
        else "fetch_web_page_profile"
        if case.case_name.endswith("-tool")
        else "requests_profile"
    )
    profile = _object_value(payload[profile_name])
    profile["content_length"] = case.response_length
    profile["content_digest"] = case.response_digest
    profile["backend"] = case.expected_backend
    profile["outcome"] = "completed"
    profile["sampled"] = True
    profile["ok"] = True
    if profile_name == "fetch_web_page_profile":
        profile["projected_content_length"] = max(
            smoke.PDF_FETCH_MIN_CHARS,
            case.response_length,
        )
        profile["projected_content_digest"] = "sha256:" + "d" * 64
    if case.case_kind == "local_challenge_control":
        profile["challenge_decision"] = "confirmed"
    if case.case_name == "local-filing-playwright":
        profile["storage_state"] = {"input_used": True}
        profile["rendered_html_length"] = case.response_length
        profile["rendered_text_length"] = 1024
        profile["network_event_count"] = 2
        profile["network_event_limit"] = 512
    payload[profile_name] = profile
    for skipped_profile_name in {
        "requests_profile",
        "fetch_web_page_profile",
        "playwright_profile",
    } - {profile_name}:
        skipped = _object_value(payload[skipped_profile_name])
        skipped["sampled"] = False
        skipped["outcome"] = "skipped"
        skipped["ok"] = False
        payload[skipped_profile_name] = skipped
    return payload


def _load_json_object(path: Path) -> JsonObject:
    """读取 JSON 对象文件。"""

    payload = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, Mapping)
    return {str(key): value for key, value in payload.items()}


def _list_field(payload: Mapping[str, JsonValue], key: str) -> list[JsonValue]:
    """读取 JSON 数组字段。"""

    value = payload.get(key)
    assert isinstance(value, list)
    return value


def _object_value(value: JsonValue) -> JsonObject:
    """把 JSON 值收窄为 JSON 对象。"""

    assert isinstance(value, Mapping)
    return {str(key): item for key, item in value.items()}


def _tool_definition(
    name: str,
    callable_: ToolCallable,
    *,
    truncate_max_chars: int | None = None,
) -> ToolDefinition:
    """构造 smoke 测试用最小工具定义。

    :param name: 工具名。
    :param callable_: 工具 callable。
    :param truncate_max_chars: 可选 text chars 截断声明。
    :returns: 工具定义。
    :raises Exception: schema 构造失败时抛出。
    """

    truncate = (
        ToolTruncateSpec(
            enabled=True,
            strategy=ToolTruncationStrategy.TEXT_CHARS,
            limits={"max_chars": truncate_max_chars},
            target_field="content",
            field_path=None,
            ttl_seconds=None,
        )
        if truncate_max_chars is not None
        else None
    )
    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=f"{name} test tool",
                parameters=ToolParametersSchema(
                    type="object",
                    properties={},
                    required=(),
                    additional_properties=False,
                ),
            ),
        ),
        callable=callable_,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=truncate,
        display=None,
        tags=(),
    )


def _patch_direct_assembly_and_search_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    """为高层 smoke 编排测试替换直接工具调用 cases。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    def fake_assembly_case(
        *,
        fixture_urls: smoke.LocalFixtureUrls,
        diagnostics_dir: Path,
    ) -> smoke.SmokeCaseResult:
        """返回 deterministic local assembly pass case。"""

        return smoke.SmokeCaseResult(
            case_name="local-assembly-config",
            case_kind="local_assembly_config",
            url=fixture_urls.html_url,
            status="passed",
            bucket="passed",
            evidence_path=str(diagnostics_dir / "local-assembly-config.json"),
            suggested_next_step="",
            reason="",
            exit_code=0,
        )

    def fake_search_cases(*, options: smoke.SmokeOptions) -> list[smoke.SmokeCaseResult]:
        """返回 deterministic search diagnostic cases。"""

        return [
            smoke.SmokeCaseResult(
                case_name=f"search-provider-{provider}",
                case_kind="search_provider",
                url="",
                status="diagnostic_only",
                bucket="search_provider_passed",
                evidence_path=str(
                    options.output_dir
                    / "diagnostics"
                    / "search"
                    / f"search-provider-{provider}.json"
                ),
                suggested_next_step="search diagnostic only",
                reason="search provider case 只作为 diagnostic-only。",
                exit_code=0,
            )
            for provider in ("auto", "tavily", "serper", "duckduckgo")
        ]

    monkeypatch.setattr(smoke, "_run_local_assembly_config_case", fake_assembly_case)
    monkeypatch.setattr(smoke, "_run_search_provider_cases", fake_search_cases)


def _patch_local_cases_as_pass(
    monkeypatch: pytest.MonkeyPatch,
    *,
    output_dir: Path,
) -> None:
    """让只关心 external 编排的测试绕过真实 local oracle。"""

    def fake_local_cases(
        *,
        options: smoke.SmokeOptions,
        runner: smoke.DiagnosticRunner,
    ) -> list[smoke.SmokeCaseResult]:
        """返回已由独立单元测试覆盖的 local passed cases。"""

        del runner
        assert options.output_dir == output_dir
        return [
            smoke.SmokeCaseResult(
                case_name="local-html-requests",
                case_kind="local_html",
                url="http://127.0.0.1/index.html",
                status="passed",
                bucket="passed",
                evidence_path=str(output_dir / "local.json"),
                suggested_next_step="",
                reason="",
                exit_code=0,
            )
        ]

    monkeypatch.setattr(smoke, "_run_local_cases", fake_local_cases)


def _command_value(command: Sequence[str], option_name: str) -> str:
    """读取命令行选项值。"""

    option_index = command.index(option_name)
    return command[option_index + 1]
