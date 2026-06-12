# WU-RET-00 Slice 1 Implementation Artifact

## Work Unit / Gate / Slice

- work unit: WU-RET-00 Host Storage Lifecycle Retention Policy
- gate: implementation
- slice: Slice 1 — artifact 模块复用 helper（containment-guarded 文件枚举与删除）
- implementer: Codex

## Changed Files

- `dayu/host/durable/artifact.py`
- `tests/host/test_artifact_store.py`

## Implementation Summary

- 在 `dayu/host/durable/artifact.py` 新增 `iter_published_artifact_relative_paths(artifact_root: Path) -> Iterator[str]`。
  - 只从 `artifact_root/sha256/` namespace 递归枚举已发布 artifact 普通文件。
  - 跳过 `.tmp` 子树与 `audit/`、`tool-trace/`、其它非 `sha256/` namespace。
  - 对 symlink 逃逸、路径 containment 失败与文件系统枚举异常统一抛 `HostArtifactWriteError`。
  - 不读取 SQLite，不做 orphan 判定。
- 在 `dayu/host/durable/artifact.py` 新增 `delete_artifact_file(artifact_root: Path, relative_path: str) -> bool`。
  - 删除链路为 `_validate_relative_path_text` -> `_path_from_posix_relative` -> `_ensure_contained(root, final_path)` -> `unlink(missing_ok=True)`。
  - 对最终文件路径本身执行 containment 校验，避免只校验父目录导致 symlink 逃逸。
  - 文件存在且删除成功返回 `True`；文件不存在返回 `False`；IO 删除失败抛 `HostArtifactWriteError`。
- 更新 `tests/host/test_artifact_store.py`，覆盖：
  - published artifact 枚举只返回 `sha256/` 下普通文件。
  - 枚举跳过 `.tmp`、`audit/`、`tool-trace/` 和其它非 artifact namespace。
  - 空 root / `sha256` 不存在时返回空。
  - 删除存在文件、缺失文件返回 `False`。
  - 越界路径和 symlink 逃逸被拒绝。

## Validation Commands and Results

```bash
source .venv/bin/activate && pytest tests/host/test_artifact_store.py -q
```

Result:

```text
15 passed in 0.41s
```

```bash
source .venv/bin/activate && pyright dayu/host/durable/artifact.py tests/host/test_artifact_store.py
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Pyright additionally reported a version availability warning:

```text
WARNING: there is a new pyright version available (v1.1.409 -> v1.1.410).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`
```

## Docs Decision

本 slice 未新增 Host public API，未改变 Service-facing contract、Host package 公共契约或架构边界，因此 `dayu/host/README.md` 不更新。

本 slice 只在既有 `tests/host/test_artifact_store.py` 中补充覆盖，没有新增测试层级；现有 `tests/README.md` 命令清单已包含该测试文件，因此 `tests/README.md` 不更新。

后续 slice 会引入 storage lifecycle report / maintenance public surface，并会触发对应 README 文档更新判断与必要更新。

## Residual Risks / Uncovered Areas

- 本 slice 只提供 artifact 文件枚举与 containment-guarded 删除 helper，不读取 descriptor，不判断 artifact 是否 orphan。
- 删除证明、grace window、删除前 SQLite recheck、maintenance dry-run / reclaim 行为均留给后续 slice。
- 本 slice 不处理 SQLite payload orphan、WAL checkpoint、storage usage report 或 Host facade。

## Completion Status

Slice 1 implementation completed. 已停止在 Slice 1 边界内，未进入 review、未进入下一 slice，未 commit、未 push、未创建 PR。
