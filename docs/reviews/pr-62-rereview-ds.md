# PR 62 Re-review — AgentDS

## Scope

- Task: Gateflow-governed re-review of PR-62 fix round
- Base review artifacts:
  - `docs/reviews/pr-62-deepreview-mimo.md`（结论 FAIL，9 findings）
  - `docs/reviews/pr-62-deepreview-ds.md`（结论 PASS，7 findings）
- Fix report: `docs/reviews/pr-62-review-fix-codex.md`（9 accepted findings）
- Verify method: 按 accepted findings 逐条检查 git diff，沿真实代码路径走读，确认 root cause 被修复、无新 blocker
- Excluded scope: 不在 accepted findings 列表中的 DS F6/F7 和 MiMo #6/#7/#8/#9/#10（non-blocking/rejected/deferred，非本轮 fix scope）
- Output: `docs/reviews/pr-62-rereview-ds.md`

## Findings

### F1-已修复-HostHandle 兼容别名删除

- **入口/函数**: `dayu/host/api.py:2798`（原）、`dayu/host/__init__.py`
- **文件(行号)**: `api.py:2798`（原 `HostHandle: TypeAlias = Host` 行已消失）、`__init__.py`（含 `__all__`）
- **直接证据**:
  - `api.py` diff 已删除 `HostHandle: TypeAlias = Host`
  - `api.py.__all__`（line 2798-2865）不再包含 `HostHandle`
  - `__init__.py`（line 40-46）不再 `from dayu.host.api import ... HostHandle`
  - `__init__.py.__all__`（line 101-187）不再包含 `HostHandle`
  - `test_package_exports.py:154-169` — `HostHandle` 在 `REMOVED_SERVICE_FACING_ALL_EXPORTS` 中，`test_removed_low_level_symbols_are_not_service_facing_all_exports` 和 `test_removed_low_level_symbols_are_not_package_root_attributes` 均通过
- **结论**: 兼容别名已完全删除，包根与 `api.__all__` 不再导出。**已修复**。

### F2-已修复-api.\_\_all\_\_ 不再导出 6 个内部类型

- **入口/函数**: `dayu/host/api.py:2798-2865` — `__all__`
- **文件(行号)**: `api.py:2798-2865`
- **直接证据**:
  - `api.py.__all__` 不再包含 `HostCommandFacet`、`HostCommandHandleOptions`、`HostEventStream`、`HostEventView`、`HostLocalExecutionOptions`、`StartRunRequest`
  - `test_package_exports.py:190-193` — `test_api_all_stays_request_snapshot_boundary` 断言 `api.__all__ == EXPECTED_API_EXPORTS`，该 set 不含上述 6 名
  - `test_package_exports.py:110-119` — 6 个名字在 `ROOT_INTERNAL_API_NAMES` 中，仅用于从包根 expected exports 中扣除
- **结论**: contract freeze 完整，6 个内部类型不再通过 `api.__all__` 公开。**已修复**。

### F3-已修复-HostInput 不再作为 Service-facing public export

- **入口/函数**: `dayu/host/api.py:1342`（类定义）、`dayu/host/__init__.py`
- **文件(行号)**: `api.py:1342`、`__init__.py`
- **直接证据**:
  - `api.py:1342` — `class HostInput:` 定义仍保留（供 `StartRunRequest` 和内部 admission 使用）
  - `api.py.__all__` — 不再包含 `HostInput`
  - `__init__.py` — 不再 `from dayu.host.api import ... HostInput`，`__all__` 不含 `HostInput`
  - `test_package_exports.py:116` — `HostInput` 在 `ROOT_INTERNAL_API_NAMES` 中
  - `test_package_exports.py:154-169` — `HostInput` 在 `REMOVED_SERVICE_FACING_ALL_EXPORTS` 中，已验证不在 `host.__all__`
- **判断**: 类定义保留在 `api.py` 内部是合理的——`StartRunRequest`（也是内部类型）和 `admission.py` 内部路径仍需要它作为 typed envelope。不把"定义保留"误判为 public export 残留。
- **结论**: **已修复**。

### F4-已修复-read_api.\_\_all\_\_ 不再导出 stream_run_events

