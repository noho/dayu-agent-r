"""源码安装的标准库只读查询；不发布文件，不产生第二版本真源。"""

from __future__ import annotations

import json
import platform
import re
import struct
import sys
import sysconfig
import tomllib
from importlib.metadata import PathDistribution
from importlib.util import find_spec
from pathlib import Path
from typing import TypeAlias, cast
from urllib.parse import urlsplit
from urllib.request import url2pathname

_SUPPORTED_POINTER_BYTES = 8

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    """验证查询结果中的映射。

    :param value: 已解码的 JSON 值。
    :returns: 字符串键映射。
    :raises ValueError: 值不是映射。
    """
    if not isinstance(value, dict):
        raise ValueError("metadata 必须是映射")
    return value


def _project(source: Path) -> tuple[str, str, str]:
    """从唯一项目声明读取安装身份。

    :param source: 真实源码根。
    :returns: 包名、版本及 console target。
    :raises ValueError: 项目声明不完整。
    :raises OSError: 声明不可读取。
    """
    data = cast(dict[str, JsonValue], tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8")))
    project = _mapping(data.get("project"))
    scripts = _mapping(project.get("scripts"))
    name, version, target = project.get("name"), project.get("version"), scripts.get("dayu-cli")
    if not all(isinstance(value, str) and value for value in (name, version, target)):
        raise ValueError("项目 name/version/dayu-cli 声明缺失")
    assert isinstance(name, str) and isinstance(version, str) and isinstance(target, str)
    return name, version, target


def _venv(source: Path) -> None:
    """断言解释器确属本源码的 Python 3.11 venv。

    :param source: 源码根。
    :returns: None。
    :raises ValueError: 解释器身份不符。
    """
    if sys.version_info[:2] != (3, 11) or sys.prefix == sys.base_prefix:
        raise ValueError("需要 Python 3.11 独立 venv")
    if Path(sys.prefix).resolve() != (source / ".venv").resolve():
        raise ValueError("venv 不属于本源码目标")
    target = (source / ".venv").resolve()
    config = (target / "pyvenv.cfg").read_text(encoding="utf-8")
    if "include-system-site-packages = false" not in config.splitlines():
        raise ValueError("目标 venv 不得借用系统 site-packages")
    if any(not Path(sysconfig.get_path(key)).resolve().is_relative_to(target) for key in ("purelib", "platlib", "scripts")):
        raise ValueError("目标 venv 路径越出本次安装目录")
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        raise ValueError("不支持非标准 Python ABI")


def _installed(source: Path) -> None:
    """核验实际 site 中唯一 dist-info、editable 来源及公开入口。

    :param source: 规范化源码根（Windows 使用 native 路径）。
    :returns: None；证据 JSON 写 stdout。
    :raises ValueError: metadata、来源、版本或入口不符合声明。
    :raises OSError: 实际 metadata 不可读取。
    """
    _venv(source)
    name, version, target = _project(source)
    sites = {Path(sysconfig.get_path(key)).resolve() for key in ("purelib", "platlib")}
    matches: list[tuple[Path, PathDistribution]] = []
    for site in sorted(sites):
        for path in sorted(site.glob("*.dist-info")):
            dist = PathDistribution(path)
            if dist.metadata["Name"] and re.sub(r"[-_.]+", "-", dist.metadata["Name"].lower()) == re.sub(r"[-_.]+", "-", name.lower()):
                if path.resolve().parent != site:
                    raise ValueError("项目 dist-info 越出目标 site")
                matches.append((path, dist))
    if len(matches) != 1:
        raise ValueError("目标 site 必须恰有一份实际项目 dist-info")
    path, dist = matches[0]
    if dist.version != version:
        raise ValueError("实际安装版本与源码声明不一致")
    entries = [entry.value for entry in dist.entry_points if entry.group == "console_scripts" and entry.name == "dayu-cli"]
    if entries != [target]:
        raise ValueError("实际 console script target 与声明不一致")
    direct = _mapping(cast(JsonValue, json.loads((path / "direct_url.json").read_text(encoding="utf-8"))))
    url = direct.get("url")
    editable = _mapping(direct.get("dir_info")).get("editable")
    if not isinstance(url, str) or editable is not True:
        raise ValueError("需要本源码的 editable 安装")
    parsed = urlsplit(url)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        raise ValueError("editable 来源必须为本地源码")
    # 两侧都 resolve，允许 pip 记录规范路径而调用路径含 symlink。
    if Path(url2pathname(parsed.path)).resolve() != source.resolve():
        raise ValueError("editable source 不属于本次源码")
    spec = find_spec("dayu")
    if spec is None or spec.origin is None or Path(spec.origin).resolve() != (source / "dayu/__init__.py").resolve():
        raise ValueError("实际模块来源不属于 editable 源码")
    console = Path(sysconfig.get_path("scripts")) / ("dayu-cli.exe" if sys.platform == "win32" else "dayu-cli")
    if not console.is_file():
        raise ValueError("pip 未生成实际 console script")
    print(json.dumps({"name": name, "version": dist.version, "dist_info": str(path), "direct_url": direct,
                      "executable": sys.executable, "prefix": sys.prefix, "sites": [str(site) for site in sorted(sites)],
                      "scripts": sysconfig.get_path("scripts"), "console": str(console), "module_origin": spec.origin}, ensure_ascii=False))


def main(argv: list[str]) -> int:
    """执行单个标准库查询。

    :param argv: 查询模式及源码路径。
    :returns: 成功 0、输入或查询失败 1。
    :raises OSError: stdout 无法写入。
    """
    try:
        if len(argv) != 2:
            raise ValueError("需要查询模式和源码路径")
        mode, source_text = argv
        source = Path(source_text).resolve()
        if mode == "platform":
            if sys.version_info[:2] != (3, 11):
                raise ValueError("安装需要 Python 3.11")
            if struct.calcsize("P") != _SUPPORTED_POINTER_BYTES:
                raise ValueError("现有依赖锁只支持 64 位 Python")
            print(f"{sys.platform}|{platform.machine().lower()}")
        elif mode == "venv":
            _venv(source)
            print(sysconfig.get_path("scripts"))
        elif mode == "installed":
            _installed(source)
        else:
            raise ValueError("未知查询模式")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"安装查询失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
