# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: 7eb9f128
- Output file: docs/reviews/wu-semantic-ownership-01-p3-j-s2-code-review-ds.md
- Review agent: DS
- Included scope (P3-J S2 uncommitted, per controller directive):
  - dayu/host/queue_policy.py
  - dayu/host/api.py
  - dayu/host/admission.py
  - dayu/host/durable/state.py
  - dayu/host/durable/run_transition.py
  - dayu/host/durable/schema.py
  - dayu/host/durable/read_model.py
  - dayu/host/read_model.py
  - dayu/host/README.md
  - tests/host/test_durable_schema.py
  - tests/host/test_projection_read_model.py
  - tests/host/test_compact_pipeline.py
  - tests/host/test_accepted_result_projection.py
  - tests/host/test_compact_material.py
  - docs/reviews/wu-semantic-ownership-01-p3-j-s2-implementation-codex.md
  - docs/reviews/wu-semantic-ownership-01-p3-j-s2-controller-validation.md
- Excluded scope: AGENTS.md, CLAUDE.md (project instruction updates, out of S2); all other dirty/untracked files outside controller scope.
- Parallel review coverage: 无。本次审查范围集中，由主 reviewer 单线逐链路走读完成。

## Controller Adjudication Targets

逐条核对总控裁决目标：

1. **S2 只解决 queue_policy owner / AdmissionPolicy deletion / host_runs.queue_policy CHECK / RunResultRow.terminal_status typed row surface** — 确认。所有改动都在这四条边界内，未扩散到 P3-J S3 idempotency/descriptor kind 或 S4 legacy config。
2. **不要把 P3-J S3 idempotency/descriptor kind 或 S4 legacy config 当作 S2 defect** — 确认。未将 S3/S4 范围事项当作 finding 报告。
3. **`execution_target` 不应闭集化** — 确认。`host_runs.execution_target` 仍然为 `TEXT NOT NULL`，无 CHECK 闭集约束；所有校验点均为 `_require_non_empty_text`。
4. **重点审 semantic ownership drift、queue policy owner 覆盖、AdmissionPolicy 兼容残留、DDL/schema version、RunResultRow typed boundary、README 是否只写当前稳定事实、测试是否固化错误语义** — 以下逐条展开。

## 逐链路走读

### 链路 1：queue_policy 从 public request 到 durable persistence

**入口**: `StartRunRequest.__post_init__` (api.py:1819)
- `parse_run_queue_policy(self.queue_policy)` → 首次校验，非空 + 闭集。

**→ Admission**: `HostAdmissionService.start_run()` (admission.py:529)
- `policy = parse_run_queue_policy(request.queue_policy)` → 二次解析，得到 `RunQueuePolicy` enum。
- 分支选择 (`_StartRunOperation._handle_active_run`, admission.py:1018,1024): `RunQueuePolicy.REJECT` / `RunQueuePolicy.ATTACH_ACTIVE` 比较 — enum 比较，无误。
- `_create_queued_admission_result` / `_create_accepted_admission_result` / `_create_source_related_admission_result`: 均传递 `RunQueuePolicy` enum 或 `RunQueuePolicy.QUEUE`，不再使用裸字符串。

**→ Durable transition**: `_validate_common_create_input` (run_transition.py:5968-5971)
- `parse_run_queue_policy(queue_policy)` → 校验通过 owner。
- `_run_accepted_event_request` (run_transition.py:2999-3001): `serialize_run_queue_policy(parse_run_queue_policy(request.queue_policy))` → EventLog payload 写入规范化文本。

**→ Durable state write**: `insert_run` (state.py:2702)
- `serialize_run_queue_policy(parse_run_queue_policy(run.queue_policy))` → SQLite 写入规范化文本。

**→ Durable state validation**: `_validate_run_for_insert` (state.py:5263-5266)
- `parse_run_queue_policy(run.queue_policy)` → 插入前校验。

**→ Durable state decode**: `run_row_from_host_row` → `_decode_run_queue_policy` (state.py:1187-1208)
- `serialize_run_queue_policy(parse_run_queue_policy(raw_policy))` → 从 SQLite 读出时校验 + 规范化。非法值 → `HostRowDecodeError`。

**→ DDL**: `host_runs.queue_policy` CHECK (schema.py:519-521)
- `CHECK (queue_policy IN ('queue', 'reject', 'attach_active'))` → 值由 `run_queue_policy_values()` 派生，与 owner 同一闭集。
- `HOST_SCHEMA_VERSION` 22 → 23。

**→ Semantic digest**: `_start_run_semantic_digest` (admission.py:4650-4652)
- `serialize_run_queue_policy(parse_run_queue_policy(request.queue_policy))` → idempotency digest 中 queue_policy 经 owner 规范化。

