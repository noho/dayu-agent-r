# WU-RET-00 Slice 1 Code Review — AgentMiMo

## Work Unit / Gate / Slice

- work unit: WU-RET-00 Host Storage Lifecycle Retention Policy
- gate: code-review
- slice: Slice 1 — artifact 模块复用 helper（containment-guarded 文件枚举与删除）
- reviewer: AgentMiMo

## Review Target

- `dayu/host/durable/artifact.py`（新增 `iter_published_artifact_relative_paths`、`delete_artifact_file`）
- `tests/host/test_artifact_store.py`（新增 4 个测试覆盖枚举与删除）

## Design Source

- `docs/host/design.md` §13.1 Payload 存储
- `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md` §8 Slice 1

## Verified Evidence

- `pytest tests/host/test_artifact_store.py -q` => 15 passed
- `pyright dayu/host/durable/artifact.py tests/host/test_artifact_store.py` => 0 errors, 0 warnings, 0 informations

---

## Findings

### F1 — `delete_artifact_file` 不拒绝非 `sha256/` namespace 相对路径

**Severity**: blocking
**File/Line**: `dayu/host/durable/artifact.py:167-196` (`delete_artifact_file`)
**Status 建议**: needs-fix

**问题**：plan §8 Slice 1 invariants 明确要求"绝不返回/删除 `.tmp`、非 `sha256/` namespace 文件或 root 外路径"。`iter_published_artifact_relative_paths` 正确地只枚举 `sha256/` namespace，但 `delete_artifact_file` 对输入 `relative_path` 仅做 `_validate_relative_path_text`（空值、null byte、绝对路径、目录穿越）校验，不检查路径是否以 `sha256/` 开头。

因此调用方可以直接传入 `audit/host-audit.jsonl`、`tool-trace/tool-trace-cold.jsonl` 或其它非 `sha256/` namespace 的相对路径，`delete_artifact_file` 会正常删除该文件。虽然 Slice 4 的 `reclaim_orphan_artifact_files` 计划从 `iter_published_artifact_relative_paths` 取候选（已限定 sha256），但 `delete_artifact_file` 是公共 helper，其自身应满足 plan 声明的 invariant，而非依赖调用层保证。

**建议**：在 `delete_artifact_file` 中增加 namespace 校验：

```python
def delete_artifact_file(artifact_root: Path, relative_path: str) -> bool:
    ...
    _validate_relative_path_text(relative_path)
    if not relative_path.startswith(f"{_ARTIFACT_NAMESPACE}/"):
        raise HostArtifactWriteError(
            "Artifact relative path must be under sha256/ namespace"
        )
    ...
```

不建议修改 `_validate_relative_path_text`，因为该函数被 `write_artifact_bytes` 路径复用，而写入路径由 `_artifact_relative_path_for_digest` 生成，天然满足 sha256 前缀。

---

### F2 — `test_delete_artifact_file_rejects_traversal_and_symlink_escape` 未覆盖非 sha256 路径拒绝

**Severity**: non-blocking（测试缺口，不影响当前通过的测试，但 F1 修复后需补测）
**File/Line**: `tests/host/test_artifact_store.py:250-269`
**Status 建议**: accepted

**问题**：该测试覆盖了 `../outside/artifact`（目录穿越）和 `sha256/ab/escape`（symlink 逃逸）两种拒绝场景，但没有测试直接传入 `audit/some-file.jsonl` 等非 `sha256/` namespace 路径的拒绝行为。F1 修复后应补一个断言：

```python
with pytest.raises(HostArtifactWriteError):
    delete_artifact_file(artifact_root, "audit/some-file.jsonl")
```

---

### F3 — `_ensure_contained` 的 `resolve(strict=True)` 行为正确，无 blocking 问题

**Severity**: info
**File/Line**: `dayu/host/durable/artifact.py:335-349` (`_ensure_contained`)
**Status 建议**: accepted

