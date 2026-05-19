# Phase 11 Aggregate Re-Review - AgentDS - 2026-05-19

## Scope

- Work unit: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening
- Re-review target: Phase 11 aggregate fix artifact `docs/reviews/phase11-aggregate-fix-codex-20260519.md`
- Fix items under review: P11-AGG-F1, P11-AGG-F2
- Controller adjudication: `docs/reviews/phase11-aggregate-deepreview-controller-adjudication-20260519.md`
- Changed files: `dayu/host/durable/state.py`, `dayu/host/durable/run_transition.py`, `dayu/host/recovery.py`, `docs/host/implementation-control.md`

## P11-AGG-F1: Move RECOVERING cancel Run-row CAS to durable state boundary

### Execution Correctness

- 旧私有 helper `_cancel_recovering_run_row` 已从 `run_transition.py` 完全删除（原 L2751-L2810）。
- `TABLE_HOST_RUNS` 导入已从 `run_transition.py` 删除；grep 确认该模块已无 `TABLE_HOST_RUNS` 引用。
- 新公共函数 `cancel_recovering_run_row` 已加入 `state.py` L3339，位于 `terminal_recovering_run_row` 与 `cancel_waiting_run_row` 之间，位置与同类 Run-row CAS helper 一致。
- SQL UPDATE 文本、CAS 条件（`WHERE ... AND status = ? AND terminal_event_id IS NULL AND terminal_event_sequence IS NULL AND terminal_at IS NULL`）、参数绑定、mutation 结果分类（UPDATED/NOT_FOUND/CAS_LOST）与旧实现逐字节一致。
- 输入校验由 `_validate_run_terminal_update` 替代旧的三次独立 `_require_*` 调用；两者校验相同字段、相同语义，均为 `HostDurableError` 抛出路径。
- `run_transition.py` 调用点 `cancel_recovering_run_in_transaction`（L2402）已从 `_cancel_recovering_run_row(...)` 改为 `cancel_recovering_run_row(...)`，参数传递一致。

### Ownership Correctness

- `cancel_recovering_run_row` 与 `start_recovering_run_row`、`terminal_recovering_run_row`、`cancel_cancelling_run_row`、`cancel_waiting_run_row`、`cancel_queued_run_row`、`cancel_running_run_row` 等同类 Run-row CAS owner 同驻 `state.py`，消除此前 ownership 不一致。
- `run_transition.py` 不再直接依赖 `TABLE_HOST_RUNS`，只编排 EventLog + state helper，符合"数据处理、存储、工具调用职责分离"。

### Adversarial Check

- row 不存在 → NOT_FOUND；CAS 未命中 → CAS_LOST；命中 → UPDATED，与旧行为一致。
- 若 `cancel_recovering_run_row` 在 `state.py` 中被重命名而 `run_transition.py` 未同步更新 → 模块加载期 ImportError，安全失败。

**P11-AGG-F1 结论：收口。**

## P11-AGG-F2: Document heartbeat interval vs stale threshold safety relationship

### Execution Correctness

- 注释已添加到 `recovery.py` L58，紧邻 `_DEFAULT_STALE_AFTER_SECONDS = 30` 上方。
- 注释内容：`# heartbeat 周期必须显著小于 stale 阈值，避免破坏 positive orphan proof。`
- 清晰声明约束与违反后果，不改变任何行为。

**P11-AGG-F2 结论：收口。**

## 新 Blocker 扫描

### 无新增 import cycle

`run_transition.py` 此前已大量从 `state.py` 导入；新增一个 import 不引入循环依赖。

### 无新增 God object / God function

`cancel_recovering_run_row` 是 `state.py` 中已有 Run-row CAS helper 族的自然补齐，不扩大 `state.py` 职责范围。

### 无 schema / public API / Engine 变更

diff 仅触及 4 个文件，净 +6 行。不涉及 schema、Engine、public API。

### 无重复逻辑残留

grep 确认全量 `_cancel_recovering_run_row` 已删除，无残留私有版本。

## 验证记录

以下命令均在当前工作区本地执行：

```bash
# focused tests
source .venv/bin/activate && pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py tests/host/test_public_cancel_session_runs.py -q
# → 50 passed

# full host tests
source .venv/bin/activate && pytest tests/host -q
# → 793 passed, 1 skipped

# full runtime tests
source .venv/bin/activate && pytest tests/runtime -q
# → 107 passed

# pyright
source .venv/bin/activate && python -m pyright dayu/host dayu/runtime tests/host tests/runtime
# → 0 errors, 0 warnings, 0 informations

# whitespace check
git diff --check
# → clean, no output
```

## implementation-control.md Gate 一致性

`docs/host/implementation-control.md` 已按时间线追加 gate 事实，从 Slice 5 accepted → aggregate deepreview → aggregate fix → aggregate re-review（当前 gate）。下一 gate 设定为 `Phase 11 accepted aggregate fix commit / ready-to-open-draft-PR`，与当前工作流匹配。

## Verdict

**PASS.**

P11-AGG-F1 与 P11-AGG-F2 均已收口。变更面窄（4 文件，净 +6 行），语义等价，所有权正确。全量 host/runtime 测试 900 passed / 1 skipped，pyright 零报错，git diff --check 通过。未发现新 blocking issue。
