# WU-LAYER-01 Slice 2 Code Review — AgentDS

## 基本信息

- Reviewer: AgentDS
- Gate: code review
- Review target: 当前工作树相对 HEAD 的 Slice 2 diff
- Plan: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`
- Implementation artifact: `docs/reviews/wu-layer-01-slice2-terminal-shape-rules-codex-20260602.md`
- Review scope: `_row_rules.py`, `schema.py`, `state.py`, `test_state_schema.py`, `test_wait_record_state.py`, controller doc bookkeeping check

## 结论：PASS

无 blocking finding。所有审查维度均通过。3 个 non-blocking informational finding 记录如下。

---

## Findings

### Finding 1 — INFO: `_validate_sql_identifier` 校验范围最小，文档未标注边界

- **Severity**: INFO (non-blocking)
- **Evidence**: `dayu/host/durable/_row_rules.py:227-236`
- **问题**: `_validate_sql_identifier` 仅检查 identifier 是否为空字符串（`value == ""`），不做 SQL identifier 合法字符校验。函数名 `validate_sql_identifier` 暗示更宽的校验语义。
- **影响**: 当前无实际注入风险——所有 caller 传入的 `status_column` 均为模块私有常量或调用方硬编码字面量（`"status"`）。但函数名可能误导未来维护者在不可信输入上调用它。
- **建议**: 在 docstring 或行内注释中标注此函数只做 empty check，不做 injection 防护；调用者负责保证传入的是受控标识符。

### Finding 2 — INFO: WaitRecord status 常量与 Run/Attempt 来源不对称

- **Severity**: INFO (non-blocking)
- **Evidence**: `dayu/host/durable/_row_rules.py:31-51`
- **问题**: `TERMINAL_RUN_STATUS_VALUES` 和 `TERMINAL_ATTEMPT_STATUS_VALUES` 从 `dayu.host.api` 中 `RunStatus`/`AttemptStatus` enum `.value` 派生；而 `WAIT_RECORD_WAITING_STATUS_VALUE` 等五个 WaitRecord 常量是手写硬编码字符串（`"waiting"`, `"resolved"`, ...）。
- **为何不是 defect**: `WaitRecordStatus` 是 `StrEnum`，定义在 `state.py:148-155`，且其成员值引用 `_row_rules.py` 常量。`_row_rules.py` 受限于不得 import `state.py` 的依赖方向约束，无法从 `WaitRecordStatus` enum 反推常量值。这是有意设计选择，不是遗漏。
- **建议**: 若后续希望统一，可考虑将 `WaitRecordStatus` 提升至 `dayu.host.api`（属 WU-LAYER-02 或独立 work unit，不在 Slice 2 scope）。

### Finding 3 — INFO: row decode 尚未添加 terminal shape 校验（Slice 3 scope）

- **Severity**: INFO (non-blocking)
- **Evidence**: `state.py:764-796` (`run_row_from_host_row`), `state.py:799-819` (`attempt_row_from_host_row`), `state.py:863-...` (`wait_record_row_from_host_row`)
- **问题**: 三个 row decode 函数在构造 typed dataclass 后未调用 terminal shape validation helper。当前只有 insert-time Python validation（`_validate_run_for_insert`, `_validate_attempt_for_insert`, `_validate_wait_record_for_insert`）执行 terminal shape 检查。
- **确认非越界**: Plan Slice 3（Row Decode Error Boundary）明确要求 "add decode-time terminal shape checks for Run / Attempt / WaitRecord"。当前 Slice 2 未越界实现。
- **影响**: 如果 malformed durable row 被 SELECT 读出（例如通过 `PRAGMA ignore_check_constraints` 写入的 corrupted row），row decode 不会在转换阶段暴露出结构化的 `HostRowDecodeError`，而是让调用方拿到一个违反 terminal shape 规则的 typed row。这是 Slice 3 需要关闭的 gap。

---

## 逐项审查

### 1. `_row_rules.py` 模块边界

| 检查项 | 状态 | Evidence |
|---|---|---|
| durable-private（`_` 前缀模块） | PASS | `dayu/host/durable/_row_rules.py` |
| 未被 `__init__.py` re-export | PASS | `grep _row_rules __init__.py` → no matches |
| 不 import `state.py` | PASS | imports: `dayu.host.api`, `dayu.host.durable.errors` only |
| 不 import `schema.py` | PASS | 同上 |
| 不 import `dayu.runtime` | PASS | grep 确认无 runtime import |
| 不 import `dayu.engine/service/ui/fins` | PASS | grep 确认无跨层 import |
| `_validation.py` 不 import `_row_rules.py` | PASS | grep `_row_rules` in `_validation.py` → no matches |
| 职责边界：只承载 terminal shape | PASS | 无 scalar validation、无 row decode、无 schema bootstrap、无 transaction |

### 2. `schema.py` DDL CHECK 生成

| 检查项 | 状态 | Evidence |
|---|---|---|
| DDL CHECK 片段由 `_row_rules.py` helper 生成 | PASS | `schema.py:173-198` 调用 `terminal_event_refs_required_check_sql` 等 |
| 生成结果仍嵌入 `HOST_DURABLE_DDL` | PASS | `_HOST_RUNS_DDL` / `_HOST_ATTEMPTS_DDL` / `_HOST_WAIT_RECORDS_DDL` 分别 f-string 嵌入 |
| Slice 1 definition validation 未被破坏 | PASS | implementation artifact 确认 Slice 1 测试 rerun 通过；`test_fresh_bootstrapped_schema_matches_generated_expected_sql` 通过 |
| 状态常量同源 | PASS | `TERMINAL_RUN_STATUS_VALUES` / `TERMINAL_ATTEMPT_STATUS_VALUES` 从 `_row_rules.py` import，DDL CHECK 与 Python validation 使用同一套常量 |

### 3. `state.py` CAS terminal refs SQL

| 检查项 | 状态 | Evidence |
|---|---|---|
| `_TERMINAL_REFS_UNSET_WHERE_SQL` 只在 terminal mutation path | PASS | 所有 20 处引用均在 `UPDATE ... WHERE ... AND status = ?` 的 CAS 路径中，无 SELECT/read path 使用 |
| 由 `_row_rules.py` helper 生成 | PASS | `state.py:78` 调用 `terminal_event_refs_unset_where_sql(indent="          ")` |
| 非 f-string 注入 | PASS | 所有使用均为 f-string 模板嵌入，列名来自模块常量，状态值通过 `serialize_*_status()` |

### 4. WaitRecord `terminal_at IS NULL` 覆盖

| 检查项 | 状态 | Evidence |
|---|---|---|
| 单条 terminal CAS 包含 `AND terminal_at IS NULL` | PASS | `state.py:5047` — `_mark_wait_record_terminal_row` |
| 批量 cancel CAS 包含 `AND terminal_at IS NULL` | PASS | `state.py:2221` — `cancel_active_wait_records_for_run` |
| 四条 mark_wait_record_* 全部委托到同一条 helper | PASS | `mark_wait_record_resolved/failed/cancelled/lost_row` 均调用 `_mark_wait_record_terminal_row` |
| 无 production repair branch | PASS | 未发现对 corrupted row 的自动修复或静默纠正逻辑 |
| CAS 源状态均为 `waiting` | PASS | 两条路径 WHERE 子句中 `status = ?` 参数均为 `serialize_wait_record_status(WaitRecordStatus.WAITING)` |

### 5. Python validation 与 DDL/CAS 一致性

| 检查项 | 状态 | Evidence |
|---|---|---|
| Run terminal shape | PASS | `validate_terminal_event_refs_shape` + DDL CHECK（`_HOST_RUN_TERMINAL_REFS_REQUIRED_CHECK_SQL` + `_HOST_RUN_TERMINAL_REFS_UNSET_CHECK_SQL`）一致 |
| Attempt terminal shape | PASS | `validate_terminal_event_refs_shape` + DDL CHECK（`_HOST_ATTEMPT_TERMINAL_REFS_REQUIRED_CHECK_SQL` + `_HOST_ATTEMPT_TERMINAL_REFS_UNSET_CHECK_SQL`）一致 |
| WaitRecord terminal shape | PASS | `validate_wait_terminal_at_shape` + DDL CHECK（`_HOST_WAIT_TERMINAL_AT_CHECK_SQL`）+ CAS `AND terminal_at IS NULL` 一致 |
| WaitRecord 五种状态全覆盖 | PASS | waiting + 四种终态（resolved/failed/cancelled/lost）在 DDL CHECK、Python validation、CAS 谓词中均有对应规则 |

### 6. 测试覆盖

| 检查项 | 状态 | Evidence |
|---|---|---|
| terminal Run 缺少 ref → DDL CHECK 拒绝 | PASS | `test_run_terminal_shape_check_rejects_terminal_missing_ref` (4 个终态 parametrize) |
| non-terminal Run 携带 ref → DDL CHECK 拒绝 | PASS | `test_run_terminal_shape_check_rejects_non_terminal_ref` (multiple non-terminal statuses parametrize) |
| terminal Attempt 缺少 ref → DDL CHECK 拒绝 | PASS | `test_attempt_terminal_shape_check_rejects_terminal_missing_ref` |
| non-terminal Attempt 携带 ref → DDL CHECK 拒绝 | PASS | `test_attempt_terminal_shape_check_rejects_non_terminal_ref` |
| waiting WaitRecord 携带 terminal_at → DDL CHECK 拒绝 | PASS | `test_wait_record_ddl_rejects_waiting_terminal_at` |
| terminal WaitRecord 缺少 terminal_at → DDL CHECK 拒绝 | PASS | `test_wait_record_ddl_rejects_terminal_missing_terminal_at` |
| Python insert validation 与 DDL 一致 | PASS | `test_wait_record_python_validation_rejects_terminal_at_shape` |
| corrupted wait row 被 terminal CAS 拒绝 | PASS | `test_wait_record_terminal_cas_rejects_corrupted_waiting_terminal_at` — 使用 `PRAGMA ignore_check_constraints=ON` 构造 test-only corrupted row，assert CAS 返回 `CAS_LOST` 或 `INVALID_STATE` |
| Slice 1 rerun | PASS | implementation artifact 确认 `test_durable_schema.py` rerun 通过 |
| 测试只构造 corrupted row，无 production repair | PASS | `PRAGMA ignore_check_constraints` 只在测试函数内临时使用，生产代码无对应 bypass/repair 路径 |

### 7. Scope 越界检查

| 检查项 | 状态 | Evidence |
|---|---|---|
| 未实现 Slice 3 `HostRowDecodeError` | PASS | grep `HostRowDecodeError` 全仓 → no matches |
| 未处理 WU-LAYER-02 | PASS | 无 helper 下沉到 `dayu.runtime`；无 shared validation/JSON/redaction consolidation |
| 未修改 `dayu.runtime` | PASS | `_row_rules.py` 不 import runtime |

### 8. Docstring / Type / Signature

| 检查项 | 状态 | Evidence |
|---|---|---|
| `_row_rules.py` 所有公开函数有完整中文 docstring | PASS | 含 `:param`、`:returns`、`:raises` |
| `_validate_sql_identifier` 有完整中文 docstring | PASS | 同上 |
| 无 `Any` / `object` / 无类型参数 | PASS | 所有函数签名均完整类型标注 |
| 无 `hasattr` / `getattr` 用于 row decode | PASS | `_row_rules.py` 不涉及 row decode |
| 无 lazy import | PASS | 所有 import 均为模块顶层直接 import |

### 9. Controller doc bookkeeping

| 检查项 | 状态 | Evidence |
|---|---|---|
| implementation status 准确 | PASS | "WU-LAYER-01 Slice 2 implementation complete; code review pending" |
| accepted slice commits 准确 | PASS | 仅 Slice 1 (`02396e5`)，Slice 2 尚未 accept |
| current slice 准确 | PASS | "WU-LAYER-01 Slice 2 code review" |
| implementation artifact 路径正确 | PASS | 列出 Slice 1 + Slice 2 两个 artifact |
| code review artifacts 未遗漏 | PASS | 列出 Slice 1 三个 review artifact，Slice 2 review artifact 待本文件产出后补充 |

---

## Open Questions

无。

## Residual Risks

1. **`_validate_sql_identifier` 命名误导风险**: 函数名暗示 SQL identifier validation，但仅做 empty check。若未来 `_row_rules.py` 增加接受外部输入的新 caller，可能被误用。建议标注文档边界（见 Finding 1）。
2. **WaitRecord status 常量与 enum 来源不对称**: 当前设计受限于依赖方向约束，是合理的。若 `WaitRecordStatus` 未来移动位置，需同步更新 `_row_rules.py` 中的常量和 `state.py` 中的 enum 定义（见 Finding 2）。
3. **row decode 阶段 terminal shape 校验缺失**: 这是 Slice 3 的 scope，当前 Slice 2 正确未越界。需确保 Slice 3 实现时在 `run_row_from_host_row`、`attempt_row_from_host_row`、`wait_record_row_from_host_row` 中添加 decode-time terminal shape check（见 Finding 3）。

---

## Review Metadata

- 审查耗时: N/A
- 审查方法: 静态代码审查 + diff 逐文件比对 + grep 交叉验证
- 审查工具: Read, Grep
- 被审查文件总数: 5 source + 2 test + 2 doc artifact
