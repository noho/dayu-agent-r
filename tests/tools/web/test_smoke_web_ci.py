"""Web CI smoke CLI 与 summary contract 的确定性测试。"""

from __future__ import annotations

import json
import sys
import contextlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Iterator, cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_declaration import ToolCallable, ToolDefinition
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


def test_default_run_executes_local_html_pdf_and_browser_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """默认运行必须执行 local HTML、PDF 与 browser cases。"""

    html_url = "http://127.0.0.1:43117/index.html"
    pdf_url = "http://127.0.0.1:43117/fixture.pdf"
    browser_url = "http://127.0.0.1:43117/client-rendered.html"
    called_commands: list[Sequence[str]] = []
    external_urls: list[str] = []

    @contextlib.contextmanager
    def fake_server() -> Iterator[smoke.LocalFixtureUrls]:
        """提供 deterministic local fixture URL，不启动真实 HTTP server。"""

        yield smoke.LocalFixtureUrls(html_url=html_url, pdf_url=pdf_url, browser_url=browser_url)

    def fake_runner(command: Sequence[str]) -> smoke.DiagnosticChildResult:
        """写入 synthetic local diagnostics artifact 并记录命令。"""

        called_commands.append(command)
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
            external_urls.append(url)
            _write_payload(output, _diagnostic_payload(url=url, comparison_bucket="all_failed"))
        return smoke.DiagnosticChildResult(returncode=0, stdout=f"diagnostic result for {url}\n", stderr="")

    monkeypatch.setattr(smoke, "_running_local_fixture_server", fake_server)
    monkeypatch.setattr(smoke, "_run_diagnostic_command", fake_runner)
    _patch_direct_assembly_and_search_cases(monkeypatch)

    exit_code = smoke.main(["--output-dir", str(tmp_path), "--run-label", "slice3-local"])
    captured = capsys.readouterr()

    summary = _load_json_object(tmp_path / "summary.json")
    assert exit_code == 0
    assert "SMOKE START Web CI smoke" in captured.out
    assert "SMOKE LOG_LEVEL DEBUG" in captured.out
    assert "SMOKE STATUS passed" in captured.out
    assert "SMOKE LOCAL_CASES 4" in captured.out
    assert "SMOKE EXTERNAL_CASES 2" in captured.out
    assert "SMOKE SEARCH_CASES 4" in captured.out
    assert "web smoke execution started" in caplog.text
    assert "stdout_prefix=diagnostic result for" in caplog.text
    assert summary["status"] == "passed"
    assert summary["exit_code"] == 0
    local_cases = _list_field(summary, "local_cases")
    external_cases = _list_field(summary, "external_cases")
    search_cases = _list_field(summary, "search_cases")
    diagnostic_only = _list_field(summary, "diagnostic_only")
    assert [str(_object_value(item)["case_kind"]) for item in local_cases] == [
        "local_html",
        "local_pdf",
        "local_browser",
        "local_assembly_config",
    ]
    assert [str(_object_value(item)["case_kind"]) for item in search_cases] == [
        "search_provider",
        "search_provider",
        "search_provider",
        "search_provider",
    ]
    assert len(called_commands) == 5
    assert len(external_cases) == 2
    assert len(search_cases) == 4
    assert len(diagnostic_only) == 6
    assert external_urls == ["https://www.reuters.com/world/", "https://apnews.com/"]
    commands_by_url = {_command_value(command, "--url"): command for command in called_commands}
    assert "--allow-private-network-url" in commands_by_url[html_url]
    assert "--allow-private-network-url" in commands_by_url[pdf_url]
    assert "--allow-private-network-url" in commands_by_url[browser_url]
    assert "--skip-playwright" in commands_by_url[html_url]
    assert "--skip-playwright" in commands_by_url[pdf_url]
    assert "--skip-playwright" not in commands_by_url[browser_url]
    for external_url in external_urls:
        assert "--allow-private-network-url" not in commands_by_url[external_url]
        assert "--skip-playwright" in commands_by_url[external_url]


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
                value={"content": smoke._HTML_FIXTURE_BODY, "title": "Fixture"},
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
    assert (
        artifact["assembly_path"]
        == "ConfigLoader -> assemble_effective_tool_provider_configs -> discover_service_tools -> ToolDefinition.callable"
    )


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
    """synthetic diagnostics artifact 应按 Slice 2 表格分类。"""

    html_pass_path = tmp_path / "html-pass.json"
    _write_payload(html_pass_path, _diagnostic_payload(url="http://127.0.0.1/index.html"))
    html_pass = smoke._classify_child_result(
        case_name="local-html",
        case_kind="local_html",
        fallback_url="http://127.0.0.1/index.html",
        artifact_path=html_pass_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
    )
    assert html_pass.status == "passed"
    assert html_pass.exit_code == 0

    html_fail_path = tmp_path / "html-fail.json"
    _write_payload(
        html_fail_path,
        _diagnostic_payload(url="http://127.0.0.1/index.html", requests_ok=False),
    )
    html_fail = smoke._classify_child_result(
        case_name="local-html",
        case_kind="local_html",
        fallback_url="http://127.0.0.1/index.html",
        artifact_path=html_fail_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
    )
    assert html_fail.status == "failed"
    assert html_fail.bucket == "local_requests_failure"
    assert html_fail.exit_code == 1

    schema_gap_path = tmp_path / "schema-gap.json"
    schema_gap_payload = _diagnostic_payload(url="http://127.0.0.1/index.html")
    schema_gap_payload.pop("diagnostic_schema_version")
    schema_gap_payload.pop("schema_version")
    _write_payload(schema_gap_path, schema_gap_payload)
    schema_gap = smoke._classify_child_result(
        case_name="local-html",
        case_kind="local_html",
        fallback_url="http://127.0.0.1/index.html",
        artifact_path=schema_gap_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
    )
    assert schema_gap.status == "failed"
    assert schema_gap.bucket == "diagnostic_schema_gap"
    assert schema_gap.exit_code == 2

    pdf_pass_path = tmp_path / "pdf-pass.json"
    _write_payload(
        pdf_pass_path,
        _diagnostic_payload(
            url="http://127.0.0.1/fixture.pdf",
            content_type="application/pdf",
            raw_length=512,
            fetch_length=smoke.PDF_FETCH_MIN_CHARS,
            docling_invoked=True,
            docling_completed=True,
        ),
    )
    pdf_pass = smoke._classify_child_result(
        case_name="local-pdf",
        case_kind="local_pdf",
        fallback_url="http://127.0.0.1/fixture.pdf",
        artifact_path=pdf_pass_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
    )
    assert pdf_pass.status == "passed"
    assert pdf_pass.exit_code == 0

    pdf_skip_path = tmp_path / "pdf-skip.json"
    _write_payload(
        pdf_skip_path,
        _diagnostic_payload(
            url="http://127.0.0.1/fixture.pdf",
            content_type="application/pdf",
            docling_invoked=True,
            docling_completed=False,
            docling_init_error=True,
        ),
    )
    pdf_skip = smoke._classify_child_result(
        case_name="local-pdf",
        case_kind="local_pdf",
        fallback_url="http://127.0.0.1/fixture.pdf",
        artifact_path=pdf_skip_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
    )
    assert pdf_skip.status == "skipped"
    assert pdf_skip.bucket == "docling_runtime_initialization_error"
    assert pdf_skip.exit_code == 0

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