- **入口/函数**: `dayu/host/read_api.py:722`
- **文件(行号)**: `read_api.py:722`
- **直接证据**:
  - `read_api.py:722` — `__all__ = ["get_run", "get_session"]`
  - `test_package_exports.py:196-199` — `test_read_api_all_keeps_service_facing_read_boundary` 断言 `read_api.__all__ == frozenset({"get_run", "get_session"})`
  - `test_package_exports.py:150` — `stream_run_events` 在 `FORBIDDEN_HOST_ROOT_EXPORTS` 中，`test_host_root_does_not_export_internal_services` 验证包根不导出
- **结论**: **已修复**。

### F5-已修复-fake_compaction budget_after_compact 与真实 LLM compactor 对齐

- **入口/函数**: `FakeContextCompactor.compact()` → `_budget_after_compact()`
- **文件(行号)**: `dayu/host/fake_compaction.py:193-204`
- **直接证据**:
  - `fake_compaction.py:193-204` — 新增 `_budget_after_compact()`:
    ```python
    half_estimate = request.budget_before_compact.estimated_input_tokens // 2
    hard_threshold_limit = request.budget_before_compact.hard_threshold_tokens - 1
    return max(0, min(half_estimate, hard_threshold_limit))
    ```
  - `llm_compaction.py:450-451`（来自 DS F1 证据）— `return min(half_estimate, estimate.hard_threshold_tokens - 1)` — **同源 clamp 语义**
  - `test_compaction_contract.py:45-61` — `test_fake_compactor_clamps_budget_below_hard_threshold`：设 `estimated_input_tokens=2000, hard_threshold_tokens=950`，断言 `budget_after_compact == 949`（即 `950 - 1`，验证 clamp 生效）。测试覆盖了 `half_estimate > hard_threshold_tokens - 1` 场景。
- **结论**: clamp 与真实 LLM compactor 同源，测试覆盖 clamp 上限场景。**已修复**。

### F6-已修复-engine_ingest reactive compaction stale guard

- **入口/函数**: `EngineEventIngestor._execute_reactive_compaction()` → `_operation()`
- **文件(行号)**: `dayu/host/engine_ingest.py:338-345, 1153-1156, 1420-1444`
- **直接证据**:
  - `engine_ingest.py:338-345` — `_ReactiveCompactPending` 新增 `expected_input_event_sequence: int`
  - `engine_ingest.py:1153-1156` — 创建 pending 时保存 `expected_input_event_sequence=context.run.input_event_sequence`
  - `engine_ingest.py:1423-1444` — 写事务内先调用 `_validate_durable_context` 重读最新状态，再检查 `sequence_stale = latest.run.input_event_sequence != pending.expected_input_event_sequence`；`RECOVERING and sequence_stale` 时写 `CONTEXT_COMPACTION_FAILED(failure_reason=stale_compaction_result)`，不写 `CONTEXT_COMPACTED`，不启动 recovery Attempt
  - `test_engine_ingest_mapping.py:190-213` — `_InputSequenceAdvancingCompactor`：在 `compact()` 期间调用 `_advance_run_input_sequence()` 推进 Run 的 `input_event_sequence`，模拟 compaction LLM 调用期间 Engine 推送新事件
  - `test_engine_ingest_mapping.py:481-511` — `test_reactive_compaction_rejects_stale_input_sequence`：断言 `CONTEXT_COMPACTED == 0`、`CONTEXT_COMPACTION_FAILED == 1`、Run 仍为 `RECOVERING`、Attempt 为 `FAILED`、failure_reason 为 `stale_compaction_result`
- **结论**: stale guard 完整——保存预期序列号、事务内重查、stale 时写 FAILED 不写 COMPACTED、不启动 recovery。测试覆盖模拟竞态。**已修复**。

### F7-已修复-大 USER_INPUT_ACCEPTED payload descriptor

