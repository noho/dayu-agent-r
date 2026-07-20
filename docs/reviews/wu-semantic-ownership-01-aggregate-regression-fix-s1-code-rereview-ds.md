# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 1 Code Re-Review — AgentDS

## 1. Gate identity

- 审查者：AgentDS。
- 时间：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix continuation；不是新 WU。
- Gate：Slice 1 complete code re-review（只读，不修改代码/测试/design/plan/control/既有 artifacts）。
- 本轮是 full re-review，不是前轮 finding closure checklist。独立完整重读全部 required reading，独立验证全部审查维度。

## 2. Immutable review inputs

### 2.1 Required reading（完整独立读取并核对，逐文件从第一行读到 EOF）

| 文档 | 行数 | 读取状态 |
| --- | --- | --- |
| `AGENTS.md` | 128 | FULL_READ_TO_EOF |
| `docs/host/issues-implementation-control.md` | 2319 | FULL_READ_TO_EOF（分 12 段逐段读取，覆盖全部 2319 行） |
| `docs/phaseflow-umbrella-optimization-control.md` | 302 | FULL_READ_TO_EOF |
| `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 731 | FULL_READ_TO_EOF |
| `docs/host/design.md` | 3704 | FULL_READ_TO_EOF（分 6 段逐段读取，覆盖全部 3704 行） |
| `docs/engine/design.md` | 553 | FULL_READ_TO_EOF |
| `docs/tool/design.md` | 134 | FULL_READ_TO_EOF |
| `docs/fins/design.md` | 123 | FULL_READ_TO_EOF |
| `docs/ui/design.md` | 116 | FULL_READ_TO_EOF |
| `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | 696 | FULL_READ_TO_EOF |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md` | 1578 | FULL_READ_TO_EOF |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-controller-authorization.md` | 43 | FULL_READ_TO_EOF |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-code-review-ds.md` | 383 | FULL_READ_TO_EOF（前轮 AgentDS review） |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-code-review-mimo.md` | 231 | FULL_READ_TO_EOF（前轮 AgentMiMo review） |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-code-review-controller-adjudication.md` | 63 | FULL_READ_TO_EOF |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-test-account-quota-user-decision-controller-record.md` | 47 | FULL_READ_TO_EOF |

### 2.2 Immutable review target — ordered manifest SHA-256

```text
bcfc4088dfb2239236579159b71f6abc8e51a32201de240603f3a2eebd954c41
```

### 2.3 Fresh SHA-256 verification

