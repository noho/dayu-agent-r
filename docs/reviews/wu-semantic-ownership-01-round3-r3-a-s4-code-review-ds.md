# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: S3 accepted commit `815432ea` 之后的 S4 implementation workspace changes
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s4-code-review-ds.md`
- Included scope:
  - Production: `dayu/host/recovery.py`（batching orchestration、batch operation、`_wake_after_committed_batch`、cursor advance guard）、`dayu/host/durable/state.py`（`NonTerminalRunKeysetCursor`、`read_non_terminal_run_upper_watermark`、`read_non_terminal_runs_keyset_page`）、`dayu/host/open_host.py`（`_StartupRecoveryActorOperation`、recovery 迁入 actor thread、READY handoff order）
  - Tests: `tests/host/test_recovery_scan.py`（bounded page size、keyset cursor stability、watermark deferral、fixed policy time、batch rollback、full rerun convergence、classification immutability）、`tests/host/test_open_host_runtime.py`（actor thread recovery barrier + READY handoff assertion、recovery failure path zero `mark_ready()` calls）
  - Docs: `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`
- Excluded scope: S3 health lease、S5 watchdog/cancel、Service/CLI/Fins/Engine。均未在 diff 中出现。`tests/host/test_recovery_dispatch.py`/`test_recovery_multiprocess.py`/`test_admission_multiprocess.py` 仅作为 required regression matrix 运行，未修改。
- Parallel review coverage: 无。

## Review Method Summary

沿 S4 六个 review focus，逐项走读 `durable/state.py`（cursor/watermark/keyset page reader SQL）→ `recovery.py`（`scan()` loop、batch operation、`_wake_after_committed_batch`、cursor advance validation、`_classify_run` unchanged）→ `open_host.py`（`_StartupRecoveryActorOperation`、actor thread execution、`mark_ready()` after recovery）完整生产调用链。随后走读全部 S4 测试代码：batch size=2 的 page 有界性、同 sequence tie-break、watermark deferral、fixed policy time、batch rollback + full rerun convergence、actor thread barrier + READY handoff。最后做 scope creep 扫描，确认 `read_non_terminal_runs()`/`OFFSET` 彻底从 recovery call graph 消失，S3/S5/Service/CLI/Fins/Engine 无越界。

### 1. Cursor/watermark from durable governance truth

**Keyset 定义**：`NonTerminalRunKeysetCursor(accepted_event_sequence: int, run_id: str)`（`durable/state.py:317-325`），全序来自 durable `host_runs` 表的 `(accepted_event_sequence, run_id)` 字段，不依赖 projection/read model。

**Upper watermark 查询**（`durable/state.py:1969-2020`）：
```sql
SELECT accepted_event_sequence, run_id FROM host_runs
WHERE status IN (non_terminal_statuses)
ORDER BY accepted_event_sequence DESC, run_id DESC
LIMIT 1
```
一次 read transaction，固定 scan 边界。若 `None`（无 non-terminal Run）→ 直接返回空 `StartupRecoveryScanResult`。

**Keyset page 查询**（`durable/state.py:2022-2129`）：
```sql
WHERE status IN (...)
  AND (accepted_event_sequence < ? OR (accepted_event_sequence = ? AND run_id <= ?))
  AND (accepted_event_sequence > ? OR (accepted_event_sequence = ? AND run_id > ?))
