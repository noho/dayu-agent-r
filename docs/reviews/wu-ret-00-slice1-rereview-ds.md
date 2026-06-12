# WU-RET-00 Slice 1 Fix Re-Review — AgentDS

- work unit: WU-RET-00 Host Storage Lifecycle Retention Policy
- gate: re-review
- slice: Slice 1 — artifact 模块复用 helper
- reviewer: AgentDS
- date: 2026-06-12
- review targets:
  - `dayu/host/durable/artifact.py`
  - `tests/host/test_artifact_store.py`
- design source: `docs/host/design.md`、`docs/engine/design.md`
- accepted plan: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`
- original reviews:
  - `docs/reviews/wu-ret-00-slice1-code-review-mimo.md`
  - `docs/reviews/wu-ret-00-slice1-code-review-ds.md`
- fix report: `docs/reviews/wu-ret-00-slice1-fix-codex.md`

---

## 1. Re-Review Scope

本 re-review 只验证 accepted findings 的修复是否到位、是否引入回归、是否越过 Slice 1 边界。不重新审查原始 review 已确认通过的部分，不对实现做任何修改。

Accepted findings 共 3 条：

| ID | Origin | 简述 |
|----|--------|------|
| MiMo F1 / DS F1 | MiMo blocking + DS Low | `delete_artifact_file` 不校验 `sha256/` namespace |
| MiMo F2 / DS F3 | MiMo non-blocking + DS Note | 测试缺口：非 `sha256/` namespace 路径无覆盖 |
| DS F2 | DS Note | `except FileNotFoundError` 死代码 |

---

## 2. Independent Verification

Controller 提供了 Codex 的验证结果。AgentDS 独立重新执行：

```bash
source .venv/bin/activate && pytest tests/host/test_artifact_store.py -q
# => 16 passed in 0.27s

source .venv/bin/activate && pyright dayu/host/durable/artifact.py tests/host/test_artifact_store.py
# => 0 errors, 0 warnings, 0 informations
```

与 fix report 一致。

---

## 3. Finding-by-Finding Verification

### 3.1 MiMo F1 / DS F1 — `delete_artifact_file` namespace 校验

**Fix**: 新增私有函数 `_validate_published_artifact_relative_path`（`artifact.py:252-264`），在 `delete_artifact_file` 中基础文本校验后、路径构造前调用（`artifact.py:183`）。同时更新 `delete_artifact_file` docstring 明确"只删除 `sha256/` 内容寻址 namespace 下的已发布 artifact 文件"。

#### a) 类型签名与 docstring 合规

```python
def _validate_published_artifact_relative_path(relative_path: str) -> None:
    """校验相对路径位于已发布 artifact 的 ``sha256/`` namespace 下。

    :param relative_path: 已通过基础文本校验的 artifact 相对路径。
    :returns: ``None``。
    :raises HostArtifactWriteError: 路径不在 ``sha256/`` namespace 下时抛出。
    """
```

- 参数类型 `str`，返回类型 `None`：严格，无 `Any`/`object`。✅
- `:raises` 声明异常类型与触发条件。✅
- 中文 docstring 完整，参数说明清晰（注明"已通过基础文本校验"表明调用顺序）。✅
- 异常类型 `HostArtifactWriteError` 由 `errors.py:128` 定义，继承自 `HostDurableError`，与模块内其他校验函数的异常类型一致。✅

#### b) namespace 校验使用 path parts，不是脆弱字符串前缀

```python
path = PurePosixPath(relative_path)
if len(path.parts) < 2 or path.parts[0] != _ARTIFACT_NAMESPACE:
    raise HostArtifactWriteError(
        "Artifact relative path must be under sha256 namespace"
    )
