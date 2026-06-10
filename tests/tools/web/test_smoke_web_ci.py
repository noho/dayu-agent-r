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

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from utils import smoke_web_ci as smoke

JsonObject = dict[str, JsonValue]


def test_not_opted_in_writes_skipped_summary_and_does_not_call_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未显式 opt-in 时只写 skipped summary，不能调用 diagnostics runner。"""

    monkeypatch.delenv("DAYU_RUN_WEB_CI_SMOKE", raising=False)

    def raising_runner(command: Sequence[str]) -> smoke.DiagnosticChildResult:
        """未 opt-in 路径不应触发本 runner。"""

        raise AssertionError(f"runner should not be called: {command}")

    monkeypatch.setattr(smoke, "_run_diagnostic_command", raising_runner)

    exit_code = smoke.main(["--output-dir", str(tmp_path), "--run-label", "skip-case"])

    summary = _load_json_object(tmp_path / "summary.json")
    assert exit_code == 0
    assert summary["status"] == "skipped"
    assert summary["exit_code"] == 0
    assert summary["run_label"] == "skip-case"
    assert (tmp_path / "summary.md").is_file()
    skips = _list_field(summary, "skips")
    assert len(skips) == 1
    assert _object_value(skips[0])["bucket"] == "not_opted_in"


def test_local_fixture_urls_and_pdf_fixture_are_stable() -> None:
    """本地 fixture URL 与 PDF 文本 fixture 应稳定可测。"""

    urls = smoke._local_fixture_urls(43117)
    pdf_bytes = smoke._pdf_fixture_bytes()

    assert urls.html_url == "http://127.0.0.1:43117/index.html"
    assert urls.pdf_url == "http://127.0.0.1:43117/fixture.pdf"
    assert b"Dayu Web Smoke PDF" in pdf_bytes
    assert b"This PDF verifies Docling conversion." in pdf_bytes
    assert smoke.PDF_FETCH_MIN_CHARS >= 20


def test_opted_in_runs_local_html_and_pdf_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """opt-in 后必须运行 local HTML 与 PDF cases。"""

    monkeypatch.setenv("DAYU_RUN_WEB_CI_SMOKE", "1")
    html_url = "http://127.0.0.1:43117/index.html"
    pdf_url = "http://127.0.0.1:43117/fixture.pdf"
    called_commands: list[Sequence[str]] = []

    @contextlib.contextmanager
    def fake_server() -> Iterator[smoke.LocalFixtureUrls]:
        """提供 deterministic local fixture URL，不启动真实 HTTP server。"""

        yield smoke.LocalFixtureUrls(html_url=html_url, pdf_url=pdf_url)

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
        else:
            raise AssertionError(f"unexpected url: {url}")
        return smoke.DiagnosticChildResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(smoke, "_running_local_fixture_server", fake_server)
    monkeypatch.setattr(smoke, "_run_diagnostic_command", fake_runner)

    exit_code = smoke.main(["--output-dir", str(tmp_path), "--run-label", "slice3-local"])

    summary = _load_json_object(tmp_path / "summary.json")
    assert exit_code == 0
    assert summary["status"] == "passed"
    assert summary["exit_code"] == 0
    local_cases = _list_field(summary, "local_cases")
    assert [str(_object_value(item)["case_kind"]) for item in local_cases] == ["local_html", "local_pdf"]
    assert len(called_commands) == 2
    assert all("--allow-private-network-url" in command for command in called_commands)
    assert all("--skip-playwright" in command for command in called_commands)


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
        suggested_next_step="安装或修复 Docling runtime 后重跑 opt-in smoke。",
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


def test_pdf_invocation_blocker_writes_artifact_and_stops_external_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF fetch 成功但缺 invocation evidence 时应写 blocker 并停止 external。"""

    html_url = "http://127.0.0.1:43117/index.html"
    pdf_url = "http://127.0.0.1:43117/fixture.pdf"
    external_file = tmp_path / "urls.txt"
    external_file.write_text("https://example.com/external\n", encoding="utf-8")
    called_urls: list[str] = []

    @contextlib.contextmanager
    def fake_server() -> Iterator[smoke.LocalFixtureUrls]:
        """提供 deterministic local fixture URL，不启动真实 HTTP server。"""

        yield smoke.LocalFixtureUrls(html_url=html_url, pdf_url=pdf_url)

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
    options = smoke.SmokeOptions(
        run_live=True,
        output_dir=tmp_path,
        request_timeout=1.0,
        tool_timeout_budget=1.0,
        include_playwright=False,
        external_url_file=external_file,
        external_limit=1,
        diagnostic_only_external=True,
        run_label="blocker",
    )

    summary = smoke._execute_smoke(options=options, runner=fake_runner)

    blocker_path = tmp_path / "blockers" / "local-pdf-docling-invocation-blocker.md"
    assert called_urls == [html_url, pdf_url]
    assert summary.status == "failed"
    assert summary.exit_code == 1
    assert summary.external_cases == ()
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


def test_external_limit_and_summary_paths_are_predictable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """external-limit 应限制 runner 调用次数，summary 路径应固定在 output-dir 下。"""

    monkeypatch.setenv("DAYU_RUN_WEB_CI_SMOKE", "1")
    html_url = "http://127.0.0.1:43117/index.html"
    pdf_url = "http://127.0.0.1:43117/fixture.pdf"
    url_file = tmp_path / "urls.jsonl"
    url_file.write_text(
        "\n".join(
            (
                json.dumps({"url": "https://example.com/a"}),
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

        yield smoke.LocalFixtureUrls(html_url=html_url, pdf_url=pdf_url)

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
        else:
            called_urls.append(url)
            _write_payload(output, _diagnostic_payload(url=url, comparison_bucket="all_failed"))
        return smoke.DiagnosticChildResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(smoke, "_running_local_fixture_server", fake_server)
    monkeypatch.setattr(smoke, "_run_diagnostic_command", fake_runner)

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
    assert len(_list_field(summary, "local_cases")) == 2
    assert len(_list_field(summary, "external_cases")) == 2
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
            "docling_conversion_invocation_evidence": evidence,
        },
        "docling_conversion_invocation_evidence": evidence,
        "playwright_profile": {
            "sampled": False,
            "ok": False,
            "skipped": True,
            "status": "skipped",
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


def _command_value(command: Sequence[str], option_name: str) -> str:
    """读取命令行选项值。"""

    option_index = command.index(option_name)
    return command[option_index + 1]