def test_local_browser_case_without_playwright_backend_is_diagnostic_only(tmp_path: Path) -> None:
    """browser fixture 未观察到 fetch_web_page browser backend 时只产生诊断项。"""

    browser_path = tmp_path / "browser.json"
    _write_payload(
        browser_path,
        _diagnostic_payload(
            url="http://127.0.0.1/client-rendered.html",
            fetch_backend="requests",
            playwright_sampled=True,
            playwright_ok=True,
        ),
    )

    browser = smoke._classify_child_result(
        case_name="local-browser",
        case_kind="local_browser",
        fallback_url="http://127.0.0.1/client-rendered.html",
        artifact_path=browser_path,
        child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
    )
    summary = smoke._summary_from_cases(
        run_label="browser-diagnostic",
        output_dir=tmp_path,
        local_cases=(browser,),
        external_cases=(),
    )

    assert browser.status == "diagnostic_only"
    assert browser.bucket == "browser_backend_not_observed"
    assert browser.exit_code == 0
    assert summary.status == "diagnostic_only"
    assert summary.exit_code == 0
    assert len(summary.diagnostic_only) == 1


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
            "diagnostic_schema_gap",
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
        artifact_path = tmp_path / f"{case_name}.json"
        _write_payload(artifact_path, payload)
        result = smoke._classify_child_result(
            case_name="local-pdf",
            case_kind="local_pdf",
            fallback_url="http://127.0.0.1/fixture.pdf",
            artifact_path=artifact_path,
            child_result=smoke.DiagnosticChildResult(returncode=0, stdout="", stderr=""),
        )
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


