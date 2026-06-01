# Code Re-Review

## Scope

- **Mode**: code re-review (role-scoped handoff)
- **Gate**: code re-review
- **Work Unit**: WU-RUNTIME-02 Slice 2
- **Branch**: `fix/wu-runtime-02-lane-clock-cancellation`
- **Fix artifact**: `docs/reviews/wu-runtime-02-fix-slice2-codex-20260601.md`
- **Source review artifacts**:
  - `docs/reviews/wu-runtime-02-code-review-slice2-mimo-20260601.md`
  - `docs/reviews/wu-runtime-02-code-review-slice2-ds-20260601.md`
- **Re-review scope**: 仅复核 controller accepted findings (001, 002) 的 fix 正确性、rejected finding (003) 是否仍无 correctness risk、以及是否新增 blocking 问题。
- **Included files**: `dayu/runtime/lane.py`, `tests/runtime/test_lane.py`

## Findings

### Accepted Finding 001 - observer 消费普通 Exception：PASS

**Fix 验证**:

三个 `_consume_abandoned_*_task` 函数均已从 `except RuntimeLaneError` 改为 `except Exception`：

- `_consume_abandoned_claim_task`（line 1231）: `except Exception:` — 使用 `_LOGGER.exception` 记录完整 traceback ✓
- `_consume_abandoned_release_task`（line 1290）: `except Exception:` — 使用 `_LOGGER.exception` 记录完整 traceback ✓
- `_consume_abandoned_refresh_task`（line 1340）: `except Exception as exc` — 保留 `error_type` extra 和 `exc_info=True` ✓

`task.cancelled()` 检查仍在 `try` 之前（line 1227/1286/1336），确保 `CancelledError` 不被 `except Exception` 捕获。`BaseException` 子类中的 `KeyboardInterrupt` / `SystemExit` 仍不被捕获，符合 controller 裁决。

**测试验证**: `test_abandoned_release_observer_logs_non_runtime_exception` 构造 `ValueError` 异常 task，注册 observer，断言 `_ABANDONED_RELEASE_FAILED_LOG_FRAGMENT` 和 `"ValueError"` 均出现在日志中。测试通过 (38 passed)。

**结论**: fix 正确。

### Accepted Finding 002 - release cancel 路径异常链：PASS

**Fix 验证**:

两处 `raise cancelled` 均已改为 `raise cancelled from exc`：

- `_release_token`（line 849）: `except RuntimeLaneError as exc:` 分支内 `raise cancelled from exc` ✓
- `_release_untracked_claim`（line 929）: `except RuntimeLaneError as exc:` 分支内 `raise cancelled from exc` ✓

与同文件中 `_try_claim_once`（line 628）和 `_refresh_token`（line 750）的异常链模式一致。

**测试验证**:
- `test_release_token_failure_after_outer_cancel_preserves_cause`: 断言 `exc_info.value.__cause__` 是 `RuntimeLaneError` 实例，且 message 匹配 ✓
- `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error`: 已更新为断言 `__cause__` 是 `RuntimeLaneError` ✓

**结论**: fix 正确。

### Rejected Finding 003 - claim.acquired=False 静默消费：无 correctness risk

**复核**:

`_consume_abandoned_claim_task`（line 1237-1241）中 `claim.acquired is False` 的路径仍然直接 return，不记录日志。

Controller 裁决理由：capacity full 的 late claim 不持有资源、不依赖 TTL fallback，记录日志会制造低价值噪音。

**风险分析**:
- capacity full 时 `claim.acquired=False`，无 DB claim row 需要清理 ✓
- 不存在 TTL fallback 路径依赖此日志 ✓
- 不影响状态机终态收敛 ✓
- observer 仍然消费了 task（避免 `Task exception was never retrieved` 警告）✓

**结论**: 无 correctness risk，rejection 合理。

## Open Questions

- 无。

## Residual Risk

- 无新增 residual risk。
- `BaseException`（`KeyboardInterrupt` / `SystemExit`）仍不被 observer 捕获，符合 controller 裁决：runtime logger 不应吞掉进程级信号。
- cleanup timeout 后底层线程仍可能继续运行，这是 approved plan 的既有设计决策。

## Conclusion: PASS

两个 accepted findings (001, 002) 的 fix 实现正确、测试充分。rejected finding (003) 无 correctness risk。未发现新增 blocking 问题。所有测试通过 (38 passed in 1.19s)。
