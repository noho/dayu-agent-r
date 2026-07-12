# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S1 Implementation - AgentCodex

## Status

`ready-for-code-review`

本次只完成 S1 implementation/fix。未进入 S2-S8，未执行 code review、commit、push、PR，也未修改 control doc。

实施依据：

- accepted plan commit：`4a282850`
- control-doc plan acceptance commit：`41bd6ca9`
- branch / pre-edit HEAD：`phaseflow/host-issues-control` / `41bd6ca9`
- plan truth：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`
- design/control truth：`docs/host/design.md`、`docs/engine/design.md`、`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`

## Schema Feasibility Pre-check

在第一次代码编辑和第一次 `apply_patch` 前，已按计划原样执行：

```bash
source .venv/bin/activate
rg -n "host_sqlite_payloads|payload_format|payload_json|payload_size_bytes|payload_digest" dayu/host/durable/schema.py
rg -n "payload_descriptors|payload_ref|payload_kind|payload_size_bytes|payload_digest|sqlite_payload_id" dayu/host/durable/schema.py
rg -n "SELECT payload_json|TABLE_SQLITE_PAYLOADS|read_payload_descriptor" dayu/host/payload_resolution.py dayu/host/durable/tool_trace.py
```

直接证据：

- `dayu/host/durable/schema.py:44` 定义 `host_sqlite_payloads`；`:372-378` 同时存在 `payload_format`、`payload_json`、`payload_size_bytes`、`payload_digest`。
- `dayu/host/durable/schema.py:45` 定义 `payload_descriptors`；`:394-401` 同时存在 `payload_ref`、`payload_kind`、`payload_digest`、`payload_size_bytes`、`sqlite_payload_id`。
- 编辑前 `dayu/host/payload_resolution.py:175,186-187` 在同一个传入 transaction 内先 `read_payload_descriptor(...)`，再按 `sqlite_payload_id` 查询 `host_sqlite_payloads`。
- 编辑前 `dayu/host/durable/tool_trace.py:464,503-504` 具有相同的同 transaction descriptor/row 读取身份。

结论：所需列与 same-transaction resolver identity 均存在，S1 不需要 schema 变更。未新增 DDL、`user_version`、migration、旧数据 compatibility 或 partial integrity fallback；pre-check 无 blocker，因此没有触发 `blocked-return-to-plan-review-before-code-edit`。

## Owner Contract Summary

### 1. Runner-call manifest / hot owner

- 新增私有 owner `dayu.host._runner_call_manifest`，统一承载：
  - fixed-shape `RunnerCallHotAtoms`；
  - fixed-shape `RunnerCallHotDiagnostic`；
  - complete / parsed diagnostic validation；
  - 唯一 hot payload projection；
  - 完整六字段 `RunnerCallProjectorMetadata` descriptor projection。
- ordinary RunInput、Engine continuation 与 compactor producer 全部委托该 owner；hot payload 不再复制 `projector_metadata_summary`，也不含任何随 message count 增长的数组。
- runner-call projection ref / digest / size 必须三项同时存在或同时缺失；digest、数量、identity 与 diagnostic status 在 owner boundary fail closed。
- 六字段 projector metadata 固定为 `projector_metadata_id`、`projector_id`、`projector_schema_version`、`projector_digest`、`purpose`、`source_contract_refs`。compactor 已移除旧 `metadata_id`，显式提供 schema version 与 source refs，不使用默认版本或 fallback。
- 完整 messages 保留在 cold runner-call projection descriptor；完整 projector metadata 保留在 manifest descriptor。EventLog / Tool Trace hot row 只保存 fixed scalar / diagnostic atoms。
- Tool Trace hot projection 不消费旧数组；query 在同一 durable transaction 中从 digest-verified manifest 重建五字段 `ProjectorMetadataSummary`，并校验完整六字段集合、digest、source refs 与 metadata id 唯一性。

### 2. Durable JSON descriptor/content integrity owner

- 新增 `dayu.host.durable.payload_resolution.resolve_json_payload(...)` 作为 JSON descriptor 完整性唯一 owner。
- SQLite 路径同时校验：
  - requested ref 与 descriptor ref；
  - caller digest 与 descriptor digest；
  - descriptor kind / payload id；
  - row id / format / digest / size；
  - 实际 canonical bytes digest / size；
  - UTF-8、JSON object shape 与 exact canonical encoding。
- artifact 路径复用 `read_artifact_bytes(...)` 的 namespace / containment / digest / size 校验，并继续验证 UTF-8、JSON object 与 canonical encoding。
- `dayu.host.payload_resolution` 与 `dayu.host.durable.tool_trace` 均委托该 owner；已删除各自只读取 `payload_json`、只比较部分 digest 的重复 resolver。
- owner 保持调用方 transaction，不引入跨 transaction descriptor/content split。

### 3. Effective execution snapshot integrity

- `effective_execution_snapshot_from_json(...)` 在反序列化 typed runner/options/policy 前重算 `sha256(config)`。
- 同时要求 `policy_snapshot_digest == sha256(config)` 且 `policy_snapshot_ref == "policy:" + digest`；config、digest 或 ref 任一篡改均抛 `HostDurableError`。

### 4. Compact evidence provenance

- accepted evidence envelope 存在时，compact material 必须取得显式 `tool_call_requested_event_ref`。
- 共享 accepted-result projection 必须证明目标是 canonical `TOOL_CALL_REQUESTED` 且 request/result identity 一致；缺 ref、目标为 result event、目标类型错误或 identity mismatch 均 fail closed。
- 已删除把 `TOOL_RESULT_ACCEPTED row.event_id` 伪装成 call ref 的 fallback。

### 5. Production stress oracle

- DR-006 修复后，stress 的第 12 个合法 runner call 已能在现有 inline limit 下被 worker 接受；测试在 gap/reconnect 阶段前显式断言 accepted count 为 12。
- reconnect watcher 是 live-cursor 契约。测试在 attach reconnect watcher 前等待 gap runs terminal durable，避免把尚在 ingest 的旧 gap terminal 误判成 reconnect 后事件；未修改 production watch、scheduler 或 lifecycle 实现。

## Changed Files and Scope Audit

以下全部位于 S1 allowed list；除本 implementation artifact 外没有越界文件。

Production code：

- `dayu/host/_runner_call_manifest.py`（新增）
- `dayu/host/durable/payload_resolution.py`（新增）
- `dayu/host/run_input.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compaction_operation.py`（仅 runner-call manifest/hot producer）
- `dayu/host/tool_trace.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/_execution_config_projection.py`
- `dayu/host/compact_material.py`

Tests：

- `tests/host/test_payload_store.py`
- `tests/host/test_effective_execution_config.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_terminal_payload.py`
- `tests/host/test_host_production_stress.py`
- `tests/host/test_runner_call_hot_payload_contract.py`（新增）
- `tests/host/test_durable_payload_integrity.py`（新增）

Docs：

- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-implementation-codex.md`（本报告）

