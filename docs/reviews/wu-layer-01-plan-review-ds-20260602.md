# WU-LAYER-01 Plan Review — AgentDS

**Reviewer**: AgentDS
**Date**: 2026-06-02
**Gate**: plan review
**Target**: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`
**Design source**: `docs/host/design.md`
**Control doc**: `docs/host/host-core-followup-implementation-control.md`

## 结论：PASS

Plan is code-generation-ready. 无 blocking finding。发现 2 条 medium、3 条 low 和 1 条 observation，均不影响 plan 进入 implementation gate。建议在 implementation 前以 plan clarification 形式处理 medium findings。

---

## Findings

### FIND-01 [MEDIUM] DDL CHECK 片段重组可能引入 schema.sql_master 不稳定

**Evidence**:
- Plan section 6.2 要求 `schema.py` 使用 `_row_rules.py` 的 `sql_string_list(...)` 和 `terminal_event_refs_required_check_sql(...)` 生成 DDL CHECK 片段（plan:133）
- Plan section 6.1 同时要求 Slice 1 对 `sqlite_master.sql` 做 definition 比较（plan:110-112）
- 当前 `_HOST_RUNS_DDL`（schema.py:347-439）和 `_HOST_ATTEMPTS_DDL`（schema.py:442-485）是静态 f-string，状态值直接内联

**问题**:
如果 Slice 2 的 DDL CHECK 片段重构与 Slice 1 的 definition validation 在同一轮实施，可能出现以下 cross-slice 问题：
1. Slice 2 修改 DDL 常量中的 CHECK 片段（从内联状态值改为从 `_row_rules.py` 导入的常量），导致 `sqlite_master.sql` 文本变化
2. Slice 1 的 definition validation 使用修改前的 DDL 生成 expected SQL，但实际 DB 的 `sqlite_master.sql` 是修改后的文本
3. 如果两个 slice 的 commit 顺序不当，中间 commit 可能出现 definition validation 自己报错

**影响**:
如果 Slice 1 先落地、Slice 2 后落地，Slice 2 的 DDL 常量修改会使 Slice 1 的 definition validation 对 fresh bootstrap 的 expected SQL 失效，导致 opener fail closed。

**建议修复**:
在 plan section 8 (Slice 切分) 中增加明确的 slice dependency 说明：
- Slice 2 必须在 Slice 1 之后实施，且 Slice 2 修改 DDL CHECK 片段后，必须重新运行 Slice 1 的 definition validation tests 验证 expected SQL 仍然匹配
- 或者：在 Slice 2 的 DDL CHECK 片段重构中，确保生成的 SQL text 与当前 `HOST_DURABLE_DDL` 产出的 `sqlite_master.sql` 逐字符一致（不只是语义一致），避免 definition validation 误报

---

### FIND-02 [MEDIUM] WaitRecord CAS `terminal_at IS NULL` 添加缺少显式 corruption scenario 测试要求

**Evidence**:
- Plan section 6.2（plan:138）要求 "For WaitRecord terminal updates, include `AND terminal_at IS NULL` alongside `status = waiting`"
- 当前代码 state.py:2200 `WHERE run_id = ? AND status = ?` 和 state.py:5060 `WHERE wait_id = ? AND status = ?` 均无 `terminal_at IS NULL`
- DDL CHECK（schema.py:662-667）已经约束 `status = 'waiting' AND terminal_at IS NULL`，所以正常路径不会出现 waiting + non-null terminal_at
- Plan section 13（plan:345-346）将此项列为 residual risk："Adding explicit terminal_at IS NULL to WaitRecord CAS predicates should be behavior-preserving for valid rows"

**问题**:
Plan 在 slice 2 expected assertions 中说 "CAS-lost classification remains unchanged except where a corrupted row with status=waiting and non-null terminal_at is now explicitly excluded by CAS predicate"（plan:241-242），但在 slice 2 的测试列表（plan:231-236）中没有显式列出这一 corruption scenario 的测试。

**影响**:
如果没有显式测试覆盖 corrupted row（`status=waiting` 且 `terminal_at IS NOT NULL`），CAS 行为变更可能未被验证。这个 scenario 正是新增 CAS 谓词的唯一语义差异点。

**建议修复**:
在 Slice 2 测试列表（plan:231-236）中增加一条：
- "corrupted wait record with `status=waiting` and non-null `terminal_at` is excluded by CAS predicate and classified as CAS lost"
- 测试需要使用 `PRAGMA writable_schema=ON` 或等价手段构造违反 DDL CHECK 的 corrupted row（与 plan:344 中对 table definition mismatch test 的技术手段一致）

---

### FIND-03 [LOW] `_row_rules.py` 与既有 `_validation.py` 的职责边界未定义

**Evidence**:
- Plan section 6.2 提议新增 `dayu/host/durable/_row_rules.py`（plan:120）
- `dayu/host/durable/_validation.py` 已存在，提供 `require_text`、`optional_text`、`require_int`、`optional_int` 等 scalar validation helper（state.py:35-41 import）
- Plan section 6.3 提议在 `state.py` 中新增 `_decode_scalar`、`_decode_required_text` 等 row decode helper（plan:153-158），它们的职责是将 `_validation` 的 `HostDurableError` 包装为 `HostRowDecodeError` 并附加 row_name 上下文

**问题**:
Plan 没有说明为什么不把 terminal shape rule constants 放在已有的 `_validation.py` 中，而是新建 `_row_rules.py`。两个模块都是 durable-private helper，职责划分需要明确。

**影响**:
低。`_row_rules.py` 的职责（terminal status constants + SQL fragment generation + terminal shape validation）与 `_validation.py`（scalar field validation）语义上可分，但 plan 应显式说明划分理由，避免 implementation agent 不确定该把新 helper 放在哪里。

**建议修复**:
在 plan section 6.2 的 Reasoning 段中增加一句话，说明 `_row_rules.py` 专门负责 terminal status 常量、terminal refs 规则和终端形状校验，与 `_validation.py` 的通用 scalar validation 分属不同语义域。

---

### FIND-04 [LOW] `HostRowDecodeError` 的 field_name 类型与行号信息不足

**Evidence**:
- Plan section 6.3（plan:150-151）定义 `HostRowDecodeError` 携带 `row_name: str` 和 `field_name: str | None`
- Plan section 6.3（plan:160-161）要求 decode failure 包括 "missing required selected column"

**问题**:
`field_name: str | None` 对于"整个行级别"的 decode 失败（如 terminal shape malformed）是合理的，但对于"缺列"场景，`field_name` 总会填具体列名，此时 `str | None` 的 None 分支只在非字段级别的失败中触发。但缺少一种场景：如果 SELECT 查询本身漏选了列（不在 `columns` tuple 中），`HostRow.get()` 会抛 `KeyError`。Plan 的 `_decode_required_text` wrapper 可以 catch 这个 `KeyError` 并转为 `HostRowDecodeError`，但 plan 没有明确说明这个 catch 点。

**影响**:
低。Implementation agent 需要在 `_decode_required_text` 实现中自行处理 `KeyError` -> `HostRowDecodeError` 的转换，plan 对此边界描述不足。

**建议修复**:
在 plan section 6.3 的 row decode helpers 描述中，明确 `_decode_required_text` 等 helper 需要 catch `KeyError`（来自 `HostRow.get()`）并转换为 `HostRowDecodeError`。

---

### FIND-05 [LOW] `sqlite_master.sql` normalization 策略需要更精确定义

**Evidence**:
- Plan section 6.1（plan:102）定义 `_normalize_schema_sql(sql: str) -> str` 为 "using whitespace normalization only, not semantic parsing"
- Plan section 13（plan:343-344）承认 "sqlite_master.sql comparison relies on SQLite catalog SQL generated by the same interpreter/runtime"

**问题**:
"Whitespace normalization only" 在实施层面不够精确。SQLite `sqlite_master.sql` 可能包含以下差异来源：
1. 标识符引用：`"host_runs"` vs `host_runs`（取决于 DDL 中是否用了双引号）
2. 多余空格：`CREATE TABLE host_runs(` vs `CREATE TABLE host_runs (`
3. 换行符：`\n` vs `\r\n`
4. `IF NOT EXISTS` 子句：SQLite 在 `sqlite_master.sql` 中会保留还是去除？

Plan section 13 将此列为 open question 并要求 tests 验证。这是正确的处理方式，但 plan 应给出 normalization 的最小定义（如：将连续空白符归一化为单个空格、去除首尾空白），让 implementation agent 有明确的起始点。

**影响**:
低。Implementation agent 可能需要多轮试验才能确定正确的 normalization 策略，但这已在 plan 的 stop conditions（plan:332）中兜底："Comparing generated sqlite_master.sql proves unstable across the same process / same SQLite version in normal tests."

**建议修复**:
在 section 6.1 的 `_normalize_schema_sql` 描述中给出最小 normalization spec：至少包含连续空白符归一化、首尾空白去除。其余细节留给 implementation 根据实际 `sqlite_master.sql` 输出调整。

---

## Observations

### OBS-01 Plan scope discipline is correct

Plan 的 non-goals（section 2）正确排除了 WU-LAYER-02 shared helper consolidation 和 runtime helper migration。Stop conditions（section 12）覆盖了所有关键越界场景。Section 4 的 affected files 与 section 8 的 allowed files per slice 一致。不越界到 Engine、Service、UI 或 `dayu.runtime`。

直接证据：
- Plan:13-24 明确 "不引入 ORM"、"不改变 public contract"、"不把 row dataclass 扩展为 domain object"
- Plan:22 明确 "不处理 WU-LAYER-02"

### OBS-02 Missing table/index fail-closed 覆盖正确识别

Plan section 3（plan:40-48）正确识别了已有的 fail-closed 测试覆盖，并引用了确切的代码行号：
- schema.py:1253-1280（bootstrap + validate）
- schema.py:1283-1305（validate 当前范围）
- schema.py:1332-1372（required tables/indexes 检查）
- tests/host/test_durable_schema.py:376-510（fail-closed 测试）

这些证据与 plan 的结论 "不能把缺表/缺索引 opener 静默修复当作未完成实现"（plan:8）一致。

### OBS-03 Terminal shape 三源漂移风险真实存在

Plan section 3（plan:53-61）正确识别了三套规则独立维护的问题：
1. DDL CHECK（schema.py:347-439 Run, schema.py:442-485 Attempt, schema.py:635-667 WaitRecord）
2. Python validation（state.py:4259-4307 Run insert, state.py:4310-4332 Attempt insert, state.py:4951-4955 WaitRecord）
3. CAS WHERE null-check（state.py:1799-1802, 2355-2357, 2440-2442 等约 20 处）

通过 `grep` 验证：`terminal_event_id IS NULL` 在 state.py 中出现 20 次，`terminal_at IS NULL` 出现 20 次。这些确实是手动重复的 CAS 谓词片段。

### OBS-04 `_is_terminal_attempt_status` 不存在

`_is_terminal_run_status`（state.py:5264-5276）存在，但没有对应的 `_is_terminal_attempt_status`。Plan 在 `_row_rules.py` 中定义了 `TERMINAL_ATTEMPT_STATUS_VALUES`（plan:123），但未指出这是一个新创建的基础设施而非已有代码的收敛。Implementation agent 应注意：Attempt terminal status 判定在当前代码中是通过 DDL CHECK 的 `status IN (...)` 和 Python validation 的内联逻辑实现的，没有统一的 helper 函数。

---

## Open Questions

无 blocking open question。Plan section 13 列出的 4 项 risk 均有合理的 mitigation：
1. `sqlite_master.sql` 稳定性 — 有 stop condition 兜底
2. Table definition mismatch 测试需 `PRAGMA writable_schema=ON` — 已限制在测试范围
3. WaitRecord CAS `terminal_at IS NULL` 添加 — 分类为 acceptable fail-closed
4. `HostRowDecodeError` subclass of `HostDurableError` — 已有测试兼容性分析

---

## Residual Risks

1. **DDL CHECK 重构与 definition validation 的 cross-slice 时序**: 见 FIND-01，建议在 slice dependency 中明确处理
2. **WaitRecord CAS corruption scenario 测试缺失**: 见 FIND-02，建议补充显式 corruption test
3. **`sqlite_master.sql` normalization 在 Python 3.11 sqlite3 上的稳定性**: Plan 已通过 stop condition 覆盖；如 implementation 阶段验证通过，风险自动关闭

---

## Verification Checklist

- [x] Plan 正确判断动机：缺表/缺索引 fail-closed 已覆盖，未重复实现
- [x] 剩余缺口（schema definition mismatch, terminal shape drift, row decode boundary）有直接代码证据
- [x] Schema invariant 方案同源于 `HOST_DURABLE_DDL`（通过 SQLite catalog SQL generation）
- [x] `_row_rules.py` 未过度设计（只持有 terminal status constants + SQL fragments + validation helpers，不是通用框架）
- [x] `_row_rules.py` 不违反 Host durable owner 边界（durable-private，不导入上层模块）
- [x] `HostRowDecodeError` subclass of `HostDurableError`，不成为 public contract
- [x] Slices 足够小且 allowed files 清晰
- [x] 测试覆盖 success signal（fail-closed, HostRowDecodeError, terminal shape consistency）
- [x] README/pyright 要求满足（section 9, 11）
- [x] 不越界到 WU-LAYER-02 或 runtime helper consolidation
- [x] 不引入 ORM、兼容 wrapper、公共接口变更

---

## Review Metadata

- Review 仅基于 plan text、design source、control doc 和 source code 直接证据
- 未修改任何 plan/source/test/README
- 未 commit / push
