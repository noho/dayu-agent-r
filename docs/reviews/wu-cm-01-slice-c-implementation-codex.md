# WU-CM-01 Slice C Implementation Blocker

## 动机判断

动机成立。Host 设计真源第 24/25 章要求 Conversation Memory 是可重建、可审计、bounded 的 EventLog read model，accepted vNext `CONTEXT_COMPACTED` 才能物化高阶 session memory；fallback、rejected、failed compact 不得生成 session summary、fact、answer anchor、forward intent 或 reference continuity。当前 `dayu/host/memory.py` 与 `dayu/host/durable/memory.py` 仍保留旧 `pinned_state`、`working_assumptions`、旧 continuity item kind、旧 policy 字段和旧 snapshot JSON shape，问题真实存在且严重性评估成立。

## Blocker

本 Slice C 无法在给定 allowed files 内形成 pyright-clean closure，必须停止，不应越界实现。

直接证据：

- `dayu/host/run_input.py` 仍直接读取 `ConversationMemorySnapshot.pinned_state`、`evidence_backed_facts`、`working_assumptions`、`conversation_continuity.items` 并渲染旧 stable memory block；但 Slice C allowed files 不包含 `dayu/host/run_input.py`，且用户明确要求不得实施 Slice D。
- `dayu/host/compact_material.py` 仍直接读取旧 snapshot 字段构造 previous compacted view / stable blocks；但 Slice C allowed files 不包含 `dayu/host/compact_material.py`。
- `dayu/host/dispatch.py` 仍在 dispatch memory precondition 路径读取 `snapshot_row.snapshot.evidence_backed_facts`；但 Slice C allowed files 不包含 `dayu/host/dispatch.py`。
- `dayu/service/host_assembly.py` 与 `dayu/runtime/config_loader.py` 仍以旧 `MemoryProjectionPolicy(max_evidence_backed_facts, max_working_assumptions, ...)` shape 装配 policy；但 Slice C 禁止修改 `dayu.service`，且 runtime config loader 不在 Slice C allowed files。
- 多个非 Slice C 测试仍构造或断言旧 snapshot / policy shape，例如 `tests/host/test_run_input_builder.py`、`tests/host/test_compact_material.py`、`tests/service/test_host_assembly.py`、`tests/runtime/test_config_loader.py`、`tests/host/test_admission_queue.py`、`tests/host/test_toolruntime_accept_barrier.py`、`tests/host/test_resolve_wait_command.py`。Slice C allowed test files 不覆盖这些 pyright/type closure consumers。

根因不是实现难度，而是 slice 边界与当前 production consumer 图不一致：若在 allowed files 内删除旧 snapshot/policy 字段，全量 `python -m pyright dayu/ tests/ utils/` 会在禁止修改的 consumers 上失败；若保留旧字段、旧 property、旧 alias 或 bridge helper，则违反 Slice C 明确禁止的旧字段 fallback codec、compat wrapper/facade/re-export、旧 snapshot -> vNext bridge helper，以及“旧字段不得作为 snapshot 顶层语义保留”的约束。

## 未实施修改

未修改生产代码、未迁移 tests、未更新 README。唯一写入是本 blocker artifact。

## 验证

未运行 Slice C 测试与 pyright。原因是实现前已经通过静态引用核对确认 allowed-files 不足，继续修改会在禁止越界和 pyright-clean 要求之间形成不可满足约束。

## README 决策

未更新 README。当前没有生产代码或测试行为落地变化；写 README 会把未实现状态写成稳定事实，违反 README 同步规则。

## Residual Risks

- WU-CM-01 Slice C 需要重新裁决 allowed files 或重新切 slice。至少要把直接 production consumers 的迁移 owner 纳入同一 pyright-clean closure，或明确调整 Slice C/D 的验收边界。
- 若仍要求 Slice C 单独删除旧 `ConversationMemorySnapshot` / `MemoryProjectionPolicy` shape，则必须允许同步处理 `run_input.py`、`compact_material.py`、`dispatch.py`、config/service assembly 与对应 tests；否则只能保留兼容桥，但这与当前 AGENTS.md 和 accepted plan 冲突。
