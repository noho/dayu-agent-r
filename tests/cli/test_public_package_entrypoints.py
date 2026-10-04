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
    "lock-windows-x64-py311.txt",
)
TRANSFORMERS_RUNTIME_CONSTRAINT = "transformers>=5.16.1,<6.0.0"
# 各 3.11 约束文件承诺的模型栈锁定值（transformers, huggingface_hub）；
# darwin 与 linux/win 的官方验证基线不同，需按文件逐项断言。
PYTHON_311_MODEL_STACK_LOCKS: dict[str, tuple[str, str]] = {
    "min-py311.txt": ("transformers==5.16.1", "huggingface_hub==1.5.0"),
    "lock-macos-arm64-py311.txt": ("transformers==5.16.1", "huggingface_hub==1.31.0"),
    "lock-linux-x64-py311.txt": ("transformers==5.17.0", "huggingface_hub==1.31.0"),
    "lock-windows-x64-py311.txt": ("transformers==5.17.0", "huggingface_hub==1.31.0"),
}
# 已放弃的旧模型栈锁定前缀：transformers 4.x 与 huggingface_hub 0.x 不得回流任何约束文件。
RETIRED_TRANSFORMERS_LOCK_PREFIX = "transformers==4."
RETIRED_HUGGINGFACE_HUB_LOCK_PREFIX = "huggingface_hub==0."
# 已否决的 OCR 引擎：ocrmac（Apple Vision）不得回流任何约束文件。
RETIRED_OCR_ENGINE_MARKER = "ocrmac"


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
    assert scripts == {"dayu-cli": "dayu.cli.__main__:exit_module"}
    assert set(PLACEHOLDER_SCRIPT_NAMES).isdisjoint(scripts)


def test_docling_transformers_runtime_contract_is_consistent_for_python_311() -> None:
    """Docling 模型栈必须在 package metadata 与所有 3.11 约束文件间同源。

    :returns: ``None``。
    :raises AssertionError: metadata 偏离 transformers 5.16.1+ 窗口、任一约束文件
        缺少承诺的锁定值、或旧模型栈（transformers 4.x / huggingface_hub 0.x）回流时抛出。
    """

    assert TRANSFORMERS_RUNTIME_CONSTRAINT in _load_project_dependencies()
    assert set(PYTHON_311_MODEL_STACK_LOCKS) == set(PYTHON_311_CONSTRAINT_NAMES)
    for constraint_name in PYTHON_311_CONSTRAINT_NAMES:
        constraint_text = (CONSTRAINTS_ROOT / constraint_name).read_text(encoding="utf-8")
        transformers_lock, huggingface_hub_lock = PYTHON_311_MODEL_STACK_LOCKS[constraint_name]
        assert transformers_lock in constraint_text, constraint_name
        assert huggingface_hub_lock in constraint_text, constraint_name
        assert RETIRED_TRANSFORMERS_LOCK_PREFIX not in constraint_text, constraint_name
        assert RETIRED_HUGGINGFACE_HUB_LOCK_PREFIX not in constraint_text, constraint_name


def test_ocr_engine_strategy_is_rapidocr_across_python_311_constraints() -> None:
    """OCR 引擎策略为三平台统一 rapidocr PP-OCRv6，任何 3.11 约束文件不得出现 ocrmac。

    macOS Apple Vision（ocrmac）已在 2026-09-16 A/B 实测中被否决：实扫页输出乱码且
    出现疑似幻觉数字；darwin / linux / win32 统一走 rapidocr PP-OCRv6 路径。

    :returns: ``None``。
    :raises AssertionError: 任一 3.11 约束文件出现 ocrmac 时抛出。
    """

    for constraint_name in PYTHON_311_CONSTRAINT_NAMES:
        constraint_text = (CONSTRAINTS_ROOT / constraint_name).read_text(encoding="utf-8")
        assert RETIRED_OCR_ENGINE_MARKER not in constraint_text, constraint_name


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

    assert "dayu-cli = dayu.cli.__main__:exit_module" in entrypoints
    assert not any(script_name in entrypoints for script_name in PLACEHOLDER_SCRIPT_NAMES)
    assert "Provides-Extra: web" not in metadata
    assert "Requires-Dist: streamlit" not in metadata
    assert not any(
        name.startswith(package_prefix)
        for name in names
        for package_prefix in PLACEHOLDER_PACKAGE_PREFIXES
    )
