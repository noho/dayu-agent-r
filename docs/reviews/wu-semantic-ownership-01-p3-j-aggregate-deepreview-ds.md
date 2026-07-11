# WU-SEMANTIC-OWNERSHIP-01 P3-J Aggregate Deepreview

## Scope

- **Mode**: current changes
- **Review agent**: AgentDS (aggregate deepreview)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `f91cd6d5` (accepted plan commit)
- **Accepted slice commits**: S1 `a63a27c7`, S2 `2b2718a2`, S3 `e8f32b77`, S4 `9ffb1a3d`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-deepreview-ds.md`
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Plan**: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- **Aggregate validation**: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-validation.md`
- **Included scope**: 42 production/test files changed (committed), plus aggregate validation artifact
- **Excluded scope**: `AGENTS.md`, `CLAUDE.md`, `docs/cli_ci*`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`; per-slice review artifacts and plan-fix artifacts not re-reviewed
- **Parallel review coverage**: 无 — 本 aggregate deepreview 由单一 reviewer 沿全部关键链路逐条走读

## Review Method

本 review 按以下步骤执行：

1. 阅读 plan、control doc、aggregate validation、design docs 建立合同基线。
2. 读取完整 `git diff f91cd6d5...HEAD` for 生产代码与测试代码 (4010 行 diff)。
3. 沿每条关键链路走读：owner 定义 → producer 写入 → validation → durable persistence (DDL + row codec) → projection/decoder → public/LLM-facing output。
4. 执行跨 slice regression 检查：S1 EventLog event-type owner 是否被 S2/S3/S4 回归；S2 queue-policy owner 是否与 S3 idempotency owner 在 `admission.py` 中正确交互；S3 descriptor-kind owner 是否在所有 producer 和 consumer 中一致；S4 config 变更是否不破坏 CLI/current schema。
5. 执行 semantic ownership drift 检查：是否存在 downstream fallback、特例、重复计算、loose parsing、兼容 shim、测试固化或多真源状态。
6. 执行 adversarial failure pass：非法输入、边界条件、DDL/decoder 不一致、异常路径。
7. 检查 AGENTS.md 约束：semantic ownership、LLM-facing、分层、类型、docstring、README 触发、无兼容代码。

## Findings

未发现实质性问题。

### 逐 Slice 验证摘要

#### S1 — EventLog Event-Type Append / Decoder / Fresh-Schema Closure

**Owner 结构**：`dayu/host/lifecycle_events.py` 定义了 9 个分类 `StrEnum`（`HostSessionEventType`、`HostRunEventType`、`HostAttemptEventType`、`HostAdmissionCommandEventType`、`HostToolWaitEventType`、`HostContextGovernanceEventType`、`HostRunnerInputEventType`、`HostEngineDiagnosticEventType`、`HostPreviewEventType`），总 type alias `HostEventType` 覆盖全部 union。分类 tuples 收敛到 `HOST_EVENT_TYPE_CATEGORIES`，parser dict `_HOST_EVENT_TYPE_BY_VALUE` 和 `all_host_event_type_values()` 均从该单一真源派生。

**Append validation**：`EventLogAppendRequest` 校验新增 `parse_host_event_type(request.event_type) is None` → `HostDurableError("EventLog event_type is unknown")`（`dayu/host/durable/event_log.py:1129-1130`）。此校验在 `_require_non_empty_text` 之后执行，fail-closed。

**Row decoder**：`_event_log_row_from_host_row` 新增 `parse_host_event_type(event_type) is None` → `HostDurableError("EventLog row has invalid event_type")`（`dayu/host/durable/event_log.py:1252-1253`）。decoder 先解析 event_type 文本，再传入 EventLogRow 构造，不存在裸字符串绕过。

**Fresh-schema DDL CHECK**：`event_log.event_type TEXT NOT NULL CHECK (event_type IN (...))`，其中 `...` 由 `_sql_text_in_values(all_host_event_type_values())` 在模块加载时生成（`dayu/host/durable/schema.py:432-435`）。DDL 值与 owner 值同源。

**Fixture migration**：所有 `TYPE_A`、`TEST_EVENT`、`host.test`、`host.payload.accepted`、`host.artifact.accepted`、`host.nulls`、`host.other`、`host.idempotent` 等任意 fixture 已替换为合法值（`USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`ENGINE_EVENT_DIAGNOSTIC` 等）。仅 `INVALID_TEST_EVENT_TYPE` 保留在非法 event type 拒绝测试中。`test_event_log_store.py:170` 和 `test_durable_schema.py:1164` 为预期保留的非法值测试。

