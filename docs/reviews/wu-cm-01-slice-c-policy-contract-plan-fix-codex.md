# WU-CM-01 Slice C Policy Contract Plan Fix - Codex

## Gate Status 与结论

- Gate: WU-CM-01 Slice C policy contract plan fix gate
- Branch: `phaseflow/wu-cm-01`
- Status: plan fix completed / ready for controller adjudication
- Changed files:
  - `docs/host/wu-cm-01-conversation-memory-plan.md`
  - `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-codex.md`
- Commits: no commit, no push, no PR
- Production code / tests / README: not modified

结论：blocker 动机成立，controller 裁决正确。后续 Slice C implementation prompt 必须以 `docs/host/design.md` 的 `memory_projection_policy` 为唯一 policy contract 真源；不得使用上一轮 retry prompt 中的 generic policy shape，也不得通过 alias、wrapper、兼容读取、默认补齐、extra payload 或双字段真源绕过冲突。

## Blocker 动机和 Root Cause 裁决

第一性原理判断：Slice C 的目标是关闭 memory snapshot、projection、durable row、RunInputBuilder、dispatch、runtime config、Service assembly 与 tests 的同源契约，不是只替换 `memory.py` 字段。policy 字段如果不先统一，implementation 只能在“偏离设计真源”和“与 prompt 冲突”之间二选一；在本项目禁止 alias / compatibility wrapper 的约束下，这是 blocker，不是可在代码中局部修补的问题。

直接证据：

- `docs/host/design.md` 第 3 章 `memory_projection_policy` 明确要求 `selected_recent_window_turn_floor` 与 per-section item / char cap / floor 字段集合。
- `docs/host/design.md` 第 24.6 章进一步说明需要 floor 的 section 固定为 `selected_recent_window_turn_floor` 与 `evidence_fact_floor`，`reference_continuity_item_floor = 0` 可以显式进入配置。
- `docs/reviews/wu-cm-01-slice-c-implementation-retry-codex.md` 记录上一轮 retry prompt 要求 `selected_recent_window_floor_turns`、`max_memory_items_per_category`、`max_text_chars_per_memory_item`、`projection_max_repair_attempts`、`projection_max_rebuild_rows`、`projection_max_catchup_rows`。
- `docs/reviews/wu-cm-01-slice-c-implementation-retry-blocker-controller-adjudication.md` 已裁决上述 retry prompt 字段与设计真源冲突，且不接受 alias、旧字段兼容读取、默认补齐、wrapper/facade 或 extra payload。
- 当前代码仍是旧 policy / snapshot consumer graph：`dayu/host/memory.py` 仍定义 `DEFAULT_MEMORY_MAX_EVIDENCE_BACKED_FACTS`、`DEFAULT_MEMORY_MAX_WORKING_ASSUMPTIONS`、`DEFAULT_MEMORY_RECENT_RAW_TURNS_FLOOR`、`history_pool_*`、`stable_layer_*` 等旧 policy 常量；`dayu/service/host_assembly.py` 仍把 runtime config 映射为 `max_evidence_backed_facts`、`max_working_assumptions`、`recent_raw_turns_floor`；`dayu/runtime/config_loader.py` 的 typed config view 仍含这些旧字段。因此后续 Slice C 必须同步迁移 direct consumers，不能只改 Host policy dataclass。

root cause：上一轮 implementation prompt 的 `MemoryProjectionPolicyVNext` 字段集合与设计真源、已接受 plan 不一致，导致 AgentCodex 在 `dayu/host/memory.py` partial draft 中选择了错误 contract。该草稿不得继续作为后续 implementation 基础。

## Plan 修改摘要

已修正 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- 在 Slice C 前置说明中新增 policy contract blocker 裁决，明确 `docs/host/design.md` 是唯一真源。
- 明确禁止 `selected_recent_window_floor_turns`、`max_memory_items_per_category`、`max_text_chars_per_memory_item`、`projection_max_repair_attempts`、`projection_max_rebuild_rows`、`projection_max_catchup_rows` 进入 production dataclass、config JSON、typed config view、Service assembly、tests 或 README。
- 将 `engine_ingest.py` 的 recent-window floor 迁移边界收敛为只能从旧 `recent_raw_turns_floor` 迁到 `selected_recent_window_turn_floor`，删除“或本 slice 明确的新字段”的歧义。
- 在 Slice C 实现边界中补充 hard requirement：production dataclass、`execution_profiles.json`、runtime typed config view、Service assembly 与 tests 必须使用完全相同的 design-source 字段集合。
- 新增 direct consumer closure list，明确 Host policy、durable/projection、compact material、RunInputBuilder、dispatch/ingest、Runtime config、Service assembly 与 tests 的同步迁移边界。

