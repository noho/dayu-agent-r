# WU-CM-01 Slice C Implementation Retry2

## Gate

- Work unit: WU-CM-01 Conversation Memory
- Gate: Slice C implementation
- Artifact path: `docs/reviews/wu-cm-01-slice-c-implementation-retry2-codex.md`
- Decision: implementation completed; no blocker; no commit / push / PR performed.

## Motivation / Root Cause Evidence

Slice C 动机成立。直接代码证据显示旧 memory contract 曾同时作为 policy、snapshot、durable item、RunInputBuilder prompt、runtime config 与 Service assembly 真源：`MemoryProjectionPolicy` 旧字段、旧 snapshot 顶层 `pinned_state` / `working_assumptions` / `conversation_continuity`、旧 RunInputBuilder memory headers、旧 config JSON keys、dispatch / engine ingest 中旧 floor 字段。

实现中另发现 durable root cause：`host_memory_items.item_kind` 与 diagnostics CHECK 仍限制旧 item kind / diagnostic reason，阻止真实 vNext item kind 写入。按用户纠偏，未保留旧 kind alias；扩展修改 `dayu/host/durable/schema.py`，将 CHECK 闭合到真实 vNext kind 与 diagnostic reason。该文件不在原 allowed list，但它是 durable schema 约束的直接 owner，否则只能通过旧 kind bridge 绕过。

## Production Summary

- `dayu/host/memory.py`：替换为 vNext policy / snapshot / projection contract。`ConversationMemorySnapshotVNext` 包含 `trace_memory`、`evidence_fact_memory`、`session_summary_memory`、`answer_anchor_memory`、`forward_intent_memory`、`diagnostics`；compact 前只生成 selected recent window；accepted vNext `CONTEXT_COMPACTED` 才物化 summary / facts / anchors / intents / reference continuity；accepted evidence 无 fact candidate 只记录 diagnostic。
- `dayu/host/durable/memory.py` 与 `dayu/host/durable/schema.py`：durable snapshot codec、item writer、diagnostic rows 与 CHECK 迁到 vNext。ProjectionRunner 仍负责在同一 transaction 内、consumer snapshot 写入之后推进 checkpoint，满足 snapshot/checkpoint 同事务且 checkpoint 不先于 snapshot。
- `dayu/host/run_input.py`、`dayu/host/compact_material.py`：RunInputBuilder 与 compact previous view 消费 vNext snapshot，渲染 Session Summary / Evidence Fact / Answer Anchor / Forward Intent / Reference Continuity / selected recent window。
- `dayu/host/context_fallback.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`：fallback / reactive pending floor 迁到 `selected_recent_window_turn_floor`，不保留旧字段 alias。
- `dayu/runtime/config_loader.py`、`dayu/service/host_assembly.py`、`dayu/config/execution_profiles.json`：runtime typed config、Service mapping、packaged defaults 全部迁到 design-source policy 字段；旧 config key fail fast。

## Tests / README

- 更新 memory projection、durable concurrency、compact material、RunInputBuilder、public smoke、runtime config、service assembly、public contracts 等测试到 vNext contract。
- 同步 `dayu/config/README.md`、`dayu/host/README.md`、`tests/README.md`，清理旧 stable layer / history pool / pinned-state memory 描述。

## Validation

All commands run with `source .venv/bin/activate`.

- `pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_durable_concurrency_matrix.py tests/host/test_memory_repair.py -q` -> `62 passed`
- `pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_engine_ingest_mapping.py -q` -> `167 passed`
- `pytest tests/host/test_admission_queue.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py -q` -> `59 passed`
- `pytest tests/service/test_host_assembly.py tests/runtime/test_config_loader.py -q` -> `66 passed`
- `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q` -> `10 passed, 1 skipped`
- Conditional: `pytest tests/host/test_public_contracts.py tests/host/test_public_tool_wiring_smoke.py -q` -> `42 passed`
- `python -m json.tool dayu/config/execution_profiles.json` -> valid JSON
- `python -m pyright dayu/ tests/ utils/` -> `0 errors`

## Residual Risk

- Durable schema was updated as an implementation-scope expansion because schema CHECK was the direct blocker for real vNext item kinds. Classification: fixed in current slice.
- Existing workspace migrations are not added because current schema policy treats this as fresh schema, not compatibility migration. Classification: fixed in current slice by fresh schema update.
- Real provider behavior beyond deterministic public smokes remains covered by existing optional real-runner smoke policy, not run here. Classification: tracked by existing optional smoke coverage.

## Completion Status

Slice C implementation is complete and pyright-clean. No blocker remains.