ORDER BY accepted_event_sequence ASC, run_id ASC
LIMIT ?
```
- 上界：`(accepted_event_sequence, run_id) <= watermark` — inclusive，watermark row 进入扫描。
- 下界（cursor 非 `None`）：`(accepted_event_sequence, run_id) > cursor` — exclusive，已处理行不重复读取。
- 排序严格升序，tie-break 由 `run_id` 字符串比较确定。
- `LIMIT ?` 参数化为 `batch_size`（正整数）。
- 参数校验：`_validate_non_terminal_run_keyset`（`durable/state.py:2132-2152`）检查 sequence 为正整数且 run_id 非空。
- `cursor >= watermark` 时提前返回空 tuple（`durable/state.py:2063-2067`）。

`test_keyset_batches_are_bounded_and_stable_with_sequence_ties`（`test_recovery_scan.py:945-1033`）验证：5 个同 sequence(=100) 的 Run 按 run_id 排序，batch_size=2 产生 (2, 2, 1) 的 page 分布，cursors 为 `None -> (100, run-b) -> (100, run-d)`，watermark 固定为 `(100, run-e)`，无重复无遗漏。

### 2. Batch transaction、commit-after-wake、READY handoff

**Batch write transaction**（`recovery.py:158-245`）：`_StartupRecoveryBatchOperation.__call__()` 在单个 `HostTransaction` 内执行 keyset 读取 + `_classify_run` 循环。accumulator 为 operation 局部变量，不跨批保留。

**Commit-after-wake**（`recovery.py:328-347`）：`_wake_after_committed_batch()` 在 `run_write` 返回后（commit 成功后）同步投递 dispatch wake 和 queue promotion wake。rollback batch 不调用此方法。

**Cursor advance guard**（`recovery.py:318-319`）：`if batch.next_cursor is None or batch.next_cursor == cursor: raise RuntimeError(...)` — 防止空页或同 cursor 导致无限循环。

**READY handoff**（`open_host.py:1350-1356` + `open_host.py:1339`）：
- recovery 通过 `durable_actor.call(_StartupRecoveryActorOperation(...))` 在 actor thread 执行。
- recovery 成功返回后，才继续创建 `_PublicHostHandle` 并调用 `health_gate.mark_ready()`。
- recovery 异常 → 进入既有 startup cleanup 路径，`mark_ready()` 零调用。

`test_startup_recovery_runs_on_actor_before_ready`（`test_open_host_runtime.py:1366-1438`）通过 `threading.Event` barrier 确认：recovery 在 actor thread（非 opener thread），释放 barrier 前 `ready_thread_ids` 为空，释放后 READY 发生在 opener loop thread。

`test_second_batch_failure_rolls_back_without_wake_and_full_rerun_converges`（`test_recovery_scan.py:1215-1333`）验证：
- 第 2 批 mutation 后异常 → 整批 rollback → 该批 zero wake → 第 3 个 Run 的 current_attempt_id 不变。
- 完整重跑（cursor=None）→ 前两行由 durable CAS 分类为 `OWNER_STILL_LIVE`，后三行创建 recovery dispatch。
- 五个 distinct wake 的 dispatch_record_id 与 durable current dispatch 一一匹配。
- canonical transition 计数与 single-batch baseline 相同，失败 scan 的内存 offset 未被复用。

### 3. 不再使用全量 `read_non_terminal_runs()` 或 OFFSET

**生产代码验证**：
- `rg "read_non_terminal_runs\b" dayu/host/recovery.py` → 零命中。import 已移除，无调用。
- `rg "OFFSET" dayu/host/recovery.py dayu/host/durable/state.py` → 仅命中 `state.py:2032` 的 docstring 说明"不使用 OFFSET"，非代码逻辑。
- legacy `read_non_terminal_runs(...)`（`state.py:1927`）仍存在，供非 recovery consumer/legacy test 使用；S4 不删除它（plan 明确"删除该通用 reader 超出本 slice"），但 recovery call graph 不再引用。

**测试验证**：所有 S4 新测试使用 `batch_size=2` 的 `StartupRecoveryScanner` 构造，never 调用 `read_non_terminal_runs`。

### 4. `fetchall()` 全部 bounded

**新增 S4 reader**：`read_non_terminal_runs_keyset_page` 中的唯一 `fetchall()`（`state.py:2075`），其 SQL 带 `LIMIT ?`（`state.py:2109`），参数来自 typed `batch_size`（`state.py:2112`）。

**既有非 S4 reader**：`read_non_terminal_runs`、`read_cancelling_runs`、Session/queued Run/wait readers 中的 `fetchall()` 均不在 S4 recovery call graph 中，未修改。

### 5. 业务分类未改写

`_classify_run` 方法（`recovery.py:349`）未被修改。新 `_StartupRecoveryBatchOperation.__call__()` 调用 `self.scanner._classify_run(transaction, run, self.policy, ...)` 的参数签名与旧 inline loop 完全一致。orphan proof、recovery dispatch limit、accepted-cancel deferral、WAITING diagnostic-only 逻辑均未变更。

`test_keyset_batches_are_bounded_and_stable_with_sequence_ties` 验证 actions 按 run_id 排序且无重复/遗漏。implementation report 明确声明 batch_size=2 下 ACCEPTED/WAITING/accepted-cancel CANCELLING 既有分类全部不变。

### 6. 无 scope creep

- S3 health lease / admission gate：`_execution_health.py` 不在 diff 中。未修改。
- S5 watchdog / cancel：`dispatch.py` 不在 diff 中。`defer_accepted_cancel_to_watchdog=True` 沿用既有参数，未改写 watchdog 行为。
- Service / CLI / Fins / Engine：无文件变更。
- 仅 `read_non_terminal_run_upper_watermark` 和 `read_non_terminal_runs_keyset_page` 两个新 durable reader；未修改 `_classify_run` 或状态迁移逻辑。

## Findings

未发现实质性问题。

所有六个 review focus 的代码实际行为与 plan Slice S4 冻结契约一致：
- `NonTerminalRunKeysetCursor(accepted_event_sequence, run_id)` 是 keyset/watermark 唯一 typed owner；SQL 使用严格 composite key comparison 和 `LIMIT ?`，无 OFFSET
- 每批独立 write transaction → commit 后同步投递 wake；accumulator 为 retry-local；`mark_ready()` 仅在全部 batch 成功后调用
- Recovery call graph 彻底不再使用 `read_non_terminal_runs()`、OFFSET 或 unbounded transaction
- 新增 `fetchall()` 仅一处且带 `LIMIT ?`；其他 `fetchall()` 命中均非 S4 reader
- `_classify_run` 方法未修改，orphan/accepted-cancel/WAITING/QUEUED/ACCEPTED 分类不漂移
- S3 health lease、S5 watchdog/cancel、Service/CLI/Fins/Engine 均无越界修改

## Open Questions

无。

## Residual Risk

- Watermark 读与 batch 写之间的并发 non-terminal Run 插入会落在 watermark 之外，由下一次 scan/scheduler 处理。这是计划预期行为，确认正确。
- 一个 batch commit 后、多个 wake callback 之间的 bridge 失败不是跨 callback 原子事务；已提交 batch 的 durable facts 已写入，后续 wake callback 失败会导致 opener fail closed（不 READY），但已写入的 facts 是 persistent 的。下一 healthy opener 通过幂等重放收敛到相同 durable 集合。该行为与 plan S4 item 3 "第N批失败不回滚已提交批次" 一致。
- Legacy `read_non_terminal_runs(...)` 仍存在于 `durable/state.py`，但不在 recovery call graph 中。plan 明确声明"删除该通用 reader 超出本 slice"，当前无风险。
