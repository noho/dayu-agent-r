# WU-LAYER-01 Slice 2 Terminal Shape Rules Implementation Artifact

## 基本信息

- Agent: AgentCodex / WU-LAYER-01 implementation Slice 2
- Gate: implementation
- Scope: Slice 2 Terminal Shape Rule Owner
- Design source: `docs/host/design.md`
- Control doc: `docs/host/host-core-followup-implementation-control.md`
- Accepted plan: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`
- Accepted Slice 1 commit: `02396e5`

## 改动文件

- `dayu/host/durable/_row_rules.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_wait_record_state.py`

未修改 `dayu/host/durable/__init__.py`，`_row_rules.py` 未被 re-export。
未修改 `dayu/host/durable/_validation.py`，该模块仍只承载 scalar validation。
`docs/host/host-core-followup-implementation-control.md` 在进入本 slice 前已有 controller 修改，本次未回滚、未覆盖。

## 实施内容

- 新增 durable-private `_row_rules.py`，集中承载：
  - Run terminal status values；
  - Attempt terminal status values；
  - WaitRecord waiting / terminal status values；
  - Run / Attempt terminal refs DDL CHECK SQL helper；
  - Run / Attempt terminal refs CAS unset SQL helper；
  - WaitRecord terminal_at DDL CHECK SQL helper；
  - WaitRecord terminal CAS `terminal_at IS NULL` SQL helper；
  - Run / Attempt terminal refs shape validation helper；
  - WaitRecord terminal_at shape validation helper。
- `schema.py` 的 Run / Attempt / WaitRecord DDL CHECK 片段改为由 `_row_rules.py` helper 生成，仍统一进入 `HOST_DURABLE_DDL`。
- `state.py` 的 Run / Attempt terminal refs Python validation 改为调用 helper。
- `state.py` 的 repeated Run / Attempt CAS terminal refs null-check SQL 改为同一 helper-generated constant。
- WaitRecord 单条 terminal CAS 与 batch cancel active waits 的 `status = waiting` 源条件旁显式增加 `terminal_at IS NULL`。
- WaitRecord Python insert validation 改为调用 `_row_rules.py` 的 terminal_at shape helper。

## 测试补强

- `tests/host/test_state_schema.py`
  - 覆盖 terminal Run 缺少 terminal ref 时 DDL CHECK 拒绝。
  - 覆盖 non-terminal Run 携带 terminal ref 时 DDL CHECK 拒绝。
  - 覆盖 terminal Attempt 缺少 terminal ref 时 DDL CHECK 拒绝。
  - 覆盖 non-terminal Attempt 携带 terminal ref 时 DDL CHECK 拒绝。
- `tests/host/test_wait_record_state.py`
  - 覆盖 waiting WaitRecord 携带 `terminal_at` 时 DDL CHECK 拒绝。
  - 覆盖 terminal WaitRecord 缺少 `terminal_at` 时 DDL CHECK 拒绝。
  - 覆盖 WaitRecord Python insert validation 与 DDL terminal_at shape 一致。
  - 覆盖测试专用 corrupted `status=waiting AND terminal_at IS NOT NULL` row 被 terminal CAS 拒绝，并分类为 `CAS_LOST` 或 `INVALID_STATE`；生产代码未添加 repair branch。

## 验证结果

命令：

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_run_attempt_transitions.py
```

结果：`115 passed in 1.01s`。

命令：

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

## Slice 1 Rerun 结果

已重新运行 `tests/host/test_durable_schema.py`，包含 Slice 1 schema definition validation 覆盖。结果随目标 pytest 集合一起通过。

本 Slice 修改了 Run / Attempt / WaitRecord DDL CHECK 的生成方式，但 fresh bootstrap 与 expected SQLite catalog SQL 仍同源于当前 `HOST_DURABLE_DDL`；`test_fresh_bootstrapped_schema_matches_generated_expected_sql` 已通过，说明 opener 不会对 fresh DB 误报 definition mismatch。

## README 决策

Checked-no-change: 未修改 `dayu/host/README.md`。

原因：本 Slice 只收口 durable-private terminal shape rule owner，不改变 Host public contract、分层边界或开发手册中需要暴露的稳定行为。README 现有 durable foundation 描述“主连接与 secondary durable connections 都会执行完整当前 schema validation”仍准确；Slice 1 的 required object definition validation 也已由该表述覆盖。

## Residual Risks / 未覆盖项

- 未实现 Slice 3 `HostRowDecodeError`，因此 row decode malformed terminal shape 的稳定错误类型仍由后续 Slice 3 负责。
- 未处理 WU-LAYER-02，也未把任何 helper 下沉到 `dayu.runtime`。
- 未改变现有 Run / Attempt terminal transition 语义；本 Slice 只收口规则 owner 与 null-check SQL 片段。

## 完成状态

Slice 2 implementation complete。
未 commit、未 push、未 open PR，未进入 review gate。
