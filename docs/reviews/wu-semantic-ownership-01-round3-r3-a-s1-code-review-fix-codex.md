# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S1 Code Review Fix（AgentCodex）

## 修复结论

状态：`ready-for-rereview`。

总控接受的 `Codex-F1`、`Codex-F2`、`Codex-F3` 已在各自语义 owner 边界修复。此次没有修改 schema DDL / migration，没有进入 S2-S8 lifecycle、admin 或 scheduler 行为，也没有为旧 hot row 或旧 manifest shape 增加兼容分支。

## 第一性原理与 owner 判定

- `Codex-F1` 真实存在且严重性成立：compact material 是 accepted evidence 的严格消费边界，但旧路径先进入 lenient projection；后者会把 shared durable resolver 抛出的 `HostDurableError` 转为 unavailable，从而让 payload 损坏表现为 evidence 缺失。正确 owner 是 compact strict consumer 与 shared durable payload integrity resolver，不是 projection 展示层。
- `Codex-F2` 真实存在：descriptor bytes 完整性只证明“读到的字节可信”，不能证明 manifest graph 语义闭合。schema、identity、message graph、metadata refs/enums 与 hot redundancy 的唯一 owner 应是 `dayu.host._runner_call_manifest`；Tool Trace 只能消费该 owner 的 typed validated result。
- `Codex-F3` 真实存在：producer-only 校验不足以约束 durable consumer。若 Tool Trace 或 Engine ingest 根据 sibling scalar 重建 complete diagnostic，hot payload 的显式 contract 就没有被真正消费。hot payload 解析与交叉校验同样由 `_runner_call_manifest` 唯一拥有。

## Finding 修复

### Codex-F1：fixed

- `dayu/host/compact_material.py` 在调用 lenient `AcceptedToolResultProjection` 前，先通过 shared `event_payload_object(...)` 完整解析 accepted result payload，再把已验证 object 交给 projection。
- descriptor digest/size、SQLite row digest/size/content、非 canonical JSON、artifact containment/bytes 损坏都会由 integrity owner 抛出 `HostDurableError`，compact material 构造 fail closed；lenient projection 的 read/display 行为未被扩大为 strict contract。
- `tests/host/test_compact_material.py` 增加上述 descriptor、row 与 artifact tamper matrix，断言失败发生在 material construction，不在下游生成 unavailable 文本。

### Codex-F2：fixed

- `dayu/host/_runner_call_manifest.py` 新增 typed full-manifest parser/validator，负责校验：
  - manifest schema 与 runner-input serializer version；
  - scope、runner-call identity、kind/trigger closed enum；
  - `message_count`、连续 message indexes 与 role sequence digest；
  - message `projector_metadata_id` 引用闭合、metadata id 唯一；
  - `projector_id`、`purpose` closed enum；
  - projection ref/digest/size 配对；
  - compactor identity 与 parent/index 一致性；
  - manifest canonical digest 以及 hot/manifest identity、count、digest、projection descriptor 一致性。
- `run_input.py`、`engine_ingest.py`、`compaction_operation.py` 在 append 前把完整 manifest 交给同一 owner 校验。Engine continuation 的每条 message entry 现在引用 manifest 中真实存在的 metadata id。
- `dayu/host/durable/tool_trace.py` 先读取并验证源 EventLog hot payload，再通过 shared durable resolver 读取完整 manifest，最终只从 typed manifest 投影 metadata summary；删除 metadata item-only 的成功路径。
- `tests/host/test_tool_trace_queries.py` 的成功用例改用真实 `DurableRunnerCallManifestRecorder` 产物；新增 incomplete manifest、dangling metadata id、unknown projector enum、unknown purpose enum、unknown schema 与 hot/manifest identity mismatch 的 fail-closed matrix。

### Codex-F3：fixed

- `_runner_call_manifest.py` 新增 shared typed hot parser，要求 hot payload 字段集合精确、diagnostic 始终显式且 shape 完整，并把 complete diagnostic 与 `validation_status`、`message_count`、`role_sequence_digest` 交叉校验。
- missing、malformed、`null` diagnostic，旧 `projector_metadata_summary` 数组，status/count/digest mismatch 均 fail closed；不存在旧 row fallback。
- Tool Trace projection/query 与 Engine ingest 均消费 shared parser 的 typed result，不再自行合成 complete diagnostic。
- `docs/host/design.md` 已明确区分 manifest body 与 event hot payload：complete manifest body 的 typed incomplete/mismatch signal 固定为 `null`，但 canonical hot payload 无论状态都必须携带显式 fixed-shape diagnostic；complete hot diagnostic 不得为 `null`。
- owner、Engine ingest 与 Tool Trace 测试覆盖显式 complete 成功，以及 missing/null/malformed/legacy/status/count/digest 反例。