`dayu/host/__init__.py` 未修改：新 owner 是 Host 私有实现契约，不需要 package export。`dayu/host/durable/payload.py` 无需修改。scheduler、Host opener/admin actor、wait、compaction cancellation scope的非 producer 部分、Engine provider、context budget、CLI/config/R3-F、Fins 与 control docs 均未修改。

## Test Coverage Added or Updated

- hot owner matrix：ordinary / continuation / compactor 对 0 / 1 / 12 / 300 messages 使用完全相同 hot keys；无 list；小于 4096 bytes；message count 从 0 到 300 时只允许数值位数造成的固定小差异。
- actual manifest producers：ordinary、continuation、compactor 均断言完整六字段 metadata；compactor 断言无旧 `metadata_id` 且 source refs 非空。
- 300-message cold path：manifest 通过 ref/digest 解析；Tool Trace query 从 verified descriptor 恢复 300 条五字段 summary，而 hot row 不复制数组。
- durable tamper matrix：SQLite `payload_json`、row digest、row size、descriptor digest、descriptor size、descriptor ref、错误 SQLite payload id、非 canonical JSON、非 object JSON、caller digest split 全部 fail closed；artifact containment、实际 digest 与实际 size 分别篡改均 fail closed。
- effective config tamper matrix：config、policy snapshot digest、policy snapshot ref 分别篡改均 fail closed。
- compact provenance matrix：正确 request ref 保持；缺 ref、ref 指向 result event、跨 identity ref 全部 fail closed。
- terminal/outbox/evidence/Tool Trace 既有 resolver regression 随共享 owner 一并验证。

