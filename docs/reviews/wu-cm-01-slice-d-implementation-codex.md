# WU-CM-01 Slice D Implementation - Codex

## Gate / Scope

- Gate: Slice D implementation gate
- Work unit: WU-CM-01 Conversation Memory overall optimization
- Slice: Public Smoke And Docs Closure
- Design source: `docs/host/design.md`
- Plan source: `docs/host/wu-cm-01-conversation-memory-plan.md`
- Accepted prerequisite commit: Slice C `29c86355`
- Artifact path: `docs/reviews/wu-cm-01-slice-d-implementation-codex.md`

## 动机判断

Slice D 动机仍成立，但性质是 closure / smoke hardening，不是继续迁移生产 Host。

直接证据：

- `docs/host/design.md` 24.7 要求 WU-CM-01 至少保留 empty / non-empty compacted view、post-compact delta、compact boundary、protected recent floor、deterministic bounded projection、provider context fallback、strict source-label / schema / provenance / whole-candidate repair、fallback no high-order memory 和 compact roll-forward 的可断言入口。
- Slice C 已把 `MemoryProjectionPolicy`、snapshot、RunInputBuilder、config README、Host README 和 tests README 迁移到 vNext；本 slice 复核后未发现需要继续修改生产 Host / Runtime / Service 代码。
- 初次运行默认 smoke 暴露 `workspace/.dayu/host/dayu_host.sqlite3` 中旧 schema 会阻断手工 smoke。按 schema 变更约束，正确做法不是旧库兼容读取，而是让手工 smoke 默认使用 fresh workspace。
- `tests/host -q` 暴露 `tests/host/test_purge_session.py` 的 seed helper 仍写旧 `raw_user_turn` item kind；根因是测试夹具没有跟随 Slice C durable memory item kind 迁移，不是生产回归。

## 修改文件

- `utils/smoke_host_public_conversation_memory.py`
  - 未显式传 `--workspace-root` 时默认使用 `workspace/tmp/host-public-conversation-memory-smoke-<id>` fresh workspace。
- `utils/smoke_host_public_conversation_memory_scenarios.py`
  - 未显式传 `--workspace-root` 时默认使用 `workspace/tmp/host-public-conversation-memory-scenarios-smoke-<id>` fresh workspace。
  - 将场景 smoke pressure reserve 从 `8192` 调整为 `160000` tokens，给 core suite 已累积 messages / memory / framing 留预算，避免 smoke 自身把 Host 推过 hard threshold。
- `utils/smoke_host_public_multiturn.py`
  - 未显式传 `--workspace-root` 时默认使用 `workspace/tmp/host-public-multiturn-smoke-<id>` fresh workspace。
- `README.md`
  - 同步三个手工 smoke 默认 fresh workspace 行为；说明需要复用 workspace / durable session 时显式传 `--workspace-root` 和必要的 `--reuse-session`。
- `tests/host/test_purge_session.py`
  - 将 purge seed memory item kind 从旧 `raw_user_turn` 迁移为 vNext `selected_recent_window`。

未修改：

- `dayu/host/README.md`：Slice C 后已描述 vNext memory / context governance 边界，本轮无新 Host 文档事实。
- `dayu/config/README.md`：字段说明已对齐 vNext `memory_projection_policy`，未发现旧 policy 字段残留。
- `tests/README.md`：当前 smoke / vNext memory 测试说明已覆盖本轮事实；本轮没有新增测试层级或维护规则。
- 生产 Host / Runtime / Service 代码：未修改。

## Doc / Smoke Re-check 证据

- 旧术语复核命令覆盖 `dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md`、`README.md`、三个 smoke 脚本、指定 public smoke / RunInputBuilder / memory tests 和 `test_purge_session.py`，未命中：
  - `working_assumptions`
  - `pinned_state`
  - `stable_layer` / stable layer
  - `history_pool` / history pool
  - `minimum_preserve` / minimum preserve
  - `max_working_assumptions`
  - `max_evidence_backed_facts`
  - `recent_raw_turns_floor`
  - `selected_recent_window_floor_turns`
  - `max_memory_items_per_category`
  - `max_text_chars_per_memory_item`
