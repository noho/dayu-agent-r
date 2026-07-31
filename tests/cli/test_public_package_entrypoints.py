"""公开包入口与 wheel metadata 测试。"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import cast
from zipfile import ZipFile

PLACEHOLDER_SURFACE_NAMES: tuple[str, ...] = ("web", "wechat", "render")
PLACEHOLDER_SCRIPT_NAMES: tuple[str, ...] = tuple(
    f"dayu-{surface_name}" for surface_name in PLACEHOLDER_SURFACE_NAMES
)
PLACEHOLDER_PACKAGE_PREFIXES: tuple[str, ...] = tuple(
    f"dayu/{surface_name}/" for surface_name in PLACEHOLDER_SURFACE_NAMES
)
REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
CONSTRAINTS_ROOT = REPO_ROOT / "constraints"
PUBLIC_PACKAGE_BUILD_ROOT = REPO_ROOT / "workspace/tmp/r11-public-package-test"
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


def _build_wheel() -> Path:
    """在 validation 专用目录构建当前 wheel。

    :returns: 唯一的 wheel 路径。
    :raises AssertionError: wheel 构建失败或产物数量不是一个时抛出。
    """

    shutil.rmtree(PUBLIC_PACKAGE_BUILD_ROOT, ignore_errors=True)
    PUBLIC_PACKAGE_BUILD_ROOT.mkdir(parents=True)
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(PUBLIC_PACKAGE_BUILD_ROOT),
            ".",
        ),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    wheels = tuple(PUBLIC_PACKAGE_BUILD_ROOT.glob("dayu_agent-*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def test_pyproject_publishes_only_real_console_scripts() -> None:
    """pyproject 只能发布已实现的 console script。

    :returns: ``None``。
    :raises AssertionError: 真实 CLI 缺失或 placeholder script 仍被声明时抛出。
    """

    scripts = _load_project_scripts()
    assert scripts == {"dayu-cli": "dayu.cli.__main__:run_module"}
    assert set(PLACEHOLDER_SCRIPT_NAMES).isdisjoint(scripts)


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


def test_wheel_excludes_placeholder_scripts_metadata_and_packages() -> None:
    """wheel 不得发布 placeholder script、extra、依赖或 package。

    :returns: ``None``。
    :raises AssertionError: wheel 构建失败或任一 placeholder contract 残留时抛出。
    """

    wheel = _build_wheel()
    with ZipFile(wheel) as archive:
        names = tuple(archive.namelist())
        metadata_names = tuple(name for name in names if name.endswith(".dist-info/METADATA"))
        entrypoint_names = tuple(name for name in names if name.endswith(".dist-info/entry_points.txt"))
        assert len(metadata_names) == 1, metadata_names
        assert len(entrypoint_names) == 1, entrypoint_names
        metadata = archive.read(metadata_names[0]).decode("utf-8")
        entrypoints = archive.read(entrypoint_names[0]).decode("utf-8")

    assert "dayu-cli = dayu.cli.__main__:run_module" in entrypoints
    assert not any(script_name in entrypoints for script_name in PLACEHOLDER_SCRIPT_NAMES)
    assert "Provides-Extra: web" not in metadata
    assert "Requires-Dist: streamlit" not in metadata
    assert not any(
        name.startswith(package_prefix)
        for name in names
        for package_prefix in PLACEHOLDER_PACKAGE_PREFIXES
    )
