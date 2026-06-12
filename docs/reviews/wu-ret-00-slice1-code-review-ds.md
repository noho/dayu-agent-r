# WU-RET-00 Slice 1 Code Review — AgentDS

- work unit: WU-RET-00 Host Storage Lifecycle Retention Policy
- gate: code review
- slice: Slice 1 — artifact 模块复用 helper（containment-guarded 文件枚举与删除）
- reviewer: AgentDS
- review target files:
  - `dayu/host/durable/artifact.py`
  - `tests/host/test_artifact_store.py`
- design source: `docs/host/design.md`、`docs/engine/design.md`
- control source: `docs/host/issues-implementation-control.md`
- accepted plan: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`
- implementation report: `docs/reviews/wu-ret-00-slice1-implementation-codex.md`

---

## 1. Review Scope and Methodology

本 review 只审查 Slice 1 边界内的代码正确性、安全性、测试覆盖和 AGENTS.md 合规性。不审查 slice 间 contract、不在本 slice 实现的后续功能（orphan 证明、grace window、maintenance entrypoint、storage usage report），也不对实现做任何修改。

审查方法：
- 逐函数 trace 数据流与异常路径。
- 对 `_ensure_contained`、symlink 逃逸、TOCTOU 做 adversarial 推演。
- 逐条对照 plan §8 Slice 1 的 objective、exact changes、invariants、non-goals。
- 逐条对照 AGENTS.md 约束（中文 docstring、严格类型、禁止 Any/object/无类型签名、禁止无理由 getattr/hasattr、禁止兼容性 facade）。
- 检查测试是否覆盖主要安全边界与失败模式。

已确认的验证证据（来自 implementation report）：
- `pytest tests/host/test_artifact_store.py -q` → 15 passed
- `pyright dayu/host/durable/artifact.py tests/host/test_artifact_store.py` → 0 errors, 0 warnings, 0 informations

---

## 2. Findings

### F1 — `delete_artifact_file` 不校验 sha256 namespace prefix（invariant 缺失）

- **Severity**: Low
- **File/Line**: `dayu/host/durable/artifact.py:167-196`
- **Status**: **accepted**

**证据**：

plan §8 Slice 1 invariants 明确写：

> 绝不返回/删除 `.tmp`、非 `sha256/` namespace 文件或 root 外路径；删除是 idempotent（缺失返回 False，不抛）。

`iter_published_artifact_relative_paths` 正确实现了 namespace 限定——只从 `artifact_root/sha256/` 遍历。但 `delete_artifact_file` 只做了路径文本校验 + containment 校验，未检查 `relative_path` 是否以 `sha256/` 开头。当前实现接受任何合法相对路径（如 `audit/audit.jsonl` 或 `tool-trace/trace.jsonl`），只要它在 artifact root 内且非 symlink 逃逸。

**影响**：若未来调用方（Slice 3/4 maintenance）因 bug 传入非 sha256 路径，可能误删 audit、tool-trace 或其他非 descriptor-managed 文件。在当前 Slice 1 内，`delete_artifact_file` 只有一个调用方——测试，实际风险为零。

**与 plan 的关系**：plan §8 "exact changes" 描述的函数签名未显式要求 namespace 校验（只写了 `_validate_relative_path_text → _path_from_posix_relative → _ensure_contained → unlink`），但 invariants 段落明确声明了 namespace 约束。这是一个 plan 内部的不一致，实现跟随了 exact changes 而非 invariants。

**裁决建议**：不在 Slice 1 修复。推荐在 Slice 3/4 的 `reclaim_orphan_artifact_files` 调用层保证只传 sha256 路径，并在 `delete_artifact_file` 的 docstring 中显式说明 namespace 过滤是调用方职责。如果后续 review 认为 helper 应自保，可在 Slice 3/4 补一个最小 prefix check。

---

### F2 — `except FileNotFoundError: return False` 在 `delete_artifact_file` 中是死代码

- **Severity**: Note
- **File/Line**: `dayu/host/durable/artifact.py:193-194`
- **Status**: **accepted**

**证据**：

```python
# delete_artifact_file L185-196
try:
    if not os.path.lexists(final_path):
        return False
    _ensure_contained(artifact_root, final_path)   # ← 内部 catch (OSError, ValueError) → HostArtifactWriteError
    final_path.unlink(missing_ok=True)              # ← missing_ok=True 不会抛 FileNotFoundError
    return True