- 根 README 触发更新，因为 smoke 命令默认 workspace 行为变化。
- `dayu/config/README.md` re-check 结论：仍只描述 selected recent window、fallback selected recent window、evidence fact、session summary、answer anchor、forward intent、reference continuity、inline delta repair limits 与 `policy_ref`，未发现旧 memory policy 字段。

## Issue-80 / Design 24.7 Mapping 复核

当前 plan 中 Issue-80 / Design 24.7 mapping 仍成立：

- current scope covered 仍有测试 / smoke 入口：empty compacted view、non-empty compacted view、post-compact delta、compact boundary、protected recent floor、deterministic bounded projection、provider context length fallback、invalid / missing / stale source label、schema invalid、provenance mismatch、partial candidate invalid、fallback 不生成高阶语义、compact roll-forward。
- 本轮 public smoke 覆盖：
  - `smoke_host_public_conversation_memory.py`：public Host session continuity；本次真实 compactor schema repair 耗尽后 fallback continuity 通过。
  - `smoke_host_public_conversation_memory_scenarios.py`：多主体、多轮、压力和 compact artifact 路径通过。
  - `smoke_host_public_multiturn.py`：Service-like assembly、accepted compact、post-compact continuity 通过。
- 完整 eval benchmark 仍不是 WU-CM-01 Slice D scope；owner 保持 WU-CM-10 / GitHub Issue #80。

## Validation

已在 `source .venv/bin/activate` 后运行：

- `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q`
  - 结果：`64 passed, 1 skipped`
- `python utils/smoke_host_public_conversation_memory.py`
  - 结果：通过，输出 `SMOKE PASS public Host conversation memory finance continuity`
- `python utils/smoke_host_public_conversation_memory_scenarios.py`
  - 结果：通过，输出 `SMOKE PASS public Host conversation memory scenario smoke`
- `python utils/smoke_host_public_multiturn.py`
  - 结果：通过，输出 `SMOKE PASS public Host handle completed three-turn closure`
- `pytest tests/host/test_purge_session.py -q`
  - 结果：`28 passed`
- `pytest tests/host -q`
  - 结果：`1100 passed, 1 skipped, 5 deselected`
- `python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`

中间失败及裁决：

- 默认 `python utils/smoke_host_public_conversation_memory.py` 初次失败于旧 workspace DB schema mismatch。裁决为 smoke 默认 workspace 问题；已改为默认 fresh workspace，不做旧库兼容读取。
- `python utils/smoke_host_public_conversation_memory_scenarios.py` 初次失败于 smoke 压力文本导致 hard threshold before dispatch。裁决为 smoke pressure 预算问题；已调低场景 smoke 压力并重跑通过。
- `pytest tests/host -q` 初次失败于 `test_purge_session.py` 旧 `raw_user_turn` seed。裁决为测试夹具迁移遗漏；已改为 vNext `selected_recent_window` 并重跑通过。

## Residual Risk Owner 状态

- 完整 Conversation Memory eval benchmark：deferred-with-owner，WU-CM-10 / GitHub Issue #80。
- Cross-session User Profile Memory：deferred-with-owner，WU-CM-11 / GitHub Issue #115。
- Deep historical recall / semantic search / vector recall / reranker / recall tool：deferred-with-owner，GitHub Issue #39。
- Provider-specific tokenizer adapter：deferred-with-owner，后续 Context Governance 精确预算 work unit。
- Fins fact grounding integration：deferred-with-owner，Fins integration work unit。
- 默认项目根 `workspace/.dayu/host/dayu_host.sqlite3` 仍可能是旧 schema：不作为代码兼容风险；按 fresh schema 约束，手工 smoke 默认不再使用该旧库。显式 `--workspace-root` 指向旧库时仍会 fail closed，owner 是调用方 workspace 重建 / 清理动作。

## 未覆盖风险

- 本轮不实现完整 offline eval runner、metrics aggregation、LongMemEval / PersonaMem adapter。
- 本轮 smoke 使用真实 provider，结果仍受 provider 可用性、临时 schema-following 质量和外部响应时间影响；pytest 中 deterministic fake compactor 仍是稳定回归入口。
- 默认 fresh smoke workspace 会在 `workspace/tmp/` 保留 artifacts；脚本语义是不删除 Host/runtime artifacts，清理由人工或后续 workspace maintenance 处理。

## Completion Status

Slice D implementation complete。无 blocking open question；未进入 review gate、未 commit、未 push、未 PR。
