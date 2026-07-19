"""``dayu-cli upload_filings_from`` 与脚本 renderer/publisher 测试。"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Final, cast

import pytest

import dayu.cli.commands.fins as fins_command
import dayu.cli.main as cli_main
import dayu.cli.upload_script as upload_script
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.fins.resolver import FmpCompanyInfo, FmpCompanyInfoResolver
from dayu.fins.upload_batch import (
    UploadBatchPlan,
    UploadBatchPlanRequest,
    generate_upload_batch_plan,
)
from dayu.service.fins_direct import FinsDirectCommandService

_FIXTURE_SOURCE: Path = (
    Path(__file__).resolve().parents[1]
    / "fins"
    / "fixtures"
    / "aapl_xbrl"
    / "fil_0000320193-24-000123"
    / "aapl-20240928.htm"
)
_WINDOWS_ARTIFACT_DIR_ENV: Final[str] = "DAYU_R11_WINDOWS_ARTIFACT_DIR"
_WINDOWS_RECORDER_ARTIFACT_SUBDIRECTORY: Final[str] = "cmd-recorder"
_WINDOWS_CLI_ARTIFACT_SUBDIRECTORY: Final[str] = "cli-storage"
_R11_WINDOWS_WORKFLOW_PATH: Final[Path] = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "r11-upload-script-windows.yml"
)
_CAPTURED_BATCH_REQUESTS: list[UploadBatchPlanRequest] = []


def _capture_request_then_generate_plan(
    request: UploadBatchPlanRequest,
) -> UploadBatchPlan:
    """记录 CLI 传播的 request 后调用真实 Fins owner。

    :param request: CLI 构造的 batch request。
    :returns: Fins owner 生成的 typed plan。
    :raises Exception: 真实 Fins owner 的异常保持原样透传。
    """

    _CAPTURED_BATCH_REQUESTS.append(request)
    return generate_upload_batch_plan(request)


def _windows_test_artifact_directory(
    tmp_path: Path,
    *,
    subdirectory: str,
) -> Path:
    """选择 Windows real test 的确定性工作与证据目录。

    :param tmp_path: 普通本地测试的 pytest 临时目录。
    :param subdirectory: 显式 artifact root 下由当前 test 独占的子目录名。
    :returns: 未配置 artifact root 时返回 ``tmp_path``；否则返回重建后的确定子目录。
    :raises AssertionError: 显式 artifact root 不存在或不是目录时抛出。
    :raises OSError: 清理或创建确定子目录失败时透传。
    """

    configured_root = os.environ.get(_WINDOWS_ARTIFACT_DIR_ENV)
    if configured_root is None:
        return tmp_path
    artifact_root = Path(configured_root)
    if not artifact_root.is_dir():
        raise AssertionError(
            f"{_WINDOWS_ARTIFACT_DIR_ENV} must name an existing directory: "
            f"{artifact_root}"
        )
    artifact_directory = artifact_root / subdirectory
    shutil.rmtree(artifact_directory, ignore_errors=True)
    artifact_directory.mkdir()
    return artifact_directory


class _FakeFmpResolver:
    """记录单次 public resolve 的 FMP resolver fake。"""

    api_keys: list[str] = []
    calls: list[str] = []

    def __init__(self, *, api_key: str) -> None:
        """记录显式 API key。

        :param api_key: CLI 从环境边界读取的 key。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.api_keys.append(api_key)

    def resolve_company_info(self, canonical_ticker: str) -> FmpCompanyInfo:
        """返回固定公司事实并记录一次 public method invocation。

        :param canonical_ticker: 请求 canonical ticker。
        :returns: 固定 FMP 公司事实。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(canonical_ticker)
        return FmpCompanyInfo(
            canonical_ticker=canonical_ticker,
            company_name="Apple Inc.",
            ticker_aliases=(canonical_ticker, "MSFT"),
        )


def test_upload_filings_from_default_output_generates_posix_script_and_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认输出必须写入 base、使用 .sh 并输出可读三分摘要。"""

    _install_forbidden_direct_service(monkeypatch)
    monkeypatch.setattr(upload_script.os, "name", "posix")
    source_dir = tmp_path / "source docs"
    base = tmp_path / "workspace"
    source_dir.mkdir(parents=True)
    filing = source_dir / "2024FY AAPL Annual Report & literal %!.pdf"
    material = source_dir / "2024 AAPL Earnings Call Transcript.pdf"
    filing.write_text("filing", encoding="utf-8")
    material.write_text("material", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_filings_from",
            "--base",
            str(base),
            "--ticker",
            "aapl,msft",
            "--from",
            str(source_dir),
            "--action",
            "update",
            "--fiscal-year",
            "2024",
            "--company-name",
            "Apple Inc.",
            "--overwrite",
        )
    )

    script_path = base / "upload_filings_AAPL.sh"
    captured = capsys.readouterr()
    content = script_path.read_text(encoding="utf-8")
    assert exit_code == EXIT_SUCCESS
    assert captured.err == ""
    assert f"Generated upload script: {script_path.resolve()}" in captured.out
    assert "Recognized filings: 1" in captured.out
    assert "Material files: 1" in captured.out
    assert "Skipped files: 0" in captured.out
    assert content.startswith("#!/usr/bin/env sh\nset -eu\n")
    assert "python -m dayu.cli upload_filing" in content
    assert "python -m dayu.cli upload_material" in content
    assert "--ticker AAPL,MSFT" in content
    assert "--action update" in content
    assert "--overwrite" in content
    assert '"$@"' in content
    assert "schema_version" not in content
    assert os.stat(script_path).st_mode & stat.S_IXUSR


