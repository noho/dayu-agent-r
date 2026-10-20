"""安装只读查询的 owner 合同；合成 dist-info 只用于单元验证。"""

from __future__ import annotations

import json
import sys
from importlib.machinery import ModuleSpec
from functools import partial
from pathlib import Path

import pytest

from scripts import install_source_query as query


_METADATA = "Metadata-Version: 2.1\nName: dayu-agent\nVersion: 0.1.5\n"
_ENTRY = "[console_scripts]\ndayu-cli = dayu.cli.__main__:exit_module\n"
_PROJECT = '[project]\nname="dayu-agent"\nversion="0.1.5"\n[project.scripts]\ndayu-cli="dayu.cli.__main__:exit_module"\n'


def _site_path(venv: Path, key: str) -> str:
    """模拟标准库路径查询的边界。

    :param venv: 合成目标。
    :param key: sysconfig 路径键。
    :returns: scripts 或 site 路径。
    :raises ValueError: 未知键。
    """
    if key == "scripts":
        return str(venv / "bin")
    if key in ("purelib", "platlib"):
        return str(venv / "site")
    raise ValueError(key)


def _spec_path(path: Path, name: str) -> ModuleSpec:
    """提供模块查找的标准库边界。

    :param path: 模块位置。
    :param name: 模块名。
    :returns: 明确 origin 的 spec。
    :raises OSError: 不主动抛出。
    """
    return ModuleSpec(name, loader=None, origin=str(path))


def _context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """准备明确标记的合成 metadata，不模拟 pip 成功。

    :param tmp_path: 独立文件系统。
    :param monkeypatch: pytest 恢复标准库查询边界。
    :returns: 源码根、dist-info。
    :raises OSError: 文件无法创建。
    """
    source = tmp_path / "source 中文 space"
    venv = source / ".venv"
    dist = venv / "site/dayu_agent-0.1.5.dist-info"
    dist.mkdir(parents=True)
    (venv / "bin").mkdir()
    (venv / "pyvenv.cfg").write_text("include-system-site-packages = false\n", encoding="utf-8")
    monkeypatch.setattr(query, "find_spec", partial(_spec_path, source / "dayu/__init__.py"))
    (venv / "bin/dayu-cli").write_text("SYNTHETIC, NOT EXECUTED", encoding="utf-8")
    (source / "pyproject.toml").write_text(_PROJECT, encoding="utf-8")
    (dist / "METADATA").write_text(_METADATA, encoding="utf-8")
    (dist / "entry_points.txt").write_text(_ENTRY, encoding="utf-8")
    (dist / "direct_url.json").write_text(json.dumps({"url": source.as_uri(), "dir_info": {"editable": True}}), encoding="utf-8")
    monkeypatch.setattr(sys, "prefix", str(venv))
    monkeypatch.setattr(query.sysconfig, "get_path", partial(_site_path, venv))
    return source, dist


@pytest.mark.parametrize("mode", ["platform", "venv", "installed"])
def test_queries_use_actual_declaration_and_normalized_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mode: str) -> None:
    """唯一声明与 direct_url 对 symlink 归一化后相同。

    :param tmp_path: 独立根。
    :param monkeypatch: 查询边界恢复器。
    :param capsys: stdout 捕获。
    :param mode: 查询模式。
    :returns: None。
    :raises AssertionError: 合法合同失败。
    """
    source, _ = _context(tmp_path, monkeypatch)
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    assert query.main([mode, str(alias)]) == 0
    assert capsys.readouterr().out


