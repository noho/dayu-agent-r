# PR #110 Review — MiMo

## Scope

- PR: https://github.com/noho/dayu-agent-r/pull/110
- Branch: `refactor/host-layer-followup-wu-layer-01-02`
- Base: `main`
- Review type: PR-level independent review
- Work units: WU-LAYER-01, WU-LAYER-02

## Findings

| ID | Severity | Category | Description | Status |
|---|---|---|---|---|
| F-01 | LOW | Behavioral drift | `diagnostic_text._BEARER_SECRET_PATTERN` 捕获组与旧引擎/Host 模式存在细微差异：(1) `Bearer` 前缀统一输出为大写 `Bearer`（旧代码也输出大写但原因不同）；(2) 分号 `;` 现在是 value 终止符（旧代码将分号纳入匹配值）。所有调用方测试通过，新行为在 `test_diagnostic_text.py` 中被锁住。 | Non-blocking; intentional consolidation |
| F-02 | NOTE | Intentional divergence | `llm_compaction._safe_outcome_text` 保留 Host 特有的截断形状（overflow 时返回前 240 字符 + `"..."`，总长 243），未使用 `truncate_diagnostic_text`（精确 `max_chars`）。Controller adjudication 已明确这是 intentional，`test_safe_outcome_text_preserves_existing_truncation_shape` 锁住此行为。 | Non-blocking; documented |

无 blocking、high 或 medium finding。

## 审查详情

### 1. WU-LAYER-01 Durable Row / Schema Changes

**与 design / control doc 一致性：PASS**

- `_row_rules.py` 新模块只承载终态状态常量、SQL 片段生成和形状校验，不导入 `state.py` / `schema.py`，不向上泄漏。`_row_rules.py:11` 只导入 `dayu.host.api`（公共契约）和 `dayu.host.durable.errors`（同层错误类型）。
- `schema.py` 中 DDL CHECK 表达式从手写内联字符串改为 `_row_rules.py` 函数生成，expected SQL 由 `HOST_DURABLE_DDL` 在内存 fresh DB 中自动导出，不存在第二份手写 DDL 真源。
- `state.py` 中 CAS `WHERE ... IS NULL` 谓词从手写内联改为 `_row_rules.terminal_event_refs_unset_where_sql` / `wait_terminal_at_unset_where_sql`，与 DDL CHECK、Python validation 同源。
- `HostRowDecodeError` 只在 `dayu.host.durable.errors` 定义，通过 `state.py` row decode 函数抛出，不导出到 Host public API。
- `_validate_required_object_definitions` 在 `validate_host_durable_schema` 末尾调用，校验 required table / index 的 SQLite catalog SQL 定义一致性，不会静默修复。

**未引入 Host durable truth 回退：PASS**

- `TERMINAL_RUN_STATUSES` 从 `frozenset((RunStatus.SUCCEEDED, ...))` 改为 `frozenset(RunStatus(value) for value in TERMINAL_RUN_STATUS_VALUES)`，终态集合只有一份真源在 `_row_rules.py`。
- `_is_terminal_run_status` 从手写 `status in (...)` 改为 `status in TERMINAL_RUN_STATUSES`，语义不变。
- `WaitRecordStatus` enum value 从字面量改为引用 `_row_rules` 常量，值不变。

**Schema 静默修复检查：PASS**

- `_validate_required_object_definitions` 在定义不匹配时抛出 `HostSchemaMismatchError`，不会尝试 DDL 修复。`_expected_schema_sql_by_name` 在内存 DB 中执行 DDL 生成 expected，再与目标 DB 比较，是 fail-closed 设计。

### 2. WU-LAYER-02 Runtime Diagnostic Text Consolidation

**Runtime 层中立：PASS**

- `dayu.runtime.diagnostic_text` 只导入 `re` 和 `typing`（标准库），不导入 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- 三个函数语义层中立：`contains_sensitive_diagnostic_value`（检测）、`redact_sensitive_diagnostic_values`（脱敏）、`truncate_diagnostic_text`（截断）。不理解 Exception、Run、Attempt 或 provider payload。

**Engine/Host policy 差异未被 runtime 吞掉：PASS**

- `agent.py`（Engine）使用 `contains_sensitive_diagnostic_value` + `truncate_diagnostic_text`，参数与旧内联实现一致。
- `compaction_operation.py`（Host）使用 `redact_sensitive_diagnostic_values` + `truncate_diagnostic_text`，参数与旧内联实现一致。
- `llm_compaction.py`（Host）使用 `redact_sensitive_diagnostic_values` 但保留 Host 特有的截断形状（总长 243 而非精确 240），由 controller adjudication 明确 intentional 并由测试锁住。

