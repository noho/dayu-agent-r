# Host Phase 8 P8-S1 Code Review Controller Adjudication - 2026-05-16

## Gate

当前 gate：P8-S1 `Projection Runner / Checkpoint / Typed Consumer Contracts` code review。

Implementation artifact：

- `docs/reviews/host-phase8-implementation-s1-projection-runner-20260516.md`

Code review artifacts：

- `docs/reviews/host-phase8-code-review-s1-mimo-20260516.md`
- `docs/reviews/host-phase8-code-review-s1-ds-20260516.md`

Truth plan：

- `docs/host/phase8-projection-core-event-stream-plan.md`

## Controller Verdict

P8-S1 implementation 符合 plan 的核心架构边界与阻塞条件：checkpoint 与 consumer write 同事务、failure 不推进 checkpoint、
runner 只接收 `HostTransactionRunner` 注入、无 forbidden import、无 weak typing、schema version 已 bump 到 5。

但 DS review 提出的 3 个测试覆盖缺口都指向 checkpoint / DDL 核心不变量，修复成本低且能显著降低后续维护回归风险。裁决：
进入 P8-S1 fix gate，fix scope 只允许补测试与 fix artifact，不修改生产逻辑。

## Accepted Findings

### P8S1-CR-001: Duplicate checkpoint advance rejection lacks test coverage

来源：DS P8S1-CR-001。

裁决：accepted current fix。

理由：生产代码当前使用 `event_sequence <= checkpoint.checkpoint_event_sequence` 拒绝倒退与重复推进，逻辑正确；但测试只覆盖倒退，
未覆盖相同 `event_sequence` 重复推进。该分支是 checkpoint 单调性核心不变量，必须补回归测试。

修复要求：在 `tests/host/test_projection_checkpoint.py` 增加重复推进同一 `event_sequence` 时抛出 `HostDurableError` 的断言。

### P8S1-CR-002: Non-positive checkpoint event_sequence rejection lacks test coverage

来源：DS P8S1-CR-002。

裁决：accepted current fix。

理由：`event_sequence <= 0` 是 checkpoint advance 的输入边界，虽然 EventLog sequence 正常从 1 开始，但防御分支应有明确测试。

修复要求：在 `tests/host/test_projection_checkpoint.py` 增加 `event_sequence=0` 与负数时抛出 `HostDurableError` 的参数化测试。

### P8S1-CR-003: Projection checkpoint CHECK constraint branches lack direct tests

来源：DS P8S1-CR-003。

裁决：accepted current fix。

理由：checkpoint DDL 的 `(0, NULL)` 与 `(>0, event_id)` 组合是 schema 不变量。当前测试覆盖负值与 FK 缺失，但没有直接覆盖
`cursor=0 + event_id != NULL`、`cursor>0 + event_id IS NULL` 两个 CHECK 违反分支。

修复要求：在 `tests/host/test_durable_schema.py` 增加两个 `sqlite3.IntegrityError` 断言，覆盖上述 CHECK 分支。

## Rejected Findings

无。

## Deferred Findings

MiMo / DS 提到的 P8-S2 `stream_run_events` 独立性、P8-S3 RunResult / Session timeline、后续 projection auto-catchup 均已由
plan 分配到后续 slice / phase，不属于 P8-S1 fix。

## Fix Scope

允许：

- `tests/host/test_projection_checkpoint.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/host-phase8-fix-s1-projection-runner-20260516.md`

禁止：

- 修改生产代码。
- 修改 plan、design、implementation-control、README 或其它 review artifacts。
- commit、push、PR 或进入下一 gate。

## Required Validation

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/host tests/host
git diff --check
```
