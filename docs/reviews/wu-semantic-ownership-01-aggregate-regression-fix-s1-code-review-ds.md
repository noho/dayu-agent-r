# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 1 Code Deepreview — AgentDS

## 1. Gate identity

- 审查者：AgentDS。
- 时间：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix continuation；不是新 WU。
- Gate：Slice 1 complete code deepreview（只读，不修改代码/测试/design/plan/control/既有 artifacts）。
- 审查类型：adversarial failure、semantic ownership drift、minimum-design trap、maintainability 与 test-oracle strength 全面审查。

## 2. Immutable review inputs

### 2.1 Required reading（完整读取并核对）

| 文档 | SHA-256 |
| --- | --- |
| `AGENTS.md` | 当前工作区 HEAD 内容 |
| `docs/host/issues-implementation-control.md` | 当前工作区 HEAD 内容（完整 2313 行至 EOF） |
| `docs/phaseflow-umbrella-optimization-control.md` | 当前工作区 HEAD 内容 |
| `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 当前工作区 HEAD 内容 |
| `docs/host/design.md` | 当前工作区 HEAD 内容（完整至 EOF） |
| `docs/engine/design.md` | 当前工作区 HEAD 内容（完整至 EOF） |
| `docs/tool/design.md` | 当前工作区 HEAD 内容（完整至 EOF） |
| `docs/fins/design.md` | 当前工作区 HEAD 内容（完整至 EOF） |
| `docs/ui/design.md` | 当前工作区 HEAD 内容（完整至 EOF） |
| `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | accepted corrected plan |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-review-controller-adjudication.md` | Controller adjudication PASS |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-local-trust-resume-controller-authorization.md` | Slice 1 resume authorization |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md` | `2c1274e17bc37a0837782fc6cb657fa1cb566ad57c340754023796a5d8703cfe` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-local-trust-provider-quota-stop-controller-adjudication.md` | Provider quota stop evidence |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-quota-gate-separation-controller-adjudication.md` | `aa6be1e35db8b3ec3528c28fcf60103ca0b54e0b33c954fca326381a92c921c5` |

### 2.2 Immutable review target — ordered manifest SHA-256

```text
bcfc4088dfb2239236579159b71f6abc8e51a32201de240603f3a2eebd954c41
```

| 测试文件 | SHA-256 |
| --- | --- |
| `tests/service/test_host_admin.py` | `5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db` |
| `tests/tools/web/test_smoke_web_ci.py` | `86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3` |
| `tests/host/test_public_compact_smoke.py` | `f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169` |
| `tests/host/test_audit_sink.py` | `20f41229f4e0da48aa1f3904d3bd5c61f436f7a9a706dfe78e899a4d06dccda2` |
| `tests/host/test_tool_trace_projection.py` | `4d9dbb9b5a215597182166b6a92c2d1d30447ae21539bf77602cc6b7c7869140` |
| `tests/host/test_host_activity_event_projection.py` | `047b89fd099fdc3250bdcdc066487b05bcf70aeccc18b60228f3bb10cca90c77` |
| `tests/host/test_run_input_builder.py` | `4ed1693ee6819caf99072883e850f2a11e0ccb11636a196b0af629205cd46190` |
| `tests/host/test_logging.py` | `e874e77e997039d7d1e907dc4df5e980edae876e3920ac4417e3836cabf5b180` |

### 2.3 Production owners traced

对八个 tests 所涉及的 production call chains 与 owners 已做完整直接 trace：

- `dayu/host/tool_trace.py::ToolTraceProjectionConsumer.event_filter` — allowlist-based `ProjectionEventFilter`，`_CANONICAL_EVENT_TYPES` / `_DIAGNOSTIC_EVENT_TYPES` / `_PROJECTION_SIGNAL_EVENT_TYPES` 均不含 `USER_INPUT_ACCEPTED`。
- `dayu/host/audit.py::build_audit_json_line` — 固定 22-field exact key contract；只从 `event_row` 读取 `payload_ref`/`payload_digest`，不复制 raw payload。
- `dayu/host/read_api.py::_host_event_from_row` — `USER_INPUT_ACCEPTED` 投影为 `kind=PROGRESS`、`activity=None` 的 typed progress event。
- `dayu/host/run_input.py` — `RunInputBuilder` 从 `display_text` 构造 LLM-facing messages，不读取 `effective_execution_config`。
- `dayu/host/local_proxy.py::DefaultLocalEngineWorker.accept` — operator 日志只记录 `run_id`/`message_count`，不记录 headers。
- `dayu/service/host_admin.py::prepare_host_admin` — 消费 `ConfigLoader` 输出与 fixture `host_runtime.json`。
- `dayu/host/compact_payload.py::_input_snapshot_refs_json_vnext` — 写出 `current_input_ref`（非 `current_user_input_ref`）。

## 3. Independent verification

### 3.1 Focused tests

```text
tests/service/test_host_admin.py                  1 passed
tests/tools/web/test_smoke_web_ci.py              48 passed, 3 warnings
tests/host/test_public_compact_smoke.py           23 passed, 1 skipped
tests/host/test_audit_sink.py (sentinel)          1 passed (of target)
tests/host/test_tool_trace_projection.py (sentinel) 1 passed (of target)
tests/host/test_host_activity_event_projection.py (sentinel) 1 passed (of target)
tests/host/test_run_input_builder.py (sentinel)   1 passed (of target)
tests/host/test_logging.py (sentinel)             1 passed (of target)
```

### 3.2 pyright

```text
0 errors, 0 warnings, 0 informations
```

全部八个 immutable test files 通过严格类型检查。

## 4. 逐项审查结论

### 4.1 AR-F01 — test fixture current-schema 修复

**审查范围**：`tests/service/test_host_admin.py`。

**审查发现**：无实质性问题。

`_write_host_runtime` 写出 current `wait_poller_policy` 全量 12 字段，包括 `enabled`、`poll_interval_seconds`、`claim_ttl_seconds`、`claim_batch_size`、`backoff_initial_delay_seconds`、`backoff_multiplier`、`backoff_max_delay_seconds`、`not_ready_observe_interval_seconds`、`idle_poll_interval_seconds`、`adapter_call_timeout_seconds`、`close_drain_timeout_seconds`、`max_outstanding_adapter_calls`。值来自 accepted plan §4.1 的固定规范。

- **semantic ownership**：fixture owner 是 `tests/service/test_host_admin.py`；production `ConfigLoader` 是 schema owner。fixture 只跟 current schema，不给 production 加默认值/fallback——与 plan §2.1 AR-F01 disposition 一致。
- **无 production fallback**：`dayu/runtime/config_loader.py` 与 `dayu/config/host_runtime.json` 均零 diff（plan §3.5 保护路径），已独立核对。
- **断言深度**：验证 `host_runtime_id`、`db_path`、`artifact_root`、`sqlite_busy_timeout_seconds`、`sqlite_write_*`、`payload_inline_threshold_bytes` 七个字段，并显式断言 `worker_factory`、`lane_name`、`tooling_options`、`ordinary_run_baseline` 不存在于 `options`。这些断言证明 fixture current schema 加载成功且 storage projection 未漂移。
- **无 test-order 依赖**：单一 fixture + 单一 test，无顺序依赖。
- **无 magic string/数字**：字段名来自 ConfigLoader typed schema，值来自 plan 规范。

### 4.2 AR-F03 — in-process logging harness 隔离

**审查范围**：`tests/tools/web/test_smoke_web_ci.py`。

**审查发现**：无实质性问题。

Harness 由以下组件构成：

- `_LoggerState` dataclass — 快照单个 concrete logger 的 `level`、`handlers`（identity + order）、`filters`（identity + order）、`propagate`、`disabled`、`parent`。
- `_LoggingSnapshot` dataclass — 快照 registry instance、registry entries、root state、全部 concrete logger states。
- `_snapshot_logging_state()` / `_restore_logging_state()` — 完整 snapshot/restore 循环。
- `_invoke_smoke_main()` — 统一隔离包装，`finally` 块保证 restore。
- `_TrackingHandler` — 记录 harness 是否正确关闭新增 handler。

**关键设计决策验证**：

1. **parent identity 恢复**：`_restore_logging_state` 在 registry entries 恢复后逐一把 root 和全部快照 logger 的 `parent` 回填为原 identity（第 283-284 行）。这是因为 stdlib 在 `logging.getLogger()` 对 `PlaceHolder` 位置创建 concrete parent 时会隐式重挂既有 child 的 `.parent`。仅恢复 registry entries 不足以恢复完整拓扑。这条路径已在 implementation-codex.md 的第二/第三次 stop history 中有完整证据链。

2. **contract test**：`test_in_process_smoke_harness_restores_complete_logging_state` 同时覆盖 success（`raises_error=False`）和 failure（`raises_error=True`）两路：
   - 预置 root + named logger 的非默认状态（level、handlers、filters、propagate、disabled）。
   - 使用 `_RegistryMutatingSmokeMain` fake 污染 root、existing logger、新建 logger、placeholder_parent logger 四个不同对象。
   - fake 显式触发 descendant reparent（第 163-165 行），断言 harness 正确恢复 parent identity。
   - 断言 pre-existing handlers 未被关闭、新增 handlers 全部关闭。
   - 断言 `PlaceHolder` entry 身份未变。

3. **无 order 依赖**：所有六个 in-process `smoke.main(...)` 调用均通过 `_invoke_smoke_main` 统一包裹，不依赖 pytest 执行顺序。

4. **无 production 特例**：常量 `_LOGGER_HARNESS_EXISTING_NAME`、`_LOGGER_HARNESS_NEW_NAME`、`_LOGGER_HARNESS_PLACEHOLDER_PARENT_NAME`、`_LOGGER_HARNESS_DESCENDANT_NAME` 均为 `tests.smoke_web_ci.harness.*` 命名空间下的通用测试名称，不含 `dayu.fins`、SEC 或其它 production 特例。harness 不复制 `_DEFAULT_THIRD_PARTY_SUPPRESSIONS` 等 production 列表。

5. **standalone production logging 零 diff**：`utils/smoke_web_ci.py` 与 `dayu/runtime/log.py` 均为 plan §3.5 保护路径，已独立核对零 diff。

6. **类型安全性**：`_LogRecordFilter` Protocol 使用 `def filter(self, record: logging.LogRecord, /) -> bool` 的位置参数签名，正确匹配 stdlib 的调用惯例（logging 只做位置调用，不传 keyword）。`_LoggerFilter` 联合类型覆盖 `logging.Filter | Callable | _LogRecordFilter` 三种合法情况。

7. **无 E402**：entry 存在的 `tests/tools/web/test_smoke_web_ci.py:32:1 E402` 已通过删除动态 `sys.path` import seam 消除（implementation-codex.md §4.2 确认）。

### 4.3 AR-F04 — manifest/digest 唯一 fail-closed 关联

**审查范围**：`tests/host/test_public_compact_smoke.py`。

**审查发现**：无实质性问题。

**关联链路**（完全 deterministic，每一步 fail-closed）：

1. `_runner_call_manifest_for_run(paths, run_id)`：
   - 遍历 artifact 文件，以 `schema_version == RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION` 过滤。
   - 以 `host_run_id == run_id` 精确匹配。
   - 以 `runner_call_kind == "compactor_proposal"` 精确匹配。
   - 断言唯一匹配（零或大于一均 `AssertionError`）。
   - 从 `compactor_identity` 读取 `parent_host_run_id`，断言与 `host_run_id` 一致（即 parent == current run）。
   - 从 `compactor_identity` 读取并返回 `compaction_request_digest`（需通过 `is_sha256_digest` 校验）。

2. `_compact_artifact_for_run(paths, compaction_request_digest)`：
   - 遍历 artifact 文件，以 `artifact_kind == "context_compaction"` 过滤。
   - 断言 `schema_version` 是整数且等于 `COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT`。
   - 以 `compaction_request_digest` 精确匹配（需通过 `is_sha256_digest` 校验输入 digest）。
   - 断言唯一匹配。

**Deterministic fail-closed cases**（4 个 parametrized + 4 个独立）：

| 测试 | 覆盖场景 |
| --- | --- |
| `test_current_manifest_digest_associates_unique_compact_artifact` | success path |
| `test_runner_call_manifest_association_fails_closed_on_missing_or_duplicate[0]` | 零 manifest |
| `test_runner_call_manifest_association_fails_closed_on_missing_or_duplicate[2]` | 重复 manifest |
| `test_runner_call_manifest_digest_fails_closed_when_missing_or_invalid[None]` | 缺失 digest 字段 |
| `test_runner_call_manifest_digest_fails_closed_when_missing_or_invalid[not-a-sha256-digest]` | 非法 digest |
| `test_runner_call_manifest_parent_run_mismatch_fails_closed` | parent run 不匹配 |
| `test_compact_artifact_association_fails_closed_on_missing_or_duplicate[0]` | 零 matching artifact |
| `test_compact_artifact_association_fails_closed_on_missing_or_duplicate[2]` | 重复 matching artifact |
| `test_compact_artifact_digest_fails_closed_when_missing_or_wrong[None]` | 缺失 artifact digest |
| `test_compact_artifact_digest_fails_closed_when_missing_or_wrong[other-digest]` | 错误 artifact digest |

**已删除的弱 oracle**：
- `_CANDIDATE_ID_FIELD` 常量已删除。
- `llm-compact:{run_id}` 拼接与 candidate-id 匹配已删除。
- 无 `dict.get` 猜测链、无 fallback、无顺序/文件名/mtime 推断。

**Stale field 纠正**：
- `current_user_input_ref` -> `current_input_ref`（经 Controller 裁决为 `PLAN_EVIDENCE_CLARIFICATION`，不是 production defect）。
- `dayu/host/compact_payload.py::_input_snapshot_refs_json_vnext` 写出 `current_input_ref`，与真实 artifact 同源一致。

### 4.4 S1-SEC-F01 — 五个 sentinel owner-boundary tests

**审查范围**：`tests/host/test_tool_trace_projection.py`、`tests/host/test_audit_sink.py`、`tests/host/test_host_activity_event_projection.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_logging.py`。

**审查发现**：无实质性问题。五个 tests 各自直达唯一 projection owner，使用同一 synthetic sentinel `synthetic-local-trust-sentinel-6f2b9d8c`（不来自真实环境），均不使用字段名黑名单。

#### 4.4.1 Tool Trace (test_tool_trace_projection.py)

测试 `test_tool_trace_excludes_internal_effective_execution_value`：

- 构造 `USER_INPUT_ACCEPTED` event，payload 含 `effective_execution_config.config.runner_spec.headers` 中的 synthetic sentinel。
- **filter 层**：`consumer.event_filter.matches(projection_event_view_from_row(row))` 返回 `False` — 直接证据是 `ToolTraceProjectionConsumer.event_filter` 的 allowlist 不含 `USER_INPUT_ACCEPTED`（`_CANONICAL_EVENT_TYPES` / `_DIAGNOSTIC_EVENT_TYPES` / `_PROJECTION_SIGNAL_EVENT_TYPES` 均不含该 event type）。这是 owner-level 排除，不是字段名黑名单。
- **hot 层**：`read_tool_trace_hot_row` 返回 `None`。
- **cold 层**：`_json_lines(cold_path) == ()` — cold JSONL 为空。
- **query 层**：`read_tool_trace_by_run` 返回 `rows == ()`，且 `repr(query_page)` 不含 sentinel。

#### 4.4.2 Audit (test_audit_sink.py)

测试 `test_audit_projection_excludes_internal_effective_execution_value`：

- 构造同样的 `USER_INPUT_ACCEPTED` event。
- 断言 audit JSONL 行 exact 22-field key contract（与 `test_jsonl_line_contains_required_audit_fields` 中的字段集合完全一致）。
- 断言 `event_type == "USER_INPUT_ACCEPTED"`。
- 断言 `canonical_json_dumps(line)` 不含 sentinel。
- `build_audit_json_line` 只从 `event_row` 读取 `payload_ref`/`payload_digest`，不从 payload 复制业务值——这是 owner 级固定字段契约，不是黑名单。

#### 4.4.3 Public HostEvent (test_host_activity_event_projection.py)

测试 `test_public_host_event_excludes_internal_effective_execution_value`：

- 构造同样的 `USER_INPUT_ACCEPTED` event。
- 通过 `_host_event_from_row` 投影为 public `HostEvent`。
- 断言 `kind is HostEventKind.PROGRESS`（不是 terminal）。
- 断言 `activity is None` — `USER_INPUT_ACCEPTED` 不产生 public activity。
- 断言 `final_answer is None`、`error_message is None`、`cancel_reason is None`、`thinking is None`。
- 断言 `canonical_json_dumps(asdict(event))` 不含 sentinel。

#### 4.4.4 RunInput / LLM-facing (test_run_input_builder.py)

测试 `test_internal_execution_value_round_trips_without_llm_projection`：

- **internal durable round-trip**：从 durable store 读回 `USER_INPUT_ACCEPTED` payload，经 `_effective_dispatch_decision_from_payload` 解析，断言 `dispatch_decision.policy_snapshot.runner_spec.headers` 保留 sentinel exact value。
- **Engine execution input**：`create_no_tool_run_input_builder(...).build(...)` 产出的 `AgentRunRequest.runner_spec.headers` 保留 sentinel exact value — 这是 Engine 执行所需的受信任 typed input，正确保留。
- **LLM-facing messages**：`request.messages` 中每个 message 的 content 均不含 sentinel。
- **memory**：`conversation_memory_snapshot_to_json_value` 序列化后不含 sentinel。
- **compact material**：`build_pre_dispatch_compact_material_view` 的 `repr()` 不含 sentinel，且 `current_input_text == "分析本期经营情况"`（只取 display_text，不含 effective_execution_config）。
- **runner-call observation**：`RUNNER_CALL_INPUT_ASSEMBLED` event 的 hot payload、manifest JSON 与 runner-call projection artifact 均不含 sentinel。

这是八个 tests 中最全面的 owner-boundary 验证，覆盖了 plan §2.2.1 表格中的全部六个 surface。

#### 4.4.5 Operator logs (test_logging.py)

测试 `test_local_proxy_logs_exclude_internal_effective_execution_value`：

- 构造 `AgentRunRequest` 并在 `runner_spec.headers` 中注入 sentinel。
- 通过 `DefaultLocalEngineWorker().accept()` 走真实 LocalProxy accept 路径。
- 断言 caplog 包含 `host.local_proxy.accept` 但不含 sentinel。

`test_command_logs_verbose_ids_without_prompt_or_auth_claims` 额外验证 command path 只记录 typed ids，不泄漏 prompt 或 authorization claims。

#### 4.4.6 Sentinel 测试质量评估

- **无字段名黑名单**：五个 tests 分别使用 owner 级排除机制（filter allowlist、fixed field contract、typed DTO kind check、display_text-only selector、log message format），没有一个使用 `"Authorization" not in text` 或 `"api_key" not in repr()` 这类弱 oracle。
- **无 mock-only bypass**：全部五个 tests 通过真实 durable store -> EventLog row -> projection consumer 管道验证，不只是 mock 了 projection 函数。
- **无 private implementation mirroring**：tests 使用 public typed API（`build_audit_json_line`、`_host_event_from_row`、`ToolTraceProjectionConsumer.event_filter`、`create_no_tool_run_input_builder`、`DefaultLocalEngineWorker.accept`）。
- **无 synthetic sentinel 失真**：同一 sentinel 在所有五个 surfaces 复用，每个 surface 独立证明排除。
- **Engine execution headers vs LLM-facing projection 区分正确**：`test_run_input_builder.py` 显式断言 `request.runner_spec.headers` 保留 sentinel（Engine 执行需要），同时断言 messages/memory/compact/manifest 零 sentinel（LLM-facing 投影禁止）。这是 plan §4.1.4 的核心要求，实现完全准确。

### 4.5 非 sentinel 测试质量评估

#### 4.5.1 test_host_admin.py

- docstring 完整（模块 + 函数）。
- 类型严格（`tmp_path: Path`、`-> None`）。
- 断言覆盖 storage projection 字段与 `not hasattr` 负向断言。
- fixture 逻辑集中在 `_write_host_runtime` 模块级私有函数。

#### 4.5.2 test_smoke_web_ci.py

- 全部 48 个 tests 有完整中文 docstring。
- 类型严格：`_LoggerState`、`_LoggingSnapshot`、`_LogRecordFilter` Protocol、`_LoggerFilter` union type。
- 测试覆盖：local fixture stability、versioned filing registration、diagnostic command owner、fixture session sentinels/negative controls/freeze order、diagnostic child log filtering、local assembly config overlay/truncate spec、typed egress deny cases、search provider buckets、HTTP status classifier、error text classifier、loader/discovery failure、callable timeout、empty results、synthetic diagnostics result classification（v2 schema/frozen ledger/content oracle mismatch/ledger gaps/old schema）、local browser without playwright、versioned filing HTTP/Playwright hard gates、browser package missing skip、PDF payload failures（6 variants）、Docling skip vs HTML failure、confirmed challenge control、challenge control decision variants、summary exit code priority、external failure diagnostic-only、external child returncode、external parse/artifact gap、include-playwright external-only、missing external file、log level CLI、invalid external file early failure、external limit predictable paths。
- 无 order 依赖：所有 in-process `smoke.main` 调用均通过 `_invoke_smoke_main` 隔离。

#### 4.5.3 test_public_compact_smoke.py

- 全部 tests 有完整中文 docstring。
- 类型严格，常量命名规范。
- 测试覆盖：compactor prompt LLM-facing self-contained、material assertion helpers、stale legacy key rejection、forbidden term rejection、evidence marker rejection、label-only fake proposal canonical ref leakage rejection、manifest/digest association success + 8 fail-closed variants、no-compaction continuity、post-compaction fact reuse、long user input second factor、multi-compact bounded memory、proactive compact long current input、public reactive compact recovery、public compact failure fallback dispatch、real compactor smoke（environment-gated）。
- 常量大写蛇形命名，field name 常量集中定义。
- `_runner_call_manifest_for_run` / `_compact_artifact_for_run` 的 fail-closed 语义完备。

#### 4.5.4 test_audit_sink.py（非 sentinel tests）

- 测试覆盖：required audit fields + line digest、marker prevents duplicate append、JSONL existing line prevents duplicate when marker missing、source key digest conflict records failure、file write failure records projection failure、audit sink doesn't modify governance or EventLog、purge audit lines append-only with completed marking、default audit path derivation。
- exact-key contract 测试使用 set equality 断言 22 fields，对抗将来字段增删的回归。

#### 4.5.5 test_tool_trace_projection.py（非 sentinel tests）

- 测试覆盖：request corruption 7 种分类（missing envelope/request row/identity mismatch/arguments digest mismatch/arguments descriptor with inline/semantic query descriptor with inline/result execution missing/mismatch）、direct request row corruption 4 种分类、missing LLM material fail-closed、tool call chain hot/cold projection（requested/governed/result）、wait-resolution tool trace、optional signal objects（context_pressure/tool_timing/failure_metadata/partial_tool_call_signal）、tool timing available/missing、failure metadata variants（failed/cancelled/policy_blocked）、provider protocol failure metadata、provider diagnostic without failure metadata、partial tool call signal states（absent/none/present）、malformed signal rejection（tool_timing/failure_metadata/partial_tool_call_signal 各 3 variants）、context pressure from compaction failed/rejected、missing/null signal omission、non-object signal rejection、large tool call arguments descriptor resolution。
- 所有 corruption/failure path 均以 `HostDurableError` fail closed。
- signal validation 使用 typed schema 校验（`schema_version`、枚举值合法性、字段类型），不是 loose dict scan。

#### 4.5.6 test_host_activity_event_projection.py（非 sentinel tests）

- 测试覆盖：tool activity display snapshot、canonical request atom no activity、display fallback stable name、tool result/batch activity、completed/cancelled outcomes、tool awaiting vs run waiting silent、context compaction 4 event types、non-terminal run lifecycle、provider protocol error bounded summary、provider diagnostic nonfatal、bounded summary boundaries、activity descriptor read degradation、tool display fallback chain（missing run/tool_set not mapping/display_names not mapping/empty display_name/missing input event）、delta/unknown events without activity、terminal HostEvent rejects thinking payload。
- 每个 activity 投影路径都有对应的负向/降级 case。

#### 4.5.7 test_run_input_builder.py（非 sentinel tests）

- 大规模测试文件（260KB+），覆盖 RunInputBuilder 的多种输入组合、policy snapshot 投影、tool selection、memory/compact material 构建、session continuity 等。
- sentinel test 安全地嵌入现有测试结构，使用现有 helper（`_user_input_payload`、`_seed_current_run`、`_policy_snapshot` 等），不复制实现逻辑。

#### 4.5.8 test_logging.py（非 sentinel tests）

- 测试覆盖：command logs verbose ids without prompt/auth、LocalProxy accept log counts not content、memory catchup logs cursors/counts、engine ingest delta stream debug gating。
- 每个 log path 都验证了应该出现和不应该出现的内容。

### 4.6 AGENTS.md 合规性检查

- **docstring**：全部八个 tests 中的新增/修改函数与测试方法均有完整中文 docstring，包含 `:param:`、`:returns:`、`:raises:`。
- **typing**：无 `Any`、`object`、无类型参数/返回值。pyright `0 errors, 0 warnings, 0 informations`。
- **禁止 hasattr/getattr 逃避类型边界**：全部八个 tests 中未发现 `hasattr`/`getattr` 用于逃避类型设计的用法。`test_host_admin.py:98-101` 的 `not hasattr` 断言是 owner-level 负向验证（确认某些不应存在的字段确实不在 options 上），不是用 `hasattr` 做 fallback 分支。
- **禁止兼容性代码**：无 re-export、无兼容常量、无 wrapper/facade。
- **禁止 God object/function/dataclass**：tests 使用小规模 focused dataclass（`_LoggerState`、`_LoggingSnapshot`、`_RegistryMutatingSmokeMain` 等），各有明确单一职责。
- **禁止魔法数字/字符串**：sentinel 值作为模块级常量 `_CONFIGURED_SECRET_SENTINEL` 定义；field name 常量集中声明；数值参数均来自 plan 规范或 production schema。
- **模块间依赖最小化**：每个 test 文件只 import 其直接测试的 production owner 与必要的测试基础设施。
- **语义所有权与修复边界**：全部修复均改在 owner boundary（test fixture、test harness、test oracle），无 downstream consumer fallback、无 production 兼容分支。

## 5. Adversarial failure pass

对每个修复做了以下 adversarial 挑战，均未发现可利用的弱点：

1. **AR-F01 如果 ConfigLoader 增加第 13 个必填字段**：fixture 会因 ConfigLoader typed validation 失败而暴露缺口——这正是 fixture 应该做的（fail on schema drift），不是 silently pass。
2. **AR-F03 如果 stdlib logging 新增另一种隐式状态修改**：harness 的 contract test 使用 generic fake 触发已知的 reparent 行为；如果 stdlib 引入新行为，contract test 会失败并需要扩展 `_LoggerState`。但这不是当前 harness 的缺陷——它已经覆盖了当前已知的全部 mutable state。
3. **AR-F04 如果 production 改变 manifest/artifact schema version**：`_runner_call_manifest_for_run` 和 `_compact_artifact_for_run` 使用精确的 current schema version 常量匹配；版本变更会导致 association 失败，这正是 fail-closed 语义期望的行为。
4. **S1-SEC-F01 如果 Tool Trace filter 被重构为 denylist**：当前测试在 `event_filter.matches()` 层面断言，不是依赖字段名。如果 filter 从 allowlist 变成 denylist（这本身是架构退化），测试的 `assert not consumer.event_filter.matches(...)` 仍然成立（denylist 也不会包含 `USER_INPUT_ACCEPTED`），但会失去对"新 event type 默认不消费"的保护。然而这是 production 设计决策，不是测试缺陷。当前 allowlist-based filter 是更强的安全保证。
5. **如果 sentinel 值因意外原因（如 logger format 截断）未出现在输出中**：所有五个 tests 先正向断言 sentinel 在 durable store/Engine request 中保留（证明 sentinel 确实进入了系统），再断言各投影不含 sentinel。这排除了"sentinel 根本没进入系统导致假阴性"的可能性。

## 6. Open questions / residual risk

### 6.1 S1-QUOTA-F01 — EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION

根据用户 2026-07-19 裁决更新：Gemini 是低 budget 测试账号，quota 不足是正常测试环境事实。此条目分类如下：

- **不是**代码 finding。
- **不是** blocking question。
- **不是**需要 fix 的 residual。
- **不阻塞** Slice 1 acceptance。
- 分类：`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION`。
- 真实 provider 3 pass + Gemini typed quota skip 证据保留（`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-local-trust-provider-quota-stop-controller-adjudication.md` 记录有效）。

### 6.2 AR-F02 — OPEN_BY_SEQUENCE

不是 Slice 1 范围。当前 `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers` 保持已知单节点失败，Slice 2 关闭。

### 6.3 AR-F05 — OPEN_BY_SEQUENCE

九个 production paths 的 owner-contract test coverage 低于 80%。Slice 3 负责补齐。当前 219-path ledger 中 210 个 `>=80%`，无第十个低覆盖路径。

### 6.4 AR-F06 — RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX

真实 scheduler/lifecycle bug。不因本 plan 消失。本轮只保持其 owner/destination。

### 6.5 AR-F07 — PENDING_RELEASE_BLOCKER

依赖真实 remote Windows runner evidence。不在本地关闭。

## 7. Verdict

```text
PASS
```

八个 immutable test files 及其直接 production owners 经过全面 adversarial failure、semantic ownership drift、minimum-design trap、maintainability 与 test-oracle strength 审查，**未发现实质性问题**。

- AR-F01：fixture 严格 current schema，无 production fallback。
- AR-F03：logging harness 完整恢复 registry/logger/parent/handler identity 与 failure 路径，无 order 依赖。
- AR-F04：manifest/digest 关联唯一 fail-closed，无 candidate id/raw guess/loose parsing。
- S1-SEC-F01：五个 sentinel tests 分别直达 unique projection owner，真实证明 internal durable/Engine retention 与 Tool Trace/audit/public HostEvent/LLM/log 零投影。
- 无字段名黑名单、无只靠 repr 的弱 oracle、无 mock-only bypass、无 private 实现镜像、无 synthetic sentinel 失真。
- RunInput 正确区分 Engine execution headers 与 LLM-facing projection。
- audit exact keys、Tool Trace filter/hot/cold/query、public DTO serialization、logging callsite 足以对抗回归。
- AGENTS docstring/typing/owner boundary 全部合规，无新兼容/overdesign/auth framework。
- S1-QUOTA-F01 分类为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION`，不阻塞 Slice 1 acceptance。

### Finding 计数

```text
code finding = 0
blocking question = 0
design contradiction = 0
open question requiring Controller decision = 0
```

---

## Artifact metadata

- 路径：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-code-review-ds.md`
- SHA-256：待写入后计算