```

使用 `PurePosixPath(relative_path).parts` 按 POSIX 路径段拆分，比较第一段与常量 `_ARTIFACT_NAMESPACE = "sha256"`。这是结构性校验，不是 `str.startswith("sha256/")` 或 `str.startswith("sha256")`。✅

**Adversarial 边界推演**：

| 输入 | `PurePosixPath.parts` | `len < 2` | `parts[0] != "sha256"` | 结果 |
|------|----------------------|-----------|------------------------|------|
| `"sha256/ab/file"` | `("sha256", "ab", "file")` | False | False | **通过** ✅ |
| `"sha256ish/foo"` | `("sha256ish", "foo")` | False | `"sha256ish" != "sha256"` → True | **拒绝** ✅ |
| `"sha256"` | `("sha256",)` | True | — | **拒绝** ✅ |
| `"sha256/"` | `("sha256",)` | True | — | **拒绝** ✅ |
| `"audit/audit.jsonl"` | `("audit", "audit.jsonl")` | False | `"audit" != "sha256"` → True | **拒绝** ✅ |
| `"tool-trace/trace.jsonl"` | `("tool-trace", "trace.jsonl")` | False | `"tool-trace" != "sha256"` → True | **拒绝** ✅ |
| `"sha256/ab/missing"` | `("sha256", "ab", "missing")` | False | False | **通过** ✅（后续由 `lexists` → `return False` 处理） |

`sha256ish/foo`（前缀匹配但不等于 `sha256`）和 `sha256`（单段路径）均被正确拒绝。✅

#### c) 异常包装诊断精度观察

`delete_artifact_file` 的异常处理结构为：

```python
try:
    _validate_relative_path_text(relative_path)                # raises HostDurableError
    _validate_published_artifact_relative_path(relative_path)  # raises HostArtifactWriteError
    final_path = _path_from_posix_relative(artifact_root, relative_path)
except HostDurableError as exc:
    raise HostArtifactWriteError("Artifact relative path invalid") from exc
```

`HostArtifactWriteError` 继承自 `HostDurableError`（`errors.py:128`）。当 `_validate_published_artifact_relative_path` 抛出 `HostArtifactWriteError("Artifact relative path must be under sha256 namespace")` 时，`except HostDurableError` 会捕获它并重新包装为 `HostArtifactWriteError("Artifact relative path invalid")`，原始消息进入 `__cause__` 链。

**影响评估**：
- 异常类型保持 `HostArtifactWriteError`，调用方按类型 catch 不受影响。✅
- `__cause__` 保留原始异常链，完整诊断信息可通过 `exc.__cause__` 获取。✅
- 但直接 `str(exc)` 看到的是泛化的 "Artifact relative path invalid" 而非 "must be under sha256 namespace"。

**结论**：这是诊断精度的小幅损失，不影响功能正确性或安全性。不属于 blocking regression。建议在后续 cleanup 中考虑 `except HostDurableError` 前增加 `if isinstance(exc, HostArtifactWriteError): raise` 守卫以保留原始消息。此观察不影响本 finding 的 verify status。

#### d) Verdict: **fixed** ✅

Namespace 校验已到位，使用结构性 path parts 比较，拒绝所有边界上的非 `sha256/` 路径，异常类型正确，docstring 合规。

---

### 3.2 MiMo F2 / DS F3 — 非 `sha256/` namespace 路径测试覆盖

**Fix**: 新增测试 `test_delete_artifact_file_rejects_non_sha256_namespace_without_deleting`（`test_artifact_store.py:250-263`）。

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

逐项验证：

- **合法但非 `sha256/` namespace 路径**：`audit/audit.jsonl` — 路径在 artifact root 内、无目录穿越、无 null byte、非 temp，完全合法，但不属于 `sha256/` namespace。✅
- **确认抛异常**：`pytest.raises(HostArtifactWriteError)` 捕获。✅
- **确认文件未删除**：`assert audit_file.read_text(encoding="utf-8") == "{}"` — 文件内容保持。✅
- **Docstring 语义明确**："拒绝非 sha256 namespace 路径且不删除对应文件"。✅

#### Verdict: **fixed** ✅

测试直接覆盖了 MiMo F2 提议的 `audit/some-file.jsonl` 场景，并额外验证了文件未被删除的完整性断言。测试 count 从 15 → 16。

---

### 3.3 DS F2 — `except FileNotFoundError` 死代码移除

**Fix**: 从 `delete_artifact_file` 移除 `except FileNotFoundError: return False` 分支。

**当前代码**（`artifact.py:188-197`）：

```python
    try:
        if not os.path.lexists(final_path):
            return False
        _ensure_contained(artifact_root, final_path)
        final_path.unlink(missing_ok=True)
        return True
    except HostArtifactWriteError:
        raise
    except OSError as exc:
        raise HostArtifactWriteError("Artifact file delete failed") from exc
```

对比 fix 前的代码（DS F2 引用）：

```python
    except HostArtifactWriteError:
        raise
    except FileNotFoundError:        # ← 已移除
        return False
    except OSError as exc:
        raise HostArtifactWriteError("Artifact file delete failed") from exc