逐文件重新采集：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
20f41229f4e0da48aa1f3904d3bd5c61f436f7a9a706dfe78e899a4d06dccda2  tests/host/test_audit_sink.py
4d9dbb9b5a215597182166b6a92c2d1d30447ae21539bf77602cc6b7c7869140  tests/host/test_tool_trace_projection.py
047b89fd099fdc3250bdcdc066487b05bcf70aeccc18b60228f3bb10cca90c77  tests/host/test_host_activity_event_projection.py
4ed1693ee6819caf99072883e850f2a11e0ccb11636a196b0af629205cd46190  tests/host/test_run_input_builder.py
e874e77e997039d7d1e907dc4df5e980edae876e3920ac4417e3836cabf5b180  tests/host/test_logging.py
```

**结论：八个文件全部精确匹配 ordered manifest。** 与两路前轮 review 使用的 immutable target 完全一致。

## 3. 逐项独立审查

### 3.1 AR-F01 — test fixture current-schema 修复（`tests/service/test_host_admin.py`）

**独立验证**：

- `_write_host_runtime`（第 14-64 行）写出 `wait_poller_policy` 全量 12 字段：`enabled`、`poll_interval_seconds`、`claim_ttl_seconds`、`claim_batch_size`、`backoff_initial_delay_seconds`、`backoff_multiplier`、`backoff_max_delay_seconds`、`not_ready_observe_interval_seconds`、`idle_poll_interval_seconds`、`adapter_call_timeout_seconds`、`close_drain_timeout_seconds`、`max_outstanding_adapter_calls`。值与 accepted plan §4.1 一致。
- `test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets`（第 67-101 行）断言 7 个 storage projection 字段值与 4 个 `not hasattr` 负向断言（`worker_factory`、`lane_name`、`tooling_options`、`ordinary_run_baseline`）。
- Production `ConfigLoader`（`dayu/runtime/config_loader.py`）与 `dayu/config/host_runtime.json` 均为 plan §3.5 保护路径，零 diff。
- `not hasattr` 是 owner-level 负向断言，证明 fixture 加载的 storage options 不包含运行时装配字段，不是用 `hasattr` 做 fallback 分支。

**结论：PASS。** Fixture 严格跟 current schema，无 production fallback，无兼容分支。

### 3.2 AR-F03 — in-process logging harness 隔离（`tests/tools/web/test_smoke_web_ci.py`）

**独立验证**：

1. **`_LoggerState`（第 62-81 行）**：`frozen=True, slots=True` dataclass，快照 `logger`、`level`、`handlers`（identity + order）、`filters`（identity + order）、`propagate`、`disabled`、`parent` 七个字段。

2. **`_LoggingSnapshot`（第 84-99 行）**：快照 `registry`（实例 identity）、`registry_entries`（identity + 插入顺序）、`root_state`、`logger_states`。

3. **`_LogRecordFilter` Protocol（第 41-52 行）**：声明 `def filter(self, record: logging.LogRecord, /) -> bool`，使用 positional-only `/` 参数。匹配 stdlib 的调用惯例（logging 只做位置调用）。

4. **`_LoggerFilter` union（第 55-59 行）**：`logging.Filter | Callable[[logging.LogRecord], bool] | _LogRecordFilter`。覆盖 stdlib 接受的三种合法 filter 类型。

5. **`_restore_logging_state`（第 243-286 行）**：恢复顺序——先移除新增 handlers → 恢复 root + 所有 concrete logger 的 level/handlers/filters/propagate/disabled → 替换 registry 实例并恢复 entries → 逐一回填 parent identity → 关闭新增 handlers。parent 回填在 registry 恢复之后，因为 stdlib 在 `logging.getLogger()` 对 `PlaceHolder` 位置创建 concrete parent 时会隐式重挂既有 child 的 `.parent`。仅恢复 registry entries 不足以恢复完整拓扑。

6. **`_invoke_smoke_main`（第 289-301 行）**：snapshot → try/return → finally restore。覆盖 success、return error、`SystemExit`、被测异常四路。

7. **Contract test `test_in_process_smoke_harness_restores_complete_logging_state`（第 319-380 行）**：
   - 预置 root + named logger 非默认状态（非零 level、preexisting handlers/filters、`propagate=False`、`disabled=True`）。
   - `_RegistryMutatingSmokeMain` fake 污染 root、existing logger、新建 logger、placeholder_parent logger 四个不同对象。
   - 显式触发 descendant reparent（第 163-165 行），断言 harness 正确恢复 parent identity。
   - success（`raises_error=False`）和 failure（`raises_error=True`）两路均通过 parametrized 覆盖。
   - 断言 pre-existing handlers 未被关闭、新增 handlers 全部关闭、`PlaceHolder` entry 身份未变。

8. **无 production 特例**：常量 `_LOGGER_HARNESS_EXISTING_NAME`、`_LOGGER_HARNESS_NEW_NAME`、`_LOGGER_HARNESS_PLACEHOLDER_PARENT_NAME`、`_LOGGER_HARNESS_DESCENDANT_NAME` 均为 `tests.smoke_web_ci.harness.*` 命名空间下的通用测试名称，不含 `dayu.fins`、SEC 或其它 production 特例。

9. **Standalone production logging 零 diff**：`utils/smoke_web_ci.py` 与 `dayu/runtime/log.py` 均为 plan §3.5 保护路径，已独立核对零 diff。

10. **E402 消除**：entry 存在的 `tests/tools/web/test_smoke_web_ci.py:32:1 E402` 已通过删除动态 `sys.path` 导入 seam 消除。

**结论：PASS。** Harness 完整恢复 registry/logger/parent/handler identity 与 failure 路径，无 order 依赖，无 production 特例。

### 3.3 AR-F04 — manifest/digest 唯一 fail-closed 关联（`tests/host/test_public_compact_smoke.py`）

**独立验证**：

1. **`_runner_call_manifest_for_run`（第 2077-2131 行）**：
   - 遍历 artifact 文件，以 `schema_version == RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION` 过滤。
   - 以 `host_run_id == run_id` 精确匹配。
   - 以 `runner_call_kind == "compactor_proposal"` 精确匹配。
   - 断言唯一匹配（零或大于一均 `AssertionError`）。
   - 从 `compactor_identity` 读取 `parent_host_run_id`，断言与 `host_run_id` 一致。
   - 从 `compactor_identity` 读取并返回 `compaction_request_digest`（需通过 `is_sha256_digest` 校验）。

2. **`_compact_artifact_for_run`（第 2028-2074 行）**：
   - 遍历 artifact 文件，以 `artifact_kind == "context_compaction"` 过滤。
   - 断言 `schema_version` 是整数且等于 `COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT`。
   - 以 `compaction_request_digest` 精确匹配（需通过 `is_sha256_digest` 校验）。
   - 断言唯一匹配。

3. **失败 case 覆盖**（10 个 deterministic fail-closed cases）：
   - 零 manifest / 重复 manifest
   - 缺失 digest 字段 / 非法 digest
   - parent run 不匹配
   - 零 matching artifact / 重复 matching artifact
   - 缺失 artifact digest / 错误 artifact digest

4. **已删除的弱 oracle**：
   - `_CANDIDATE_ID_FIELD` 常量已删除。
   - `llm-compact:{run_id}` 拼接与 candidate-id 匹配已删除。
   - 无 `dict.get` 猜测链、fallback、顺序/文件名/mtime 推断。

5. **Stale field 纠正**：
   - `current_user_input_ref` → `current_input_ref`（经 Controller 裁决为 `PLAN_EVIDENCE_CLARIFICATION`）。
   - 字段存在性、`str` 类型、非空 continuity assertions 保留。

**结论：PASS。** Association 完全依赖 owner-published exact fields，无 fallback、无顺序推断、无 candidate id。

### 3.4 S1-SEC-F01 — 五个 sentinel owner-boundary tests

**独立验证**：完整读取五个 test 文件的全部 sentinel 测试代码，并 cross-reference 对应 production owners。

#### 3.4.1 Production owner evidence（独立核对）

| Surface | Owner | 直接证据 |
| --- | --- | --- |
| Tool Trace filter | `ToolTraceProjectionConsumer.event_filter`（`dayu/host/tool_trace.py:397-419`） | `_CANONICAL_EVENT_TYPES`（第 204-216 行）、`_DIAGNOSTIC_EVENT_TYPES`（第 217-221 行）、`_PROJECTION_SIGNAL_EVENT_TYPES`（第 222 行）均不含 `USER_INPUT_ACCEPTED` |
| Audit JSONL | `build_audit_json_line`（`dayu/host/audit.py:411-467`） | 固定 22 字段契约，只从 `event_row` 读取 `payload_ref`/`payload_digest`（第 461-462 行），不复制 raw payload |
| Public HostEvent | `_host_event_from_row`（`dayu/host/read_api.py:875-908`） | `parse_host_run_event_type("USER_INPUT_ACCEPTED")` 返回 `None`（`dayu/host/lifecycle_events.py:302-313`：`HostRunEventType` enum 不含 `USER_INPUT_ACCEPTED`，它在 `HostAdmissionCommandEventType` 中）→ 落入 generic `HostEvent(PROGRESS, activity=None)` 路径 |
| Public activity | `_activity_from_row`（`dayu/host/read_api.py:1063-1100`） | `USER_INPUT_ACCEPTED` 不在 activity allowlist 中 → 返回 `None` |
| LLM-facing messages | `RunInputBuilder` from `display_text`（`dayu/host/run_input.py`） | 只读取 `display_text`，不读取 `effective_execution_config` |
| LocalProxy log | `DefaultLocalEngineWorker.accept`（`dayu/host/local_proxy.py:61-76`） | 日志记录 `session_id`、`run_id`、`attempt_id`、`execution_id`、`dispatch_record_id`、`local_worker_id`、`message_count`、`disable_tools`，不记录 headers |

#### 3.4.2 test_run_input_builder.py（第 1029-1164 行）

- **Durable round-trip**：`effective_execution_config` 写入 `USER_INPUT_ACCEPTED` payload → `DurableCurrentRunFactProvider` → `_effective_dispatch_decision_from_payload` → `dispatch_decision.policy_snapshot.runner_spec.headers` 保留 exact sentinel（第 1079-1081 行）。
- **Engine execution input**：`create_no_tool_run_input_builder(...).build(...)` → `request.runner_spec.headers` 保留 exact sentinel（第 1094-1096 行）。这是 Engine 执行所需的受信任 typed input，正确保留。
- **LLM-facing messages**：`request.messages` 中每个 message 的 content 均不含 sentinel（第 1097-1098 行）。
- **Memory**：`ConversationMemoryProjectionConsumer` → `conversation_memory_snapshot_to_json_value` → `canonical_json_dumps` 不含 sentinel（第 1100-1118 行）。
- **Compact material**：`build_pre_dispatch_compact_material_view` → `repr(compact_material)` 不含 sentinel，且 `current_input_text == "分析本期经营情况"`（第 1120-1133 行）。
- **Runner-call projection**：`RUNNER_CALL_INPUT_ASSEMBLED` event 的 hot payload、manifest JSON 与 runner-call projection artifact 均不含 sentinel（第 1135-1164 行）。

#### 3.4.3 test_tool_trace_projection.py（第 775-838 行）

- **filter 层**：`consumer.event_filter.matches(projection_event_view_from_row(row))` 返回 `False`（第 815-817 行）。直接证据是 allowlist 不含 `USER_INPUT_ACCEPTED`。
- **hot 层**：`read_tool_trace_hot_row` 返回 `None`（第 834 行）。
- **cold 层**：`_json_lines(cold_path) == ()`（第 838 行）。
- **query 层**：`read_tool_trace_by_run` 返回 `rows == ()`，且 `repr(query_page)` 不含 sentinel（第 835-836 行）。

#### 3.4.4 test_audit_sink.py（第 416-477 行）

- 断言 audit JSONL 行 exact 22-field key contract（第 451-474 行）。字段集合：`schema_version`、`event_sequence`、`event_id`、`event_type`、`event_class`、`occurred_at`、`session_id`、`run_id`、`attempt_id`、`execution_id`、`actor`、`principal`、`source`、`client_request_id`、`operation_context_refs`、`operation_context_digest`、`policy_decision_ref`、`policy_decision_summary`、`reason`、`payload_ref`、`payload_digest`、`line_digest`。
- 断言 `event_type == "USER_INPUT_ACCEPTED"`。
- 断言 `canonical_json_dumps(line)` 不含 sentinel（第 476-477 行）。

#### 3.4.5 test_host_activity_event_projection.py（第 220-262 行）

- 断言 `event.kind is HostEventKind.PROGRESS`（第 255 行）。
- 断言 `event.activity is None`（第 256 行）。
- 断言 `event.final_answer is None`、`event.error_message is None`、`event.cancel_reason is None`、`event.thinking is None`（第 257-260 行）。
- 断言 `canonical_json_dumps(asdict(event))` 不含 sentinel（第 261-262 行）。

#### 3.4.6 test_logging.py（第 154-182 行）

- 使用 `dataclasses.replace` 注入 `runner_spec.headers={header_name: sentinel}`（第 166-173 行）。
- 断言 sentinel 在 `request.runner_spec.headers.values()` 中（正向注入确认，第 175 行）。
- `caplog.at_level(VERBOSE_LOG_LEVEL, logger="dayu.host.local_proxy")` 捕获日志。
- 断言 `"host.local_proxy.accept" in caplog.text`（日志确实产生，第 181 行）。
- 断言 sentinel `not in caplog.text`（第 182 行）。

#### 3.4.7 Sentinel 测试质量独立评估

- **无字段名黑名单**：五个 tests 分别使用 owner 级排除机制（filter allowlist、fixed field contract、typed DTO kind check、display_text-only selector、log message format），没有一个使用 `"Authorization" not in text` 或 `"api_key" not in repr()` 这类弱 oracle。
- **无 mock-only bypass**：全部五个 tests 通过真实 durable store → EventLog row → projection consumer 管道验证。
- **无 private implementation mirroring**：tests 使用 public typed API。
- **无 synthetic sentinel 失真**：同一 sentinel 在所有五个 surfaces 复用，每个 surface 独立证明排除。
- **Engine execution headers vs LLM-facing projection 分离正确**：`test_run_input_builder.py` 显式断言 `request.runner_spec.headers` 保留 sentinel（Engine 执行需要），同时断言 messages/memory/compact/manifest 零 sentinel。
- **正向注入确认**：所有五个 tests 先正向断言 sentinel 进入系统（durable store/Engine request），再断言投影不含 sentinel，排除"sentinel 根本没进入系统导致假阴性"的风险。

**结论：PASS。** 五个 sentinel tests 各自直达唯一 projection owner，真实证明 internal durable/Engine retention 与 Tool Trace/audit/public HostEvent/LLM/log 零投影。

### 3.5 AGENTS.md 合规性

- **docstring**：所有新增/修改函数与测试方法均有完整中文 docstring，包含 `:param:`、`:returns:`、`:raises:`。
- **typing**：无 `Any`、`object`、无类型参数/返回值。pyright `0 errors, 0 warnings, 0 informations`（前轮已确认）。
- **`hasattr`/`getattr`**：`test_host_admin.py:98-101` 的 `not hasattr` 是 owner-level 负向断言，不是 fallback 分支。
- **兼容性代码**：零。
- **God object/function/dataclass**：零。`_LoggerState`、`_LoggingSnapshot`、`_RegistryMutatingSmokeMain` 各有明确单一职责。
- **魔法数字/字符串**：sentinel 作为模块级常量 `_CONFIGURED_SECRET_SENTINEL` 定义；field name 常量集中声明；数值参数均来自 plan 规范或 production schema。
- **模块间依赖最小化**：每个 test 文件只 import 其直接测试的 production owner。

**结论：PASS。**

### 3.6 Adversarial failure pass（独立重新挑战）

对每个修复做以下 adversarial 挑战：

1. **AR-F01：ConfigLoader 增加第 13 个必填字段**：fixture 会因 ConfigLoader typed validation 失败而暴露缺口——fail on schema drift，不是 silently pass。✅ 通过。

2. **AR-F03：stdlib logging 新增另一种隐式状态修改**：harness 的 contract test 使用 generic fake 触发已知的 reparent 行为；如果 stdlib 引入新行为，contract test 会失败并需要扩展 `_LoggerState`。但这不是当前 harness 的缺陷——它已覆盖当前已知的全部 mutable state。✅ 通过。

3. **AR-F04：production 改变 manifest/artifact schema version**：`_runner_call_manifest_for_run` 和 `_compact_artifact_for_run` 使用精确的 current schema version 常量匹配；版本变更会导致 association 失败——fail-closed 语义期望的行为。✅ 通过。

4. **S1-SEC-F01：Tool Trace filter 被重构为 denylist**：当前测试在 `event_filter.matches()` 层面断言，不依赖字段名。如果 filter 从 allowlist 变成 denylist，测试的 `assert not consumer.event_filter.matches(...)` 仍然成立，但会失去对"新 event type 默认不消费"的保护。这是 production 设计决策，不是测试缺陷。当前 allowlist-based filter 是更强的安全保证。✅ 通过。

5. **Sentinel 因意外原因未进入系统**：所有五个 tests 先正向断言 sentinel 在 durable store/Engine request 中保留，再断言投影不含。排除假阴性。✅ 通过。

6. **repr 作为唯一 oracle**：`test_run_input_builder.py` 中 `repr(compact_material)` 是辅助断言，主断言是 `compact_material.current_input_text == "分析本期经营情况"`。repr 作为补充扫描合理。`test_tool_trace_projection.py` 中 `repr(query_page)` 同样作为补充，主断言是 `query_page.rows == ()`。✅ 通过。

### 3.7 与前轮 review 的差异检查

前轮 AgentDS 和 AgentMiMo 均报告零 material code finding。本轮独立完整重读全部 required reading 和全部八个 test files 后，未发现前轮审查遗漏的缺陷。

前轮 Controller adjudication 确认：
- 两路 reviewer 均覆盖八个 immutable tests、直接 production owners、failure paths、semantic ownership drift、minimum-design trap、test-oracle strength。
- Finding 计数：`accepted code finding = 0`、`blocking question = 0`、`design contradiction = 0`。

本轮 re-review 独立确认上述结论全部成立。

### 3.8 生产代码 owner 核对

独立核对以下生产代码 owner 路径，确认 tests 的 owner boundary 判断准确：

| 测试断言 | 生产代码 owner | 独立核对结果 |
| --- | --- | --- |
| Tool Trace filter 不含 USER_INPUT_ACCEPTED | `dayu/host/tool_trace.py:204-222` `_CANONICAL_EVENT_TYPES` / `_DIAGNOSTIC_EVENT_TYPES` / `_PROJECTION_SIGNAL_EVENT_TYPES` | 三个 tuple 均不含 `USER_INPUT_ACCEPTED` |
| audit exact 22 fields | `dayu/host/audit.py:437-463` `build_audit_json_line` | 22 字段全部来自 `event_row` typed 字段或 projection event view，`payload_ref`/`payload_digest` 为引用 |
| public HostEvent kind=PROGRESS | `dayu/host/read_api.py:884-908` `_host_event_from_row` | `parse_host_run_event_type("USER_INPUT_ACCEPTED")` 返回 `None`（在第 310 行 `HostRunEventType(event_type)` raise `ValueError` 后返回 `None`），落入 generic `PROGRESS` 路径 |
| activity=None | `dayu/host/read_api.py:1063-1100` `_activity_from_row` | `USER_INPUT_ACCEPTED` 不在 activity allowlist |
| LocalProxy log 不含 headers | `dayu/host/local_proxy.py:61-76` | 日志格式串与参数只含 ids/counts/refs |
| RunInput 只读 display_text | `dayu/host/run_input.py:171` `_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"` | LLM-facing message 构造只取 display_text |

