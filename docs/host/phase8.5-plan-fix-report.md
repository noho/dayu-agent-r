# P8.5 Plan Fix Report

- **work gate name**: fix
- **work-unit name**: P8.5 — P8 Stabilization / ToolRuntime Event Model
- **source review artifact path**: `docs/host/phase8.5-plan-review.md`
- **fixed plan path**: `docs/host/phase8.5-plan.md`
- **artifact path**: `docs/host/phase8.5-plan-fix-report.md`

## Scope

本轮只修 P8.5 plan 与设计 / migration 文档口径，不进入 implementation，不改生产代码或测试代码，不 commit。

Changed files:

- `docs/host/phase8.5-plan.md`
- `docs/host/design.md`
- `docs/host/migration-plan.md`
- `docs/host/phase8.5-plan-fix-report.md`

## Findings Fixed

### F01 — framework `fetch_more` schema 自动投影路径不够 handoff-ready

- **status**: fixed
- **fix**:
  - 在 plan §2.1 增加 Host 私有 framework schema 投影 owner 裁决：owner 是 Host runtime assembly，不是 Engine，也不是调用方。
  - 明确推荐新增 Host-private schema provider / protocol，例如 `EngineToolSchemaProvider`。
  - 明确 `HostToolRuntime` / runtime assembly 从私有 framework `ToolDefinition` 投影 `definition.to_tool_schema()`。
  - 明确 `_run_harness.py` / `_worker.py` / durable assembly 在构造 `AgentRunRequest` 前生成 enhanced tool schemas。
  - 明确 `StartRunRequest.options.tool_schemas` / `RunOptions` 不做 public in-place mutation。
  - 明确 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 记录 Engine 实际收到的 enhanced schemas。
  - Slice 1 allowed files 增加 `_worker.py`、`_run_harness.py`、`_durable_harness.py` 和 Host 私有 schema provider module。
  - Slice 1 tests 增加调用方只传业务 schema、Engine request 含 `fetch_more` schema、RunOptions 不被污染、Engine 不接收 definition/callable/manager 的断言。

### F02 — EventLog 保留 cursor / `scope_token` 后 memory / RunInput capability 边界未定义

- **status**: fixed
- **fix**:
  - 在 plan §2.1 增加 Memory / RunInput capability ingestion policy。
  - 明确 EventLog / trace 保留 ordinary payload；Conversation Memory / RunInput 是独立 ingestion policy。
  - 明确 ordinary `TOOL_RESULT_ACCEPTED` 中的 raw cursor、raw `scope_token`、`truncation.fetch_more_args` 只生成安全摘要，不进入长期 memory 或下一轮 RunInput。
  - Slice 1 allowed files 增加 `_conversation_memory.py`。
  - Slice 1 tests 增加 EventLog / trace 可见 raw payload，但 memory snapshot / RunInput rendered tool facts 不包含 raw cursor / raw `scope_token` 的断言。

### F03 — shared `ToolTruncationInfo` contract 未列入 impact

- **status**: fixed
- **fix**:
  - plan §5 / §6 / Slice 1 allowed files 增加 `dayu/contracts/tool_result.py` 与 contract tests。
  - plan §6 明确 `ToolTruncationInfo` 是 ordinary LLM-facing tool result payload 的一部分，可进入 EventLog / trace；不得进入 memory / 下一轮 RunInput / 普通日志 / README 大块输出。
  - Slice 1 instruction 要求更新 `ToolTruncationInfo` 文档并加 contract-level test。

### F04 — RunInput raw payload side store schema / API 留给 implementation 设计

