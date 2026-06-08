# WU-TOOLS-01-F01-01 Code Review Slice 2 — MiMo

## Work Unit / Gate / Slice

- Work unit: WU-TOOLS-01-F01-01 Fins filelock convergence to dayu.runtime.filelock
- Gate: code review
- Slice: Slice 2 — Storage batch lock convergence
- Reviewer: AgentMiMo

## Verdict

**pass-with-findings**

## Files Reviewed

- `dayu/fins/storage/_fs_storage_infra.py`
- `tests/fins/test_fins_storage_provider.py`
- `docs/reviews/wu-tools-01-f01-01-implementation-slice2-codex.md`
- `docs/host/issues-implementation-control.md`

## Findings

### F1 — `_release_ticker_lock` 显式 token 与 cached token 同时存在时偏向显式 token

- 文件: `dayu/fins/storage/_fs_storage_infra.py:500-505`
- 严重性: low
- 影响: 当调用方传入的 `token` 与 `cached_token` 是同一对象时（正常路径），`token or cached_token` 求值为 `token`，release 显式 token 后 cached token 已通过 `pop` 移除，功能正确。但语义上应优先使用 cached token（它是 `_acquire_ticker_lock` 创建并存入 dict 的那个），显式 token 仅作为 fallback。当前实现在 `begin_batch` error path（token 尚未存入 dict）下正确工作，但选择逻辑可以更清晰。
- 建议修复方向: 改为 `effective_token = cached_token or token`，让 cached token 优先；若 cached token 存在则它就是权威 token，显式 token 仅在 cached miss 时使用。
- 裁决: **accepted** — 不阻塞，功能正确，可作为 Slice 3 或后续 cleanup 改进。

### F2 — `docs/host/issues-implementation-control.md` 修改超出 Slice 2 计划范围

- 文件: `docs/host/issues-implementation-control.md:140-148`
- 严重性: low
- 影响: Plan 中 Slice 2 的 "No expected changes" 列表包含 `docs/host/issues-implementation-control.md`。Implementation 将 gate 从 `implementation` 更新为 `code review`、更新 implementation status 和 next entry point。这是 gated workflow 的合理 bookkeeping 动作，但严格来说超出了 plan 定义的 Slice 2 allowed files 范围。
- 建议修复方向: 无需修复。Gate bookkeeping 更新是 gated workflow 正常推进的附带动作。Future slices 的 plan 可显式允许 control doc 状态更新。
- 裁决: **accepted** — 合理的 gate 推进 bookkeeping，不影响实现正确性。

### F3 — `_acquire_lock_token` blocking 路径未显式传递 `timeout_seconds=None`

- 文件: `dayu/fins/storage/_fs_storage_infra.py:440-442`
- 严重性: low
- 影响: Blocking 路径调用 `file_lock(lock_path).acquire()`，依赖 `file_lock()` 默认 `timeout_seconds=None` 和 `acquire()` 默认行为（传 `-1` 给第三方 `FileLock`，即无限等待）。这是正确的，但不如显式 `file_lock(lock_path).acquire(timeout_seconds=None)` 自解释。Plan 允许两种写法。
- 建议修复方向: 无需修复。当前写法依赖 runtime filelock 公共契约的默认行为，语义明确。
- 裁决: **accepted** — 不影响正确性。

## Plan / Slice Conformance Checklist

| 检查项 | 结果 |
|---|---|
| 未删除 `dayu/fins/_file_lock.py` | PASS — 文件未修改 |
| 未触碰 `dayu/fins/ingestion_runtime.py` | PASS — 文件未修改 |
| `_fs_storage_infra` 不再 import `dayu.fins._file_lock` | PASS — import 已替换为 `dayu.runtime.filelock` |
| `_ticker_lock_streams` 替换为 `_ticker_lock_tokens` | PASS |
| `_open_and_lock_stream` / `_release_lock_stream` 替换为 token helper | PASS |
| `_acquire_lock_token` 使用 `timeout_seconds=0` 做 non-blocking acquire | PASS |
| `RuntimeFileLockTimeoutError` 正确映射为 `RuntimeError` 用户消息 | PASS |
| `_release_ticker_lock` 无条件 pop dict | PASS |
| Recovery global lock blocking acquire + finally release | PASS |
| Recovery per-ticker conflict 返回 None | PASS |
| `BatchToken` public shape 未改变 | PASS |
| Storage repository protocol 未改变 | PASS |
| Batch atomic semantics 未改变 | PASS |
| 新增测试覆盖 public behavior | PASS |
| Docstring / 类型已更新 | PASS |
| `TextIO` import 已移除 | PASS |
| 变量名从 stream 改为 token | PASS |

## Validation Performed

| 命令 | 结果 |
|---|---|
| `pytest tests/fins/test_fins_storage_provider.py -q` | 12 passed, 3 warnings |
| `pytest tests/fins/test_fins_ingestion_runtime.py -q` | 26 passed, 3 warnings |
| `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q` | 23 passed |
| `pyright dayu/fins/storage/_fs_storage_infra.py tests/fins/test_fins_storage_provider.py` | 0 errors, 0 warnings |
| `git diff --check` | 无 whitespace error |
| `rg -n "_file_lock\|file_lock_module\|_ticker_lock_streams\|_release_lock_stream\|_open_and_lock_stream" dayu/fins/storage/_fs_storage_infra.py` | 无命中 |
| `git diff HEAD -- dayu/fins/ingestion_runtime.py dayu/fins/_file_lock.py` | 无 diff — 未触碰 |

## Residual Risks and Uncovered Areas

- R1 (低): `RuntimeFileLockError` 不是 `OSError`，部分内部 docstring 从 `OSError` 更新为 `RuntimeFileLockError`。已由 pyright 和 runtime tests 覆盖。
- R2 (低): `filelock.FileLock` 同进程 reentrancy 细节未被测试断言。Plan 明确这是 non-goal（R3），测试只断言 Fins public behavior。
- R3 (低): `_release_ticker_lock` 在显式 token 与 cached token 同一对象时执行两次 release（第二次被 `_release_completed` 幂等保护）。不影响正确性，见 F1。

## Blocking Open Questions

无。
