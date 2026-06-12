# WU-RET-00 Slice 1 Re-Review — AgentMiMo

- work unit: WU-RET-00 Host Storage Lifecycle Retention Policy
- gate: re-review
- slice: Slice 1 — artifact helper
- reviewer: AgentMiMo
- date: 2026-06-12

## Review Target

- `dayu/host/durable/artifact.py`
- `tests/host/test_artifact_store.py`

## Review Sources

- Original review: `docs/reviews/wu-ret-00-slice1-code-review-mimo.md`
- Original review: `docs/reviews/wu-ret-00-slice1-code-review-ds.md`
- Fix report: `docs/reviews/wu-ret-00-slice1-fix-codex.md`
- Accepted plan: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`

## Verified Evidence

- `pytest tests/host/test_artifact_store.py -q` → 16 passed（controller independently verified）
- `pyright dayu/host/durable/artifact.py tests/host/test_artifact_store.py` → 0 errors（controller independently verified）

---

## Accepted Findings Verification

### 1. MiMo F1 / DS F1 — `delete_artifact_file` 必须拒绝非 `sha256/` namespace relative_path

**Verify status: fixed**

**实现**：

新增私有 helper `_validate_published_artifact_relative_path`（`artifact.py:252-264`），在 `delete_artifact_file` 的 `_validate_relative_path_text` 之后、`_path_from_posix_relative` 之前调用（`artifact.py:183`）。

**namespace 校验方式审查**：

```python
def _validate_published_artifact_relative_path(relative_path: str) -> None:
    path = PurePosixPath(relative_path)
    if len(path.parts) < 2 or path.parts[0] != _ARTIFACT_NAMESPACE:
        raise HostArtifactWriteError(
            "Artifact relative path must be under sha256 namespace"
        )