## 最终 Slice C Policy Field List

后续 Slice C implementation prompt 必须使用以下字段，且字段名必须逐字一致：

```text
context_window_size
selected_recent_window_item_cap
selected_recent_window_char_cap
selected_recent_window_turn_floor
fallback_selected_recent_window_item_cap
fallback_selected_recent_window_char_cap
evidence_fact_item_cap
evidence_fact_char_cap
evidence_fact_floor
session_summary_char_cap
answer_anchor_item_cap
answer_anchor_char_cap
forward_intent_item_cap
forward_intent_char_cap
reference_continuity_item_cap
reference_continuity_char_cap
reference_continuity_item_floor
max_lag_events_for_inline_delta
max_delta_repair_events
policy_ref
```

禁止字段：

```text
selected_recent_window_floor_turns
max_memory_items_per_category
max_text_chars_per_memory_item
projection_max_repair_attempts
projection_max_rebuild_rows
projection_max_catchup_rows
max_evidence_backed_facts
max_working_assumptions
recent_raw_turns_floor
history_pool_*
stable_layer_*
```

## Direct Consumer Closure 与 Matrix

direct consumer closure list 已补入 plan，需要调整。原因是原 plan 虽已有正确字段清单，但缺少对 retry prompt generic shape 的显式拒绝，也缺少把 dataclass、JSON、typed config view、Service assembly 与 test fixture 绑定为同一字段集合的硬约束。

allowed file matrix 不需要扩大。Slice C 仍限制在 plan 已列文件内：Host memory/durable/projection/RunInputBuilder/dispatch/ingest、`dayu/service/host_assembly.py`、`dayu/runtime/config_loader.py`、`dayu/config/execution_profiles.json` 与对应 tests。Pre-Slice C compact contract closure 的 allowed files 也不因本 gate 改变。

test matrix 不需要新增命令，但后续 implementation 必须在既有 Slice C 测试批次中加入字段级断言：runtime config 旧 key 与 generic retry key fail fast，Service assembly 一对一映射 design-source field，Host policy dataclass / digest 不包含旧字段或 generic fields。

## Stop Conditions 和 Required Validation

后续 Slice C implementation stop conditions：

- implementation prompt 或代码尝试使用 `selected_recent_window_floor_turns`、generic item/text cap、projection rebuild/catchup generic fields，必须停止并回到 plan/design gate。
- 发现 `docs/host/design.md` 的 `memory_projection_policy` 字段不足以实现需求，必须停止；本 gate 不授权修改 design source。
- 需要 alias、compatibility wrapper、旧 config key 兼容读取、旧 snapshot bridge、extra payload 或 raw dict patch 才能 pyright-clean，必须停止。
- 直接 consumer 无法在同一 Slice C 内 pyright-clean closure，必须停止并重新裁剪 slice，不得只更新 tests 或 README。

required validation for next implementation：

```bash
source .venv/bin/activate
pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_durable_concurrency_matrix.py tests/host/test_memory_repair.py -q
pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_engine_ingest_mapping.py -q
pytest tests/host/test_admission_queue.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py -q
pytest tests/service/test_host_assembly.py tests/runtime/test_config_loader.py -q
pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q
python -m pyright dayu/ tests/ utils/
```

README validation remains owned by later implementation / Slice D per plan trigger rules; this gate did not modify README because no code behavior changed.

## 本 Gate 未运行测试 / Pyright 的原因

本 gate 只修正文档计划和 review artifact，不做生产代码、测试或 README 实现。运行 pytest 或 pyright 不能验证本次文档 contract fix，且当前代码仍处于旧 memory policy / snapshot implementation 状态，会产生与本 gate 无关的旧-contract 噪音。因此本 gate 未运行测试和 pyright；后续 implementation gate 必须按上方 required validation 执行。

## Residual Risks

- 后续 Slice C 仍是较大的 memory durable/projection、prompt assembly、config-service vertical closure；分类为 covered by later approved slice。
- README 同步、public smoke 与 issue-80 映射复核仍由 Slice D 处理；分类为 covered by later approved slice。
- 完整 Conversation Memory eval benchmark、User Profile Memory、deep historical recall / search 仍按原 plan deferred owner 处理。
