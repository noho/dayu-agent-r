# Batch 1 implementation report - AgentCodex

## 范围

本轮处理 full-repo review fix loop batch 1 中由 AgentCodex 负责的 Host 侧阻断项与复核项。未执行 commit、push 或 PR 操作。

## 已修复项

### A. HostEventKind LOST

- 结论：动机成立。`RUN_LOST` 是 public host event 的终态语义，不应被投影为 `PROGRESS`。
- 修改：
  - 在 `HostEventKind` 与 `HostTerminalStatus` 增加 `LOST`。
  - `read_api._host_event_from_row` 对 `RUN_LOST` 生成 lost terminal host event。
  - failed / cancelled / lost 终态均禁止携带 final answer。
- 证据：
  - `RUN_LOST` 是 durable event type。
  - public read API 原映射缺失，只能落入非终态路径。
- 测试：
  - 覆盖 `RUN_LOST` 投影为 lost host event。
  - 覆盖 lost terminal event 拒绝 final answer payload。

### B. execution config projection durable error

- 结论：动机成立。durable execution config JSON 属于持久化数据边界，损坏时应抛 `HostDurableError`，不能暴露裸 `RuntimeError`。
- 修改：
  - `_execution_config_projection.py` 的 required / optional JSON shape 错误统一抛 `HostDurableError`。
  - provider request 未知 kind 与 snapshot 解析异常统一归入 durable error。
- 证据：
  - 解析入口消费 durable JSON，错误来源是持久化状态损坏或 schema 不一致。
- 测试：
  - 覆盖 corrupted JSON。
  - 覆盖未知 provider request kind。

### C. ToolRuntime `_execute_one` finally 兜底

- 结论：动机成立。duplicate governance cleanup 是 best-effort cleanup，不应替换工具执行的原始返回或异常。
- 修改：
  - `record_durable_missing` 包装为 best-effort helper。
  - cleanup 失败时记录 warning，并尽力通过现有 diagnostic emitter 发出诊断。
  - diagnostic emitter 自身失败也不会替换原始控制流。
- 证据：
  - 原 finally 中 cleanup 直接 await，cleanup 异常会覆盖 try 块返回值或原始异常。
- 测试：
  - cleanup 抛错时，工具 timeout 返回仍保持原始 governed timeout。
  - cleanup 抛错时，工具原始异常仍保持为原始异常。

### D. `terminal_run_row` CAS 防御

- 结论：动机成立。terminal mutation 应与其它终态写入一致，防止 terminal refs 已存在时再次写入终态。
- 修改：
  - `terminal_run_row` 的 `UPDATE ... WHERE` 增加 terminal refs unset 条件。
- 证据：
  - 同文件其它 terminal mutation 已使用 terminal refs unset 条件。
  - `terminal_run_row` 原路径只校验 attempt 与 status，缺少 terminal refs 防御。
- 测试：
  - 构造 running 但 terminal refs 已存在的损坏行，证明 mutation 进入 CAS lost，既不覆盖既有 terminal ref，也不推进终态。

### E. 中文/CJK token 估算保守化

- 结论：动机成立。CJK 文本按 chars/3 会系统性低估 context budget 与 compaction prompt 成本。
- 修改：
  - 在 `context_budget.py` 增加共享 typed helper `estimate_budget_text_tokens`。
  - 英文仍按原 chars/3 近似。
  - East Asian Width 为 Wide / Fullwidth 的字符按 1 char/token 估算。
  - `llm_compaction.py` 复用同一 helper，避免 Host 内两套估算逻辑。
- 证据：
  - 原 `context_budget.py` 与 `llm_compaction.py` 各自维护 chars/3 估算，且没有 CJK 分支。
- 测试：
  - 覆盖纯英文保持旧近似。
  - 覆盖纯中文与中英混合文本使用更保守估算。

## 复核项

### F1. DS finding 1 prompt injection

