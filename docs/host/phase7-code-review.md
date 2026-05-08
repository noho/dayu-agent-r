# Host P7 Code Review: Tool Trace Projection / Sink

**结论：通过**

## 验证命令结果

| 命令 | 结果 |
|------|------|
| `pytest tests/host/ tests/utils/ -q` | 231 passed, 0 failed |
| `python -m pyright` | 0 errors, 0 warnings, 0 informations |
| `python utils/smoke_host_p7_tool_trace.py` | 5 类 record 全部落盘，secret scrub 验证通过，analyzer 去重 0 duplicate |
| `git diff --check` | clean |

## 审查范围

未提交改动覆盖 8 个实现文件（3 new + 5 modified）、10 个测试文件（7 new host + 1 new utils + 2 modified）、3 个文档更新、2 个 utility 脚本（new）。

## 逐项审查

### 1. 实现是否符合已通过 P7 plan

全部对齐：

- JSONL 文件系统真源，0 新增 SQLite 表 ✅
- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 在 RunInputBuilder 完成后、Engine attempt 启动前同事务追加 ✅
- `tool_trace_v2_host` schema，严格拒绝 OLD `tool_trace_v2` ✅
- `DurableHarnessConfig.tool_trace_path` 非空装配 observer，None/空不装配 ✅
- sha256[:32] `idempotency_key` 确定性非空 ✅
- `ToolTraceObserver` 实现 `ObserverSink` 协议，`tx` 参数保留但不使用 ✅
- `RunInputContextFactBuilder` 无状态 frozen dataclass，不持有 LRU ✅

### 2. JSONL 文件系统真源与非原子 checkpoint

**判定：可接受实现取舍，plan 与设计文档已正确记录。**

实现路径：`ProjectionCoordinator.drain()` 同步调用 `observer.process()` → `ToolTraceJsonlSink.append_record_line()` 每行 `flush + fsync` → coordinator checkpoint 推进。

crash 窗口分析：
- JSONL 已写、checkpoint 未推 → replay 重写同一行，`idempotency_key` 去重 ✅
- JSONL 未写、checkpoint 已推 → trace 丢失，与 EventLog 不一致但不影响 EventLog 正确性；属于可接受的 trace best-effort 语义
- raw payload blob 使用 `tmp + os.replace` 原子覆盖 ✅

`_emit_iteration_context_snapshot` 先写 2 个 blob 文件、再写 1 行 JSONL。若 crash 在 blob 写完但 JSONL 未写之间，replay 后 `os.replace` 原子覆盖同一文件名，`idempotency_key` 让 analyzer 去重。设计合理。

### 3. `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact sizing

`_run_input_context_fact.py:113-119` 把完整 `raw_input_messages_json` 和 `raw_tool_schemas_json` 内联在 fact data 中。`test_phase7_schema_bootstrap.py` 用 256KB input + 128KB tools 验证 round-trip 通过。SQLite TEXT 列无硬限制，该策略正确。

`_append_run_input_context_snapshot_fact`（`_run_harness.py:1314-1389`）使用 `self.storage.transaction()` 开启短事务，fact append 与 EventLog 在同一事务中提交。符合 plan review 要求的"同事务提交"不变量。

### 4. Engine 边界

`test_phase7_tool_trace_eventlog_source.py:285-306` 用 `pkgutil.walk_packages` 扫描 `dayu.engine` 包，断言不 import `dayu.host._tool_trace_projection` / `dayu.host._tool_trace_jsonl_sink` / `dayu.host._run_input_context_fact`。Engine 只产出 `EngineEvent`，trace 由 Host observer 从 EventLog 派生。

### 5. ToolRuntime 边界

`ToolRuntime` 不直接写 trace。`_tool_trace_projection.py:626-640` 的 `_iteration_id_for_tool_runtime` 对 ToolRuntime 事件（`TOOL_RESULT_TRUNCATED` / `TOOL_FETCH_MORE_COMPLETED` / `TOOL_CURSOR_DENIED` / `TOOL_CURSOR_EXPIRED`）返回空字符串作为 group key 的 iteration_id 维度。这与 OLD trace 行为一致（OLD 也按 `tool_call_id` 维度聚合），当前单 batch 约束下无问题。

### 6. payload retention 策略

- `PROVIDER_PROTOCOL_ERROR.raw_payload` → `_scrub_provider_secret` 递归替换 `authorization` / `api_key` / `cookie` / `x-api-key` 等 9 个敏感键为 `"***"` ✅
- scope_token / cursor / prompt / tool result → 按 OLD 热/冷分层保留不过滤 ✅
- 缺失 payload → fallback `{"reason": "omitted_no_payload"}` ✅