**跨 slice 一致性**：S2/S3/S4 均不修改 EventLog event type 相关逻辑。append validation 和 row decoder 的 typed owner 校验对所有 slice 的 EventLog 写入透明生效。`HostSchemaMismatchError` 在 connection open 时检查 `HOST_SCHEMA_VERSION`（现为 23），已更新的 DDL CHECK 在首次连接时自动应用。

#### S2 — Queue Policy Owner / RunResult Terminal Row Surface

**Queue policy owner**：`dayu/host/queue_policy.py` 定义 `RunQueuePolicy(StrEnum)`（`QUEUE`、`REJECT`、`ATTACH_ACTIVE`）及 `parse_run_queue_policy`、`serialize_run_queue_policy`、`run_queue_policy_values` helper。此为全仓唯一真源。

**AdmissionPolicy 删除**：`rg -n 'AdmissionPolicy' dayu tests` → 无匹配。旧 `AdmissionPolicy(StrEnum)` 已完全删除，无 alias、re-export、wrapper 或 facade。

**public API validation**：`StartRunRequest.__post_init__` 新增 `parse_run_queue_policy(self.queue_policy)`（`dayu/host/api.py:1819`）。非法值时抛出 `ValueError`。

**Durable insert validation**：`_validate_run_for_insert` 新增 `parse_run_queue_policy(run.queue_policy)`（`dayu/host/durable/state.py:5264`）。`insert_run` 新增 `serialize_run_queue_policy(parse_run_queue_policy(run.queue_policy))` 双重校验+规范化（`dayu/host/durable/state.py:2702`）。

**Durable decode**：`_decode_run_queue_policy` 新增 decode → parse → serialize 链（`dayu/host/durable/state.py:1187-1210`），在 `run_row_from_host_row` 中使用（替换原 `_decode_required_text`）。

**Run transition**：`_validate_common_create_input` 新增 `parse_run_queue_policy(queue_policy)`（`dayu/host/durable/run_transition.py:5969`）。`_run_accepted_event_request` 在 payload JSON 中序列化时经过 parse→serialize（`dayu/host/durable/run_transition.py:2999-3000`）。

**admission.py 消费者**：全部 `AdmissionPolicy.QUEUE/REJECT/ATTACH_ACTIVE` 引用替换为 `RunQueuePolicy.QUEUE/REJECT/ATTACH_ACTIVE`。`_CreateAdmissionRequest` 相关函数的 `queue_policy: str` 参数已改为 `queue_policy: RunQueuePolicy`，调用方传入 typed 值。

**Fresh-schema DDL CHECK**：`host_runs.queue_policy TEXT NOT NULL CHECK (queue_policy IN ('queue', 'reject', 'attach_active'))`，由 `_sql_text_in_values(run_queue_policy_values())` 生成（`dayu/host/durable/schema.py:599-601`）。测试 `test_host_runs_queue_policy_check_uses_owner_values` 验证合法值通过、非法值 `invalid_policy` 被 `IntegrityError` 拒绝。

