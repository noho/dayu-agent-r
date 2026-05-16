# Code Review

## Scope

- Mode: current changes (uncommitted workspace changes)
- Branch: feat/host-phase8-projection-core-event-stream
- Base: main (Phase 8 plan commit b85fd8e)
- Output file: docs/reviews/host-phase8-code-review-s1-ds-20260516.md
- Included scope: P8-S1 plan-allowed files only
- Excluded scope: P8-S2/S3 files, Engine/Service/UI/Fins/Runtime, command path, admission, waiting, dispatch, recovery, audit, tool trace, outbox, memory modules
- Parallel review coverage: 无（单 reviewer 逐链路走读）
- Truth plan: docs/host/phase8-projection-core-event-stream-plan.md
- Implementation artifact: docs/reviews/host-phase8-implementation-s1-projection-runner-20260516.md

### Review Entry Points Walked

1. `bootstrap_host_durable_store` → `HOST_DURABLE_DDL` → `PROJECTION_DDL` → `_HOST_PROJECTION_CHECKPOINTS_DDL` / `_HOST_PROJECTION_FAILURES_DDL`
2. `ProjectionRunner.__init__` → `run_once` → `_ensure_checkpoint` → `_process_next_event` → `advance_projection_checkpoint` / `clear_projection_failure` / `_record_failure`
3. `ensure_projection_checkpoint` → `read_projection_checkpoint` → `INSERT` init path
4. `advance_projection_checkpoint` → validation → `UPDATE` → read-back
5. `write_projection_failure` → validation → INSERT/UPDATE with `failure_count` increment
6. `projection_event_view_from_row` → `payload_object` → `EventLogRow.payload_json` parse
7. `ProjectionEventFilter.matches` → `ProjectionEventClassFilter.matches` → OR/AND logic
8. All test entry points against plan-required invariants

### Blocking Checks

| Check | Result | Evidence |
|-------|--------|----------|
| checkpoint advancing outside same transaction as consumer write | PASS | `_process_next_event` 内 `consumer.apply_event(transaction, event)` 与 `advance_projection_checkpoint(transaction, ...)` 在同一 `run_write()` lambda 内；失败时 `run_write` ROLLBACK 回滚全部 |
| failure row advancing checkpoint | PASS | `_record_failure` 在独立 `run_write()` 中写 failure row，不调用 `advance_projection_checkpoint`；失败 transaction 已回滚 |
| runner opening its own connection or using public command facade | PASS | `ProjectionRunner` 只接收注入的 `HostTransactionRunner`，不持有 `sqlite3.Connection`，不导入 `HostCommandHandle` |
| untyped Any/object/raw payload boundary | PASS | `ProjectionEventView.payload: Mapping[str, JsonValue]`，无 `Any`、`object`、裸容器 |
| projection importing Host mutators or Engine/runtime/service/ui/fins | PASS | `dayu/host/projection.py` 和 `dayu/host/durable/projection.py` 的 import 均由 `test_projection_modules_do_not_import_forbidden_layers_or_mutators` 守卫，无违规 |
| schema mismatch | PASS | DDL 与 plan §3.1/§3.2 一致；`HOST_SCHEMA_VERSION` 从 4 bump 到 5 |
| missing tests for critical invariants | PASS（附 finding） | 关键不变量均有测试覆盖；发现 2 个 test coverage gap（见 Findings） |

## Findings

### P8S1-CR-001-已发现-中-test_coverage-advance_projection_checkpoint 重复推进拒绝未覆盖测试

- **入口/函数**: `advance_projection_checkpoint` (dayu/host/durable/projection.py:138)
- **文件(行号)**: dayu/host/durable/projection.py:163
- **输入场景**: 对同一 consumer，先用 `event_sequence=N` 推进 checkpoint 成功，再用相同 `event_sequence=N` 再次调用 `advance_projection_checkpoint`
- **实际分支**: 代码 `if event_sequence <= checkpoint.checkpoint_event_sequence` （行 163），`<=` 条件正确同时覆盖倒退与重复推进。重复推进时进入 `raise HostDurableError("projection checkpoint cannot move backwards")` 分支
- **预期行为**: 重复推进被拒绝并抛出 `HostDurableError`
- **实际行为**: 生产代码正确拒绝；但测试 `test_advancing_checkpoint_backwards_is_rejected` 只覆盖倒退场景（event-2 后倒退到 event-1），未覆盖相同 event_sequence 的重复推进
- **直接证据**:
  - 生产代码行 163: `if event_sequence <= checkpoint.checkpoint_event_sequence` — 代码正确
  - 测试文件 tests/host/test_projection_checkpoint.py:129-154 — 只测试 event-2 → event-1 倒退，未测试 event-2 → event-2 重复
- **影响**: 若未来维护中误将 `<=` 改为 `<`，重复推进将静默通过，导致同一 event 被重复计为 checkpoint 推进。当前正确，但缺乏回归守护
- **建议改法和验证点**: 在 `test_advancing_checkpoint_backwards_is_rejected` 中增加相同 `event_sequence` 重复推进拒绝断言；或在独立 test case 中覆盖
- **修复风险（低）**: 纯测试补充，不影响生产行为
- **严重程度（中）**: 生产代码正确但缺乏回归测试守护核心不变量