- **status**: fixed
- **fix**:
  - plan §2.4 / §6 / Slice 4 固定 SQLite schema：
    `run_input_raw_payloads(blob_id, session_id, run_id, attempt_index, iteration_index, iteration_id, payload_kind, content_sha256, byte_size, payload_json, created_at)`。
  - 固定 `payload_kind` allowed values：`input_messages`、`tool_schemas`。
  - 固定 primary key、unique key 与索引。
  - 明确 `RunInputContextSnapshotBuiltData` 删除 inline raw json 字段，保留 blob id、hash、byte size。
  - 明确 writer owner 是 Host durable run input context fact append boundary，和 EventLog append 共用同一个 `HostStorage.transaction()`。
  - 明确 reader owner 是 Tool trace projection / debug reader。
  - 明确 missing / corrupt / hash mismatch row 触发 typed projection failure，required read path checkpoint 不推进，不合成 fake payload。
  - Slice 4 tests 增加 rollback 无 orphan row、blob 可读、hash mismatch / missing row typed failure 的断言。

### F05 — `design.md` 仍残留旧专属 fact / observer transaction 口径

- **status**: fixed
- **fix**:
  - plan §0 增加设计优先级声明：`docs/host/design.md` §11 与当前 plan supersede 旧 P2/P7/P8 wording。
  - `docs/host/design.md` §8.2 将 “ToolRuntime 产生的 truncate / cursor / fetch_more facts” 改为普通 tool calling facts，并说明 P8.5 后不再使用专属 RunEvent fact。
  - `docs/host/design.md` §9.4 将 P8-S2 observer 同事务语义标为 P8 前置实现事实，并写入 P8.5 non-required trace sink at-least-once / idempotency-key 去重口径。
  - plan Slice 6 仍保留最终文档 closeout，但不再把会误导 implementation 的冲突留到最后。

### F06 — Slice 3 非事务 trace observer 语义不足以直接实现

- **status**: fixed
- **fix**:
  - plan §2.3 和 Slice 3 明确 non-required trace JSONL/blob sink 是 at-least-once。
  - 明确 I/O success + checkpoint 前 crash / checkpoint failure 允许 replay duplicate，reader/analyzer 按 `idempotency_key` 去重。
  - 明确 checkpoint 只能在 sink success 后推进；sink failure 不推进 checkpoint；checkpoint failure 不得报告 success。
  - 明确 required observer 与 non-required observer failure status 分离，trace failure 不阻塞 required memory observer。
  - Slice 3 tests 增加 I/O success + checkpoint failure replay duplicate same idempotency key、I/O failure 不阻塞 required memory observer、checkpoint failure 不标 success。

### F07 — grep guard 会被历史 docs 命中

- **status**: fixed
- **fix**:
  - Slice 6 validation 拆成 production/current-doc guard 与 historical-doc audit guard。
  - production/current-doc guard 覆盖 `dayu`、`tests`、`dayu/host/README.md`、`tests/README.md`，只允许 negative forbidden-name tests 命中。
  - historical-doc audit guard 明确 `docs/host/migration-plan.md`、旧 review artifacts、本 plan 可作为历史 / residual context 命中旧名，不得为零命中删除审计上下文。

## Payload Policy Correction

- **status**: fixed
- **fix**:
  - `docs/host/migration-plan.md` §3 记录长期口径：Dayu 是本地 Agent；EventLog / trace ordinary tool payload 默认保留，只做窄 credential scrub；除 `API_KEY` / 明确凭证外，不因 cursor、`scope_token`、tool args 或 tool result 字段名删除或遮蔽。
  - plan 中统一使用 credential scrub / ordinary payload retention 口径，避免把 cursor / `scope_token` 描述为敏感字段。
  - design §11 对 EventLog payload policy 同步为窄 credential scrub。

## Validation

未运行 pytest / pyright；本轮是 docs-only plan fix，且用户明确要求不运行。

Manual checks performed:

- 阅读并对照 `docs/host/phase8.5-plan-review.md` 的 F01-F07。
- 检查 plan 中不再把 raw payload side-store schema 留给 implementation agent。
- 检查 design 中已清理与新版 §11 冲突的旧 ToolRuntime fact / observer transaction 口径。

## Open Questions

No blocking open questions.

Non-blocking watch item remains: credential scrub 必须保持窄定义；implementation agent 不得把 cursor、`scope_token`、普通 tool args/result 扩大解释为 credentials。
