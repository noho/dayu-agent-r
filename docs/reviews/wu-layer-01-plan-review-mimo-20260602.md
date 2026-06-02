# WU-LAYER-01 Plan Review — AgentMiMo

- Reviewer: AgentMiMo
- Date: 2026-06-02
- Target: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`
- Design source: `docs/host/design.md`
- Control doc: `docs/host/host-core-followup-implementation-control.md`
- Gate: plan review

## 结论：PASS

Plan code-generation-ready。无 blocking finding。以下为 medium/low findings 和 open questions。

---

## Findings

### M-01: `_expected_schema_sql_by_name` 需要证明 `sqlite_master.sql` 稳定性（Medium）

**Evidence**: plan section 6.1, `dayu/host/durable/schema.py:1320` (`_bootstrap_fresh_schema`)

**问题**: plan 提出创建 in-memory SQLite DB 执行 `HOST_DURABLE_DDL`，然后读 `sqlite_master.sql` 作为 expected 定义。这依赖 SQLite 在同一进程/同一版本下对 `CREATE TABLE IF NOT EXISTS` 的 `sqlite_master.sql` 输出是稳定的。plan 自身在 section 13 Risks 中承认了这一点，但没有给出验证策略的具体断言形式。

**影响**: 如果 `sqlite_master.sql` 格式化在不同 Python 3.11 补丁版本或不同 SQLite 编译选项间有差异，测试会 false-fail。这不是 blocking 风险（同一进程内比较是稳定的），但测试必须显式证明这一点。

**建议修复**: Slice 1 测试中增加一个 dedicated test：对 fresh in-memory DB 执行 `HOST_DURABLE_DDL`，读回 `sqlite_master.sql`，断言 `_expected_schema_sql_by_name()` 返回值与直接读取一致。这既是 self-test 也是稳定性证明。plan 已在 section 13 Risks 中提到此风险，但 Slice 1 测试列表中没有对应的显式测试条目。

### M-02: `_row_rules.py` 引入新模块但 plan 未明确其 `__all__` 或 import 边界（Medium）

**Evidence**: plan section 6.2, section 7

**问题**: plan 定义 `_row_rules.py` 为 durable-private 模块，列出了它可 import 的依赖（`dayu.host.api`、`dayu.host.durable.errors`），但没有明确 `schema.py` 和 `state.py` 如何 import 它（直接 import 具体符号还是 import module）。由于 `_row_rules.py` 同时被 DDL 生成（`schema.py`）和 Python validation（`state.py`）消费，如果未来有人从 `state.py` 之外 import 它，可能破坏 durable-private 边界。

**影响**: 低。当前 plan 已明确 `_row_rules.py` 不得被 `dayu.runtime` 或上层 import。但作为 code-generation-ready plan，建议明确 import 方式为 `from dayu.host.durable._row_rules import ...`（具体符号 import），不 re-export。

**建议修复**: 在 section 7 Exact Change Rules 中补充一条：`_row_rules.py` 的符号只通过 `from dayu.host.durable._row_rules import ...` 直接导入，不在 `dayu/host/durable/__init__.py` 中 re-export。

### L-01: `HostRowDecodeError` 的 `row_name` / `field_name` 属性命名可能与现有 `_require_text` helper 的 `field_name` 参数混淆（Low）

**Evidence**: plan section 6.3, `dayu/host/durable/state.py:742-774`

**问题**: 现有 `_require_text(..., field_name="run_id")` 已经使用 `field_name` 参数。`HostRowDecodeError` 也计划携带 `field_name: str | None`。两者语义一致（都是列名），命名一致是合理的，但 `_require_text` 当前在失败时抛的是 `HostDurableError`，不是 `HostRowDecodeError`。plan 要求把 `_require_text` 的失败包装为 `HostRowDecodeError`，这改变了现有错误路径。

**影响**: 低。现有调用方 catch `HostDurableError`，`HostRowDecodeError` 是其子类，不影响行为。但需要确认 `_require_text` / `_require_int` 等 helper 是否直接改为抛 `HostRowDecodeError`，还是由新的 `_decode_scalar` 等 wrapper 捕获后重新抛出。plan 说"Add row decode private helpers in `state.py`"，暗示是新 helper 包装旧 helper，这是正确方向。

**建议修复**: 无需修改 plan，但实现时应确保 `_require_text` 等现有 helper 不改签名/错误类型，由新的 `_decode_*` helper 在外层捕获 `HostDurableError` 并包装为 `HostRowDecodeError`。

### L-02: Slice 2 allowed files 列出 `test_run_attempt_transitions.py` 但条件是 "only if CAS SQL behavior tests need adjustment"（Low）

**Evidence**: plan section 8, Slice 2 allowed files

**问题**: 这个条件是合理的，但如果 Slice 2 实现中 CAS SQL 变化确实触及了 transition tests，那么 Slice 2 的范围就会扩大。plan 没有说明这种情况下是否需要停止并重新评估 slice 边界。

**影响**: 低。plan 的 stop conditions (section 12) 已覆盖"existing transition tests reveal a real behavior mismatch"的情况。

**建议修复**: 无需修改。实现 agent 应在 Slice 2 开始时先运行 `test_run_attempt_transitions.py` 确认 baseline，再决定是否需要修改。

### L-03: plan section 6.2 列出的 SQL helper 函数签名缺少返回类型细节（Low）

**Evidence**: plan section 6.2

**问题**: `terminal_event_refs_required_check_sql(...)` 和 `terminal_event_refs_unset_check_sql(...)` 的签名只写了返回 `str`，但没有说明返回的是完整 CHECK 约束片段（如 `terminal_event_id IS NOT NULL AND terminal_event_sequence IS NOT NULL AND terminal_at IS NOT NULL`）还是只返回部分条件。对于 `terminal_event_refs_unset_where_sql(...)` 返回的是 WHERE 片段还是完整 SQL 语句也没有明确。

**影响**: 低。实现 agent 可以从 DDL CHECK 和 CAS WHERE 的现有文本推导。

**建议修复**: 无需修改 plan。实现时以现有 DDL CHECK 文本和 CAS WHERE 文本为 truth。

---

## Open Questions

1. **`_expected_schema_sql_by_name` 是否需要 normalize 大小写？** plan 说 `_normalize_schema_sql` 使用 whitespace normalization only。但 SQLite 的 `sqlite_master.sql` 输出是否会保留原始 DDL 的大小写？如果 `HOST_DURABLE_DDL` 中写了 `TEXT` 而 SQLite 输出变成 `TEXT`（一致），则无需大小写 normalize。但如果 SQLite 标准化了某些关键字大小写，可能需要额外处理。建议实现 agent 在 Slice 1 开始时先做一个 quick check。

2. **Slice 3 的 `_decode_enum` 实现策略**: plan 说"only if it remains narrowly typed without `Any` / `object`; otherwise call existing enum deserializers inside a `try` block and wrap `HostDurableError`"。现有 `deserialize_run_status` / `deserialize_attempt_status` 已经存在且返回 typed enum。建议直接在 `_decode_*` helper 中调用它们并在 `except HostDurableError` 中包装为 `HostRowDecodeError`，不需要额外的 `_decode_enum` 抽象。

3. **WaitRecord CAS 变化是否影响 `resolve_wait` 路径？** plan section 6.2 提到为 WaitRecord terminal update 增加 `AND terminal_at IS NULL` CAS 谓词。这会影响 `resolve_wait` 的 UPDATE WHERE 子句。需要确认 `resolve_wait` 的现有 CAS 谓词是否已经包含 `terminal_at IS NULL`。从 `state.py` 的代码看，WaitRecord 的 CAS 谓词分布在多处，需要实现 agent 逐一核对。

---

## Residual Risks

1. **`sqlite_master.sql` 跨版本稳定性**: 同一进程内稳定，但跨 Python/SQLite 补丁版本可能有格式差异。测试应证明当前环境稳定性，不假设跨版本稳定。
2. **`PRAGMA writable_schema=ON` 测试技巧**: plan 提到可能需要此 pragma 来模拟 corrupted same-name table DDL。这是 acceptable test-only 技巧，但实现时应确保测试结束后 pragma 被正确关闭。
3. **CAS 谓词变化对 corrupted row 的影响**: 增加 `terminal_at IS NULL` 到 WaitRecord CAS 会使 corrupted row（`status=waiting` 但 `terminal_at IS NOT NULL`）从 CAS updated 变为 CAS lost。这是 fail-closed 行为，但应在实现报告中记录。

---

## 对 plan 核心判断的审查

### 动机判断：成立

Plan 正确识别了三个真实缺口：
- schema validation 只验证 existence 不验证 definition — 直接证据 `schema.py:1286` docstring 确认。
- terminal shape 规则三处维护（DDL CHECK、Python validation、CAS WHERE）— 直接证据 `schema.py:398-432`、`state.py:4259-4307`、`state.py:1799-1802` 确认。
- row decode 缺列抛 `KeyError` 不是稳定边界 — 直接证据 `transaction.py:112-123` 确认 `HostRow.get` 缺列抛 `KeyError`。

Plan 正确排除了"缺表/缺索引 fail-closed"作为本轮缺口（已有测试覆盖 `test_durable_schema.py:376-510`）。

### schema invariant 方案：同源性成立

`_expected_schema_sql_by_name()` 通过执行 `HOST_DURABLE_DDL` 生成 expected SQL，与 fresh bootstrap 使用同一 DDL 文本，是真正同源。比较的是 SQLite 生成的 catalog SQL，不是手写字符串，避免了 format drift。

### terminal rule helper：未过度设计

`_row_rules.py` 只承载 terminal status 常量、SQL 片段生成和 Python validation helper，不是通用验证框架。它不抽象任意 validation，不引入 factory/profile/query 接口。符合"最小化满足需求"。

### HostRowDecodeError：合理，不泄漏

作为 `HostDurableError` 子类，保持 durable-internal 定位。现有 catch `HostDurableError` 的调用方无需修改。plan 明确不改 public exports。

### Slices 足够小

4 个 slice 各有明确 allowed files、exact changes 和 expected assertions。Slice 1 纯 schema，Slice 2 纯 terminal rules，Slice 3 纯 row decode，Slice 4 纯 verification/doc。依赖方向清晰（Slice 2 依赖 Slice 1 的 schema helpers，Slice 3 独立于 Slice 1/2）。

### 未越界到 WU-LAYER-02

Plan section 2 明确"不处理 WU-LAYER-02 的 shared helper consolidation，不把 Host durable 专用规则下沉到 `dayu.runtime`"。`_row_rules.py` 是 Host durable-private，不进 `dayu.runtime`。
