# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 1 Code Deepreview — AgentMiMo

## 1. Gate identity

- 时间：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 1 concurrent code deepreview。
- Reviewer：AgentMiMo。
- Review target：八个 immutable test files，ordered manifest SHA-256 `bcfc4088dfb2239236579159b71f6abc8e51a32201de240603f3a2eebd954c41`。
- Implementation artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md`，SHA-256 `2c1274e17bc37a0837782fc6cb657fa1cb566ad57c340754023796a5d8703cfe`。
- 本文档是只读 code review artifact，不修改任何 code / test / design / plan / control / 既有 artifact。

## 2. Entry verification

### 2.1 SHA-256 manifest match

八个 test files 的 fresh SHA-256 全部精确匹配 ordered manifest：

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

### 2.2 Read-only validation

- Focused tests：`259 passed, 1 skipped, 3 warnings`；唯一 skip 是 real-compactor opt-in gate，属既有分类。
- Pyright（八个 files）：`0 errors, 0 warnings, 0 informations`。
- Ruff（八个 files）：`All checks passed!`。

## 3. Review dimensions

### 3.1 AR-F01 fixture schema — `tests/service/test_host_admin.py`

**审查内容**：`_write_host_runtime` 是否只跟 current schema，无 production fallback。

**直接证据**：
- 新增 `wait_poller_policy` 块包含 12 个必填字段（`enabled`、`poll_interval_seconds`、`claim_ttl_seconds`、`claim_batch_size`、`backoff_initial_delay_seconds`、`backoff_multiplier`、`backoff_max_delay_seconds`、`not_ready_observe_interval_seconds`、`idle_poll_interval_seconds`、`adapter_call_timeout_seconds`、`close_drain_timeout_seconds`、`max_outstanding_adapter_calls`），全部使用显式值。
- 新增断言 `result.options.sqlite_write_retry_initial_delay_seconds == 0.001` 等四个字段，证明 current profile 成功加载且 projection 未漂移。
- 无 `getattr`、`hasattr`、`dict.get` fallback 或默认值填充。

**结论**：`PASS`。Fixture 严格对齐 ConfigLoader current required schema，无 production 补偿。

### 3.2 AR-F03 logger harness — `tests/tools/web/test_smoke_web_ci.py`

**审查内容**：harness 是否完整恢复 registry / logger / parent / handler identity 与 failure 路径，无 order 依赖。

**直接证据**：
- `_LoggerState` 快照精确包含 `logger`、`level`、`handlers`、`filters`、`propagate`、`disabled`、`parent` 七个字段。
- `_LoggingSnapshot` 快照 `registry`（实例 identity）、`registry_entries`（identity + 插入顺序）、`root_state`、`logger_states`。
- `_restore_logging_state` 恢复顺序：先移除新增 handlers → 恢复 root/logger state → 恢复 registry → 回填 parent identity → 关闭新增 handlers。父节点回填在 registry 恢复之后，避免 stdlib 在 PlaceHolder 位置创建 concrete parent 时重挂 child 导致拓扑不一致。
- `_invoke_smoke_main` 在 `finally` 中恢复，覆盖 success、return error、`SystemExit`、被测异常。
- `test_in_process_smoke_harness_restores_complete_logging_state` 的 success/failure contract 预存 descendant、保留 PlaceHolder、由 fake 创建 concrete parent 触发 reparent，断言 `reparented_descendant=True`、parent identity 精确恢复、pre-existing handlers 不关闭、新增 handlers 全关闭。
- `_LogRecordFilter` 使用 positional-only `record` 参数，满足 stdlib structural Protocol。
- 删除了 entry `E402` 的 `sys.path` 导入 seam。

**结论**：`PASS`。Harness 覆盖 identity/order/parent/handler close scope，无 order 依赖、无 production 特例、无硬编码 module name。

### 3.3 AR-F04 manifest/digest association — `tests/host/test_public_compact_smoke.py`

**审查内容**：manifest / digest 关联是否唯一 fail-closed，无 candidate id / raw guess / loose parsing。

**直接证据**：
- 删除 `_CANDIDATE_ID_FIELD` 与 `llm-compact:{run_id}` 拼接。
- `_runner_call_manifest_for_run` 以 current schema version、`host_run_id`、`runner_call_kind=compactor_proposal` 唯一定位 manifest；缺失或重复 `AssertionError`。
- 从 manifest 的 `compactor_identity.compaction_request_digest` 读取 SHA-256 digest；断言 `parent_host_run_id == host_run_id`。
- `_compact_artifact_for_run` 以 `artifact_kind=context_compaction`、current schema version、相同 request digest 唯一定位 compact artifact；缺失、重复、schema/type 不符均 `AssertionError`。
- 使用 `is_sha256_digest` 校验 digest 格式。
- 新增六个 deterministic fail-closed cases：missing/duplicate manifest、missing/invalid digest、parent run mismatch、missing/duplicate compact artifact、wrong/missing compact digest。
- Real compactor smoke 使用同一链路，`current_input_ref` 字段存在性、`str`、非空 continuity assertions 通过。

**结论**：`PASS`。Association 完全依赖 owner-published exact fields，无 fallback、无顺序推断、无 candidate id。

### 3.4 五个 sentinel tests — S1-SEC-F01 owner evidence

**审查内容**：五个 tests 是否分别直达 unique owner，真实证明 internal durable / Engine retention 与 Tool Trace / audit / public HostEvent / LLM / log 零投影。

#### 3.4.1 `test_run_input_builder.py::test_internal_execution_value_round_trips_without_llm_projection`

**Owner**：RunInput / dispatch decision / memory / compact / runner-call projection。

**直接证据**：
- 使用 `effective_execution_config_json` 构造真实 effective config，写入 `USER_INPUT_ACCEPTED` payload。
- 经 `DurableCurrentRunFactProvider` → `_effective_dispatch_decision_from_payload` → `dispatch_decision.policy_snapshot.runner_spec.headers` 证明 durable round-trip 保留 exact sentinel。
- 经 `create_no_tool_run_input_builder(...).build(...)` → `request.runner_spec.headers` 证明 Engine execution input 保留 exact sentinel。
- 逐条断言 `messages` 中不含 sentinel（`_message_content` helper）。
- 经 `ConversationMemoryProjectionConsumer` → `conversation_memory_snapshot_to_json_value` → `canonical_json_dumps` 证明 memory 不含 sentinel。
- 经 `build_pre_dispatch_compact_material_view` → `repr(compact_material)` 证明 compact material 不含 sentinel。
- 经 `RUNNER_CALL_INPUT_ASSEMBLED` event → hot payload / manifest / runner-call projection 证明 runner-call 三面均不含 sentinel。

**结论**：`PASS`。Test 直接调用 dispatch decision owner、RunInput builder、memory consumer、compact material builder、runner-call projection owner，无 mock-only bypass。

#### 3.4.2 `test_tool_trace_projection.py::test_tool_trace_excludes_internal_effective_execution_value`

**Owner**：ToolTraceProjectionConsumer event filter / hot / cold / query。

**直接证据**：
- 使用 `_append_tool_event` 写入 `USER_INPUT_ACCEPTED` 事件，payload 含 sentinel。
- `consumer.event_filter.matches(projection_event_view_from_row(row))` 返回 `False`（已验证 `USER_INPUT_ACCEPTED` 不在 filter 的 event_types 中）。
- `_run_trace_once` 后 `read_tool_trace_hot_row` 返回 `None`。
- `read_tool_trace_by_run` 返回空 `rows`。
- Cold JSONL 文件为空。

**结论**：`PASS`。Filter 直接拒绝 `USER_INPUT_ACCEPTED`，hot/cold/query 三面零投影。

#### 3.4.3 `test_audit_sink.py::test_audit_projection_excludes_internal_effective_execution_value`

**Owner**：`build_audit_json_line` exact key set / serialization。

**直接证据**：
- 使用 `_append_event` 写入 `USER_INPUT_ACCEPTED` 事件，payload 含 sentinel。
- `_run_audit_once` 后断言 exact key set（22 个字段），不包含 `payload`、`effective_execution_config` 或任何内部字段。
- `canonical_json_dumps(cast(JsonValue, line))` 不含 sentinel。

**结论**：`PASS`。Audit line 使用 `payload_ref` / `payload_digest` 引用，不复制 payload 内容。Exact key contract 可对抗回归。

#### 3.4.4 `test_host_activity_event_projection.py::test_public_host_event_excludes_internal_effective_execution_value`

**Owner**：`_host_event_from_row` / `_activity_from_row`。

**直接证据**：
- 使用 `_project_event` 投影 `USER_INPUT_ACCEPTED` 事件，payload 含 sentinel。
- 断言 `event.kind is HostEventKind.PROGRESS`、`event.activity is None`（`USER_INPUT_ACCEPTED` 不在 activity allowlist 中）。
- `canonical_json_dumps(cast(JsonValue, asdict(event)))` 不含 sentinel。

**结论**：`PASS`。Public DTO 不复制 payload 内容，activity 返回 `None`。

#### 3.4.5 `test_logging.py::test_local_proxy_logs_exclude_internal_effective_execution_value`

**Owner**：`DefaultLocalEngineWorker.accept` logger callsite。

**直接证据**：
- 使用 `dataclasses.replace` 注入 `runner_spec.headers={...: sentinel}`。
- 断言 sentinel 在 `request.runner_spec.headers.values()` 中（证明注入成功）。
- `caplog.at_level(VERBOSE_LOG_LEVEL, logger="dayu.host.local_proxy")` 捕获日志。
- 断言 `"host.local_proxy.accept" in caplog.text`（证明日志确实产生）。
- 断言 sentinel `not in caplog.text`。

**结论**：`PASS`。Logger callsite 记录 ids / counts / refs，不记录 runner_spec headers。

### 3.5 Adversarial failure analysis

**字段名黑名单**：未使用。五个 sentinel tests 通过 payload round-trip 和 owner projection 验证，不依赖字段名匹配。

**仅对 repr 的弱 oracle**：`test_run_input_builder` 中 `repr(compact_material)` 是辅助断言，主断言是 `compact_material.current_input_text == "分析本期经营情况"` 和 `_CONFIGURED_SECRET_SENTINEL not in repr(compact_material)`。`repr` 作为补充扫描是合理的，不是唯一 oracle。

**Mock-only bypass**：无。`test_run_input_builder` 使用真实 `open_host_durable_store`、`DurableCurrentRunFactProvider`、`_effective_dispatch_decision_from_payload`、`create_no_tool_run_input_builder`。`test_tool_trace_projection` 使用真实 `ToolTraceProjectionConsumer`。`test_audit_sink` 使用真实 `build_audit_json_line`。`test_logging` 使用真实 `DefaultLocalEngineWorker`。

**Private implementation mirroring**：无。所有 imports 来自 public 或 internal-but-stable paths：`dayu.host._execution_config_projection`、`dayu.host.dispatch`、`dayu.host.compact_payload`、`dayu.host.durable.codec`。

**Synthetic sentinel 失真**：sentinel `synthetic-local-trust-sentinel-6f2b9d8c` 是显式合成值，不与任何真实 configured secret 相关。五个 tests 共用同一 sentinel，通过不同 owner boundary 验证，不构成失真。

**漏掉 plan 要求 surface**：plan §2.2.1 列出六个 surfaces（Tool Trace、audit、public HostEvent、LLM-facing、operator logs、Engine execution input）。五个 tests 覆盖全部六个（RunInput test 同时覆盖 messages、memory、compact、runner-call projection 和 Engine execution input retention）。

### 3.6 RunInput Engine execution headers vs LLM-facing projection

**审查内容**：是否正确区分 Engine execution headers 与 LLM-facing projection。

**直接证据**：
- `request.runner_spec.headers == {header_name: sentinel}` 断言 Engine execution input 保留。
- `for message in request.messages: assert sentinel not in _message_content(message)` 断言 LLM-facing messages 不含。
- Memory JSON、compact material、runner-call projection 均独立断言不含 sentinel。

**结论**：`PASS`。Test 正确区分了 Engine 执行参数（保留）与 LLM-facing 投影（排除）。

### 3.7 Audit exact keys / Tool Trace filter / public DTO / logging callsite

**Audit exact keys**：22 个字段的 exact set assertion 可对抗字段漂移。新增字段会立即失败。

**Tool Trace filter**：`USER_INPUT_ACCEPTED` 不在 filter event_types 中，filter 直接拒绝。新增 event type 到 filter 需要显式修改。

**Public DTO serialization**：`asdict(event)` + `canonical_json_dumps` + sentinel not-in 断言覆盖完整 DTO。

**Logging callsite**：`host.local_proxy.accept` 记录 session_id / run_id / attempt_id / execution_id / dispatch_record_id / local_worker_id / message_count / disable_tools，不记录 headers。

**结论**：上述四处均可对抗回归。新增 projection surface 或修改 callsite 参数会立即触发对应 test failure。

### 3.8 AGENTS docstring / typing / owner boundary

**Docstring**：所有新增函数和 test 均有完整中文 docstring，包含参数、返回值、异常。

**Typing**：`_LoggerState` 使用 `frozen=True, slots=True` dataclass；`_LoggerFilter` 使用 public `Protocol` + `Callable` + `logging.Filter` union；`_LogRecordFilter.filter` 使用 positional-only 参数。Pyright 0 errors。

**Owner boundary**：Tests 直接调用唯一 projection owner，不通过下游 adapter 或 mock。Production 零 diff。

**结论**：`PASS`。符合 AGENTS.md 编码硬约束。

### 3.9 Implementation artifact 可信度

**直接证据**：
- Implementation artifact 记录了六次 stop 的完整历史、每次 Controller adjudication、fresh validation ledger。
- 29 个 protected paths 在 entry/exit 均用 SHA-256 复核。
- Configured-value semantic classification 按 logical owner 分类：`ACCEPTED_TRUSTED_INTERNAL` 仅在 Host internal physical path 命中，所有 `ZERO_REQUIRED` surfaces 为零。
- 三个 real smokes 全部 PASS。

**结论**：`PASS`。Artifact 记录完整、可追溯、无掩盖。

### 3.10 Quota environment evidence

`S1-QUOTA-F01` 是外部 Gemini test-account provider daily quota exhaustion 导致 final exact-coverage validation 多一个 typed `RESOURCE_EXHAUSTED` skip。直接环境证据：public real runner matrix 3 provider nodes PASS + 1 Gemini typed quota skip。这不是代码 defect，不构成 code review finding，不要求 fix / retry / config / budget 改变。用户裁决为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## 4. Finding ledger

```text
accepted code finding = 0
rejected reviewer candidate = 0
open code finding = 0
blocking question = 0
open external blocker = 0
```

## 5. Open Questions / Residual Risks

| ID | 分类 | 描述 | Owner / Destination |
| --- | --- | --- | --- |
| S1-QUOTA-F01 | Expected test-account quota / non-blocking | 真实 provider 3 pass + Gemini typed quota skip；环境证据不阻塞 Slice 1 acceptance，不要求 fix / retry / config / budget 改变 | 用户裁决：non-blocking |
| AR-F02 | OPEN_BY_SEQUENCE | Service import boundary 单节点失败，属 Slice 2 scope | Slice 2 implementation |
| AR-F05 | OPEN_BY_SEQUENCE | 九个 production paths coverage <80%，属 Slice 3 scope | Slice 3 implementation |
| AR-F06 | Retained / unfixed / unwaived | Scheduler close/promotion node coverage exclusion | 未来 Host scheduler/lifecycle WU |
| AR-F07 | Pending release blocker | Windows runner 无真实 Actions evidence | 外部 CI environment |

## 6. Verdict

`PASS / NO MATERIAL CODE FINDING`

S1-QUOTA-F01 已由用户裁决为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，不阻塞 Slice 1 acceptance。其余 code review 结论、测试证据和 finding 计数不变。
