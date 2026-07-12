"""``dayu-cli upload_filings_from`` 测试。"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

import dayu.cli.commands.fins as fins_command
import dayu.cli.main as cli_main
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.contracts import JsonValue
from dayu.fins.upload_batch import UploadBatchPlanRequest, UploadBatchPlanResult
from dayu.service.fins_direct import FinsDirectCommandService


def test_upload_filings_from_writes_structured_argv_plan_to_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认输出跨平台 JSON argv，并保持 shell 特殊字符属于单个参数。"""

    _install_forbidden_direct_service(monkeypatch)
    source_dir = tmp_path / "source docs"
    source_dir.mkdir()
    filing = source_dir / "AAPL 10-K 2024 & echo %PATH%!.pdf"
    material = source_dir / "AAPL EX-99.1 investor day.pdf"
    filing.write_text("filing", encoding="utf-8")
    material.write_text("material", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_filings_from",
            "--ticker",
            "AAPL,Apple Inc.",
            "--from",
            str(source_dir),
            "--action",
            "update",
            "--material-forms",
            "EX-99.1",
            "--fiscal-year",
            "2024",
            "--company-name",
            "Apple Inc.",
        )
    )

    captured = capsys.readouterr()
    commands = _load_plan_commands(captured.out)
    assert exit_code == EXIT_SUCCESS
    assert captured.err == ""
    assert len(commands) == 2
    filing_argv = next(command for command in commands if command[1] == "upload_filing")
    material_argv = next(
        command for command in commands if command[1] == "upload_material"
    )
    assert filing_argv[:7] == (
        "dayu-cli",
        "upload_filing",
        "--ticker",
        "AAPL",
        "--action",
        "update",
        "--files",
    )
    assert filing_argv[7] == str(filing.resolve())
    assert "& echo %PATH%!" in filing_argv[7]
    assert material_argv[:11] == (
        "dayu-cli",
        "upload_material",
        "--ticker",
        "AAPL",
        "--action",
        "update",
        "--forms",
        "EX-99.1",
        "--material-name",
        "AAPL EX-99.1 investor day",
        "--files",
    )
    assert material_argv[11] == str(material.resolve())
    assert ("--fiscal-year", "2024") == _option_pair(filing_argv, "--fiscal-year")
    assert ("--company-name", "Apple Inc.") == _option_pair(
        filing_argv,
        "--company-name",
    )
    assert "Fins job" not in captured.out


def test_upload_filings_from_respects_non_recursive_scan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未传 --recursive 时不得扫描子目录。"""

    _install_forbidden_direct_service(monkeypatch)
    source_dir = tmp_path / "source"
    nested_dir = source_dir / "nested"
    nested_dir.mkdir(parents=True)
    (source_dir / "AAPL 10-K 2024.pdf").write_text("filing", encoding="utf-8")
    (nested_dir / "AAPL 10-Q 2024.pdf").write_text("nested", encoding="utf-8")

    assert cli_main.main(
        ("upload_filings_from", "--ticker", "AAPL", "--from", str(source_dir))
    ) == EXIT_SUCCESS

    output = capsys.readouterr().out
    commands = _load_plan_commands(output)
    assert len(commands) == 1
    assert commands[0][1] == "upload_filing"
    assert "10-K" in commands[0][7]
    assert "10-Q" not in commands[0][7]
    assert "Fins job" not in output


def test_upload_filings_from_recursive_scan_includes_nested_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """传入 --recursive 时必须扫描子目录。"""

    _install_forbidden_direct_service(monkeypatch)
    source_dir = tmp_path / "source"
    nested_dir = source_dir / "nested"
    nested_dir.mkdir(parents=True)
    (source_dir / "AAPL 10-K 2024.pdf").write_text("filing", encoding="utf-8")
    (nested_dir / "AAPL 10-Q 2024.pdf").write_text("nested", encoding="utf-8")

    assert cli_main.main(
        (
            "upload_filings_from",
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
            "--recursive",
        )
    ) == EXIT_SUCCESS

    output = capsys.readouterr().out
    commands = _load_plan_commands(output)
    assert len(commands) == 2
    assert all(command[1] == "upload_filing" for command in commands)
    uploaded_paths = tuple(command[7] for command in commands)
    assert any("10-K" in path for path in uploaded_paths)
    assert any("10-Q" in path for path in uploaded_paths)
    assert "Fins job" not in output


def test_upload_filings_from_writes_output_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """提供 --output 时必须写入指定 JSON argv 计划且不向 stdout 输出。"""

    _install_forbidden_direct_service(monkeypatch)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "AAPL 10-K 2024.pdf").write_text("filing", encoding="utf-8")
    output_file = tmp_path / "upload-plan.json"

    exit_code = cli_main.main(
        (
            "upload_filings_from",
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
            "--output",
            str(output_file),
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_SUCCESS
    assert captured.out == ""
    assert captured.err == ""
    commands = _load_plan_commands(output_file.read_text(encoding="utf-8"))
    assert len(commands) == 1
    assert commands[0][1] == "upload_filing"


def test_upload_filings_from_missing_source_dir_exits_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """source dir 不存在必须映射为 exit 2。"""

    _install_forbidden_direct_service(monkeypatch)

    exit_code = cli_main.main(
        (
            "upload_filings_from",
            "--ticker",
            "AAPL",
            "--from",
            str(tmp_path / "missing"),
        )
    )

    assert exit_code == EXIT_USAGE_ERROR
    captured = capsys.readouterr()
    assert "source dir does not exist" in captured.err
    assert "Fins job" not in captured.err


def test_upload_filings_from_empty_source_dir_exits_usage_error(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空 --from 必须映射为 exit 2。"""

    _install_forbidden_direct_service(monkeypatch)

    exit_code = cli_main.main(
        ("upload_filings_from", "--ticker", "AAPL", "--from", "")
    )

    assert exit_code == EXIT_USAGE_ERROR
    captured = capsys.readouterr()
    assert "--from must not be empty" in captured.err
    assert "Fins job" not in captured.err