def test_material_form_candidate_reaches_fins_owner_and_maps_usage_exit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI 必须传播规范化候选，并把 Fins owner 的拒绝映射为 usage exit。"""

    _install_forbidden_direct_service(monkeypatch)
    _CAPTURED_BATCH_REQUESTS.clear()
    monkeypatch.setattr(
        fins_command,
        "generate_upload_batch_plan",
        _capture_request_then_generate_plan,
    )
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "2024 Earnings Call Transcript.pdf").write_text(
        "material",
        encoding="utf-8",
    )

    exit_code = cli_main.main(
        (
            "upload_filings_from",
            "--base",
            str(tmp_path / "workspace"),
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
            "--material-forms",
            " esg_report ",
        )
    )

    assert exit_code == EXIT_USAGE_ERROR
    assert [request.material_form for request in _CAPTURED_BATCH_REQUESTS] == [
        "ESG_REPORT"
    ]
    assert "unsupported material form: ESG_REPORT" in capsys.readouterr().err
    assert not (tmp_path / "workspace").exists()


def test_upload_filings_from_explicit_file_and_directory_outputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式文件必须原样采用，既有目录必须使用默认文件名。"""

    _install_forbidden_direct_service(monkeypatch)
    monkeypatch.setattr(upload_script.os, "name", "posix")
    source_dir = tmp_path / "source"
    base = tmp_path / "workspace"
    output_dir = base / "scripts"
    source_dir.mkdir()
    output_dir.mkdir(parents=True)
    (source_dir / "2024FY年报.pdf").write_text("filing", encoding="utf-8")
    explicit_file = output_dir / "exact custom name.script"

    assert cli_main.main(
        (
            "upload_filings_from",
            "--base",
            str(base),
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
            "--output",
            str(explicit_file),
        )
    ) == EXIT_SUCCESS
    capsys.readouterr()
    assert explicit_file.is_file()

    assert cli_main.main(
        (
            "upload_filings_from",
            "--base",
            str(base),
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
            "--output",
            str(output_dir),
        )
    ) == EXIT_SUCCESS
    assert (output_dir / "upload_filings_AAPL.sh").is_file()