**RunResultRow terminal status**：字段类型从 `str` 改为 `RunStatus`（`dayu/host/durable/read_model.py:61`）。`_run_result_from_host_row` 中 `_terminal_status_from_text(...)` 不再 `.value` 调用，直接返回 `RunStatus`（`dayu/host/durable/read_model.py:403-405`）。`_validate_run_result` 从 `_terminal_status_from_text(row.terminal_status)` 改为 `serialize_run_result_terminal_status(row.terminal_status)` — 后者既验证类型正确性又验证终态合法性（`dayu/host/durable/read_model.py:323`）。`insert_run_result_if_absent` 使用 `serialize_run_result_terminal_status(row.terminal_status)` 写入 SQLite（`dayu/host/durable/read_model.py:181`）。

**projection 消费者**：`read_model.py` 中 `_require_terminal_status` 函数从返回 `str`（`.value`）改为返回 `RunStatus`（`dayu/host/read_model.py:289-298`）。创建 `RunResultRow` 时直接传入 typed `RunStatus`。测试断言从 `result.terminal_status == "succeeded"` 改为 `result.terminal_status == RunStatus.SUCCEEDED`。

**execution_target**：保持为非空 resolved deployment target text，未添加 DDL 闭集约束。与 plan 中 `deferred-with-owner` disposition 一致。

#### S3 — Idempotency / Descriptor Kind Weak-Contract Closure

**Idempotency owner**：`dayu/host/durable/idempotency.py` 定义 `IdempotencyScopeKind(StrEnum)`（16 值）和 `IdempotencyResultKind(StrEnum)`（7 值），含 `parse_*`、`*_values()` helper。`IdempotencyScope.__post_init__`、`IdempotencyResultRef.__post_init__`、`IdempotencyRecord.__post_init__` 在构造边界调用 owner parser，非法值抛出 `HostDurableError`。

**Producer 迁移**：
- `admission.py`: `_OPERATION_*` 常量从裸字符串改为 `IdempotencyScopeKind.START_RUN` 等；`_IDEMPOTENCY_RESULT_KIND_*` 改为 `IdempotencyResultKind.RUN/SESSION`；`_idempotency_scope` 参数签名从 `operation: str` 改为 `operation: IdempotencyScopeKind`。
- `session_lifecycle.py`: 同上模式，`_OPERATION_ENSURE/CREATE/CLOSE_SESSION` 改为 typed 值；`_idempotency_scope` 参数签名 typed。
- `waiting.py`: `_TOOL_AWAITING_ACCEPT_SCOPE_KIND` 等常量改为 typed 值。
- `tool_runtime.py`: `_TOOL_FACT_ACCEPT_SCOPE_KIND/RESULT_KIND` 改为 typed。
- `purge.py`: `PURGE_IDEMPOTENCY_SCOPE_KIND/RESULT_KIND` 改为 typed。

**DDL 不添加 CHECK**：`scope_kind TEXT NOT NULL CHECK` 和 `result_kind TEXT NOT NULL CHECK` 在 `dayu/host/durable/schema.py` 中不存在（通过 scan 和测试 `test_schema_constraints_are_explicit` 双重确认）。与 plan 中"Python-level typed validation only"策略一致。

**Row decoder**：`_idempotency_record_from_host_row` 在传入 `IdempotencyRecord` 构造前先调用 `parse_idempotency_scope_kind` 和 `parse_idempotency_result_kind`，非法值 fail-closed（`dayu/host/durable/idempotency.py:414-416`）。

**Tests**：`test_idempotency_owner_values_match_current_host_baseline` 锁定当前 legal set；`test_idempotency_dataclass_construction_rejects_unknown_kind` 验证构造边界拒绝；`test_idempotency_read_rejects_mutated_unknown_result_kind` 验证 decoder 拒绝手工篡改。

**Descriptor kind owner**：`PayloadDescriptorKind(StrEnum)` 定义在 `dayu/host/durable/schema.py:238-247`，7 值覆盖全部当前 descriptor kind。`parse_payload_descriptor_kind`、`payload_descriptor_kind_values`、`payload_descriptor_metadata` helper 同模块定义。