except HostArtifactWriteError:
    raise
except FileNotFoundError:                           # ← 死代码
    return False
except OSError as exc:
    raise HostArtifactWriteError("Artifact file delete failed") from exc
```

唯一可能抛出 `FileNotFoundError` 的调用是 `_ensure_contained` 内部的 `candidate.resolve(strict=True)`——但 `_ensure_contained` 的 `except (OSError, ValueError)` 已将其包装为 `HostArtifactWriteError`，随后被 `except HostArtifactWriteError: raise` 截获。`Path.unlink(missing_ok=True)` 不会对缺失文件抛异常（这正是 `missing_ok` 的语义）。`os.path.lexists` 不会对合法 Path 参数抛异常。

因此 `except FileNotFoundError: return False` 永远不会被触发。

**影响**：无害但误导。阅读者可能以为存在一条"文件消失时返回 False"的路径，实际上该路径被 `_ensure_contained` 阻断，会以 `HostArtifactWriteError` 形式抛出。

**裁决建议**：移除死代码，或在 `_ensure_contained` 中区分"路径逃逸"与"路径不存在"两种错误（后者可在 `delete_artifact_file` 中转为 `return False`）。推荐在 Slice 1 修复后进入 accepted commit，或在 Slice 4 处理。非 blocking。

---

### F3 — 测试缺口：`delete_artifact_file` 对非 sha256 路径无覆盖

- **Severity**: Note
- **File/Line**: `tests/host/test_artifact_store.py`（缺失测试）
- **Status**: **accepted**

**证据**：

现有测试 `test_delete_artifact_file_deletes_existing_file_and_reports_missing` 只测试了 sha256 路径的存在/缺失删除行为。`test_delete_artifact_file_rejects_traversal_and_symlink_escape` 覆盖了越界路径和 symlink 逃逸。但没有测试验证：当传入合法但不在 `sha256/` namespace 下的路径（如 `audit/audit.jsonl`、`other/file`）时 `delete_artifact_file` 的行为。

**影响**：如果 F1 在后续 slice 中未被修复（即 `delete_artifact_file` 继续保持接受任意合法路径），则缺少回归测试来捕获可能的调用方错误。

**裁决建议**：在 Slice 3/4 补充测试。如果届时决定在 `delete_artifact_file` 内增加 namespace prefix check，则测试应验证非 sha256 路径被拒绝。如果决定保持 caller-responsible 语义，则测试应在 maintenance 层验证调用方不会传入非 sha256 路径。非 Slice 1 blocking。

---

### F4 — 测试缺口：dangling symlink 在 sha256 namespace 中的行为无覆盖

- **Severity**: Note
- **File/Line**: `tests/host/test_artifact_store.py`（缺失测试）
- **Status**: **accepted**

**证据**：

`_iter_contained_regular_files` 对每个 entry 调用 `entry.is_dir()` / `entry.is_file()` 判断类型。在 Python `pathlib` 中，这两个方法默认 `follow_symlinks=True`——对 dangling symlink 两者均返回 `False`，因此 dangling symlink 会被静默跳过，不会进入 `yield` 也不会触发 `_ensure_contained` 检查。这是安全行为（不会误把 dangling symlink 当作 artifact 文件），但缺少测试来锁定该行为。

此外，如果 dangling symlink 目标路径指向 artifact root 外，当前行为也是静默跳过——因为 `is_file()` 返回 `False`，根本不会进入 `_ensure_contained`。这也是安全的，但同样缺少显式测试。

**影响**：行为本身安全，但缺少回归测试意味着未来重构可能意外改变该行为（例如改用 `entry.is_file(follow_symlinks=False)` 后 dangling symlink 可能被当作普通文件处理）。

**裁决建议**：在后续 slice 或独立测试加固 PR 中补充 dangling symlink 测试。非 Slice 1 blocking。

---

### F5 — TOCTOU 竞态：`delete_artifact_file` 中 `lexists` 与 `_ensure_contained` 之间文件被删除时误报错误

- **Severity**: Note
- **File/Line**: `dayu/host/durable/artifact.py:186-188`
- **Status**: **accepted**

**证据**：

```python
if not os.path.lexists(final_path):   # T1: 文件存在
    return False
