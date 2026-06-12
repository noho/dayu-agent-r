# WU-RET-00 Slice 1 Fix - AgentCodex

- work unit: WU-RET-00 Host Storage Lifecycle Retention Policy
- gate: fix
- slice: Slice 1 - artifact helper
- date: 2026-06-12
- design source: `docs/host/design.md`、`docs/engine/design.md`
- accepted plan: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`
- review sources:
  - `docs/reviews/wu-ret-00-slice1-code-review-mimo.md`
  - `docs/reviews/wu-ret-00-slice1-code-review-ds.md`

## 改动摘要

1. `dayu/host/durable/artifact.py`
   - 在 `delete_artifact_file` 完成基础 POSIX 相对路径文本校验后、生成最终文件路径前，增加 `sha256/` namespace 校验。
   - 新增私有 helper `_validate_published_artifact_relative_path(...)`，集中表达“已发布 artifact 文件必须位于 `sha256/` namespace 下”的语义。
   - 更新 `delete_artifact_file` 中文 docstring，明确该 helper 只删除 `sha256/` 内容寻址 namespace 下的已发布 artifact 文件。
   - 移除 `except FileNotFoundError: return False` 死代码分支；当前实现中 `_ensure_contained(...)` 会先把路径不存在类 `OSError` 包装为 `HostArtifactWriteError`，`Path.unlink(missing_ok=True)` 不会抛 `FileNotFoundError`。

2. `tests/host/test_artifact_store.py`
   - 新增 `test_delete_artifact_file_rejects_non_sha256_namespace_without_deleting`。
   - 覆盖合法但非 `sha256/` namespace 路径 `audit/audit.jsonl`：调用 `delete_artifact_file` 时抛 `HostArtifactWriteError`，且原 audit 文件内容保持未删除。

## Accepted Findings 对应关系

| Finding | 裁决 | Fix 结果 |
| --- | --- | --- |
| MiMo F1 / DS F1 | accepted blocking | 已修复。`delete_artifact_file` 自身拒绝不在 `sha256/` namespace 下的 relative path，不依赖 Slice 3/4 调用层保证。 |
| MiMo F2 / DS F3 | accepted test gap | 已补测试。新增用例直接覆盖 `audit/audit.jsonl`，确认抛 `HostArtifactWriteError` 且文件未删除。 |
| DS F2 | accepted cleanup if trivial | 已处理。移除当前实现中的 `FileNotFoundError` 死代码分支，未重构 `_ensure_contained`，未扩大并发语义。 |

## 验证命令与结果

```bash
source .venv/bin/activate && pytest tests/host/test_artifact_store.py -q
```

结果：

```text
16 passed in 0.27s
```

```bash
source .venv/bin/activate && pyright dayu/host/durable/artifact.py tests/host/test_artifact_store.py
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

pyright 同时提示有新版本可用：`v1.1.409 -> v1.1.410`。这不是本次代码错误。

## 未覆盖风险

- dangling symlink 额外测试按 controller 裁决 deferred，本次未处理。
- `lexists` / containment / unlink 之间的 TOCTOU 更精确并发语义按 controller 裁决 deferred，本次未重构。
- Slice 3/4 maintenance 调用层 orphan 判定、删除前 recheck、grace window 等逻辑不属于本 fix gate，本次未处理。
- 按本次 allowed files 限制，未修改 README 或 control doc。
