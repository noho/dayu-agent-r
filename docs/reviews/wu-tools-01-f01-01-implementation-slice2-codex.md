# WU-TOOLS-01-F01-01 Implementation Slice 2

## Work Unit / Gate / Slice

- Work unit: WU-TOOLS-01-F01-01 Fins filelock convergence to dayu.runtime.filelock
- Gate: implementation
- Slice: Slice 2 — Storage batch lock convergence
- Implementer: AgentCodex

## Files Changed

- `dayu/fins/storage/_fs_storage_infra.py`
- `tests/fins/test_fins_storage_provider.py`
- `docs/reviews/wu-tools-01-f01-01-implementation-slice2-codex.md`

## Implementation Summary

- 将 storage batch 的私有 `dayu.fins._file_lock` import 替换为 `dayu.runtime.filelock` 的 `RuntimeFileLockTimeoutError`、`RuntimeFileLockToken` 与 `file_lock`。
- 将 `_ticker_lock_streams` 收敛为 `_ticker_lock_tokens`，batch 生命周期只在 `_FsStorageInfra` 私有状态中持有 runtime token，不改变 `BatchToken`。
- 将 stream acquire / release helper 改为 runtime token acquire / release helper。
- blocking recovery lock 使用 runtime filelock 默认阻塞 acquire。
- non-blocking ticker lock 使用 `acquire(timeout_seconds=0)`，并在 `RuntimeFileLockTimeoutError` 时保留现有用户可读错误：`ticker=<TICKER> 已存在跨进程活动 batch`。
- `_release_ticker_lock` 先清理 `_ticker_lock_tokens`，再释放显式或缓存 token，避免留下 stale token reference。
- recovery 的全局锁与 per-ticker skip-live-batch 锁均改为 `RuntimeFileLockToken`；per-ticker conflict 继续返回 `None`。

## Tests Changed

- 新增 `test_same_ticker_batch_fails_fast_across_independent_repository_cores`，覆盖同 workspace 两个独立 repository/core 同 ticker 活动 batch 的 fail-fast 行为，并确认第一个 rollback 后第二个可成功 acquire。

## README Decision

- 已先阅读 `dayu/fins/README.md` 的 Agent 更新约束。本次只替换 storage batch 内部锁 primitive，不改变 Fins capability 定位、公共接口、执行路径、状态机或稳定边界，因此不更新。
- 已先阅读 `tests/README.md` 的维护约束。本次新增测试仍落在既有 `tests/fins/` 财报仓储测试分层描述内，未新增测试层级或运行方式，因此不更新。

## Validation Commands and Results

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: passed, `38 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q`
  - Result: passed, `23 passed`
- `source .venv/bin/activate && pyright dayu/fins/storage/_fs_storage_infra.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pyright`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- `rg -n "file_lock_module|_ticker_lock_streams|_open_and_lock_stream|_release_lock_stream|dayu\\.fins import _file_lock" dayu/fins/storage/_fs_storage_infra.py`
  - Result: no old helper or stream matches; `rg` exited 1 due to no matches.

## Completion Signal

- Slice 2 implementation complete.
- `dayu/fins/storage/_fs_storage_infra.py` no longer imports or calls `dayu.fins._file_lock`.
- Storage batch lock lifecycle now uses `RuntimeFileLockToken`.
- 同 ticker 跨 repository/core fail-fast 语义已由 public behavior 测试覆盖。

## Blocking Open Questions

- None.

## Residual Risks Classification

- Low: runtime `filelock.FileLock` now owns lock file descriptor lifecycle instead of Fins text streams. `tests/runtime/test_filelock.py` covers runtime token release, idempotent release, context release and non-blocking timeout wrapping; storage behavior tests cover the Fins conflict mapping.
- Low: recovery global blocking lock is validated indirectly through existing ingestion/storage tests and runtime filelock tests; no recovery-specific behavior changed beyond primitive replacement.

## Explicit Non-Changes

- Host / Engine / ToolRuntime contract: unchanged.
- Fins job schema: unchanged.
- Storage repository protocol: unchanged.
- `BatchToken` public shape: unchanged.
- Batch journal / backup / staging / atomic directory swap semantics: unchanged.
- `dayu/fins/_file_lock.py`: not modified and not deleted; deletion remains Slice 3.
