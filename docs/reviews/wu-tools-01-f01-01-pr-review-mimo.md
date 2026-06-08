# WU-TOOLS-01-F01-01 PR Review

## Verdict

**PASS**

## PR State Checked

- PR URL: https://github.com/noho/dayu-agent-r/pull/127
- Base: `main` (sha `688b9de02a00b5f270266726b991d3a8085f537e`)
- Head: `phase/wu-tools-01-f01-01-filelock` (sha `daf5adbc76879276e261cb78186749ccefee9d1b`)
- PR state: open（非 draft）
- 本地 HEAD sha 与 PR head sha 一致：`daf5adbc76879276e261cb78186749ccefee9d1b`
- 本地 main sha 与 PR base sha 一致：`688b9de02a00b5f270266726b991d3a8085f537e`
- 本地 diff 与 PR diff 基于相同 base/head commit，内容一致（diff hash 差异因 GitHub API 格式化差异，非实质差异）
- 40 files changed, 2896 insertions, 358 deletions

## Findings

### F-01: PR 未处于 draft 状态

- **严重性**: 低（流程状态，非代码缺陷）
- **位置**: PR #127 元数据
- **证据**: GitHub API 返回 PR state=open，无 `draft` 字段（draft PR 会在 JSON 中包含 `"draft": true`）
- **Root cause**: PR 在创建后已被标记为 ready for review，或创建时未设为 draft
- **影响**: 不影响代码质量。Gate 流程要求"不得 mark ready for review"，但 PR 已处于 open 状态
- **建议修复**: 若 gate 流程要求 PR 保持 draft 直到用户显式 merge decision，可将 PR 转回 draft 状态。否则确认当前 open 状态为预期行为后关闭此 finding

## Evidence Checked

### 1. 旧私有锁完全删除验证

- `dayu/fins/_file_lock.py`：文件已删除（diff 确认 169 行全部删除）
- `dayu/fins/ingestion_runtime.py`：`_StoreFileLock` 类已删除，`import fcntl` 已删除
- `dayu/fins/storage/_fs_storage_infra.py`：`from dayu.fins._file_lock import ...` 已替换为 `from dayu.runtime.filelock import ...`
- 全局 grep `_StoreFileLock|_file_lock|acquire_text_file_lock|release_text_file_lock` 在 `dayu/` 和 `tests/` Python 文件中零命中
- 全局 grep `import fcntl|from fcntl` 在 `dayu/` Python 文件中零命中
- 测试文件 `test_fins_ingestion_runtime.py` 中 `_StoreFileLock` import 和 `test_store_file_lock_closes_stream_when_flock_fails` 测试已删除

### 2. Runtime filelock 消费验证

- `dayu/fins/ingestion_runtime.py:49`：`from dayu.runtime.filelock import file_lock`
- `dayu/fins/storage/_fs_storage_infra.py:17`：`from dayu.runtime.filelock import RuntimeFileLockTimeoutError, RuntimeFileLockToken, file_lock`
- `dayu/runtime/filelock.py:16`：`from filelock import FileLock, Timeout` — 第三方 filelock 只在此处直接 import

### 3. dayu.runtime 层中立验证

- `dayu/runtime/` 不 import `dayu.fins`、`dayu.host`、`dayu.engine`、`dayu.service`、`dayu.ui`
- `dayu/runtime/__init__.py` 无变更

### 4. FsFinsIngestionJobStore 临界区验证

- 六处 `.store.lock` 临界区（`create_job`、`save_job`、`save_succeeded_or_cancelled`、`claim_running_or_cancelled`、`read_job`、`request_cancel`）均使用 `with file_lock(self.root_dir / _LOCK_FILE_NAME):` — blocking lock 语义保持
- 所有六处 docstring 均声明 `RuntimeFileLockError: 文件锁获取失败时抛出`
- `_write_record_locked` 保持 atomic tmp + os.replace + fsync 语义

### 5. Storage batch RuntimeFileLockToken 生命周期验证

- `_acquire_lock_token`（line 425-447）：
  - `blocking=True` → `file_lock(lock_path).acquire()`（默认无限等待）
  - `blocking=False` → `file_lock(lock_path).acquire(timeout_seconds=0)`（fail-fast）
  - `RuntimeFileLockTimeoutError` → `RuntimeError` 映射（line 444-446）