### 3. Rejected Scope 检查

**OpenAI diagnostic payload：未改。** `agent.py` 的 `_exception_diagnostic_message` / `_safe_log_message` 只处理异常消息文本，不涉及 OpenAI provider payload 结构。

**Runtime digest：未改。** `diagnostic_text` 不提供 digest 能力。

**Host durable canonical JSON / digest / timestamp：未改。** `codec.py` 中的 `format_utc_timestamp` / `parse_utc_timestamp` 和 canonical JSON 逻辑未被修改。

**Tool trace / EventLog / audit 语义：未改。** PR diff 中无 `tool_trace.py`、`event_log.py` 或 audit 相关文件变更。

### 4. 总控文档一致性

**Ready-to-open-draft-PR 状态：PASS**

- `gate` = `draft PR gate`，`implementation status` = `draft PR opened; PR review pending`。
- `active work unit` = `WU-LAYER-02`，`default next work unit` = `WU-LAYER-02`。

**PR URL：PASS** — `draft PR` = `https://github.com/noho/dayu-agent-r/pull/110`，与实际 PR 一致。

**Residual risk owner：PASS**

- `RR-CTX-SLICED-01` owner 从 `WU-LAYER-02 shared helper consolidation` 更新为 `future Host internal constant cleanup if concrete correctness risk appears`。
- `RR-ENGINE-01-01` 保持 `closed`。
- 无新增无 owner 的 open item。

### 5. README 同步

**PASS**

- `dayu/README.md:37` 新增 `diagnostic 文本脱敏与有界截断` 到 runtime 能力列表，新增 `diagnostic_text` 子模块描述。准确反映新增模块。
- `dayu/host/README.md:297` 更新 schema validation 描述，从 "完整当前 schema validation" 改为 "当前 schema validation，校验 schema version、required object 存在性与 required object 定义一致性"。准确反映新增 `_validate_required_object_definitions`。
- `tests/README.md` 有 +2/-1 变更，新增 `test_diagnostic_text.py` 描述。
- `dayu/runtime/__init__.py` docstring 同步更新。

### 6. 编码规范检查

**PASS**

- 无 `Any`、`object`、无类型参数、无类型返回值。
- 无 `getattr` / `hasattr`。
- 无兼容 wrapper、兼容 re-export。
- 无魔法数字 / 魔法字符串（schema 工具函数内的 SQL 关键字除外，属于工具 schema 例外）。
- 所有函数有完整中文 docstring。
- `_row_rules.py` 不向 `_validation.py` 泄漏，不成为通用验证框架。
- 无反向依赖：`runtime` 不导入 `host` / `engine`，`_row_rules.py` 不导入 `state.py` / `schema.py`。

### 7. 测试 / pyright 验证

**PASS**

- `pytest -q tests/runtime tests/engine/test_agent_phase2.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py tests/host/test_import_boundary.py` → **469 passed**。
- `pytest -q tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_run_attempt_transitions.py tests/host/test_import_boundary.py` → schema / row decode / terminal shape 相关测试通过。
- `python -m pyright dayu/ tests/ utils/` → **0 errors, 0 warnings, 0 informations**。

## Verification Summary

| 验证项 | 结果 |
|---|---|
| Target tests (469 passed) | PASS |
| Durable + schema + row decode tests | PASS |
| Import boundary tests | PASS |
| pyright (0 errors) | PASS |
| Schema definition validation tests (wrong index / mutated table) | PASS |
| Row decode error boundary tests (missing column / type / terminal shape) | PASS |
| Diagnostic text tests (detection / redaction / truncation / idempotency) | PASS |
| llm_compaction secret redaction + truncation shape tests | PASS |
| README sync accuracy | PASS |
| Control doc consistency | PASS |

## Residual Risk

| Risk | Severity | Owner | Note |
|---|---|---|---|
| `_ASSIGNED_SECRET_VALUE_PATTERN` 分号终止行为变化 | Low | Runtime diagnostic_text | 新 pattern 将分号视为 value 终止符，旧 pattern 将分号纳入匹配值。所有调用方测试通过，行为由测试锁住。若未来有分号出现在合法 secret value 中的场景，需重新评估。 |
| `llm_compaction._safe_outcome_text` 截断形状 diverges from `truncate_diagnostic_text` | Low | Host llm_compaction | Intentional per controller adjudication；返回总长 243 而非精确 240。测试锁住。 |

## Verdict

**PASS.** 无 accepted blocking / high / medium finding。PR 可进入 draft-PR-pass。
