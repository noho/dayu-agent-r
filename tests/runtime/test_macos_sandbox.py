"""中立策略及运行库清单合同，不在 pytest 父进程施加不可逆策略。"""
from __future__ import annotations
import ast
import ctypes
import hashlib
from pathlib import Path
import subprocess
import sys
import pytest
from dayu.runtime import macos_sandbox as sandbox

def test_profile_exact_permissions_and_aliases(tmp_path: Path) -> None:
    """参数：独占根；返回：无；异常：策略扩大或未绑定别名时断言失败。"""
    runtime=tmp_path/'runtime'; runtime.mkdir(); alias=tmp_path/'alias'; alias.symlink_to(runtime,target_is_directory=True)
    profile=sandbox.build_macos_sandbox_profile(readonly_roots=(alias,),readonly_files=(runtime/'lib.dylib',),writable_root=tmp_path/'work',executable_files=(runtime/'python',),allow_existing_posix_semaphores=True)
    assert '(deny default)' in profile and '(allow ipc-posix-sem)' in profile
    assert 'network' not in profile and 'ipc-posix-shm' not in profile and '(allow default)' not in profile
    assert '(allow file-read-data (literal "/"))' in profile
    assert '(subpath "/")' not in profile
    assert f'(allow file-read* (subpath "{alias}"))' in profile
    assert f'(allow file-read* (subpath "{runtime}"))' in profile
    assert f'(allow file-read-metadata (literal "{tmp_path}"))' in profile
    assert f'(allow file-read* (subpath "{tmp_path}"))' not in profile
    no_ipc=sandbox.build_macos_sandbox_profile(readonly_roots=(),readonly_files=(),writable_root=tmp_path/'work',executable_files=(),allow_existing_posix_semaphores=False)
    assert 'ipc' not in no_ipc

@pytest.mark.parametrize('path',[Path('/'),Path('relative'),Path('/tmp/../private')])
def test_invalid_policy_path_rejected(tmp_path: Path, path: Path) -> None:
    """参数：非法路径；返回：无；异常：未拒绝路径时断言失败。"""
    with pytest.raises(sandbox.MacosSandboxError): sandbox.build_macos_sandbox_profile(readonly_roots=(path,),readonly_files=(),writable_root=tmp_path/'work',executable_files=(),allow_existing_posix_semaphores=False)

def _runtime_seed(tmp_path: Path) -> tuple[Path,Path]:
    """参数：根；返回：合成运行库边界；异常：IO 错误透传。"""
    base=tmp_path/'python'; base.mkdir(); executable=base/'Python'; executable.write_bytes(b'synthetic-runtime'); return base,executable

def test_inventory_actual_alias_and_recursion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：根与定向命令替身；返回：无；异常：清单没绑定实际 bytes 时断言失败。"""
    base,executable=_runtime_seed(tmp_path); library=tmp_path/'external.dylib'; library.write_bytes(b'actual-file'); alias=tmp_path/'alias.dylib'; alias.symlink_to(library)
    outputs=[f'{executable}:\n {alias} (compatibility version 1)\n /usr/lib/libSystem.B.dylib (compatibility version 1)\n',f'{library}:\n /System/Library/Frameworks/System.framework/System (compatibility version 1)\n']
    def run(argv: list[str], *, capture_output: bool, text: bool, timeout: int, check: bool) -> subprocess.CompletedProcess[str]:
        """参数：实际命令参数；返回：合成 otool 输出；异常：不符合预算时断言失败。"""
        assert argv[:2]==['/usr/bin/otool','-L'] and timeout==10 and capture_output and text and check
        return subprocess.CompletedProcess(argv,0,outputs.pop(0),'')
    monkeypatch.setattr(sandbox.subprocess,'run',run)
    result=sandbox.inspect_macos_runtime_dependencies(executable,base)
    assert result==(sandbox.RuntimeReadFile(alias,library,hashlib.sha256(b'actual-file').hexdigest()),)

@pytest.mark.parametrize('dependency',['@rpath/unknown','relative','@loader_path/../external','/missing/library.dylib'])
def test_inventory_fails_closed_for_unbound_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dependency: str) -> None:
    """参数：未闭合路径；返回：无；异常：不拒绝未知加载路径时断言失败。"""
    base,executable=_runtime_seed(tmp_path)
    def run(argv: list[str], *, capture_output: bool, text: bool, timeout: int, check: bool) -> subprocess.CompletedProcess[str]:
        """参数：检查 argv；返回：合成未闭合加载声明；异常：无。"""
        return subprocess.CompletedProcess(argv,0,f'{executable}:\n {dependency} (compatibility version 1)\n','')
    monkeypatch.setattr(sandbox.subprocess,'run',run)
    with pytest.raises(sandbox.MacosSandboxError): sandbox.inspect_macos_runtime_dependencies(executable,base)

def test_apply_wrong_platform_and_empty_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：平台替身；返回：无；异常：允许未部署平台时断言失败。"""
    monkeypatch.setattr(sys,'platform','linux')
    with pytest.raises(sandbox.MacosSandboxError): sandbox.apply_macos_sandbox('(deny default)')
    monkeypatch.setattr(sys,'platform','darwin')
    with pytest.raises(sandbox.MacosSandboxError): sandbox.apply_macos_sandbox('')

def test_runtime_never_imports_business_layers() -> None:
    """参数：无；返回：无；异常：新增反向 import 时断言失败。"""
    tree=ast.parse(Path(sandbox.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom) and node.module:
            assert not node.module.startswith(('dayu.engine','dayu.host','dayu.service','dayu.ui','dayu.fins','dayu.documents'))


def test_native_library_missing_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：库加载替身；返回：无；异常：库缺失未闭合映射时断言失败。"""
    def missing(name: str) -> ctypes.CDLL:
        """参数：精确库名；返回：无；异常：模拟动态加载失败。"""
        assert name=='/usr/lib/libsandbox.dylib'
        raise OSError('synthetic missing library')
    monkeypatch.setattr(sys,'platform','darwin'); monkeypatch.setattr(sandbox.ctypes,'CDLL',missing)
    with pytest.raises(sandbox.MacosSandboxError) as error: sandbox.apply_macos_sandbox('(deny default)')
    assert isinstance(error.value.__cause__,OSError)


def test_inventory_loader_within_runtime_and_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：根及有限预算；返回：无；异常：相对内根或预算行为错误时断言失败。"""
    base,executable=_runtime_seed(tmp_path)
    def run(argv: list[str], *, capture_output: bool, text: bool, timeout: int, check: bool) -> subprocess.CompletedProcess[str]:
        """参数：运行库命令；返回：合成同根 alias；异常：无。"""
        return subprocess.CompletedProcess(argv,0,f'{executable}:\n @loader_path/Python (compatibility version 1)\n {executable} (compatibility version 1)\n','')
    monkeypatch.setattr(sandbox.subprocess,'run',run)
    assert sandbox.inspect_macos_runtime_dependencies(executable,base)==()
    monkeypatch.setattr(sandbox,'_MAX_INSPECTED_BINARIES',0)
    with pytest.raises(sandbox.MacosSandboxError): sandbox.inspect_macos_runtime_dependencies(executable,base)