## 改动文件摘要

- shared contract / producer：`dayu/host/_runner_call_manifest.py`、`dayu/host/run_input.py`、`dayu/host/engine_ingest.py`、`dayu/host/compaction_operation.py`。
- strict/read consumers：`dayu/host/compact_material.py`、`dayu/host/tool_trace.py`、`dayu/host/durable/tool_trace.py`。
- owner/integration tests：`tests/host/test_runner_call_hot_payload_contract.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_tool_trace_projection.py`、`tests/host/test_tool_trace_queries.py`、`tests/host/test_compact_material.py`。
- contract docs：`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`。

工作区中其余 S1 implementation baseline 文件与既有 review artifacts 保持未提交状态；本 fix 没有覆盖或清理用户/前序 Agent 改动。

## README decision

- 更新 `dayu/host/README.md`：本次改变 Host stable internal contract，补充 runner-call typed full-graph owner、显式 hot diagnostic 与 strict compact resolution 规则，命中其模块职责。
- 更新 `tests/README.md`：补充 owner matrix、真实 producer manifest、Tool Trace fail-closed graph 以及 compact durable tamper coverage，命中测试分层职责。
- 不更新根 `README.md` 与 `dayu/README.md`：没有用户可见入口/工作流变化，也没有改变 `UI -> Service -> Host -> Engine` 分层或装配关系。

## 验证结果

- focused S1 matrix：
  - 命令：`source .venv/bin/activate && pytest tests/host/test_payload_store.py tests/host/test_effective_execution_config.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_compact_material.py tests/host/test_terminal_payload.py tests/host/test_outbox_projection.py tests/host/test_runner_call_hot_payload_contract.py tests/host/test_durable_payload_integrity.py -q`
  - 通过：`435 passed in 2.97s`。
- stress suite：
  - 命令：`source .venv/bin/activate && pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q`
  - 最终通过：`5 passed in 6.95s`。
  - 收口复验前同一命令曾出现一次 `test_scheduler_liveness_long_run_mixed_flow_stress` 的 `active_cleanup` 失败；直接读取唯一 predicate 后确认该边界只剩 `total_cancel_count < 1`，失败日志同时显示 scheduler close 竞态。该单例随后 `1 passed in 1.36s`，完整命令复跑通过。本 fix 未修改 S4 scheduler/worker cancellation 行为。
- type check：
  - 命令：`source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - 通过：`0 errors, 0 warnings, 0 informations`。
- owner coverage spot check：
  - `_runner_call_manifest.py`：`91%`，相关 owner/producer/query 用例 `259 passed`。
- targeted scans：
  - production hot producer/consumer 文件中 `projector_metadata_summary` 无匹配。
  - complete hot success fixture 不含 `diagnostic=None`；扫描到的三处 `None` 分别是 Tool Trace null-negative fixture，以及两个允许 complete manifest body diagnostic 为 null 的真实 shape fixture。
  - metadata-only manifest success fixture 无匹配；Tool Trace 大规模成功 fixture 使用真实 producer manifest。
- `git diff --check`：通过，无 whitespace error。

## 残余风险

- stress suite 暴露一次 active-cancel 传播时序波动；直接证据指向既有 S4 scheduler stress boundary，不与本次 runner-call/compact semantic owner 改动同源。按 scope 归类为后续 scheduler/stress work unit 的稳定性事项，不在本 S1 fix 中下游掩盖或扩展修复。
- fresh-schema contract 会对旧 hot row、metadata-only manifest 或不闭合 graph fail closed。这是本 gate 明确要求的行为，不提供兼容 shim；部署前若存在历史数据，需要由独立 deployment preflight/work unit 处理，不属于当前 code fix。
- S2-S8 lifecycle/admin/scheduler 行为未在本次实现中评审或修改，继续由后续已批准 slice 覆盖。

accepted findings 已全部修复，无未分类的 S1 residual。未 commit、push、创建 PR 或启动 re-review。
