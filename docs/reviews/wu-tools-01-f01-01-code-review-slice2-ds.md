# WU-TOOLS-01-F01-01 Code Review — Slice 2

## Review Metadata

- **Reviewer**: AgentDS
- **Work Unit**: WU-TOOLS-01-F01-01 Fins filelock convergence to dayu.runtime.filelock
- **Slice**: Slice 2 — Storage batch lock convergence
- **Gate**: code review
- **Review Target**: uncommitted changes on `phase/wu-tools-01-f01-01-filelock`
- **Design Sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Plan Source**: `docs/host/wu-tools-01-f01-01-filelock-plan.md`
- **Implementation Artifact**: `docs/reviews/wu-tools-01-f01-01-implementation-slice2-codex.md`

## Verdict: PASS

无 blocking finding。实现严格遵循 plan Slice 2 的所有约束，所有验证通过。

---

## Plan / Slice Conformance Checklist

| # | Check | Status |
|---|-------|--------|
| 1 | 只完成 Slice 2，未删除 `dayu/fins/_file_lock.py` | ✅ PASS — 文件仍存在 |
| 2 | 未触碰 ingestion runtime | ✅ PASS — `ingestion_runtime.py` 无改动 |
| 3 | 完全移除 `dayu.fins._file_lock` 生产引用 | ✅ PASS — rg 零命中 |
| 4 | `_ticker_lock_streams: dict[str, TextIO]` → `_ticker_lock_tokens: dict[str, RuntimeFileLockToken]` | ✅ PASS |
| 5 | `_open_and_lock_stream` → `_acquire_lock_token`，返回 `RuntimeFileLockToken` | ✅ PASS |
| 6 | `_release_lock_stream(stream)` → `_release_lock_token(token)` | ✅ PASS |
| 7 | `_release_ticker_lock` 签名从 `stream: TextIO` 改为 `token: RuntimeFileLockToken \| None = None` | ✅ PASS |
| 8 | `_release_ticker_lock` 无条件 pop dict (`_ticker_lock_tokens.pop(ticker, None)`) | ✅ PASS — 第 501 行 |
| 9 | 显式 token 路径不残留 stale token reference | ✅ PASS — `effective_token = token or cached_token`，dict 已 unconditionally pop |
| 10 | 不泄露 cached token（未 release 即丢弃） | ✅ PASS — 当 `token` 非 None 时 dict cached 值被 pop 后未被使用，但显式 token 回调方自行 release |
| 11 | Non-blocking acquire 使用 `timeout_seconds=0` | ✅ PASS — 第 443 行 |
| 12 | `RuntimeFileLockTimeoutError` → `RuntimeError(f"ticker={...} 已存在跨进程活动 batch")` | ✅ PASS — 第 444-446 行 |
| 13 | Recovery global lock blocking acquire / finally release | ✅ PASS — 第 369-374 行 |
| 14 | Recovery per-ticker conflict 返回 `None` skip live batch | ✅ PASS — `_try_acquire_recovery_ticker_lock` 第 728-731 行 |
| 15 | `BatchToken` public shape 不变 | ✅ PASS — 无修改 |
| 16 | Storage repository protocol 不变 | ✅ PASS — 无修改 |
| 17 | Batch atomic semantics 不变 | ✅ PASS — journal / backup / staging / swap 逻辑未改 |
| 18 | 新增 test 覆盖 public behavior，不依赖第三方 internals | ✅ PASS — `test_same_ticker_batch_fails_fast_across_independent_repository_cores` 只通过 `FsBatchingRepository.begin_batch` / `rollback_batch` 公共接口验证 |
| 19 | Docstring 完整更新至 `RuntimeFileLockToken` / `RuntimeFileLockError` / `RuntimeError` | ✅ PASS |
| 20 | Import boundary: 只从 `dayu.runtime.filelock` import | ✅ PASS — 第 17 行 |
| 21 | 无 `TextIO` 残留 import | ✅ PASS — `typing` import 中已无 `TextIO`（第 14 行） |
| 22 | 所有变量名从 stream 改为 token | ✅ PASS — `lock_token`, `ticker_token`, `recovery_token`, `cached_token`, `effective_token` |
| 23 | `docs/host/issues-implementation-control.md` gate bookkeeping 未越界 | ✅ PASS — 仅更新 gate 状态与 next entry point |

---

## Findings

### F1 — Docstring Raises 精度不足（Low Severity）

- **文件**: `dayu/fins/storage/_fs_storage_infra.py:437`
- **行号**: 437
- **描述**: `_acquire_lock_token` 的 Raises 声明为 `RuntimeFileLockError: 锁文件访问或加锁失败时抛出`。在 blocking 路径中，若第三方 `FileLock` 超时，实际抛出的具体类型是 `RuntimeFileLockTimeoutError`。虽然 `RuntimeFileLockTimeoutError` 是 `RuntimeFileLockError` 的子类，文档声明在继承层级上正确，但未能区分 blocking 超时（透传 `RuntimeFileLockTimeoutError`）与非超时 acquire 失败（`RuntimeFileLockError`）。
- **影响**: 调用方如果只捕获 `RuntimeFileLockError`，能同时捕获两种异常，不影响正确性。但若调用方期望区分超时与一般失败，当前 docstring 未提供足够信息。
- **建议修复方向**: 在 Raises 中补充说明 blocking 路径可能抛出 `RuntimeFileLockTimeoutError`。
- **裁决**: **accepted** — 低优先级，可在后续 slice 或独立 docstring cleanup 中修复。

