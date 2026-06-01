# WU-LIFE-01 + WU-LIFE-02 Slice A Fix Report

日期：2026-06-01
Role：gateflow fix worker
Controller：AgentController
Gate：fix slice A

## Scope

- 仅修复 controller accepted findings。
- 修改文件：
  - `tests/host/test_recovery_scan.py`
  - `docs/reviews/wu-life-01-02-fix-sliceA-codex-20260601.md`
- 未修改生产代码、schema、EventLog、Host public API、plan、README、control doc 或 Slice B 文件。
- 未 commit、未 push、未进入 re-review gate。

## Accepted Findings Fix Status

| Finding | 状态 | 修复证据 |
|---|---|---|
| A-MIMO-01 | fixed | `_active_run_observation()` 从 `transaction_runner.run_write(operation)` 改为 `transaction_runner.run_read(operation)`，与纯读 helper 语义一致。 |
| A-MIMO-02 | fixed | 回退旧代码上的无关机械 reflow；既有 assert、函数签名、`EventLogStore().append_event(...).row` 调用、`_event_types()`、`_event_type_count()`、`_event_payload_by_type()` 保持原格式。 |
| A-DS-01 | fixed | 同 A-MIMO-02；最终 diff 聚焦 Slice A matrix、tests、helpers 的语义新增。 |
| A-DS-02 | fixed | 将 WAITING matrix 拆为 `waiting-diagnostic-only-low-level`（existing）与 `waiting-durable-read-diagnostic-only`（new），并在 matrix test 中断言分类。 |
| A-DS-03 | fixed | 新增 `test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation`，直接构造 RUNNING + 缺失 dispatch row，断言 `ORPHAN_INCONCLUSIVE`、reason 与无 recovery/terminal fact；matrix row 改为 new coverage。 |
| A-DS-04 | fixed | `test_scan_waiting_public_visible_durable_state_remains_diagnostic_only` 改名为 `test_scan_waiting_durable_read_state_remains_diagnostic_only`，docstring 改为 durable-read 语义，不再暗示 public API。 |

## Validation

均在 `source .venv/bin/activate` 后运行。

```bash
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_orphan_classifier.py -q
```

结果：`33 passed in 0.34s`

```bash
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

## New Risks / Open Questions

- Blocking open questions：none。
- 新增 scanner 测试通过删除 dispatch row 构造 durable 缺口；这是测试内 deterministic fixture mutation，不改变生产 schema 或 public contract。
- 未发现新增 pyright 或测试风险。

## Residual Risk Classification

| Residual risk | 分类 | 说明 |
|---|---|---|
| RR-DUR-04 未做交易时长 instrumentation | retained non-blocking residual | Slice A 仍只用 proof matrix 与既有 projection-lag scanner 测试表达 durable truth；本 fix 未扩大为生产 instrumentation，符合 Slice A scope。 |
| stress repeated crash recovery terminal dedupe | non-goal | matrix 仍标注 non-goal；本 fix 未把 stress 纳入默认验证。 |
| WAITING public API path | not covered by current slice | 本 slice 明确使用 durable-read 证明，不声称覆盖 Host public API。 |

## Completion

fix slice A complete。