- **入口/函数**: `admission._append_user_input_event()` → `_write_user_input_payload_if_needed()` → `payload_resolution.event_payload_object()`
- **文件(行号)**: `admission.py:2900-2950, 2961-3011`；`payload_resolution.py:17-55`
- **直接证据**:

  1. **admission 写入侧**（`admission.py:2900-2950`）:
     - `_append_user_input_event()` 先构造完整 `_user_input_payload()`（包含 display_text, system_prompt, user_prompt 等全部字段）
     - 调用 `_write_user_input_payload_if_needed()`：`canonical_json_dumps(payload)` 后检查 `len(encoded.encode("utf-8")) <= transaction.payload_inline_threshold_bytes`
     - 超限时通过 `PayloadStore().write_sqlite_payload()` 在同一 transaction 内写 SQLite payload row + descriptor row
     - EventLog inline 用轻量 `_referenced_user_input_event_payload()`（仅含 input_ref, input_digest, payload_ref, payload_digest, operation_kind, call_context_digest），EventLog append 时设置 `payload_ref` 和 `payload_digest`

  2. **dispatch / engine_ingest / RunInputBuilder 读取侧**:
     - `dispatch.py:2634-2650` — `_display_text_from_input_event()` 改用 `event_payload_object(transaction, event, ...)`
     - `engine_ingest.py:2907-2922` — 同上
     - `run_input.py:521-527` — `DurableCurrentRunFactProvider._resolve()` 改用 `event_payload_object(transaction, user_input_event, ...)`
     - 旧 `_payload_json_from_event()` 已被替换——旧的 `json.loads(event.payload_json)` 路径被移除

  3. **payload_resolution 解析逻辑**（`payload_resolution.py:17-55`）:
     - `event.payload_ref is None` → 读 inline `payload_json`
     - `event.payload_ref is not None` → 读 descriptor → 校验 `payload_kind is SQLITE_PAYLOAD` → 校验 `descriptor.payload_digest == event.payload_digest` → 从 `TABLE_SQLITE_PAYLOADS` 读 `payload_json` → 反序列化
     - 缺失 descriptor / digest mismatch / 非 SQLite payload / SQLite row 缺失 → 全部 `raise HostDurableError`

  4. **与 docs/host/design.md §13.1 一致性检查**:
     - "EventLog row 不应内嵌大 payload；canonical event 必须记录 payload ref / descriptor 与 digest" ✅
     - "第一版使用 SQLite payload table 作为默认 durable payload store" ✅
     - "小型 / 中型可恢复 payload 与引用它的 EventLog append 在同一 SQLite transaction 内提交" ✅（admission 在同一 write transaction 内写 payload + descriptor + EventLog）
     - "payloade_digest ... 必须基于确定性序列化" ✅（使用 `canonical_json_dumps` + `sha256_digest_bytes`）
     - "会参与 resume、memory、audit ... 的 payload / ref / descriptor 缺失或 digest 不匹配时，Host 不能把该 fact 当作 accepted fact 使用" ✅（`event_payload_object` 在 digest mismatch / descriptor missing / SQLite row missing 时全部 `raise HostDurableError`）

  5. **digest/transaction/read path 检查**:
     - 写入：payload + descriptor + EventLog 在同一 write transaction → 原子提交，不会出现 descriptor 已提交但 payload row 未提交（或反之）
     - 读取：dispatch/ingest/RunInputBuilder 的 read transaction 与写入 transaction 是不同事务，但因为写入已提交，SQLite 保证可见性。descriptor 先读、digest 校验后再读 payload row，两读之间无中间状态风险
     - 无 digest 绕过路径：`event_payload_object` 只有 `payload_ref is None` 时才读 inline JSON；有 `payload_ref` 时必须通过 descriptor → digest check → SQLite payload read 全链路

  6. **测试覆盖**（`test_admission_queue.py:380-416`）:
     - `test_followup_queue_spills_large_user_input_payload`：设置 `payload_inline_threshold_bytes=4096`，构造 `"long prompt " * 600`（远超阈值），验证 `input_event.payload_ref is not None`、`input_event.payload_digest is not None`、inline `payload_json` 不含 `"long prompt"`、通过 `event_payload_object` 读取完整 payload 后 `display_text` 和 `user_prompt` 均为原始长文本

- **结论**: SQLite payload descriptor 方案与 `docs/host/design.md` §13.1 的 Payload 存储语义一致；digest 校验、transaction 原子性、read path 均无漏洞。**已修复**。

### F8-已修复-手工 smoke blocker 从 root cause 修复