- `_release_lock_token`（line 449-462）：直接调用 `token.release()`
- `_acquire_ticker_lock`（line 464-479）：non-blocking acquire + 缓存到 `_ticker_lock_tokens`
- `_release_ticker_lock`（line 482-505）：先 pop cached token，再 release
- `_acquire_recovery_lock`（line 507-520）：blocking acquire
- `_try_acquire_recovery_ticker_lock`（line 715-731）：non-blocking acquire，`RuntimeError` 时返回 `None`（跳过被持有的 ticker）
- `_batch_recovery_completed` 标志保证 per-ticker recovery skip 语义

### 6. 未误改 contract 验证

- `dayu/fins/domain/document_models.py`：无变更（BatchToken schema 不变）
- `dayu/fins/storage/` 仓储协议：无变更
- `dayu/host/`、`dayu/engine/`、`dayu/ui/`：无变更
- atomic replace（`_write_record_locked` 中的 tmp + os.replace + fsync）：语义不变

### 7. 测试与 artifact 一致性验证

- `test_fins_ingestion_runtime.py`：删除 `_StoreFileLock` import 和 `test_store_file_lock_closes_stream_when_flock_fails` 测试（38 行删除），其余测试未受影响
- `test_fins_storage_provider.py`：新增 `test_same_ticker_batch_fails_fast_across_independent_repository_cores` 测试（18 行新增），验证同 workspace 独立仓储 core 的同 ticker fail-fast 语义
- `tests/runtime/test_filelock.py`、`tests/runtime/test_import_boundary.py`：无变更
- 已验证证据：pytest 38+23 passed，pyright 0 errors，git diff --check 通过
- aggregate deepreview artifact 存在且结论为 PASS（`docs/reviews/wu-tools-01-f01-01-aggregate-deepreview-mimo.md`）

### 8. Control doc 一致性验证

- `docs/host/issues-implementation-control.md`：WU-TOOLS-01-F01-01 状态更新为 "PR review gate"，记录 PR #127 URL，下一步入口为 "Dispatch AgentMiMo and AgentDS for WU-TOOLS-01-F01-01 PR review"
- 验收信号与实际代码变更一致

### 9. Review artifacts 完整性

PR diff 包含以下 review artifacts，均为只读文档，不影响代码：
- `docs/reviews/wu-tools-01-f01-01-plan-review-*.md`（plan review）
- `docs/reviews/wu-tools-01-f01-01-plan-rereview-*.md`（plan re-review）
- `docs/reviews/wu-tools-01-f01-01-plan-fix-codex.md`
- `docs/reviews/wu-tools-01-f01-01-implementation-slice*.md`（implementation reports）
- `docs/reviews/wu-tools-01-f01-01-code-review-slice*.md`（code review）
- `docs/reviews/wu-tools-01-f01-01-code-rereview-slice*.md`（code re-review）
- `docs/reviews/wu-tools-01-f01-01-fix-slice*.md`（fix reports）
- `docs/reviews/wu-tools-01-f01-01-aggregate-deepreview-*.md`（aggregate deepreview）
- `docs/host/wu-tools-01-f01-01-filelock-plan.md`（plan 真源）

## Project Instruction Check

- **架构约束**: 无违反。Fins 只消费 `dayu.runtime.filelock`，`dayu.runtime` 保持层中立
- **类型签名**: 无违反。pyright 0 errors
- **docstring**: 无违反。所有修改的函数/方法保持完整中文 docstring
- **测试**: 无违反。旧测试随实现边界迁移删除，新测试覆盖收敛后的 fail-fast 语义
- **README**: `tests/README.md` 有微调（2 行变更），与当前测试结构一致
- **兼容性 wrapper/re-export**: 无。删除旧实现后未引入兼容性 re-export 或 wrapper
- **反向依赖**: 无。`dayu.runtime` 不 import 上层模块

## Residual Risks

| Risk | Owner | Destination |
|------|-------|-------------|
| PR 当前为 open 状态而非 draft，与 gate 流程预期可能不一致 | PR owner | 确认是否需要转回 draft，或接受当前 open 状态 |
| `dayu.runtime.filelock` 的 `_ensure_lock_file_marker_exists` 在 release 后 touch marker 文件失败时仅 debug log，不抛异常 — 这是已有行为，非本 PR 引入 | runtime owner | 后续如需强化可单独处理 |