def test_infer_resolves_once_and_projects_same_facts_without_secret(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FMP 每次生成最多调用一次，并把同源 metadata 投影到所有 entries。"""

    _install_forbidden_direct_service(monkeypatch)
    monkeypatch.setattr(upload_script.os, "name", "posix")
    monkeypatch.setattr(
        fins_command,
        "FmpCompanyInfoResolver",
        cast(type[FmpCompanyInfoResolver], _FakeFmpResolver),
    )
    secret = "R11_SENTINEL_FMP_SECRET_7f31c0"
    monkeypatch.setenv("FMP_API_KEY", secret)
    _FakeFmpResolver.api_keys.clear()
    _FakeFmpResolver.calls.clear()
    source_dir = tmp_path / "source"
    base = tmp_path / "workspace"
    source_dir.mkdir()
    (source_dir / "2024FY年报.pdf").write_text("filing", encoding="utf-8")
    (source_dir / "2024 财务报表.pdf").write_text("material", encoding="utf-8")

    assert cli_main.main(
        (
            "upload_filings_from",
            "--base",
            str(base),
            "--ticker",
            "AAPL,GOOG",
            "--from",
            str(source_dir),
            "--infer",
        )
    ) == EXIT_SUCCESS

    content = (base / "upload_filings_AAPL.sh").read_text(encoding="utf-8")
    body = "\n".join(
        line for line in content.splitlines() if not line.startswith("#")
    )
    assert _FakeFmpResolver.api_keys == [secret]
    assert _FakeFmpResolver.calls == ["AAPL"]
    assert body.count("--ticker AAPL,GOOG,MSFT") == 2
    assert body.count("--company-name 'Apple Inc.'") == 2
    assert "--infer" not in body
    assert "--infer" in content.splitlines()[2]
    assert secret not in content
    assert "financialmodelingprep.com" not in content
    assert secret not in capsys.readouterr().out


def test_without_infer_never_constructs_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未传 ``--infer`` 时必须零 resolver 调用，即使环境存在 FMP key。"""

    _install_forbidden_direct_service(monkeypatch)
    monkeypatch.setattr(upload_script.os, "name", "posix")
    monkeypatch.setenv("FMP_API_KEY", "unused-secret")

    class _ForbiddenResolver:
        """未启用 infer 时禁止构造的 resolver。"""

        def __init__(self, *, api_key: str) -> None:
            """始终失败以证明构造路径不可达。"""

            raise AssertionError(f"resolver must not be constructed: {api_key}")

    monkeypatch.setattr(
        fins_command,
        "FmpCompanyInfoResolver",
        cast(type[FmpCompanyInfoResolver], _ForbiddenResolver),
    )
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "2024FY年报.pdf").write_text("filing", encoding="utf-8")

    assert cli_main.main(
        (
            "upload_filings_from",
            "--base",
            str(tmp_path / "workspace"),
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
        )
    ) == EXIT_SUCCESS