## Validation Results

Required focused command：

```bash
source .venv/bin/activate
pytest tests/host/test_payload_store.py tests/host/test_effective_execution_config.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_compact_material.py tests/host/test_terminal_payload.py tests/host/test_outbox_projection.py tests/host/test_runner_call_hot_payload_contract.py tests/host/test_durable_payload_integrity.py -q
```

结果：`406 passed in 2.73s`。

Production stress：

```bash
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
```

结果：`5 passed in 6.72s`；runner-call stress 在后续 gap runs 前显式断言 accepted count 为 `12`。

Type check：

```bash
python -m pyright dayu/host/ tests/host/
```

结果：`0 errors, 0 warnings, 0 informations`。

Source scans：

```bash
rg -n "projector_metadata_summary" dayu/host/run_input.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/tool_trace.py
```

结果：零命中（`rg` exit 1，符合预期）。

```bash
rg -n "projector_metadata_id|projector_schema_version|source_contract_refs" dayu/host/_runner_call_manifest.py dayu/host/run_input.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/tool_trace.py
```

结果：exit 0；shared owner、ordinary、continuation、compactor 均有 typed 六字段命中。`tool_trace.py` 不再写 hot summary。

```bash
rg -n "tool_call_event_ref = row\.event_id" dayu/host/compact_material.py
```

结果：零命中（`rg` exit 1，符合预期）。

```bash
git diff --check
```

结果：通过。

## README / Design Trigger Decisions

- 已先读取 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。本次新增当前已实现且稳定的 Host 私有 runner-call owner、durable resolver 与 Tool Trace query boundary，属于 Host package developer contract，因此更新该 README；未写 work-unit 流水账或测试命令。
- `tests/` 发生修改并新增 owner-level test layer，因此更新 `tests/README.md`，记录 fixed-hot、durable integrity、300-message query 与 stress 5/5 / accepted-12 契约。
- `docs/host/design.md` 是本 work unit 的 Host 设计真源，且 runner-call hot/cold、payload integrity、effective config 与 compact provenance contract 已实际落地，因此同步更新。
- 未更新根 `README.md`：没有用户可见安装、CLI/Web/WeChat、命令参数、日志或 workspace workflow 变化。
- 未更新 `dayu/README.md`：没有改变 `UI -> Service -> Host -> Engine` 分层或装配边界。
- 未更新 Engine、Config 或 Fins README：没有修改对应目录或其稳定契约。

## Residual Risks / Uncovered Items

- 按 fresh-schema 与 S1 明确约束，不提供旧数据 compatibility。已有损坏 descriptor、row 或 artifact 会在读取时 fail closed；部署前坏数据审计属于后续运维动作，不在本 slice 增加 fallback。
- Tool Trace 对 300 条 metadata 的完整解析发生在显式 read-only query 路径，不在 EventLog append 或 hot projection 路径；该 cold query 的成本已被 owner test 覆盖，但本 slice 不引入分页 metadata 子协议。
- 本次只验证 S1 required focused suite 与 production stress；S2-S8 的 opener、scheduler、recovery、cancel、wait、compaction cancellation 和 runtime cleanup 风险保持原计划状态，未在本实现中提前修改或裁决。

## Stop Status

`ready-for-code-review`

S1 implementation 已完成且 required validation 全部通过；按 gate 约束在此停止，等待独立 code review。