@pytest.mark.parametrize("defect", ["missing", "duplicate", "version", "entry", "source", "remote", "noneditable", "badjson", "mapping", "console", "project", "prefix", "base", "system-site", "module"])
def test_invalid_installation_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str) -> None:
    """实际 site/来源/入口异常不能用版本字符串掩盖。

    :param tmp_path: 独立根。
    :param monkeypatch: 标准库边界恢复器。
    :param defect: 异常事实。
    :returns: None。
    :raises AssertionError: 错误被接受。
    """
    source, dist = _context(tmp_path, monkeypatch)
    if defect == "missing":
        (dist / "METADATA").write_text("Name: other\nVersion: 0.1.5\n", encoding="utf-8")
    elif defect == "duplicate":
        duplicate = dist.parent / "duplicate.dist-info"
        duplicate.mkdir()
        (duplicate / "METADATA").write_text(_METADATA, encoding="utf-8")
    elif defect == "version":
        (dist / "METADATA").write_text(_METADATA.replace("0.1.5", "0.1.4"), encoding="utf-8")
    elif defect == "entry":
        (dist / "entry_points.txt").write_text(_ENTRY.replace("exit_module", "other"), encoding="utf-8")
    elif defect in ("source", "remote", "noneditable", "mapping", "badjson"):
        content = {"url": source.as_uri(), "dir_info": {"editable": True}}
        if defect == "source":
            content["url"] = tmp_path.as_uri()
        elif defect == "remote":
            content["url"] = "https://example.invalid/source"
        elif defect == "noneditable":
            content["dir_info"] = {"editable": False}
        (dist / "direct_url.json").write_text("[" if defect == "badjson" else "[]" if defect == "mapping" else json.dumps(content), encoding="utf-8")
    elif defect == "console":
        (source / ".venv/bin/dayu-cli").unlink()
    elif defect == "project":
        (source / "pyproject.toml").write_text(_PROJECT.replace('version="0.1.5"', 'version=1'), encoding="utf-8")
    elif defect == "prefix":
        monkeypatch.setattr(sys, "prefix", str(tmp_path))
    elif defect == "system-site":
        (source / ".venv/pyvenv.cfg").write_text("include-system-site-packages = true\n", encoding="utf-8")
    elif defect == "module":
        monkeypatch.setattr(query, "find_spec", partial(_spec_path, tmp_path / "wrong.py"))
    else:
        monkeypatch.setattr(sys, "base_prefix", sys.prefix)
    assert query.main(["installed", str(source)]) == 1


def test_invalid_query_and_python_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """输入错误和错误 Python 版本应明确失败。

    :param tmp_path: 独立根。
    :param monkeypatch: 标准库恢复器。
    :returns: None。
    :raises AssertionError: 非法输入被接受。
    """
    assert query.main([]) == 1
    assert query.main(["unknown", str(tmp_path)]) == 1
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))
    assert query.main(["platform", str(tmp_path)]) == 1


def _pointer32(format_text: str) -> int:
    """模拟标准库指针宽度查询边界。

    :param format_text: struct 格式。
    :returns: 32 位指针的字节数。
    :raises AssertionError: 查询不是指针。
    """
    assert format_text == "P"
    return 4


@pytest.mark.parametrize("mode", ["platform", "venv", "installed"])
def test_32bit_python_cannot_select_64bit_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """OS 架构不能替代 Python 指针宽度；写前拒绝 32 位解释器。

    :param tmp_path: 独立 cwd。
    :param monkeypatch: 标准库恢复器。
    :param mode: bootstrap、实际 pip venv 或安装核验查询。
    :returns: None。
    :raises AssertionError: 错误接受 32 位解释器。
    """
    source, _ = _context(tmp_path, monkeypatch)
    monkeypatch.setattr(query.struct, "calcsize", _pointer32)
    assert query.main([mode, str(source)]) == 1


@pytest.mark.parametrize(("os_name", "arch"), [("darwin", "arm64"), ("linux", "x86_64"), ("win32", "amd64")])
def test_venv_query_projects_its_own_platform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], os_name: str, arch: str) -> None:
    """实际 venv 身份查询直接携带平台，不从 bootstrap 或目录后缀推断。

    :param tmp_path: 隔离文件系统。
    :param monkeypatch: 标准库身份边界恢复器。
    :param capsys: 输出捕获器。
    :param os_name: 受控 OS。
    :param arch: 受控架构。
    :returns: None。
    :raises AssertionError: 平台投影与解释器事实不同源。
    """
    source, _ = _context(tmp_path, monkeypatch)
    monkeypatch.setattr(query.sys, "platform", os_name)
    monkeypatch.setattr(query.platform, "machine", partial(str, arch))
    assert query.main(["venv", str(source)]) == 0
    assert capsys.readouterr().out.strip() == f"{os_name}|{arch}|{source / '.venv/bin'}"