def test_infer_missing_key_is_usage_error_without_script(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式 infer 缺 key 必须立即失败且不发布脚本。"""

    _install_forbidden_direct_service(monkeypatch)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    source_dir = tmp_path / "source"
    base = tmp_path / "workspace"
    source_dir.mkdir()
    (source_dir / "2024FY年报.pdf").write_text("filing", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_filings_from",
            "--base",
            str(base),
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
            "--infer",
        )
    )

    assert exit_code == EXIT_USAGE_ERROR
    assert "FMP_API_KEY" in capsys.readouterr().err
    assert not base.exists()


def test_posix_script_round_trips_adversarial_argv_with_real_sh(tmp_path: Path) -> None:
    """真实 ``/bin/sh`` 必须逐元素恢复 fixed 与 appended adversarial argv。"""

    recorder = tmp_path / "recorder.py"
    output = tmp_path / "recorded.jsonl"
    marker = tmp_path / "injected"
    recorder.write_text(
        "import json, pathlib, sys\n"
        "with pathlib.Path(sys.argv[1]).open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(sys.argv[2:], ensure_ascii=False) + '\\n')\n",
        encoding="utf-8",
    )
    adversarial = (
        "",
        "space value",
        "中文",
        "single'quote",
        'double"quote',
        "trail\\",
        f"$(touch {marker})",
        "& | ^ ( ) < > %PATH% !",
    )
    commands = (
        (sys.executable, str(recorder), str(output), "first", *adversarial),
        (sys.executable, str(recorder), str(output), "second"),
    )
    script = tmp_path / "upload.sh"
    script.write_text(
        upload_script.render_upload_script(
            commands,
            regeneration_argv=("python", "-m", "dayu.cli", "upload_filings_from"),
            platform="posix",
        ),
        encoding="utf-8",
    )
    appended = ("appended value", "尾随\\", f"; touch {marker}")

    completed = subprocess.run(
        ("/bin/sh", str(script), *appended),
        check=False,
        capture_output=True,
        text=True,
    )

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert completed.returncode == 0, completed.stderr
    assert rows == [
        ["first", *adversarial, *appended],
        ["second", *appended],
    ]
    assert not marker.exists()


def test_windows_renderer_round_trips_fixed_argument_oracles() -> None:
    """独立 batch+CRT oracle 必须恢复 Windows fixed argv 并锁定安全头。"""

    arguments = (
        "",
        "space value",
        "中文",
        "single'quote",
        'double"quote',
        "slashes\\\\tail\\",
        "%PATH% ! & | ^ ( ) < >",
    )
    for argument in arguments:
        rendered = upload_script._quote_windows_batch_argument(argument)
        after_batch_parse = _decode_windows_batch_fixed_token(rendered)
        assert _parse_single_windows_crt_argument(after_batch_parse) == argument
    content = upload_script.render_upload_script(
        (("python", "-m", "dayu.cli", "upload_filing", *arguments),),
        regeneration_argv=("python", "-m", "dayu.cli", "upload_filings_from", "%PATH%"),
        platform="windows",
    )
    assert content.startswith(
        "@echo off\r\nchcp 65001 >nul\r\nsetlocal DisableDelayedExpansion\r\n"
    )
    assert "%*\r\n" in content
    assert "%%PATH%%" in content
    assert "setlocal EnableDelayedExpansion" not in content
    assert "\n" not in content.replace("\r\n", "")


@pytest.mark.parametrize("forbidden", ("line\nfeed", "carriage\rreturn", "nul\x00byte"))
def test_windows_renderer_rejects_arguments_that_escape_one_batch_line(
    forbidden: str,
) -> None:
    """Windows renderer 必须 fail-closed 拒绝 NUL 与跨行 argv。

    :param forbidden: 含 Windows batch 单行不能表达字符的 argv。
    :returns: ``None``。
    :raises AssertionError: renderer 接受 line injection 输入时抛出。
    """

    with pytest.raises(ValueError, match="NUL or line breaks"):
        upload_script.render_upload_script(
            (("python", forbidden),),
            regeneration_argv=("python", "-m", "dayu.cli"),
            platform="windows",
        )
    with pytest.raises(ValueError, match="NUL or line breaks"):
        upload_script.render_upload_script(
            (("python", "safe"),),
            regeneration_argv=("python", forbidden),
            platform="windows",
        )


def test_r11_workflow_uses_fail_closed_exact_cmd_process_probe() -> None:
    """R11 必须按进程精确捕获 ver/help exit，且不得全局忽略 native failure。

    :returns: ``None``。
    :raises AssertionError: workflow 恢复 native pipeline 或弱化 exact exit 时抛出。
    """

    workflow = _R11_WINDOWS_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "[System.Diagnostics.ProcessStartInfo]::new()" in workflow
    assert "$startInfo.UseShellExecute = $false" in workflow
    assert "$startInfo.RedirectStandardOutput = $true" in workflow
    assert "$startInfo.RedirectStandardError = $true" in workflow
    assert '-ArgumentList @("/d", "/c", "ver")' in workflow
    assert '-ArgumentList @("/?")' in workflow
    assert "if ($verExitCode -ne 0)" in workflow
    assert "if ($cmdHelpExitCode -ne 1)" in workflow
    assert "cmd.exe /? 2>&1 |" not in workflow
    assert "$PSNativeCommandUseErrorActionPreference" not in workflow
    assert "$ErrorActionPreference" not in workflow


def test_publisher_preserves_old_target_and_cleans_temp_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """replace 失败时旧 target 必须 byte-for-byte 保留且 temp 清理。"""

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "upload_filings_AAPL.sh"
    target.write_bytes(b"old-target\n")

    def fail_replace(_source: Path, _target: Path) -> None:
        """模拟原子 replace 失败。

        :param _source: 临时文件。
        :param _target: 最终文件。
        :returns: 不返回。
        :raises OSError: 始终抛出。
        """

        raise OSError("replace failed")

    monkeypatch.setattr(upload_script.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        upload_script.publish_upload_script(
            workspace_root=workspace,
            output=None,
            canonical_ticker="AAPL",
            platform="posix",
            content="new-target\n",
        )

    assert target.read_bytes() == b"old-target\n"
    assert tuple(workspace.glob(".upload_filings_AAPL.sh.*.tmp")) == ()


def test_publisher_rejects_escape_root_symlink_and_internal_symlink(
    tmp_path: Path,
) -> None:
    """output lexical escape、root-self 与内部 symlink 必须拒绝。"""

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(upload_script.UploadScriptPublishError, match="escapes"):
        upload_script.publish_upload_script(
            workspace_root=workspace,
            output=tmp_path / "outside.sh",
            canonical_ticker="AAPL",
            platform="posix",
            content="safe\n",
        )
    root_link = tmp_path / "root-link"
    root_link.symlink_to(workspace, target_is_directory=True)
    with pytest.raises(upload_script.UploadScriptPublishError, match="root must not"):
        upload_script.publish_upload_script(
            workspace_root=root_link,
            output=None,
            canonical_ticker="AAPL",
            platform="posix",
            content="safe\n",
        )
    real_dir = workspace / "real"
    real_dir.mkdir()
    linked_dir = workspace / "linked"
    linked_dir.symlink_to(real_dir, target_is_directory=True)
    with pytest.raises(upload_script.UploadScriptPublishError, match="internal symlink"):
        upload_script.publish_upload_script(
            workspace_root=workspace,
            output=linked_dir / "upload.sh",
            canonical_ticker="AAPL",
            platform="posix",
            content="safe\n",
        )


def test_publisher_allows_external_ancestor_symlink(tmp_path: Path) -> None:
    """workspace root 外部祖先 symlink 必须允许。"""

    real_parent = tmp_path / "real"
    workspace = real_parent / "workspace"
    workspace.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(real_parent, target_is_directory=True)

    target = upload_script.publish_upload_script(
        workspace_root=alias / "workspace",
        output=None,
        canonical_ticker="AAPL",
        platform="posix",
        content="safe\n",
    )

    assert target == (workspace / "upload_filings_AAPL.sh").resolve()


def test_upload_filings_from_usage_empty_and_write_failures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """source usage、empty plan 与 output containment 必须映射稳定 exit code。"""

    _install_forbidden_direct_service(monkeypatch)
    missing = cli_main.main(
        (
            "upload_filings_from",
            "--base",
            str(tmp_path / "workspace"),
            "--ticker",
            "AAPL",
            "--from",
            str(tmp_path / "missing"),
        )
    )
    assert missing == EXIT_USAGE_ERROR
    assert "source dir does not exist" in capsys.readouterr().err

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "notes.pdf").write_text("notes", encoding="utf-8")
    empty = cli_main.main(
        (
            "upload_filings_from",
            "--base",
            str(tmp_path / "workspace"),
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
        )
    )
    assert empty == EXIT_FAILURE
    assert "no recognizable filing or material files" in capsys.readouterr().err

    (source_dir / "2024FY年报.pdf").write_text("filing", encoding="utf-8")
    outside = cli_main.main(
        (
            "upload_filings_from",
            "--base",
            str(tmp_path / "workspace"),
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
            "--output",
            str(tmp_path / "outside.sh"),
        )
    )
    assert outside == EXIT_FAILURE
    assert "escapes workspace root" in capsys.readouterr().err


def test_upload_filings_from_keyboard_interrupt_exits_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """目录扫描或发布阶段 KeyboardInterrupt 必须映射为 130。"""

    _install_forbidden_direct_service(monkeypatch)

    def raise_keyboard_interrupt(_request: UploadBatchPlanRequest) -> UploadBatchPlan:
        """模拟扫描阶段用户中断。

        :param _request: batch request。
        :returns: 不返回。
        :raises KeyboardInterrupt: 始终抛出。
        """

        raise KeyboardInterrupt

    monkeypatch.setattr(
        fins_command,
        "generate_upload_batch_plan",
        raise_keyboard_interrupt,
    )

    assert cli_main.main(
        ("upload_filings_from", "--ticker", "AAPL", "--from", "unused")
    ) == EXIT_KEYBOARD_INTERRUPT


def test_posix_generated_script_runs_real_cli_into_temp_storage() -> None:
    """真实生成脚本必须经 parser→Service→Fins 写入临时 storage。"""

    if os.name == "nt":
        pytest.skip("POSIX real workflow is exercised on non-Windows runners")
    smoke_root = Path(__file__).resolve().parents[2] / "workspace/tmp/r11-posix-real"
    shutil.rmtree(smoke_root, ignore_errors=True)
    source_dir = smoke_root / "source"
    storage = smoke_root / "storage"
    source_dir.mkdir(parents=True)
    fixture = _FIXTURE_SOURCE.read_bytes()
    (source_dir / "2024FY_AAPL_Annual_Report.htm").write_bytes(fixture)
    (source_dir / "2024FY_AAPL_Earnings_Call_Transcript.htm").write_bytes(fixture)
    generation = subprocess.run(
        (
            sys.executable,
            "-m",
            "dayu.cli",
            "--base",
            str(storage),
            "upload_filings_from",
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
            "--action",
            "create",
            "--company-name",
            "Apple Inc.",
        ),
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    script_path = storage / "upload_filings_AAPL.sh"
    execution = subprocess.run(
        ("/bin/sh", str(script_path)),
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )

    assert generation.returncode == 0, generation.stderr
    assert execution.returncode == 0, execution.stderr
    assert execution.stdout.count("Fins succeeded") == 2
    source_meta = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (storage / "portfolio").rglob("meta.json")
        if path.parent.parent.name in {"filings", "materials"}
    ]
    assert {meta["source_kind"] for meta in source_meta} == {"filing", "material"}


@pytest.mark.skipif(os.name != "nt", reason="requires real cmd.exe")
def test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd(
    tmp_path: Path,
) -> None:
    """真实 cmd.exe 必须逐元素恢复 fixed/appended argv 且不产生 injection marker。"""

    artifact_directory = _windows_test_artifact_directory(
        tmp_path,
        subdirectory=_WINDOWS_RECORDER_ARTIFACT_SUBDIRECTORY,
    )
    recorder = artifact_directory / "recorder.py"
    output = artifact_directory / "recorder-oracle.jsonl"
    marker = artifact_directory / "injected"
    recorder.write_text(
        "import json, pathlib, sys\n"
        "with pathlib.Path(sys.argv[1]).open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(sys.argv[2:], ensure_ascii=False) + '\\n')\n",
        encoding="utf-8",
    )
    fixed = (
        "",
        "space value",
        "中文",
        'quote"value',
        "trail\\",
        "%PATH%",
        "!",
        "&",
        "|",
        "^",
        "(",
        ")",
        "<",
        ">",
    )
    command = (sys.executable, str(recorder), str(output), *fixed)
    script = artifact_directory / "generated-upload.cmd"
    script.write_text(
        upload_script.render_upload_script(
            (command,),
            regeneration_argv=("python", "-m", "dayu.cli", "upload_filings_from"),
            platform="windows",
        ),
        encoding="utf-8",
        newline="",
    )
    appended = ("appended value", f"& type nul > {marker}")
    completed = subprocess.run(
        ("cmd.exe", "/d", "/c", str(script), *appended),
        check=False,
        capture_output=True,
        text=True,
    )

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()
    assert rows == [[*fixed, *appended]]


@pytest.mark.skipif(os.name != "nt", reason="requires real cmd.exe")
def test_windows_generated_script_runs_real_cli_into_temp_storage(tmp_path: Path) -> None:
    """真实 Windows 脚本必须完成 CLI→Service→Fins temp-storage 闭环。"""

    artifact_directory = _windows_test_artifact_directory(
        tmp_path,
        subdirectory=_WINDOWS_CLI_ARTIFACT_SUBDIRECTORY,
    )
    source_dir = artifact_directory / "source"
    storage = artifact_directory
    source_dir.mkdir()
    fixture = _FIXTURE_SOURCE.read_bytes()
    (source_dir / "2024FY_AAPL_Annual_Report.htm").write_bytes(fixture)
    generation = subprocess.run(
        (
            sys.executable,
            "-m",
            "dayu.cli",
            "--base",
            str(storage),
            "upload_filings_from",
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
            "--action",
            "create",
            "--output",
            str(artifact_directory / "cli-generated-upload.cmd"),
        ),
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    script_path = artifact_directory / "cli-generated-upload.cmd"
    execution = subprocess.run(
        ("cmd.exe", "/d", "/c", str(script_path)),
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )

    assert generation.returncode == 0, generation.stderr
    assert execution.returncode == 0, execution.stderr
    assert "Fins result" in execution.stdout
    source_artifacts = tuple(
        path for path in (storage / "portfolio").rglob("*") if path.is_file()
    )
    assert source_artifacts
    (artifact_directory / "cli-grammar-oracle.json").write_text(
        json.dumps(
            {
                "test_node": (
                    "test_windows_generated_script_runs_real_cli_into_temp_storage"
                ),
                "result": "passed",
                "generated_script_sha256": hashlib.sha256(
                    script_path.read_bytes()
                ).hexdigest(),
                "source_artifact_count": len(source_artifacts),
                "cmd_invocation": "cmd.exe /d /c",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_cli_fins_command_has_no_host_engine_or_storage_imports() -> None:
    """CLI fins command 不得导入 Host、Engine 或 Fins storage。"""

    module_path = Path(fins_command.__file__).resolve()
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_prefixes = ("dayu.engine", "dayu.host", "dayu.fins.storage")
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)

    assert [
        name
        for name in imports
        if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
    ] == []


def _parse_single_windows_crt_argument(value: str) -> str:
    """独立解析 production quote owner 生成的单个 Windows CRT 参数。

    :param value: 双引号包裹的 command-line token。
    :returns: CRT 规则恢复的单一 argv。
    :raises AssertionError: token 不是完整单参数时抛出。
    """

    assert value.startswith('"') and value.endswith('"')
    index = 0
    in_quotes = False
    result: list[str] = []
    while index < len(value):
        slash_start = index
        while index < len(value) and value[index] == "\\":
            index += 1
        slash_count = index - slash_start
        if index < len(value) and value[index] == '"':
            result.append("\\" * (slash_count // 2))
            if slash_count % 2 == 1:
                result.append('"')
            else:
                in_quotes = not in_quotes
            index += 1
        else:
            result.append("\\" * slash_count)
        if index < len(value) and value[index] != '"':
            result.append(value[index])
            index += 1
    assert not in_quotes
    return "".join(result)


def _decode_windows_batch_fixed_token(value: str) -> str:
    """独立模拟 fixed token 的 batch percent 与 caret 解码。

    本 oracle 只实现 production contract 使用的非递归 percent doubling 和
    caret-protected metacharacter，不复用 renderer helper。

    :param value: renderer 写入 batch body 的一个 fixed token。
    :returns: ``cmd.exe`` 交给目标进程命令行的 CRT token。
    :raises AssertionError: token 包含未闭合的 percent/caret escape 时抛出。
    """

    index = 0
    decoded: list[str] = []
    while index < len(value):
        if value.startswith("%%", index):
            decoded.append("%")
            index += 2
            continue
        character = value[index]
        if character == "^":
            assert index + 1 < len(value)
            decoded.append(value[index + 1])
            index += 2
            continue
        decoded.append(character)
        index += 1
    return "".join(decoded)


def _install_forbidden_direct_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """安装不允许生成阶段调用的 Fins direct service factory。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 生成阶段错误启动 direct service 时抛出。
    """

    def factory(_workspace_root: Path) -> FinsDirectCommandService:
        """拒绝构造 direct service。

        :param _workspace_root: workspace root。
        :returns: 不返回。
        :raises AssertionError: 始终抛出。
        """

        raise AssertionError("upload_filings_from must not create Fins direct service")

    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        cast(fins_command.FinsDirectServiceFactory, factory),
    )
