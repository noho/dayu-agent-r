# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-phase-1`
- Base: `HEAD` (commit `9ae1238`)
- Output file: `docs/reviews/gateflow-code-review-host-p1-s3-runtime-filelock-mimo-20260514.md`
- Included scope: 当前 workspace 未提交变更，相对 HEAD 的 staged + unstaged diff 以及 untracked 新文件。
- Excluded scope: 无。
- Parallel review coverage: 无。

## Findings

### 1-未修复-低-`_ensure_lock_file_marker_exists` 在 release 后重建 marker 存在跨进程交错窗口

- **入口/函数**: `RuntimeFileLockToken.release()` -> `_ensure_lock_file_marker_exists()`
- **文件(行号)**: `dayu/runtime/filelock.py:99-104`
- **输入场景**: 进程 A 持有锁并调用 `release()`；同时进程 B 正在等待 acquire 同一把锁。
- **实际分支**: `_third_party_lock.release()` 先调用（第三方 Unix 实现会 unlink lock file），随后 `_ensure_lock_file_marker_exists` 调用 `lock_path.touch(exist_ok=True)` 重建 marker。
- **预期行为**: release 后 lock marker 文件保持存在，wrapper 对外呈现"不删除锁文件"语义。
- **实际行为**: 在步骤 100（`_third_party_lock.release()`）与步骤 101（`_ensure_lock_file_marker_exists`）之间，进程 B 的第三方 `acquire()` 可能成功并创建新 lock file；随后进程 A 的 `touch` 在 B 持锁期间写入该文件；当 B 随后 release（unlink）时，marker 再次消失。最终状态为 marker 文件不存在，wrapper 的"不删除锁文件"外部语义在该交错窗口下被打破。
- **直接证据**: `filelock.py:100-101`，两行之间没有原子性保证；第三方 filelock 3.28.0 的 Unix `release()` 实现会 `os.unlink` lock file。
- **影响**: 不影响互斥正确性（OS 级 advisory lock 是真同步机制），但在高频 acquire/release 交错场景下，marker 文件存在性 invariant 可能瞬时违反。对当前 Phase 1 使用场景（低频文件互斥）影响极小。
- **建议改法和验证点**: 当前实现可接受为已知 trade-off（implementation artifact 已记录）。若需消除窗口，可考虑：(a) 将 `_ensure_lock_file_marker_exists` 移到 `_third_party_lock.release()` 之前（在仍持锁时 touch），但需确认第三方 release 不依赖 marker 文件存在性；或 (b) 接受第三方 unlink 行为，不强制恢复 marker。当前不建议修改，仅记录。
- **修复风险（低/中/高）**: 中（修改 release 顺序可能引入新的第三方依赖假设）
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-`RuntimeFileLock` 不阻止同一实例的重复 acquire，与 plan disclaimed reentrant 语义存在隐式歧义

- **入口/函数**: `RuntimeFileLock.acquire()`
- **文件(行号)**: `dayu/runtime/filelock.py:135-163`
- **输入场景**: 调用方对同一 `RuntimeFileLock` 实例连续调用两次 `acquire()` 而不 release 第一个 token。
- **实际分支**: 第一次 `acquire` 成功并返回 token A；第二次 `acquire` 调用第三方 `FileLock.acquire()`，因 filelock 的同线程 reentrant 特性而成功，返回 token B。
- **预期行为**: plan 明确声明"不承诺 reentrant lock 语义"（`phase1-public-contract-runtime-plan.md:450`）。
- **实际行为**: 实现未拒绝重复 acquire，也未复用已有 token；两个独立 `RuntimeFileLockToken` 同时存在，均指向同一 `_third_party_lock`。token A `release()` 后设置 `released=True` 并调用第三方 `release()`；token B 仍为 `released=False` 但底层锁计数已递减。
- **直接证据**: `filelock.py:153-163`，每次 `acquire()` 无条件创建新 `RuntimeFileLockToken`，无 `_active_token` 检查或计数器。
- **影响**: 若调用方误用重复 acquire，token 生命周期管理变得不直观；但 plan 已 disclaim reentrant 支持，属于 caller misuse 范畴。
- **建议改法和验证点**: 可选改进：在 `acquire()` 中检测 `_active_token is not None and not _active_token.released` 时抛出 `RuntimeFileLockError("已有未释放的活跃 token")`。但当前 plan 不要求此防护，且实现已通过 non-goal 测试明确边界，故可保持现状。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-`dayu/runtime/__init__.py` docstring 未按 plan 更新

- **入口/函数**: 模块级 docstring
- **文件(行号)**: `dayu/runtime/__init__.py:1-21`
- **输入场景**: Phase 1 Slice 3 计划要求更新包 docstring 描述新增 filelock 能力。
- **实际分支**: `__init__.py` 未被修改（diff 中无此文件）。
- **预期行为**: plan 要求"最小修改 `dayu/runtime/__init__.py` docstring，说明 Phase 1 新增的层中立 lane / filelock runtime 能力"（`phase1-public-contract-runtime-plan.md:53`）。
- **实际行为**: 包 docstring 仍为 Slice 2 版本，未提及 `filelock`。
- **直接证据**: `git diff HEAD -- dayu/runtime/__init__.py` 无输出；当前 docstring 第 4-5 行只提"日志装配、协作式取消等待 / race helper"。
- **影响**: 包级文档与实际能力不一致，但不影响运行时行为或 import。
- **建议改法和验证点**: 在 docstring 第 4-5 行补充 `filelock` 能力描述，例如将"日志装配、协作式取消等待 / race helper"扩展为"日志装配、协作式取消等待 / race helper、同步文件锁"。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

- **跨进程互斥正确性**: 当前测试均为单进程测试，未覆盖多进程并发 acquire/release 交错场景。plan 中 Slice 3 不要求多进程测试（那是 lane 的测试面），但 `_ensure_lock_file_marker_exists` 的跨进程行为未被测试验证。
- **第三方 filelock 版本升级风险**: wrapper 依赖 filelock 3.28.0 的 Unix `release()` 行为（unlink lock file）来驱动 marker 恢复逻辑。若第三方后续版本改变 release 行为（例如不再 unlink），marker 恢复逻辑变成无害冗余但语义变化未被测试捕获。
- **`dayu/runtime/__init__.py` 更新缺失**: 如 finding #3 所述，docstring 未同步，属于 plan 偏差但无功能影响。