### 7. OLD analyzer 迁移

`utils/analyze_tool_trace_host.py` 实现了 OLD `analyze_tool_trace.py` 的全部业务无关诊断：

- 重复 tool_call（`(run_id, tool_name, arguments_json)` 计数）✅
- truncation 后未续读 fetch_more ✅
- fetch_more 引用未知 cursor ✅
- `provider_protocol_error` 计数 ✅
- `final_response` 是否存在 ✅
- 同 run 内 `source_event_position` 单调性 ✅
- 严格拒绝 OLD schema ✅（`_validate_schema_version` 抛 `ValueError`）

未迁移的 OLD 项（plan 已明确 deferred）：context pressure 估算、fetch_more 质量分析、large payload / large prompt 检测。这些需要更多 OLD 迭代状态，属于 P8+ 范畴。

### 8. 双重计数风险

`ToolTraceRecordType` 使用 `provider_protocol_error`（非 OLD `sse_protocol_error`）。`ProviderProtocolErrorRecord` 只写一条 canonical record。analyzer 只计 `provider_protocol_error` 类型。OLD exporter 路径由 analyzer adapter 负责映射，当前 P7 无 exporter，不产生双重计数。

### 9. 测试覆盖

| 测试文件 | 覆盖点 |
|---------|--------|
| `test_phase7_contract_serializer.py` | `_DATA_CLASS_BY_TYPE` 注册、round-trip、缺失字段拒绝、optional cursor None |
| `test_phase7_schema_bootstrap.py` | 无新 SQLite 表、大 payload round-trip |
| `test_phase7_contract_serializer.py` | 序列化/反序列化封闭联合 |
| `test_phase7_run_input_context_fact.py` | builder 输出一致性、blob_id 跨调用稳定、非 user 事件拒绝、无状态 |
| `test_phase7_durable_harness_config.py` | tool_trace_path=None/空/非空装配开关、frozen |
| `test_phase7_tool_trace_jsonl_sink.py` | append_record_line、文件滚动、raw payload 原子写、secret scrub、idempotency_key 确定性 |
| `test_phase7_tool_trace_projection.py` | 5 类 record 派发、未配对抛 ProjectionSchemaError、secret scrub、context snapshot blob + JSONL、跨 drain idempotency 稳定 |
| `test_phase7_tool_trace_eventlog_source.py` | 端到端 EventLog → drain → JSONL + blob、未启用不写 fact、Engine 不 import Host trace |
| `test_analyze_tool_trace_host.py` | analyzer 去重、拒绝 OLD schema、重复 tool_call、truncation gap、unknown cursor、position gap、provider error 计数 |

### 10. Findings

#### [Info] `_resolve_source_kind` 冗余条件 `[无需修复-说明]`

`_run_input_context_fact.py:243-248`：`not seen_first_system and index == 0` 与 `not seen_first_system`（不含 index 条件）两个分支返回相同值。第二个分支已覆盖第一个。功能正确但代码冗余。

**不阻断。**

#### [Info] `_select_jsonl_file` 文件编号可能跳号 `[无需修复-说明]`

`_tool_trace_jsonl_sink.py:229`：`next_index = len(existing) + 1`。若中间分片被人工删除，新文件编号会跳号。不影响功能（`glob` 只找已存在文件）。

**不阻断。**

#### [Info] `_ToolCallGroup` 同 key 重复事件静默覆盖 `[无需修复-说明]`

`_tool_trace_projection.py:219-230`：若同 batch 内出现两条相同类型的 tool 维度事件（例如两条 `TOOL_CALL_REQUESTED`），后者覆盖前者。当前 EventLog 保证同一 `(iteration_id, tool_call_id)` 只有一种事件类型，但 observer 未做防御性检查。

**不阻断。** 若 EventLog 不变量被打破，`ProjectionSchemaError` 会在配对阶段被捕获。

## 通过项

- EventLog 是 trace 唯一真源；Engine 不恢复 recorder/store，ToolRuntime 不直接写 trace
- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` raw payload 与 EventLog fact 同事务提交
- JSONL + checkpoint 非原子窗口通过 idempotency_key 去重、raw payload 原子覆盖约束
- 5 类 trace record 全部有对应派发路径与测试
- `tool_trace_v2_host` 与 OLD `tool_trace_v2` 严格隔离
- provider secret scrub 仅作用于 `PROVIDER_PROTOCOL_ERROR.raw_payload`
- analyzer 覆盖 OLD 全部业务无关诊断语义
- Engine / Host 架构边界由 import boundary 测试守护
- 231 测试全部通过，pyright 0 错误，smoke 验证通过
