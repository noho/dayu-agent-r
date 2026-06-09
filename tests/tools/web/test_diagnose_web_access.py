"""Web access diagnostics utility 的确定性测试。"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolCallable, ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.contracts.tool_schema import ToolFunctionSchema, ToolParametersSchema, ToolSchema
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


def test_storage_state_dir_resolves_existing_host_input_and_default_output(tmp_path: Path) -> None:
    """storage-state 目录应按 URL host 解析输入和输出路径。"""

    storage_dir = tmp_path / "state"
    storage_dir.mkdir()
    host_state = storage_dir / "example.com.json"
    host_state.write_text('{"cookies":[]}', encoding="utf-8")
    options = _options(storage_state_dir=str(storage_dir))

    storage_state_in, storage_state_out = diag._resolve_storage_state_paths(
        options,
        "https://example.com/report",
    )

    assert storage_state_in == str(host_state)
    assert storage_state_out == str(host_state)


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
            "all_success",
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
        "stdout_prefix": "out",
        "stderr_prefix": "err",
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
    assert summary["comparison_buckets"] == {"all_success": 1, "child_process_error": 1}
    assert summary["child_returncodes"] == {"7": 1}


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
    assert profile["status"] == "completed"
    assert profile["title"] == "Report"
    assert profile["final_url"] == "https://example.com/final"
    assert profile["fetch_backend"] == "requests"
    assert profile["content_prefix"] == "abcdef"
    assert profile["content_length"] == 6


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
    assert profile["status"] == "failed"
    assert profile["error_code"] == "blocked_by_site_policy"
    assert profile["message"] == "Target site blocked automated access."
    assert profile["hint"] == "[change_source] Use another source."
    assert profile["next_action"] == "change_source"
    assert profile["http_status"] is None
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
    assert payload["schema_version"] == "web-diagnostics-v1"
    assert payload["generated_at"] == "2026-06-09T00:00:00+00:00"
    assert payload["comparison_bucket"] == "all_success"


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
    skip_playwright: bool = False,
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
        skip_playwright=skip_playwright,
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

    payload: JsonObject = {
        "requests_profile": {
            "sampled": requests_sampled,
            "result": {
                "ok": requests_ok,
                "status": "completed" if requests_ok else "request_exception",
                "status_code": 200 if requests_ok else None,
            },
        },
        "fetch_web_page_profile": {
            "sampled": fetch_sampled,
            "ok": fetch_ok,
            "status": "completed" if fetch_ok else "failed",
            "error_code": "" if fetch_ok else "fetch_failed",
            "final_url": "https://example.com/fetch",
        },
        "playwright_profile": {
            "sampled": playwright_sampled,
            "ok": playwright_ok,
            "status": "completed" if playwright_ok else "skipped",
            "challenge_detected": challenge_detected,
            "challenge_signals": ["challenge"] if challenge_detected else [],
            "navigation": {
                "response_status": 200 if playwright_ok else None,
                "final_url": "https://example.com/browser",
            },
        },
    }
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
    allow_private_network_url: bool,
) -> JsonObject:
    """返回确定性 requests profile。"""

    assert url == "https://example.com"
    assert timeout_seconds > 0
    assert allow_private_network_url is False
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


def _fake_playwright_profile(url: str, options: diag.CliOptions) -> JsonObject:
    """返回确定性 Playwright profile。"""

    assert url == "https://example.com"
    assert options.url == "https://example.com"
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