**Producer-side validation**：`payload_descriptor_metadata` helper 在构造 metadata 时调用 `parse_payload_descriptor_kind` 并拒绝 `descriptor_kind` 字段覆盖（`dayu/host/durable/schema.py:292-296`）。`_validate_payload_descriptor_metadata` 在 `_insert_payload_descriptor` 入口校验 metadata 中的 `descriptor_kind`（`dayu/host/durable/payload.py:459`）。所有 payload producer（`tool_runtime.py`、`run_input.py`、`engine_ingest.py`、`compaction_operation.py`）已从裸 `metadata={"descriptor_kind": "..."}` 改为 `payload_descriptor_metadata(PayloadDescriptorKind.XXX, {...})`。

**Consumer-side validation**：`payload_resolution.py` 中 `_validate_descriptor_kind` 参数从 `expected_kind: str` 改为 `expected_kind: PayloadDescriptorKind`，先 `parse_payload_descriptor_kind(expected_kind)` 再读 metadata JSON，再 `parse_payload_descriptor_kind(descriptor_kind)` 比较 typed 值。非法/缺失 descriptor kind 统一 `HostDurableError` fail-closed。

**admission.py sequencing**：idempotency 常量迁移和 descriptor-kind 变更不涉及 queue-policy owner（RunQueuePolicy 导入和使用独立）。S2 和 S3 在 `admission.py` 中无交叉回归。

**旧 descriptor kind 常量兼容**：`TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND` 等旧常量仍保留为 `PayloadDescriptorKind.XXX.value` 别名（`dayu/host/durable/schema.py:300-367`），但所有 producer 和 consumer 代码路径均已改为直接使用 `PayloadDescriptorKind` enum 成员或 `payload_descriptor_metadata` helper。旧常量为存量消费者提供平滑过渡，但新增代码应使用 typed owner。此项属于过渡期共存，非 semantic drift。

#### S4 — Legacy Config Exposure Re-Ownership

**删除**：`legacy_config_file_names()` 函数和 `_LEGACY_CONFIG_FILES` 常量从 `dayu/runtime/config_loader.py` 完全删除。`rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES' dayu tests README.md` → 无匹配。

**CLI init guard**：`_LEGACY_CONFIG_FILE_NAMES` 移至 `dayu/cli/commands/init.py:33-35` 作为模块级 private 常量。`_raise_if_legacy_asset_selected` 重命名为 `_raise_if_legacy_top_level_config_asset_selected`，增加 `workspace_config_dir` 参数和 `asset.destination.parent == workspace_config_dir` 判断，只拦截顶层配置目录下的旧文件名，不误伤 prompts 子目录下的同名文件。

**Tests**：
- `test_config_loader.py`: `test_legacy_files_do_not_exist_and_are_not_read` 从调用 `legacy_config_file_names()` 改为使用本地 `_REMOVED_CONFIG_FILE_NAMES` 常量和 `config_file_names()` 交叉校验。
- `test_init_command.py`: 新增 `test_init_rejects_legacy_top_level_config_asset` 验证顶层旧配置文件被拒绝；新增 `test_init_allows_prompt_asset_with_removed_config_file_name` 验证 prompts 子目录下的同名文件不被误伤。

**CLI init 行为**：`dayu-cli init` 仍只复制 `config_file_names()` 中的当前 schema 文件；不会生成旧 `llm_models.json` / `run.json`。行为不变，用户不可见。

**Current config schema**：`config_file_names()` 元组不变（`_MODELS_FILE`, `_EXECUTION_PROFILES_FILE`, `_HOST_RUNTIME_FILE`, `_RUNTIME_LANES_FILE`, `_TOOL_DISCOVERY_FILE`）。无 config schema 变更。

### 跨 Slice 综合验证

**语义所有权一致性**：