```

逐项验证：

- **死代码已移除**：`except FileNotFoundError: return False` 不再存在。✅
- **缺失 sha256 文件返回 False 的行为未改变**：
  - 路径：`delete_artifact_file(artifact_root, "sha256/ab/missing")`
  - 经过 `_validate_relative_path_text` → `_validate_published_artifact_relative_path` → `_path_from_posix_relative`
  - 到达 `os.path.lexists(final_path)` → 返回 `False` → `return False`
  - 不经过 `_ensure_contained`，不经过 `unlink`。✅
- **测试覆盖仍然存在**：`test_delete_artifact_file_deletes_existing_file_and_reports_missing` 第 247 行：
  ```python
  assert delete_artifact_file(artifact_root, "sha256/ab/missing") is False
  ```
  ✅
- **DS F2 原始分析中 `_ensure_contained` 会拦截 `FileNotFoundError` 的推理仍然成立**：如果文件在 `lexists` 与 `_ensure_contained` 之间被并发删除，`_ensure_contained` 内部 `candidate.resolve(strict=True)` 抛出 `FileNotFoundError` → 被 `except (OSError, ValueError)` 捕获 → 转为 `HostArtifactWriteError("Artifact path escapes artifact root")`。该并发窗口已在 DS F5/F6 中记录为已知残余风险，不因死代码移除而改变。✅

#### Verdict: **fixed** ✅

死代码已移除，缺失 sha256 文件返回 `False` 的行为由 `lexists` 守卫保证，测试覆盖持续。

---

## 4. Slice 1 边界合规检查

| 检查项 | 结论 |
|--------|------|
| 不引入 SQLite 读取 | ✅ `_validate_published_artifact_relative_path` 纯路径运算 |
| 不做 orphan 判定 | ✅ 无 descriptor 读取、无引用计数 |
| 不做 descriptor/payload 关联 | ✅ 不 import payload.py |
| 不做 usage report | ✅ 无 COUNT 查询 |
| 不修改 `write_artifact_bytes` 路径 | ✅ 校验函数专用于 `delete_artifact_file` |
| 不新增环境变量或 cwd 依赖 | ✅ artifact root 仍由调用方显式注入 |

## 5. 过度设计检查

| 检查项 | 结论 |
|--------|------|
| `_validate_published_artifact_relative_path` 职责单一 | ✅ 只校验 namespace，不混合路径文本/空字节/越界校验 |
| 函数命名与模块风格一致 | ✅ 符合 `_validate_*` 前缀约定，与 `_validate_relative_path_text` 对称 |
| 未引入新依赖或 import | ✅ 使用已有的 `PurePosixPath`、`_ARTIFACT_NAMESPACE` |
| 未抽象为可配置策略 | ✅ 当前只有 `sha256` 一个 artifact namespace，不需要泛化 |
| 未修改公共 API 签名 | ✅ `delete_artifact_file` 签名不变 |

**结论**：fix 范围最小化，无过度设计，未越过 Slice 1 边界。

---

## 6. Accepted Findings Verify Status

| Finding | Severity | Status | 证据 |
|---------|----------|--------|------|
| MiMo F1 / DS F1 | blocking (MiMo) / Low (DS) | **fixed** | `_validate_published_artifact_relative_path` 使用 path parts 校验 namespace，拒绝 `sha256ish/foo`、`sha256`、`audit/...` 等边界输入 |
| MiMo F2 / DS F3 | non-blocking (MiMo) / Note (DS) | **fixed** | 新测试 `test_delete_artifact_file_rejects_non_sha256_namespace_without_deleting` 覆盖 `audit/audit.jsonl` 拒绝 + 文件保全 |
| DS F2 | Note | **fixed** | `except FileNotFoundError` 死代码移除；`sha256/ab/missing → False` 由 `lexists` 守卫保持，测试持续覆盖 |

无 `not-fixed`、`regressed`、`needs-more-evidence` 项。

---

## 7. Conclusion

### 7.1 Verdict: **PASS**

所有 3 条 accepted findings 均已正确修复。无 blocking regression，无过度设计，未越过 Slice 1 边界。16 个测试全部通过，pyright 零错误。

### 7.2 Observation（非 blocking）

`delete_artifact_file` 的 `except HostDurableError as exc` 会捕获并重新包装 `_validate_published_artifact_relative_path` 抛出的 `HostArtifactWriteError`（因后者继承自 `HostDurableError`），导致原始消息 "must be under sha256 namespace" 被泛化为 "Artifact relative path invalid"。`__cause__` 保留原始异常链，不影响功能正确性，但降低了表面诊断精度。建议在后续 cleanup 中增加 `isinstance(exc, HostArtifactWriteError)` 守卫。

### 7.3 Blocking Finding Count: **0**
