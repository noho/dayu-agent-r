# WU-OBS-00 Whole-PR Fix Re-Review — AgentMiMo

status=complete

work_unit=WU-OBS-00

gate=whole-PR-fix-dual-rereview

reviewer=AgentMiMo

decision=pass

implementation_base=9519b02949941477bc5e2ca3dc7684967222a4ed

review_artifacts=

- docs/reviews/wu-obs-00-whole-pr-deepreview-controller-adjudication.md
- docs/reviews/wu-obs-00-whole-pr-deepreview-fix-controller-adjudication.md
- docs/reviews/wu-obs-00-whole-pr-deepreview-fix-final-controller-adjudication.md
- docs/reviews/wu-obs-00-whole-pr-deepreview-fix-codex.md

## Scope

- Mode: PR re-review（当前未提交 fix，固定基线 9519b029）
- Branch: work/wu-obs-00
- Base: 9519b029（HEAD 未改变）
- Output file: docs/reviews/wu-obs-00-whole-pr-deepreview-rereview-mimo.md
- Included scope: `dayu/host/tool_trace_analysis_input.py`、`tests/host/test_tool_trace_analysis_input.py`
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 逐项验证

#### PR-CTRL-01 — read+close 双失败 primary 保持

**入口**: `_capture_cold_prefix()` (`tool_trace_analysis_input.py:729`)

**实现验证** (`tool_trace_analysis_input.py:792-834`):

- L792-805: operation phase 以 `try/except BaseException` 捕获 read/identity 任意异常为 `operation_failure`；
- L807-810: 无条件 `try: handle.close()` 捕获任意 close 异常为 `close_failure`；
- L812-823: `operation_failure is not None` 时优先裁决：`OSError` 映射为 `ToolTraceAnalysisInputError`，summary="无法从同一 handle 读取完整 cold snapshot prefix。"，`__cause__` 指向 operation failure 原实例；
- L824-834: 只有 `operation_failure is None` 时才处理 `close_failure`。

**直接证据**:

- `test_cold_prefix_read_failure_is_not_masked_by_close_failure` (L908-964): 同时注入 read `OSError("primary exact read failed")` 与 close `OSError("close failed")`，断言 `reason=COLD_SNAPSHOT_READ_FAILED`、`summary="无法从同一 handle 读取完整 cold snapshot prefix。"`、`__cause__ is read_failure`、`str(__cause__)="primary exact read failed"`。
- `test_cold_handle_close_failure_is_fatal` (L869-905): close-only failure 断言 `summary="关闭 cold snapshot handle 失败。"`、`isinstance(__cause__, OSError)`。

**判定**: PASS ✓ — read primary 不被 close secondary 覆盖；close-only 保持 fatal。

#### PR-FIX-CTRL-01 — 任意 BaseException 后 mandatory close 与异常 identity

**入口**: `_capture_cold_prefix()` (`tool_trace_analysis_input.py:792-834`)

**实现验证**:

- L804: `except BaseException as exc: operation_failure = exc` — 捕获任意 `BaseException`，包括 `KeyboardInterrupt`、`SystemExit`、`MemoryError`；
- L807-810: 无论 operation success/failure，`handle.close()` 始终执行；
- L823: operation 非 `OSError` 时 `raise operation_failure` — 原实例传播，identity 不变；
- 没有使用 `finally` 中的 raise，不会覆盖 primary。

**直接证据**:

- `test_non_os_operation_failure_closes_handle_and_preserves_identity` (L967-1036):
  - `KeyboardInterrupt("read interrupted")` + close success: `captured.value is operation_failure`、`close_calls == 1`；
  - `SystemExit("read exited")` + close `OSError("close failed")`: `captured.value is operation_failure`、`close_calls == 1`。

**判定**: PASS ✓ — 非 OSError operation failure close 后原实例传播；close secondary 不覆盖中断。

#### operation/close 优先级完整矩阵

| operation phase | close phase | 实现行号 | 最终结果 |
| --- | --- | --- | --- |
| success | success | L835 | 返回 captured prefix |
| `OSError` | success / 任意 failure | L814-822 | read `ToolTraceAnalysisInputError`，cause 指向 operation |
| 非 `OSError` `BaseException` | success / 任意 failure | L823 | operation 原实例传播 |
| success | `OSError` | L825-833 | close `ToolTraceAnalysisInputError` |
| success | 非 `OSError` `BaseException` | L834 | close 原实例传播 |

**判定**: PASS ✓ — 所有五种组合均按预期行为映射。

#### Controller 已驳回建议

rules/dataset lock-path contract 扩张（`expected_cold_lock_path` 塞入 `ToolTraceAnalysisDataset`）：当前实现未重新引入该建议，`_tool_trace_cold_lock_path` 仍为 `dayu.host.tool_trace` 内部 helper，rules 在 Host 内部直接复用，无 path 错误、owner drift 或测试失败证据。

**判定**: 无新直接错误证据，不重开。

## 新回归检查

- 完整 host test suite: **2328 passed, 1 skipped, 6 deselected**（无新增失败）
- 全量 pyright: **0 errors, 0 warnings, 0 informations**
- changed production branch coverage: **81%**（≥80% 目标）
- HEAD 未改变，未 commit/push/修改 PR metadata
- `git diff --check`: 通过

## Open Questions

- 无。

## Residual Risk

- 未执行真实文件系统 close/read 设备故障；owner-level deterministic failure injection 覆盖了所有 Controller 指定的 failure 注入场景。
- CI 未配置、native correlation、超大 cold file 成本与双文件非事务继续作为已有明确 owner 的既有 residual，不进入本 fix。
- Controller 已驳回的 rules/dataset lock-path 建议保持不实施。

## Verification Results

| 验证项 | 结果 |
| --- | --- |
| Focused input tests | 30 passed |
| Full host test suite | 2328 passed, 1 skipped, 6 deselected |
| Full pyright | 0 errors / 0 warnings |
| Changed-file branch coverage | 81% |
| PR-CTRL-01 closure | verified ✓ |
| PR-FIX-CTRL-01 closure | verified ✓ |
| New regressions | none |
| Controller-rejected suggestions reopened | no |

## Conclusion

**pass** — PR-CTRL-01 与 PR-FIX-CTRL-01 两项 closure 均由实现与 owner tests 证实；无新 actionable findings；无新回归。
