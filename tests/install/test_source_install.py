"""Bash 安装 owner 的隔离行为回归；受控边界不替代真实 pip 安装。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from dayu.cli.init_environment import (
    EnvironmentPersistenceEntry,
    persist_environment,
    plan_environment_persistence,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "install-source.sh"
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"
def _python_executable() -> str:
    """定位测试的基础 Python。

    :returns: Python 3.11 的单个路径。
    :raises RuntimeError: 未找到解释器。
    """
    executable = shutil.which("python3.11", path=BASE_PATH)
    if executable is None:
        raise RuntimeError("需要基础 Python 3.11")
    return executable


PYTHON = _python_executable()
pytestmark = pytest.mark.skipif(os.name == "nt", reason="本机 POSIX Bash/zsh 行为测试；Windows 另需真实 runner")


def _run(home: Path, code: str, *args: str, zdotdir: str | None = None) -> subprocess.CompletedProcess[str]:
    """在源外目录调用真实 Bash owner 函数或脚本。

    :param home: 隔离用户目录。
    :param code: 固定测试代码，不拼接用户输入。
    :param args: 通过位置参数传递的输入。
    :param zdotdir: None 表示未继承，否则原样传递（含空值）。
    :returns: 两通道及退出码。
    :raises OSError: 子进程无法启动。
    """
    env = {"HOME": str(home), "PATH": BASE_PATH, "LC_ALL": "en_US.UTF-8"}
    if zdotdir is not None:
        env["ZDOTDIR"] = zdotdir
    argv = ["/bin/bash", "-c", code, "test", str(SCRIPT), *args]
    result = subprocess.run(
        argv, cwd=home.parent, env=env, capture_output=True, text=True, check=False,
    )
    # 失败与成功都保留实际子进程证据；不以 pytest 的汇总替代负例结果。
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=home.parent,
                                     prefix="install-command-", suffix=".json", delete=False) as record:
        json.dump({"argv": argv, "cwd": str(home.parent), "env_whitelist": env,
                   "stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode},
                  record, ensure_ascii=False, indent=2)
    return result


@pytest.mark.skipif(not Path("/bin/zsh").exists(), reason="需要真实 zsh")
@pytest.mark.parametrize("value", [None, "", "home", "other", "env-empty", "env-other"])
def test_zdotdir_guard_before_any_install_write(tmp_path: Path, value: str | None) -> None:
    """真实 zsh 两种正常模式必须拒绝空值和其它目录且不写安装文件。

    :param tmp_path: 独立文件系统。
    :param value: 继承值或 .zshenv 场景。
    :returns: None。
    :raises AssertionError: 错误接受目录或发生写入。
    """
    home = tmp_path / "home"
    home.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    if value and value.startswith("env-"):
        setting = "" if value == "env-empty" else str(other)
        (home / ".zshenv").write_text(f'export ZDOTDIR="{setting}"\n', encoding="utf-8")
    before = {p.name: p.read_bytes() for p in home.iterdir()}
    inherited = str(home) if value == "home" else str(other) if value == "other" else "" if value == "" else None
    result = _run(home, 'source "$1"; check_shell zsh /bin/zsh preflight "$HOME/.local/bin/dayu-cli"', zdotdir=inherited)
    assert (result.returncode == 0) == (value in (None, "home")), result.stderr
    assert {p.name: p.read_bytes() for p in home.iterdir()} == before


@pytest.mark.skipif(not Path("/bin/zsh").exists(), reason="需要真实 zsh")
@pytest.mark.parametrize("kind", ["unknown", "directory", "directory-link", "fifo", "parent-link", "local-parent-link", "profile-link", "broken-block"])
def test_known_conflicts_fail_before_venv(tmp_path: Path, kind: str) -> None:
    """真实脚本预检不接管未知文件和特殊路径。

    :param tmp_path: 独立源码和 HOME。
    :param kind: 冲突形态。
    :returns: None。
    :raises AssertionError: 冲突被覆盖或预检过晚。
    """
    source = tmp_path / "source"
    shutil.copytree(ROOT / "scripts", source / "scripts")
    shutil.copytree(ROOT / "constraints", source / "constraints")
    shutil.copyfile(ROOT / "pyproject.toml", source / "pyproject.toml")
    home = tmp_path / "home"
    home.mkdir()
    dest = home / ".local" / "bin" / "dayu-cli"
    dest.parent.mkdir(parents=True)
    if kind == "unknown":
        dest.write_text("user executable", encoding="utf-8")
    elif kind == "directory":
        dest.mkdir()
    elif kind == "directory-link":
        dest.symlink_to(tmp_path, target_is_directory=True)
    elif kind == "fifo":
        os.mkfifo(dest)
    elif kind == "parent-link":
        dest.parent.rmdir()
        dest.parent.symlink_to(tmp_path, target_is_directory=True)
    elif kind == "local-parent-link":
        dest.parent.rmdir()
        dest.parent.parent.rmdir()
        dest.parent.parent.symlink_to(tmp_path, target_is_directory=True)
    elif kind == "profile-link":
        (home / ".zshrc").symlink_to(source / "pyproject.toml")
    else:
        (home / ".zshrc").write_text("# >>> dayu source install PATH >>>\nchanged\n", encoding="utf-8")
    result = _run(home, 'bash "$2" --shell zsh --python "$3"', str(source / "scripts" / "install-source.sh"), PYTHON)
    assert result.returncode != 0
    assert "安装失败 [预检]" in result.stderr
    assert not (source / ".venv").exists()
    if kind == "unknown":
        assert dest.read_text(encoding="utf-8") == "user executable"


def test_launcher_forwards_arguments_and_exit_without_fallback(tmp_path: Path) -> None:
    """普通 launcher 的 exec 保留空格、中文、空参数和目标退出码。

    :param tmp_path: 独立路径。
    :returns: None。
    :raises AssertionError: argv 或失败状态改变。
    """
    target = tmp_path / "中文 space ' target"
    target.write_text('#!/bin/bash\nprintf "<%s>\\n" "$@"\nexit 37\n', encoding="utf-8")
    target.chmod(0o700)
    launcher = tmp_path / "launcher"
    result = _run(tmp_path, 'source "$1"; launcher_text "$2" > "$3"; chmod 700 "$3"; "$3" "空 格" "" \'$literal\'', str(target), str(launcher))
    assert result.returncode == 37
    assert result.stdout == "<空 格>\n<>\n<$literal>\n"
    target.unlink()
    failed = _run(tmp_path, 'bash "$2"', str(launcher))
    assert failed.returncode != 0


def test_profile_preserves_bytes_mode_and_single_block(tmp_path: Path) -> None:
    """完整重复发布保持原文、权限与 init block，破损 block 拒绝。

    :param tmp_path: 独立 HOME。
    :returns: None。
    :raises AssertionError: 幂等或保全合同不成立。
    """
    profile = tmp_path / ".bashrc"
    original = b"# user\n# >>> dayu-cli init >>>\nexport HF_ENDPOINT=https://example.invalid\n# <<< dayu-cli init <<<"
    profile.write_bytes(original)
    profile.chmod(0o640)
    result = _run(tmp_path, 'source "$1"; publish_profile "$2"; publish_profile "$2"', str(profile))
    assert result.returncode == 0, result.stderr
    assert profile.read_bytes().startswith(original + b"\n")
    assert profile.read_bytes().count(b"# >>> dayu source install PATH >>>") == 1
    assert profile.stat().st_mode & 0o777 == 0o640
    profile.write_bytes(profile.read_bytes().replace(b"export PATH", b"export WRONG"))
    before = profile.read_bytes()
    rejected = _run(tmp_path, 'source "$1"; inspect_profile "$2"', str(profile))
    assert rejected.returncode != 0
    assert profile.read_bytes() == before


@pytest.mark.parametrize("kind", ["absent", "legacy", "dangling", "current", "same"])
def test_entry_replacement_preserves_old_target(tmp_path: Path, kind: str) -> None:
    """替换 symlink 只改目录项，重复普通 launcher 不改 mtime。

    :param tmp_path: 独立目录。
    :param kind: 已授权入口状态。
    :returns: None。
    :raises AssertionError: 目标被沿链修改或幂等失败。
    """
    old = tmp_path / "old"
    old.write_bytes(b"SYNTHETIC preservation\x00")
    old.chmod(0o751)
    fingerprint = (old.read_bytes(), old.stat().st_mode, old.stat().st_mtime_ns)
    dest = tmp_path / "dayu-cli"
    target = tmp_path / "new console"
    if kind in ("legacy", "dangling", "current"):
        dest.symlink_to(old if kind == "legacy" else tmp_path / "missing" if kind == "dangling" else target)
    if kind == "same":
        result = _run(tmp_path, 'source "$1"; publish_entry "$2" "$3"', str(dest), str(target))
        assert result.returncode == 0, result.stderr
    result = _run(tmp_path, 'source "$1"; publish_entry "$2" "$3"', str(dest), str(target))
    assert result.returncode == 0, result.stderr
    assert dest.is_file() and not dest.is_symlink()
    before = (dest.read_bytes(), dest.stat().st_mtime_ns)
    repeat = _run(tmp_path, 'source "$1"; publish_entry "$2" "$3"', str(dest), str(target))
    assert repeat.returncode == 0
    assert (dest.read_bytes(), dest.stat().st_mtime_ns) == before
    assert (old.read_bytes(), old.stat().st_mode, old.stat().st_mtime_ns) == fingerprint


@pytest.mark.parametrize("shell", ["bash", "zsh"])
@pytest.mark.parametrize("override", ["function", "alias", "path"])
def test_normal_shell_resolves_external_entry_and_rejects_function(tmp_path: Path, shell: str, override: str) -> None:
    """真实正常 shell 不能用 function 或后置 PATH 覆盖冒充默认命令。

    :param tmp_path: 独立 HOME。
    :param shell: 目标 shell。
    :param override: function、alias 或后置 PATH 覆盖。
    :returns: None。
    :raises AssertionError: 正常解析或冲突判断错误。
    """
    if not Path(f"/bin/{shell}").exists():
        pytest.skip("目标 shell 未安装")
    dest = tmp_path / ".local/bin/dayu-cli"
    dest.parent.mkdir(parents=True)
    dest.write_text('#!/bin/bash\n[[ "$1" == --help ]]\n', encoding="utf-8")
    dest.chmod(0o700)
    profiles = [tmp_path / ".zshrc"] if shell == "zsh" else [tmp_path / ".bashrc", tmp_path / ".bash_profile"]
    for profile in profiles:
        assert _run(tmp_path, 'source "$1"; publish_profile "$2"', str(profile)).returncode == 0
    result = _run(tmp_path, 'source "$1"; check_shell "$2" "$3" published "$4"', shell, f"/bin/{shell}", str(dest))
    assert result.returncode == 0, result.stderr
    with profiles[0].open("a") as stream:
        stream.write('\ndayu-cli() { return 0; }\n' if override == 'function' else '\nalias dayu-cli=true\n' if override == 'alias' else '\nexport PATH=/usr/bin:/bin\n')
    rejected = _run(tmp_path, 'source "$1"; check_shell "$2" "$3" published "$4"', shell, f"/bin/{shell}", str(dest))
    assert rejected.returncode != 0


@pytest.mark.parametrize("operation", ["profile", "entry"])
def test_atomic_publish_failure_keeps_original(tmp_path: Path, operation: str) -> None:
    """在 mv 边界注入失败，原文件不会被截断或沿链接修改。

    :param tmp_path: 独立目录。
    :param operation: 发布类型。
    :returns: None。
    :raises AssertionError: 失败被吞或原资产变化。
    """
    dest = tmp_path / "destination"
    old = tmp_path / "old"
    old.write_text("preserve", encoding="utf-8")
    if operation == "entry":
        dest.symlink_to(old)
    else:
        dest.write_text("preserve", encoding="utf-8")
    result = _run(tmp_path, 'source "$1"; trap cleanup EXIT; mv() { return 43; }; if [[ "$2" == profile ]]; then publish_profile "$3"; else publish_entry "$3" "$4"; fi', operation, str(dest), str(tmp_path / "console"))
    assert result.returncode == 43
    assert dest.read_text(encoding="utf-8") == "preserve"
    assert old.read_text(encoding="utf-8") == "preserve"
    assert not list(tmp_path.glob("*.dayu.*"))


def test_windows_exe_collision_is_preflight_conflict(tmp_path: Path) -> None:
    """Git Bash 同名 exe 碰撞按入口合同拒绝；这不是 Windows 实机测试。

    :param tmp_path: 合成路径布局。
    :returns: None。
    :raises AssertionError: exe 被忽略。
    """
    (tmp_path / "dayu-cli.exe").write_bytes(b"SYNTHETIC EXE collision")
    result = _run(tmp_path, 'source "$1"; inspect_entry "$2" "$3"', str(tmp_path / "dayu-cli"), str(tmp_path / "Scripts/dayu-cli.exe"))
    assert result.returncode != 0
    assert not (tmp_path / "dayu-cli").exists()


@pytest.mark.parametrize(("host", "os_name", "arch", "lock"), [
    ("Darwin", "darwin", "arm64", "lock-macos-arm64-py311.txt"),
    ("Linux", "linux", "x86_64", "lock-linux-x64-py311.txt"),
    ("MINGW64_NT", "win32", "amd64", "lock-windows-x64-py311.txt"),
    ("MSYS_NT", "win32", "amd64", "lock-windows-x64-py311.txt"),
    ("Linux", "win32", "amd64", ""),
    ("MINGW64_NT", "linux", "x86_64", ""),
    ("Darwin", "darwin", "x86_64", ""),
])
def test_platform_lock_contract(tmp_path: Path, host: str, os_name: str, arch: str, lock: str) -> None:
    """平台分支只验证选择合同，不能声称非本机 OS 安装通过。

    :param tmp_path: 独立 cwd。
    :param host: Bash OS。
    :param os_name: Python OS。
    :param arch: Python 架构。
    :param lock: 预期锁或拒绝。
    :returns: None。
    :raises AssertionError: 混用 Windows/WSL 或错误选锁。
    """
    result = _run(tmp_path, 'source "$1"; select_lock "$2" "$3" "$4"', host, os_name, arch)
    assert (result.returncode == 0) == bool(lock)
    if lock:
        assert result.stdout.strip() == lock


@pytest.mark.skipif(not Path("/bin/zsh").exists(), reason="需要真实 zsh")
@pytest.mark.parametrize("setting", ["", "other", "env-empty", "env-other"])
def test_full_preflight_zdotdir_preserves_files(tmp_path: Path, setting: str) -> None:
    """完整入口在真实 zsh 启动后、任何 venv/profile 写入前拒绝异常值。

    :param tmp_path: 独立源码、HOME。
    :param setting: 继承或启动配置值。
    :returns: None。
    :raises AssertionError: 失败过晚或资产改变。
    """
    source = tmp_path / "source"
    shutil.copytree(ROOT / "scripts", source / "scripts")
    shutil.copytree(ROOT / "constraints", source / "constraints")
    home = tmp_path / "home"
    home.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    (other / ".zshrc").write_text('export PATH="$HOME/.local/bin:$PATH"\n', encoding="utf-8")
    if setting.startswith("env-"):
        (home / ".zshenv").write_text('export ZDOTDIR=""\n' if setting == "env-empty" else f'export ZDOTDIR="{other}"\n', encoding="utf-8")
    before = {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in home.iterdir()}
    result = _run(home, 'bash "$2" --shell zsh --python "$3"', str(source / "scripts/install-source.sh"), PYTHON, zdotdir=None if setting.startswith("env-") else str(other) if setting == "other" else "")
    assert result.returncode != 0
    assert "正常 zsh" in result.stderr
    assert not (source / ".venv").exists()
    assert {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in home.iterdir()} == before


@pytest.mark.parametrize("kind", ["pip-fail", "venv-link", "venv-file", "bad-python", "missing-lock"])
def test_full_install_failure_never_publishes(tmp_path: Path, kind: str) -> None:
    """真实 pip 外部资源失败与输入错误不能发布默认入口。

    :param tmp_path: 独立源码和 HOME。
    :param kind: 失败阶段。
    :returns: None。
    :raises AssertionError: 错误输出成功或提前发布。
    """
    source = tmp_path / "source"
    shutil.copytree(ROOT / "scripts", source / "scripts")
    shutil.copytree(ROOT / "constraints", source / "constraints")
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copyfile(ROOT / name, source / name)
    home = tmp_path / "home"
    home.mkdir()
    if kind == "venv-link":
        (source / ".venv").symlink_to(tmp_path, target_is_directory=True)
    elif kind == "venv-file":
        (source / ".venv").write_bytes(b"unknown")
    elif kind == "missing-lock":
        (source / "constraints/lock-common-py311.txt").unlink()
    python = "/bin/false" if kind == "bad-python" else PYTHON
    result = _run(home, 'export PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=1; bash "$2" --shell bash --python "$3"', str(source / "scripts/install-source.sh"), python)
    assert result.returncode != 0
    assert "安装完成。" not in result.stdout
    assert not (home / ".bashrc").exists()
    assert not (home / ".local").exists()
    if kind == "pip-fail":
        assert "venv/pip" in result.stderr


def test_profile_cleanup_failure_is_reported(tmp_path: Path) -> None:
    """临时文件无法清理时保留路径及原始失败，不能伪装成功。

    :param tmp_path: 独立文件系统。
    :returns: None。
    :raises AssertionError: 清理诊断丢失。
    """
    dest = tmp_path / ".bashrc"
    result = _run(tmp_path, 'source "$1"; trap cleanup EXIT; mv() { return 43; }; rm() { return 44; }; publish_profile "$2"', str(dest))
    assert result.returncode == 43
    assert "清理失败，残留:" in result.stderr
    assert not dest.exists()
    assert len(list(tmp_path.glob(".bashrc.dayu.*"))) == 1


@pytest.mark.parametrize("order", ["init-first", "install-first"])
def test_init_and_install_owners_preserve_each_other(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, order: str) -> None:
    """顺序执行两个真实 owner，不借用或误判对方 block。

    :param tmp_path: 独立 HOME。
    :param monkeypatch: 恢复测试变量。
    :param order: 执行顺序。
    :returns: None。
    :raises AssertionError: 任一 block 遗失。
    """
    monkeypatch.setenv("HF_ENDPOINT", "https://before.invalid")
    profile = tmp_path / ".bashrc"
    plan = plan_environment_persistence(
        entries=(EnvironmentPersistenceEntry(name="HF_ENDPOINT", value="https://synthetic.invalid"),),
        platform_system="Darwin", home_directory=tmp_path, shell_path="/bin/bash", confirmed=True,
    )
    if order == "init-first":
        assert persist_environment(plan).succeeded
    assert _run(tmp_path, 'source "$1"; publish_profile "$2"', str(profile)).returncode == 0
    if order == "install-first":
        assert persist_environment(plan).succeeded
    before = profile.read_bytes()
    assert persist_environment(plan).succeeded
    assert _run(tmp_path, 'source "$1"; publish_profile "$2"', str(profile)).returncode == 0
    assert profile.read_bytes() == before
    assert before.count(b"# >>> dayu-cli init >>>") == 1
    assert before.count(b"# >>> dayu source install PATH >>>") == 1


@pytest.mark.parametrize("setting", ["", "other"])
def test_login_startup_zdotdir_is_checked_before_writes(tmp_path: Path, setting: str) -> None:
    """非登录检查通过后，真实登录启动设置空/其它目录仍必须写前失败。

    :param tmp_path: 隔离源码与 HOME。
    :param setting: .zprofile 中的 ZDOTDIR。
    :returns: None。
    :raises AssertionError: 登录模式检测遗漏。
    """
    if not Path("/bin/zsh").exists():
        pytest.skip("需要真实 zsh")
    source = tmp_path / "source"
    shutil.copytree(ROOT / "scripts", source / "scripts")
    shutil.copytree(ROOT / "constraints", source / "constraints")
    home = tmp_path / "home"
    home.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    (home / ".zprofile").write_text(f'export ZDOTDIR="{other if setting else ""}"\n', encoding="utf-8")
    before = (home / ".zprofile").read_bytes()
    result = _run(home, 'bash "$2" --shell zsh --python "$3"', str(source / "scripts/install-source.sh"), PYTHON)
    assert result.returncode != 0
    assert "正常 zsh -lic" in result.stderr
    assert not (source / ".venv").exists()
    assert (home / ".zprofile").read_bytes() == before
    assert not (home / ".local").exists()


def test_gitbash_native_query_paths_before_exe_conflict(tmp_path: Path) -> None:
    """受控 Windows 查询边界核对 native 转换与 exe 碰撞；不冒充真机。

    :param tmp_path: 合成 Git Bash 路径布局。
    :returns: None。
    :raises AssertionError: 路径转换或碰撞检查遗漏。
    """
    source = tmp_path / "源码 space"
    shutil.copytree(ROOT / "scripts", source / "scripts")
    shutil.copytree(ROOT / "constraints", source / "constraints")
    home = tmp_path / "home"
    (home / ".local/bin").mkdir(parents=True)
    collision = home / ".local/bin/dayu-cli.exe"
    collision.write_bytes(b"SYNTHETIC Windows collision")
    code = '''source "$2"
uname() { printf 'MINGW64_NT\\n'; }
cygpath() { [[ "$1" == -w ]] || return 97; printf 'NATIVE:%s\\n' "$2"; }
windows_python() {
  [[ "$1" == -I && "$2" == NATIVE:*install_source_query.py && "$3" == platform && "$4" == NATIVE:* ]] || return 98
  printf 'win32|amd64\\n'
}
main --shell bash --python windows_python'''
    result = _run(home, code, str(source / "scripts/install-source.sh"))
    assert result.returncode != 0
    assert "入口 .exe 碰撞" in result.stderr
    assert not (source / ".venv").exists()
    assert collision.read_bytes() == b"SYNTHETIC Windows collision"


@pytest.mark.parametrize(("present", "rejected"), [
    ((".bash_login", ".profile"), True),
    ((".profile",), True),
    ((".bash_profile", ".bash_login", ".profile"), False),
])
def test_bash_login_file_priority(tmp_path: Path, present: tuple[str, ...], rejected: bool) -> None:
    """完整入口按 Bash 登录文件优先级预检，不接管较低优先级文件。

    :param tmp_path: 隔离源码与 HOME。
    :param present: 存在的登录文件。
    :param rejected: 首个候选是否为 symlink 冲突。
    :returns: None。
    :raises AssertionError: 选择了错误文件或发布过早。
    """
    source = tmp_path / "source"
    shutil.copytree(ROOT / "scripts", source / "scripts")
    shutil.copytree(ROOT / "constraints", source / "constraints")
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copyfile(ROOT / name, source / name)
    home = tmp_path / "home"
    home.mkdir()
    for name in present:
        if name == ".bash_profile":
            (home / name).write_text("# synthetic login\n", encoding="utf-8")
        else:
            (home / name).symlink_to(source / "README.md")
    result = _run(home, 'export PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=1; bash "$2" --shell bash --python "$3"', str(source / "scripts/install-source.sh"), PYTHON)
    assert result.returncode != 0
    assert ("profile 不能为 symlink" in result.stderr) == rejected
    if not rejected:
        assert "venv/pip" in result.stderr
    assert not (home / ".local").exists()
    assert (source / "README.md").read_bytes() == (ROOT / "README.md").read_bytes()


def test_profile_success_then_entry_failure_is_honest(tmp_path: Path) -> None:
    """入口发布失败保留已经完成的 profile 与旧链接目标，重试可收敛。

    :param tmp_path: 独立文件系统。
    :returns: None。
    :raises AssertionError: 谎称回滚或损坏旧目标。
    """
    old = tmp_path / "old"
    old.write_bytes(b"SYNTHETIC old executable")
    dest = tmp_path / "dayu-cli"
    dest.symlink_to(old)
    profile = tmp_path / ".bashrc"
    target = tmp_path / "new console"
    result = _run(tmp_path, 'source "$1"; trap cleanup EXIT; publish_profile "$2"; mv() { return 43; }; INSTALL_STAGE=入口发布; publish_entry "$3" "$4"', str(profile), str(dest), str(target))
    assert result.returncode == 43
    assert "入口发布" in result.stderr
    assert "未回滚" in result.stderr
    assert profile.exists() and dest.is_symlink()
    assert old.read_bytes() == b"SYNTHETIC old executable"
    before = profile.read_bytes()
    retry = _run(tmp_path, 'source "$1"; publish_profile "$2"; publish_entry "$3" "$4"', str(profile), str(dest), str(target))
    assert retry.returncode == 0
    assert profile.read_bytes() == before
    assert not dest.is_symlink()


def test_shell_help_failure_is_not_success(tmp_path: Path) -> None:
    """真实正常 Bash 的外部默认命令 help 失败不能被解析成功掩盖。

    :param tmp_path: 隔离 HOME。
    :returns: None。
    :raises AssertionError: help 失败被当作安装成功。
    """
    dest = tmp_path / ".local/bin/dayu-cli"
    dest.parent.mkdir(parents=True)
    dest.write_text('#!/bin/bash\nprintf "SYNTHETIC help failure\\n" >&2\nexit 17\n', encoding="utf-8")
    dest.chmod(0o700)
    for name in (".bashrc", ".bash_profile"):
        assert _run(tmp_path, 'source "$1"; publish_profile "$2"', str(tmp_path / name)).returncode == 0
    result = _run(tmp_path, 'source "$1"; check_shell bash /bin/bash published "$2"', str(dest))
    assert result.returncode != 0
    assert "SYNTHETIC help failure" in result.stderr
    assert "安装完成。" not in result.stdout
