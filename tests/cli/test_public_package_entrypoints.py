"""公开包入口 import/help smoke 测试。"""

from __future__ import annotations

import importlib
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

ENTRYPOINT_SCRIPT_NAMES: tuple[str, ...] = (
    "dayu-web",
    "dayu-wechat",
    "dayu-render",
)
MODULE_HELP_TARGETS: tuple[tuple[str, str], ...] = (
    ("dayu.web", "dayu-web"),
    ("dayu.wechat.main", "dayu-wechat"),
    ("dayu.render.render", "dayu-render"),
)
REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
CONSTRAINTS_ROOT = REPO_ROOT / "constraints"
PYTHON_311_CONSTRAINT_NAMES: tuple[str, ...] = (
    "min-py311.txt",
    "lock-linux-x64-py311.txt",
    "lock-macos-arm64-py311.txt",
    "lock-macos-x64-py311.txt",
    "lock-windows-x64-py311.txt",
)
TRANSFORMERS_RUNTIME_CONSTRAINT = "transformers>=4.57.6,<5.0.0"
TRANSFORMERS_LOCK = "transformers==4.57.6"
HUGGINGFACE_HUB_LOCK = "huggingface_hub==0.36.2"
EXIT_SUCCESS: int = 0
EXIT_UNAVAILABLE: int = 1

EntrypointMain = Callable[[Sequence[str] | None], int]


def _load_project_scripts() -> dict[str, str]:
    """读取 ``pyproject.toml`` 中的公开脚本声明。

    :returns: 脚本名到 ``module:function`` target 的映射。
    :raises AssertionError: pyproject 缺少可用脚本表时抛出。
    """

    pyproject_data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    project_section = pyproject_data["project"]
    assert isinstance(project_section, dict)
    scripts_section = project_section["scripts"]
    assert isinstance(scripts_section, dict)
    scripts: dict[str, str] = {}
    for script_name, target in scripts_section.items():
        assert isinstance(script_name, str)
        assert isinstance(target, str)
        scripts[script_name] = target
    return scripts


def _load_project_dependencies() -> tuple[str, ...]:
    """读取 ``pyproject.toml`` 的运行依赖声明。

    :returns: 项目运行依赖字符串元组。
    :raises AssertionError: project dependencies 缺失或包含非字符串时抛出。
    """

    pyproject_data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    project_section = pyproject_data["project"]
    assert isinstance(project_section, dict)
    dependencies = project_section["dependencies"]
    assert isinstance(dependencies, list)
    assert all(isinstance(dependency, str) for dependency in dependencies)
    return tuple(cast(list[str], dependencies))


def _load_script_target(script_name: str) -> tuple[ModuleType, str, EntrypointMain]:
    """按 pyproject 脚本真源动态导入入口函数。

    :param script_name: 公开脚本名。
    :returns: 模块对象、函数名和入口函数。
    :raises AssertionError: target 格式错误或入口不可调用时抛出。
    """

    scripts = _load_project_scripts()
    target = scripts[script_name]
    module_name, separator, function_name = target.partition(":")
    assert separator == ":"
    assert module_name != ""
    assert function_name != ""
    module = importlib.import_module(module_name)
    # 测试刻意按 pyproject 真源解析 console script target，避免手写 target
    # 与 packaging metadata 再次漂移。
    entrypoint = getattr(module, function_name)
    assert callable(entrypoint)
    return module, function_name, cast(EntrypointMain, entrypoint)


@pytest.mark.parametrize("script_name", ENTRYPOINT_SCRIPT_NAMES)
def test_pyproject_public_script_targets_import_and_help(script_name: str) -> None:
    """公开脚本 target 必须可导入，且 ``--help`` 返回成功。

    :param script_name: pyproject 中声明的公开脚本名。
    :returns: ``None``。
    :raises AssertionError: target 不可导入、不可调用或 help 退出码错误时抛出。
    """

    _module, _function_name, entrypoint = _load_script_target(script_name)

    assert entrypoint(("--help",)) == EXIT_SUCCESS