- EventLog `event_type` 真源：`dayu/host/lifecycle_events.py`（S1 owner）→ append validation（`event_log.py:1129`）→ DDL CHECK（`schema.py:432`）→ row decoder（`event_log.py:1252`）。四层同源，无 consumer drift。
- Run `queue_policy` 真源：`dayu/host/queue_policy.py`（S2 owner）→ public API validation（`api.py:1819`）→ durable insert validation（`state.py:5264`）→ durable decode（`state.py:1187`）→ DDL CHECK（`schema.py:599`）→ admission consumer（`admission.py` 全部 typed 参数）。六层同源。
- `RunResultRow.terminal_status` 真源：`dayu/host/durable/read_model.py` typed 字段 + `serialize_run_result_terminal_status` helper → projection producer（`read_model.py:240` typed `_require_terminal_status`）→ durable row codec（durable `read_model.py:403` typed `_terminal_status_from_text` 不再 `.value`）。三层 typed，无裸字符串泄漏到 consumer。
- Idempotency `scope_kind`/`result_kind` 真源：`dayu/host/durable/idempotency.py` `StrEnum` → dataclass `__post_init__` 边界校验 → row decoder `parse_*` → 无 DDL CHECK（plan 有意）。Producer 端所有 caller 使用 typed 值；consumer 端通过 typed dataclass 字段消费。
- Descriptor `kind` 真源：`dayu/host/durable/schema.py` `PayloadDescriptorKind` → producer `payload_descriptor_metadata` helper + `_validate_payload_descriptor_metadata` → consumer `_validate_descriptor_kind` 使用 `parse_payload_descriptor_kind`。producer 和 consumer 使用同一 owner，consumer 不维护独立 all-known-kind 列表。

**source-of-truth duplication 检查**：无发现。每个语义只有一个 Python owner。DDL CHECK 从同一 owner 的 `*_values()` helper 生成。测试中的 `_REMOVED_CONFIG_FILE_NAMES` 为测试本地 fixture，不构成第二真源。`purge.py` 的 `_SESSION_FACT_SCOPE_KINDS` 是 `IdempotencyScopeKind` 值的 filtered subset（SQL 查询用），不构成独立 owner（见 Residual Risk）。

**downstream masking 检查**：无发现。非法值在各层 fail-closed（`HostDurableError`、`ValueError`、`IntegrityError`），不产生 fallback、默认值或 silent pass。

**test fixture 固化检查**：无发现。所有任意 fixture 值已迁移为合法 owner 值。非法值仅保留在显式非法值拒绝测试中（`INVALID_TEST_EVENT_TYPE`、`cast(RunStatus, "future_terminal")`、`cast(IdempotencyScopeKind, " \t")` 等）。

**DDL/decoder 不一致检查**：无发现。DDL CHECK 值与 row decoder 值同源（均从 owner `*_values()` 或 `parse_*` 函数派生）。Schema version 从 21 → 23 在 S1 和 S2 之间递增一次（S1 DDL CHECK 和 S2 DDL CHECK 合并在同一 version bump），无中间 version 的 partial state 暴露。

**public API/persistence/projection 语义不一致检查**：无发现。

- public API `StartRunRequest.queue_policy` 接受 `str`，在 `__post_init__` 解析为 `RunQueuePolicy`（`api.py:1819`）。
- persistence `RunRow.queue_policy` 仍为 `str`，但 `insert_run` 和 `run_row_from_host_row` 均经过 parse/serialize 规范化（`state.py:2702, 1255`）。
- projection `RunResultRow.terminal_status` 为 `RunStatus` typed 值，序列化只在 `insert_run_result_if_absent` SQL 边界调用 `serialize_run_result_terminal_status`。
- 三者不存在"API 层接受 X 但 durable 写入 Y、projection 读出 Z"的不一致。

### AGENTS.md 约束检查