def test_upload_filings_from_no_recognizable_files_exits_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无可识别文件必须映射为 exit 1 并输出原因。"""

    _install_forbidden_direct_service(monkeypatch)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "notes.pdf").write_text("notes", encoding="utf-8")

    exit_code = cli_main.main(
        ("upload_filings_from", "--ticker", "AAPL", "--from", str(source_dir))
    )

    assert exit_code == EXIT_FAILURE
    captured = capsys.readouterr()
    assert "no recognizable filing or material files" in captured.err
    assert "Fins job" not in captured.err


def test_upload_filings_from_output_write_failure_exits_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """输出路径不可写时必须映射为 exit 1。"""

    _install_forbidden_direct_service(monkeypatch)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "AAPL 10-K 2024.pdf").write_text("filing", encoding="utf-8")

    exit_code = cli_main.main(
        (
            "upload_filings_from",
            "--ticker",
            "AAPL",
            "--from",
            str(source_dir),
            "--output",
            str(tmp_path),
        )
    )

    assert exit_code == EXIT_FAILURE
    captured = capsys.readouterr()
    assert "dayu-cli upload_filings_from:" in captured.err
    assert "Fins job" not in captured.err


def test_upload_filings_from_keyboard_interrupt_exits_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """目录扫描阶段 SIGINT 必须映射为 130。"""

    _install_forbidden_direct_service(monkeypatch)

    def raise_keyboard_interrupt(
        _request: UploadBatchPlanRequest,
    ) -> UploadBatchPlanResult:
        """模拟扫描阶段用户中断。

        :param _request: 批量上传计划请求。
        :returns: 正常路径不会返回。
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

    violations = [
        name
        for name in imports
        if any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in forbidden_prefixes
        )
    ]
    assert violations == []


def _load_plan_commands(value: str) -> tuple[tuple[str, ...], ...]:
    """读取并校验 upload batch JSON argv 公共契约。

    :param value: CLI 输出或计划文件文本。
    :returns: 命令 argv 元组。
    :raises AssertionError: payload 不符合 version 1 contract 时抛出。
    """

    payload = cast(Mapping[str, JsonValue], json.loads(value))
    assert payload["schema_version"] == 1
    raw_commands = payload["commands"]
    assert isinstance(raw_commands, list)
    commands: list[tuple[str, ...]] = []
    for raw_command in raw_commands:
        assert isinstance(raw_command, list)
        assert all(isinstance(argument, str) for argument in raw_command)
        commands.append(tuple(cast(list[str], raw_command)))
    return tuple(commands)


def _option_pair(argv: tuple[str, ...], option: str) -> tuple[str, str]:
    """读取带单值的 argv option pair。

    :param argv: 单条命令 argv。
    :param option: 待读取 option 名称。
    :returns: option 与紧随其后的值。
    :raises ValueError: argv 不包含 option 时由 ``tuple.index`` 抛出。
    :raises IndexError: option 缺值时抛出。
    """

    option_index = argv.index(option)
    return argv[option_index], argv[option_index + 1]


def _install_forbidden_direct_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """安装不允许被调用的 Fins direct service factory。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: upload_filings_from 错误启动 Fins direct service 时抛出。
    """

    def factory(_workspace_root: Path) -> FinsDirectCommandService:
        """禁止 upload_filings_from 创建 direct service。

        :param _workspace_root: workspace root。
        :returns: 正常路径不会返回。
        :raises AssertionError: 始终抛出。
        """

        raise AssertionError("upload_filings_from must not create Fins direct service")

    monkeypatch.setattr(
        fins_command,
        "FINS_DIRECT_SERVICE_FACTORY",
        cast(fins_command.FinsDirectServiceFactory, factory),
    )