- **入口/函数**: `utils/smoke_host_public_multiturn.py`（未修改）
- **文件(行号)**: 无 smoke 脚本修改
- **直接证据**:
  - codex fix report 记录：root cause 是 "round2 admission 失败来自大 `USER_INPUT_ACCEPTED` canonical payload 超过 inline threshold"，不是 DeepSeek/network 问题
  - 修复方法：admission 对大 payload 写入 SQLite payload descriptor，EventLog inline 用轻量 payload；dispatch / engine_ingest / RunInputBuilder 通过 `event_payload_object` 跟随 descriptor 读取真源内容
  - 修复后 smoke 输出：`SMOKE PASS public Host handle completed three-turn closure`
  - 没有修改阈值（`payload_inline_threshold_bytes=4096` 未变）、没有缩 prompt（smoke 脚本未改）
- **结论**: root cause（inline 阈值拒绝大 payload）被直接修复，不是通过调阈值或缩 prompt 绕过。**已修复**。

### F9-已修复-README 同步只写当前实现边界

- **入口/函数**: `dayu/README.md`、`dayu/host/README.md`、`dayu/host/__init__.py`、`tests/README.md`
- **文件(行号)**: 各文件全文
- **直接证据**:
  - `dayu/README.md`：完全重写，聚焦当前架构、稳定边界、设计意图、扩展入口、代码阅读顺序。无 Phase 引用、无过程状态、无未来计划。
  - `dayu/host/README.md`：大量同步更新。"当前未实现"段列出未实现能力，使用 Phase 标签（如 "Phase 3/5"、"Phase 10"）作为实现范围稳定标识符，与 `docs/host/design.md` 的 phase labeling 约定一致，不构成过程状态。全文以"当前"为主语，无"未来设计"、"近期更新"、"版本记录"等表述。
  - `dayu/host/__init__.py:1-6` — docstring 已从 "Phase 4 已实现的 Session / Run public facade" 改为 "Session / Run public facade"
  - `tests/README.md`：覆盖新增测试层（public-path smoke 覆盖、payload descriptor 测试、compaction contract 测试、engine ingest 测试），使用"当前"语态，无旧术语。
  - 搜索确认：`dayu/README.md` 无 "Phase" 引用；`dayu/host/README.md` 无 "过程状态"、"未来计划" 等词汇。
- **结论**: README 同步仅描述当前已实现边界，无过程状态、未来计划或旧语义残留。**已修复**。

---

## Open Questions

无。

## Residual Risk

1. **`stream_run_events` 函数定义仍保留**在 `dayu/host/read_api`，虽然不在 `__all__` 中，内部 diagnostic / 低层测试仍可通过显式模块路径导入。若未来需要完全删除，需确认所有内部 consumer 已迁移。

2. **`HostInput` 类定义仍保留**在 `dayu/host/api.py`，`StartRunRequest` 仍依赖它。当 `StartRunRequest` 在后续 phase 被废弃时，`HostInput` 的保留合理性需要重新评估。

3. **`dayu/host/payload_resolution.py` 是新增模块**，位于 `dayu.host` 内部。该模块通过 `event_payload_object` 使用 `TABLE_SQLITE_PAYLOADS` 的直接 SQL 查询。当前设计与 `docs/host/design.md` §13.1 一致，但随 payload 类型扩展（`artifact_ref` 类型 descriptor），`event_payload_object` 可能需要扩展以支持非 SQLite payload 的读取路径。

## 结论

**PASS**

所有 9 项 accepted findings 均已从 root cause 修复，未引入新 blocker。关键修复验证：

| # | Finding | Gateflow 状态 |
|---|---------|--------------|
| 1 | HostHandle 兼容别名 | 已修复 |
| 2 | api.__all__ 6 个内部类型 | 已修复 |
| 3 | HostInput 死导出 | 已修复 |
| 4 | read_api.__all__ stream_run_events | 已修复 |
| 5 | fake_compaction budget clamp | 已修复 |
| 6 | reactive compaction stale guard | 已修复 |
| 7 | 大 USER_INPUT_ACCEPTED payload descriptor | 已修复 |
| 8 | 手工 smoke blocker | 已修复 |
| 9 | README 同步 | 已修复 |