- **Semantic ownership**：每个 closed set 有唯一 Python owner。EventLog event type → `lifecycle_events.py`；queue policy → `queue_policy.py`；terminal status → `durable/read_model.py`；idempotency kinds → `durable/idempotency.py`；descriptor kind → `durable/schema.py`。无 consumer 自行复制合法值集合。
- **LLM-facing 文本**：变更不涉及 LLM-facing prompt/schema 修改。EventLog event type、queue policy、terminal status、idempotency kind、descriptor kind 均为 Host 内部治理类型，不直接暴露给 LLM。
- **分层**：全部变更在 `dayu.host` 和 `dayu.runtime`/`dayu.cli` 边界内。无反向依赖（runtime 不 import host，host 不 import service/engine）。`dayu.runtime.config_loader` 删除了旧文件名暴露，未新增 host 依赖。
- **类型**：所有新 `StrEnum`、dataclass 字段、函数参数和返回值均有完整类型标注。`pyright → 0 errors, 0 warnings, 0 informations`。
- **docstring**：所有新 public 函数（`parse_host_event_type`、`serialize_host_event_type`、`all_host_event_type_values`、`host_event_type_values`、`parse_run_queue_policy`、`serialize_run_queue_policy`、`run_queue_policy_values`、`parse_idempotency_scope_kind`、`parse_idempotency_result_kind`、`idempotency_scope_kind_values`、`idempotency_result_kind_values`、`parse_payload_descriptor_kind`、`payload_descriptor_kind_values`、`payload_descriptor_metadata`、`serialize_run_result_terminal_status`、`_decode_run_queue_policy`、`_validate_payload_descriptor_metadata`）均含完整中文 docstring，包含参数、返回值、异常说明。
- **无兼容代码**：`AdmissionPolicy` 完全删除（无 alias/re-export/wrapper/facade）。`legacy_config_file_names()` 完全删除。旧 descriptor kind 常量（`TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND` 等）保留为 `PayloadDescriptorKind.XXX.value` 别名，但此非兼容代码（定义为 owner 字符串的稳定引用，非对旧接口的包装）。
- **无 `hasattr`/`getattr`**：在改动的 6 个核心 owner 文件中均无使用。
- **README 触发**：`dayu/host/README.md` 在 S2 更新了 queue policy 说明（第 559 行新增闭集约束描述）。S1/S3/S4 的 README 检查确认无需更新（当前文档已覆盖相关语义或行为未变）。
- **测试**：全部受影响测试已更新（fixture migration + 新增 owner-level 测试）。598 passed, 0 failures in aggregate matrix。

## Open Questions

无。

## Residual Risk

1. **`RunRow.queue_policy` 仍为 `str` 类型注解**：Python 类型系统层面，`RunRow.queue_policy` 仍声明为 `str`（`dayu/host/durable/state.py:286`），不在类型层面表达"必须属于 RunQueuePolicy 闭集"的约束。当前防御层次为：(a) public API `__post_init__` 校验、(b) `_validate_run_for_insert` 校验、(c) `_decode_run_queue_policy` decode 校验、(d) DDL CHECK。但直接构造 `RunRow` 并绕过这些入口的理论路径（如测试 fixture）仍可传入非法字符串。**风险低**：所有正常生产路径均已覆盖，且 `insert_run` 内 `serialize_run_queue_policy(parse_run_queue_policy(...))` 构成最后防线。

2. **存量模块中仍存在 event type 字符串字面量**：`dayu/host/durable/run_transition.py:98`（`_EVENT_TYPE_ATTEMPT_STARTED = "ATTEMPT_STARTED"`）等模块使用字符串常量而非 `HostAttemptEventType.ATTEMPT_STARTED`。这些值在语义上等同于 owner enum 的 `.value`，且通过 append request validation 时经过 owner parser 校验，当前不构成 correctness 缺陷。但存在双轨维护负担——若 event type 值变更（几率极低），需同时修改 owner enum 和这些字符串常量。**风险低**：plan 明确将 consumer-wide redirection 列为 S1 non-goal；且 event type 值为稳定 durable 标识，不预期变更。