### P8S1-CR-002-已发现-低-test_coverage-advance_projection_checkpoint 零值与负值 event_sequence 拒绝未覆盖测试

- **入口/函数**: `advance_projection_checkpoint` (dayu/host/durable/projection.py:138)
- **文件(行号)**: dayu/host/durable/projection.py:160
- **输入场景**: 调用 `advance_projection_checkpoint` 时传入 `event_sequence=0` 或 `event_sequence=-1`
- **实际分支**: `if event_sequence <= _INITIAL_CHECKPOINT_SEQUENCE:` （`_INITIAL_CHECKPOINT_SEQUENCE=0`），命中后 `raise HostDurableError("projection checkpoint event_sequence must be positive")`
- **预期行为**: 抛出 `HostDurableError`
- **实际行为**: 生产代码正确拒绝；无显式测试覆盖此分支
- **直接证据**: 生产代码行 160-161；测试文件中无该分支的显式断言
- **影响**: 当前无直接影响，但缺少该防御边界的显式测试
- **建议改法和验证点**: 增加参数化测试：`event_sequence=0` 和 `event_sequence=-1` 均应抛出 `HostDurableError`
- **修复风险（低）**: 纯测试补充
- **严重程度（低）**: 防御性代码的测试 gap，实际运行中 EventLog sequence 从 1 开始

### P8S1-CR-003-已发现-低-test_coverage-schema CHECK 约束分支覆盖不完整

- **入口/函数**: `test_projection_schema_constraints_reject_invalid_rows` (tests/host/test_durable_schema.py:264)
- **文件(行号)**: tests/host/test_durable_schema.py:264-325
- **输入场景**: CHECK 约束 `(checkpoint_event_sequence = 0 AND checkpoint_event_id IS NULL) OR (checkpoint_event_sequence > 0 AND checkpoint_event_id IS NOT NULL)` 有两个违反分支：cursor=0 时 event_id 非 NULL；cursor>0 时 event_id 为 NULL
- **实际分支**: 当前测试只覆盖了 negative checkpoint_event_sequence、zero failure_count、missing FK event_id 三个场景
- **预期行为**: CHECK 约束两个分支均应被测试覆盖，确认 SQLite 拒绝非法行
- **实际行为**: 两个 CHECK 违反分支（cursor=0+event_id!=NULL, cursor>0+event_id=NULL）未显式测试
- **直接证据**: 测试行 264-325 — 测试三个 `IntegrityError` 场景，均不命中上述 CHECK 分支
- **影响**: 若 DDL CHECK 书写错误（例如将 AND/OR 写反），当前测试可能无法捕获
- **建议改法和验证点**: 增加两条 INSERT 测试：(1) `checkpoint_event_sequence=0` + `checkpoint_event_id='some-id'`；(2) `checkpoint_event_sequence=1` + `checkpoint_event_id=NULL`；均断言 `IntegrityError`
- **修复风险（低）**: 纯测试补充
- **严重程度（低）**: DDL 已在 PRAGMA 层定义，可通过 `PRAGMA table_info` 间接验证，但直接行为测试覆盖更完整

## Open Questions

- 无

## Residual Risk

- **P8-S2 覆盖**: `stream_run_events` cursor truth 与 projection checkpoint/failure 独立性 — 由 P8-S2 测试守护
- **P8-S3 覆盖**: RunResult / Session timeline idempotent consumer 与 repair helper — 由 P8-S3 实现与测试
- **当前 Slice 未覆盖**:
  - 多 consumer 并发 `run_once` 时，不同 consumer 的 checkpoint 各自独立，无冲突风险 — 但无显式并发测试。当前 runner 不暴露给并发调用方，单线程调用语义下安全
  - `limit` 超大值（如 `10**9`）在 EventLog 为空时的行为 — 代码在 `len(rows)==0` 时正确 break，但循环 `for _index in range(limit)` 创建了 `range(10**9)` 迭代器。Python 中 `range` 对象惰性求值，不会分配内存，无实际问题
  - `_record_failure` 中 `run_write` 失败（如 DB 损坏）会直接传播异常、中断 `run_once` — 这是合理行为：无法记录 failure 时 runner 不应继续
- **README 同步**: `tests/README.md` 已更新 Phase 8 projection 相关测试命令与层级描述；`dayu/host/README.md` 按 S1 决策未更新（S1 仅新增内部 projection core contracts，未改变 Host developer manual facts）
- **Scope creep**: 未发现 — 未修改任何 P8-S2/S3 文件或 plan 禁止的模块

## Verdict

**PASS** — 3 个 test coverage gap findings，均为 Low-Medium 严重度。无 blocking finding。所有 plan-defined blocking checks 均已通过逐行代码走读和测试验证确认。关键不变量（同事务原子性、失败不推进 checkpoint、import 边界、类型严格性、schema 合规）均已正确实现且被测试覆盖。
