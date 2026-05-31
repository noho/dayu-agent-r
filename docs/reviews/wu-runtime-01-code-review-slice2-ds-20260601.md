# WU-RUNTIME-01 Slice 2 Code Review (AgentDS)

## Conclusion: pass

Blocking findings: 0

---

## 1. Scope Verification

**Evidence**: `git diff HEAD -- tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py` 显示仅两个测试文件变更。`grep` 确认 `dayu/host/audit.py` 和 `dayu/host/tool_trace.py` 未被修改。`dayu/runtime/filelock.py` 中 `_active_token` 和 `.released` 已不存在（Slice 1 已清理）。

**Finding (PASS)**: 改动范围严格限于 `tests/host/test_audit_sink.py`、`tests/host/test_tool_trace_projection.py` 及 implementation artifact 本身。无 Host production source 修改。

---

## 2. Call-Path Coverage

**Evidence**:
- `test_jsonl_line_contains_required_audit_fields` 通过 `_run_audit_once(..., lock_path=tmp_path / "locks" / "host-audit.jsonl.lock")` → `LogAuditSink(LogAuditSinkOptions(..., lock_path=lock_path))` → `ProjectionRunner.run_once()` 走完整 audit projection，内部经过 `_append_audit_jsonl_line_if_absent()` 的 `with file_lock(lock_path, ...)` 调用链。
- `test_tool_call_chain_projects_hot_rows_and_cold_lines` 通过 `_run_trace_once(..., lock_path=tmp_path / "locks" / "tool-trace-cold.jsonl.lock")` → `ToolTraceProjectionConsumer(ToolTraceSinkOptions(..., lock_path=lock_path))` → `ProjectionRunner.run_once()` 走完整 tool trace projection，内部经过 `_append_line()` 的 `with file_lock(lock_path, ...)` 调用链。
- 两个测试均断言 `lock_path.exists()`，证明 runtime marker restore 在生产调用路径上执行。

**Finding (PASS)**: 两个 regression 用例覆盖了 plan 要求的 audit JSONL append 与 tool trace cold JSONL append 的 explicit `lock_path` 调用面。

---

## 3. Import Boundary / No Leaked Internals

**Evidence**: `grep "filelock\|FileLock\|RuntimeFileLock\|RuntimeFileLockToken\|_active_token\|\.released\|_context_token" tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py` 返回零匹配。测试仅通过 Host 层 public API（`LogAuditSinkOptions`、`ToolTraceSinkOptions`）传递 `lock_path` 参数。

**Finding (PASS)**: 无第三方 `filelock` import、无 token 状态读取、无 runtime internals mock。

---

## 4. Assertion Minimality and Stability

**Evidence**:

| 断言 | 类型 | 稳定性分析 |
|------|------|-----------|
| `assert lock_path.exists()` | 文件系统可观测事实 | 不依赖内部状态；lock marker 是 `release()` best-effort 产物，在可写 tmp_path 下稳定 |
| `assert checkpoint is not None` | projection checkpoint 公共契约 | checkpoint 存在性是 projection runner 的稳定语义 |
| `assert checkpoint.checkpoint_event_sequence == <event>.event_sequence` | projection checkpoint 公共字段 | `event_sequence` 是 EventLogRow 的稳定字段，checkpoint 指向最新已扫描事件是 projection runner 的标准行为 |

**为什么不是脆弱断言**:
- `lock_path.exists()` 不检查 marker 内容、不依赖 token lifecycle state，仅验证文件存在——这是 runtime marker restore 的最小可观测信号。
- checkpoint 断言复用现有 projection system 的稳定公共契约——`checkpoint_event_sequence` 的定义和语义在 `dayu.host.durable.projection` 中已有明确约定，不引入新业务期望。
- 未对 `file_lock()` 内部 acquire/release 顺序、token 生命周期、context manager 嵌套行为做任何断言。

**Finding (PASS)**: 新增断言最小且稳定，均基于可观测公共事实或已有公共契约，无脆弱额外业务期望。

---

## 5. Overdesign Check

**Evidence**:
- 修改的测试函数：2 个（每个文件 1 个）
- 新增测试函数：0 个
- 修改的辅助函数：2 个（`_run_audit_once`、`_run_trace_once`，仅增加可选 `lock_path` 参数）
- 新增辅助函数/工具/夹具：0 个
- 新增 import：0 个
- 每测试新增断言行数：~4-5 行

**Finding (PASS)**: 无过度设计。改动量为满足 Slice 2 覆盖目标的最小必要集。辅助函数 `lock_path` 参数采用 backward-compatible 可选参数设计，不影响现有调用方。

---

## 6. README Decision Review

**Evidence**: `tests/README.md` 触发规则要求检查 filelock 相关描述是否包含 `released` 或等价旧语义。Implementation artifact 确认现有 filelock bullet 仅描述 parent directory、context manager release、release 幂等、non-blocking timeout 和 import boundary——无 `released` 或 `_active_token` 语义残留。Slice 2 未新增测试层、测试命令或测试架构变更。

**Finding (PASS)**: 不更新 `tests/README.md` 的决策合理，符合 plan 中的 README sync decision。

---

## 7. Residual Risk

**Accepted residual risk (无新增)**:
- lock marker 文件不是 Host durable truth；marker restore 失败仅 debug log。本 Slice 仅在可写 tmp_path 下验证 marker restore 成功路径。
- 未覆盖多进程 contention 场景；runtime filelock 自身的 non-blocking timeout 互斥失败包装已在 Slice 1 测试中覆盖。

**无新增 residual risk**。

---

## 8. Validation Reproducibility

Implementation artifact 报告：
- `pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q` → 13 passed
- `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q` → 36 passed
- `pyright` → 0 errors, 0 warnings, 0 informations

验证命令与 plan 要求的 Slice 2 验证命令一致。

---

## Findings Summary

| # | Severity | Category | Finding | Blocking |
|---|----------|----------|---------|----------|
| 1 | — | Scope | 仅测试文件变更，无 production source 修改 | No |
| 2 | — | Coverage | explicit lock_path 调用面已覆盖 | No |
| 3 | — | Boundary | 无第三方 filelock import / token 读取 / mock | No |
| 4 | — | Stability | 断言最小且基于公共契约 | No |
| 5 | — | Overdesign | 无过度设计或测试膨胀 | No |
| 6 | — | Docs | README 不更新决策合理 | No |

**Blocking findings: 0**