@pytest.mark.parametrize(("module_name", "expected_text"), MODULE_HELP_TARGETS)
def test_public_modules_execute_help(module_name: str, expected_text: str) -> None:
    """模块形式入口必须能执行 ``--help``。

    :param module_name: 传给 ``python -m`` 的模块名。
    :param expected_text: help 输出中应出现的命令名。
    :returns: ``None``。
    :raises AssertionError: 模块 help 失败或输出不含命令名时抛出。
    """

    completed = subprocess.run(
        [sys.executable, "-m", module_name, "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == EXIT_SUCCESS
    assert expected_text in completed.stdout
    assert completed.stderr == ""


def test_public_entrypoint_import_does_not_load_optional_heavy_dependencies() -> None:
    """公开入口模块 import 不应加载可选重依赖。

    :returns: ``None``。
    :raises AssertionError: import 入口时加载了当前 slice 不需要的可选重依赖时抛出。
    """

    optional_modules = frozenset({"streamlit", "playwright", "pypandoc"})
    before_import = optional_modules.intersection(sys.modules)
    for script_name in ENTRYPOINT_SCRIPT_NAMES:
        _load_script_target(script_name)
    after_import = optional_modules.intersection(sys.modules)

    assert after_import == before_import


def test_docling_transformers_runtime_contract_is_consistent_for_python_311() -> None:
    """Docling 模型栈必须在 package metadata 与所有 3.11 锁文件中同源。

    :returns: ``None``。
    :raises AssertionError: metadata 允许 transformers 5.x 或任一锁文件漂移时抛出。
    """

    assert TRANSFORMERS_RUNTIME_CONSTRAINT in _load_project_dependencies()
    for constraint_name in PYTHON_311_CONSTRAINT_NAMES:
        constraint_text = (CONSTRAINTS_ROOT / constraint_name).read_text(encoding="utf-8")
        assert TRANSFORMERS_LOCK in constraint_text, constraint_name
        assert HUGGINGFACE_HUB_LOCK in constraint_text, constraint_name
        assert "transformers==5." not in constraint_text, constraint_name
        assert "huggingface_hub==1." not in constraint_text, constraint_name


def test_non_help_execution_returns_controlled_diagnostics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """当前未实现的公开入口在非 help 执行时返回受控诊断。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 诊断缺失或退出码不是当前不可用时抛出。
    """

    from dayu.render.render import main as render_main
    from dayu.web.__main__ import main as web_main
    from dayu.wechat.main import main as wechat_main

    cases: tuple[tuple[EntrypointMain, tuple[str, ...], str], ...] = (
        (web_main, (), "尚未提供可运行的 Web UI"),
        (wechat_main, (), "尚未提供可运行的微信登录"),
        (render_main, ("input.md", "output.pdf"), "尚未提供 Markdown 到 HTML、Word 或 PDF 的转换实现"),
    )
    for entrypoint, argv, expected_diagnostic in cases:
        assert entrypoint(argv) == EXIT_UNAVAILABLE
        captured = capsys.readouterr()
        assert expected_diagnostic in captured.err
        assert captured.out == ""


@pytest.mark.parametrize(
    "argv",
    (
        ("login", "--help"),
        ("run", "--help"),
        ("service", "--help"),
        ("service", "install", "--help"),
    ),
)
def test_wechat_subcommand_help_is_controlled(argv: tuple[str, ...]) -> None:
    """WeChat 子命令 help 必须由当前入口模块受控处理。

    :param argv: 不含程序名的 ``dayu-wechat`` 参数。
    :returns: ``None``。
    :raises AssertionError: 子命令 help 退出码不是 0 时抛出。
    """

    from dayu.wechat.main import main as wechat_main

    assert wechat_main(argv) == EXIT_SUCCESS