_ensure_contained(artifact_root, final_path)  # T2: 文件被外部删除
```

时序：T1 时刻 `lexists` 返回 `True`；T1 与 T2 之间文件被并发删除；T2 时刻 `_ensure_contained` 内部的 `candidate.resolve(strict=True)` 抛出 `FileNotFoundError` → 被包装为 `HostArtifactWriteError("Artifact path escapes artifact root")` → 向上传播。

结果：调用方收到 `HostArtifactWriteError`，消息暗示路径越界，但实际上只是文件被并发删除。与函数 docstring 声明的"文件不存在时返回 `False`"不一致（在并发场景下）。

**实际风险**：极低。maintenance entrypoint 预期由 operator 显式调用，不存在并发写入方。artifact root 下的写入只发生在 command path（EventLog append），而 maintenance 不应与 command path 并发运行。plan §7.6 明确要求 maintenance 不进 command path。因此该 TOCTOU 窗口在预期使用场景中不会触发。

**裁决建议**：记录为已知残余风险，不在 Slice 1 修复。如果在 Slice 3/4 的 maintenance 实现中需要更精确的并发语义，可考虑在 `delete_artifact_file` 中把 `_ensure_contained` 的 `FileNotFoundError` 转为 `return False`。非 blocking。

---

### F6 — `_ensure_contained` 对 `strict=True` 的依赖导致所有"路径不存在"被归为"路径逃逸"

- **Severity**: Note
- **File/Line**: `dayu/host/durable/artifact.py:335-349`
- **Status**: **accepted**

**证据**：

`_ensure_contained` 使用 `root.resolve(strict=True)` 和 `candidate.resolve(strict=True)`。`strict=True` 要求路径必须存在，否则抛出 `OSError`（通常是 `FileNotFoundError`）。该 OSError 被统一捕获并转为 `HostArtifactWriteError("Artifact path escapes artifact root")`。

这意味着以下三种语义不同的失败被合并为同一错误消息：
1. Root 不存在（调用方 bug 或文件系统异常）。
2. Candidate 不存在（文件已被删除）。
3. Candidate 解析后确实逃逸 root（真正的安全违规）。

**影响**：在正常流程中，root 应已由 `_prepare_artifact_root` 确保存在；candidate 应已由调用方确认存在。因此错误消息的精度损失在当前 Slice 1 的调用上下文中影响很小。但若未来有新的 `_ensure_contained` 调用方未做前置存在性检查，诊断信息可能不足。

**裁决建议**：当前实现满足 Slice 1 需求，不要求修改。若后续发现诊断精度不足，可在 `_ensure_contained` 中区分子错误类型并给出不同消息。非 blocking。

---

### F7 — plan 的 `iter_published_artifact_relative_paths` docstring 缺少 namespace 范围说明

- **Severity**: Note
- **File/Line**: `dayu/host/durable/artifact.py:136-146`
- **Status**: **deferred**

**证据**：

当前 docstring 写"只遍历 `artifact_root/sha256` 内容寻址 namespace"，这对代码阅读者和 LLM 上下文都是清晰的。但 plan §8 Slice 1 描述为：

> 只递归遍历 artifact root 下的 `sha256/` namespace，跳过 `.tmp` 子树和所有非 `sha256/` 路径

这一描述准确地反映在函数的 docstring 中。然而，与 `delete_artifact_file` 形成对比——后者未在 docstring 中说明 namespace 限制。如果最终决定 `delete_artifact_file` 不自行校验 namespace，则其 docstring 应显式声明"调用方负责确保 relative_path 为合法的 artifact namespace 路径（通常以 `sha256/` 开头）"。

**裁决建议**：与 F1 联动。若 F1 决议为 caller-responsible，则在 Slice 3/4 更新 docstring。非 Slice 1 blocking。

---

## 3. Review Dimension Check Results

### 3.1 Slice 1 边界合规

| 检查项 | 结论 |
| --- | --- |
| 只提供 artifact 文件枚举和删除 helper | ✅ `iter_published_artifact_relative_paths` + `delete_artifact_file` |
| 不做 usage report | ✅ 无 SQLite 读取、无 COUNT 查询 |
| 不做 descriptor/payload 关联 | ✅ 不 import payload.py、不读 descriptor |
| 不做 orphan reclaim | ✅ 不做引用判定、不做差集计算 |
| 不读取 SQLite | ✅ 纯文件系统操作 |
| 不读取环境变量或当前工作目录 | ✅ artifact root 由调用方显式注入 |

### 3.2 Namespace 限定

| 检查项 | 结论 |
| --- | --- |
| 枚举只覆盖 sha256 namespace | ✅ `namespace_dir = artifact_root / "sha256"` |
| 不误扫 audit/ | ✅ 测试验证 `audit/audit.jsonl` 不入枚举 |
| 不误扫 tool-trace/ | ✅ 测试验证 `tool-trace/trace.jsonl` 不入枚举 |
| 不误扫 loose file | ✅ 测试验证 `loose-file` 不入枚举 |
| 不误扫 .tmp | ✅ `entry.name == ".tmp"` 时 continue |
| `delete_artifact_file` namespace 校验 | ⚠️ 缺失，见 F1 |

### 3.3 Symlink Containment

| 检查项 | 结论 |
| --- | --- |
| `_ensure_contained` 使用 resolve(strict=True) | ✅ 完整解析所有 symlink 链 |
| 拒绝 symlink 目录遍历 | ✅ `entry.is_dir() and not entry.is_symlink()` 跳过 symlink 目录 |
| 拒绝 symlink 文件产出 | ✅ `entry.is_file() and not entry.is_symlink()` 跳过 symlink 文件 |
| 写入路径的父目录 containment | ✅ `_ensure_parent_dir_contained` + 创建后 `_ensure_contained` |
| temp 目录 containment | ✅ `_prepare_directory` 内含 `_ensure_contained` |
| dangling symlink 行为 | ✅ 被 `is_file()`/`is_dir()` 返回 False 自然跳过（安全） |
| TOCTOU：check-unlink 间 symlink 替换 | ✅ `unlink()` 删除 symlink 自身，不跟随目标 |
| TOCTOU：lexists-ensure_contained 间文件删除 | ⚠️ 误报 HostArtifactWriteError，见 F5 |

### 3.4 Generator 早期 return 行为

| 检查项 | 结论 |
| --- | --- |
| root 不存在 → 空迭代器 | ✅ `return` 终止生成器 |
| root 不是目录 → 抛错 | ✅ `raise HostArtifactWriteError` |
| sha256/ 不存在 → 空迭代器 | ✅ `return` 终止生成器 |
| sha256/ 不是目录 → 空迭代器 | ✅ `return` 终止生成器 |
| 异常不静默吞掉 | ✅ `except HostArtifactWriteError: raise` |

### 3.5 OSError 处理

| 检查项 | 结论 |
| --- | --- |
| 所有 OSError → HostArtifactWriteError | ✅ 统一转换 |
| 所有转换使用 `from exc` 保留链 | ✅ 全部 10 处异常转换均保留 root cause |
| `FileNotFoundError` 在 `OSError` 前捕获 | ✅ `delete_artifact_file` 中顺序正确（虽然该处理器是死代码，见 F2） |
| temp 文件清理在异常路径中执行 | ✅ `_unlink_if_exists(temp_path)` 在 except 块中 |
| `_fsync_directory` 的 fd 在 finally 中关闭 | ✅ `finally: os.close(directory_fd)` |

### 3.6 AGENTS.md 合规

| 检查项 | 结论 |
| --- | --- |
| 中文 docstring（模块、类、函数） | ✅ 全部提供完整中文 docstring |
| 严格类型签名 | ✅ 无 `Any`、`object`、无类型参数/返回值 |
| 禁止无理由 getattr/hasattr | ✅ 无使用 |
| 禁止兼容性 facade/re-export | ✅ 全部为新增功能，无兼容性代码 |
| 禁止魔法数字/字符串 | ✅ 全部提取为模块级常量 |
| 模块级私有辅助函数 | ✅ 全部为模块级函数，无嵌套函数/类 |
| 数据处理/存储/工具调用职责分离 | ✅ artifact.py 只做文件系统操作 |
| 禁止 god object/function/dataclass | ✅ `LocalArtifactStore` 职责单一 |

---

## 4. Symlink Escape Adversarial Analysis

对 `_ensure_contained` 的 adversarial pass：

**场景 A：正常文件在 root 内**
- `root.resolve(strict=True)` → `/real/artifact_root`
- `candidate.resolve(strict=True)` → `/real/artifact_root/sha256/ab/file`
- `relative_to` 成功 → 通过 ✅

**场景 B：candidate 是指向 root 外的 symlink**
- `candidate.resolve(strict=True)` → `/etc/passwd`
- `relative_to(root)` → `ValueError`
- 抛出 `HostArtifactWriteError` ✅

**场景 C：candidate 的祖先目录是 root 外的 symlink**
- `candidate.resolve(strict=True)` → 跟随祖先 symlink → `/outside/sha256/ab/file`
- `relative_to(root)` → `ValueError`
- 抛出 `HostArtifactWriteError` ✅

**场景 D：root 自身是 root 外的 symlink**
- `root.resolve(strict=True)` → `/other/location`
- `candidate.resolve(strict=True)` → `/other/location/sha256/ab/file`
- `relative_to` 成功 → 通过
- 安全分析：调用方显式注入 root，若 root 是指向外部的 symlink，这是调用方的意图。不属于逃逸。✅

**场景 E：candidate 不存在（dangling symlink 或已删除）**
- `candidate.resolve(strict=True)` → `FileNotFoundError`
- 抛出 `HostArtifactWriteError("Artifact path escapes artifact root")`
- 安全分析：不存在的路径不能读也不能删，抛出错误是安全的。消息不够精确但安全。✅

**场景 F：root 不存在**
- `root.resolve(strict=True)` → `FileNotFoundError`
- 抛出 `HostArtifactWriteError`
- 安全分析：调用方 bug，安全失败。✅

**场景 G：在多级 symlink 链中部分组件被替换**
- `resolve()` 是单次系统调用（`realpath`），对每个路径组件逐级解析。TOCTOU 存在于组件级（symlink 替换可能在两次 `readlink` 系统调用之间）。但 Python `Path.resolve()` 内部使用 `os.path.realpath`，它在 CPython 中通过循环 `readlink` 实现，确实存在组件级 TOCTOU。这是所有基于 `realpath` 的 containment 检查的已知局限。
- plan §7.3 已记录该残余风险："recheck 与 unlink 之间仍存在极短窗口"。当前 Slice 1 只实现 containment 守卫，grace window + recheck 留给 Slice 3/4。✅（已记录风险）

**结论**：`_ensure_contained` 的 containment 守卫在单线程/非并发场景下可靠。TOCTOU 风险已知且已由 plan §7.3 分配后续缓解措施。

---

## 5. Test Coverage Assessment

### 5.1 已覆盖场景

| 场景 | 测试 |
| --- | --- |
| 基本写入 + 路径在注入 root 下 | `test_artifact_helper_writes_under_injected_root` |
| ref 拒绝非法路径（绝对、空字节、穿越、temp） | `test_artifact_ref_rejects_invalid_relative_paths` |
| ref 拒绝负数 size | `test_artifact_ref_rejects_negative_size` |
| 写入拒绝 symlink 逃逸 | `test_artifact_helper_rejects_symlink_escape` |
| 枚举只返回 sha256/ 下普通文件 | `test_iter_published_artifact_relative_paths_returns_only_sha256_files` |
| 空 root / 无 sha256 → 空枚举 | `test_iter_published_artifact_relative_paths_empty_without_sha256` |
| 枚举拒绝 symlink 逃逸 | `test_iter_published_artifact_relative_paths_rejects_symlink_escape` |
| 删除存在/不存在文件 | `test_delete_artifact_file_deletes_existing_file_and_reports_missing` |
| 删除拒绝越界和 symlink 逃逸 | `test_delete_artifact_file_rejects_traversal_and_symlink_escape` |
| temp 目录位置 + 并发写入不碰撞 | `test_temp_area_is_under_artifact_root_and_concurrent_writes_do_not_collide` |
| digest 不匹配阻止 descriptor 写入 | `test_digest_verify_happens_before_descriptor_write` |
| 最终文件 digest 匹配 | `test_final_artifact_is_published_and_digest_matches` |
| EventLog 引用 descriptor 不引用 temp | `test_event_log_references_descriptor_not_artifact_temp_path` |
| SQLite rollback 后 orphan 文件遗留 | `test_sqlite_failure_after_artifact_publish_leaves_orphan_not_fact` |
| EventLog 拒绝 temp path descriptor | `test_event_log_rejects_descriptor_with_artifact_temp_path` |

### 5.2 未覆盖场景

| 场景 | 相关 Finding |
| --- | --- |
| `delete_artifact_file` 传入合法但非 sha256 路径 | F3 |
| sha256 namespace 中存在 dangling symlink | F4 |
| `delete_artifact_file` 并发删除（TOCTOU） | F5（低优先级，难以可靠测试） |
| `iter_published_artifact_relative_paths` root 是 symlink 到外部 | N/A（合法场景，行为正确） |
| `_ensure_contained` 对多级 symlink 链的处理 | N/A（已由现有 symlink 测试间接覆盖） |

---

## 6. Conclusion

### 6.1 Verdict: **PASS**

无 blocking finding。Slice 1 实现满足 plan 规定的 objective、exact changes、invariants 和 non-goals。安全边界（namespace 限定、containment 守卫、symlink 逃逸拒绝）正确实现。测试覆盖了主要安全边界和失败模式。AGENTS.md 合规。

### 6.2 Finding Summary

| ID | Severity | Status | 简述 |
| --- | --- | --- | --- |
| F1 | Low | accepted | `delete_artifact_file` 不校验 sha256 namespace prefix |
| F2 | Note | accepted | `except FileNotFoundError` 在 `delete_artifact_file` 中是死代码 |
| F3 | Note | accepted | 测试缺口：非 sha256 路径删除行为 |
| F4 | Note | accepted | 测试缺口：dangling symlink 行为 |
| F5 | Note | accepted | TOCTOU 竞态：lexists 与 ensure_contained 间文件删除误报错 |
| F6 | Note | accepted | `_ensure_contained` 不区分"路径不存在"和"路径逃逸" |
| F7 | Note | deferred | `delete_artifact_file` docstring 缺少 namespace 职责说明 |

### 6.3 Blocking Finding Count: **0**

### 6.4 Recommendation

Slice 1 可以进入 accepted commit。建议在 Slice 3/4 实现时：
- 在 `delete_artifact_file` 调用层保证 namespace 过滤（回应 F1）。
- 移除 `except FileNotFoundError` 死代码或赋予其实际语义（回应 F2）。
- 补充 dangling symlink 和非 sha256 路径的测试（回应 F3、F4）。