def test_pdf_invocation_blocker_runs_search_cases_and_stops_external_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF invocation blocker 应写 artifact、保留 search cases 并停止 external。"""

    html_url = "http://127.0.0.1:43117/index.html"
    pdf_url = "http://127.0.0.1:43117/fixture.pdf"
    browser_url = "http://127.0.0.1:43117/client-rendered.html"
    external_file = tmp_path / "urls.txt"
    external_file.write_text("https://example.com/external\n", encoding="utf-8")
    called_urls: list[str] = []

    @contextlib.contextmanager
    def fake_server() -> Iterator[smoke.LocalFixtureUrls]:
        """提供 deterministic local fixture URL，不启动真实 HTTP server。"""

        yield smoke.LocalFixtureUrls(html_url=html_url, pdf_url=pdf_url, browser_url=browser_url)

    def fake_runner(command: Sequence[str]) -> smoke.DiagnosticChildResult:
        """写入 local diagnostics artifact 并拒绝 external 调用。"""

        url = _command_value(command, "--url")
        called_urls.append(url)
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
                    docling_invoked=False,
                    docling_completed=False,
                ),
            )
        else:
            raise AssertionError(f"external should not run after blocker: {url}")
        return smoke.DiagnosticChildResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(smoke, "_running_local_fixture_server", fake_server)
    _patch_direct_assembly_and_search_cases(monkeypatch)
    options = smoke.SmokeOptions(
        output_dir=tmp_path,
        request_timeout=1.0,
        tool_timeout_budget=1.0,
        include_playwright=False,
        external_url_file=external_file,
        external_limit=1,
        diagnostic_only_external=True,
        run_label="blocker",
        log_level=smoke.LogLevel.DEBUG,
    )

    summary = smoke._execute_smoke(options=options, runner=fake_runner)

    blocker_path = tmp_path / "blockers" / "local-pdf-docling-invocation-blocker.md"
    assert called_urls == [html_url, pdf_url]
    assert summary.status == "failed"
    assert summary.exit_code == 1
    assert summary.external_cases == ()
    assert len(summary.search_cases) == 4
    assert len(summary.diagnostic_only) == 4
    assert blocker_path.is_file()
    assert "不能用 content-type" in blocker_path.read_text(encoding="utf-8")


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

    monkeypatch.setattr(smoke, "_running_local_fixture_server", fake_server)
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

    monkeypatch.setattr(smoke, "_running_local_fixture_server", fake_server)
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

    monkeypatch.setattr(smoke, "_running_local_fixture_server", fake_server)
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
    assert "--skip-playwright" in commands_by_url[html_url]
    assert "--skip-playwright" in commands_by_url[pdf_url]
    assert "--skip-playwright" not in commands_by_url[browser_url]
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

    monkeypatch.setattr(smoke, "_running_local_fixture_server", fake_server)
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
    assert len(_list_field(summary, "local_cases")) == 4
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
    """构造 synthetic diagnostics artifact。"""

    evidence: JsonObject = {
        "invoked": docling_invoked,
        "stream_name": stream_name if docling_invoked else "",
        "raw_bytes_length": raw_length if docling_invoked else None,
        "target_module": "dayu.tools.web.web_tools",
        "target_function": "_docling_convert_to_markdown",
        "original_completed": docling_completed,
        "original_exception_type": "DoclingRuntimeInitializationError" if docling_init_error else "",
        "docling_runtime_initialization_error": docling_init_error,
        "diagnostic_url": url,
    }
    return {
        "schema_version": "web-diagnostics-v1",
        "diagnostic_schema_version": "web-diagnostics-v1",
        "diagnostic_schema_revision": 1,
        "url": url,
        "comparison_bucket": comparison_bucket,
        "observed_bucket": comparison_bucket,
        "diagnostic_action_hint": "查看诊断证据。",
        "requests_profile": {
            "sampled": True,
            "ok": requests_ok,
            "result": {
                "ok": requests_ok,
                "status": "completed" if requests_ok else "request_exception",
                "response_headers": {"Content-Type": content_type},
                "content_length": raw_length,
                "text_length": raw_length,
            },
        },
        "fetch_web_page_profile": {
            "sampled": True,
            "ok": fetch_ok,
            "status": "completed" if fetch_ok else "failed",
            "content_length": fetch_length,
            "fetch_backend": fetch_backend,
            "docling_conversion_invocation_evidence": evidence,
        },
        "docling_conversion_invocation_evidence": evidence,
        "playwright_profile": {
            "sampled": playwright_sampled,
            "ok": playwright_ok,
            "skipped": not playwright_sampled,
            "status": "completed" if playwright_ok else "skipped",
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


def _command_value(command: Sequence[str], option_name: str) -> str:
    """读取命令行选项值。"""

    option_index = command.index(option_name)
    return command[option_index + 1]