- 裁决：小修复已实施。
- 证据：
  - `llm_compaction._compaction_request_prompt_block` 会把 `request.llm_material_json` 直接放入 compactor prompt。
  - material 内包含来自 evidence/result text 的非信任文本。
- 修改：
  - compaction material JSON 外层增加明确的 untrusted material begin/end delimiter。
  - 不改变 material JSON 字段契约，不重写 compactor prompt contract。
- 测试：
  - 覆盖 prompt 渲染包含 untrusted material delimiter。

### F2. DS finding 3 duplicate governance 永久阻塞

- 裁决：不做额外大改；本轮 C 项已覆盖同 event loop 下 ToolRuntime owner 正常退栈路径。
- 证据：
  - waiter 等待 duplicate governance condition。
  - ToolRuntime owner 的 cleanup 是唤醒/清理路径。
  - 本轮将 cleanup 改为 best-effort，避免 cleanup 失败替换原始工具返回或异常。
- 未实施原因：
  - 进程崩溃不会在同一 event loop 内留下可继续等待的 waiter。
  - 当前 duplicate governance 是内存治理，不是跨进程 durable 锁；把它扩成 durable lease 属于更大 contract 改动。

### F3. MiMo host-core-002 Host import Engine

- 裁决：拒绝实施，判定为误报或不属于本轮低/中风险修复。
- 证据：
  - AGENTS.md 明确层级方向为 `UI -> Service -> Host -> Engine`，Host 依赖 Engine 是允许方向，不是反向依赖。
  - 当前相关路径使用 Engine 公共契约或公共入口，没有发现 Host 依赖 Engine 内部实现细节的直接证据。
- 未实施原因：
  - 大范围重构会改变分层 contract，风险高，且当前 review item 的动机不成立。

## 文档同步

- `dayu/host/README.md`：同步 HostEvent LOST、终态 final answer 约束、compaction untrusted delimiter 与 CJK 估算。
- `tests/README.md`：同步新增测试覆盖范围。

## 验证命令

```bash
source .venv/bin/activate && pytest tests/host/test_context_compact_events.py::test_run_lost_projects_to_lost_host_event tests/host/test_public_host_event.py tests/host/test_effective_execution_config.py::test_effective_execution_snapshot_rejects_corrupted_json_with_durable_error tests/host/test_effective_execution_config.py::test_effective_execution_snapshot_rejects_unknown_provider_request_with_durable_error tests/host/test_context_budget.py::test_text_token_estimator_keeps_english_chars_per_token_semantics tests/host/test_context_budget.py::test_text_token_estimator_counts_cjk_more_conservatively tests/host/test_llm_compaction.py::test_prompt_renders_material_pack_without_ledger_dump tests/host/test_llm_compaction.py::test_llm_compaction_text_estimator_uses_cjk_conservative_budget tests/host/test_run_attempt_transitions.py::test_terminal_run_row_reports_cas_lost_when_terminal_refs_already_set tests/host/test_toolruntime_executor.py::test_duplicate_cleanup_failure_does_not_replace_tool_timeout_return tests/host/test_toolruntime_executor.py::test_duplicate_cleanup_failure_does_not_replace_original_exception
```

结果：`14 passed in 0.32s`

```bash
source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_public_host_event.py tests/host/test_effective_execution_config.py tests/host/test_context_budget.py tests/host/test_llm_compaction.py tests/host/test_run_attempt_transitions.py tests/host/test_toolruntime_executor.py tests/host/test_watch_session_events.py
```

结果：`179 passed in 1.08s`

```bash
source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_public_contracts.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py tests/host/test_public_event_stream.py tests/host/test_outbox_durable.py tests/host/test_outbox_projection.py
```

结果：`88 passed in 1.69s`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

## 剩余风险

- 本轮未把 duplicate governance 扩展为跨进程 durable lease；该方向需要 controller 单独裁决 contract 与持久化语义。
- prompt injection 仅做 untrusted delimiter 小修复，未重写 compactor prompt contract。
- 未运行完整全仓测试，仅运行受影响 Host 测试、公共契约测试与 pyright。
