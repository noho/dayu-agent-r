# WU-OBS-00 Whole-PR Deepreview Re-Review — AgentDS

## Verdict

**pass** — PR-CTRL-01 与 PR-FIX-CTRL-01 均已由 owner boundary implementation 与 owner tests 闭合。read+close OSError 双失败 primary 保持、close-only 仍 fatal、任意 operation BaseException 后 mandatory close、KeyboardInterrupt/SystemExit 原实例原样传播、operation/close 优先级正确。未发现新回归或新 actionable finding。

---

## Scope

- Mode: PR re-review（fixed implementation baseline）
- PR: #186
- Implementation baseline: `9519b029`
- Output file: `docs/reviews/wu-obs-00-whole-pr-deepreview-rereview-ds.md`
- Included scope:
  - `dayu/host/tool_trace_analysis_input.py` — `_capture_cold_prefix(...)` fix
  - `tests/host/test_tool_trace_analysis_input.py` — owner tests
  - Controller adjudication chain: `*-controller-adjudication.md` × 3
  - Fix artifact: `wu-obs-00-whole-pr-deepreview-fix-codex.md`
  - Original DS/MiMo review artifacts（背景参考）
- Excluded scope: Controller 已驳回的 rules/dataset lock-path 建议（无新直接错误证据，不重开）；`docs/host/issues-implementation-control.md`（仅 gate status 更新，非生产代码变更）
- Parallel review coverage: 无（单 AgentDS 独立复审）
- Verification focus:
  - PR-CTRL-01: read+close OSError 双失败 primary
  - PR-FIX-CTRL-01: 任意 BaseException 后 mandatory close、identity 保持
  - KeyboardInterrupt/SystemExit identity
  - operation/close 优先级
  - 新回归检查

---

## Verification

### Focused input tests

```text
30 passed in 0.64s
```

### Affected Tool Trace matrix

```text
244 passed, 3 warnings in 5.06s
```

三条 warning 均为既有第三方 `edgar` deprecation，不属本 fix owner。

### Full pyright

```text
0 errors, 0 warnings, 0 informations
```

### Changed-file branch coverage

```text
dayu/host/tool_trace_analysis_input.py  Stmts=499 Miss=77 Branch=134 BrPart=26 Cover=81%
```

唯一修改的生产文件 branch coverage 81%，达到 ≥80% 目标。覆盖缺口分析见下方 Findings。

---

## Findings

### 已验证闭合项

#### PR-CTRL-01 — read+close OSError 双失败 primary 保持

`_capture_cold_prefix(...)` 实现（`tool_trace_analysis_input.py:792-835`）：

1. `operation_failure` 与 `close_failure` 分别初始化为 `None`（行 792-793），`content` 初始化为 `b""`（行 794）；
2. operation phase（行 795-805）：`_read_exact_prefix`、`os.fstat`、identity check 均在同一个 `try` 中，任意 `BaseException` 存入 `operation_failure`；
3. close phase（行 807-810）：无条件 `handle.close()`，任意 `BaseException` 存入 `close_failure`；
4. 优先级裁决（行 813-834）：
   - operation primary 存在时优先传播（行 813-823）；
   - close failure 仅在无 operation primary 时接管（行 824-834）。

**read+close OSError 双失败路径走读**：

- `_read_exact_prefix` 抛 `OSError("primary exact read failed")` → `operation_failure = OSError(...)`；
- `handle.close()` 抛 `OSError("close failed")` → `close_failure = OSError(...)`；
- 行 813: `operation_failure is not None` → True；
- 行 814: `isinstance(operation_failure, OSError)` → True；
- 行 815-822: 构造并抛出 `ToolTraceAnalysisInputError`，summary=`"无法从同一 handle 读取完整 cold snapshot prefix。"`，`__cause__` 指向 read `OSError`；
- `close_failure` 永不检查 → secondary close 不覆盖 primary。

**owner test 验证**（`test_cold_prefix_read_failure_is_not_masked_by_close_failure`）：

- 同时注入 exact-read `OSError` 与 close `OSError`；
- 断言 `reason=COLD_SNAPSHOT_READ_FAILED`、`summary="无法从同一 handle 读取完整 cold snapshot prefix。"`；
- 断言 `__cause__ is read_failure`（同一实例 identity）；
- 断言 `str(__cause__) == "primary exact read failed"`（内容不被覆盖）。

**close-only failure 验证**（增强的 `test_cold_handle_close_failure_is_fatal`）：

- 断言 `summary="关闭 cold snapshot handle 失败。"`、`__cause__` 为 close `OSError`；
- close-only fatal contract 保持不变，未把所有 close failure 改为 best-effort。

**PR-CTRL-01=closed** ✅

---

#### PR-FIX-CTRL-01 — 任意 operation BaseException 后 mandatory close

**非 OSError operation + close success 路径走读**：