**结论**: queue_policy 从 public request → admission → durable transition → durable state write/decode/validate → DDL → semantic digest，所有路径均经过 `dayu.host.queue_policy` owner helper。无 semantic ownership drift。无下游 fallback、特例、loose parsing、兼容 shim。

### 链路 2：RunResultRow.terminal_status 从 projection 到 SQLite

**入口**: `_project_run_result` (read_model.py:240)
- `_require_terminal_status(event.event_type)` 返回 `RunStatus`（已去除旧 `.value` 调用）。

**→ RunResultRow 构造** (read_model.py:237-249)
- `terminal_status=_require_terminal_status(event.event_type)` → `RunStatus` typed 赋值。

**→ SQLite write**: `insert_run_result_if_absent` (durable/read_model.py:291)
- `serialize_run_result_terminal_status(row.terminal_status)` → RunStatus → text，同时校验 isinstance + is_terminal。

**→ SQLite read**: `_run_result_from_host_row` (durable/read_model.py:403-405)
- `_terminal_status_from_text(...)` → text → RunStatus，同时校验 StrEnum membership + is_terminal。旧 `.value` 调用已移除。

**→ Python validation**: `_validate_run_result` (durable/read_model.py:323)
- `serialize_run_result_terminal_status(row.terminal_status)` → 校验 isinstance(RunStatus) + is_terminal。

**→ Public comparison**: `_stable_run_result` (test_projection_read_model.py:522)
- `serialize_run_result_terminal_status(row.terminal_status)` → 使用 owner serializer 做稳定文本比较。

**结论**: RunResultRow.terminal_status typed boundary 完整。从 projection 生产 → row 构造 → SQLite write/read → Python validation → public comparison，全部经过 typed `RunStatus` 边界，序列化/反序列化各有一个 owner helper。无类型逃逸、无裸字符串泄漏。

### 链路 3：AdmissionPolicy deletion 残留扫描

- `rg -n 'AdmissionPolicy' dayu tests` → 无匹配。
- `rg -n 'RunQueuePolicy\s*=|AdmissionPolicy\s*=|from dayu\.host\.admission import AdmissionPolicy' dayu tests` → 无匹配。
- 旧 `_parse_admission_policy` 函数已删除，未保留 alias/re-export/wrapper。
- 旧 `AdmissionPolicy` StrEnum 已删除，未保留兼容常量。

**结论**: AdmissionPolicy 清理彻底，无兼容残留。

### 链路 4：测试是否固化错误语义

- `tests/host/test_accepted_result_projection.py`: `queue_policy="fifo"` → `queue_policy="queue"`。旧 fixture 值 `fifo` 不是合法 queue policy，属于历史错误语义。已修正。
- `tests/host/test_compact_material.py`: 同上，`fifo` → `queue`。
- `tests/host/test_compact_pipeline.py`: 同上，`fifo` → `queue`。
- `tests/host/test_durable_schema.py`:
  - `test_host_schema_version_is_queue_policy_check_version`: 断言 `HOST_SCHEMA_VERSION == 23`，与 owner 一致。
  - `test_host_runs_queue_policy_check_uses_owner_values`: 验证 fresh schema DDL 包含 owner 三值，且 SQLite CHECK 拒绝 `invalid_policy`。测试的是 owner 级 contract 行为，非偶然行为。
- `tests/host/test_projection_read_model.py`:
  - `test_terminal_event_projects_run_result_and_duplicate_replay_is_noop`: 断言 `result.terminal_status == RunStatus.SUCCEEDED`，typed 比较，非字符串比较。
  - `test_terminal_event_mapping_covers_current_run_terminal_statuses`: 断言 `result.terminal_status == status`，typed 比较。
  - `test_read_model_python_validation_rejects_unknown_terminal_status`: 使用 `cast(RunStatus, "future_terminal")` 构造非法输入，验证 `insert_run_result_if_absent` fail closed。`cast` 在此仅用于绕过类型检查器，运行时 `"future_terminal"` 是 plain str，`serialize_run_result_terminal_status` 的 `isinstance` 检查会拒绝。测试验证的是 owner 级 contract（非法输入 → HostDurableError），非偶然行为。

**结论**: 测试未固化错误语义。旧非法 fixture 已修正。新测试断言 owner contract 行为。

### 链路 5：README 是否只写当前稳定事实

- `dayu/host/README.md` 变更仅一行（line 559），在 Admission 与 active slot 章节增加：queue policy 只允许三值、Host queue policy owner 统一校验、fresh durable schema 使用同一闭集 CHECK。
- 变更在 README Agent 更新约束范围内：Host admission 和 durable schema 现在暴露稳定 queue policy owner 和 DDL CHECK 行为。
- 未引入未来计划、未稳定功能或推测性描述。

