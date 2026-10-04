"""macOS 强制沙箱与显式运行库清单；仅依赖标准库和路径参数。"""

from __future__ import annotations

import ctypes
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_OTOOL = "/usr/bin/otool"
_INSPECTION_TIMEOUT_SECONDS = 10
_MAX_INSPECTED_BINARIES = 160
_LIBSANDBOX = "/usr/lib/libsandbox.dylib"
_MACOS_PLATFORM = "darwin"


class MacosSandboxError(RuntimeError):
    """策略生成、运行库检查或内核应用失败；无宽松回退。"""


@dataclass(frozen=True, slots=True)
class RuntimeReadFile:
    """同一实际运行库的声明别名、规范路径及字节摘要。"""

    declared_path: Path
    resolved_path: Path
    sha256: str


def inspect_macos_runtime_dependencies(executable_file: Path, python_base_root: Path) -> tuple[RuntimeReadFile, ...]:
    """参数：实际解释器和 Python 根；返回：有限运行库闭包；异常：检查未闭合抛沙箱错误。"""
    try:
        base = python_base_root.resolve(strict=True)
        executable = executable_file.resolve(strict=True)
        pending = [executable, base / "Python", *sorted((base / "lib/python3.11/lib-dynload").glob("*.so"))]
        visited: set[Path] = set()
        dependencies: dict[Path, RuntimeReadFile] = {}
        while pending:
            binary = pending.pop(0).resolve(strict=True)
            if binary in visited:
                continue
            if len(visited) >= _MAX_INSPECTED_BINARIES:
                raise MacosSandboxError("运行库检查超出已声明预算")
            visited.add(binary)
            result = subprocess.run([_OTOOL, "-L", str(binary)], capture_output=True, text=True, timeout=_INSPECTION_TIMEOUT_SECONDS, check=True)
            for line in result.stdout.splitlines()[1:]:
                library = line.strip().split(" (compatibility", 1)[0]
                if library.startswith(("/usr/lib/", "/System/Library/Frameworks/")):
                    # shared cache 的系统声明可能没有独立磁盘文件。
                    continue
                if library.startswith("@"):
                    if library.startswith("@loader_path/"):
                        resolved = (binary.parent / library.removeprefix("@loader_path/")).resolve(strict=True)
                        if not resolved.is_relative_to(base):
                            raise MacosSandboxError("运行库相对加载路径超出已批准 Python 根")
                    else:
                        raise MacosSandboxError("运行库 rpath 未能绑定到显式批准根")
                    continue
                alias = Path(library)
                if not alias.is_absolute():
                    raise MacosSandboxError("运行库加载路径未闭合")
                resolved = alias.resolve(strict=True)
                if resolved.is_relative_to(base):
                    continue
                digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
                if hashlib.sha256(alias.read_bytes()).hexdigest() != digest:
                    raise MacosSandboxError("运行库别名未绑定同一资源")
                dependencies[alias] = RuntimeReadFile(alias, resolved, digest)
                pending.append(resolved)
        return tuple(dependencies[path] for path in sorted(dependencies))
    except MacosSandboxError:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise MacosSandboxError("运行库检查失败") from exc


def _paths_with_aliases(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    """参数：显式路径；返回：原声明与规范路径；异常：非绝对路径抛沙箱错误。"""
    expanded: set[Path] = set()
    for path in paths:
        if not path.is_absolute() or ".." in path.parts:
            raise MacosSandboxError("沙箱路径必须显式绝对")
        expanded.update((path, path.resolve()))
    return tuple(sorted(expanded))


def build_macos_sandbox_profile(*, readonly_roots: tuple[Path, ...], readonly_files: tuple[Path, ...], writable_root: Path, executable_files: tuple[Path, ...], allow_existing_posix_semaphores: bool) -> str:
    """参数：精确读取/执行清单、独占写根、IPC 权限；返回：策略；异常：非法参数抛沙箱错误。"""
    if not isinstance(allow_existing_posix_semaphores, bool):
        raise MacosSandboxError("IPC 选择必须显式布尔")
    roots = _paths_with_aliases(readonly_roots)
    files = _paths_with_aliases(readonly_files)
    executables = _paths_with_aliases(executable_files)
    write_roots = _paths_with_aliases((writable_root,))
    if any(path == Path("/") for path in (*roots, *write_roots)):
        raise MacosSandboxError("不允许根目录子树权限")
    clauses = ["(version 1)", "(deny default)", "(allow process-fork)", "(allow sysctl-read)", "(allow mach-lookup)", "(allow signal)", '(allow file-read-data (literal "/"))']
    if allow_existing_posix_semaphores:
        clauses.append("(allow ipc-posix-sem)")
    for path in executables:
        clauses.append(f"(allow process-exec (literal {json.dumps(str(path))}))")
    for path in roots:
        clauses.append(f"(allow file-read* (subpath {json.dumps(str(path))}))")
    for path in (*files, *executables):
        clauses.append(f"(allow file-read* (literal {json.dumps(str(path))}))")
    ancestors = {ancestor for path in (*roots, *files, *executables, *write_roots) for ancestor in path.parents}
    for path in sorted(ancestors):
        clauses.append(f"(allow file-read-metadata (literal {json.dumps(str(path))}))")
    for path in write_roots:
        clauses.append(f"(allow file-read* file-write* (subpath {json.dumps(str(path))}))")
    clauses.append('(allow file-write* (literal "/dev/null"))')
    return "\n".join(clauses) + "\n"


def apply_macos_sandbox(profile: str) -> None:
    """参数：完整策略；返回：无；异常：平台/内核拒绝抛沙箱错误，释放原错误缓冲。"""
    if sys.platform != _MACOS_PLATFORM or not profile:
        raise MacosSandboxError("macOS 沙箱平台或策略不可用")
    try:
        library = ctypes.CDLL(_LIBSANDBOX)
        initialize = library.sandbox_init
        initialize.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_void_p)]
        initialize.restype = ctypes.c_int
        release = library.sandbox_free_error
        release.argtypes = [ctypes.c_void_p]
        release.restype = None
        error = ctypes.c_void_p()
        status = initialize(profile.encode("utf-8"), 0, ctypes.byref(error))
        try:
            if status != 0:
                message = ctypes.string_at(error.value).decode("utf-8", errors="replace") if error.value else "sandbox_init failed"
                raise MacosSandboxError(message)
        finally:
            if error.value:
                release(error)
    except OSError as exc:
        raise MacosSandboxError("macOS 沙箱库不可用") from exc