```

使用 `PurePosixPath.parts` 做结构化校验，不是脆弱字符串前缀：

| 输入 | `parts` | `len < 2` | `parts[0] != "sha256"` | 结果 |
|---|---|---|---|---|
| `"audit/audit.jsonl"` | `("audit", "audit.jsonl")` | False | True → raise | ✅ 拒绝 |
| `"sha256/ab/file"` | `("sha256", "ab", "file")` | False | False | ✅ 通过 |
| `"sha256"` | `("sha256",)` | True → raise | — | ✅ 拒绝 |
| `"sha256ish/foo"` | `("sha256ish", "foo")` | False | True → raise | ✅ 拒绝 |
| `"tool-trace/trace.jsonl"` | `("tool-trace", "trace.jsonl")` | False | True → raise | ✅ 拒绝 |

`len(path.parts) < 2` 条件确保单段路径 `"sha256"` 也被拒绝（必须有至少两段：namespace + 子路径）。`path.parts[0] != _ARTIFACT_NAMESPACE` 精确匹配首段，不存在 `"sha256ish"` 类误通过。

**类型 / docstring / 异常合规**：

- 函数签名 `_validate_published_artifact_relative_path(relative_path: str) -> None`：严格类型，无 `Any`/`object`。✅
- 完整中文 docstring，含参数、返回值、异常说明。✅
- 异常：`HostDurableError` → 在 `delete_artifact_file` 中被 `except HostDurableError as exc: raise HostArtifactWriteError(...) from exc` 包装，保留 exception chain。✅
- 非过度设计：单 helper、单调用点、聚焦单一语义。✅

---

### 2. MiMo F2 / DS F3 — 测试必须覆盖合法但非 `sha256/` namespace 路径

**Verify status: fixed**

**新增测试**：`test_delete_artifact_file_rejects_non_sha256_namespace_without_deleting`（`test_artifact_store.py:250-263`）。

**审查**：

```python
def test_delete_artifact_file_rejects_non_sha256_namespace_without_deleting(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    audit_file = artifact_root / "audit" / "audit.jsonl"
    audit_file.parent.mkdir(parents=True)
    audit_file.write_text("{}", encoding="utf-8")

    with pytest.raises(HostArtifactWriteError):
        delete_artifact_file(artifact_root, "audit/audit.jsonl")

    assert audit_file.read_text(encoding="utf-8") == "{}"
```

- 路径 `"audit/audit.jsonl"` 是合法 POSIX 相对路径，但不在 `sha256/` namespace 下。✅
- 断言抛出 `HostArtifactWriteError`。✅
- 断言文件内容未被删除（`"{}"` 保持不变）。✅
- 测试粒度恰当：一个 case 覆盖"拒绝 + 不删除"两个语义。✅

---

### 3. DS F2 — 移除 `FileNotFoundError` 死代码，确认缺失文件返回 False 行为不变

**Verify status: fixed**

**原实现**（已被移除）：

```python
except FileNotFoundError:
    return False
```

DS review 已确认这是死代码：`_ensure_contained` 的 `except (OSError, ValueError)` 已将 `FileNotFoundError` 包装为 `HostArtifactWriteError`；`Path.unlink(missing_ok=True)` 不抛 `FileNotFoundError`。

**新实现**：

```python
if not os.path.lexists(final_path):
    return False
_ensure_contained(artifact_root, final_path)
final_path.unlink(missing_ok=True)
return True
```

**行为一致性审查**：

| 场景 | 原行为 | 新行为 | 一致 |
|---|---|---|---|
| 文件不存在（从未创建） | `lexists` → False → `return False` | `lexists` → False → `return False` | ✅ |
| 文件存在后被删除 | `lexists` → True → `_ensure_contained` → `resolve(strict=True)` → `FileNotFoundError` → `HostArtifactWriteError` | `lexists` → True → `_ensure_contained` → `resolve(strict=True)` → `OSError` → `HostArtifactWriteError` | ✅ 行为一致（抛错而非 return False） |
| TOCTOU：lexists 后文件被删 | N/A（原死代码不触发） | `lexists` → True → `_ensure_contained` 抛错 或 `unlink(missing_ok=True)` 不抛 | ✅ `missing_ok=True` 兜底 |

**测试覆盖确认**：

`test_delete_artifact_file_deletes_existing_file_and_reports_missing`（`test_artifact_store.py:234-247`）仍覆盖：

```python
assert delete_artifact_file(artifact_root, "sha256/ab/artifact") is True   # 存在 → 删除
assert artifact_path.exists() is False                                       # 已删
assert delete_artifact_file(artifact_root, "sha256/ab/artifact") is False   # 再删 → False
assert delete_artifact_file(artifact_root, "sha256/ab/missing") is False    # 从未存在 → False
```

缺失 sha256 文件返回 `False` 的行为完整保留。✅

---

## Regression Check

| 检查项 | 状态 |
|---|---|
| 现有 15 个测试全部通过（fix 前为 15 passed） | ✅ 16 passed（+1 新增） |
| `validate_artifact_ref` 行为未变 | ✅ 未修改 |
| `iter_published_artifact_relative_paths` 行为未变 | ✅ 未修改 |
| `write_artifact_bytes` 行为未变 | ✅ 未修改 |
| `_validate_relative_path_text` 行为未变 | ✅ 未修改 |
| `_ensure_contained` 行为未变 | ✅ 未修改 |
| pyright 干净 | ✅ 0 errors |

## Overdesign / Boundary Check

| 检查项 | 状态 |
|---|---|
| `_validate_published_artifact_relative_path` 是否过度设计 | ✅ 否：单函数、单语义、单调用点 |
| 是否越过 Slice 1 边界（不做 descriptor 读取、不做 orphan 判定） | ✅ 未越界 |
| 是否引入不必要的依赖 | ✅ 无新 import |
| 是否修改已有函数签名或语义 | ✅ 无 |

---

## Conclusion

**PASS** — 全部 3 个 accepted finding 已正确修复，无 blocking regression，无过度设计，无越界。

### Accepted Findings Summary

| Finding | 来源 | Verify Status |
|---|---|---|
| F1 — `delete_artifact_file` 拒绝非 sha256 namespace 路径 | MiMo F1 / DS F1 | **fixed** |
| F2 — 测试覆盖非 sha256 路径拒绝 + 不删除 | MiMo F2 / DS F3 | **fixed** |
| F3 — FileNotFoundError 死代码移除，缺失文件行为不变 | DS F2 | **fixed** |

**Blocking findings**: 0
**Regressions**: 0