**结论**: README 只写当前稳定事实。

## Findings

未发现实质性问题。

### 逐项核对

| 审查维度 | 结果 |
|---|---|
| semantic ownership drift | 无。queue_policy 所有路径均经 `dayu.host.queue_policy` owner；RunResultRow.terminal_status 所有路径均经 typed `RunStatus` + owner serializer/parser。 |
| queue policy owner 覆盖 | 完整。public request、admission、durable transition、durable state decode/write/validate、DDL CHECK、EventLog payload、semantic digest 全部经过 owner helper。 |
| AdmissionPolicy 兼容残留 | 无。`rg` 扫描确认零残留；旧类/函数已删除，无 alias/re-export/wrapper。 |
| DDL/schema version | 正确。`HOST_SCHEMA_VERSION` 22→23；`host_runs.queue_policy` CHECK 值由 `run_queue_policy_values()` 派生；`execution_target` 维持 `TEXT NOT NULL` 无闭集。 |
| RunResultRow typed boundary | 正确。`terminal_status: RunStatus` typed；SQLite write 经 `serialize_run_result_terminal_status`；SQLite read 经 `_terminal_status_from_text` → `RunStatus`；projection 返回 typed `RunStatus`。 |
| README 稳定性 | 正确。仅记录当前稳定事实（三值闭集 + owner 校验 + DDL CHECK），无未来计划。 |
| 测试是否固化错误语义 | 无。旧 `fifo` fixture 已修正；新测试断言 owner contract；`cast(RunStatus, ...)` 仅用于构造非法输入触发 fail-closed 验证。 |
| execution_target 闭集化 | 未发生。保持 `TEXT NOT NULL`，仅 `_require_non_empty_text` 校验。 |

### 补充验证点

- **`serialize_run_queue_policy(parse_run_queue_policy(...))` 双重解析模式**: 在 `_start_run_semantic_digest`、`_run_accepted_event_request`、`insert_run`、`_decode_run_queue_policy` 四处出现。`parse_run_queue_policy` 已在 admission 入口调用过一次，这些下游调用属于防御性重校验。每次调用均正确，parse → enum → serialize 构成 normalization round-trip，不改变合法输入的值。无性能问题（StrEnum 构造 + `.value` 访问均为 O(1)）。
- **`parse_run_queue_policy` 空字符串显式检查**: `value.strip() == ""` 先于 `RunQueuePolicy(value)` 检查，对空白字符串提供一致的错误消息。`RunQueuePolicy("")` 本就会抛 ValueError，显式检查不改变行为，只统一消息。无功能差异。
- **`serialize_run_result_terminal_status` 与 `_terminal_status_from_text` 对称性**: 两者均检查终态（`is_terminal_run_status`），均抛出 `HostDurableError`，消息一致。parse path 用 `RunStatus(value)` + `is_terminal_run_status`；serialize path 用 `isinstance(status, RunStatus)` + `is_terminal_run_status`。输入侧与输出侧保护对称。

## Open Questions

无。

## Residual Risk

- **旧 schema-22 数据库**: 项目采用 fresh-schema 策略，旧库不迁移。旧库 `host_runs.queue_policy` 列无 CHECK 约束，但 Python 层 decode/insert 校验仍然生效（`_decode_run_queue_policy` 在 `run_row_from_host_row` 中、`parse_run_queue_policy` 在 `_validate_run_for_insert` 和 `insert_run` 中）。若旧库中存在非法 queue_policy 值（只能来自历史 bug 或直接 SQL 操作），decode 时会被 `HostRowDecodeError` 拦截。风险可控。
- **RunResultRow.terminal_status 非终态 RunStatus 输入路径**: `_validate_run_result` 和 `insert_run_result_if_absent` 均调用 `serialize_run_result_terminal_status`，会拒绝非终态 RunStatus。但当前没有专门测试验证"传入 RunStatus.ACCEPTED 作为 terminal_status 被拒绝"的场景——现有测试通过 `cast(RunStatus, "future_terminal")` 覆盖了非 RunStatus 输入，通过合法终态测试覆盖了正常路径。非终态 RunStatus 输入属于内部调用错误，概率极低，且 validator 已有防御。风险低。
- **`RunRow.queue_policy` 仍为 text**: 控制器已接受此设计选择。`RunRow` 是 durable row snapshot，保持 text 避免扩大 fixture 迁移范围。owner closure 已在 public input、admission、durable insert、durable decode、EventLog payload、DDL 六层生效。若未来需要 typed `RunRow.queue_policy`，迁移路径清晰（替换为 `RunQueuePolicy`，更新所有构造点和 fixture）。