### F2 — 新增测试为同进程内验证，非真实跨进程（Low Severity，已知设计决策）

- **文件**: `tests/fins/test_fins_storage_provider.py:344-359`
- **行号**: 344-359
- **描述**: `test_same_ticker_batch_fails_fast_across_independent_repository_cores` 在同一测试进程内创建两个独立 `_FsStorageInfra` 实例，验证同 ticker fail-fast。这验证的是 `RuntimeFileLock` + 第三方 `FileLock` 的同进程行为，与真实跨进程场景不完全等价。
- **影响**: 无法检测 `FileLock` 在真实多进程场景的行为差异（如有）。但：
  - Plan R3 明确要求 tests 不得断言第三方 internals
  - `tests/runtime/test_filelock.py` 已在 runtime 公共契约层覆盖 non-blocking timeout 包装
  - 跨进程行为由第三方 `filelock` 包保证
- **裁决**: **accepted** — 符合设计决策。如需增强跨进程信心，应在 runtime 公共契约层补充，而非在 Fins 层。

### F3 — `_release_ticker_lock` 显式 token 路径的 dict 清理顺序隐含信息丢失（Informational）

- **文件**: `dayu/fins/storage/_fs_storage_infra.py:501-505`
- **行号**: 501-505
- **描述**: 当 `begin_batch` 异常路径调用 `_release_ticker_lock(normalized_ticker, token=lock_token)` 时，`_ticker_lock_tokens.pop(ticker, None)` 先执行（移除 dict 条目），然后 `effective_token = token or cached_token` 选用显式 `token`，`cached_token` 被丢弃。此行为正确满足 plan 的"无条件 pop dict"要求，但意味着 `cached_token` 与 `token` 相同时实际持有了两个引用（从 pop 得到的 + 调用方传入的），pop 出的那个引用不会被显式 release（最终由 gc 回收，而 token 持有的 `FileLock` 已在显式 release 时 unlock）。
- **影响**: 无功能影响——锁只会释放一次（`token.release()` 幂等性由 `RuntimeFileLockToken._release_completed` 保证）。这是实现细节的语义澄清。
- **裁决**: **accepted** — 无需修改，仅记录供后续维护参考。

---

## Validation Performed

| Validation | Command | Result |
|---|---|---|
| Fins storage & ingestion tests | `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py -q` | 38 passed |
| Runtime filelock & import boundary tests | `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q` | 23 passed |
| Pyright type check | `pyright` | 0 errors, 0 warnings |
| Whitespace check | `git diff --check` | no errors |
| Old reference cleanup (stream/helper) | `rg` for `_ticker_lock_streams\|_open_and_lock_stream\|_release_lock_stream\|file_lock_module\|dayu\.fins import _file_lock` in `_fs_storage_infra.py` | 0 matches |
| Third-party filelock import boundary | `rg "import filelock" dayu -g '*.py'` | only `dayu/runtime/filelock.py:16` |
| `_file_lock.py` existence | `test -f dayu/fins/_file_lock.py` | EXISTS (correct for Slice 2) |

---

## Residual Risks and Uncovered Areas

| Risk | Owner | Classification |
|---|---|---|
| 同进程 FileLock reentrancy 行为差异未被 Fins 层测试覆盖 | Runtime filelock contract owner | Low — 由 `tests/runtime/test_filelock.py` 和第三方 `filelock` 保证；plan R3 明确禁止 Fins 测试断言第三方 internals |
| `_release_ticker_lock` 在 commit/rollback finally 块中的执行依赖于 `_ticker_lock_tokens` 中仍存在对应条目；若 caller 违反协议重复释放，第二次调用将 no-op（pop 返回 None，无 explicit token） | Caller（现有代码无此问题） | Low — 与旧 stream 路径等价风险 |
| Recovery global lock 阻塞 acquire 在极端情况下（第三方 FileLock 永远无法获取）可能导致 recovery 永久阻塞 | Future runtime/Host work unit | Deferred — plan R5 明确 defer stale lock detection 至未来需求 |

---

## Blocking Open Questions

无。

---

## Accepted / Candidate Findings Summary

- **F1** (accepted, Low): `_acquire_lock_token` docstring 可补充区分 blocking 超时类型。
- **F2** (accepted, Low): 新增 test 为同进程验证，符合 plan 设计决策。
- **F3** (accepted, Informational): `_release_ticker_lock` 显式 token 路径的 dict 清理顺序隐含信息，无功能影响。