- `_read_exact_prefix` 抛 `KeyboardInterrupt("read interrupted")` → `operation_failure = KeyboardInterrupt(...)`；
- `handle.close()` 成功 → `close_failure = None`；
- 行 813: `operation_failure is not None` → True；
- 行 814: `isinstance(operation_failure, OSError)` → False；
- 行 823: `raise operation_failure` → 原 `KeyboardInterrupt` 实例原样传播。

**非 OSError operation + close failure 路径走读**：

- `_read_exact_prefix` 抛 `SystemExit("read exited")` → `operation_failure = SystemExit(...)`；
- `handle.close()` 抛 `OSError("close failed")` → `close_failure = OSError(...)`；
- 行 813: True → 行 814: False → 行 823: `raise operation_failure`；
- close failure 不覆盖 operation primary。

**owner test 验证**（参数化 `test_non_os_operation_failure_closes_handle_and_preserves_identity`）：

- 两个分支均断言 `close_calls == 1`（close 确实执行）；
- 两个分支均断言 `raised.value is operation_failure`（同一异常实例 identity 保持）；
- `SystemExit + close OSError` 分支额外证明 secondary close 不覆盖 primary。

**PR-FIX-CTRL-01=closed** ✅

---

### 新回归检查

沿以下维度逐一走读，未发现新回归：

| 检查维度 | 结果 | 证据 |
|---|---|---|
| `handle` 为 `None` 时到达行 808 | 不可能 | 行 776-781 guard 在到达前已 raise |
| operation phase 成功但 close 后 `content` 未定义 | 不可能 | `content = b""` 在行 794 预初始化，成功路径行 796 赋值，行 835 使用 |
| close phase 的 `BaseException` 捕获覆盖 operation primary | 不可能 | 行 813-823 优先传播 operation primary |
| operation 与 close 均为非 OSError 时 close 覆盖 operation | 不可能 | 行 823 传播 operation primary 后不再检查 close_failure |
| `_read_exact_prefix` 返回有效数据但 identity check 失败时 content 泄漏 | 不泄漏 | identity check 失败触发 operation_failure → typed error raise，content 不使用 |
| `FileNotFoundError`/`BlockingIOError` 等 OSError 子类处理 | 正确 | `isinstance(exc, OSError)` 覆盖所有子类 |
| 锁获取失败路径 handle lifecycle | 不涉及 | 锁获取 except 块使用 `_close_cold_handle_best_effort(handle)`，与本 fix 独立 |

### 覆盖缺口

以下为本次 re-review 确认的覆盖缺口，均为既有或极低风险，不作新 blocking finding：

1. **行 803**（identity/size check `raise OSError`）：`_read_exact_prefix` 的 short read 在 truncation 场景下先触发，使得同 inode identity check 的 raise 不会被走到。这是既有覆盖缺口，本 fix 未改变该行。

2. **行 834**（close-only 非 OSError `raise close_failure`）：close 在无 operation failure 时抛出非 OSError `BaseException`（如 `KeyboardInterrupt`）的路径未被测试覆盖。实际场景中 `BufferedReader.close()` 几乎不可能抛出 `KeyboardInterrupt`；当前测试 helper `_FailingCloseReader` 只抛 `OSError`。如需覆盖需新增抛非 OSError 的 reader 子类，投入产出比低。

两项均不构成新 actionable finding。

---

## Controller 已驳回项确认

- **DS Finding 2**（rules 导入 `_tool_trace_cold_lock_path`）：Controller 驳回为 `reject-nondefect`。本次 re-review 确认 rules 模块未复制 suffix、未从 raw field 推断、未创建第二真源；仍在 Host 内部直接复用唯一 owner helper。未发现新直接错误证据，不重开。
- **MiMo 观察 #1**（`open_host.py` 同包私有 import）：同理由驳回，不重开。
- **MiMo 观察 #2**（Markdown section 固定索引）：无新错误证据，不重开。

---

## Open Questions

无。

## Residual Risk

- 既有 whole-PR residual（CI 未配置、#64 native correlation limited signal、超大 cold file 成本、双文件非事务）保持原 owner，本 fix 不引入新 residual。
- 未执行真实文件系统设备级故障测试（磁盘满、NFS stale handle、权限撤销）；owner-level deterministic failure injection 已覆盖 OS error propagation 与 BaseException lifecycle 契约。

---

## Closure

| Item | Status | Evidence |
|---|---|---|
| PR-CTRL-01 | closed | owner implementation + `test_cold_prefix_read_failure_is_not_masked_by_close_failure` |
| PR-FIX-CTRL-01 | closed | owner implementation + 参数化 `test_non_os_operation_failure_closes_handle_and_preserves_identity` |
| New regressions | none found | 全维度 static analysis + 244 条 affected tests + full pyright |
| Rejected findings re-open | not warranted | 无新直接错误证据 |
