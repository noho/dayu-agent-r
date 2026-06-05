# WU-CM-01 Slice C Implementation Blocker

## Gate

- Work unit: WU-CM-01 Conversation Memory overall optimization.
- Gate: Slice C implementation gate.
- Design source: `docs/host/design.md`.
- Plan source: `docs/host/wu-cm-01-conversation-memory-plan.md`.
- Boundary commit: `b892b773`.
- Result: **blocked after partial typed-contract attempt**.

## 动机判断

动机成立，严重性评估正确。Slice C 不是字段改名，而是把 Host Conversation Memory 从旧 `pinned_state` / `working_assumptions` / `stable_input` / `history_input` 语义，收敛为设计真源中的五类 session semantic memory：

- Trace Memory。
- Evidence / Fact Memory。
- Session Summary Memory。
- Answer Anchor Memory。
- Forward Intent Memory。

如果保留旧字段 alias、旧 snapshot bridge、旧 compact material wrapper 或旧 config alias，会让 Host 的 EventLog read model 和 prompt assembly 继续混用两套 contract，违反计划中的 no-compat 约束。

## 已尝试的最小补丁

本轮按用户要求先做了小步 typed-contract patch 和部分 direct consumer patch，未提交：

- `dayu/host/memory.py`：引入 `MemoryProjectionPolicy` vNext 字段、`ConversationMemorySnapshotVNext` 与五类 section dataclass，删除旧 `ConversationMemorySnapshot` / `PinnedStateView` / `WorkingAssumptionView` / `ConversationContinuity*` 生产定义。
- `dayu/runtime/config_loader.py`、`dayu/service/host_assembly.py`、`dayu/config/execution_profiles.json`：切换到 vNext `memory_projection_policy` 字段集合。
- `dayu/host/durable/memory.py`、`dayu/host/run_input.py`、`dayu/host/compact_material.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`：迁移了部分直接读取 vNext snapshot / policy 的生产路径。

局部生产类型检查曾通过：

```bash
source .venv/bin/activate
python -m pyright dayu/host/memory.py dayu/host/durable/memory.py dayu/host/run_input.py dayu/host/compact_material.py dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/context_fallback.py dayu/host/context_governance.py dayu/runtime/config_loader.py dayu/service/host_assembly.py
```

但这个结果不构成 Slice C completion，因为测试和 compact contract 生产入口尚未闭合。

## Blocker

Slice C 无法在当前 implementation gate 内继续用小补丁完成，根因是当前仓库仍保留 Slice A/B 的旧 compact production contract，而 Slice C 要求删除旧 snapshot / policy / material shape 后形成 pyright-clean vertical closure。

直接证据：

- `dayu/host/compaction.py` 仍定义旧 `CompactMaterialPack.stable_input`、`history_input`、`evidence_input`，以及旧 `CompactMaterialBlockKind`。
- `dayu/host/compaction.py` 仍定义并导出旧 `CompactionCandidate`、`MinimumPreserveItemCandidate` 和 `pinned_state_patch_candidate`。
- `dayu/host/llm_compaction.py` 的 production `compact()` 仍返回旧 `CompactionCandidate`，并解析 `pinned_state_patch_candidate`。
- `dayu/host/context_governance.py` 的旧 `check_compaction_candidate()` 仍读取 `candidate.pinned_state_patch_candidate`，并遍历 `request.material_pack.stable_input + request.material_pack.history_input`。
- 受影响测试仍大量直接绑定旧 contract：`tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_compact_material.py` 仍导入旧 snapshot / policy / continuity / pinned / working assumption 类型。

激活 venv 后运行受影响 pyright：

```bash
source .venv/bin/activate
python -m pyright dayu/host/memory.py dayu/host/durable/memory.py dayu/host/run_input.py dayu/host/compact_material.py dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/context_fallback.py dayu/host/context_governance.py dayu/runtime/config_loader.py dayu/service/host_assembly.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py
```

结果：`138 errors`。错误不是环境噪声，而是旧 contract 被删除后，测试和 compact material consumer 仍引用旧符号与旧字段，例如：

- `ConversationMemorySnapshot`、`PinnedStateView`、`WorkingAssumptionView`、`ConversationContinuity*` unknown import。
- `MemoryProjectionPolicy(max_evidence_backed_facts=..., recent_raw_turns_floor=...)` 不再是合法构造。
- `snapshot.pinned_state`、`snapshot.working_assumptions`、`snapshot.conversation_continuity` 不再存在。
- `MemoryIncludedReason.WORKING_ASSUMPTION`、`RECENT_RAW_TURN`、`MINIMUM_PRESERVE_ITEM`、`EPISODE_SUMMARY` 不再存在。

继续实现需要同时重写 compaction production contract、LLM parser、context governance、compact material pack、RunInputBuilder tests、memory projection tests 和 compact material tests。这已经越过“不要整文件一次性重写、以小补丁可检查推进”的策略，也越过 Slice C 对 `llm_compaction.py` 的允许边界。

## 最小修复建议

建议不要在当前 Slice C gate 里继续硬推。最小可维护路径是先补一个前置 fix gate：

1. 回到 Slice A/B closure，删除或迁移旧 production `CompactionCandidate` 路径，使 `ContextCompactor.compact()`、LLM parser、quality gate、`CompactMaterialPack` 和 event payload 全部只使用 vNext compact input/output。
2. 单独迁移 `tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_compact_material.py` 到 vNext compact contract，并跑通 pyright。
3. 再重新进入 Slice C，只迁移 memory snapshot、durable projection、RunInputBuilder、dispatch、config/service 和对应 tests。

如果 Controller 坚持当前 gate 合并完成，则需要显式扩大 implementation scope 到 `dayu/host/llm_compaction.py` 和旧 compact contract tests，并接受这是跨 Slice A/B/C 的大迁移，不再是 Slice C 小补丁实施。

## README 同步

本轮没有完成可验证 implementation，因此没有更新 README。当前已有代码差异触发了 `dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md` 的同步条件，但在 blocker 状态下不应写成已落地稳定事实。

## 验证

已运行：

- `source .venv/bin/activate && python -m pyright ...` 受影响生产 + 测试文件，结果 `138 errors`。
- `rg` 检查旧 compact contract / old snapshot / old policy 残留。

未运行 pytest。原因是 pyright 已在受影响测试入口失败，继续跑 pytest 只能得到同源 import / constructor 错误。

## 当前风险

- 工作区存在未提交的 partial implementation diff，不能作为完成态使用。
- partial diff 删除了旧 memory production contract，但旧 compact production contract 和测试未闭合；在继续前应由 Controller 决定是回滚 partial diff 后执行前置 Slice A/B fix，还是扩大 scope 继续跨 slice 完成。
- 未执行 README 同步，因为当前状态是 blocker，不是稳定实现。