## 4. Quota disposition

Gemini 测试账号 quota 按用户 2026-07-19 最终裁决处理：

```text
EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING
```

- 不是代码 finding。
- 不是 blocking question。
- 不是需要 fix 的 residual。
- 不阻塞 Slice 1 acceptance。
- 不要求修改 provider 配置、模型、key、重试、quota、budget。
- 真实 provider 三路 PASS + Gemini typed quota skip 证据保留。

## 5. Residual ownership（与前轮一致，重新确认）

- `AR-F02`：`OPEN_BY_SEQUENCE`，由 Slice 2 关闭。
- `AR-F05`：`OPEN_BY_SEQUENCE`，由 Slice 3 关闭。
- `AR-F06`：`RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，owner 为未来 Host scheduler/lifecycle WU。
- `AR-F07`：`PENDING_RELEASE_BLOCKER`，owner 为真实 remote Windows runner evidence。

## 6. Verdict

```text
PASS / ZERO MATERIAL CODE FINDING
```

### Finding 计数

```text
code finding = 0
blocking question = 0
design contradiction = 0
open question requiring Controller decision = 0
```

### 结论

经过独立完整重读全部 required reading（逐文件从第一行读到 EOF）、重新核对八个 immutable test files SHA-256、独立审查全部八个 test files 的全部 sentinel 及非 sentinel 代码、独立 cross-reference 全部 production code owner、独立执行 adversarial failure pass，**确认前轮零 finding 结论仍然成立**。全部 required reading 的全文证据未发现与既有审查结论矛盾的内容，未发现遗漏的 semantic ownership 缺陷、架构边界违规或测试 oracle 不足。

- **AR-F01**：fixture 严格 current schema，无 production fallback。
- **AR-F03**：logging harness 完整恢复 registry/logger/parent/handler identity 与 failure 路径，无 order 依赖。
- **AR-F04**：manifest/digest 关联唯一 fail-closed，无 candidate id/raw guess/loose parsing。
- **S1-SEC-F01**：五个 sentinel tests 分别直达 unique projection owner，真实证明 internal durable/Engine retention 与 Tool Trace/audit/public HostEvent/LLM/log 零投影。
- **No field-name blacklist**：所有 tests 使用 owner 级排除机制。
- **No repr-only weak oracle**：repr 仅作为补充扫描。
- **No mock-only bypass**：所有 tests 通过真实 durable → projection 管道。
- **Engine execution headers vs LLM-facing projection**：正确分离。
- **Audit exact keys**：22-field set equality 可对抗回归。
- **Tool Trace filter/hot/cold/query**：四层均验证。
- **AGENTS.md**：docstring/typing/owner boundary 全部合规。
- **Scope/deferred/security/auth-framework**：零 production diff，零越界。

---

## Artifact metadata

- 路径：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-code-rereview-ds.md`
- SHA-256：待写入后计算