3. **`purge.py` `_SESSION_FACT_SCOPE_KINDS` 为手工维护的 scope kind 子集**：`dayu/host/durable/purge.py:141-152` 枚举了 10 个 session-fact scope kinds 的 `.value`。如果 `IdempotencyScopeKind` 新增一个 session-fact 类别，`purge.py` 必须同步更新。当前无自动一致性校验（如遍历所有 scope kinds 并分类为 session-fact vs 其他）。**风险低**：scope kind 类别由 Host command 语义决定，新增是低频事件；且 purge 操作在写入幂等记录时有 owner 校验保护。

4. **历史旧配置文件名引用**：design docs 和 review archive 中仍存在 `llm_models.json` / `run.json` 的引用（如 `docs/host/design.md` 中的历史描述）。这些不是 runtime/public API 暴露，不构成当前 correctness 风险。S4 已完成 runtime 和 CLI 入口的清理。

5. **Schema version 合并 bump**：`HOST_SCHEMA_VERSION` 从 21 跳至 23（跳过 22），S1 的 `event_log.event_type CHECK` 和 S2 的 `host_runs.queue_policy CHECK` 共享同一 version bump。如果未来需要独立回滚 S1 或 S2，schema version 粒度可能不够。**风险低**：两个 CHECK 均为 additive（只增加约束），回滚任一不会导致数据不一致；且 plan 要求四个 slice 作为整体合入。

## Verification Summary

| 验证项 | 结果 |
|---|---|
| Aggregate test matrix (598 tests) | 598 passed, 0 failures |
| pyright (dayu/ tests/ utils/) | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | passed |
| `AdmissionPolicy` scan | 无匹配 |
| `legacy_config_file_names` / `_LEGACY_CONFIG_FILES` scan | 无匹配 |
| `scope_kind TEXT NOT NULL CHECK` / `result_kind TEXT NOT NULL CHECK` scan | 无匹配（plan 有意） |
| 任意 event type fixture scan (`TYPE_A`, `TEST_EVENT`, `host.test`, etc.) | 仅 `INVALID_TEST_EVENT_TYPE` 在非法值拒绝测试中 |
| `hasattr` / `getattr` scan (核心 owner 文件) | 无匹配 |
| `host_runs.queue_policy CHECK` 与 `run_queue_policy_values()` 一致性 | 通过测试 `test_host_runs_queue_policy_check_uses_owner_values` |
| `event_log.event_type CHECK` 与 `all_host_event_type_values()` 一致性 | 通过测试 `test_schema_constraints_are_explicit` |
| idempotency scope/result kind 无 DDL CHECK | 通过测试 `test_schema_constraints_are_explicit` |
| `RunResultRow.terminal_status` 为 `RunStatus` typed 值 | 通过测试 `test_terminal_event_projects_run_result` |
| 旧 descriptor kind 常量稳定性 | 通过测试 `test_tool_call_request_payload_descriptor_kinds_are_stable` |
| CLI init 拒绝旧顶层配置文件 | 通过测试 `test_init_rejects_legacy_top_level_config_asset` |
| CLI init 不误伤 prompt 子文件 | 通过测试 `test_init_allows_prompt_asset_with_removed_config_file_name` |
| README 触发 | `dayu/host/README.md` 已更新 queue policy 说明 |

## Conclusion

P3-J 四个 accepted slice 作为一个整体，在 EventLog event-type owner、queue-policy owner、RunResultRow terminal-status typed surface、idempotency scope/result kind typed validation、descriptor-kind owner、legacy config exposure removal 六个维度上，均实现了 plan 定义的 owner boundary closure。各 owner 的 producer 写入、validation、durable DDL/decoder、projection 消费四层边界同源一致，无 consumer drift、无 downstream masking、无 source-of-truth duplication、无测试固化非法行为。未发现跨 slice regression 或 AGENTS.md 约束违反。Residual risk 限于类型注解粒度、存量字符串字面量双轨维护和 scope kind 子集的非自动一致性——这些为 plan 明确接受的设计取舍或已由多层 defense-in-depth 缓解。