**分析**：
- `resolve(strict=True)` 对不存在的路径（含 dangling symlink target）抛 `OSError`，被 `_ensure_contained` 捕获并转为 `HostArtifactWriteError("Artifact path escapes artifact root")`。
- 对正常路径，`resolve(strict=True)` 会解析全部 symlink 并返回绝对路径；`relative_to` 校验确保解析后路径仍在 root 内。
- `delete_artifact_file` 中 `lexists` 在 `_ensure_contained` 之前调用：若文件是 dangling symlink，`lexists=True` → `_ensure_contained` 的 `resolve(strict=True)` 抛 `OSError` → `HostArtifactWriteError`。正确。
- `delete_artifact_file` 中 `lexists` 与 `unlink` 之间存在极短 TOCTOU 窗口（另一个进程可能在 `lexists` 之后删除文件），但 `unlink(missing_ok=True)` 保证不抛 `FileNotFoundError`。plan §7.3 已将此标记为 residual R1，grace + recheck + content-addressed 可重写性将其降至可接受范围。

---

### F4 — `iter_published_artifact_relative_paths` generator early return 行为正确

**Severity**: info
**File/Line**: `dayu/host/durable/artifact.py:136-164`
**Status 建议**: accepted

**分析**：函数为 generator（含 `yield from`）。当 `artifact_root` 不存在或 `namespace_dir` 不存在时，显式 `return` 使 generator 立即终止，caller 收到空迭代器。`_iter_contained_regular_files` 内部对 `.tmp` 子目录用 `continue` 跳过（不递归、不 yield），对非 symlink 目录递归、对非 symlink 普通文件 yield 相对路径。行为符合 plan 要求。

---

### F5 — OSError handling 保留 root cause chain

**Severity**: info
**File/Line**: 多处
**Status 建议**: accepted

**分析**：
- `iter_published_artifact_relative_paths:161` — `raise HostArtifactWriteError("Artifact file enumeration failed") from exc`
- `delete_artifact_file:196` — `raise HostArtifactWriteError("Artifact file delete failed") from exc`
- `_iter_contained_regular_files:312` — `raise HostArtifactWriteError("Artifact file enumeration failed") from exc`

所有 OSError 包装均使用 `from exc` 保留 exception chain，`HostArtifactWriteError.__cause__` 指向原始 OSError。不丢失 root cause。

---

### F6 — 测试覆盖主要安全边界与失败模式

**Severity**: info
**File/Line**: `tests/host/test_artifact_store.py:173-269`
**Status 建议**: accepted

**覆盖矩阵**：

| 场景 | 测试 | 状态 |
|---|---|---|
| 枚举只返回 sha256 下文件 | `test_iter_published...returns_only_sha256_files` | ✅ |
| 跳过 .tmp / audit / tool-trace / other | 同上 | ✅ |
| 空 root / sha256 缺失 | `test_iter...empty_without_sha256` | ✅ |
| sha256 内 symlink 逃逸 | `test_iter...rejects_symlink_escape` | ✅ |
| 删除存在文件 + 缺失返回 False | `test_delete...deletes_existing_and_reports_missing` | ✅ |
| 目录穿越拒绝 | `test_delete...rejects_traversal_and_symlink_escape` | ✅ |
| symlink 逃逸拒绝 | 同上 | ✅ |
| 非 sha256 路径拒绝 | **缺失**（F1/F2） | ❌ |
| dangling symlink in sha256 | **缺失**（建议补充） | ❌ |

---

### F7 — AGENTS.md 合规检查

**Severity**: info
**Status 建议**: accepted

| 检查项 | 状态 |
|---|---|
| 中文 docstring | ✅ 全部函数 / 类 / 模块均有中文 docstring |
| 严格类型签名 | ✅ 无 `Any`、`object`、无类型参数或返回值 |
| 无无理由 `getattr`/`hasattr` | ✅ |
| 无兼容性 facade | ✅ 新函数为新增，不透传旧接口 |
| 魔法数字/字符串 | ✅ 常量已命名：`_ARTIFACT_NAMESPACE`、`_ARTIFACT_TEMP_DIR_NAME`、`_DIGEST_SHARD_LENGTH` |

---

## Conclusion

**FAIL** — 存在 1 个 blocking finding（F1）：`delete_artifact_file` 不拒绝非 `sha256/` namespace 相对路径，违反 plan §8 Slice 1 invariants。修复范围极小（单函数增加一行 namespace 校验 + 补一个测试断言），不影响 Slice 1 的整体设计正确性。

**Blocking findings**: 1（F1）
**Non-blocking findings**: 1（F2，F1 的测试缺口）
**Info findings**: 5（F3–F7）

**建议**：修复 F1 + 补 F2 测试后可直接进入 accepted slice commit，无需重新 review。
